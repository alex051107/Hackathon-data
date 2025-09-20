"""Generate an interactive Plotly dashboard for the exoplanet project."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.io as pio

from habitable_priority import compute_priority_scores, load_planet_catalog, select_habitable_inputs
from method_evolution import (
    aggregate_method_timeseries,
    compute_facility_method_summary,
    label_detection_methods,
    load_detection_data,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
WEBAPP_DIR = ROOT / "webapp"

WEBAPP_DIR.mkdir(parents=True, exist_ok=True)


def build_detection_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detection = label_detection_methods(load_detection_data())
    timeseries = aggregate_method_timeseries(detection)
    facility = compute_facility_method_summary(
        detection, window=range(2015, detection["disc_year"].max() + 1)
    )
    metadata_cols = ["disc_year", "discoverymethod", "disc_facility"]
    detection_meta = detection[metadata_cols + ["method_group"]]
    return timeseries, facility, detection_meta


def build_priority_frame() -> pd.DataFrame:
    base = load_planet_catalog()
    inputs = select_habitable_inputs(base)
    priority = compute_priority_scores(inputs)
    merged = priority.merge(
        base[["pl_name", "disc_year", "discoverymethod", "disc_facility"]],
        on="pl_name",
        how="left",
    )
    return merged


def make_method_share_chart(timeseries: pd.DataFrame) -> str:
    ts = timeseries.copy()
    ts["share"] = ts["discoveries"] / ts.groupby("disc_year")["discoveries"].transform("sum")
    fig = px.area(
        ts,
        x="disc_year",
        y="share",
        color="method_group",
        hover_data={"discoveries": True, "share": ":.1%"},
        labels={"disc_year": "Discovery year", "share": "Annual share"},
        title="Detection method share over time",
    )
    fig.update_layout(yaxis_tickformat=",")
    fig.update_yaxes(tickformat=",.0%")
    return pio.to_html(fig, include_plotlyjs="cdn", full_html=False, div_id="method-share")


def make_method_animation(timeseries: pd.DataFrame) -> str:
    fig = px.bar(
        timeseries,
        x="method_group",
        y="discoveries",
        color="method_group",
        animation_frame="disc_year",
        labels={"method_group": "Detection method", "discoveries": "Confirmed planets"},
        title="Year-by-year discovery counts by method",
    )
    ymax = timeseries["discoveries"].max() * 1.1
    fig.update_layout(yaxis_range=[0, ymax], showlegend=False)
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id="method-animation")


def make_facility_chart(facility: pd.DataFrame) -> str:
    facility_sorted = facility.sort_values("share_within_facility", ascending=False)
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
    )
    fig.update_traces(texttemplate="%{text:.1%}", textposition="inside")
    fig.update_layout(xaxis_tickformat=",.0%", yaxis=dict(categoryorder="total ascending"))
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id="facility-share")


def make_priority_scatter(priority: pd.DataFrame) -> str:
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
    )
    fig.update_layout(legend_title="Priority band")
    fig.add_shape(
        type="rect",
        x0=240,
        x1=320,
        y0=0.7,
        y1=1.6,
        line=dict(color="rgba(0,0,0,0)"),
        fillcolor="rgba(135,206,250,0.15)",
    )
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id="priority-scatter")


def assemble_html(share_html: str, facility_html: str, priority_html: str, animation_html: str) -> None:
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
    Crafted for CDC 2025 · Generated automatically by analysis/build_dashboard.py
  </footer>
</body>
</html>
"""
    (WEBAPP_DIR / "index.html").write_text(template, encoding="utf-8")


def main() -> None:
    timeseries, facility, _ = build_detection_frames()
    priority = build_priority_frame()

    share_html = make_method_share_chart(timeseries)
    animation_html = make_method_animation(timeseries)
    facility_html = make_facility_chart(facility)
    priority_html = make_priority_scatter(priority)

    assemble_html(share_html, facility_html, priority_html, animation_html)
    print(f"Dashboard written to {WEBAPP_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
