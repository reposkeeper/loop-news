# 调度方案(Phase 4)

Loop News 的循环靠**定时云 agent(routines)**驱动。两条任务,时区 Asia/Shanghai。
> 设计默认:早班**到编译为止**,**发布留人工确认**(对应当前"暂不自动发布"的选择)。
> 想全自动时,把早班 prompt 末尾的 `ln-publish` 一步打开即可。

## 早班 · 每天 07:00(汇总前一天 + 出刊)
Routine prompt:
```
在 /Users/reposkeeper/devops/loop-news 执行 Loop News 早班:
1. /ln-collect am          # 采集今天上午批次
2. /ln-synthesize 昨天      # 汇总前一天,产出 data/analysis/<昨天>.json
3. python3 web/compile.py  # 编译昨天那一期 → docs/
4. /ln-evolve              # 自评并改进 prompts/config,写 CHANGELOG
# 5.(可选,全自动时打开)bash scripts/publish.sh  # 发布上线
完成后把当期 summary 与 evolve 改动贴出来等我确认发布。
```
建议 cron:`3 7 * * *`(避开整点)。

## 晚班 · 每天 19:00(仅采集)
Routine prompt:
```
在 /Users/reposkeeper/devops/loop-news 执行 Loop News 晚班:只跑 /ln-collect pm,把今天的新闻补进 data/corpus/<今天>.json。
```
建议 cron:`7 19 * * *`。

## 如何启用
- 在 Claude Code 里用 `/schedule` skill 创建上述两条 routine(durable)。
- 或让我代为创建:说"帮我把早晚两条调度排上"。

## 注意事项
- **X MCP 在无头/定时环境可能不可用**:云端 routine 跑采集时,X 名人原声会自动退到 WebSearch 还原引用(见 `prompts/collect.deep.md`)。要在云端也直采 X,需确保该 MCP 在无头会话可用,或配 `config/secrets.yaml` 的 API key。
- 早班依赖前一天已有 `data/corpus/<昨天>.json`(由前一天早晚两次采集累积)。首次启用前可先手动跑一两天攒数据。
- 发布需仓库 Pages 已开启(`main` 分支 `/docs`,已配置)。
