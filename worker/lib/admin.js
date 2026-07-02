import { identify } from "./auth.js";
import { revokeAllForUser } from "./session.js";
import { logActivity } from "./activity.js";
import { nowISO } from "./store.js";
import { readProfile, feedbackCount, ownerEvolution } from "./profile.js";

export function parseUserId(path) {
  const m = path.match(/^\/admin\/users\/(\d+)$/);
  return m ? parseInt(m[1], 10) : null;
}
// /admin/users/:id/evolution —— owner 看某用户真实个人进化。
export function parseUserEvolution(path) {
  const m = path.match(/^\/admin\/users\/(\d+)\/evolution$/);
  return m ? parseInt(m[1], 10) : null;
}
const ROLES = new Set(["owner", "viewer"]);
const STATUSES = new Set(["invited", "active", "disabled"]);
export function buildUserUpdate(body) {
  const parts = [], vals = [];
  if (typeof body.name === "string") { parts.push("name=?"); vals.push(body.name.slice(0, 60)); }
  if (ROLES.has(body.role)) { parts.push("role=?"); vals.push(body.role); }
  if (STATUSES.has(body.status)) { parts.push("status=?"); vals.push(body.status); }
  return { sql: parts.join(", "), vals };
}

async function owner(req, env, json) {
  const who = await identify(req, env);
  if (!who || who.role !== "owner") return { err: json({ error: "forbidden" }, 403) };
  return { who };
}

export async function handleAdmin(req, env, url, json) {
  const p = url.pathname;
  const gate = await owner(req, env, json);
  if (gate.err) return gate.err;
  const me = gate.who;

  if (p === "/admin/users" && req.method === "GET") {
    const users = (await env.DB.prepare(
      "SELECT id,email,name,role,status,theme,channel,created_at,last_seen_at FROM users ORDER BY created_at").all()).results;
    const fb = (await env.DB.prepare("SELECT user_id, COUNT(*) c FROM feedback GROUP BY user_id").all()).results;
    const ac = (await env.DB.prepare("SELECT user_id, COUNT(*) c FROM activity GROUP BY user_id").all()).results;
    const fbm = Object.fromEntries(fb.map((r) => [r.user_id, r.c]));
    const acm = Object.fromEntries(ac.map((r) => [r.user_id, r.c]));
    const items = users.map((u) => ({ ...u, feedback_count: fbm[u.id] || 0, activity_count: acm[u.id] || 0 }));
    return json({ count: items.length, items });
  }

  if (p === "/admin/users" && req.method === "POST") {
    let d; try { d = await req.json(); } catch { return json({ error: "bad json" }, 400); }
    const email = String(d.email || "").trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return json({ error: "邮箱格式不对" }, 400);
    const name = String(d.name || "").slice(0, 60);
    const role = ROLES.has(d.role) ? d.role : "viewer";
    try {
      const r = await env.DB.prepare(
        "INSERT INTO users (email,name,role,status,created_at) VALUES (?,?,?, 'invited', ?)")
        .bind(email, name, role, nowISO()).run();
      await logActivity(env, me.user_id, "admin_invite", email);
      return json({ ok: true, id: r.meta.last_row_id });
    } catch (e) {
      return json({ error: "该邮箱已存在" }, 409);
    }
  }

  const evoUid = parseUserEvolution(p);
  if (evoUid !== null && req.method === "GET") {
    const profile = await readProfile(env, evoUid);
    const fc = await feedbackCount(env, evoUid);
    return json(ownerEvolution(profile, fc));   // owner 侧真实分(§8.5 例外)
  }

  const uid = parseUserId(p);
  if (uid !== null && req.method === "PATCH") {
    if (uid === me.user_id) return json({ error: "不能改自己(防锁死)" }, 400);
    let d; try { d = await req.json(); } catch { return json({ error: "bad json" }, 400); }
    const { sql, vals } = buildUserUpdate(d);
    if (!sql) return json({ error: "无可改字段" }, 400);
    await env.DB.prepare(`UPDATE users SET ${sql} WHERE id=?`).bind(...vals, uid).run();
    if (d.status === "disabled") await revokeAllForUser(env, uid);
    await logActivity(env, me.user_id, "admin_update", String(uid), JSON.stringify(d));
    return json({ ok: true });
  }
  if (uid !== null && req.method === "DELETE") {
    if (uid === me.user_id) return json({ error: "不能删自己" }, 400);
    await revokeAllForUser(env, uid);
    for (const t of ["feedback", "favorites", "follows", "reads", "requests", "activity"]) {
      await env.DB.prepare(`DELETE FROM ${t} WHERE user_id=?`).bind(uid).run();
    }
    await env.DB.prepare("DELETE FROM users WHERE id=?").bind(uid).run();
    await logActivity(env, me.user_id, "admin_delete", String(uid));
    return json({ ok: true });
  }

  if (p === "/admin/activity" && req.method === "GET") {
    const userId = url.searchParams.get("user_id");
    const limit = Math.min(200, parseInt(url.searchParams.get("limit") || "100", 10) || 100);
    const before = url.searchParams.get("before");
    let q = "SELECT id,user_id,ts,action,target,meta FROM activity", cond = [], binds = [];
    if (userId) { cond.push("user_id=?"); binds.push(parseInt(userId, 10)); }
    if (before) { cond.push("ts<?"); binds.push(before); }
    if (cond.length) q += " WHERE " + cond.join(" AND ");
    q += " ORDER BY ts DESC LIMIT ?"; binds.push(limit);
    const items = (await env.DB.prepare(q).bind(...binds).all()).results;
    return json({ count: items.length, items });
  }
  return json({ error: "not found" }, 404);
}
