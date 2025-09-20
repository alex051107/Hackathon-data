# NASA 行星系统项目：方法演化与宜居优先级

## 项目总览
- **数据来源**：NASA Exoplanet Archive Planetary Systems 表（版本 `PS_2025.09.20_08.15.55.csv`），并补充人工整理的观测设施元数据。项目分析均只保留 `default_flag=1` 的标准参数集，避免重复记录。
- **交付内容**：两条主线分析脚本（`analysis/method_evolution.py`、`analysis/habitable_priority.py`）、三份结果表格（`results/*.csv` 与 `results/habitable_top20.md`）、一份说明文档（本文）；静态图表可在运行脚本后本地生成并保存在 `figures/`（已从 git 忽略）。
- **创新亮点**：
  1. 构建“方法份额 + 设施贡献 + 趋势预测”的组合仪表板，直接支持资源配置决策。
  2. 设计可解释的宜居候选体评分体系，对温度、半径、入射辐射、轨道周期、主星性质与可观测性进行加权融合。
  3. 全流程代码化，实现一键复现清洗、分析、制图与结果导出，方便黑客松演示与后续扩展。

---

## 数据处理与公共步骤
1. **数据读入**：所有脚本通过 `pandas.read_csv` 读入主表，并过滤 `default_flag=1`。【F:analysis/method_evolution.py†L33-L42】【F:analysis/habitable_priority.py†L36-L45】
2. **关键信息清洗**：针对分析需求删除缺失字段并限制异常值范围（如温度 150–450 K、辐射 0.05–5 倍地球、轨道周期 1–800 天等）。【F:analysis/habitable_priority.py†L48-L63】
3. **派生标签**：根据发现方法频次将低频方法聚合为 “Other”；补充观测设施平台、运营方与地理信息。【F:analysis/method_evolution.py†L44-L61】【F:data/discovery_facilities.csv†L1-L21】
4. **结果落地**：所有关键表格保存至 `results/` 目录，图表在运行脚本时导出到本地 `figures/` 目录（未被 git 跟踪），方便撰写报告或导入幻灯片。【F:analysis/method_evolution.py†L214-L235】【F:analysis/habitable_priority.py†L221-L245】

---

## 课题一：轨道探测方法的演化与未来资源配置
### 分析流程
1. **年度方法统计**：将观测方法按份额聚合，生成 1989–2025 年的年度堆叠面积图；脚本会在本地导出 `figures/method_evolution/method_stack.png` 供展示使用（未纳入 git）。【F:analysis/method_evolution.py†L69-L110】
2. **设施贡献拆解**：筛选近十年（2015 年起）贡献最多的 12 个设施，计算各设施内部不同方法的发现份额，并叠加元数据注释；对应图表导出为 `figures/method_evolution/facility_method_share.png`（本地保存，未纳入 git）。【F:analysis/method_evolution.py†L112-L189】
3. **趋势预测**：对拥有充足历史记录的方法采用 Holt-Winters 加性模型，预测未来五年的发现量并输出置信区间；可选地将曲线导出为 `figures/method_evolution/method_forecast.png` 供汇报使用。【F:analysis/method_evolution.py†L191-L213】【F:results/method_forecast.csv†L1-L11】

### 关键发现
- 2015 年以来，凌日法贡献了 **77.8%** 的新发现，是资源分配的主力方向。【F:results/method_timeseries.csv†L1-L5】【a40384†L1-L5】
- Kepler、TESS 与 K2 三大空间望远镜均将 **>99%** 的时间投入凌日测量；KMTNet 和 OGLE 则完全聚焦微引力透镜，凸显地面广域监测的补位作用。【F:results/facility_method_summary.csv†L1-L10】
- Holt-Winters 模型预测到 2030 年凌日法仍将维持 400+ 颗/年的发现规模，而径向速度法有望逼近 80 颗/年；模型同时给出置信区间，提示当前观测量的高波动性。【F:results/method_forecast.csv†L1-L11】

### 科学意义与资源建议
- 结合方法与设施两层可视化，可以解释为何凌日法在空间望远镜时代占据主导地位，同时识别出对径向速度与微引力透镜贡献最大的地面设施，为继续投资高精度光谱仪与全球化网络提供数据支持。
- 预测结果表明，若要维持凌日法的高发现率，需要在 2026 年后规划新的宽视场空间任务或延长 TESS 运行时间；径向速度法的提升则高度依赖于 La Silla、Keck 等地面观测站的设备升级。

### 技术难点与解决方案
- **困难**：设施名称存在不同拼写与合并项，且部分方法样本较少。**解决**：手工整理高频设施元数据，设定最小份额阈值并统一低频方法至 “Other”，确保图表可读性。【F:analysis/method_evolution.py†L44-L78】【F:data/discovery_facilities.csv†L1-L21】
- **困难**：时间序列模型对索引频率敏感。**解决**：将年份序列转换为 RangeIndex，再手动构造预测年份，消除 statsmodels 的频率警告并输出置信区间。【F:analysis/method_evolution.py†L127-L149】

---

## 课题二：宜居带候选体的优先级评分体系
### 分析流程
1. **候选体筛选**：选择具备温度、半径、入射辐射、轨道周期、主星参数及视星等的行星，剔除明显异常值，最终保留 37 个可评分对象。【F:analysis/habitable_priority.py†L36-L74】【f9fdb6†L1-L4】
2. **多指标打分**：对每个指标构建可解释的函数（高斯或 Sigmoid），并赋予权重，得到最终优先级得分及等级标签（High Priority / Follow-up / Context）。【F:analysis/habitable_priority.py†L76-L127】
3. **结果呈现**：输出散点、组件条形图、雷达图三类可视化，并生成前 20 名的 Markdown 表格，方便直接嵌入报告或幻灯片；图像文件在本地保存为 `figures/habitability/*.png`（未纳入 git）。【F:analysis/habitable_priority.py†L129-L220】

### 关键发现
- 目前仅有 **Kepler-22 b** 达到“高优先级”阈值（得分 0.72），该行星温度与地球最为接近，且位于单星系统，适合作为后续透射光谱的重点目标。【F:results/habitable_priority_scores.csv†L1-L6】【a40384†L19-L22】
- 三个“Follow-up” 行星（Kepler-452 b、PH2 b、HIP 41378 f）虽在温度和入射辐射上接近宜居带，但受半径偏大或亮度限制，需要进一步观测以确认大气性质。【F:results/habitable_top20.md†L5-L19】
- 评分分布的中位半径约为 3.1 个地球半径，说明现有样本仍偏向迷你海王星；未来提高光谱灵敏度、瞄准更小半径行星是关键突破点。【f9fdb6†L1-L4】

### 技术难点与解决方案
- **困难**：不同指标的量纲与目标区间不一致。**解决**：采用高斯/对数距离函数衡量“接近地球”的程度，再通过归一化权重保证可解释性。【F:analysis/habitable_priority.py†L82-L113】
- **困难**：视星等缺失会导致可观测性评分为空。**解决**：在候选筛选阶段即过滤缺失值，并在分数过低时标记为 “Context” 类别，提醒需补充观测数据。【F:analysis/habitable_priority.py†L48-L109】

### 推广建议
- 将评分表导入交互式仪表板（如 Streamlit）可方便导师快速筛选目标；也可结合 JWST/罗曼等未来任务的观测窗口，重新加权 `observability_score`。
- 若获取恒星活动度或噪声指标，可扩展至动态优先级评估，自动推荐适合的望远镜与观测模式。

---

## 项目结构与复现方式
1. 安装依赖：`pip install pandas seaborn matplotlib numpy statsmodels scikit-learn tabulate`。
2. 运行方法演化分析：`python analysis/method_evolution.py`，生成时间序列图、设施拆解图和五年预测表。【F:analysis/method_evolution.py†L214-L235】
3. 运行宜居评分分析：`python analysis/habitable_priority.py`，输出评分图表与候选清单。【F:analysis/habitable_priority.py†L221-L245】
4. 在运行脚本生成图像后，将本地 `figures/` 目录与 `results/` 目录中的素材导入 DevPost 展示或决赛演示文稿。

---

## 致谢与合规说明
- 观测设施信息基于公开的天文台背景知识人工整理，已在 `data/discovery_facilities.csv` 中列出，便于评委追溯来源。【F:data/discovery_facilities.csv†L1-L21】
- 本项目在黑客松规定下使用了生成式 AI（ChatGPT）辅助撰写分析思路与代码实现，已在代码与文档中给出完整引用。

