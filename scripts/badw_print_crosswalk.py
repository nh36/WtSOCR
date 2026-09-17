#!/usr/bin/env python3
"""Crosswalk canonical BAdW pages to the registered two-up print scan.

The matcher uses rare word evidence from the source-faithful decoded page and
the registered scan OCR.  Printed-page numbers come from the BAdW page footer;
the scan match is evidence about the physical two-up source page, not a rewrite
of either text.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Iterable
import unicodedata


CONTRACT_VERSION = "badw-print-scan-crosswalk-v1"
VOLUME_PAGE_COUNTS = {2: 523, 3: 579, 4: 382}
TOKEN = re.compile(r"[^\W\d_]+(?:[’'][^\W\d_]+)*", re.UNICODE)
CROSSWALK_FIELDS = (
    "volume",
    "printed_page",
    "canonical_status",
    "page_id",
    "scan_page",
    "scan_half",
    "match_score",
    "runner_up_margin",
    "match_confidence",
    "mapping_method",
    "source_token_count",
    "runner_up_scan_page",
    "top_five_scan_pages",
)


def tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFC", text).casefold().replace("’", "'")
    return {value for value in TOKEN.findall(normalized) if len(value) >= 4}


def missing_ranges(values: Iterable[int]) -> list[tuple[int, int]]:
    ordered = sorted(set(values))
    if not ordered:
        return []
    result: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value != previous + 1:
            result.append((start, previous))
            start = value
        previous = value
    result.append((start, previous))
    return result


class ScanIndex:
    def __init__(self, pages: list[str]):
        self.pages = pages
        page_tokens = [tokens(page) for page in pages]
        document_frequency: Counter[str] = Counter()
        for values in page_tokens:
            document_frequency.update(values)
        self.page_tokens = page_tokens
        total = len(pages)
        self.weights = {
            token: math.log((total + 1) / (frequency + 1)) + 1.0
            for token, frequency in document_frequency.items()
        }
        inverse: defaultdict[str, list[int]] = defaultdict(list)
        for page_index, values in enumerate(page_tokens):
            for token in values:
                if document_frequency[token] <= 400:
                    inverse[token].append(page_index)
        self.inverse = dict(inverse)

    def match(self, text: str) -> dict[str, object]:
        source_tokens = tokens(text)
        source_weight = sum(self.weights.get(token, 1.0) for token in source_tokens)
        candidates: Counter[int] = Counter()
        for token in source_tokens:
            weight = self.weights.get(token, 1.0)
            for page_index in self.inverse.get(token, []):
                candidates[page_index] += weight
        ranked = candidates.most_common(5)
        top_page, top_shared = ranked[0] if ranked else (-1, 0.0)
        second_shared = ranked[1][1] if len(ranked) > 1 else 0.0
        score = top_shared / source_weight if source_weight else 0.0
        margin = (top_shared - second_shared) / source_weight if source_weight else 0.0
        duplicate_similarity = 0.0
        if len(ranked) > 1:
            top_tokens = self.page_tokens[ranked[0][0]]
            second_tokens = self.page_tokens[ranked[1][0]]
            union = top_tokens | second_tokens
            duplicate_similarity = len(top_tokens & second_tokens) / len(union) if union else 0.0
        confidence = (
            "high_text_match"
            if score >= 0.35 and margin >= 0.06
            else "high_duplicate_scan_match"
            if score >= 0.35 and duplicate_similarity >= 0.80
            else "medium_text_match"
            if score >= 0.22 and margin >= 0.025
            else "low_text_match"
        )
        return {
            "scan_page": top_page + 1 if top_page >= 0 else "",
            "match_score": score,
            "runner_up_margin": margin,
            "match_confidence": confidence,
            "source_token_count": len(source_tokens),
            "runner_up_scan_page": ranked[1][0] + 1 if len(ranked) > 1 else "",
            "top_five_scan_pages": ",".join(str(item[0] + 1) for item in ranked),
        }


def _canonical_pages(canonical_root: Path, volume: int) -> dict[int, dict[str, str]]:
    table_path = canonical_root / f"volume_{volume}" / "canonical_pages.tsv"
    with table_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    result: dict[int, dict[str, str]] = {}
    for row in rows:
        if not row["printed_page"]:
            continue
        number = int(row["printed_page"])
        if number in result:
            raise ValueError(f"duplicate canonical v{volume} p{number}")
        result[number] = row
    return result


def _write_tsv(path: Path, fields: Iterable[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def build_crosswalk(
    canonical_root: Path,
    scan_ocr_path: Path,
    output_root: Path,
    volume_page_counts: dict[int, int] | None = None,
) -> dict[str, object]:
    """Build deterministic page and scan-insertion evidence."""

    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing to mix output with existing data: {output_root}")
    expected_counts = volume_page_counts or VOLUME_PAGE_COUNTS
    scan_pages = scan_ocr_path.read_text(encoding="utf-8").split("\f")
    scan_index = ScanIndex(scan_pages)
    rows: list[dict[str, object]] = []

    for volume in sorted(expected_counts):
        canonical = _canonical_pages(canonical_root, volume)
        for printed_page in range(1, expected_counts[volume] + 1):
            row = canonical.get(printed_page)
            if row is None:
                rows.append(
                    {
                        "volume": volume,
                        "printed_page": printed_page,
                        "canonical_status": "missing",
                        "page_id": "",
                        "scan_page": "",
                        "scan_half": "left" if printed_page % 2 == 0 else "right",
                        "match_score": "",
                        "runner_up_margin": "",
                        "match_confidence": "not_matched",
                        "mapping_method": "",
                        "source_token_count": "",
                        "runner_up_scan_page": "",
                        "top_five_scan_pages": "",
                    }
                )
                continue
            object_path = canonical_root / f"volume_{volume}" / row["canonical_object"]
            with gzip.open(object_path, "rt", encoding="utf-8") as handle:
                record = json.load(handle)
            match = scan_index.match(str(record["source_faithful_decoded_text"]))
            rows.append(
                {
                    "volume": volume,
                    "printed_page": printed_page,
                    "canonical_status": "present",
                    "page_id": row["page_id"],
                    "scan_page": match["scan_page"],
                    "scan_half": "left" if printed_page % 2 == 0 else "right",
                    "match_score": f"{float(match['match_score']):.8f}",
                    "runner_up_margin": f"{float(match['runner_up_margin']):.8f}",
                    "match_confidence": match["match_confidence"],
                    "mapping_method": "idf_token_match",
                    "source_token_count": match["source_token_count"],
                    "runner_up_scan_page": match["runner_up_scan_page"],
                    "top_five_scan_pages": match["top_five_scan_pages"],
                }
            )

    by_identity = {(int(row["volume"]), int(row["printed_page"])): row for row in rows}

    def reliable(row: dict[str, object] | None) -> bool:
        return bool(
            row
            and row["scan_page"]
            and row["match_confidence"] not in {"low_text_match", "not_matched"}
        )

    # The two printed halves share one physical scan page.  This gives exact
    # scan provenance for a missing or weakly matched half whenever its partner
    # is reliable.
    for row in rows:
        if row["match_confidence"] not in {"low_text_match", "not_matched"}:
            continue
        page = int(row["printed_page"])
        partner_page = page + 1 if page % 2 == 0 else page - 1
        partner = by_identity.get((int(row["volume"]), partner_page))
        if reliable(partner):
            row["scan_page"] = partner["scan_page"]
            row["match_confidence"] = "high_shared_physical_page"
            row["mapping_method"] = f"paired_with_printed_page:{partner_page}"

    # If both halves have weak text matches, the adjacent physical pages can
    # still establish their location uniquely.  Do not bridge inserted print
    # matter: the bounding scan pages must be exactly two apart.
    for volume, count in sorted(expected_counts.items()):
        for even_page in range(2, count, 2):
            left = by_identity[(volume, even_page)]
            right = by_identity[(volume, even_page + 1)]
            if reliable(left) or reliable(right):
                continue
            previous = by_identity.get((volume, even_page - 1))
            following = by_identity.get((volume, even_page + 2))
            if not (reliable(previous) and reliable(following)):
                continue
            previous_scan = int(previous["scan_page"])
            following_scan = int(following["scan_page"])
            if following_scan != previous_scan + 2:
                continue
            for row in (left, right):
                row["scan_page"] = previous_scan + 1
                row["match_confidence"] = "high_sequence_inference"
                row["mapping_method"] = (
                    f"bounded_by_printed_pages:{even_page - 1},{even_page + 2}"
                )

    # A volume's first printed page occupies the right half of the physical
    # scan immediately before the scan containing printed pages 2 and 3.  Use
    # this only when both following halves independently agree; this handles a
    # missing page 1 without assuming that no front matter was inserted before
    # the volume boundary.
    for volume in sorted(expected_counts):
        first = by_identity[(volume, 1)]
        second = by_identity.get((volume, 2))
        third = by_identity.get((volume, 3))
        if reliable(first) or not (reliable(second) and reliable(third)):
            continue
        if int(second["scan_page"]) != int(third["scan_page"]):
            continue
        following_scan = int(second["scan_page"])
        if following_scan <= 1:
            continue
        first["scan_page"] = following_scan - 1
        first["match_confidence"] = "high_adjacent_volume_boundary"
        first["mapping_method"] = "preceding_scan_from_printed_pages:2,3"

    _write_tsv(output_root / "print_page_crosswalk.tsv", CROSSWALK_FIELDS, rows)

    gaps = []
    for volume, count in sorted(expected_counts.items()):
        missing = [
            page
            for page in range(1, count + 1)
            if by_identity[(volume, page)]["canonical_status"] == "missing"
        ]
        for first, last in missing_ranges(missing):
            gaps.append(
                {
                    "volume": volume,
                    "first_printed_page": first,
                    "last_printed_page": last,
                    "page_count": last - first + 1,
                }
            )
    _write_tsv(
        output_root / "missing_ranges.tsv",
        ("volume", "first_printed_page", "last_printed_page", "page_count"),
        gaps,
    )

    insertion_rows = []
    for volume in sorted(expected_counts):
        matched = {
            int(row["scan_page"])
            for row in rows
            if int(row["volume"]) == volume and row["scan_page"]
        }
        confident = {
            int(row["scan_page"])
            for row in rows
            if int(row["volume"]) == volume
            and row["scan_page"]
            and row["match_confidence"] != "low_text_match"
        }
        if not confident:
            continue
        for scan_page in range(min(confident), max(confident) + 1):
            if scan_page in matched:
                continue
            text = scan_pages[scan_page - 1]
            insertion_rows.append(
                {
                    "volume": volume,
                    "scan_page": scan_page,
                    "scan_text_sha256": sha256(text.encode("utf-8")).hexdigest(),
                    "nonblank_characters": len("".join(text.split())),
                    "text_snippet": " ".join(text.split())[:240],
                }
            )
    _write_tsv(
        output_root / "scan_pages_without_canonical_match.tsv",
        ("volume", "scan_page", "scan_text_sha256", "nonblank_characters", "text_snippet"),
        insertion_rows,
    )

    scan_span_pages: set[int] = set()
    for volume in sorted(expected_counts):
        volume_scan_pages = {
            int(row["scan_page"])
            for row in rows
            if int(row["volume"]) == volume and reliable(row)
        }
        if volume_scan_pages:
            scan_span_pages.update(range(min(volume_scan_pages), max(volume_scan_pages) + 1))
    occupancy_rows = []
    duplicate_scan_pages = {
        int(row["runner_up_scan_page"])
        for row in rows
        if row["match_confidence"] == "high_duplicate_scan_match"
        and row["runner_up_scan_page"]
    }
    for scan_page in sorted(scan_span_pages):
        scan_rows = [row for row in rows if reliable(row) and row["scan_page"] == scan_page]
        left = [
            f"v{row['volume']}:p{row['printed_page']}"
            for row in scan_rows
            if row["scan_half"] == "left"
        ]
        right = [
            f"v{row['volume']}:p{row['printed_page']}"
            for row in scan_rows
            if row["scan_half"] == "right"
        ]
        if left and right:
            status = "two_dictionary_halves"
        elif left:
            status = "left_dictionary_only"
        elif right:
            status = "right_dictionary_only"
        elif scan_page in duplicate_scan_pages:
            status = "duplicate_dictionary_page"
        else:
            status = "no_dictionary_match"
        text = scan_pages[scan_page - 1]
        occupancy_rows.append(
            {
                "scan_page": scan_page,
                "left_print_identity": ",".join(left),
                "right_print_identity": ",".join(right),
                "occupancy": status,
                "scan_text_sha256": sha256(text.encode("utf-8")).hexdigest(),
                "nonblank_characters": len("".join(text.split())),
                "text_snippet": " ".join(text.split())[:240],
            }
        )
    _write_tsv(
        output_root / "scan_page_occupancy.tsv",
        (
            "scan_page",
            "left_print_identity",
            "right_print_identity",
            "occupancy",
            "scan_text_sha256",
            "nonblank_characters",
            "text_snippet",
        ),
        occupancy_rows,
    )

    confidence = Counter(str(row["match_confidence"]) for row in rows)
    volume_summary = {}
    for volume, expected in sorted(expected_counts.items()):
        volume_rows = [row for row in rows if int(row["volume"]) == volume]
        present = sum(row["canonical_status"] == "present" for row in volume_rows)
        volume_summary[str(volume)] = {
            "expected_printed_pages": expected,
            "canonical_pages_present": present,
            "canonical_pages_missing": expected - present,
        }
    summary: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "scan_ocr_sha256": sha256(scan_ocr_path.read_bytes()).hexdigest(),
        "scan_pages": len(scan_pages),
        "expected_printed_pages": sum(expected_counts.values()),
        "canonical_pages_present": sum(
            row["canonical_status"] == "present" for row in rows
        ),
        "canonical_pages_missing": sum(
            row["canonical_status"] == "missing" for row in rows
        ),
        "match_confidence": dict(sorted(confidence.items())),
        "unmatched_scan_pages_within_volume_spans": len(insertion_rows),
        "scan_page_occupancy": dict(
            sorted(Counter(row["occupancy"] for row in occupancy_rows).items())
        ),
        "volumes": volume_summary,
        "crosswalk_sha256": sha256(
            (output_root / "print_page_crosswalk.tsv").read_bytes()
        ).hexdigest(),
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--scan-ocr", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    summary = build_crosswalk(args.canonical_root, args.scan_ocr, args.output_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
