#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loop News 小编译系统:把 data/analysis/<date>.json 编译成 docs/ 下的纯静态网页。

用法:
    python3 web/compile.py            # 编译昨天(Asia/Shanghai)
    python3 web/compile.py 2026-06-29 # 编译指定日期
    python3 web/compile.py --all      # 重建全部历史页面(模板/样式改版后用)

零第三方依赖:只用 Python 标准库;loop.yaml 用内置迷你解析器读取。
"""
import sys, os, json, html, glob, shutil
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS_DIR = os.path.join(ROOT, "data", "analysis")
DOCS_DIR = os.path.join(ROOT, "docs")
TPL = os.path.join(ROOT, "web", "templates", "page.html")
ASSETS_SRC = os.path.join(ROOT, "web", "assets")
ASSETS_DST = os.path.join(DOCS_DIR, "assets")
CFG_PATH = os.path.join(ROOT, "config", "loop.yaml")

CST = timezone(timedelta(hours=8))  # Asia/Shanghai


# ── 迷你 YAML 解析器:仅支持 loop.yaml 的"嵌套标量 map"子集 ──
def load_yaml_min(path):
    root = {}
    stack = [(-1, root)]
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            # 去行内注释(本文件值不含 '#',安全)
            if " #" in line:
                line = line[: line.index(" #")]
            indent = len(line) - len(line.lstrip(" "))
            key, _, val = line.strip().partition(":")
            key = key.strip()
            val = val.strip()
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if val == "":
                node = {}
                parent[key] = node
                stack.append((indent, node))
            else:
                parent[key] = _coerce(val)
    return root


def _coerce(v):
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
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


# ── 各分区渲染 ──
GRADE_CLASS = {"事实": "grade-fact", "推断": "grade-infer", "预测": "grade-predict"}


def render_consensus(items):
    if not items:
        return '<p class="empty">本期暂无共识类要闻。</p>'
    out = []
    for it in items:
        topics = "".join(f'<span class="topic">#{e(t)}</span> ' for t in it.get("topics", []))
        srcs = it.get("sources", [])
        cc = it.get("consensus_count", len(srcs))
        src_badge = f'<span class="badge badge-consensus">{e(cc)} 家在报</span>' if cc else ""
        src_list = " · ".join(e(s) for s in srcs)
        url = it.get("url", "")
        link = f'<a href="{e(url)}" target="_blank" rel="noopener">原文 ↗</a>' if url else ""
        out.append(f"""<article class="card">
  <h3>{e(it.get('title_zh'))}</h3>
  <p>{e(it.get('summary_zh'))}</p>
  <div class="meta-row">{src_badge}<span class="badge badge-src">{src_list}</span>{topics}{link}</div>
</article>""")
    return "\n".join(out)


def render_deep(items):
    if not items:
        return '<p class="empty">本期暂无深度原声。</p>'
    out = []
    for it in items:
        quote = it.get("original_quote", "")
        qhtml = ""
        if quote:
            qhtml = (f'<button class="quote-toggle">显示原文</button>'
                     f'<div class="quote-box">{e(quote)}</div>')
        insight = it.get("insight_zh", "")
        ihtml = f'<div class="insight">💡 {e(insight)}</div>' if insight else ""
        url = it.get("url", "")
        link = f'<a href="{e(url)}" target="_blank" rel="noopener">来源 ↗</a>' if url else ""
        out.append(f"""<article class="card">
  <h3>{e(it.get('title_zh'))}</h3>
  <div class="meta-row"><span class="badge badge-src">{e(it.get('source'))}</span><span class="topic">{e(it.get('lang'))}</span>{link}</div>
  <p>{e(it.get('summary_zh'))}</p>
  {ihtml}
  {qhtml}
</article>""")
    return "\n".join(out)


def render_connections(conns):
    if not conns:
        return '<p class="empty">本期暂无跨条目关联。</p>'
    out = []
    for c in conns:
        ev = c.get("evidence", [])
        evhtml = f'<div class="evidence">证据:{e(", ".join(ev))}</div>' if ev else ""
        out.append(f"""<div class="conn">
  <span class="lens">{e(c.get('lens'))}</span>
  <h3>{e(c.get('title_zh'))}</h3>
  <p>{e(c.get('narrative_zh'))}</p>
  {evhtml}
</div>""")
    return "\n".join(out)


def render_conclusions(concls):
    if not concls:
        return '<p class="empty">本期暂无结论。</p>'
    out = []
    for c in concls:
        g = c.get("grade", "推断")
        gc = GRADE_CLASS.get(g, "grade-infer")
        conf = c.get("confidence")
        confhtml = f'<span class="conf">置信度 {int(conf*100)}%</span>' if isinstance(conf, (int, float)) else ""
        ev = c.get("evidence", [])
        evhtml = f'<div class="evidence">证据:{e(", ".join(ev))}</div>' if ev else ""
        out.append(f"""<div class="concl">
  <p><span class="grade {gc}">{e(g)}</span>{e(c.get('text_zh'))} {confhtml}</p>
  {evhtml}
</div>""")
    return "\n".join(out)


def render_day_content(a):
    note = a.get("methodology_note_zh", "")
    note_html = f'<div class="section"><h2 class="section-title">方法论说明</h2><p>{e(note)}</p></div>' if note else ""
    return f"""<div class="day-meta">
  <h1 class="day-date">{e(a.get('date'))}</h1>
  <p class="day-summary">{e(a.get('summary_zh'))}</p>
</div>

<section class="section"><h2 class="section-title">今日要闻 · 共识</h2>
{render_consensus(a.get('consensus', []))}
</section>

<section class="section"><h2 class="section-title">深度原声</h2>
{render_deep(a.get('deep', []))}
</section>

<section class="section"><h2 class="section-title">关联</h2>
{render_connections(a.get('connections', []))}
</section>

<section class="section"><h2 class="section-title">结论 · 事实 / 推断 / 预测</h2>
{render_conclusions(a.get('conclusions', []))}
</section>

{note_html}"""


def render_page(cfg, page_title, page_desc, content):
    with open(TPL, encoding="utf-8") as f:
        tpl = f.read()
    footer = (f'由 Loop Engineering 自动编译 · '
              f'<a href="archive.html">历史归档</a> · '
              f'<a href="{e(cfg_get(cfg, "site.url"))}">{e(cfg_get(cfg, "site.author"))}</a>')
    repl = {
        "{{PAGE_TITLE}}": e(page_title),
        "{{PAGE_DESC}}": e(page_desc),
        "{{SITE_TITLE}}": e(cfg_get(cfg, "site.title", "Loop News")),
        "{{SITE_SUBTITLE}}": e(cfg_get(cfg, "site.subtitle")),
        "{{CONTENT}}": content,
        "{{FOOTER}}": footer,
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    return tpl


def load_analysis(date):
    p = os.path.join(ANALYSIS_DIR, f"{date}.json")
    if not os.path.exists(p):
        sys.exit(f"[compile] 缺少分析文件 {p};请先跑 ln-synthesize。")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def all_dates():
    ds = []
    for p in glob.glob(os.path.join(ANALYSIS_DIR, "*.json")):
        ds.append(os.path.splitext(os.path.basename(p))[0])
    return sorted(ds, reverse=True)


def build_day(cfg, date):
    a = load_analysis(date)
    title = f"{date} · {cfg_get(cfg, 'site.title', 'Loop News')}"
    page = render_page(cfg, title, a.get("summary_zh", ""), render_day_content(a))
    out = os.path.join(DOCS_DIR, f"{date}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"[compile] 写出 {out}")
    return a


def build_index(cfg, latest_date):
    a = load_analysis(latest_date)
    title = cfg_get(cfg, "site.title", "Loop News")
    page = render_page(cfg, title, a.get("summary_zh", ""), render_day_content(a))
    out = os.path.join(DOCS_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"[compile] 写出 {out}(指向最新一期 {latest_date})")


def build_archive(cfg):
    rows = []
    for d in all_dates():
        try:
            a = load_analysis(d)
            s = a.get("summary_zh", "")
        except SystemExit:
            s = ""
        rows.append(f'<li><a class="d" href="{e(d)}.html">{e(d)}</a><span class="topic">{e(s)}</span></li>')
    content = ('<div class="day-meta"><h1 class="day-date">历史归档</h1></div>'
               f'<ul class="archive-list">{"".join(rows) or "<li class=empty>暂无历史</li>"}</ul>')
    page = render_page(cfg, f"历史归档 · {cfg_get(cfg, 'site.title')}", "全部往期", content)
    out = os.path.join(DOCS_DIR, "archive.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"[compile] 写出 {out}")


def sync_assets():
    os.makedirs(ASSETS_DST, exist_ok=True)
    for fn in os.listdir(ASSETS_SRC):
        shutil.copy2(os.path.join(ASSETS_SRC, fn), os.path.join(ASSETS_DST, fn))
    print(f"[compile] 同步 assets → {ASSETS_DST}")


def main():
    os.makedirs(DOCS_DIR, exist_ok=True)
    cfg = load_yaml_min(CFG_PATH) if os.path.exists(CFG_PATH) else {}
    args = sys.argv[1:]

    if args and args[0] == "--all":
        ds = all_dates()
        if not ds:
            sys.exit("[compile] data/analysis 下没有任何分析文件。")
        for d in ds:
            build_day(cfg, d)
        build_index(cfg, ds[0])
    else:
        if args:
            date = args[0]
        else:
            date = (datetime.now(CST) - timedelta(days=1)).strftime("%Y-%m-%d")
        build_day(cfg, date)
        latest = all_dates()[0] if all_dates() else date
        build_index(cfg, latest)

    build_archive(cfg)
    sync_assets()
    print("[compile] 完成。")


if __name__ == "__main__":
    main()
