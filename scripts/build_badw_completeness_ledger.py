#!/usr/bin/env python3
"""Build and query a read-only, source-hash-bound BAdW completeness ledger.

The ledger consumes certified accounting outputs and an existing projection cache;
it never extracts or reparses source material. Database output belongs in ignored
work/ storage.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/badw_forensic_structure"
DEFAULT_DB = ROOT / "work/badw_completeness_ledger/ledger.sqlite"
EXPECTED = {
    "witnesses": 29877,
    "unassigned_alphabetic": 131068,
    "typed": 45273,
    "structural": 66214,
    "decoding": 9841,
    "meaningful_pending": 9740,
}
LATER_MEASURED = "109365 owners / 60 unresolved / 9309 pending; input hashes unreconciled, not certified"


class LedgerError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _headword(record: dict[str, Any]) -> str:
    value = record.get("reader", {}).get("headword", "")
    if isinstance(value, dict):
        return str(value.get("display") or value.get("loc") or "")
    return str(value)


def _jsonl_gz(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LedgerError(f"{path}:{number}: invalid JSON: {exc}") from exc


def _jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LedgerError(f"{path}:{number}: invalid JSON: {exc}") from exc


def _unique(rows: Iterable[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = row.get(key)
        if not identity or identity in result:
            raise LedgerError(f"{label}: missing or duplicate {key}: {identity!r}")
        result[identity] = row
    return result


def _read_entries(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    result = _unique(rows, "identity", "entries.tsv")
    for identity, row in result.items():
        if row.get("source_kind") not in {"html", "pdf"}:
            raise LedgerError(f"{identity}: invalid source_kind {row.get('source_kind')!r}")
        if len(row.get("text_sha256", "")) != 64:
            raise LedgerError(f"{identity}: invalid text SHA-256")
        for field, value in list(row.items()):
            if field not in {"identity", "source_kind", "text_sha256"}:
                try:
                    row[field] = int(value)
                except (ValueError, TypeError):
                    raise LedgerError(f"{identity}: non-integer statistic {field}={value!r}")
    return result


def _read_semantic_entries(path: Path, entries: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Join existing semantic-store summaries by identity and source hash."""
    semantic = _read_entries(path)
    if set(semantic) != set(entries):
        raise LedgerError(
            f"semantic-store witness set differs: missing={len(set(entries)-set(semantic))}, "
            f"extra={len(set(semantic)-set(entries))}"
        )
    for identity, row in semantic.items():
        source = entries[identity]
        if row["source_kind"] != source["source_kind"] or row["text_sha256"] != source["text_sha256"]:
            raise LedgerError(f"{identity}: semantic-store source kind/hash mismatch")
    return semantic


def _validate_manifest(data_dir: Path) -> dict[str, Any]:
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    for rel in (
        "data/badw_forensic_structure/entries.tsv",
        "data/badw_forensic_structure/header_accounting.json",
        "data/badw_forensic_structure/header_accounting.jsonl.gz",
        "data/badw_forensic_structure/pending_structure.jsonl.gz",
    ):
        expected = manifest.get("outputs_sha256", {}).get(rel)
        if not expected:
            raise LedgerError(f"manifest has no output hash for {rel}")
        actual = sha256((ROOT / rel).read_bytes())
        if actual != expected:
            raise LedgerError(f"manifest hash mismatch for {rel}: {actual} != {expected}")
    return manifest


def _projection_records(path: Path, entries: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            metrics = record.get("metrics", {})
            identity = metrics.get("identity")
            packet = record.get("packet", {})
            projection = record.get("projection", {})
            if not identity or identity in result:
                raise LedgerError(f"projection cache: missing or duplicate identity {identity!r}")
            if identity not in entries:
                raise LedgerError(f"projection cache contains unaccounted witness {identity}")
            text = packet.get("review_text")
            digest = sha256(text.encode("utf-8")) if isinstance(text, str) else None
            stated = packet.get("review_text_sha256")
            if not text or digest != stated:
                raise LedgerError(f"{identity}: cached source text hash mismatch")
            row = entries[identity]
            if digest != row["text_sha256"] or metrics.get("text_sha256") != digest:
                raise LedgerError(f"{identity}: projection and accounting source hashes differ")
            if metrics.get("source_kind") != row["source_kind"] or packet.get("source_kind") != row["source_kind"]:
                raise LedgerError(f"{identity}: source kind differs across projection and accounting")
            if projection.get("identity") != identity or projection.get("review_text_sha256") != digest:
                raise LedgerError(f"{identity}: semantic projection is not bound to cached source")
            result[identity] = {
                "text": text,
                "source_kind": row["source_kind"],
                "headword": _headword(record),
                "projection_status": "projected" if record.get("reader") and record.get("entry") else "incomplete",
                "projection_contract": projection.get("contract_version", ""),
                "projection_evidence": "certified corpus-structure projection cache",
            }
    extra = set(result) - set(entries)
    if extra:
        raise LedgerError(f"projection cache has {len(extra)} unknown witnesses")
    bad = [identity for identity, row in result.items() if row["projection_status"] != "projected"]
    if bad:
        raise LedgerError(f"incomplete projections: {bad[:5]}")
    return result


def _supplement_projections(path: Path, entries: dict[str, dict[str, Any]],
                            projections: dict[str, dict[str, Any]]) -> None:
    """Fill only missing zero-gap historical exceptions from the later semantic cache."""
    missing = set(entries) - set(projections)
    if not missing:
        return
    targets = {
        "badw:https://wts-digital.badw.de/lemma/ka%20chen/1",
        "badw:https://wts-digital.badw.de/lemma/kos%20s%C3%B1u%E1%B9%85/1",
    }
    if not missing <= targets:
        raise LedgerError(f"projection/accounting witness set differs: missing={len(missing)}")
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            metrics = record.get("metrics", {})
            identity = metrics.get("identity")
            if identity not in missing:
                continue
            packet = record.get("packet", {})
            projection = record.get("projection", {})
            text = packet.get("review_text")
            digest = sha256(text.encode("utf-8")) if isinstance(text, str) else None
            entry = entries[identity]
            if (not text or digest != entry["text_sha256"]
                    or packet.get("review_text_sha256") != digest
                    or metrics.get("text_sha256") != digest
                    or metrics.get("source_kind") != entry["source_kind"]
                    or packet.get("source_kind") != entry["source_kind"]
                    or projection.get("identity") != identity
                    or projection.get("review_text_sha256") != digest):
                raise LedgerError(f"{identity}: later semantic projection is not source-hash aligned")
            projections[identity] = {
                "text": text, "source_kind": entry["source_kind"], "headword": _headword(record),
                "projection_status": "projected",
                "projection_contract": projection.get("contract_version", ""),
                "projection_evidence": "later semantic-hierarchy cache; nested arrow/link correction",
            }
            missing.remove(identity)
            if not missing:
                break
    if missing:
        raise LedgerError(f"later semantic projection cache lacks {len(missing)} exceptions: {sorted(missing)}")


def _check_ordered_spans(identity: str, spans: list[dict[str, Any]], limit: int, label: str) -> None:
    ordered = sorted(spans, key=lambda x: (x["start"], x["end"]))
    previous_end = -1
    for span in ordered:
        start, end = span["start"], span["end"]
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or end > limit:
            raise LedgerError(f"{identity}: invalid {label} span [{start},{end})")
        if start < previous_end:
            raise LedgerError(f"{identity}: overlapping {label} intervals at [{start},{end})")
        previous_end = end


def build_ledger(
    *, entries_path: Path, header_json_path: Path, header_jsonl_path: Path,
    pending_path: Path, projection_path: Path, manifest_path: Path,
    database_path: Path, supplemental_projection_path: Path | None = None,
    semantic_entries_path: Path | None = None,
    enforce_certified_totals: bool = True,
) -> dict[str, Any]:
    """Validate inputs and atomically replace a SQLite ledger."""
    data_dir = entries_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data_dir == DATA and manifest_path == DATA / "manifest.json":
        _validate_manifest(data_dir)

    entries = _read_entries(entries_path)
    semantic_entries = _read_semantic_entries(semantic_entries_path, entries) if semantic_entries_path else {}
    projections = _projection_records(projection_path, entries)
    if supplemental_projection_path is not None:
        _supplement_projections(supplemental_projection_path, entries, projections)
    if set(projections) != set(entries):
        raise LedgerError(f"projection/accounting witness set differs: missing={len(set(entries)-set(projections))}")
    header_rows = _unique(_jsonl_gz(header_jsonl_path), "identity", "header accounting")
    missing_header = set(entries) - set(header_rows)
    extra_header = set(header_rows) - set(entries)
    if extra_header:
        raise LedgerError(f"header accounting has {len(extra_header)} unknown witnesses")
    # One certified witness has exactly zero unassigned characters and was omitted
    # from the sparse gap stream. Represent that omission as an empty gap list.
    for identity in missing_header:
        row = entries[identity]
        if row["unassigned_characters"] != 0 or row["unassigned_alphabetic"] != 0:
            raise LedgerError(f"header accounting is missing nonempty witness {identity}")
        header_rows[identity] = {
            "identity": identity, "source_kind": row["source_kind"],
            "source_sha256": row["text_sha256"], "gaps": [], "source_candidates": [],
        }

    pending_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for span in _jsonl_gz(pending_path):
        identity = span.get("identity")
        if identity not in entries:
            raise LedgerError(f"pending spans contain unknown witness {identity!r}")
        pending_by_id[identity].append(span)

    aggregate_gap_alpha = 0
    aggregate_gap_chars = 0
    aggregate_pending_alpha = 0
    all_gaps: dict[str, list[dict[str, Any]]] = {}
    for identity, entry in entries.items():
        h = header_rows[identity]
        if h.get("source_kind") != entry["source_kind"] or h.get("source_sha256") != entry["text_sha256"]:
            raise LedgerError(f"{identity}: header accounting source kind/hash mismatch")
        text = projections[identity]["text"]
        gaps = h.get("gaps", [])
        _check_ordered_spans(identity, gaps, len(text), "accounting")
        gap_chars = sum(g["end"] - g["start"] for g in gaps)
        gap_alpha = sum(g.get("alphabetic_characters", 0) for g in gaps)
        if gap_chars != entry["unassigned_characters"] or gap_alpha != entry["unassigned_alphabetic"]:
            raise LedgerError(f"{identity}: accounting interval totals disagree with entry stats")
        aggregate_gap_chars += gap_chars
        aggregate_gap_alpha += gap_alpha
        all_gaps[identity] = gaps

        pending = sorted(pending_by_id.get(identity, []), key=lambda x: (x["start"], x["end"]))
        _check_ordered_spans(identity, pending, len(text), "pending meaningful")
        for span in pending:
            if span.get("source_kind") != entry["source_kind"] or span.get("source_sha256") != entry["text_sha256"]:
                raise LedgerError(f"{identity}: pending source kind/hash mismatch")
            start, end = span["start"], span["end"]
            literal = span.get("literal")
            if not isinstance(literal, str) or text[start:end] != literal:
                raise LedgerError(f"{identity}: pending literal does not match exact Unicode source offsets")
            alpha = sum(ch.isalpha() for ch in literal)
            if alpha != span.get("alphabetic_characters"):
                raise LedgerError(f"{identity}: pending alphabetic count mismatch")
            if not any(g["start"] <= start and end <= g["end"] for g in gaps):
                raise LedgerError(f"{identity}: pending span is outside all unassigned accounting intervals")
            aggregate_pending_alpha += alpha
    if aggregate_gap_chars != sum(e["unassigned_characters"] for e in entries.values()):
        raise LedgerError("global unassigned character count mismatch")

    header_accounting = json.loads(header_json_path.read_text(encoding="utf-8"))
    alpha_rows = header_accounting.get("alphabetic_characters", [])
    alpha_families: dict[str, int] = defaultdict(int)
    for row in alpha_rows:
        alpha_families[row["family"]] += row["count"]
    typed = sum(v for k, v in alpha_families.items() if k.startswith("typed_"))
    structural = alpha_families.get("source_structural_label", 0)
    decoding = alpha_families.get("source_decoding_residue", 0)
    partition = {
        "typed": typed, "structural": structural, "decoding": decoding,
        "meaningful_pending": aggregate_pending_alpha,
    }
    unassigned = sum(partition.values())
    if unassigned != aggregate_gap_alpha:
        raise LedgerError(f"partition sums to {unassigned}, gap accounting says {aggregate_gap_alpha}")
    report = {
        "witnesses": len(entries), "unassigned_characters": aggregate_gap_chars,
        "unassigned_alphabetic": aggregate_gap_alpha, **partition,
        "pending_spans": sum(map(len, pending_by_id.values())),
        "later_measured_replay": LATER_MEASURED,
        "certification": "certified checked-in accounting; later measured replay is unreconciled",
    }
    if enforce_certified_totals:
        for field, expected in EXPECTED.items():
            if report[field] != expected:
                raise LedgerError(f"certified {field} total {report[field]} != expected {expected}")

    database_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = database_path.with_suffix(database_path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE witness (
                identity TEXT PRIMARY KEY, headword TEXT NOT NULL, source_kind TEXT NOT NULL,
                source_sha256 TEXT NOT NULL, projection_status TEXT NOT NULL,
                projection_contract TEXT NOT NULL, projection_evidence TEXT NOT NULL,
                statistics_json TEXT NOT NULL, semantic_statistics_json TEXT NOT NULL
            );
            CREATE TABLE accounting_span (
                identity TEXT NOT NULL REFERENCES witness(identity), start INTEGER NOT NULL,
                end INTEGER NOT NULL, family TEXT NOT NULL, alphabetic_characters INTEGER NOT NULL,
                PRIMARY KEY(identity,start,end)
            );
            CREATE TABLE meaningful_span (
                identity TEXT NOT NULL REFERENCES witness(identity), start INTEGER NOT NULL,
                end INTEGER NOT NULL, literal TEXT NOT NULL, alphabetic_characters INTEGER NOT NULL,
                family TEXT NOT NULL, source_grammar_family TEXT NOT NULL,
                unresolved_reason TEXT NOT NULL, context TEXT NOT NULL,
                PRIMARY KEY(identity,start,end)
            );
            CREATE INDEX meaningful_family ON meaningful_span(family);
            CREATE INDEX witness_headword ON witness(headword);
        """)
        for key, value in report.items():
            connection.execute("INSERT INTO metadata VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))
        connection.execute("INSERT INTO metadata VALUES (?,?)", ("manifest_baseline_commit", json.dumps(manifest.get("baseline_commit"))))
        connection.execute("INSERT INTO metadata VALUES (?,?)", ("semantic_store_sha256", json.dumps(manifest.get("semantic_store_sha256"))))
        if semantic_entries_path:
            connection.execute("INSERT INTO metadata VALUES (?,?)", ("semantic_entries_path", json.dumps(str(semantic_entries_path))))
        for identity, entry in entries.items():
            projection = projections[identity]
            connection.execute(
                "INSERT INTO witness VALUES (?,?,?,?,?,?,?,?,?)",
                (identity, projection["headword"], entry["source_kind"], entry["text_sha256"],
                 projection["projection_status"], projection["projection_contract"],
                 projection["projection_evidence"],
                 json.dumps({k: v for k, v in entry.items() if k not in {"identity", "source_kind", "text_sha256"}}, sort_keys=True),
                 json.dumps({k: v for k, v in semantic_entries.get(identity, {}).items()
                             if k not in {"identity", "source_kind", "text_sha256"}}, sort_keys=True)),
            )
        for identity, row in header_rows.items():
            for gap in row.get("gaps", []):
                connection.execute("INSERT INTO accounting_span VALUES (?,?,?,?,?)",
                                   (identity, gap["start"], gap["end"], gap["family"], gap.get("alphabetic_characters", 0)))
        for identity, spans in pending_by_id.items():
            for span in spans:
                connection.execute("INSERT INTO meaningful_span VALUES (?,?,?,?,?,?,?,?,?)",
                                   (identity, span["start"], span["end"], span["literal"], span["alphabetic_characters"],
                                    span["family"], span.get("source_grammar_family", ""),
                                    span.get("unresolved_reason", ""), span.get("context", "")))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    temporary.replace(database_path)
    return report


def query_witness(database_path: Path, identity: str) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        witness = connection.execute("SELECT * FROM witness WHERE identity=?", (identity,)).fetchone()
        if witness is None:
            raise LedgerError(f"no witness with identity {identity!r}")
        result = dict(witness)
        result["statistics"] = json.loads(result.pop("statistics_json"))
        result["semantic_statistics"] = json.loads(result.pop("semantic_statistics_json"))
        result["accounting_spans"] = [dict(row) for row in connection.execute(
            "SELECT start,end,family,alphabetic_characters FROM accounting_span WHERE identity=? ORDER BY start", (identity,))]
        result["meaningful_spans"] = [dict(row) for row in connection.execute(
            "SELECT start,end,literal,alphabetic_characters,family,source_grammar_family,unresolved_reason,context "
            "FROM meaningful_span WHERE identity=? ORDER BY start", (identity,))]
        return result
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="validate certified inputs and write SQLite ledger")
    build.add_argument("--database", type=Path, default=DEFAULT_DB)
    build.add_argument("--projection-cache", type=Path, default=ROOT / "work/badw_corpus_structure/projections.jsonl")
    build.add_argument("--supplemental-projection-cache", type=Path,
                       default=ROOT / "work/badw_semantic_hierarchy/projections.jsonl")
    query = sub.add_parser("query", help="show one witness and its outstanding meaningful spans")
    query.add_argument("--database", type=Path, default=DEFAULT_DB)
    query.add_argument("identity")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            report = build_ledger(
                entries_path=DATA / "entries.tsv", header_json_path=DATA / "header_accounting.json",
                header_jsonl_path=DATA / "header_accounting.jsonl.gz", pending_path=DATA / "pending_structure.jsonl.gz",
                projection_path=args.projection_cache, manifest_path=DATA / "manifest.json", database_path=args.database,
                supplemental_projection_path=args.supplemental_projection_cache,
                semantic_entries_path=ROOT / "data/badw_semantic_hierarchy/entries.tsv",
            )
            print(json.dumps({"database": str(args.database), **report}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(query_witness(args.database, args.identity), ensure_ascii=False, indent=2))
    except (LedgerError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"ledger error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
