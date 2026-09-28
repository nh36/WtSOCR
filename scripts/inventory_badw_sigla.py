#!/usr/bin/env python3
"""Inventory BAdW's own siglum tooltips without declaring them reviewed authorities.

Both outputs belong under ignored ``work/``: tooltip expansions may contain
substantial first-party text.  A spelling with multiple expansions is kept as
multiple candidates, never collapsed by a normalization heuristic.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


class InventoryError(ValueError):
    """A siglum occurrence cannot be traced to its exact parser source."""


def _read_articles(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    article = json.loads(line)
                except json.JSONDecodeError as error:
                    raise InventoryError(f"article line {line_number}: {error.msg}") from error
                if not isinstance(article, dict):
                    raise InventoryError(f"article line {line_number}: not an object")
                yield article


def _span(article: dict[str, Any], field: str, locator: dict[str, Any],
          start_key: str, end_key: str, expected: str) -> dict[str, Any]:
    source_text = article.get(field)
    start, end = locator.get(start_key), locator.get(end_key)
    if (not isinstance(source_text, str) or not isinstance(start, int)
            or not isinstance(end, int) or not 0 <= start < end <= len(source_text)
            or source_text[start:end] != expected):
        raise InventoryError(f"bad {field} source span for {article.get('source_identifier')}")
    source = article.get("source_object", {})
    sha = source.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        raise InventoryError(f"missing source hash for {article.get('source_identifier')}")
    return {"source_id": article["source_identifier"], "source_sha256": sha,
            "field": field, "start": start, "end": end,
            "dom_path": locator.get("dom_path")}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def inventory(articles: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    candidates: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    article_count = 0
    seen_articles: set[str] = set()
    for article in articles:
        article_count += 1
        source_id = article.get("source_identifier")
        if not isinstance(source_id, str) or source_id in seen_articles:
            raise InventoryError(f"missing or duplicate article source ID: {source_id}")
        seen_articles.add(source_id)
        for ordinal, siglum in enumerate(article.get("sigla", []), 1):
            label = siglum.get("source_text")
            expansion = siglum.get("expanded_display_text")
            full_expansion = siglum.get("expanded_source_text")
            if not isinstance(label, str) or not label or not isinstance(expansion, str):
                raise InventoryError(f"invalid siglum in {source_id}:{ordinal}")
            visible_span = _span(article, "article_source_text", siglum["locator"],
                                 "visible_text_start", "visible_text_end", label)
            tooltip_span = None
            if full_expansion:
                tooltip_span = _span(article, "dom_full_text", siglum["expanded_locator"],
                                     "dom_text_start", "dom_text_end", full_expansion)
            elif expansion:
                raise InventoryError(f"tooltip display without source in {source_id}:{ordinal}")
            candidate_key = (label, expansion)
            candidate_id = "badw:siglum:" + hashlib.sha256(
                (label + "\0" + expansion).encode("utf-8")
            ).hexdigest()
            occurrence = {
                "candidate_id": candidate_id,
                "siglum": label,
                "expansion": expansion,
                "source_url": article["source_object"]["final_url"],
                "source_span": visible_span,
                "tooltip_span": tooltip_span,
                "ordinal_in_article": ordinal,
            }
            occurrences.append(occurrence)
            candidates[candidate_key].append(occurrence)
    occurrences.sort(key=lambda row: (row["source_url"], row["ordinal_in_article"]))
    variants_per_siglum = Counter(label for label, _ in candidates)
    candidate_rows: list[dict[str, Any]] = []
    for (label, expansion), evidence in sorted(candidates.items()):
        exemplar = min(evidence, key=lambda row: (row["source_url"], row["ordinal_in_article"]))
        candidate_rows.append({
            "candidate_id": exemplar["candidate_id"], "siglum": label,
            "expansion": expansion, "article_count": len({row["source_url"] for row in evidence}),
            "occurrence_count": len(evidence), "variant_count_for_siglum": variants_per_siglum[label],
            "candidate_status": "single_observed_expansion" if variants_per_siglum[label] == 1 else "multiple_observed_expansions",
            "example_source_url": exemplar["source_url"],
            "example_source_span": exemplar["source_span"],
            "example_tooltip_span": exemplar["tooltip_span"],
        })
    summary = {
        "article_count": article_count,
        "siglum_count": len(variants_per_siglum),
        "candidate_count": len(candidate_rows),
        "occurrence_count": len(occurrences),
        "sigla_with_multiple_expansions": sum(n > 1 for n in variants_per_siglum.values()),
        "occurrences_without_tooltip": sum(row["tooltip_span"] is None for row in occurrences),
    }
    return candidate_rows, occurrences, summary


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(_canonical_json(row) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--occurrences", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    candidates, occurrences, summary = inventory(_read_articles(args.articles))
    _write_jsonl(args.candidates, candidates)
    _write_jsonl(args.occurrences, occurrences)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(_canonical_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
