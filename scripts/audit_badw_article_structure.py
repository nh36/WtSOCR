#!/usr/bin/env python3
"""Offline, stratified source/structure audit of cached BAdW HTML articles.

This checks reproducibility and exact field provenance, not semantic accuracy;
human review of the selected cases remains a separate gate.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from badw_article_parser import parse_database_article
from badw_source_cache import RequestSpec, SourceCache


FIELD_LISTS = ("meanings", "examples", "citations", "sigla", "sanskrit", "lexical_blocks")


def _read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _stratum(article: dict[str, Any]) -> str:
    lemma = article["lemma"]
    return lemma[0].lower() if lemma else "?"


def select(articles: list[dict[str, Any]], count: int = 300) -> list[dict[str, Any]]:
    """Fair first-character allocation plus deterministic complexity oversample."""
    if count < 1:
        raise ValueError("sample count must be positive")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        groups[_stratum(article)].append(article)
    selected: dict[str, dict[str, Any]] = {}
    for key in sorted(groups):
        group = sorted(groups[key], key=lambda row: hashlib.sha256(row["source_identifier"].encode()).hexdigest())
        for article in group[:min(2, len(group))]:
            selected[article["source_identifier"]] = article
    def complexity(row: dict[str, Any]) -> int:
        return (len(row["meanings"]) * 4 + len(row["examples"]) * 2
                + len(row["sigla"]) + len(row["cross_references"]) * 5
                + len(row["sanskrit"]) * 3)
    for article in sorted(articles, key=lambda row: (-complexity(row), row["source_identifier"])):
        if len(selected) >= min(count // 3, len(articles)):
            break
        selected[article["source_identifier"]] = article
    for article in sorted(articles, key=lambda row: hashlib.sha256(row["source_identifier"].encode()).hexdigest()):
        if len(selected) >= min(count, len(articles)):
            break
        selected[article["source_identifier"]] = article
    return sorted(selected.values(), key=lambda row: row["source_identifier"])


def _check_field(article: dict[str, Any], field: dict[str, Any] | None, name: str, errors: list[str]):
    if field is None:
        return
    locator = field.get("locator") or {}
    start, end = locator.get("visible_text_start"), locator.get("visible_text_end")
    source = field.get("source_text")
    text = article["article_source_text"]
    if (not isinstance(start, int) or not isinstance(end, int)
            or not isinstance(source, str) or text[start:end] != source
            or not 0 <= start < end <= len(text)):
        errors.append(f"{name}:bad_source_span")


def audit(article: dict[str, Any], cache: SourceCache) -> dict[str, Any]:
    source = article["source_object"]
    url = source["requested_url"]
    response = cache.fetch(RequestSpec(url), offline=True)
    errors: list[str] = []
    if response.metadata["sha256"] != source["sha256"]:
        errors.append("cache_hash_mismatch")
    replay = parse_database_article(response.body, source_metadata=response.metadata)
    if replay != article:
        errors.append("nonreproducible_parser")
    fragments = article["text_fragments"]
    if "".join(item["source_text"] for item in fragments if item["visible"]) != article["article_source_text"]:
        errors.append("visible_fragment_reconstruction")
    if "".join(item["source_text"] for item in fragments) != article["dom_full_text"]:
        errors.append("full_fragment_reconstruction")
    path_homonym = unquote(urlsplit(source["final_url"]).path.split("/")[-1])
    if article["homonym"] != path_homonym:
        errors.append("homonym_url_disagreement")
    for name in ("lemma_field", "tibetan_heading"):
        _check_field(article, article.get(name), name, errors)
    for name in FIELD_LISTS:
        for index, field in enumerate(article[name]):
            _check_field(article, field, f"{name}:{index}", errors)
    for index, example in enumerate(article["examples"]):
        for name in ("citation", "location", "tibetan", "translation"):
            _check_field(article, example.get(name), f"examples:{index}:{name}", errors)
        for sig_index, siglum in enumerate(example["citation_sigla"]):
            _check_field(article, siglum, f"examples:{index}:siglum:{sig_index}", errors)
    spans = [field["locator"]["visible_text_start"] for field in article["meanings"]]
    if spans != sorted(spans):
        errors.append("meanings_out_of_order")
    for index, division in enumerate(article["divisions"]):
        if division["meaning_index"] != index:
            errors.append(f"division:{index}:meaning_index")
        for name, target in (("example_indices", "examples"), ("lexical_block_indices", "lexical_blocks")):
            if any(not 0 <= item < len(article[target]) for item in division[name]):
                errors.append(f"division:{index}:{name}:out_of_range")
    return {
        "source_identifier": article["source_identifier"], "source_sha256": source["sha256"],
        "lemma": article["lemma"], "homonym": article["homonym"], "stratum": _stratum(article),
        "meanings": len(article["meanings"]), "examples": len(article["examples"]),
        "citations": len(article["citations"]), "sigla": len(article["sigla"]),
        "cross_references": len(article["cross_references"]), "sanskrit": len(article["sanskrit"]),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=300)
    args = parser.parse_args()
    articles = list(_read_jsonl(args.articles))
    rows = [audit(article, SourceCache(args.cache_root)) for article in select(articles, args.count)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    summary = {"sampled": len(rows), "failed": sum(bool(row["errors"]) for row in rows),
               "strata": dict(sorted(Counter(row["stratum"] for row in rows).items())),
               "errors": dict(sorted(Counter(error for row in rows for error in row["errors"]).items()))}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
