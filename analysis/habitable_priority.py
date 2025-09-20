"""Habitable zone candidate prioritisation for confirmed exoplanets with per-step explanations."""

from __future__ import annotations  # Enable postponed evaluation of annotations for Python 3.8 compatibility.

from io import BytesIO  # Provide an in-memory buffer for optional catalog downloads.
from pathlib import Path  # Handle filesystem paths robustly across operating systems.
from typing import Dict, List, Optional  # Type hints for clarity around function inputs and outputs.
from urllib.error import URLError  # Capture connectivity errors when fetching authoritative samples.
from urllib.request import Request, urlopen  # Perform HTTP requests for the external catalog fallback.

import matplotlib.pyplot as plt  # Matplotlib supplies base plotting primitives used by seaborn.
import numpy as np  # NumPy powers fast vectorised math for scoring transformations.
import pandas as pd  # Pandas handles tabular data manipulation and filtering.
import seaborn as sns  # Seaborn adds aesthetically pleasing defaults for Matplotlib figures.

# ---------------------------------------------------------------------------
# Project paths and constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]  # Resolve the repository root relative to this script.
DATA_PATH = ROOT / "PS_2025.09.20_08.15.55.csv"  # NASA Planetary Systems export bundled with the project.
FIG_DIR = ROOT / "figures" / "habitability"  # Folder for saving static habitability visualisations.
RESULTS_DIR = ROOT / "results"  # Directory for tabular scoring outputs.
AUTHORITATIVE_SAMPLE_PATH = ROOT / "data" / "authoritative_habitable_sample.csv"  # Offline validation sample.
PHL_CATALOG_URL = (
    "https://phl.upr.edu/projects/habitable-exoplanets-catalog/data/"
    "habitable_exoplanets_catalog.csv"
)  # Source URL for the Planetary Habitability Laboratory authoritative list.

FIG_DIR.mkdir(parents=True, exist_ok=True)  # Create the figure directory if it does not already exist.
RESULTS_DIR.mkdir(parents=True, exist_ok=True)  # Ensure results directory exists for downstream exports.

sns.set_theme(style="whitegrid")  # Use a consistent aesthetic across generated figures.

REQUIRED_COLUMNS = [
    "pl_name",  # Planet name used for joins and reporting.
    "hostname",  # Host star identifier for context.
    "pl_eqt",  # Planet equilibrium temperature (K) for thermal suitability.
    "pl_rade",  # Planet radius (Earth radii) for size classification.
    "pl_insol",  # Stellar insolation relative to Earth for irradiation checks.
    "pl_orbper",  # Orbital period (days) to capture dynamical stability.
    "st_teff",  # Stellar effective temperature for host context.
    "st_rad",  # Stellar radius to estimate illumination geometry.
    "sy_vmag",  # Apparent visual magnitude to approximate observational effort.
    "sy_snum",  # Stellar system multiplicity for dynamical complexity.
]  # All fields required by the scoring logic.


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def load_planet_catalog() -> pd.DataFrame:
    """Load the NASA planetary systems table restricted to default parameter rows."""

    df = pd.read_csv(DATA_PATH, comment="#")  # Parse the CSV while ignoring metadata comment lines.
    df = df[df["default_flag"] == 1].copy()  # Keep only the canonical solution for each planet to avoid duplicates.
    return df  # Return the cleaned base catalog for downstream processing.


def select_habitable_inputs(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to systems with complete measurements and physically plausible values."""

    filtered = df.dropna(subset=REQUIRED_COLUMNS).copy()  # Remove rows missing any required metric.

    filtered = filtered[filtered["pl_rade"] <= filtered["pl_rade"].quantile(0.99)]  # Trim extreme radius outliers.
    filtered = filtered[filtered["pl_eqt"].between(150, 450)]  # Restrict to plausible habitable-zone temperatures.
    filtered = filtered[filtered["pl_insol"].between(0.05, 5)]  # Keep moderate stellar irradiation values.
    filtered = filtered[filtered["pl_orbper"].between(1, 800)]  # Remove ultra-short or poorly constrained periods.
    filtered = filtered[filtered["st_teff"].between(3500, 7500)]  # Focus on FGKM-like host stars for comparability.
    filtered = filtered[filtered["sy_vmag"].between(0, 18)]  # Ensure brightness values fall within observable ranges.

    return filtered  # Provide the curated dataset ready for scoring.


# ---------------------------------------------------------------------------
# Scoring model
# ---------------------------------------------------------------------------

def sigmoid(x: np.ndarray, midpoint: float, steepness: float) -> np.ndarray:
    """Numerically stable logistic transform used for observability scoring."""

    return 1 / (1 + np.exp((x - midpoint) / steepness))  # Logistic mapping to (0, 1) range.


def compute_priority_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Generate the weighted habitability score along with component metrics."""

    data = df.copy()  # Work on a copy to avoid modifying caller state.

    data.loc[:, "temp_score"] = np.exp(-((data["pl_eqt"] - 288) / 60) ** 2)  # Score closeness to Earth-like temperature.
    data.loc[:, "radius_score"] = np.exp(-((data["pl_rade"] - 1) / 0.35) ** 2)  # Prefer Earth-sized planets.
    data.loc[:, "insolation_score"] = np.exp(-((data["pl_insol"] - 1) / 0.5) ** 2)  # Reward Earth-like irradiation.

    log_period = np.log10(data["pl_orbper"])  # Use log-period to smooth wide dynamical ranges.
    data.loc[:, "period_score"] = np.exp(-((log_period - np.log10(365)) / 0.3) ** 2)  # Target ~1-year orbits.

    data.loc[:, "stellar_temp_score"] = np.exp(-((data["st_teff"] - 5778) / 800) ** 2)  # Prefer Sun-like stars.

    data.loc[:, "observability_score"] = sigmoid(
        data["sy_vmag"], midpoint=11.5, steepness=1.8
    )  # Bright stars are easier to observe.

    data.loc[:, "system_score"] = np.where(
        data["sy_snum"] == 1, 1.0, 0.75
    )  # Slightly down-weight multi-star systems due to dynamical complexity.

    weights = {
        "temp_score": 0.24,  # Thermal suitability receives the highest weight.
        "radius_score": 0.22,  # Planet size influences habitability prospects.
        "insolation_score": 0.16,  # Stellar flux supports the temperature metric.
        "period_score": 0.14,  # Orbital period affects surface conditions and observability cadence.
        "stellar_temp_score": 0.14,  # Host star temperature influences stellar activity and spectral quality.
        "observability_score": 0.07,  # Observational practicality is important but secondary.
        "system_score": 0.03,  # System simplicity carries modest weight.
    }  # Weights sum to one for interpretability.

    total = sum(weights.values())  # Normalise combined weighted sum to preserve scale.
    data.loc[:, "priority_score"] = sum(data[k] * v for k, v in weights.items()) / total  # Weighted aggregate score.

    bins = [0, 0.55, 0.7, 1.0]  # Define thresholds for qualitative interpretation bands.
    labels = ["Context", "Follow-up", "High Priority"]  # Human-readable categories for presentations.
    data.loc[:, "priority_band"] = pd.cut(
        data["priority_score"], bins=bins, labels=labels, include_lowest=True
    )  # Assign each planet to a band.

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
    ]  # Columns to retain in the exported scoring table.
    return data[cols].sort_values("priority_score", ascending=False)  # Highest priority planets first.


# ---------------------------------------------------------------------------
# Visualisation helpers
# ---------------------------------------------------------------------------

def plot_temp_radius(priority_df: pd.DataFrame) -> None:
    """Create a scatter plot of temperature vs radius coloured by priority score."""

    plt.figure(figsize=(10, 6))  # Allocate a figure canvas with presentation-friendly proportions.
    scatter = sns.scatterplot(
        data=priority_df,  # Provide the scored dataset.
        x="pl_eqt",  # Equilibrium temperature along the x-axis.
        y="pl_rade",  # Planet radius on the y-axis.
        hue="priority_score",  # Colour-coded by overall priority score.
        size="observability_score",  # Encode observational ease with point size.
        palette="viridis",  # Use perceptually uniform colour map.
        alpha=0.7,  # Slight transparency to manage overplotting.
        edgecolor="none",  # Remove borders for cleaner glyphs.
    )
    scatter.set(
        title="Habitable zone priority landscape",  # Figure title for clarity.
        xlabel="Planet equilibrium temperature (K)",  # Label the x-axis.
        ylabel="Planet radius (Earth radii)",  # Label the y-axis.
    )
    plt.axvspan(240, 320, color="lightgray", alpha=0.2, label="Classical habitable band")  # Highlight classic HZ temps.
    plt.axhspan(0.7, 1.6, color="lightblue", alpha=0.2, label="Earth-size range")  # Highlight Earth-like radii.
    plt.legend(loc="upper right", title="Priority score")  # Place the legend near the data.
    plt.tight_layout()  # Reduce padding around the figure for export.
    plt.savefig(FIG_DIR / "temp_radius_priority.png", dpi=300)  # Save a high-resolution PNG for reports.
    plt.close()  # Release the figure to free memory in batch runs.


def plot_component_bars(priority_df: pd.DataFrame, top_n: int = 15) -> None:
    """Plot stacked component contributions for the highest-priority planets."""

    components = [
        "temp_score",
        "radius_score",
        "insolation_score",
        "period_score",
        "stellar_temp_score",
        "observability_score",
        "system_score",
    ]  # Score components to visualise.
    top = priority_df.head(top_n).copy()  # Select the top-N targets for readability.
    melted = top.melt(
        id_vars=["pl_name", "priority_score"],
        value_vars=components,
        var_name="component",
        value_name="score",
    )  # Convert to long format for stacked bar plotting.

    plt.figure(figsize=(11, 7))  # Provide ample space for rotated labels.
    sns.barplot(
        data=melted,
        x="pl_name",
        y="score",
        hue="component",
        palette="viridis",
    )  # Display contributions by component for each planet.
    plt.xticks(rotation=45, ha="right")  # Tilt labels to prevent overlap.
    plt.ylabel("Component score")  # Annotate y-axis.
    plt.xlabel("Planet")  # Annotate x-axis.
    plt.title("Score composition for top-priority targets")  # Add descriptive title.
    plt.tight_layout()  # Ensure axes labels remain visible.
    plt.savefig(FIG_DIR / "priority_components.png", dpi=300)  # Export figure for documentation.
    plt.close()  # Release figure resources.


def plot_radar_chart(priority_df: pd.DataFrame, top_n: int = 5) -> None:
    """Create radar plots showing component balance for the highest-ranked planets."""

    components = [
        "temp_score",
        "radius_score",
        "insolation_score",
        "period_score",
        "stellar_temp_score",
        "observability_score",
        "system_score",
    ]  # Radar axes representing scoring dimensions.

    theta = np.linspace(0, 2 * np.pi, len(components), endpoint=False)  # Compute angle for each axis.
    theta = np.concatenate([theta, theta[:1]])  # Close the loop by repeating the first angle.

    plt.figure(figsize=(10, 10))  # Large figure to house multiple radar charts.

    for idx, (_, row) in enumerate(priority_df.head(top_n).iterrows(), start=1):  # Loop through top targets.
        values = row[components].to_numpy()  # Extract component scores as array.
        values = np.concatenate([values, values[:1]])  # Close the polygon for plotting.
        ax = plt.subplot(3, 2, idx, polar=True)  # Place each radar chart in a grid of polar subplots.
        ax.plot(theta, values, label=row["pl_name"])  # Draw the polygon for this planet.
        ax.fill(theta, values, alpha=0.3)  # Fill the polygon for readability.
        ax.set_xticks(theta[:-1])  # Align axis labels with each component.
        ax.set_xticklabels(components, fontsize=9)  # Display component names around the radar.
        ax.set_title(row["pl_name"], fontsize=12)  # Annotate each subplot with the planet name.

    plt.tight_layout()  # Avoid overlapping subplots.
    plt.savefig(FIG_DIR / "priority_radar.png", dpi=300)  # Save the radar chart grid for presentations.
    plt.close()  # Clean up Matplotlib state.


# ---------------------------------------------------------------------------
# Authoritative sample comparison
# ---------------------------------------------------------------------------

def download_authoritative_catalog() -> Optional[pd.DataFrame]:
    """Fetch the authoritative habitable exoplanet sample from PHL with graceful fallbacks."""

    try:
        req = Request(PHL_CATALOG_URL, headers={"User-Agent": "CDC-Project/1.0"})  # Provide a UA to avoid blocking.
        with urlopen(req, timeout=15) as response:  # Attempt to download within 15 seconds.
            payload = response.read()  # Read the entire CSV payload into memory.
        buffer = BytesIO(payload)  # Wrap bytes in BytesIO for pandas compatibility.
        df = pd.read_csv(buffer)  # Parse CSV into DataFrame.
        return df  # Return authoritative sample on success.
    except URLError:
        return None  # Signal download failure without aborting the pipeline.


def load_authoritative_sample() -> pd.DataFrame:
    """Load the authoritative sample from disk or fetch it if absent."""

    if AUTHORITATIVE_SAMPLE_PATH.exists():
        return pd.read_csv(AUTHORITATIVE_SAMPLE_PATH)  # Use pre-downloaded sample for offline reproducibility.

    remote = download_authoritative_catalog()  # Attempt live download when offline cache missing.
    if remote is not None:
        remote.to_csv(AUTHORITATIVE_SAMPLE_PATH, index=False)  # Cache the download for future runs.
        return remote  # Return the freshly downloaded sample.

    raise FileNotFoundError(
        "Authoritative habitable sample unavailable locally and remote download failed."
    )  # Provide actionable error if both paths fail.


def compare_with_authoritative(priority_df: pd.DataFrame) -> pd.DataFrame:
    """Cross-check top candidates against the PHL authoritative catalog."""

    authoritative = load_authoritative_sample()  # Load authoritative sample for comparison.
    authoritative["pl_name"] = authoritative["pl_name"].str.strip()  # Normalise naming for safe joins.
    if "confidence" not in authoritative.columns:
        authoritative["confidence"] = np.nan  # Provide placeholder column when dataset lacks explicit ratings.

    merged = priority_df.merge(
        authoritative[["pl_name", "confidence"]],
        on="pl_name",
        how="left",
        suffixes=("", "_authoritative"),
    )  # Add authoritative confidence labels where available.
    merged = merged.rename(columns={"confidence": "phl_confidence"})  # Standardise column naming for exports.
    return merged  # Provide combined table for reporting and diagnostics.


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_priority_table(priority_df: pd.DataFrame) -> None:
    """Write the full priority table and top targets to disk for reproducibility."""

    priority_df.to_csv(RESULTS_DIR / "habitable_priority_scores.csv", index=False)  # Persist detailed table.
    top20 = priority_df.head(20)[
        [
            "pl_name",
            "priority_score",
            "priority_band",
            "pl_eqt",
            "pl_rade",
            "pl_orbper",
            "sy_vmag",
            "sy_snum",
        ]
    ]  # Select fields of interest for quick review.
    top20.to_markdown(RESULTS_DIR / "habitable_top20.md", index=False)  # Export top candidates as Markdown summary.


def export_authoritative_comparison(comparison: pd.DataFrame) -> None:
    """Save comparison between internal scores and the authoritative PHL list."""

    columns = [
        "pl_name",
        "priority_score",
        "priority_band",
        "phl_confidence",
    ]  # Columns emphasising alignment between datasets.
    comparison.to_csv(RESULTS_DIR / "habitable_authoritative_comparison.csv", index=False, columns=columns)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full habitable priority workflow with documentation-friendly outputs."""

    catalog = load_planet_catalog()  # Load the base NASA catalog.
    inputs = select_habitable_inputs(catalog)  # Filter to planets with complete and plausible data.

    if inputs.empty:  # Guardrail to prevent silent failure if filters remove all rows.
        raise ValueError("No planets meet the habitable input criteria; review filtering thresholds.")

    priority = compute_priority_scores(inputs)  # Compute composite scores and component metrics.
    comparison = compare_with_authoritative(priority)  # Align scores with the authoritative list for validation.

    export_priority_table(priority)  # Persist scoring outputs for reproducibility.
    export_authoritative_comparison(comparison)  # Save authoritative comparison diagnostics.

    plot_temp_radius(priority)  # Generate temperature-radius scatter visual.
    plot_component_bars(priority)  # Plot component breakdown for the top targets.
    plot_radar_chart(priority)  # Export radar charts illustrating score balance.

    print(
        f"Priority scoring complete. {len(priority)} planets evaluated; "
        f"{(priority['priority_band'] == 'High Priority').sum()} high-priority candidates identified."
    )  # Provide succinct CLI summary.


if __name__ == "__main__":  # Support command-line execution.
    main()  # Execute the full workflow when the module is run directly.
