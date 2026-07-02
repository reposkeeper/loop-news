# loop.md — 个人进化循环(loop engineering)· base

> 把这个用户的自进化循环写死成**六要素**(设计 §5.4):**目标 → 信号 → 执行器 → 驱动 → 护栏 → 节律**。
> 由通道 B([`ln-evolve-lite`](../../.claude/skills/ln-evolve-lite/SKILL.md))在无状态 runner 上执行(§6);**面向用户永远是确定性的:LLM 只在后台,产物落成 `profile.json` 再被热路径消费**(§5.3)。base 版是缺省循环,一般不必改。

| 要素 | 内容 |
|---|---|
| **目标 goal** | 见 `goals.md`:对**此用户**最大化「非显然洞察」;硬约束 = 不臆造、宁缺毋滥、不喂气泡(承 [GOALS.md](../../GOALS.md))。 |
| **信号 signal** | **只用此人自己的**反馈——👍赞 / 👎踩 / ✓采用 / 关注 / 屏蔽 / 停留(D1 `feedback` 按 `user_id` 隔离)+ 此人的**个人 8 维分**(`rubric.md`)。**不掺别人、不掺系统分。** |
| **执行器 actuator** | 只能改此人的 overlay:`agent.md` / `spec.md` / `rubric.md` / `goals.md` 侧重 + `profile.json` 权重(`topics`/`entities`/`sources`/`tones`)与 `muted`。**不能改代码 / schema / ② 共享语料 / owner 全局 base / 别的用户。** |
| **驱动 driver** | 每轮把个人 8 分里**最低的**那个提上去;**张力矩阵防作弊**(`rubric.md` / §8.3):**过度 mute → 个人克制↓(反回音室)**、**兴趣过窄 → 个人创新↓(反过滤气泡)**。⇒ 循环自动收敛到「既懂他、又不把他关进气泡」。 |
| **护栏 guard** | **隔离不变量**:个人 evolve 只碰本用户 overlay,不碰全局、不碰他人、不碰共享语料;全局 `ln-evolve` 也不碰已分叉 overlay。**小步、有据、可回滚**(个人 `changelog.md` + git revert)。**降级即安全**:runner 宕机 → 热路径服务最后一版 `profile.json` 照常出页,只是进化暂停。 |
| **节律 cadence** | 每日一次(或此人活跃时增量),批量;规则为主、LLM 一次小精修为辅(§5.3 通道 B)。 |

## 一句话
个人 8 维分 = 奖励函数,「**提最低分 + 张力矩阵**」= 让循环自动收敛到「既懂这个人、又不把他关进过滤气泡」。这就是这个人的 loop engineering。
