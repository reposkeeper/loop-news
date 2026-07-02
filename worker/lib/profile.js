/**
 * 个人画像(profile)——SP2 相位 2a 的确定性核心。
 *
 * 三块内容:
 *  1) 纯函数(无 env、可单测):normalizeProfile / applyEWMA / applyMute / applyTopic /
 *     rank / rankFeed / capability / ownerEvolution / translateEvolution。
 *  2) D1 读写(env.DB,单一真源 user_profile 表):readProfile / writeProfile / feedbackCount。
 *  3) 通道 A(确定性、即时):updateProfileFromSignal —— 反馈/收藏/关注/屏蔽即时微调本人画像。
 *
 * 硬约束(§8.5):这里产出的"真实权重/维度/分数/公式"绝不下发客户端。
 *   - /me/feed 只回顺序 + 隐藏集 + 不透明「为你」标签(见 me.js)。
 *   - /me/evolution 只回不透明等级/进度/叙事(translateEvolution)。
 *   - 真实分只在 owner 侧(ownerEvolution → /admin/users/:id/evolution)。
 *
 * 隔离不变量:所有写只落到当前 user_id 自己的 user_profile 行,绝不因 A 改他人画像。
 */

// ── 常量(rank / EWMA / 阈值,集中在此便于审计与调参)──
export const ALPHA = 0.3;            // EWMA 学习率
export const W_MIN = -3;             // 权重截断下界
export const W_MAX = 3;              // 权重截断上界
export const MUTE_PEN = 5;           // 命中 muted 的分数惩罚
export const FRESH = 1.0;            // 新鲜度权重(freshness ∈ [0,1])
export const HIDE_THRESH = -1.0;     // 分 < 此值 → 隐藏(严格小于)
export const TOP_THRESH = 1.0;       // 分 ≥ 此值 → 打「为你」标签

// 反馈动作 → EWMA 目标值。
export const TARGET = { up: 1, down: -1, adopt: 1.5, favorite: 1, follow: 1 };

// 条目 kind → 语气(tone)维度。页面层 data-kind 是 deep|consensus(见 web/compile.py),
// 语料层还有 data/voices,一并归一。
export const KIND_TONE = {
  deep: "深度", consensus: "共识", data: "数据",
  voice: "原声", voices: "原声", primary: "原声",
};

const clampWeight = (w) => {
  const n = Number(w);
  if (!Number.isFinite(n)) return 0;
  return n < W_MIN ? W_MIN : n > W_MAX ? W_MAX : n;
};
const asStr = (x) => String(x == null ? "" : x);
const strArr = (a) => (Array.isArray(a) ? a : []).map(asStr).filter((s) => s.length > 0);

// 上海时区 ISO(+08:00),契约要求 updated_at 形如 "<ISO+08:00>"。
export function nowShanghaiISO(date = new Date()) {
  const shifted = new Date(date.getTime() + 8 * 3600 * 1000);
  return shifted.toISOString().replace(/\.\d+Z$/, "Z").replace("Z", "+08:00");
}

// 新用户 / 空画像:所有权重视为 0、muted 空 → rank 保持原顺序 → 页 ≡ base。
export function baseProfile() {
  return { topics: {}, entities: {}, sources: {}, tones: {}, muted: [], version: 0, updated_at: null };
}

// 归一成规范形状:补齐字段、截断权重、去重 muted、保留 version/updated_at。不改动传入对象。
export function normalizeProfile(input) {
  let p = input;
  if (typeof p === "string") { try { p = JSON.parse(p); } catch { p = null; } }
  if (!p || typeof p !== "object") return baseProfile();
  const bag = (o) => {
    const out = {};
    if (o && typeof o === "object") {
      for (const k of Object.keys(o)) {
        const v = clampWeight(o[k]);
        if (v !== 0) out[asStr(k)] = v;   // 稀疏:只留非零
      }
    }
    return out;
  };
  const muted = Array.from(new Set(strArr(p.muted)));
  const version = Number.isFinite(p.version) ? p.version : 0;
  return {
    topics: bag(p.topics), entities: bag(p.entities),
    sources: bag(p.sources), tones: bag(p.tones),
    muted, version, updated_at: p.updated_at || null,
  };
}

// 是否为 base(新用户)画像:无任何非零权重且 muted 空。
export function isBaseProfile(profile) {
  const p = normalizeProfile(profile);
  const anyW = [p.topics, p.entities, p.sources, p.tones]
    .some((bag) => Object.values(bag).some((v) => v !== 0));
  return !anyW && p.muted.length === 0;
}

// 新鲜度:条目自带 freshness ∈ [0,1] 则用之,否则 0(/me/feed 同日条目无逐条时间戳 → 0)。
export function freshness(item) {
  const f = Number(item && item.freshness);
  if (!Number.isFinite(f)) return 0;
  return f < 0 ? 0 : f > 1 ? 1 : f;
}

// ── 纯打分:单条 → {score, muted}。无 LLM、确定性。 ──
export function rank(item, profile) {
  const p = normalizeProfile(profile);
  const mutedSet = new Set(p.muted);
  const topics = strArr(item && item.topics);
  const entities = strArr(item && item.entities);
  const source = item && item.source ? asStr(item.source) : "";
  const kind = item && item.kind ? asStr(item.kind) : "";

  let score = 0;
  let muted = false;
  for (const t of topics) { score += p.topics[t] || 0; if (mutedSet.has(t)) muted = true; }
  for (const e of entities) { score += p.entities[e] || 0; if (mutedSet.has(e)) muted = true; }
  if (source) { score += p.sources[source] || 0; if (mutedSet.has(source)) muted = true; }
  const tone = KIND_TONE[kind];
  if (tone) score += p.tones[tone] || 0;
  if (muted) score -= MUTE_PEN;
  score += FRESH * freshness(item);
  return { score, muted };
}

/**
 * 对一整页条目排序。返回 {order:[id...], hidden:[id...], tags:{id:"为你"}}。
 * base 画像 → 稳定保持输入顺序、hidden 空、tags 空(新用户页 ≡ base)。
 * 稳定排序:分数降序,同分按输入下标升序(不依赖引擎稳定性)。
 */
export function rankFeed(items, profile) {
  const list = Array.isArray(items) ? items : [];
  if (isBaseProfile(profile)) {
    return { order: list.map((it) => asStr(it && it.id)), hidden: [], tags: {} };
  }
  const scored = list.map((it, i) => {
    const id = asStr(it && it.id);
    const { score, muted } = rank(it, profile);
    return { id, i, score, muted };
  });
  scored.sort((a, b) => (b.score - a.score) || (a.i - b.i));
  const order = [];
  const hidden = [];
  const tags = {};
  for (const s of scored) {
    order.push(s.id);
    const hide = s.muted || s.score < HIDE_THRESH;
    if (hide) hidden.push(s.id);
    else if (s.score >= TOP_THRESH) tags[s.id] = "为你";
  }
  return { order, hidden, tags };
}

// ── 画像更新(纯函数,返回新对象,不改传入)──
function cloneProfile(profile) {
  const p = normalizeProfile(profile);
  return {
    topics: { ...p.topics }, entities: { ...p.entities },
    sources: { ...p.sources }, tones: { ...p.tones },
    muted: [...p.muted], version: p.version, updated_at: p.updated_at,
  };
}
const ewmaStep = (w, target) => clampWeight(w + ALPHA * (target - w));

// 反馈/收藏/关注信号 → EWMA 微调命中的 topics/entities/source/tone(按 kind)。
export function applyEWMA(profile, signal) {
  const p = cloneProfile(profile);
  const target = TARGET[signal && signal.action];
  if (target === undefined) return p;                 // 未知动作:不动
  const topics = strArr(signal.topics);
  const entities = strArr(signal.entities);
  const source = signal.source ? asStr(signal.source) : "";
  const kind = signal.kind ? asStr(signal.kind) : "";
  const bump = (bag, key) => {
    const v = ewmaStep(bag[key] || 0, target);
    if (v === 0) delete bag[key]; else bag[key] = v;  // 保持稀疏
  };
  for (const t of topics) bump(p.topics, t);
  for (const e of entities) bump(p.entities, e);
  if (source) bump(p.sources, source);
  const tone = KIND_TONE[kind];
  if (tone) bump(p.tones, tone);
  return p;
}

// 屏蔽:value 入/出 muted[](去重)。kind 仅作语义,muted 是扁平字符串集合。
export function applyMute(profile, value, on) {
  const p = cloneProfile(profile);
  const v = asStr(value);
  if (!v) return p;
  const set = new Set(p.muted);
  if (on === false) set.delete(v); else set.add(v);
  p.muted = Array.from(set);
  return p;
}

// 订阅/退订话题:2a 仅写 profile.topics。订阅=显式正权重;退订=移除。
export function applyTopic(profile, topic, on) {
  const p = cloneProfile(profile);
  const t = asStr(topic);
  if (!t) return p;
  if (on === false) { delete p.topics[t]; return p; }
  p.topics[t] = clampWeight(Math.max(p.topics[t] || 0, 1));  // 显式订阅 → 至少 +1
  return p;
}

// ── 个人成熟度(2a 确定性版,服务端内部;真实分仅 owner 侧可见)──
function countNonZero(bag) { return Object.values(bag).filter((v) => v !== 0).length; }
function countPositive(bag) { return Object.values(bag).filter((v) => v > 0).length; }

/**
 * capability ∈ [0,100] = f(画像丰富度, 参与度, 反过滤气泡守卫)。
 * 返回 {capability, dims}。dims 是真实内部分量(只喂 owner)。
 */
export function capability(profile, feedbackCount = 0) {
  const p = normalizeProfile(profile);
  const nonZero = countNonZero(p.topics) + countNonZero(p.entities)
    + countNonZero(p.sources) + countNonZero(p.tones);
  const posBreadth = countPositive(p.topics) + countPositive(p.entities)
    + countPositive(p.sources) + countPositive(p.tones);
  const muteCount = p.muted.length;

  const richness = Math.min(1, nonZero / 16);          // 16 个非零权重 → 满
  const engagement = Math.min(1, (feedbackCount || 0) / 24);
  const base = 0.5 * richness + 0.5 * engagement;      // [0,1]

  // 反过滤气泡守卫:屏蔽过猛(反回音室)或兴趣过窄(反过滤气泡)→ 扣分。
  const overMuted = muteCount >= 5 && muteCount > posBreadth;
  const tooNarrow = posBreadth <= 2 && engagement > 0.3;
  const penalty = (overMuted ? 0.15 : 0) + (tooNarrow ? 0.15 : 0);
  const guard = Math.max(0.7, 1 - penalty);            // [0.7,1]

  const cap = Math.round(100 * base * guard);
  return {
    capability: Math.max(0, Math.min(100, cap)),
    dims: {
      richness: Math.round(100 * richness),
      engagement: Math.round(100 * engagement),
      breadth: posBreadth,
      guard: Math.round(100 * guard),
      non_zero_weights: nonZero,
      muted_count: muteCount,
    },
  };
}

// owner 侧真实进化面(§8.5 例外:真实分只在 owner)。
export function ownerEvolution(profile, feedbackCount = 0) {
  const p = normalizeProfile(profile);
  const { capability: cap, dims } = capability(p, feedbackCount);
  const top = (bag, n) => Object.entries(bag)
    .sort((a, b) => b[1] - a[1]).slice(0, n).map(([name, weight]) => ({ name, weight }));
  return {
    capability: cap,
    dims,
    profile_summary: {
      top_topics: top(p.topics, 5),
      top_entities: top(p.entities, 5),
      muted_count: p.muted.length,
    },
    trend: p.updated_at ? [{ at: p.updated_at, capability: cap }] : [],
  };
}

// ── 翻译版进化面(用户侧;硬约束§8.5:绝不含真实维度/分数/权重/公式)──
const LEVELS = [
  { name: "初识", floor: 0 },
  { name: "熟悉", floor: 20 },
  { name: "默契", floor: 40 },
  { name: "知音", floor: 60 },
  { name: "心有灵犀", floor: 80 },
];
// 每级一组会变的叙事(按 level + 近期活动轮换,措辞不透明、无数字/维度)。
const NARRATIVES = [
  ["它刚开始认识你,多点几下喜欢与不喜欢,它会更懂你想看什么。",
   "还在打量你的口味,你的每一次反馈都在教它。"],
  ["它对你的偏好有了初步感觉,已经在悄悄为你调整顺序。",
   "熟起来了——它开始把你更在意的往前放。"],
  ["你们之间有了默契,它越来越能猜中你想先看哪条。",
   "它读懂了你的一些偏好,页面正按你的镜头重排。"],
  ["它像个懂你的老友,能把你最在意的一眼递到面前。",
   "知音级别——它对你的取舍已相当有把握。"],
  ["心有灵犀:它几乎和你想到一块去,依然会为你留一扇发现新东西的窗。",
   "默契拉满,它替你策展的同时,也守着不让你困在信息茧房。"],
];
// 里程碑:纯定性、无真实阈值/维度。reached 由 capability 粗略触发。
function milestonesFor(cap, feedbackCount) {
  return [
    { key: "first_signal", name: "第一次表达喜好", reached: (feedbackCount || 0) >= 1 },
    { key: "taking_shape", name: "偏好开始成形", reached: cap >= 25 },
    { key: "in_sync", name: "与你渐入默契", reached: cap >= 50 },
    { key: "curator", name: "成为你的私人策展人", reached: cap >= 75 },
  ];
}

/**
 * 把真实 capability 翻译成不透明的等级/进度/叙事。
 * progress = 当前等级带内的相对位置(0-100),刻意不暴露绝对 capability。
 * 输出仅含 level/level_name/progress/narrative/milestones —— 无任何真实维度/分数/权重/公式。
 */
export function translateEvolution(cap, feedbackCount = 0) {
  const c = Math.max(0, Math.min(100, Number(cap) || 0));
  let idx = 0;
  for (let i = 0; i < LEVELS.length; i++) if (c >= LEVELS[i].floor) idx = i;
  const floor = LEVELS[idx].floor;
  const ceil = idx + 1 < LEVELS.length ? LEVELS[idx + 1].floor : 100;
  const span = ceil - floor || 1;
  const progress = Math.max(0, Math.min(100, Math.round(((c - floor) / span) * 100)));
  const set = NARRATIVES[idx];
  const narrative = set[(feedbackCount || 0) % set.length];  // 随反馈轮换 → "会变"
  return {
    level: idx + 1,
    level_name: LEVELS[idx].name,
    progress,
    narrative,
    milestones: milestonesFor(c, feedbackCount),
  };
}

// ── D1 读写(单一真源 user_profile 表)──
export async function readProfile(env, userId) {
  const row = await env.DB.prepare(
    "SELECT profile, version, updated_at FROM user_profile WHERE user_id=?"
  ).bind(userId).first();
  if (!row) return baseProfile();
  const p = normalizeProfile(row.profile);
  p.version = Number.isFinite(row.version) ? row.version : p.version;
  p.updated_at = row.updated_at || p.updated_at;
  return p;
}

// UPSERT:version+1、updated_at=now(上海)。只落当前 user_id 自己的行。
export async function writeProfile(env, userId, profile) {
  const p = normalizeProfile(profile);
  p.version = (Number.isFinite(profile && profile.version) ? profile.version : 0) + 1;
  p.updated_at = nowShanghaiISO();
  await env.DB.prepare(
    "INSERT INTO user_profile (user_id, profile, version, updated_at) VALUES (?,?,?,?) " +
    "ON CONFLICT(user_id) DO UPDATE SET profile=excluded.profile, version=excluded.version, updated_at=excluded.updated_at"
  ).bind(userId, JSON.stringify(p), p.version, p.updated_at).run();
  return p;
}

export async function feedbackCount(env, userId) {
  try {
    const r = await env.DB.prepare("SELECT COUNT(*) c FROM feedback WHERE user_id=?").bind(userId).first();
    return (r && r.c) || 0;
  } catch { return 0; }
}

/**
 * 通道 A:一条信号 → 即时确定性更新本人画像。
 * signal:{action, topics?, entities?, source?, kind?}。无任何条目维度则跳过(老客户端不传 → 不报错)。
 * 调用方须自行 try/catch(见 feedback-worker.js);此处也不吞异常以便测试可断言。
 */
export async function updateProfileFromSignal(env, userId, signal) {
  if (!signal || TARGET[signal.action] === undefined) return null;
  const hasDim = strArr(signal.topics).length || strArr(signal.entities).length
    || signal.source || (signal.kind && KIND_TONE[signal.kind]);
  if (!hasDim) return null;                      // 无维度可更 → 跳过(不报错)
  const cur = await readProfile(env, userId);
  const next = applyEWMA(cur, signal);
  return await writeProfile(env, userId, next);
}
