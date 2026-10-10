#!/usr/bin/env python3
"""Conservatively parse positioned BAdW PDF article witnesses.

This is a structural *source* index, not an OCR correction or a final lexical
database.  Source glyphs and article spans are replayed and checked before any
derived visual text is produced.  Typography-supported numbered divisions are
identified; quotations and references remain candidates until their lexical
and bibliographic associations can be established independently.
"""

from __future__ import annotations

import argparse
import csv
from bisect import bisect_right
from collections import Counter
from functools import lru_cache
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterator

from badw_canonical_pages import stable_json_bytes


VERSION = "badw-pdf-structural-parser-v8"
EXTRACTION_VERSION = "badw-source-components-v2"
PREVIOUS_VERSION = "badw-pdf-structural-parser-v6"
# A sense number is a standalone printed label, not the first component of a
# wrapped source locator such as 1.3.34c). Require actual following space.
SENSE_LABEL = re.compile(r"^\s*([1-9][0-9]?)\.(?=\s+\S)")
SIGLUM = re.compile(r"^(?:in\s+)?(?P<siglum>[’']?[\wĀāĪīŪūŚśṢṣṬṭḌḍṄṅÑñ-]{1,24})(?=\s|,|\(|/|$)")
# Reviewed, locatorless source sigla in the frozen PDF-structure benchmark.
# Other locatorless parentheses remain unassociated until source evidence is
# reviewed; this is deliberately not a broad capitalisation heuristic.
LOCATORLESS_SIGLA = frozenset({"Dagy", "TTC", "brDa"})
QUALIFIED_LOCATORLESS_SIGLA = re.compile(r"^brDa,\s*ähnl\.\s*Dagy$")
# Source-shaped citation forms checked against the frozen unresolved queue.
# Do not admit arbitrary parenthetical prose or (r. ...) apparatus here.
REVIEWED_CITATION_FORMS = {
    "Bca Kolophon": "Bca", "Bca Kol.": "Bca", "Pś Kolophon": "Pś",
    "Pś Kolo-\nphon": "Pś", "PT1083 Siegelabdruck": "PT1083",
    "brDa, Dagy": "brDa", "PW": "PW", "SWTF": "SWTF",
    # Exact additional forms verified in the positioned PDF corpus. These
    # are bibliography sigla, not the printed (r. ...) correction apparatus.
    "KanL Kol.": "KanL", "Siddh Kol.": "Siddh",
    "M.I.vi.2a b2": "M.I", "BHSD": "BHSD",
}
EMBEDDED_LOCATOR_SIGLA = re.compile(r"^(?P<siglum>(?:ChFr|Ctr)\d+)$")
REVIEWED_QUESTIONED_SIGLUM = re.compile(r"^Vḍk2\?\s+\d+,\d+$")
REVIEWED_COLON_SIGLUM = re.compile(r"^Vḍk2:\s+\d+,\d+$")


def _parenthetical_spans(text: str) -> Iterator[tuple[int, int, str]]:
    """Yield balanced outer groups; nested source locators remain intact.

    Unbalanced groups are not guessed. A length cap avoids treating an entire
    damaged article as one citation.
    """
    start: int | None = None
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            if depth == 0:
                start = index
            depth += 1
        elif char == ")" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                if index + 1 - start <= 180:
                    yield start, index + 1, text[start + 1:index].strip()
                start = None


def _citation_siglum(interior: str) -> str | None:
    if interior in REVIEWED_CITATION_FORMS:
        return REVIEWED_CITATION_FORMS[interior]
    # PDF wrapping is presentation, not a different citation form. Use a
    # derived lookup string only; candidates retain exact source bounds/text.
    interior = " ".join(interior.split())
    if interior in REVIEWED_CITATION_FORMS:
        return REVIEWED_CITATION_FORMS[interior]
    if REVIEWED_QUESTIONED_SIGLUM.fullmatch(interior):
        return "Vḍk2?"
    if REVIEWED_COLON_SIGLUM.fullmatch(interior):
        return "Vḍk2"
    embedded = EMBEDDED_LOCATOR_SIGLA.fullmatch(interior)
    if embedded:
        return embedded.group("siglum")
    members = [part.strip() for part in interior.split(",")]
    locatorless_group = (len(members) > 1
                         and all(part in LOCATORLESS_SIGLA for part in members))
    if interior in LOCATORLESS_SIGLA or locatorless_group or QUALIFIED_LOCATORLESS_SIGLA.fullmatch(interior):
        match = SIGLUM.match(interior)
        return match.group("siglum") if match else None
    match = SIGLUM.match(interior)
    if not match:
        return None
    siglum = match.group("siglum")
    # This is only a *candidate* citation, but require a source-shaped
    # siglum and a locator outside the siglum.  In particular (r. ...),
    # (zw.), and ordinary parenthetical German are not sources.
    source_shaped = (any(char.isalpha() for char in siglum)
                     and (siglum[0].isupper() or siglum[0].isdigit()
                          or siglum[0] in "’'" or any(c.isupper() for c in siglum[1:])))
    locator = interior[match.end():]
    if not source_shaped or not re.search(r"\d", locator):
        return None
    return siglum


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _font_table(page: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {font["font_id"]: font for font in page["representative_fonts"]}


def _overprints(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Identify a repeated impression, never a different glyph at same position."""
    return (
        first["font_id"] == second["font_id"]
        and first["cid_hex"] == second["cid_hex"]
        and first["unicode"] == second["unicode"]
        and abs(first["font_size"] - second["font_size"]) <= 0.000001
        # Simulated bold also changes advances slightly between impressions;
        # a later punctuation glyph can be displaced farther than its digit.
        # Keep the tolerance sub-glyph-sized and require identical font/CID.
        and abs(first["x"] - second["x"]) <= max(0.04, first["font_size"] * 0.032)
        and abs(first["y"] - second["y"]) <= max(0.04, first["font_size"] * 0.032)
    )


def _visual_glyphs(runs: list[dict[str, Any]], excluded: set[int]) -> tuple[list[dict[str, Any]], int]:
    result: list[dict[str, Any]] = []
    overprints = 0
    for run in runs:
        index = int(run["run_index"])
        if index in excluded:
            continue
        for glyph_index, glyph in enumerate(run["glyphs"]):
            atom = {
                "unicode": glyph["unicode"], "x": float(glyph["x"]), "y": float(glyph["y"]),
                "cid_hex": glyph["cid_hex"], "font_id": run["font_id"],
                "run_index": index, "glyph_index": glyph_index,
                "unknown": bool(glyph["unknown"]),
                "font_size": float(run.get("font_size", 0)),
            }
            # Simulated bold offsets are approximately .027 em, not .027
            # physical points after the text matrix is applied. Match only
            # the same font, size and CID, never spelling. Raw runs remain
            # untouched. Search a small window because one run can contain
            # the next character as well as an overprinted earlier one.
            if any(_overprints(atom, earlier) for earlier in result[-8:]):
                overprints += 1
                continue
            result.append(atom)
    return result, overprints


def _lines(atoms: list[dict[str, Any]], fonts: dict[str, dict[str, Any]],
           span_index: int, source_span: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for atom in atoms:
        if current and abs(atom["y"] - current[-1]["y"]) > 0.08:
            lines.append(_line(current, fonts, span_index, source_span))
            current = []
        current.append(atom)
    if current:
        lines.append(_line(current, fonts, span_index, source_span))
    return lines


def _line(atoms: list[dict[str, Any]], fonts: dict[str, dict[str, Any]],
          span_index: int, source_span: dict[str, Any]) -> dict[str, Any]:
    text = "".join(atom["unicode"] for atom in atoms)
    style_spans: list[dict[str, Any]] = []
    offset = 0
    for atom in atoms:
        font = fonts.get(atom["font_id"], {})
        identity = (atom["font_id"], font.get("family", ""), font.get("style", ""))
        length = len(atom["unicode"])
        if style_spans and tuple(style_spans[-1][key] for key in ("font_id", "family", "style")) == identity:
            style_spans[-1]["end"] += length
            style_spans[-1]["last_run_index"] = atom["run_index"]
            style_spans[-1]["last_glyph_index"] = atom["glyph_index"]
        else:
            style_spans.append({"start": offset, "end": offset + length,
                "font_id": identity[0], "family": identity[1], "style": identity[2],
                "first_run_index": atom["run_index"], "first_glyph_index": atom["glyph_index"],
                "last_run_index": atom["run_index"], "last_glyph_index": atom["glyph_index"]})
        offset += length
    if offset != len(text) or any(not text[span["start"]:span["end"]] for span in style_spans):
        raise AssertionError("visual style spans do not cover line")
    return {
        "text": text,
        "span_index": span_index,
        "page_id": source_span["page_id"],
        "printed_page": source_span["printed_page"],
        "run_start": min(atom["run_index"] for atom in atoms),
        "run_end_exclusive": max(atom["run_index"] for atom in atoms) + 1,
        "first_x": round(atoms[0]["x"], 4),
        "y": round(atoms[0]["y"], 4),
        "unknown_glyphs": sum(atom["unknown"] for atom in atoms),
        "style_spans": style_spans,
        "italic_text": "".join(
            atom["unicode"] for atom in atoms
            if fonts.get(atom["font_id"], {}).get("style") == "italic"
        ),
    }


def _line_ref(line: dict[str, Any]) -> dict[str, Any]:
    return {key: line[key] for key in (
        "span_index", "page_id", "printed_page", "run_start", "run_end_exclusive"
    )}


def _structure(lines: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    divisions: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    current: dict[str, Any] | None = None
    for index, line in enumerate(lines):
        match = SENSE_LABEL.match(line["text"])
        if match:
            # Repeated or out-of-order labels can be substructure, citations,
            # or a layout artefact.  Preserve them without promoting a sense.
            number = int(match.group(1))
            last = next((int(d["label"]) for d in reversed(divisions) if d["kind"] == "numbered_sense"), 0)
            if number == last + 1:
                current = {"kind": "numbered_sense", "label": str(number), "line_indices": [], "confidence": "typographic"}
                divisions.append(current)
                counts["numbered_senses"] += 1
            else:
                counts["unpromoted_number_labels"] += 1
        if current is None:
            if not divisions or divisions[-1]["kind"] != "unsegmented":
                divisions.append({"kind": "unsegmented", "label": "", "line_indices": [], "confidence": "unresolved"})
            current = divisions[-1]
        current["line_indices"].append(index)
    if not divisions and lines:
        raise AssertionError("line partition failed")
    if sum(len(d["line_indices"]) for d in divisions) != len(lines):
        raise AssertionError("division coverage failed")
    for division in divisions:
        indices = division["line_indices"]
        if indices != list(range(indices[0], indices[-1] + 1)):
            raise AssertionError("PDF division is not a contiguous visual-line range")
        selected = [lines[i] for i in indices]
        division["text"] = "\n".join(line["text"] for line in selected)
        division["source_runs"] = [_line_ref(line) for line in selected]
        division["start_line_index"] = indices[0]
        division["end_line_index_exclusive"] = indices[-1] + 1
        del division["line_indices"]
    return divisions, dict(counts)


def quotation_spans(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Balanced literal German quotations, without flattening nested speech.

    Only double low/high quotation marks establish outer boundaries. Single
    low/high marks remain literal within those boundaries, never independent
    translations. Unclosed marks are diagnostics, not guessed quotations.
    An immediately repeated closing mark remains in the literal outer span
    and is diagnosed; this is not source-text repair.
    """
    stack: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "„":
            stack.append({"visual_start": i, "children": []})
        elif char == "“":
            if not stack:
                diagnostics.append({"kind": "unmatched_closing_quote", "visual_start": i,
                                    "visual_end": i + 1})
            else:
                item = stack.pop()
                end = i + 1
                item["diagnostics"] = []
                if not stack and text[end:end + 1] == "“":
                    end += 1
                    i += 1
                    item["diagnostics"].append("repeated_closing_quote")
                item["visual_end"] = end
                item["text"] = text[item["visual_start"] + 1:end - 1]
                if stack:
                    stack[-1]["children"].append(item)
                else:
                    roots.append(item)
        i += 1
    for item in stack:
        diagnostics.append({"kind": "unclosed_opening_quote",
                            "visual_start": item["visual_start"], "visual_end": len(text)})
        # An unclosed outer mark must not hide independently closed later
        # quotations (including subsequent senses). Preserve those literal
        # children, but never invent a closing boundary for their parent.
        roots.extend(item["children"])
    roots.sort(key=lambda item: item["visual_start"])
    return roots, diagnostics


@lru_cache(maxsize=4)
def load_quote_boundary_reviews() -> dict[str, list[dict[str, str]]]:
    path = Path(__file__).resolve().parents[1] / "data/reviewed_badw_pdf_quote_boundaries.tsv"
    result: dict[str, list[dict[str, str]]] = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            result.setdefault(row["article_id"], []).append(row)
    return result


def reviewed_quotation_spans(text: str, article_id: str,
                             reviews: dict[str, list[dict[str, str]]]):
    """Apply exact visible-source boundary reviews without repairing punctuation."""
    quotes, diagnostics = quotation_spans(text)
    for row in reviews.get(article_id, []):
        start, end = int(row["visual_start"]), int(row["visual_end"])
        inner_start, inner_end = int(row["inner_start"]), int(row["inner_end"])
        if (row["visual_sha256"] != sha256(text.encode()).hexdigest()
                or not 0 <= start < inner_start < inner_end < end <= len(text)
                or row["quote_sha256"] != sha256(text[start:end].encode()).hexdigest()
                or text[start] != "„" or text[end - 1] != "“"
                or text[inner_start] != "," or text[inner_end - 1] != "“"):
            raise ValueError("stale or invalid reviewed quotation boundary: " + article_id)
        overlaps = [q for q in quotes if q["visual_start"] < end and start < q["visual_end"]]
        if any(q["visual_start"] < start or q["visual_end"] > end for q in overlaps):
            raise ValueError("reviewed quotation boundary overlaps another quotation")
        quotes = [q for q in quotes if q not in overlaps]
        quotes.append({"visual_start": start, "visual_end": end,
                       "text": text[start + 1:end - 1],
                       "children": [{"visual_start": inner_start, "visual_end": inner_end,
                                     "text": text[inner_start + 1:inner_end - 1],
                                     "children": [], "diagnostics": ["reviewed_literal_comma_opener"]}],
                       "diagnostics": ["exact_source_boundary_review:" + row["basis"]]})
        for diagnostic in diagnostics:
            if start <= diagnostic["visual_start"] < end:
                diagnostic["review_basis"] = row["basis"]
    quotes.sort(key=lambda q: q["visual_start"])
    return quotes, diagnostics


def _candidates(lines: list[dict[str, Any]], divisions: list[dict[str, Any]],
                article_id: str = "") -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {"german_quotes": [], "parenthetical_citations": [],
        "cross_references": [], "adjacent_quote_citation_pairs": [], "quotation_diagnostics": [],
        "sanskrit": [], "unclassified_italic_spans": [], "language_diagnostics": [],
        "transliteration_candidates": [],
        "lexical_blocks": []}
    if not lines:
        return result
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line["text"]) + 1
    text = "\n".join(line["text"] for line in lines)
    division_by_line: dict[int, int] = {}
    for division_index, division in enumerate(divisions):
        for line_index in range(division["start_line_index"], division["end_line_index_exclusive"]):
            if line_index in division_by_line:
                raise AssertionError("PDF division line ranges overlap")
            division_by_line[line_index] = division_index
    if len(division_by_line) != len(lines):
        raise AssertionError("PDF divisions do not cover visual lines")

    def location(start: int, end: int) -> dict[str, Any]:
        first = bisect_right(offsets, start) - 1
        last = bisect_right(offsets, end - 1) - 1
        first_division = division_by_line[first]
        division_index = first_division if division_by_line[last] == first_division else None
        return {"source_line": _line_ref(lines[first]), "source_line_end": _line_ref(lines[last]),
            "start_line_index": first, "end_line_index": last,
            "line_start": start - offsets[first], "line_end": end - offsets[last],
            "visual_start": start, "visual_end": end,
            "division_index": division_index}

    def italic_span_at(position: int) -> tuple[int, int, int, dict[str, Any]] | None:
        if position >= len(text):
            return None
        line_index = bisect_right(offsets, position) - 1
        offset = position - offsets[line_index]
        for span in lines[line_index]["style_spans"]:
            if span["start"] <= offset < span["end"] and span["style"] == "italic":
                return offsets[line_index] + span["start"], offsets[line_index] + span["end"], line_index, span
        return None

    def anchored_quote(item: dict[str, Any]) -> dict[str, Any]:
        return {**item, **location(item["visual_start"], item["visual_end"]),
                "children": [anchored_quote(child) for child in item["children"]]}

    # A typographic field can wrap without acquiring a new language or losing
    # its literal hyphen/newline. Font, page and division continuity are required.
    italic_fields = []
    for line_index, line in enumerate(lines):
        for span in line["style_spans"]:
            if span["style"] != "italic":
                continue
            start, end = offsets[line_index] + span["start"], offsets[line_index] + span["end"]
            previous = italic_fields[-1] if italic_fields else None
            joins = (previous is not None and previous["end_line_index"] + 1 == line_index
                and previous["visual_end"] + 1 == start and span["start"] == 0
                and span.get("font_id") is not None and previous["font_id"] == span["font_id"]
                and lines[previous["end_line_index"]]["page_id"] == line["page_id"]
                and previous["division_index"] == division_by_line[line_index]
                and text[previous["visual_end"] - 1] not in ".;:")
            if joins:
                previous.update(location(previous["visual_start"], end))
                previous["source_text"] = text[previous["visual_start"]:end]
                previous["source_style_spans"].append({"line_index": line_index, **span})
            else:
                italic_fields.append({"source_text": text[start:end], "font_id": span.get("font_id"),
                    "family": span.get("family"), "style": "italic",
                    "source_style_spans": [{"line_index": line_index, **span}],
                    "status": "language_unresolved", **location(start, end)})

    # Retain full source clauses independently of downstream example/quote
    # claims. A partial semantic container must not hide a Lex. tail.
    from badw_source_components import lexical_clauses, quoted_spans
    for division in divisions:
        first, last = division["start_line_index"], division["end_line_index_exclusive"]
        a, b = offsets[first], offsets[last - 1] + len(lines[last - 1]["text"])
        label = re.search(r"\bLex\.\s*", text[a:b])
        if not label:
            continue
        start = a + label.end()
        clauses, diagnostics = lexical_clauses(text, start, b)
        for clause in clauses:
            clause.update(location(clause["start"], clause["end"]))
            clause["german_quotation_candidates"] = quoted_spans(text, clause["start"], clause["end"])
            # Typography is independently recoverable even for ASCII Sanskrit,
            # Tibetan, sigla or Latin names. Retain clipped source fields as
            # clause children without asserting a language or quote ownership.
            clause["typographic_fields"] = []
            for field in italic_fields:
                left = max(clause["start"], field["visual_start"])
                right = min(clause["end"], field["visual_end"])
                if left < right:
                    clause["typographic_fields"].append({
                        **field, **location(left, right), "source_text": text[left:right],
                        "parent_field_visual_start": field["visual_start"],
                        "parent_field_visual_end": field["visual_end"],
                    })
            clause["status"] = "unassociated_source_clause"
        result["lexical_blocks"].append({"source_text": text[a + label.start():b],
            "label_start": a + label.start(), "clauses": clauses,
            "diagnostics": diagnostics, "extent_status": "to_source_division_end",
            **location(a + label.start(), b)})

    # Typography preserves a source span, not its language. Only a literal
    # Sanskrit label licenses a language claim; Tibetan uses the same italics.
    for label in re.finditer(r"\bskt\.\s*", text):
        position = label.end()
        span = italic_span_at(position)
        if span is None:
            result["language_diagnostics"].append({
                "reason": "Sanskrit label without italic source field",
                **location(label.start(), label.end())})
            continue
        field = next(item for item in italic_fields
                     if item["visual_start"] <= position < item["visual_end"])
        end = field["visual_end"]
        while end > position and text[end - 1].isspace():
            end -= 1
        if position < end:
            result["sanskrit"].append({"source_text": text[position:end],
                "label_start": label.start(), "label_end": label.end(),
                "evidence": "literal skt. label and italic field boundary",
                "status": "source_language_field", **location(position, end)})
    for field in italic_fields:
        if not any(item["visual_start"] == field["visual_start"]
                   and item["visual_end"] <= field["visual_end"] for item in result["sanskrit"]):
            result["unclassified_italic_spans"].append(field)
    # Diacritics are a discovery signal, not proof of Sanskrit. This also
    # surfaces names embedded in German prose (e.g. Viṣṇus), without turning
    # inflected names or shared Tibetan typography into language assertions.
    for token in re.finditer(r"[^\W\d_]+(?:-\n[^\W\d_]+)*", text, re.UNICODE):
        if not re.search(r"[āīūṛṝḷḹṭḍṇṣḥṃ]", token.group()):
            continue
        if any(item["visual_start"] <= token.start() < token.end() <= item["visual_end"]
               for item in result["sanskrit"]):
            continue
        result["transliteration_candidates"].append({"source_text": token.group(),
            "status": "language_unresolved", "evidence": "transliteration diacritic; not a language claim",
            **location(token.start(), token.end())})

    quotes, quote_diagnostics = reviewed_quotation_spans(text, article_id, load_quote_boundary_reviews())
    result["quotation_diagnostics"] = quote_diagnostics
    for item in quotes:
        result["german_quotes"].append({**anchored_quote(item),
                                        "status": "unassociated_candidate"})
    for start, end, interior in _parenthetical_spans(text):
        siglum = _citation_siglum(interior)
        if siglum is not None:
            result["parenthetical_citations"].append({"text": text[start:end],
                "siglum_candidate": siglum, **location(start, end),
                "status": "unassociated_candidate"})
    for marker in re.finditer(r"[↑↓]", text):
        start = marker.start()
        target_start = marker.end()
        # A separately positioned homonym numeral may sit on its own visual
        # line between the arrow and the italic headword (e.g. ↓\n1\n’chos).
        interlude = re.match(r"\s*(?:[1-9][0-9]?\s*)?", text[target_start:])
        if interlude:
            target_start += interlude.end()
        italic = italic_span_at(target_start)
        if italic and (italic[0] == target_start or italic[0] <= start):
            end = italic[1]
            line_index, last_span = italic[2], italic[3]
            # A reference may wrap at the visual line boundary.  Continue
            # only through an immediately following italic span in the same
            # font, source page, and division; never infer from plain text.
            while (end == offsets[line_index] + len(lines[line_index]["text"])
                    and text[end - 1] not in ".;:"
                    and line_index + 1 < len(lines)
                    and end - start < 80):
                next_line = lines[line_index + 1]
                first_span = next_line["style_spans"][0]
                if (first_span["start"] != 0 or first_span["style"] != "italic"
                        or first_span["font_id"] != last_span["font_id"]
                        or next_line["page_id"] != lines[line_index]["page_id"]
                        or division_by_line[line_index + 1] != division_by_line[line_index]):
                    break
                line_index += 1
                last_span = first_span
                end = offsets[line_index] + first_span["end"]
            while end > target_start and text[end - 1] in " \t\n.,;:":
                end -= 1
        else:
            # Some source runs have no useful italic boundary.  Retain the
            # older, conservative one-token candidate in that case, but do
            # not infer a multiword target from unstyled prose.
            fallback = re.match(r"[^\s;,.()„“]{1,80}", text[target_start:])
            if not fallback:
                continue
            end = target_start + fallback.end()
        # A shared italic run can contain consecutive references. Typography
        # is not permission to absorb the next literal direction marker.
        next_marker = re.search(r"[↑↓]", text[target_start:end])
        if next_marker is not None:
            end = target_start + next_marker.start()
            while end > target_start and text[end - 1].isspace():
                end -= 1
        if end == target_start or end - start > 80:
            continue
        targets = [{"source_text": text[marker.end():end],
                    **location(marker.end(), end)}]
        # A comma-separated source list can carry a second printed homonym
        # and target without repeating the arrow. Require the original
        # target's italic font plus exact page/division continuity; plain
        # prose and differently styled text cannot extend this candidate.
        if italic:
            while end - start < 80:
                separator = re.match(r",\s*(?:[1-9]\d*\s*)?", text[end:])
                if separator is None:
                    break
                next_start = end + separator.end()
                following = italic_span_at(next_start)
                if (following is None or following[0] != next_start
                        or following[3]["font_id"] != italic[3]["font_id"]
                        or lines[following[2]]["page_id"] != lines[italic[2]]["page_id"]
                        or division_by_line[following[2]] != division_by_line[italic[2]]):
                    break
                next_end = following[1]
                while next_end > next_start and text[next_end - 1] in " \t\n.,;:":
                    next_end -= 1
                if next_end <= next_start or next_end - start > 80:
                    break
                label_start = end + 1
                while label_start < next_start and text[label_start].isspace():
                    label_start += 1
                targets.append({"source_text": text[label_start:next_end],
                                **location(label_start, next_end)})
                end = next_end
        result["cross_references"].append({"marker": text[start],
            "target_label_candidate": text[marker.end():end], **location(start, end),
            "target_candidates": targets,
            "status": "unresolved_candidate"})
    citations = result["parenthetical_citations"]
    for quote_index, quote in enumerate(result["german_quotes"]):
        following = [index for index, citation in enumerate(citations)
                     if citation["visual_start"] >= quote["visual_end"]]
        if not following:
            continue
        citation_index = following[0]
        citation = citations[citation_index]
        between = text[quote["visual_end"]:citation["visual_start"]]
        # This records typographic adjacency, not a resolved Belegstelle or
        # bibliographic authority.  Do not bridge another quote or prose.
        if (quote["division_index"] is not None
                and quote["division_index"] == citation["division_index"]
                and not between.strip()):
            result["adjacent_quote_citation_pairs"].append({
                "quote_index": quote_index, "citation_index": citation_index,
                "division_index": quote["division_index"],
                "status": "typographic_candidate",
            })
    return result


def parse_article(article: dict[str, Any], load_page: Any) -> dict[str, Any]:
    if article.get("contract_version") != "badw-pdf-article-witness-v1":
        raise ValueError("unsupported PDF article witness contract")
    lines: list[dict[str, Any]] = []
    overprints = 0
    source_objects: list[dict[str, Any]] = []
    replayed_source: list[str] = []
    for span_index, span in enumerate(article["source_spans"]):
        page = load_page(span["canonical_object"])
        if page["page_id"] != span["page_id"] or page["visible_body_sha256"] != span["visible_body_sha256"]:
            raise ValueError(f"page identity mismatch: {span['page_id']}")
        runs = page["positioned_page"]["positioned_text_runs"]
        start, end = int(span["run_start"]), int(span["run_end_exclusive"])
        if not 0 <= start < end <= len(runs):
            raise ValueError("source run range outside canonical page")
        selected = runs[start:end]
        if any("".join(glyph["unicode"] for glyph in run["glyphs"]) != run["decoded_unicode"]
               for run in selected):
            raise ValueError(f"glyph/run Unicode mismatch: {span['page_id']}")
        source_text = "".join(run["decoded_unicode"] for run in selected)
        if source_text != span["source_faithful_text"] or _hash_text(source_text) != span["source_text_sha256"]:
            raise ValueError(f"source text mismatch: {span['page_id']}")
        replayed_source.append(source_text)
        if any(int(run["run_index"]) != start + offset for offset, run in enumerate(selected)):
            raise ValueError("nonsequential positioned runs")
        excluded: set[int] = set()
        if span_index == 0:
            heading = article["entry_start_source_span"]
            for key in ("tibetan_run_indices", "loc_run_indices", "homonym_run_indices"):
                excluded.update(int(value) for value in heading[key])
            if not excluded.issubset(set(range(start, end))):
                raise ValueError("heading runs outside first source span")
        atoms, repeats = _visual_glyphs(selected, excluded)
        overprints += repeats
        lines.extend(_lines(atoms, _font_table(page), span_index, span))
        source_objects.append({"page_id": span["page_id"], "canonical_object": span["canonical_object"],
            "canonical_object_sha256": page.get("_canonical_object_sha256"),
            "pdf_url": span["representative_pdf_url"], "pdf_sha256": span["representative_pdf_sha256"],
            "source_text_sha256": span["source_text_sha256"], "run_start": start, "run_end_exclusive": end})
    if "".join(replayed_source) != article["source_faithful_text"]:
        raise ValueError(f"article source text mismatch: {article['id']}")
    divisions, diagnostics = _structure(lines)
    for index, line in enumerate(lines):
        line["line_index"] = index
    candidates = _candidates(lines, divisions, article["id"])
    diagnostics["visual_overprint_impressions_removed"] = overprints
    diagnostics["line_count"] = len(lines)
    diagnostics["unknown_glyphs"] = sum(line["unknown_glyphs"] for line in lines)
    diagnostics.update({key: len(value) for key, value in candidates.items()})
    return {
        "contract_version": VERSION, "extraction_version": EXTRACTION_VERSION,
        "article_id": article["id"], "volume": article["volume"],
        "loc_headword": article["loc_headword"], "tibetan_headword": article["tibetan_headword"],
        "homonym": article["homonym"], "ending_status": article["ending_status"],
        "source_objects": source_objects, "source_faithful_sha256": _hash_text(article["source_faithful_text"]),
        "source_faithful_text": article["source_faithful_text"],
        "visual_lines": lines, "divisions": divisions, "candidates": candidates,
        "diagnostics": diagnostics,
    }


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reindex_article(article: dict[str, Any]) -> dict[str, Any]:
    """Rebuild only derived divisions/candidates from an audited cached row.

    This offline path never reloads a PDF and never changes source/visual text.
    """
    if article.get("contract_version") not in (PREVIOUS_VERSION, "badw-pdf-structural-parser-v7", VERSION):
        raise ValueError("unsupported source structure contract for reindex")
    lines = article["visual_lines"]
    if [line["line_index"] for line in lines] != list(range(len(lines))):
        raise ValueError("nonsequential visual lines")
    if _hash_text(article["source_faithful_text"]) != article["source_faithful_sha256"]:
        raise ValueError("source-faithful text hash mismatch")
    divisions, diagnostics = _structure(lines)
    candidates = _candidates(lines, divisions, article["article_id"])
    diagnostics.update({key: article["diagnostics"][key] for key in
        ("visual_overprint_impressions_removed", "line_count", "unknown_glyphs")})
    diagnostics.update({key: len(value) for key, value in candidates.items()})
    if diagnostics["line_count"] != len(lines) or diagnostics["unknown_glyphs"] != sum(
            line["unknown_glyphs"] for line in lines):
        raise ValueError("visual-line diagnostics mismatch")
    return {**article, "contract_version": VERSION, "extraction_version": EXTRACTION_VERSION,
            "divisions": divisions,
            "candidates": candidates, "diagnostics": diagnostics}


def reindex_corpus(source: Path, output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite output: {output_root}")
    output_root.mkdir(parents=True)
    output = output_root / "pdf_article_structure.jsonl.gz"
    counts: Counter[str] = Counter()
    logical = sha256()
    with gzip.open(source, "rt", encoding="utf-8") as rows, output.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as sink:
            for row in rows:
                parsed = reindex_article(json.loads(row))
                encoded = stable_json_bytes(parsed) + b"\n"
                sink.write(encoded)
                logical.update(encoded)
                counts["articles"] += 1
                counts[f"volume_{parsed['volume']}"] += 1
                counts["divisions"] += len(parsed["divisions"])
                for key, value in parsed["diagnostics"].items():
                    counts[key] += value
    summary = {"contract_version": VERSION, "reindexed_from_sha256": _file_hash(source),
        "logical_output_sha256": logical.hexdigest(), "compressed_output_sha256": _file_hash(output),
        "counts": dict(sorted(counts.items()))}
    (output_root / "summary.json").write_bytes(stable_json_bytes(summary) + b"\n")
    return summary


def build(witnesses: Path, canonical_roots: Path | list[Path], output_root: Path) -> dict[str, Any]:
    if isinstance(canonical_roots, Path):
        canonical_roots = [canonical_roots]
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite output: {output_root}")
    output_root.mkdir(parents=True)
    @lru_cache(maxsize=8)
    def load_page(relative: str) -> dict[str, Any]:
        paths = [root / relative for root in canonical_roots if (root / relative).is_file()]
        if not paths:
            raise FileNotFoundError(f"canonical page absent from all roots: {relative}")
        # The canonical index may have been copied without every object.  A
        # later root may supply it, but conflicting objects must not be
        # silently selected by command-line order.
        bodies = [path.read_bytes() for path in paths]
        if any(body != bodies[0] for body in bodies[1:]):
            raise ValueError(f"conflicting canonical page objects: {relative}")
        page = json.loads(gzip.decompress(bodies[0]))
        page["_canonical_object_sha256"] = sha256(bodies[0]).hexdigest()
        return page
    stats: Counter[str] = Counter()
    logical = sha256()
    output = output_root / "pdf_article_structure.jsonl.gz"
    with gzip.open(witnesses, "rt", encoding="utf-8") as source, output.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as target:
            for row in source:
                article = json.loads(row)
                parsed = parse_article(article, load_page)
                encoded = stable_json_bytes(parsed) + b"\n"
                target.write(encoded)
                logical.update(encoded)
                stats["articles"] += 1
                stats[f"volume_{parsed['volume']}"] += 1
                stats["divisions"] += len(parsed["divisions"])
                for key, value in parsed["diagnostics"].items():
                    stats[key] += value
                if any(d["kind"] == "numbered_sense" for d in parsed["divisions"]):
                    stats["articles_with_numbered_senses"] += 1
                if any(d["kind"] == "unsegmented" for d in parsed["divisions"]):
                    stats["articles_with_unsegmented_text"] += 1
    summary = {"contract_version": VERSION, "witnesses_sha256": _file_hash(witnesses),
        "logical_output_sha256": logical.hexdigest(), "compressed_output_sha256": _file_hash(output),
        "counts": dict(sorted(stats.items()))}
    (output_root / "summary.json").write_bytes(stable_json_bytes(summary) + b"\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--witnesses", type=Path)
    source.add_argument("--reindex-structure", type=Path)
    parser.add_argument("--canonical-root", type=Path, action="append",
                        help="repeat for compatible historical canonical page-object roots")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.reindex_structure:
        if args.canonical_root:
            parser.error("--canonical-root is not used when reindexing")
        summary = reindex_corpus(args.reindex_structure, args.output_root)
    else:
        if not args.canonical_root:
            parser.error("--canonical-root is required with --witnesses")
        summary = build(args.witnesses, args.canonical_root, args.output_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
