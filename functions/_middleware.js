/**
 * Cloudflare Pages 中间件:token 分享访问门(简单但服务端真生效)。
 * - 有效 token(来自 ?token= 或 cookie lnt)才放行;否则返回"输入令牌"门页(内容不下发)。
 * - token 清单 = Pages 环境变量 SHARE_TOKENS(JSON: {"<token>":{"name":..,"owner":bool}})。
 * - 命中后写 cookie:lnt(令牌)+ lnrole(owner/viewer,供前端决定是否显示全局反馈按钮)。
 * 用 scripts/share-token.sh 生成/同步令牌。
 */
const GATE_HTML = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Loop News · 访问</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#FAFAF8;
color:#17171A;font:16px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
.box{width:90%;max-width:340px;text-align:center;padding:32px 26px;border:1px solid #E7E6E1;border-radius:12px;background:#fff}
h1{font-size:20px;margin:0 0 4px}p{color:#6B6B70;font-size:13.5px;margin:0 0 18px}
input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #E7E6E1;border-radius:8px;font-size:14px;margin-bottom:10px}
button{width:100%;padding:10px;border:none;border-radius:8px;background:#17171A;color:#fff;font-size:14px;font-weight:600;cursor:pointer}
button:hover{background:#1F5C57}</style></head>
<body><div class="box"><h1>Loop News</h1><p>需要访问令牌(向站长索取)</p>
<input id="t" placeholder="粘贴你的访问令牌…" autofocus>
<button onclick="var v=document.getElementById('t').value.trim();if(v)location.href='/?token='+encodeURIComponent(v)">进入</button>
</div></body></html>`;

function cookie(name, req) {
  const m = (req.headers.get("Cookie") || "").match(new RegExp("(?:^|;\\s*)" + name + "=([^;]+)"));
  return m ? decodeURIComponent(m[1]) : "";
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const url = new URL(request.url);
  let tokens = {};
  try { tokens = JSON.parse(env.SHARE_TOKENS || "{}"); } catch (_) {}

  const tok = url.searchParams.get("token") || cookie("lnt", request);
  const rec = tok && tokens[tok];

  if (!rec) {
    return new Response(GATE_HTML, { status: 401, headers: { "Content-Type": "text/html; charset=utf-8" } });
  }
  const role = rec.owner ? "owner" : "viewer";
  const setCookies = [
    `lnt=${encodeURIComponent(tok)}; Path=/; Max-Age=31536000; SameSite=Lax`,
    `lnrole=${role}; Path=/; Max-Age=31536000; SameSite=Lax`,
  ];
  // 带 ?token= 进来 → 写 cookie 并重定向到干净 URL
  if (url.searchParams.get("token")) {
    url.searchParams.delete("token");
    const h = new Headers({ Location: url.pathname + (url.search || "") });
    setCookies.forEach((c) => h.append("Set-Cookie", c));
    return new Response(null, { status: 302, headers: h });
  }
  const resp = await next();
  const out = new Response(resp.body, resp);
  setCookies.forEach((c) => out.headers.append("Set-Cookie", c));
  return out;
}
