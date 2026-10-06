#!/usr/bin/env python3
"""Extract conservative, source-anchored lexical candidates from BAdW PDF structure.

These are review candidates, not dictionary facts.  In particular, an italic
LoC passage in a ``Lex.`` section is not promoted to an illustrative example.
No source text is normalized or silently repaired.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
import gzip
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable

from badw_canonical_pages import stable_json_bytes
from parse_badw_pdf_articles import VERSION as STRUCTURE_VERSION
from badw_pdf_expressions import boundary_mask, contains_unknown, NONPRINTING


VERSION = "badw-pdf-lexical-candidates-v12"
ROLE_REVIEWS = Path(__file__).resolve().parents[1] / "data/reviewed_badw_pdf_quote_roles.tsv"
SPAN_REVIEWS = Path(__file__).resolve().parents[1] / "data/reviewed_badw_pdf_example_spans.tsv"


@lru_cache(maxsize=4)
def load_role_reviews(path: Path = ROLE_REVIEWS) -> dict[tuple[str, int], dict[str, str]]:
    """Exact semantic reviews, never language/font-based blanket promotion."""
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    result = {}
    for row in rows:
        key = (row["article_id"], int(row["visual_start"]))
        if key in result or row["role"] not in {
                "definition", "usage_gloss", "etymological_gloss", "scholarly_commentary"}:
            raise ValueError("invalid or duplicate PDF quote role review")
        result[key] = row
    return result


def reviewed_quote_role(article: dict[str, Any], quote: dict[str, Any], text: str,
                        reviews: dict[tuple[str, int], dict[str, str]]) -> dict[str, str] | None:
    row = reviews.get((article["article_id"], int(quote["visual_start"])))
    if row is None:
        return None
    literal = text[quote["visual_start"]:quote["visual_end"]]
    if (row["visual_sha256"] != sha256(text.encode()).hexdigest()
            or int(row["visual_end"]) != quote["visual_end"]
            or row["quote_sha256"] != sha256(literal.encode()).hexdigest()):
        raise ValueError("stale PDF quote role review: " + article["article_id"])
    return row


@lru_cache(maxsize=4)
def load_span_reviews(path: Path = SPAN_REVIEWS) -> dict[tuple[str, int], dict[str, str]]:
    """Source-reviewed mixed-font boundaries, not a general roman-text rule."""
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    result = {}
    for row in rows:
        key = (row["article_id"], int(row["visual_start"]))
        if key in result:
            raise ValueError("duplicate PDF example span review")
        result[key] = row
    return result


def reviewed_example_span(article: dict[str, Any], quote: dict[str, Any], text: str,
                          reviews: dict[tuple[str, int], dict[str, str]]) -> dict[str, str] | None:
    row = reviewed_quote_role(article, quote, text, reviews)
    if row is None:
        return None
    start, end = int(row["example_start"]), int(row["example_end"])
    division_index = quote.get("division_index")
    if division_index is None:
        raise ValueError("reviewed PDF example has no division")
    offsets = _offsets(article["visual_lines"])
    division = article["divisions"][division_index]
    division_start = offsets[division["start_line_index"]]
    if (not division_start <= start < end <= quote["visual_start"]
            or row["example_sha256"] != sha256(text[start:end].encode()).hexdigest()
            or any(mark in text[end:quote["visual_start"]] for mark in "„“")):
        raise ValueError("stale or out-of-division PDF example span review")
    return row


QUALIFIER = re.compile(r"\s*(?:\(metr\.\s*\)\s*)?\Z")
LEX_LABEL = re.compile(r"(?:^|[\s;])Lex\.\s")
MORPHOLOGY = re.compile(r"\b(?:pf\.|fut\.|prs\.|imp\.|vgl\.|siehe)\b|[↑↓]")
MORPHOLOGY_PREFIX = re.compile(r"^\s*(?:pf\.|fut\.|prs\.|imp\.)\s+zu\s+[↑↓]")
GLOSS_REFERENCE_SUFFIX = re.compile(r"[,;]\s*vgl\.\s+[↑↓][^\n,;()„“]+\.?\s*$")
REFERENCE_CONTINUATION = re.compile(r"\s*vgl\.\s+[↑↓][^\n;()„“]+\.?\s*\Z")
MORPHOLOGY_PREAMBLE = re.compile(r"\s*(?:pf\.|fut\.|prs\.|imp\.)\s*\Z")
PRINTED_CORRECTION = re.compile(r"\(r\.\s*(?P<proposal>[^()]+?)\)")
PRECEDING_TOKEN = re.compile(r"(?P<target>[^\s()]+)\s*\Z")
VARIANT_GLOSS_CUE = re.compile(
    r"(?<!\w)(?P<cue>auch|Kurzf\.\s+für|(?:pf|prs|fut|imp)\.\s*(?:zu\s*)?[↑↓])\s*\Z")


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
            "line_char_start": max(0, start - offsets[i]),
            "line_char_end": min(len(lines[i]["text"]), end - offsets[i]),
            "run_start": lines[i]["run_start"],
            "run_end_exclusive": lines[i]["run_end_exclusive"]}
            for i in range(first, last + 1)]}


def _in_italic(intervals: list[tuple[int, int, int]], start: int, end: int) -> bool:
    return any(left <= start and end <= right for left, right, _ in intervals)


def _corrections(text: str, examples: list[dict[str, Any]],
                 lines: list[dict[str, Any]], offsets: list[int],
                 intervals: list[tuple[int, int, int]]) -> list[dict[str, Any]]:
    """Inventory literal simple r.-apparatus, including unpaired passages."""
    records: list[dict[str, Any]] = []
    for match in PRINTED_CORRECTION.finditer(text):
        proposed = match.group("proposal").strip()
        pstart = match.start("proposal") + len(match.group("proposal")) - len(match.group("proposal").lstrip())
        pend = pstart + len(proposed)
        example_index = next((i for i, example in enumerate(examples)
                              if example["visual_start"] <= match.start() and
                              match.end() <= example["visual_end"]), None)
        line_start = text.rfind("\n", 0, match.start()) + 1
        prior = PRECEDING_TOKEN.search(text[line_start:match.start()])
        target_start = line_start + prior.start("target") if prior else None
        target_end = line_start + prior.end("target") if prior else None
        multiword_proposal = len(proposed.split()) > 1
        anchored = (bool(proposed) and "~" not in proposed and not multiword_proposal
                    and prior is not None and
                    _in_italic(intervals, target_start, target_end) and
                    "⟦UNKNOWN:" not in proposed and
                    "⟦UNKNOWN:" not in prior.group("target"))
        record = {"literal_text": match.group(), "proposed_reading": proposed,
            "interpretation": "printed_apparatus_not_applied",
            "example_index": example_index,
            "division_index": examples[example_index]["division_index"]
                if example_index is not None else None,
            "status": "anchored_printed_proposal" if anchored else
                ("contextual_placeholder" if "~" in proposed else
                 "multiword_target_scope_unresolved" if multiword_proposal else
                 "unresolved_target"),
            "proposal_span": _anchor(lines, offsets, pstart, pend),
            **_anchor(lines, offsets, match.start(), match.end())}
        if anchored:
            record["target_text"] = prior.group("target")
            record["target_span"] = _anchor(lines, offsets, target_start, target_end)
        records.append(record)
    return records


def _italic_intervals(lines: list[dict[str, Any]], offsets: list[int]) -> list[tuple[int, int, int]]:
    intervals: list[tuple[int, int, int]] = []
    for i, line in enumerate(lines):
        for span in line["style_spans"]:
            if span["family"] == "TGaramond" and span["style"] == "italic":
                if line["text"][span["start"]:span["end"]].strip():
                    intervals.append((offsets[i] + span["start"], offsets[i] + span["end"], i))
    return intervals


def _lexical_region(lines: list[dict[str, Any]], quote_line: int, division_start: int) -> bool:
    # A Lex. block may begin after illustrative citations in the same sense.
    # A new numbered sense starts a new region.
    return any(LEX_LABEL.search(lines[i]["text"]) for i in range(division_start, quote_line + 1))


def _opening_prose_offset(lines, offsets, division, text):
    """Skip explicit opening reference/alias typography, not lexical spelling.

    A target is an uninterrupted italic TGaramond sequence, possibly wrapped.
    Repeated tense references are permitted; only the following regular run
    can start prose. No language or citation ownership is inferred here.
    """
    a = offsets[division["start_line_index"]]
    stop = division["end_line_index_exclusive"]
    b = offsets[stop] - 1 if stop < len(offsets) else len(text)
    italic = [(offsets[i] + s["start"], offsets[i] + s["end"])
              for i in range(division["start_line_index"], stop)
              for s in lines[i]["style_spans"]
              if s["family"] == "TGaramond" and s["style"] == "italic"]
    tense = r"(?:pf\.|fut\.|prs\.|imp\.)"
    prefix = re.compile(r"\s*(?:" + tense + r"(?:\s+und\s+" + tense
                        + r")*\s+(?:zu\s+)?[↑↓]\s*|auch\s+)")
    pos, consumed = a, False
    while (match := prefix.match(text, pos, b)):
        target = match.end()
        run = next(((x, y) for x, y in italic if x <= target < y), None)
        if run is None:
            break
        end = run[1]
        # Whitespace joins a wrapped target. Only the explicit alias opening
        # permits a comma-separated list of italic aliases; regular prose
        # between runs always stops the opening.
        alias_list = match.group().lstrip().startswith("auch ")
        for x, y in italic:
            separator = text[end:x]
            if x >= end and (not separator.strip()
                             or alias_list and separator.strip() == ","):
                end = y
        pos, consumed = end, True
    return pos if consumed else a


def _definition_candidates(article: dict[str, Any], text: str,
                           offsets: list[int]) -> list[dict[str, Any]]:
    lines = article["visual_lines"]
    results: list[dict[str, Any]] = []
    for division_index, division in enumerate(article["divisions"]):
        indices = range(division["start_line_index"], division["end_line_index_exclusive"])
        fragments: list[str] = []
        start: int | None = None
        opening = _opening_prose_offset(lines, offsets, division, text)
        for i in indices:
            line = lines[i]
            if offsets[i] + len(line["text"]) <= opening:
                continue
            opening_cut = max(0, opening - offsets[i]) if not fragments else 0
            if LEX_LABEL.search(line["text"]) or line["unknown_glyphs"]:
                break
            # A definition may contain an italic LoC term (e.g. "Krug für
            # chaṅ").  Require a regular prose start, but permit such an
            # inline term.  Stop before any non-TGaramond heading/shad.
            spans = line["style_spans"]
            if not spans or spans[0]["family"] != "TGaramond":
                break
            first_prose = next((s for s in spans if s["end"] > opening_cut), spans[0])
            starts_regular = first_prose["style"] == "regular"
            # A source definition can continue after a line-final italic
            # tilde: "~ / mdzad geloben ...".  This is narrowly admitted
            # only when the next line also contains regular German prose.
            mixed_continuation = (bool(fragments) and not starts_regular
                and fragments[-1].rstrip().endswith("~")
                and any(span["family"] == "TGaramond" and span["style"] == "regular"
                        for span in spans)
                and "„" not in line["text"] and "“" not in line["text"])
            sanskrit_continuation = (bool(fragments) and not starts_regular
                and fragments[-1].rstrip().endswith("-")
                and "skt." in "\n".join(fragments)
                and spans[0]["family"] == "TGaramond"
                and spans[0]["style"] == "italic"
                and "„" not in line["text"] and "“" not in line["text"])
            if not starts_regular and not (mixed_continuation or sanskrit_continuation):
                break
            if (opening_cut == 0 and division["kind"] == "unsegmented" and i == division["start_line_index"]
                    and re.match(r"\s*(?:Kurzf\.\s+für|auch\s+)", line["text"])
                    and any(span["family"] == "TGaramond" and span["style"] == "italic"
                            for span in spans)):
                # A variant may be followed by a German gloss on the same
                # source line.  Do not promote the variant itself to a gloss.
                variant = next((span for span in spans if span["family"] == "TGaramond"
                                and span["style"] == "italic"), None)
                trailing = line["text"][variant["end"]:] if variant else ""
                if (not re.match(r"\s*auch\s+", line["text"])
                        or not re.match(r"\s+[A-ZÄÖÜ][a-zäöüß]", trailing)):
                    break
                segment_start = variant["end"]
            else:
                segment_start = opening_cut
            prose_end = min((span["start"] for span in spans
                             if span["family"] != "TGaramond"), default=len(line["text"]))
            if opening_cut == 0 and i == division["start_line_index"] and MORPHOLOGY_PREFIX.match(line["text"]):
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
            reference_suffix = GLOSS_REFERENCE_SUFFIX.search(part)
            # A wrapped reference target need not end on this source line.
            # Preserve the preceding German continuation without swallowing
            # the reference or inferring its target/ownership.
            reference_opening = re.search(r"[,;]\s*vgl\.\s+[↑↓]", part)
            if reference_opening and not reference_suffix:
                preceding = part[:reference_opening.start()]
                if (re.search(r"[A-Za-zÄÖÜäöüß]", preceding)
                        and not MORPHOLOGY.search(preceding)
                        and not MORPHOLOGY_PREAMBLE.fullmatch(preceding)):
                    part = preceding
                    truncated = True
            gloss_before_reference = part[:reference_suffix.start()] if reference_suffix else ""
            reference_continuation = (bool(fragments) and fragments[-1].rstrip().endswith(";")
                                      and REFERENCE_CONTINUATION.fullmatch(part))
            hyphenated_prose_continuation = (bool(fragments)
                                            and fragments[-1].rstrip().endswith("-")
                                            and bool(re.match(r"\s*[a-zäöüß]", part))
                                            and bool(reference_suffix)
                                            and bool(re.search(r"[A-Za-zÄÖÜäöüß]", gloss_before_reference))
                                            and not bool(MORPHOLOGY_PREAMBLE.fullmatch(gloss_before_reference)))
            if (len(part) > 250 or
                    (MORPHOLOGY.search(part) and not reference_continuation
                     and not hyphenated_prose_continuation and not (
                        reference_suffix and
                        re.search(r"[A-Za-zÄÖÜäöüß]", gloss_before_reference) and
                        not MORPHOLOGY_PREAMBLE.fullmatch(gloss_before_reference) and
                        not MORPHOLOGY.search(gloss_before_reference)))):
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


def _opening_quoted_definition(article: dict[str, Any], quote: dict[str, Any],
                               quote_index: int, paired: set[int],
                               text: str, offsets: list[int]) -> dict[str, Any] | None:
    """Retain a source-quoted opening gloss as a definition candidate.

    The rule is deliberately narrow: only the first visual line of its own
    division, with no LoC text before it, no adjacent citation, and regular
    TGaramond type. Other orphan quotes remain unresolved for review.
    """
    division_index = quote.get("division_index")
    if division_index is None or quote_index in paired:
        return None
    division = article["divisions"][division_index]
    line_index = int(quote["start_line_index"])
    if line_index != division["start_line_index"]:
        return None
    line = article["visual_lines"][line_index]
    start, end = int(quote["visual_start"]), int(quote["visual_end"])
    local_start = start - offsets[line_index]
    prefix = line["text"][:local_start]
    if division["kind"] == "numbered_sense":
        prefix = re.sub(r"^\s*" + re.escape(division["label"]) + r"\.\s+", "", prefix, count=1)
    if prefix.strip() or line["unknown_glyphs"]:
        return None
    if not any(span["family"] == "TGaramond" and span["style"] == "regular"
               and span["start"] <= local_start < span["end"]
               for span in line["style_spans"]):
        return None
    return {"text": text[start:end], "division_index": division_index,
            "quote_index": quote_index, "status": "unverified_quoted_gloss_candidate",
            **_anchor(article["visual_lines"], offsets, start, end)}


def _quote_internal_lexicon(article: dict[str, Any], quote: dict[str, Any],
                           quote_index: int, citation_index: int | None,
                           text: str, offsets: list[int]) -> dict[str, Any] | None:
    """Quoted LoC lemma followed by a roman German gloss in a cited Lex. region.

    This is not a Tibetan example preceding a translation. Require the literal
    colon boundary, contiguous source-italic prefix, and source-roman suffix.
    """
    division_index = quote.get("division_index")
    if division_index is None or citation_index is None or quote.get("children"):
        return None
    lines = article["visual_lines"]
    if not _lexical_region(lines, quote["start_line_index"],
                           article["divisions"][division_index]["start_line_index"]):
        return None
    start, end = int(quote["visual_start"]), int(quote["visual_end"])
    colon = text.find(":", start + 1, end - 1)
    if colon < 0 or contains_unknown(text[start:end]):
        return None
    def style_at(position: int, style: str) -> bool:
        line_index = max(i for i, offset in enumerate(offsets) if offset <= position)
        local = position - offsets[line_index]
        return any(s["family"] == "TGaramond" and s["style"] == style
                   and s["start"] <= local < s["end"] for s in lines[line_index]["style_spans"])
    if (not all(style_at(i, "italic") for i in range(start + 1, colon) if not text[i].isspace())
            or not all(style_at(i, "regular") for i in range(colon, end) if not text[i].isspace())
            or not text[colon + 1:end - 1].strip()
            or not text[start + 1:colon].strip()):
        return None
    german_start = colon + 1
    while text[german_start].isspace():
        german_start += 1
    citation_end = article["candidates"]["parenthetical_citations"][citation_index]["visual_end"]
    return {"text": text[start:citation_end], "quote_index": quote_index,
            "translation_index": quote_index, "citation_index": citation_index,
            "division_index": division_index, "loc_text": text[start + 1:colon],
            "boundary_kind": "quote_internal_loc_gloss",
            "quoted_loc": {"text": text[start + 1:colon], **_anchor(lines, offsets, start + 1, colon)},
            "german_gloss": {"text": text[german_start:end - 1], **_anchor(lines, offsets, german_start, end - 1)},
            "boundary_review_basis": "source_italic_prefix_roman_colon_and_gloss_in_cited_lex_region",
            "status": "source_lexicon_parallel_candidate",
            **_anchor(lines, offsets, start, citation_end)}


def extract(article: dict[str, Any]) -> dict[str, Any]:
    if article.get("contract_version") != STRUCTURE_VERSION:
        raise ValueError("unsupported PDF structure contract")
    lines = article["visual_lines"]
    text = "\n".join(line["text"] for line in lines)
    offsets = _offsets(lines)
    result: dict[str, Any] = {"contract_version": VERSION,
        "article_id": article["article_id"], "volume": article["volume"],
        "loc_headword": article["loc_headword"],
        "tibetan_headword": article.get("tibetan_headword"),
        "homonym": article.get("homonym"),
        "source_objects": article.get("source_objects", []),
        "source_faithful_sha256": article["source_faithful_sha256"],
        "visual_sha256": sha256(text.encode("utf-8")).hexdigest(),
        "definitions": [], "tibetan_examples": [], "belegstellen": [],
        "lexicographic_parallels": [], "variant_glosses": [], "quoted_non_examples": [], "quote_dispositions": [],
        "translations": [], "citations": [], "correction_apparatus": [],
        "divisions": [], "unresolved_quotes": [], "nonprinting_layout_tokens": []}
    if not lines:
        return result
    result["definitions"] = _definition_candidates(article, text, offsets)
    intervals = _italic_intervals(lines, offsets)
    allowed, apparatus = boundary_mask(text)
    result["nonprinting_layout_tokens"] = [
        {"text": m.group(), "interpretation": "reviewed_nonprinting_outline_not_unicode_mapping",
         **_anchor(lines, offsets, m.start(), m.end())}
        for m in NONPRINTING.finditer(text)]
    quotes = article["candidates"]["german_quotes"]
    citations = article["candidates"]["parenthetical_citations"]
    pairs = {pair["quote_index"]: pair["citation_index"]
             for pair in article["candidates"]["adjacent_quote_citation_pairs"]}
    paired = set(pairs)
    for quote in quotes:
        start, end = int(quote["visual_start"]), int(quote["visual_end"])
        def nested_quotes(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [{"text": text[child["visual_start"]:child["visual_end"]],
                     **_anchor(lines, offsets, child["visual_start"], child["visual_end"]),
                     "children": nested_quotes(child["children"])} for child in children]
        result["translations"].append({"text": text[start:end],
            "division_index": quote.get("division_index"),
            "nested_quotes": nested_quotes(quote.get("children", [])),
            "quotation_diagnostics": quote.get("diagnostics", []),
            "status": "source_quote_candidate", **_anchor(lines, offsets, start, end)})
    for citation in citations:
        start, end = int(citation["visual_start"]), int(citation["visual_end"])
        result["citations"].append({"text": text[start:end],
            "division_index": citation.get("division_index"),
            "status": "unlinked_source_citation_candidate",
            **_anchor(lines, offsets, start, end)})
    # Supplement component observations only. Do not insert these into the
    # indexed quote/citation pairing table or infer support from proximity.
    from badw_source_components import comparison_reference_candidates, author_year_reference_candidates
    for candidate in (comparison_reference_candidates(text, 0, len(text))
                      + author_year_reference_candidates(text, 0, len(text))):
        start, end = candidate["start"], candidate["end"]
        if any(int(c["visual_start"]) <= start and end <= int(c["visual_end"])
               for c in result["citations"]):
            continue
        containing = [i for i, division in enumerate(article["divisions"])
                      if offsets[division["start_line_index"]] <= start
                      and end <= (offsets[division["end_line_index_exclusive"]] - 1
                                  if division["end_line_index_exclusive"] < len(offsets)
                                  else len(text))]
        result["citations"].append({"text": text[start:end],
            "division_index": containing[0] if len(containing) == 1 else None,
            "status": "unlinked_source_citation_candidate",
            "evidence": candidate["evidence"], **_anchor(lines, offsets, start, end)})
    for quote_index, quote in enumerate(quotes):
        review = reviewed_quote_role(article, quote, text, load_role_reviews())
        if review is not None and quote.get("division_index") is not None:
            record = {**result["translations"][quote_index], "quote_index": quote_index,
                      "semantic_role": review["role"], "review_basis": review["basis"],
                      "citation_index": pairs.get(quote_index),
                      "status": "source_reviewed_semantic_candidate"}
            collection = "definitions" if review["role"] == "definition" else "quoted_non_examples"
            result[collection].append(record)
            continue
        internal_lexicon = _quote_internal_lexicon(article, quote, quote_index,
                                                  pairs.get(quote_index), text, offsets)
        if internal_lexicon is not None:
            result["lexicographic_parallels"].append(internal_lexicon)
            continue
        qstart = int(quote["visual_start"])
        quote_line = int(quote["start_line_index"])
        span_review = reviewed_example_span(article, quote, text, load_span_reviews())
        eligible: list[tuple[int, int]] = []
        for interval_index, (_, interval_end, interval_line) in enumerate(intervals):
            # Some generated font runs carry the opening German quote in the
            # preceding italic LoC run.  The quotation candidate starts at
            # that literal mark, so trim exactly that one character; never
            # admit a genuine overlap with German translation text.
            effective_end = (qstart if text[qstart:interval_end] == "„"
                             else interval_end)
            if effective_end > qstart:
                continue
            if (quote.get("division_index") is not None
                    and quote_line - interval_line <= 6 and qstart - effective_end <= 500
                    and (lines[interval_line]["page_id"] == lines[quote_line]["page_id"]
                         or QUALIFIER.fullmatch(text[effective_end:qstart]))
                    and interval_line >= article["divisions"][quote["division_index"]]["start_line_index"]
                    and not any(line["unknown_glyphs"] and "⟦UNKNOWN:" not in line["text"]
                                for line in lines[interval_line:quote_line + 1])):
                if all(allowed[effective_end:qstart]):
                    # Keep a plain metre qualifier outside the example, as in
                    # the previous contract; other literal apparatus remains.
                    example_end = effective_end if QUALIFIER.fullmatch(text[effective_end:qstart]) else qstart
                    metre = re.search(r"\s*\(metr\.\s*\)\s*\Z", text[effective_end:qstart])
                    if metre and "~" not in text[effective_end:qstart]:
                        example_end = effective_end + metre.start()
                    eligible.append((interval_index, example_end))
        if not eligible and span_review is None:
            definition = _opening_quoted_definition(article, quote, quote_index,
                                                    paired, text, offsets)
            if definition is not None:
                result["definitions"].append(definition)
                continue
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "no_adjacent_italic_loc_span"})
            continue
        if span_review is not None:
            start, end = int(span_review["example_start"]), int(span_review["example_end"])
            first_line = max(i for i, offset in enumerate(offsets) if offset <= start)
            index = 0  # Exact reviewed boundary must not be widened by the joiner.
        else:
            index, example_end = eligible[-1]
            start, _, first_line = intervals[index]
            end = example_end
        # Join italic LoC across whitespace and balanced literal apparatus.
        # A page boundary requires adjacent source lines and continuation
        # whitespace or the same apparatus spanning both sides.
        while index > 0:
            prev_start, prev_end, prev_line = intervals[index - 1]
            crosses_page = lines[prev_line]["page_id"] != lines[first_line]["page_id"]
            continuous_page_boundary = (first_line == prev_line + 1
                and (text[prev_end:start].isspace()
                     or any((left <= prev_end <= start <= right
                             or prev_end <= left <= start <= right
                             and text[prev_end:left].isspace())
                            for left, right in apparatus)))
            if (crosses_page and not continuous_page_boundary
                    or first_line - prev_line > 6 or end - prev_start > 500
                    or prev_line < article["divisions"][quote["division_index"]]["start_line_index"]
                    or not all(allowed[prev_end:start])):
                break
            start, first_line = prev_start, prev_line
            index -= 1
        example_text = text[start:end].strip()
        start += len(text[start:end]) - len(text[start:end].lstrip())
        end = start + len(example_text)
        if not example_text or contains_unknown(example_text):
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "empty_or_unknown_loc_span"})
            continue
        division_index = quote.get("division_index")
        if division_index is None:
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "quote_crosses_division"})
            continue
        division = article["divisions"][division_index]
        lex = _lexical_region(lines, quote_line, division["start_line_index"])
        # Apparatus can contain italic runs. Reject a tail beginning inside a
        # balanced expression instead of interpreting its proposal as a new
        # Tibetan example; a successfully joined outer span is safe.
        for left, right in apparatus:
            if left < start < right and (text[left:left + 1] in "⟨{"
                    or re.match(r"\(\s*Gl\.", text[left:right])):
                start = left
        if any(left < start < right for left, right in apparatus):
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "italic_fragment_inside_apparatus"})
            continue
        # Unbalanced literal apparatus is not a license to emit its tail.
        prefix = text[max(0, start - 100):start]
        if prefix.count("(") > prefix.count(")"):
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "italic_fragment_after_open_parenthesis"})
            continue
        # A newly joined italic span can include leading/trailing source
        # whitespace.  Re-anchor the final candidate, not its pre-join tail.
        joined = text[start:end]
        start += len(joined) - len(joined.lstrip())
        end -= len(joined) - len(joined.rstrip())
        example_text = text[start:end]
        # An explicit Sanskrit cue overrides the purely typographic Tibetan
        # hypothesis. Preserve both the italic source and quotation, but do
        # not manufacture a Tibetan example or translation edge. Semantic
        # gloss ownership remains available for source-bound review.
        if re.search(r"\bskt\.\s*\Z", text[max(0, start - 30):start]):
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "explicit_sanskrit_gloss_not_tibetan_example"})
            continue
        # Leading gloss/apparatus expansion can expose glyphs outside the
        # original italic interval. Check the final source span as well.
        if contains_unknown(example_text):
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "empty_or_unknown_loc_span"})
            continue
        cite_index = pairs.get(quote_index)
        if lex:
            parallel_end = int(citations[cite_index]["visual_end"]) if cite_index is not None else int(quote["visual_end"])
            result["lexicographic_parallels"].append({
                "text": text[start:parallel_end], "quote_index": quote_index,
                "translation_index": quote_index, "citation_index": cite_index,
                "division_index": division_index, "loc_text": example_text,
                "boundary_review_basis": span_review["basis"] if span_review else None,
                "status": "source_lexicon_parallel_candidate",
                **_anchor(lines, offsets, start, parallel_end)})
            continue
        # A quoted German gloss immediately following an explicit variant
        # cue is not an illustrative Tibetan Belegstelle.  Require the cue
        # directly before the source-italic LoC span and no citation; other
        # uncited quotations remain unresolved for review.
        variant_cue = (VARIANT_GLOSS_CUE.search(text[max(0, start - 100):start])
                       if cite_index is None else None)
        if variant_cue:
            result["variant_glosses"].append({
                "text": text[start:int(quote["visual_end"])],
                "loc_text": example_text, "cue": variant_cue.group("cue"),
                "quote_index": quote_index, "translation_index": quote_index,
                "division_index": division_index,
                "status": "source_variant_gloss_candidate",
                **_anchor(lines, offsets, start, int(quote["visual_end"]))})
            continue
        example_index = len(result["tibetan_examples"])
        example = {"text": example_text, "quote_index": quote_index,
            "boundary_review_basis": span_review["basis"] if span_review else None,
            "division_index": division_index, "lexical_region": False,
            "status": "unverified_typographic_candidate",
            **_anchor(lines, offsets, start, end)}
        result["tibetan_examples"].append(example)
        if cite_index is None:
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "no_adjacent_citation"})
            continue
        citation = citations[cite_index]
        citation_end = int(citation["visual_end"])
        # The candidate covers the entire visible citation group; it does
        # not claim that its siglum has been linked to a bibliography record.
        group = {"text": text[start:citation_end], "quote_index": quote_index,
            "citation_index": cite_index, "example_index": example_index,
            "translation_index": quote_index,
            "division_index": division_index, "status": "unverified_typographic_candidate",
            **_anchor(lines, offsets, start, citation_end)}
        result["belegstellen"].append(group)
    result["correction_apparatus"] = _corrections(
        text, result["tibetan_examples"], lines, offsets, intervals)
    for group in result["belegstellen"]:
        group["correction_indices"] = [i for i, correction in
            enumerate(result["correction_apparatus"])
            if correction["example_index"] == group["example_index"]]
    dispositions = {item["quote_index"]: ("unresolved", item["reason"])
                    for item in result["unresolved_quotes"]}
    for item in result["belegstellen"]:
        dispositions[item["quote_index"]] = ("belegstelle_candidate", "typographic_source_sequence")
    for item in result["lexicographic_parallels"]:
        dispositions[item["quote_index"]] = ("lexicographic_parallel_candidate", "lexicon_region")
    for item in result["variant_glosses"]:
        dispositions[item["quote_index"]] = ("variant_gloss_candidate", "adjacent_source_variant_cue")
    for item in result["definitions"]:
        if "quote_index" in item:
            dispositions[item["quote_index"]] = ("quoted_definition_candidate", "division_opening_regular_gloss")
            if "review_basis" in item:
                dispositions[item["quote_index"]] = ("quoted_definition_candidate", "exact_source_role_review")
    for item in result["quoted_non_examples"]:
        dispositions[item["quote_index"]] = (item["semantic_role"] + "_candidate", "exact_source_role_review")
    result["quote_dispositions"] = [
        {"quote_index": i, "kind": dispositions[i][0], "reason": dispositions[i][1]}
        for i in range(len(quotes))]
    for division_index, division in enumerate(article["divisions"]):
        result["divisions"].append({"kind": division["kind"], "label": division["label"],
            "start_line_index": division["start_line_index"],
            "end_line_index_exclusive": division["end_line_index_exclusive"],
            "definition_indices": [i for i, item in enumerate(result["definitions"])
                                   if item["division_index"] == division_index],
            "example_indices": [i for i, item in enumerate(result["tibetan_examples"])
                                if item["division_index"] == division_index],
            "belegstelle_indices": [i for i, item in enumerate(result["belegstellen"])
                                    if item["division_index"] == division_index],
            "parallel_indices": [i for i, item in enumerate(result["lexicographic_parallels"])
                                 if item["division_index"] == division_index],
            "variant_gloss_indices": [i for i, item in enumerate(result["variant_glosses"])
                                      if item["division_index"] == division_index],
            "quoted_non_example_indices": [i for i, item in enumerate(result["quoted_non_examples"])
                                            if item["division_index"] == division_index]})
    validate(article, result)
    return result


def validate(article: dict[str, Any], result: dict[str, Any]) -> None:
    """Check source replay and internal links, not semantic truth of candidates."""
    lines = article["visual_lines"]
    visual = "\n".join(line["text"] for line in lines)
    if (result["article_id"] != article["article_id"] or
            result["source_faithful_sha256"] != article["source_faithful_sha256"]):
        raise ValueError("article source identity mismatch")
    if result["visual_sha256"] != sha256(visual.encode("utf-8")).hexdigest():
        raise ValueError("visual source hash mismatch")
    def check_children(parent: dict[str, Any]) -> None:
        previous_end = parent["visual_start"]
        for child in parent.get("nested_quotes", parent.get("children", [])):
            if (not parent["visual_start"] < child["visual_start"] < child["visual_end"] < parent["visual_end"]
                    or child["visual_start"] < previous_end
                    or visual[child["visual_start"]:child["visual_end"]] != child["text"]
                    or child["source_lines"] != _anchor(lines, _offsets(lines),
                        child["visual_start"], child["visual_end"])["source_lines"]):
                raise ValueError("nested quotation source link mismatch")
            check_children(child)
            previous_end = child["visual_end"]
    for translation in result["translations"]:
        check_children(translation)
    for collection in ("definitions", "tibetan_examples", "belegstellen", "lexicographic_parallels", "variant_glosses",
                       "translations", "citations", "correction_apparatus", "nonprinting_layout_tokens", "quoted_non_examples"):
        for record in result[collection]:
            if collection == "correction_apparatus":
                source_text = record["literal_text"]
                nested = [record["proposal_span"]]
                if "target_span" in record:
                    nested.append(record["target_span"])
            else:
                source_text = record["text"]
                nested = []
            if visual[record["visual_start"]:record["visual_end"]] != source_text:
                raise ValueError(f"{collection} source span does not replay")
            for span in [record, *nested]:
                if not span["source_lines"]:
                    raise ValueError(f"{collection} lacks source lines")
                indices = [source_line["line_index"] for source_line in span["source_lines"]]
                if indices != list(range(indices[0], indices[-1] + 1)):
                    raise ValueError(f"{collection} source lines are not contiguous")
                pieces = []
                for source_line in span["source_lines"]:
                    line = lines[source_line["line_index"]]
                    if (source_line["page_id"] != line["page_id"] or
                            source_line["span_index"] != line["span_index"] or
                            source_line["printed_page"] != line["printed_page"] or
                            source_line["run_start"] != line["run_start"] or
                            source_line["run_end_exclusive"] != line["run_end_exclusive"] or
                            not 0 <= source_line["line_char_start"] <=
                            source_line["line_char_end"] <= len(line["text"])):
                        raise ValueError(f"{collection} source line mismatch")
                    pieces.append(line["text"][source_line["line_char_start"]:
                                               source_line["line_char_end"]])
                if "\n".join(pieces) != visual[span["visual_start"]:span["visual_end"]]:
                    raise ValueError(f"{collection} source-line text does not replay")
            if collection == "correction_apparatus":
                if record["interpretation"] != "printed_apparatus_not_applied":
                    raise ValueError("correction apparatus interpretation changed")
                proposal = record["proposal_span"]
                if visual[proposal["visual_start"]:proposal["visual_end"]] != record["proposed_reading"]:
                    raise ValueError("correction proposal does not replay")
                if "target_span" in record:
                    target = record["target_span"]
                    if visual[target["visual_start"]:target["visual_end"]] != record["target_text"]:
                        raise ValueError("correction target does not replay")
    for index, beleg in enumerate(result["belegstellen"]):
        example = result["tibetan_examples"][beleg["example_index"]]
        translation = result["translations"][beleg["translation_index"]]
        citation = result["citations"][beleg["citation_index"]]
        if not (beleg["visual_start"] == example["visual_start"] and
                beleg["quote_index"] == example["quote_index"] ==
                beleg["translation_index"] and
                example["visual_end"] <= translation["visual_start"] and
                translation["visual_end"] <= citation["visual_start"] and
                citation["visual_end"] == beleg["visual_end"] and
                beleg["division_index"] == example["division_index"] ==
                translation["division_index"] and
                citation["division_index"] in (None, beleg["division_index"])):
            raise ValueError(f"Belegstelle {index} has invalid source order or links")
        expected_corrections = [i for i, correction in enumerate(result["correction_apparatus"])
                                if correction["example_index"] == beleg["example_index"]]
        if beleg["correction_indices"] != expected_corrections:
            raise ValueError(f"Belegstelle {index} correction links mismatch")
    for parallel in result["lexicographic_parallels"]:
        quote = result["translations"][parallel["translation_index"]]
        internal = parallel.get("boundary_kind") == "quote_internal_loc_gloss"
        if internal:
            candidates = article["candidates"]["german_quotes"]
            expected = _quote_internal_lexicon(article, candidates[parallel["quote_index"]],
                parallel["quote_index"], parallel["citation_index"], visual, _offsets(article["visual_lines"]))
            if expected != parallel:
                raise ValueError("quote-internal lexicon source boundaries mismatch")
        if (parallel["quote_index"] != parallel["translation_index"] or
                not ((parallel["visual_start"] == quote["visual_start"] if internal
                      else parallel["visual_start"] < quote["visual_start"])
                     and quote["visual_start"] < quote["visual_end"] <= parallel["visual_end"]) or
                parallel["division_index"] != quote["division_index"]):
            raise ValueError("lexicographic parallel source order mismatch")
        if parallel["citation_index"] is not None:
            citation = result["citations"][parallel["citation_index"]]
            if citation["visual_end"] != parallel["visual_end"]:
                raise ValueError("lexicographic parallel citation mismatch")
    for variant in result["variant_glosses"]:
        quote = result["translations"][variant["translation_index"]]
        if (variant["quote_index"] != variant["translation_index"] or
                not variant["visual_start"] < quote["visual_start"] < quote["visual_end"] == variant["visual_end"] or
                variant["division_index"] != quote["division_index"] or
                result["quote_dispositions"][variant["quote_index"]]["kind"] != "variant_gloss_candidate"):
            raise ValueError("variant gloss source order mismatch")
    if ([item["quote_index"] for item in result["quote_dispositions"]] !=
            list(range(len(result["translations"])))):
        raise ValueError("quote disposition coverage mismatch")
    for definition in result["definitions"]:
        if "quote_index" not in definition:
            continue
        index = definition["quote_index"]
        translation = result["translations"][index]
        if (definition["visual_start"] != translation["visual_start"] or
                definition["visual_end"] != translation["visual_end"] or
                definition["division_index"] != translation["division_index"] or
                result["quote_dispositions"][index]["kind"] != "quoted_definition_candidate"):
            raise ValueError("quoted definition source link mismatch")
    for record in [*result["quoted_non_examples"],
                   *(r for r in result["definitions"] if "review_basis" in r)]:
        quote = result["translations"][record["quote_index"]]
        if (record["text"] != quote["text"] or record["division_index"] != quote["division_index"]
                or record["semantic_role"] not in
                {"definition", "usage_gloss", "etymological_gloss", "scholarly_commentary"}):
            raise ValueError("reviewed quote semantic link mismatch")
        if record["citation_index"] is not None:
            citation = result["citations"][record["citation_index"]]
            if (citation["visual_start"] < quote["visual_end"] or
                    citation["division_index"] not in (None, record["division_index"])):
                raise ValueError("reviewed quote citation link mismatch")
    for index, division in enumerate(result["divisions"]):
        for field, collection in (("definition_indices", "definitions"),
                                  ("example_indices", "tibetan_examples"),
                                  ("belegstelle_indices", "belegstellen"),
                                  ("parallel_indices", "lexicographic_parallels"),
                                  ("variant_gloss_indices", "variant_glosses"),
                                  ("quoted_non_example_indices", "quoted_non_examples")):
            expected = [item for item, record in enumerate(result[collection])
                        if record["division_index"] == index]
            if division[field] != expected:
                raise ValueError("division link mismatch")


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
            for key in ("definitions", "tibetan_examples", "belegstellen",
                        "lexicographic_parallels", "variant_glosses", "quote_dispositions",
                        "translations", "citations", "correction_apparatus",
                        "divisions", "unresolved_quotes", "nonprinting_layout_tokens", "quoted_non_examples"):
                stats[key] += len(row[key])
            stats["anchored_printed_proposals"] += sum(
                item["status"] == "anchored_printed_proposal"
                for item in row["correction_apparatus"])
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
