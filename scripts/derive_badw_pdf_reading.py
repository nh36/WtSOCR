#!/usr/bin/env python3
"""Derive reversible reading text from source-anchored PDF lexical candidates.

The visual source, its SHA and all candidate offsets are inputs, never edited.
Only a line break *inside an already identified lexical item* is eligible for
joining. Ambiguous hyphenated and page-crossing breaks remain literal and are
reported for review. This is a reading layer, not an OCR correction layer.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from itertools import zip_longest
from pathlib import Path
import re
from typing import Any, Iterator

from badw_canonical_pages import stable_json_bytes
from extract_badw_pdf_lexical_candidates import VERSION as LEXICAL_VERSION
from parse_badw_pdf_articles import VERSION as STRUCTURE_VERSION

VERSION = "badw-pdf-derived-reading-v1"
CAPITAL_FRAGMENT = re.compile(r"(?:^|[\s(])[A-ZÄÖÜ]$")
CAPITAL_CONTINUATION = re.compile(r"[A-ZÄÖÜ]{2,}")
POWER_TEN_FRAGMENT = re.compile(r"(?<![\w/])10$")
POWER_TEN_TRAILER = re.compile(r"(?<![\w/])10\n\d{1,3}$")
# These characters close the preceding token even when PDF visual wrapping
# places them at the start of the next line. A German low opening comma/quote,
# an ellipsis, and Tibetan initial ’ are deliberately not included.
RIGHT_CLOSERS = frozenset("“)]};:!?")
COLLECTIONS = ("definitions", "tibetan_examples", "belegstellen",
               "lexicographic_parallels", "variant_glosses", "translations",
               "citations")


def rows(path: Path) -> Iterator[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def derive_item(source: str, visual_start: int, lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Return reading plus an exact, source-offset boundary substitution map."""
    pieces: list[str] = []
    boundaries: list[dict[str, Any]] = []
    cursor = 0
    reading_cursor = 0
    ordered = sorted(lines, key=lambda line: line["line_index"])
    for local_offset, character in enumerate(source):
        if character != "\n":
            continue
        left = source[cursor:local_offset]
        pieces.append(left)
        reading_cursor += len(left)
        # Source-line coordinates are usually sufficient, but their character
        # offsets are local to each line. The newline belongs between the
        # sequential source_lines entries, independent of visual indentation.
        boundary_index = len(boundaries)
        before = ordered[boundary_index] if boundary_index < len(ordered) else None
        after = ordered[boundary_index + 1] if boundary_index + 1 < len(ordered) else None
        if before is None or after is None:
            raise ValueError("candidate newline has no pair of source lines")
        if before["page_id"] != after["page_id"]:
            kind, replacement = "page_boundary_review", "\n"
        elif left.rstrip().endswith(("-", "‐", "‑", "–")):
            kind, replacement = "hyphen_boundary_review", "\n"
        elif (CAPITAL_FRAGMENT.search(left.rstrip()) and
              CAPITAL_CONTINUATION.match(source[local_offset + 1:])):
            # Small-cap names such as H\nAHN and K\nRETSCHMAR must not
            # silently become two words. Their exact join needs review.
            kind, replacement = "capital_fragment_boundary_review", "\n"
        elif ((POWER_TEN_FRAGMENT.search(left.rstrip()) and
               re.match(r"\d{1,3}(?:\W|$)", source[local_offset + 1:])) or
              (POWER_TEN_TRAILER.search(source[:local_offset].rstrip()) and
               source[local_offset + 1:local_offset + 2] in ",;“")):
            # Positioned superscripts can surface as separate visual lines:
            # 10\n51\n, must not become an asserted reading of "10 51 ,".
            kind, replacement = "numeric_fragment_boundary_review", "\n"
        elif source[local_offset + 1:local_offset + 2] in RIGHT_CLOSERS:
            kind, replacement = "right_closer_join", ""
        else:
            kind = "same_item_space"
            replacement = "" if (left.endswith(" ") or source[local_offset + 1:local_offset + 2] == " ") else " "
        pieces.append(replacement)
        boundaries.append({"source_visual_offset": visual_start + local_offset,
                           "source_local_offset": local_offset,
                           "reading_start": reading_cursor,
                           "reading_end": reading_cursor + len(replacement),
                           "left_line_index": before["line_index"],
                           "right_line_index": after["line_index"],
                           "kind": kind, "replacement": replacement})
        reading_cursor += len(replacement)
        cursor = local_offset + 1
    pieces.append(source[cursor:])
    reading = "".join(pieces)
    return {"source_text": source, "source_visual_start": visual_start,
            "source_sha256": sha256(source.encode("utf-8")).hexdigest(),
            "reading_text": reading, "boundaries": boundaries}


def project(structure: dict[str, Any], lexical: dict[str, Any]) -> dict[str, Any]:
    if (structure.get("contract_version") != STRUCTURE_VERSION or
            lexical.get("contract_version") != LEXICAL_VERSION or
            structure.get("article_id") != lexical.get("article_id") or
            structure.get("source_faithful_sha256") != lexical.get("source_faithful_sha256") or
            structure.get("source_objects", []) != lexical.get("source_objects", [])):
        raise ValueError("structure/lexical source identity mismatch")
    visual = "\n".join(line["text"] for line in structure["visual_lines"])
    if sha256(visual.encode("utf-8")).hexdigest() != lexical["visual_sha256"]:
        raise ValueError("visual source SHA mismatch")
    annotations: dict[str, list[dict[str, Any]]] = {}
    for collection in COLLECTIONS:
        annotations[collection] = []
        for item in lexical[collection]:
            start, end = item["visual_start"], item["visual_end"]
            if visual[start:end] != item["text"]:
                raise ValueError(f"{collection} source anchor mismatch")
            annotations[collection].append(derive_item(item["text"], start, item["source_lines"]))
    return {"contract_version": VERSION, "article_id": lexical["article_id"],
            "visual_sha256": lexical["visual_sha256"],
            "source_faithful_sha256": lexical["source_faithful_sha256"],
            "annotations": annotations}


def build(structure_path: Path, lexical_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    logical = sha256()
    with output.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw,
                                                  mode="wb", mtime=0) as sink:
        for structure, lexical in zip_longest(rows(structure_path), rows(lexical_path)):
            if structure is None or lexical is None:
                raise ValueError("structure/lexical corpus lengths differ")
            record = project(structure, lexical)
            encoded = stable_json_bytes(record) + b"\n"
            sink.write(encoded)
            logical.update(encoded)
            counts["articles"] += 1
            for items in record["annotations"].values():
                counts["items"] += len(items)
                for item in items:
                    for boundary in item["boundaries"]:
                        counts[boundary["kind"]] += 1
    return {"contract_version": VERSION, "counts": dict(sorted(counts.items())),
            "logical_sha256": logical.hexdigest(),
            "compressed_sha256": sha256(output.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("structure", type=Path)
    parser.add_argument("lexical", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.structure, args.lexical, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
