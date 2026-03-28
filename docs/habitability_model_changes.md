# Habitability Model: Changes and Rationale

Date: 2025-09-20

This document explains the changes applied to the habitability screening pipeline in `analysis/habitable_priority.py`, why they were necessary, and their observed impact on results and validation against an authoritative list of habitable candidates.

## Summary of Issues Identified

- Very low recall versus authoritative habitable lists dominated by M-dwarf systems.
- Strict input filtering removed many otherwise plausible targets (especially around cool stars).
- Scoring choices implicitly favored Sun–Earth analogs (period centered at 365 days, narrow stellar temperature band, V-band observability and hard V-mag cut).

## Changes Implemented

### 1) Relax input filters and remove non-essential required columns

- Removed `st_rad` from `REQUIRED_COLUMNS` (it was not used by scoring).
- Loosened physical gates:
  - Orbital period: from `[1, 800]` to `[0.5, 1200]` days
  - Stellar effective temperature: from `[3500, 7500]` K to `[2500, 7500]` K (include M-dwarfs)
  - Removed hard filter on `sy_vmag` (V-band) to avoid eliminating faint M-dwarfs. Observability remains handled via a score instead of a hard cut.

Rationale: Improve recall and include cool-star habitable-zone systems commonly recognized by the community (e.g., TRAPPIST-1 family, LHS 1140 b).

### 2) De-bias the scoring model

- Period score: switched from a fixed 365-day optimum to a star-adjusted habitable-zone period:
  - `P_hz ≈ 365 * (st_teff/5778)^1.5`, scoring on log10(period / P_hz) with a wider width (0.35).
  - Motivation: M-dwarf habitable zones have much shorter orbital periods than the Sun’s.
- Stellar temperature score: widened and re-centered the Gaussian to be tolerant of cooler stars:
  - From `μ=5778, σ=800` to `μ=5200, σ=1800`.
- Weights: reduced emphasis on period and stellar temperature; increased emphasis on insolation (already encodes HZ) and observability (soft, not hard filter):
  - `temp: 0.24, radius: 0.22, insolation: 0.18, period: 0.08, stellar_temp: 0.06, observability: 0.18, system: 0.04`.

Rationale: Keep the physics of habitability (insolation, temperature, size) central while removing biases against cool-star systems. Observability remains important but is no longer a gating filter.

### 3) Keep previously fixed radius score

- Retained the wider radius Gaussian (`σ=1.0`) rather than the original very tight `σ=0.35`.
  - Motivation: avoid collapsing scores to ~0 for most known planets given the observed radius distribution.

## Observed Impact

- Candidate pool size increased: 37 → 65
- Authoritative match rate (top-50 shortlist): 2.7% → 6.0%
- Newly matching authoritative planets include: `Kepler-1649 c`, `LHS 1140 b` (in addition to `Kepler-452 b`).

Note: The authoritative list used here is a compact curated sample. A broader external list (e.g., PHL HEC when accessible) would allow more comprehensive benchmarking.

## Trade-offs and Future Work

- Observability uses V-band (`sy_vmag`). Many M-dwarfs are faint in V but bright in NIR. If J/K magnitudes are available, consider replacing or complementing `sy_vmag`.
- Consider computing missing `pl_insol`/`pl_eqt` where feasible, to further reduce row drops.
- Period score could be removed entirely since insolation already anchors HZ; currently its weight is low (0.08) and adjusted to be star-relative.
- Consider cross-validation against a larger authoritative set and quantify per-filter and per-feature contributions to recall/precision.

## File Diffs (high-level)

- `analysis/habitable_priority.py`
  - Removed `st_rad` from `REQUIRED_COLUMNS`
  - Relaxed filters for `pl_orbper`, `st_teff`; removed hard cut on `sy_vmag`
  - Period score now uses star-relative HZ period; widened stellar temperature Gaussian
  - Updated weights; maintained wider radius Gaussian


