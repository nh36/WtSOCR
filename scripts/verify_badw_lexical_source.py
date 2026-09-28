#!/usr/bin/env python3
"""Bind BAdW parsed HTML and lexical records to an immutable source snapshot.

The raw BAdW cache and parser output remain ignored working material.  This
tool writes only small, deterministic provenance manifests: it proves that a
parsed database-article corpus corresponds exactly to the database objects
recorded by a frozen ``badw_source_snapshot`` and that later lexical source
spans stay within those exact parsed source fields.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from badw_source_snapshot import verify_snapshot
from validate_lexical_record_contract import read_jsonl, validate


CONTRACT_VERSION = "badw-verified-lexical-source-v1"
ROOT = Path(__file__).resolve().parents[1]


class VerificationError(ValueError):
    """A purported lexical source is not exactly reproducible from C8."""


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise VerificationError(f"path must be inside repository: {path}") from error


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _read_articles(path: Path) -> list[dict[str, Any]]:
    # Deliberately do not use splitlines(): U+2028 is preserved BAdW Unicode.
    articles: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                article = json.loads(line)
            except json.JSONDecodeError as error:
                raise VerificationError(f"article line {line_number}: invalid JSON: {error.msg}") from error
            if not isinstance(article, dict):
                raise VerificationError(f"article line {line_number}: expected object")
            articles.append(article)
    return articles


def _database_objects(snapshot_root: Path) -> dict[str, dict[str, str]]:
    index_path = snapshot_root / "cache_manifest_index.tsv"
    if not index_path.is_file():
        raise VerificationError(f"missing cache manifest index: {index_path}")
    expected: dict[str, dict[str, str]] = {}
    for row in _read_tsv(index_path):
        if not (
            row.get("valid_resource") == "true"
            and row.get("content_classification") == "database_article"
            and row.get("delivery_type") == "database_article"
        ):
            continue
        final_url = row.get("final_url", "")
        source_sha = row.get("source_sha256", "")
        if not final_url or len(source_sha) != 64:
            raise VerificationError(f"invalid database cache observation: {row.get('request_manifest_path', '')}")
        if row.get("object_exists") != "true" or row.get("object_sha256_matches") != "true":
            raise VerificationError(f"unverified cached database object: {final_url}")
        source_id = "badw:" + final_url
        item = {
            "source_identifier": source_id,
            "final_url": final_url,
            "source_sha256": source_sha,
            "object_path": row.get("object_path", ""),
            "request_key": row.get("request_key", ""),
        }
        if source_id in expected:
            raise VerificationError(f"duplicate valid database source identifier in snapshot: {source_id}")
        expected[source_id] = item
    if not expected:
        raise VerificationError("snapshot contains no valid database articles")
    return expected


def _article_inventory(articles: Iterable[dict[str, Any]], expected: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    observed: dict[str, dict[str, str]] = {}
    for ordinal, article in enumerate(articles, 1):
        source_id = article.get("source_identifier")
        source = article.get("source_object")
        if not isinstance(source_id, str) or not source_id:
            raise VerificationError(f"parsed article {ordinal} has no source_identifier")
        if source_id in observed:
            raise VerificationError(f"duplicate parsed source_identifier: {source_id}")
        if not isinstance(source, dict):
            raise VerificationError(f"parsed article {source_id} has no source_object")
        expected_item = expected.get(source_id)
        if expected_item is None:
            raise VerificationError(f"parsed article absent from source snapshot: {source_id}")
        final_url = source.get("final_url")
        source_sha = source.get("sha256")
        if final_url != expected_item["final_url"] or source_sha != expected_item["source_sha256"]:
            raise VerificationError(f"parsed source object disagrees with source snapshot: {source_id}")
        if not isinstance(article.get("article_source_text"), str):
            raise VerificationError(f"parsed article lacks article_source_text: {source_id}")
        observed[source_id] = expected_item
    missing = sorted(set(expected) - set(observed))
    if missing:
        raise VerificationError(f"parsed corpus omits {len(missing)} snapshot database articles (first: {missing[0]})")
    return [observed[source_id] for source_id in sorted(observed)]


def _manifest_payload(snapshot_root: Path, articles_path: Path, repo_root: Path) -> dict[str, Any]:
    snapshot = verify_snapshot(snapshot_root, repo_root)
    summary_path = snapshot_root / "source_snapshot.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expected = _database_objects(snapshot_root)
    articles = _read_articles(articles_path)
    inventory = _article_inventory(articles, expected)
    return {
        "contract_version": CONTRACT_VERSION,
        "source_snapshot_id": snapshot["snapshot_id"],
        "source_snapshot_path": _repo_relative(snapshot_root, repo_root),
        "source_snapshot_sha256": sha256(summary_path),
        "cache_manifest_index_sha256": summary["cache_manifest_index_sha256"],
        "parsed_articles_path": _repo_relative(articles_path, repo_root),
        "parsed_articles_sha256": sha256(articles_path),
        "parsed_article_count": len(inventory),
        "database_cache_object_count": len(expected),
        "article_source_objects": inventory,
    }


def create_verified_lexical_source(snapshot_root: Path, articles_path: Path, output_path: Path,
                                   repo_root: Path | None = None) -> dict[str, Any]:
    """Create an immutable, deterministic BAdW HTML source verification."""
    repo_root = repo_root or ROOT
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite verification manifest: {output_path}")
    payload = _manifest_payload(snapshot_root, articles_path, repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return payload


def verify_verified_lexical_source(manifest_path: Path, repo_root: Path | None = None) -> dict[str, Any]:
    """Recompute and verify a lexical-source manifest, entirely offline."""
    repo_root = repo_root or ROOT
    if not manifest_path.is_file():
        raise VerificationError(f"missing verified lexical source manifest: {manifest_path}")
    observed = json.loads(manifest_path.read_text(encoding="utf-8"))
    if observed.get("contract_version") != CONTRACT_VERSION:
        raise VerificationError(f"unsupported lexical source contract: {observed.get('contract_version')}")
    snapshot_path = repo_root / str(observed.get("source_snapshot_path") or "")
    articles_path = repo_root / str(observed.get("parsed_articles_path") or "")
    if not snapshot_path.is_dir() or not articles_path.is_file():
        raise VerificationError("verified lexical source paths are unavailable")
    recomputed = _manifest_payload(snapshot_path, articles_path, repo_root)
    if recomputed != observed:
        raise VerificationError("verified lexical source manifest no longer matches its frozen inputs")
    return {"verified": True, **recomputed, "verified_lexical_source_sha256": sha256(manifest_path)}


def _parsed_sources(manifest: dict[str, Any], repo_root: Path) -> dict[str, dict[str, Any]]:
    articles_path = repo_root / manifest["parsed_articles_path"]
    sources: dict[str, dict[str, Any]] = {}
    for article in _read_articles(articles_path):
        source_id = article["source_identifier"]
        if source_id in sources:
            raise VerificationError(f"duplicate parsed source_identifier: {source_id}")
        sources[source_id] = article
    return sources


def audit_lexical_records(records_path: Path, verified_manifest_path: Path,
                          repo_root: Path | None = None) -> dict[str, Any]:
    """Check every lexical source span against the verified parser source field."""
    repo_root = repo_root or ROOT
    verified = verify_verified_lexical_source(verified_manifest_path, repo_root)
    records = read_jsonl(records_path)
    errors = validate(records)
    if errors:
        raise VerificationError("invalid lexical records: " + "; ".join(errors[:3]))
    snapshots = {record["source_snapshot_id"] for record in records}
    if snapshots != {verified["source_snapshot_id"]}:
        raise VerificationError("lexical record snapshot id does not match verified source")
    expected = {item["source_identifier"]: item for item in verified["article_source_objects"]}
    sources = _parsed_sources(verified, repo_root)
    source_span_count = 0
    used_sources: set[str] = set()
    fields: set[str] = set()
    for record in records:
        for span in record["source_spans"]:
            source_span_count += 1
            source_id = span["source_id"]
            expected_item = expected.get(source_id)
            article = sources.get(source_id)
            if expected_item is None or article is None:
                raise VerificationError(f"record {record['id']} references source outside verified corpus: {source_id}")
            if span["source_sha256"] != expected_item["source_sha256"]:
                raise VerificationError(f"record {record['id']} source hash mismatch: {source_id}")
            field = span["field"]
            if field != "article_source_text":
                raise VerificationError(f"record {record['id']} uses unsupported parsed source field: {field}")
            text = article.get(field)
            if not isinstance(text, str) or not (0 <= span["start"] < span["end"] <= len(text)):
                raise VerificationError(f"record {record['id']} span is outside {source_id}:{field}")
            used_sources.add(source_id)
            fields.add(field)
    return {
        "contract_version": CONTRACT_VERSION,
        "source_snapshot_id": verified["source_snapshot_id"],
        "verified_lexical_source_sha256": verified["verified_lexical_source_sha256"],
        "records_path": _repo_relative(records_path, repo_root),
        "records_sha256": sha256(records_path),
        "record_count": len(records),
        "source_span_count": source_span_count,
        "used_source_object_count": len(used_sources),
        "source_fields": sorted(fields),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("verify-source", help="bind parsed HTML to a source snapshot")
    source.add_argument("--snapshot-root", type=Path, required=True)
    source.add_argument("--articles", type=Path, required=True)
    source.add_argument("--output", type=Path, required=True)
    audit = commands.add_parser("audit-records", help="check lexical spans against a verified source")
    audit.add_argument("--records", type=Path, required=True)
    audit.add_argument("--verified-source-manifest", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify-source":
            result = create_verified_lexical_source(args.snapshot_root, args.articles, args.output)
            report = {
                "database_cache_object_count": result["database_cache_object_count"],
                "output": args.output.as_posix(),
                "parsed_article_count": result["parsed_article_count"],
                "source_snapshot_id": result["source_snapshot_id"],
                "verified_source_manifest_sha256": sha256(args.output),
            }
        else:
            result = audit_lexical_records(args.records, args.verified_source_manifest)
            _write_json(args.output, result)
            report = result
    except (FileNotFoundError, FileExistsError, VerificationError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
