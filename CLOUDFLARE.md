# 部署到 Cloudflare(Pages 站点 + Worker 反馈 API + R2 桶)

架构:
- **Cloudflare Pages** 托管静态站(`docs/`)——对标 GitHub Pages,HTTPS + 自定义域 + 自动 index/路由。
- **Cloudflare Worker**(`worker/feedback-worker.js`)跑反馈 API(`/tags` `/feedback`)。
- **R2 桶** 存反馈(`fb/*.json`)与常用词(`config/feedback_tags.json`)。
- 站点与反馈都在**你的域名**子域下、同源 HTTPS,手机/任意设备可用。

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
它会:编译 `docs/` → `wrangler pages deploy docs` → 把 `feedback_tags.json` 同步进 R2 → `wrangler deploy`(Worker)。
> 也可改用 **Pages 连 GitHub 仓库**(Build command 留空、Output 目录 `docs`),这样 `git push` 即自动发站;Worker 仍用 `wrangler deploy`。

## ln-evolve 读反馈
- 本地服务器模式:读 `data/feedback.jsonl`。
- Cloudflare 模式:从 Worker 拉,`curl https://feedback.你的域名/feedback`(`scripts/feedback.sh` 可据此改造)。

## 回退
不想用 Cloudflare 时,`scripts/publish.sh` 仍可把 `docs/` 推回 GitHub Pages;本地仍可 `python3 server/feedback_server.py`。
