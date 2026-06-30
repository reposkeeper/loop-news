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

    return json({ error: "not found" }, 404);
  },
};
