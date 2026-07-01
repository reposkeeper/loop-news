import { kvGetJSON, kvPutJSON } from "./store.js";

export function genCode() {
  const n = crypto.getRandomValues(new Uint32Array(1))[0] % 1000000;
  return String(n).padStart(6, "0");
}
export async function hashCode(code, email, salt) {
  const data = new TextEncoder().encode(`${code}:${email}:${salt}`);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
export function constEq(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
// KV 计数器限流:窗口内自增,超过 limit 返回 {ok:false}
export async function checkRate(env, key, limit, ttlSec) {
  const cur = (await kvGetJSON(env, key)) || { n: 0 };
  if (cur.n >= limit) return { ok: false };
  await kvPutJSON(env, key, { n: cur.n + 1 }, ttlSec);
  return { ok: true };
}
