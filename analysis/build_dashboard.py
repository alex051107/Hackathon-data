"""Generate the interactive dashboard summarising the habitability scoring results."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd
import plotly.express as px
import plotly.io as pio

from habitable_priority import (
    compute_priority_scores,
    load_planet_catalog,
    select_habitable_inputs,
)

ROOT = Path(__file__).resolve().parents[1]
WEBAPP_DIR = ROOT / "webapp"
WEBAPP_DIR.mkdir(parents=True, exist_ok=True)


def build_priority_frame() -> pd.DataFrame:
    """Score habitable-zone candidates and attach contextual metadata for Plotly charts."""

    base = load_planet_catalog()
    inputs = select_habitable_inputs(base)
    priority = compute_priority_scores(inputs)

    enriched = priority.merge(
        base[
            [
                "pl_name",
                "disc_year",
                "discoverymethod",
                "disc_facility",
                "sy_pnum",
            ]
        ],
        on="pl_name",
        how="left",
    )
    return enriched


def validate_priority_data(priority: pd.DataFrame) -> None:
    """Assert that the scoring output contains the expected ranges and uniqueness."""

    if priority["priority_score"].isna().any():
        raise ValueError("Priority table contains missing scores; rerun the scoring pipeline.")

    if priority["pl_name"].duplicated().any():
        raise ValueError("Duplicate planet entries detected in the priority table.")

    if (priority["priority_score"] < 0).any() or (priority["priority_score"] > 1.05).any():
        raise ValueError("Priority scores fall outside the expected 0–1 window.")

    if priority["priority_band"].isna().any():
        raise ValueError("Priority band labels are missing for one or more planets.")


def make_priority_scatter(priority: pd.DataFrame) -> str:
    """Render the temperature-radius scatter encoded by priority band and observability."""

    fig = px.scatter(
        priority,
        x="pl_eqt",
        y="pl_rade",
        color="priority_band",
        size="observability_score",
        hover_data={
            "pl_name": True,
            "priority_score": ":.3f",
            "climate_score": ":.3f",
            "structure_score": ":.3f",
            "observability_score": ":.3f",
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
    )
    fig.update_layout(legend_title="Priority band")
    fig.add_shape(
        type="rect",
        x0=240,
        x1=320,
        y0=0.8,
        y1=1.6,
        line=dict(color="rgba(0,0,0,0)"),
        fillcolor="rgba(135,206,250,0.18)",
    )
    return pio.to_html(fig, include_plotlyjs="cdn", full_html=False, div_id="priority-scatter")


def make_pillar_bar(priority: pd.DataFrame, top_n: int = 12) -> str:
    """Produce a stacked bar chart summarising pillar balance for the leading targets."""

    components = ["climate_score", "structure_score", "observability_score", "system_score"]
    melted = (
        priority.head(top_n)
        .melt(id_vars=["pl_name", "priority_score"], value_vars=components, var_name="pillar", value_name="score")
    )
    fig = px.bar(
        melted,
        x="pl_name",
        y="score",
        color="pillar",
        labels={"pl_name": "Planet", "score": "Score", "pillar": "Pillar"},
        title="Pillar contributions for top-ranked planets",
    )
    fig.update_layout(xaxis_tickangle=45)
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id="pillar-bars")


def make_observability_scatter(priority: pd.DataFrame) -> str:
    """Plot host brightness against transit depth to highlight follow-up feasibility."""

    fig = px.scatter(
        priority,
        x="sy_vmag",
        y="transit_depth_ppm",
        color="priority_score",
        size="structure_score",
        hover_data={
            "pl_name": True,
            "priority_band": True,
            "sy_dist": ":.1f",
            "transit_depth_ppm": ":.0f",
        },
        labels={
            "sy_vmag": "Host V magnitude",
            "transit_depth_ppm": "Transit depth (ppm)",
            "priority_score": "Priority score",
            "structure_score": "Structure score",
        },
        title="Observability phase space",
    )
    fig.update_layout(yaxis_type="log")
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id="observability-scatter")


def make_band_table(priority: pd.DataFrame) -> Tuple[str, pd.DataFrame]:
    """Create a Markdown-ready table summarising band counts and medians."""

    summary = (
        priority.groupby("priority_band", observed=False)
        .agg(
            count=("pl_name", "count"),
            median_priority=("priority_score", "median"),
            median_distance=("sy_dist", "median"),
        )
        .reset_index()
    )
    summary["median_priority"] = summary["median_priority"].round(3)
    summary["median_distance"] = summary["median_distance"].round(1)
    return summary.to_html(index=False, classes="band-table"), summary


def build_dashboard() -> None:
    """Assemble the Plotly dashboard and persist the HTML bundle."""

    priority = build_priority_frame()
    validate_priority_data(priority)

    scatter_html = make_priority_scatter(priority)
    pillar_html = make_pillar_bar(priority)
    observability_html = make_observability_scatter(priority)
    table_html, band_summary = make_band_table(priority)

    html = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>Habitable Candidate Dashboard</title>
  <style>
    body {{ font-family: "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 2rem; background: #f7f8fa; }}
    h1 {{ margin-bottom: 0.25rem; }}
    h2 {{ margin-top: 2rem; }}
    .chart {{ margin-bottom: 3rem; background: #fff; padding: 1.5rem; border-radius: 12px; box-shadow: 0 8px 20px rgba(0,0,0,0.08); }}
    table.band-table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    table.band-table th, table.band-table td {{ border: 1px solid #ddd; padding: 0.6rem; text-align: center; }}
    table.band-table th {{ background: #0b3d91; color: #fff; }}
    .badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 999px; background: #0b3d91; color: #fff; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <h1>Habitable Candidate Dashboard</h1>
  <p class=\"badge\">Updated automatically from analysis/habitable_priority.py</p>

  <section class=\"chart\">
    <h2>1. Priority landscape</h2>
    <p>The scatterplot highlights how equilibrium temperature, size, and observability combine to set the final priority tiers.</p>
    {scatter_html}
  </section>

  <section class=\"chart\">
    <h2>2. Pillar balance for the top cohort</h2>
    <p>The stacked bars show how climate suitability, internal structure, observability, and system simplicity contribute for the leading candidates.</p>
    {pillar_html}
  </section>

  <section class=\"chart\">
    <h2>3. Observability phase space</h2>
    <p>Targets in the lower-left combine bright hosts with deep transits, making them ideal for rapid atmospheric follow-up.</p>
    {observability_html}
  </section>

  <section class=\"chart\">
    <h2>4. Priority band summary</h2>
    <p>The table summarises how many planets fall into each tier and the typical distance to the system.</p>
    {table_html}
  </section>
</body>
</html>
"""

    (WEBAPP_DIR / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    build_dashboard()
