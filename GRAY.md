# 灰度环境(Canary · gray-*)

一套与生产**平行的代码部署**,挂在 `gray-` 前缀域名下,用来在**真实账号/数据**上验证候选代码,并为「按客户灰度」打底。

## 模型:同一后端,另一套代码

**共享(身份 + 数据都共享)** —— 客户被路由到灰度也无缝保持登录、看到自己真实数据:
- 同一个会话 cookie `lns`(作用域 `Domain=.xdzq.org`,不加命名空间)。
- 同一个 KV `SESSIONS`(会话)、同一个 D1 `loop-news-db`(用户 + 反馈/收藏/关注/已读/请求 + 活动)、同一个 R2 桶。
- 因此**灰度无任何认证/cookie 代码改动**——它只是绑定了同一批资源的另一套 Worker/Pages。

**不同(灰度特有)**:
- 域名:`gray-news.xdzq.org`(站点 Pages)、`gray-feedback.xdzq.org`(API Worker)、`gray-share.xdzq.org`(分享出图 Worker)。
- 跑的是**候选代码**(你要发布前先灰度验证的版本)。
- CORS:灰度反馈 Worker 的 `SITE_ORIGIN=https://gray-news.xdzq.org`(只认灰度站源)。
- 前端 API 基址:灰度构建把页面里的 `FEEDBACK_API` 指向 `gray-feedback`(见 `web/compile.py` 的 `LN_FEEDBACK_API` 覆盖)。

> ⚠️ **真·灰度=共享生产数据**:灰度的候选代码直接读写生产 D1。适合**非破坏性**变更;涉及数据结构的改动要**向后兼容**(灰度与生产同时在读写同一份数据)。

## 实现要点(已在代码/配置里)
- `wrangler.toml` 的 `[env.gray]`:worker 名 `loop-news-feedback-gray`、路由 `gray-feedback.xdzq.org`、**重声明**与顶层相同 id 的 KV/D1/R2(wrangler 环境不继承顶层绑定)、`SITE_ORIGIN=gray-news`。
- `wrangler.share.toml` 的 `[env.gray]`:`loop-news-share-gray` @ `gray-share.xdzq.org`。
- `web/compile.py`:`LN_FEEDBACK_API` / `LN_SHARE_API` 环境变量覆盖前端 API 基址(未设=生产)。
- `worker/schema.sql`:`users.channel`(`stable|gray`)列 —— 现未消费,是**未来「按客户灰度」路由**的铺垫。
- `scripts/deploy-gray.sh`:一键部署灰度(构建到 `build/gray/` → Pages → 两个 Worker)。

## 一次性 provision(需你的 Cloudflare 账号,脚本不代跑)
前提:生产账号体系已 provision(D1/KV 建好、真实 id 已填进 `wrangler.toml` 顶层;见 [CLOUDFLARE.md](CLOUDFLARE.md))。灰度**复用**这些资源。
1. 把 `[env.gray]` 里 KV/D1 的 `PLACEHOLDER_*` 改成与顶层**相同**的真实 id(共享)。
2. 建灰度 Pages 项目:`npx wrangler pages project create loop-news-gray --production-branch main`。
3. 控制台 → Pages → `loop-news-gray` → Settings:
   - **Functions → KV 绑定**:变量名 `SESSIONS` → 选**与生产同一个**命名空间(共享会话,关键)。
   - **环境变量**:`SITE_API = https://gray-feedback.xdzq.org`(登录页 API 基址)。
   - **Custom domains**:加 `gray-news.xdzq.org`。
4. 灰度 Worker 密钥:`npx wrangler secret put RESEND_API_KEY --env gray`(灰度发真验证码)。
5. 自定义域:`gray-feedback.xdzq.org` / `gray-share.xdzq.org` 会随 `wrangler deploy --env gray` 自动建 custom_domain 路由(xdzq.org 已托管在本账号)。

## 日常部署灰度
```bash
bash scripts/deploy-gray.sh
```
它:构建灰度站(API 指向 gray-*)→ `build/gray/` → 部署到 `loop-news-gray` Pages → `wrangler deploy --env gray`(反馈 Worker)→ `wrangler deploy -c wrangler.share.toml --env gray`(分享 Worker)。**不动生产**(生产仍走 `scripts/deploy-cloudflare.sh`)。

## 验证灰度
1. 无痕访问 `https://gray-news.xdzq.org` → 登录页。
2. 用一个**生产已存在**的账号邮箱收码登录 → 应看到内容,且是该账号的**真实数据**(证明共享后端)。
3. 在生产 `news.xdzq.org` 已登录的浏览器直接开 `gray-news.xdzq.org` → **无需重新登录**(证明共享 cookie/会话)。
4. 反馈一条 → 回生产看,应能看到同一条(共享数据)。

## 未来:按客户灰度(路由层)
`users.channel` 列已就位。将来加一个路由层(如生产站中间件或边缘规则):读登录用户的 `channel`,`gray` 的客户重定向/服务到 `gray-news`。届时把选定客户置 `channel='gray'` 即可精准灰度,无需他们改变操作。
