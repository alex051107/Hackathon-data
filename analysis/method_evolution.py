"""Analysis of detection method evolution and facility contributions for the
NASA Exoplanet Archive planetary systems table."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from statsmodels.tsa.api import ExponentialSmoothing

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "PS_2025.09.20_08.15.55.csv"
FACILITY_METADATA_PATH = ROOT / "data/discovery_facilities.csv"
FIG_DIR = ROOT / "figures" / "method_evolution"
RESULTS_DIR = ROOT / "results"

FIG_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")


# ---------------------------------------------------------------------------
# Data preparation helpers
# ---------------------------------------------------------------------------

def load_detection_data() -> pd.DataFrame:
    """Load the planetary systems table restricted to default parameter sets."""

    df = pd.read_csv(DATA_PATH, comment="#")
    df = df[df["default_flag"] == 1].copy()
    df = df.dropna(subset=["disc_year", "discoverymethod"])
    df = df.astype({"disc_year": "int64"})
    df = df[df["disc_year"] >= 1989]
    df.loc[:, "discoverymethod"] = df["discoverymethod"].str.strip()
    return df


def label_detection_methods(df: pd.DataFrame, min_share: float = 0.02) -> pd.DataFrame:
    """Group low-frequency discovery methods into an "Other" bucket."""

    df = df.copy()
    method_share = df["discoverymethod"].value_counts(normalize=True)
    major_methods = method_share[method_share >= min_share].index.tolist()
    df.loc[:, "method_group"] = df["discoverymethod"].where(
        df["discoverymethod"].isin(major_methods), "Other"
    )
    return df


def load_facility_metadata() -> pd.DataFrame:
    """Read supplemental facility metadata if available."""

    if not FACILITY_METADATA_PATH.exists():
        return pd.DataFrame(columns=["disc_facility", "platform", "operator", "location"])
    return pd.read_csv(FACILITY_METADATA_PATH)


# ---------------------------------------------------------------------------
# Aggregations and metrics
# ---------------------------------------------------------------------------

def aggregate_method_timeseries(df: pd.DataFrame) -> pd.DataFrame:
    """Return annual discovery counts per detection method group."""

    grouped = (
        df.groupby(["disc_year", "method_group"], as_index=False)
        .size()
        .rename(columns={"size": "discoveries"})
    )
    return grouped.sort_values("disc_year")


def compute_facility_method_summary(
    df: pd.DataFrame,
    top_n: int = 12,
    window: Iterable[int] | None = None,
) -> pd.DataFrame:
    """Summarise how major facilities contribute to detection methods."""

    facility_counts = df["disc_facility"].value_counts()
    top_facilities = facility_counts.head(top_n).index

    filtered = df[df["disc_facility"].isin(top_facilities)].copy()
    if window is not None:
        start, end = min(window), max(window)
        filtered = filtered[filtered["disc_year"].between(start, end)]

    summary = (
        filtered.groupby(["disc_facility", "method_group"], as_index=False)
        .size()
        .rename(columns={"size": "discoveries"})
    )

    totals = summary.groupby("disc_facility")["discoveries"].transform("sum")
    summary.loc[:, "share_within_facility"] = summary["discoveries"] / totals
    return summary


def prepare_forecast_input(timeseries: pd.DataFrame, min_years: int = 6) -> Dict[str, pd.Series]:
    """Return time series for methods with sufficient history for forecasting."""

    forecast_data: Dict[str, pd.Series] = {}
    for method, group in timeseries.groupby("method_group"):
        pivot = group.set_index("disc_year")["discoveries"].sort_index()
        if len(pivot) >= min_years:
            forecast_data[method] = pivot
    return forecast_data


def forecast_method_activity(
    series_by_method: Dict[str, pd.Series],
    horizon: int = 5,
) -> pd.DataFrame:
    """Generate additive-trend Holt-Winters forecasts for each method."""

    records = []
    for method, series in series_by_method.items():
        original_years = series.index.to_numpy()
        model_series = pd.Series(series.values)
        model = ExponentialSmoothing(model_series, trend="add", seasonal=None, initialization_method="estimated")
        fitted = model.fit()
        last_year = int(original_years[-1])
        forecast_index = np.arange(last_year + 1, last_year + horizon + 1)
        forecast_values = fitted.forecast(horizon)
        nobs = len(model_series)
        conf_int = 1.96 * np.sqrt(fitted.sse / nobs)
        for year, value in zip(forecast_index, forecast_values):
            records.append(
                {
                    "method_group": method,
                    "disc_year": int(year),
                    "forecast": float(value),
                    "conf_low": float(value - conf_int),
                    "conf_high": float(value + conf_int),
                }
            )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Visualisation helpers
# ---------------------------------------------------------------------------

def plot_method_stack(timeseries: pd.DataFrame) -> None:
    """Produce a stacked area chart of annual discoveries by method."""

    pivot = timeseries.pivot(index="disc_year", columns="method_group", values="discoveries").fillna(0)
    pivot = pivot.sort_index()

    plt.figure(figsize=(11, 6))
    plt.stackplot(pivot.index, pivot.T, labels=pivot.columns)
    plt.title("Detection method share over time")
    plt.xlabel("Discovery year")
    plt.ylabel("Number of confirmed planets")
    plt.legend(loc="upper left", ncol=2)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "method_stack.png", dpi=300)
    plt.close()


def plot_facility_method_share(summary: pd.DataFrame, metadata: pd.DataFrame) -> None:
    """Visualise how top facilities split their discoveries across methods."""

    pivot = summary.pivot(index="disc_facility", columns="method_group", values="share_within_facility").fillna(0)
    pivot = pivot.sort_values(by=pivot.columns.tolist(), ascending=False)

    facilities = pivot.index.tolist()
    annotations = {
        row["disc_facility"]: f"{row['platform']}\n{row['location']}"
        for _, row in metadata.iterrows()
    }

    fig, ax = plt.subplots(figsize=(12, 7))
    bottom = np.zeros(len(pivot))
    colors = sns.color_palette("Spectral", n_colors=len(pivot.columns))
    for color, method in zip(colors, pivot.columns):
        ax.barh(facilities, pivot[method], left=bottom, label=method, color=color)
        bottom += pivot[method].values

    for idx, facility in enumerate(facilities):
        if facility in annotations:
            ax.annotate(
                annotations[facility],
                xy=(1.01, idx),
                xycoords=("axes fraction", "data"),
                va="center",
                fontsize=9,
                color="dimgray",
            )

    ax.set_title("How top discovery facilities allocate effort across methods")
    ax.set_xlabel("Share of facility discoveries")
    ax.set_ylabel("Facility")
    ax.set_xlim(0, 1.05)
    ax.legend(loc="lower right", title="Method")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "facility_method_share.png", dpi=300)
    plt.close(fig)


def plot_method_forecast(
    history: pd.DataFrame,
    forecast: pd.DataFrame,
    methods: Iterable[str],
) -> None:
    """Plot historical counts and model forecasts for selected methods."""

    plt.figure(figsize=(11, 6))
    palette = sns.color_palette("tab10", n_colors=len(methods))

    for color, method in zip(palette, methods):
        hist = history[history["method_group"] == method]
        plt.plot(hist["disc_year"], hist["discoveries"], label=f"{method} observed", color=color)

        fc = forecast[forecast["method_group"] == method]
        if not fc.empty:
            plt.plot(fc["disc_year"], fc["forecast"], linestyle="--", color=color)
            plt.fill_between(fc["disc_year"], fc["conf_low"], fc["conf_high"], color=color, alpha=0.15)

    plt.title("Projected discoveries by detection method")
    plt.xlabel("Year")
    plt.ylabel("Number of confirmed planets")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / "method_forecast.png", dpi=300)
    plt.close()


# ---------------------------------------------------------------------------
# Main execution flow
# ---------------------------------------------------------------------------

def main() -> None:
    df = load_detection_data()
    df = label_detection_methods(df)

    timeseries = aggregate_method_timeseries(df)
    timeseries.to_csv(RESULTS_DIR / "method_timeseries.csv", index=False)

    plot_method_stack(timeseries)

    metadata = load_facility_metadata()
    facility_summary = compute_facility_method_summary(df, window=range(2015, df["disc_year"].max() + 1))
    facility_summary.to_csv(RESULTS_DIR / "facility_method_summary.csv", index=False)
    plot_facility_method_share(facility_summary, metadata)

    series_by_method = prepare_forecast_input(timeseries)
    forecast = forecast_method_activity(series_by_method)
    forecast.to_csv(RESULTS_DIR / "method_forecast.csv", index=False)

    top_methods = (
        timeseries.groupby("method_group")["discoveries"].sum().sort_values(ascending=False).head(4).index.tolist()
    )
    plot_method_forecast(timeseries, forecast, top_methods)


if __name__ == "__main__":
    main()
