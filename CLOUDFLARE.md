# 部署到 Cloudflare(Pages 站点 + Worker 反馈 API + R2 桶)

架构:
- **Cloudflare Pages** 托管静态站(`docs/`)——对标 GitHub Pages,HTTPS + 自定义域 + 自动 index/路由。
- **Cloudflare Worker**(`worker/feedback-worker.js`)跑 API:账号体系(`/auth/*` `/me`)+ 反馈/收藏/关注/已读/请求/活动(`/feedback` `/favorite(s)` `/follow(s)` `/read(s)` `/request(s)` `/activity`)。
- **D1 数据库**(`loop-news-db`,binding `DB`,见 `worker/schema.sql`)存用户/活动日志/反馈/收藏/关注/已读/请求,**全部按 `user_id` 隔离**。
- **KV 命名空间**(`SESSIONS`)存验证码(otp)与会话(session),`functions/_middleware.js` 与 Worker 共用。
- **R2 桶** 存分享出图缓存与常用词(`config/feedback_tags.json`)。
- **Resend** 发登录验证码邮件。
- 站点、API 都在**你的域名**子域下、同源 HTTPS,手机/任意设备可用。

> 仓库继续留 GitHub(源码/管线/历史);只把**托管**搬到 Cloudflare。

## 前置(只需一次)
1. 有 Cloudflare 账号,且**你的域名已托管在该账号**(Cloudflare 控制台能看到这个 zone)。
2. 登录 wrangler:
   ```bash
   npx wrangler login
   npx wrangler whoami   # 确认账号
   ```

## 一次性创建资源
```bash
# 1) 建 R2 桶(名字要和 wrangler.toml 的 bucket_name 一致,默认 loop-news)
npx wrangler r2 bucket create loop-news

# 2) 建 Pages 项目(直接上传式,无需构建)
npx wrangler pages project create loop-news --production-branch main
```

## 接你的自定义域(二选一)
- **站点(Pages)**:控制台 → Pages → loop-news → Custom domains → 添加,例如 `news.你的域名`。
- **反馈 API(Worker)**:编辑 `wrangler.toml`,取消注释 `routes` 并填子域,例如:
  ```toml
  routes = [{ pattern = "feedback.你的域名", custom_domain = true }]
  ```
  (不接自定义域也行,Worker 默认有 `https://loop-news-feedback.<你的子域>.workers.dev`。)

## 把前端指向反馈 API
编辑 `config/loop.yaml`:
```yaml
feedback:
  api_url: "https://feedback.你的域名"   # 或上面的 *.workers.dev 地址
```
> Pages 是 HTTPS,API 也必须 HTTPS(Worker 自带),不会有混合内容问题。

## 部署(日常一行)
```bash
bash scripts/deploy-cloudflare.sh
```
它会:编译 `docs/` → `wrangler pages deploy docs` → 把 `feedback_tags.json` 同步进 R2 → 应用 D1 schema(幂等)→ `wrangler deploy`(Worker,含账号体系 `/auth` `/me`)→ 部署分享出图 Worker。
> 也可改用 **Pages 连 GitHub 仓库**(Build command 留空、Output 目录 `docs`),这样 `git push` 即自动发站;Worker 仍用 `wrangler deploy`。

## 账号体系(邮箱验证码)

登录身份从"分享 token"升级为"邮箱账号"(SP1-Core)。只有白名单邮箱(D1 `users` 表 status ∈ invited/active)能收到验证码登录;登录后按 `user_id` 隔离每个人的反馈/收藏/关注/已读/请求;全站行为记 `activity`。**一次性设置**(先后顺序很重要):

```bash
# 1) Resend:注册 → 在 Cloudflare 给你的域名(如 xdzq.org)加 DNS 记录(SPF/DKIM)验证发件域 → 拿到 API Key
npx wrangler secret put RESEND_API_KEY

# 2) 建 D1 数据库 + KV 命名空间,把返回的真实 id 填进 wrangler.toml(替换 PLACEHOLDER_D1_ID / PLACEHOLDER_KV_ID)
npx wrangler d1 create loop-news-db
npx wrangler kv namespace create SESSIONS

# 3) 应用 schema(远端,幂等)
npx wrangler d1 execute loop-news-db --remote --file worker/schema.sql

# 4) 播种 owner 账号(会再次 apply schema,幂等,不重复)
OWNER_EMAIL=you@example.com bash scripts/setup-auth.sh
```

- **Pages 项目还要在控制台绑定 KV**:Pages → loop-news → Settings → Functions → KV namespace bindings,把 `SESSIONS` 绑到同一个命名空间(`functions/_middleware.js` 用它查会话,`wrangler.toml` 里的绑定只对 Worker 生效,对 Pages 不生效)。
- 日常部署 `bash scripts/deploy-cloudflare.sh` 已包含"应用 D1 schema"这一步(幂等,重复跑无副作用),不需要每次手动执行。
- 验收:无痕访问站点 → 两步登录页(邮箱 → 验证码);用 owner 邮箱登录 → 看到内容;退出 → 回登录页。

**旧的"访问令牌门"(`scripts/share-token.sh` + `SHARE_TOKENS` + `?token=`)已废弃**,`functions/_middleware.js` 不再校验它;不必再生成分享 token。

- **owner 用户管理**(SP1-UI):owner 登录后页面内有「👥 用户管理」面板——列出全部账号、邀请新邮箱、启用/禁用/改角色、删除账号,并可查看每人的活动记录;禁用即吊销该用户全部会话,删除级联清空其反馈/收藏/关注/已读/请求/活动数据,且都禁止对自己操作(防锁死)。owner-only(`role=owner` 之外一律 403)。
- **夜间模式**:任何用户可在页头切换 自动/浅色/深色 三档主题,选择会同步进账号(跨设备一致),无闪屏。

## ln-evolve 读反馈
反馈存 D1(按 `user_id` 隔离,见 `worker/schema.sql` 的 `feedback` 表),**只有 `role=owner` 的反馈驱动全局 prompts/config 进化**(普通用户反馈是个人数据,属 SP2 千人千面,尚未消费)。
- **本地/owner 拉取**:`bash scripts/feedback.sh`(owner 本机已 `wrangler login`,直接 `wrangler d1 execute` 查询,无需带 session cookie)。
- **等价的 HTTP 接口**(供前端/以后 admin 面板用):`GET https://feedback.你的域名/feedback?role=owner`(需带登录 session cookie)。

## 回退
不想用 Cloudflare 时,`scripts/publish.sh` 仍可把 `docs/` 推回 GitHub Pages;本地仍可 `python3 server/feedback_server.py`(注意:本地反馈服务器是账号体系之前的旧路径,已不是当前反馈主存储)。
