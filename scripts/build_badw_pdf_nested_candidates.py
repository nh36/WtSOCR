#!/usr/bin/env python3
"""Project source-anchored PDF candidates into an auditable entry hierarchy.

This is deliberately a *candidate* contract. A numbered division is a sense
candidate; an unsegmented division is not silently promoted to a sense. The
original LoC text, every candidate, and every unresolved quote remain linked
to the source-anchored flat parse. No OCR or editorial correction is applied.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterator

from badw_canonical_pages import stable_json_bytes
from extract_badw_pdf_lexical_candidates import VERSION as LEXICAL_VERSION, validate as validate_lexical
from parse_badw_pdf_articles import VERSION as STRUCTURE_VERSION

VERSION = "badw-pdf-nested-candidates-v4"
COLLECTIONS = ("definitions", "tibetan_examples", "belegstellen",
               "lexicographic_parallels", "variant_glosses", "translations", "citations",
               "correction_apparatus", "quoted_non_examples")


def rows(path: Path) -> Iterator[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def quote_subtype(structure: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    """Describe interrupted-span evidence without deciding the quote's role."""
    lines = structure["visual_lines"]
    line_index = quote["start_line_index"]
    first = max(0, line_index - 2)
    nearby = lines[first:line_index + 1]
    italic = [(i, span) for i in range(first, line_index + 1)
              for span in lines[i]["style_spans"]
              if span["family"] == "TGaramond" and span["style"] == "italic"]
    flags = []
    if any(line["unknown_glyphs"] for line in nearby):
        flags.append("unknown_glyph_nearby")
    if any("(r." in line["text"] or "(r.\n" in line["text"] for line in nearby):
        flags.append("printed_correction_nearby")
    if any("(metr.)" in line["text"] for line in nearby):
        flags.append("metrical_qualifier_nearby")
    if any("Lex." in line["text"] for line in nearby):
        flags.append("lexical_region_nearby")
    if not italic:
        subtype = "no_nearby_italic_span"
    elif any(i == line_index for i, _ in italic):
        subtype = "same_line_italic_evidence"
    else:
        subtype = "prior_line_italic_evidence"
    return {"subtype": subtype, "evidence_flags": flags,
            "context_line_indices": list(range(first, line_index + 1))}


def project(structure: dict[str, Any], lexical: dict[str, Any]) -> dict[str, Any]:
    if (structure.get("contract_version") != STRUCTURE_VERSION or
            lexical.get("contract_version") != LEXICAL_VERSION or
            structure.get("article_id") != lexical.get("article_id") or
            structure.get("source_faithful_sha256") != lexical.get("source_faithful_sha256") or
            structure.get("source_objects") != lexical.get("source_objects")):
        raise ValueError("PDF structure/lexical source identity mismatch")
    if len(structure["divisions"]) != len(lexical["divisions"]):
        raise ValueError("PDF division count mismatch")
    text = "\n".join(line["text"] for line in structure["visual_lines"])
    if sha256(text.encode("utf-8")).hexdigest() != lexical["visual_sha256"]:
        raise ValueError("PDF visual source mismatch")
    validate_lexical(structure, lexical)
    seen: dict[str, set[int]] = {name: set() for name in COLLECTIONS}
    quote_seen: set[int] = set()
    divisions: list[dict[str, Any]] = []
    for d, (source_division, division) in enumerate(zip(structure["divisions"], lexical["divisions"])):
        if any(source_division[key] != division[key] for key in
               ("kind", "label", "start_line_index", "end_line_index_exclusive")):
            raise ValueError("PDF division boundaries differ")
        items: list[dict[str, Any]] = []

        def add(kind: str, references: dict[str, int | None], *, extra: dict[str, Any] | None = None) -> None:
            members = {name: lexical[name][index] for name, index in references.items()
                       if index is not None}
            for name, index in references.items():
                if index is None:
                    continue
                if index in seen[name]:
                    raise ValueError(f"duplicate {name} reference in {lexical['article_id']}")
                seen[name].add(index)
            anchor = members.get("belegstellen") or members.get("lexicographic_parallels") or next(iter(members.values()))
            items.append({"kind": kind, "references": references,
                          "components": members,
                          "visual_start": anchor["visual_start"],
                          "visual_end": anchor["visual_end"], **(extra or {})})

        for i in division["definition_indices"]:
            definition = lexical["definitions"][i]
            if "quote_index" in definition:
                quote_index = definition["quote_index"]
                add("definition_candidate", {"definitions": i, "translations": quote_index,
                    "citations": definition.get("citation_index")})
                quote_seen.add(quote_index)
            else:
                add("definition_candidate", {"definitions": i})
        for i in division["belegstelle_indices"]:
            group = lexical["belegstellen"][i]
            if group["division_index"] != d:
                raise ValueError("Belegstelle in wrong division")
            refs = {"belegstellen": i, "tibetan_examples": group["example_index"],
                    "translations": group["translation_index"],
                    "citations": group["citation_index"]}
            # Printed r.-apparatus is linked, but remains a literal proposal.
            corrections = group["correction_indices"]
            add("belegstelle_candidate", refs,
                extra={"corrections": [lexical["correction_apparatus"][c] for c in corrections],
                       "correction_indices": corrections})
            for c in corrections:
                if c in seen["correction_apparatus"]:
                    raise ValueError("duplicate correction reference")
                seen["correction_apparatus"].add(c)
            quote_seen.add(group["quote_index"])
        for i in division["example_indices"]:
            if i in seen["tibetan_examples"]:
                continue
            example = lexical["tibetan_examples"][i]
            quote_index = example["quote_index"]
            disposition = lexical["quote_dispositions"][quote_index]
            if disposition["kind"] != "unresolved":
                raise ValueError("unpaired example has non-unresolved quote")
            # This is a complete, literal Tibetan span with a translation;
            # only its citation association is unresolved. Printed (r. ...)
            # proposals inside that span never make the example incomplete.
            corrections = [c for c, item in enumerate(lexical["correction_apparatus"])
                           if item.get("example_index") == i]
            add("uncited_example_candidate",
                {"tibetan_examples": i, "translations": quote_index},
                extra={"quote_index": quote_index, "reason": disposition["reason"],
                       "correction_indices": corrections,
                       "corrections": [lexical["correction_apparatus"][c] for c in corrections]})
            for c in corrections:
                if c in seen["correction_apparatus"]:
                    raise ValueError("duplicate correction reference")
                seen["correction_apparatus"].add(c)
            quote_seen.add(quote_index)
        for i in division["parallel_indices"]:
            parallel = lexical["lexicographic_parallels"][i]
            add("lexicographic_parallel_candidate",
                {"lexicographic_parallels": i,
                 "translations": parallel["translation_index"],
                 "citations": parallel["citation_index"]})
            quote_seen.add(parallel["quote_index"])
        for i in division["variant_gloss_indices"]:
            variant = lexical["variant_glosses"][i]
            add("variant_gloss_candidate", {"variant_glosses": i,
                "translations": variant["translation_index"]})
            quote_seen.add(variant["quote_index"])
        for i, record in enumerate(lexical["quoted_non_examples"]):
            if record["division_index"] == d:
                add(record["semantic_role"] + "_candidate",
                    {"quoted_non_examples": i, "translations": record["quote_index"],
                     "citations": record.get("citation_index")})
                quote_seen.add(record["quote_index"])
        for quote_index, disposition in enumerate(lexical["quote_dispositions"]):
            if quote_index in quote_seen or disposition["kind"] != "unresolved":
                continue
            translation = lexical["translations"][quote_index]
            if translation["division_index"] != d:
                continue
            add("unresolved_quote", {"translations": quote_index},
                extra={"quote_index": quote_index, "reason": disposition["reason"],
                       "triage": quote_subtype(structure,
                           structure["candidates"]["german_quotes"][quote_index])})
            quote_seen.add(quote_index)
        # Unpaired citations and corrections are retained as source items, not
        # forced onto the nearest example or definition.
        for name, kind in (("citations", "unassigned_citation_candidate"),
                           ("correction_apparatus", "unassigned_printed_correction")):
            for i, record in enumerate(lexical[name]):
                if i not in seen[name] and record.get("division_index") == d:
                    add(kind, {name: i})
        items.sort(key=lambda x: (x["visual_start"], x["visual_end"], x["kind"]))
        divisions.append({"division_index": d,
                          "kind": "sense_candidate" if division["kind"] == "numbered_sense"
                                  else "unsegmented_source_division",
                          "printed_label": division["label"],
                          "start_line_index": division["start_line_index"],
                          "end_line_index_exclusive": division["end_line_index_exclusive"],
                          "source_text": source_division["text"],
                          "items": items})
    # Some source candidates can be outside a typographic division. Keep them
    # at entry level with their exact coordinates rather than inventing one.
    unassigned: list[dict[str, Any]] = []
    for name in COLLECTIONS:
        for i, record in enumerate(lexical[name]):
            if i not in seen[name]:
                if name in ("definitions", "tibetan_examples", "belegstellen",
                            "lexicographic_parallels", "variant_glosses", "translations", "quoted_non_examples") and record.get("division_index") is not None:
                    raise ValueError(f"lost in-division {name} candidate")
                unassigned.append({"collection": name, "index": i, "record": record})
                seen[name].add(i)
        if seen[name] != set(range(len(lexical[name]))):
            raise ValueError(f"{name} coverage mismatch")
    if quote_seen != set(range(len(lexical["quote_dispositions"]))):
        raise ValueError("quote disposition coverage mismatch")
    return {"contract_version": VERSION, "article_id": lexical["article_id"],
            "volume": lexical["volume"], "loc_headword": lexical["loc_headword"],
            "tibetan_headword": lexical["tibetan_headword"], "homonym": lexical["homonym"],
            "source_objects": lexical["source_objects"],
            "source_faithful_sha256": lexical["source_faithful_sha256"],
            "visual_sha256": lexical["visual_sha256"],
            "flat_candidate_sha256": sha256(stable_json_bytes(lexical)).hexdigest(),
            "divisions": divisions, "unassigned_source_candidates": unassigned}


def build(structure_path: Path, lexical_path: Path, output: Path, diagnostics: Path) -> dict[str, Any]:
    if output.exists() or diagnostics.exists():
        raise FileExistsError("output or diagnostics already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    digest = sha256()
    with output.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as sink, diagnostics.open("wb") as diag:
        for structure, lexical in zip_longest(rows(structure_path), rows(lexical_path)):
            if structure is None or lexical is None:
                raise ValueError("PDF structure and lexical corpus lengths differ")
            result = project(structure, lexical)
            encoded = stable_json_bytes(result) + b"\n"
            sink.write(encoded)
            digest.update(encoded)
            counts["articles"] += 1
            for division in result["divisions"]:
                counts[division["kind"]] += 1
                for item in division["items"]:
                    counts[item["kind"]] += 1
            counts["entry_unassigned_candidates"] += len(result["unassigned_source_candidates"])
            # Emit one diagnostic for *every* unresolved quote, including
            # valid Tibetan spans awaiting citation association.
            for disposition in lexical["quote_dispositions"]:
                if disposition["kind"] != "unresolved":
                    continue
                index = disposition["quote_index"]
                quote = structure["candidates"]["german_quotes"][index]
                triage = quote_subtype(structure, quote)
                diagnostic = {"article_id": result["article_id"],
                              "volume": result["volume"],
                              "loc_headword": result["loc_headword"],
                              "homonym": result["homonym"],
                              "division_index": quote.get("division_index"),
                              "quote_index": index,
                              "reason": disposition["reason"], "triage": triage,
                              "context_lines": [structure["visual_lines"][i]["text"]
                                                for i in triage["context_line_indices"]],
                              "translation": lexical["translations"][index]}
                diag.write(stable_json_bytes(diagnostic) + b"\n")
                counts["reason:" + disposition["reason"]] += 1
                counts["subtype:" + triage["subtype"]] += 1
    return {"contract_version": VERSION, "counts": dict(sorted(counts.items())),
            "logical_sha256": digest.hexdigest(),
            "compressed_sha256": sha256(output.read_bytes()).hexdigest(),
            "diagnostics_sha256": sha256(diagnostics.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("structure", type=Path)
    parser.add_argument("lexical", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("diagnostics", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.structure, args.lexical, args.output, args.diagnostics), sort_keys=True))


if __name__ == "__main__":
    main()
