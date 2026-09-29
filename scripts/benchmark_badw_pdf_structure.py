#!/usr/bin/env python3
"""Select and score a small, source-anchored PDF-structure review sample.

The gold file is human-reviewed material in ignored work/, not parser output.
This tool never promotes a typography candidate to a lexical fact.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable


VERSION = "badw-pdf-structure-benchmark-v1"
WINDOWED_VERSION = "badw-pdf-structure-benchmark-v2"
KINDS = ("numbered_sense", "german_quote", "parenthetical_citation",
         "cross_reference", "definition", "tibetan_example", "belegstelle",
         "correction_apparatus")
PREDICTED = {"german_quote": "german_quotes",
             "parenthetical_citation": "parenthetical_citations",
             "cross_reference": "cross_references"}
STRATA = ("short", "long", "numbered", "unknown", "reference", "paired",
          "correction", "general", "general_2")


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


def reviewed_ranges(row: dict[str, Any]) -> list[tuple[int, int]]:
    if row["contract_version"] == VERSION:
        return [(0, row["reviewed_end"])]
    if row["contract_version"] != WINDOWED_VERSION:
        raise ValueError(f"unsupported benchmark contract: {row['contract_version']}")
    ranges = [tuple(pair) for pair in row["reviewed_ranges"]]
    if (not ranges or any(not 0 <= start < end <= len(row["visual_text"])
                          for start, end in ranges)
            or any(left[1] >= right[0] for left, right in zip(ranges, ranges[1:]))):
        raise ValueError(f"invalid reviewed ranges: {row['article_id']}")
    return ranges


def _inside(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(left <= start < end <= right for left, right in ranges)


def _review_windows(text: str, width: int) -> list[tuple[int, int]]:
    """Two complete-line windows, one at the opening and one later in the article."""
    if len(text) <= 2 * width:
        return [(0, len(text))]
    first_end = text.find("\n", width)
    first_end = len(text) if first_end < 0 else first_end
    later_start = text.rfind("\n", 0, max(first_end + 1, len(text) * 2 // 3)) + 1
    if later_start <= first_end:
        later_start = text.find("\n", first_end) + 1
    if later_start <= first_end:
        return [(0, len(text))]
    later_end = text.find("\n", later_start + width)
    later_end = len(text) if later_end < 0 else later_end
    return [(0, first_end), (later_start, later_end)]


def _correction_windows(text: str, width: int) -> list[tuple[int, int]]:
    """Keep a printed correction and its surrounding complete source lines in view."""
    match = re.search(r"\(r\.\s+[^()]+\)", text)
    if match is None:
        raise ValueError("correction stratum lacks a literal printed correction")
    start = text.rfind("\n", 0, max(0, match.start() - width // 2)) + 1
    end = text.find("\n", min(len(text), match.end() + width // 2))
    end = len(text) if end < 0 else end
    return [(start, end)]


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
        "correction": bool(re.search(r"\(r\.\s+[^()]+\)", visual_text(article))),
        "general": True,
        "general_2": True,
    }[stratum]


def select(articles: Iterable[dict[str, Any]], per_volume: int = 8,
           review_chars: int = 500,
           exclude_ids: set[str] | None = None,
           windowed: bool = False) -> list[dict[str, Any]]:
    """Hash-rank each stratum; selection is independent of input ordering."""
    if per_volume < 1 or review_chars < 1:
        raise ValueError("per_volume and review_chars must be positive")
    best: dict[tuple[int, str], list[tuple[str, dict[str, Any]]]] = {}
    seen: set[str] = set()
    exclude_ids = exclude_ids or set()
    for article in articles:
        volume = int(article["volume"])
        if volume not in (2, 3, 4):
            raise ValueError(f"unexpected PDF volume: {volume}")
        article_id = article["article_id"]
        if article_id in seen:
            raise ValueError(f"duplicate article_id: {article_id}")
        seen.add(article_id)
        if article_id in exclude_ids:
            continue
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
        volume_rows: list[dict[str, Any]] = []
        # Take the best unused article in each stratum per round.  The old
        # single pass silently capped a volume at eight articles, even when
        # callers requested a larger independent readiness sample.
        for _ in range(per_volume):
            for stratum in STRATA:
                article = next((candidate for _, candidate in best.get((volume, stratum), [])
                                if candidate["article_id"] not in used), None)
                if article is None:
                    continue
                used.add(article["article_id"])
                text = visual_text(article)
                ranges = (_correction_windows(text, review_chars) if stratum == "correction"
                          else _review_windows(text, review_chars)) if windowed else [(0, min(len(text), review_chars))]
                row = {"contract_version": WINDOWED_VERSION if windowed else VERSION,
                    "article_id": article["article_id"],
                    "volume": volume, "stratum": stratum, "loc_headword": article["loc_headword"],
                    "tibetan_headword": article["tibetan_headword"],
                    "source_faithful_sha256": article["source_faithful_sha256"],
                    "visual_sha256": sha256(text.encode("utf-8")).hexdigest(),
                    "visual_text": text if windowed else text[:review_chars],
                    "predictions": predictions(article, ranges)}
                if windowed:
                    row["reviewed_ranges"] = ranges
                else:
                    row.update(reviewed_start=0, reviewed_end=ranges[0][1])
                volume_rows.append(row)
                if len(used) >= per_volume:
                    break
            if len(used) >= per_volume:
                break
        if len(used) < per_volume:
            raise ValueError(f"volume {volume}: only {len(used)} distinct sample articles")
        if windowed:
            # Freeze review assignments with the sample.  They are hash-ranked
            # independently of input order and parser predictions.
            ranked = sorted(volume_rows, key=lambda row: sha256(
                f"partition\0{volume}\0{row['article_id']}".encode()).hexdigest())
            acceptance = {row["article_id"] for row in ranked[:max(1, per_volume // 4)]}
            double_review = {row["article_id"] for row in ranked[:max(1, round(per_volume * .15))]}
            for row in volume_rows:
                row["review_partition"] = "acceptance" if row["article_id"] in acceptance else "development"
                row["double_review"] = row["article_id"] in double_review
        chosen.extend(volume_rows)
    return chosen


def predictions(article: dict[str, Any], review_end: int | list[tuple[int, int]]) -> dict[str, list[tuple[int, int]]]:
    ranges = [(0, review_end)] if isinstance(review_end, int) else review_end
    result: dict[str, list[tuple[int, int]]] = {kind: [] for kind in KINDS}
    offsets: list[int] = []
    offset = 0
    for line in article["visual_lines"]:
        offsets.append(offset)
        offset += len(line["text"]) + 1
    for division in article["divisions"]:
        if division["kind"] == "numbered_sense":
            line = article["visual_lines"][division["start_line_index"]]["text"]
            label = re.match(r"^\s*(?P<label>" + re.escape(division["label"]) + r"\.)", line)
            if label is None:
                raise ValueError(f"numbered sense lacks its printed label: {article['article_id']}")
            start = offsets[division["start_line_index"]] + label.start("label")
            end = offsets[division["start_line_index"]] + label.end("label")
            if _inside(start, end, ranges):
                result["numbered_sense"].append((start, end))
    for kind, key in PREDICTED.items():
        result[kind] = sorted((int(item["visual_start"]), int(item["visual_end"]))
                              for item in article["candidates"][key]
                              if _inside(int(item["visual_start"]), int(item["visual_end"]), ranges))
    return result


def score(sample: Iterable[dict[str, Any]], gold: Iterable[dict[str, Any]]) -> dict[str, Any]:
    samples = {row["article_id"]: row for row in sample}
    metric_fields = ("reviewed_articles", "true_positive", "false_positive",
                     "false_negative", "gold", "predicted")
    totals: dict[str, Counter[str]] = {
        kind: Counter({field: 0 for field in metric_fields}) for kind in KINDS}
    reviewed: Counter[str] = Counter()
    seen_gold: set[str] = set()
    versions: set[str] = set()
    for annotation in gold:
        article_id = annotation["article_id"]
        if article_id in seen_gold:
            raise ValueError(f"duplicate gold article: {article_id}")
        seen_gold.add(article_id)
        if article_id not in samples:
            raise ValueError(f"gold article absent from sample: {article_id}")
        row = samples[article_id]
        ranges = reviewed_ranges(row)
        versions.add(row["contract_version"])
        if (annotation["source_faithful_sha256"] != row["source_faithful_sha256"]
                or annotation["visual_sha256"] != row["visual_sha256"]
                or (annotation.get("reviewed_ranges") if row["contract_version"] == WINDOWED_VERSION
                    else annotation.get("reviewed_end")) !=
                   (row["reviewed_ranges"] if row["contract_version"] == WINDOWED_VERSION
                    else row["reviewed_end"])):
            raise ValueError(f"gold source/review boundary mismatch: {article_id}")
        reviewed[f"volume_{row['volume']}"] += 1
        reviewed_kinds = set(annotation["reviewed_kinds"])
        if not reviewed_kinds or not reviewed_kinds.issubset(KINDS):
            raise ValueError(f"invalid reviewed_kinds: {article_id}")
        gold_spans: dict[str, set[tuple[int, int]]] = {kind: set() for kind in KINDS}
        for span in annotation["spans"]:
            kind, start, end = span["kind"], int(span["start"]), int(span["end"])
            if kind not in KINDS or not _inside(start, end, ranges):
                raise ValueError(f"invalid gold span: {article_id}: {span}")
            if kind not in reviewed_kinds:
                raise ValueError(f"gold span in unreviewed kind: {article_id}: {kind}")
            if row["visual_text"][start:end] != span["text"]:
                raise ValueError(f"gold text mismatch: {article_id}: {span}")
            gold_spans[kind].add((start, end))
        for kind in KINDS:
            if kind not in reviewed_kinds:
                continue
            actual = set(tuple(pair) for pair in row["predictions"].get(kind, []))
            expected = gold_spans[kind]
            totals[kind]["reviewed_articles"] += 1
            totals[kind]["true_positive"] += len(actual & expected)
            totals[kind]["false_positive"] += len(actual - expected)
            totals[kind]["false_negative"] += len(expected - actual)
            totals[kind]["gold"] += len(expected)
            totals[kind]["predicted"] += len(actual)
    return {"contract_version": versions.pop() if len(versions) == 1 else "mixed",
            "sample_size": len(samples),
            "reviewed_count": sum(reviewed.values()), "reviewed_by_volume": dict(sorted(reviewed.items())),
            "metrics": {kind: dict(sorted(counter.items())) for kind, counter in totals.items()}}


def with_lexical_predictions(sample: list[dict[str, Any]],
                             lexical: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join independent candidate output without modifying the frozen sample."""
    sample = deepcopy(sample)
    by_id = {row["article_id"]: row for row in sample}
    if len(by_id) != len(sample):
        raise ValueError("duplicate sample article_id")
    seen: set[str] = set()
    for candidate in lexical:
        article_id = candidate["article_id"]
        if article_id not in by_id:
            continue
        if article_id in seen:
            raise ValueError(f"duplicate lexical article_id: {article_id}")
        seen.add(article_id)
        row = by_id[article_id]
        if (candidate["source_faithful_sha256"] != row["source_faithful_sha256"]
                or candidate["visual_sha256"] != row["visual_sha256"]):
            raise ValueError(f"lexical source mismatch: {article_id}")
        mapping = (("definition", "definitions"), ("tibetan_example", "tibetan_examples"),
                   ("belegstelle", "belegstellen"),
                   ("correction_apparatus", "correction_apparatus"))
        for kind, key in mapping:
            row["predictions"][kind] = sorted(
                (int(item["visual_start"]), int(item["visual_end"]))
                for item in candidate.get(key, [])
                if _inside(int(item["visual_start"]), int(item["visual_end"]), reviewed_ranges(row))
                and (kind != "tibetan_example" or not item["lexical_region"])
            )
    if seen != set(by_id):
        raise ValueError(f"missing lexical candidates for {len(by_id) - len(seen)} sampled articles")
    return sample


def refresh_predictions(sample: list[dict[str, Any]],
                        articles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recompute structural predictions without changing frozen review sources."""
    sample = deepcopy(sample)
    by_id = {row["article_id"]: row for row in sample}
    if len(by_id) != len(sample):
        raise ValueError("duplicate sample article_id")
    seen: set[str] = set()
    for article in articles:
        article_id = article["article_id"]
        if article_id not in by_id:
            continue
        if article_id in seen:
            raise ValueError(f"duplicate source article_id: {article_id}")
        seen.add(article_id)
        row = by_id[article_id]
        text = visual_text(article)
        if (row["source_faithful_sha256"] != article["source_faithful_sha256"]
                or row["visual_sha256"] != sha256(text.encode("utf-8")).hexdigest()
                or row["visual_text"] != (text if row["contract_version"] == WINDOWED_VERSION
                                          else text[:row["reviewed_end"]])):
            raise ValueError(f"sample source mismatch: {article_id}")
        row["predictions"] = predictions(article, reviewed_ranges(row))
    if seen != set(by_id):
        raise ValueError(f"missing structural sources for {len(by_id) - len(seen)} sampled articles")
    return sample


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
            "visual_sha256": row["visual_sha256"],
            "spans": [], "reviewed": False, "reviewed_kinds": []})
        if row["contract_version"] == WINDOWED_VERSION:
            entry["reviewed_ranges"] = row["reviewed_ranges"]
        else:
            entry["reviewed_end"] = row["reviewed_end"]
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
            if _inside(found, found + len(needle), reviewed_ranges(row)):
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
    sample_cmd.add_argument("--windowed", action="store_true",
                            help="review opening and later complete-line windows (v2 contract)")
    sample_cmd.add_argument("--exclude-sample", type=Path, action="append",
                            help="exclude article IDs in an existing review sample")
    score_cmd = commands.add_parser("score")
    score_cmd.add_argument("--sample", type=Path, required=True)
    score_cmd.add_argument("--gold", type=Path, required=True)
    score_cmd.add_argument("--output", type=Path, required=True)
    score_cmd.add_argument("--lexical-candidates", type=Path,
                           help="source-hash-checked lexical candidate corpus")
    gold_cmd = commands.add_parser("gold")
    gold_cmd.add_argument("--sample", type=Path, required=True)
    gold_cmd.add_argument("--annotations", type=Path, required=True)
    gold_cmd.add_argument("--output", type=Path, required=True)
    refresh_cmd = commands.add_parser("refresh")
    refresh_cmd.add_argument("--sample", type=Path, required=True)
    refresh_cmd.add_argument("--articles", type=Path, required=True)
    refresh_cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "select":
        excluded = ({row["article_id"] for path in args.exclude_sample for row in _rows(path)}
                    if args.exclude_sample else set())
        chosen = select(_rows(args.articles), args.per_volume, args.review_chars,
                        excluded, args.windowed)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(b"".join(_stable(row) + b"\n" for row in chosen))
        print(json.dumps({"sample_size": len(chosen), "output": str(args.output)}))
    elif args.command == "score":
        sample = list(_rows(args.sample))
        if args.lexical_candidates:
            sample = with_lexical_predictions(sample, _rows(args.lexical_candidates))
        result = score(sample, _rows(args.gold))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(_stable(result) + b"\n")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif args.command == "refresh":
        rows = refresh_predictions(list(_rows(args.sample)), _rows(args.articles))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(b"".join(_stable(row) + b"\n" for row in rows))
        print(json.dumps({"sample_size": len(rows), "output": str(args.output)}))
    else:
        with args.annotations.open(newline="", encoding="utf-8") as handle:
            gold = materialize_gold(list(_rows(args.sample)), csv.DictReader(handle, delimiter="\t"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(b"".join(_stable(row) + b"\n" for row in gold))
        print(json.dumps({"reviewed_count": len(gold), "output": str(args.output)}))


if __name__ == "__main__":
    main()
