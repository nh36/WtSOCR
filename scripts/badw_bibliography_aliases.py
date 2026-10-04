"""Reviewed bibliography identity crosswalks, never source-text corrections."""
from __future__ import annotations

import csv
from pathlib import Path


def load_reviews(path: Path | None, rows: list[dict], registry: Path | None) -> list[dict]:
    if path is None:
        return []
    if registry is None:
        raise ValueError("alias reviews require the registered print sources")
    with registry.open(encoding="utf-8") as stream:
        prints = {r["sha256"]: r for r in csv.DictReader(stream, delimiter="\t")}
    occurrences = {r["occurrence_id"]: r for r in rows}
    seen, result = set(), []
    with path.open(encoding="utf-8") as stream:
        for review in csv.DictReader(stream, delimiter="\t"):
            key = (review["layer"], review["alias"])
            row = occurrences.get(review["online_occurrence_id"])
            if key in seen or review["layer"] != "pdf" or not review["alias"]:
                raise ValueError("duplicate or unsupported alias scope")
            seen.add(key)
            if (not row or row["kind"] != "work" or
                    row["source_sha256"] != review["online_source_sha256"] or
                    row["label"] != review["canonical_label"]):
                raise ValueError("alias target occurrence/hash/label mismatch")
            if any(r["kind"] == "work" and r["label"] == review["alias"] for r in rows):
                raise ValueError("alias collides with a registered work label")
            if (review["print_pdf_sha256"] not in prints or
                    not review["print_scan_page"].isdecimal() or
                    int(review["print_scan_page"]) < 1 or
                    review["status"] != "visually_reviewed_work_identity" or
                    not review["evidence_note"].strip()):
                raise ValueError("alias lacks registered print review evidence")
            result.append({**review, "authority_id": row["id"]})
    return sorted(result, key=lambda r: (r["layer"], r["alias"]))
