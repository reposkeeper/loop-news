export async function sendCode(env, email, code) {
  if (env.LN_DEV) return { ok: true, dev: true };
  const from = env.MAIL_FROM || "Loop News <login@xdzq.org>";
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
  return { ok: resp.ok };
}
