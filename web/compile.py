#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loop News 小编译系统:把全部 data/analysis/*.json + data/threads.json
编译成 **单个** docs/index.html(左侧日期/线索列表,右侧主区,JS 同页切换,无 iframe)。

用法:
    python3 web/compile.py            # 重建整站(单页)
    python3 web/compile.py --all      # 同上(保留兼容)

零第三方依赖:仅标准库;loop.yaml 用内置迷你解析器。
"""
import sys, os, json, html, glob, shutil, re, math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS_DIR = os.path.join(ROOT, "data", "analysis")
CORPUS_DIR = os.path.join(ROOT, "data", "corpus")
THREADS_PATH = os.path.join(ROOT, "data", "threads.json")
SERIES_DIR = os.path.join(ROOT, "data", "series")
DOSSIERS_DIR = os.path.join(ROOT, "data", "dossiers")
DOCS_DIR = os.environ.get("LN_DOCS_DIR") or os.path.join(ROOT, "docs")  # 自检时可指向临时目录
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
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
HL_CAP = 2  # 每块最多高亮处数;main 中按 config 覆盖


def hl(s):
    """先转义;**文本**→<strong>(不限次、不占高亮额度);==文本==→<mark>(最多 HL_CAP 处,多出的去 == 留文字)。"""
    if s is None:
        return ""
    out = BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", e(s))
    n = [0]
    def repl(m):
        n[0] += 1
        return f'<mark class="hl">{m.group(1)}</mark>' if n[0] <= HL_CAP else m.group(1)
    return HL_RE.sub(repl, out)


# ── 内联 SVG 图表(零依赖;趋势线 / 柱 / 饼)。仅渲染 analysis 条目的 charts 字段 ──
CHART_PAL = ["#1F5C57", "#9A6B16", "#5B3FB0", "#2F6F4E", "#3A5A8C", "#7A5C9E"]
CHART_POS, CHART_NEG = "#2F6F4E", "#B0413E"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fmt(v):
    s = f"{v:.1f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _svg_open(extra=""):
    return f'<svg viewBox="0 0 640 240" xmlns="http://www.w3.org/2000/svg" class="chart-svg" role="img">{extra}'


def _svg_bar(c):
    data = [d for d in c.get("data", []) if d.get("label") is not None]
    if not data:
        return ""
    labels = [str(d.get("label", "")) for d in data]
    vals = [_num(d.get("value")) for d in data]
    signed = any(v < 0 for v in vals)
    unit = c.get("unit", "")
    L, R, T, B = 30, 18, 28, 44
    x0, x1, y0, y1 = L, 640 - R, T, 240 - B
    vmax, vmin = max(vals + [0.0]), min(vals + [0.0])
    rng = (vmax - vmin) or 1.0
    yv = lambda v: y1 - (v - vmin) / rng * (y1 - y0)
    zeroY = yv(0.0)
    n = len(data)
    step = (x1 - x0) / n
    bw = min(56.0, step * 0.5)
    p = [f'<line x1="{x0}" y1="{zeroY:.1f}" x2="{x1}" y2="{zeroY:.1f}" stroke="#d8d8d2"/>']
    for i, (lab, v) in enumerate(zip(labels, vals)):
        cx = x0 + (i + 0.5) * step
        y = yv(v)
        top, h = min(y, zeroY), abs(y - zeroY)
        col = CHART_POS if v >= 0 else CHART_NEG
        vlab = ("+" if (signed and v > 0) else "") + _fmt(v) + unit
        vy = top - 7 if v >= 0 else top + h + 14
        p.append(f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(h, 0.6):.1f}" rx="2" fill="{col}"/>')
        p.append(f'<text x="{cx:.1f}" y="{vy:.1f}" text-anchor="middle" font-size="12" fill="#33333A">{e(vlab)}</text>')
        p.append(f'<text x="{cx:.1f}" y="222" text-anchor="middle" font-size="11.5" fill="#6B6B70">{e(lab)}</text>')
    return _svg_open("".join(p)) + "</svg>"


def _svg_line(c):
    data = [d for d in c.get("data", []) if d.get("label") is not None]
    if len(data) < 2:
        return _svg_bar(c)
    labels = [str(d.get("label", "")) for d in data]
    vals = [_num(d.get("value")) for d in data]
    unit = c.get("unit", "")
    L, R, T, B = 34, 18, 26, 42
    x0, x1, y0, y1 = L, 640 - R, T, 240 - B
    vmax, vmin = max(vals), min(vals)
    pad = ((vmax - vmin) or abs(vmax) or 1.0) * 0.18
    vmax += pad
    vmin -= pad
    rng = (vmax - vmin) or 1.0
    n = len(data)
    xv = lambda i: x0 + (i / (n - 1)) * (x1 - x0)
    yv = lambda v: y1 - (v - vmin) / rng * (y1 - y0)
    pts = " ".join(f"{xv(i):.1f},{yv(v):.1f}" for i, v in enumerate(vals))
    p = [f'<polyline points="{pts}" fill="none" stroke="{CHART_PAL[0]}" stroke-width="2.5"/>']
    for i, v in enumerate(vals):
        p.append(f'<circle cx="{xv(i):.1f}" cy="{yv(v):.1f}" r="3.5" fill="{CHART_PAL[0]}"/>')
        p.append(f'<text x="{xv(i):.1f}" y="{yv(v) - 10:.1f}" text-anchor="middle" font-size="12" fill="#33333A">{e(_fmt(v))}{e(unit)}</text>')
        p.append(f'<text x="{xv(i):.1f}" y="224" text-anchor="middle" font-size="11.5" fill="#6B6B70">{e(labels[i])}</text>')
    return _svg_open("".join(p)) + "</svg>"


def _svg_pie(c):
    data = [d for d in c.get("data", []) if _num(d.get("value")) > 0]
    if not data:
        return ""
    vals = [_num(d.get("value")) for d in data]
    total = sum(vals) or 1.0
    cx, cy, r, ir = 116, 120, 92, 48
    ang = -math.pi / 2
    p = []
    for i, d in enumerate(data):
        frac = vals[i] / total
        a2 = ang + frac * 2 * math.pi
        x1c, y1c = cx + r * math.cos(ang), cy + r * math.sin(ang)
        x2c, y2c = cx + r * math.cos(a2), cy + r * math.sin(a2)
        large = 1 if frac > 0.5 else 0
        col = CHART_PAL[i % len(CHART_PAL)]
        p.append(f'<path d="M {cx} {cy} L {x1c:.1f} {y1c:.1f} A {r} {r} 0 {large} 1 {x2c:.1f} {y2c:.1f} Z" fill="{col}"/>')
        ang = a2
    p.append(f'<circle cx="{cx}" cy="{cy}" r="{ir}" fill="#fbfaf7"/>')
    lx, ly = 250, 46
    for i, d in enumerate(data):
        col = CHART_PAL[i % len(CHART_PAL)]
        pct = vals[i] / total * 100
        p.append(f'<rect x="{lx}" y="{ly + i * 26}" width="12" height="12" rx="2" fill="{col}"/>')
        p.append(f'<text x="{lx + 18}" y="{ly + i * 26 + 11}" font-size="12.5" fill="#33333A">{e(str(d.get("label", "")))} · {pct:.0f}%</text>')
    return _svg_open("".join(p)) + "</svg>"


def svg_chart(c):
    t = c.get("type", "bar")
    svg = _svg_line(c) if t == "line" else _svg_pie(c) if t == "pie" else _svg_bar(c)
    if not svg:
        return ""
    src = c.get("source", "")
    note = c.get("note", "据报道生成,仅供参考")
    cap = " · ".join(x for x in [f"来源:{e(src)}" if src else "", e(note)] if x)
    return (f'<figure class="chart"><figcaption class="chart-title">{e(c.get("title", ""))}</figcaption>'
            f'{svg}<figcaption class="chart-cap">{cap}</figcaption></figure>')


def _resolve_chart(c):
    """series 引用 → 从 data/series/<id>.json 取时间序列(可 recent 截断);否则用 inline data。"""
    if c.get("series"):
        s = load_json(os.path.join(SERIES_DIR, str(c["series"]) + ".json"), {}) or {}
        pts = s.get("points", [])
        if c.get("recent"):
            pts = pts[-int(c["recent"]):]
        c = dict(c)
        c["data"] = [{"label": p.get("period", ""), "value": p.get("value")} for p in pts]
        c.setdefault("unit", s.get("unit", ""))
        c.setdefault("source", s.get("source", ""))
        if not c.get("title"):
            c["title"] = s.get("name", "")
    return c


def render_charts(charts):
    out = []
    for c in (charts or []):
        c = _resolve_chart(c)
        if c.get("data"):
            out.append(svg_chart(c))
    return "".join(out)


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


def act_row(cfg, date, it):
    """新闻条目的 收藏 / 关注(per-user,凭 token;关注驱动后续采集)。"""
    if not cfg_get(cfg, "feedback.enabled", True):
        return ""
    iid, t, d = e(it.get("id")), e(it.get("title_zh")), e(date)
    topics = e(json.dumps(it.get("topics", []), ensure_ascii=False))
    ents = e(json.dumps(it.get("entities", []), ensure_ascii=False))
    # 分享出图:把卡片内容(纯文本)带在 data-* 上,点击 → POST 出图服务 → 自动下载;图表由 JS 从 DOM 取
    deep = bool(it.get("original_quote"))
    kind = "deep" if deep else "consensus"
    src = it.get("source") or " · ".join(it.get("sources", []))
    cc = it.get("consensus_count") or len(it.get("sources") or [])
    badge = f"{cc} 家在报" if (cc and not deep) else ""
    share = (f'<button class="act share" data-item="{iid}" data-date="{d}" data-title="{t}" '
             f'data-summary="{e(it.get("summary_zh",""))}" data-source="{e(src)}" data-kind="{kind}" '
             f'data-badge="{e(badge)}" data-quote="{e(it.get("original_quote",""))}">⤴ 分享</button>')
    return (f'<span class="act-row">'
            f'<button class="act fav" data-item="{iid}" data-date="{d}" data-title="{t}">★ 收藏</button>'
            f'<button class="act follow" data-item="{iid}" data-date="{d}" data-title="{t}" data-topics="{topics}" data-entities="{ents}">+ 关注</button>'
            f'{share}'
            f'</span>')


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
        cc = it.get("consensus_count") or len(it.get("sources") or [])
        src_badge = f'<span class="badge badge-consensus">{e(cc)} 家在报</span>' if cc else ""
        # 来源:有 source_links(每家带 url)→ 每家各自可点原文;否则退化为名字 + 单一原文
        links = [x for x in (it.get("source_links") or []) if x.get("url")]
        if links:
            srcs = " · ".join(
                f'<a class="src-link" href="{e(x["url"])}" target="_blank" rel="noopener">{e(x.get("name") or "原文")} ↗</a>'
                for x in links)
            src_html = f'<span class="srcs">{srcs}</span>'
        else:
            src_list = " · ".join(e(s) for s in it.get("sources", []))
            url = it.get("url", "")
            one = f' <a class="src-link" href="{e(url)}" target="_blank" rel="noopener">原文 ↗</a>' if url else ""
            src_html = f'<span class="badge badge-src">{src_list}</span>{one}'
        out.append(f"""<article class="card" id="item-{e(it.get('id'))}">
  <h3>{e(it.get('title_zh'))}</h3>
  <p>{hl(it.get('summary_zh'))}</p>
  {render_charts(it.get('charts'))}
  <div class="meta-row">{src_badge}{src_html}{topics}</div>
  <div class="row-actions">{fb_row(cfg, date, it.get('id',''), it.get('title_zh',''))}{act_row(cfg, date, it)}</div>
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
  {render_charts(it.get('charts'))}
  {ihtml}
  <div class="row-actions">{fb_row(cfg, date, it.get('id',''), it.get('title_zh',''))}{act_row(cfg, date, it)}</div>
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


def render_podcasts(items, cfg, date):
    """🎙️ 播客 · AI 人物访谈:知名播客主 × 知名 AI 人物的整集深访。"""
    out = []
    for it in items or []:
        show, host = e(it.get("show", "")), e(it.get("host", ""))
        guest = e(it.get("guest", ""))
        gt = it.get("guest_title", "")
        guest_line = f"<b>{guest}</b>" + (f" · {e(gt)}" if gt else "")
        url = it.get("url", "")
        link = f'<a class="src-link" href="{e(url)}" target="_blank" rel="noopener">收听 ↗</a>' if url else ""
        pq = f'<blockquote class="pq" lang="{e(it.get("lang","en"))}">{e(it.get("quote"))}</blockquote>' if it.get("quote") else ""
        pts = "".join(f"<li>{hl(p)}</li>" for p in it.get("key_points_zh", []))
        pts_html = f'<ul class="pod-points">{pts}</ul>' if pts else ""
        out.append(f"""<article class="card podcast" id="item-{e(it.get('id',''))}">
  <div class="pod-head"><span class="pod-show">🎙 {show}</span><span class="pod-meta">{host} × {guest_line}</span><span class="pod-date">{e(it.get('date',''))}</span>{link}</div>
  <h3>{e(it.get('title_zh'))}</h3>
  {pq}
  <p>{hl(it.get('summary_zh'))}</p>
  {pts_html}
  <div class="row-actions">{fb_row(cfg, date, it.get('id',''), it.get('title_zh',''))}{act_row(cfg, date, it)}</div>
</article>""")
    return "\n".join(out)


def render_day(a, cfg, id_to_date):
    date = a.get("date", "")
    note = a.get("methodology_note_zh", "")
    note_html = f'<div class="section"><h2 class="section-title">方法论说明</h2><p>{e(note)}</p></div>' if note else ""
    pods = render_podcasts(a.get("podcasts", []), cfg, date)
    pod_section = f'<section class="section"><h2 class="section-title">🎙️ 播客 · AI 人物访谈</h2>{pods}</section>' if pods else ""
    inner = f"""<div class="day-meta">
  <h1 class="day-date">{e(date)}</h1>
  <p class="day-summary">{hl(a.get('summary_zh'))}</p>
</div>
<section class="section"><h2 class="section-title">今日要闻 · 共识</h2>
{render_consensus(a.get('consensus', []), cfg, date)}
</section>
<section class="section"><h2 class="section-title">深度原声</h2>
{render_deep(a.get('deep', []), cfg, date)}
</section>
{pod_section}
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


def _inline(s):
    """行内 markdown:**粗体** 与 `代码`(先转义)。"""
    out = e(s)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    return out


def _rel_headline(s):
    """从 changelog 行提取简短要点(分享卡用):优先粗体小标题,否则取冒号前。"""
    s = re.sub(r"^\s*(?:\d+\.|[-*])\s*", "", s.strip())
    mb = re.search(r"\*\*(.+?)\*\*", s)
    if mb:
        return mb.group(1).strip()
    s = re.split(r"[:：]", s, 1)[0]
    return re.sub(r"[`*]", "", s).strip()


def render_evolution(md):
    """把 prompts/CHANGELOG.md 渲染成「更新日志 / Release Notes」视图——产品发布形态,与新闻刻意区分。"""
    entries, cur = [], None
    for ln in (md or "").splitlines():
        if ln.startswith("## "):
            if cur:
                entries.append(cur)
            cur = {"title": ln[3:].strip(), "body": []}
        elif cur is not None:
            cur["body"].append(ln)
    if cur:
        entries.append(cur)
    if not entries:
        return ('<section class="view" id="view-evolution"><div class="release-masthead">'
                '<h1 class="release-h1">更新日志 · Release Notes</h1></div>'
                '<p class="empty">暂无发布记录。</p></section>')
    cards = []
    for ent in entries:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*·\s*(.+)$", ent["title"])
        date, rest = (m.group(1), m.group(2)) if m else ("", ent["title"])
        m2 = re.match(r"^(.*?)\s*[(（](.+?)[)）]\s*$", rest)
        tag, sub = (m2.group(1).strip(), m2.group(2).strip()) if m2 else (rest.strip(), "")
        rows = []
        for b in ent["body"]:
            s = b.rstrip()
            if not s or s == "---":
                continue
            if re.match(r"^\s+\d+\.", s):
                rows.append(f'<li class="rn-sub">{_inline(s.strip())}</li>')
            elif s.startswith("- "):
                rows.append(f'<li class="rn-item">{_inline(s[2:])}</li>')
            else:
                rows.append(f'<li class="rn-item">{_inline(s.strip())}</li>')
        date_html = f'<time class="release-date">{e(date)}</time>' if date else ""
        note_html = f'<p class="release-note">{e(sub)}</p>' if sub else ""
        # 分享成现代产品发布卡:要点取数字子项(无则取顶层 - 项)的简短小标题
        sitems = [_rel_headline(b) for b in ent["body"] if re.match(r"^\s+\d+\.", b.rstrip())]
        if not sitems:
            sitems = [_rel_headline(b) for b in ent["body"] if b.strip().startswith("- ")]
        sitems = [x for x in sitems if x][:6]
        share_btn = ""
        if sitems:
            share_btn = ('<div class="release-actions">'
                         f'<button class="act share" data-kind="release" data-title="{e(sub or tag)}" '
                         f'data-date="{e(date)}" data-badge="{e(tag)}" '
                         f'data-items="{e(json.dumps(sitems, ensure_ascii=False))}">⤴ 分享卡片</button></div>')
        cards.append(f'''<article class="release">
  <div class="release-head"><span class="release-tag">{e(tag)}</span>{date_html}</div>
  {note_html}
  <ul class="release-body">{"".join(rows)}</ul>
  {share_btn}
</article>''')
    return ('<section class="view" id="view-evolution">'
            '<div class="release-masthead">'
            '<h1 class="release-h1">更新日志 · Release Notes</h1>'
            '<p class="release-lead">系统每轮自进化(ln-evolve)的产品式变更记录——改了什么、为什么、如何回滚。最新在上。</p>'
            '</div>'
            f'{"".join(cards)}</section>')


def render_favorites():
    """「我的收藏」视图外壳;内容由前端按 token 从反馈服务拉取填充。"""
    return ('<section class="view" id="view-favorites">'
            '<h1 class="day-date">★ 我的收藏</h1>'
            '<p class="intro">你收藏的新闻(按访问令牌区分,各看各的)。点条目跳到原文位置;可在此取消收藏。</p>'
            '<div id="favList" class="fav-list"><p class="empty">加载中…</p></div>'
            '</section>')


TYPE_LABEL = {"request": "请求", "follow": "关注", "adopt": "采用", "ask": "提问", "up": "赞", "down": "踩", "metrics": "指标", "directive": "指令"}


def render_feedback(ledger):
    """「📋 反馈台账」:实时反馈(前端拉服务)+ 进化台账(哪一轮覆盖了什么,来自 data/feedback_ledger.json)。"""
    cards = []
    for cyc in (ledger.get("cycles", []) if isinstance(ledger, dict) else []):
        rows = "".join(
            f'<li class="lg-item"><span class="lg-type">{e(TYPE_LABEL.get(c.get("type"), c.get("type","")))}</span>'
            f'<span class="lg-text">{e(c.get("text",""))}</span>'
            f'<span class="lg-how">→ {e(c.get("how",""))}</span></li>'
            for c in cyc.get("covered", []))
        cards.append(
            f'<article class="ledger-cycle"><div class="lg-head"><time class="release-date">{e(cyc.get("date",""))}</time>'
            f'<span class="lg-cl">{e(cyc.get("changelog",""))}</span></div><ul class="lg-list">{rows}</ul></article>')
    cycles_html = "".join(cards) or '<p class="empty">暂无进化台账。</p>'
    return ('<section class="view" id="view-feedback">'
            '<h1 class="day-date">📋 反馈台账</h1>'
            '<p class="intro">大家的反馈,以及每条在哪一轮自进化里被消化。反馈实时来自服务;台账由 ln-evolve 每轮维护。</p>'
            '<section class="section"><h2 class="section-title">反馈现状 · 实时</h2>'
            '<div id="fbLedgerLive"><p class="empty">加载中…</p></div></section>'
            '<section class="section"><h2 class="section-title">进化台账 · 哪一轮覆盖了什么</h2>'
            f'{cycles_html}</section></section>')


DASH_LABELS = [("correlation", "关联度"), ("volume", "数量"), ("analysis", "分析整合"),
               ("breadth", "自进化广度"), ("source_quality", "信息源固化"), ("timeliness", "及时性")]


def render_dashboard(scores, srcq):
    """📊 自进化仪表盘(owner 专属):5 个系统分数 + 趋势 + 成分 + 来源分档。"""
    hist = (scores or {}).get("history", [])
    if not hist:
        return ('<section class="view" id="view-dashboard"><h1 class="day-date">📊 自进化仪表盘</h1>'
                '<p class="empty">暂无评分数据(跑 scripts/score.py)。</p></section>')
    cur = hist[-1]
    s = cur.get("scores", {})
    d = cur.get("delta_vs_prev", {})

    def dtxt(k):
        dv = d.get(k)
        if dv is None:
            return '<span class="dash-d">·</span>'
        cls = "sc-up" if dv > 0 else "sc-down" if dv < 0 else ""
        arr = "▲" if dv > 0 else "▼" if dv < 0 else "·"
        return f'<span class="dash-d {cls}">{arr} {"+" if dv >= 0 else ""}{dv}</span>'

    cards = "".join(
        f'<div class="dash-card"><div class="dash-lab">{lab}</div>'
        f'<div class="dash-numrow"><span class="dash-num">{s.get(k, 0)}</span>{dtxt(k)}</div>'
        f'<div class="dash-bar"><span style="width:{min(100, s.get(k, 0))}%"></span></div></div>'
        for k, lab in DASH_LABELS)
    comp = s.get("composite", 0)
    cd = d.get("composite")
    comp_d = "" if cd is None else f' <span class="{"sc-up" if cd >= 0 else "sc-down"}">{"+" if cd >= 0 else ""}{cd}</span>'
    trend = "".join(f'<span class="tr-dot" style="--h:{min(100, h["scores"].get("composite", 0))}%" title="{e(h["date"])}:{h["scores"].get("composite", 0)}"></span>' for h in hist[-8:])
    comps = cur.get("components", {})
    detail = " · ".join(f'{k} <b>{v}</b>' for k, v in comps.items())
    # 来源分档
    tiers = {"core": 0, "trial": 0, "watch": 0, "demoted": 0}
    for v in (srcq or {}).get("sources", {}).values():
        tiers[v.get("tier", "trial")] = tiers.get(v.get("tier", "trial"), 0) + 1
    tierrow = (f'<span class="tier tier-core">固化 {tiers.get("core",0)}</span>'
               f'<span class="tier tier-trial">试用 {tiers.get("trial",0)}</span>'
               f'<span class="tier tier-watch">观察 {tiers.get("watch",0)}</span>'
               f'<span class="tier tier-demoted">降级 {tiers.get("demoted",0)}</span>'
               f'<span class="dash-lc">上次评选 {e((srcq or {}).get("last_curation",""))}</span>')
    return (
        '<section class="view" id="view-dashboard">'
        '<h1 class="day-date">📊 自进化仪表盘</h1>'
        f'<p class="intro">系统每轮自评的 {len(DASH_LABELS)} 个分数,目标是都向上涨。数据 {e(cur.get("date",""))} · 由 <code>scripts/score.py</code> 确定性计算。</p>'
        f'<div class="dash-composite"><div class="dash-comp-num">{comp}<span class="dash-comp-d">{comp_d}</span></div>'
        f'<div class="dash-comp-lab">综合分</div><div class="dash-trend">{trend}</div></div>'
        f'<div class="dashboard">{cards}</div>'
        f'<section class="section"><h2 class="section-title">信息源固化 · 分档</h2><div class="tier-row">{tierrow}</div></section>'
        f'<section class="section"><h2 class="section-title">本轮成分</h2><p class="dash-detail">{detail}</p></section>'
        '<section class="section"><h2 class="section-title">评分制度</h2><p class="dash-detail">数量分对欠采<b>陡峭惩罚</b>(采太少即暴跌);信息源固化分<b>强迫每轮评选来源</b>(不评选则随天数衰减)。制度见 <code>prompts/scoring.md</code>。</p></section>'
        '</section>')


def _render_graded(items, id_to_date):
    out = []
    for c in items or []:
        g = c.get("grade", "推断"); gc = GRADE_CLASS.get(g, "grade-infer")
        conf = c.get("confidence")
        confhtml = f'<span class="conf">置信度 {int(conf*100)}%</span>' if isinstance(conf, (int, float)) else ""
        ev = ev_links(c.get("evidence", []), id_to_date)
        evhtml = f'<div class="evidence">证据:{ev}</div>' if ev else ""
        out.append(f'<div class="concl"><p><span class="grade {gc}">{e(g)}</span>{hl(c.get("text_zh"))} {confhtml}</p>{evhtml}</div>')
    return "".join(out)


def _paras(text):
    """多段正文:按换行分段,每段过 hl() 支持 ==高亮==。"""
    parts = [hl(p.strip()) for p in re.split(r"\n+", str(text or "")) if p.strip()]
    return "".join(f"<p>{p}</p>" for p in parts)


def _dossier_voices(voices):
    """各方立场:多方在录原声(带角色标签,深度保真原文)。"""
    out = []
    for v in voices or []:
        q = v.get("quote") or v.get("original_quote", "")
        pq = f'<blockquote class="pq" lang="{e(v.get("lang","en"))}">{e(q)}</blockquote>' if q else ""
        role = v.get("role", "")
        role_html = f'<span class="voice-role">{e(role)}</span>' if role else ""
        who = e(v.get("who") or v.get("source", ""))
        url = v.get("url", "")
        link = f'<a class="src-link" href="{e(url)}" target="_blank" rel="noopener">来源 ↗</a>' if url else ""
        stance = v.get("stance_zh") or v.get("summary_zh", "")
        stance_html = f'<p class="deep-sum">{e(stance)}</p>' if stance else ""
        out.append(f'<article class="card deep voice"><div class="byline">{role_html}<span class="byline-src">{who}</span>{link}</div>{pq}{stance_html}</article>')
    return "".join(out)


def _render_dossier_legacy(d, id_to_date, P):
    """旧字段兼容渲染(kol_voices/data/timeline/outlook/adjacent)。"""
    voices = _dossier_voices([dict(v, role="") for v in d.get("kol_voices", [])])
    if voices:
        P.append('<section class="section"><h2 class="section-title">KOL / KOC 在说什么</h2>' + voices + "</section>")
    charts = render_charts(d.get("data"))
    if charts:
        P.append('<section class="section"><h2 class="section-title">历年数据 · 变化</h2>' + charts + "</section>")
    tl = d.get("timeline", [])
    if tl:
        items = "".join(f'<li class="tl-entry"><span class="tl-date">{e(t.get("date",""))}</span> <span class="tl-note">{e(t.get("note_zh",""))}</span></li>' for t in tl)
        P.append('<section class="section"><h2 class="section-title">脉络</h2><ul class="timeline">' + items + "</ul></section>")
    if d.get("outlook"):
        P.append('<section class="section"><h2 class="section-title">未来展望</h2>' + _render_graded(d.get("outlook"), id_to_date) + "</section>")
    for a in d.get("adjacent", []):
        ev = ev_links(a.get("evidence", []), id_to_date)
        evhtml = f'<div class="evidence">证据:{ev}</div>' if ev else ""
        P.append(f'<section class="section"><h2 class="section-title">周边产业 · {e(a.get("name",""))}</h2><p>{e(a.get("note_zh",""))}</p>{evhtml}</section>')


def render_dossier(d, id_to_date):
    """领域专题(深度报道):核心判断→脉络→数据→各方→分析→反方→看点→来源→方法。"""
    did = e(d.get("id", ""))
    title = e(d.get("title_zh") or d.get("name", ""))
    P = [f'<div class="dossier-head"><span class="dossier-kicker">📂 {e(d.get("name",""))} · 深度报道</span>'
         f'<h1 class="dossier-title">{title}</h1>']
    if d.get("dek_zh"):
        P.append(f'<p class="dossier-dek">{e(d.get("dek_zh"))}</p>')
    P.append(f'<span class="dossier-upd">持续追踪 · 更新 {e(d.get("updated",""))}</span></div>')
    # 核心判断(lede)
    if d.get("lede_zh"):
        P.append(f'<div class="dossier-lede">{_paras(d.get("lede_zh"))}</div>')
    elif d.get("summary_zh"):
        P.append(f'<p class="day-summary">{hl(d.get("summary_zh"))}</p>')
    # 文章主体(sections);无则退化到旧字段
    if d.get("sections"):
        for s in d.get("sections", []):
            inner = _paras(s.get("body_zh", "")) if s.get("body_zh") else ""
            if s.get("charts"):
                inner += render_charts(s.get("charts"))
            if s.get("voices"):
                inner += _dossier_voices(s.get("voices"))
            ev = ev_links(s.get("evidence", []), id_to_date)
            if ev:
                inner += f'<div class="evidence">证据:{ev}</div>'
            P.append(f'<section class="section"><h2 class="section-title">{e(s.get("heading_zh",""))}</h2>{inner}</section>')
    else:
        _render_dossier_legacy(d, id_to_date, P)
    # 分级结论
    if d.get("conclusions"):
        P.append('<section class="section"><h2 class="section-title">分级结论</h2>' + _render_graded(d.get("conclusions"), id_to_date) + "</section>")
    # 反方与不确定
    if d.get("counterpoints_zh"):
        items = "".join(f'<li>{hl(x)}</li>' for x in d.get("counterpoints_zh"))
        P.append('<section class="section"><h2 class="section-title">反方与不确定</h2><ul class="counter-list">' + items + "</ul></section>")
    # 后续看点
    if d.get("watch_zh"):
        items = "".join(f'<li>{hl(x)}</li>' for x in d.get("watch_zh"))
        P.append('<section class="section"><h2 class="section-title">后续看点</h2><ul class="watch-list">' + items + "</ul></section>")
    # 来源(透明)
    if d.get("sources"):
        srcs = " · ".join(
            (f'<a class="src-link" href="{e(x.get("url"))}" target="_blank" rel="noopener">{e(x.get("name") or "来源")} ↗</a>' if x.get("url") else e(x.get("name", "")))
            for x in d.get("sources"))
        P.append(f'<section class="section"><h2 class="section-title">来源</h2><p class="dossier-sources">{srcs}</p></section>')
    # 方法与局限
    if d.get("methodology_note_zh"):
        P.append('<section class="section dossier-method"><h2 class="section-title">方法与局限</h2><p>' + e(d.get("methodology_note_zh")) + "</p></section>")
    return f'<section class="view dossier-view" id="dossier-{did}">' + "".join(P) + "</section>"


def load_dossiers():
    out = []
    for p in sorted(glob.glob(os.path.join(DOSSIERS_DIR, "*.json"))):
        dd = load_json(p, None)
        if isinstance(dd, dict) and dd.get("id"):
            out.append(dd)
    return out


def render_dossier_nav(dossiers):
    if not dossiers:
        return ""
    links = ['<div class="nav-section">专题</div>']
    for d in dossiers:
        links.append(f'<a class="nav-link dossier" data-target="dossier-{e(d["id"])}" data-updated="{e(d.get("updated",""))}" href="#dossier-{e(d["id"])}">📂 {e(d.get("name",""))}<span class="dot"></span></a>')
    return "\n".join(links)


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
    changelog_md = ""
    cpath = os.path.join(ROOT, "prompts", "CHANGELOG.md")
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            changelog_md = f.read()

    threads_view = render_threads(threads)
    evolution_view = render_evolution(changelog_md)
    favorites_view = render_favorites()
    ledger = load_json(os.path.join(ROOT, "data", "feedback_ledger.json"), {}) or {}
    feedback_view = render_feedback(ledger)
    scores = load_json(os.path.join(ROOT, "state", "scores.json"), {}) or {}
    srcq = load_json(os.path.join(ROOT, "data", "source_quality.json"), {}) or {}
    dashboard_view = render_dashboard(scores, srcq)
    dossiers = load_dossiers()
    dossier_nav = render_dossier_nav(dossiers)
    dossier_views = "\n".join(render_dossier(d, id_to_date) for d in dossiers)
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
        "{{PAGE_DESC}}": e(analyses[dates[0]].get("summary_zh", "").replace("==", "").replace("**", "")),
        "{{DATE_NAV}}": date_nav,
        "{{THREADS_VIEW}}": threads_view,
        "{{EVOLUTION_VIEW}}": evolution_view,
        "{{FAVORITES_VIEW}}": favorites_view,
        "{{FEEDBACK_VIEW}}": feedback_view,
        "{{DASHBOARD_VIEW}}": dashboard_view,
        "{{LEDGER_JSON}}": json.dumps(ledger, ensure_ascii=False),
        "{{DOSSIER_NAV}}": dossier_nav,
        "{{DOSSIER_VIEWS}}": dossier_views,
        "{{DAY_VIEWS}}": day_views,
        "{{FOOTER}}": footer,
        "{{FEEDBACK_ENABLED}}": "true" if cfg_get(cfg, "feedback.enabled", True) else "false",
        # 灰度构建:LN_FEEDBACK_API / LN_SHARE_API 环境变量可覆盖 API 基址(指向 gray-*);未设则用 config(生产)。
        "{{FEEDBACK_API}}": e(os.environ.get("LN_FEEDBACK_API") or cfg_get(cfg, "feedback.api_url", "")),
        "{{SHARE_API}}": e(os.environ.get("LN_SHARE_API") or cfg_get(cfg, "feedback.share_api_url", "")),
        "{{SYS_OWNER_NAV}}": '<button class="nav-link nav-owner" id="adminBtn">👥 用户管理</button>',
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
    static_src = os.path.join(ROOT, "web", "static")   # favicon / logo 等根静态文件
    if os.path.isdir(static_src):
        for fn in os.listdir(static_src):
            shutil.copy2(os.path.join(static_src, fn), os.path.join(DOCS_DIR, fn))
        print(f"[compile] 同步 static(favicon 等)→ {DOCS_DIR}")
    print("[compile] 完成。")


if __name__ == "__main__":
    main()
