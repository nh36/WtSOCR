#!/usr/bin/env python3
"""Build deterministic canonical page records from decoded BAdW PDFs.

The decoder emits one record per catalogue PDF.  Generated PDFs commonly
overlap, so the same printed page can occur in many records.  This module
deduplicates exact visible page bodies while retaining every source occurrence
and the representative positioned glyph provenance needed for later audits.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Iterable


CONTRACT_VERSION = "badw-canonical-source-page-v2"
SUMMARY_CONTRACT_VERSION = "badw-canonical-source-page-summary-v2"


def stable_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def write_gzip_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as out:
            out.write(stable_json_bytes(value) + b"\n")


def write_tsv(
    path: Path, fields: Iterable[str], rows: Iterable[dict[str, object]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def printed_page_number(runs: list[dict[str, object]]) -> tuple[int | None, str]:
    """Recover the positioned footer used by BAdW generated source pages."""

    index = len(runs)
    while index:
        run = runs[index - 1]
        if not str(run["decoded_unicode"]).strip() or float(run["y"]) > 780:
            index -= 1
        else:
            break
    fragments: list[str] = []
    baseline: float | None = None
    cursor = index - 1
    while cursor >= 0:
        run = runs[cursor]
        text = str(run["decoded_unicode"]).strip()
        y = float(run["y"])
        if not text:
            cursor -= 1
            continue
        if re.fullmatch(r"\d+", text) and (
            baseline is None or abs(y - baseline) < 0.02
        ):
            fragments.append(text)
            baseline = y if baseline is None else baseline
            cursor -= 1
            continue
        break
    if fragments:
        digits = "".join(reversed(fragments))
        return int(digits), f"positioned_footer_same_baseline:{digits}"

    visible_tail = "".join(str(run["decoded_unicode"]) for run in runs[-20:])
    match = re.search(r"(?:^|\n)(\d{1,3})\s*$", visible_tail)
    if match:
        return int(match.group(1)), f"final_standalone_footer:{match.group(1)}"
    return None, "footer_not_found"


def extract_headings(
    page: dict[str, object], font_by_id: dict[str, dict[str, object]]
) -> list[dict[str, object]]:
    """Extract paired Tibetan, optional homonym, and italic LoC heading runs.

    The generated PDFs put a regular TGaramond homonym digit between the Tibetan
    heading and the italic Library-of-Congress (LoC) transliterated headword.
    It is source structure rather than a presentation artefact, so retain its
    run provenance instead of folding it into either neighbouring field.
    """

    runs = page["positioned_text_runs"]
    assert isinstance(runs, list)
    headings: list[dict[str, object]] = []
    for candidate in page["tibetan_text_candidates"]:
        if candidate["kind"] != "body_tibetan_text":
            continue
        tibetan = str(candidate["decoded_unicode"])
        if not re.search(r"[\u0f40-\u0fbc]", tibetan):
            continue
        cursor = max(candidate["run_indices"]) + 1
        homonym_pieces: list[str] = []
        homonym_run_indices: list[int] = []
        heading_y = float(candidate["y"])
        while cursor < len(runs):
            run = runs[cursor]
            font = font_by_id.get(str(run["font_id"]), {})
            text = str(run["decoded_unicode"])
            if (
                font.get("family") != "TGaramond"
                or font.get("style") != "regular"
                or abs(float(run["y"]) - heading_y) > 0.02
                or not re.fullmatch(r"\s*\d+\s*", text)
            ):
                break
            homonym_pieces.append(text)
            homonym_run_indices.append(int(run["run_index"]))
            cursor += 1
        pieces: list[str] = []
        loc_run_indices: list[int] = []
        baseline: float | None = None
        while cursor < len(runs):
            run = runs[cursor]
            font = font_by_id.get(str(run["font_id"]), {})
            if font.get("family") != "TGaramond" or font.get("style") != "italic":
                break
            y = float(run["y"])
            if baseline is not None and abs(y - baseline) > 0.02:
                break
            baseline = y if baseline is None else baseline
            pieces.append(str(run["decoded_unicode"]))
            loc_run_indices.append(int(run["run_index"]))
            cursor += 1
        headings.append(
            {
                "candidate_index": candidate["candidate_index"],
                "tibetan": tibetan,
                "tibetan_run_indices": ",".join(
                    str(value) for value in candidate["run_indices"]
                ),
                "tibetan_unknown_glyphs": candidate["unknown_glyphs"],
                "homonym": "".join(homonym_pieces).strip(),
                "homonym_run_indices": ",".join(
                    str(value) for value in homonym_run_indices
                ),
                "loc": "".join(pieces).strip(),
                "loc_run_indices": ",".join(
                    str(value) for value in loc_run_indices
                ),
                "x": candidate["x"],
                "y": candidate["y"],
            }
        )
    return headings


def dimensions_by_url(decode_root: Path) -> dict[str, list[list[float]]]:
    path = decode_root / "reports/structural_census.tsv"
    result: dict[str, list[list[float]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            result[row["canonical_url"]] = json.loads(row["page_dimensions"])
    return result


def _positioned_paths(decode_root: Path, volume: int) -> list[Path]:
    source_root = decode_root / f"decoded/corpus/positioned/volume_{volume}"
    paths = sorted(source_root.glob("*.jsonl.gz"))
    if not paths:
        raise FileNotFoundError(f"no positioned partitions under {source_root}")
    return paths


def build_volume(decode_root: Path, output_root: Path, volume: int) -> dict[str, object]:
    """Build one canonical volume and return its deterministic summary."""

    if volume not in (2, 3, 4):
        raise ValueError(f"unsupported BAdW PDF volume: {volume}")
    volume_root = output_root / f"volume_{volume}"
    if volume_root.exists() and any(volume_root.iterdir()):
        raise FileExistsError(
            f"refusing to mix a canonical rebuild with existing output: {volume_root}"
        )
    pages_root = volume_root / "pages"
    page_dimensions = dimensions_by_url(decode_root)

    page_meta: dict[str, dict[str, object]] = {}
    occurrences: list[dict[str, object]] = []
    heading_rows: list[dict[str, object]] = []
    overlap_counts: Counter[tuple[str, str]] = Counter()
    unknown_identity_counts: Counter[tuple[str, str, str, str]] = Counter()
    source_records = 0
    source_page_occurrences = 0

    for source_path in _positioned_paths(decode_root, volume):
        with gzip.open(source_path, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                record = json.loads(line)
                source_records += 1
                canonical_url = str(record["canonical_url"])
                if canonical_url not in page_dimensions:
                    raise ValueError(f"missing dimensions for {canonical_url}")
                font_by_id = {
                    str(font["font_id"]): font for font in record.get("fonts", [])
                }
                record_page_ids: list[str] = []
                dims = page_dimensions[canonical_url]
                for page in record["pages"]:
                    source_page_occurrences += 1
                    page_index = int(page["page"])
                    if not 1 <= page_index <= len(dims):
                        raise ValueError(
                            f"invalid page index {page_index} for {canonical_url}"
                        )
                    visible_hash = sha256(page["visible_text"].encode("utf-8")).hexdigest()
                    page_id = f"badw-v{volume}-{visible_hash}"
                    positioned_hash = sha256(stable_json_bytes(page)).hexdigest()
                    number, number_evidence = printed_page_number(
                        page["positioned_text_runs"]
                    )
                    headings = extract_headings(page, font_by_id)
                    if visible_hash not in page_meta:
                        canonical_record = {
                            "contract_version": CONTRACT_VERSION,
                            "source_decoder_contract_version": record.get(
                                "contract_version"
                            ),
                            "decoder_version": record.get("decoder_version"),
                            "glyph_registry_sha256": record.get(
                                "glyph_registry_sha256"
                            ),
                            "page_id": page_id,
                            "volume": volume,
                            "printed_page": number,
                            "printed_page_evidence": number_evidence,
                            "visible_body_sha256": visible_hash,
                            "representative_positioned_sha256": positioned_hash,
                            "representative_source": {
                                "canonical_url": canonical_url,
                                "source_sha256": record["source_sha256"],
                                "pdf_page_index": page_index,
                                "source_partition": source_path.relative_to(
                                    decode_root
                                ).as_posix(),
                                "source_partition_line": line_number,
                            },
                            "page_dimensions": dims[page_index - 1],
                            "source_faithful_decoded_text": page["visible_text"],
                            "derived_reading_order_text": page["normalized_reading"],
                            "unknown_glyph_occurrences": page["unknown_glyphs"],
                            "representative_fonts": record.get("fonts", []),
                            "positioned_page": page,
                        }
                        write_gzip_json(
                            pages_root / f"{page_id}.json.gz", canonical_record
                        )
                        page_meta[visible_hash] = {
                            "page_id": page_id,
                            "printed_page": number,
                            "printed_page_evidence": number_evidence,
                            "dimensions": dims[page_index - 1],
                            "representative_url": canonical_url,
                            "representative_source_sha256": record["source_sha256"],
                            "representative_positioned_sha256": positioned_hash,
                            "unknown_glyph_occurrences": page["unknown_glyphs"],
                            "occurrence_count": 0,
                            "positioned_hashes": set(),
                            "headings": headings,
                        }
                        for run in page["positioned_text_runs"]:
                            font = font_by_id.get(str(run["font_id"]), {})
                            for glyph in run["glyphs"]:
                                if glyph["unknown"]:
                                    unknown_identity_counts[
                                        (
                                            str(font.get("family", "")),
                                            str(font.get("style", "")),
                                            str(glyph["cid_hex"]),
                                            str(glyph["glyph_signature"]),
                                        )
                                    ] += 1
                    meta = page_meta[visible_hash]
                    if meta["printed_page"] != number:
                        raise ValueError(
                            f"page-number disagreement for {page_id}: "
                            f"{meta['printed_page']} vs {number}"
                        )
                    meta["occurrence_count"] = int(meta["occurrence_count"]) + 1
                    meta["positioned_hashes"].add(positioned_hash)
                    occurrences.append(
                        {
                            "page_id": page_id,
                            "volume": volume,
                            "printed_page": number if number is not None else "",
                            "canonical_url": canonical_url,
                            "catalogue_lemma": record["catalogue_identity"]["lemma"],
                            "source_pdf_sha256": record["source_sha256"],
                            "pdf_page_index": page_index,
                            "source_partition": source_path.relative_to(
                                decode_root
                            ).as_posix(),
                            "source_partition_line": line_number,
                            "positioned_page_sha256": positioned_hash,
                        }
                    )
                    record_page_ids.append(page_id)
                overlap_counts.update(zip(record_page_ids, record_page_ids[1:]))

    numbered: dict[int, str] = {}
    for meta in page_meta.values():
        number = meta["printed_page"]
        if number is None:
            continue
        if not 1 <= int(number) <= 1000:
            raise ValueError(f"implausible printed page {number}: {meta['page_id']}")
        if int(number) in numbered and numbered[int(number)] != meta["page_id"]:
            raise ValueError(
                f"two bodies claim v{volume} p{number}: "
                f"{numbered[int(number)]} and {meta['page_id']}"
            )
        numbered[int(number)] = str(meta["page_id"])

    page_rows: list[dict[str, object]] = []
    for visible_hash, meta in sorted(
        page_meta.items(), key=lambda item: (item[1]["printed_page"] or 10**9, item[0])
    ):
        number = meta["printed_page"]
        predecessor = numbered.get(int(number) - 1, "") if number is not None else ""
        successor = numbered.get(int(number) + 1, "") if number is not None else ""
        observed_predecessor = overlap_counts[(predecessor, meta["page_id"])]
        observed_successor = overlap_counts[(meta["page_id"], successor)]
        confidence = (
            "high_footer_and_overlap"
            if observed_predecessor or observed_successor
            else "high_positioned_footer"
            if number is not None
            else "unresolved"
        )
        page_rows.append(
            {
                "page_id": meta["page_id"],
                "volume": volume,
                "printed_page": number if number is not None else "",
                "sequence_confidence": confidence,
                "predecessor_page_id": predecessor,
                "predecessor_overlap_observations": observed_predecessor,
                "successor_page_id": successor,
                "successor_overlap_observations": observed_successor,
                "width": meta["dimensions"][0],
                "height": meta["dimensions"][1],
                "visible_body_sha256": visible_hash,
                "representative_positioned_sha256": meta[
                    "representative_positioned_sha256"
                ],
                "representative_url": meta["representative_url"],
                "representative_source_sha256": meta[
                    "representative_source_sha256"
                ],
                "url_page_occurrences": meta["occurrence_count"],
                "distinct_positioned_forms": len(meta["positioned_hashes"]),
                "unknown_glyph_occurrences": meta["unknown_glyph_occurrences"],
                "canonical_object": (
                    Path("pages") / f"{meta['page_id']}.json.gz"
                ).as_posix(),
            }
        )
        for heading in meta["headings"]:
            heading_rows.append(
                {
                    "page_id": meta["page_id"],
                    "volume": volume,
                    "printed_page": number if number is not None else "",
                    **heading,
                }
            )

    edge_rows = [
        {
            "from_page_id": left,
            "to_page_id": right,
            "observations": count,
            "from_printed_page": next(
                (m["printed_page"] for m in page_meta.values() if m["page_id"] == left),
                "",
            ),
            "to_printed_page": next(
                (m["printed_page"] for m in page_meta.values() if m["page_id"] == right),
                "",
            ),
        }
        for (left, right), count in sorted(overlap_counts.items())
    ]
    max_page = max(numbered) if numbered else 0
    missing = [number for number in range(1, max_page + 1) if number not in numbered]

    page_fields = list(page_rows[0]) if page_rows else ["page_id", "volume"]
    occurrence_fields = list(occurrences[0]) if occurrences else ["page_id", "volume"]
    edge_fields = (
        list(edge_rows[0])
        if edge_rows
        else ["from_page_id", "to_page_id", "observations"]
    )
    heading_fields = (
        list(heading_rows[0])
        if heading_rows
        else ["page_id", "volume", "printed_page"]
    )
    write_tsv(volume_root / "canonical_pages.tsv", page_fields, page_rows)
    write_tsv(
        volume_root / "page_occurrences.tsv",
        occurrence_fields,
        sorted(
            occurrences,
            key=lambda row: (
                int(row["printed_page"]) if row["printed_page"] != "" else 10**9,
                row["page_id"],
                row["canonical_url"],
                int(row["pdf_page_index"]),
            ),
        ),
    )
    write_tsv(volume_root / "overlap_edges.tsv", edge_fields, edge_rows)
    write_tsv(volume_root / "headings.tsv", heading_fields, heading_rows)
    unknown_rows = [
        {
            "family": key[0],
            "style": key[1],
            "cid": key[2],
            "glyph_signature": key[3],
            "canonical_page_occurrences": count,
        }
        for key, count in sorted(
            unknown_identity_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    write_tsv(
        volume_root / "canonical_unknown_glyphs.tsv",
        list(unknown_rows[0])
        if unknown_rows
        else [
            "family",
            "style",
            "cid",
            "glyph_signature",
            "canonical_page_occurrences",
        ],
        unknown_rows,
    )
    summary: dict[str, object] = {
        "contract_version": SUMMARY_CONTRACT_VERSION,
        "volume": volume,
        "source_records": source_records,
        "source_page_occurrences": source_page_occurrences,
        "canonical_pages": len(page_meta),
        "numbered_pages": len(numbered),
        "printed_page_min": min(numbered) if numbered else None,
        "printed_page_max": max_page or None,
        "missing_printed_pages": missing,
        "overlap_edges": len(overlap_counts),
        "consecutive_overlap_edges": sum(
            1
            for row in edge_rows
            if row.get("from_printed_page") != ""
            and row.get("to_printed_page") != ""
            and int(row["to_printed_page"]) == int(row["from_printed_page"]) + 1
        ),
        "nonconsecutive_overlap_edges": sum(
            1
            for row in edge_rows
            if row.get("from_printed_page") == ""
            or row.get("to_printed_page") == ""
            or int(row["to_printed_page"]) != int(row["from_printed_page"]) + 1
        ),
        "distinct_unknown_identities": len(unknown_identity_counts),
        "canonical_unknown_occurrences": sum(unknown_identity_counts.values()),
        "headings_extracted": len(heading_rows),
    }
    (volume_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decode-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--volume", action="append", type=int, choices=(2, 3, 4), dest="volumes"
    )
    args = parser.parse_args()
    summaries = [
        build_volume(args.decode_root, args.output_root, volume)
        for volume in (args.volumes or [2, 3, 4])
    ]
    print(json.dumps(summaries, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
