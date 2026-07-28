#!/usr/bin/env python3
"""Apply newly reviewed exact rows to an existing trusted work artifact.

The trusted work trees already contain the full alternate-witness and
postprocessing history.  Re-running the whole pipeline from that corrected
text would erase provenance tables.  This helper applies only exact reviewed
page/line/token overrides, appends their change rows, and refreshes line text
in the line-zone table.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from postprocess_entry_map import (
    apply_reviewed_tibetan_exact_normalizations,
    parse_entries,
)


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), list(reader)


def write_tsv(
    path: Path, fields: list[str], rows: list[dict[str, str]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\r\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    text_path = args.work_dir / f"{args.label}_corrected_full.txt"
    changes_path = args.work_dir / f"{args.label}_changes.tsv"
    lines_path = args.work_dir / f"{args.label}_line_zones.tsv"
    summary_path = args.work_dir / f"{args.label}_summary.json"

    original = text_path.read_text(encoding="utf-8")
    _entries, line_infos, _rows, _issues, _summary, _pages = parse_entries(
        original, {}
    )
    corrected, change_rows, applied = apply_reviewed_tibetan_exact_normalizations(
        corrected_text=original, line_infos=line_infos, label=args.label
    )
    if not applied:
        raise SystemExit("no newly applicable reviewed exact overrides")

    with changes_path.open("a", encoding="utf-8", newline="") as handle:
        csv.writer(
            handle, delimiter="\t", lineterminator="\n"
        ).writerows(change_rows)
    text_path.write_text(corrected, encoding="utf-8")

    corrected_pages = [page.split("\n") for page in corrected.split("\f")]
    changed_keys = {(int(row[0]), int(row[1])) for row in change_rows}
    with lines_path.open("r", encoding="utf-8", newline="") as handle:
        raw_lines = handle.readlines()
    for index, raw_line in enumerate(raw_lines[1:], start=1):
        values = next(csv.reader([raw_line], delimiter="\t"))
        key = (int(values[0]), int(values[1]))
        if key not in changed_keys:
            continue
        values[-1] = corrected_pages[key[0] - 1][key[1] - 1]
        buffer = io.StringIO(newline="")
        csv.writer(
            buffer, delimiter="\t", lineterminator="\n"
        ).writerow(values)
        raw_lines[index] = buffer.getvalue()
    with lines_path.open("w", encoding="utf-8", newline="") as handle:
        handle.writelines(raw_lines)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["reviewed_tibetan_exact_changes"] = (
        int(summary.get("reviewed_tibetan_exact_changes", 0)) + applied
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"label={args.label} applied={applied}")


if __name__ == "__main__":
    main()
