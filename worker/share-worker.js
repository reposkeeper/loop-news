/**
 * Loop News 分享出图 —— Cloudflare Worker(Satori + resvg,经 workers-og 封装)。
 * 每条新闻点「分享」→ 前端把该卡片内容 POST 过来 → 这里按统一手机卡片模板渲染成 PNG → 自动下载。
 *   POST /share  body: {title, summary, source, date, kind, badge, quote, chart}
 *   GET  /share?title=...&...        (调试用)
 *   GET  /health
 * 中文字体走 workers-og 的 loadGoogleFont(按本卡片文本子集化 Noto Sans SC,只取用到的字,几 KB、快)。
 * 样式由服务端统一定义 → 每张图风格完整一致;图表(若有)以内嵌 SVG 形式带进图里。
 */
import { ImageResponse } from "workers-og";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const FAMILY = "Noto Sans SC";
const C = { ink: "#17171A", soft: "#33333A", muted: "#6B6B70", paper: "#FAFAF8", accent: "#1F5C57", predict: "#5B3FB0" };

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
function clip(s, n) {
  s = String(s == null ? "" : s);
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function cardHtml(d) {
  const deep = d.kind === "deep";
  const grade = deep ? C.predict : C.accent;
  const badge = deep ? "深度原声" : "今日要闻 · 共识" + (d.badge ? " · " + d.badge : "");
  const title = clip(d.title, 64);
  const summary = clip(d.summary, deep ? 120 : 200);
  const quote = deep ? clip(d.quote, 150) : "";

  const quoteBlock = quote
    ? `<div style="display:flex;font-size:30px;line-height:1.5;color:${C.ink};border-left:5px solid ${C.ink};padding-left:22px;margin-bottom:18px;">${esc(quote)}</div>`
    : "";
  const cw = d.chartW || 512, ch = d.chartH || Math.round((cw * 240) / 640);
  const chartBlock = d.chart
    ? `<div style="display:flex;margin-top:18px;padding:12px 14px;background:#FBFAF7;border:1px solid #E7E6E1;border-radius:10px;"><img src="${d.chart}" width="${cw}" height="${ch}" style="width:${cw}px;height:${ch}px;"/></div>`
    : "";

  return `
  <div style="display:flex;flex-direction:column;width:600px;background:${C.paper};font-family:'${FAMILY}';">
    <div style="display:flex;align-items:center;justify-content:space-between;background:${C.ink};padding:20px 30px;">
      <div style="display:flex;color:#FFFFFF;font-size:27px;font-weight:700;letter-spacing:-0.5px;">Loop News</div>
      <div style="display:flex;color:#B9B9BD;font-size:19px;">${esc(d.date || "")}</div>
    </div>
    <div style="display:flex;flex-direction:column;padding:30px 32px 18px;">
      <div style="display:flex;color:${grade};font-size:18px;font-weight:700;letter-spacing:2px;margin-bottom:18px;">${esc(badge)}</div>
      ${quoteBlock}
      <div style="display:flex;font-size:35px;line-height:1.42;font-weight:700;color:${C.ink};margin-bottom:16px;">${esc(title)}</div>
      <div style="display:flex;font-size:24px;line-height:1.66;color:${C.soft};">${esc(summary)}</div>
      ${chartBlock}
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;border-top:2px solid ${C.ink};margin:14px 0 0;padding:18px 32px;">
      <div style="display:flex;color:${C.muted};font-size:19px;">${esc(clip(d.source, 40))}</div>
      <div style="display:flex;color:${C.accent};font-size:19px;font-weight:700;">news.xdzq.org</div>
    </div>
  </div>`;
}

// 老版 Safari UA → Google Fonts 对子集请求返回 TTF(satori 不吃 woff2)
const UA = "Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_6_8; de-at) AppleWebKit/533.21.1 (KHTML, like Gecko) Version/5.0.5 Safari/533.21.1";
async function loadFont(weight, text) {
  // 关键:text 必须 encodeURIComponent(含 CJK 与空格),否则 Google 退回拉丁子集 → 中文豆腐块
  const url = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(FAMILY)}:wght@${weight}&text=${encodeURIComponent(text)}`;
  const css = await fetch(url, { headers: { "User-Agent": UA } }).then((r) => r.text());
  const m = css.match(/src:\s*url\((.+?)\)\s*format\('(?:opentype|truetype)'\)/);
  if (!m) throw new Error("font css parse failed: " + css.slice(0, 120));
  return await fetch(m[1]).then((r) => r.arrayBuffer());
}
async function fontsFor(text) {
  // 子集化:只取本卡片用到的字 + 静态标签/品牌字,体积极小、速度快
  const sub = text + " Loop News news.xdzq.org 今日要闻 共识 深度原声 · 家在报 0123456789% …—《》「」『』、,。:;()";
  const [reg, bold] = await Promise.all([loadFont(400, sub), loadFont(700, sub)]);
  return [
    { name: FAMILY, data: reg, weight: 400, style: "normal" },
    { name: FAMILY, data: bold, weight: 700, style: "normal" },
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
      const fonts = await fontsFor([d.title, d.summary, d.source, d.date, d.badge, d.quote].filter(Boolean).join(" "));
      const img = new ImageResponse(html, { width: 600, fonts });
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
