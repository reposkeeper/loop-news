/**
 * Loop News 分享出图 —— Cloudflare Worker(Satori + resvg,经 workers-og 封装)。
 * 每条新闻点「分享」→ 前端把该卡片内容 POST 过来 → 这里按统一手机卡片模板渲染成 PNG → 自动下载。
 *   POST /share  body: {title, summary, source, date, kind, badge, quote, chart}
 *   GET  /share?title=...&...        (调试用)
 *   GET  /health
 * 设计:2× 高清(1200px 宽,治糊);标题=优雅衬线 Noto Serif SC,正文=Noto Sans SC;
 *   中文走 Google Fonts css2 + &text= 子集化(必须 encodeURIComponent,否则中文豆腐块)。
 *   字体:标题/正文/日期同用 Noto Serif SC(衬线,400 / 700),仅品牌刊名=Playfair Display。
 *   样式服务端统一定义 → 每张图风格一致;图表(若有)以内嵌 SVG 带进图里。
 */
import { ImageResponse } from "workers-og";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const SERIF = "Noto Serif SC", SANS = "Noto Sans SC";
const C = { ink: "#1A1A1F", soft: "#3A3A42", muted: "#86868C", line: "#E5E4DF", paper: "#FBFAF7", accent: "#1F5C57", predict: "#5B3FB0", date: "#33333A", frame: "#232228" };
const BRAND = "Playfair Display", MONO = "JetBrains Mono";
// 分辨率:卡片按 1200 逻辑设计,输出放大到 OUT_W(更清晰)。scalePx 把 HTML 里所有 px 统一乘 K
// (line-height/flex 等无单位值不受影响;图表 base64 用 __CHART_URI__ 占位、缩放后再填,避免被误改)。
const OUT_W = 1600, K = OUT_W / 1200;   // 输出宽度;2000 时图表卡偶发超 Worker CPU 限额(503),1600 稳定且清晰
function scalePx(html) {
  return html.replace(/(-?\d*\.?\d+)px/g, (_, n) => +(parseFloat(n) * K).toFixed(2) + "px");
}

// workers-og 的 HTML 解析器不解码实体(&#160; / &amp; 会原样显示),故用形近字符中和 < > &(均罕见于中文标题)
function esc(s) {
  // 去掉 markdown 标记 == 高亮与 ** 加粗(分享图不渲染,避免原样显示);再中和 < > &
  return String(s == null ? "" : s).replace(/==/g, "").replace(/\*\*/g, "").replace(/&/g, "＆").replace(/</g, "‹").replace(/>/g, "›");
}
function clip(s, n) {
  s = String(s == null ? "" : s);
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

// 设计感边框:内嵌四条线,但四角各自向外伸出、交叉不闭合(overshoot / 裁切标记风)。
// 用绝对定位的 4 条线(border 会自动闭合,故不用);F=内收、OV=角部伸出量、T=线宽。
function frameWrap(inner) {
  const F = 26, OV = 15, T = 1.5, cl = C.frame, o = F - OV;
  const ln = (s) => `<div style="display:flex;position:absolute;background:${cl};${s}"></div>`;
  const frame =
    ln(`top:${F}px;left:${o}px;right:${o}px;height:${T}px;`) +
    ln(`bottom:${F}px;left:${o}px;right:${o}px;height:${T}px;`) +
    ln(`left:${F}px;top:${o}px;bottom:${o}px;width:${T}px;`) +
    ln(`right:${F}px;top:${o}px;bottom:${o}px;width:${T}px;`);
  return `<div style="position:relative;display:flex;width:1200px;background:${C.paper};">${frame}`
    + `<div style="display:flex;flex:1;flex-direction:column;font-family:'${SERIF}';padding:62px 66px 64px;">${inner}</div></div>`;
}

// 卡片(2× 物理像素;所有数值即最终 px)
function cardHtml(d) {
  const deep = d.kind === "deep";
  const grade = deep ? C.predict : C.accent;
  const badge = deep ? "深度原声" : "今日要闻 · 共识" + (d.badge ? " · " + d.badge : "");
  const title = clip(d.title, 58);
  const summary = clip(d.summary, deep ? 96 : 184);
  const quote = deep ? clip(d.quote, 132) : "";
  const src = clip(d.source, 36);
  const titleSize = deep ? 46 : 62;

  const quoteBlock = quote
    ? `<div style="display:flex;flex-direction:column;margin-bottom:38px;">`
      + `<div style="display:flex;font-family:'${SERIF}';font-size:50px;line-height:1.56;color:${C.ink};border-left:7px solid ${C.accent};padding-left:36px;">${esc(quote)}</div>`
      + (src ? `<div style="display:flex;justify-content:flex-end;color:${C.muted};font-size:31px;margin-top:22px;">—— ${esc(src)}</div>` : "")
      + `</div>`
    : "";
  const iw = 1020, ih = Math.round((iw * 240) / 640);
  const chartBlock = d.chart
    ? `<div style="display:flex;margin-top:38px;padding:30px;background:#FFFFFF;border:2px solid ${C.line};border-radius:20px;"><img src="__CHART_URI__" width="${iw}" height="${ih}" style="width:${iw}px;height:${ih}px;"/></div>`
    : "";

  return frameWrap(`
    <div style="display:flex;align-items:flex-end;padding-bottom:30px;border-bottom:3px solid ${C.ink};">
      <div style="display:flex;font-family:'${BRAND}';font-weight:700;font-size:66px;color:${C.ink};">Loop News</div>
      <div style="display:flex;margin-left:auto;font-family:'${SERIF}';font-weight:400;font-size:33px;color:${C.date};">${esc(d.date || "")}</div>
    </div>
    <div style="display:flex;flex-direction:column;padding:48px 0 0;">
      <div style="display:flex;color:${grade};font-size:27px;letter-spacing:6px;margin-bottom:32px;">${esc(badge)}</div>
      ${quoteBlock}
      <div style="display:flex;font-family:'${SERIF}';font-size:${titleSize}px;line-height:1.42;font-weight:700;color:${C.ink};margin-bottom:30px;letter-spacing:-0.5px;">${esc(title)}</div>
      <div style="display:flex;font-size:37px;line-height:1.78;color:${C.soft};">${esc(summary)}</div>
      ${chartBlock}
    </div>`);
}

// 自进化日志 → 现代产品发布卡(版本徽章 + 标题 + 要点,刻意区别于新闻卡)
function releaseHtml(d) {
  const tag = clip(d.badge || d.tag || "更新", 16);
  const items = (Array.isArray(d.items) ? d.items : []).slice(0, 6);
  const bullets = items.map((t) =>
    `<div style="display:flex;align-items:flex-start;margin-bottom:22px;">`
    + `<div style="display:flex;width:14px;height:14px;border-radius:4px;background:${C.accent};margin:14px 22px 0 0;flex:0 0 14px;"></div>`  // 绘制标记,不依赖字体字形
    + `<div style="display:flex;flex:1;font-size:35px;line-height:1.46;color:${C.soft};">${esc(clip(t, 60))}</div>`
    + `</div>`).join("");
  return frameWrap(`
    <div style="display:flex;align-items:flex-end;padding-bottom:30px;border-bottom:3px solid ${C.ink};">
      <div style="display:flex;font-family:'${BRAND}';font-weight:700;font-size:66px;color:${C.ink};">Loop News</div>
      <div style="display:flex;margin-left:auto;font-size:32px;color:${C.date};">更新日志</div>
    </div>
    <div style="display:flex;flex-direction:column;padding:46px 0 0;">
      <div style="display:flex;align-items:center;margin-bottom:32px;">
        <div style="display:flex;background:${C.accent};color:#FFFFFF;font-size:27px;font-weight:700;padding:9px 24px;border-radius:999px;">${esc(tag)}</div>
        <div style="display:flex;margin-left:20px;color:${C.muted};font-size:29px;">${esc(d.date || "")}</div>
      </div>
      <div style="display:flex;font-size:54px;line-height:1.4;font-weight:700;color:${C.ink};margin-bottom:42px;letter-spacing:-0.5px;">${esc(clip(d.title, 42))}</div>
      ${bullets}
    </div>`);
}

// 老版 Safari UA → Google Fonts 对子集请求返回 TTF(satori 不吃 woff2)
const UA = "Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_6_8; de-at) AppleWebKit/533.21.1 (KHTML, like Gecko) Version/5.0.5 Safari/533.21.1";
async function loadFont(family, weight, text) {
  // 关键:text 必须 encodeURIComponent(含 CJK 与空格),否则 Google 退回拉丁子集 → 中文豆腐块
  const url = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(family)}:wght@${weight}&text=${encodeURIComponent(text)}`;
  const css = await fetch(url, { headers: { "User-Agent": UA } }).then((r) => r.text());
  const m = css.match(/src:\s*url\((.+?)\)\s*format\('(?:opentype|truetype)'\)/);
  if (!m) throw new Error("font css parse failed: " + css.slice(0, 120));
  return await fetch(m[1]).then((r) => r.arrayBuffer());
}
async function fontsFor(d) {
  const punct = " ·…—《》「」『』、,。:;!?()%0123456789";
  const latin = " @&.,'\"-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";       // 兜底:署名/引文里的拉丁字符不缺字形
  // 标题与正文同字体(Noto Serif SC):一份全文,加载 400(正文/徽章/署名)与 700(标题)两个字重
  const items = Array.isArray(d.items) ? d.items.join(" ") : "";
  const text = (d.title || "") + (d.quote || "") + (d.summary || "") + (d.source || "") + (d.badge || "") + (d.date || "") + (d.tag || "") + items + " 今日要闻 共识 深度原声 家在报 图表 更新日志 " + punct + latin;
  const [brand, serif400, serif700] = await Promise.all([
    loadFont(BRAND, 700, "Loop News"),                                               // 品牌刊名(Playfair)
    loadFont(SERIF, 400, text),                                                      // 正文/徽章/署名/日期
    loadFont(SERIF, 700, text),                                                      // 标题
  ]);
  return [
    { name: BRAND, data: brand, weight: 700, style: "normal" },
    { name: SERIF, data: serif400, weight: 400, style: "normal" },
    { name: SERIF, data: serif700, weight: 700, style: "normal" },
  ];
}

export default {
  async fetch(req) {
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    const url = new URL(req.url);
    if (url.pathname === "/health") return new Response(JSON.stringify({ ok: true }), { headers: { ...CORS, "Content-Type": "application/json" } });
    if (url.pathname !== "/share") return new Response("not found", { status: 404, headers: CORS });

    let d = {};
    if (req.method === "POST") {
      try { d = await req.json(); } catch (_) { return new Response("bad json", { status: 400, headers: CORS }); }
    } else {
      const p = url.searchParams;
      d = { title: p.get("title"), summary: p.get("summary"), source: p.get("source"), date: p.get("date"), kind: p.get("kind"), badge: p.get("badge"), quote: p.get("quote") };
    }
    if (!d.title && !d.quote) return new Response("nothing to render", { status: 400, headers: CORS });

    try {
      let html = d.kind === "release" ? releaseHtml(d) : cardHtml(d);
      html = scalePx(html);
      if (d.chart) html = html.replace("__CHART_URI__", d.chart);
      const fonts = await fontsFor(d);
      const img = new ImageResponse(html, { width: OUT_W, fonts });
      const h = new Headers(img.headers);
      for (const [k, v] of Object.entries(CORS)) h.set(k, v);
      h.set("Content-Disposition", 'attachment; filename="loop-news.png"');
      h.set("Cache-Control", "public, max-age=86400");
      return new Response(img.body, { status: img.status, headers: h });
    } catch (e) {
      return new Response("render error: " + (e && e.message ? e.message : String(e)), { status: 500, headers: CORS });
    }
  },
};
