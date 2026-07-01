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

## 早班(am)—— 全链路(**先进化修复,再生成当天总结**)
**串行执行;任一步失败 → 立即停止、记入 `state/metrics.json`、不进入发布(绝不带病发布)。**
1. **`ln-collect`(batch=am)** —— 采集今天(共识 + 深度;X 走 `x_cost` 低成本模式)。
2. **`ln-evolve`(★ 先跑,必须先完成)** —— **消化所有待处理反馈/问题(尤其 owner 的全局提问 `ask`)并据此改进 `prompts/*.md`、`config/*.yaml`**。当天的总结要用改进后的提示词,所以**进化没跑完不进入下一步**。遇到需决策的点**不等待**:按 [GOALS.md](../../../GOALS.md) 北极星选**最简可行**方案、记 `prompts/CHANGELOG.md`,继续。
3. **`ln-synthesize`(date=昨天)** —— 用刚改进的方法论汇总**前一天**(数据已 am+pm 两班完整);产 `data/analysis/<昨天>.json` + 更新 `data/threads.json`。
4. **`ln-compile`** —— `python3 web/compile.py` 重建单页 `docs/index.html`。
5. **发布门**:`interactive` 本地预览 + 人工确认 / `autonomous` 直接(已由调度授权)。
6. **`ln-publish`** —— `bash scripts/deploy-cloudflare.sh` 部署 Cloudflare(Pages 站点 + Worker 反馈 API)。
7. **预热分享图** —— `python3 scripts/warm-share.py <当天>`:把当天所有卡片(共识/深度/播客)按 id 预渲染进 R2 缓存,之后用户点「分享」几乎都是缓存命中(秒发、不吃 Worker CPU、不受字体抖动影响)。脚本幂等自收敛(偶发 503 自动重试补齐);仍有零星失败可稍后再跑一次。**非阻塞**:预热失败不影响已发布的站点。

## 晚班(pm)—— 仅采集
1. **`ln-collect`(batch=pm)** —— 采集今天晚班,入语料库供次日早班汇总。

## 纪律
- 严格串行;**编译失败 / 当日分析为空 → 不发布**。
- 全程中文产出;深度类保留原文;X 成本受 `config/loop.yaml` 的 `x_cost` 约束。
- 跨 agent:Codex 等无此编排器时,照 RUNBOOK.md 的"每日循环"逐步执行,等价。
- **变更落地契约**:本轮任何进化/改动须落进【代码】或【skill/文档】;`ln-evolve` 末尾会跑 `bash scripts/check.sh` 自检(git 提交时也强制),不通过先修。
