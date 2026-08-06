#!/usr/bin/env python3
"""Apply newly added exact overrides to the established final-ṅ work bundle."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import postprocess_entry_map as postprocess


LINE_FIELDS = [
    "page",
    "line",
    "entry_id",
    "zone",
    "headword_tibetan",
    "headword_latin",
    "headword_latin_confidence",
    "translit_token_count",
    "german_token_count",
    "audit_candidates",
    "audit_replaced",
    "line_text",
]


def write_tsv(path: Path, fields: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--volume", action="append", required=True)
    args = parser.parse_args()

    for volume in args.volume:
        run_dir = args.work_root / volume
        corrected_path = run_dir / f"{volume}_corrected_full.txt"
        changes_path = run_dir / f"{volume}_changes.tsv"
        line_zones_path = run_dir / f"{volume}_line_zones.tsv"
        summary_path = run_dir / f"{volume}_summary.json"

        corrected = corrected_path.read_text(encoding="utf-8")
        _entries, line_infos, _rows, _validators, _summary, _pages = (
            postprocess.parse_entries(corrected, {})
        )
        corrected, tibetan_script_rows, tibetan_script_applied = (
            postprocess.apply_reviewed_tibetan_script_exact_overrides(
                corrected, line_infos, volume, strict=True
            )
        )
        if tibetan_script_applied:
            _entries, line_infos, _rows, _validators, _summary, _pages = (
                postprocess.parse_entries(corrected, {})
            )
        corrected, tibetan_phrase_rows, tibetan_phrase_applied = (
            postprocess.apply_reviewed_tibetan_script_exact_phrase_overrides(
                corrected, line_infos, volume, strict=True
            )
        )
        tibetan_script_rows += tibetan_phrase_rows
        tibetan_script_applied += tibetan_phrase_applied
        if tibetan_phrase_applied:
            _entries, line_infos, _rows, _validators, _summary, _pages = (
                postprocess.parse_entries(corrected, {})
            )
        corrected, change_rows, applied = (
            postprocess.apply_reviewed_tibetan_exact_normalizations(
                corrected, line_infos, volume
            )
        )
        change_rows = tibetan_script_rows + change_rows
        applied += tibetan_script_applied
        if not applied:
            print(f"{volume}: no new exact overrides")
            continue

        with changes_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            for row in change_rows:
                writer.writerow(
                    row[:6] + ["A", row[7], "1", row[9]]
                )
        corrected_path.write_text(corrected, encoding="utf-8")

        corrected_pages = [page.split("\n") for page in corrected.split("\f")]
        changed_keys = {(int(row[0]), int(row[1])) for row in change_rows}
        with line_zones_path.open(encoding="utf-8", newline="") as handle:
            zone_lines = handle.read().splitlines(keepends=True)
        for index, raw_line in enumerate(zone_lines):
            body = raw_line.rstrip("\r\n")
            ending = raw_line[len(body):]
            fields = body.split("\t", 11)
            if len(fields) != 12 or not fields[0].isdigit():
                continue
            row_key = (int(fields[0]), int(fields[1]))
            if row_key in changed_keys:
                fields[11] = corrected_pages[row_key[0] - 1][row_key[1] - 1]
                zone_lines[index] = "\t".join(fields) + "\n"
        with line_zones_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("".join(zone_lines))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["reviewed_tibetan_exact_changes"] += applied
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"{volume}: applied={applied}")


if __name__ == "__main__":
    main()
