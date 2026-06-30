# CLAUDE.md · Loop News 运行约定

给在本仓库工作的 Claude 的操作说明。本项目是一个自循环新闻情报系统,详见 [README.md](README.md)。

> **跨 agent 的权威流程见 [RUNBOOK.md](RUNBOOK.md)**(Codex 等见 [AGENTS.md](AGENTS.md))。本文件是 Claude 视角的补充约定;两者冲突时以 RUNBOOK 的流程为准。
>
> **进化北极星见 [GOALS.md](GOALS.md):最大化「非显然洞察」(信息优势)。所有自进化朝它收敛;硬约束=不臆造、宁缺毋滥。**

## 时区
所有"今天/昨天/早班/晚班"按 **Asia/Shanghai**(见 `config/loop.yaml`)。

## 每日循环
> **一键编排:`/ln-daily am`(早班全链路)、`/ln-daily pm`(晚班)。** 下面是它内部的权威步骤。
> 定时调度**未 arm**(用户选择手动跑);将来无人值守时 `ln-daily mode=autonomous` = 免确认自动发布。
- **早班 07:00**:`ln-collect`(batch=am) → `ln-synthesize`(汇总**昨天**) → `python3 web/compile.py` → `bash scripts/deploy-cloudflare.sh`(部署 Cloudflare) → `ln-evolve`
- **晚班 19:00**:仅 `ln-collect`(batch=pm)

## 关键纪律(所有 LLM 步骤通用)
1. **不臆造**:新闻、引文、链接必须真实可回溯。深度类 `original_quote` 保留原话原文,不得改写丢失锋芒。
2. **中文呈现**:`title_zh` / `summary_zh` 一律中文;深度类同时保留原文。
3. **结论必须分级 + 回链证据**:`事实 / 推断 / 预测` + `evidence`(corpus 条目 id)。无证据不出结论。
4. **去重有别**:共识类强去重(合并同事件,`consensus_count` 记几家在报);深度类弱去重(保留不同声音)。
5. **失败要记录**:某来源抓不到 → 记进 `state/metrics.json`,供 `ln-evolve` 优化,不要静默跳过。

## 文件职责
- 改"抓什么" → `config/sources.yaml` / `config/people.yaml`
- 改"怎么抓/怎么分析"(提示词) → `prompts/*.md`(改完记 `prompts/CHANGELOG.md`)
- 改"怎么呈现" → `web/templates/page.html` + `web/assets/style.css`(改后 `python3 web/compile.py` 重建单页)
- 数据 schema:语料 → `.claude/skills/ln-collect/SKILL.md`;分析 + 跨日期线索 → `.claude/skills/ln-synthesize/SKILL.md`
- 跨日期关联 → `data/threads.json`(由 ln-synthesize 维护,编译成"线索时间线")
- 领域专题(产业纵深)→ `config/domains.yaml`(领域剧本,ln-evolve 进化)+ `data/dossiers/<id>.json`(由 `ln-dossier` 生成/更新,编译成「📂 专题」);历年数据序列 → `data/series/<id>.json`(累积沉淀)
- 人类反馈 → 网页弹窗(👍赞/👎踩/✓采用 + 常用词 + 文字)经 `server/feedback_server.py` 写入 `data/feedback.jsonl` + `feedback.md`(`bash scripts/feedback.sh` 读取;ln-evolve 消化并进化 `config/feedback_tags.json`)

## 网站(单页)
`docs/index.html` 是**唯一**页面:左侧日期列表 + 🧵线索 + ⚙️自进化日志(渲染自 `prompts/CHANGELOG.md`)入口,右侧主区,JS hash 路由同页切换(无 iframe)。现代杂志风(宋体+Newsreader 标题、抽印引文、分级配色)。每块正文最多 2 处高亮(`==文本==`)。每条新闻/结论**底部**有 👍赞/👎踩/✓采用,点击弹出页面内对话框(常用词 chips + 可选文字),提交到反馈服务器,**不跳转 GitHub**。

## 自我进化边界(ln-evolve)
- 可改:`prompts/*.md`、`config/*.yaml`(来源增删降权、提示词措辞)。
- 不可自动改:数据 schema、`web/compile.py` 逻辑(属人工大版本)。
- 每轮改动小而有据,可被 git revert + CHANGELOG 回滚。
- **变更落地契约**:进化/功能改动必须落进【代码】或【skill/提示词/文档】(不留在对话);提交前 `bash scripts/check.sh` 自检(pre-commit 已挂,不通过不提交),进化记 CHANGELOG。详见 [RUNBOOK.md](RUNBOOK.md)「变更落地契约」。

## 编译/发布是确定性脚本
`web/compile.py` 与 `scripts/publish.sh` 不含 LLM 逻辑,直接运行即可。
托管二选一:GitHub Pages(`scripts/publish.sh`)或 **Cloudflare**(`scripts/deploy-cloudflare.sh`:Pages 站点 + Worker 反馈 API + R2 桶,见 [CLOUDFLARE.md](CLOUDFLARE.md))。
