/**
 * Loop News 反馈 API —— Cloudflare Worker。
 * 反馈存入 R2 桶(binding: BUCKET);常用词从 R2 的 config/feedback_tags.json 读,缺则用内置默认。
 * 端点(CORS 全开,任何设备/页面可调):
 *   GET  /health    健康检查
 *   GET  /tags      常用反馈词(弹窗 chips)
 *   POST /feedback  追加一条反馈(写 R2:fb/<ts>-<rand>.json)
 *   GET  /feedback  列出全部反馈(供 ln-evolve / 自查)
 * 部署见 CLOUDFLARE.md。
 */
const DEFAULT_TAGS = {
  up: ["有洞察", "信息密度高", "正是我想看的", "角度新颖", "证据扎实"],
  down: ["噪音/水文", "太旧了", "来源不可靠", "与我无关", "重复了"],
  adopt: ["已发微博/X", "已写进 newsletter", "已做视频选题", "已转发社群", "已存为选题库"],
};
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const ALLOWED = new Set(["up", "down", "adopt", "ask"]);

function validTokens(env) {
  try { return JSON.parse(env.SHARE_TOKENS || "{}"); } catch (_) { return {}; }
}
async function listAll(env, prefix) {
  const items = [];
  let cursor;
  do {
    const l = await env.BUCKET.list({ prefix, cursor });
    for (const o of l.objects) {
      const g = await env.BUCKET.get(o.key);
      if (g) { try { items.push(JSON.parse(await g.text())); } catch (_) {} }
    }
    cursor = l.truncated ? l.cursor : undefined;
  } while (cursor);
  return items;
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const p = url.pathname;
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (p === "/health") return json({ ok: true });

    if (p === "/tags" && req.method === "GET") {
      let tags = DEFAULT_TAGS;
      try {
        const o = await env.BUCKET.get("config/feedback_tags.json");
        if (o) tags = JSON.parse(await o.text());
      } catch (_) {}
      return json(tags);
    }

    if (p === "/feedback" && req.method === "POST") {
      let d;
      try { d = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
      if (!ALLOWED.has(d.action)) return json({ error: "action must be up|down|adopt|ask" }, 400);
      // 全局提问(ask)只接受站长令牌(env.OWNER_TOKEN);其余反馈匿名可提
      if (d.action === "ask" && env.OWNER_TOKEN && d.token !== env.OWNER_TOKEN) {
        return json({ error: "global feedback requires owner token" }, 403);
      }
      const ts = new Date().toISOString();
      const rec = {
        ts,
        action: d.action,
        item_id: String(d.item_id || "").slice(0, 120),
        date: String(d.date || "").slice(0, 20),
        title: String(d.title || "").slice(0, 300),
        tags: (Array.isArray(d.tags) ? d.tags : []).slice(0, 8).map((t) => String(t).slice(0, 40)),
        text: String(d.text || "").trim().slice(0, 2000),
      };
      const key = `fb/${ts}-${crypto.randomUUID().slice(0, 8)}.json`;
      await env.BUCKET.put(key, JSON.stringify(rec), { httpMetadata: { contentType: "application/json" } });
      return json({ ok: true, saved: rec });
    }

    if (p === "/feedback" && req.method === "GET") {
      const out = [];
      let cursor;
      do {
        const list = await env.BUCKET.list({ prefix: "fb/", cursor });
        for (const obj of list.objects) {
          const o = await env.BUCKET.get(obj.key);
          if (o) { try { out.push(JSON.parse(await o.text())); } catch (_) {} }
        }
        cursor = list.truncated ? list.cursor : undefined;
      } while (cursor);
      out.sort((a, b) => (a.ts < b.ts ? -1 : 1));
      return json({ count: out.length, items: out });
    }

    // ── 收藏(per-user;按 token 隔离)──
    if (p === "/favorite" && req.method === "POST") {
      let d; try { d = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
      const tok = String(d.token || "");
      if (!validTokens(env)[tok]) return json({ error: "invalid token" }, 403);
      const key = `fav/${tok}/${String(d.item_id || "").slice(0, 120)}.json`;
      if (d.on === false) { await env.BUCKET.delete(key); return json({ ok: true, on: false }); }
      const rec = { item_id: d.item_id, date: String(d.date || "").slice(0, 20), title: String(d.title || "").slice(0, 300), ts: new Date().toISOString() };
      await env.BUCKET.put(key, JSON.stringify(rec), { httpMetadata: { contentType: "application/json" } });
      return json({ ok: true, on: true });
    }
    if (p === "/favorites" && req.method === "GET") {
      const tok = url.searchParams.get("token") || "";
      if (!validTokens(env)[tok]) return json({ error: "invalid token" }, 403);
      const items = await listAll(env, `fav/${tok}/`);
      items.sort((a, b) => (a.ts < b.ts ? 1 : -1));
      return json({ count: items.length, items });
    }

    // ── 关注(驱动后续采集;按 token 存,读取时聚合话题/实体)──
    if (p === "/follow" && req.method === "POST") {
      let d; try { d = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
      const tok = String(d.token || "");
      const who = validTokens(env)[tok];
      if (!who) return json({ error: "invalid token" }, 403);
      const key = `follow/${tok}/${String(d.item_id || "").slice(0, 120)}.json`;
      if (d.on === false) { await env.BUCKET.delete(key); return json({ ok: true, on: false }); }
      const rec = {
        item_id: d.item_id, title: String(d.title || "").slice(0, 300),
        topics: (Array.isArray(d.topics) ? d.topics : []).slice(0, 12).map((x) => String(x).slice(0, 40)),
        entities: (Array.isArray(d.entities) ? d.entities : []).slice(0, 12).map((x) => String(x).slice(0, 40)),
        by: who.name || "", ts: new Date().toISOString(),
      };
      await env.BUCKET.put(key, JSON.stringify(rec), { httpMetadata: { contentType: "application/json" } });
      return json({ ok: true, on: true });
    }
    if (p === "/follows" && req.method === "GET") {
      const items = await listAll(env, "follow/");
      const topics = {}, ents = {};
      for (const it of items) {
        (it.topics || []).forEach((t) => (topics[t] = (topics[t] || 0) + 1));
        (it.entities || []).forEach((en) => (ents[en] = (ents[en] || 0) + 1));
      }
      return json({ count: items.length, items, topics, entities: ents });
    }

    // ── 已读状态(per-user;专题更新小红点)──
    if (p === "/reads" && req.method === "GET") {
      const tok = url.searchParams.get("token") || "";
      if (!validTokens(env)[tok]) return json({ error: "invalid token" }, 403);
      const o = await env.BUCKET.get(`reads/${tok}.json`);
      let m = {};
      if (o) { try { m = JSON.parse(await o.text()); } catch (_) {} }
      return json(m);
    }
    if (p === "/read" && req.method === "POST") {
      let d; try { d = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
      const tok = String(d.token || "");
      if (!validTokens(env)[tok]) return json({ error: "invalid token" }, 403);
      const key = `reads/${tok}.json`;
      const o = await env.BUCKET.get(key);
      let m = {};
      if (o) { try { m = JSON.parse(await o.text()); } catch (_) {} }
      m[String(d.id || "").slice(0, 80)] = String(d.ts || "").slice(0, 32);
      await env.BUCKET.put(key, JSON.stringify(m), { httpMetadata: { contentType: "application/json" } });
      return json({ ok: true });
    }

    return json({ error: "not found" }, 404);
  },
};
