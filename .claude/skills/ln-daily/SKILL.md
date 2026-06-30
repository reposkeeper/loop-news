---
name: ln-daily
description: Loop News 每日循环编排。一条命令按权威顺序跑完整轮——早班(am)=采集→汇总昨天→编译→发布→进化;晚班(pm)=仅采集。当用户说"跑早班/晚班"、"跑整轮"、"走一遍流程"、"daily loop"、"ln-daily"、"每日循环"时使用。参数:batch=am|pm(默认按当前时间);mode=interactive|autonomous(后者供定时调度免确认发布)。
---

# ln-daily · 每日循环编排

把 5 个分步 skill 按 [RUNBOOK.md](../../../RUNBOOK.md) 的权威顺序串起来跑完一轮。时区 Asia/Shanghai。
**这是编排层——真正逻辑都在各分步 skill + `prompts/*.md` + 脚本里,本 skill 只负责"按序、可靠、不带病发布"。**

## 参数
- `batch`:`am` 或 `pm`(不传则按当前时间:< 12:00 视为 am,否则 pm)。
- `mode`:`interactive`(默认,**发布前人工确认**)或 `autonomous`(定时调度用,免确认直接发布)。

## 早班(am)—— 全链路
**串行执行,前一步产物是后一步输入;任一步失败 → 立即停止、记入 `state/metrics.json`、不进入发布(绝不带病发布)。**
1. **`ln-collect`(batch=am)** —— 采集今天(共识 + 深度;X 走 `x_cost` 低成本模式)。
2. **`ln-synthesize`(date=昨天)** —— 汇总**前一天**(其数据已 am+pm 两班完整);产出 `data/analysis/<昨天>.json` + 更新 `data/threads.json`。
3. **`ln-compile`** —— `python3 web/compile.py` 重建单页 `docs/index.html`。
4. **发布门**:
   - `interactive`:先本地预览(`preview` / 浏览器看 `docs/index.html`),**请用户确认**后再继续。
   - `autonomous`:跳过确认,直接进入下一步(已由调度授权)。
5. **`ln-publish`** —— `bash scripts/publish.sh` 提交并 push,GitHub Pages 上线。
6. **`ln-evolve`** —— 读人类反馈(`scripts/feedback.sh`)+ 自评 + 小步改进 `prompts/*.md`/`config/*.yaml` + 记 `prompts/CHANGELOG.md`。

## 晚班(pm)—— 仅采集
1. **`ln-collect`(batch=pm)** —— 采集今天晚班,入语料库供次日早班汇总。

## 纪律
- 严格串行;**编译失败 / 当日分析为空 → 不发布**。
- 全程中文产出;深度类保留原文;X 成本受 `config/loop.yaml` 的 `x_cost` 约束。
- 跨 agent:Codex 等无此编排器时,照 RUNBOOK.md 的"每日循环"逐步执行,等价。
