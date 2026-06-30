---
name: ln-publish
description: Loop News 发布步骤。运行 scripts/deploy-cloudflare.sh,把编译好的 docs/ 部署到 Cloudflare Pages(站点)+ Worker(反馈 API)+ R2(常用词)。当用户说"发布"、"上线"、"publish"、"ln-publish"、"部署"时使用。
---

# ln-publish · 发布步骤(Cloudflare)

把 `docs/` 部署到 **Cloudflare**。托管已从 GitHub Pages 迁出,**不再依赖 GitHub Pages**;GitHub 仅作源码/历史。确定性脚本。

## 前提(一次性)
- `npx wrangler login` 已登录;R2 桶 `loop-news` 与 Pages 项目 `loop-news` 已建(见 [CLOUDFLARE.md](../../../CLOUDFLARE.md))。
- `config/loop.yaml` 的 `feedback.api_url` 指向 Worker(`https://feedback.xdzq.org`);`site.url` = `https://news.xdzq.org`。

## 运行
```bash
bash scripts/deploy-cloudflare.sh
```
它做:`python3 web/compile.py` → `wrangler pages deploy docs`(站点)→ 同步 `config/feedback_tags.json` 到 R2 → `wrangler deploy`(反馈 Worker)。

## 源码备份(与发布解耦,可选)
`bash scripts/publish.sh "<msg>"` 把改动 commit + push 到 GitHub —— **仅留源码/历史,不用于托管**。

## 验证
浏览器开 `site.url`(`https://news.xdzq.org`)确认新一期已上线;`curl https://feedback.xdzq.org/health` 确认反馈 API 正常。

## 纪律
- 发布是公开操作;早班默认人工确认(见 ln-daily 的发布门)。
- 不提交密钥/token;`.gitignore` 已排除敏感文件与 `vendor/`。
