# SP1-UI 实现计划:owner 用户管理面板 + 夜间模式

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐用户最初 4 条需求里剩的两条——owner 在页面内管理用户(邀请/启禁/改角色 + 查每个用户的活动)、以及用户可自配的夜间模式(自动/浅/深,跟随账号)。

**Architecture:** 建在 SP1-Core 之上(分支 `feat/user-isolation-auth`)。owner API 放新模块 `worker/lib/admin.js`(owner-only,查/改 D1),路由接进 `worker/feedback-worker.js`;前端在单页里加「用户管理」面板(owner 可见)。夜间模式利用**已变量化**的 `web/assets/style.css`——加一组 `[data-theme="dark"]` token 覆盖 + 无闪内联脚本 + 三档切换 + `POST /me/theme` 持久化到账号。

**Tech Stack:** Cloudflare Worker(ESM)、D1、KV;`web/compile.py`(确定性编译);CSS 自定义属性;Vitest(纯函数单测);`wrangler dev` 本地集成。

## Global Constraints

- **不改文件名 `worker/feedback-worker.js`**(被 CLAUDE/RUNBOOK/AGENTS 按名引用;改名破 check.sh 引用完整性)。新逻辑放 `worker/lib/admin.js`(子目录不被扫描)。
- **每次提交过 `bash scripts/check.sh`**(pre-commit 强制):编译到临时目录**不许残留 `{{token}}`**,校验 JSON/skill/引用。改 `web/templates/page.html`/`web/compile.py` 后务必编译通过。
- **owner 鉴权靠会话 role**:每个 `/admin/*` 端点 `const who = await identify(req, env); if (!who || who.role !== "owner") return json({error:"forbidden"}, 403);`。绝不信客户端。
- **响应用 worker 内的 `json(obj,status)`**(已 env 感知 = 具体源 + `Access-Control-Allow-Credentials: true`);前端所有 fetch 带 `credentials:"include"`。
- **主题值只允许** `auto` | `light` | `dark`。`auto` = 跟随 `prefers-color-scheme`。
- **无闪白**:主题在 CSS 前由 `<head>` 内联脚本按 localStorage 立即置 `document.documentElement.dataset.theme`。
- **设计纪律**(style.css 顶部):全站近乎墨×纸单色,唯一彩色留给认知分级(事实/推断/预测);夜间模式沿用此纪律(暖灰底 + 柔白字,分级色相不变、明度压暗)。
- 提交 SSH 签名(1Password);若 `op-ssh-sign`/"failed to fill whole buffer" 失败:重试一次,再不行 `git add -A` 报 DONE_WITH_CONCERNS(已 staged),**不禁用签名**。
- 时区 Asia/Shanghai;`logActivity(env,user_id,action,target,meta)` 已存在(`worker/lib/activity.js`),失败自吞不阻塞。

---

## 文件结构(SP1-UI 创建/修改)

| 文件 | 职责 |
|---|---|
| `worker/lib/admin.js`(新) | owner-only:`/admin/users`(列/邀/改/删)、`/admin/activity`(某用户或全部活动) |
| `worker/lib/admin.test.js`(新) | 纯函数单测(路径解析、字段白名单构建) |
| `worker/feedback-worker.js`(改) | 接 `/admin/*` 与 `POST /me/theme` 路由 |
| `worker/lib/auth.js`(改) | 加 `handleSetTheme`(POST /me/theme) |
| `web/assets/style.css`(改) | 加 `[data-theme="dark"]` token 覆盖 + `@media prefers-color-scheme` 自动;变量化少量残留裸色;删死 `.token-*` CSS |
| `web/templates/page.html`(改) | 无闪脚本 + 主题切换 UI + owner 用户管理面板(表/邀请/活动抽屉) |
| `web/compile.py`(改) | 注入无闪脚本到 `<head>`;`{{SYS_OWNER_NAV}}` → 「用户管理」按钮 |
| `CLOUDFLARE.md`/`RUNBOOK.md`/`prompts/CHANGELOG.md`(改) | 记 owner 面板 + 夜间模式 |

**依赖顺序**:T1(/me/theme)→ T2(暗色 CSS)→ T3(主题前端)→ T4(admin.js + 路由)→ T5(owner 面板前端)→ T6(文档 + CHANGELOG)。夜间模式(T1-3)与 owner 管理(T4-5)彼此独立,可分别验收。

---

### Task 1: `POST /me/theme` 端点(持久化主题到账号)

**Files:**
- Modify: `worker/lib/auth.js`
- Modify: `worker/feedback-worker.js`

**Interfaces:**
- Consumes: `identify(req,env)`、`logActivity`、`store.js` D1。
- Produces: `handleSetTheme(req, env)` — POST `{theme}` → 校验 auto|light|dark → `UPDATE users SET theme=?` → `{ok:true}`;非法 400;未登录 401。

- [ ] **Step 1: `worker/lib/auth.js` 加 `handleSetTheme`**

在文件末尾(其它 handler 旁)加,并确保 `handleSetTheme` 被 `export`:
```js
export async function handleSetTheme(req, env) {
  const who = await identify(req, env);
  if (!who) return J(env, { error: "unauthorized" }, 401);
  let d; try { d = await req.json(); } catch { return J(env, { error: "bad json" }, 400); }
  const theme = String(d.theme || "");
  if (!["auto", "light", "dark"].includes(theme)) return J(env, { error: "theme must be auto|light|dark" }, 400);
  await env.DB.prepare("UPDATE users SET theme=? WHERE id=?").bind(theme, who.user_id).run();
  await logActivity(env, who.user_id, "theme", theme);
  return J(env, { ok: true, theme });
}
```
(`J`, `identify`, `logActivity` already exist in this file.)

- [ ] **Step 2: `worker/feedback-worker.js` 导入 + 接路由**

顶部 import 追加 `handleSetTheme`:把现有 `import { handleRequestCode, handleVerify, handleLogout, handleMe, identify } from "./lib/auth.js";` 改为也含 `handleSetTheme`。
在 `GET /me` 路由之后加:
```js
if (p === "/me/theme" && req.method === "POST") return handleSetTheme(req, env);
```

- [ ] **Step 3: 本地冒烟**

Run(复用 SP1-Core 的本地起法):
```bash
npx wrangler d1 execute loop-news-db --local --file worker/schema.sql
npx wrangler d1 execute loop-news-db --local --command "INSERT OR IGNORE INTO users (email,name,role,status,created_at) VALUES ('me@test.com','我','owner','active','2026-07-01T00:00:00+08:00')"
npx wrangler dev --port 8787 --var LN_DEV:1   # 后台
curl --retry-connrefused --retry 60 --retry-delay 1 -sf localhost:8787/health
# 登录拿 cookie(request-code→dev_code→verify -i 取 lns),然后:
curl -s -X POST localhost:8787/me/theme -H "Cookie: lns=<TOKEN>" -H 'Content-Type: application/json' -d '{"theme":"dark"}'   # 期望 {"ok":true,"theme":"dark"}
curl -s -X POST localhost:8787/me/theme -H "Cookie: lns=<TOKEN>" -H 'Content-Type: application/json' -d '{"theme":"bogus"}'  # 期望 400
curl -s localhost:8787/me -H "Cookie: lns=<TOKEN>"   # 期望 theme:"dark"
npx wrangler d1 execute loop-news-db --local --command "SELECT theme FROM users WHERE email='me@test.com'"  # dark
pkill -f "wrangler dev"
```
Expected: 合法 theme 落库、`/me` 反映、非法 400。**Fallback**:若 `wrangler dev` 不稳,`node --check worker/lib/auth.js worker/feedback-worker.js`,提交并报 DONE_WITH_CONCERNS。

- [ ] **Step 4: 提交**
```bash
git add worker/lib/auth.js worker/feedback-worker.js
git commit -m "feat(ui): POST /me/theme 持久化主题到账号(SP1-UI T1)"
```

---

### Task 2: 夜间模式配色(CSS token 覆盖 + 变量化残留 + 清死 CSS)

**Files:**
- Modify: `web/assets/style.css`

**Interfaces:**
- Produces: `:root[data-theme="dark"]` 暗色 token;`@media (prefers-color-scheme:dark)` 让 `auto` 落暗色;新增少量语义变量(`--surface`/`--danger`/`--ok`)替换裸色。

- [ ] **Step 1: 现有 `:root`(第 3-11 行)补充语义变量**

在 `:root{ ... }` 内(`--predict` 那行后)追加,供暗色覆盖:
```css
  --surface:#FFFFFF;      /* 卡片/浮层实体面(原多处硬编码 #fff) */
  --danger:#B0413E; --ok:#2F6F4E;   /* 踩/错误、成功 */
  --sel:#1f5c5722;        /* ::selection 底 */
```

- [ ] **Step 2: 把关键裸色改用变量(仅核心几处,保持墨×纸)**

在 `web/assets/style.css` 里替换(用编辑器全局替换,注意只改颜色值处):
- `::selection{background:#1f5c5722;}` → `::selection{background:var(--sel);}`
- 出现的实体面 `#fff` / `#FFFFFF`(卡片、浮层、弹窗背景)→ `var(--surface)`(逐处确认是「面」语义再换;若是图标描边等特殊处可保留)。
- 踩/错误红 `#b0413e`/`#b0472e`/`#cf3b3b` → `var(--danger)`;成功绿 `#2f6f4e` 若非分级用 → `var(--ok)`。
> 不必穷尽所有裸色;目标是让**底/面/字/线/分级**这几类随主题走即可。

- [ ] **Step 3: 加暗色板 + auto**

在 `:root{...}` 块之后新增:
```css
/* ── 夜间模式:暖灰底 + 柔白字,分级色相不变、明度压暗(沿用墨×纸纪律) ── */
:root[data-theme="dark"]{
  --paper:#17171A; --raised:#202024; --surface:#202024;
  --ink:#ECEBE6; --ink-soft:#C7C6C1; --muted:#9A9AA0; --faint:#6B6B70;
  --line:#33333A; --line-soft:#2A2A30;
  --accent:#5FB6AC;
  --fact:#5FB98C; --infer:#D0A24E; --predict:#A98BE6;
  --danger:#E0736F; --ok:#5FB98C; --sel:#5fb6ac33;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#17171A; --raised:#202024; --surface:#202024;
    --ink:#ECEBE6; --ink-soft:#C7C6C1; --muted:#9A9AA0; --faint:#6B6B70;
    --line:#33333A; --line-soft:#2A2A30;
    --accent:#5FB6AC;
    --fact:#5FB98C; --infer:#D0A24E; --predict:#A98BE6;
    --danger:#E0736F; --ok:#5FB98C; --sel:#5fb6ac33;
  }
}
```
> 逻辑:显式 `data-theme="dark"` → 暗;显式 `="light"` → 亮(默认 :root);`auto`(无属性或 ="auto")→ 跟随系统。内联脚本(T3)保证 `data-theme` 早置,`@media` 覆盖仅在 auto 生效。

- [ ] **Step 4: 删死 `.token-*` CSS(SP1-Core 遗留)**

删掉 8 行分享令牌相关 CSS(`.token-list`/`.token-list-h`/`.token-row`/`.token-name`/`.token-copy`/`.token-new`/`.token-url` 等——`grep -n '\.token-' web/assets/style.css` 定位后删除这些规则)。

- [ ] **Step 5: 编译 + 门 + 目检**

Run: `python3 web/compile.py && bash scripts/check.sh`
Expected: `✅ 变更落地自检通过`。
```bash
grep -c 'data-theme="dark"' web/assets/style.css   # >0
grep -c '\.token-' web/assets/style.css            # 0(死 CSS 已清)
```

- [ ] **Step 6: 提交**
```bash
git add web/assets/style.css
git commit -m "feat(ui): 夜间模式配色([data-theme=dark] + auto)+ 清死 token CSS(SP1-UI T2)"
```

---

### Task 3: 主题前端(无闪脚本 + 三档切换 + 账号同步)

**Files:**
- Modify: `web/compile.py`
- Modify: `web/templates/page.html`

**Interfaces:**
- Consumes: `POST /me/theme`、`GET /me`(返回 theme)。
- Produces: `<head>` 无闪脚本;头部三档切换(自动/浅色/深色);localStorage `ln-theme` + 登录后同步账号。

- [ ] **Step 1: `web/compile.py` 注入无闪脚本到 `<head>`**

模板 `<head>` 里应有一处放脚本的位置;若无,在 `page.html` 的 `<head>` 内(样式表 `<link>` 之前)直接写内联脚本(它不依赖编译变量,可直接进模板,见 Step 2)。无需新增编译变量。

- [ ] **Step 2: `web/templates/page.html` 的 `<head>` 顶部加无闪脚本**

在 `<head>` 内、任何 CSS `<link>` 之前:
```html
<script>(function(){try{var t=localStorage.getItem("ln-theme")||"auto";document.documentElement.setAttribute("data-theme",t);}catch(e){}})();</script>
```
(`auto` 也写成属性值,配合 CSS 的 `:root:not([data-theme="light"])`+`[data-theme="dark"]` 逻辑正确落地。)

- [ ] **Step 3: 头部加三档切换**

在报头(`.hwrap` 内,靠右)加:
```html
<div class="theme-switch" role="group" aria-label="主题">
  <button class="th" data-theme-set="auto" title="跟随系统">🌗</button>
  <button class="th" data-theme-set="light" title="浅色">☀</button>
  <button class="th" data-theme-set="dark" title="深色">🌙</button>
</div>
```
`web/assets/style.css` 里给一点样式(可放本任务提交,与 T2 不冲突):
```css
.theme-switch{display:inline-flex;gap:2px;margin-left:auto;}
.theme-switch .th{background:none;border:1px solid var(--line);color:var(--muted);border-radius:4px;padding:2px 7px;cursor:pointer;font-size:13px;line-height:1;}
.theme-switch .th[aria-pressed="true"]{border-color:var(--accent);color:var(--accent);}
```

- [ ] **Step 4: 主题 JS(切换 + 持久化 + 账号同步)**

在 page.html 的 `<script>`(主脚本)里加,并在启动时调用 `initTheme()`:
```js
function applyTheme(t){document.documentElement.setAttribute("data-theme",t);
  document.querySelectorAll(".theme-switch .th").forEach(function(b){b.setAttribute("aria-pressed", b.getAttribute("data-theme-set")===t ? "true":"false");});}
function setTheme(t){try{localStorage.setItem("ln-theme",t);}catch(e){} applyTheme(t);
  if(API) fetch(API+"/me/theme",{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({theme:t})}).catch(function(){});}
function initTheme(){var t="auto";try{t=localStorage.getItem("ln-theme")||"auto";}catch(e){} applyTheme(t);
  document.querySelectorAll(".theme-switch .th").forEach(function(b){b.addEventListener("click",function(){setTheme(b.getAttribute("data-theme-set"));});});}
```
并在已有的启动 `/me` 回调里(T10 加的那段)——当 localStorage 无 `ln-theme` 且服务端 `u.theme` 存在时,用账号主题 hydrate:在 `.then(function(u){ ... })` 内加
```js
try{ if(!localStorage.getItem("ln-theme") && u.theme){ localStorage.setItem("ln-theme",u.theme); applyTheme(u.theme);} }catch(e){}
```
在脚本初始化处调用 `initTheme();`(与其它 init 并列)。

- [ ] **Step 5: 编译 + 门 + 目检**

Run: `python3 web/compile.py && bash scripts/check.sh` → 通过。
```bash
grep -c 'ln-theme' docs/index.html          # >0(无闪脚本 + JS)
grep -c 'data-theme-set' docs/index.html    # 3
node -e "1"  # 占位:JS 语法可由下方浏览器核对
```
(可选)用静态服务器打开 `docs/index.html`,点三档确认 `<html data-theme>` 变化、无控制台报错。

- [ ] **Step 6: 提交**
```bash
git add web/templates/page.html web/compile.py web/assets/style.css docs/index.html
git commit -m "feat(ui): 夜间模式前端——无闪脚本 + 三档切换 + 账号同步(SP1-UI T3)"
```

---

### Task 4: `admin.js` owner 用户管理 API + 路由

**Files:**
- Create: `worker/lib/admin.js`
- Create: `worker/lib/admin.test.js`
- Modify: `worker/feedback-worker.js`

**Interfaces:**
- Consumes: `identify`(auth.js)、`revokeAllForUser`(session.js)、`logActivity`(activity.js)、`nowISO`(store.js)、`json(obj,status)`(worker,env 感知 CORS)。
- Produces(均 owner-only,否则 403):
  - `GET /admin/users` → `{count, items:[{...user, feedback_count, activity_count}]}`
  - `POST /admin/users {email,name,role}` → `{ok, id}`(重复邮箱 409)
  - `PATCH /admin/users/:id {name?,role?,status?}` → `{ok}`(status=disabled 时吊销其会话;禁止改自己)
  - `DELETE /admin/users/:id` → `{ok}`(连带删其 per-user 数据 + 吊销会话;禁止删自己)
  - `GET /admin/activity?user_id=&limit=&before=` → `{count, items}`
  - 纯函数导出供测试:`parseUserId(path)`、`buildUserUpdate(body)`。

- [ ] **Step 1: 写失败测试 `worker/lib/admin.test.js`(纯函数)**
```js
import { describe, it, expect } from "vitest";
import { parseUserId, buildUserUpdate } from "./admin.js";

describe("admin helpers", () => {
  it("parseUserId 取路径末段数字", () => {
    expect(parseUserId("/admin/users/42")).toBe(42);
    expect(parseUserId("/admin/users/")).toBe(null);
    expect(parseUserId("/admin/users/abc")).toBe(null);
  });
  it("buildUserUpdate 只白名单 name/role/status,过滤非法", () => {
    expect(buildUserUpdate({ name: "A", role: "owner", status: "disabled" }))
      .toEqual({ sql: "name=?, role=?, status=?", vals: ["A", "owner", "disabled"] });
    expect(buildUserUpdate({ role: "hacker", evil: 1 })).toEqual({ sql: "", vals: [] });
    expect(buildUserUpdate({ status: "active" })).toEqual({ sql: "status=?", vals: ["active"] });
  });
});
```

- [ ] **Step 2: 运行,确认失败**

Run: `npm test` → FAIL(`Cannot find module './admin.js'`)。

- [ ] **Step 3: 写 `worker/lib/admin.js`**
```js
import { identify } from "./auth.js";
import { revokeAllForUser } from "./session.js";
import { logActivity } from "./activity.js";
import { nowISO } from "./store.js";

export function parseUserId(path) {
  const m = path.match(/^\/admin\/users\/(\d+)$/);
  return m ? parseInt(m[1], 10) : null;
}
const ROLES = new Set(["owner", "viewer"]);
const STATUSES = new Set(["invited", "active", "disabled"]);
export function buildUserUpdate(body) {
  const parts = [], vals = [];
  if (typeof body.name === "string") { parts.push("name=?"); vals.push(body.name.slice(0, 60)); }
  if (ROLES.has(body.role)) { parts.push("role=?"); vals.push(body.role); }
  if (STATUSES.has(body.status)) { parts.push("status=?"); vals.push(body.status); }
  return { sql: parts.join(", "), vals };
}

async function owner(req, env, json) {
  const who = await identify(req, env);
  if (!who || who.role !== "owner") return { err: json({ error: "forbidden" }, 403) };
  return { who };
}

export async function handleAdmin(req, env, url, json) {
  const p = url.pathname;
  const gate = await owner(req, env, json);
  if (gate.err) return gate.err;
  const me = gate.who;

  if (p === "/admin/users" && req.method === "GET") {
    const users = (await env.DB.prepare(
      "SELECT id,email,name,role,status,theme,channel,created_at,last_seen_at FROM users ORDER BY created_at").all()).results;
    const fb = (await env.DB.prepare("SELECT user_id, COUNT(*) c FROM feedback GROUP BY user_id").all()).results;
    const ac = (await env.DB.prepare("SELECT user_id, COUNT(*) c FROM activity GROUP BY user_id").all()).results;
    const fbm = Object.fromEntries(fb.map((r) => [r.user_id, r.c]));
    const acm = Object.fromEntries(ac.map((r) => [r.user_id, r.c]));
    const items = users.map((u) => ({ ...u, feedback_count: fbm[u.id] || 0, activity_count: acm[u.id] || 0 }));
    return json({ count: items.length, items });
  }

  if (p === "/admin/users" && req.method === "POST") {
    let d; try { d = await req.json(); } catch { return json({ error: "bad json" }, 400); }
    const email = String(d.email || "").trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return json({ error: "邮箱格式不对" }, 400);
    const name = String(d.name || "").slice(0, 60);
    const role = ROLES.has(d.role) ? d.role : "viewer";
    try {
      const r = await env.DB.prepare(
        "INSERT INTO users (email,name,role,status,created_at) VALUES (?,?,?, 'invited', ?)")
        .bind(email, name, role, nowISO()).run();
      await logActivity(env, me.user_id, "admin_invite", email);
      return json({ ok: true, id: r.meta.last_row_id });
    } catch (e) {
      return json({ error: "该邮箱已存在" }, 409);
    }
  }

  const uid = parseUserId(p);
  if (uid !== null && req.method === "PATCH") {
    if (uid === me.user_id) return json({ error: "不能改自己(防锁死)" }, 400);
    let d; try { d = await req.json(); } catch { return json({ error: "bad json" }, 400); }
    const { sql, vals } = buildUserUpdate(d);
    if (!sql) return json({ error: "无可改字段" }, 400);
    await env.DB.prepare(`UPDATE users SET ${sql} WHERE id=?`).bind(...vals, uid).run();
    if (d.status === "disabled") await revokeAllForUser(env, uid);
    await logActivity(env, me.user_id, "admin_update", String(uid), JSON.stringify(d));
    return json({ ok: true });
  }
  if (uid !== null && req.method === "DELETE") {
    if (uid === me.user_id) return json({ error: "不能删自己" }, 400);
    await revokeAllForUser(env, uid);
    for (const t of ["feedback", "favorites", "follows", "reads", "requests", "activity"]) {
      await env.DB.prepare(`DELETE FROM ${t} WHERE user_id=?`).bind(uid).run();
    }
    await env.DB.prepare("DELETE FROM users WHERE id=?").bind(uid).run();
    await logActivity(env, me.user_id, "admin_delete", String(uid));
    return json({ ok: true });
  }

  if (p === "/admin/activity" && req.method === "GET") {
    const userId = url.searchParams.get("user_id");
    const limit = Math.min(200, parseInt(url.searchParams.get("limit") || "100", 10) || 100);
    const before = url.searchParams.get("before");
    let q = "SELECT id,user_id,ts,action,target,meta FROM activity", cond = [], binds = [];
    if (userId) { cond.push("user_id=?"); binds.push(parseInt(userId, 10)); }
    if (before) { cond.push("ts<?"); binds.push(before); }
    if (cond.length) q += " WHERE " + cond.join(" AND ");
    q += " ORDER BY ts DESC LIMIT ?"; binds.push(limit);
    const items = (await env.DB.prepare(q).bind(...binds).all()).results;
    return json({ count: items.length, items });
  }
  return json({ error: "not found" }, 404);
}
```

- [ ] **Step 4: 运行,确认纯函数测试通过**

Run: `npm test` → PASS(admin helpers + 之前的 otp/session)。

- [ ] **Step 5: `worker/feedback-worker.js` 接路由**

顶部加 `import { handleAdmin } from "./lib/admin.js";`。在 `/me/theme` 路由之后(其它认证路由旁)加:
```js
if (p.startsWith("/admin/")) return handleAdmin(req, env, url, json);
```
(`json` 与 `url` 在 fetch 作用域内;`handleAdmin` 自己做 owner 鉴权。)

- [ ] **Step 6: 本地冒烟(owner 可管、非 owner 403)**
```bash
npx wrangler d1 execute loop-news-db --local --file worker/schema.sql
npx wrangler d1 execute loop-news-db --local --command "INSERT OR IGNORE INTO users (email,name,role,status,created_at) VALUES ('me@test.com','我','owner','active','2026-07-01T00:00:00+08:00'),('bob@test.com','Bob','viewer','active','2026-07-01T00:00:00+08:00')"
npx wrangler dev --port 8787 --var LN_DEV:1   # 后台;登录 owner(me)与 bob 各取 cookie
curl --retry-connrefused --retry 60 --retry-delay 1 -sf localhost:8787/health
# owner:
curl -s localhost:8787/admin/users -H "Cookie: lns=<OWNER>"            # 列出 me+bob,带 counts
curl -s -X POST localhost:8787/admin/users -H "Cookie: lns=<OWNER>" -H 'Content-Type: application/json' -d '{"email":"c@test.com","name":"C","role":"viewer"}'  # {ok,id}
curl -s -X PATCH localhost:8787/admin/users/2 -H "Cookie: lns=<OWNER>" -H 'Content-Type: application/json' -d '{"status":"disabled"}'  # {ok};bob 会话应被吊销
curl -s "localhost:8787/admin/activity?user_id=1" -H "Cookie: lns=<OWNER>"  # owner 的活动
# 非 owner:
curl -s -o /dev/null -w "%{http_code}\n" localhost:8787/admin/users -H "Cookie: lns=<BOB>"  # 403
pkill -f "wrangler dev"
```
Expected: owner 能列/邀/禁(禁后该用户 `/me` 401)、非 owner 403。**Fallback**:`wrangler dev` 不稳则 `node --check` 三文件 + 纯函数测试,提交并报 DONE_WITH_CONCERNS。

- [ ] **Step 7: 提交**
```bash
git add worker/lib/admin.js worker/lib/admin.test.js worker/feedback-worker.js
git commit -m "feat(ui): admin.js owner 用户管理 API(列/邀/改/删/活动)+ 路由(SP1-UI T4)"
```

---

### Task 5: owner 用户管理面板(前端)

**Files:**
- Modify: `web/templates/page.html`
- Modify: `web/compile.py`

**Interfaces:**
- Consumes: `/admin/users`(GET/POST/PATCH/DELETE)、`/admin/activity`。
- Produces: owner 可见的「👥 用户管理」入口 + 面板(用户表 + 邀请表单 + 点用户看活动抽屉)。

- [ ] **Step 1: `web/compile.py` 的 `{{SYS_OWNER_NAV}}` → 用户管理按钮**

把 `"{{SYS_OWNER_NAV}}": "",` 改为:
```python
        "{{SYS_OWNER_NAV}}": '<button class="nav-link nav-owner" id="adminBtn">👥 用户管理</button>',
```
(`.nav-owner` 已有 CSS,仅 `body.is-owner` 可见——沿用 SP1-Core 约定。)

- [ ] **Step 2: `web/templates/page.html` 加面板 HTML**

在页面弹窗区(原 tokenModal 位置附近、其它 `.fb-modal` 旁)加:
```html
<div class="fb-modal" id="adminModal" hidden>
  <div class="fb-box admin-box">
    <div class="fb-head"><span class="fb-act">👥 用户管理</span><button class="fb-x" id="adminClose" aria-label="关闭">✕</button></div>
    <div class="admin-invite">
      <input id="invEmail" class="fb-text" placeholder="邀请邮箱…" autocomplete="off">
      <input id="invName" class="fb-text" placeholder="名字(可选)">
      <button class="fb-submit" id="invBtn">邀请</button>
      <span class="fb-msg" id="invMsg"></span>
    </div>
    <div id="userList" class="user-list"><p class="empty">加载中…</p></div>
    <div id="actDrawer" class="act-drawer" hidden></div>
  </div>
</div>
```

- [ ] **Step 3: 面板 JS(加载/邀请/启禁/活动)**

在主 `<script>` 里加(并给 `#adminBtn` 绑开):
```js
var API_ADMIN = API; // 复用 API base
function openAdmin(){var m=document.getElementById("adminModal");if(!m)return;m.hidden=false;loadUsers();}
document.getElementById("adminBtn") && document.getElementById("adminBtn").addEventListener("click",openAdmin);
document.getElementById("adminClose") && document.getElementById("adminClose").addEventListener("click",function(){document.getElementById("adminModal").hidden=true;});
function loadUsers(){var el=document.getElementById("userList");
  fetch(API_ADMIN+"/admin/users",{credentials:"include"}).then(function(r){return r.json();}).then(function(d){
    if(!d.items){el.innerHTML='<p class="empty">无权限或无数据</p>';return;}
    el.innerHTML=d.items.map(function(u){
      return '<div class="user-row" data-id="'+u.id+'"><span class="u-email">'+esc(u.email)+'</span>'
        +'<span class="u-meta">'+esc(u.role)+' · '+esc(u.status)+' · 最近 '+esc((u.last_seen_at||"—").slice(0,10))+' · 反馈'+u.feedback_count+'</span>'
        +'<span class="u-ops"><button class="u-act" data-act="toggle" data-id="'+u.id+'" data-status="'+esc(u.status)+'">'+(u.status==="disabled"?"启用":"禁用")+'</button>'
        +'<button class="u-act" data-act="activity" data-id="'+u.id+'">活动</button></span></div>';
    }).join("");});}
document.getElementById("userList") && document.getElementById("userList").addEventListener("click",function(e){
  var b=e.target.closest(".u-act");if(!b)return;var id=b.getAttribute("data-id");
  if(b.getAttribute("data-act")==="toggle"){var ns=b.getAttribute("data-status")==="disabled"?"active":"disabled";
    fetch(API_ADMIN+"/admin/users/"+id,{method:"PATCH",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:ns})}).then(function(){loadUsers();});}
  else if(b.getAttribute("data-act")==="activity"){
    fetch(API_ADMIN+"/admin/activity?user_id="+id,{credentials:"include"}).then(function(r){return r.json();}).then(function(d){
      var dr=document.getElementById("actDrawer");dr.hidden=false;
      dr.innerHTML='<h4>活动(user '+id+')</h4>'+(d.items||[]).map(function(a){return '<div class="act-row"><span class="a-ts">'+esc(a.ts.slice(0,16))+'</span> <span class="a-act">'+esc(a.action)+'</span> <span class="a-t">'+esc(a.target||"")+'</span></div>';}).join("");});}
});
document.getElementById("invBtn") && document.getElementById("invBtn").addEventListener("click",function(){
  var em=document.getElementById("invEmail").value.trim(),nm=document.getElementById("invName").value.trim(),msg=document.getElementById("invMsg");
  fetch(API_ADMIN+"/admin/users",{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:em,name:nm})})
    .then(function(r){return r.json().then(function(j){return{s:r.status,j:j};});}).then(function(x){
      msg.textContent=x.s===200?"已邀请":(x.j.error||"失败");if(x.s===200){document.getElementById("invEmail").value="";loadUsers();}});
});
```
(`esc` 已在脚本里存在——SP1-Core 用过;若无则加 `function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}`。)

- [ ] **Step 4: 一点面板样式(`web/assets/style.css`)**
```css
.admin-box{max-width:560px;}
.admin-invite{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;}
.user-row{display:flex;flex-direction:column;gap:2px;padding:8px 0;border-bottom:1px solid var(--line-soft);}
.user-row .u-email{font-weight:600;}
.user-row .u-meta{font-size:12px;color:var(--muted);}
.user-row .u-ops{display:flex;gap:6px;margin-top:3px;}
.u-act{font-size:12px;border:1px solid var(--line);background:var(--surface);border-radius:4px;padding:2px 8px;cursor:pointer;color:var(--ink);}
.act-drawer{margin-top:10px;border-top:1px solid var(--line);padding-top:8px;max-height:220px;overflow:auto;}
.act-drawer .act-row{font-size:12px;color:var(--ink-soft);padding:2px 0;}
```

- [ ] **Step 5: 编译 + 门 + 目检**

Run: `python3 web/compile.py && bash scripts/check.sh` → 通过。
```bash
grep -c 'adminBtn\|/admin/users' docs/index.html   # >0
grep -c '{{' docs/index.html                         # 0(无残留占位)
```
(可选)静态服务器打开、给 `<body>` 加 `class="is-owner"` 模拟 owner,点「用户管理」确认面板渲染、无控制台报错(真实数据需部署后)。

- [ ] **Step 6: 提交**
```bash
git add web/templates/page.html web/compile.py web/assets/style.css docs/index.html
git commit -m "feat(ui): owner 用户管理面板(表/邀请/启禁/活动抽屉)(SP1-UI T5)"
```

---

### Task 6: 文档 + CHANGELOG

**Files:**
- Modify: `CLOUDFLARE.md`、`RUNBOOK.md`、`prompts/CHANGELOG.md`

- [ ] **Step 1: 文档补 owner 面板 + 夜间模式**

- `CLOUDFLARE.md` / `RUNBOOK.md`:在账号体系段补一句——owner 登录后页面内「👥 用户管理」可邀请/启禁用户、看每人活动;用户可在头部切换 自动/浅/深 主题(跟随账号)。
- 注意 check.sh 引用完整性:只点名真实存在的文件(勿引入不存在的路径)。

- [ ] **Step 2: `prompts/CHANGELOG.md` 加条目**

顶部加 `## 2026-07-01 · SP1-UI(owner 面板 + 夜间模式)`,列:`POST /me/theme` + `[data-theme=dark]` 三档主题(跟随账号);`worker/lib/admin.js` owner 用户管理(列/邀/改/删/活动,owner-only);死 token CSS 清理。

- [ ] **Step 3: 全量自检 + 提交**

Run: `bash scripts/check.sh` → `✅`。
```bash
git add CLOUDFLARE.md RUNBOOK.md prompts/CHANGELOG.md
git commit -m "docs: 记 owner 用户管理面板 + 夜间模式(SP1-UI T6)"
```

---

## Self-Review(对照 SP1 spec §9/§10 + 原始需求 3/4)

- **需求 4 夜间模式(用户自配)**:T1(/me/theme)、T2(暗色板/auto)、T3(无闪+三档+账号同步)。✅
- **需求 3 owner 管理用户 + 全动作日志**:活动日志 SP1-Core 已建;本计划 T4(admin API:列/邀/改/删 + 查活动)、T5(面板 UI)。✅
- **SP1 spec §9.1 端点**:`/admin/users`(GET/POST/PATCH/DELETE)、`/admin/activity` → T4。✅ 禁用即吊销会话(revokeAllForUser)、禁止改/删自己(防锁死)已含。
- **§10 主题**:变量化(已就绪)+ 暗板 + auto + 无闪 + 三档 + 账号同步 → T2/T3。✅
- **owner 鉴权靠 role**(全局约束):admin.js `owner()` 门。✅
- **凭证 CORS**:admin/theme 走 worker 的 env 感知 `json()`(SP1-Core 已修),前端 credentialed。✅
- **未覆盖(有意)**:owner 看用户「真实进化分」属 SP2(本计划只到活动日志);per-user 个性化属 SP2。
- **Placeholder 扫描**:无 TODO/TBD;各步含实际代码/命令。
- **类型一致**:`handleAdmin(req,env,url,json)`、`parseUserId`/`buildUserUpdate` 签名前后一致;`handleSetTheme` 用现有 `J`/`identify`/`logActivity`。

## 后续(本计划后)
- **SP2**:千人千面(话题为键共享 + 服务端个人重排)+ 个人进化 + 6→8 系统分(克制/创新)+ 评分框架保密(用户只见翻译版进化面)。见 `specs/2026-07-01-personalization-evolution-design.md`。
