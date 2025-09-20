"""Habitable zone candidate prioritisation for confirmed exoplanets."""

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

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "PS_2025.09.20_08.15.55.csv"
FIG_DIR = ROOT / "figures" / "habitability"
RESULTS_DIR = ROOT / "results"
AUTHORITATIVE_SAMPLE_PATH = ROOT / "data" / "authoritative_habitable_sample.csv"
PHL_CATALOG_URL = (
    "https://phl.upr.edu/projects/habitable-exoplanets-catalog/data/"
    "habitable_exoplanets_catalog.csv"
)

FIG_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")

REQUIRED_COLUMNS = [
    "pl_name",
    "hostname",
    "pl_eqt",
    "pl_rade",
    "pl_insol",
    "pl_orbper",
    "st_teff",
    "st_rad",
    "sy_vmag",
    "sy_snum",
]


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def load_planet_catalog() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, comment="#")
    df = df[df["default_flag"] == 1].copy()
    return df


def select_habitable_inputs(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to systems with complete measurements for scoring."""

    filtered = df.dropna(subset=REQUIRED_COLUMNS).copy()

    # Remove clear outliers that distort scoring ranges
    filtered = filtered[filtered["pl_rade"] <= filtered["pl_rade"].quantile(0.99)]
    filtered = filtered[filtered["pl_eqt"].between(150, 450)]
    filtered = filtered[filtered["pl_insol"].between(0.05, 5)]
    filtered = filtered[filtered["pl_orbper"].between(1, 800)]
    filtered = filtered[filtered["st_teff"].between(3500, 7500)]
    filtered = filtered[filtered["sy_vmag"].between(0, 18)]

    return filtered


# ---------------------------------------------------------------------------
# Scoring model
# ---------------------------------------------------------------------------

def sigmoid(x: np.ndarray, midpoint: float, steepness: float) -> np.ndarray:
    return 1 / (1 + np.exp((x - midpoint) / steepness))


def compute_priority_scores(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()

    data.loc[:, "temp_score"] = np.exp(-((data["pl_eqt"] - 288) / 60) ** 2)
    data.loc[:, "radius_score"] = np.exp(-((data["pl_rade"] - 1) / 0.35) ** 2)
    data.loc[:, "insolation_score"] = np.exp(-((data["pl_insol"] - 1) / 0.5) ** 2)

    log_period = np.log10(data["pl_orbper"])
    data.loc[:, "period_score"] = np.exp(-((log_period - np.log10(365)) / 0.3) ** 2)

    data.loc[:, "stellar_temp_score"] = np.exp(-((data["st_teff"] - 5778) / 800) ** 2)

    data.loc[:, "observability_score"] = sigmoid(data["sy_vmag"], midpoint=11.5, steepness=1.8)

    data.loc[:, "system_score"] = np.where(data["sy_snum"] == 1, 1.0, 0.75)

    weights = {
        "temp_score": 0.24,
        "radius_score": 0.22,
        "insolation_score": 0.16,
        "period_score": 0.14,
        "stellar_temp_score": 0.14,
        "observability_score": 0.07,
        "system_score": 0.03,
    }

    total = sum(weights.values())
    data.loc[:, "priority_score"] = sum(data[k] * v for k, v in weights.items()) / total

    bins = [0, 0.55, 0.7, 1.0]
    labels = ["Context", "Follow-up", "High Priority"]
    data.loc[:, "priority_band"] = pd.cut(data["priority_score"], bins=bins, labels=labels, include_lowest=True)

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
# Visualisation helpers
# ---------------------------------------------------------------------------

def plot_temp_radius(priority_df: pd.DataFrame) -> None:
    plt.figure(figsize=(10, 6))
    scatter = sns.scatterplot(
        data=priority_df,
        x="pl_eqt",
        y="pl_rade",
        hue="priority_score",
        size="observability_score",
        palette="viridis",
        alpha=0.7,
        edgecolor="none",
    )
    scatter.set(
        title="Habitable zone priority landscape",
        xlabel="Planet equilibrium temperature (K)",
        ylabel="Planet radius (Earth radii)",
    )
    plt.axvspan(240, 320, color="lightgray", alpha=0.2, label="Classical habitable band")
    plt.axhspan(0.7, 1.6, color="lightblue", alpha=0.2, label="Earth-size range")
    plt.legend(loc="upper right", title="Priority score")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "temp_radius_priority.png", dpi=300)
    plt.close()


def plot_component_bars(priority_df: pd.DataFrame, top_n: int = 15) -> None:
    components = [
        "temp_score",
        "radius_score",
        "insolation_score",
        "period_score",
        "stellar_temp_score",
        "observability_score",
        "system_score",
    ]
    melted = priority_df.head(top_n).melt(
        id_vars=["pl_name", "priority_score"],
        value_vars=components,
        var_name="component",
        value_name="score",
    )
    plt.figure(figsize=(11, 7))
    sns.barplot(
        data=melted,
        y="pl_name",
        x="score",
        hue="component",
        order=priority_df.head(top_n)["pl_name"],
        orient="h",
    )
    plt.title("Score composition for top habitable candidates")
    plt.xlabel("Component score")
    plt.ylabel("Planet")
    plt.xlim(0, 1.05)
    plt.legend(title="Component", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "priority_components.png", dpi=300)
    plt.close()


def plot_radar_top(priority_df: pd.DataFrame, top_n: int = 5) -> None:
    features = [
        "temp_score",
        "radius_score",
        "insolation_score",
        "period_score",
        "stellar_temp_score",
        "observability_score",
        "system_score",
    ]
    top = priority_df.head(top_n)
    angles = np.linspace(0, 2 * np.pi, len(features), endpoint=False)
    angles = np.concatenate([angles, angles[:1]])

    plt.figure(figsize=(8, 8))
    ax = plt.subplot(111, polar=True)

    for _, row in top.iterrows():
        values = row[features].values
        values = np.concatenate([values, values[:1]])
        ax.plot(angles, values, label=row["pl_name"])
        ax.fill(angles, values, alpha=0.1)

    ax.set_xticks(np.linspace(0, 2 * np.pi, len(features), endpoint=False))
    ax.set_xticklabels([feat.replace("_", "\n") for feat in features])
    ax.set_ylim(0, 1)
    ax.set_title("Multi-metric profile of leading targets")
    ax.legend(loc="upper right", bbox_to_anchor=(1.4, 1.1))
    plt.tight_layout()
    plt.savefig(FIG_DIR / "priority_radar.png", dpi=300)
    plt.close()


# ---------------------------------------------------------------------------
# Reporting utilities
# ---------------------------------------------------------------------------

def summarise_priority(priority_df: pd.DataFrame) -> Dict[str, float]:
    summary = {
        "candidate_count": len(priority_df),
        "high_priority_share": (priority_df["priority_band"] == "High Priority").mean(),
        "follow_up_share": (priority_df["priority_band"] == "Follow-up").mean(),
        "median_score": float(priority_df["priority_score"].median()),
    }
    return summary


def save_priority_tables(priority_df: pd.DataFrame) -> None:
    """Persist master scoring table and markdown export of the top cohort."""
    priority_df.to_csv(RESULTS_DIR / "habitable_priority_scores.csv", index=False)
    top_table = priority_df.head(20).copy()
    top_table.to_markdown(RESULTS_DIR / "habitable_top20.md", index=False)


# ---------------------------------------------------------------------------
# External validation helpers
# ---------------------------------------------------------------------------

def load_authoritative_catalog() -> Optional[pd.DataFrame]:
    """Load the authoritative habitable exoplanet catalog if available.

    The function first attempts to download the latest Puerto Rico Habitable
    Exoplanet Catalog (PHL HEC). Because network access may be locked down in
    hackathon environments, any error (e.g., HTTP 403) falls back to the
    curated local sample assembled from NASA Exoplanet Archive entries. If both
    sources fail the function returns ``None`` so downstream callers can skip
    the comparison gracefully.
    """

    try:
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
        # Standardise the column names that hold the canonical planet label.
        name_column = None
        for candidate in ("P. Name", "Planet", "pl_name"):
            if candidate in remote.columns:
                name_column = candidate
                break
        if name_column is None:
            raise ValueError("Unable to locate planet name column in PHL feed")
        remote = remote.rename(columns={name_column: "pl_name"})
        remote["pl_name"] = remote["pl_name"].astype(str).str.strip()
        remote["reference_source"] = "PHL Habitable Exoplanets Catalog"
        return remote
    except (URLError, ValueError, TimeoutError, pd.errors.ParserError) as exc:
        print(
            "Warning: Could not download the PHL Habitable Exoplanets Catalog. "
            f"Details: {exc}."
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        print(
            "Warning: Unexpected error while downloading PHL catalog; "
            f"falling back to local sample. Details: {exc}."
        )

    if AUTHORITATIVE_SAMPLE_PATH.exists():
        local = pd.read_csv(AUTHORITATIVE_SAMPLE_PATH)
        local["pl_name"] = local["pl_name"].astype(str).str.strip()
        if "reference_source" not in local.columns:
            local["reference_source"] = "Curated NASA Exoplanet Archive sample"
        return local

    print(
        "Warning: No authoritative habitable reference catalog available. "
        "Skip cross-check step."
    )
    return None


def compare_with_authoritative_catalog(priority_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Cross-check high-priority targets against an authoritative catalog."""

    authoritative = load_authoritative_catalog()
    if authoritative is None:
        return None

    # Focus on highest-tier candidates to avoid cluttering the comparison table.
    shortlist = priority_df.head(50).copy()
    shortlist["pl_name"] = shortlist["pl_name"].astype(str).str.strip()

    merged = shortlist.merge(
        authoritative[["pl_name", "reference_source"]].drop_duplicates(),
        on="pl_name",
        how="left",
        indicator=True,
    )
    merged = merged.rename(columns={"_merge": "authoritative_match"})
    merged["authoritative_match"] = merged["authoritative_match"].map(
        {"left_only": "Not in reference", "both": "Match", "right_only": "Reference only"}
    )

    merged.sort_values("priority_score", ascending=False, inplace=True)
    merged.to_csv(RESULTS_DIR / "habitable_authoritative_comparison.csv", index=False)

    match_rate = (merged["authoritative_match"] == "Match").mean()
    print(f"Authoritative catalog match rate (top 50): {match_rate:.2%}")

    return merged


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

def main() -> None:
    df = load_planet_catalog()
    inputs = select_habitable_inputs(df)
    priority = compute_priority_scores(inputs)

    save_priority_tables(priority)

    plot_temp_radius(priority)
    plot_component_bars(priority)
    plot_radar_top(priority)

    summary = summarise_priority(priority)
    for key, value in summary.items():
        print(f"{key}: {value}")

    compare_with_authoritative_catalog(priority)


if __name__ == "__main__":
    main()
