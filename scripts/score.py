#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Loop News 系统评分器(确定性,非 LLM)。六个分数,每轮都算、都要往上涨:
  1) correlation   新闻关联度   —— 关联/跨日期/非显然 结论的密度
  2) volume        新闻数量      —— 采集量 vs 目标;低于底线 = 陡峭惩罚
  3) analysis      分析整合      —— 分级结论/证据回链/共识缺口/可证伪
  4) breadth       自进化广度    —— 来源角度/话题覆盖/领域专题/已消化反馈
  5) source_quality 信息源固化   —— 已固化 core 源数量/质量、采自 core 占比、是否在持续评选(否则衰减)
  6) timeliness    新闻及时性    —— 采集日−事件日 的 lateness;旧闻/漏采后补 双重惩罚,多条陈旧强惩罚
外加 composite = 六者均值。写入 state/scores.json(时间序列 + 与上轮的 delta)。
用法:python3 scripts/score.py [YYYY-MM-DD]   # 默认最新有分析的日期
被 ln-synthesize/ln-evolve/ln-daily 调用;agent 每轮都要看分数、并优先把最低/下滑的那个提上去。
"""
import json, os, re, glob, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def J(p, d=None):
    try:
        with open(os.path.join(ROOT, p), encoding="utf-8") as f: return json.load(f)
    except Exception: return d
def txt(p):
    try:
        with open(os.path.join(ROOT, p), encoding="utf-8") as f: return f.read()
    except Exception: return ""

TARGETS = {"volume_target": 20, "volume_floor": 12, "connections": 6, "cross_date": 3,
           "non_obvious": 4, "conclusions": 8, "edge": 3, "falsifiable": 2,
           "sources": 30, "topics": 20, "domains": 3, "feedback_recent": 6, "angles": 8, "core_sources": 12,
           "fresh_days": 4, "stale_decay": 0.78}

def clamp01(x): return max(0.0, min(1.0, x))

def is_7xx_id(i):  # 2026-07-01 起用 16 位 hex id;更早用 co-/dp- 前缀 → 用于识别跨日期证据
    return bool(re.fullmatch(r"[0-9a-f]{16}", str(i)))

def spans_dates(ev):
    kinds = {is_7xx_id(i) for i in (ev or [])}
    return len(kinds) >= 2  # 证据里同时有"今日 hex id"和"历史 co-/dp- id" = 跨日期

def volume_score(c):
    T, F = TARGETS["volume_target"], TARGETS["volume_floor"]
    if c >= T: return 100.0
    if c >= F: return round(55 + 45 * (c - F) / (T - F), 1)
    return round(55 * (c / F) ** 2, 1)  # 低于底线:平方级陡峭惩罚(6 条≈14 分)

def compute(date):
    a = J(f"data/analysis/{date}.json", {}) or {}
    corpus = J(f"data/corpus/{date}.json", []) or []
    conns = a.get("connections", []); concls = a.get("conclusions", [])
    # 关联度
    cross_date = sum(1 for x in conns if "时间线" in x.get("lens", "") or spans_dates(x.get("evidence"))) \
               + sum(1 for x in concls if spans_dates(x.get("evidence")))
    non_obvious = sum(1 for x in concls if len(x.get("evidence", [])) >= 2 and x.get("grade") != "事实")
    correlation = 100 * (0.30 * clamp01(len(conns) / TARGETS["connections"])
                       + 0.35 * clamp01(cross_date / TARGETS["cross_date"])
                       + 0.35 * clamp01(non_obvious / TARGETS["non_obvious"]))
    # 数量
    collected = len(corpus)
    volume = volume_score(collected)
    # 分析整合
    grades = [x.get("grade") for x in concls]
    graded = 1.0 if concls and all(g in ("事实", "推断", "预测") for g in grades) else (0.5 if concls else 0.0)
    ev_ratio = (sum(1 for x in concls if x.get("evidence")) / len(concls)) if concls else 0.0
    edge = sum(1 for x in conns if x.get("lens", "") and any(k in x["lens"] for k in ("共识缺口", "矛盾")))
    falsifiable = sum(1 for x in concls if x.get("grade") == "预测")
    analysis = 100 * (0.25 * clamp01(len(concls) / TARGETS["conclusions"]) + 0.25 * ev_ratio
                    + 0.20 * clamp01(edge / TARGETS["edge"]) + 0.15 * clamp01(falsifiable / TARGETS["falsifiable"])
                    + 0.15 * graded)
    # 自进化广度
    src = txt("config/sources.yaml")
    angles = len(re.findall(r'^\s*-\s*"', src, re.M))                       # web_search_queries 组数(近似)
    sources = angles + len(re.findall(r'-\s*\{\s*name:', src)) + src.count("okjike")  # + RSS/平台
    pods = txt("config/podcasts.yaml"); sources += pods.count("name:")
    topics = len({t for it in corpus for t in it.get("topics", [])})
    domains = len(glob.glob(os.path.join(ROOT, "data/dossiers/*.json")))
    ledger = J("data/feedback_ledger.json", {}) or {}
    feedback_recent = len((ledger.get("cycles") or [{}])[0].get("covered", [])) if ledger.get("cycles") else 0
    breadth = 100 * (0.28 * clamp01(sources / TARGETS["sources"]) + 0.24 * clamp01(topics / TARGETS["topics"])
                   + 0.20 * clamp01(domains / TARGETS["domains"]) + 0.16 * clamp01(feedback_recent / TARGETS["feedback_recent"])
                   + 0.12 * clamp01(angles / TARGETS["angles"]))
    # 信息源固化(第 5 分):固化(core)源够不够 + 质量 + 今日采自已固化源的占比 + 是否在持续评选(否则衰减=惩罚)
    sq = J("data/source_quality.json", {}) or {}
    srcs = sq.get("sources", {})
    core = [n for n, v in srcs.items() if v.get("tier") == "core"]
    core_n = len(core)
    core_q = (sum(srcs[n].get("quality", 0) for n in core) / core_n) if core_n else 0.0
    def is_core(itsrc):
        return any((n in itsrc) and srcs[n].get("tier") == "core" for n in srcs)
    from_core = sum(1 for it in corpus if is_core(it.get("source", ""))) / len(corpus) if corpus else 0.0
    # 持续评选:距上次评选越久,curation 越低(强迫每轮评选来源;>7 天基本清零)
    lc = sq.get("last_curation", "")
    try:
        days = (datetime.date(*map(int, date.split("-"))) - datetime.date(*map(int, lc.split("-")))).days
        curation = 1.0 if days <= 1 else 0.7 if days <= 3 else 0.4 if days <= 7 else 0.15
    except Exception:
        curation = 0.3
    source_quality = 100 * (0.35 * clamp01(core_n / TARGETS["core_sources"]) + 0.25 * clamp01(core_q)
                          + 0.25 * clamp01(from_core) + 0.15 * curation)
    # 及时性(第 6 分):lateness = 采集日 − 事件日(published)。越大 = 既是旧闻、又说明当时漏采现在才补 →
    # 双重触发惩罚;一天里多条『超过几天』→ 用 0.78ⁿ 强惩罚,几条就大跌(硬约束:新闻要实时,漏采要罚)。
    def d2(sd):
        try: return datetime.date(*map(int, str(sd).split("-")))
        except Exception: return None
    col = d2(date)
    news = [it for it in corpus if it.get("category") in ("consensus", "deep")]
    def lateness(it):
        p = d2(it.get("published"))
        return max(0, (col - p).days) if (p and col) else None
    lts = [lateness(it) for it in news]
    stamped = [x for x in lts if x is not None]
    coverage = (len(stamped) / len(news)) if news else 1.0      # 未标事件日 = 无法主张及时 → 拉低
    def fresh_w(x):
        return 1.0 if x <= 1 else 0.85 if x <= 3 else 0.5 if x <= 5 else 0.2 if x <= 8 else 0.05
    recency = (sum(fresh_w(x) for x in stamped) / len(stamped)) if stamped else 0.0
    realtime = (sum(1 for x in stamped if x <= 2) / len(stamped)) if stamped else 0.0
    stale_n = sum(1 for x in stamped if x > TARGETS["fresh_days"])   # 超过几天 = 陈旧/漏采后补
    penalty = TARGETS["stale_decay"] ** max(0, stale_n - 1)          # 容忍 1 条,之后每条 ×0.78 → 多条即大跌
    avg_late = round(sum(stamped) / len(stamped), 1) if stamped else None
    timeliness = 100 * coverage * (0.5 * recency + 0.5 * realtime) * penalty
    scores = {k: round(v, 1) for k, v in {"correlation": correlation, "volume": volume, "analysis": analysis,
              "breadth": breadth, "source_quality": source_quality, "timeliness": timeliness}.items()}
    scores["composite"] = round((scores["correlation"] + scores["volume"] + scores["analysis"] + scores["breadth"]
                               + scores["source_quality"] + scores["timeliness"]) / 6, 1)
    comps = {"collected": collected, "connections": len(conns), "cross_date": cross_date,
             "non_obvious": non_obvious, "conclusions": len(concls), "edge": edge,
             "falsifiable": falsifiable, "evidence_ratio": round(ev_ratio, 2), "graded": graded,
             "sources": sources, "topics": topics, "domains": domains, "feedback_recent": feedback_recent,
             "angles": angles, "core_sources": core_n, "core_quality": round(core_q, 2),
             "from_core_share": round(from_core, 2), "curation_freshness": round(curation, 2),
             "fresh_le2d": sum(1 for x in stamped if x <= 2), "stale_gt4d": stale_n,
             "avg_lateness_d": avg_late, "recency_coverage": round(coverage, 2)}
    return scores, comps

def main():
    date = sys.argv[1] if len(sys.argv) > 1 else None
    if not date:
        ds = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ROOT, "data/analysis/*.json")))
        if not ds: sys.exit("no analysis")
        date = ds[-1]
    scores, comps = compute(date)
    store = J("state/scores.json", {"targets": TARGETS, "history": []}) or {"targets": TARGETS, "history": []}
    hist = store.setdefault("history", [])
    prev = next((h for h in reversed(hist) if h["date"] < date), hist[-1] if hist else None)
    delta = {k: round(scores[k] - prev["scores"].get(k, 0), 1) for k in scores} if prev else {k: None for k in scores}
    entry = {"date": date, "computed_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
             "scores": scores, "components": comps, "delta_vs_prev": delta}
    hist = [h for h in hist if h["date"] != date] + [entry]
    hist.sort(key=lambda h: h["date"])
    store["history"] = hist; store["targets"] = TARGETS
    with open(os.path.join(ROOT, "state/scores.json"), "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    print(f"[score] {date}  综合 {scores['composite']}  = 关联 {scores['correlation']} · 数量 {scores['volume']} · 分析 {scores['analysis']} · 广度 {scores['breadth']} · 源固化 {scores['source_quality']} · 及时 {scores['timeliness']}")
    if prev: print(f"        Δvs {prev['date']}: " + " ".join(f"{k}{'+' if (delta[k] or 0)>=0 else ''}{delta[k]}" for k in ["composite","correlation","volume","analysis","breadth","source_quality","timeliness"]))
    low = min(scores, key=lambda k: scores[k] if k != "composite" else 999)
    print(f"        ⚠ 最低分 = {low}({scores[low]})→ 下一轮优先把它提上去")
    return scores

if __name__ == "__main__":
    main()
