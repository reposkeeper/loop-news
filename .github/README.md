# CI/CD · 分支 ↔ 环境

GitHub Actions 调用仓库现有部署脚本,把**分支**映射到 Cloudflare **环境**。一套机制同时管 Pages + 两个 Worker。

## 分支流

```
feature/* ──PR──► gray ──PR──► release ──PR──► main
                   │             │
                   ▼             ▼
              灰度环境        生产环境
          gray-*.xdzq.org   news.xdzq.org
          (共享 KV/D1/R2)    (deploy-cloudflare.sh)
          (deploy-gray.sh)
```

- **`gray`** push → `.github/workflows/gray.yml` → `scripts/deploy-gray.sh`(环境 `gray`)。灰度与生产**共享** KV/D1/R2/cookie,用真实账号在候选代码上验证(见 [GRAY.md](../GRAY.md))。
- **`release`** push → `.github/workflows/release.yml` → `scripts/deploy-cloudflare.sh`(环境 `release`,带生产审批)。
- **`main`** = 稳定主干,**只经 PR 从 `release` 合入**(受保护:需 PR + 通过 CI)。
- 所有 PR/主要分支 push → `.github/workflows/ci.yml`:vitest 单测 + `scripts/check.sh` 落地自检。

## 必需的 GitHub 配置(一次性)

**Environments**(Settings → Environments):`gray`、`release`。
- 每个环境的 secret:`CLOUDFLARE_API_TOKEN`(Cloudflare API Token,权限见下)。可选 `CLOUDFLARE_ACCOUNT_ID`(多账号时)。
- `release` 建议加 **Required reviewers**(生产上线人工审批)+ Deployment branch policy 限定 `release`。
- `gray` 的 Deployment branch policy 限定 `gray`。

**Cloudflare API Token** 权限:Pages Edit · Workers Scripts Edit · D1 Edit · Workers KV Edit · Workers R2 Edit · Account Settings Read · Zone(xdzq.org)Workers Routes Edit + DNS Edit。

## Cloudflare 侧一次性 provision(控制台/CLI,CI 不代做)
见 [GRAY.md](../GRAY.md) §一次性 provision 与 [CLOUDFLARE.md](../CLOUDFLARE.md):
- 建 Pages 项目 `loop-news`(生产)、`loop-news-gray`(灰度),各绑**共享** KV `SESSIONS`、设 `SITE_API`、加 custom domain。
- 灰度 Worker secret:`npx wrangler secret put RESEND_API_KEY --env gray`。
- 顶层/`[env.gray]` 的 D1/KV/R2 id 已填真实值(共享同一批资源)。
