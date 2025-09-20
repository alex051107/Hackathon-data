# Habitable-Zone Priority Pipeline — Technical Notes

## 1. Objective and Scope
The `analysis/habitable_priority.py` module ranks confirmed exoplanets that sit in temperate stellar environments so that follow-up telescope time can be allocated efficiently. This revision retires the earlier detection-method storyline and concentrates exclusively on a physics-guided habitability score. The code now:

1. Standardises the NASA Planetary Systems catalog (`PS_2025.09.20_08.15.55.csv`).
2. Applies conservative physical filters to isolate planets with trustworthy temperature, flux, size, mass, and host-star measurements.
3. Computes interpretable pillar scores for climate suitability, planet structure, observability, and system simplicity.
4. Aggregates the pillars into a single priority value between 0 and 1.
5. Exports publication-ready tables and figures.
6. Cross-checks the high-priority cohort against an authoritative habitable-planet list when network access allows.

Every executable line in the Python source carries inline rationale so reviewers can trace why each step exists without cross-referencing external notes.

## 2. Data Dependencies
| Dataset | Location | Purpose |
| --- | --- | --- |
| NASA Exoplanet Archive — Planetary Systems (2025-09-20 snapshot) | `PS_2025.09.20_08.15.55.csv` | Primary source for planetary and stellar parameters. Loaded via `load_planet_catalog()`. |
| Puerto Rico Habitable Exoplanets Catalog (PHL HEC) | `https://phl.upr.edu/.../habitable_exoplanets_catalog.csv` | External benchmark. Attempted first inside `load_authoritative_catalog()`; gracefully skipped if blocked. |
| Curated NASA Exoplanet Archive sample | `data/authoritative_habitable_sample.csv` | Offline fallback for cross-checking when HTTP access to PHL is denied. |

All datasets are stored or cached locally to keep the pipeline deterministic. When external downloads succeed the latest public numbers are used; otherwise the curated sample ensures the comparison step still runs end-to-end.

## 3. Pipeline Walkthrough
### 3.1 Loading and Filtering
- `load_planet_catalog()` ingests the NASA CSV, keeps only the `default_flag = 1` rows, and returns a Pandas `DataFrame`. This mirrors the archive's recommendation to avoid duplicate parameter sets.
- `select_habitable_inputs(df)` enforces the minimal variable set defined in `REQUIRED_COLUMNS` (temperature, insolation, radius, mass, orbital period, stellar temperature/radius, V magnitude, distance, system multiplicity). It also applies conservative physical bounds to remove outliers (e.g., radii outside 0.4–3.5 Earth radii, masses outside 0.2–15 Earth masses, distances beyond 1000 pc). The intent is to avoid skewing the scoring kernels with hot Jupiters, ultra-faint hosts, or uncertain fits.

### 3.2 Component Scoring
`compute_priority_scores(df)` implements a four-pillar scoring system. The pillars and their sub-components are listed below; all functions return values in `[0, 1]`.

| Pillar | Component | Membership Function | Intuition |
| --- | --- | --- | --- |
| **Climate** | `temp_score` | Trapezoidal membership on 180–240–320–400 K | Conservative liquid-water temperatures. |
|  | `insolation_score` | Trapezoidal membership on 0.2–0.32–1.7–2.2 `S_⊕` | Kopparapu optimistic/optimistic HZ boundaries. |
|  | `period_score` | Trapezoidal membership on log10 days (15–30–400–800) | Avoid ultra-short and extreme orbits. |
|  | `stellar_temp_score` | Trapezoidal membership on 3300–4100–6400–7200 K | Prefer quieter FGK hosts while keeping early-M and late-F stars. |
| **Structure** | `radius_score` | Trapezoidal membership on 0.5–0.85–1.6–2.5 `R_⊕` | Reward Earth-sized/super-Earth planets; down-weight giants. |
|  | `mass_score` | Trapezoidal membership on 0.3–0.7–5–10 `M_⊕` | Highlight rocky or ocean worlds while tolerating mini-Neptunes. |
| **Observability** | `brightness_score` | Logistic decreasing on V magnitude (midpoint 11.5, width 1.2) | Bright hosts simplify spectroscopy. |
|  | `transit_visibility_score` | Logistic increasing on log transit depth (midpoint log₁₀=2.6, width 0.35) | Deep transits support atmospheric retrievals. |
|  | `distance_score` | Logistic decreasing on log distance (midpoint log₁₀=80 pc, width 0.4) | Nearby systems reduce exposure times. |
| **System** | `system_score` | Piecewise penalty based on `sy_snum` | Single-star systems receive full credit; binaries and triples are damped. |

The observability pillar uses internal weights `{brightness: 0.4, transit depth: 0.35, distance: 0.25}` before averaging. The climate and structure pillars are simple means over their components.

### 3.3 Priority Aggregation
Weights are chosen so climate suitability dominates, with structure and observability close behind while system context contributes a modest penalty:

| Pillar | Weight |
| --- | --- |
| `climate_score` | 0.45 |
| `structure_score` | 0.25 |
| `observability_score` | 0.22 |
| `system_score` | 0.08 |

`priority_score` is calculated as the weighted average of the four pillars. Planets are then binned into qualitative tiers via `pd.cut`:
- `High Priority` ≥ 0.70 (top science targets)
- `Follow-up` 0.58–0.70 (worth spectroscopic vetting)
- `Context` < 0.58 (supporting sample for population studies)

All intermediate component columns plus the final score/tier are preserved in the master CSV so downstream analysts can audit the math planet-by-planet.

### 3.4 Reporting and Visuals
- `export_priority_table()` writes two artefacts: `results/habitable_priority_scores.csv` (full table) and `results/habitable_top20.md` (Markdown summary ready for the report or DevPost entry).
- `plot_temp_radius()`, `plot_component_bars()`, and `plot_radar_chart()` generate the scatter, stacked pillar bar chart, and radar chart in `figures/habitability/`. They show the overall habitable landscape, what drives the highest ranked planets, and how top targets compare across pillars.

### 3.5 External Validation Hook
`compare_with_authoritative(priority_df)` calls `load_authoritative_sample()` to obtain a trusted habitable-planet roster. It merges that roster with the local candidates, renames the confidence column to `phl_confidence`, saves `results/habitable_authoritative_comparison.csv`, and prints the match rate. When network access is unavailable, the function transparently falls back to the curated NASA list so analysts still receive a diagnostic table.

## 4. Accuracy and Cross-Checks
Running `python analysis/habitable_priority.py` after installing `requirements.txt` prints a summary such as:

```
Priority scoring complete. 31 planets evaluated; 8 high-priority and 11 follow-up targets identified.
```

The companion script `analysis/validate_analysis.py` recomputes the scorecard, verifies that every component remains in the `[0, 1]` interval, confirms that the observability and aggregate weights reproduce the stored scores within numerical tolerance, and records a PASS/REVIEW summary in `results/validation_report.*`.

## 5. Visualisation Extensions
Beyond the static Matplotlib outputs already produced, consider these additions:
- **Interactive dashboard**: `analysis/build_dashboard.py` now focuses on the habitability story, publishing a Plotly scatter, stacked pillar bars, observability phase space, and priority band summary to `webapp/index.html`.
- **Transit scheduling helper**: integrate orbital phase information to plan JWST/ARIEL observation windows directly from the ranked list.
- **Score waterfall per planet**: a Plotly waterfall chart showing how each pillar pushes the composite priority up or down relative to the median.

These ideas reuse the same scoring output, keeping the analysis consistent while enriching the storytelling during the seven-minute pitch.

## 6. Reproducibility Checklist
1. `python -m pip install -r requirements.txt`
2. `python analysis/habitable_priority.py`
3. Inspect outputs under `results/` and `figures/habitability/`
4. (Optional) Ensure internet access and rerun step 2 to refresh the PHL comparison.
5. `python analysis/build_dashboard.py` to update the interactive dashboard.

Version-control every regenerated asset so the DevPost submission, slides, and live demo all reference the identical numbers documented here.
