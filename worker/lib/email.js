export async function sendCode(env, email, code) {
  if (env.LN_DEV) return { ok: true, dev: true };
  const from = env.MAIL_FROM || "Loop News <login@xdzq.org>";
  try {
    const resp = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.RESEND_API_KEY}` },
      body: JSON.stringify({
        from,
        to: [email],
        subject: "Loop News 登录验证码",
        text: `你的登录验证码是 ${code},10 分钟内有效。若非本人操作请忽略。`,
        html: `<p>你的 Loop News 登录验证码:</p><p style="font-size:26px;font-weight:700;letter-spacing:4px">${code}</p><p>10 分钟内有效。若非本人操作请忽略。</p>`,
      }),
    });
    if (!resp.ok) {
      // 详细失败原因记服务端日志(wrangler tail / 面板可见),不下发给客户端。
      const body = await resp.text().catch(() => "");
      console.error(`[email] Resend send failed status=${resp.status} to=${email} from=${from} body=${body.slice(0, 400)}`);
      return { ok: false, status: resp.status };
    }
    return { ok: true };
  } catch (e) {
    console.error(`[email] Resend request error to=${email} err=${e && e.message}`);
    return { ok: false, error: String(e && e.message) };
  }
}
