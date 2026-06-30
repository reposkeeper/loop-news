# AGENTS.md

面向 **Codex 及其他 agent**。本仓库的权威操作手册是 **[RUNBOOK.md](RUNBOOK.md)**——请照它执行,**不要假设任何 Claude 专有工具或 skill**。

## 从哪读起
- 目标与架构:[README.md](README.md)
- 完整流程 + 能力映射 + 数据 schema:[RUNBOOK.md](RUNBOOK.md)
- 采集/分析策略(可编辑、会被自进化修改):`prompts/*.md`
- 配置:`config/*.yaml`
- 确定性脚本:`web/compile.py`(编译单页)、`scripts/publish.sh`(发布)、`scripts/feedback.sh`(读 `data/feedback.jsonl` 反馈)、`server/feedback_server.py`(网页弹窗反馈服务,零依赖)

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
