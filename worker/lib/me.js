/**
 * /me/* 端点(均需登录)。用本人私有 profile 对共享语料做确定性重排/设置。
 *   POST /me/feed      → {order, hidden, tags}(只回顺序/隐藏/不透明「为你」;绝不下发权重/公式)
 *   POST /me/mute      → 屏蔽/取消屏蔽 topic|entity|source(通道A 信号)
 *   POST /me/topics    → 订阅/退订话题(2a 仅写 profile.topics)
 *   GET  /me/evolution → 翻译版进化面(不透明等级/进度/叙事;硬约束§8.5:无真实维度/分数)
 *
 * 硬约束§8.5:客户端没有任何返回真实权重/维度/公式/分数的响应。
 */
import { identify } from "./auth.js";
import {
  readProfile, writeProfile, feedbackCount,
  rankFeed, applyMute, applyTopic, capability, translateEvolution,
} from "./profile.js";

const asStr = (x) => String(x == null ? "" : x);
const strArr = (a, cap = 24) => (Array.isArray(a) ? a : []).slice(0, cap).map(asStr).filter((s) => s.length > 0);

// POST /me/feed  {date, items:[{id,topics,entities,source,kind}]}
export async function handleMeFeed(req, env, json) {
  const who = await identify(req, env);
  if (!who) return json({ error: "unauthorized" }, 401);
  let d; try { d = await req.json(); } catch { return json({ error: "bad json" }, 400); }
  const raw = Array.isArray(d.items) ? d.items.slice(0, 500) : [];
  const items = raw.map((it) => ({
    id: asStr(it && it.id).slice(0, 120),
    topics: strArr(it && it.topics),
    entities: strArr(it && it.entities),
    source: it && it.source ? asStr(it.source).slice(0, 80) : "",
    kind: it && it.kind ? asStr(it.kind).slice(0, 24) : "",
    freshness: it && it.freshness,
  }));
  const profile = await readProfile(env, who.user_id);
  const { order, hidden, tags } = rankFeed(items, profile);   // 纯确定性;不含权重/公式
  return json({ order, hidden, tags });
}

// POST /me/mute {kind:"topic"|"entity"|"source", value, on}
export async function handleMeMute(req, env, json) {
  const who = await identify(req, env);
  if (!who) return json({ error: "unauthorized" }, 401);
  let d; try { d = await req.json(); } catch { return json({ error: "bad json" }, 400); }
  const kind = asStr(d.kind);
  if (!["topic", "entity", "source"].includes(kind)) return json({ error: "kind must be topic|entity|source" }, 400);
  const value = asStr(d.value).slice(0, 80);
  if (!value) return json({ error: "empty value" }, 400);
  const cur = await readProfile(env, who.user_id);
  await writeProfile(env, who.user_id, applyMute(cur, value, d.on !== false));
  return json({ ok: true });
}

// POST /me/topics {topic, on}  —— 2a 仅写 profile.topics
export async function handleMeTopics(req, env, json) {
  const who = await identify(req, env);
  if (!who) return json({ error: "unauthorized" }, 401);
  let d; try { d = await req.json(); } catch { return json({ error: "bad json" }, 400); }
  const topic = asStr(d.topic).slice(0, 80);
  if (!topic) return json({ error: "empty topic" }, 400);
  const cur = await readProfile(env, who.user_id);
  await writeProfile(env, who.user_id, applyTopic(cur, topic, d.on !== false));
  return json({ ok: true });
}

// GET /me/evolution  —— 翻译版(不透明);绝不含真实维度/分数/权重/公式
export async function handleMeEvolution(req, env, json) {
  const who = await identify(req, env);
  if (!who) return json({ error: "unauthorized" }, 401);
  const profile = await readProfile(env, who.user_id);
  const fc = await feedbackCount(env, who.user_id);
  const { capability: cap } = capability(profile, fc);   // 真实分:仅服务端内部,不进响应
  return json(translateEvolution(cap, fc));
}
