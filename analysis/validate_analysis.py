"""Validation and reproducibility checks for the habitability-focused project."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd

from habitable_priority import (
    AGGREGATE_WEIGHTS,
    CLIMATE_COMPONENTS,
    OBSERVABILITY_COMPONENT_WEIGHTS,
    STRUCTURE_COMPONENTS,
    compute_priority_scores,
    load_planet_catalog,
    select_habitable_inputs,
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


def compare_priority_tables(model: pd.DataFrame, stored: pd.DataFrame) -> List[ValidationRecord]:
    records: List[ValidationRecord] = []

    missing = set(model["pl_name"]).difference(stored["pl_name"])
    extra = set(stored["pl_name"]).difference(model["pl_name"])
    status = "pass" if not missing and not extra else "fail"
    details = f"Rows in model: {len(model)}; stored: {len(stored)}; missing={len(missing)}; extra={len(extra)}"
    records.append(ValidationRecord("Priority candidate coverage", status, details))

    merged = model.merge(stored, on="pl_name", suffixes=("_model", "_stored"))
    score_delta = float((merged["priority_score_model"] - merged["priority_score_stored"]).abs().max())
    status = "pass" if score_delta < 1e-6 else "fail"
    details = f"Max |priority_score_model - priority_score_stored| = {score_delta:.2e}"
    records.append(ValidationRecord("Priority score equality", status, details))

    bands_match = (merged["priority_band_model"] == merged["priority_band_stored"]).all()
    records.append(
        ValidationRecord(
            "Priority band labels",
            "pass" if bands_match else "fail",
            "Priority bands identical" if bands_match else "Priority band mismatch detected",
        )
    )

    return records


def validate_component_ranges(priority: pd.DataFrame) -> ValidationRecord:
    columns = [
        *CLIMATE_COMPONENTS,
        *STRUCTURE_COMPONENTS,
        "climate_score",
        "structure_score",
        "brightness_score",
        "distance_score",
        "transit_visibility_score",
        "observability_score",
        "system_score",
    ]
    mins = priority[columns].min().min()
    maxs = priority[columns].max().max()
    status = "pass" if mins >= 0 and maxs <= 1.05 else "fail"
    details = f"Component score range: [{mins:.3f}, {maxs:.3f}]"
    return ValidationRecord("Component score bounds", status, details)


def validate_observability_blend(priority: pd.DataFrame) -> ValidationRecord:
    weights_sum = sum(OBSERVABILITY_COMPONENT_WEIGHTS.values())
    recomputed = sum(
        priority[col] * weight for col, weight in OBSERVABILITY_COMPONENT_WEIGHTS.items()
    ) / weights_sum
    delta = float((priority["observability_score"] - recomputed).abs().max())
    status = "pass" if delta < 1e-6 else "fail"
    details = f"Max |observability_score - weighted components| = {delta:.2e}"
    return ValidationRecord("Observability weighting", status, details)


def validate_priority_weighting(priority: pd.DataFrame) -> ValidationRecord:
    weights_sum = sum(AGGREGATE_WEIGHTS.values())
    recomputed = (
        priority["climate_score"] * AGGREGATE_WEIGHTS["climate_score"]
        + priority["structure_score"] * AGGREGATE_WEIGHTS["structure_score"]
        + priority["observability_score"] * AGGREGATE_WEIGHTS["observability_score"]
        + priority["system_score"] * AGGREGATE_WEIGHTS["system_score"]
    ) / weights_sum
    delta = float((priority["priority_score"] - recomputed).abs().max())
    status = "pass" if delta < 1e-6 else "fail"
    details = f"Max |priority_score - weighted pillars| = {delta:.2e}"
    return ValidationRecord("Aggregate weighting", status, details)


def validate_band_distribution(priority: pd.DataFrame) -> ValidationRecord:
    counts = priority["priority_band"].value_counts(dropna=False)
    details = ", ".join(f"{band}: {int(count)}" for band, count in counts.items())
    status = "pass" if counts.get("High Priority", 0) > 0 else "warn"
    return ValidationRecord("Priority band distribution", status, details)


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
    catalog = load_planet_catalog()
    inputs = select_habitable_inputs(catalog)
    priority = compute_priority_scores(inputs)

    records: List[ValidationRecord] = []

    stored_path = RESULTS_DIR / "habitable_priority_scores.csv"
    if stored_path.exists():
        stored = pd.read_csv(stored_path)
        records.extend(compare_priority_tables(priority, stored))
    else:
        records.append(ValidationRecord("Priority table availability", "fail", "Stored priority scores not found"))

    records.append(validate_component_ranges(priority))
    records.append(validate_observability_blend(priority))
    records.append(validate_priority_weighting(priority))
    records.append(validate_band_distribution(priority))

    export_reports(records)

    for rec in records:
        print(f"[{rec.status.upper()}] {rec.name}: {rec.details}")


if __name__ == "__main__":
    main()
