/**
 * Cloudflare Pages 中间件:session 登录门(替代旧的 token 分享门)。
 * - 读 cookie `lns`(登录 token)→ 查 KV SESSIONS 里的 `session:<token>` → 命中且解析成功才放行;否则返回两步登录页(邮箱→验证码),内容不下发。
 * - 会话由 API Worker(见 worker/feedback-worker.js 的 /auth/* + /me)在验证码校验通过后写入 KV。
 * - 放行时追加非 httpOnly 的 cookie `lnrole=<role>`,供前端 JS 判断是否显示 owner 专属功能(如全局反馈按钮);
 *   `lnname` 由 API 的 /auth/verify 已经写过,会话失效时前端自会隐藏问候,这里不重复处理。
 */
const LOGIN_HTML = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Loop News · 登录</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#FAFAF8;color:#17171A;font:16px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
.box{width:90%;max-width:340px;text-align:center;padding:32px 26px;border:1px solid #E7E6E1;border-radius:12px;background:#fff}
h1{font-size:20px;margin:0 0 4px}p{color:#6B6B70;font-size:13.5px;margin:0 0 18px}
input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #E7E6E1;border-radius:8px;font-size:14px;margin-bottom:10px}
button{width:100%;padding:10px;border:none;border-radius:8px;background:#17171A;color:#fff;font-size:14px;font-weight:600;cursor:pointer}
button:hover{background:#1F5C57}.msg{min-height:18px;color:#B0413E;font-size:12.5px}</style></head>
<body><div class="box"><h1>Loop News</h1><p>邮箱验证码登录</p>
<div id="s1"><input id="email" type="email" placeholder="你的邮箱" autofocus>
<button id="send">发送验证码</button></div>
<div id="s2" hidden><input id="code" inputmode="numeric" placeholder="6 位验证码">
<button id="login">登录</button></div>
<div class="msg" id="msg"></div></div>
<script>
var API=%API%;var email=document.getElementById('email'),code=document.getElementById('code'),msg=document.getElementById('msg');
function post(path,body){return fetch(API+path,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(function(r){return r.json().then(function(j){return{s:r.status,j:j}})})}
document.getElementById('send').onclick=function(){msg.textContent='';post('/auth/request-code',{email:email.value.trim()}).then(function(x){if(x.s!==200){msg.textContent=x.j.error||'失败';return}document.getElementById('s1').hidden=true;document.getElementById('s2').hidden=false;code.focus();if(x.j.dev_code)msg.style.color='#1F5C57',msg.textContent='dev 码:'+x.j.dev_code})};
document.getElementById('login').onclick=function(){msg.textContent='';post('/auth/verify',{email:email.value.trim(),code:code.value.trim()}).then(function(x){if(x.s!==200){msg.textContent=x.j.error||'失败';return}location.reload()})};
</script></body></html>`;

export async function onRequest(context) {
  const { request, env, next } = context;
  const tok = (request.headers.get("Cookie") || "").match(/(?:^|;\s*)lns=([^;]+)/);
  let sess = null;
  if (tok) {
    const raw = await env.SESSIONS.get("session:" + decodeURIComponent(tok[1]));
    if (raw) { try { sess = JSON.parse(raw); } catch {} }
  }
  if (!sess) {
    // 登录页的 API 基址:优先 env.SITE_API;否则按域名自动推导(gray-* → 灰度 API,否则生产)。
    const host = new URL(request.url).hostname;
    const api = JSON.stringify(env.SITE_API || (host.includes("gray") ? "https://gray-feedback.xdzq.org" : "https://feedback.xdzq.org"));
    return new Response(LOGIN_HTML.replace("%API%", api), {
      status: 401, headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }
  const resp = await next();
  const out = new Response(resp.body, resp);
  out.headers.append("Set-Cookie", `lnrole=${sess.role}; Domain=.xdzq.org; Path=/; Secure; SameSite=Lax; Max-Age=2592000`);
  return out;
}
