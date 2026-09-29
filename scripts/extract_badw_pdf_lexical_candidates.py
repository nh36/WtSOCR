#!/usr/bin/env python3
"""Extract conservative, source-anchored lexical candidates from BAdW PDF structure.

These are review candidates, not dictionary facts.  In particular, an italic
LoC passage in a ``Lex.`` section is not promoted to an illustrative example.
No source text is normalized or silently repaired.
"""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable

from badw_canonical_pages import stable_json_bytes


VERSION = "badw-pdf-lexical-candidates-v1"
QUALIFIER = re.compile(r"\s*(?:\(metr\.\)\s*)?\Z")
LEX_LABEL = re.compile(r"(?:^|[\s;])Lex\.\s")
MORPHOLOGY = re.compile(r"\b(?:pf\.|fut\.|prs\.|imp\.|vgl\.|siehe)\b|[↑↓]")
MORPHOLOGY_PREFIX = re.compile(r"^\s*(?:pf\.|fut\.|prs\.|imp\.)\s+zu\s+[↑↓]")


def _offsets(lines: list[dict[str, Any]]) -> list[int]:
    result: list[int] = []
    cursor = 0
    for line in lines:
        result.append(cursor)
        cursor += len(line["text"]) + 1
    return result


def _anchor(lines: list[dict[str, Any]], offsets: list[int], start: int, end: int) -> dict[str, Any]:
    if not 0 <= start < end <= offsets[-1] + len(lines[-1]["text"]):
        raise ValueError("candidate outside visual text")
    first = max(i for i, offset in enumerate(offsets) if offset <= start)
    last = max(i for i, offset in enumerate(offsets) if offset < end)
    return {"visual_start": start, "visual_end": end,
        "source_lines": [{"line_index": i, "page_id": lines[i]["page_id"],
            "span_index": lines[i]["span_index"], "printed_page": lines[i]["printed_page"],
            "run_start": lines[i]["run_start"],
            "run_end_exclusive": lines[i]["run_end_exclusive"]}
            for i in range(first, last + 1)]}


def _italic_intervals(lines: list[dict[str, Any]], offsets: list[int]) -> list[tuple[int, int, int]]:
    intervals: list[tuple[int, int, int]] = []
    for i, line in enumerate(lines):
        for span in line["style_spans"]:
            if span["family"] == "TGaramond" and span["style"] == "italic":
                intervals.append((offsets[i] + span["start"], offsets[i] + span["end"], i))
    return intervals


def _lexical_region(lines: list[dict[str, Any]], quote_line: int, division_start: int) -> bool:
    # A Lex. block may begin after illustrative citations in the same sense.
    # A new numbered sense starts a new region.
    return any(LEX_LABEL.search(lines[i]["text"]) for i in range(division_start, quote_line + 1))


def _definition_candidates(article: dict[str, Any], text: str,
                           offsets: list[int]) -> list[dict[str, Any]]:
    lines = article["visual_lines"]
    results: list[dict[str, Any]] = []
    for division_index, division in enumerate(article["divisions"]):
        indices = range(division["start_line_index"], division["end_line_index_exclusive"])
        fragments: list[str] = []
        start: int | None = None
        for i in indices:
            line = lines[i]
            if LEX_LABEL.search(line["text"]) or line["unknown_glyphs"]:
                break
            # A definition may contain an italic LoC term (e.g. "Krug für
            # chaṅ").  Require a regular prose start, but permit such an
            # inline term.  Stop before any non-TGaramond heading/shad.
            spans = line["style_spans"]
            if not spans or spans[0]["family"] != "TGaramond":
                break
            starts_regular = spans[0]["style"] == "regular"
            # A source definition can continue after a line-final italic
            # tilde: "~ / mdzad geloben ...".  This is narrowly admitted
            # only when the next line also contains regular German prose.
            mixed_continuation = (bool(fragments) and not starts_regular
                and fragments[-1].rstrip().endswith("~")
                and any(span["family"] == "TGaramond" and span["style"] == "regular"
                        for span in spans)
                and "„" not in line["text"] and "“" not in line["text"])
            if not starts_regular and not mixed_continuation:
                break
            if (division["kind"] == "unsegmented" and i == division["start_line_index"]
                    and re.match(r"\s*(?:Kurzf\.\s+für|auch\s+)", line["text"])
                    and any(span["family"] == "TGaramond" and span["style"] == "italic"
                            for span in spans)):
                # Lemma variants and abbreviation expansions are source
                # metadata, not German definitions.
                break
            prose_end = min((span["start"] for span in spans
                             if span["family"] != "TGaramond"), default=len(line["text"]))
            segment_start = 0
            if i == division["start_line_index"] and MORPHOLOGY_PREFIX.match(line["text"]):
                # A printed inflection reference may precede the gloss, on
                # the same visual line or the next.  Its italic target is
                # typographically bounded; never infer the end from spelling.
                italic = next((span for span in spans if span["family"] == "TGaramond"
                               and span["style"] == "italic"), None)
                if italic is None:
                    break
                segment_start = italic["end"]
                if not line["text"][segment_start:prose_end].strip():
                    continue
            part = line["text"][segment_start:prose_end]
            if "„" in part or "“" in part:
                break
            if division["kind"] == "numbered_sense" and i == division["start_line_index"]:
                part = re.sub(r"^\s*" + re.escape(division["label"]) + r"\.\s*", "", part, count=1)
            truncated = prose_end < len(line["text"]) or "།" in part
            if "།" in part:
                part = part.split("།", 1)[0]
            if MORPHOLOGY.search(part) or len(part) > 250:
                break
            if start is None:
                start = offsets[i] + line["text"].find(part)
            fragments.append(part)
            if truncated or len(fragments) >= 4:
                break
        if start is None or not fragments:
            continue
        candidate = "\n".join(fragments)
        trimmed = candidate.strip()
        if not trimmed or not re.search(r"[A-Za-zÄÖÜäöüß]", trimmed):
            continue
        start += len(candidate) - len(candidate.lstrip())
        end = start + len(trimmed)
        if text[start:end] != trimmed:
            raise AssertionError("definition candidate lost visual alignment")
        results.append({"text": trimmed, "division_index": division_index,
            "status": "unverified_typographic_candidate", **_anchor(lines, offsets, start, end)})
    return results


def extract(article: dict[str, Any]) -> dict[str, Any]:
    if article.get("contract_version") != "badw-pdf-structural-parser-v3":
        raise ValueError("unsupported PDF structure contract")
    lines = article["visual_lines"]
    text = "\n".join(line["text"] for line in lines)
    offsets = _offsets(lines)
    result: dict[str, Any] = {"contract_version": VERSION,
        "article_id": article["article_id"], "volume": article["volume"],
        "loc_headword": article["loc_headword"],
        "source_faithful_sha256": article["source_faithful_sha256"],
        "visual_sha256": sha256(text.encode("utf-8")).hexdigest(),
        "definitions": [], "tibetan_examples": [], "belegstellen": [],
        "unresolved_quotes": []}
    if not lines:
        return result
    result["definitions"] = _definition_candidates(article, text, offsets)
    intervals = _italic_intervals(lines, offsets)
    quotes = article["candidates"]["german_quotes"]
    citations = article["candidates"]["parenthetical_citations"]
    pairs = {pair["quote_index"]: pair["citation_index"]
             for pair in article["candidates"]["adjacent_quote_citation_pairs"]}
    for quote_index, quote in enumerate(quotes):
        qstart = int(quote["visual_start"])
        eligible = [index for index, (_, end, _) in enumerate(intervals)
                    if end <= qstart and QUALIFIER.fullmatch(text[end:qstart])]
        if not eligible:
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "no_adjacent_italic_loc_span"})
            continue
        index = eligible[-1]
        start, end, first_line = intervals[index]
        # Join LoC text across a visual line break only when the same source
        # page carries an uninterrupted italic continuation.
        while index > 0:
            prev_start, prev_end, prev_line = intervals[index - 1]
            if (lines[prev_line]["page_id"] != lines[first_line]["page_id"]
                    or text[prev_end:start] not in ("", "\n")):
                break
            start, first_line = prev_start, prev_line
            index -= 1
        example_text = text[start:end].strip()
        start += len(text[start:end]) - len(text[start:end].lstrip())
        end = start + len(example_text)
        if not example_text or "⟦UNKNOWN:" in example_text:
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "empty_or_unknown_loc_span"})
            continue
        division_index = quote.get("division_index")
        if division_index is None:
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "quote_crosses_division"})
            continue
        division = article["divisions"][division_index]
        quote_line = int(quote["start_line_index"])
        lex = _lexical_region(lines, quote_line, division["start_line_index"])
        # A parenthetical correction inside a source quote splits the italic
        # run.  Never present the tail as a complete Tibetan example.
        preceding = text[max(0, start - 100):start]
        if preceding.count("(") > preceding.count(")"):
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "italic_fragment_after_open_parenthesis"})
            continue
        prior_same_line = [prior_start for prior_start, _, line_index in intervals
                           if line_index == first_line and prior_start < start]
        if prior_same_line and re.search(r"\(\s*r\.\s*", text[min(prior_same_line):start]):
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "mixed_style_parenthetical_correction"})
            continue
        example = {"text": example_text, "quote_index": quote_index,
            "division_index": division_index, "lexical_region": lex,
            "status": "lexicon_quote_candidate" if lex else "unverified_typographic_candidate",
            **_anchor(lines, offsets, start, end)}
        result["tibetan_examples"].append(example)
        cite_index = pairs.get(quote_index)
        if cite_index is None or lex:
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "lexicon_region" if lex else "no_adjacent_citation"})
            continue
        citation = citations[cite_index]
        citation_end = int(citation["visual_end"])
        # The candidate covers the entire visible citation group; it does
        # not claim that its siglum has been linked to a bibliography record.
        group = {"text": text[start:citation_end], "quote_index": quote_index,
            "citation_index": cite_index, "example_index": len(result["tibetan_examples"]) - 1,
            "division_index": division_index, "status": "unverified_typographic_candidate",
            **_anchor(lines, offsets, start, citation_end)}
        result["belegstellen"].append(group)
    return result


def _rows(path: Path) -> Iterable[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def build(source: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stats: Counter[str] = Counter()
    logical = sha256()
    with output.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as sink:
        for article in _rows(source):
            row = extract(article)
            encoded = stable_json_bytes(row) + b"\n"
            sink.write(encoded)
            logical.update(encoded)
            stats["articles"] += 1
            stats[f"volume_{row['volume']}"] += 1
            for key in ("definitions", "tibetan_examples", "belegstellen", "unresolved_quotes"):
                stats[key] += len(row[key])
    return {"contract_version": VERSION, "counts": dict(sorted(stats.items())),
        "logical_sha256": logical.hexdigest(),
        "compressed_sha256": sha256(output.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.articles, args.output), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
