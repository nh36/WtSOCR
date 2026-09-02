#!/usr/bin/env python3
"""Parse cached BAdW database-article HTML into auditable JSON records."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence
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


ARTICLE_CONTRACT_VERSION = "badw-database-article-v1"
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


def _path_identity(url: str) -> tuple[str, str]:
    parts = [unquote(part) for part in urlsplit(url).path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "lemma":
        return parts[1], parts[2] if len(parts) >= 3 else ""
    return "", ""


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
    sup = find_first(article, tag="sup")
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
        tibetan = find_first(element, tag="tib") or find_first(
            element, class_name="tibetisch"
        )
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
                "tibetan": _located_field(tibetan, fragments),
                "translation": _located_field(translation, fragments),
            }
        )

    lexical_nodes = find_all(article, tag="div", class_name="lex")
    lexical_blocks = _records_for_elements(lexical_nodes, fragments)
    sanskrit = _records_for_elements(find_all(article, tag="skt"), fragments)
    citations = _records_for_elements(
        find_all(article, class_name="stelle"), fragments
    )

    sigla = []
    for element in find_all(article, class_name="textsiglum"):
        field = _located_field(element, fragments) or {}
        expansion = find_first(element, class_name="infotext")
        sigla.append(
            {
                **field,
                "expanded_source_text": exact_text(expansion) if expansion else "",
                "expanded_text": compact_text(exact_text(expansion)) if expansion else "",
            }
        )

    cross_references = []
    for link_container in find_all(article, class_name="link"):
        anchor = find_first(
            link_container,
            tag="a",
            predicate=lambda item: "lemma" in item.classes,
        )
        if anchor is None or anchor is link_container or not anchor.attrs.get("href"):
            continue
        container_text = exact_text(
            link_container,
            excluded_classes=HIDDEN_CLASSES,
            excluded_tags=HIDDEN_TAGS,
        )
        markers = [character for character in container_text if character in "↑↓"]
        if not markers:
            continue
        target_url = quote_iri(urljoin(final_url, anchor.attrs["href"]))
        target_lemma, target_homonym = _path_identity(target_url)
        for marker in markers:
            link_field = _located_field(link_container, fragments) or {}
            cross_references.append(
                {
                    "locator": link_field.get("locator"),
                    "marker": marker,
                    "source_text": container_text,
                    "target_homonym": target_homonym,
                    "target_lemma": target_lemma,
                    "target_text": compact_text(exact_text(anchor)),
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
        "citations": citations,
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
    }


def parse_cached_article(cache: SourceCache, spec: RequestSpec) -> dict[str, object]:
    response = cache.fetch(spec, offline=True)
    return parse_database_article(response.body, source_metadata=response.metadata)


def parse_cached_catalogue(
    cache: SourceCache,
    records: Sequence[CatalogueRecord],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    parsed = []
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
        parsed.append(article)
        counts["parsed"] += 1
    return parsed, {"attempted_database_articles": counts["parsed"] + counts["failed"], "failures": failures, **dict(sorted(counts.items()))}


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
    records, summary = parse_cached_catalogue(cache, read_catalogue(args.catalogue))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
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
