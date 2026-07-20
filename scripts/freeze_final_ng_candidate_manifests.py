#!/usr/bin/env python3
"""Freeze exact positional and echo candidate identities for reviewed families."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QA_ROOT = ROOT / "release/current/qa"

FAMILIES = {
    "གཏོང": ({"gton"}, "gtoṅ"),
    "སྐྱོང": ({"skyon"}, "skyoṅ"),
    "འབྱུང": ({"byun", "byuh"}, "byuṅ"),
    "སྟེང": ({"sten", "steh"}, "steṅ"),
    "དྲུང": ({"drun"}, "druṅ"),
    "ཁུང": ({"khun"}, "khuṅ"),
    "དོང": ({"don"}, "doṅ"),
    "གུང": ({"gun", "guh"}, "guṅ"),
    "བྱང": ({"byan", "byah"}, "byaṅ"),
    "སེང": ({"sen", "seh"}, "seṅ"),
    "སོང": ({"son"}, "soṅ"),
    "ལིང": ({"lin"}, "liṅ"),
}

FIELDS = [
    "frozen_prepass_sha",
    "volume",
    "page",
    "line",
    "token_index",
    "tibetan_syllable",
    "source_token",
    "target",
    "candidate_status",
    "alignment_category",
    "damage_category",
    "context_excerpt",
]


def read_rows(filename: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(QA_ROOT.glob(f"*/tibetan_cleanup_diagnostics/{filename}")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/final_ng_exact_candidate_prepass_manifest.tsv",
    )
    parser.add_argument(
        "--tibetan-syllables",
        help="Optional comma-separated subset of configured Tibetan syllables.",
    )
    args = parser.parse_args()
    selected = (
        set(args.tibetan_syllables.split(","))
        if args.tibetan_syllables
        else set(FAMILIES)
    )

    frozen: list[dict[str, str]] = []
    for row in read_rows("tibetan_final_ng_consensus_candidates.tsv"):
        family = FAMILIES.get(row["tibetan_syllable"])
        if not family:
            continue
        if row["tibetan_syllable"] not in selected:
            continue
        sources, target = family
        if (
            row["source_latin_token"] not in sources
            or row["proposed_latin_target"] != target
        ):
            continue
        category = row["alignment_category"]
        frozen.append(
            {
                "frozen_prepass_sha": args.sha,
                "volume": row["volume"],
                "page": row["page"],
                "line": row["line"],
                "token_index": row["token_index"],
                "tibetan_syllable": row["tibetan_syllable"],
                "source_token": row["source_latin_token"],
                "target": target,
                "candidate_status": "positional",
                "alignment_category": category,
                "damage_category": row.get("damage_scope", "")
                if category == "damaged_context"
                else "none",
                "context_excerpt": row["context_excerpt"],
            }
        )

    for row in read_rows("tibetan_final_ng_same_entry_echo_candidates.tsv"):
        family = FAMILIES.get(row["tibetan_syllable"])
        if not family:
            continue
        if row["tibetan_syllable"] not in selected:
            continue
        sources, target = family
        if (
            row["additional_source_token"] not in sources
            or row["proposed_target"] != target
        ):
            continue
        category = row["echo_category"]
        frozen.append(
            {
                "frozen_prepass_sha": args.sha,
                "volume": row["volume"],
                "page": row["page"],
                "line": row["line"],
                "token_index": row["token_index"],
                "tibetan_syllable": row["tibetan_syllable"],
                "source_token": row["additional_source_token"],
                "target": target,
                "candidate_status": "echo",
                "alignment_category": category,
                "damage_category": category
                if category in {"damaged_reference", "uncertain"}
                else "none",
                "context_excerpt": row["context_excerpt"],
            }
        )

    frozen.sort(
        key=lambda row: (
            row["tibetan_syllable"],
            row["candidate_status"],
            row["volume"],
            int(row["page"]),
            int(row["line"]),
            int(row["token_index"]),
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(frozen)
    output_label = (
        args.output.resolve().relative_to(ROOT)
        if args.output.resolve().is_relative_to(ROOT)
        else args.output
    )
    print(f"wrote {len(frozen)} rows to {output_label}")


if __name__ == "__main__":
    main()
