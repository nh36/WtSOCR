#!/usr/bin/env python3
"""Parse cached BAdW database-article HTML into auditable JSON records."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence
from urllib.parse import unquote, urljoin, urlsplit

from badw_catalogue import CatalogueRecord, read_catalogue
from badw_html import (
    Element,
    TextNode,
    compact_text,
    decode_html_bytes,
    dom_path,
    element_locator,
    exact_text,
    find_all,
    find_first,
    iter_text_nodes,
    parse_html,
)
from badw_source_cache import RequestSpec, SourceCache, quote_iri


ARTICLE_CONTRACT_VERSION = "badw-database-article-v4"
HIDDEN_CLASSES = ("infotext",)
HIDDEN_TAGS = ("script", "style", "input")


class ArticleParseError(ValueError):
    """Raised when a cached response is not a valid database article."""


def _is_visible_text_node(node: TextNode, article: Element) -> bool:
    current = node.parent
    while current is not None:
        if current.tag in HIDDEN_TAGS or current.classes.intersection(HIDDEN_CLASSES):
            return False
        if current is article:
            return True
        current = current.parent
    return False


def _build_text_audit(article: Element) -> tuple[str, str, list[dict[str, object]]]:
    visible_parts = []
    full_parts = []
    fragments = []
    visible_offset = 0
    full_offset = 0
    for node in iter_text_nodes(article):
        visible = _is_visible_text_node(node, article)
        full_start = full_offset
        full_offset += len(node.text)
        full_parts.append(node.text)
        if visible:
            visible_start: int | None = visible_offset
            visible_offset += len(node.text)
            visible_end: int | None = visible_offset
            visible_parts.append(node.text)
        else:
            visible_start = None
            visible_end = None
        fragments.append(
            {
                "dom_path": dom_path(node),
                "dom_text_end": full_offset,
                "dom_text_start": full_start,
                "source_column": node.column,
                "source_line": node.line,
                "source_text": node.text,
                "visible": visible,
                "visible_text_end": visible_end,
                "visible_text_start": visible_start,
            }
        )
    return "".join(visible_parts), "".join(full_parts), fragments


def _span_for_element(
    element: Element, fragments: Sequence[Mapping[str, object]]
) -> tuple[int | None, int | None]:
    prefix = dom_path(element) + "/"
    offsets = [
        (fragment["visible_text_start"], fragment["visible_text_end"])
        for fragment in fragments
        if str(fragment["dom_path"]).startswith(prefix)
        and fragment["visible_text_start"] is not None
    ]
    if not offsets:
        return None, None
    return int(offsets[0][0]), int(offsets[-1][1])


def _dom_span_for_element(
    element: Element, fragments: Sequence[Mapping[str, object]]
) -> tuple[int | None, int | None]:
    prefix = dom_path(element) + "/"
    offsets = [
        (fragment["dom_text_start"], fragment["dom_text_end"])
        for fragment in fragments
        if str(fragment["dom_path"]).startswith(prefix)
    ]
    if not offsets:
        return None, None
    return int(offsets[0][0]), int(offsets[-1][1])


def _tooltip_display_text(element: Element) -> str:
    """Tooltip content without *nested* explanatory/UI tooltip expansions."""

    parts = []
    for child in element.children:
        if isinstance(child, TextNode):
            parts.append(child.text)
        else:
            parts.append(
                exact_text(child, excluded_classes=HIDDEN_CLASSES, excluded_tags=HIDDEN_TAGS)
            )
    return "".join(parts)


def _located_field(
    element: Element | None, fragments: Sequence[Mapping[str, object]]
) -> dict[str, object] | None:
    if element is None:
        return None
    source_text = exact_text(
        element, excluded_classes=HIDDEN_CLASSES, excluded_tags=HIDDEN_TAGS
    )
    start, end = _span_for_element(element, fragments)
    locator = element_locator(element)
    locator["visible_text_start"] = start
    locator["visible_text_end"] = end
    return {
        "locator": locator,
        "source_text": source_text,
        "text": compact_text(source_text),
    }


def _field_envelope(fields, source_text):
    """Keep all explicitly tagged segments, including literal intervening text.

    The derived envelope is auditable but does not assert the language of its
    untagged gaps. Individual tagged segments are always retained separately.
    """
    if not fields:
        return None
    start = min(f["locator"]["visible_text_start"] for f in fields)
    end = max(f["locator"]["visible_text_end"] for f in fields)
    value = source_text[start:end]
    gaps, cursor = [], start
    for field in sorted(fields, key=lambda f: f["locator"]["visible_text_start"]):
        a, b = field["locator"]["visible_text_start"], field["locator"]["visible_text_end"]
        if cursor < a:
            gaps.append({"source_text": source_text[cursor:a],
                         "locator": {"visible_text_start": cursor, "visible_text_end": a},
                         "status": "untagged_language_unresolved"})
        cursor = max(cursor, b)
    return {"locator": {"visible_text_start": start, "visible_text_end": end,
                        "derivation": "tagged_segment_envelope"},
            "source_text": value, "text": compact_text(value), "untagged_gaps": gaps}


def _path_identity(url: str) -> tuple[str, str]:
    parts = [unquote(part) for part in urlsplit(url).path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"lemma", "pdf"}:
        return parts[1], parts[2] if len(parts) >= 3 else ""
    return "", ""


def _intersect_field(field, start, end, source_text):
    """Intersect source containment without losing the original DOM locator."""
    locator = field["locator"]
    left = max(start, locator["visible_text_start"])
    right = min(end, locator["visible_text_end"])
    if left >= right:
        return None
    if (left, right) == (locator["visible_text_start"], locator["visible_text_end"]):
        return field
    value = source_text[left:right]
    return {**field, "source_text": value, "text": compact_text(value),
            "parent_source_locator": dict(locator),
            "locator": {**locator, "visible_text_start": left, "visible_text_end": right,
                        "derivation": "source_clause_intersection"}}


def _children_after_until_meaning(meaning: Element) -> list[Element]:
    if meaning.parent is None:
        return []
    siblings = [child for child in meaning.parent.children if isinstance(child, Element)]
    try:
        start = siblings.index(meaning) + 1
    except ValueError:
        return []
    following = []
    for sibling in siblings[start:]:
        if "bedeutung" in sibling.classes:
            break
        following.append(sibling)
    return following


def _records_for_elements(
    elements: Iterable[Element], fragments: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    return [
        field
        for element in elements
        if (field := _located_field(element, fragments)) is not None
        and field["source_text"]
        and field["locator"]["visible_text_start"] is not None
    ]


def parse_database_article(
    body: bytes,
    *,
    source_metadata: Mapping[str, object],
) -> dict[str, object]:
    """Parse one exact cached object into a deterministic article record."""

    expected_sha = str(source_metadata.get("sha256") or "")
    actual_sha = hashlib.sha256(body).hexdigest()
    if expected_sha and actual_sha != expected_sha:
        raise ArticleParseError("cached object SHA-256 does not match its manifest")
    if source_metadata.get("delivery_type") != "database_article":
        raise ArticleParseError("cached response is not classified as a database article")
    if not source_metadata.get("valid_resource"):
        raise ArticleParseError(
            f"invalid cached article: {source_metadata.get('content_classification')}"
        )

    headers = source_metadata.get("response_headers")
    header_mapping = headers if isinstance(headers, Mapping) else {}
    html, encoding, used_replacement_characters = decode_html_bytes(body, header_mapping)
    root = parse_html(html)
    article = find_first(root, tag="div", class_name="text")
    if article is None:
        raise ArticleParseError("database article has no div.text container")
    article_source_text, dom_full_text, fragments = _build_text_audit(article)

    lemma_element = find_first(article, tag="span", class_name="lem")
    tibetan_element = find_first(article, tag="span", class_name="lemtib")
    lemma_field = _located_field(lemma_element, fragments)
    tibetan_field = _located_field(tibetan_element, fragments)
    final_url = str(source_metadata.get("final_url") or source_metadata.get("requested_url"))
    path_lemma, path_homonym = _path_identity(final_url)
    # Superscripts in definitions and examples also encode exponents and
    # cross-reference homonyms.  Only the lemma heading can supply this one's
    # homonym; otherwise the stable article URL is authoritative.
    lemma_heading = find_first(article, tag="span", class_name="lemma")
    sup = find_first(lemma_heading, tag="sup") if lemma_heading is not None else None
    homonym = compact_text(exact_text(sup)) if sup is not None else path_homonym
    lemma = str(lemma_field["text"]) if lemma_field else path_lemma

    meaning_nodes = find_all(article, tag="div", class_name="bedeutung")
    meanings = []
    for element in meaning_nodes:
        field = _located_field(element, fragments)
        number_element = find_first(element, class_name="bedeutungsnummer")
        number = (
            compact_text(exact_text(number_element)).rstrip(".")
            if number_element is not None
            else ""
        )
        meanings.append({"number": number, **(field or {})})

    example_nodes = find_all(article, class_name="beleg-all")
    examples = []
    for element in example_nodes:
        field = _located_field(element, fragments) or {}
        # A Tibetan example can contain multiple <tib> segments separated by
        # apparatus or literal text. The container, not its first child, is
        # the authoritative complete field. Keep the segments independently.
        tibetan = find_first(element, class_name="tibetisch")
        tibetan_segments = _records_for_elements(find_all(element, tag="tib"), fragments)
        translation = find_first(element, class_name="deutsch")
        location = find_first(element, class_name="stellenangabe")
        example_sigla = find_all(element, class_name="textsiglum")
        examples.append(
            {
                **field,
                "citation": _located_field(
                    find_first(element, class_name="stelle"), fragments
                ),
                "citation_sigla": _records_for_elements(example_sigla, fragments),
                "location": _located_field(location, fragments),
                "tibetan": (_located_field(tibetan, fragments) if tibetan is not None
                            else _field_envelope(tibetan_segments, article_source_text)),
                "tibetan_segments": tibetan_segments,
                # The legacy segment list covers the whole example, including
                # Tibetan quoted inside German. Expose exact DOM containment
                # separately; do not infer semantic ownership from language.
                "tibetan_container_segments": _records_for_elements(
                    find_all(tibetan, tag="tib") if tibetan is not None else [], fragments),
                "translation_tibetan_segments": _records_for_elements(
                    find_all(translation, tag="tib") if translation is not None else [], fragments),
                "translation_sanskrit": _records_for_elements(
                    find_all(translation, tag="skt") if translation is not None else [], fragments),
                # A .tibetisch container can include explicitly tagged Sanskrit
                # equivalences. Its full text is not a homogeneous language
                # assertion: retain both the container and its tagged children.
                "sanskrit": _records_for_elements(find_all(element, tag="skt"), fragments),
                "tibetan_container_languages": sorted(
                    {language for tag, language in (("tib", "tibetan"), ("skt", "sanskrit"))
                     if tibetan is not None and find_all(tibetan, tag=tag)}),
                "translation": _located_field(translation, fragments),
            }
        )

    from badw_source_components import siglum_parentheses, comparison_reference_candidates, author_year_reference_candidates
    tagged_sigla = _records_for_elements(find_all(article, class_name="textsiglum"), fragments)
    siglum_spans = [(f["locator"]["visible_text_start"], f["locator"]["visible_text_end"])
                   for f in tagged_sigla if f["locator"]["visible_text_start"] is not None]
    marked_citations = siglum_parentheses(article_source_text, 0, len(article_source_text), siglum_spans)
    marked_citations.extend(comparison_reference_candidates(article_source_text, 0, len(article_source_text)))
    # An explicit visible bibliography tag followed by a numeric locator is
    # citation evidence even outside parentheses. Tooltip expansions remain
    # excluded. This records the citation, never ownership of nearby prose.
    for field in _records_for_elements(find_all(article, class_name="bibl"), fragments):
        a, b = field["locator"]["visible_text_start"], field["locator"]["visible_text_end"]
        if a is None or b is None:
            continue
        suffix = re.match(r":\s*\d+(?:[a-z])?(?:\s*[–-]\s*\d+(?:[a-z])?)?(?:\s+ff?\.)?", article_source_text[b:])
        if suffix:
            end = b + suffix.end()
            # Reuse the complete author/year locator grammar. DOM priority
            # must not truncate a following Nr./Anm. locator that the same
            # source occurrence supplies. The tag is evidence, not an end
            # boundary for the citation.
            complete = [c for c in author_year_reference_candidates(
                article_source_text, a, len(article_source_text))
                if c["start"] == a and c["end"] >= end]
            if complete:
                end = max(c["end"] for c in complete)
            marked_citations.append(dict(start=a, end=end, source_text=article_source_text[a:end],
                status="unresolved_source_citation_candidate",
                evidence="explicit visible DOM bibl tag followed by numeric locator"))
    # Prefer explicit DOM evidence when the same span is also recognized by
    # the untagged author/year grammar.
    marked_citations.extend(author_year_reference_candidates(article_source_text, 0, len(article_source_text)))
    # Untagged source expressions in definitions and Lex. blocks remain candidates,
    # not authority resolutions or ownership assertions. Reuse the bounded
    # source grammar; prose, corrections and quoted parentheses fail closed.
    from badw_source_components import terminal_lexical_citation, located_parenthetical_citations
    citation_containers = (find_all(article, class_name="bedeutung")
                           + find_all(article, tag="div", class_name="lex"))
    for element in citation_containers:
        field = _located_field(element, fragments)
        a, b = field["locator"]["visible_text_start"], field["locator"]["visible_text_end"]
        if a is not None and b is not None:
            candidates = located_parenthetical_citations(article_source_text, a, b)
            terminal = terminal_lexical_citation(article_source_text, a, b)
            if terminal:
                candidates.append(terminal)
            for candidate in candidates:
                if not any(c["start"] == candidate["start"] and c["end"] == candidate["end"] for c in marked_citations):
                    marked_citations.append(candidate)
    # A translation can explicitly interrupt its quotation with an editorial
    # [vgl. title (source locator)] note. Recover only that marked apparatus;
    # ordinary parentheses inside quoted speech are not citation evidence.
    for element in example_nodes:
        translation = find_first(element, class_name="deutsch")
        field = _located_field(translation, fragments)
        if not field:
            continue
        a, b = field["locator"]["visible_text_start"], field["locator"]["visible_text_end"]
        if a is None or b is None:
            continue
        for candidate in located_parenthetical_citations(article_source_text, a, b):
            if not candidate["evidence"].startswith("bracketed explicit vgl."):
                continue
            if not any(c["start"] == candidate["start"] and c["end"] == candidate["end"]
                       for c in marked_citations):
                marked_citations.append(candidate)
    explicit_citations = _records_for_elements(find_all(article, class_name="stelle"), fragments)
    bibliography_candidates = [c for c in marked_citations
                               if c["evidence"].startswith("explicit visible DOM bibl")]
    citation_candidate_diagnostics = []
    retained_candidates = []
    for candidate in marked_citations:
        a, b = candidate["start"], candidate["end"]
        overlaps = [f for f in explicit_citations
                    if f["locator"]["visible_text_start"] is not None
                    and a < f["locator"]["visible_text_end"]
                    and f["locator"]["visible_text_start"] < b]
        bibliography_overlaps = [c for c in bibliography_candidates
                                 if c is not candidate and a < c["end"] and c["start"] < b
                                 and not candidate["evidence"].startswith("explicit visible DOM bibl")]
        if overlaps or bibliography_overlaps:
            # A generic parenthesis may also contain a Tibetan s.v. target.
            # Keep that envelope for audit, not as a second, broader citation.
            citation_candidate_diagnostics.append({**candidate,
                "diagnosis": "overlaps_explicit_dom_citation",
                "explicit_citation_locators": [f["locator"] for f in overlaps],
                "explicit_bibliography_spans": [dict(start=c["start"], end=c["end"])
                                                for c in bibliography_overlaps]})
        else:
            retained_candidates.append(candidate)
    marked_citations = retained_candidates
    lexical_nodes = find_all(article, tag="div", class_name="lex")
    lexical_blocks = []
    for element in lexical_nodes:
        block = {
            **(_located_field(element, fragments) or {}),
            "tibetan_segments": _records_for_elements(find_all(element, tag="tib"), fragments),
            "sanskrit": _records_for_elements(find_all(element, tag="skt"), fragments),
            "translations": _records_for_elements(find_all(element, class_name="deutsch"), fragments),
            "citations": _records_for_elements(find_all(element, class_name="stelle"), fragments),
            "sigla": _records_for_elements(find_all(element, class_name="textsiglum"), fragments),
        }
        from badw_source_components import lexical_clauses, quoted_spans, terminal_lexical_citation
        a, b = block["locator"]["visible_text_start"], block["locator"]["visible_text_end"]
        if a is not None and b is not None:
            # The label is not part of a lexical parallel, but remains in the
            # full block and original source. Never strip punctuation internally.
            label = re.match(r"\s*Lex\.\s*", article_source_text[a:b])
            clauses, diagnostics = lexical_clauses(article_source_text, a + (label.end() if label else 0), b)
            for clause in clauses:
                clause["tagged_fields"] = {
                    name: [intersection for f in block[name]
                           if (intersection := _intersect_field(
                               f, clause["start"], clause["end"], article_source_text)) is not None]
                    for name in ("tibetan_segments", "sanskrit", "translations", "citations", "sigla")}
                clause["german_quotation_candidates"] = quoted_spans(article_source_text, clause["start"], clause["end"])
                citation = terminal_lexical_citation(article_source_text, clause["start"], clause["end"])
                marked = [c for c in marked_citations if clause["start"] <= c["start"] < c["end"] <= clause["end"]]
                explicit = [f for f in explicit_citations
                            if f["locator"]["visible_text_start"] is not None
                            and clause["start"] <= f["locator"]["visible_text_start"]
                            and f["locator"]["visible_text_end"] <= clause["end"]]
                clause["terminal_citation_candidates"] = marked or ([citation] if citation and not explicit else [])
            block["clauses"] = clauses
            block["delimiter_diagnostics"] = diagnostics
        lexical_blocks.append(block)
    sanskrit = _records_for_elements(find_all(article, tag="skt"), fragments)
    citations = list(explicit_citations)
    for candidate in marked_citations:
        a, b = candidate["start"], candidate["end"]
        if any(f["locator"]["visible_text_start"] <= a and b <= f["locator"]["visible_text_end"]
               for f in citations if f["locator"]["visible_text_start"] is not None):
            continue
        citations.append({"locator": {"visible_text_start": a, "visible_text_end": b,
                         "derivation": ("explicit_bibliography_locator_candidate"
                             if candidate["evidence"].startswith("explicit visible DOM bibl")
                             else "explicit_comparison_reference_candidate"
                             if candidate["evidence"].startswith("explicit vgl.")
                             else "source_author_year_locator_candidate"
                             if candidate["evidence"].startswith("capitalized author year")
                             else "source_parenthesis_candidate")},
                         "source_text": article_source_text[a:b], "text": compact_text(article_source_text[a:b]),
                         "candidate_status": candidate["status"], "evidence": candidate["evidence"]})

    sigla = []
    for element in find_all(article, class_name="textsiglum"):
        field = _located_field(element, fragments) or {}
        expansion = find_first(element, class_name="infotext")
        expansion_locator = element_locator(expansion) if expansion else None
        if expansion_locator is not None:
            start, end = _dom_span_for_element(expansion, fragments)
            expansion_locator["dom_text_start"] = start
            expansion_locator["dom_text_end"] = end
        display_source = _tooltip_display_text(expansion) if expansion else ""
        sigla.append(
            {
                **field,
                "expanded_source_text": exact_text(expansion) if expansion else "",
                "expanded_text": compact_text(exact_text(expansion)) if expansion else "",
                "expanded_display_source_text": display_source,
                "expanded_display_text": compact_text(display_source),
                "expanded_locator": expansion_locator,
            }
        )

    # Direct grammatical/variant links need not have an arrow or a wrapping
    # span.link. Keep every visible lemma anchor, independently of marker
    # association; never assign multiple targets to the first anchor.
    entry_links = []
    for anchor in find_all(article, tag="a"):
        href = anchor.attrs.get("href")
        if not href:
            continue
        target_url = quote_iri(urljoin(final_url, href))
        delivery = urlsplit(target_url).path.split("/")[1:2]
        if delivery not in (["lemma"], ["pdf"]):
            continue
        field = _located_field(anchor, fragments)
        if not field or field["locator"]["visible_text_start"] is None:
            continue
        target_lemma, target_homonym = _path_identity(target_url)
        entry_links.append({**field, "target_url": target_url,
            "target_lemma": target_lemma, "target_homonym": target_homonym,
            "target_delivery_type": "database_article" if delivery == ["lemma"] else "generated_pdf",
            "status": "explicit_source_link"})

    cross_references = []
    reference_diagnostics = []
    for link_container in find_all(article, class_name="link"):
        link_field = _located_field(link_container, fragments)
        if not link_field or link_field["locator"]["visible_text_start"] is None:
            continue
        anchors = [a for a in find_all(link_container, tag="a") if a.attrs.get("href")
                   and (_located_field(a, fragments) or {}).get("locator", {}).get("visible_text_start") is not None]
        container_text = exact_text(
            link_container,
            excluded_classes=HIDDEN_CLASSES,
            excluded_tags=HIDDEN_TAGS,
        )
        markers = [character for character in container_text if character in "↑↓"]
        if not markers:
            continue
        if len(anchors) != 1:
            reference_diagnostics.append({**link_field,
                "reason": "arrow container has no unique target", "anchor_count": len(anchors),
                "markers": markers, "status": "explicit_reference_target_unresolved"})
            continue
        anchor = anchors[0]
        target_url = quote_iri(urljoin(final_url, anchor.attrs["href"]))
        target_lemma, target_homonym = _path_identity(target_url)
        for marker in markers:
            cross_references.append(
                {
                    "locator": link_field.get("locator"),
                    "marker": marker,
                    "source_text": container_text,
                    "target_homonym": target_homonym,
                    "target_lemma": target_lemma,
                    "target_text": compact_text(exact_text(anchor, excluded_classes=HIDDEN_CLASSES,
                                                           excluded_tags=HIDDEN_TAGS)),
                    "target_url": target_url,
                }
            )

    example_index = {dom_path(node): index for index, node in enumerate(example_nodes)}
    lexical_index = {dom_path(node): index for index, node in enumerate(lexical_nodes)}
    divisions = []
    for meaning_index, meaning in enumerate(meaning_nodes):
        associated = _children_after_until_meaning(meaning)
        division_examples = []
        division_lexical = []
        for element in associated:
            for candidate in find_all(element, class_name="beleg-all"):
                index = example_index.get(dom_path(candidate))
                if index is not None:
                    division_examples.append(index)
            for candidate in find_all(element, tag="div", class_name="lex"):
                index = lexical_index.get(dom_path(candidate))
                if index is not None:
                    division_lexical.append(index)
        divisions.append(
            {
                "example_indices": division_examples,
                "lexical_block_indices": division_lexical,
                "meaning_index": meaning_index,
            }
        )

    source_object = {
        "byte_length": source_metadata.get("byte_length"),
        "content_classification": source_metadata.get("content_classification"),
        "decoded_encoding": encoding,
        "fetch_timestamp_utc": source_metadata.get("fetched_at_utc"),
        "final_url": final_url,
        "http_status": source_metadata.get("http_status"),
        "media_type": source_metadata.get("media_type"),
        "object_path": source_metadata.get("object_path"),
        "request_key": source_metadata.get("request_key"),
        "requested_url": source_metadata.get("requested_url"),
        "sha256": actual_sha,
        "used_replacement_characters": used_replacement_characters,
    }
    return {
        "article_contract_version": ARTICLE_CONTRACT_VERSION,
        "article_source_text": article_source_text,
        "article_text": compact_text(article_source_text),
        "cross_references": cross_references,
        "entry_links": entry_links,
        "reference_diagnostics": reference_diagnostics,
        "citations": citations,
        "citation_candidate_diagnostics": citation_candidate_diagnostics,
        "qualifiers": _records_for_elements(find_all(article, class_name="metr"), fragments),
        "divisions": divisions,
        "dom_full_text": dom_full_text,
        "examples": examples,
        "homonym": homonym,
        "lemma": lemma,
        "lemma_field": lemma_field,
        "lexical_blocks": lexical_blocks,
        "meanings": meanings,
        "sanskrit": sanskrit,
        "sigla": sigla,
        "source_identifier": f"badw:{final_url}",
        "source_object": source_object,
        "text_fragments": fragments,
        "tibetan_heading": tibetan_field,
        "tibetan_segments": _records_for_elements(find_all(article, tag="tib"), fragments),
    }


def parse_cached_article(cache: SourceCache, spec: RequestSpec) -> dict[str, object]:
    response = cache.fetch(spec, offline=True)
    return parse_database_article(response.body, source_metadata=response.metadata)


def _process_cached_catalogue(
    cache: SourceCache,
    records: Iterable[CatalogueRecord],
    emit: Callable[[dict[str, object]], None],
) -> dict[str, object]:
    failures = []
    counts = Counter()
    for record in records:
        if record.delivery_type != "database_article":
            counts["skipped_non_database"] += 1
            continue
        try:
            article = parse_cached_article(cache, RequestSpec(record.canonical_url))
        except Exception as error:
            counts["failed"] += 1
            failures.append(
                {"error": f"{type(error).__name__}: {error}", "url": record.canonical_url}
            )
            continue
        emit(article)
        counts["parsed"] += 1
    return {"attempted_database_articles": counts["parsed"] + counts["failed"], "failures": failures, **dict(sorted(counts.items()))}


def parse_cached_catalogue(
    cache: SourceCache,
    records: Sequence[CatalogueRecord],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Parse a small in-memory catalogue (primarily for callers and tests)."""

    parsed: list[dict[str, object]] = []
    summary = _process_cached_catalogue(cache, records, parsed.append)
    return parsed, summary


def write_cached_catalogue_jsonl(
    cache: SourceCache,
    records: Iterable[CatalogueRecord],
    output: Path,
) -> dict[str, object]:
    """Parse cached articles directly to JSONL without retaining the corpus in RAM."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        def write_record(record: dict[str, object]) -> None:
            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

        return _process_cached_catalogue(cache, records, write_record)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cache = SourceCache(args.cache_root)
    summary = write_cached_catalogue_jsonl(
        cache, read_catalogue(args.catalogue), args.output
    )
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if not summary.get("failed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
