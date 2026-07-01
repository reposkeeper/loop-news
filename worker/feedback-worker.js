/**
 * Loop News 反馈 API —— Cloudflare Worker。
 * per-user 端点(反馈/收藏/关注/已读/请求)按会话身份(identify)写读 D1(binding: DB),真正按账号隔离;
 * 常用词从 R2 的 config/feedback_tags.json 读,缺则用内置默认。
 * 端点(CORS 全开,任何设备/页面可调,per-user 端点需登录 cookie):
 *   GET  /health     健康检查
 *   GET  /tags       常用反馈词(弹窗 chips)
 *   POST /feedback   写一条反馈(D1 feedback,按当前会话 user_id)
 *   GET  /feedback   列出反馈(普通用户只看自己;owner 看全部,?role=owner 只看 owner 一组,供 ln-evolve)
 *   POST /favorite   收藏/取消收藏(D1 favorites)
 *   GET  /favorites  我的收藏
 *   POST /follow     关注/取消关注(D1 follows)
 *   GET  /follows    全量关注聚合(owner-only,供采集管线)
 *   POST /request    提采集请求(D1 requests)
 *   GET  /requests   全量请求(owner-only)
 *   GET  /reads      我的已读状态
 *   POST /read       标记已读
 *   POST /activity   记一条浏览活动(view/open/share_link/share_image,D1 activity,按当前会话 user_id)
 * 部署见 CLOUDFLARE.md。
 */
import { handleRequestCode, handleVerify, handleLogout, handleMe, handleSetTheme, identify } from "./lib/auth.js";
import { logActivity } from "./lib/activity.js";
import { nowISO } from "./lib/store.js";

const DEFAULT_TAGS = {
  up: ["有洞察", "信息密度高", "正是我想看的", "角度新颖", "证据扎实"],
  down: ["噪音/水文", "太旧了", "来源不可靠", "与我无关", "重复了"],
  adopt: ["已发微博/X", "已写进 newsletter", "已做视频选题", "已转发社群", "已存为选题库"],
};
// 带凭证的 CORS(OPTIONS 预检 + 所有 JSON 响应共用;auth 路由自身响应头见 lib/auth.js 的 J())。
function corsHeaders(env) {
  return {
    "Access-Control-Allow-Origin": (env && env.SITE_ORIGIN) || "https://news.xdzq.org",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Credentials": "true",
  };
}
const ALLOWED = new Set(["up", "down", "adopt"]);

export default {
  async fetch(req, env) {
    function json(obj, status = 200) {
      return new Response(JSON.stringify(obj), {
        status,
        headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders(env) },
      });
    }
    const url = new URL(req.url);
    const p = url.pathname;
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(env) });
    if (p === "/health") return json({ ok: true });

    if (p === "/auth/request-code" && req.method === "POST") return handleRequestCode(req, env);
    if (p === "/auth/verify" && req.method === "POST") return handleVerify(req, env);
    if (p === "/auth/logout" && req.method === "POST") return handleLogout(req, env);
    if (p === "/me" && req.method === "GET") return handleMe(req, env);
    if (p === "/me/theme" && req.method === "POST") return handleSetTheme(req, env);

    if (p === "/activity" && req.method === "POST") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      let d;
      try { d = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
      const allowedActions = new Set(["view", "open", "share_link", "share_image"]);
      if (!allowedActions.has(d.action)) return json({ error: "bad action" }, 400);
      await logActivity(env, who.user_id, d.action, d.target || "", d.meta || "");
      return json({ ok: true });
    }

    if (p === "/tags" && req.method === "GET") {
      let tags = DEFAULT_TAGS;
      try {
        const o = await env.BUCKET.get("config/feedback_tags.json");
        if (o) tags = JSON.parse(await o.text());
      } catch (_) {}
      return json(tags);
    }

    if (p === "/feedback" && req.method === "POST") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      let d;
      try { d = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
      if (!ALLOWED.has(d.action)) return json({ error: "action must be up|down|adopt" }, 400);
      await env.DB.prepare(
        "INSERT INTO feedback (user_id,ts,action,item_id,date,title,tags,text) VALUES (?,?,?,?,?,?,?,?)"
      ).bind(who.user_id, nowISO(), d.action, String(d.item_id || "").slice(0, 120),
             String(d.date || "").slice(0, 20), String(d.title || "").slice(0, 300),
             JSON.stringify((Array.isArray(d.tags) ? d.tags : []).slice(0, 8).map((t) => String(t).slice(0, 40))),
             String(d.text || "").trim().slice(0, 2000)).run();
      await logActivity(env, who.user_id, "feedback", d.item_id, d.action);
      return json({ ok: true });
    }

    if (p === "/feedback" && req.method === "GET") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      const onlyOwner = url.searchParams.get("role") === "owner";
      // owner 可看全部或按 role;普通用户只能看自己
      let rows;
      if (who.role === "owner" && onlyOwner) {
        rows = await env.DB.prepare(
          "SELECT f.* FROM feedback f JOIN users u ON u.id=f.user_id WHERE u.role='owner' ORDER BY f.ts").all();
      } else if (who.role === "owner") {
        rows = await env.DB.prepare("SELECT * FROM feedback ORDER BY ts").all();
      } else {
        rows = await env.DB.prepare("SELECT * FROM feedback WHERE user_id=? ORDER BY ts").bind(who.user_id).all();
      }
      return json({ count: rows.results.length, items: rows.results });
    }

    // ── 收藏(per-user;按会话 user_id 隔离)──
    if (p === "/favorite" && req.method === "POST") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      let d; try { d = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
      const item_id = String(d.item_id || "").slice(0, 120);
      if (d.on === false) {
        await env.DB.prepare("DELETE FROM favorites WHERE user_id=? AND item_id=?").bind(who.user_id, item_id).run();
        return json({ ok: true, on: false });
      }
      await env.DB.prepare(
        "INSERT OR REPLACE INTO favorites (user_id,item_id,date,title,ts) VALUES (?,?,?,?,?)"
      ).bind(who.user_id, item_id, String(d.date || "").slice(0, 20), String(d.title || "").slice(0, 300), nowISO()).run();
      await logActivity(env, who.user_id, "favorite", item_id);
      return json({ ok: true, on: true });
    }
    if (p === "/favorites" && req.method === "GET") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      const rows = await env.DB.prepare(
        "SELECT item_id,date,title,ts FROM favorites WHERE user_id=? ORDER BY ts DESC").bind(who.user_id).all();
      return json({ count: rows.results.length, items: rows.results });
    }

    // ── 关注(驱动后续采集;按会话 user_id 存,owner 读取时聚合话题/实体)──
    if (p === "/follow" && req.method === "POST") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      let d; try { d = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
      const item_id = String(d.item_id || "").slice(0, 120);
      if (d.on === false) {
        await env.DB.prepare("DELETE FROM follows WHERE user_id=? AND item_id=?").bind(who.user_id, item_id).run();
        return json({ ok: true, on: false });
      }
      const topics = (Array.isArray(d.topics) ? d.topics : []).slice(0, 12).map((x) => String(x).slice(0, 40));
      const entities = (Array.isArray(d.entities) ? d.entities : []).slice(0, 12).map((x) => String(x).slice(0, 40));
      await env.DB.prepare(
        "INSERT OR REPLACE INTO follows (user_id,item_id,title,topics,entities,ts) VALUES (?,?,?,?,?,?)"
      ).bind(who.user_id, item_id, String(d.title || "").slice(0, 300), JSON.stringify(topics), JSON.stringify(entities), nowISO()).run();
      await logActivity(env, who.user_id, "follow", item_id);
      return json({ ok: true, on: true });
    }
    if (p === "/follows" && req.method === "GET") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      if (who.role !== "owner") return json({ error: "owner only" }, 403);
      const rows = await env.DB.prepare("SELECT * FROM follows").all();
      const items = rows.results.map((r) => {
        let topics = [], entities = [];
        try { topics = JSON.parse(r.topics || "[]"); } catch (_) {}
        try { entities = JSON.parse(r.entities || "[]"); } catch (_) {}
        return { ...r, topics, entities };
      });
      const topics = {}, ents = {};
      for (const it of items) {
        (it.topics || []).forEach((t) => (topics[t] = (topics[t] || 0) + 1));
        (it.entities || []).forEach((en) => (ents[en] = (ents[en] || 0) + 1));
      }
      return json({ count: items.length, items, topics, entities: ents });
    }

    // ── 采集请求(任意用户:想持续看到的新闻类型 → 下次采集去找)──
    if (p === "/request" && req.method === "POST") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      let d; try { d = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
      const text = String(d.text || "").trim().slice(0, 500);
      const tags = (Array.isArray(d.tags) ? d.tags : []).slice(0, 8).map((x) => String(x).slice(0, 40));
      if (!text && !tags.length) return json({ error: "empty" }, 400);
      await env.DB.prepare(
        "INSERT INTO requests (user_id,ts,text,tags,status) VALUES (?,?,?,?,'new')"
      ).bind(who.user_id, nowISO(), text, JSON.stringify(tags)).run();
      await logActivity(env, who.user_id, "request");
      return json({ ok: true });
    }
    if (p === "/requests" && req.method === "GET") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      if (who.role !== "owner") return json({ error: "owner only" }, 403);
      const rows = await env.DB.prepare("SELECT * FROM requests ORDER BY ts DESC").all();
      return json({ count: rows.results.length, items: rows.results });
    }

    // ── 已读状态(per-user;专题更新小红点)──
    if (p === "/reads" && req.method === "GET") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      const rows = await env.DB.prepare("SELECT item_id, ts FROM reads WHERE user_id=?").bind(who.user_id).all();
      const m = {};
      for (const r of rows.results) m[r.item_id] = r.ts;
      return json(m);
    }
    if (p === "/read" && req.method === "POST") {
      const who = await identify(req, env);
      if (!who) return json({ error: "unauthorized" }, 401);
      let d; try { d = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
      const item_id = String(d.id || "").slice(0, 80);
      const ts = String(d.ts || "").slice(0, 32);
      await env.DB.prepare(
        "INSERT OR REPLACE INTO reads (user_id,item_id,ts) VALUES (?,?,?)"
      ).bind(who.user_id, item_id, ts).run();
      return json({ ok: true });
    }

    return json({ error: "not found" }, 404);
  },
};
