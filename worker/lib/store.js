export const d1 = (env) => env.DB;

// 上海时区 ISO(无 Date 依赖问题:Worker 有真实时钟)
export function nowISO() {
  return new Date().toISOString(); // 存 UTC Z;展示层转上海
}

export async function getUserByEmail(env, email) {
  const r = await env.DB.prepare(
    "SELECT id,email,name,role,status,theme,created_at,last_seen_at FROM users WHERE email=?"
  ).bind(email).first();
  return r || null;
}
export async function getUserById(env, id) {
  return (await env.DB.prepare(
    "SELECT id,email,name,role,status,theme FROM users WHERE id=?"
  ).bind(id).first()) || null;
}
export async function insertUser(env, { email, name = "", role = "viewer", status = "invited" }) {
  const r = await env.DB.prepare(
    "INSERT INTO users (email,name,role,status,created_at) VALUES (?,?,?,?,?)"
  ).bind(email, name, role, status, nowISO()).run();
  return r.meta.last_row_id;
}
export async function setUserStatus(env, id, status) {
  await env.DB.prepare("UPDATE users SET status=? WHERE id=?").bind(status, id).run();
}
export async function touchLastSeen(env, id) {
  await env.DB.prepare("UPDATE users SET last_seen_at=? WHERE id=?").bind(nowISO(), id).run();
}

export async function kvGetJSON(env, key) {
  const s = await env.SESSIONS.get(key);
  if (!s) return null;
  try { return JSON.parse(s); } catch { return null; }
}
export async function kvPutJSON(env, key, obj, ttlSec) {
  const opt = ttlSec ? { expirationTtl: ttlSec } : {};
  await env.SESSIONS.put(key, JSON.stringify(obj), opt);
}
export async function kvDel(env, key) { await env.SESSIONS.delete(key); }
