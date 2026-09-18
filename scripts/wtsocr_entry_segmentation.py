#!/usr/bin/env python3
"""Inventory deterministic, coordinate-anchored local WtSOCR entry boundaries.

The CURRENT QA line-zone files already mark every detected dictionary-entry
start as ``headword_line``. Their legacy ``entry_id`` is useful provenance,
but a few IDs contain multiple such starts (or none). This utility does not
change CURRENT text or its QA files. It makes a separate, source-free local
anchor inventory: one provisional entry segment per declared headword line.

The inventory is deliberately conservative. It neither compares BAdW prose
nor attempts to infer a missing headword boundary. Later BAdW reconciliation
can use stable ``volume:page:line`` anchor IDs while retaining every legacy QA
entry ID that contributed rows to the segment.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
VOLUMES = ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m")
CONTRACT_VERSION = "wtsocr-local-headword-anchor-v2"


def _coordinate(row: dict[str, str]) -> tuple[int, int]:
    return int(row["page"]), int(row["line"])


def reconstruct_headword(row: dict[str, str]) -> str:
    """Recover a bounded historical LoC display key from a marked source row."""
    tibetan = row.get("headword_tibetan", "").strip()
    syllables = [part for part in re.split(r"[་༌\s]+", tibetan) if part]
    line = row.get("line_text", "").strip()
    if tibetan and line.startswith(tibetan):
        remainder = line[len(tibetan):].strip()
    else:
        remainder = re.sub(r"^[\u0f00-\u0fff\s]+", "", line).strip()
    return " ".join(remainder.split()[:len(syllables)])


def heading_identity_fields(row: dict[str, str]) -> dict[str, str]:
    """Expose source-free heading fields without repairing their readings.

    ``headword_latin`` is a QA field and can be only the final syllable of a
    multi-syllable historical Library of Congress (LoC) heading.  The bounded
    display reconstruction is retained separately, with the original field
    and line text, so later identity work can assess the extraction without
    treating either form as an OCR correction.
    """
    raw_tibetan = row.get("headword_tibetan", "")
    raw_latin = row.get("headword_latin", "")
    line_text = row.get("line_text", "")
    loc_display = reconstruct_headword(row)
    if raw_tibetan.strip() and loc_display:
        status = "usable_tibetan_and_loc_display"
    elif raw_tibetan.strip():
        status = "missing_loc_display"
    elif loc_display:
        status = "missing_tibetan"
    else:
        status = "missing_tibetan_and_loc_display"
    return {
        "headword_tibetan": raw_tibetan,
        "headword_latin_field": raw_latin,
        "headword_loc_display": loc_display,
        "headword_line_text": line_text,
        "headword_parser_status": status,
    }


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    previous: tuple[int, int] | None = None
    for row in rows:
        current = _coordinate(row)
        if previous is not None and current <= previous:
            raise ValueError(f"non-increasing QA coordinate in {path}: {current}")
        previous = current
    return rows


def anchor_records(volume: str, rows: Iterable[dict[str, str]]) -> list[dict[str, object]]:
    """Return one exact-local-coordinate anchor for each marked headword."""
    result: list[dict[str, object]] = []
    current_rows: list[dict[str, str]] = []
    head: dict[str, str] | None = None

    def finish() -> None:
        if head is None:
            return
        assert current_rows
        start_page, start_line = _coordinate(head)
        end_page, end_line = _coordinate(current_rows[-1])
        entry_ids = sorted(
            {row["entry_id"] for row in current_rows if row["entry_id"] != "0"}, key=int
        )
        result.append({
            "contract_version": CONTRACT_VERSION,
            "anchor_id": f"{volume}:{start_page}:{start_line}",
            "volume": volume,
            "start_page": start_page,
            "start_line": start_line,
            "end_page": end_page,
            "end_line": end_line,
            "boundary_kind": "qa_headword_line",
            "legacy_entry_ids": entry_ids,
            **heading_identity_fields(head),
            "line_count": len(current_rows),
            "zones": dict(sorted(Counter(row["zone"] for row in current_rows).items())),
        })

    for row in rows:
        if row["zone"] == "headword_line":
            finish()
            head = row
            current_rows = [row]
        elif head is not None:
            current_rows.append(row)
    finish()
    return result


def inventory(qa_root: Path, output_root: Path) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=True)
    all_anchors: list[dict[str, object]] = []
    summary_volumes: dict[str, object] = {}
    issues: list[dict[str, object]] = []
    for volume in VOLUMES:
        rows = read_rows(qa_root / volume / f"{volume}_line_zones.tsv")
        anchors = anchor_records(volume, rows)
        all_anchors.extend(anchors)
        heads_by_entry: Counter[str] = Counter(
            row["entry_id"] for row in rows
            if row["entry_id"] != "0" and row["zone"] == "headword_line"
        )
        all_entries = {row["entry_id"] for row in rows if row["entry_id"] != "0"}
        for entry_id in sorted(all_entries, key=int):
            count = heads_by_entry[entry_id]
            if count != 1:
                issues.append({
                    "volume": volume,
                    "legacy_entry_id": entry_id,
                    "headword_anchor_count": count,
                    "issue": "missing_headword_anchor" if count == 0 else "multiple_headword_anchors",
                })
        summary_volumes[volume] = {
            "qa_rows": len(rows),
            "legacy_entry_ids": len(all_entries),
            "headword_anchors": len(anchors),
            "legacy_entry_headword_count_distribution": {
                str(key): value for key, value in sorted(
                    Counter(heads_by_entry.get(entry_id, 0) for entry_id in all_entries).items()
                )
            },
        }
    all_anchors.sort(key=lambda record: (
        str(record["volume"]), int(record["start_page"]), int(record["start_line"])
    ))
    with (output_root / "anchors.jsonl").open("w", encoding="utf-8") as handle:
        for record in all_anchors:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    fields = ["volume", "legacy_entry_id", "headword_anchor_count", "issue"]
    with (output_root / "legacy_entry_issues.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(issues)
    summary = {
        "contract_version": CONTRACT_VERSION,
        "volumes": summary_volumes,
        "headword_anchors": len(all_anchors),
        "legacy_entry_issues": len(issues),
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-root", type=Path, default=ROOT / "release/current/qa")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inventory(args.qa_root, args.output_root), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
