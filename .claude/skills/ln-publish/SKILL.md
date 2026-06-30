---
name: ln-publish
description: Loop News 发布步骤。运行 scripts/publish.sh,把编译好的 docs/ 提交并 push 到 GitHub,GitHub Pages 自动上线。当用户说"发布"、"上线"、"publish"、"ln-publish"、"推到 pages"时使用。
---

# ln-publish · 发布步骤

把 `docs/` 的最新网页发布到 GitHub Pages。确定性脚本。

## 前提(一次性)
- 仓库已 `git init` 并关联 GitHub 远程 `loop-news`。
- GitHub 仓库 Settings → Pages 设为 **从 `main` 分支 `/docs` 目录** 托管。

## 运行
```bash
bash scripts/publish.sh "<commit message>"   # 默认 message: "publish: <date>"
```

## 它做什么
1. `git add docs/ data/ state/ prompts/ config/`(数据与产物都入库,便于回溯与进化)。
2. `git commit -m "<message>"`(无改动则跳过)。
3. `git push origin main`。
4. 打印上线地址 `config/loop.yaml` 的 `site.url`。

## 验证
push 后等 ~1 分钟,浏览器访问站点 URL 确认新一期已上线。

## 纪律
- 不强推(no force-push);冲突先 `git pull --rebase`。
- 不提交密钥/token;`.gitignore` 已排除敏感文件。
