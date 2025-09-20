"""Construct the interactive Plotly dashboard summarising the exoplanet analysis."""

from __future__ import annotations  # Ensure future-compatible typing behaviour.

from pathlib import Path  # Handle filesystem paths in an OS-agnostic fashion.
from typing import Tuple  # Provide explicit type hints for returned tuples.

import numpy as np  # Numerical utilities for validation checks.
import pandas as pd  # Primary data manipulation library for tabular analysis.
import plotly.express as px  # High-level Plotly API for interactive figures.
import plotly.io as pio  # Utilities to export Plotly figures as embeddable HTML snippets.

# Import project-specific helpers that load and score the cleaned planet catalog.
from habitable_priority import compute_priority_scores, load_planet_catalog, select_habitable_inputs
# Import method evolution helpers that prepare discovery method aggregates.
from method_evolution import (
    aggregate_method_timeseries,
    compute_facility_method_summary,
    label_detection_methods,
    load_detection_data,
)

# Resolve important project directories relative to this file for reproducibility.
ROOT = Path(__file__).resolve().parents[1]  # Repository root directory.
WEBAPP_DIR = ROOT / "webapp"  # Location where the generated dashboard will live.

WEBAPP_DIR.mkdir(parents=True, exist_ok=True)  # Ensure the web directory exists before writing files.


def build_detection_frames() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create the three summary tables required for method-related visuals."""

    detection_raw = load_detection_data()  # Load the cleaned detection metadata from the archive export.
    detection = label_detection_methods(detection_raw)  # Collapse sparse discovery methods into an "Other" bucket.
    timeseries = aggregate_method_timeseries(detection)  # Count annual discoveries for each method grouping.
    facility = compute_facility_method_summary(  # Summarise post-2015 facility contributions for stacked bars.
        detection,
        window=range(2015, detection["disc_year"].max() + 1),
    )
    metadata_cols = ["disc_year", "discoverymethod", "disc_facility"]  # Fields to preserve for traceability.
    detection_meta = detection[metadata_cols + ["method_group"]]  # Attach the derived grouping for audits.
    return timeseries, facility, detection_meta  # Provide all three tables to downstream consumers.


def build_priority_frame() -> pd.DataFrame:
    """Score habitable-zone candidates and attach contextual metadata for plotting."""

    base = load_planet_catalog()  # Read the canonical NASA catalog limited to default parameter sets.
    inputs = select_habitable_inputs(base)  # Filter to planets with complete measurements for scoring.
    priority = compute_priority_scores(inputs)  # Compute the weighted habitability scorecard.
    merged = priority.merge(  # Attach discovery context for hover tooltips in the scatter plot.
        base[["pl_name", "disc_year", "discoverymethod", "disc_facility"]],
        on="pl_name",
        how="left",
    )
    return merged  # Return the annotated scoring table for visualisation and validation.


def validate_detection_data(timeseries: pd.DataFrame, detection_meta: pd.DataFrame) -> None:
    """Assert that the aggregated detection tables exactly match the row-level catalog."""

    total_discoveries = detection_meta.shape[0]  # Count raw detection records after cleaning.
    aggregated_total = int(timeseries["discoveries"].sum())  # Sum the yearly discovery totals.
    if aggregated_total != total_discoveries:  # Prevent silent drift between raw and aggregated records.
        raise ValueError(
            "Aggregated method timeseries counts do not match the source catalog "
            f"(raw={total_discoveries}, aggregated={aggregated_total})."
        )

    method_breakdown = (
        detection_meta.groupby("method_group")["method_group"].count().sort_values(ascending=False)
    )  # Recompute counts by method directly from the row-level table.
    timeseries_breakdown = (
        timeseries.groupby("method_group")["discoveries"].sum().sort_values(ascending=False)
    )  # Compute the same totals from the aggregated output.
    if not method_breakdown.equals(timeseries_breakdown):  # Guard against grouping bugs.
        raise ValueError("Method share totals differ between detailed and aggregated datasets.")

    recent = detection_meta[detection_meta["disc_year"] >= 2015]  # Restrict to the post-2015 era used in documentation.
    share_since_2015 = (recent["method_group"] == "Transit").mean()  # Calculate the share of Transit discoveries since 2015.
    if not np.isclose(share_since_2015, 0.778, atol=0.02):  # Verify the headline statistic from the report.
        raise ValueError(
            "Transit share since 2015 deviates materially from the documented 77.8% figure "
            f"(observed={share_since_2015:.3f})."
        )


def validate_priority_data(priority: pd.DataFrame) -> None:
    """Ensure the habitability scoring table contains internally consistent values."""

    if priority["priority_score"].isna().any():  # Confirm the scoring algorithm produced numeric results.
        raise ValueError("Priority table contains missing scores; check the scoring pipeline.")

    if (priority["priority_score"] < 0).any() or (priority["priority_score"] > 1.2).any():
        raise ValueError("Priority scores fall outside the expected 0–1.2 window, indicating scaling issues.")

    if priority["priority_band"].isna().any():  # Confirm band labels are present for legend usage.
        raise ValueError("Some priority bands are missing; verify pd.cut configuration.")

    duplicates = priority["pl_name"].duplicated().any()  # Guarantee uniqueness per planet name.
    if duplicates:
        raise ValueError("Duplicate planet entries detected in the priority scoring table.")


def make_method_share_chart(timeseries: pd.DataFrame) -> str:
    """Render the stacked area chart capturing detection method share over time."""

    ts = timeseries.copy()  # Operate on a copy to avoid mutating the cached table.
    ts["share"] = ts["discoveries"] / ts.groupby("disc_year")["discoveries"].transform("sum")  # Compute yearly shares.
    fig = px.area(
        ts,
        x="disc_year",
        y="share",
        color="method_group",
        hover_data={"discoveries": True, "share": ":.1%"},
        labels={"disc_year": "Discovery year", "share": "Annual share"},
        title="Detection method share over time",
    )  # Configure the stacked area chart with informative hover text.
    fig.update_layout(yaxis_tickformat=",")  # Display year ticks without decimals.
    fig.update_yaxes(tickformat=",.0%")  # Show the share axis as percentages.
    return pio.to_html(fig, include_plotlyjs="cdn", full_html=False, div_id="method-share")  # Export to embeddable HTML.


def make_method_animation(timeseries: pd.DataFrame) -> str:
    """Build an animated bar chart showing yearly discovery totals by method."""

    fig = px.bar(
        timeseries,
        x="method_group",
        y="discoveries",
        color="method_group",
        animation_frame="disc_year",
        labels={"method_group": "Detection method", "discoveries": "Confirmed planets"},
        title="Year-by-year discovery counts by method",
    )  # Use Plotly Express animation to emphasise annual breakthroughs.
    ymax = timeseries["discoveries"].max() * 1.1  # Reserve headroom so the tallest bar is not clipped.
    fig.update_layout(yaxis_range=[0, ymax], showlegend=False)  # Fix the axis for stable animation scaling.
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id="method-animation")


def make_facility_chart(facility: pd.DataFrame) -> str:
    """Create a horizontal stacked bar chart for facility-method portfolios."""

    facility_sorted = facility.sort_values("share_within_facility", ascending=False)  # Order bars by contribution share.
    fig = px.bar(
        facility_sorted,
        x="share_within_facility",
        y="disc_facility",
        color="method_group",
        orientation="h",
        text="share_within_facility",
        labels={
            "share_within_facility": "Share of facility discoveries",
            "disc_facility": "Facility",
            "method_group": "Method",
        },
        title="Facility portfolios since 2015",
    )  # Compose the horizontal stacked bars with share labels.
    fig.update_traces(texttemplate="%{text:.1%}", textposition="inside")  # Format share labels as percentages.
    fig.update_layout(xaxis_tickformat=",.0%", yaxis=dict(categoryorder="total ascending"))  # Sort facilities bottom-up.
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id="facility-share")


def make_priority_scatter(priority: pd.DataFrame) -> str:
    """Generate the multi-encoding scatterplot for habitable candidate prioritisation."""

    fig = px.scatter(
        priority,
        x="pl_eqt",
        y="pl_rade",
        color="priority_band",
        size="observability_score",
        hover_data={
            "pl_name": True,
            "priority_score": ":.3f",
            "pl_orbper": ":.1f",
            "disc_year": True,
            "disc_facility": True,
        },
        labels={
            "pl_eqt": "Equilibrium temperature (K)",
            "pl_rade": "Radius (Earth radii)",
            "priority_band": "Priority band",
            "observability_score": "Observability",
        },
        title="Habitable-zone candidate landscape",
    )  # Encode physics-informed attributes into colour and size.
    fig.update_layout(legend_title="Priority band")  # Provide a descriptive legend title.
    fig.add_shape(
        type="rect",
        x0=240,
        x1=320,
        y0=0.7,
        y1=1.6,
        line=dict(color="rgba(0,0,0,0)"),
        fillcolor="rgba(135,206,250,0.15)",
    )  # Highlight the Earth-like temperature and radius window for presenters.
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id="priority-scatter")


def assemble_html(
    share_html: str,
    facility_html: str,
    priority_html: str,
    animation_html: str,
) -> None:
    """Embed the Plotly snippets into the dashboard HTML scaffold."""

    template = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>NASA Exoplanet Project Dashboard</title>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <style>
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 0; background: #0c1220; color: #f5f7ff; }}
    header {{ padding: 2rem 1.5rem; background: linear-gradient(135deg, #1c2340, #101525); }}
    main {{ padding: 1rem 1.5rem 3rem; max-width: 1100px; margin: 0 auto; }}
    h1 {{ margin: 0; font-size: 2.2rem; }}
    h2 {{ margin-top: 2.5rem; color: #9ad0ff; }}
    p {{ line-height: 1.6; }}
    .card {{ background: rgba(18, 24, 45, 0.92); border-radius: 12px; padding: 1.2rem; margin-top: 1.2rem; box-shadow: 0 12px 28px rgba(0, 0, 0, 0.35); }}
    .figure {{ margin-top: 1.2rem; }}
    a {{ color: #69c0ff; }}
    footer {{ text-align: center; padding: 1.5rem; font-size: 0.85rem; color: #9aa4c3; }}
  </style>
</head>
<body>
  <header>
    <h1>NASA Exoplanet Analysis – Interactive Briefing</h1>
    <p>Explore the evolution of detection strategies and the prioritisation of habitable-zone candidates through interactive graphics optimised for the Carolina Data Challenge presentation.</p>
  </header>
  <main>
    <section class=\"card\">
      <h2>1. Detection method evolution</h2>
      <p>The stacked area chart quantifies how detection methods traded dominance over the past three decades, while the animated bar race highlights annual breakthroughs. Hover to retrieve exact discovery counts and identify inflection years.</p>
      <div class=\"figure\">{share_html}</div>
      <div class=\"figure\">{animation_html}</div>
    </section>
    <section class=\"card\">
      <h2>2. Facility contribution mix</h2>
      <p>Inspect how flagship observatories allocate their observing time across methods. Click legend entries to isolate a single method and reveal the facilities carrying that technique.</p>
      <div class=\"figure\">{facility_html}</div>
    </section>
    <section class=\"card\">
      <h2>3. Habitable-zone candidate scoring</h2>
      <p>The scatterplot encodes temperature, size, observability, and discovery context for every scored planet. Zoom into the light-blue rectangle to focus on Earth-like regimes, or use the legend to highlight follow-up targets.</p>
      <div class=\"figure\">{priority_html}</div>
    </section>
  </main>
  <footer>
    Crafted for CDC 2025 · Generated automatically by analysis/build_dashboard.py · Data integrity checks executed prior to export.
  </footer>
</body>
</html>
"""  # Inline HTML template emphasising automated generation and validation.
    (WEBAPP_DIR / "index.html").write_text(template, encoding="utf-8")  # Persist the dashboard to disk.


def main() -> None:
    """Orchestrate data loading, validation, and dashboard creation."""

    timeseries, facility, detection_meta = build_detection_frames()  # Prepare method-focused aggregates.
    priority = build_priority_frame()  # Compute the habitability scoring table with context columns.

    validate_detection_data(timeseries, detection_meta)  # Confirm method aggregates are exact.
    validate_priority_data(priority)  # Guard against scoring inconsistencies prior to plotting.

    share_html = make_method_share_chart(timeseries)  # Build the area chart snippet for method share.
    animation_html = make_method_animation(timeseries)  # Create the animated bar race snippet.
    facility_html = make_facility_chart(facility)  # Render the facility contribution chart.
    priority_html = make_priority_scatter(priority)  # Produce the habitability scatter plot snippet.

    assemble_html(share_html, facility_html, priority_html, animation_html)  # Write the final HTML document.
    print(f"Dashboard written to {WEBAPP_DIR / 'index.html'}")  # Provide a console cue for reproducibility logs.


if __name__ == "__main__":  # Support CLI execution.
    main()  # Trigger the dashboard pipeline when run as a script.
