/**
 * Loop News 分享出图 —— Cloudflare Worker(Satori + resvg,经 workers-og 封装)。
 * 每条新闻点「分享」→ 前端把该卡片内容 POST 过来 → 这里按统一手机卡片模板渲染成 PNG → 自动下载。
 *   POST /share  body: {title, summary, source, date, kind, badge, quote, chart}
 *   GET  /share?title=...&...        (调试用)
 *   GET  /health
 * 设计:2× 高清(1200px 宽,治糊);标题=优雅衬线 Noto Serif SC,正文=Noto Sans SC;
 *   中文走 Google Fonts css2 + &text= 子集化(必须 encodeURIComponent,否则中文豆腐块)。
 *   样式服务端统一定义 → 每张图风格一致;图表(若有)以内嵌 SVG 带进图里。
 */
import { ImageResponse } from "workers-og";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const SERIF = "Noto Serif SC", SANS = "Noto Sans SC";
const C = { ink: "#1A1A1F", soft: "#3A3A42", muted: "#86868C", line: "#E5E4DF", paper: "#FBFAF7", accent: "#1F5C57", predict: "#5B3FB0", date: "#33333A" };
const BRAND = "Playfair Display", MONO = "JetBrains Mono";

// workers-og 的 HTML 解析器不解码实体(&#160; / &amp; 会原样显示),故用形近字符中和 < > &(均罕见于中文标题)
function esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "＆").replace(/</g, "‹").replace(/>/g, "›");
}
function clip(s, n) {
  s = String(s == null ? "" : s);
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

// 卡片(2× 物理像素;所有数值即最终 px)
function cardHtml(d) {
  const deep = d.kind === "deep";
  const grade = deep ? C.predict : C.accent;
  const badge = deep ? "深度原声" : "今日要闻 · 共识" + (d.badge ? " · " + d.badge : "");
  const title = clip(d.title, 58);
  const summary = clip(d.summary, deep ? 96 : 184);
  const quote = deep ? clip(d.quote, 132) : "";
  const titleSize = deep ? 46 : 62;

  const quoteBlock = quote
    ? `<div style="display:flex;font-family:'${SERIF}';font-size:50px;line-height:1.56;color:${C.ink};border-left:7px solid ${C.accent};padding-left:36px;margin-bottom:36px;">${esc(quote)}</div>`
    : "";
  const iw = 1020, ih = Math.round((iw * 240) / 640);
  const chartBlock = d.chart
    ? `<div style="display:flex;margin-top:38px;padding:30px;background:#FFFFFF;border:2px solid ${C.line};border-radius:20px;"><img src="${d.chart}" width="${iw}" height="${ih}" style="width:${iw}px;height:${ih}px;"/></div>`
    : "";

  return `
  <div style="display:flex;flex-direction:column;width:1200px;background:${C.paper};font-family:'${SANS}';padding:64px 70px 66px;">
    <div style="display:flex;align-items:center;padding-bottom:30px;border-bottom:3px solid ${C.ink};">
      <div style="display:flex;font-family:'${BRAND}';font-weight:700;font-size:55px;color:${C.ink};">Loop News</div>
      <div style="display:flex;margin-left:auto;font-family:'${MONO}';font-weight:500;font-size:30px;color:${C.date};letter-spacing:0.5px;">${esc(d.date || "")}</div>
    </div>
    <div style="display:flex;flex-direction:column;padding:48px 0 0;">
      <div style="display:flex;color:${grade};font-size:27px;letter-spacing:6px;margin-bottom:32px;">${esc(badge)}</div>
      ${quoteBlock}
      <div style="display:flex;font-family:'${SERIF}';font-size:${titleSize}px;line-height:1.42;font-weight:700;color:${C.ink};margin-bottom:30px;letter-spacing:-0.5px;">${esc(title)}</div>
      <div style="display:flex;font-size:37px;line-height:1.78;color:${C.soft};">${esc(summary)}</div>
      ${chartBlock}
    </div>
  </div>`;
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
  const punct = " ·…—《》「」『』、,。:;()%0123456789";
  const serifText = (d.title || "") + (d.quote || "") + punct;                       // 标题/引文
  const sansText = (d.summary || "") + " 今日要闻 共识 深度原声 家在报 图表 " + (d.badge || "") + punct; // 正文/徽章
  const [brand, serif, sans, mono] = await Promise.all([
    loadFont(BRAND, 700, "Loop News"),                                               // 品牌刊名(Playfair)
    loadFont(SERIF, 700, serifText),
    loadFont(SANS, 400, sansText),
    loadFont(MONO, 500, (d.date || "") + "0123456789-./: "),                          // 日期(等宽)
  ]);
  return [
    { name: BRAND, data: brand, weight: 700, style: "normal" },
    { name: SERIF, data: serif, weight: 700, style: "normal" },
    { name: SANS, data: sans, weight: 400, style: "normal" },
    { name: MONO, data: mono, weight: 500, style: "normal" },
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
      const html = cardHtml(d);
      const fonts = await fontsFor(d);
      const img = new ImageResponse(html, { width: 1200, fonts });
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
