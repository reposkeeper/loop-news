# SP1-Core 账号认证与登录门 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用邮箱验证码真账号 + 服务端会话替代现有 token 访问墙,并把现有 per-user 端点(反馈/收藏/关注/已读/请求)从 token 改用会话身份,使反馈**按账号隔离**、动作**进活动日志**,站点全程不破坏。

**Architecture:** 单个 API Worker(仍是 `worker/feedback-worker.js`,挂 `feedback.xdzq.org`)内拆出 `worker/lib/*` 模块,承载 `/auth/*` 与身份化的 per-user 端点;短命/热点(OTP、session、限流)放 **KV**,关系/可查询数据(users、activity、feedback、favorites…)放 **D1**;`functions/_middleware.js` 从 token 门改为 **session 门 + 登录页**。验证码邮件走 **Resend** REST。

**Tech Stack:** Cloudflare Workers(ES Modules)+ Pages Functions;D1(SQLite)、KV;Resend(HTTP API);Web Crypto(`crypto.subtle` / `getRandomValues`);Vitest(纯函数单测,Node 环境);`wrangler` CLI。

## Global Constraints

以下为**全计划硬约束**,每个任务都隐含遵守(取自两份 spec,逐字):

- **时区** Asia/Shanghai;所有时间戳写 ISO8601 带 `+08:00` 或 UTC `Z` 一致即可,展示按上海时区。
- **不改文件名 `worker/feedback-worker.js`**:它被 `CLAUDE.md`/`RUNBOOK.md`/`AGENTS.md` 按名引用,改名会让 `scripts/check.sh` 的「引用完整性」失败。只在其内 `import` 新的 `worker/lib/*.js`(check.sh 的正则 `worker/[\w.\-]+\.js` 不扫子目录,安全)。
- **每次提交必过 `bash scripts/check.sh`**(pre-commit 已强制):它会 `python3 web/compile.py` 到临时目录且**不许残留 `{{token}}`**、校验 JSON/skill/引用自洽。改 `web/templates/page.html` 或 `web/compile.py` 后务必保证编译通过、无残留占位。
- **cookie 作用域** `Domain=.xdzq.org`;会话 cookie `lns` 必须 `HttpOnly; Secure; SameSite=Lax`。
- **CORS**:带凭证的端点响应 `Access-Control-Allow-Origin: <SITE_ORIGIN>`(具体源,**禁用 `*`)+ `Access-Control-Allow-Credentials: true`;`SITE_ORIGIN` 从 env 读(默认 `https://news.xdzq.org`)。
- **OTP**:6 位数字、KV 哈希存、TTL 600s、一次性、尝试≤5、**恒定时间比对**、按邮箱(1/60s)+ IP(20/3600s)限流。
- **会话**:32 字节随机 → base64url;KV `session:<token>` TTL 2592000s(30 天),可吊销;`usess:<user_id>` 维护该用户 token 列表以便踢下线。
- **注册策略**:owner 白名单/邀请——只有 D1 `users` 里 `status ∈ {invited, active}` 的邮箱能收码;其余 `request-code` 返回 403。
- **owner 判定**靠会话里的 `role`(D1 真源),非前端 cookie。
- **秘密**:`RESEND_API_KEY` 用 `wrangler secret put`,**永不入库**;`.dev.vars`(本地)已被 `.gitignore` 的 `.env`/`*.key` 覆盖不到,需在本任务把 `.dev.vars` 加进 `.gitignore`。
- **本地 dev 不发真邮件**:`LN_DEV=1` 时验证码直接在响应/日志给出,不调 Resend。

---

## 文件结构(SP1-Core 创建/修改)

| 文件 | 职责 |
|---|---|
| `worker/schema.sql`(新) | D1 全量建表(users/activity/feedback/favorites/follows/reads/requests),`IF NOT EXISTS` 幂等 |
| `worker/lib/store.js`(新) | D1/KV 薄封装:参数化查询、JSON 序列化、KV get/put/del(带 TTL) |
| `worker/lib/otp.js`(新) | 生成/哈希/恒定时间校验 6 位码;限流计数 |
| `worker/lib/session.js`(新) | 会话签发/校验/吊销;cookie 解析与 Set-Cookie 串;身份提取 `identify(req,env)` |
| `worker/lib/email.js`(新) | Resend 发信;`LN_DEV` 时跳过 |
| `worker/lib/auth.js`(新) | 端点处理:`/auth/request-code`、`/auth/verify`、`/auth/logout`、`/me`;活动日志 |
| `worker/lib/activity.js`(新) | `logActivity(env,user_id,action,target,meta)` + `/activity` beacon 端点 |
| `worker/feedback-worker.js`(改) | 路由:接 `/auth/*`、`/me`、`/activity`;per-user 端点改用会话身份;CORS 收紧带凭证 |
| `functions/_middleware.js`(改) | session 门 + 两步登录页;绑定 KV;写 `lnrole`/`lnname` 供前端即时 UI |
| `wrangler.toml`(改) | 加 `[[kv_namespaces]]`(SESSIONS)、`[[d1_databases]]`(DB)、env `SITE_ORIGIN` |
| `scripts/setup-auth.sh`(新) | 一次性:建 KV/D1、apply schema、按 `OWNER_EMAIL` 播种 owner |
| `web/templates/page.html`(改) | per-user JS 去 token 化:凭证 fetch;`is-owner` 由 `/me` 确认;加「退出」入口 |
| `web/compile.py`(改) | 注入 `{{SITE_API}}`(已有 `{{FEEDBACK_API}}` 可复用);移除 token 生成入口(留到 SP1-UI 换成用户管理) |
| `package.json`(改) | 加 `vitest` devDep + `"test": "vitest run"` |
| `worker/lib/otp.test.js` / `session.test.js`(新) | 纯函数单测 |
| `CLOUDFLARE.md` / `RUNBOOK.md` / `AGENTS.md` / `CLAUDE.md`(改) | 身份模型、setup、ln-evolve owner 过滤说明 |
| `.gitignore`(改) | 加 `.dev.vars` |
| `prompts/CHANGELOG.md`(改) | 记结构升级(check.sh 要求进化留痕) |

**依赖顺序**:T1(资源+schema)→ T2(store)→ T3(otp)→ T4(session)→ T5(email)→ T6(auth 端点)→ T7(路由接线)→ T8(middleware 登录门)→ T9(per-user 端点身份化)→ T10(前端去 token)→ T11(活动日志)→ T12(setup 脚本 + 文档 + 收尾)。

---

### Task 1: Cloudflare 资源 + D1 schema + wrangler 绑定

**Files:**
- Create: `worker/schema.sql`
- Modify: `wrangler.toml`
- Modify: `.gitignore`

**Interfaces:**
- Produces: D1 库 `loop-news-db`(binding `DB`)、KV 命名空间(binding `SESSIONS`);表 `users(id,email,name,role,status,theme,created_at,last_seen_at)`、`activity(id,user_id,ts,action,target,meta)`、`feedback(id,user_id,ts,action,item_id,date,title,tags,text)`、`favorites(user_id,item_id,date,title,ts)`、`follows(user_id,item_id,title,topics,entities,ts)`、`reads(user_id,item_id,ts)`、`requests(id,user_id,ts,text,tags,status)`。

- [ ] **Step 1: 写 `worker/schema.sql`(全量,幂等)**

```sql
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT 'viewer',    -- owner|viewer
  status TEXT NOT NULL DEFAULT 'invited',  -- invited|active|disabled
  theme TEXT NOT NULL DEFAULT 'auto',       -- auto|light|dark
  created_at TEXT NOT NULL,
  last_seen_at TEXT
);
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL, ts TEXT NOT NULL,
  action TEXT NOT NULL, target TEXT DEFAULT '', meta TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_activity_user_ts ON activity(user_id, ts);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL, ts TEXT NOT NULL, action TEXT NOT NULL,
  item_id TEXT, date TEXT, title TEXT, tags TEXT, text TEXT
);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id, ts);
CREATE TABLE IF NOT EXISTS favorites (
  user_id INTEGER NOT NULL, item_id TEXT NOT NULL,
  date TEXT, title TEXT, ts TEXT, PRIMARY KEY(user_id, item_id)
);
CREATE TABLE IF NOT EXISTS follows (
  user_id INTEGER NOT NULL, item_id TEXT NOT NULL,
  title TEXT, topics TEXT, entities TEXT, ts TEXT, PRIMARY KEY(user_id, item_id)
);
CREATE TABLE IF NOT EXISTS reads (
  user_id INTEGER NOT NULL, item_id TEXT NOT NULL, ts TEXT, PRIMARY KEY(user_id, item_id)
);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL, ts TEXT, text TEXT, tags TEXT, status TEXT DEFAULT 'new'
);
```

- [ ] **Step 2: 创建资源(一次性,记下返回的 id)**

Run:
```bash
npx wrangler d1 create loop-news-db
npx wrangler kv namespace create SESSIONS
```
Expected: 各自打印一段 `[[d1_databases]]` / `[[kv_namespaces]]` TOML 片段(含 `database_id` / `id`)。复制备用。

- [ ] **Step 3: 在 `wrangler.toml` 追加绑定与 env**

在现有 `[[r2_buckets]]` 之后追加(把上一步的真实 id 填入):
```toml
[[kv_namespaces]]
binding = "SESSIONS"
id = "<粘贴 KV id>"

[[d1_databases]]
binding = "DB"
database_name = "loop-news-db"
database_id = "<粘贴 D1 id>"

[vars]
SITE_ORIGIN = "https://news.xdzq.org"
```

- [ ] **Step 4: 应用 schema 到远端 D1**

Run: `npx wrangler d1 execute loop-news-db --remote --file worker/schema.sql`
Expected: `Executed N commands` 无错误。

- [ ] **Step 5: `.gitignore` 加 `.dev.vars`**

在 `.env` 那组下加一行 `.dev.vars`(本地 secret,不入库)。

- [ ] **Step 6: 提交**

```bash
git add worker/schema.sql wrangler.toml .gitignore
git commit -m "feat(auth): D1 schema + KV/D1 wrangler 绑定(SP1-Core T1)"
```

---

### Task 2: `store.js` —— D1/KV 薄封装

**Files:**
- Create: `worker/lib/store.js`

**Interfaces:**
- Produces:
  - `d1(env)` → env.DB
  - `getUserByEmail(env, email)` → `{id,email,name,role,status,theme,...}|null`
  - `insertUser(env, {email,name,role,status})` → id
  - `touchLastSeen(env, user_id)`
  - `kvGetJSON(env, key)` / `kvPutJSON(env, key, obj, ttlSec)` / `kvDel(env, key)`
  - `nowISO()` → 上海时区 ISO 字符串

- [ ] **Step 1: 写 `worker/lib/store.js`**

```js
export const d1 = (env) => env.DB;

// 上海时区 ISO(无 Date 依赖问题:Worker 有真实时钟)
export function nowISO() {
  return new Date().toISOString(); // 存 UTC Z;展示层转上海
}

export async function getUserByEmail(env, email) {
  const r = await env.DB.prepare(
    "SELECT id,email,name,role,status,theme,created_at,last_seen_at FROM users WHERE email=?"
  ).bind(email).first();
  return r || null;
}
export async function getUserById(env, id) {
  return (await env.DB.prepare(
    "SELECT id,email,name,role,status,theme FROM users WHERE id=?"
  ).bind(id).first()) || null;
}
export async function insertUser(env, { email, name = "", role = "viewer", status = "invited" }) {
  const r = await env.DB.prepare(
    "INSERT INTO users (email,name,role,status,created_at) VALUES (?,?,?,?,?)"
  ).bind(email, name, role, status, nowISO()).run();
  return r.meta.last_row_id;
}
export async function setUserStatus(env, id, status) {
  await env.DB.prepare("UPDATE users SET status=? WHERE id=?").bind(status, id).run();
}
export async function touchLastSeen(env, id) {
  await env.DB.prepare("UPDATE users SET last_seen_at=? WHERE id=?").bind(nowISO(), id).run();
}

export async function kvGetJSON(env, key) {
  const s = await env.SESSIONS.get(key);
  if (!s) return null;
  try { return JSON.parse(s); } catch { return null; }
}
export async function kvPutJSON(env, key, obj, ttlSec) {
  const opt = ttlSec ? { expirationTtl: ttlSec } : {};
  await env.SESSIONS.put(key, JSON.stringify(obj), opt);
}
export async function kvDel(env, key) { await env.SESSIONS.delete(key); }
```

- [ ] **Step 2: 提交**

```bash
git add worker/lib/store.js
git commit -m "feat(auth): store.js D1/KV 薄封装(SP1-Core T2)"
```

---

### Task 3: `otp.js` —— 验证码生成/哈希/校验 + 限流(TDD)

**Files:**
- Create: `worker/lib/otp.js`
- Create: `worker/lib/otp.test.js`
- Modify: `package.json`

**Interfaces:**
- Produces:
  - `genCode()` → 6 位数字字符串(前导零保留)
  - `hashCode(code, email, salt)` → hex string(SHA-256)
  - `constEq(a, b)` → bool(恒定时间)
  - `checkRate(env, key, limit, ttlSec)` → `{ok:bool}`(KV 计数器)

- [ ] **Step 1: `package.json` 加测试**

`"scripts"` 里加 `"test": "vitest run"`;`devDependencies` 加 `"vitest": "^2.0.0"`。然后 `npm install`。

- [ ] **Step 2: 写失败测试 `worker/lib/otp.test.js`**

```js
import { describe, it, expect } from "vitest";
import { genCode, hashCode, constEq } from "./otp.js";

describe("otp", () => {
  it("genCode 是 6 位数字、含前导零可能", () => {
    for (let i = 0; i < 200; i++) {
      const c = genCode();
      expect(c).toMatch(/^\d{6}$/);
    }
  });
  it("hashCode 确定且随 salt/email 变化", async () => {
    const a = await hashCode("123456", "x@a.com", "s1");
    const b = await hashCode("123456", "x@a.com", "s1");
    const c = await hashCode("123456", "x@a.com", "s2");
    expect(a).toBe(b);
    expect(a).not.toBe(c);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
  });
  it("constEq 相等/不等", () => {
    expect(constEq("abc", "abc")).toBe(true);
    expect(constEq("abc", "abd")).toBe(false);
    expect(constEq("abc", "ab")).toBe(false);
  });
});
```

- [ ] **Step 3: 运行,确认失败**

Run: `npm test`
Expected: FAIL(`Cannot find module './otp.js'` 或断言失败)。

- [ ] **Step 4: 写 `worker/lib/otp.js`**

```js
import { kvGetJSON, kvPutJSON } from "./store.js";

export function genCode() {
  const n = crypto.getRandomValues(new Uint32Array(1))[0] % 1000000;
  return String(n).padStart(6, "0");
}
export async function hashCode(code, email, salt) {
  const data = new TextEncoder().encode(`${code}:${email}:${salt}`);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
export function constEq(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
// KV 计数器限流:窗口内自增,超过 limit 返回 {ok:false}
export async function checkRate(env, key, limit, ttlSec) {
  const cur = (await kvGetJSON(env, key)) || { n: 0 };
  if (cur.n >= limit) return { ok: false };
  await kvPutJSON(env, key, { n: cur.n + 1 }, ttlSec);
  return { ok: true };
}
```

- [ ] **Step 5: 运行,确认通过**

Run: `npm test`
Expected: PASS(3 通过)。

- [ ] **Step 6: 提交**

```bash
git add worker/lib/otp.js worker/lib/otp.test.js package.json package-lock.json
git commit -m "feat(auth): otp 生成/哈希/恒定时间比对/限流 + 单测(SP1-Core T3)"
```

---

### Task 4: `session.js` —— 会话签发/校验/吊销 + cookie(TDD 纯函数)

**Files:**
- Create: `worker/lib/session.js`
- Create: `worker/lib/session.test.js`

**Interfaces:**
- Consumes: `store.js` 的 KV 封装。
- Produces:
  - `parseCookie(header, name)` → string(纯函数,可测)
  - `sessionCookie(token, {maxAge})` / `clearCookie(name)` → Set-Cookie 串(纯函数,可测)
  - `mintSession(env, user)` → token(写 KV `session:<token>` + `usess:<id>`)
  - `verifySession(env, token)` → `{user_id,email,role}|null`(命中则滑动续期)
  - `revokeSession(env, token)`;`revokeAllForUser(env, user_id)`
  - `SESSION_TTL = 2592000`

- [ ] **Step 1: 写失败测试 `worker/lib/session.test.js`(纯函数部分)**

```js
import { describe, it, expect } from "vitest";
import { parseCookie, sessionCookie, clearCookie } from "./session.js";

describe("cookie", () => {
  it("parseCookie 取指定名", () => {
    const h = "lns=abc.def; lnrole=owner; x=1";
    expect(parseCookie(h, "lns")).toBe("abc.def");
    expect(parseCookie(h, "lnrole")).toBe("owner");
    expect(parseCookie(h, "nope")).toBe("");
    expect(parseCookie(null, "lns")).toBe("");
  });
  it("sessionCookie 含安全属性与 Domain", () => {
    const c = sessionCookie("tok123", { maxAge: 100 });
    expect(c).toContain("lns=tok123");
    expect(c).toContain("Domain=.xdzq.org");
    expect(c).toContain("HttpOnly");
    expect(c).toContain("Secure");
    expect(c).toContain("SameSite=Lax");
    expect(c).toContain("Max-Age=100");
  });
  it("clearCookie 立即过期", () => {
    expect(clearCookie("lns")).toContain("Max-Age=0");
  });
});
```

- [ ] **Step 2: 运行,确认失败**

Run: `npm test`
Expected: FAIL(`Cannot find module './session.js'`)。

- [ ] **Step 3: 写 `worker/lib/session.js`**

```js
import { kvGetJSON, kvPutJSON, kvDel, getUserById } from "./store.js";

export const SESSION_TTL = 2592000; // 30d
const COOKIE_DOMAIN = "Domain=.xdzq.org";

export function parseCookie(header, name) {
  const m = (header || "").match(new RegExp("(?:^|;\\s*)" + name + "=([^;]+)"));
  return m ? decodeURIComponent(m[1]) : "";
}
export function sessionCookie(token, { maxAge = SESSION_TTL } = {}) {
  return `lns=${token}; ${COOKIE_DOMAIN}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}
export function uiCookie(name, val, maxAge = SESSION_TTL) {
  // 非 httpOnly,供前端即时渲染(role/name)
  return `${name}=${encodeURIComponent(val)}; ${COOKIE_DOMAIN}; Path=/; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}
export function clearCookie(name) {
  return `${name}=; ${COOKIE_DOMAIN}; Path=/; Secure; SameSite=Lax; Max-Age=0`;
}

function b64url(bytes) {
  let s = btoa(String.fromCharCode(...bytes));
  return s.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
export async function mintSession(env, user) {
  const token = b64url(crypto.getRandomValues(new Uint8Array(32)));
  await kvPutJSON(env, `session:${token}`, { user_id: user.id, email: user.email, role: user.role }, SESSION_TTL);
  const idx = (await kvGetJSON(env, `usess:${user.id}`)) || [];
  idx.push(token);
  await kvPutJSON(env, `usess:${user.id}`, idx, SESSION_TTL);
  return token;
}
export async function verifySession(env, token) {
  if (!token) return null;
  const s = await kvGetJSON(env, `session:${token}`);
  if (!s) return null;
  // 滑动续期 + 校验用户仍有效
  const u = await getUserById(env, s.user_id);
  if (!u || u.status === "disabled") { await kvDel(env, `session:${token}`); return null; }
  await kvPutJSON(env, `session:${token}`, s, SESSION_TTL);
  return { user_id: s.user_id, email: s.email, role: u.role };
}
export async function revokeSession(env, token) {
  await kvDel(env, `session:${token}`);
}
export async function revokeAllForUser(env, user_id) {
  const idx = (await kvGetJSON(env, `usess:${user_id}`)) || [];
  for (const t of idx) await kvDel(env, `session:${t}`);
  await kvDel(env, `usess:${user_id}`);
}
```

- [ ] **Step 4: 运行,确认通过**

Run: `npm test`
Expected: PASS(cookie 3 项 + 之前 otp 全过)。

- [ ] **Step 5: 提交**

```bash
git add worker/lib/session.js worker/lib/session.test.js
git commit -m "feat(auth): session 签发/校验/吊销 + cookie 纯函数单测(SP1-Core T4)"
```

---

### Task 5: `email.js` —— Resend 发信(dev 跳过)

**Files:**
- Create: `worker/lib/email.js`

**Interfaces:**
- Produces: `sendCode(env, email, code)` → `{ok:bool, dev?:bool}`;`LN_DEV` 为真时不发信、返回 `{ok:true, dev:true}`(码由调用方在 dev 下回显)。

- [ ] **Step 1: 写 `worker/lib/email.js`**

```js
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
```

- [ ] **Step 2: 提交**

```bash
git add worker/lib/email.js
git commit -m "feat(auth): email.js Resend 发信(dev 跳过)(SP1-Core T5)"
```

---

### Task 6: `auth.js` —— 端点处理(request-code / verify / logout / me)

**Files:**
- Create: `worker/lib/auth.js`
- Create: `worker/lib/activity.js`

**Interfaces:**
- Consumes: `store.js`、`otp.js`、`session.js`、`email.js`。
- Produces(供路由调用,均返回 `Response`):
  - `handleRequestCode(req, env)` — POST `{email}`
  - `handleVerify(req, env)` — POST `{email, code}`
  - `handleLogout(req, env)`
  - `handleMe(req, env)` — GET
  - `identify(req, env)` → `{user_id,email,role}|null`(其他端点复用)
  - `logActivity(env, user_id, action, target, meta)`

- [ ] **Step 1: 写 `worker/lib/activity.js`**

```js
import { nowISO } from "./store.js";
export async function logActivity(env, user_id, action, target = "", meta = "") {
  try {
    await env.DB.prepare(
      "INSERT INTO activity (user_id,ts,action,target,meta) VALUES (?,?,?,?,?)"
    ).bind(user_id, nowISO(), action, String(target).slice(0, 200),
           typeof meta === "string" ? meta : JSON.stringify(meta)).run();
  } catch (_) { /* 日志失败不阻塞主流程 */ }
}
```

- [ ] **Step 2: 写 `worker/lib/auth.js`**

```js
import { getUserByEmail, setUserStatus, touchLastSeen, kvGetJSON, kvPutJSON, kvDel } from "./store.js";
import { genCode, hashCode, constEq, checkRate } from "./otp.js";
import { mintSession, verifySession, revokeSession, parseCookie, sessionCookie, uiCookie, clearCookie } from "./session.js";
import { sendCode } from "./email.js";
import { logActivity } from "./activity.js";

const OTP_TTL = 600;
function J(env, obj, status = 200, extraCookies = []) {
  const h = new Headers({ "Content-Type": "application/json; charset=utf-8" });
  h.set("Access-Control-Allow-Origin", env.SITE_ORIGIN || "https://news.xdzq.org");
  h.set("Access-Control-Allow-Credentials", "true");
  for (const c of extraCookies) h.append("Set-Cookie", c);
  return new Response(JSON.stringify(obj), { status, headers: h });
}
const norm = (e) => String(e || "").trim().toLowerCase();
const emailOk = (e) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e);

export async function identify(req, env) {
  const tok = parseCookie(req.headers.get("Cookie"), "lns");
  return await verifySession(env, tok);
}

export async function handleRequestCode(req, env) {
  let d; try { d = await req.json(); } catch { return J(env, { error: "bad json" }, 400); }
  const email = norm(d.email);
  if (!emailOk(email)) return J(env, { error: "邮箱格式不对" }, 400);
  const ip = req.headers.get("CF-Connecting-IP") || "0";
  if (!(await checkRate(env, `rl:code:${email}`, 1, 60)).ok) return J(env, { error: "请稍后再试(1 分钟 1 次)" }, 429);
  if (!(await checkRate(env, `rl:ip:${ip}`, 20, 3600)).ok) return J(env, { error: "请求过于频繁" }, 429);
  const user = await getUserByEmail(env, email);
  if (!user || user.status === "disabled") return J(env, { error: "该邮箱未被邀请" }, 403);
  const code = genCode();
  const salt = env.OTP_SALT || "ln";
  await kvPutJSON(env, `otp:${email}`, { hash: await hashCode(code, email, salt), attempts: 0 }, OTP_TTL);
  const r = await sendCode(env, email, code);
  const body = { ok: true };
  if (r.dev) body.dev_code = code; // 仅 LN_DEV
  return J(env, body);
}

export async function handleVerify(req, env) {
  let d; try { d = await req.json(); } catch { return J(env, { error: "bad json" }, 400); }
  const email = norm(d.email);
  const code = String(d.code || "").trim();
  const rec = await kvGetJSON(env, `otp:${email}`);
  if (!rec) return J(env, { error: "验证码已过期,请重发" }, 400);
  if (rec.attempts >= 5) { await kvDel(env, `otp:${email}`); return J(env, { error: "尝试过多,请重发" }, 400); }
  const salt = env.OTP_SALT || "ln";
  const ok = constEq(rec.hash, await hashCode(code, email, salt));
  if (!ok) {
    rec.attempts += 1;
    await kvPutJSON(env, `otp:${email}`, rec, OTP_TTL);
    return J(env, { error: "验证码不正确" }, 400);
  }
  await kvDel(env, `otp:${email}`); // 一次性
  const user = await getUserByEmail(env, email);
  if (!user || user.status === "disabled") return J(env, { error: "该邮箱未被邀请" }, 403);
  if (user.status === "invited") await setUserStatus(env, user.id, "active");
  const token = await mintSession(env, user);
  await touchLastSeen(env, user.id);
  await logActivity(env, user.id, "login");
  const cookies = [
    sessionCookie(token),
    uiCookie("lnrole", user.role),
    uiCookie("lnname", user.name || ""),
  ];
  return J(env, { ok: true, user: { name: user.name, role: user.role, theme: user.theme } }, 200, cookies);
}

export async function handleLogout(req, env) {
  const tok = parseCookie(req.headers.get("Cookie"), "lns");
  const who = await verifySession(env, tok);
  await revokeSession(env, tok);
  if (who) await logActivity(env, who.user_id, "logout");
  return J(env, { ok: true }, 200, [clearCookie("lns"), clearCookie("lnrole"), clearCookie("lnname")]);
}

export async function handleMe(req, env) {
  const who = await identify(req, env);
  if (!who) return J(env, { error: "unauthorized" }, 401);
  const u = await getUserByEmail(env, who.email);
  return J(env, { email: u.email, name: u.name, role: u.role, theme: u.theme });
}
```

- [ ] **Step 3: 提交**

```bash
git add worker/lib/auth.js worker/lib/activity.js
git commit -m "feat(auth): request-code/verify/logout/me + activity 日志(SP1-Core T6)"
```

---

### Task 7: 路由接线 + CORS 收紧(改 `feedback-worker.js`)

**Files:**
- Modify: `worker/feedback-worker.js`

**Interfaces:**
- Consumes: `auth.js`(`handle*`、`identify`、`logActivity`)。
- Produces: Worker 接受 `/auth/request-code`、`/auth/verify`、`/auth/logout`、`GET /me`;`OPTIONS` 预检返回带凭证 CORS;`/health` 保留。

- [ ] **Step 1: 顶部加 import**

在文件顶部加:
```js
import { handleRequestCode, handleVerify, handleLogout, handleMe, identify } from "./lib/auth.js";
```

- [ ] **Step 2: 收紧 CORS 常量(支持凭证)**

把现有 `const CORS = {... "Access-Control-Allow-Origin": "*" ...}` 改为按请求生成:新增函数
```js
function corsHeaders(env) {
  return {
    "Access-Control-Allow-Origin": env.SITE_ORIGIN || "https://news.xdzq.org",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Credentials": "true",
  };
}
```
并把 `fetch` 里 `OPTIONS` 分支与各 `json()`/响应改用 `corsHeaders(env)`(逐处替换 `...CORS`)。

- [ ] **Step 3: 在路由最前面(`/health` 之后)接 auth**

```js
if (p === "/auth/request-code" && req.method === "POST") return handleRequestCode(req, env);
if (p === "/auth/verify" && req.method === "POST") return handleVerify(req, env);
if (p === "/auth/logout" && req.method === "POST") return handleLogout(req, env);
if (p === "/me" && req.method === "GET") return handleMe(req, env);
```

- [ ] **Step 4: 本地起 dev + curl 冒烟(需先播种一个用户,见 T12;此处用临时 INSERT)**

Run(两个终端):
```bash
# 终端 A:本地 dev(LN_DEV 回显验证码,不发真邮件)
npx wrangler dev worker/feedback-worker.js --local --var LN_DEV:1 --port 8787
# 终端 B:先给本地 D1 播种一个 invited 用户
npx wrangler d1 execute loop-news-db --local --command \
 "INSERT INTO users (email,name,role,status,created_at) VALUES ('me@test.com','我','owner','invited','2026-07-01T00:00:00+08:00')"
curl -s -X POST localhost:8787/auth/request-code -H 'Content-Type: application/json' -d '{"email":"me@test.com"}'
```
Expected: 返回 `{"ok":true,"dev_code":"NNNNNN"}`。用该码:
```bash
curl -s -i -X POST localhost:8787/auth/verify -H 'Content-Type: application/json' -d '{"email":"me@test.com","code":"NNNNNN"}'
```
Expected: `200`,响应头含 `Set-Cookie: lns=...; HttpOnly; ...`,body `{"ok":true,"user":{"role":"owner"...}}`。带该 cookie 打 `/me` 应回该用户。

- [ ] **Step 5: 提交**

```bash
git add worker/feedback-worker.js
git commit -m "feat(auth): 路由接 /auth/* 与 /me,CORS 收紧带凭证(SP1-Core T7)"
```

---

### Task 8: middleware 登录门 + 两步登录页(改 `_middleware.js`)

**Files:**
- Modify: `functions/_middleware.js`

**Interfaces:**
- Consumes: KV `SESSIONS`(Pages 绑定);会话 `session:<token>` 由 API Worker 写入。
- Produces: 未登录 → 返回登录页(内容不下发);已登录 → 放行并回写 `lnrole`/`lnname`。移除旧 token 门与 `?token=` 逻辑。

- [ ] **Step 1: 给 Pages 项目绑定 KV**

Cloudflare 控制台 → Pages → loop-news → Settings → Functions → KV namespace bindings:变量名 `SESSIONS` → 选同一命名空间。(或 `wrangler pages` 部署时用 `--kv SESSIONS=<id>`。)

- [ ] **Step 2: 重写 `functions/_middleware.js`**

用登录页 HTML(两步:邮箱→码)替换现有 `GATE_HTML`;`onRequest` 改为查 KV session:
```js
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
    const api = JSON.stringify(env.SITE_API || "https://feedback.xdzq.org");
    return new Response(LOGIN_HTML.replace("%API%", api), {
      status: 401, headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }
  const resp = await next();
  const out = new Response(resp.body, resp);
  out.headers.append("Set-Cookie", `lnrole=${sess.role}; Domain=.xdzq.org; Path=/; Secure; SameSite=Lax; Max-Age=2592000`);
  return out;
}
```
> 注:middleware 只做「有无有效会话」的门;`lnname` 由 API 的 verify 已写过,失效时前端自会隐藏问候。`SITE_API` 若未在 Pages env 设置则回退默认。

- [ ] **Step 3: 本地验证门行为**

Run: `npx wrangler pages dev docs --kv SESSIONS --port 8788`(先 `python3 web/compile.py` 生成 docs)。
Expected: 无 cookie 访问 `localhost:8788/` → 返回登录页;带有效 `lns` cookie → 正常下发单页。

- [ ] **Step 4: 提交**

```bash
git add functions/_middleware.js
git commit -m "feat(auth): middleware 换 session 登录门 + 两步登录页(SP1-Core T8)"
```

---

### Task 9: per-user 端点身份化(反馈/收藏/关注/已读/请求改用会话)

**Files:**
- Modify: `worker/feedback-worker.js`

**Interfaces:**
- Consumes: `identify(req, env)`、`logActivity`、`store.js` 的 D1 封装。
- Produces: `/feedback`(POST)写 D1 `feedback(user_id=当前会话用户)`;`/favorite`/`/follow`/`/read`/`/request` 从会话取 `user_id`;`GET /feedback?role=owner` 供 ln-evolve;去掉请求体 `token` 依赖。

- [ ] **Step 1: `/feedback` POST 改为按会话写 D1**

把原 `fb/${ts}-...json`(R2)写入改为:先 `const who = await identify(req, env); if(!who) return 401;` 再
```js
await env.DB.prepare(
  "INSERT INTO feedback (user_id,ts,action,item_id,date,title,tags,text) VALUES (?,?,?,?,?,?,?,?)"
).bind(who.user_id, nowISO(), d.action, String(d.item_id||"").slice(0,120),
       String(d.date||"").slice(0,20), String(d.title||"").slice(0,300),
       JSON.stringify((d.tags||[]).slice(0,8)), String(d.text||"").slice(0,2000)).run();
await logActivity(env, who.user_id, "feedback", d.item_id, d.action);
```
移除对 `env.OWNER_TOKEN`/`d.token` 的判断(`ask` 动作留到 SP1-UI 的 owner 面板)。

- [ ] **Step 2: `GET /feedback` 改为查 D1,支持 role 过滤(给 ln-evolve)**

```js
if (p === "/feedback" && req.method === "GET") {
  const who = await identify(req, env);
  if (!who) return json(env, { error: "unauthorized" }, 401);
  const onlyOwner = url.searchParams.get("role") === "owner";
  // owner 可看全部或按 role;普通用户只能看自己
  let rows;
  if (who.role === "owner" && onlyOwner) {
    rows = await env.DB.prepare(
      "SELECT f.* FROM feedback f JOIN users u ON u.id=f.user_id WHERE u.role='owner' ORDER BY f.ts").all();
  } else if (who.role === "owner") {
    rows = await env.DB.prepare("SELECT * FROM feedback ORDER BY ts").all();
  } else {
    rows = await env.DB.prepare("SELECT * FROM feedback WHERE user_id=? ORDER BY ts").bind(who.user_id).all();
  }
  return json(env, { count: rows.results.length, items: rows.results });
}
```

- [ ] **Step 3: `/favorite`、`/favorites`、`/follow`、`/read`、`/reads`、`/request` 改用会话 user_id + D1**

逐个:开头 `const who = await identify(req, env); if(!who) return json(env,{error:"unauthorized"},401);`,把原 `tok = d.token` / `resolveToken` 逻辑删掉,存取键从 `<token>` 换成 `who.user_id`,改写/读取对应 D1 表(favorites/follows/reads/requests)。记 `logActivity(env, who.user_id, "favorite"|"follow"|"read"|"request", d.item_id)`。删除已无用的 `resolveToken`/`validTokens`/`/validate`/`/mint`/`/tokens`(token 体系整体退役;若 SP1-UI 尚需 `/mint` 概念则届时以用户邀请替代)。

- [ ] **Step 4: 本地 curl 冒烟(带 T7 拿到的 cookie)**

Run:
```bash
C='lns=<粘贴 verify 拿到的 token>'
curl -s -X POST localhost:8787/feedback -H "Cookie: $C" -H 'Content-Type: application/json' -d '{"action":"up","item_id":"x1","title":"t"}'
curl -s localhost:8787/feedback -H "Cookie: $C"
```
Expected: POST `{"ok":true...}`;GET 里出现刚写入的、且带 `user_id`。用另一个用户的 cookie GET 应看不到该条(隔离)。

- [ ] **Step 5: 提交**

```bash
git add worker/feedback-worker.js
git commit -m "feat(auth): per-user 端点改用会话身份 + 反馈迁 D1(隔离)(SP1-Core T9)"
```

---

### Task 10: 前端去 token 化(改 `page.html` / `compile.py`)

**Files:**
- Modify: `web/templates/page.html`
- Modify: `web/compile.py`

**Interfaces:**
- Consumes: API `/me`、`/feedback`、`/favorite`…(凭证 cookie)。
- Produces: 前端所有 per-user fetch 带 `credentials:'include'` 且**不再传 token**;`is-owner` 由 `/me` 的 `role` 决定;加「退出」按钮调 `/auth/logout`。

- [ ] **Step 1: 定位并改造 `page.html` 的 `<script>`**

- 删除 `ck("lnt")` 取 token 的用法;所有 `fetch(API+...)` 统一加 `credentials:'include'`,请求体去掉 `token` 字段,GET 去掉 `?token=`。
- 启动时 `fetch(API+'/me',{credentials:'include'}).then(...)`:200 则据 `role==='owner'` 给 `document.body.classList.add('is-owner')`、按 `name` 问候、应用 `theme`(SP1-UI 用);401 理论上不会发生(middleware 已挡),忽略。
- 保留原 `ck()` 仅用于读非敏感 UI cookie(`lnrole`/`lnname`),或直接改用 `/me` 结果。

- [ ] **Step 2: 加「退出」入口**

在导航区加一个按钮(可放页脚或设置位):
```html
<button class="nav-link" id="logoutBtn">退出登录</button>
```
脚本:
```js
document.getElementById('logoutBtn')?.addEventListener('click',function(){fetch(API+'/auth/logout',{method:'POST',credentials:'include'}).then(function(){location.reload()})});
```

- [ ] **Step 3: `compile.py` 收尾**

- `{{SYS_OWNER_NAV}}` 里现有「🔗 生成分享链接」按钮暂时改为空串或占位(token 分享退役;owner 用户管理留到 SP1-UI)。保证模板无残留 `{{}}`。
- 确认 `{{FEEDBACK_API}}` 仍注入(前端 API base);无需新增变量。

- [ ] **Step 4: 编译 + 门校验**

Run: `bash scripts/check.sh`
Expected: `✅ 变更落地自检通过`(编译无残留 token)。

- [ ] **Step 5: 提交**

```bash
git add web/templates/page.html web/compile.py
git commit -m "feat(auth): 前端去 token 化,凭证 fetch + 退出 + /me 判定 owner(SP1-Core T10)"
```

---

### Task 11: 浏览活动 beacon(view/open/share 记日志)

**Files:**
- Modify: `worker/feedback-worker.js`
- Modify: `web/templates/page.html`

**Interfaces:**
- Produces: `POST /activity {action,target,meta}`(会话校验)→ 写 `activity`;前端在 hash 路由切换(view)与分享点击(share_link/share_image)时发带凭证 beacon(view 去抖)。

- [ ] **Step 1: Worker 加 `/activity` 端点**

```js
if (p === "/activity" && req.method === "POST") {
  const who = await identify(req, env);
  if (!who) return json(env, { error: "unauthorized" }, 401);
  let d; try { d = await req.json(); } catch { return json(env, { error: "bad json" }, 400); }
  const allowed = new Set(["view","open","share_link","share_image"]);
  if (!allowed.has(d.action)) return json(env, { error: "bad action" }, 400);
  await logActivity(env, who.user_id, d.action, d.target || "", d.meta || "");
  return json(env, { ok: true });
}
```

- [ ] **Step 2: 前端发 beacon**

在 hash 路由切换处(现有 JS 切 view 的地方)加去抖上报:
```js
var _lastView='';
function reportView(t){if(t===_lastView)return;_lastView=t;fetch(API+'/activity',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'view',target:t})}).catch(function(){})}
```
在切到某日期/视图时调用 `reportView(target)`;在分享按钮点击处加 `fetch(API+'/activity',...{action:'share_link'|'share_image', target:item})`。

- [ ] **Step 3: 编译 + 校验 + 冒烟**

Run: `bash scripts/check.sh` → 通过。带 cookie `curl -X POST localhost:8787/activity -d '{"action":"view","target":"2026-07-01"}'` → `{"ok":true}`;`wrangler d1 execute ... --command "SELECT * FROM activity"` 里出现该行。

- [ ] **Step 4: 提交**

```bash
git add worker/feedback-worker.js web/templates/page.html
git commit -m "feat(auth): /activity beacon,记 view/open/share 动作(SP1-Core T11)"
```

---

### Task 12: setup 脚本 + 文档 + 部署收尾

**Files:**
- Create: `scripts/setup-auth.sh`
- Modify: `scripts/deploy-cloudflare.sh`
- Modify: `CLOUDFLARE.md`、`RUNBOOK.md`、`AGENTS.md`、`CLAUDE.md`
- Modify: `.claude/skills/ln-evolve/SKILL.md`
- Modify: `prompts/CHANGELOG.md`

**Interfaces:**
- Produces: 一次性建资源 + 播种 owner 的脚本;部署脚本加 D1 迁移;文档同步身份模型;ln-evolve 读反馈加 `role=owner` 过滤。

- [ ] **Step 1: 写 `scripts/setup-auth.sh`**

```bash
#!/usr/bin/env bash
# 一次性:建 KV/D1、apply schema、播种 owner。需先 wrangler login。
set -euo pipefail
cd "$(dirname "$0")/.."
: "${OWNER_EMAIL:?请先 export OWNER_EMAIL=你的邮箱}"
echo "[setup-auth] apply schema(远端)"
npx wrangler d1 execute loop-news-db --remote --file worker/schema.sql
echo "[setup-auth] 播种 owner: $OWNER_EMAIL"
npx wrangler d1 execute loop-news-db --remote --command \
 "INSERT OR IGNORE INTO users (email,name,role,status,created_at) VALUES ('$OWNER_EMAIL','站长','owner','active','$(date -u +%Y-%m-%dT%H:%M:%SZ)')"
echo "[setup-auth] 完成。别忘了:wrangler secret put RESEND_API_KEY;给 Pages 绑定 KV(SESSIONS)。"
```
`chmod +x scripts/setup-auth.sh`。

- [ ] **Step 2: `deploy-cloudflare.sh` 加 D1 迁移**

在部署 Worker 之前插一步:
```bash
echo "[deploy] 应用 D1 schema(幂等)"
npx wrangler d1 execute loop-news-db --remote --file worker/schema.sql
```

- [ ] **Step 3: 文档同步(改 4 份 + skill)**

- `CLOUDFLARE.md`:新增「账号体系」段:Resend 注册/验证 xdzq.org DNS/`wrangler secret put RESEND_API_KEY`;`bash scripts/setup-auth.sh`;Pages 绑 KV。删/标注旧 token 门段落废弃。
- `RUNBOOK.md`/`AGENTS.md`/`CLAUDE.md`:身份从 token → 邮箱账号;登录必需;反馈按 user_id 隔离;**ln-evolve 只吃 owner 反馈**(`GET /feedback?role=owner`)。
- `.claude/skills/ln-evolve/SKILL.md`(或其引用 prompt):读反馈处加 `role=owner` 过滤说明。
- **注意**:这些是 `check.sh` 会扫引用的文档,凡点名 `worker/*.js`/`scripts/*.sh` 必须真实存在——本任务新增的 `scripts/setup-auth.sh` 已建,`worker/feedback-worker.js` 未改名,安全。

- [ ] **Step 4: `prompts/CHANGELOG.md` 记一条**

加 `## 2026-07-01 · 账号体系(SP1-Core)` 段,列:token 门 → 邮箱验证码会话;反馈按 user_id 隔离;ln-evolve 限 owner 反馈。(check.sh 要求进化留痕。)

- [ ] **Step 5: 全量自检 + 提交**

Run: `bash scripts/check.sh`
Expected: `✅ 变更落地自检通过`。
```bash
git add scripts/setup-auth.sh scripts/deploy-cloudflare.sh CLOUDFLARE.md RUNBOOK.md AGENTS.md CLAUDE.md .claude/skills/ln-evolve/SKILL.md prompts/CHANGELOG.md
git commit -m "docs+setup: 账号体系 setup 脚本/部署迁移/文档/ln-evolve owner 过滤(SP1-Core T12)"
```

- [ ] **Step 6: 生产部署与验收(人工)**

Run: `bash scripts/deploy-cloudflare.sh`;`export OWNER_EMAIL=...; bash scripts/setup-auth.sh`;`npx wrangler secret put RESEND_API_KEY`;Pages 控制台绑 KV `SESSIONS`。
验收:① 无痕访问 news.xdzq.org → 登录页;② 用 owner 邮箱收到真码 → 登录 → 看到内容且 `is-owner`;③ 赞一条 → `GET /admin`(下阶段)或 D1 查 feedback 有 user_id;④ 退出 → 回登录页。

---

## Self-Review(对照 spec)

- **登录/会话/过期**(SP1 §6):T3(otp TTL/尝试/限流)、T4(会话 TTL/吊销)、T6(verify 一次性)、T8(门)。✓
- **访问门替代 token 墙**(§7):T8。✓
- **反馈按 user_id 隔离 + ln-evolve owner 过滤**(§8):T9、T12。✓
- **活动日志**(§9.2):T6(login/logout)、T9(feedback/favorite/…)、T11(view/open/share)。✓ 注:owner 管理 UI/活动抽屉属 **SP1-UI**。
- **CORS/cookie 跨子域**(§6.4):T7、T4、T8。✓
- **本地 dev 不发信**(§14):T5(`LN_DEV`)、T7(dev_code 回显)。✓
- **owner 引导**(§13):T12 setup-auth.sh。✓
- **未覆盖(有意,留后续计划)**:owner 用户管理面板 + 活动抽屉、夜间模式、`/me/theme`、精细部署文档打磨 → **SP1-UI**;个人画像/重排/进化/6→8 分 → **SP2**。
- **Placeholder 扫描**:无 TODO/TBD;各步含实际代码或确切命令。
- **类型一致**:`identify`→`{user_id,email,role}` 全程一致;`logActivity(env,user_id,action,target,meta)` 签名统一;cookie 名 `lns`/`lnrole`/`lnname` 统一。

## 后续计划(本计划完成后再各自 writing-plans)
1. **SP1-UI**:owner 用户管理面板(邀请/启禁/改角色)+ 活动抽屉 + 夜间模式(主题变量+切换+`/me/theme`+无闪白)+ CLOUDFLARE.md 打磨 + 本地 dev owner 模式。
2. **SP2-2c**:score.py 6→8(克制/创新)+ GOALS/scoring.md/owner 仪表盘(无账号依赖,可并行)。
3. **SP2-2a / 2b**:个人画像+服务端重排+个人 evolve+翻译版进化面;话题为键采集扩展。
