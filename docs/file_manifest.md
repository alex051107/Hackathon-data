# File Manifest

This manifest lists every tracked file in the repository, grouped by directory,
and explains how each asset contributes to the Carolina Data Challenge
exoplanet analysis project.  Use it as a reference when navigating the codebase
or preparing materials for GitHub / DevPost submission.

## Repository root

| Path | Category | Purpose | Notes |
| --- | --- | --- | --- |
| `README.md` | Documentation | High-level project overview, directory map, reproduction instructions, and documentation index. | Authored for public GitHub presentation. |
| `requirements.txt` | Environment | Python dependency pin list used to recreate the analysis environment. | Install via `pip install -r requirements.txt`. |
| `International Astronaut Database.csv` | Raw data | CDC-provided social science dataset snapshot retained for provenance. | Not used directly in the exoplanet analyses. |
| `PS_2025.09.20_08.15.55.csv` | Raw data | NASA Planetary Systems table download captured at hackathon start. | Serves as the canonical raw data snapshot for scripts in `analysis/`. |

## `analysis/`

| File | Description | Key outputs |
| --- | --- | --- |
| `ps_overview.py` | Shared utilities for loading the Planetary Systems snapshot, cleaning key fields, and producing baseline exploratory figures (method share, temperature-radius scatter, orbital period boxplots). | Generates baseline exploratory figures under `figures/` when executed (PNG outputs are ignored by git). |
| `method_evolution.py` | End-to-end pipeline for the "discovery method evolution" storyline: cleans observations, aggregates annual counts, blends facility metadata, and fits a Holt-Winters forecast. | CSV summaries in `results/method_timeseries.csv` & `results/method_forecast.csv`; facility shares in `results/facility_method_summary.csv`; optional PNG plots generated under `figures/method_evolution/` (not tracked). |
| `habitable_priority.py` | Builds the habitable-zone prioritisation score from planetary and stellar metrics, validates against an authoritative catalogue, and exports ranked tables plus diagnostic plots. | `results/habitable_priority_scores.csv`, `results/habitable_authoritative_comparison.csv`, `results/habitable_top20.md`; optional PNG diagnostics generated under `figures/habitability/` (not tracked). |
| `validate_analysis.py` | Regression test script that reruns all analysis modules, checks for missing files/columns, and writes a PASS/FAIL summary. | Validation artefacts in `results/validation_report.json` and `results/validation_report.md`. |
| `build_dashboard.py` | Generates the interactive Plotly dashboard consolidating method evolution, facility mix, animated discovery race, and habitability scatter. | Standalone HTML at `webapp/index.html`. |

## `data/`

| File | Description | Source |
| --- | --- | --- |
| `authoritative_habitable_sample.csv` | Reference list of well-studied habitable-zone candidates used for cross-checking the scoring pipeline. | Curated from NASA announcements (stored locally for offline validation). |
| `discovery_facilities.csv` | Lookup table that maps discovery facilities to agency, platform class, and launch year metadata. | Assembled manually from public mission documentation. |

## `docs/`

| File | Description |
| --- | --- |
| `final_documentation.md` | Comprehensive narrative covering goals, methodology, scientific insights, presentation plan, and reproducibility notes. |
| `project_report.md` | Concise report tailored for hackathon submission forms and judge briefings. |
| `habitable_priority_technical.md` | Technical whitepaper detailing the habitability scoring approach, feature engineering, weighting, and validation procedure. |
| `file_manifest.md` | (This document) Exhaustive catalogue of repository files and their purposes. |

## `figures/`

Static plots are generated on demand when the analysis scripts run.  They are no longer tracked in git so that the repository remains text-only and easy to review.  After executing the scripts, expect the following PNG exports:

- `figures/discoveries_by_method.png` — Stacked area chart of annual exoplanet discoveries by detection method (from `analysis/ps_overview.py`).
- `figures/orbital_period_by_multiplicity.png` — Box-and-whisker comparison of orbital period distributions across system multiplicities (from `analysis/ps_overview.py`).
- `figures/radius_vs_teff.png` — Scatter plot showing planetary radius vs host star temperature with equilibrium temperature colouring (from `analysis/ps_overview.py`).
- `figures/habitability/temp_radius_priority.png` — Equilibrium temperature vs radius scatter coloured by priority score (from `analysis/habitable_priority.py`).
- `figures/habitability/priority_components.png` — Bar chart of component contributions for the top-ranked habitable candidates (from `analysis/habitable_priority.py`).
- `figures/habitability/priority_radar.png` — Radar chart comparing multi-metric profiles for leading habitable candidates (from `analysis/habitable_priority.py`).
- `figures/method_evolution/method_stack.png` — Stacked area timeline of detection method counts (from `analysis/method_evolution.py`).
- `figures/method_evolution/method_forecast.png` — Holt-Winters projections for method shares through 2030 (from `analysis/method_evolution.py`).
- `figures/method_evolution/facility_method_share.png` — Stacked bar chart of detection methods by discovery facility grouping (from `analysis/method_evolution.py`).

## `results/`

| File | Description |
| --- | --- |
| `method_timeseries.csv` | Annual discovery counts and shares by detection method. |
| `method_forecast.csv` | Holt-Winters projections for future method counts/shares. |
| `facility_method_summary.csv` | Cross-tab summarising method contributions by discovery facility class. |
| `habitable_priority_scores.csv` | Ranked list of planets with computed habitability priority scores and component metrics. |
| `habitable_authoritative_comparison.csv` | Join between internal scores and the authoritative habitable candidate sample for validation. |
| `habitable_top20.md` | Human-readable markdown brief describing the top 20 habitable candidates. |
| `validation_report.json` | Machine-readable status report with checksums and PASS/FAIL flags for each module. |
| `validation_report.md` | Narrative summary of the validation run for quick review. |

## `webapp/`

| File | Description |
| --- | --- |
| `index.html` | Bundled Plotly dashboard featuring animated discovery method race, facility shares, and habitability scatterplot matrix. |

---

For any new analyses or artefacts added in the future, append them to this
manifest so that collaborators and judges can quickly understand their role.
