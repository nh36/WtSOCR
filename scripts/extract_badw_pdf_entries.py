#!/usr/bin/env python3
"""Extract conservative, page-contained BAdW PDF entry witnesses.

This is a source transcription index, not a sense/attestation parser.  In
particular the last entry on a printed page may continue on the next page.
Every text field can be replayed from the canonical positioned page object.
"""

from __future__ import annotations

import argparse
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
from collections import Counter
import re

from badw_canonical_pages import extract_headings, stable_json_bytes


CONTRACT_VERSION = "badw-pdf-page-entry-v1"


def _indices(value: str) -> list[int]:
    return [int(piece) for piece in value.split(",") if piece]


def _reading(runs: list[dict[str, object]]) -> str:
    parts: list[str] = []
    previous_y: float | None = None
    for run in runs:
        value = str(run["decoded_unicode"])
        y = float(run["y"])
        if previous_y is not None and abs(previous_y - y) > 0.02 and parts:
            if not parts[-1].endswith((" ", "\n")) and not value.startswith((" ", "\n")):
                parts.append("\n")
        parts.append(value)
        previous_y = y
    return "".join(parts)


def _heading_reading(runs: list[dict[str, object]]) -> str:
    """Expose line breaks in a wrapped LoC headword without changing its source text."""
    lines: list[str] = []
    current: list[str] = []
    previous_y: float | None = None
    for run in runs:
        y = float(run["y"])
        if previous_y is not None and abs(previous_y - y) > 0.02:
            lines.append("".join(current).strip())
            current = []
        current.append(str(run["decoded_unicode"]))
        previous_y = y
    if current:
        lines.append("".join(current).strip())
    return "\n".join(lines)


def _body_end(runs: list[dict[str, object]], printed_page: int | None) -> tuple[int, str]:
    """Exclude the positioned footer and the header repeated after it.

    If the footer cannot be established, retain all runs and flag the span.
    """
    if printed_page is None:
        return len(runs), "footer_not_identified"
    cursor = len(runs) - 1
    while cursor >= 0 and float(runs[cursor]["y"]) > 780:
        cursor -= 1
    if cursor >= 0:
        baseline = float(runs[cursor]["y"])
        digits: list[str] = []
        while cursor >= 0:
            run = runs[cursor]
            piece = str(run["decoded_unicode"]).strip()
            if not piece.isdigit() or abs(float(run["y"]) - baseline) > 0.02:
                break
            digits.append(piece)
            cursor -= 1
        if digits and "".join(reversed(digits)) == str(printed_page):
            return cursor + 1, "positioned_footer"
    return len(runs), "footer_not_identified"


def _entry_headings(
    positioned: dict[str, object], fonts: dict[str, dict[str, object]]
) -> tuple[list[dict[str, object]], int]:
    """Remove alphabet headers and join only immediately adjacent wrapped heads.

    The source sometimes wraps a long Rabten heading before its LoC heading.
    Do not join arbitrary unpaired Tibetan text: both lines must be adjacent
    runs, aligned in x, and on consecutive baselines.
    """
    raw = sorted(
        extract_headings(positioned, fonts),
        key=lambda heading: min(_indices(str(heading["tibetan_run_indices"]))),
    )
    runs = positioned["positioned_text_runs"]
    headings: list[dict[str, object]] = []
    section_headers = 0
    cursor = 0
    while cursor < len(raw):
        heading = dict(raw[cursor])
        if cursor + 1 < len(raw) and not heading["loc"]:
            following = raw[cursor + 1]
            first_indices = _indices(str(heading["tibetan_run_indices"]))
            next_indices = _indices(str(following["tibetan_run_indices"]))
            if (
                following["loc"]
                and first_indices[-1] + 1 == next_indices[0]
                and abs(float(heading["x"]) - float(following["x"])) < 1.0
                and 0 < float(heading["y"]) - float(following["y"]) < 2.0
            ):
                heading["tibetan"] = str(heading["tibetan"]) + str(following["tibetan"])
                heading["tibetan_run_indices"] = ",".join(map(str, first_indices + next_indices))
                heading["loc"] = following["loc"]
                heading["loc_run_indices"] = following["loc_run_indices"]
                heading["homonym"] = following["homonym"]
                heading["homonym_run_indices"] = following["homonym_run_indices"]
                heading["wrapped_tibetan_heading"] = True
                cursor += 1
        # A single Tibetan letter at the first positioned run is a printed
        # alphabet section title, not a dictionary entry.
        if (
            not heading["loc"]
            and _indices(str(heading["tibetan_run_indices"])) == [0]
            and re.fullmatch(r"[\u0f40-\u0f6c]", str(heading["tibetan"]))
        ):
            section_headers += 1
        else:
            loc_indices = _indices(str(heading["loc_run_indices"]))
            if loc_indices:
                last_y = float(runs[loc_indices[-1]]["y"])
                next_run = loc_indices[-1] + 1
                while next_run < len(runs):
                    run = runs[next_run]
                    font = fonts.get(str(run["font_id"]), {})
                    y = float(run["y"])
                    if (
                        font.get("family") != "TGaramond"
                        or font.get("style") != "italic"
                        or not 0 <= last_y - y < 1.5
                    ):
                        break
                    loc_indices.append(next_run)
                    last_y = y
                    next_run += 1
                heading["loc_run_indices"] = ",".join(map(str, loc_indices))
                heading["loc"] = "".join(str(runs[index]["decoded_unicode"]) for index in loc_indices).strip()
                heading["multiline_loc_heading"] = len({float(runs[index]["y"]) for index in loc_indices}) > 1
            headings.append(heading)
        cursor += 1
    return headings, section_headers


def extract_page(page: dict[str, object], canonical_object: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    positioned = page["positioned_page"]
    runs = positioned["positioned_text_runs"]
    if any(int(run["run_index"]) != index for index, run in enumerate(runs)):
        raise ValueError(f"non-sequential runs: {page['page_id']}")
    fonts = {str(font["font_id"]): font for font in page["representative_fonts"]}
    headings, section_headers = _entry_headings(positioned, fonts)
    body_end, footer_evidence = _body_end(runs, page.get("printed_page"))
    entries: list[dict[str, object]] = []
    heading_starts = [min(_indices(str(h["tibetan_run_indices"]))) for h in headings]
    for ordinal, heading in enumerate(headings):
        start = heading_starts[ordinal]
        if start >= body_end:
            continue
        end = min(body_end, heading_starts[ordinal + 1] if ordinal + 1 < len(headings) else body_end)
        if end <= start:
            raise ValueError(f"overlapping headings: {page['page_id']}:{start}")
        span = runs[start:end]
        unknown = [
            {"run_index": int(run["run_index"]), "cid_hex": glyph["cid_hex"],
             "font_id": run["font_id"], "glyph_signature": glyph["glyph_signature"]}
            for run in span for glyph in run["glyphs"] if glyph["unknown"]
        ]
        loc_indices = _indices(str(heading["loc_run_indices"]))
        flags = []
        if not loc_indices:
            flags.append("missing_loc_heading")
        if ordinal == len(headings) - 1:
            flags.append("page_end_continuation_possible")
        if footer_evidence != "positioned_footer":
            flags.append("footer_not_identified")
        if unknown:
            flags.append("unknown_glyphs")
        if heading.get("wrapped_tibetan_heading"):
            flags.append("wrapped_tibetan_heading")
        if heading.get("multiline_loc_heading"):
            flags.append("multiline_loc_heading")
        entries.append({
            "contract_version": CONTRACT_VERSION,
            "id": f"badw:pdf:{page['page_id']}:{start}",
            "page_id": page["page_id"],
            "volume": page["volume"],
            "printed_page": page.get("printed_page"),
            "ordinal_on_page": ordinal + 1,
            "loc_headword": heading["loc"],
            "loc_headword_reading": _heading_reading([runs[index] for index in loc_indices]),
            "tibetan_headword": heading["tibetan"],
            "homonym": heading["homonym"],
            "source_faithful_text": "".join(str(run["decoded_unicode"]) for run in span),
            "derived_reading_text": _reading(span),
            "source_span": {
                "canonical_object": canonical_object,
                "representative_pdf_url": page["representative_source"]["canonical_url"],
                "representative_pdf_sha256": page["representative_source"]["source_sha256"],
                "visible_body_sha256": page["visible_body_sha256"],
                "run_start": start,
                "run_end_exclusive": end,
                "tibetan_run_indices": _indices(str(heading["tibetan_run_indices"])),
                "loc_run_indices": loc_indices,
                "homonym_run_indices": _indices(str(heading["homonym_run_indices"])),
            },
            "unknown_glyphs": unknown,
            "boundary_status": "bounded_on_page" if ordinal + 1 < len(headings) else "page_end_open",
            "flags": flags,
        })
    return entries, {
        "page_id": page["page_id"], "heading_count": len(headings),
        "entry_count": len(entries), "body_run_end": body_end,
        "footer_evidence": footer_evidence,
        "leading_unassigned_runs": heading_starts[0] if heading_starts else body_end,
        "unpaired_headings": sum(not h["loc"] for h in headings),
        "section_headers": section_headers,
        "wrapped_tibetan_headings": sum(bool(h.get("wrapped_tibetan_heading")) for h in headings),
        "multiline_loc_headings": sum(bool(h.get("multiline_loc_heading")) for h in headings),
    }


def build(canonical_root: Path, output_root: Path) -> dict[str, object]:
    # Check the entire source tree before creating output. Some historical
    # canonical snapshots contain a complete index but only overlay objects.
    indexed: dict[int, list[dict[str, str]]] = {}
    index_hashes: dict[str, str] = {}
    for volume in (2, 3, 4):
        root = canonical_root / f"volume_{volume}"
        index_path = root / "canonical_pages.tsv"
        index_hashes[f"volume_{volume}/canonical_pages.tsv"] = sha256(index_path.read_bytes()).hexdigest()
        with index_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        for row in rows:
            if not (root / row["canonical_object"]).is_file():
                raise FileNotFoundError(f"indexed canonical object missing: {root / row['canonical_object']}")
        indexed[volume] = sorted(rows, key=lambda r: (int(r["printed_page"] or 0), r["page_id"]))
    output_root.mkdir(parents=True, exist_ok=True)
    entries_path = output_root / "pdf_page_entries.jsonl.gz"
    diagnostics_path = output_root / "page_diagnostics.tsv"
    if entries_path.exists() or diagnostics_path.exists():
        raise FileExistsError("refusing to overwrite existing PDF extraction")
    stats: Counter[str] = Counter()
    diagnostics: list[dict[str, object]] = []
    logical_hash = sha256()
    with entries_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            for volume in (2, 3, 4):
                root = canonical_root / f"volume_{volume}"
                for row in indexed[volume]:
                    path = root / row["canonical_object"]
                    with gzip.open(path, "rt", encoding="utf-8") as handle:
                        page = json.load(handle)
                    if page["page_id"] != row["page_id"]:
                        raise ValueError(f"page identity mismatch: {path}")
                    visible_hash = sha256(str(page["source_faithful_decoded_text"]).encode("utf-8")).hexdigest()
                    if visible_hash != page["visible_body_sha256"] or visible_hash != row["visible_body_sha256"]:
                        raise ValueError(f"visible source hash mismatch: {path}")
                    records, diagnostic = extract_page(page, path.relative_to(canonical_root).as_posix())
                    diagnostics.append(diagnostic)
                    stats[f"volume_{volume}_pages"] += 1
                    stats[f"volume_{volume}_entries"] += len(records)
                    stats["unpaired_headings"] += int(diagnostic["unpaired_headings"])
                    stats["section_headers"] += int(diagnostic["section_headers"])
                    stats["wrapped_tibetan_headings"] += int(diagnostic["wrapped_tibetan_headings"])
                    stats["multiline_loc_headings"] += int(diagnostic["multiline_loc_headings"])
                    stats["footer_not_identified"] += diagnostic["footer_evidence"] != "positioned_footer"
                    stats["leading_unassigned_pages"] += int(diagnostic["leading_unassigned_runs"]) > 0
                    for record in records:
                        blob = stable_json_bytes(record) + b"\n"
                        compressed.write(blob)
                        logical_hash.update(blob)
                        stats["unknown_glyph_occurrences"] += len(record["unknown_glyphs"])
                        stats["page_end_open"] += record["boundary_status"] == "page_end_open"
    with diagnostics_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(diagnostics[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(diagnostics)
    summary = {"contract_version": CONTRACT_VERSION, "logical_sha256": logical_hash.hexdigest(),
               "entries_path": str(entries_path), "diagnostics_path": str(diagnostics_path),
               "canonical_index_sha256": index_hashes,
               "counts": dict(sorted(stats.items()))}
    (output_root / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.canonical_root, args.output_root), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
