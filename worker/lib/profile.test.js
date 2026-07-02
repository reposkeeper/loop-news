import { describe, it, expect } from "vitest";
import {
  baseProfile, normalizeProfile, isBaseProfile,
  rank, rankFeed, applyEWMA, applyMute, applyTopic,
  capability, ownerEvolution, translateEvolution,
  W_MIN, W_MAX, ALPHA,
} from "./profile.js";

const feed = (ids) => ids.map((id) => ({ id, topics: [], entities: [], source: "", kind: "" }));

describe("rank / rankFeed", () => {
  it("全 0(base)画像 → 保持输入顺序、hidden 空、tags 空", () => {
    const items = feed(["a", "b", "c"]);
    const r = rankFeed(items, baseProfile());
    expect(r.order).toEqual(["a", "b", "c"]);
    expect(r.hidden).toEqual([]);
    expect(r.tags).toEqual({});
  });

  it("命中正权重的条目上浮并被标「为你」", () => {
    const profile = normalizeProfile({ topics: { ai: 2 } });
    const items = [
      { id: "x", topics: ["misc"] },
      { id: "y", topics: ["ai"] },     // 命中 +2
      { id: "z", topics: ["misc"] },
    ];
    const r = rankFeed(items, profile);
    expect(r.order[0]).toBe("y");       // 上浮到第一
    expect(r.tags.y).toBe("为你");       // 高分 → 为你
    expect(r.hidden).toEqual([]);
  });

  it("命中 muted → 隐藏(且不打为你)", () => {
    const profile = normalizeProfile({ topics: { ai: 3 }, muted: ["spam"] });
    const items = [
      { id: "good", topics: ["ai"] },
      { id: "bad", topics: ["ai", "spam"] },   // 虽命中 ai,但也命中 muted
    ];
    const r = rankFeed(items, profile);
    expect(r.hidden).toContain("bad");
    expect(r.tags.bad).toBeUndefined();
    expect(r.hidden).not.toContain("good");
  });

  it("source 与 tone(kind)命中都计分", () => {
    const profile = normalizeProfile({ sources: { Reuters: 1 }, tones: { 深度: 2 } });
    const a = rank({ id: "a", source: "Reuters", kind: "deep" }, profile).score; // 1 + 2
    const b = rank({ id: "b", source: "Other", kind: "consensus" }, profile).score; // 0
    expect(a).toBeGreaterThan(b);
    expect(a).toBeCloseTo(3, 6);
  });

  it("稳定排序:同分保持输入下标顺序", () => {
    const profile = normalizeProfile({ topics: { ai: 1 } });
    const items = [
      { id: "1", topics: ["ai"] }, { id: "2", topics: ["ai"] }, { id: "3", topics: ["ai"] },
    ];
    expect(rankFeed(items, profile).order).toEqual(["1", "2", "3"]);
  });
});

describe("EWMA 更新(通道A 规则)", () => {
  it("up(+1)使命中权重上升,down(-1)使其下降", () => {
    const up = applyEWMA(baseProfile(), { action: "up", topics: ["ai"] });
    expect(up.topics.ai).toBeCloseTo(ALPHA * 1, 6);         // 0 + 0.3*(1-0)=0.3
    const down = applyEWMA(baseProfile(), { action: "down", topics: ["ai"] });
    expect(down.topics.ai).toBeCloseTo(-ALPHA, 6);          // 0 + 0.3*(-1-0)=-0.3
    expect(down.topics.ai).toBeLessThan(0);
  });

  it("adopt 目标 +1.5;收藏/关注 +1", () => {
    const adopt = applyEWMA(baseProfile(), { action: "adopt", topics: ["ai"] });
    expect(adopt.topics.ai).toBeCloseTo(ALPHA * 1.5, 6);    // 0.45
    const fav = applyEWMA(baseProfile(), { action: "favorite", entities: ["OpenAI"] });
    expect(fav.entities.OpenAI).toBeCloseTo(ALPHA, 6);
  });

  it("kind → tone 维度按同法更新", () => {
    const p = applyEWMA(baseProfile(), { action: "up", kind: "deep" });
    expect(p.tones["深度"]).toBeCloseTo(ALPHA, 6);
  });

  it("反复 up 收敛向 +1 但不超权重上界", () => {
    let p = baseProfile();
    for (let i = 0; i < 50; i++) p = applyEWMA(p, { action: "up", topics: ["ai"] });
    expect(p.topics.ai).toBeLessThanOrEqual(1 + 1e-9);
    expect(p.topics.ai).toBeGreaterThan(0.9);
  });

  it("权重截断在 [W_MIN, W_MAX]", () => {
    const hi = normalizeProfile({ topics: { ai: 999 } });
    expect(hi.topics.ai).toBe(W_MAX);
    const lo = normalizeProfile({ topics: { ai: -999 } });
    expect(lo.topics.ai).toBe(W_MIN);
  });

  it("纯函数:不改动传入画像(隔离友好)", () => {
    const before = baseProfile();
    const snapshot = JSON.stringify(before);
    applyEWMA(before, { action: "up", topics: ["ai"] });
    expect(JSON.stringify(before)).toBe(snapshot);
  });

  it("未知动作 / 无维度不产生变更", () => {
    expect(applyEWMA(baseProfile(), { action: "bogus", topics: ["ai"] }).topics).toEqual({});
    expect(isBaseProfile(applyEWMA(baseProfile(), { action: "up" }))).toBe(true);
  });
});

describe("mute / topic", () => {
  it("mute value 入/出 muted[] 去重", () => {
    let p = applyMute(baseProfile(), "spam", true);
    p = applyMute(p, "spam", true);                 // 重复
    expect(p.muted).toEqual(["spam"]);
    p = applyMute(p, "spam", false);
    expect(p.muted).toEqual([]);
  });
  it("mute 使 base 画像不再是 base(会被 rank 消费)", () => {
    expect(isBaseProfile(applyMute(baseProfile(), "spam", true))).toBe(false);
  });
  it("topic 订阅写 profile.topics(≥+1),退订移除", () => {
    let p = applyTopic(baseProfile(), "finance", true);
    expect(p.topics.finance).toBeGreaterThanOrEqual(1);
    p = applyTopic(p, "finance", false);
    expect(p.topics.finance).toBeUndefined();
  });
});

describe("capability(成熟度)", () => {
  it("base 画像 capability 为 0", () => {
    expect(capability(baseProfile(), 0).capability).toBe(0);
  });
  it("画像更丰富 + 参与更多 → capability 上升", () => {
    const rich = normalizeProfile({ topics: { a: 1, b: 1, c: 1 }, entities: { d: 1, e: 1 }, sources: { f: 1 } });
    const low = capability(rich, 2).capability;
    const high = capability(rich, 20).capability;
    expect(high).toBeGreaterThan(low);
    expect(high).toBeGreaterThan(0);
  });
  it("反过滤气泡守卫:屏蔽过猛扣分", () => {
    const engaged = { topics: { a: 1 }, entities: { b: 1 } };
    const clean = capability(normalizeProfile(engaged), 20).capability;
    const overMuted = capability(
      normalizeProfile({ ...engaged, muted: ["m1", "m2", "m3", "m4", "m5", "m6"] }), 20).capability;
    expect(overMuted).toBeLessThan(clean);
  });
});

describe("翻译版进化面(硬约束§8.5:不泄真实分/维度/公式)", () => {
  // 真实内部关键字 + 语气维度中文名(muted 会被「milestones」误伤,故按需精选)。
  const FORBIDDEN = ["capability", "richness", "engagement", "composite", "weight",
    "profile_summary", "\"dims\"", "深度", "共识", "数据", "原声"];

  it("只含不透明 level/level_name/progress/narrative/milestones", () => {
    const out = translateEvolution(55, 7);
    expect(Object.keys(out).sort()).toEqual(
      ["level", "level_name", "milestones", "narrative", "progress"]);
    expect(typeof out.level).toBe("number");
    expect(out.progress).toBeGreaterThanOrEqual(0);
    expect(out.progress).toBeLessThanOrEqual(100);
    expect(typeof out.narrative).toBe("string");
    expect(Array.isArray(out.milestones)).toBe(true);
  });

  it("序列化后不含任何真实维度/分数/权重/公式关键字", () => {
    const blob = JSON.stringify(translateEvolution(72, 13)).toLowerCase();
    for (const k of FORBIDDEN) expect(blob.includes(k.toLowerCase())).toBe(false);
  });

  it("progress 是等级带内相对位置,不等于绝对 capability", () => {
    // capability 55 落在「默契」带(40-59),带内相对 = (55-40)/20*100 = 75
    expect(translateEvolution(55, 0).progress).toBe(75);
    expect(translateEvolution(55, 0).level).toBe(3);
  });

  it("narrative 随近期活动(反馈数)轮换 → 会变", () => {
    const a = translateEvolution(50, 0).narrative;
    const b = translateEvolution(50, 1).narrative;
    expect(a).not.toBe(b);
  });

  it("等级随 capability 升高单调不降", () => {
    const levels = [0, 20, 40, 60, 80, 100].map((c) => translateEvolution(c, 0).level);
    for (let i = 1; i < levels.length; i++) expect(levels[i]).toBeGreaterThanOrEqual(levels[i - 1]);
  });
});

describe("ownerEvolution(owner 侧真实分)", () => {
  it("返回真实 capability/dims/profile_summary(owner 例外)", () => {
    const p = normalizeProfile({ topics: { ai: 2, chips: 1 }, entities: { OpenAI: 1.5 }, muted: ["spam"] });
    const o = ownerEvolution(p, 10);
    expect(typeof o.capability).toBe("number");
    expect(o.dims).toBeTruthy();
    expect(o.profile_summary.top_topics[0].name).toBe("ai"); // 权重最高在前
    expect(o.profile_summary.muted_count).toBe(1);
    expect(Array.isArray(o.trend)).toBe(true);
  });
});
