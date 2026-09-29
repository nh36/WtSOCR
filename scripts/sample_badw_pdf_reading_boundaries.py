#!/usr/bin/env python3
"""Select a reproducible, source-anchored audit sample of PDF reading joins.

Sampling is by *unique visual boundary*, not by candidate occurrence: the
same PDF characters may belong to a definition, example and Belegstelle.
This tool makes no linguistic judgment and changes no reading text.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from derive_badw_pdf_reading import VERSION as READING_VERSION, rows

VERSION = "badw-pdf-reading-boundary-sample-v1"
FIELDS = ("boundary_id", "article_id", "visual_sha256", "collection",
          "source_visual_offset", "kind", "left_context", "right_context",
          "proposed_replacement", "review_status", "review_notes")


def boundary_rows(reading_path: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    unique: dict[tuple[str, int], dict[str, str]] = {}
    duplicate_occurrences = 0
    for article in rows(reading_path):
        if article.get("contract_version") != READING_VERSION:
            raise ValueError("unsupported derived-reading contract")
        for collection, items in article["annotations"].items():
            for item in items:
                source = item["source_text"]
                for boundary in item["boundaries"]:
                    offset = int(boundary["source_local_offset"])
                    if source[offset] != "\n":
                        raise ValueError("boundary is not a source newline")
                    visual_offset = int(boundary["source_visual_offset"])
                    key = (article["article_id"], visual_offset)
                    if key in unique:
                        existing = unique[key]
                        if (existing["visual_sha256"] != article["visual_sha256"] or
                                existing["kind"] != boundary["kind"] or
                                existing["proposed_replacement"] != boundary["replacement"]):
                            raise ValueError("inconsistent duplicate visual boundary")
                        duplicate_occurrences += 1
                        continue
                    context = 50
                    unique[key] = {
                        "boundary_id": sha256(f"{article['article_id']}\t{visual_offset}\t{article['visual_sha256']}".encode()).hexdigest()[:20],
                        "article_id": article["article_id"],
                        "visual_sha256": article["visual_sha256"],
                        "collection": collection,
                        "source_visual_offset": str(visual_offset),
                        "kind": boundary["kind"],
                        "left_context": source[max(0, offset - context):offset],
                        "right_context": source[offset + 1:offset + 1 + context],
                        "proposed_replacement": boundary["replacement"],
                        "review_status": "unreviewed", "review_notes": ""}
    return list(unique.values()), {"duplicate_candidate_occurrences": duplicate_occurrences}


def sample(reading_path: Path, output: Path, per_kind: int = 200) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    if per_kind <= 0:
        raise ValueError("per_kind must be positive")
    all_rows, extra = boundary_rows(reading_path)
    by_kind: dict[str, list[dict[str, str]]] = {}
    for row in all_rows:
        by_kind.setdefault(row["kind"], []).append(row)
    chosen: list[dict[str, str]] = []
    for kind in sorted(by_kind):
        # SHA order is stable across processes, independent of corpus order.
        chosen.extend(sorted(by_kind[kind], key=lambda row: row["boundary_id"])[:per_kind])
    chosen.sort(key=lambda row: (row["kind"], row["boundary_id"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(chosen)
    return {"contract_version": VERSION,
            "unique_boundaries_by_kind": dict(sorted(Counter(row["kind"] for row in all_rows).items())),
            "sample_by_kind": dict(sorted(Counter(row["kind"] for row in chosen).items())),
            **extra, "sample_sha256": sha256(output.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reading", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--per-kind", type=int, default=200)
    args = parser.parse_args()
    print(json.dumps(sample(args.reading, args.output, args.per_kind), sort_keys=True))


if __name__ == "__main__":
    main()
