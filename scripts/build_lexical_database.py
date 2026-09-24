#!/usr/bin/env python3
"""Build a reproducible local SQLite/FTS backend from lexical-record JSONL.

The builder imports source-faithful records only.  It never normalizes LoC
transliteration as Wylie, resolves citations merely from a siglum spelling, or
alters the print-faithful WtSOCR release.  The resulting database belongs in
ignored ``work/`` when it contains BAdW material.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, os, sqlite3, tempfile, unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from validate_lexical_record_contract import CONTRACT_VERSION, read_jsonl, validate

BUILDER_VERSION = "lexical-database-builder-v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "data" / "lexical_database.schema.sql"
DEFAULT_SIGLA = ROOT / "data" / "sigla_registry.tsv"

class BuildError(ValueError): pass

def sha256(path: Path) -> str:
    with path.open("rb") as f: return hashlib.file_digest(f, "sha256").hexdigest()

def canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def stable_url(source_id: str) -> str | None:
    return source_id.removeprefix("badw:") if source_id.startswith("badw:http") else None

def read_sigla(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as h:
        rows = list(csv.DictReader(h, delimiter="\t"))
    required = {"canon", "work_title", "intro_line_ref", "allowed_variants", "status"}
    if not rows or set(rows[0]) != required: raise BuildError("sigla registry has unexpected columns")
    return sorted(rows, key=lambda r: r["canon"])

def logical_digest(conn: sqlite3.Connection) -> str:
    tables = ["source_snapshot", "source_object", "lexical_record", "record_source_span", "entry", "sense", "citation", "attestation", "attestation_citation", "cross_reference", "bibliographic_source", "bibliographic_alias", "citation_authority_candidate"]
    digest = hashlib.sha256()
    for table in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY " + ", ".join(cols)).fetchall()
        digest.update(table.encode()+b"\n")
        for row in rows: digest.update(canon(dict(zip(cols,row))).encode("utf-8")+b"\n")
    return digest.hexdigest()

def build(records_path: Path, database: Path, manifest: Path, *, schema: Path = DEFAULT_SCHEMA,
          sigla: Path = DEFAULT_SIGLA, records_manifest: Path | None = None, force: bool = False) -> dict[str, Any]:
    records = read_jsonl(records_path)
    errors = validate(records)
    if errors: raise BuildError("invalid lexical records:\n" + "\n".join(errors[:20]))
    snapshots = sorted({r["source_snapshot_id"] for r in records})
    if len(snapshots) != 1: raise BuildError("this v1 builder requires exactly one source snapshot")
    snapshot = snapshots[0]
    if database.exists() and not force: raise BuildError(f"database exists: {database} (use --force to replace it)")
    if manifest.exists() and not force: raise BuildError(f"manifest exists: {manifest} (use --force to replace it)")
    database.parent.mkdir(parents=True, exist_ok=True); manifest.parent.mkdir(parents=True, exist_ok=True)
    input_hash, schema_hash, sigla_hash = sha256(records_path), sha256(schema), sha256(sigla)
    manifest_hash = sha256(records_manifest) if records_manifest else None
    temp = database.with_name(database.name + ".tmp")
    if temp.exists(): temp.unlink()
    conn = sqlite3.connect(temp)
    try:
        conn.executescript(schema.read_text(encoding="utf-8")); conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("INSERT INTO source_snapshot VALUES (?, ?, ?, ?, NULL)", (snapshot, "badw_html", input_hash, manifest_hash))
        objects: dict[str, str] = {}
        for row in records:
            for span in row["source_spans"]:
                prior = objects.setdefault(span["source_id"], span["source_sha256"])
                if prior != span["source_sha256"]: raise BuildError(f"source {span['source_id']} has conflicting hashes")
        conn.executemany("INSERT INTO source_object VALUES (?, ?, ?, ?)", [(snapshot, sid, h, stable_url(sid)) for sid,h in sorted(objects.items())])
        for row in sorted(records, key=lambda r:r["id"]):
            conn.execute("INSERT INTO lexical_record VALUES (?, ?, ?, ?, ?)", (row["id"], snapshot, row["record_type"], row["extraction_run_id"], canon(row)))
            for n, span in enumerate(row["source_spans"], 1):
                conn.execute("INSERT INTO record_source_span VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (row["id"],n,snapshot,span["source_id"],span["source_sha256"],span["field"],span["start"],span["end"]))
        for r in read_sigla(sigla):
            bid = "registry:siglum:" + r["canon"]
            conn.execute("INSERT INTO bibliographic_source VALUES (?, ?, ?, ?, ?, ?)", (bid,r["canon"],r["work_title"],r["intro_line_ref"],"sigla_registry",r["status"]))
            aliases = [(r["canon"],"canonical")] + [(x,"allowed_variant") for x in r["allowed_variants"].split("|") if x]
            for alias, kind in aliases:
                conn.execute("INSERT INTO bibliographic_alias VALUES (?, ?, ?, ?)", (bid,alias,kind,unicodedata.normalize("NFC",alias).casefold()))
            conn.execute("INSERT INTO bibliography_fts VALUES (?, ?, ?, ?)", (bid,r["canon"],r["work_title"]," ".join(a for a,_ in aliases)))
        by_type: dict[str,list[dict[str,Any]]] = {}
        for row in records: by_type.setdefault(row["record_type"],[]).append(row)
        for r in sorted(by_type.get("entry",[]),key=lambda r:r["id"]):
            conn.execute("INSERT INTO entry VALUES (?, ?, ?, ?, ?, ?)", (r["id"],r["layer"],r["headword"]["loc"],r["headword"]["tibetan"],r.get("homonym", ""),r.get("stable_url", "")))
            conn.execute("INSERT INTO entry_fts VALUES (?, ?, ?)", (r["id"],r["headword"]["loc"],r["headword"]["tibetan"]))
        for r in sorted(by_type.get("sense",[]),key=lambda r:r["id"]):
            conn.execute("INSERT INTO sense VALUES (?, ?, ?, ?, ?)", (r["id"],r["entry_id"],r["ordinal"],r.get("source_label", ""),r["definition"]))
            conn.execute("INSERT INTO sense_fts VALUES (?, ?, ?)", (r["id"],r["entry_id"],r["definition"]))
        for r in sorted(by_type.get("citation",[]),key=lambda r:r["id"]):
            conn.execute("INSERT INTO citation VALUES (?, ?, ?, ?, ?, ?, ?)", (r["id"],r["entry_id"],r["raw_text"],r.get("siglum"),r.get("locator"),r["authority_status"],r.get("bibliographic_source_id")))
            conn.execute("INSERT INTO citation_fts VALUES (?, ?, ?, ?, ?)", (r["id"],r["entry_id"],r["raw_text"],r.get("siglum",""),r.get("locator", "")))
        aliases = conn.execute("SELECT bibliographic_source_id, alias, alias_kind, normalized_alias FROM bibliographic_alias").fetchall()
        for cid, siglum in conn.execute("SELECT id, siglum FROM citation WHERE siglum IS NOT NULL"):
            normalized = unicodedata.normalize("NFC",siglum).casefold()
            for bid, alias, kind, norm in aliases:
                if norm == normalized:
                    method = "registry_canonical_exact" if kind == "canonical" and alias == siglum else "registry_alias_exact"
                    conn.execute("INSERT OR IGNORE INTO citation_authority_candidate VALUES (?, ?, ?)", (cid,bid,method))
        for r in sorted(by_type.get("attestation",[]),key=lambda r:r["id"]):
            conn.execute("INSERT INTO attestation VALUES (?, ?, ?, ?, ?, ?, ?)", (r["id"],r["entry_id"],r.get("sense_id"),r["ordinal"],r["association_status"],r["tibetan"],r.get("german_translation", "")))
            conn.execute("INSERT INTO attestation_fts VALUES (?, ?, ?, ?)", (r["id"],r["entry_id"],r["tibetan"],r.get("german_translation", "")))
            for cid in r["citation_ids"]: conn.execute("INSERT INTO attestation_citation VALUES (?, ?)", (r["id"],cid))
        for r in sorted(by_type.get("cross_reference",[]),key=lambda r:r["id"]):
            conn.execute("INSERT INTO cross_reference VALUES (?, ?, ?, ?, ?, ?)", (r["id"],r["entry_id"],r["marker"],r.get("target_label"),r.get("target_url"),r["resolution_status"]))
        conn.execute("INSERT INTO metadata VALUES (?, ?)", ("contract_version", CONTRACT_VERSION)); conn.execute("INSERT INTO metadata VALUES (?, ?)", ("builder_version", BUILDER_VERSION))
        conn.commit(); conn.execute("VACUUM"); conn.commit()
        report = {"builder_version":BUILDER_VERSION,"contract_version":CONTRACT_VERSION,"input_sha256":input_hash,"records_manifest_sha256":manifest_hash,"schema_sha256":schema_hash,"sigla_registry_sha256":sigla_hash,"source_snapshot_id":snapshot,"record_counts":dict(sorted(Counter(r["record_type"] for r in records).items())),"source_object_count":len(objects),"logical_sha256":logical_digest(conn)}
    finally: conn.close()
    os.replace(temp, database)
    report["database_sha256"] = sha256(database); report["database_bytes"] = database.stat().st_size
    manifest.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    return report

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("records",type=Path); p.add_argument("database",type=Path); p.add_argument("manifest",type=Path); p.add_argument("--records-manifest",type=Path); p.add_argument("--schema",type=Path,default=DEFAULT_SCHEMA); p.add_argument("--sigla",type=Path,default=DEFAULT_SIGLA); p.add_argument("--force",action="store_true"); a=p.parse_args()
    try: print(json.dumps(build(a.records,a.database,a.manifest,schema=a.schema,sigla=a.sigla,records_manifest=a.records_manifest,force=a.force),ensure_ascii=False,sort_keys=True))
    except (BuildError, ValueError, sqlite3.Error) as e: print(f"error: {e}"); return 2
    return 0
if __name__ == "__main__": raise SystemExit(main())
