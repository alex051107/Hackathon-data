# 宜居候选优先级项目 7 分钟演讲稿

> **演讲角色假设**：两人团队，由主讲人（Speaker A）负责问题、方法与结果，由辅讲人（Speaker B）在关键图表切换时补充数据亮点。括号内为提示，不朗读。

---

## 0:00 – 0:45  开场：赛题与使命
**Speaker A**：
“各位评委、同学大家好，我们来自 Zero Gravity 自然科学赛道。今天要解决的问题是：在 NASA 公布的 5,500 多颗系外行星里，究竟哪些目标值得我们在下一个十年优先指向 JWST、罗曼望远镜或大型地面望远镜？我们聚焦的是 NASA Exoplanet Archive 的 Planetary Systems 表，并只保留 `default_flag=1` 的记录避免重复参数。这份数据代表目前同行评审认可的观测成果，是我们探讨宜居可能性的最佳起点。”【F:docs/final_documentation.md†L1-L13】

**Speaker B**（展示 Slide 1：项目封面 + 研究问题）：
“为了保证结论可复现，我们在仓库中提供了原始数据 `PS_2025.09.20_08.15.55.csv` 以及整套脚本，所有结果都能通过 `python analysis/habitable_priority.py` 和 `python analysis/validate_analysis.py` 重建。”【F:docs/final_documentation.md†L1-L31】

---

## 0:45 – 1:45  数据与挑战
**Speaker A**（切换 Slide 2：数据处理流程图）：
“数据的第一道关口是质量控制。我们只接受温度 150–450 K、半径 0.4–3.5 Earth Radii、质量 0.2–15 Earth Mass 的样本，并补全缺失的入射辐射与质量。经过这一轮筛选，5,500 多颗行星只剩下 31 个满足所有约束，比例不到 1%。这意味着我们的分析必须既谨慎又解释充分。”【F:analysis/habitable_priority.py†L63-L152】【F:results/habitable_priority_scores.csv†L1-L32】

**Speaker B**：
“为了回应 ‘数据是否合理’ 的质疑，我们增加了四道防线：一是与 PHL 权威清单逐项比对，二是自动校验四大支柱分数、发现任何超过 1e-6 的偏差都会报错，三是记录每个被过滤样本的原因，四是将最终权重写入验证报告防止静默漂移。”【F:docs/final_documentation.md†L52-L63】

---

## 1:45 – 3:15  四大支柱评分框架
**Speaker A**（切换 Slide 3：四支柱示意图）：
“我们没有使用黑盒模型，而是把宜居性拆成四个支柱，每个支柱都有明确的物理意义。气候支柱权重 0.45，衡量温度、入射辐射和轨道周期是否落在可保持液态水的范围；结构支柱权重 0.25，确保半径和质量支持岩质或海洋行星；可观测性支柱权重 0.22，以过境深度、视星等和距离估计未来光谱信噪比；最后是系统支柱权重 0.08，惩罚多星系统的动力学不确定性。”【F:analysis/habitable_priority.py†L114-L196】

**Speaker B**（展示 Slide 4：评分公式表）：
“每个支柱的得分都在 `[0,1]`，并通过梯形隶属函数或逻辑函数控制边界效应。权重之和固定为 1，任何修改都能通过验证脚本立即检测。右侧的日志示例显示，我们的最新版本通过了全部权重与范围检查。”【F:docs/final_documentation.md†L52-L63】【F:analysis/validate_analysis.py†L77-L120】【F:results/validation_report.json†L1-L39】

---

## 3:15 – 4:45  关键结果与可视化
**Speaker A**（切换 Slide 5：温度-半径散点图）：
“请看散点图，横轴是行星半径、纵轴是平衡温度。绿色窗口标记我们的气候支柱所认可的宜居带。点的大小表示优先级分数，颜色代表可观测性。像 K2-3 d、Kepler-452 b、TOI-2095 c 这样的行星都位于窗口中心，同时具备明亮的主星与较深的过境。”【F:analysis/habitable_priority.py†L198-L220】【F:results/habitable_priority_scores.csv†L1-L16】

**Speaker B**（切换 Slide 6：Pillar 条形图 + 雷达图）：
“在这里我们对前 12 名候选体展示四支柱贡献。可以看到 LHS 1140 b 虽然气候偏冷，但凭借 5,397 ppm 的过境深度和仅 15 光年的距离，在可观测性上弥补了劣势；而 Kepler-452 b 虽然相对暗淡，但长期轨道稳定性让它依然进入 High Priority。”【F:analysis/habitable_priority.py†L198-L244】【F:results/habitable_priority_scores.csv†L9-L16】

**Speaker A**（展示 Slide 7：权威对照表）：
“我们还把内部高分目标与 PHL 权威样本对照。`phl_confidence` 字段显示，31 个候选中有 21 个与权威结论一致，其余 10 个被标记为 `investigate`，主要原因是缺乏质量测量或主星活动度数据。这部分差异会在 Q&A 中详细解释。”【F:results/habitable_authoritative_comparison.csv†L1-L22】

---

## 4:45 – 5:45  互动仪表板与复现
**Speaker B**（切换 Slide 8：Dashboard 录屏或网页）：
“所有图表都在 `webapp/index.html` 中以 Plotly 实现互动。我们提供了优先级散点、支柱堆叠条形图、可观测性相图和分档统计。评委可以直接悬停查看 TOI-2095 c 的 768 ppm 过境深度、13.19 视星等等细节，从而验证我们前面提到的数据。”【F:analysis/build_dashboard.py†L1-L154】【F:results/habitable_priority_scores.csv†L1-L16】

**Speaker A**：
“为了保证每位评委都能复现，我们编写了 `analysis/validate_analysis.py` 自动检查分数、权重、标签一致性，并生成 PASS 报告。一旦指标出现漂移，该脚本会立即在结果表中将状态从 PASS 改为 REVIEW。”【F:analysis/validate_analysis.py†L1-L135】【F:results/validation_report.md†L1-L13】

---

## 5:45 – 6:45  科学意义与下一步
**Speaker A**（切换 Slide 9：科学意义）：
“科学意义在于三个层面。第一，清晰界定了 31 个真正值得关注的目标，为未来 10 年的观测排程提供优先列表。第二，可观测性支柱让我们能评估每颗行星的信噪比，避免将宝贵的 JWST 时间浪费在过暗的目标上。第三，我们把全流程自动化，每次 NASA 更新数据时，重新运行脚本即可得到新一代榜单。”【F:docs/final_documentation.md†L70-L99】

**Speaker B**：
“下一步我们计划接入恒星活动度与噪声模型，进一步缩小 `investigate` 名单；同时，把 dashboard 部署到在线服务，方便评委和公众互动。”【F:docs/final_documentation.md†L105-L132】

---

## 6:45 – 7:00  收尾与 Q&A
**Speaker A**：
“总结一下：我们从 5,500 多颗行星中筛出 31 个数据完整的候选，构建物理约束明确的四支柱评分，验证了每一步的合理性，并通过互动仪表板讲述故事。期待各位的提问，谢谢。”

**Speaker B**（准备答问）：
“我们已经把重点候选的原始参数与评分结果整理在 `results/habitable_top20.md`，欢迎评委在 Q&A 时抽查任何一颗行星，我们可以现场追溯到计算细节。”【F:results/habitable_top20.md†L1-L22】

---

## 附录：Q&A 备用要点
- **为何信任 31 个样本？** → 指向过滤规则和验证脚本日志，说明其他样本缺乏必需测量或超出物理范围。【F:analysis/habitable_priority.py†L63-L152】
- **是否考虑权威榜单差异？** → 说明 `phl_confidence` 分类，并列举 TOI-2095 c 等新发现尚未收录的原因。【F:analysis/habitable_priority.py†L208-L244】
- **可观测性指标是否现实？** → 引用过境深度与视星等公式，强调采用 ppm 级别指标对接 JWST 观测策略。【F:analysis/habitable_priority.py†L132-L144】
- **如何复现？** → 列出 `pip install -r requirements.txt`、运行四个脚本即可重建所有成果。【F:docs/final_documentation.md†L110-L127】【F:requirements.txt†L1-L8】

