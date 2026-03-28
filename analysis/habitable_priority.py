"""宜居带候选行星优先级排序系统 - 用于确认的系外行星数据

本模块实现了多维度评分模型，用于识别和优先排序最有可能支持生命的系外行星。
评分基于温度、半径、辐射通量、轨道周期、恒星温度、可观测性和系统复杂度等七个维度。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# 设置项目根目录和文件路径
ROOT = Path(__file__).resolve().parents[1]  # 项目根目录
DATA_PATH = ROOT / "PS_2025.09.20_08.15.55.csv"  # 主要数据文件路径
FIG_DIR = ROOT / "figures" / "habitability"  # 图表保存目录
RESULTS_DIR = ROOT / "results"  # 结果保存目录
AUTHORITATIVE_SAMPLE_PATH = ROOT / "data" / "authoritative_habitable_sample.csv"  # 权威样本数据路径

# 波多黎各大学宜居系外行星目录的在线URL
PHL_CATALOG_URL = (
    "https://phl.upr.edu/projects/habitable-exoplanets-catalog/data/"
    "habitable_exoplanets_catalog.csv"
)

# 创建必要的目录
FIG_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# 设置图表样式
sns.set_theme(style="whitegrid")
# 提升演示观感：放大字号、统一配色、增强网格
sns.set_context("talk", font_scale=1.05)
sns.set_palette("colorblind")
import matplotlib as mpl
mpl.rcParams.update({
    "figure.dpi": 140,
    "savefig.dpi": 300,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})

# 评分系统所需的必需列名
REQUIRED_COLUMNS = [
    "pl_name",      # 行星名称
    "hostname",     # 宿主恒星名称
    "pl_eqt",       # 行星平衡温度
    "pl_rade",      # 行星半径（地球半径）
    "pl_insol",     # 行星辐射通量（地球辐射）
    "pl_orbper",    # 轨道周期（天）
    "st_teff",      # 恒星有效温度
    # "st_rad",     # 移除：恒星半径不参与评分，避免无谓丢数
    "sy_vmag",      # 系统视星等
    "sy_snum",      # 系统中行星数量
]


# ---------------------------------------------------------------------------
# 数据准备模块
# ---------------------------------------------------------------------------

def load_planet_catalog() -> pd.DataFrame:
    """加载行星目录数据
    
    从CSV文件中读取所有确认的系外行星数据，只保留默认标志为1的行。
    
    Returns:
        pd.DataFrame: 包含所有确认系外行星数据的DataFrame
    """
    df = pd.read_csv(DATA_PATH, comment="#")
    df = df[df["default_flag"] == 1].copy()  # 只保留默认标志为1的行
    return df


def select_habitable_inputs(df: pd.DataFrame) -> pd.DataFrame:
    """筛选具有完整测量数据的系统用于评分
    
    这个函数执行以下筛选步骤：
    1. 移除所有必需列中有缺失值的行
    2. 移除明显的异常值，这些异常值会扭曲评分范围
    3. 应用保守的物理边界来确保数据的合理性
    
    Args:
        df: 原始行星目录数据
        
    Returns:
        pd.DataFrame: 筛选后的数据，包含所有必需列且无异常值
    """
    # 移除必需列中的缺失值
    filtered = df.dropna(subset=REQUIRED_COLUMNS).copy()

    # 移除明显的异常值，这些异常值会扭曲评分范围
    filtered = filtered[filtered["pl_rade"] <= filtered["pl_rade"].quantile(0.99)]  # 行星半径不超过99分位数
    filtered = filtered[filtered["pl_eqt"].between(150, 450)]  # 平衡温度在150-450K之间
    filtered = filtered[filtered["pl_insol"].between(0.05, 5)]  # 辐射通量在0.05-5之间
    filtered = filtered[filtered["pl_orbper"].between(0.5, 1200)]  # 放宽轨道周期范围
    filtered = filtered[filtered["st_teff"].between(2500, 7500)]   # 放宽恒星温度范围，覆盖M矮星
    # 移除对V带视星等的硬过滤，改由评分体现可观测性

    return filtered


# ---------------------------------------------------------------------------
# 评分模型模块
# ---------------------------------------------------------------------------

def sigmoid(x: np.ndarray, midpoint: float, steepness: float) -> np.ndarray:
    """S型函数，用于表示递减回报或阈值效应
    
    Args:
        x: 输入值数组
        midpoint: 中点值，函数在此处值为0.5
        steepness: 陡峭度，值越大函数变化越陡峭
        
    Returns:
        np.ndarray: S型函数输出值，范围在0-1之间
    """
    return 1 / (1 + np.exp((x - midpoint) / steepness))


def compute_priority_scores(df: pd.DataFrame) -> pd.DataFrame:
    """计算宜居行星优先级评分
    
    基于七个维度计算每个行星的优先级评分：
    1. 温度适宜性：基于高斯函数，288K附近最优
    2. 半径适宜性：基于高斯函数，1地球半径附近最优
    3. 辐射通量：基于高斯函数，1地球辐射附近最优
    4. 轨道周期：基于高斯函数，365天附近最优
    5. 恒星温度：基于高斯函数，5778K附近最优
    6. 可观测性：基于S型函数，视星等越小越好
    7. 系统复杂度：单行星系统优先
    
    Args:
        df: 筛选后的行星数据
        
    Returns:
        pd.DataFrame: 包含所有评分和优先级分组的DataFrame
    """
    data = df.copy()

    # 1. 温度适宜性评分 - 基于高斯函数，288K附近最优
    # 使用高斯函数：exp(-((x - 中心值) / 标准差)²)
    data.loc[:, "temp_score"] = np.exp(-((data["pl_eqt"] - 288) / 60) ** 2)

    # 2. 半径适宜性评分 - 基于高斯函数，1地球半径附近最优
    # 修复：调整参数以适应实际数据分布，使用更合理的标准差
    data.loc[:, "radius_score"] = np.exp(-((data["pl_rade"] - 1) / 1.0) ** 2)

    # 3. 辐射通量评分 - 基于高斯函数，1地球辐射附近最优
    data.loc[:, "insolation_score"] = np.exp(-((data["pl_insol"] - 1) / 0.5) ** 2)

    # 4. 轨道周期评分 - 使用相对宜居带周期而非固定365天，减少对M矮星的偏见
    # 近似把宜居带轨道期设为与恒星有效温度的函数：
    # 对于太阳(5778K)取365天；对更冷的M矮星缩短周期(指数缩放)，更热恒星延长周期
    # 经验缩放：P_hz ≈ 365 * (st_teff/5778)^1.5，避免对数空间中严重惩罚M矮星
    with np.errstate(invalid="ignore"):
        period_hz = 365.0 * np.power(np.clip(data["st_teff"], 2500, 7500) / 5778.0, 1.5)
        log_ratio = np.log10(data["pl_orbper"] / period_hz)
    data.loc[:, "period_score"] = np.exp(-(log_ratio / 0.35) ** 2)

    # 5. 恒星温度评分 - 放宽带宽，避免将M矮星温度强惩罚
    data.loc[:, "stellar_temp_score"] = np.exp(-((data["st_teff"] - 5200) / 1800) ** 2)

    # 6. 可观测性评分 - 基于S型函数，视星等越小越好
    # 中点设为11.5等，陡峭度为1.8
    data.loc[:, "observability_score"] = sigmoid(data["sy_vmag"], midpoint=11.5, steepness=1.8)

    # 7. 系统复杂度评分 - 单行星系统优先
    # 单行星系统得1.0分，多行星系统得0.75分
    data.loc[:, "system_score"] = np.where(data["sy_snum"] == 1, 1.0, 0.75)

    # 定义各维度权重
    weights = {
        "temp_score": 0.24,           # 维持温度为核心
        "radius_score": 0.22,         # 维持半径为重要约束
        "insolation_score": 0.18,     # 略增辐射通量权重以替代周期约束
        "period_score": 0.08,         # 降低周期权重（已用相对周期修正）
        "stellar_temp_score": 0.06,   # 大幅降低恒星温度权重
        "observability_score": 0.18,  # 提升可观测性（但不做硬过滤）
        "system_score": 0.04,         # 略微提高系统简洁度
    }

    # 计算加权平均优先级评分
    total = sum(weights.values())
    data.loc[:, "priority_score"] = sum(data[k] * v for k, v in weights.items()) / total

    # 将行星分为三个优先级组
    bins = [0, 0.55, 0.7, 1.0]
    labels = ["Context", "Follow-up", "High Priority"]
    data.loc[:, "priority_band"] = pd.cut(data["priority_score"], bins=bins, labels=labels, include_lowest=True)

    # 选择要返回的列
    cols = REQUIRED_COLUMNS + [
        "temp_score",
        "radius_score",
        "insolation_score",
        "period_score",
        "stellar_temp_score",
        "observability_score",
        "system_score",
        "priority_score",
        "priority_band",
    ]
    return data[cols].sort_values("priority_score", ascending=False)


# ---------------------------------------------------------------------------
# 可视化辅助函数模块
# ---------------------------------------------------------------------------

def plot_temp_radius(priority_df: pd.DataFrame) -> None:
    """绘制温度-半径散点图，显示宜居带优先级分布
    
    Args:
        priority_df: 包含优先级评分的DataFrame
    """
    plt.figure(figsize=(11, 7))
    # 使用一致的归一化以匹配色条
    norm = mpl.colors.Normalize(vmin=priority_df["priority_score"].min(), vmax=priority_df["priority_score"].max())
    scatter = sns.scatterplot(
        data=priority_df,
        x="pl_eqt",                    # X轴：行星平衡温度
        y="pl_rade",                   # Y轴：行星半径
        hue="priority_score",          # 颜色：优先级评分
        size="observability_score",    # 大小：可观测性评分
        sizes=(20, 220),                # 提升层次感
        linewidth=0.2,                  # 细边框
        edgecolor="white",
        palette="viridis",             # 调色板
        hue_norm=norm,
        alpha=0.85,                     # 稍高透明度
        legend=False,                   # 用色条替代图例
    )
    scatter.set(
        title="Habitable Zone Priority Landscape",
        xlabel="Planet Equilibrium Temperature (K)",
        ylabel="Planet Radius (Earth radii)",
    )
    # 添加经典宜居带标记
    plt.axvspan(240, 320, color="lightgray", alpha=0.2, label="Classical Habitable Zone")
    # 添加地球大小范围标记
    plt.axhspan(0.7, 1.6, color="lightblue", alpha=0.2, label="Earth-size Range")
    # 连续色条代替离散图例，更专业
    sm = plt.cm.ScalarMappable(cmap="viridis", norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, ax=plt.gca(), pad=0.02)
    cbar.set_label("Priority Score")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "temp_radius_priority.png", dpi=300)
    plt.close()


def plot_component_bars(priority_df: pd.DataFrame, top_n: int = 15) -> None:
    """绘制前N个候选行星的评分组成条形图
    
    Args:
        priority_df: 包含优先级评分的DataFrame
        top_n: 显示前N个行星，默认15个
    """
    components = [
        "temp_score",
        "radius_score",
        "insolation_score",
        "period_score",
        "stellar_temp_score",
        "observability_score",
        "system_score",
    ]
    # 将数据转换为长格式，便于绘制分组条形图
    melted = priority_df.head(top_n).melt(
        id_vars=["pl_name", "priority_score"],
        value_vars=components,
        var_name="component",
        value_name="score",
    )
    plt.figure(figsize=(12, 8))
    sns.barplot(
        data=melted,
        y="pl_name",
        x="score",
        hue="component",
        order=priority_df.head(top_n)["pl_name"],
        orient="h",
        edgecolor="white",
        linewidth=0.5,
    )
    plt.title("Score Composition for Top 15 Habitable Candidates")
    plt.xlabel("Component Score")
    plt.ylabel("Planet")
    plt.xlim(0, 1.05)
    plt.legend(title="Component", bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "priority_components.png", dpi=300)
    plt.close()


def plot_radar_comparison(priority_df: pd.DataFrame, top_n: int = 5) -> None:
    """绘制前N名和后N名候选行星的对比雷达图
    
    Args:
        priority_df: 包含优先级评分的DataFrame
        top_n: 显示前N个和后N个行星，默认5个
    """
    features = [
        "temp_score",
        "radius_score",
        "insolation_score",
        "period_score",
        "stellar_temp_score",
        "observability_score",
        "system_score",
    ]
    
    # 获取前N名和后N名
    top_candidates = priority_df.head(top_n)
    bottom_candidates = priority_df.tail(top_n)
    
    # 计算雷达图的角度
    angles = np.linspace(0, 2 * np.pi, len(features), endpoint=False)
    angles = np.concatenate([angles, angles[:1]])  # 闭合图形

    # 创建子图
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8), subplot_kw=dict(projection='polar'))
    
    # 绘制前N名
    ax1.set_title("Top 5 Candidates", pad=20, fontsize=14, fontweight='bold')
    for _, row in top_candidates.iterrows():
        values = row[features].values
        values = np.concatenate([values, values[:1]])  # 闭合图形
        ax1.plot(angles, values, label=row["pl_name"], linewidth=2)
        ax1.fill(angles, values, alpha=0.1)
    
    # 设置前N名雷达图格式
    ax1.set_xticks(np.linspace(0, 2 * np.pi, len(features), endpoint=False))
    ax1.set_xticklabels([feat.replace("_", "\n") for feat in features])
    ax1.set_ylim(0, 1)
    ax1.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)
    ax1.grid(True, alpha=0.3)
    
    # 绘制后N名
    ax2.set_title("Bottom 5 Candidates", pad=20, fontsize=14, fontweight='bold')
    for _, row in bottom_candidates.iterrows():
        values = row[features].values
        values = np.concatenate([values, values[:1]])  # 闭合图形
        ax2.plot(angles, values, label=row["pl_name"], linewidth=2)
        ax2.fill(angles, values, alpha=0.1)
    
    # 设置后N名雷达图格式
    ax2.set_xticks(np.linspace(0, 2 * np.pi, len(features), endpoint=False))
    ax2.set_xticklabels([feat.replace("_", "\n") for feat in features])
    ax2.set_ylim(0, 1)
    ax2.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)
    ax2.grid(True, alpha=0.3)
    
    # 添加总标题
    fig.suptitle("Multi-metric Profile Comparison: Top vs Bottom Candidates", 
                 fontsize=16, fontweight='bold', y=0.95)
    
    plt.tight_layout()
    plt.savefig(FIG_DIR / "priority_radar_comparison.png", dpi=300, bbox_inches='tight')
    plt.close()


# ---------------------------------------------------------------------------
# 报告生成工具模块
# ---------------------------------------------------------------------------

def summarise_priority(priority_df: pd.DataFrame) -> Dict[str, float]:
    """生成优先级评分的统计摘要
    
    Args:
        priority_df: 包含优先级评分的DataFrame
        
    Returns:
        Dict[str, float]: 包含统计摘要的字典
    """
    summary = {
        "candidate_count": len(priority_df),  # 候选行星总数
        "high_priority_share": (priority_df["priority_band"] == "High Priority").mean(),  # 高优先级比例
        "follow_up_share": (priority_df["priority_band"] == "Follow-up").mean(),  # 跟进优先级比例
        "median_score": float(priority_df["priority_score"].median()),  # 中位数评分
    }
    return summary


def save_priority_tables(priority_df: pd.DataFrame) -> None:
    """保存优先级评分表和前20名候选行星的Markdown报告
    
    Args:
        priority_df: 包含优先级评分的DataFrame
    """
    # 保存完整的评分表
    priority_df.to_csv(RESULTS_DIR / "habitable_priority_scores.csv", index=False)
    # 保存前20名的Markdown报告
    top_table = priority_df.head(20).copy()
    top_table.to_markdown(RESULTS_DIR / "habitable_top20.md", index=False)


# ---------------------------------------------------------------------------
# 外部验证辅助函数模块
# ---------------------------------------------------------------------------

def load_authoritative_catalog() -> Optional[pd.DataFrame]:
    """加载权威的宜居系外行星目录
    
    首先尝试下载最新的波多黎各大学宜居系外行星目录(PHL HEC)。
    由于网络访问可能在黑客马拉松环境中被锁定，任何错误(如HTTP 403)都会
    回退到从NASA系外行星档案条目组装的本地样本。如果两个源都失败，
    函数返回None，以便下游调用者可以优雅地跳过比较步骤。
    
    Returns:
        Optional[pd.DataFrame]: 权威目录数据，如果加载失败则返回None
    """
    try:
        # 尝试下载在线目录
        request = Request(
            PHL_CATALOG_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (CDC Hackathon analysis)",
                "Accept": "text/csv",
            },
        )
        with urlopen(request, timeout=15) as response:
            payload = response.read()
        remote = pd.read_csv(BytesIO(payload))
        
        # 标准化包含规范行星标签的列名
        name_column = None
        for candidate in ("P. Name", "Planet", "pl_name"):
            if candidate in remote.columns:
                name_column = candidate
                break
        if name_column is None:
            raise ValueError("无法在PHL数据源中找到行星名称列")
        remote = remote.rename(columns={name_column: "pl_name"})
        remote["pl_name"] = remote["pl_name"].astype(str).str.strip()
        remote["reference_source"] = "PHL宜居系外行星目录"
        return remote
        
    except (URLError, ValueError, TimeoutError, pd.errors.ParserError) as exc:
        print(
            "警告：无法下载PHL宜居系外行星目录。"
            f"详细信息：{exc}。"
        )
    except Exception as exc:  # pragma: no cover - 防御性日志记录
        print(
            "警告：下载PHL目录时发生意外错误；"
            f"回退到本地样本。详细信息：{exc}。"
        )

    # 如果在线下载失败，尝试使用本地样本
    if AUTHORITATIVE_SAMPLE_PATH.exists():
        local = pd.read_csv(AUTHORITATIVE_SAMPLE_PATH)
        local["pl_name"] = local["pl_name"].astype(str).str.strip()
        if "reference_source" not in local.columns:
            local["reference_source"] = "精选NASA系外行星档案样本"
        return local

    print(
        "警告：没有可用的权威宜居参考目录。"
        "跳过交叉检查步骤。"
    )
    return None


def compare_with_authoritative_catalog(priority_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """将高优先级目标与权威目录进行交叉检查
    
    Args:
        priority_df: 包含优先级评分的DataFrame
        
    Returns:
        Optional[pd.DataFrame]: 比较结果，如果无法加载权威目录则返回None
    """
    # 加载权威目录
    authoritative = load_authoritative_catalog()
    if authoritative is None:
        return None

    # 专注于最高层级的候选行星，避免比较表过于杂乱
    shortlist = priority_df.head(50).copy()
    shortlist["pl_name"] = shortlist["pl_name"].astype(str).str.strip()

    # 合并数据，检查匹配情况
    merged = shortlist.merge(
        authoritative[["pl_name", "reference_source"]].drop_duplicates(),
        on="pl_name",
        how="left",
        indicator=True,
    )
    merged = merged.rename(columns={"_merge": "authoritative_match"})
    merged["authoritative_match"] = merged["authoritative_match"].map(
        {"left_only": "不在参考中", "both": "匹配", "right_only": "仅参考"}
    )

    # 按优先级评分排序
    merged.sort_values("priority_score", ascending=False, inplace=True)
    merged.to_csv(RESULTS_DIR / "habitable_authoritative_comparison.csv", index=False)

    # 计算匹配率
    match_rate = (merged["authoritative_match"] == "匹配").mean()
    print(f"权威目录匹配率（前50名）：{match_rate:.2%}")

    return merged


# ---------------------------------------------------------------------------
# 主执行模块
# ---------------------------------------------------------------------------

def main() -> None:
    """主函数：执行完整的宜居行星优先级分析流程
    
    流程包括：
    1. 加载行星目录数据
    2. 筛选具有完整测量数据的系统
    3. 计算优先级评分
    4. 保存评分表和报告
    5. 生成可视化图表
    6. 打印统计摘要
    7. 与权威目录进行交叉验证
    """
    # 1. 加载数据
    df = load_planet_catalog()
    
    # 2. 筛选数据
    inputs = select_habitable_inputs(df)
    
    # 3. 计算优先级评分
    priority = compute_priority_scores(inputs)

    # 4. 保存结果
    save_priority_tables(priority)

    # 5. 生成可视化图表
    plot_temp_radius(priority)
    plot_component_bars(priority)
    plot_radar_comparison(priority)

    # 6. 打印统计摘要
    summary = summarise_priority(priority)
    for key, value in summary.items():
        print(f"{key}: {value}")

    # 7. 与权威目录进行交叉验证
    compare_with_authoritative_catalog(priority)


if __name__ == "__main__":
    main()
