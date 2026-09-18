#!/usr/bin/env python3
"""Build a deterministic, provenance-preserving BAdW/WtSOCR source identity graph.

This is deliberately an identity inventory, not an article reconciliation or a
correction generator.  It keeps BAdW witness occurrences separate from the
provisional local-entry clusters to which they can be confidently linked.
The Latin transliteration in this project is the historical Library of
Congress (LoC) system, not Wylie.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from badw_source_matcher import load_local_entries as load_matcher_local_entries


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_VERSION = "badw-source-identity-v1"
SNAPSHOT_CONTRACT_VERSION = "badw-source-snapshot-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jsonl_records(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(f"{path}:{line_number}: JSONL record is not an object")
                yield record


def tsv_records(path: Path) -> Iterable[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle, delimiter="\t")


def stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def local_cluster_id(volume: str, entry_id: str) -> str:
    """Return an opaque, snapshot-independent local anchor identifier."""
    return f"wtsocr-local:{volume}:{entry_id}"


def source_witness_id(source_id: str) -> str:
    return f"badw-witness:{source_id}"


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def classify_match(match: dict[str, str]) -> tuple[str, str | None, str]:
    """Return disposition, local-cluster id, and an explanation code.

    Only a high-confidence match becomes an identity edge. Medium and low
    candidates remain recorded as candidate evidence instead of being silently
    promoted into an entry cluster.
    """
    if not parse_bool(match.get("matched", "")):
        return "unmatched", None, "no_local_candidate"
    confidence = match.get("confidence", "none")
    volume, entry_id = match.get("local_volume", ""), match.get("local_entry_id", "")
    if confidence == "high" and volume and entry_id:
        return "confident_link", local_cluster_id(volume, entry_id), "high_confidence_identity"
    if confidence in {"medium", "low"} and volume and entry_id:
        return "candidate_only", None, f"{confidence}_confidence_candidate"
    return "unmatched", None, "incomplete_match_record"


def input_manifest(paths: dict[str, Path]) -> dict[str, object]:
    files = {
        label: {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for label, path in sorted(paths.items())
    }
    logical = {label: {"sha256": value["sha256"], "bytes": value["bytes"]}
               for label, value in files.items()}
    return {
        "contract_version": SNAPSHOT_CONTRACT_VERSION,
        "inputs": files,
        "snapshot_id": hashlib.sha256(stable_json(logical).encode("utf-8")).hexdigest(),
    }


def refresh_snapshot_id(manifest: dict[str, object]) -> None:
    inputs = manifest["inputs"]
    assert isinstance(inputs, dict)
    logical = {label: {"sha256": value["sha256"], "bytes": value["bytes"]}
               for label, value in sorted(inputs.items())}
    manifest["snapshot_id"] = hashlib.sha256(stable_json(logical).encode("utf-8")).hexdigest()


def load_local_entries(qa_root: Path) -> dict[tuple[str, str], dict[str, object]]:
    entries: dict[tuple[str, str], dict[str, object]] = {}
    for local in load_matcher_local_entries(qa_root):
        key = (local.volume, local.entry_id)
        entries[key] = {
            "cluster_id": local_cluster_id(*key), "volume": local.volume,
            "entry_id": local.entry_id, "lemma": local.lemma,
            "tibetan": local.tibetan, "pages": list(local.pages),
        }
    return entries


def load_scan_only(inventory: Path | None) -> list[dict[str, str]]:
    return list(tsv_records(inventory)) if inventory else []


def build_identity_graph(
    source_articles: Path,
    matches: Path,
    qa_root: Path,
    scan_only_inventory: Path | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    source_by_id = {str(record["source_id"]): record for record in jsonl_records(source_articles)}
    match_by_id = {row["source_id"]: row for row in tsv_records(matches)}
    missing_matches = sorted(set(source_by_id) - set(match_by_id))
    extra_matches = sorted(set(match_by_id) - set(source_by_id))
    if missing_matches or extra_matches:
        raise ValueError("source/match inventory differs: "
                         f"missing_matches={len(missing_matches)}, extra_matches={len(extra_matches)}")

    local_entries = load_local_entries(qa_root)
    witnesses: list[dict[str, object]] = []
    linked_by_cluster: dict[str, list[str]] = defaultdict(list)
    disposition_counts: Counter[str] = Counter()
    for source_id in sorted(source_by_id):
        source, match = source_by_id[source_id], match_by_id[source_id]
        disposition, cluster_id, reason = classify_match(match)
        candidate: dict[str, object] | None = None
        if parse_bool(match.get("matched", "")):
            candidate = {
                "cluster_id": local_cluster_id(match["local_volume"], match["local_entry_id"])
                if match.get("local_volume") and match.get("local_entry_id") else None,
                "volume": match.get("local_volume", ""), "entry_id": match.get("local_entry_id", ""),
                "score": match.get("score", ""), "margin": match.get("margin", ""),
                "candidate_count": int(match.get("candidate_count") or 0),
                "loc_exact": parse_bool(match.get("latin_exact", "")),
                "tibetan_exact": parse_bool(match.get("tibetan_exact", "")),
            }
        witness = {
            "contract_version": CONTRACT_VERSION,
            "witness_id": source_witness_id(source_id), "source_id": source_id,
            "delivery_type": source.get("delivery_type", ""),
            "source_identity": {"lemma": source.get("lemma", ""), "homonym": source.get("homonym", ""),
                                "tibetan_heading": source.get("tibetan", "")},
            "source_provenance": source.get("provenance", {}),
            "local_identity_disposition": disposition,
            "local_identity_reason": reason,
            "linked_cluster_id": cluster_id,
            "candidate_local_identity": candidate,
        }
        witnesses.append(witness)
        disposition_counts[disposition] += 1
        if cluster_id:
            linked_by_cluster[cluster_id].append(witness["witness_id"])

    clusters: list[dict[str, object]] = []
    for key, entry in sorted(local_entries.items()):
        cluster_id = entry["cluster_id"]
        clusters.append({
            "contract_version": CONTRACT_VERSION,
            "cluster_id": cluster_id,
            "identity_kind": "provisional_local_anchor",
            "local_identity": {"volume": entry["volume"], "entry_id": entry["entry_id"],
                               "lemma": entry["lemma"], "tibetan_heading": entry["tibetan"],
                               "pages": entry["pages"]},
            "confident_witness_ids": sorted(linked_by_cluster[cluster_id]),
            "confident_witness_count": len(linked_by_cluster[cluster_id]),
        })
    summary = {
        "contract_version": CONTRACT_VERSION, "source_witnesses": len(witnesses),
        "provisional_local_clusters": len(clusters),
        "dispositions": dict(sorted(disposition_counts.items())),
        "clusters_with_confident_witnesses": sum(bool(x["confident_witness_ids"]) for x in clusters),
        "scan_only_registered_pages": len(load_scan_only(scan_only_inventory)),
    }
    return witnesses, clusters, summary


def write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(stable_json(record) + "\n")


def run(source_articles: Path, matches: Path, qa_root: Path, output_root: Path,
        scan_only_inventory: Path | None = None) -> dict[str, object]:
    inputs = {"source_articles": source_articles, "matches": matches}
    if scan_only_inventory:
        inputs["scan_only_inventory"] = scan_only_inventory
    qa_files = sorted(qa_root.glob("*/*_line_zones.tsv"))
    if not qa_files:
        raise ValueError(f"no line_zones.tsv files under {qa_root}")
    # A compound QA checksum makes entry-anchor provenance explicit without
    # copying the release bundle into the ignored graph output.
    qa_logical = [(str(path.relative_to(qa_root)), sha256_file(path)) for path in qa_files]
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = input_manifest(inputs)
    # The source snapshot must not depend on its output directory.  The QA
    # collection is represented as one deterministic compound input instead.
    qa_bytes = sum(path.stat().st_size for path in qa_files)
    manifest["inputs"]["qa_line_zones"] = {
        "path": "release/current/qa/*/*_line_zones.tsv",
        "sha256": hashlib.sha256(stable_json(qa_logical).encode("utf-8")).hexdigest(),
        "bytes": qa_bytes,
        "file_count": len(qa_files),
    }
    refresh_snapshot_id(manifest)
    witnesses, clusters, summary = build_identity_graph(
        source_articles, matches, qa_root, scan_only_inventory)
    summary["snapshot_id"] = manifest["snapshot_id"]
    write_jsonl(output_root / "witnesses.jsonl", witnesses)
    write_jsonl(output_root / "provisional_local_clusters.jsonl", clusters)
    (output_root / "source_snapshot.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-articles", required=True, type=Path)
    parser.add_argument("--matches", required=True, type=Path)
    parser.add_argument("--qa-root", default=ROOT / "release/current/qa", type=Path)
    parser.add_argument("--scan-only-inventory", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(**vars(args)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
