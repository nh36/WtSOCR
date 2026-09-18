#!/usr/bin/env python3
"""Build an offline BAdW source index and match its articles to CURRENT WtSOCR.

This deliberately does *not* reconcile text or propose corrections.  It makes
article identity and every source span explicit so that a later ledger can be
conservative about print-faithful changes.  Inputs are cached BAdW material and
the generated CURRENT QA line zones; no network access is used.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import gzip
import json
from pathlib import Path
import re
import shutil
from typing import Iterable
import unicodedata

from badw_canonical_pages import extract_headings


ROOT = Path(__file__).resolve().parents[1]
VOLUMES = ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m")
CONTRACT_VERSION = "badw-source-index-v2"
CANDIDATE_CONTRACT_VERSION = "badw-source-match-candidate-v1"


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def lemma_key(text: str) -> str:
    return compact(text).replace("'", "’").replace("‘", "’").strip(" ,.;:·")


def tibetan_key(text: str) -> str:
    kept = []
    for char in unicodedata.normalize("NFC", text or "").replace("༌", "་"):
        category = unicodedata.category(char)
        if char == "་" or ("\u0f00" <= char <= "\u0fff" and category[0] in {"L", "M"}):
            kept.append(char)
    return re.sub("་+", "་", "".join(kept)).strip("་")


def reconstructed_headword(row: dict[str, str]) -> str:
    tibetan = row["headword_tibetan"].strip()
    syllables = [value for value in re.split(r"[་༌\s]+", tibetan) if value]
    line = row["line_text"].strip()
    if tibetan and line.startswith(tibetan):
        remainder = line[len(tibetan) :].strip()
    else:
        remainder = re.sub(r"^[\u0f00-\u0fff\s]+", "", line).strip()
    return lemma_key(" ".join(remainder.split()[: len(syllables)]))


@dataclass(frozen=True)
class LocalEntry:
    volume: str
    entry_id: str
    lemma: str
    tibetan: str
    pages: tuple[int, ...]
    text: str

    @property
    def key(self) -> str:
        return f"{self.volume}:{self.entry_id}"


@dataclass(frozen=True)
class SourceArticle:
    source_id: str
    delivery_type: str
    lemma: str
    homonym: str
    tibetan: str
    text: str
    provenance: dict[str, object]


def load_local_entries(qa_root: Path) -> list[LocalEntry]:
    entries: list[LocalEntry] = []
    for volume in VOLUMES:
        path = qa_root / volume / f"{volume}_line_zones.tsv"
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            if row["entry_id"] != "0":
                grouped[row["entry_id"]].append(row)
        for entry_id, entry_rows in sorted(grouped.items(), key=lambda item: int(item[0])):
            heads = [row for row in entry_rows if row["zone"] == "headword_line"]
            if not heads:
                continue
            lemma = reconstructed_headword(heads[0])
            if not lemma or len(lemma) > 120:
                continue
            entries.append(LocalEntry(
                volume=volume,
                entry_id=entry_id,
                lemma=lemma,
                tibetan=heads[0]["headword_tibetan"],
                pages=tuple(sorted({int(row["page"]) for row in entry_rows})),
                text="\n".join(row["line_text"] for row in entry_rows),
            ))
    return entries


def load_html_articles(path: Path) -> list[SourceArticle]:
    result: list[SourceArticle] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            source = record["source_object"]
            heading = record.get("tibetan_heading") or {}
            result.append(SourceArticle(
                source_id=str(record["source_identifier"]),
                delivery_type="database_article",
                lemma=str(record.get("lemma", "")),
                homonym=str(record.get("homonym", "")),
                tibetan=str(heading.get("text", "")),
                text=str(record.get("article_text", "")),
                provenance={
                    "canonical_url": source.get("final_url") or source.get("requested_url"),
                    "source_sha256": source.get("sha256"),
                    "fetched_at_utc": source.get("fetch_timestamp_utc"),
                    "object_path": source.get("object_path"),
                    "article_text_locator": record.get("article_text_locator"),
                },
            ))
    return sorted(result, key=lambda item: item.source_id)


def _runs_to_text(runs: list[dict[str, object]], start: int, end: int) -> str:
    pieces: list[str] = []
    previous_y: float | None = None
    for run in runs[start:end]:
        text = str(run["decoded_unicode"])
        y = float(run["y"])
        if previous_y is not None and abs(y - previous_y) > 0.02 and pieces:
            if not pieces[-1].endswith((" ", "\n")) and not text.startswith((" ", "\n")):
                pieces.append("\n")
        pieces.append(text)
        previous_y = y
    return "".join(pieces)


def _ints(value: str) -> list[int]:
    return [int(piece) for piece in value.split(",") if piece]


def load_pdf_articles(canonical_root: Path) -> list[SourceArticle]:
    """Make page-contained article spans from canonical positioned PDFs."""
    occurrences: dict[str, list[dict[str, str]]] = defaultdict(list)
    for volume in (2, 3, 4):
        with (canonical_root / f"volume_{volume}" / "page_occurrences.tsv").open(
            encoding="utf-8", newline=""
        ) as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                occurrences[row["page_id"]].append(row)
    result: list[SourceArticle] = []
    for volume in (2, 3, 4):
        pages_root = canonical_root / f"volume_{volume}" / "pages"
        for path in sorted(pages_root.glob("*.json.gz")):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                page_record = json.load(handle)
            page = page_record["positioned_page"]
            font_by_id = {str(font["font_id"]): font for font in page_record["representative_fonts"]}
            headings = [heading for heading in extract_headings(page, font_by_id) if heading["loc"]]
            headings.sort(key=lambda heading: min(_ints(heading["loc_run_indices"])))
            runs = page["positioned_text_runs"]
            for index, heading in enumerate(headings):
                start = min(_ints(heading["tibetan_run_indices"]))
                end = min(_ints(headings[index + 1]["tibetan_run_indices"])) if index + 1 < len(headings) else len(runs)
                page_id = str(page_record["page_id"])
                source_id = f"badw:pdf:{page_id}:{start}"
                page_occurrences = sorted(occurrences.get(page_id, []), key=lambda row: row["canonical_url"])
                result.append(SourceArticle(
                    source_id=source_id,
                    delivery_type="generated_pdf_span",
                    lemma=str(heading["loc"]),
                    homonym=str(heading.get("homonym", "")),
                    tibetan=str(heading["tibetan"]),
                    text=_runs_to_text(runs, start, end),
                    provenance={
                        "page_id": page_id,
                        "volume": volume,
                        "printed_page": page_record.get("printed_page"),
                        "source_sha256": page_record["representative_source"]["source_sha256"],
                        "canonical_urls": [row["canonical_url"] for row in page_occurrences],
                        "run_start": start,
                        "run_end_exclusive": end,
                        "loc_run_indices": heading["loc_run_indices"],
                        "tibetan_run_indices": heading["tibetan_run_indices"],
                    },
                ))
    return sorted(result, key=lambda item: item.source_id)


def build_indexes(entries: Iterable[LocalEntry]):
    latin: dict[str, list[LocalEntry]] = defaultdict(list)
    tibetan: dict[str, list[LocalEntry]] = defaultdict(list)
    page: dict[tuple[str, int], list[LocalEntry]] = defaultdict(list)
    all_entries = list(entries)
    for entry in all_entries:
        latin[lemma_key(entry.lemma)].append(entry)
        tibetan[tibetan_key(entry.tibetan)].append(entry)
        for number in entry.pages:
            page[(entry.volume, number)].append(entry)
    return all_entries, latin, tibetan, page


def score_candidates(
    source: SourceArticle,
    entries: list[LocalEntry],
    latin: dict[str, list[LocalEntry]],
    tibetan: dict[str, list[LocalEntry]],
    page: dict[tuple[str, int], list[LocalEntry]],
) -> list[dict[str, object]]:
    """Return every deterministic local-identity candidate and its evidence.

    This is deliberately an identity-only operation.  It does not compare an
    article's prose with WtSOCR and it does not normalize the historical LoC
    transliteration beyond Unicode/whitespace comparison used for headword
    identity.  Callers must retain the complete returned set: selecting a
    convenient best candidate would conceal ambiguity needed by Stage C.
    """
    candidates: set[LocalEntry] = set(latin.get(lemma_key(source.lemma), []))
    candidates.update(tibetan.get(tibetan_key(source.tibetan), []))
    if source.delivery_type == "generated_pdf_span":
        printed_page = source.provenance.get("printed_page")
        if printed_page:
            scan_page = {2: 239, 3: 521, 4: 869}[int(source.provenance["volume"])] + int(printed_page)
            candidates.update(page.get(("wts_1_34", scan_page), []))
            candidates.update(page.get(("wts_1_34", scan_page + 1), []))
    scored: list[dict[str, object]] = []
    for entry in candidates:
        latin_exact = lemma_key(source.lemma) == lemma_key(entry.lemma)
        tibetan_exact = bool(tibetan_key(source.tibetan)) and tibetan_key(source.tibetan) == tibetan_key(entry.tibetan)
        page_bonus = 0.0
        if source.delivery_type == "generated_pdf_span" and entry.volume == "wts_1_34":
            printed_page = int(source.provenance["printed_page"])
            scan_page = {2: 239, 3: 521, 4: 869}[int(source.provenance["volume"])] + printed_page
            if scan_page in entry.pages:
                page_bonus = 0.18
        score = (0.41 if latin_exact else 0.0) + (0.41 if tibetan_exact else 0.0) + page_bonus
        scored.append({
            "entry": entry,
            "score": round(score, 6),
            "latin_exact": latin_exact,
            "tibetan_exact": tibetan_exact,
            "printed_page_exact": bool(page_bonus),
        })
    scored.sort(key=lambda item: (-float(item["score"]), str(item["entry"].key)))
    for rank, candidate in enumerate(scored, start=1):
        candidate["rank"] = rank
    return scored


def score_article(
    source: SourceArticle,
    entries: list[LocalEntry],
    latin: dict[str, list[LocalEntry]],
    tibetan: dict[str, list[LocalEntry]],
    page: dict[tuple[str, int], list[LocalEntry]],
) -> dict[str, object]:
    """Classify only the best candidate while retaining all rows elsewhere."""
    scored = score_candidates(source, entries, latin, tibetan, page)
    if not scored:
        return {"matched": False, "confidence": "none", "candidate_count": 0}
    best = scored[0]
    margin = float(best["score"]) - float(scored[1]["score"]) if len(scored) > 1 else float(best["score"])
    if (best["latin_exact"] and best["tibetan_exact"] and margin >= 0.08) or (float(best["score"]) >= 0.70 and margin >= 0.12):
        confidence = "high"
    elif (best["latin_exact"] or best["tibetan_exact"]) and margin >= 0.04:
        confidence = "medium"
    else:
        confidence = "low"
    return {
        "matched": True,
        "confidence": confidence,
        "candidate_count": len(scored),
        "score": round(float(best["score"]), 6),
        "margin": round(margin, 6),
        "latin_exact": best["latin_exact"],
        "tibetan_exact": best["tibetan_exact"],
        "entry": best["entry"],
    }


def write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_source_articles(path: Path) -> Iterable[SourceArticle]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            yield SourceArticle(
                source_id=record["source_id"], delivery_type=record["delivery_type"],
                lemma=record["lemma"], homonym=record["homonym"], tibetan=record["tibetan"],
                text=record["source_text"], provenance=record["provenance"],
            )


def candidate_record(source: SourceArticle, candidate: dict[str, object]) -> dict[str, object]:
    """Serialize a candidate without leaking source text into tracked output."""
    entry = candidate["entry"]
    assert isinstance(entry, LocalEntry)
    return {
        "contract_version": CANDIDATE_CONTRACT_VERSION,
        "source_id": source.source_id,
        "delivery_type": source.delivery_type,
        "local_volume": entry.volume,
        "local_entry_id": entry.entry_id,
        "rank": candidate["rank"],
        "score": candidate["score"],
        "latin_exact": candidate["latin_exact"],
        "tibetan_exact": candidate["tibetan_exact"],
        "printed_page_exact": candidate["printed_page_exact"],
        "local_pages": list(entry.pages),
    }


def materialize_source_snapshot(
    source_jsonl: Path | None,
    html_jsonl: Path | None,
    canonical_root: Path | None,
    output_path: Path,
) -> int:
    """Materialize one deterministic input snapshot for offline identity work."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if source_jsonl is not None:
        previous = list(read_source_articles(source_jsonl))
        if [source.source_id for source in previous] != sorted(source.source_id for source in previous):
            raise ValueError(f"source snapshot is not ordered by source_id: {source_jsonl}")
        if len({source.source_id for source in previous}) != len(previous):
            raise ValueError(f"source snapshot has duplicate source_id values: {source_jsonl}")
        shutil.copyfile(source_jsonl, output_path)
        return len(previous)
    if html_jsonl is None or canonical_root is None:
        raise ValueError("either source_jsonl or both html_jsonl and canonical_root are required")
    sources = load_html_articles(html_jsonl) + load_pdf_articles(canonical_root)
    sources.sort(key=lambda item: item.source_id)
    write_jsonl(output_path, ({
        "contract_version": CONTRACT_VERSION, "source_id": source.source_id,
        "delivery_type": source.delivery_type, "lemma": source.lemma,
        "homonym": source.homonym, "tibetan": source.tibetan,
        "source_text": source.text, "provenance": source.provenance,
    } for source in sources))
    return len(sources)


def run(
    html_jsonl: Path | None, canonical_root: Path | None, qa_root: Path,
    output_root: Path, source_jsonl: Path | None = None,
) -> dict[str, object]:
    entries, latin, tibetan, page = build_indexes(load_local_entries(qa_root))
    output_root.mkdir(parents=True, exist_ok=True)
    source_path = output_root / "source_articles.jsonl"
    source_count = materialize_source_snapshot(
        source_jsonl, html_jsonl, canonical_root, source_path
    )
    counts: Counter[str] = Counter()
    fields = [
        "source_id", "delivery_type", "source_lemma", "source_homonym", "source_tibetan",
        "source_text_characters", "matched", "confidence", "candidate_count", "score", "margin",
        "latin_exact", "tibetan_exact", "local_volume", "local_entry_id",
        "local_lemma", "local_tibetan", "local_pages", "source_provenance",
    ]
    with (output_root / "matches.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for source in read_source_articles(source_path):
            match = score_article(source, entries, latin, tibetan, page)
            counts[f"{source.delivery_type}:{match['confidence']}"] += 1
            row: dict[str, object] = {
                "source_id": source.source_id, "delivery_type": source.delivery_type,
                "source_lemma": source.lemma, "source_homonym": source.homonym,
                "source_tibetan": source.tibetan, "source_text_characters": len(source.text),
                "matched": match["matched"], "confidence": match["confidence"],
                "candidate_count": match.get("candidate_count", 0), "score": match.get("score", ""),
                "margin": match.get("margin", ""),
                "latin_exact": match.get("latin_exact", ""), "tibetan_exact": match.get("tibetan_exact", ""),
                "local_volume": "", "local_entry_id": "", "local_lemma": "", "local_tibetan": "", "local_pages": "",
                "source_provenance": json.dumps(source.provenance, ensure_ascii=False, sort_keys=True),
            }
            if match["matched"]:
                entry = match["entry"]
                row.update({"local_volume": entry.volume, "local_entry_id": entry.entry_id,
                            "local_lemma": entry.lemma, "local_tibetan": entry.tibetan,
                            "local_pages": ",".join(map(str, entry.pages))})
            writer.writerow(row)
    candidate_rows: list[dict[str, object]] = []
    for source in read_source_articles(source_path):
        for candidate in score_candidates(source, entries, latin, tibetan, page):
            candidate_rows.append(candidate_record(source, candidate))
    write_jsonl(output_root / "candidate_evidence.jsonl", candidate_rows)
    summary = {"contract_version": CONTRACT_VERSION, "source_articles": source_count,
               "local_entries": len(entries), "match_counts": dict(sorted(counts.items())),
               "candidate_evidence_rows": len(candidate_rows)}
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html-jsonl", type=Path)
    parser.add_argument("--canonical-root", type=Path)
    parser.add_argument("--source-jsonl", type=Path,
                        help="reuse an existing deterministic source snapshot offline")
    parser.add_argument("--qa-root", default=ROOT / "release/current/qa", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    if args.source_jsonl is not None and (args.html_jsonl is not None or args.canonical_root is not None):
        parser.error("--source-jsonl cannot be combined with --html-jsonl or --canonical-root")
    if args.source_jsonl is None and (args.html_jsonl is None or args.canonical_root is None):
        parser.error("supply --source-jsonl or both --html-jsonl and --canonical-root")
    print(json.dumps(run(args.html_jsonl, args.canonical_root, args.qa_root, args.output_root,
                         source_jsonl=args.source_jsonl), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
