"""Baseline exploratory plots for the NASA planetary systems snapshot."""

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


def plot_distance_histogram(df: pd.DataFrame) -> None:
    """Visualise the distribution of system distances relevant for follow-up planning."""

    filtered = df.dropna(subset=["sy_dist"]).copy()
    filtered = filtered[filtered["sy_dist"] <= 2000]

    plt.figure(figsize=(9, 6))
    sns.histplot(filtered["sy_dist"], bins=40, color="#0b3d91")
    plt.title("Distribution of confirmed system distances")
    plt.xlabel("Distance (parsec)")
    plt.ylabel("Number of planets")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "distance_histogram.png", dpi=300)
    plt.close()


def summarize_key_metrics(df: pd.DataFrame) -> pd.Series:
    """Return summary statistics used in documentation."""

    summary = {}
    summary["total_planets"] = len(df)
    summary["median_disc_year"] = df["disc_year"].median()

    habitable_window = df.dropna(subset=["pl_eqt", "pl_insol", "pl_rade"]).copy()
    summary["temperate_fraction"] = (
        habitable_window["pl_eqt"].between(200, 350)
        & habitable_window["pl_insol"].between(0.2, 2.5)
        & habitable_window["pl_rade"].between(0.5, 2.5)
    ).mean()

    nearby = df[df["sy_dist"].between(0, 100)].copy()
    summary["nearby_targets"] = len(nearby)

    return pd.Series(summary)


if __name__ == "__main__":
    planets = load_default_planets()
    plot_radius_vs_teff(planets)
    plot_orbital_period_by_multiplicity(planets)
    plot_distance_histogram(planets)

    stats = summarize_key_metrics(planets)
    print(stats.to_string())
