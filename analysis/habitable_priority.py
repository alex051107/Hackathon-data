"""Habitable-zone candidate prioritisation with physics-guided scoring revisions."""

from __future__ import annotations  # Allow postponed evaluation of annotations for compatibility.

from io import BytesIO  # Buffer external CSV downloads in memory before handing to pandas.
from pathlib import Path  # Resolve project-relative paths robustly across platforms.
from typing import Dict, List, Optional  # Provide explicit type hints for shared helpers.
from urllib.error import URLError  # Catch connectivity failures when requesting authoritative catalogues.
from urllib.request import Request, urlopen  # Perform HTTP requests with a custom user agent.

import matplotlib.pyplot as plt  # Matplotlib powers the static figures exported alongside the tables.
import numpy as np  # NumPy enables fast vectorised scoring transforms across many planets at once.
import pandas as pd  # Pandas provides the tabular wrangling primitives used throughout the pipeline.
import seaborn as sns  # Seaborn supplies presentation-ready defaults for Matplotlib charts.

# ---------------------------------------------------------------------------
# Project paths and constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]  # Resolve the repository root relative to this script file.
DATA_PATH = ROOT / "PS_2025.09.20_08.15.55.csv"  # NASA Planetary Systems table snapshot bundled with the project.
FIG_DIR = ROOT / "figures" / "habitability"  # Folder where diagnostic PNGs are exported.
RESULTS_DIR = ROOT / "results"  # Directory that stores reproducible CSV/Markdown artefacts.
AUTHORITATIVE_SAMPLE_PATH = ROOT / "data" / "authoritative_habitable_sample.csv"  # Offline benchmark table.
PHL_CATALOG_URL = (
    "https://phl.upr.edu/projects/habitable-exoplanets-catalog/data/"
    "habitable_exoplanets_catalog.csv"
)  # Public URL for the Planetary Habitability Laboratory reference list.

FIG_DIR.mkdir(parents=True, exist_ok=True)  # Ensure the figure output directory exists before plotting.
RESULTS_DIR.mkdir(parents=True, exist_ok=True)  # Create the results directory when running the pipeline fresh.

sns.set_theme(style="whitegrid")  # Apply a consistent chart style across figures for the report.

SOLAR_RADIUS_TO_EARTH = 109.076  # Conversion factor between solar and Earth radii for transit depth estimates.
EARTH_EQ_TEMP = 255.0  # Reference equilibrium temperature (K) used to approximate insolation when missing.

REQUIRED_COLUMNS = [
    "pl_name",  # Unique planet identifier retained throughout the outputs.
    "hostname",  # Host star identifier used in authoritative cross-checks.
    "pl_eqt",  # Planetary equilibrium temperature (K) captures the climate regime.
    "pl_rade",  # Planet radius (Earth radii) differentiates terrestrial from gaseous worlds.
    "pl_orbper",  # Orbital period (days) acts as a proxy for dynamical stability and seasonality.
    "st_teff",  # Stellar effective temperature (K) links to host spectral class and activity.
    "st_rad",  # Stellar radius (solar radii) supports transit depth calculations.
    "sy_vmag",  # Apparent visual magnitude gauges how bright the host is to observers.
    "sy_dist",  # Distance from Earth (parsec) informs follow-up feasibility.
    "sy_snum",  # Number of stars in the system (single vs multi-star stability considerations).
]  # Every column required for scoring and observability diagnostics.

CLIMATE_COMPONENTS = [
    "temp_score",  # Membership in the conservative equilibrium-temperature window.
    "insolation_score",  # Membership in the Kopparapu-inspired stellar flux window.
    "period_score",  # Orbital period suitability for long-term stability and scheduling.
    "stellar_temp_score",  # Preference for host stars with moderate effective temperatures.
]  # The four sub-metrics that roll into the climate pillar.

STRUCTURE_COMPONENTS = [
    "radius_score",  # Favour Earth-sized planets relative to giants or dwarfs.
    "mass_score",  # Reward masses consistent with rocky or ocean worlds.
]  # The ingredients of the planet-structure pillar.

OBSERVABILITY_COMPONENT_WEIGHTS: Dict[str, float] = {
    "brightness_score": 0.4,  # Bright hosts produce higher signal-to-noise in spectroscopy.
    "transit_visibility_score": 0.35,  # Deep transits simplify atmospheric retrievals.
    "distance_score": 0.25,  # Nearby systems reduce exposure time requirements.
}  # Relative emphasis when averaging the observability sub-metrics.

AGGREGATE_WEIGHTS: Dict[str, float] = {
    "climate_score": 0.45,  # Climate suitability carries the heaviest influence on final ranking.
    "structure_score": 0.25,  # Planet size/mass balance ensures rocky worlds bubble to the top.
    "observability_score": 0.22,  # Practical follow-up considerations remain prominent.
    "system_score": 0.08,  # Dynamical simplicity is valued but does not override science potential.
}  # Overall weighting scheme applied when combining the four scoring pillars.

# ---------------------------------------------------------------------------
# Helper transforms
# ---------------------------------------------------------------------------

def trapezoidal_membership(values: pd.Series, lower_start: float, lower_full: float,
                           upper_full: float, upper_end: float) -> np.ndarray:
    """Return trapezoidal fuzzy membership scores between 0 and 1 for the supplied window."""

    array = values.to_numpy(dtype=float)  # Convert to NumPy for vectorised math.
    ascend = np.clip((array - lower_start) / (lower_full - lower_start), 0, 1)  # Linear ramp up.
    descend = np.clip((upper_end - array) / (upper_end - upper_full), 0, 1)  # Linear ramp down.
    return np.minimum.reduce([ascend, descend, np.ones_like(array)])  # Cap at 1 inside the plateau.


def logistic_decreasing(values: pd.Series, midpoint: float, width: float) -> np.ndarray:
    """Logistic curve that maps low values to ~1 and high values to ~0."""

    array = values.to_numpy(dtype=float)  # Vectorise the computation.
    return 1 / (1 + np.exp((array - midpoint) / width))  # Classical logistic centred on the chosen midpoint.


def logistic_increasing(values: pd.Series, midpoint: float, width: float) -> np.ndarray:
    """Logistic curve that maps low values to ~0 and high values to ~1."""

    array = values.to_numpy(dtype=float)  # Convert Series to ndarray for speed.
    return 1 / (1 + np.exp(-(array - midpoint) / width))  # Rising logistic controlled by midpoint and slope.


def compute_transit_depth_ppm(radius_earth: pd.Series, star_radius_solar: pd.Series) -> np.ndarray:
    """Estimate transit depth (parts per million) assuming a central transit geometry."""

    planet_to_star = radius_earth.to_numpy(dtype=float) / (star_radius_solar.to_numpy(dtype=float) * SOLAR_RADIUS_TO_EARTH)
    depth_fraction = np.square(planet_to_star)  # Fractional loss of light during transit.
    return depth_fraction * 1e6  # Express the depth in parts per million for human readability.


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def load_planet_catalog() -> pd.DataFrame:
    """Load the NASA planetary systems snapshot restricted to default parameter sets."""

    df = pd.read_csv(DATA_PATH, comment="#")  # Parse the CSV while skipping metadata comment lines.
    df = df[df["default_flag"] == 1].copy()  # Retain only the canonical solution for each planet.
    return df  # Provide the cleaned base catalog for downstream filtering.


def select_habitable_inputs(df: pd.DataFrame) -> pd.DataFrame:
    """Filter the catalog to planets with complete, physically plausible habitability inputs."""

    filtered = df.dropna(subset=REQUIRED_COLUMNS).copy()  # Remove rows lacking any required measurements.

    insolation_proxy = pd.Series(
        np.power(filtered["pl_eqt"].to_numpy(dtype=float) / EARTH_EQ_TEMP, 4), index=filtered.index
    )  # Approximate flux when missing.
    filtered.loc[:, "pl_insol_effective"] = filtered["pl_insol"].fillna(insolation_proxy)  # Store the filled column explicitly.

    filtered = filtered[filtered["pl_eqt"].between(150, 450)]  # Restrict to temperate climates.
    filtered = filtered[filtered["pl_insol_effective"].between(0.1, 3.0)]  # Keep moderate stellar flux values.
    filtered = filtered[filtered["pl_rade"].between(0.4, 3.5)]  # Discard ultra-small and giant planets.

    mass_proxy = filtered["pl_bmasse"].copy()  # Start with measured masses when available.
    missing_mass = mass_proxy.isna()
    if missing_mass.any():
        radii = filtered.loc[missing_mass, "pl_rade"].to_numpy(dtype=float)
        approx_mass = np.where(
            radii <= 1.5,
            np.power(radii, 3.7),  # Rocky scaling from mass-radius studies.
            1.5 * np.power(radii, 2.3),  # Sub-Neptune scaling for larger radii.
        )
        mass_proxy.loc[missing_mass] = approx_mass
    filtered.loc[:, "pl_bmasse_filled"] = mass_proxy  # Preserve the filled mass for scoring transparency.
    filtered = filtered[filtered["pl_bmasse_filled"].between(0.2, 15)]  # Focus on terrestrial-to-mini-Neptune masses.
    filtered = filtered[filtered["pl_orbper"].between(3, 800)]  # Remove extremely short or poorly constrained periods.
    filtered = filtered[filtered["st_teff"].between(3000, 7200)]  # Limit to FGKM-like hosts.
    filtered = filtered[filtered["st_rad"].between(0.2, 2.5)]  # Avoid evolved giants or under-sized radii entries.
    filtered = filtered[filtered["sy_vmag"].between(0, 18)]  # Ensure the host brightness is within observable limits.
    filtered = filtered[filtered["sy_dist"] <= 1000]  # Exclude very distant systems unlikely to be practical targets.

    return filtered  # Hand back the curated dataset ready for scoring.


# ---------------------------------------------------------------------------
# Scoring model
# ---------------------------------------------------------------------------

def compute_priority_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute pillar scores and the aggregate habitability priority for each candidate planet."""

    data = df.copy()  # Work on a copy to preserve the caller's DataFrame.

    data.loc[:, "temp_score"] = trapezoidal_membership(data["pl_eqt"], 180, 240, 320, 400)  # Conservative temperature window.
    data.loc[:, "insolation_score"] = trapezoidal_membership(
        pd.Series(data["pl_insol_effective"].to_numpy(dtype=float)), 0.2, 0.32, 1.7, 2.2
    )  # Kopparapu flux window using filled flux values.

    log_period = np.log10(data["pl_orbper"].to_numpy(dtype=float))  # Log-scale periods to even out long tails.
    data.loc[:, "period_score"] = trapezoidal_membership(pd.Series(log_period), np.log10(15), np.log10(30), np.log10(400), np.log10(800))
    data.loc[:, "stellar_temp_score"] = trapezoidal_membership(data["st_teff"], 3300, 4100, 6400, 7200)  # Prefer calm FGK hosts.

    data.loc[:, "climate_score"] = data[CLIMATE_COMPONENTS].mean(axis=1)  # Average the climate-oriented sub-metrics.

    data.loc[:, "radius_score"] = trapezoidal_membership(data["pl_rade"], 0.5, 0.85, 1.6, 2.5)  # Highlight Earth-sized planets.
    data.loc[:, "mass_score"] = trapezoidal_membership(
        pd.Series(data["pl_bmasse_filled"].to_numpy(dtype=float)), 0.3, 0.7, 5.0, 10.0
    )  # Emphasise rocky/oceanic masses including proxy estimates.
    data.loc[:, "structure_score"] = data[STRUCTURE_COMPONENTS].mean(axis=1)  # Roll-up for the planet structure pillar.

    depth_ppm = compute_transit_depth_ppm(data["pl_rade"], data["st_rad"])  # Estimate how deep a transit would be.
    data.loc[:, "transit_depth_ppm"] = depth_ppm  # Persist depth for documentation and hover-tooltips.

    depth_log = np.log10(np.clip(depth_ppm, 5, None))  # Avoid log10(0) by clipping at a minimal detectable depth.
    data.loc[:, "transit_visibility_score"] = logistic_increasing(pd.Series(depth_log), midpoint=2.6, width=0.35)
    data.loc[:, "brightness_score"] = logistic_decreasing(data["sy_vmag"], midpoint=11.5, width=1.2)
    data.loc[:, "distance_score"] = logistic_decreasing(pd.Series(np.log10(data["sy_dist"].to_numpy(dtype=float))), midpoint=np.log10(80), width=0.4)

    observability_components = sum(
        data[key] * weight for key, weight in OBSERVABILITY_COMPONENT_WEIGHTS.items()
    )  # Weighted sum across observability sub-metrics.
    data.loc[:, "observability_score"] = observability_components / sum(OBSERVABILITY_COMPONENT_WEIGHTS.values())

    data.loc[:, "system_score"] = np.where(
        data["sy_snum"] <= 1,
        1.0,
        np.clip(1.0 - 0.25 * (data["sy_snum"] - 1), 0.45, 0.85),
    )  # Penalise multi-star systems without fully excluding them.

    total_weight = sum(AGGREGATE_WEIGHTS.values())  # Normalise the weighted sum below.
    data.loc[:, "priority_score"] = (
        data["climate_score"] * AGGREGATE_WEIGHTS["climate_score"]
        + data["structure_score"] * AGGREGATE_WEIGHTS["structure_score"]
        + data["observability_score"] * AGGREGATE_WEIGHTS["observability_score"]
        + data["system_score"] * AGGREGATE_WEIGHTS["system_score"]
    ) / total_weight  # Weighted combination of the four pillars.

    bins = [0, 0.58, 0.7, 1.0]  # Thresholds tuned after inspecting score distributions.
    labels = ["Context", "Follow-up", "High Priority"]  # Human-readable categories for storytelling.
    data.loc[:, "priority_band"] = pd.cut(
        data["priority_score"], bins=bins, labels=labels, include_lowest=True
    )  # Assign each planet to a qualitative tier.

    ordered_columns: List[str] = REQUIRED_COLUMNS + [
        "pl_insol",  # Original insolation value when available (may be NaN).
        "pl_insol_effective",  # Filled flux used for scoring to retain transparency.
        "pl_bmasse",  # Report measured mass when available (may be NaN after filtering).
        "pl_bmasse_filled",  # Proxy mass used for scoring transparency.
        "temp_score",
        "insolation_score",
        "period_score",
        "stellar_temp_score",
        "climate_score",
        "radius_score",
        "mass_score",
        "structure_score",
        "transit_depth_ppm",
        "transit_visibility_score",
        "brightness_score",
        "distance_score",
        "observability_score",
        "system_score",
        "priority_score",
        "priority_band",
    ]  # Preserve both component and aggregate scores for full transparency.

    return data[ordered_columns].sort_values("priority_score", ascending=False)  # Highest scores first for downstream use.


# ---------------------------------------------------------------------------
# Visualisation helpers
# ---------------------------------------------------------------------------

def plot_temp_radius(priority_df: pd.DataFrame) -> None:
    """Render a temperature-radius scatter coloured by composite priority."""

    plt.figure(figsize=(10, 6))  # Allocate canvas sized for slides.
    scatter = sns.scatterplot(
        data=priority_df,
        x="pl_eqt",
        y="pl_rade",
        hue="priority_score",
        size="observability_score",
        palette="viridis",
        alpha=0.75,
        edgecolor="none",
    )  # Encode science priority and follow-up ease simultaneously.
    scatter.set(
        title="Habitable zone candidate landscape",
        xlabel="Planet equilibrium temperature (K)",
        ylabel="Planet radius (Earth radii)",
    )
    plt.axvspan(240, 320, color="lightgray", alpha=0.2, label="Conservative habitable band")  # Highlight climate sweet spot.
    plt.axhspan(0.8, 1.6, color="lightskyblue", alpha=0.2, label="Earth-size range")  # Highlight desired radii.
    plt.legend(loc="upper right", title="Priority score")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "temp_radius_priority.png", dpi=300)  # Persist scatter for documentation.
    plt.close()


def plot_component_bars(priority_df: pd.DataFrame, top_n: int = 12) -> None:
    """Plot stacked pillar contributions for the highest-ranked planets."""

    components = ["climate_score", "structure_score", "observability_score", "system_score"]  # Pillar labels.
    top = priority_df.head(top_n).copy()  # Limit to manageable number of bars.
    melted = top.melt(
        id_vars=["pl_name", "priority_score"],
        value_vars=components,
        var_name="pillar",
        value_name="score",
    )  # Convert to tidy format for stacking.

    plt.figure(figsize=(12, 7))
    sns.barplot(data=melted, x="pl_name", y="score", hue="pillar", palette="viridis")
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Pillar contribution")
    plt.xlabel("Planet")
    plt.title("Pillar balance across top-ranked candidates")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "priority_components.png", dpi=300)
    plt.close()


def plot_radar_chart(priority_df: pd.DataFrame, top_n: int = 5) -> None:
    """Create radar plots showing how leading planets balance the four pillars."""

    components = ["climate_score", "structure_score", "observability_score", "system_score"]
    theta = np.linspace(0, 2 * np.pi, len(components), endpoint=False)
    theta = np.concatenate([theta, theta[:1]])  # Close the radar loop.

    plt.figure(figsize=(10, 10))
    for idx, (_, row) in enumerate(priority_df.head(top_n).iterrows(), start=1):
        values = row[components].to_numpy(dtype=float)
        values = np.concatenate([values, values[:1]])
        ax = plt.subplot(3, 2, idx, polar=True)
        ax.plot(theta, values, label=row["pl_name"])
        ax.fill(theta, values, alpha=0.3)
        ax.set_xticks(theta[:-1])
        ax.set_xticklabels(components, fontsize=9)
        ax.set_title(row["pl_name"], fontsize=12)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "priority_radar.png", dpi=300)
    plt.close()


# ---------------------------------------------------------------------------
# Authoritative sample comparison
# ---------------------------------------------------------------------------

def download_authoritative_catalog() -> Optional[pd.DataFrame]:
    """Fetch the authoritative habitable exoplanet sample from PHL when network access permits."""

    try:
        req = Request(PHL_CATALOG_URL, headers={"User-Agent": "CDC-Project/1.0"})
        with urlopen(req, timeout=15) as response:
            payload = response.read()
        buffer = BytesIO(payload)
        df = pd.read_csv(buffer)
        return df
    except URLError:
        return None  # Fall back to the cached sample when offline.


def load_authoritative_sample() -> pd.DataFrame:
    """Load the authoritative sample from disk, downloading it if necessary."""

    if AUTHORITATIVE_SAMPLE_PATH.exists():
        return pd.read_csv(AUTHORITATIVE_SAMPLE_PATH)

    remote = download_authoritative_catalog()
    if remote is not None:
        remote.to_csv(AUTHORITATIVE_SAMPLE_PATH, index=False)
        return remote

    raise FileNotFoundError(
        "Authoritative habitable sample unavailable locally and remote download failed."
    )


def compare_with_authoritative(priority_df: pd.DataFrame) -> pd.DataFrame:
    """Cross-check internal scores with the authoritative habitable list."""

    authoritative = load_authoritative_sample()
    authoritative["pl_name"] = authoritative["pl_name"].str.strip()
    if "confidence" not in authoritative.columns:
        authoritative["confidence"] = np.nan

    merged = priority_df.merge(
        authoritative[["pl_name", "confidence"]],
        on="pl_name",
        how="left",
        suffixes=("", "_authoritative"),
    )
    merged = merged.rename(columns={"confidence": "phl_confidence"})
    return merged


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_priority_table(priority_df: pd.DataFrame) -> None:
    """Write the full priority table and a human-readable top list to disk."""

    priority_df.to_csv(RESULTS_DIR / "habitable_priority_scores.csv", index=False)

    columns = [
        "pl_name",
        "hostname",
        "priority_score",
        "priority_band",
        "climate_score",
        "structure_score",
        "observability_score",
        "system_score",
        "pl_eqt",
        "pl_insol_effective",
        "pl_rade",
        "pl_bmasse",
        "pl_bmasse_filled",
        "pl_orbper",
        "sy_vmag",
        "sy_dist",
        "transit_depth_ppm",
    ]
    top20 = priority_df.head(20)[columns]
    top20.to_markdown(RESULTS_DIR / "habitable_top20.md", index=False)


def export_authoritative_comparison(comparison: pd.DataFrame) -> None:
    """Save the join between the internal ranking and the authoritative list."""

    columns = [
        "pl_name",
        "priority_score",
        "priority_band",
        "climate_score",
        "structure_score",
        "observability_score",
        "system_score",
        "phl_confidence",
    ]
    comparison.to_csv(RESULTS_DIR / "habitable_authoritative_comparison.csv", index=False, columns=columns)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the habitability scoring workflow end-to-end."""

    catalog = load_planet_catalog()
    inputs = select_habitable_inputs(catalog)

    if inputs.empty:
        raise ValueError("No planets meet the habitability input criteria; revisit filters and source data.")

    priority = compute_priority_scores(inputs)
    comparison = compare_with_authoritative(priority)

    export_priority_table(priority)
    export_authoritative_comparison(comparison)

    plot_temp_radius(priority)
    plot_component_bars(priority)
    plot_radar_chart(priority)

    high_priority = (priority["priority_band"] == "High Priority").sum()
    follow_up = (priority["priority_band"] == "Follow-up").sum()
    print(
        "Priority scoring complete. "
        f"{len(priority)} planets evaluated; {high_priority} high-priority and {follow_up} follow-up targets identified."
    )


if __name__ == "__main__":
    main()
