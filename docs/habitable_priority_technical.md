# Habitable-Zone Priority Pipeline — Technical Notes

## 1. Objective and Scope
The `analysis/habitable_priority.py` module ranks confirmed exoplanets that sit in temperate stellar environments so that follow-up telescope time can be allocated efficiently. It operationalises the "habitability" question into reproducible code by:

1. Standardising the NASA Planetary Systems catalog (`PS_2025.09.20_08.15.55.csv`).
2. Computing interpretable component scores that reflect thermal balance, size, irradiation, orbit, host star properties, and observability.
3. Aggregating these components into a single priority value between 0 and 1.
4. Exporting publication-ready tables and figures.
5. Cross-checking the high-priority cohort against an authoritative habitable-planet list when network access allows.

This document is the engineer-facing explanation of every major block in the file, the mathematics behind the scoring function, data dependencies, validation logic, and follow-on visualisation ideas.

## 2. Data Dependencies
| Dataset | Location | Purpose |
| --- | --- | --- |
| NASA Exoplanet Archive — Planetary Systems (2025-09-20 snapshot) | `PS_2025.09.20_08.15.55.csv` | Primary source for planet and stellar parameters. Loaded via `load_planet_catalog()`.
| Puerto Rico Habitable Exoplanets Catalog (PHL HEC) | `https://phl.upr.edu/.../habitable_exoplanets_catalog.csv` | External benchmark. Attempted first inside `load_authoritative_catalog()`; gracefully skipped if blocked.
| Curated NASA Exoplanet Archive sample | `data/authoritative_habitable_sample.csv` | Offline fallback for cross-checking when HTTP access to PHL is denied.

Every dataset is stored or cached locally to keep the pipeline deterministic. When external downloads succeed the latest public numbers are used; otherwise the curated sample ensures the comparison step still runs end-to-end.

## 3. Pipeline Walkthrough
### 3.1 Loading and Filtering
- `load_planet_catalog()` ingests the NASA CSV, keeps only the `default_flag = 1` rows, and returns a Pandas `DataFrame`. This mirrors the archive's recommendation to avoid duplicate parameter sets.
- `select_habitable_inputs(df)` enforces the minimal variable set defined in `REQUIRED_COLUMNS` (temperature, radius, insolation, orbital period, stellar temperature/radius, V magnitude, system multiplicity). It also applies conservative physical bounds to remove outliers (e.g., radii > 99th percentile, equilibrium temperature outside 150–450 K). The intent is to avoid skewing Gaussian kernels with hot Jupiters or ultra-long orbits.

### 3.2 Component Scoring
`compute_priority_scores(df)` implements seven interpretable sub-scores:

| Component | Code fragment | Intuition |
| --- | --- | --- |
| `temp_score` | `exp(-((pl_eqt - 288) / 60)^2)` | Peak habitability near Earth's equilibrium temperature, tolerant to ±120 K.
| `radius_score` | `exp(-((pl_rade - 1) / 0.35)^2)` | Prefers Earth-size planets while down-weighting giants.
| `insolation_score` | `exp(-((pl_insol - 1) / 0.5)^2)` | Highlights planets receiving Earth-like stellar flux.
| `period_score` | `exp(-((log10(orbper) - log10(365)) / 0.3)^2)` | Encourages ~1-year orbits, penalises extremely short/long periods.
| `stellar_temp_score` | `exp(-((st_teff - 5778) / 800)^2)` | Rewards Sun-like hosts; still gives moderate credit to F/M dwarfs.
| `observability_score` | `sigmoid(sy_vmag, midpoint=11.5, steepness=1.8)` | Logistic taper; bright systems (low `V` magnitude) are easier to observe.
| `system_score` | `1.0` for single-planet systems, `0.75` otherwise | Simplistic penalty recognising that multi-planet fits can complicate scheduling.

The Gaussian components are deliberately smooth to avoid hard thresholds, and the logistic brightness term ensures diminishing returns for very bright hosts while heavily penalising >15 magnitude targets.

### 3.3 Priority Aggregation
Weights are chosen so thermal balance and planet size dominate, while practical observability remains present but secondary:

| Component | Weight |
| --- | --- |
| `temp_score` | 0.24 |
| `radius_score` | 0.22 |
| `insolation_score` | 0.16 |
| `period_score` | 0.14 |
| `stellar_temp_score` | 0.14 |
| `observability_score` | 0.07 |
| `system_score` | 0.03 |

`priority_score` is calculated as the weighted average of the seven components. Planets are then binned into qualitative tiers via `pd.cut`:
- `High Priority` ≥ 0.70 (top science targets)
- `Follow-up` 0.55–0.70 (worth spectroscopic vetting)
- `Context` < 0.55 (supporting sample for population studies)

All intermediate component columns plus the final score/tier are preserved in the master CSV so downstream analysts can audit the math planet-by-planet.

### 3.4 Reporting and Visuals
- `save_priority_tables()` writes two artefacts: `results/habitable_priority_scores.csv` (full table) and `results/habitable_top20.md` (Markdown summary ready for the report or DevPost entry).
- `plot_temp_radius()`, `plot_component_bars()`, and `plot_radar_top()` generate the scatter, stacked bar, and radar chart in `figures/habitability/`. They show the overall habitable landscape, what drives the highest ranked planets, and how top targets compare across metrics.

### 3.5 External Validation Hook
`compare_with_authoritative_catalog(priority_df)` calls `load_authoritative_catalog()` to obtain a trusted habitable-planet roster. It merges that roster with the top 50 local candidates, saves `results/habitable_authoritative_comparison.csv`, and prints the match rate. When online downloads fail, the function transparently falls back to the curated NASA list so that analysts still receive a diagnostic table.

## 4. Accuracy and Cross-Checks
Running `python analysis/habitable_priority.py` after installing `requirements.txt` produces:

```
candidate_count: 37
high_priority_share: 0.027...
follow_up_share: 0.081...
median_score: 0.345...
Warning: Could not download the PHL Habitable Exoplanets Catalog... (HTTP 403)
Authoritative catalog match rate (top 50): 2.70%
```

The generated `results/habitable_authoritative_comparison.csv` highlights where the ranking agrees with widely cited habitable candidates (`Kepler-452 b` is an immediate match) and where it surfaces new prospects absent from the public lists. When network access is restored the same command will automatically consume the live PHL catalog and rerun the comparison without code changes.

For deeper auditing you can:
1. Open `results/habitable_priority_scores.csv` to trace the component contributions of any planet.
2. Review `results/habitable_authoritative_comparison.csv` to spot mismatches and prioritise manual vetting.
3. Update or expand `data/authoritative_habitable_sample.csv` with additional NASA links if judges request an explicit citation for every overlapping planet.

## 5. Visualisation Extensions
Beyond the static Matplotlib outputs already produced, consider these additions:
- **Interactive dashboard**: reuse `analysis/build_dashboard.py` to add a Plotly scatter with hover tooltips for the priority table, enabling judges to filter by score band and host star brightness.
- **Distance vs. observability map**: cross-join the `sy_dist` column (parse from the base CSV) to plot reachable targets for ground- vs. space-based follow-up.
- **Score waterfall per planet**: a Plotly waterfall chart showing how each component pushes the composite priority up or down relative to the median.
- **Time-to-transit schedule**: integrate orbital phase information to plan JWST/ARIEL observation windows.

These ideas reuse the same scoring output, keeping the analysis consistent while enriching the storytelling during the seven-minute pitch.

## 6. Reproducibility Checklist
1. `python -m pip install -r requirements.txt`
2. `python analysis/habitable_priority.py`
3. Inspect outputs under `results/` and `figures/habitability/`
4. (Optional) Ensure internet access and rerun step 2 to refresh the PHL comparison.

Version-control every regenerated asset so the DevPost submission, slides, and live demo all reference the identical numbers documented here.
