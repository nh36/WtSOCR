#!/usr/bin/env python3
"""Build an exact-source review queue for unresolved PDF quotation roles.

The output is diagnostic, not a correction or an automatic disposition. It
includes source hashes, visual coordinates, nearby typographic spans and
adjacent citation evidence so individual decisions can be reviewed offline.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from itertools import zip_longest
import json
from pathlib import Path
from typing import Any

from badw_canonical_pages import stable_json_bytes
from build_badw_pdf_nested_candidates import quote_subtype, rows
from extract_badw_pdf_lexical_candidates import VERSION as LEXICAL_VERSION
from parse_badw_pdf_articles import VERSION as STRUCTURE_VERSION

VERSION = "badw-pdf-quote-review-v1"
FIELDS = ("review_id", "article_id", "volume", "loc_headword", "homonym",
          "source_faithful_sha256", "visual_sha256", "source_objects_json",
          "division_index", "quote_index", "reason", "subtype", "flags",
          "quote_visual_start", "quote_visual_end", "quote_text",
          "citation_index", "citation_text", "preceding_italic_json",
          "context_json", "review_status", "reviewed_role", "review_notes")


def review_rows(structure: dict[str, Any], lexical: dict[str, Any]) -> list[dict[str, str]]:
    if (structure.get("contract_version") != STRUCTURE_VERSION or
            lexical.get("contract_version") != LEXICAL_VERSION or
            structure.get("article_id") != lexical.get("article_id") or
            structure.get("source_faithful_sha256") != lexical.get("source_faithful_sha256") or
            structure.get("source_objects", []) != lexical.get("source_objects", [])):
        raise ValueError("PDF structure/lexical source identity mismatch")
    text = "\n".join(line["text"] for line in structure["visual_lines"])
    if sha256(text.encode("utf-8")).hexdigest() != lexical["visual_sha256"]:
        raise ValueError("PDF visual source mismatch")
    line_offsets: list[int] = []
    cursor = 0
    for line in structure["visual_lines"]:
        line_offsets.append(cursor)
        cursor += len(line["text"]) + 1
    citations = structure["candidates"]["parenthetical_citations"]
    cite_by_quote = {pair["quote_index"]: pair["citation_index"]
                     for pair in structure["candidates"]["adjacent_quote_citation_pairs"]}
    result: list[dict[str, str]] = []
    for disposition in lexical["quote_dispositions"]:
        if disposition["kind"] != "unresolved":
            continue
        index = disposition["quote_index"]
        quote = structure["candidates"]["german_quotes"][index]
        start, end = quote["visual_start"], quote["visual_end"]
        triage = quote_subtype(structure, quote)
        line_index = quote["start_line_index"]
        context = [{"line_index": i, "page_id": structure["visual_lines"][i]["page_id"],
                    "printed_page": structure["visual_lines"][i]["printed_page"],
                    "text": structure["visual_lines"][i]["text"]}
                   for i in range(max(0, line_index - 3),
                                  min(len(structure["visual_lines"]), line_index + 3))]
        italic: list[dict[str, Any]] = []
        for i in range(max(0, line_index - 3), line_index + 1):
            for span in structure["visual_lines"][i]["style_spans"]:
                if span["family"] != "TGaramond" or span["style"] != "italic":
                    continue
                span_end = line_offsets[i] + span["end"]
                if span_end > start or start - span_end > 300:
                    continue
                italic.append({"line_index": i, "visual_start": line_offsets[i] + span["start"],
                               "visual_end": span_end,
                               "text": structure["visual_lines"][i]["text"][span["start"]:span["end"]],
                               "gap_to_quote": text[span_end:start]})
        cite_index = cite_by_quote.get(index)
        citation = citations[cite_index] if cite_index is not None else None
        review_id = sha256(f"{structure['article_id']}\t{index}\t{start}\t{end}\t{lexical['visual_sha256']}".encode()).hexdigest()[:20]
        result.append({"review_id": review_id, "article_id": structure["article_id"],
                       "volume": str(structure["volume"]),
                       "loc_headword": structure["loc_headword"],
                       "homonym": str(structure.get("homonym") or ""),
                       "source_faithful_sha256": structure["source_faithful_sha256"],
                       "visual_sha256": lexical["visual_sha256"],
                       "source_objects_json": json.dumps(structure.get("source_objects", []), ensure_ascii=False, sort_keys=True),
                       "division_index": str(quote.get("division_index", "")),
                       "quote_index": str(index), "reason": disposition["reason"],
                       "subtype": triage["subtype"], "flags": ",".join(triage["evidence_flags"]),
                       "quote_visual_start": str(start), "quote_visual_end": str(end),
                       "quote_text": text[start:end],
                       "citation_index": str(cite_index) if cite_index is not None else "",
                       "citation_text": text[citation["visual_start"]:citation["visual_end"]] if citation else "",
                       "preceding_italic_json": json.dumps(italic, ensure_ascii=False, sort_keys=True),
                       "context_json": json.dumps(context, ensure_ascii=False, sort_keys=True),
                       "review_status": "unreviewed", "reviewed_role": "", "review_notes": ""})
    return result


def build(structure_path: Path, lexical_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    logical = sha256()
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for structure, lexical in zip_longest(rows(structure_path), rows(lexical_path)):
            if structure is None or lexical is None:
                raise ValueError("PDF structure and lexical corpus lengths differ")
            for row in review_rows(structure, lexical):
                writer.writerow(row)
                logical.update(stable_json_bytes(row) + b"\n")
                count += 1
    return {"contract_version": VERSION, "unresolved_quotes": count,
            "logical_sha256": logical.hexdigest(),
            "tsv_sha256": sha256(output.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("structure", type=Path)
    parser.add_argument("lexical", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.structure, args.lexical, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
