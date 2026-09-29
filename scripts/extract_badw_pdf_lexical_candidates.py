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
from parse_badw_pdf_articles import VERSION as STRUCTURE_VERSION


VERSION = "badw-pdf-lexical-candidates-v6"
QUALIFIER = re.compile(r"\s*(?:\(metr\.\)\s*)?\Z")
# In generated pages the lemma placeholder can be roman while the surrounding
# LoC example is italic. Admit only this literal, adjacent suffix; do not
# bridge arbitrary regular-font text to a quotation.
PLACEHOLDER_QUALIFIER = re.compile(r"\s*~\s*(?:\(metr\.\)\s*)?\Z")
# A printed correction belongs to the preceding LoC example. Its proposal
# may use italic type, so the final italic run before a quote can be the
# proposal rather than the example. Require the entire intervening source
# span to be exactly one literal correction and an optional metre qualifier.
CORRECTION_BEFORE_QUOTE = re.compile(
    r"(?P<apparatus>\s*\(r\.\s+[^()]+\))\s*(?:\(metr\.\)\s*)?\Z")
LEX_LABEL = re.compile(r"(?:^|[\s;])Lex\.\s")
MORPHOLOGY = re.compile(r"\b(?:pf\.|fut\.|prs\.|imp\.|vgl\.|siehe)\b|[↑↓]")
MORPHOLOGY_PREFIX = re.compile(r"^\s*(?:pf\.|fut\.|prs\.|imp\.)\s+zu\s+[↑↓]")
GLOSS_REFERENCE_SUFFIX = re.compile(r"[,;]\s*vgl\.\s+[↑↓][^\n,;()„“]+\.?\s*$")
REFERENCE_CONTINUATION = re.compile(r"\s*vgl\.\s+[↑↓][^\n;()„“]+\.?\s*\Z")
MORPHOLOGY_PREAMBLE = re.compile(r"\s*(?:pf\.|fut\.|prs\.|imp\.)\s*\Z")
INLINE_ITALIC_INTERRUPTION = re.compile(
    r"(?:\s+\.\.\.\s+|\s*⟨[^<>\n]+⟩\s*|\s*\(r\.\s+[^()]+\)\s*)\Z")
PRINTED_CORRECTION = re.compile(r"\(r\.\s+(?P<proposal>[^()]+?)\)")
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
            sanskrit_continuation = (bool(fragments) and not starts_regular
                and fragments[-1].rstrip().endswith("-")
                and "skt." in "\n".join(fragments)
                and spans[0]["family"] == "TGaramond"
                and spans[0]["style"] == "italic"
                and "„" not in line["text"] and "“" not in line["text"])
            if not starts_regular and not (mixed_continuation or sanskrit_continuation):
                break
            if (division["kind"] == "unsegmented" and i == division["start_line_index"]
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
                segment_start = 0
            prose_end = min((span["start"] for span in spans
                             if span["family"] != "TGaramond"), default=len(line["text"]))
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
            reference_suffix = GLOSS_REFERENCE_SUFFIX.search(part)
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
        "lexicographic_parallels": [], "variant_glosses": [], "quote_dispositions": [],
        "translations": [], "citations": [], "correction_apparatus": [],
        "divisions": [], "unresolved_quotes": []}
    if not lines:
        return result
    result["definitions"] = _definition_candidates(article, text, offsets)
    intervals = _italic_intervals(lines, offsets)
    quotes = article["candidates"]["german_quotes"]
    citations = article["candidates"]["parenthetical_citations"]
    pairs = {pair["quote_index"]: pair["citation_index"]
             for pair in article["candidates"]["adjacent_quote_citation_pairs"]}
    paired = set(pairs)
    for quote in quotes:
        start, end = int(quote["visual_start"]), int(quote["visual_end"])
        result["translations"].append({"text": text[start:end],
            "division_index": quote.get("division_index"),
            "status": "source_quote_candidate", **_anchor(lines, offsets, start, end)})
    for citation in citations:
        start, end = int(citation["visual_start"]), int(citation["visual_end"])
        result["citations"].append({"text": text[start:end],
            "division_index": citation.get("division_index"),
            "status": "unlinked_source_citation_candidate",
            **_anchor(lines, offsets, start, end)})
    for quote_index, quote in enumerate(quotes):
        qstart = int(quote["visual_start"])
        quote_line = int(quote["start_line_index"])
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
            if QUALIFIER.fullmatch(text[effective_end:qstart]):
                eligible.append((interval_index, effective_end))
                continue
            if (PLACEHOLDER_QUALIFIER.fullmatch(text[effective_end:qstart]) and
                    quote_line - interval_line <= 1 and
                    lines[interval_line]["page_id"] == lines[quote_line]["page_id"] and
                    not any(lines[i]["unknown_glyphs"]
                            for i in range(interval_line, quote_line + 1))):
                eligible.append((interval_index, qstart))
                continue
            match = CORRECTION_BEFORE_QUOTE.fullmatch(text[effective_end:qstart])
            if (match and quote_line - interval_line <= 2 and
                    lines[interval_line]["page_id"] == lines[quote_line]["page_id"] and
                    not any(lines[i]["unknown_glyphs"]
                            for i in range(interval_line, quote_line + 1))):
                eligible.append((interval_index, effective_end + match.end("apparatus")))
        if not eligible:
            definition = _opening_quoted_definition(article, quote, quote_index,
                                                    paired, text, offsets)
            if definition is not None:
                result["definitions"].append(definition)
                continue
            result["unresolved_quotes"].append({"quote_index": quote_index,
                "reason": "no_adjacent_italic_loc_span"})
            continue
        index, example_end = eligible[-1]
        start, _, first_line = intervals[index]
        end = example_end
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
        lex = _lexical_region(lines, quote_line, division["start_line_index"])
        # Ellipses, angle-bracket emendations and an explicit '(r. …)'
        # correction can interrupt an otherwise continuous italic LoC span.
        # Admit only those literal source delimiters within the same page
        # and at most one visual-line boundary; retain the interruption.
        for prior_start, prior_end, prior_line in reversed(intervals[:index]):
            if first_line - prior_line > 1:
                break
            if (prior_end > start or lines[prior_line]["page_id"] != lines[first_line]["page_id"]
                    or lines[prior_line]["unknown_glyphs"]
                    or lines[first_line]["unknown_glyphs"]):
                continue
            if INLINE_ITALIC_INTERRUPTION.fullmatch(text[prior_end:start]):
                start, first_line = prior_start, prior_line
                example_text = text[start:end].strip()
        # A newly joined italic span can include leading/trailing source
        # whitespace.  Re-anchor the final candidate, not its pre-join tail.
        joined = text[start:end]
        start += len(joined) - len(joined.lstrip())
        end -= len(joined) - len(joined.rstrip())
        example_text = text[start:end]
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
        cite_index = pairs.get(quote_index)
        if lex:
            parallel_end = int(citations[cite_index]["visual_end"]) if cite_index is not None else int(quote["visual_end"])
            result["lexicographic_parallels"].append({
                "text": text[start:parallel_end], "quote_index": quote_index,
                "translation_index": quote_index, "citation_index": cite_index,
                "division_index": division_index, "loc_text": example_text,
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
    for collection in ("definitions", "tibetan_examples", "belegstellen", "lexicographic_parallels", "variant_glosses",
                       "translations", "citations", "correction_apparatus"):
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
        if (parallel["quote_index"] != parallel["translation_index"] or
                not parallel["visual_start"] < quote["visual_start"] < quote["visual_end"] <= parallel["visual_end"] or
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
    for index, division in enumerate(result["divisions"]):
        for field, collection in (("definition_indices", "definitions"),
                                  ("example_indices", "tibetan_examples"),
                                  ("belegstelle_indices", "belegstellen"),
                                  ("parallel_indices", "lexicographic_parallels"),
                                  ("variant_gloss_indices", "variant_glosses")):
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
                        "divisions", "unresolved_quotes"):
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
