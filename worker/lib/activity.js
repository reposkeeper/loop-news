import { nowISO } from "./store.js";
export async function logActivity(env, user_id, action, target = "", meta = "") {
  try {
    await env.DB.prepare(
      "INSERT INTO activity (user_id,ts,action,target,meta) VALUES (?,?,?,?,?)"
    ).bind(user_id, nowISO(), action, String(target).slice(0, 200),
           typeof meta === "string" ? meta : JSON.stringify(meta)).run();
  } catch (_) { /* 日志失败不阻塞主流程 */ }
}
