# AGENTS.md

面向 **Codex 及其他 agent**。本仓库的权威操作手册是 **[RUNBOOK.md](RUNBOOK.md)**——请照它执行,**不要假设任何 Claude 专有工具或 skill**。

## 从哪读起
- **进化北极星(目标函数)**:[GOALS.md](GOALS.md) —— 最大化「非显然洞察」(信息优势);硬约束=不臆造、回链证据、宁缺毋滥
- 目标与架构:[README.md](README.md)
- 完整流程 + 能力映射 + 数据 schema:[RUNBOOK.md](RUNBOOK.md)
- 采集/分析策略(可编辑、会被自进化修改):`prompts/*.md`
- 配置:`config/*.yaml`
- 确定性脚本:`web/compile.py`(编译单页)、`scripts/publish.sh`(发布)、`scripts/feedback.sh`(读 D1 owner 反馈,供 ln-evolve)、`server/feedback_server.py`(本地零依赖反馈服务,账号体系之前的旧路径)、`scripts/deploy-cloudflare.sh`(部署 Cloudflare,含 D1 schema 迁移)、`scripts/setup-auth.sh`(一次性:apply D1 schema + 播种 owner 账号)
- 网页能力:每条新闻可带 `charts`(synthesize 产规格、compile 渲染内联 SVG;只对可核实数字、标来源);站点**登录门**(邮箱验证码 → 会话,`functions/_middleware.js` 服务端查 KV `SESSIONS` 校验,非整站私有,已替代旧的 token 分享门);每个账号的反馈/收藏/关注/已读/请求按 `user_id` 隔离存 D1,`ln-evolve` 只消化 `role=owner` 的反馈驱动全局进化。托管/部署/账号体系详见 [CLOUDFLARE.md](CLOUDFLARE.md)

## 手动跑一轮
```
collect → synthesize → python3 web/compile.py → 预览 → bash scripts/publish.sh → evolve
```
其中 collect / synthesize / evolve 需要 LLM 判断(按 RUNBOOK 的步骤 + `prompts/` 执行);compile / publish 是纯脚本。

## 环境
`python3`(仅标准库)、`git`、`gh`;网页搜索/抓取能力;X 访问见下。时区 Asia/Shanghai。

## MCP(X / Twitter 名人原声)
本仓库已配 X MCP(Infatoshi x-mcp)。首次使用:
1. `bash scripts/setup-mcp.sh` —— 克隆并构建到 `vendor/x-mcp`(不入库)。
2. `cp .env.example .env`,填 3 个真实 key(API Key/Secret + Bearer;读取够用),Access Token/Secret 留占位(server 启动要求非空,但读取不用);启动前 `set -a; source .env; set +a`。
3. Claude Code 读 `.mcp.json` 自动加载名为 `x` 的 server;**Codex 等请在自己的 MCP 配置里指向** `node vendor/x-mcp/dist/index.js`(同样 5 个 env)。
读工具:`search_tweets` / `get_timeline` / `get_user` / `get_tweet`。未配凭证则退化为网页搜索还原引用。

另已配远程 MCP **`x-docs`**(`https://docs.x.com/mcp`,X 官方文档搜索,只读、**免凭证**,远程 HTTP)。查/调 X API 时**优先用它**,防止读到过时文档。Claude Code 自动从 `.mcp.json` 加载;Codex 等把它作为远程 HTTP MCP 加进自己的配置(URL 同上)。

## 红线
- 不臆造新闻/引文/链接;深度类保留原文;结论必须分级 + 证据回链。
- **发布是公开操作**:默认先本地预览、人工确认后再 `publish`。
- 不自动改数据 schema(属人工大版本)。
- **变更落地契约**:任何进化/功能改动必须落进【代码】或【skill/提示词/文档】,不留在对话;提交前自动跑 `bash scripts/check.sh`(git pre-commit 已强制,不通过不提交),进化须记 `prompts/CHANGELOG.md`。详见 RUNBOOK「变更落地契约」。
