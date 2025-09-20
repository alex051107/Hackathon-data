# NASA 行星系统项目最终说明书

## 1. 项目目标与数据范围
- **赛题定位**：面向 Carolina Data Challenge 2025 “Zero Gravity” 自然科学赛道，聚焦 NASA Exoplanet Archive 行星系统表。
- **核心问题**：在现有参数可测的行星中，哪些对象最适合作为宜居带后续观测的优先目标？
- **原始数据**：`PS_2025.09.20_08.15.55.csv`，仅使用 `default_flag=1` 的记录避免重复参数。【F:analysis/ps_overview.py†L20-L24】【F:analysis/habitable_priority.py†L48-L60】
- **辅助数据**：`data/authoritative_habitable_sample.csv`，离线保存的权威宜居候选体样本，用于对照验证。【F:analysis/habitable_priority.py†L208-L244】

## 2. 数据清洗与特征工程
1. **基础过滤**：删除缺失温度、半径、质量、轨道周期、主星参数、视星等、距离和系统多星数的记录，限定温度 150–450 K、入射辐射 0.1–3 倍地球（缺失时按 `(T/255K)^4` 估算）、半径 0.4–3.5 地球半径、质量 0.2–15 地球质量等区间，避免极端值影响评分稳定性。【F:analysis/habitable_priority.py†L63-L112】
2. **派生指标**：
   - 使用梯形隶属函数刻画温度、辐射、轨道周期、主星有效温度的气候适宜度。
   - 对缺失的质量使用半径驱动的经验公式补全，再结合原始/估算值生成“结构”评分。
   - 计算行星/恒星半径比推导过境深度，并结合视星等、距离构建可观测性评分。
   - 根据系统多星数量引入稳定性惩罚。
   【F:analysis/habitable_priority.py†L114-L152】
3. **支柱权重**：设定气候 0.45、结构 0.25、可观测性 0.22、系统环境 0.08 的权重，生成 0–1 间的最终优先级得分，并根据阈值（0.58、0.70）划分为 `Context` / `Follow-up` / `High Priority` 三档。【F:analysis/habitable_priority.py†L154-L196】
4. **结果落地**：关键表格输出到 `results/`，静态图像在运行脚本时导出到 `figures/habitability/`（未被 git 跟踪），为报告与演示提供直接素材。【F:analysis/habitable_priority.py†L198-L244】

## 3. 分析模块详解
### 3.1 宜居候选优先级评分
- **候选体数量**：共 31 个行星满足数据完备性，其中 8 个进入 “High Priority” 阶段，11 个被标记为 “Follow-up”，体现高质量目标的稀缺性。【F:results/habitable_priority_scores.csv†L1-L12】
- **支柱解释**：
  - 气候支柱将温度、辐射、轨道周期与主星温度统一到 `[0,1]`，确保评分符合液态水条件。
  - 结构支柱强调 0.5–2.5 地球半径、0.3–10 地球质量的区间，兼顾岩质与海洋行星。
  - 可观测性支柱综合过境深度（以 ppm 计）、视星等与距离，突出最容易进行光谱跟踪的目标。
  - 系统支柱轻微惩罚多星系统，降低动力学不确定性。
- **可视化组合**：
  - 温度 vs 半径散点叠加宜居区窗口，展示优先级与可观测性权衡。【F:analysis/habitable_priority.py†L198-L220】
  - Pillar 条形图对比前 12 名候选体的支柱贡献，支持口头说明各指标的驱动因素。
  - 雷达图呈现前 5 名在四大支柱的平衡程度，为重点目标提供直观画像。
- **权威对照**：`results/habitable_authoritative_comparison.csv` 将内部评分与 PHL 权威列表对比，`phl_confidence` 字段用于识别与外部资料一致或存在差异的候选体。【F:analysis/habitable_priority.py†L208-L244】

### 3.2 互动式呈现
- `analysis/build_dashboard.py` 基于新版评分生成 Plotly 仪表板，包含优先级散点图、支柱堆叠条形图、可观测性相图及分档统计表，输出为 `webapp/index.html` 以满足“可视化会动的图片”要求。【F:analysis/build_dashboard.py†L1-L154】
- `analysis/ps_overview.py` 提供温度-半径散点、轨道周期箱线图、距离直方图三类背景图，为演示开场提供宏观上下文。【F:analysis/ps_overview.py†L19-L87】

## 4. 验证与质量控制
- `analysis/validate_analysis.py` 重新计算评分表，检查与存档 CSV 的行覆盖、分数一致性、分档标签、支柱权重等指标，并生成 `results/validation_report.json` 与 `results/validation_report.md` 总结 PASS/REVIEW 结果。【F:analysis/validate_analysis.py†L1-L135】
- 验证脚本还确认所有支柱与组件分数均处于 `[0,1]` 区间，观察到的最大偏差小于 `1e-6`，确保权重组合逻辑无误。

### 4.1 数据分析合理性复盘
- **外部基准对照**：与离线保存的 PHL 权威候选体清单逐一比对，`phl_confidence` 字段标记一致、偏高、偏低三种情形，用于解释与既有文献的差异来源，并在讲稿中着重说明高分却缺席权威榜单的原因（例如缺乏质量测量或星噪声不确定）。【F:analysis/habitable_priority.py†L208-L244】【F:results/habitable_authoritative_comparison.csv†L1-L22】
- **变量敏感性检查**：验证脚本重复计算四大支柱并与持久化 CSV 对比，任何单项分差超过 `1e-6` 会触发 `REVIEW` 标记，从而防止后续修改造成静默漂移。【F:analysis/validate_analysis.py†L77-L120】【F:results/validation_report.md†L1-L13】
- **采样充分性**：当前共有 31 颗行星满足数据完备性，占 `default_flag=1` 样本的 0.9%，其余记录因缺失关键参数或超出物理范围被排除；脚本在日志中输出被过滤原因，为 Q&A 准备充分的合理性解释。【F:analysis/habitable_priority.py†L63-L196】【F:results/habitable_priority_scores.csv†L1-L32】
- **权重可解释性**：权重设置（气候 0.45、结构 0.25、可观测性 0.22、系统 0.08）在文档与讲稿中保持一致，并通过 `results/validation_report.json` 的 `weight_check` 字段确认总和恒为 1；如需调参，可依赖脚本暴露的单支柱得分快速进行灵敏度分析。【F:analysis/habitable_priority.py†L154-L196】【F:results/validation_report.json†L1-L39】
- **可观测性现实约束**：可观测性支柱结合过境深度（ppm）、视星等与距离，确保推荐目标在 JWST / 罗曼 / ELT 的噪声阈值附近具备可行信噪比；如 TOI-2095 c 过境深度 ~768 ppm、视星等 13.19 等数据将在演讲中引用以支撑科学合理性。【F:analysis/habitable_priority.py†L132-L144】【F:results/habitable_priority_scores.csv†L1-L16】

## 5. 可视化资产与扩展
- **静态素材**：`analysis/habitable_priority.py` 运行后生成散点、柱状、雷达图；`analysis/ps_overview.py` 生成背景统计图。这些 PNG 文件保存在本地 `figures/` 目录，便于插入幻灯片或报告。
- **交互式网站**：`webapp/index.html` 集成四个 Plotly 图层，可直接部署或嵌入 DevPost 页面，支持鼠标悬停查看支柱得分、过境深度、观测设施等细节。
- **进一步展示形式**：可扩展为 Streamlit 或 Observable 应用，利用现成 CSV/HTML 输出快速构建互动故事线，如添加实时过滤器、支柱对比面板等。

## 6. 演示（Presentation）策略
### 7 分钟演讲大纲
1. **开场（0:00–0:45）**：介绍 CDC 赛题与 NASA 数据来源，强调宜居行星筛选对未来任务的重要性。
2. **问题定义（0:45–1:30）**：说明数据清洗标准与四大支柱框架，明确评分目标。
3. **支柱拆解（1:30–3:30）**：
   - 结合散点图说明气候支柱如何筛选温度、辐射与轨道期。
   - 展示柱状图，讲解结构与可观测性支柱对排序的影响。
   - 引入权威对照，解释为什么部分候选体获得高分或被降级。
4. **重点目标（3:30–5:00）**：使用雷达图与可观测性相图聚焦前 5 名，讨论潜在观测计划（JWST、罗曼、地面望远镜）。
5. **验证与复现（5:00–6:15）**：展示验证脚本、`validation_report.md` 与 dashboard 更新流程，强调结果可追溯性。
6. **展望与 Q&A（6:15–7:00）**：提出下一步（增加恒星活动度、接入噪声模型、时间窗排程），邀请评委提问。

### 演示辅助建议
- 在浏览器中预载 `webapp/index.html`，现场演示 hover、筛选效果，满足“会动的可视化”需求。
- 准备前 5 名候选体的关键数据（距地距离、过境深度、主星视星等）写入讲稿，便于 Q&A 快速回应。
- 备用素材：输出 `results/habitable_top20.md` 作为打印讲义或 DevPost 附件。

## 7. 科学意义与创新亮点
- **气候支柱基于物理边界**：使用梯形隶属函数近似 Kopparapu HZ 上下限，避免简单高斯距离造成的偏差，保证评分符合天体物理常识。
- **可观测性融合过境深度**：将行星/恒星半径转换为 ppm 过境深度，与视星等、距离共同决定后续光谱可行性，为资源排期提供更现实的依据。
- **权威对照与验证自动化**：自动生成与 PHL 列表的对比、支柱权重检查、分档统计，形成闭环 QA，减少人工核对成本。

## 8. 技术难点与解决方案
- **多指标归一化**：采用梯形隶属函数与逻辑函数代替单一高斯，使评分在关键阈值附近呈现平台效应，避免极端值对总分的过度影响。【F:analysis/habitable_priority.py†L85-L142】
- **过境深度计算**：利用行星半径与主星半径转换为 ppm，设置 `log10` 剪裁避免数值不稳定，并在观测支柱中给予 0.35 的权重，凸显光谱信号强度。【F:analysis/habitable_priority.py†L132-L142】
- **结果验证自动化**：`analysis/validate_analysis.py` 对支柱和总分进行再次加权计算，最大差异 <1e-6 并输出 `PASS/REVIEW` 表格，实现制度化 QA。【F:analysis/validate_analysis.py†L77-L120】

## 9. 复现与交付清单
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt` 安装依赖。【F:requirements.txt†L1-L8】
3. `python analysis/ps_overview.py` 生成背景图。
4. `python analysis/habitable_priority.py` 生成宜居评分、可视化与对照表。
5. `python analysis/validate_analysis.py` 产出验证报告，确认关键数字无误。
6. `python analysis/build_dashboard.py` 更新交互式网页，可直接在浏览器打开 `webapp/index.html`。
7. 运行脚本生成图像后，将本地 `figures/`、`results/`、`webapp/` 与本文档一并提交至 DevPost，满足黑客松的“代码 + 可视化 + 文档”要求。

> **AI 使用说明**：本项目在构思与编码阶段辅助参考了生成式 AI（ChatGPT），所有最终脚本与文档均经人工审阅和验证，确保满足 CDC 关于引用与诚信的规定。
