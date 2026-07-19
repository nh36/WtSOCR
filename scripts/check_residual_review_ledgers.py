#!/usr/bin/env python3
"""Validate manually maintained residual OCR and Dublin review ledgers."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


VOLUMES = ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_release_lines(release_root: Path) -> dict[tuple[str, str, str], str]:
    lines: dict[tuple[str, str, str], str] = {}
    for volume in VOLUMES:
        path = release_root / "qa" / volume / f"{volume}_line_zones.tsv"
        for row in read_tsv(path):
            lines[(volume, row["page"], row["line"])] = row["line_text"]
    return lines


def validate_ledgers(
    release_root: Path,
    residual_path: Path,
    dublin_path: Path,
) -> list[str]:
    errors: list[str] = []
    release_lines = load_release_lines(release_root)
    for row in read_tsv(residual_path):
        key = (row["volume"], row["page"], row["line"])
        actual = release_lines.get(key)
        if actual is None:
            errors.append(f"residual row does not exist: {key}")
            continue
        if row["current_line"] != actual:
            errors.append(f"residual current_line is stale: {key}")
        for correction in row["corrected_exact_tokens"].split(";"):
            if "→" not in correction:
                continue
            target = correction.split("→", 1)[1].strip().split()[0]
            if target not in actual:
                errors.append(f"corrected target {target!r} absent at {key}")
        if row["classification"] == "internally_resolved_now":
            if "control" not in row["next_action"].lower():
                errors.append(f"resolved row lacks explicit control policy: {key}")

    for row in read_tsv(dublin_path):
        key = (row["volume"], row["page"], row["line"])
        actual = release_lines.get(key)
        if actual is None:
            errors.append(f"Dublin row does not exist: {key}")
            continue
        if row["current_tibetan_ocr"] not in actual:
            errors.append(f"Dublin Tibetan OCR is stale: {key}")
        if row["current_latin_ocr"] not in actual:
            errors.append(f"Dublin Latin OCR is stale: {key}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=Path("release/current"))
    parser.add_argument(
        "--residual-ledger",
        type=Path,
        default=Path("data/residual_aligned_line_damage.tsv"),
    )
    parser.add_argument(
        "--dublin-ledger",
        type=Path,
        default=Path("data/dublin_source_image_review.tsv"),
    )
    args = parser.parse_args()
    errors = validate_ledgers(
        args.release_root,
        args.residual_ledger,
        args.dublin_ledger,
    )
    if errors:
        raise SystemExit("\n".join(errors))
    print("Residual OCR review ledgers are current.")


if __name__ == "__main__":
    main()
