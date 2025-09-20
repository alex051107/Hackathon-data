# NASA 行星系统项目最终说明书

## 1. 项目目标与数据范围
- **赛题定位**：面向 Carolina Data Challenge 2025 “Zero Gravity” 自然科学赛道，聚焦 NASA Exoplanet Archive 行星系统表。
- **核心问题**：
  1. 不同观测方法的发现能力如何在 1989–2025 年间演进？哪些设施值得未来投入？
  2. 在现有参数可测的行星中，哪些对象最适合作为宜居带后续观测的优先目标？
- **原始数据**：`PS_2025.09.20_08.15.55.csv`，仅使用 `default_flag=1` 的记录避免重复参数。【F:analysis/method_evolution.py†L26-L33】【F:analysis/habitable_priority.py†L32-L39】
- **辅助数据**：手工整理的 `data/discovery_facilities.csv`，统一主要观测设施的名称、平台与地理位置。【F:data/discovery_facilities.csv†L1-L21】

## 2. 数据清洗与特征工程
1. **基础过滤**：删除缺失 `disc_year`、`discoverymethod` 的记录，限定年份 ≥1989 确保时间序列完整。【F:analysis/method_evolution.py†L28-L36】
2. **方法分组**：统计频率后，将出现占比 <2% 的发现方法合并为 “Other”，保持可视化可读性。【F:analysis/method_evolution.py†L38-L46】
3. **宜居筛选**：仅保留温度、半径、入射辐射、轨道周期、主星参数与视星等完整的行星，并剔除 99 分位以上异常值及明显不合理区间。【F:analysis/habitable_priority.py†L41-L63】
4. **多指标得分**：对温度、半径、入射辐射、轨道周期、主星温度等构造高斯/对数距离函数，对可观测性使用 Sigmoid，在 0–1 之间规范化后加权求和得到优先级分数。【F:analysis/habitable_priority.py†L68-L119】
5. **结果落地**：全部关键表格输出到 `results/`，静态图在运行脚本时导出到本地 `figures/` 目录（未被 git 跟踪），为报告与演示提供直接素材。【F:analysis/method_evolution.py†L206-L235】【F:analysis/habitable_priority.py†L202-L245】

## 3. 分析模块详解
### 3.1 观测方法演化与设施贡献
- **年度堆叠面积图**：`aggregate_method_timeseries` 生成年度×方法的发现量，`plot_method_stack` 输出主图；显示凌日法在 2015 年后逐步占据 77.8% 份额。【F:analysis/method_evolution.py†L56-L110】【F:results/method_timeseries.csv†L1-L5】
- **设施拆解**：筛选 2015 年以来贡献最高的 12 个设施，计算内部方法份额并叠加平台/地点注释。【F:analysis/method_evolution.py†L112-L172】
- **趋势预测**：使用 Holt-Winters 加性模型对历史样本 ≥6 年的方法做五年滚动预测，输出置信区间。【F:analysis/method_evolution.py†L174-L213】
- **关键洞察**：
  - 凌日法贡献 77.8%，说明宽视场空间任务（Kepler、K2、TESS）仍主导新发现。
  - 地面设施 KMTNet/OGLE 负责全部微引力透镜信号，地面资源在特定领域不可替代。
  - 模型显示 2030 年凌日年发现量仍可超过 400 颗，径向速度法趋向 80 颗/年，需要高精度光谱仪支撑。【F:results/method_forecast.csv†L1-L11】

### 3.2 宜居候选优先级评分
- **候选体数量**：共 37 个行星满足数据完备性，只有 Kepler-22 b 达到“High Priority”阈值，三颗 Follow-up 目标等待后续光谱确认。【F:analysis/habitable_priority.py†L161-L199】【F:results/habitable_priority_scores.csv†L1-L6】
- **可视化组合**：
  - 温度 vs 半径散点，叠加宜居带与地球类尺寸窗口。【F:analysis/habitable_priority.py†L129-L156】
  - 成分条形图展示前 15 名指标贡献，凸显各指标的权重影响。【F:analysis/habitable_priority.py†L158-L181】
  - 雷达图比较前 5 名候选体的多指标特征。【F:analysis/habitable_priority.py†L183-L201】
- **洞察与建议**：优先候选体多位于单星系统，视星等 <13.5，提示未来观测策略需兼顾光谱灵敏度与星级稳定性。

## 4. 验证与质量控制
- 新增 `analysis/validate_analysis.py` 自动重算时间序列、设施份额、预测与宜居评分，与现有结果对比输出差异上限和状态标记。【F:analysis/validate_analysis.py†L1-L147】
- 脚本生成 `results/validation_report.json` 与 `results/validation_report.md`，汇总每项检查的 PASS/REVIEW 结论，确保关键数字可追溯。【F:analysis/validate_analysis.py†L149-L186】
- 2025-2030 预测、设施归一化、优先级表格均实现全量一致（最大差值 <1e-6），验证结果为 PASS。

## 5. 可视化资产与扩展
- **静态素材**：运行脚本后生成并保存在本地 `figures/method_evolution/*.png`、`figures/habitability/*.png`（未纳入 git），适合插入幻灯片或打印展示。【F:analysis/method_evolution.py†L90-L152】【F:analysis/habitable_priority.py†L129-L201】
- **交互式网站**：`analysis/build_dashboard.py` 生成 `webapp/index.html`，包含堆叠面积、年度动画条形图、设施组合与宜居散点四个 Plotly 图层，可直接部署或嵌入 DevPost 页面。【F:analysis/build_dashboard.py†L1-L158】
- **动画亮点**：年度条形动画展示方法份额的年度波动，宜居散点可交互框选地球类区域，满足“会动的可视化”要求。
- **进一步展示形式**：可扩展为 Streamlit 或 Observable dashboard，利用现成 CSV/HTML 输出迅速搭建互动故事线。

## 6. 演示（Presentation）策略
### 7 分钟演讲大纲
1. **开场（0:00–0:45）**：介绍 CDC 赛题与 NASA 数据来源，强调资源配置与宜居探索的现实意义。
2. **问题定义（0:45–1:30）**：分别界定“观测方法演化”和“宜居优先级”两个分析目标，说明数据处理与验证策略。
3. **方法演化故事线（1:30–3:15）**：
   - 使用堆叠面积图讲述凌日法崛起。
   - 切换到设施条形图解释空间/地面任务分工。
   - 引入预测曲线，讨论未来五年资源投入建议。
4. **宜居优先级（3:15–5:15）**：
   - 展示散点图与雷达图，解释评分模型与结果。
   - 强调高优先级与 Follow-up 目标的科学意义。
5. **验证与复现（5:15–6:10）**：展示验证脚本与报告，说明项目如何保证数据准确性与可复制性。
6. **展望与问答准备（6:10–7:00）**：概述下一步（接入 JWST/罗曼观测窗口、增加噪声指标等），邀请评委提问。

### 演示辅助建议
- 将 `webapp/index.html` 放在独立浏览器标签页用于现场互动演示。
- 预先截取关键帧（如 2015、2020、2025 年）放入幻灯片，保证离线情况下仍能讲述故事。
- 准备备用统计数据（Transit 份额、候选体数量等）写在讲稿/便签上，便于 Q&A 快速响应。

## 7. 科学意义与创新亮点
- 解释 2015 年后凌日法 77.8% 的贡献，为下一代宽视场任务和地面光谱升级提供数据支撑。【F:results/method_timeseries.csv†L1-L5】
- 构建多指标宜居评分体系，量化筛选优先观测对象，仅 2.7% 的样本进入高/中优先级，体现资源稀缺性。【F:results/habitable_priority_scores.csv†L1-L6】
- 结合预测模型与交互式网站，实现“方法份额 + 设施贡献 + 情景预测”的立体呈现，是区别于常规静态分析的主要创新。【F:analysis/build_dashboard.py†L68-L156】

## 8. 技术难点与解决方案
- **命名标准化**：设施名称存在多种写法，通过补充 `data/discovery_facilities.csv` 并在脚本中统一处理，确保图表注释一致。【F:analysis/method_evolution.py†L44-L74】
- **时间序列建模警告**：Holt-Winters 模型对索引频率敏感，脚本中手动构造预测年份并计算置信区间，避免 statsmodels 警告。【F:analysis/method_evolution.py†L178-L213】
- **多指标归一化**：使用高斯/ Sigmoid 函数将不同量纲映射至 0–1 并赋权，保证得分可解释性。【F:analysis/habitable_priority.py†L82-L118】
- **结果验证**：`analysis/validate_analysis.py` 自动对比存档结果与现算数据，最大差异 <1e-6 即视为通过，形成制度化 QA。【F:analysis/validate_analysis.py†L46-L132】

## 9. 复现与交付清单
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt` 安装依赖。【F:requirements.txt†L1-L8】
3. `python analysis/method_evolution.py` 生成方法演化结果与预测。
4. `python analysis/habitable_priority.py` 生成宜居评分与图表。
5. `python analysis/validate_analysis.py` 产出验证报告，确认关键数字无误。
6. `python analysis/build_dashboard.py` 更新交互式网页，可直接在浏览器打开 `webapp/index.html`。
7. 在运行脚本生成图像后，将本地 `figures/`、`results/`、`webapp/` 与本文档一并提交至 DevPost，满足黑客松的“代码 + 可视化 + 文档”要求。

> **AI 使用说明**：本项目在构思与编码阶段辅助参考了生成式 AI（ChatGPT），所有最终脚本与文档均经人工审阅和验证，确保满足 CDC 关于引用与诚信的规定。
