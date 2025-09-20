"""Exploratory analysis and visualizations for the NASA Exoplanet Archive
Planetary Systems table used in the CDC hackathon."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "PS_2025.09.20_08.15.55.csv"
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")


def load_default_planets() -> pd.DataFrame:
    """Load the planetary systems table restricted to default parameter sets."""

    df = pd.read_csv(DATA_PATH, comment="#")
    df = df[df["default_flag"] == 1].copy()
    return df


def plot_discoveries_by_method(df: pd.DataFrame) -> None:
    """Create a stacked area chart of discoveries per year and detection method."""

    top_methods = (
        df["discoverymethod"].value_counts().head(4).index.tolist()
    )
    discoveries = (
        df.assign(
            method=df["discoverymethod"].fillna("Unknown"),
            year=df["disc_year"],
        )
        .query("year.notna()")
        .assign(
            method=lambda d: d["method"].where(d["method"].isin(top_methods), "Other")
        )
        .groupby(["year", "method"], as_index=False)
        .size()
    )

    pivot = discoveries.pivot(index="year", columns="method", values="size").fillna(0)
    pivot = pivot.sort_index()

    plt.figure(figsize=(10, 6))
    plt.stackplot(pivot.index, pivot.T, labels=pivot.columns)
    plt.title("Confirmed exoplanet discoveries by detection method")
    plt.xlabel("Discovery year")
    plt.ylabel("Number of planets")
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "discoveries_by_method.png", dpi=300)
    plt.close()


def plot_radius_vs_teff(df: pd.DataFrame) -> None:
    """Plot planet radius against stellar effective temperature."""

    filtered = df.dropna(subset=["pl_rade", "st_teff", "pl_eqt"]).copy()
    upper_radius = filtered["pl_rade"].quantile(0.99)
    filtered = filtered[filtered["pl_rade"] <= upper_radius]

    plt.figure(figsize=(9, 6))
    scatter = sns.scatterplot(
        data=filtered,
        x="st_teff",
        y="pl_rade",
        hue="pl_eqt",
        palette="viridis",
        alpha=0.6,
        edgecolor="none",
    )
    scatter.set(
        title="Planet radius vs. host star temperature",
        xlabel="Stellar effective temperature (K)",
        ylabel="Planet radius (Earth radii)",
    )
    cbar = scatter.get_figure().colorbar(scatter.collections[0])
    cbar.set_label("Planet equilibrium temperature (K)")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "radius_vs_teff.png", dpi=300)
    plt.close()


def plot_orbital_period_by_multiplicity(df: pd.DataFrame) -> None:
    """Compare orbital periods across system multiplicities."""

    filtered = df.dropna(subset=["pl_orbper", "sy_pnum"]).copy()
    filtered = filtered[filtered["pl_orbper"] > 0]
    filtered = filtered.assign(
        multiplicity=pd.cut(
            filtered["sy_pnum"],
            bins=[0, 1, 2, 3, 4, filtered["sy_pnum"].max()],
            labels=["1 planet", "2 planets", "3 planets", "4 planets", "5+ planets"],
            include_lowest=True,
            right=True,
        ),
        log_orbper=lambda d: d["pl_orbper"].pipe(np.log10),
    )
    filtered = filtered.dropna(subset=["multiplicity"])

    plt.figure(figsize=(9, 6))
    sns.boxplot(data=filtered, x="multiplicity", y="log_orbper")
    plt.title("Orbital period distribution by system multiplicity")
    plt.xlabel("Number of confirmed planets in system")
    plt.ylabel("log10(Orbital period in days)")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "orbital_period_by_multiplicity.png", dpi=300)
    plt.close()


def summarize_key_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Return summary statistics used in the report."""

    summary = {}
    summary["total_planets"] = len(df)
    summary["median_disc_year"] = df["disc_year"].median()

    latest_decade = df[df["disc_year"] >= 2015]
    summary["recent_transits_share"] = (
        (latest_decade["discoverymethod"] == "Transit").mean()
    )

    temp_filtered = df.dropna(subset=["pl_eqt", "pl_rade"])
    summary["cool_small_fraction"] = (
        temp_filtered["pl_eqt"].between(200, 400)
        & temp_filtered["pl_rade"].between(0.5, 1.5)
    ).mean()

    multi = df[df["sy_pnum"] >= 3]
    summary["multi_systems"] = multi["hostname"].nunique()

    return pd.Series(summary)


if __name__ == "__main__":
    planets = load_default_planets()
    plot_discoveries_by_method(planets)
    plot_radius_vs_teff(planets)
    plot_orbital_period_by_multiplicity(planets)

    stats = summarize_key_metrics(planets)
    print(stats.to_string())
