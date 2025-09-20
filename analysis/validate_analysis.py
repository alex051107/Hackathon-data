"""Validation and reproducibility checks for the exoplanet hackathon project."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from habitable_priority import compute_priority_scores, load_planet_catalog, select_habitable_inputs
from method_evolution import (
    aggregate_method_timeseries,
    compute_facility_method_summary,
    forecast_method_activity,
    label_detection_methods,
    load_detection_data,
    prepare_forecast_input,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
REPORT_JSON = RESULTS_DIR / "validation_report.json"
REPORT_MD = RESULTS_DIR / "validation_report.md"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ValidationRecord:
    name: str
    status: str
    details: str

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "details": self.details}


def compare_dataframes(new: pd.DataFrame, stored: pd.DataFrame, keys: List[str], value_col: str, atol: float = 1e-6) -> float:
    """Return maximum absolute difference between two aggregated tables."""

    merged = new.merge(stored, on=keys, how="outer", suffixes=("_new", "_stored")).fillna(0)
    diff = (merged[f"{value_col}_new"] - merged[f"{value_col}_stored"]).abs()
    return float(diff.max())


def validate_method_timeseries(df: pd.DataFrame) -> ValidationRecord:
    recomputed = aggregate_method_timeseries(df)
    stored_path = RESULTS_DIR / "method_timeseries.csv"
    if not stored_path.exists():
        details = "Stored timeseries missing; run analysis/method_evolution.py first."
        return ValidationRecord("Method timeseries availability", "fail", details)

    stored = pd.read_csv(stored_path)
    max_diff = compare_dataframes(recomputed, stored, ["disc_year", "method_group"], "discoveries")
    status = "pass" if max_diff < 1e-6 else "fail"
    details = f"Maximum difference between recomputed and stored counts: {max_diff:.2e}"
    return ValidationRecord("Method timeseries consistency", status, details)


def validate_transit_share(df: pd.DataFrame) -> ValidationRecord:
    recent = df[df["disc_year"] >= 2015]
    share_catalog = (recent["discoverymethod"] == "Transit").mean()

    stored_path = RESULTS_DIR / "method_timeseries.csv"
    if stored_path.exists():
        timeseries = pd.read_csv(stored_path)
        recent_ts = timeseries[timeseries["disc_year"] >= 2015]
        transit_counts = recent_ts[recent_ts["method_group"] == "Transit"]["discoveries"].sum()
        total_counts = recent_ts["discoveries"].sum()
        share_timeseries = transit_counts / total_counts if total_counts > 0 else np.nan
    else:
        share_timeseries = np.nan

    delta = abs(share_catalog - share_timeseries)
    status = "pass" if np.isnan(delta) or delta < 1e-6 else "fail"
    details = (
        f"Transit share since 2015 (catalog): {share_catalog:.4f}; "
        f"timeseries-derived: {share_timeseries:.4f}; |delta|={delta:.2e}"
    )
    return ValidationRecord("Transit dominance cross-check", status, details)


def validate_facility_shares(df: pd.DataFrame) -> ValidationRecord:
    summary = compute_facility_method_summary(df, window=range(2015, df["disc_year"].max() + 1))
    totals = summary.groupby("disc_facility")["share_within_facility"].sum()
    max_dev = float((totals - 1).abs().max())
    status = "pass" if max_dev < 1e-6 else "fail"
    details = f"Maximum deviation from unit share per facility: {max_dev:.2e}"
    return ValidationRecord("Facility share normalisation", status, details)


def validate_forecast(df: pd.DataFrame) -> ValidationRecord:
    timeseries = aggregate_method_timeseries(df)
    series_by_method = prepare_forecast_input(timeseries)
    forecast = forecast_method_activity(series_by_method)

    if forecast.empty:
        return ValidationRecord("Forecast generation", "fail", "Forecast output is empty")

    horizon = 5
    counts = forecast.groupby("method_group")["disc_year"].nunique()
    expected_year = timeseries["disc_year"].max() + horizon
    max_year = forecast["disc_year"].max()

    status = "pass" if counts.min() == horizon and max_year == expected_year else "fail"
    details = (
        f"Minimum horizon rows per method: {counts.min()}; "
        f"forecast extends through {max_year}, expected {expected_year}."
    )
    return ValidationRecord("Forecast horizon", status, details)


def validate_priority_table() -> List[ValidationRecord]:
    base = load_planet_catalog()
    inputs = select_habitable_inputs(base)
    priority = compute_priority_scores(inputs)

    stored_path = RESULTS_DIR / "habitable_priority_scores.csv"
    records: List[ValidationRecord] = []

    if not stored_path.exists():
        records.append(
            ValidationRecord("Priority table availability", "fail", "Stored priority scores not found")
        )
        return records

    stored = pd.read_csv(stored_path)
    missing = set(priority["pl_name"]).difference(stored["pl_name"])
    extra = set(stored["pl_name"]).difference(priority["pl_name"])

    status = "pass" if not missing and not extra else "fail"
    details = f"Rows in model: {len(priority)}; stored: {len(stored)}; missing={len(missing)}; extra={len(extra)}"
    records.append(ValidationRecord("Priority candidate coverage", status, details))

    merged = priority.merge(stored, on="pl_name", suffixes=("_model", "_stored"))
    score_delta = float((merged["priority_score_model"] - merged["priority_score_stored"]).abs().max())
    status = "pass" if score_delta < 1e-6 else "fail"
    details = f"Max |priority_score_model - priority_score_stored| = {score_delta:.2e}"
    records.append(ValidationRecord("Priority score equality", status, details))

    bands_match = (merged["priority_band_model"] == merged["priority_band_stored"]).all()
    details = "Priority bands identical" if bands_match else "Priority band mismatch detected"
    records.append(ValidationRecord("Priority band labels", "pass" if bands_match else "fail", details))

    high_priority_share = (priority["priority_band"] == "High Priority").mean()
    status = "pass" if np.isclose(high_priority_share, 1 / len(priority)) else "warn"
    details = f"High priority share = {high_priority_share:.4f}"
    records.append(ValidationRecord("High-priority proportion", status, details))

    return records


def export_reports(records: List[ValidationRecord]) -> None:
    data = [rec.to_dict() for rec in records]
    with REPORT_JSON.open("w", encoding="utf-8") as fp:
        json.dump({"checks": data}, fp, indent=2, ensure_ascii=False)

    header = ["# Validation report", ""]
    overall = "PASS" if all(rec.status == "pass" for rec in records) else "REVIEW"
    header.append(f"Overall status: **{overall}**")
    header.append("")
    header.append("| Check | Status | Details |")
    header.append("| --- | --- | --- |")
    for rec in records:
        header.append(f"| {rec.name} | {rec.status.upper()} | {rec.details} |")

    REPORT_MD.write_text("\n".join(header), encoding="utf-8")


def main() -> None:
    detection = label_detection_methods(load_detection_data())

    records: List[ValidationRecord] = []
    records.append(validate_method_timeseries(detection))
    records.append(validate_transit_share(detection))
    records.append(validate_facility_shares(detection))
    records.append(validate_forecast(detection))
    records.extend(validate_priority_table())

    export_reports(records)

    for rec in records:
        print(f"[{rec.status.upper()}] {rec.name}: {rec.details}")


if __name__ == "__main__":
    main()
