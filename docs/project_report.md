# NASA 行星系统项目：宜居优先级

## 项目总览
- **数据来源**：NASA Exoplanet Archive Planetary Systems 表（版本 `PS_2025.09.20_08.15.55.csv`），所有分析仅保留 `default_flag=1` 的标准参数集，避免重复记录。
- **交付内容**：单一主线分析脚本（`analysis/habitable_priority.py`）及其配套工具（`analysis/ps_overview.py`、`analysis/validate_analysis.py`、`analysis/build_dashboard.py`）、结果表格（`results/*.csv`、`results/habitable_top20.md`）与说明文档（本文及 `docs/final_documentation.md`）。
- **创新亮点**：
  1. 基于物理边界的四支柱评分模型（气候、结构、可观测性、系统稳定性），兼顾科学潜力与实际观测可行性。
  2. 自动化 QA 流程与权威样本对照，确保评分与外部数据一致且可复现。
  3. 交互式 Plotly 仪表板 + 静态图组合，满足黑客松对“会动的可视化”与演示素材的双重需求。

---

## 数据处理与评分流程
1. **数据读入**：`load_planet_catalog()` 读取 NASA CSV，并过滤 `default_flag=1`。【F:analysis/habitable_priority.py†L48-L60】
2. **候选筛选**：`select_habitable_inputs()` 删除缺失关键指标的记录，并限制温度、入射辐射（缺失时按 `(T/255K)^4` 估算）、半径、质量、轨道周期、主星参数、视星等、距离等区间，最终保留 31 个可评分行星。【F:analysis/habitable_priority.py†L63-L112】
3. **支柱构建**：
   - 气候：对温度、辐射、轨道周期、主星温度使用梯形隶属函数，确保评分集中在合理的液态水区间。【F:analysis/habitable_priority.py†L87-L113】
   - 结构：半径与质量梯形函数突出类地或海洋行星。【F:analysis/habitable_priority.py†L115-L121】
   - 可观测性：计算过境深度（ppm）并结合视星等、距离，通过逻辑函数形成可观测性评分。【F:analysis/habitable_priority.py†L123-L142】
   - 系统：对多星系统施加轻微惩罚，避免复杂动力学带来的排期风险。【F:analysis/habitable_priority.py†L144-L152】
4. **权重聚合**：气候 0.45、结构 0.25、可观测性 0.22、系统 0.08，生成最终 `priority_score`；根据阈值划分 `Context` / `Follow-up` / `High Priority`。【F:analysis/habitable_priority.py†L154-L196】
5. **结果导出**：`results/habitable_priority_scores.csv`、`results/habitable_top20.md`、`results/habitable_authoritative_comparison.csv` 等文件记录完整表格与对照结果；图像保存在 `figures/habitability/`（本地生成，未纳入 git）。【F:analysis/habitable_priority.py†L198-L244】

---

## 关键发现
- **优先级概况**：31 个行星中，仅有 8 个进入 “High Priority” 档，11 个进入 “Follow-up”，体现高质量目标的稀缺性。【F:results/habitable_priority_scores.csv†L1-L12】
- **高分目标特征**：
  - 气候支柱集中在 260–310 K、入射辐射 0.4–1.6 `S_⊕`、轨道周期 30–300 天、主星温度 4000–6300 K。
  - 结构支柱偏好 0.8–1.8 地球半径、0.5–7 地球质量的组合。
  - 可观测性支柱偏好视星等 <12.5、距离 <150 pc、过境深度 >250 ppm 的系统。
- **权威对照**：多数高优先级候选体与 PHL 样本一致，对未入榜但得分高的行星（如近期 TESS 发现）可作为提案亮点。【F:results/habitable_authoritative_comparison.csv†L1-L10】

---

## 交互式与静态呈现
- **Plotly 仪表板**：`analysis/build_dashboard.py` 将优先级散点、支柱堆叠条形、可观测性相图、分档统计表整合为 `webapp/index.html`，可直接在演示中操作。【F:analysis/build_dashboard.py†L1-L154】
- **静态图**：
  - 温度 vs 半径散点强调优先级与可观测性关系。【F:analysis/habitable_priority.py†L198-L214】
  - 支柱条形图展示前 12 名目标的支柱权重差异。【F:analysis/habitable_priority.py†L216-L229】
  - 雷达图比较前 5 名候选体的多支柱平衡。【F:analysis/habitable_priority.py†L231-L244】
  - 背景图（温度-半径散点、轨道周期箱线图、距离直方图）由 `analysis/ps_overview.py` 提供，帮助在演讲开场建立上下文。【F:analysis/ps_overview.py†L26-L87】

---

## 技术难点与解决方案
- **多指标归一化**：采用梯形隶属函数与逻辑函数，避免旧版高斯评分在阈值附近过度衰减，保证高分段呈现平台效应。【F:analysis/habitable_priority.py†L87-L138】
- **过境深度稳定性**：计算时对深度进行剪裁（≥5 ppm）并在 log 空间计算逻辑函数，消除极小值导致的数值问题。【F:analysis/habitable_priority.py†L132-L138】
- **权重校验**：`analysis/validate_analysis.py` 重新加权可观测性与总分，最大误差 <1e-6 并输出 `PASS/REVIEW` 表，确保存档结果与现算一致。【F:analysis/validate_analysis.py†L77-L120】

---

## 复现步骤
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `python analysis/ps_overview.py`
4. `python analysis/habitable_priority.py`
5. `python analysis/validate_analysis.py`
6. `python analysis/build_dashboard.py`

运行完成后检查 `results/`、`figures/`、`webapp/` 是否已更新；将 `results/habitable_top20.md`、`results/habitable_priority_scores.csv`、`webapp/index.html` 作为 DevPost 交付物核心附件。

---

## 致谢与合规说明
- `data/authoritative_habitable_sample.csv` 基于公开 NASA 公告整理，便于在无网络环境下完成权威对照。【F:data/authoritative_habitable_sample.csv†L1-L12】
- 本项目在黑客松规定下使用了生成式 AI（ChatGPT）辅助构思与编码，所有脚本与文档均经人工审核与测试，确保满足 CDC 关于引用与诚信的要求。
