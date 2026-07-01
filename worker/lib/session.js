import { kvGetJSON, kvPutJSON, kvDel, getUserById } from "./store.js";

export const SESSION_TTL = 2592000; // 30d
const COOKIE_DOMAIN = "Domain=.xdzq.org";

export function parseCookie(header, name) {
  const m = (header || "").match(new RegExp("(?:^|;\\s*)" + name + "=([^;]+)"));
  return m ? decodeURIComponent(m[1]) : "";
}
export function sessionCookie(token, { maxAge = SESSION_TTL } = {}) {
  return `lns=${token}; ${COOKIE_DOMAIN}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}
export function uiCookie(name, val, maxAge = SESSION_TTL) {
  // 非 httpOnly,供前端即时渲染(role/name)
  return `${name}=${encodeURIComponent(val)}; ${COOKIE_DOMAIN}; Path=/; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}
export function clearCookie(name) {
  return `${name}=; ${COOKIE_DOMAIN}; Path=/; Secure; SameSite=Lax; Max-Age=0`;
}

function b64url(bytes) {
  let s = btoa(String.fromCharCode(...bytes));
  return s.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
export async function mintSession(env, user) {
  const token = b64url(crypto.getRandomValues(new Uint8Array(32)));
  await kvPutJSON(env, `session:${token}`, { user_id: user.id, email: user.email, role: user.role }, SESSION_TTL);
  const idx = (await kvGetJSON(env, `usess:${user.id}`)) || [];
  idx.push(token);
  await kvPutJSON(env, `usess:${user.id}`, idx, SESSION_TTL);
  return token;
}
export async function verifySession(env, token) {
  if (!token) return null;
  const s = await kvGetJSON(env, `session:${token}`);
  if (!s) return null;
  // 滑动续期 + 校验用户仍有效
  const u = await getUserById(env, s.user_id);
  if (!u || u.status === "disabled") { await kvDel(env, `session:${token}`); return null; }
  await kvPutJSON(env, `session:${token}`, s, SESSION_TTL);
  return { user_id: s.user_id, email: s.email, role: u.role };
}
export async function revokeSession(env, token) {
  await kvDel(env, `session:${token}`);
}
export async function revokeAllForUser(env, user_id) {
  const idx = (await kvGetJSON(env, `usess:${user_id}`)) || [];
  for (const t of idx) await kvDel(env, `session:${t}`);
  await kvDel(env, `usess:${user_id}`);
}
