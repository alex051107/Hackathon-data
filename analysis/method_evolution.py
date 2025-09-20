"""Analysis of detection method evolution and facility contributions with verbose in-line rationale."""

from __future__ import annotations  # Future annotations ensure compatibility across Python versions.

from pathlib import Path  # OS-agnostic path manipulation utilities.
from typing import Dict, Iterable  # Type hints for dictionaries and iterable inputs.

import matplotlib.pyplot as plt  # Base plotting library underpinning seaborn charts.
import numpy as np  # Numerical helpers for forecasting confidence intervals.
import pandas as pd  # Data wrangling toolkit for tabular operations.
import seaborn as sns  # Statistical plotting aesthetics for Matplotlib.
from statsmodels.tsa.api import ExponentialSmoothing  # Holt-Winters forecasting implementation.

# ---------------------------------------------------------------------------
# Project constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]  # Resolve repository root relative to this file.
DATA_PATH = ROOT / "PS_2025.09.20_08.15.55.csv"  # NASA Planetary Systems dataset export.
FACILITY_METADATA_PATH = ROOT / "data/discovery_facilities.csv"  # Supplemental facility descriptors.
FIG_DIR = ROOT / "figures" / "method_evolution"  # Folder for saved figures.
RESULTS_DIR = ROOT / "results"  # Directory for storing aggregated tables.

FIG_DIR.mkdir(parents=True, exist_ok=True)  # Ensure output figure directory is available.
RESULTS_DIR.mkdir(parents=True, exist_ok=True)  # Ensure results directory exists before writing files.

sns.set_theme(style="whitegrid")  # Apply consistent styling to all charts.


# ---------------------------------------------------------------------------
# Data preparation helpers
# ---------------------------------------------------------------------------

def load_detection_data() -> pd.DataFrame:
    """Load the planetary systems table restricted to default parameter sets."""

    df = pd.read_csv(DATA_PATH, comment="#")  # Read CSV while skipping metadata comment lines.
    df = df[df["default_flag"] == 1].copy()  # Keep only canonical planet solutions to avoid duplicates.
    df = df.dropna(subset=["disc_year", "discoverymethod"])  # Remove rows lacking discovery year or method labels.
    df = df.astype({"disc_year": "int64"})  # Cast discovery year to integer for grouping stability.
    df = df[df["disc_year"] >= 1989]  # Filter to era with reliable published detections.
    df.loc[:, "discoverymethod"] = df["discoverymethod"].str.strip()  # Normalise method text for grouping.
    return df  # Provide cleaned detection records.


def label_detection_methods(df: pd.DataFrame, min_share: float = 0.02) -> pd.DataFrame:
    """Group low-frequency discovery methods into an "Other" bucket."""

    df = df.copy()  # Avoid mutating the caller's DataFrame.
    method_share = df["discoverymethod"].value_counts(normalize=True)  # Compute global method frequency share.
    major_methods = method_share[method_share >= min_share].index.tolist()  # Identify methods above share threshold.
    df.loc[:, "method_group"] = df["discoverymethod"].where(
        df["discoverymethod"].isin(major_methods), "Other"
    )  # Replace rare methods with "Other" label.
    return df  # Return DataFrame with new grouping column.


def load_facility_metadata() -> pd.DataFrame:
    """Read supplemental facility metadata if available."""

    if not FACILITY_METADATA_PATH.exists():
        return pd.DataFrame(columns=["disc_facility", "platform", "operator", "location"])  # Empty placeholder.
    return pd.read_csv(FACILITY_METADATA_PATH)  # Return facility metadata for enrichment.


# ---------------------------------------------------------------------------
# Aggregations and metrics
# ---------------------------------------------------------------------------

def aggregate_method_timeseries(df: pd.DataFrame) -> pd.DataFrame:
    """Return annual discovery counts per detection method group."""

    grouped = (
        df.groupby(["disc_year", "method_group"], as_index=False)
        .size()
        .rename(columns={"size": "discoveries"})
    )  # Count number of planets discovered by year and method.
    return grouped.sort_values("disc_year")  # Sort chronologically for plotting.


def compute_facility_method_summary(
    df: pd.DataFrame,
    top_n: int = 12,
    window: Iterable[int] | None = None,
) -> pd.DataFrame:
    """Summarise how major facilities contribute to detection methods."""

    facility_counts = df["disc_facility"].value_counts()  # Determine busiest facilities overall.
    top_facilities = facility_counts.head(top_n).index  # Select top-N facilities for reporting.

    filtered = df[df["disc_facility"].isin(top_facilities)].copy()  # Keep rows for major facilities only.
    if window is not None:
        start, end = min(window), max(window)  # Determine inclusive year window bounds.
        filtered = filtered[filtered["disc_year"].between(start, end)]  # Restrict dataset to the analysis window.

    summary = (
        filtered.groupby(["disc_facility", "method_group"], as_index=False)
        .size()
        .rename(columns={"size": "discoveries"})
    )  # Count discoveries per facility-method pairing.

    totals = summary.groupby("disc_facility")["discoveries"].transform("sum")  # Compute facility totals for shares.
    summary.loc[:, "share_within_facility"] = summary["discoveries"] / totals  # Convert counts to facility share.
    return summary  # Provide dataset for stacked facility charts.


def prepare_forecast_input(timeseries: pd.DataFrame, min_years: int = 6) -> Dict[str, pd.Series]:
    """Return time series for methods with sufficient history for forecasting."""

    forecast_data: Dict[str, pd.Series] = {}  # Container for per-method time series.
    for method, group in timeseries.groupby("method_group"):
        pivot = group.set_index("disc_year")["discoveries"].sort_index()  # Convert to year-indexed series.
        if len(pivot) >= min_years:  # Require minimum history for stable Holt-Winters fits.
            forecast_data[method] = pivot  # Store eligible series for forecasting.
    return forecast_data  # Return dictionary keyed by method name.


def forecast_method_activity(
    series_by_method: Dict[str, pd.Series],
    horizon: int = 5,
) -> pd.DataFrame:
    """Generate additive-trend Holt-Winters forecasts for each method."""

    records = []  # Collect forecast rows for concatenation.
    for method, series in series_by_method.items():
        original_years = series.index.to_numpy()  # Preserve original year index for horizon calculations.
        model_series = pd.Series(series.values)  # Convert to zero-indexed series for statsmodels.
        model = ExponentialSmoothing(
            model_series, trend="add", seasonal=None, initialization_method="estimated"
        )  # Configure additive trend without seasonality.
        fitted = model.fit()  # Estimate Holt-Winters parameters.
        last_year = int(original_years[-1])  # Determine final observed year.
        forecast_index = np.arange(last_year + 1, last_year + horizon + 1)  # Generate future year labels.
        forecast_values = fitted.forecast(horizon)  # Forecast discovery counts across horizon.
        nobs = len(model_series)  # Number of observations for confidence interval estimation.
        conf_int = 1.96 * np.sqrt(fitted.sse / nobs)  # Approximate 95% confidence via residual variance.
        for year, value in zip(forecast_index, forecast_values):  # Record predictions year by year.
            records.append(
                {
                    "method_group": method,
                    "disc_year": int(year),
                    "forecast": float(value),
                    "conf_low": float(value - conf_int),
                    "conf_high": float(value + conf_int),
                }
            )
    return pd.DataFrame(records)  # Compile forecasts for all methods into a DataFrame.


# ---------------------------------------------------------------------------
# Visualisation helpers
# ---------------------------------------------------------------------------

def plot_method_stack(timeseries: pd.DataFrame) -> None:
    """Produce a stacked area chart of annual discoveries by method."""

    pivot = timeseries.pivot(index="disc_year", columns="method_group", values="discoveries").fillna(0)
    pivot = pivot.sort_index()  # Ensure chronological ordering for stack plot.

    plt.figure(figsize=(11, 6))  # Allocate canvas for widescreen presentation.
    plt.stackplot(pivot.index, pivot.T, labels=pivot.columns)  # Plot stacked area by method.
    plt.title("Detection method share over time")  # Set descriptive title.
    plt.xlabel("Discovery year")  # Label x-axis.
    plt.ylabel("Number of confirmed planets")  # Label y-axis.
    plt.legend(loc="upper left", ncol=2)  # Provide multi-column legend for readability.
    plt.tight_layout()  # Prevent label clipping.
    plt.savefig(FIG_DIR / "discoveries_by_method.png", dpi=300)  # Export figure for documentation.
    plt.close()  # Release figure resources.


def plot_facility_mix(summary: pd.DataFrame) -> None:
    """Plot stacked bars showing facility contribution mix."""

    plt.figure(figsize=(10, 7))  # Create figure with enough width for facility labels.
    pivot = summary.pivot(
        index="disc_facility", columns="method_group", values="share_within_facility"
    ).fillna(0)  # Convert to share matrix for stacking.
    pivot = pivot.loc[pivot.sum(axis=1).sort_values().index]  # Sort facilities by total activity ascending.

    pivot.plot(
        kind="barh", stacked=True, cmap="viridis", ax=plt.gca()
    )  # Draw horizontal stacked bars using shares.
    plt.xlabel("Share of facility discoveries")  # Annotate x-axis.
    plt.ylabel("Facility")  # Annotate y-axis.
    plt.title("Facility portfolios since 2015")  # Provide context for time window.
    plt.legend(title="Method", bbox_to_anchor=(1.05, 1), loc="upper left")  # Place legend outside for readability.
    plt.tight_layout()  # Adjust layout to include legend.
    plt.savefig(FIG_DIR / "facility_method_mix.png", dpi=300)  # Export figure asset.
    plt.close()  # Free resources.


def plot_bar_animation_stub(timeseries: pd.DataFrame) -> None:
    """Placeholder for CLI pipeline; animation handled by Plotly dashboard."""

    summary = timeseries.groupby("disc_year")["discoveries"].sum().tail(5)  # Recent totals for logging.
    print("Recent discovery counts by year:")  # Provide CLI context for analysts.
    for year, count in summary.items():
        print(f"  {year}: {int(count)}")  # Report counts to console.


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_tables(timeseries: pd.DataFrame, facility: pd.DataFrame, forecast: pd.DataFrame) -> None:
    """Write aggregated tables for reproducibility and dashboard consumption."""

    timeseries.to_csv(RESULTS_DIR / "method_timeseries.csv", index=False)  # Save annual counts.
    facility.to_csv(RESULTS_DIR / "facility_method_summary.csv", index=False)  # Save facility shares.
    forecast.to_csv(RESULTS_DIR / "method_forecast.csv", index=False)  # Save forecast results.


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def main() -> None:
    """Execute the detection method evolution analysis end-to-end."""

    detection = load_detection_data()  # Load cleaned detection records.
    labelled = label_detection_methods(detection)  # Annotate with grouped method labels.
    timeseries = aggregate_method_timeseries(labelled)  # Aggregate to yearly counts.
    facility = compute_facility_method_summary(labelled, window=range(2015, labelled["disc_year"].max() + 1))
    forecast_input = prepare_forecast_input(timeseries)  # Prepare time series for forecasting.
    forecast = forecast_method_activity(forecast_input)  # Generate Holt-Winters forecasts.

    export_tables(timeseries, facility, forecast)  # Persist outputs for dashboard usage.

    plot_method_stack(timeseries)  # Save stacked area chart.
    plot_facility_mix(facility)  # Save facility mix visual.
    plot_bar_animation_stub(timeseries)  # Provide CLI summary for quick inspection.

    recent = labelled[labelled["disc_year"] >= 2015]  # Focus on the contemporary era for dominance analysis.
    transit_share = (recent["method_group"] == "Transit").mean()  # Compute transit share within the filtered window.
    print(f"Transit share since 2015: {transit_share:.3f}")  # Log share for validation against dashboard figure.


if __name__ == "__main__":  # Allow script execution from CLI.
    main()  # Run the workflow when executed directly.
