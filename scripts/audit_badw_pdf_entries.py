#!/usr/bin/env python3
"""Replay every extracted BAdW PDF entry against its cached canonical page.

This checks exact source provenance, not the semantic correctness of a heading
or entry boundary. It never accesses the network or rewrites source material.
"""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path

from extract_badw_pdf_entries import _heading_reading, _reading


def audit(canonical_root: Path, entries_path: Path) -> dict[str, object]:
    counts: Counter[str] = Counter()
    logical_hash = sha256()
    page_id: str | None = None
    page: dict[str, object] | None = None
    last_end = -1
    last_ordinal = 0
    with gzip.open(entries_path, "rb") as handle:
        for blob in handle:
            logical_hash.update(blob)
            record = json.loads(blob)
            source = record["source_span"]
            if record["page_id"] != page_id:
                path = canonical_root / source["canonical_object"]
                with gzip.open(path, "rt", encoding="utf-8") as page_handle:
                    page = json.load(page_handle)
                page_id = str(page["page_id"])
                if page_id != record["page_id"]:
                    raise ValueError(f"page ID mismatch: {path}")
                visible_hash = sha256(str(page["source_faithful_decoded_text"]).encode("utf-8")).hexdigest()
                if visible_hash != source["visible_body_sha256"]:
                    raise ValueError(f"visible-body hash mismatch: {page_id}")
                last_end = -1
                last_ordinal = 0
                counts["pages"] += 1
            assert page is not None
            runs = page["positioned_page"]["positioned_text_runs"]
            start, end = source["run_start"], source["run_end_exclusive"]
            if not 0 <= start < end <= len(runs) or start < last_end:
                raise ValueError(f"invalid/overlapping run span: {record['id']}")
            if record["ordinal_on_page"] != last_ordinal + 1:
                raise ValueError(f"nonsequential entry ordinal: {record['id']}")
            span = runs[start:end]
            if record["source_faithful_text"] != "".join(str(run["decoded_unicode"]) for run in span):
                raise ValueError(f"source-faithful text mismatch: {record['id']}")
            if record["derived_reading_text"] != _reading(span):
                raise ValueError(f"reading-order text mismatch: {record['id']}")
            for field, indices in (
                ("tibetan_headword", source["tibetan_run_indices"]),
                ("loc_headword", source["loc_run_indices"]),
                ("homonym", source["homonym_run_indices"]),
            ):
                if any(not start <= index < end for index in indices):
                    raise ValueError(f"heading span outside entry: {record['id']}:{field}")
                expected = "".join(str(runs[index]["decoded_unicode"]) for index in indices).strip()
                if record[field] != expected:
                    raise ValueError(f"heading text mismatch: {record['id']}:{field}")
            if record["loc_headword_reading"] != _heading_reading(
                [runs[index] for index in source["loc_run_indices"]]
            ):
                raise ValueError(f"LoC reading mismatch: {record['id']}")
            unknown = [
                {"run_index": int(run["run_index"]), "cid_hex": glyph["cid_hex"],
                 "font_id": run["font_id"], "glyph_signature": glyph["glyph_signature"]}
                for run in span for glyph in run["glyphs"] if glyph["unknown"]
            ]
            if record["unknown_glyphs"] != unknown:
                raise ValueError(f"unknown glyph mismatch: {record['id']}")
            if (source["representative_pdf_url"] != page["representative_source"]["canonical_url"]
                    or source["representative_pdf_sha256"] != page["representative_source"]["source_sha256"]):
                raise ValueError(f"PDF provenance mismatch: {record['id']}")
            counts["entries"] += 1
            counts["unknown_glyph_occurrences"] += len(unknown)
            counts[f"volume_{record['volume']}_entries"] += 1
            last_end = end
            last_ordinal = record["ordinal_on_page"]
    return {"logical_sha256": logical_hash.hexdigest(), "counts": dict(sorted(counts.items()))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--entries", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.canonical_root, args.entries), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
