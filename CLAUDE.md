# CLAUDE.md · Loop News 运行约定

给在本仓库工作的 Claude 的操作说明。本项目是一个自循环新闻情报系统,详见 [README.md](README.md)。

## 时区
所有"今天/昨天/早班/晚班"按 **Asia/Shanghai**(见 `config/loop.yaml`)。

## 每日循环
- **早班 07:00**:`ln-collect`(batch=am) → `ln-synthesize`(汇总**昨天**) → `python3 web/compile.py` → `bash scripts/publish.sh` → `ln-evolve`
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
- 改"怎么呈现" → `web/templates/` + `web/assets/style.css`(改后 `python3 web/compile.py --all` 重建)
- 数据 schema:语料 → `.claude/skills/ln-collect/SKILL.md`;分析 → `.claude/skills/ln-synthesize/SKILL.md`

## 自我进化边界(ln-evolve)
- 可改:`prompts/*.md`、`config/*.yaml`(来源增删降权、提示词措辞)。
- 不可自动改:数据 schema、`web/compile.py` 逻辑(属人工大版本)。
- 每轮改动小而有据,可被 git revert + CHANGELOG 回滚。

## 编译/发布是确定性脚本
`web/compile.py` 与 `scripts/publish.sh` 不含 LLM 逻辑,直接运行即可。
