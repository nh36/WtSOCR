#!/usr/bin/env python3
"""Enumerate and acquire the public BAdW digital WTS catalogue."""

from __future__ import annotations

import argparse
from collections import Counter, deque
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Iterable, Mapping, Sequence
from urllib.parse import unquote, urljoin, urlsplit

from badw_html import Element, compact_text, exact_text, find_all, find_first, parse_html
from badw_source_cache import (
    CacheMissError,
    DEFAULT_DELAY_SECONDS,
    RequestSpec,
    SourceCache,
    delivery_type_for_url,
    quote_iri,
    utc_now,
)


BASE_URL = "https://wts-digital.badw.de"
SEARCH_URL = f"{BASE_URL}/suche"
CATALOGUE_CONTRACT_VERSION = "badw-catalogue-v1"
INITIAL_PREFIXES = tuple("abcdefghijklmnopqrstuvwxyz") + ("'",) + (
    "A",
    "I",
    "U",
    "R",
    "T",
    "D",
    "N",
    "M",
    "H",
    "Sh",
)
CATALOGUE_FIELDS = (
    "lemma",
    "display_lemma",
    "homonym",
    "canonical_url",
    "delivery_type",
    "enumeration_prefix",
    "catalogue_observed_at_utc",
    "search_meaning",
    "source_request_key",
)


@dataclass(frozen=True)
class CatalogueRecord:
    lemma: str
    display_lemma: str
    homonym: str
    canonical_url: str
    delivery_type: str
    enumeration_prefix: str
    catalogue_observed_at_utc: str
    search_meaning: str = ""
    source_request_key: str = ""


@dataclass(frozen=True)
class SearchPage:
    records: tuple[CatalogueRecord, ...]
    pagination_urls: tuple[str, ...]


def _record_sort_key(record: CatalogueRecord) -> tuple[object, ...]:
    homonym: tuple[int, object]
    if record.homonym.isdigit():
        homonym = (0, int(record.homonym))
    else:
        homonym = (1, record.homonym)
    return (
        record.lemma,
        homonym,
        record.delivery_type,
        record.canonical_url,
        record.enumeration_prefix,
    )


def _direct_child(element: Element, class_name: str) -> Element | None:
    for child in element.children:
        if isinstance(child, Element) and class_name in child.classes:
            return child
    return None


def _lemma_from_url(url: str) -> tuple[str, str]:
    parts = [unquote(part) for part in urlsplit(url).path.split("/") if part]
    if len(parts) < 2 or parts[0] not in {"lemma", "pdf"}:
        return "", ""
    lemma = parts[1]
    homonym = parts[2] if parts[0] == "lemma" and len(parts) >= 3 else ""
    return lemma, homonym


def parse_search_results(
    html: str,
    *,
    prefix: str,
    observed_at_utc: str,
    source_request_key: str = "",
    page_url: str = SEARCH_URL,
) -> SearchPage:
    """Parse all result links on one search page without an item limit."""

    root = parse_html(html)
    records = []
    for link_span in find_all(root, tag="span", class_name="lemlink"):
        anchor = find_first(link_span, tag="a")
        if anchor is None or not anchor.attrs.get("href"):
            continue
        canonical_url = quote_iri(urljoin(page_url, anchor.attrs["href"]))
        delivery_type = delivery_type_for_url(canonical_url)
        if delivery_type not in {"database_article", "generated_pdf"}:
            continue
        lemma, homonym = _lemma_from_url(canonical_url)
        display_element = find_first(anchor, class_name="lem")
        display_lemma = compact_text(
            exact_text(display_element or anchor, excluded_classes=("infotext",))
        )
        parent = link_span.parent
        meaning_element = (
            _direct_child(parent, "bedeutung") if parent is not None else None
        )
        search_meaning = (
            compact_text(
                exact_text(meaning_element, excluded_classes=("infotext",))
            )
            if meaning_element is not None
            else ""
        )
        records.append(
            CatalogueRecord(
                lemma=lemma or display_lemma,
                display_lemma=display_lemma or lemma,
                homonym=homonym,
                canonical_url=canonical_url,
                delivery_type=delivery_type,
                enumeration_prefix=prefix,
                catalogue_observed_at_utc=observed_at_utc,
                search_meaning=search_meaning,
                source_request_key=source_request_key,
            )
        )

    pagination_urls = set()
    for anchor in find_all(root, tag="a"):
        href = anchor.attrs.get("href", "")
        rel = anchor.attrs.get("rel", "").casefold().split()
        classes = {item.casefold() for item in anchor.classes}
        candidate = urljoin(page_url, href) if href else ""
        candidate_parts = urlsplit(candidate)
        looks_paginated = (
            "next" in rel
            or bool(classes & {"next", "page", "pagination"})
            or "page=" in candidate_parts.query.casefold()
            or "seite=" in candidate_parts.query.casefold()
        )
        if looks_paginated and candidate_parts.path.rstrip("/") == "/suche":
            pagination_urls.add(quote_iri(candidate))

    return SearchPage(
        records=tuple(sorted(records, key=_record_sort_key)),
        pagination_urls=tuple(sorted(pagination_urls)),
    )


def enumerate_catalogue(
    cache: SourceCache,
    *,
    prefixes: Sequence[str] = INITIAL_PREFIXES,
    observed_at_utc: str | None = None,
    offline: bool = False,
    refresh: bool = False,
    maximum_pages_per_prefix: int = 100,
) -> tuple[list[CatalogueRecord], dict[str, object]]:
    """Enumerate prefixes, follow search pagination, and detect duplicate URLs."""

    observed_at = observed_at_utc or utc_now()
    all_occurrences: list[CatalogueRecord] = []
    pages_fetched = 0
    fetch_stats = Counter()
    invalid_pages: list[str] = []

    for prefix in prefixes:
        first_spec = RequestSpec.post_form(SEARCH_URL, {"bedeutung": "", "lemma": prefix})
        queue: deque[RequestSpec] = deque([first_spec])
        seen_requests: set[str] = set()
        while queue:
            spec = queue.popleft()
            if spec.key in seen_requests:
                continue
            if len(seen_requests) >= maximum_pages_per_prefix:
                raise RuntimeError(f"pagination limit exceeded for prefix {prefix!r}")
            seen_requests.add(spec.key)
            response = cache.fetch(spec, offline=offline, refresh=refresh)
            pages_fetched += 1
            fetch_stats["cache_hits" if response.cache_hit else "network_fetches"] += 1
            if not response.is_valid_resource:
                invalid_pages.append(spec.safe_url)
                continue
            html = response.body.decode("utf-8", errors="strict")
            page = parse_search_results(
                html,
                prefix=prefix,
                observed_at_utc=observed_at,
                source_request_key=spec.key,
                page_url=str(response.metadata["final_url"]),
            )
            all_occurrences.extend(page.records)
            for page_url in page.pagination_urls:
                queue.append(RequestSpec(page_url))

    by_url: dict[str, list[CatalogueRecord]] = {}
    for record in all_occurrences:
        by_url.setdefault(record.canonical_url, []).append(record)

    records = [
        sorted(occurrences, key=_record_sort_key)[0]
        for occurrences in by_url.values()
    ]
    records.sort(key=_record_sort_key)
    duplicate_urls = {
        url: sorted({record.enumeration_prefix for record in occurrences})
        for url, occurrences in by_url.items()
        if len(occurrences) > 1
    }
    delivery_counts = Counter(record.delivery_type for record in records)
    summary: dict[str, object] = {
        "catalogue_contract_version": CATALOGUE_CONTRACT_VERSION,
        "catalogue_observed_at_utc": observed_at,
        "cache_hits": fetch_stats["cache_hits"],
        "database_articles": delivery_counts["database_article"],
        "duplicate_occurrences": len(all_occurrences) - len(records),
        "duplicate_url_count": len(duplicate_urls),
        "duplicate_urls": duplicate_urls,
        "generated_pdfs": delivery_counts["generated_pdf"],
        "invalid_search_pages": invalid_pages,
        "network_fetches": fetch_stats["network_fetches"],
        "pages_processed": pages_fetched,
        "prefixes": list(prefixes),
        "total_occurrences": len(all_occurrences),
        "unique_results": len(records),
    }
    return records, summary


def write_catalogue(path: Path | str, records: Iterable[CatalogueRecord]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CATALOGUE_FIELDS, delimiter="\t")
        writer.writeheader()
        for record in sorted(records, key=_record_sort_key):
            writer.writerow(asdict(record))


def read_catalogue(path: Path | str) -> list[CatalogueRecord]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != CATALOGUE_FIELDS:
            raise ValueError(f"unexpected BAdW catalogue fields in {path}")
        records = [CatalogueRecord(**row) for row in reader]
    return sorted(records, key=_record_sort_key)


def catalogue_signature(record: CatalogueRecord) -> tuple[str, str, str, str]:
    return (record.canonical_url, record.lemma, record.homonym, record.delivery_type)


def compare_catalogues(
    older: Sequence[CatalogueRecord], newer: Sequence[CatalogueRecord]
) -> dict[str, object]:
    old = {catalogue_signature(record) for record in older}
    new = {catalogue_signature(record) for record in newer}
    return {
        "added": [list(item) for item in sorted(new - old)],
        "added_count": len(new - old),
        "new_count": len(new),
        "old_count": len(old),
        "removed": [list(item) for item in sorted(old - new)],
        "removed_count": len(old - new),
        "unchanged_count": len(old & new),
    }


def select_stratified_records(
    records: Sequence[CatalogueRecord],
    *,
    prefixes: Sequence[str] | None = None,
    delivery_types: frozenset[str] | None = None,
    per_prefix: int = 1,
) -> list[CatalogueRecord]:
    """Select deterministic, evenly spaced records within each prefix stratum."""

    if per_prefix < 1:
        raise ValueError("per_prefix must be positive")
    allowed_prefixes = set(prefixes) if prefixes is not None else None
    groups: dict[str, list[CatalogueRecord]] = {}
    for record in sorted(records, key=_record_sort_key):
        if allowed_prefixes is not None and record.enumeration_prefix not in allowed_prefixes:
            continue
        if delivery_types is not None and record.delivery_type not in delivery_types:
            continue
        groups.setdefault(record.enumeration_prefix, []).append(record)

    selected: dict[str, CatalogueRecord] = {}
    for prefix in sorted(groups):
        group = groups[prefix]
        count = min(per_prefix, len(group))
        if count == 1:
            indices = [len(group) // 2]
        else:
            indices = [
                index * (len(group) - 1) // (count - 1) for index in range(count)
            ]
        for index in indices:
            record = group[index]
            selected.setdefault(record.canonical_url, record)
    return sorted(selected.values(), key=_record_sort_key)


def acquire_catalogue_records(
    cache: SourceCache,
    records: Sequence[CatalogueRecord],
    *,
    delivery_types: frozenset[str] | None = None,
    maximum_items: int | None = None,
    offline: bool = False,
) -> dict[str, object]:
    selected = [
        record
        for record in sorted(records, key=_record_sort_key)
        if delivery_types is None or record.delivery_type in delivery_types
    ]
    if maximum_items is not None:
        attempted_records = selected[:maximum_items]
    else:
        attempted_records = selected
    stats = Counter()
    failures = []
    for record in attempted_records:
        try:
            response = cache.fetch(RequestSpec(record.canonical_url), offline=offline)
        except CacheMissError as error:
            stats["offline_misses"] += 1
            failures.append({"url": record.canonical_url, "error": str(error)})
            continue
        stats["cache_hits" if response.cache_hit else "network_fetches"] += 1
        if response.is_valid_resource:
            stats["valid_resources"] += 1
        else:
            stats["invalid_resources"] += 1
            kind = str(response.metadata.get("failure_kind", "unknown"))
            stats[kind] += 1
            failures.append(
                {
                    "classification": response.metadata.get("content_classification"),
                    "http_status": response.metadata.get("http_status"),
                    "url": record.canonical_url,
                }
            )
    return {
        "attempted": len(attempted_records),
        "available": len(selected),
        "failures": failures,
        "remaining": len(selected) - len(attempted_records),
        **dict(sorted(stats.items())),
    }


def _write_json(path: Path | str, payload: Mapping[str, object]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _cache_from_args(args: argparse.Namespace) -> SourceCache:
    return SourceCache(
        args.cache_root,
        delay_seconds=args.delay,
        max_attempts=args.max_attempts,
        backoff_seconds=args.backoff,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    enumerate_parser = subparsers.add_parser("enumerate", help="enumerate search prefixes")
    enumerate_parser.add_argument("--cache-root", type=Path, required=True)
    enumerate_parser.add_argument("--output", type=Path, required=True)
    enumerate_parser.add_argument("--summary", type=Path, required=True)
    enumerate_parser.add_argument("--prefix", action="append", dest="prefixes")
    enumerate_parser.add_argument("--observed-at")
    enumerate_parser.add_argument("--offline", action="store_true")
    enumerate_parser.add_argument("--refresh", action="store_true")
    enumerate_parser.add_argument("--fail-on-duplicates", action="store_true")
    enumerate_parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    enumerate_parser.add_argument("--max-attempts", type=int, default=4)
    enumerate_parser.add_argument("--backoff", type=float, default=1.0)

    acquire_parser = subparsers.add_parser("acquire", help="acquire catalogue objects")
    acquire_parser.add_argument("--cache-root", type=Path, required=True)
    acquire_parser.add_argument("--catalogue", type=Path, required=True)
    acquire_parser.add_argument("--summary", type=Path, required=True)
    acquire_parser.add_argument(
        "--delivery-type",
        action="append",
        choices=("database_article", "generated_pdf"),
    )
    acquire_parser.add_argument("--limit", type=int)
    acquire_parser.add_argument("--offline", action="store_true")
    acquire_parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    acquire_parser.add_argument("--max-attempts", type=int, default=4)
    acquire_parser.add_argument("--backoff", type=float, default=1.0)

    sample_parser = subparsers.add_parser(
        "sample", help="write a deterministic prefix-stratified sub-catalogue"
    )
    sample_parser.add_argument("--catalogue", type=Path, required=True)
    sample_parser.add_argument("--output", type=Path, required=True)
    sample_parser.add_argument("--prefix", action="append", dest="prefixes")
    sample_parser.add_argument(
        "--delivery-type",
        action="append",
        choices=("database_article", "generated_pdf"),
    )
    sample_parser.add_argument("--per-prefix", type=int, default=1)

    compare_parser = subparsers.add_parser("compare", help="compare two catalogues")
    compare_parser.add_argument("older", type=Path)
    compare_parser.add_argument("newer", type=Path)
    compare_parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "enumerate":
        cache = _cache_from_args(args)
        records, summary = enumerate_catalogue(
            cache,
            prefixes=args.prefixes or INITIAL_PREFIXES,
            observed_at_utc=args.observed_at,
            offline=args.offline,
            refresh=args.refresh,
        )
        write_catalogue(args.output, records)
        _write_json(args.summary, summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        if args.fail_on_duplicates and summary["duplicate_url_count"]:
            return 2
        return 0
    if args.command == "acquire":
        cache = _cache_from_args(args)
        summary = acquire_catalogue_records(
            cache,
            read_catalogue(args.catalogue),
            delivery_types=frozenset(args.delivery_type) if args.delivery_type else None,
            maximum_items=args.limit,
            offline=args.offline,
        )
        _write_json(args.summary, summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "sample":
        records = select_stratified_records(
            read_catalogue(args.catalogue),
            prefixes=args.prefixes,
            delivery_types=(
                frozenset(args.delivery_type) if args.delivery_type else None
            ),
            per_prefix=args.per_prefix,
        )
        write_catalogue(args.output, records)
        delivery_counts = Counter(record.delivery_type for record in records)
        print(
            json.dumps(
                {
                    "database_articles": delivery_counts["database_article"],
                    "generated_pdfs": delivery_counts["generated_pdf"],
                    "selected": len(records),
                },
                sort_keys=True,
            )
        )
        return 0

    comparison = compare_catalogues(
        read_catalogue(args.older), read_catalogue(args.newer)
    )
    serialised = json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _write_json(args.output, comparison)
    else:
        print(serialised)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CacheMissError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
