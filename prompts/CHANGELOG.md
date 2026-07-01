# 进化改动日志(CHANGELOG)

> `ln-evolve` 每轮自评后,把对 `prompts/*.md`、`config/*.yaml` 的改动记在这里。
> 格式:日期 · 改了什么 · 为什么 · 如何回滚。最新在最上。

---

## 2026-07-01 · 进化(消化反馈:更多 AI + 即刻 + 🎙️ 播客环节)
- **依据**:线上 `/requests`(「AI 在企业中的应用 / harness engineering」「机器人 / 具身智能创业融资」)+ `/follows`(AI 安全 / 前沿模型)+ metrics(ylecun/DrJimFan/paulkrugman/RayDalio 多口水/格言/无实质);站长指令「AI 内容太少、加即刻、新增播客」。
- **改了什么**:
  1. **更多 AI**:`sources.yaml` 加 AI 专项 query(企业 AI/harness、机器人具身融资、AI 安全/前沿模型)+ AI RSS(TechCrunch AI / VentureBeat AI / MIT Tech Review);`people.yaml` 新增高信号声音(Mira Murati / Noam Shazeer / Jared Kaplan / Aidan Gomez / Arvind Narayanan),低产者标 `priority: low` 降权(ylecun/DrJimFan/paulkrugman/RayDalio)。
  2. **即刻 Jike**:`sources.cn_platforms` 加即刻(WebSearch 限定 okjike.com 找一手,抓不到只作信号,不臆造)。
  3. **🎙️ 播客环节(新)**:`config/podcasts.yaml`(Dwarkesh / Lex / No Priors / Latent Space … + 重点 AI 嘉宾);ln-collect 加播客采集步、ln-synthesize schema 加 `podcasts`、compile 新增「🎙️ 播客 · AI 人物访谈」区(节目 / 主持×嘉宾 / 要点 / 原话 / 收听);示例接入 3 集真实访谈(Dwarkesh×Amodei、Lex×Hassabis、Lex×Pichai)。
- **为什么**:反馈明确要更多 AI 与高质量中文平台;知名主持 × 知名 AI 人物的整集深访是「非显然洞察」的富矿(北极星)。
- **如何回滚**:`git revert` 对应提交;播客/即刻/AI 源均为配置与提示词,删对应段即回退。

---

## 2026-07-01 · 进化(专题升级为深度报道 + 严肃媒体房规)
- **改了什么**:
  1. 新增 `prompts/dossier.method.md`(深度报道方法论 + 严肃媒体写法 + 反煽动硬约束 + 自评口径);重写 `ln-dossier` skill:深挖一手/多元信源 → 写成结构化文章(核心判断 / 脉络 / 数据 / 各方 / 分析 / 反方 / 看点 / 来源)。
  2. compile 专题改文章式渲染(刊头 + 导语首字下沉 + 各方角色标签 + 分级结论 + 反方 + 看点 + 来源);示例「AI 监管」专题据实重写为深度报道——州法爆发 vs 联邦 99–1 预占失败 vs 州内降温,含 Cruz / Markey 真实原话与 NCSL / 参议院一手来源。
  3. `ln-evolve` 读专题 `quality_self_eval` 持续打磨 dossier.method;`collect.consensus/deep` 与 `domains.yaml` 加"对标严肃媒体 + 一手优先 + 多方在录"房规。
- **为什么**:专题不该是新闻聚合,而应是有数据、图表、(挣来的)观点、分析的深度报道;把"严肃新闻体、反自媒体危言耸听"固化成可进化的房规。
- **如何回滚**:`git revert` 对应提交;方法都在 `dossier.method.md`,回退即恢复旧专题形态。

---

## 2026-07-01 · 发布(系统/新闻分离 + 多家原文 + 自助分享链接)
- **改了什么**:
  1. **「想看的话题」改浮动按钮**叠在「反馈」上(所有访客);**「自进化日志」等系统项**移入侧栏底部「系统」区,与新闻导航(线索/收藏/专题/每日)分开——系统管理不与新闻混。
  2. **多家报道→逐家可点原文**:`source_links` 让"N 家在报"渲染成逐家各自可点的原文链接;并据实修正科罗拉多 AI 法(实为 SB189 大改 + 推迟到 2027-01)。
  3. **自进化日志可分享成现代产品发布卡**:版本徽章 + 标题 + 要点,刻意区别于新闻卡。
  4. **owner 自助生成分享链接**:网页填名字一键生成专属访问链接(便于区分分享给谁),访问门与各接口同时认 R2 里的自助 token。
- **为什么**:把"系统管理"与"新闻消费"在信息架构上分开;让多家印证可逐家溯源;让"分享与放行"从改配置变成网页自助。
- **如何回滚**:`git revert` 对应提交;自助 token 存 R2 `tokens/`,删对象即吊销。

---

## 2026-07-01 · 发布(改版 + 分享出图 + 想看的话题)
- **改了什么**:
  1. **整页重设计 + 移动端适配**:统一条目动作栏(赞/踩/采用 · 收藏/关注/分享 同一行、顶部发丝线分隔),侧栏抽屉、底部抽屉式弹窗、安全区与触控目标下沉;桌面/手机两端实测。
  2. **每条新闻「⤴ 分享」**:服务端按手机卡片样式出图(独立 Worker `loop-news-share` · Satori+resvg / `workers-og`),中文按本卡片文本子集化加载、含图表,点击自动下载 PNG。
  3. **「➕ 想看的话题」**:任意用户提交想持续看到的新闻类型,下一轮 `ln-collect` 并入采集议程。
  4. **「提问」→「反馈」**:全局浮动按钮更名。
- **为什么**:多次迭代后按钮位置/结构不统一,先理顺;并补齐对外分享通路与用户驱动采集,贴近北极星——让有信息优势的内容更易被带走、被持续追踪。
- **如何回滚**:`git revert` 对应提交;分享出图为独立 Worker,可单独下线不影响主站与反馈 API。

---

## 2026-06-30 · 进化 #1(首期真实运行后自评)
- **依据**:`state/metrics.json` 的 `2026-06-30-am` 一轮 —— `x_mcp: unavailable`、`reddit: blocked`、`nitter: dead`;且抽查首期产物发现共识类 `url` 多指向聚合/周报页(buildfastwithai、medium 综述)而非一手出处。
- **改了什么**:
  1. `prompts/collect.consensus.md`:新增「优先一手出处」规则——`url` 优先原始媒体/官方稿,禁用聚合页当来源,`consensus_count` 必须实数不估算。
  2. `config/sources.yaml`:标注 Reddit 被拦(仅作 WebSearch 信号)、HN 改用 Algolia API、新增 `x.via: mcp`(fallback websearch)。
- **为什么**:提升共识类来源可信度与可回溯性;把实测的来源可用性固化进配置,指导下一轮采集。
- **如何回滚**:`git revert` 本次提交,或删除上述两处新增段落即可恢复到「进化 #0/初始化」基线。

---

## 2026-06-30 · 工程初始化
- **改了什么**:创建初始提示词(collect.consensus / collect.deep / synthesize.method)与来源配置。
- **为什么**:Loop Engineering 工程起步,建立可被后续自动演进的基线。
- **如何回滚**:本条为初始版本,无需回滚;后续改动以本版本为基线对比。
