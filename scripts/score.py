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
           "fresh_days": 4, "stale_decay": 0.78,
           # 第7/8分(克制/创新)新增目标:
           "novelty_window": 7,        # 创新对比的历史窗口 K(天)
           "novel_target": 6,          # new_productive:近窗口未见过的话题/实体数量目标
           "lens_target": 5,           # lens_diversity:透镜种类数(含冷门加成)目标
           "cross_domain_target": 2}   # cross_domain_novel:近窗口未配过的跨域连接数目标

def clamp01(x): return max(0.0, min(1.0, x))

def is_7xx_id(i):  # 2026-07-01 起用 16 位 hex id;更早用 co-/dp- 前缀 → 用于识别跨日期证据
    return bool(re.fullmatch(r"[0-9a-f]{16}", str(i)))

def spans_dates(ev):
    kinds = {is_7xx_id(i) for i in (ev or [])}
    return len(kinds) >= 2  # 证据里同时有"今日 hex id"和"历史 co-/dp- id" = 跨日期

def _date(s):
    try: return datetime.date(*map(int, str(s).split("-")))
    except Exception: return None

def _find_prev(hist, date):
    return next((h for h in reversed(hist) if h["date"] < date), hist[-1] if hist else None)

# ── 第7分 克制 restraint ─────────────────────────────────────────────────────
_CONF_KEYS = ("confidence", "probability", "概率", "置信度")
def _has_conf(c):
    return any(isinstance(c.get(k), (int, float)) for k in _CONF_KEYS)

def restraint_score(a, corpus):
    """第7分 克制:大胆结论是否被证据/分级/置信度约束 + 呈现信噪比。
    纯函数(入参=已加载的 analysis dict + corpus list),不依赖磁盘上特定日期文件,便于单测。"""
    concls = a.get("conclusions", []) or []
    conns = a.get("connections", []) or []
    bold = [c for c in concls if c.get("grade") in ("推断", "预测")]
    # 置信度检测:若本份 analysis 的结论 schema 带 confidence/概率字段(任一结论有 → 视作 schema 支持),
    # 则"预测"缺置信度标注也算越界;若整份 schema 无此字段,则"预测"的越界判据退化为仅 len(evidence)<2。
    # (实测 data/analysis 里结论普遍带 confidence 浮点字段,故这里会启用置信度判据。)
    schema_has_conf = any(_has_conf(c) for c in concls)
    def _over(c):
        if len(c.get("evidence", []) or []) < 2: return True
        if c.get("grade") == "预测" and schema_has_conf and not _has_conf(c): return True
        return False
    overreach = sum(1 for c in bold if _over(c))
    overreach_rate = (overreach / len(bold)) if bold else 0.0
    grounded = 1.0 - overreach_rate
    p = (sum(1 for c in concls if c.get("grade") == "预测") / len(concls)) if concls else 0.0
    grade_discipline = 1.0 if p <= 0.4 else clamp01(1 - (p - 0.4) / 0.6)
    if bold:
        evidence_depth = clamp01((sum(len(c.get("evidence", []) or []) for c in bold) / len(bold)) / 2)
    else:
        evidence_depth = 1.0  # 无大胆结论 → 没有浅证据可罚,视作充分克制(而非 0/0 罚满)
    cited = set()
    for c in list(concls) + list(conns):
        for e in (c.get("evidence") or []): cited.add(e)
    corpus_ids = {it.get("id") for it in corpus if it.get("id")}
    snr = clamp01(len(cited & corpus_ids) / len(corpus_ids)) if corpus_ids else 1.0
    restraint = 100 * (0.40 * grounded + 0.20 * grade_discipline + 0.20 * evidence_depth + 0.20 * snr)
    comps = {"overreach_rate": round(overreach_rate, 2), "grounded": round(grounded, 2),
             "grade_discipline": round(grade_discipline, 2), "evidence_depth": round(evidence_depth, 2),
             "snr": round(snr, 2)}
    return round(restraint, 1), comps

# ── 第8分 创新 innovation ────────────────────────────────────────────────────
def _conn_topics(conn, corpus_by_id):
    tops = set()
    for e in (conn.get("evidence") or []):
        it = corpus_by_id.get(e)
        if it: tops |= set(it.get("topics", []) or [])
    return tops

def _conn_sig(conn, corpus_by_id):
    tops = _conn_topics(conn, corpus_by_id)
    return frozenset(tops) if tops else frozenset({conn.get("title_zh") or conn.get("lens") or ""})

def _learning_velocity(prev_scores, cur_partial):
    if not prev_scores: return 0.5                                   # 无上一 entry → 中性
    cand = {k: v for k, v in prev_scores.items() if k != "composite"}
    if not cand: return 0.5
    low_dim = min(cand, key=lambda k: cand[k])                       # 上轮最低分维度
    if low_dim not in cur_partial: return 0.5  # 最弱维=innovation 自身时避免自引用循环 → 中性
    d = round(cur_partial[low_dim] - prev_scores[low_dim], 1)        # 本轮该维 delta_vs_prev
    return 1.0 if d > 0 else (0.5 if d == 0 else 0.0)

def innovation_score(today_tokens, prior_seen, from_core_share, conns, corpus_by_id,
                     prior_pairs, prev_scores, cur_partial, targets):
    """第8分 创新:新产出话题/实体、探索非core、透镜多样、跨域新配对、学习速度。
    纯函数(入参皆为已加载/预算好的数据),便于单测。"""
    new_tokens = {t for t in today_tokens if t} - set(prior_seen or ())
    new_productive = clamp01(len(new_tokens) / targets["novel_target"])
    exploration = clamp01((1 - from_core_share) / 0.5)              # 与第5分反向:逼别只吃 core
    lenses = [c.get("lens", "") for c in conns]
    kinds = len({l for l in lenses if l})
    RARE = ("二阶效应", "跨域", "跟着钱走", "共识缺口")
    rare_bonus = sum(1 for r in RARE if any(r in l for l in lenses))
    lens_diversity = clamp01((kinds + rare_bonus) / targets["lens_target"])
    novel = 0
    for c in conns:
        tops = _conn_topics(c, corpus_by_id)
        if not (("跨域" in c.get("lens", "")) or len(tops) >= 2): continue  # 标注跨域 / 证据跨话题域
        if _conn_sig(c, corpus_by_id) not in (prior_pairs or set()): novel += 1  # 近窗口未配过
    cross_domain_novel = clamp01(novel / targets["cross_domain_target"])
    learning_velocity = _learning_velocity(prev_scores, cur_partial)
    innovation = 100 * (0.25 * new_productive + 0.20 * exploration + 0.20 * lens_diversity
                       + 0.20 * cross_domain_novel + 0.15 * learning_velocity)
    comps = {"new_productive": round(new_productive, 2), "exploration": round(exploration, 2),
             "lens_diversity": round(lens_diversity, 2), "cross_domain_novel": round(cross_domain_novel, 2),
             "learning_velocity": round(learning_velocity, 2)}
    return round(innovation, 1), comps

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
    # ── 第7分 克制 restraint(analysis + corpus 确定性)──
    restraint, rcomps = restraint_score(a, corpus)
    scores["restraint"] = restraint
    # ── 第8分 创新 innovation(对比 K 天历史窗口)──
    K = TARGETS["novelty_window"]
    col_d = _date(date)
    prior_seen, prior_pairs = set(), set()
    if col_d:
        lo = col_d - datetime.timedelta(days=K)
        for cp in glob.glob(os.path.join(ROOT, "data/corpus/*.json")):        # 近 K 天语料的话题/实体
            dnm = os.path.basename(cp)[:-5]; dd = _date(dnm)
            if dd and lo <= dd < col_d:
                for it in (J(f"data/corpus/{dnm}.json", []) or []):
                    prior_seen |= set(it.get("topics", []) or []); prior_seen |= set(it.get("entities", []) or [])
        for ent, occ in (J("data/entities/index.json", {}) or {}).items():    # 实体索引:近 K 天出现过的实体
            if any((_date(o.get("date")) and lo <= _date(o.get("date")) < col_d) for o in (occ or [])):
                prior_seen.add(ent)
        for ap in glob.glob(os.path.join(ROOT, "data/analysis/*.json")):      # 近 K 天已配过的跨域连接签名
            dnm = os.path.basename(ap)[:-5]; dd = _date(dnm)
            if dd and lo <= dd < col_d:
                pa = J(f"data/analysis/{dnm}.json", {}) or {}
                pmap = {x.get("id"): x for x in (J(f"data/corpus/{dnm}.json", []) or []) if x.get("id")}
                for cn in (pa.get("connections", []) or []):
                    ptops = _conn_topics(cn, pmap)
                    if ("跨域" in cn.get("lens", "")) or len(ptops) >= 2:
                        prior_pairs.add(_conn_sig(cn, pmap))
    today_tokens = set()
    for it in corpus:
        today_tokens |= set(it.get("topics", []) or []); today_tokens |= set(it.get("entities", []) or [])
    corpus_by_id = {it.get("id"): it for it in corpus if it.get("id")}
    prev = _find_prev((J("state/scores.json", {}) or {}).get("history", []), date)
    prev_scores = prev.get("scores") if prev else None
    cur_partial = {k: scores[k] for k in ("correlation", "volume", "analysis", "breadth", "source_quality", "timeliness", "restraint")}
    innovation, icomps = innovation_score(today_tokens, prior_seen, from_core, conns, corpus_by_id,
                                          prior_pairs, prev_scores, cur_partial, TARGETS)
    scores["innovation"] = innovation
    scores["composite"] = round((scores["correlation"] + scores["volume"] + scores["analysis"] + scores["breadth"]
                               + scores["source_quality"] + scores["timeliness"]
                               + scores["restraint"] + scores["innovation"]) / 8, 1)
    comps = {"collected": collected, "connections": len(conns), "cross_date": cross_date,
             "non_obvious": non_obvious, "conclusions": len(concls), "edge": edge,
             "falsifiable": falsifiable, "evidence_ratio": round(ev_ratio, 2), "graded": graded,
             "sources": sources, "topics": topics, "domains": domains, "feedback_recent": feedback_recent,
             "angles": angles, "core_sources": core_n, "core_quality": round(core_q, 2),
             "from_core_share": round(from_core, 2), "curation_freshness": round(curation, 2),
             "fresh_le2d": sum(1 for x in stamped if x <= 2), "stale_gt4d": stale_n,
             "avg_lateness_d": avg_late, "recency_coverage": round(coverage, 2)}
    comps.update(rcomps); comps.update(icomps)   # 透明化:克制/创新的分项成分
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
    prev = _find_prev(hist, date)
    # 向后兼容:prev 中不存在的键(旧 entry 只有 6 分)→ delta 取 None(不是 new−0);旧 entry composite 不重算
    if prev:
        delta = {}
        for k in scores:
            pv = prev["scores"].get(k)
            delta[k] = round(scores[k] - pv, 1) if pv is not None else None
    else:
        delta = {k: None for k in scores}
    entry = {"date": date, "computed_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
             "scores": scores, "components": comps, "delta_vs_prev": delta}
    hist = [h for h in hist if h["date"] != date] + [entry]
    hist.sort(key=lambda h: h["date"])
    store["history"] = hist; store["targets"] = TARGETS
    with open(os.path.join(ROOT, "state/scores.json"), "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    print(f"[score] {date}  综合 {scores['composite']}  = 关联 {scores['correlation']} · 数量 {scores['volume']} · 分析 {scores['analysis']} · 广度 {scores['breadth']} · 源固化 {scores['source_quality']} · 及时 {scores['timeliness']} · 克制 {scores['restraint']} · 创新 {scores['innovation']}")
    if prev:
        def _fd(k):
            d = delta.get(k)
            return f"{k}=—" if d is None else f"{k}{'+' if d >= 0 else ''}{d}"   # None(旧 entry 无此维)→ 显示 —
        print(f"        Δvs {prev['date']}: " + " ".join(_fd(k) for k in
              ["composite","correlation","volume","analysis","breadth","source_quality","timeliness","restraint","innovation"]))
    low = min(scores, key=lambda k: scores[k] if k != "composite" else 999)
    print(f"        ⚠ 最低分 = {low}({scores[low]})→ 下一轮优先把它提上去")
    return scores

if __name__ == "__main__":
    main()
