import { getUserByEmail, setUserStatus, touchLastSeen, kvGetJSON, kvPutJSON, kvDel } from "./store.js";
import { genCode, hashCode, constEq, checkRate } from "./otp.js";
import { mintSession, verifySession, revokeSession, parseCookie, sessionCookie, uiCookie, clearCookie } from "./session.js";
import { sendCode } from "./email.js";
import { logActivity } from "./activity.js";

const OTP_TTL = 600;
function J(env, obj, status = 200, extraCookies = []) {
  const h = new Headers({ "Content-Type": "application/json; charset=utf-8" });
  h.set("Access-Control-Allow-Origin", env.SITE_ORIGIN || "https://news.xdzq.org");
  h.set("Access-Control-Allow-Credentials", "true");
  for (const c of extraCookies) h.append("Set-Cookie", c);
  return new Response(JSON.stringify(obj), { status, headers: h });
}
const norm = (e) => String(e || "").trim().toLowerCase();
const emailOk = (e) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e);

export async function identify(req, env) {
  const tok = parseCookie(req.headers.get("Cookie"), "lns");
  return await verifySession(env, tok);
}

export async function handleRequestCode(req, env) {
  let d; try { d = await req.json(); } catch { return J(env, { error: "bad json" }, 400); }
  const email = norm(d.email);
  if (!emailOk(email)) return J(env, { error: "邮箱格式不对" }, 400);
  const ip = req.headers.get("CF-Connecting-IP") || "0";
  if (!(await checkRate(env, `rl:code:${email}`, 1, 60)).ok) return J(env, { error: "请稍后再试(1 分钟 1 次)" }, 429);
  if (!(await checkRate(env, `rl:ip:${ip}`, 20, 3600)).ok) return J(env, { error: "请求过于频繁" }, 429);
  const user = await getUserByEmail(env, email);
  if (!user || user.status === "disabled") return J(env, { error: "该邮箱未被邀请" }, 403);
  const code = genCode();
  const salt = env.OTP_SALT || "ln";
  await kvPutJSON(env, `otp:${email}`, { hash: await hashCode(code, email, salt), attempts: 0 }, OTP_TTL);
  const r = await sendCode(env, email, code);
  const body = { ok: true };
  if (r.dev) body.dev_code = code; // 仅 LN_DEV
  return J(env, body);
}

export async function handleVerify(req, env) {
  let d; try { d = await req.json(); } catch { return J(env, { error: "bad json" }, 400); }
  const email = norm(d.email);
  const code = String(d.code || "").trim();
  const rec = await kvGetJSON(env, `otp:${email}`);
  if (!rec) return J(env, { error: "验证码已过期,请重发" }, 400);
  if (rec.attempts >= 5) { await kvDel(env, `otp:${email}`); return J(env, { error: "尝试过多,请重发" }, 400); }
  const salt = env.OTP_SALT || "ln";
  const ok = constEq(rec.hash, await hashCode(code, email, salt));
  if (!ok) {
    rec.attempts += 1;
    await kvPutJSON(env, `otp:${email}`, rec, OTP_TTL);
    return J(env, { error: "验证码不正确" }, 400);
  }
  await kvDel(env, `otp:${email}`); // 一次性
  const user = await getUserByEmail(env, email);
  if (!user || user.status === "disabled") return J(env, { error: "该邮箱未被邀请" }, 403);
  if (user.status === "invited") await setUserStatus(env, user.id, "active");
  const token = await mintSession(env, user);
  await touchLastSeen(env, user.id);
  await logActivity(env, user.id, "login");
  const cookies = [
    sessionCookie(token),
    uiCookie("lnrole", user.role),
    uiCookie("lnname", user.name || ""),
  ];
  return J(env, { ok: true, user: { name: user.name, role: user.role, theme: user.theme } }, 200, cookies);
}

export async function handleLogout(req, env) {
  const tok = parseCookie(req.headers.get("Cookie"), "lns");
  const who = await verifySession(env, tok);
  await revokeSession(env, tok);
  if (who) await logActivity(env, who.user_id, "logout");
  return J(env, { ok: true }, 200, [clearCookie("lns"), clearCookie("lnrole"), clearCookie("lnname")]);
}

export async function handleMe(req, env) {
  const who = await identify(req, env);
  if (!who) return J(env, { error: "unauthorized" }, 401);
  const u = await getUserByEmail(env, who.email);
  return J(env, { email: u.email, name: u.name, role: u.role, theme: u.theme });
}
