# 设计:真实用户隔离(邮箱验证码账号体系)

> 日期:2026-07-01 · 状态:待评审 · 作者:reposkeeper + Claude
> 上游需求(用户四点)见文末「附:原始需求」。本文是实现级设计,评审通过后进入 writing-plans。

## 1. 背景与目标

现状身份 = **分享 token**(`lnk_xxx`)。内容墙在 `functions/_middleware.js`(有 token 才下发内容);per-user 数据(收藏/关注/已读/请求)已按 token 隔离在 R2,但 **`/feedback`(赞/踩/采用)是全局匿名的**——任何人的反馈都进同一个 `fb/*.json`,并被 `ln-evolve` 吃进去改**全局**提示词,等于「一个人的口味影响所有人看到的新闻」。

把「token 身份」升级为「邮箱账号身份」,达成四个目标:

1. **反馈隔离**:共享同一份新闻底座;每个账户的反馈单独沉淀,**互不影响**。
2. **邮箱验证码登录/退出**:基础账号凭证 + 权限;登录只经邮箱 6 位验证码;码与会话都有过期。
3. **owner 管理用户 + 全动作日志**:owner 可增删/启禁用户;记录每个用户的查看时间、分享情况等所有操作。
4. **夜间模式**:用户自配主题(自动/浅色/深色),跟随账号。

## 2. 非目标(YAGNI)

- ❌ 自助注册(采用 **owner 白名单/邀请**)、密码登录、2FA、第三方 OAuth。
- ❌ **per-user 新闻生成**——新闻底座对所有人是**同一份**(守住「共享底座」,避免爆炸式 scope)。
- ❌ 精确停留时长(先记 view 时间点 + `last_seen`;停留时长以后可选加)。
- ❌ per-user 的新闻**排序个性化**(反馈只做「单独沉淀 + owner 侧可见」;个性化排序留待后续)。

## 3. 身份模型

| 概念 | 定义 |
|---|---|
| **user** | 一个邮箱 = 一个账户。字段:email、name、role、status、theme、时间戳。 |
| **role** | `owner`(站长,唯一或少数)/ `viewer`(普通用户)。 |
| **status** | `invited`(owner 已加白名单、尚未首次登录)/ `active` / `disabled`(被禁用,立即失效)。 |
| **白名单** | = `users` 表里 status ∈ {invited, active} 的邮箱。**只有白名单邮箱能收到验证码**。 |
| **session** | 登录后签发的服务端会话(KV,可吊销),对应 httpOnly cookie `lns`。 |

owner 判定 = **session 里的 role**(不再是静态 token / env)。首个 owner 由一次性 setup 脚本按 `OWNER_EMAIL` 写入 D1。

## 4. 架构总览

```
                         浏览器
                 news.xdzq.org (Pages)
        ┌───────────────────────────────────┐
        │ functions/_middleware.js          │  未登录→登录页;已登录→下发单页
        │   读 cookie lns → KV 查 session    │  绑定:KV(SESSIONS)
        └───────────────┬───────────────────┘
                        │ 凭证 fetch(cookie 同站带上)
                        ▼
             feedback.xdzq.org (API Worker)          share.xdzq.org (不动)
        ┌───────────────────────────────────┐
        │ worker/api-worker.js  路由         │
        │  /auth/*   邮箱码登录/退出/me       │  绑定:KV(SESSIONS)、D1(DB)、
        │  /admin/*  owner 用户管理/活动/反馈 │       secret RESEND_API_KEY
        │  /feedback /favorite /follow ...    │
        │  /activity 前端 beacon 记动作       │
        └──────┬───────────────┬─────────────┘
               │               │
          KV(SESSIONS)      D1(DB)          R2(BUCKET,不动:share 缓存 + tags)
          otp/session/限流   users/activity/feedback/收藏/关注/已读/请求
                            └─→ Resend(发验证码邮件)
```

- **KV 命名空间 `SESSIONS`**:热路径 + 原生 TTL(otp、session、限流)。middleware 每次访问要查,故用 KV。
- **D1 数据库 `DB`**:关系/可查询数据(用户、活动日志、per-user 反馈与收藏等)。owner「按用户查所有动作」= SQL 查询,R2 的 list-scan 做不了。
- **R2 `BUCKET`**:保持现状(分享出图缓存 `share/*`、`config/feedback_tags.json`)。

## 5. 存储设计

### 5.1 KV(`SESSIONS`)

| key | value | TTL |
|---|---|---|
| `otp:<email>` | `{code_hash, exp, attempts}` | 600s(10 分钟) |
| `session:<token>` | `{user_id, email, role}` | 2592000s(30 天,活跃滑动续期) |
| `usess:<user_id>` | `[token, ...]`(会话索引,供吊销/踢人) | 随最长会话 |
| `rl:code:<email>` | 计数 | 60s(每邮箱 1 次/分) |
| `rl:ip:<ip>` | 计数 | 3600s(每 IP N 次/时) |

- `token` = 32 字节随机(`crypto.getRandomValues` → base64url)。
- `code_hash` = SHA-256(code + email + SALT),避免明文码落 KV;校验用哈希比对。

### 5.2 D1(`DB`)—— `worker/schema.sql`

```sql
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT UNIQUE NOT NULL,
  name          TEXT DEFAULT '',
  role          TEXT NOT NULL DEFAULT 'viewer',   -- owner|viewer
  status        TEXT NOT NULL DEFAULT 'invited',  -- invited|active|disabled
  theme         TEXT NOT NULL DEFAULT 'auto',      -- auto|light|dark
  created_at    TEXT NOT NULL,
  last_seen_at  TEXT
);
CREATE TABLE IF NOT EXISTS activity (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id  INTEGER NOT NULL,
  ts       TEXT NOT NULL,
  action   TEXT NOT NULL,     -- request_code|login|logout|view|open|feedback|favorite|follow|read|request|share_link|share_image|theme
  target   TEXT DEFAULT '',   -- item_id / date / 分享对象等
  meta     TEXT DEFAULT ''    -- JSON 补充
);
CREATE INDEX IF NOT EXISTS idx_activity_user_ts ON activity(user_id, ts);

CREATE TABLE IF NOT EXISTS feedback (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id  INTEGER NOT NULL,
  ts       TEXT NOT NULL,
  action   TEXT NOT NULL,     -- up|down|adopt
  item_id  TEXT, date TEXT, title TEXT, tags TEXT, text TEXT
);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id, ts);

CREATE TABLE IF NOT EXISTS favorites (
  user_id INTEGER NOT NULL, item_id TEXT NOT NULL,
  date TEXT, title TEXT, ts TEXT,
  PRIMARY KEY (user_id, item_id)
);
CREATE TABLE IF NOT EXISTS follows (
  user_id INTEGER NOT NULL, item_id TEXT NOT NULL,
  title TEXT, topics TEXT, entities TEXT, ts TEXT,
  PRIMARY KEY (user_id, item_id)
);
CREATE TABLE IF NOT EXISTS reads (
  user_id INTEGER NOT NULL, item_id TEXT NOT NULL, ts TEXT,
  PRIMARY KEY (user_id, item_id)
);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL, ts TEXT, text TEXT, tags TEXT, status TEXT DEFAULT 'new'
);
```

## 6. 认证流程

### 6.1 请求验证码 `POST /auth/request-code {email}`
1. 规范化 email(小写、trim)。
2. 限流:`rl:code:<email>`(1/分)、`rl:ip:<ip>`(N/时)超限 → 429。
3. 查 D1 `users`:email 不在白名单(无记录或 status=disabled)→ **403「该邮箱未被邀请」**。
   > 权衡:私有邀请制小站,明确提示优先于防枚举;后续要防枚举可改为统一 200。
4. 生成 6 位数字码 → 存 KV `otp:<email>`(哈希、TTL 600s、attempts=0)。
5. Resend 发信(标题「Loop News 登录验证码」,正文含码 + 10 分钟有效提示)。
6. 记 activity `login`?否——此处记 `request_code`(带 email,不带码)。返回 200。

### 6.2 校验登录 `POST /auth/verify {email, code}`
1. 取 KV `otp:<email>`;不存在/过期 → 400「码已过期,请重发」。
2. attempts≥5 → 删码 + 400「尝试过多,请重发」。
3. 哈希比对(**恒定时间**):不匹配 → attempts++ 回写 → 400。
4. 匹配:删码(**一次性**)。若 users.status=invited → 置 active。
5. 签发 session:写 KV `session:<token>`(TTL 30d)+ 追加 `usess:<user_id>`。
6. 写 cookie:`lns=<token>; Domain=.xdzq.org; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`。
   同时写**非 httpOnly** 的 `lnrole` / `lnname`(仅供前端即时渲染,真正鉴权仍在服务端)。
7. 更新 `last_seen_at`;记 activity `login`。返回 `{user:{name,role,theme}}`。

### 6.3 会话 / 身份 / 退出
- `GET /me`:凭 cookie 返回 `{email,name,role,theme}` 或 401。
- `POST /me/theme {theme}`:持久化到 users.theme;记 activity `theme`。
- `POST /auth/logout`:删 KV `session:<token>`、从 `usess` 移除、清 cookie(Max-Age=0);记 `logout`。
- **过期语义**:码 10 分钟且一次性;会话 30 天,任一已登录请求滑动续期(重写 TTL);限流全覆盖。

### 6.4 跨子域 cookie 与 CORS
- 站点 news.xdzq.org 与 API feedback.xdzq.org 同注册域 `xdzq.org` → **same-site**。cookie `Domain=.xdzq.org` 使 middleware(news 子域)也能读到 `lns`。
- 前端 `fetch(..., {credentials:'include'})`;API 响应 `Access-Control-Allow-Origin: https://news.xdzq.org` + `Access-Control-Allow-Credentials: true`(**不能再用 `*`**)。允许来源可配 env `SITE_ORIGIN`。

## 7. 访问门槛(`functions/_middleware.js` 改造)

- 给 Pages 项目**绑定 KV `SESSIONS`**。
- 读 `lns` cookie → KV 查 session:
  - 命中 → 放行 `next()`,并回写 `lnrole` / `lnname`(供前端即时 UI)。
  - 未命中 → 返回**登录页**(HTTP 200 的门页,内容不下发)。登录页两步:① 邮箱 → 「发送验证码」;② 输入 6 位码 → 「登录」。两步都 `fetch` 打 API 子域(`FEEDBACK_API`/`SITE` env 已有类似约定)。
- 删除旧的 `?token=`/`SHARE_TOKENS`/`/validate` token 门逻辑(见 §12 迁移)。

## 8. Per-user 隔离 + ln-evolve 语义

### 8.1 隔离
- `/feedback`(POST)写 **D1 feedback(user_id=当前用户)**;不再进全局 `fb/*.json`。
- `favorite/follow/read/request` 从「按 `<token>` 存 R2」改为「按 `user_id` 存 D1」,读同理。
- 所有 per-user 端点**去掉请求体里的 token 参数**,一律从 session 推导用户(凭证 cookie)。

### 8.2 ln-evolve:只吃 owner 反馈驱动全局进化(**核心语义**)
- 「以目前的基础作为所有人的新闻基础」⇒ 共享底座由 **owner 一人策展**。
- `ln-evolve` 拉反馈时**只取 role=owner 的反馈**(`GET /feedback` 或 D1 查询加 `WHERE role='owner'`)来改全局 `prompts/*.md`、`config/*.yaml`。
- 其他用户的反馈**只沉淀在各自账户**,驱动他们自己的收藏/关注视图,**绝不改动别人所见**。
- 旧全局 `fb/*.json` 作为 legacy 归入 owner,ln-evolve 仍可读,平滑过渡。
- **落地**:改 `.claude/skills/ln-evolve/SKILL.md`(或其引用的 prompt)+ `RUNBOOK.md`/`AGENTS.md`/`CLAUDE.md` 说明此语义 + `prompts/CHANGELOG.md` 留痕。

## 9. Owner 管理 + 活动日志

### 9.1 owner-only API(session.role=owner 才通过,否则 403)
| 端点 | 作用 |
|---|---|
| `GET /admin/users` | 用户列表 + last_seen + 各类计数(view/feedback/share) |
| `POST /admin/users {email,name,role}` | 邀请/新增(status=invited) |
| `PATCH /admin/users/:id {name?,role?,status?}` | 改名 / 升降 owner / 启用禁用 |
| `DELETE /admin/users/:id` | 删除用户(连带其 per-user 数据,可选保留活动日志) |
| `GET /admin/activity?user_id=&limit=&before=` | 某用户(或全部)活动流,分页 |
| `GET /admin/feedback?user_id=` | 某用户反馈(owner 侧可见) |

- **禁用/删除即时生效**:置 disabled 或删除时,读 `usess:<user_id>` 逐个删 KV session → 该用户下次访问即被登录页拦下。

### 9.2 活动事件
记录到 D1 `activity`:`request_code / login / logout / view(哪天/哪块) / open(哪条) / feedback / favorite / follow / read / request / share_link / share_image / theme`。
- 服务端动作(反馈/收藏/…)在其端点内顺带记。
- **纯前端动作**(浏览、打开某条、点分享)由前端发**带凭证 beacon** `POST /activity {action,target,meta}`(session 校验;view 做去抖,如按 hash 路由切换记一次)。
- 「查看时间」= view 事件时间点 + `last_seen_at`;「分享情况」= share_link/share_image 事件。

### 9.3 Owner UI(单页内)
复用已有 `is-owner` body class,把现在的「🔗 生成分享链接」弹窗换成**用户管理面板**:
- 用户表(邮箱 / 名 / 角色 / 状态 / 最近访问 / 计数);行内启禁用、改角色。
- 邀请表单(输入邮箱+名 → `POST /admin/users`)。
- 点某用户 → 抽屉展示其活动流(`/admin/activity?user_id=`)。

## 10. 夜间模式(用户自配)

- **CSS 变量化**:`web/assets/style.css`(与 `page.html` 内联样式)现有硬编码色(`#FAFAF8`、`#17171A`、`#1F5C57`、`#6B6B70`、`#E7E6E1` 等)抽到 `:root` 变量;新增 `:root[data-theme="dark"]` 深色板(纸感换成低亮暖灰底、正文柔白、抽印引文/分级配色相应压暗)。
- **三档**:`auto`(跟随 `prefers-color-scheme`)/ `light` / `dark`。`auto` 用 `@media (prefers-color-scheme: dark)` 落到深色变量。
- **无闪白**:`<head>` 内联脚本先于 CSS 读 `localStorage.ln-theme`,设 `document.documentElement.dataset.theme`。
- **持久化**:localStorage 即时 + 登录后 `POST /me/theme` 同步到账户;`/me` 返回 theme,首次登录用它 hydrate localStorage → **跟随账号跨设备**。
- **入口**:头部「设置」菜单(自动/浅色/深色三选一 + 退出登录)。

## 11. 前端改造(`web/templates/page.html` / `style.css` / `compile.py`)

- 身份:去掉 `ck("lnt")` token 逻辑;per-user 请求改 `credentials:'include'`,身份由 session 决定。`is-owner` 由 `lnrole` cookie(即时)+ `/me`(确认)决定。保留 `lnname` 问候。
- 新增:设置/退出菜单、主题切换、owner 用户面板、活动抽屉。
- 分享按钮点选时发 `POST /activity {action:'share_link'|'share_image'}`。
- `compile.py`:注入主题变量与无闪白内联脚本、API base;移除 token 相关模板分支。改动小、仍是确定性脚本(不含 LLM)。

## 12. Worker 拓扑与模块拆分

- 把 `worker/feedback-worker.js` 升级为主 API worker。**保持路由 feedback.xdzq.org 与 worker 名不变**(避免动 `wrangler.toml` 路由;文件可留名或改名——若改名,同步 CLAUDE.md/RUNBOOK/AGENTS 中的 `worker/feedback-worker.js` 引用,否则 `check.sh` 引用完整性会失败)。
- 拆模块(`worker/lib/` 子目录,`check.sh` 不扫子目录,安全):
  - `lib/store.js`:D1/KV 封装(参数化查询、JSON 序列化)。
  - `lib/session.js`:签发/校验/吊销 session,cookie 读写。
  - `lib/auth.js`:request-code / verify / logout / me;Resend 发信。
  - `lib/admin.js`:/admin/* 用户与活动。
  - `lib/feedback.js`:per-user 反馈/收藏/关注/已读/请求 + /activity。
- share worker 不动。

## 13. 部署与一次性设置

- **Resend**:注册 → 在 Cloudflare 给 xdzq.org 加 DNS(SPF/DKIM)验证发件域 → 得 API Key。`wrangler secret put RESEND_API_KEY`。发件人如 `login@xdzq.org`。
- **D1**:`wrangler d1 create loop-news-db` → 把 `database_id` 填进 `wrangler.toml` `[[d1_databases]]`(binding `DB`)→ `wrangler d1 execute loop-news-db --file worker/schema.sql`。
- **KV**:`wrangler kv namespace create SESSIONS` → id 填进 `wrangler.toml` `[[kv_namespaces]]`;**同一命名空间也绑定到 Pages 项目**(middleware 用)。
- **owner 引导**:`scripts/setup-auth.sh`:建 KV/D1、apply schema、按 `OWNER_EMAIL` `INSERT` 一条 role=owner/status=active。
- `scripts/deploy-cloudflare.sh` 增:部署前 `wrangler d1 execute --file schema.sql`(幂等 `IF NOT EXISTS`)。
- `wrangler.toml` 增:`[[kv_namespaces]]`、`[[d1_databases]]`;`CLOUDFLARE.md` 补 Resend/D1/KV/secret 全流程。

## 14. 本地开发

- `server/feedback_server.py`(零依赖)加 **dev 模式**:`LN_DEV_OWNER=<email>` 时自动以该 owner 身份注入,跳过真实发邮件(码打印到控制台或直接放行),用本地文件/内存模拟隔离,便于改前端与主题。文档注明「本地不发真邮件」。

## 15. 迁移与向后兼容

- 系统仅约两天数据。**旧 `lnk_` 分享 token 退役**;旧分享链接 `?token=` 将命中登录页 → owner 用**邮箱重新邀请**对应的人。
- 旧 R2 per-user(`fav/<tok>/`…)与全局 `fb/*.json`:owner 自己的可选一次性迁到其 user_id,否则从新开始;`fb/*.json` 归 owner 供 ln-evolve 继续读。
- `.gitignore` 已忽略 `config/share_tokens.json`;新体系不再需要它,文档标注废弃(文件可留)。

## 16. 安全考量

- OTP:6 位、哈希存、TTL 10 分钟、一次性、尝试≤5、恒定时间比对、按邮箱+IP 限流。
- session:32B 随机、httpOnly+Secure+SameSite=Lax、服务端可吊销;`Domain=.xdzq.org` 精确到本注册域。
- CORS 收紧为具体来源 + 允许凭证(不再 `*`)。
- owner 鉴权靠 session.role(D1 真源),非可伪造的前端 cookie;`lnrole` 仅 UI 提示。
- 禁用/删除用户即时踢下线(清 KV session)。
- 输入长度/类型统一收敛(沿用现有 `.slice()` 风格);email 正则校验。

## 17. 测试策略

- **Worker 单测**(Vitest + `@cloudflare/vitest-pool-workers` 或 miniflare):request-code 限流/白名单、verify 过期/超次/一次性、session 续期/吊销、owner 鉴权 403、per-user 隔离(A 的反馈不入 B)。
- **端到端手测**(用 `browse`/`gstack` skill 或 Chrome MCP):登录两步流、退出、主题切换无闪白+跨设备、owner 面板增删/禁用即时生效、活动日志出现。
- `bash scripts/check.sh` 必过(编译自洽 + 引用完整 + 落地留痕)。

## 18. 文档与落地契约

- 更新:`CLOUDFLARE.md`(Resend/D1/KV)、`RUNBOOK.md`/`AGENTS.md`/`CLAUDE.md`(身份模型、ln-evolve 只吃 owner 反馈、访问门改造)、`README.md`(账号体系简述)。
- `.claude/skills/ln-evolve/SKILL.md` + 其 prompt:反馈来源限定 owner。
- `prompts/CHANGELOG.md`:记本次结构升级。
- 每次提交过 `scripts/check.sh`(pre-commit 强制)。**改 `worker/feedback-worker.js` 文件名务必同步文档引用**。

## 19. 实施顺序(细化交给 writing-plans)

1. 存储与骨架:`wrangler.toml`(KV/D1/secret)、`worker/schema.sql`、`lib/store.js`、`scripts/setup-auth.sh`。
2. 认证:`lib/session.js`、`lib/auth.js`(含 Resend)、`/me`;`_middleware.js` 换 session 门 + 登录页。
3. 隔离:`lib/feedback.js` 反馈/收藏/关注/已读/请求迁 D1 + `/activity`;前端去 token 化。
4. owner:`lib/admin.js` + 单页用户面板/活动抽屉;ln-evolve 语义改造 + 文档。
5. 夜间模式:CSS 变量化 + 深色板 + 切换 + 无闪白 + 账户同步。
6. 部署/文档/测试:deploy 脚本、CLOUDFLARE.md、单测、端到端、check.sh。

## 20. 已决决策

- 存储:**D1 主库 + KV 热路径 + R2 不动**。
- 注册:**owner 白名单/邀请**;登录**必需**(替代 token 墙)。
- 发信:**Resend**。
- ln-evolve:**只吃 owner 反馈**驱动全局进化;他人反馈仅个人沉淀。
- 新闻底座:**全员同一份**。

---

### 附:原始需求
1. 以目前的基础作为所有人的新闻基础;各账户反馈单独沉淀,互不影响。
2. 登录/退出 + 基础凭证与权限;登录仅邮箱验证码(点击登录→发码→输入→登录);考虑过期。
3. owner 管理用户;记录每个用户查看时间、分享情况等所有操作。
4. 夜间模式主题,用户自配。
