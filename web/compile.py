#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loop News 小编译系统:把全部 data/analysis/*.json + data/threads.json
编译成 **单个** docs/index.html(左侧日期/线索列表,右侧主区,JS 同页切换,无 iframe)。

用法:
    python3 web/compile.py            # 重建整站(单页)
    python3 web/compile.py --all      # 同上(保留兼容)

零第三方依赖:仅标准库;loop.yaml 用内置迷你解析器。
"""
import sys, os, json, html, glob, shutil, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS_DIR = os.path.join(ROOT, "data", "analysis")
CORPUS_DIR = os.path.join(ROOT, "data", "corpus")
THREADS_PATH = os.path.join(ROOT, "data", "threads.json")
DOCS_DIR = os.path.join(ROOT, "docs")
TPL = os.path.join(ROOT, "web", "templates", "page.html")
ASSETS_SRC = os.path.join(ROOT, "web", "assets")
ASSETS_DST = os.path.join(DOCS_DIR, "assets")
CFG_PATH = os.path.join(ROOT, "config", "loop.yaml")
GRADE_CLASS = {"事实": "grade-fact", "推断": "grade-infer", "预测": "grade-predict"}


# ── 迷你 YAML(仅支持 loop.yaml 的嵌套标量 map 子集) ──
def load_yaml_min(path):
    root = {}; stack = [(-1, root)]
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if " #" in line:
                line = line[: line.index(" #")]
            indent = len(line) - len(line.lstrip(" "))
            key, _, val = line.strip().partition(":")
            key = key.strip(); val = val.strip()
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if val == "":
                node = {}; parent[key] = node; stack.append((indent, node))
            else:
                parent[key] = _coerce(val)
    return root


def _coerce(v):
    if (v[:1] == '"' and v[-1:] == '"') or (v[:1] == "'" and v[-1:] == "'"):
        return v[1:-1]
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def cfg_get(cfg, path, default=""):
    cur = cfg
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


def e(s):
    return html.escape(str(s if s is not None else ""))


HL_RE = re.compile(r"==(.+?)==")
HL_CAP = 2  # 每块最多高亮处数;main 中按 config 覆盖


def hl(s):
    """先转义,再把 ==文本== 转成 <mark>(最多 HL_CAP 处;多出的去掉 == 保留文字)。"""
    if s is None:
        return ""
    n = [0]
    def repl(m):
        n[0] += 1
        return f'<mark class="hl">{m.group(1)}</mark>' if n[0] <= HL_CAP else m.group(1)
    return HL_RE.sub(repl, e(s))


# ── 数据加载 ──
def all_dates():
    ds = [os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(ANALYSIS_DIR, "*.json"))]
    return sorted(ds, reverse=True)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_id_to_date():
    """扫描全部语料,建立 条目id → 日期 映射(供跨日期证据/线索链接)。"""
    m = {}
    for p in glob.glob(os.path.join(CORPUS_DIR, "*.json")):
        date = os.path.splitext(os.path.basename(p))[0]
        try:
            items = load_json(p, [])
        except Exception:
            continue
        for it in items or []:
            if isinstance(it, dict) and it.get("id"):
                m[it["id"]] = date
    # 分析文件内嵌的条目兜底
    for d in all_dates():
        a = load_json(os.path.join(ANALYSIS_DIR, d + ".json"), {}) or {}
        for it in (a.get("consensus", []) + a.get("deep", [])):
            if it.get("id") and it["id"] not in m:
                m[it["id"]] = d
    return m


# ── 反馈按钮(指向 GitHub Issues) ──
def fb_row(cfg, date, item_id, title):
    """三键反馈(赞/踩/采用),点击弹出页面内对话框(JS 处理),不跳转。"""
    if not cfg_get(cfg, "feedback.enabled", True):
        return ""
    iid, d, t = e(item_id), e(date), e(title)
    def btn(act, label):
        return (f'<button class="fb" data-act="{act}" data-item="{iid}" '
                f'data-date="{d}" data-title="{t}">{label}</button>')
    return (f'<div class="fb-row">{btn("up", "👍 赞")}{btn("down", "👎 踩")}'
            f'{btn("adopt", "✓ 采用")}</div>')


def ev_links(ev, id_to_date):
    parts = []
    for x in ev or []:
        d = id_to_date.get(x)
        parts.append(f'<a href="#{e(d)}__{e(x)}">{e(x)}</a>' if d else e(x))
    return ", ".join(parts)


# ── 分区渲染 ──
def render_consensus(items, cfg, date):
    if not items:
        return '<p class="empty">本期暂无共识类要闻。</p>'
    out = []
    for it in items:
        topics = "".join(f'<span class="topic">#{e(t)}</span> ' for t in it.get("topics", []))
        cc = it.get("consensus_count", len(it.get("sources", [])))
        src_badge = f'<span class="badge badge-consensus">{e(cc)} 家在报</span>' if cc else ""
        src_list = " · ".join(e(s) for s in it.get("sources", []))
        url = it.get("url", "")
        link = f'<a href="{e(url)}" target="_blank" rel="noopener">原文 ↗</a>' if url else ""
        out.append(f"""<article class="card" id="item-{e(it.get('id'))}">
  <h3>{e(it.get('title_zh'))}</h3>
  <p>{hl(it.get('summary_zh'))}</p>
  <div class="meta-row">{src_badge}<span class="badge badge-src">{src_list}</span>{topics}{link}</div>
  {fb_row(cfg, date, it.get('id',''), it.get('title_zh',''))}
</article>""")
    return "\n".join(out)


def render_deep(items, cfg, date):
    if not items:
        return '<p class="empty">本期暂无深度原声。</p>'
    out = []
    for it in items:
        quote = it.get("original_quote", "")
        lang = e(it.get("lang"))
        pq = f'<blockquote class="pq" lang="{lang}">{e(quote)}</blockquote>' if quote else ""
        insight = it.get("insight_zh", "")
        ihtml = f'<p class="insight">{e(insight)}</p>' if insight else ""
        url = it.get("url", "")
        link = f'<a class="src-link" href="{e(url)}" target="_blank" rel="noopener">来源 ↗</a>' if url else ""
        out.append(f"""<article class="card deep" id="item-{e(it.get('id'))}">
  <div class="byline"><span class="byline-src">{e(it.get('source'))}</span>{link}</div>
  {pq}
  <h3 class="deep-title">{e(it.get('title_zh'))}</h3>
  <p class="deep-sum">{hl(it.get('summary_zh'))}</p>
  {ihtml}
  {fb_row(cfg, date, it.get('id',''), it.get('title_zh',''))}
</article>""")
    return "\n".join(out)


def render_connections(conns, id_to_date):
    if not conns:
        return '<p class="empty">本期暂无跨条目关联。</p>'
    out = []
    for c in conns:
        ev = ev_links(c.get("evidence", []), id_to_date)
        evhtml = f'<div class="evidence">证据:{ev}</div>' if ev else ""
        out.append(f"""<div class="conn">
  <span class="lens">{e(c.get('lens'))}</span>
  <h3>{e(c.get('title_zh'))}</h3>
  <p>{hl(c.get('narrative_zh'))}</p>
  {evhtml}
</div>""")
    return "\n".join(out)


def render_conclusions(concls, cfg, date, id_to_date):
    if not concls:
        return '<p class="empty">本期暂无结论。</p>'
    out = []
    for i, c in enumerate(concls):
        g = c.get("grade", "推断"); gc = GRADE_CLASS.get(g, "grade-infer")
        conf = c.get("confidence")
        confhtml = f'<span class="conf">置信度 {int(conf*100)}%</span>' if isinstance(conf, (int, float)) else ""
        ev = ev_links(c.get("evidence", []), id_to_date)
        evhtml = f'<div class="evidence">证据:{ev}</div>' if ev else ""
        cid = f"{date}-concl-{i}"
        out.append(f"""<div class="concl">
  <p><span class="grade {gc}">{e(g)}</span>{hl(c.get('text_zh'))} {confhtml}</p>
  {evhtml}
  {fb_row(cfg, date, cid, c.get('text_zh',''))}
</div>""")
    return "\n".join(out)


def render_day(a, cfg, id_to_date):
    date = a.get("date", "")
    note = a.get("methodology_note_zh", "")
    note_html = f'<div class="section"><h2 class="section-title">方法论说明</h2><p>{e(note)}</p></div>' if note else ""
    inner = f"""<div class="day-meta">
  <h1 class="day-date">{e(date)}</h1>
  <p class="day-summary">{e(a.get('summary_zh'))}</p>
</div>
<section class="section"><h2 class="section-title">今日要闻 · 共识</h2>
{render_consensus(a.get('consensus', []), cfg, date)}
</section>
<section class="section"><h2 class="section-title">深度原声</h2>
{render_deep(a.get('deep', []), cfg, date)}
</section>
<section class="section"><h2 class="section-title">关联</h2>
{render_connections(a.get('connections', []), id_to_date)}
</section>
<section class="section"><h2 class="section-title">结论 · 事实 / 推断 / 预测</h2>
{render_conclusions(a.get('conclusions', []), cfg, date, id_to_date)}
</section>
{note_html}"""
    return f'<section class="view day" id="day-{e(date)}">{inner}</section>'


def render_threads(threads):
    if not threads:
        return ('<section class="view" id="view-threads"><h1 class="day-date">线索时间线</h1>'
                '<p class="empty">暂无跨日期线索。</p></section>')
    blocks = []
    for t in threads:
        entries = []
        for en in t.get("timeline", []):
            d = en.get("date", "")
            iid = en.get("item_id", "")
            href = f"#{e(d)}__{e(iid)}" if iid else f"#{e(d)}"
            entries.append(f"""<li class="tl-entry">
  <a href="{href}"><span class="tl-date">{e(d)}</span> · <span class="tl-title">{e(en.get('title_zh'))}</span></a>
  <div class="tl-note">{e(en.get('note_zh'))}</div>
</li>""")
        blocks.append(f"""<div class="thread">
  <span class="tstatus">{e(t.get('status_zh'))}</span>
  <h3>{e(t.get('title_zh'))}</h3>
  <p class="tsum">{e(t.get('summary_zh'))}</p>
  <ul class="timeline">{''.join(entries)}</ul>
</div>""")
    return (f'<section class="view" id="view-threads">'
            f'<h1 class="day-date">🧵 线索时间线</h1>'
            f'<p class="intro">把同一主题/主体跨多天串成一条线,看它如何演进。点任一节点跳到那条新闻。</p>'
            f'{"".join(blocks)}</section>')


def render_nav(dates, analyses):
    links = []
    for d in dates:
        a = analyses.get(d, {})
        n = len(a.get("consensus", [])) + len(a.get("deep", []))
        links.append(f'<a class="nav-link day" data-target="day-{e(d)}" href="#{e(d)}">{e(d)}'
                     f'<br><span class="nd">{n} 条</span></a>')
    return "\n".join(links)


def main():
    os.makedirs(DOCS_DIR, exist_ok=True)
    cfg = load_yaml_min(CFG_PATH) if os.path.exists(CFG_PATH) else {}
    global HL_CAP
    HL_CAP = int(cfg_get(cfg, "feedback.highlight_max", 2) or 2)
    fb_tags = load_json(os.path.join(ROOT, "config", "feedback_tags.json"), {}) or {}
    dates = all_dates()
    if not dates:
        sys.exit("[compile] data/analysis 下没有任何分析文件。")
    analyses = {d: load_json(os.path.join(ANALYSIS_DIR, d + ".json"), {}) for d in dates}
    id_to_date = build_id_to_date()
    threads = (load_json(THREADS_PATH, {}) or {}).get("threads", [])

    threads_view = render_threads(threads)
    day_views = "\n".join(render_day(analyses[d], cfg, id_to_date) for d in dates)
    date_nav = render_nav(dates, analyses)

    with open(TPL, encoding="utf-8") as f:
        tpl = f.read()
    footer = (f'由 Loop Engineering 自动编译 · 共 {len(dates)} 期 · '
              f'<a href="https://github.com/{e(cfg_get(cfg,"site.repo"))}" target="_blank" rel="noopener">GitHub</a> · '
              f'{e(cfg_get(cfg, "site.author"))}')
    repl = {
        "{{SITE_TITLE}}": e(cfg_get(cfg, "site.title", "Loop News")),
        "{{SITE_SUBTITLE}}": e(cfg_get(cfg, "site.subtitle")),
        "{{PAGE_DESC}}": e(analyses[dates[0]].get("summary_zh", "").replace("==", "")),
        "{{DATE_NAV}}": date_nav,
        "{{THREADS_VIEW}}": threads_view,
        "{{DAY_VIEWS}}": day_views,
        "{{FOOTER}}": footer,
        "{{FEEDBACK_ENABLED}}": "true" if cfg_get(cfg, "feedback.enabled", True) else "false",
        "{{FEEDBACK_API}}": e(cfg_get(cfg, "feedback.api_url", "")),
        "{{FEEDBACK_TAGS}}": json.dumps(fb_tags, ensure_ascii=False),
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)

    # 清理旧的分日/归档页(单页化后不再需要)
    for old in glob.glob(os.path.join(DOCS_DIR, "*.html")):
        if os.path.basename(old) != "index.html":
            os.remove(old)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(tpl)
    print(f"[compile] 写出 docs/index.html(单页,{len(dates)} 期,{len(threads)} 条线索)")

    os.makedirs(ASSETS_DST, exist_ok=True)
    for fn in os.listdir(ASSETS_SRC):
        shutil.copy2(os.path.join(ASSETS_SRC, fn), os.path.join(ASSETS_DST, fn))
    print(f"[compile] 同步 assets → {ASSETS_DST}")
    print("[compile] 完成。")


if __name__ == "__main__":
    main()
