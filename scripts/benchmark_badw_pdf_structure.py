#!/usr/bin/env python3
"""Select and score a small, source-anchored PDF-structure review sample.

The gold file is human-reviewed material in ignored work/, not parser output.
This tool never promotes a typography candidate to a lexical fact.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable


VERSION = "badw-pdf-structure-benchmark-v1"
KINDS = ("numbered_sense", "german_quote", "parenthetical_citation",
         "cross_reference", "definition", "tibetan_example", "belegstelle")
PREDICTED = {"german_quote": "german_quotes",
             "parenthetical_citation": "parenthetical_citations",
             "cross_reference": "cross_references"}
STRATA = ("short", "long", "numbered", "unknown", "reference", "paired", "general", "general_2")


def _stable(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _rows(path: Path) -> Iterable[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def visual_text(article: dict[str, Any]) -> str:
    return "\n".join(line["text"] for line in article["visual_lines"])


def _qualifies(article: dict[str, Any], stratum: str) -> bool:
    size = len(visual_text(article))
    diagnostics = article["diagnostics"]
    candidates = article["candidates"]
    return {
        "short": size < 200,
        "long": size >= 1500,
        "numbered": diagnostics.get("numbered_senses", 0) >= 2,
        "unknown": diagnostics.get("unknown_glyphs", 0) > 0,
        "reference": bool(candidates["cross_references"]),
        "paired": bool(candidates["adjacent_quote_citation_pairs"]),
        "general": True,
        "general_2": True,
    }[stratum]


def select(articles: Iterable[dict[str, Any]], per_volume: int = 8,
           review_chars: int = 500) -> list[dict[str, Any]]:
    """Hash-rank each stratum; selection is independent of input ordering."""
    if per_volume < 1 or review_chars < 1:
        raise ValueError("per_volume and review_chars must be positive")
    best: dict[tuple[int, str], list[tuple[str, dict[str, Any]]]] = {}
    seen: set[str] = set()
    for article in articles:
        volume = int(article["volume"])
        if volume not in (2, 3, 4):
            raise ValueError(f"unexpected PDF volume: {volume}")
        article_id = article["article_id"]
        if article_id in seen:
            raise ValueError(f"duplicate article_id: {article_id}")
        seen.add(article_id)
        for stratum in STRATA:
            if not _qualifies(article, stratum):
                continue
            rank = sha256(f"{volume}\0{stratum}\0{article_id}".encode()).hexdigest()
            bucket = best.setdefault((volume, stratum), [])
            bucket.append((rank, article))
            bucket.sort(key=lambda item: item[0])
            del bucket[per_volume:]
    chosen: list[dict[str, Any]] = []
    for volume in (2, 3, 4):
        used: set[str] = set()
        for stratum in STRATA:
            for _, article in best.get((volume, stratum), []):
                if article["article_id"] not in used:
                    used.add(article["article_id"])
                    text = visual_text(article)
                    chosen.append({"contract_version": VERSION, "article_id": article["article_id"],
                        "volume": volume, "stratum": stratum, "loc_headword": article["loc_headword"],
                        "tibetan_headword": article["tibetan_headword"],
                        "source_faithful_sha256": article["source_faithful_sha256"],
                        "visual_sha256": sha256(text.encode("utf-8")).hexdigest(),
                        "reviewed_start": 0, "reviewed_end": min(len(text), review_chars),
                        "visual_text": text[:review_chars],
                        "predictions": predictions(article, min(len(text), review_chars))})
                    break
            if len(used) >= per_volume:
                break
        if len(used) < per_volume:
            raise ValueError(f"volume {volume}: only {len(used)} distinct sample articles")
    return chosen


def predictions(article: dict[str, Any], review_end: int) -> dict[str, list[tuple[int, int]]]:
    result: dict[str, list[tuple[int, int]]] = {kind: [] for kind in KINDS}
    offsets: list[int] = []
    offset = 0
    for line in article["visual_lines"]:
        offsets.append(offset)
        offset += len(line["text"]) + 1
    for division in article["divisions"]:
        if division["kind"] == "numbered_sense":
            start = offsets[division["start_line_index"]]
            end = start + len(division["label"]) + 1
            if end <= review_end:
                result["numbered_sense"].append((start, end))
    for kind, key in PREDICTED.items():
        result[kind] = sorted((int(item["visual_start"]), int(item["visual_end"]))
                              for item in article["candidates"][key]
                              if int(item["visual_end"]) <= review_end)
    return result


def score(sample: Iterable[dict[str, Any]], gold: Iterable[dict[str, Any]]) -> dict[str, Any]:
    samples = {row["article_id"]: row for row in sample}
    metric_fields = ("reviewed_articles", "true_positive", "false_positive",
                     "false_negative", "gold", "predicted")
    totals: dict[str, Counter[str]] = {
        kind: Counter({field: 0 for field in metric_fields}) for kind in KINDS}
    reviewed: Counter[str] = Counter()
    seen_gold: set[str] = set()
    for annotation in gold:
        article_id = annotation["article_id"]
        if article_id in seen_gold:
            raise ValueError(f"duplicate gold article: {article_id}")
        seen_gold.add(article_id)
        if article_id not in samples:
            raise ValueError(f"gold article absent from sample: {article_id}")
        row = samples[article_id]
        if (annotation["source_faithful_sha256"] != row["source_faithful_sha256"]
                or annotation["visual_sha256"] != row["visual_sha256"]
                or annotation["reviewed_end"] != row["reviewed_end"]):
            raise ValueError(f"gold source/review boundary mismatch: {article_id}")
        reviewed[f"volume_{row['volume']}"] += 1
        reviewed_kinds = set(annotation["reviewed_kinds"])
        if not reviewed_kinds or not reviewed_kinds.issubset(KINDS):
            raise ValueError(f"invalid reviewed_kinds: {article_id}")
        gold_spans: dict[str, set[tuple[int, int]]] = {kind: set() for kind in KINDS}
        for span in annotation["spans"]:
            kind, start, end = span["kind"], int(span["start"]), int(span["end"])
            if kind not in KINDS or not 0 <= start < end <= row["reviewed_end"]:
                raise ValueError(f"invalid gold span: {article_id}: {span}")
            if kind not in reviewed_kinds:
                raise ValueError(f"gold span in unreviewed kind: {article_id}: {kind}")
            if row["visual_text"][start:end] != span["text"]:
                raise ValueError(f"gold text mismatch: {article_id}: {span}")
            gold_spans[kind].add((start, end))
        for kind in KINDS:
            if kind not in reviewed_kinds:
                continue
            actual = set(tuple(pair) for pair in row["predictions"][kind])
            expected = gold_spans[kind]
            totals[kind]["reviewed_articles"] += 1
            totals[kind]["true_positive"] += len(actual & expected)
            totals[kind]["false_positive"] += len(actual - expected)
            totals[kind]["false_negative"] += len(expected - actual)
            totals[kind]["gold"] += len(expected)
            totals[kind]["predicted"] += len(actual)
    return {"contract_version": VERSION, "sample_size": len(samples),
            "reviewed_count": sum(reviewed.values()), "reviewed_by_volume": dict(sorted(reviewed.items())),
            "metrics": {kind: dict(sorted(counter.items())) for kind, counter in totals.items()}}


def materialize_gold(sample: list[dict[str, Any]], annotations: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Resolve manually chosen literal spans against immutable sampled text.

    Each reviewed article must have a `reviewed` row.  All text fields are
    literal except `\\n`, which denotes an actual visual-line break.
    """
    by_index: dict[int, dict[str, Any]] = {}
    for item in annotations:
        index = int(item["sample_index"])
        if not 0 <= index < len(sample):
            raise ValueError(f"sample_index outside sample: {index}")
        row = sample[index]
        if (item.get("article_id") and item["article_id"] != row["article_id"]
                or item.get("loc_headword") and item["loc_headword"] != row["loc_headword"]
                or not item.get("article_id") and not item.get("loc_headword") and index not in by_index):
            raise ValueError(f"article identity mismatch at sample_index {index}")
        entry = by_index.setdefault(index, {"article_id": row["article_id"],
            "source_faithful_sha256": row["source_faithful_sha256"],
            "visual_sha256": row["visual_sha256"], "reviewed_end": row["reviewed_end"],
            "spans": [], "reviewed": False, "reviewed_kinds": []})
        kind = item["kind"]
        if kind == "reviewed":
            if entry["reviewed"]:
                raise ValueError(f"duplicate reviewed marker: {index}")
            entry["reviewed"] = True
            kinds = item["text"].split(",")
            if not kinds or any(kind not in KINDS for kind in kinds) or len(kinds) != len(set(kinds)):
                raise ValueError(f"invalid reviewed kind list: {index}")
            entry["reviewed_kinds"] = kinds
            continue
        if kind not in KINDS:
            raise ValueError(f"unsupported annotation kind: {kind}")
        needle = item["text"].replace("\\n", "\n")
        if not needle:
            raise ValueError(f"empty gold text: {index} {kind}")
        matches: list[int] = []
        cursor = 0
        while True:
            found = row["visual_text"].find(needle, cursor)
            if found < 0:
                break
            matches.append(found)
            cursor = found + 1
        occurrence = int(item["occurrence"] or 1)
        if not 1 <= occurrence <= len(matches):
            raise ValueError(f"gold literal absent/occurrence invalid: {index} {kind} {needle!r}")
        start = matches[occurrence - 1]
        entry["spans"].append({"kind": kind, "start": start,
                               "end": start + len(needle), "text": needle})
    if any(not entry["reviewed"] for entry in by_index.values()):
        raise ValueError("annotation spans exist without reviewed marker")
    for index, entry in by_index.items():
        span_keys = [(span["kind"], span["start"], span["end"]) for span in entry["spans"]]
        if len(span_keys) != len(set(span_keys)):
            raise ValueError(f"duplicate gold span: {index}")
        if any(span["kind"] not in entry["reviewed_kinds"] for span in entry["spans"]):
            raise ValueError(f"gold span in unreviewed kind: {index}")
    return [{key: value for key, value in by_index[index].items() if key != "reviewed"}
            for index in sorted(by_index)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    sample_cmd = commands.add_parser("select")
    sample_cmd.add_argument("--articles", type=Path, required=True)
    sample_cmd.add_argument("--output", type=Path, required=True)
    sample_cmd.add_argument("--per-volume", type=int, default=8)
    sample_cmd.add_argument("--review-chars", type=int, default=500)
    score_cmd = commands.add_parser("score")
    score_cmd.add_argument("--sample", type=Path, required=True)
    score_cmd.add_argument("--gold", type=Path, required=True)
    score_cmd.add_argument("--output", type=Path, required=True)
    gold_cmd = commands.add_parser("gold")
    gold_cmd.add_argument("--sample", type=Path, required=True)
    gold_cmd.add_argument("--annotations", type=Path, required=True)
    gold_cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "select":
        chosen = select(_rows(args.articles), args.per_volume, args.review_chars)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(b"".join(_stable(row) + b"\n" for row in chosen))
        print(json.dumps({"sample_size": len(chosen), "output": str(args.output)}))
    elif args.command == "score":
        result = score(_rows(args.sample), _rows(args.gold))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(_stable(result) + b"\n")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        with args.annotations.open(newline="", encoding="utf-8") as handle:
            gold = materialize_gold(list(_rows(args.sample)), csv.DictReader(handle, delimiter="\t"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(b"".join(_stable(row) + b"\n" for row in gold))
        print(json.dumps({"reviewed_count": len(gold), "output": str(args.output)}))


if __name__ == "__main__":
    main()
