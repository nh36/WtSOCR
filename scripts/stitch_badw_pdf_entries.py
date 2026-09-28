#!/usr/bin/env python3
"""Join BAdW page-local PDF entry witnesses across verified print-page edges.

This preserves positioned source spans. It does not parse senses or citations,
and an article ending at the final recovered page remains explicitly open.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
from functools import lru_cache

from badw_canonical_pages import stable_json_bytes
from extract_badw_pdf_entries import _body_end, _reading


CONTRACT_VERSION = "badw-pdf-article-witness-v1"


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _span(page: dict, canonical_object: str, start: int, end: int, role: str,
          join_method: str = "") -> dict:
    runs = page["positioned_page"]["positioned_text_runs"]
    if not 0 <= start < end <= len(runs):
        raise ValueError(f"invalid source span {page['page_id']}:{start}:{end}")
    selected = runs[start:end]
    source_text = "".join(str(run["decoded_unicode"]) for run in selected)
    unknown = [
        {"run_index": int(run["run_index"]), "cid_hex": glyph["cid_hex"],
         "font_id": run["font_id"], "glyph_signature": glyph["glyph_signature"]}
        for run in selected for glyph in run["glyphs"] if glyph["unknown"]
    ]
    return {
        "page_id": page["page_id"], "volume": page["volume"],
        "printed_page": page.get("printed_page"), "canonical_object": canonical_object,
        "representative_pdf_url": page["representative_source"]["canonical_url"],
        "representative_pdf_sha256": page["representative_source"]["source_sha256"],
        "visible_body_sha256": page["visible_body_sha256"],
        "run_start": start, "run_end_exclusive": end, "segment_role": role,
        "join_method": join_method, "source_text_sha256": sha256(source_text.encode("utf-8")).hexdigest(),
        "source_faithful_text": source_text, "derived_reading_text": _reading(selected),
        "unknown_glyphs": unknown,
    }


def _linked(previous: dict | None, current: dict) -> str:
    if previous is None:
        return ""
    if (
        previous["volume"] != current["volume"]
        or int(previous["printed_page"]) + 1 != int(current["printed_page"])
        or previous["successor_page_id"] != current["page_id"]
        or current["predecessor_page_id"] != previous["page_id"]
    ):
        return ""
    if int(previous["successor_overlap_observations"]) or int(current["predecessor_overlap_observations"]):
        return "observed_pdf_overlap"
    return "reciprocal_print_page_adjacency"


def stitch_volume(pages: list[tuple[dict, dict, list[dict], dict]]) -> tuple[list[dict], list[dict], Counter]:
    """Compose entry starts and page-leading continuations, without inferred text edits."""
    articles: list[dict] = []
    unassigned: list[dict] = []
    counts: Counter = Counter()
    active: dict | None = None
    previous: dict | None = None

    def finish(reason: str) -> None:
        nonlocal active
        if active is None:
            return
        active["ending_status"] = reason
        active["end_printed_page"] = active["source_spans"][-1]["printed_page"]
        active["source_faithful_text"] = "".join(s["source_faithful_text"] for s in active["source_spans"])
        active["derived_reading_text"] = "\n".join(s["derived_reading_text"] for s in active["source_spans"])
        active["unknown_glyphs"] = [
            {"page_id": s["page_id"], **glyph}
            for s in active["source_spans"] for glyph in s["unknown_glyphs"]
        ]
        counts[f"ending_{reason}"] += 1
        articles.append(active)
        active = None

    for row, page, entries, diagnostic in pages:
        if row["page_id"] != page["page_id"] or row["page_id"] != diagnostic["page_id"]:
            raise ValueError("page/diagnostic identity mismatch")
        canonical_object = row["canonical_object"]
        body_end, footer_evidence = _body_end(page["positioned_page"]["positioned_text_runs"], page.get("printed_page"))
        if footer_evidence != "positioned_footer" or body_end != int(diagnostic["body_run_end"]):
            raise ValueError(f"unverified body boundary: {page['page_id']}")
        entries = sorted(entries, key=lambda entry: int(entry["source_span"]["run_start"]))
        if len(entries) != int(diagnostic["entry_count"]):
            raise ValueError(f"entry count mismatch: {page['page_id']}")
        lead_end = int(entries[0]["source_span"]["run_start"]) if entries else body_end
        if lead_end != int(diagnostic["leading_unassigned_runs"]):
            raise ValueError(f"leading-run mismatch: {page['page_id']}")
        cursor = lead_end
        for entry in entries:
            source = entry["source_span"]
            start, end = int(source["run_start"]), int(source["run_end_exclusive"])
            if start != cursor or end <= start or end > body_end:
                raise ValueError(f"entry coverage gap/overlap: {page['page_id']}")
            cursor = end
        if entries and cursor != body_end:
            raise ValueError(f"uncovered article text: {page['page_id']}")
        link = _linked(previous, row)
        if active and not link:
            finish("open_at_page_gap")
        if lead_end:
            if int(diagnostic["section_headers"]):
                # A printed alphabet divider is not an article continuation.
                if lead_end != 1:
                    raise ValueError(f"unaccounted section-header material: {page['page_id']}")
                if active:
                    finish("bounded_by_section_divider")
                counts["section_divider_pages"] += 1
            else:
                lead = _span(page, canonical_object, 0, lead_end, "page_leading_continuation", link)
                if active and link:
                    active["source_spans"].append(lead)
                    counts[f"joined_{link}"] += 1
                else:
                    unassigned.append(lead)
                    counts["unassigned_leading_fragments"] += 1
        elif active and entries:
            finish("bounded_by_next_page_heading")

        for entry in entries:
            source = entry["source_span"]
            start, end = int(source["run_start"]), int(source["run_end_exclusive"])
            if (
                entry["page_id"] != page["page_id"]
                or source["canonical_object"] != canonical_object
                or source["visible_body_sha256"] != page["visible_body_sha256"]
                or source["representative_pdf_sha256"] != page["representative_source"]["source_sha256"]
            ):
                raise ValueError(f"entry source identity mismatch: {entry['id']}")
            segment = _span(page, canonical_object, start, end, "entry_start")
            if segment["source_faithful_text"] != entry["source_faithful_text"]:
                raise ValueError(f"entry replay mismatch: {entry['id']}")
            if active:
                finish("bounded_by_next_heading")
            active = {
                "contract_version": CONTRACT_VERSION, "id": entry["id"],
                "volume": entry["volume"], "start_printed_page": entry["printed_page"],
                "loc_headword": entry["loc_headword"],
                "loc_headword_reading": entry["loc_headword_reading"],
                "tibetan_headword": entry["tibetan_headword"],
                "homonym": entry["homonym"], "entry_start_source_span": source,
                "source_spans": [segment], "ending_status": "",
                "end_printed_page": None, "source_faithful_text": "",
                "derived_reading_text": "", "unknown_glyphs": [],
            }
        previous = row
    finish("open_after_last_recovered_page")
    return articles, unassigned, counts


def build(canonical_root: Path, page_entries_root: Path, output_root: Path) -> dict:
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite output: {output_root}")
    extraction_summary = json.loads((page_entries_root / "summary.json").read_text(encoding="utf-8"))
    expected_indexes = extraction_summary.get("canonical_index_sha256")
    if not isinstance(expected_indexes, dict):
        raise ValueError("page-entry extraction lacks canonical index hashes; rebuild it from the intended source")
    for volume in (2, 3, 4):
        key = f"volume_{volume}/canonical_pages.tsv"
        actual = _file_sha256(canonical_root / key)
        if expected_indexes.get(key) != actual:
            raise ValueError(f"page-entry/canonical snapshot mismatch: {key}")
    output_root.mkdir(parents=True)
    entries_path = page_entries_root / "pdf_page_entries.jsonl.gz"
    diagnostics_path = page_entries_root / "page_diagnostics.tsv"
    entries_by_page: dict[str, list[dict]] = defaultdict(list)
    with gzip.open(entries_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            entry = json.loads(line)
            entries_by_page[entry["page_id"]].append(entry)
    with diagnostics_path.open(encoding="utf-8", newline="") as handle:
        diagnostic_rows = list(csv.DictReader(handle, delimiter="\t"))
    diagnostics = {row["page_id"]: row for row in diagnostic_rows}
    if len(diagnostics) != len(diagnostic_rows):
        raise ValueError("duplicate page diagnostics")
    input_hashes = {
        "pdf_page_entries.jsonl.gz": _file_sha256(entries_path),
        "page_diagnostics.tsv": _file_sha256(diagnostics_path),
    }
    counts: Counter = Counter()
    logical_hash = sha256()
    unassigned_hash = sha256()
    attributions: list[dict[str, object]] = []
    with (output_root / "pdf_article_witnesses.jsonl.gz").open("wb") as raw, (
        output_root / "unassigned_page_fragments.jsonl.gz"
    ).open("wb") as unassigned_raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed, gzip.GzipFile(
            filename="", mode="wb", fileobj=unassigned_raw, mtime=0
        ) as unassigned_compressed:
            for volume in (2, 3, 4):
                root = canonical_root / f"volume_{volume}"
                index_path = root / "canonical_pages.tsv"
                input_hashes[f"volume_{volume}/canonical_pages.tsv"] = _file_sha256(index_path)
                with index_path.open(encoding="utf-8", newline="") as handle:
                    rows = sorted(csv.DictReader(handle, delimiter="\t"), key=lambda row: int(row["printed_page"]))
                pages = []
                for row in rows:
                    path = root / row["canonical_object"]
                    with gzip.open(path, "rt", encoding="utf-8") as handle:
                        page = json.load(handle)
                    visible_hash = sha256(str(page["source_faithful_decoded_text"]).encode("utf-8")).hexdigest()
                    if visible_hash != page["visible_body_sha256"] or visible_hash != row["visible_body_sha256"]:
                        raise ValueError(f"canonical page hash mismatch: {path}")
                    row["canonical_object"] = path.relative_to(canonical_root).as_posix()
                    pages.append((row, page, entries_by_page.pop(row["page_id"], []), diagnostics.pop(row["page_id"])))
                articles, unassigned, volume_counts = stitch_volume(pages)
                counts.update(volume_counts)
                counts[f"volume_{volume}_articles"] = len(articles)
                counts[f"volume_{volume}_unassigned_fragments"] = len(unassigned)
                counts[f"volume_{volume}_pages"] = len(pages)
                for article in articles:
                    blob = stable_json_bytes(article) + b"\n"
                    compressed.write(blob)
                    logical_hash.update(blob)
                    counts["article_source_spans"] += len(article["source_spans"])
                    counts["article_unknown_glyph_occurrences"] += len(article["unknown_glyphs"])
                    for span in article["source_spans"][1:]:
                        attributions.append({
                            "article_id": article["id"],
                            "loc_headword": article["loc_headword"],
                            "start_printed_page": article["start_printed_page"],
                            "continuation_page": span["printed_page"],
                            "continuation_page_id": span["page_id"],
                            "run_start": span["run_start"],
                            "run_end_exclusive": span["run_end_exclusive"],
                            "join_method": span["join_method"],
                            "source_text_sha256": span["source_text_sha256"],
                        })
                for fragment in unassigned:
                    blob = stable_json_bytes(fragment) + b"\n"
                    unassigned_compressed.write(blob)
                    unassigned_hash.update(blob)
    if entries_by_page or diagnostics:
        raise ValueError(f"unmatched page entries/diagnostics: {len(entries_by_page)}/{len(diagnostics)}")
    attribution_path = output_root / "continuation_attributions.tsv"
    with attribution_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "article_id", "loc_headword", "start_printed_page", "continuation_page",
            "continuation_page_id", "run_start", "run_end_exclusive", "join_method",
            "source_text_sha256",
        ], delimiter="\t")
        writer.writeheader()
        writer.writerows(attributions)
    summary = {
        "contract_version": CONTRACT_VERSION,
        "source_page_entries": str(page_entries_root / "pdf_page_entries.jsonl.gz"),
        "input_sha256": input_hashes,
        "continuation_attributions_sha256": _file_sha256(attribution_path),
        "article_logical_sha256": logical_hash.hexdigest(),
        "unassigned_logical_sha256": unassigned_hash.hexdigest(),
        "counts": dict(sorted(counts.items())),
    }
    (output_root / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return summary


def verify_output(output_root: Path) -> dict:
    """Check deterministic output hashes and internal source-span invariants offline."""
    summary = json.loads((output_root / "summary.json").read_text(encoding="utf-8"))
    if summary["contract_version"] != CONTRACT_VERSION:
        raise ValueError("unsupported article-witness contract")
    seen_ids: set[str] = set()
    counts: Counter = Counter()
    expected_attributions: list[dict[str, str]] = []
    for filename, hash_field in (
        ("pdf_article_witnesses.jsonl.gz", "article_logical_sha256"),
        ("unassigned_page_fragments.jsonl.gz", "unassigned_logical_sha256"),
    ):
        digest = sha256()
        with gzip.open(output_root / filename, "rb") as handle:
            for line in handle:
                digest.update(line)
                record = json.loads(line)
                if filename.startswith("pdf_article"):
                    article_id = record["id"]
                    if article_id in seen_ids:
                        raise ValueError(f"duplicate article ID: {article_id}")
                    seen_ids.add(article_id)
                    spans = record["source_spans"]
                    if not spans or spans[0]["segment_role"] != "entry_start":
                        raise ValueError(f"missing entry start: {article_id}")
                    if any(span["segment_role"] != "page_leading_continuation" for span in spans[1:]):
                        raise ValueError(f"unexpected continuation role: {article_id}")
                    if record["source_faithful_text"] != "".join(span["source_faithful_text"] for span in spans):
                        raise ValueError(f"article source text mismatch: {article_id}")
                    if record["derived_reading_text"] != "\n".join(span["derived_reading_text"] for span in spans):
                        raise ValueError(f"article reading mismatch: {article_id}")
                    if record["end_printed_page"] != spans[-1]["printed_page"]:
                        raise ValueError(f"article end-page mismatch: {article_id}")
                    expected_unknown = [
                        {"page_id": span["page_id"], **glyph}
                        for span in spans for glyph in span["unknown_glyphs"]
                    ]
                    if record["unknown_glyphs"] != expected_unknown:
                        raise ValueError(f"unknown-glyph inventory mismatch: {article_id}")
                    for span in spans[1:]:
                        expected_attributions.append({
                            "article_id": article_id,
                            "loc_headword": str(record["loc_headword"]),
                            "start_printed_page": str(record["start_printed_page"]),
                            "continuation_page": str(span["printed_page"]),
                            "continuation_page_id": str(span["page_id"]),
                            "run_start": str(span["run_start"]),
                            "run_end_exclusive": str(span["run_end_exclusive"]),
                            "join_method": str(span["join_method"]),
                            "source_text_sha256": str(span["source_text_sha256"]),
                        })
                    counts["articles"] += 1
                    counts["article_source_spans"] += len(spans)
                    counts["article_unknown_glyph_occurrences"] += len(expected_unknown)
                else:
                    counts["unassigned_leading_fragments"] += 1
                    spans = [record]
                for span in spans:
                    if sha256(span["source_faithful_text"].encode("utf-8")).hexdigest() != span["source_text_sha256"]:
                        raise ValueError(f"source span hash mismatch: {span['page_id']}")
        if digest.hexdigest() != summary[hash_field]:
            raise ValueError(f"logical output hash mismatch: {filename}")
    for key in ("article_source_spans", "article_unknown_glyph_occurrences", "unassigned_leading_fragments"):
        if counts[key] != summary["counts"].get(key, 0):
            raise ValueError(f"output count mismatch: {key}")
    if counts["articles"] != sum(summary["counts"][f"volume_{v}_articles"] for v in (2, 3, 4)):
        raise ValueError("article count mismatch")
    if "continuation_attributions_sha256" in summary:
        path = output_root / "continuation_attributions.tsv"
        if _file_sha256(path) != summary["continuation_attributions_sha256"]:
            raise ValueError("continuation attribution hash mismatch")
        with path.open(encoding="utf-8", newline="") as handle:
            observed_attributions = list(csv.DictReader(handle, delimiter="\t"))
        if observed_attributions != expected_attributions:
            raise ValueError("continuation attributions do not match article spans")
        counts["continuation_attributions"] = len(observed_attributions)
    return dict(sorted(counts.items()))


def verify_source(output_root: Path, canonical_root: Path) -> dict:
    """Replay every witness span against the pinned canonical positioned pages."""
    counts = verify_output(output_root)
    summary = json.loads((output_root / "summary.json").read_text(encoding="utf-8"))
    known: dict[str, dict] = {}
    for volume in (2, 3, 4):
        index = canonical_root / f"volume_{volume}" / "canonical_pages.tsv"
        key = f"volume_{volume}/canonical_pages.tsv"
        if _file_sha256(index) != summary["input_sha256"][key]:
            raise ValueError(f"canonical page index hash mismatch: {key}")
        with index.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                relative = f"volume_{volume}/{row['canonical_object']}"
                if relative in known:
                    raise ValueError(f"duplicate canonical object: {relative}")
                known[relative] = row

    @lru_cache(maxsize=4)
    def page_for(relative: str) -> dict:
        if relative not in known:
            raise ValueError(f"unregistered canonical object: {relative}")
        with gzip.open(canonical_root / relative, "rt", encoding="utf-8") as handle:
            page = json.load(handle)
        visible = page["source_faithful_decoded_text"]
        if sha256(visible.encode("utf-8")).hexdigest() != page["visible_body_sha256"]:
            raise ValueError(f"canonical visible text hash mismatch: {relative}")
        positioned = page["positioned_page"]
        if positioned["visible_text"] != visible or sha256(stable_json_bytes(positioned)).hexdigest() != page["representative_positioned_sha256"]:
            raise ValueError(f"canonical positioned page hash mismatch: {relative}")
        return page

    replayed = 0
    for filename in ("pdf_article_witnesses.jsonl.gz", "unassigned_page_fragments.jsonl.gz"):
        with gzip.open(output_root / filename, "rt", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                spans = record["source_spans"] if filename.startswith("pdf_article") else [record]
                for span in spans:
                    relative = span["canonical_object"]
                    page = page_for(relative)
                    row = known[relative]
                    if page["page_id"] != row["page_id"] or page["visible_body_sha256"] != row["visible_body_sha256"]:
                        raise ValueError(f"canonical page identity mismatch: {relative}")
                    expected = _span(page, relative, span["run_start"], span["run_end_exclusive"],
                                     span["segment_role"], span["join_method"])
                    if span != expected:
                        raise ValueError(f"source replay mismatch: {relative}")
                    replayed += 1
    if replayed != counts["article_source_spans"] + counts.get("unassigned_leading_fragments", 0):
        raise ValueError("replayed span count mismatch")
    return {**counts, "replayed_source_spans": replayed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-root", type=Path)
    parser.add_argument("--page-entries-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--verify-output-root", type=Path)
    parser.add_argument("--verify-source-root", type=Path)
    args = parser.parse_args()
    if args.verify_source_root:
        if not args.canonical_root or args.page_entries_root or args.output_root or args.verify_output_root:
            parser.error("--verify-source-root requires --canonical-root and no build/output verification arguments")
        result = verify_source(args.verify_source_root, args.canonical_root)
    elif args.verify_output_root:
        if args.canonical_root or args.page_entries_root or args.output_root:
            parser.error("--verify-output-root cannot be combined with build arguments")
        result = verify_output(args.verify_output_root)
    else:
        if not all((args.canonical_root, args.page_entries_root, args.output_root)):
            parser.error("build requires --canonical-root, --page-entries-root, and --output-root")
        result = build(args.canonical_root, args.page_entries_root, args.output_root)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
