#!/usr/bin/env python3
"""Build a reproducible local SQLite/FTS backend from lexical-record JSONL.

The builder imports source-faithful records only.  It never normalizes LoC
transliteration as Wylie, resolves citations merely from a siglum spelling, or
alters the print-faithful WtSOCR release.  The resulting database belongs in
ignored ``work/`` when it contains BAdW material.
"""
from __future__ import annotations

import argparse, csv, gzip, hashlib, json, os, sqlite3, tempfile, unicodedata
from collections import Counter
from itertools import zip_longest
from pathlib import Path
from typing import Any

from validate_lexical_record_contract import CONTRACT_VERSION, read_jsonl, validate
from verify_badw_lexical_source import VerificationError, audit_lexical_records, sha256 as verified_sha256, verify_verified_lexical_source
from inventory_badw_sigla import inventory, _read_articles
from stitch_badw_pdf_entries import verify_source as verify_pdf_source
from extract_badw_pdf_lexical_candidates import extract as extract_pdf_lexical
from parse_badw_pdf_articles import VERSION as PDF_STRUCTURE_VERSION
from extract_badw_pdf_lexical_candidates import VERSION as PDF_LEXICAL_VERSION

BUILDER_VERSION = "lexical-database-builder-v7"
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

def _jsonl_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise BuildError(f"invalid JSON in {path}:{number}: {error}") from error

def _import_pdf_candidates(conn: sqlite3.Connection, witnesses: Path,
                           structure_path: Path, lexical_path: Path) -> dict[str, int]:
    """Stage source-anchored candidates without promoting them to dictionary facts."""
    names = {"definitions": "definition", "tibetan_examples": "tibetan_example",
             "belegstellen": "belegstelle", "lexicographic_parallels": "lexicographic_parallel",
             "variant_glosses": "variant_gloss",
             "translations": "translation", "citations": "citation",
             "correction_apparatus": "correction_apparatus"}
    counts: Counter[str] = Counter()
    for witness, structure, lexical in zip_longest(
            _jsonl_gz(witnesses), _jsonl_gz(structure_path), _jsonl_gz(lexical_path)):
        if witness is None or structure is None or lexical is None:
            raise BuildError("PDF witness, structure and lexical article counts differ")
        article_id = witness["id"]
        if (structure.get("article_id") != article_id or
                lexical.get("article_id") != article_id or
                structure.get("contract_version") != PDF_STRUCTURE_VERSION or
                lexical.get("contract_version") != PDF_LEXICAL_VERSION):
            raise BuildError(f"PDF candidate article identity or contract mismatch: {article_id}")
        source_hash = hashlib.sha256(witness["source_faithful_text"].encode("utf-8")).hexdigest()
        if (structure.get("source_faithful_sha256") != source_hash or
                lexical.get("source_faithful_sha256") != source_hash or
                structure.get("source_faithful_text") != witness["source_faithful_text"] or
                structure.get("volume") != witness["volume"] or
                structure.get("loc_headword") != witness["loc_headword"] or
                structure.get("tibetan_headword") != witness["tibetan_headword"] or
                structure.get("homonym") != witness["homonym"]):
            raise BuildError(f"PDF candidate source identity mismatch: {article_id}")
        expected_objects = [(span["page_id"], span["canonical_object"],
                             span["representative_pdf_url"], span["representative_pdf_sha256"],
                             span["source_text_sha256"], span["run_start"],
                             span["run_end_exclusive"]) for span in witness["source_spans"]]
        actual_objects = [(item["page_id"], item["canonical_object"],
                           item["pdf_url"], item["pdf_sha256"],
                           item["source_text_sha256"], item["run_start"],
                           item["run_end_exclusive"]) for item in structure["source_objects"]]
        if actual_objects != expected_objects or lexical.get("source_objects") != structure["source_objects"]:
            raise BuildError(f"PDF candidate source spans differ from witness: {article_id}")
        try:
            expected_lexical = extract_pdf_lexical(structure)
        except (ValueError, KeyError, IndexError, AssertionError) as error:
            raise BuildError(f"PDF lexical extraction failed for {article_id}: {error}") from error
        if lexical != expected_lexical:
            raise BuildError(f"PDF lexical candidate replay mismatch: {article_id}")
        conn.execute("INSERT INTO pdf_article_analysis VALUES (?, ?, ?, ?, ?, ?)",
                     (article_id, PDF_STRUCTURE_VERSION, PDF_LEXICAL_VERSION,
                      source_hash, lexical["visual_sha256"], canon(structure)))
        counts["articles"] += 1
        for collection, kind in names.items():
            for ordinal, row in enumerate(lexical[collection]):
                conn.execute("INSERT INTO pdf_lexical_candidate VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (article_id, kind, ordinal, row.get("division_index"),
                              row["visual_start"], row["visual_end"],
                              row.get("text", row.get("literal_text")), row["status"], canon(row)))
                counts[kind] += 1
        for row in lexical["quote_dispositions"]:
            conn.execute("INSERT INTO pdf_quote_disposition VALUES (?, ?, ?, ?)",
                         (article_id, row["quote_index"], row["kind"], row["reason"]))
            counts["quote_" + row["kind"]] += 1
    return dict(sorted(counts.items()))

def logical_digest(conn: sqlite3.Connection) -> str:
    tables = ["metadata", "source_snapshot", "source_object", "lexical_record", "record_source_span", "entry", "sense", "citation", "citation_siglum", "attestation", "attestation_citation", "cross_reference", "bibliographic_source", "bibliographic_alias", "citation_authority_candidate", "citation_siglum_authority_candidate", "badw_siglum_candidate", "badw_siglum_occurrence", "citation_siglum_candidate", "badw_bibliographic_authority", "citation_siglum_badw_authority", "pdf_article_witness", "pdf_article_source_span", "pdf_unassigned_fragment", "pdf_article_analysis", "pdf_lexical_candidate", "pdf_quote_disposition"]
    digest = hashlib.sha256()
    for table in tables:
        columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
        cols = [r[1] for r in columns]
        order = [r[1] for r in sorted(columns, key=lambda r: r[5]) if r[5]] or cols
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY " + ", ".join(order))
        digest.update(table.encode()+b"\n")
        for row in rows: digest.update(canon(dict(zip(cols,row))).encode("utf-8")+b"\n")
    return digest.hexdigest()

def build(records_path: Path, database: Path, manifest: Path, *, schema: Path = DEFAULT_SCHEMA,
          sigla: Path = DEFAULT_SIGLA, records_manifest: Path | None = None,
          verified_source_manifest: Path | None = None, force: bool = False,
          siglum_candidates: Path | None = None, siglum_occurrences: Path | None = None,
          pdf_article_root: Path | None = None, pdf_canonical_root: Path | None = None,
          pdf_structure: Path | None = None, pdf_lexical_candidates: Path | None = None,
          repo_root: Path = ROOT) -> dict[str, Any]:
    if records_manifest is None or verified_source_manifest is None:
        raise BuildError("records_manifest and verified_source_manifest are required")
    if (siglum_candidates is None) != (siglum_occurrences is None):
        raise BuildError("siglum candidates and occurrences must be supplied together")
    if (pdf_article_root is None) != (pdf_canonical_root is None):
        raise BuildError("PDF article and canonical roots must be supplied together")
    if (pdf_structure is None) != (pdf_lexical_candidates is None):
        raise BuildError("PDF structure and lexical candidates must be supplied together")
    if pdf_structure is not None and pdf_article_root is None:
        raise BuildError("PDF candidate import requires verified PDF witness inputs")
    try:
        verified_source = verify_verified_lexical_source(verified_source_manifest, repo_root)
        span_audit = audit_lexical_records(records_path, verified_source_manifest, repo_root)
    except VerificationError as error:
        raise BuildError(str(error)) from error
    try:
        extractor_manifest = json.loads(records_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BuildError(f"invalid records manifest: {records_manifest}") from error
    if extractor_manifest.get("diagnostic_count") != 0:
        raise BuildError("records manifest contains extraction diagnostics")
    if extractor_manifest.get("records_sha256") != sha256(records_path):
        raise BuildError("records do not match records manifest")
    if extractor_manifest.get("input_sha256") != verified_source["parsed_articles_sha256"]:
        raise BuildError("records manifest input differs from verified parsed source")
    if extractor_manifest.get("snapshot_id") != verified_source["source_snapshot_id"]:
        raise BuildError("records manifest snapshot differs from verified source")
    if extractor_manifest.get("verified_lexical_source_sha256") != verified_source["verified_lexical_source_sha256"]:
        raise BuildError("records manifest is not bound to verified lexical source")
    expected_objects = {(item["source_identifier"], item["source_sha256"])
                        for item in verified_source["article_source_objects"]}
    manifest_objects = {(str(item.get("source_identifier")), str(item.get("sha256")))
                        for item in extractor_manifest.get("source_objects", []) if isinstance(item, dict)}
    if manifest_objects != expected_objects or extractor_manifest.get("source_object_count") != len(expected_objects):
        raise BuildError("records manifest source objects differ from verified source")
    records = read_jsonl(records_path)
    errors = validate(records)
    if errors: raise BuildError("invalid lexical records:\n" + "\n".join(errors[:20]))
    snapshots = sorted({r["source_snapshot_id"] for r in records})
    if len(snapshots) != 1: raise BuildError("builder requires exactly one source snapshot")
    snapshot = snapshots[0]
    if snapshot != verified_source["source_snapshot_id"]:
        raise BuildError("records snapshot differs from verified source")
    tooltip_candidates: list[dict[str, Any]] = []
    tooltip_occurrences: list[dict[str, Any]] = []
    if siglum_candidates is not None and siglum_occurrences is not None:
        parsed_path = repo_root / verified_source["parsed_articles_path"]
        expected_candidates, expected_occurrences, _ = inventory(_read_articles(parsed_path))
        tooltip_candidates = read_jsonl(siglum_candidates)
        tooltip_occurrences = read_jsonl(siglum_occurrences)
        if tooltip_candidates != expected_candidates or tooltip_occurrences != expected_occurrences:
            raise BuildError("siglum inventory differs from verified parsed source")
    pdf_summary: dict[str, Any] | None = None
    pdf_audit: dict[str, Any] | None = None
    if pdf_article_root is not None and pdf_canonical_root is not None:
        try:
            pdf_audit = verify_pdf_source(pdf_article_root, pdf_canonical_root)
            pdf_summary = json.loads((pdf_article_root / "summary.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise BuildError(f"PDF witness source verification failed: {error}") from error
    if database.exists() and not force: raise BuildError(f"database exists: {database} (use --force to replace it)")
    if manifest.exists() and not force: raise BuildError(f"manifest exists: {manifest} (use --force to replace it)")
    database.parent.mkdir(parents=True, exist_ok=True); manifest.parent.mkdir(parents=True, exist_ok=True)
    input_hash, schema_hash, sigla_hash = sha256(records_path), sha256(schema), sha256(sigla)
    manifest_hash = sha256(records_manifest)
    verified_manifest_hash = verified_sha256(verified_source_manifest)
    temp = database.with_name(database.name + ".tmp")
    if temp.exists(): temp.unlink()
    conn = sqlite3.connect(temp)
    try:
        conn.executescript(schema.read_text(encoding="utf-8")); conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("INSERT INTO source_snapshot VALUES (?, ?, ?, ?, NULL)",
                     (snapshot, "badw_html", input_hash, manifest_hash))
        pdf_snapshot = ""
        if pdf_summary is not None:
            pdf_input_hash = hashlib.sha256((pdf_summary["article_logical_sha256"] + "\n" +
                                             pdf_summary["unassigned_logical_sha256"]).encode("ascii")).hexdigest()
            pdf_snapshot = "badw-pdf-witnesses:" + pdf_input_hash
            conn.execute("INSERT INTO source_snapshot VALUES (?, ?, ?, ?, NULL)",
                         (pdf_snapshot, "badw_generated_pdf", pdf_input_hash,
                          sha256(pdf_article_root / "summary.json")))
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
            conn.execute("INSERT INTO citation_fts VALUES (?, ?, ?, ?, ?)", (r["id"],r["entry_id"],r["raw_text"]," ".join(s["text"] for s in r.get("sigla", [])) or r.get("siglum", ""),r.get("locator", "")))
            for ordinal, siglum in enumerate(r.get("sigla", []), 1):
                span = siglum["source_span"]
                conn.execute("INSERT INTO citation_siglum VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (r["id"],ordinal,siglum["text"],snapshot,span["source_id"],
                              span["source_sha256"],span["start"],span["end"]))
        aliases = conn.execute("SELECT bibliographic_source_id, alias, alias_kind, normalized_alias FROM bibliographic_alias").fetchall()
        for cid, ordinal, siglum in conn.execute("SELECT citation_id, ordinal, siglum FROM citation_siglum"):
            normalized = unicodedata.normalize("NFC",siglum).casefold()
            for bid, alias, kind, norm in aliases:
                if norm == normalized:
                    method = "registry_canonical_exact" if kind == "canonical" and alias == siglum else "registry_alias_exact"
                    conn.execute("INSERT OR IGNORE INTO citation_siglum_authority_candidate VALUES (?, ?, ?, ?)", (cid,ordinal,bid,method))
        for cid, siglum in conn.execute("SELECT id, siglum FROM citation WHERE siglum IS NOT NULL AND id NOT IN (SELECT citation_id FROM citation_siglum)"):
            normalized = unicodedata.normalize("NFC",siglum).casefold()
            for bid, alias, kind, norm in aliases:
                if norm == normalized:
                    method = "registry_canonical_exact" if kind == "canonical" and alias == siglum else "registry_alias_exact"
                    conn.execute("INSERT OR IGNORE INTO citation_authority_candidate VALUES (?, ?, ?)", (cid,bid,method))
        if tooltip_candidates:
            for row in tooltip_candidates:
                conn.execute("INSERT INTO badw_siglum_candidate VALUES (?, ?, ?, ?, ?)",
                             (row["candidate_id"],row["siglum"],row["expansion"],row["candidate_status"],row["occurrence_count"]))
                conn.execute("INSERT INTO badw_siglum_fts VALUES (?, ?, ?)",
                             (row["candidate_id"],row["siglum"],row["expansion"]))
                if row["expansion"]:
                    conn.execute("INSERT INTO badw_bibliographic_authority VALUES (?, ?, ?, ?)",
                                 (row["candidate_id"], "siglum_expansion", "first_party_tooltip", "unverified"))
            for row in tooltip_occurrences:
                visible, hidden = row["source_span"], row["tooltip_span"]
                conn.execute("INSERT INTO badw_siglum_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (row["candidate_id"],snapshot,visible["source_id"],visible["source_sha256"],
                              row["source_url"],row["ordinal_in_article"],visible["start"],visible["end"],
                              hidden["start"] if hidden else None,hidden["end"] if hidden else None))
            occurrence_by_location: dict[tuple[str, str, int, int, str],list[tuple[str, int]]] = {}
            for row in tooltip_occurrences:
                visible = row["source_span"]
                key = (visible["source_id"],visible["source_sha256"],
                       visible["start"],visible["end"],row["siglum"])
                occurrence_by_location.setdefault(key,[]).append((row["candidate_id"],row["ordinal_in_article"]))
            for cid, ordinal, siglum, source_id, source_sha, start, end in conn.execute(
                    "SELECT citation_id, ordinal, siglum, source_id, source_sha256, visible_start, visible_end FROM citation_siglum"):
                for candidate_id, occurrence_ordinal in occurrence_by_location.get(
                        (source_id,source_sha,start,end,siglum),[]):
                    conn.execute("INSERT INTO citation_siglum_candidate VALUES (?, ?, ?, ?, ?, ?)",
                                 (cid,ordinal,candidate_id,source_id,occurrence_ordinal,
                                  "badw_tooltip_same_source_span"))
            # A unique same-span occurrence is stronger than spelling-only
            # matching.  Multiple occurrences are retained as candidates but
            # never promoted to an authority link by arbitrary row order.
            for cid, ordinal, count in conn.execute(
                    "SELECT citation_id, siglum_ordinal, count(*) FROM citation_siglum_candidate "
                    "GROUP BY citation_id, siglum_ordinal"):
                if count != 1:
                    continue
                candidate_id, source_id, occurrence_ordinal = conn.execute(
                    "SELECT candidate_id, occurrence_source_id, occurrence_ordinal "
                    "FROM citation_siglum_candidate WHERE citation_id=? AND siglum_ordinal=?",
                    (cid, ordinal)).fetchone()
                if conn.execute("SELECT 1 FROM badw_bibliographic_authority WHERE id=?",
                                (candidate_id,)).fetchone():
                    conn.execute("INSERT INTO citation_siglum_badw_authority VALUES (?, ?, ?, ?, ?, ?)",
                                 (cid, ordinal, candidate_id, source_id, occurrence_ordinal,
                                  "exact_visible_source_span"))
        for r in sorted(by_type.get("attestation",[]),key=lambda r:r["id"]):
            conn.execute("INSERT INTO attestation VALUES (?, ?, ?, ?, ?, ?, ?)", (r["id"],r["entry_id"],r.get("sense_id"),r["ordinal"],r["association_status"],r["tibetan"],r.get("german_translation", "")))
            conn.execute("INSERT INTO attestation_fts VALUES (?, ?, ?, ?)", (r["id"],r["entry_id"],r["tibetan"],r.get("german_translation", "")))
            for cid in r["citation_ids"]: conn.execute("INSERT INTO attestation_citation VALUES (?, ?)", (r["id"],cid))
        for r in sorted(by_type.get("cross_reference",[]),key=lambda r:r["id"]):
            conn.execute("INSERT INTO cross_reference VALUES (?, ?, ?, ?, ?, ?)", (r["id"],r["entry_id"],r["marker"],r.get("target_label"),r.get("target_url"),r["resolution_status"]))
        pdf_count = 0
        pdf_source_objects: dict[str, str] = {}
        if pdf_article_root is not None:
            with gzip.open(pdf_article_root / "pdf_article_witnesses.jsonl.gz", "rt", encoding="utf-8") as handle:
                for line in handle:
                    article = json.loads(line)
                    pdf_count += 1
                    conn.execute("INSERT INTO pdf_article_witness VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (article["id"], pdf_snapshot, article["volume"], article["start_printed_page"],
                                  article["end_printed_page"], article["loc_headword"], article["tibetan_headword"],
                                  article["homonym"], article["ending_status"], article["source_faithful_text"],
                                  article["derived_reading_text"], len(article["unknown_glyphs"])))
                    conn.execute("INSERT INTO pdf_article_fts VALUES (?, ?, ?, ?)",
                                 (article["id"], article["loc_headword"], article["tibetan_headword"],
                                  article["derived_reading_text"]))
                    for ordinal, span in enumerate(article["source_spans"], 1):
                        url, source_sha = span["representative_pdf_url"], span["representative_pdf_sha256"]
                        prior = pdf_source_objects.setdefault(url, source_sha)
                        if prior != source_sha:
                            raise BuildError(f"PDF URL has conflicting source hashes: {url}")
                        conn.execute("INSERT INTO pdf_article_source_span VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                     (article["id"], ordinal, span["page_id"], span["canonical_object"],
                                      span["printed_page"], url, source_sha, span["visible_body_sha256"],
                                      span["run_start"], span["run_end_exclusive"], span["segment_role"],
                                      span["join_method"], span["source_text_sha256"], span["source_faithful_text"],
                                      span["derived_reading_text"], canon(span["unknown_glyphs"])))
            pdf_fragment_count = 0
            with gzip.open(pdf_article_root / "unassigned_page_fragments.jsonl.gz", "rt", encoding="utf-8") as handle:
                for line in handle:
                    span = json.loads(line)
                    pdf_fragment_count += 1
                    url, source_sha = span["representative_pdf_url"], span["representative_pdf_sha256"]
                    prior = pdf_source_objects.setdefault(url, source_sha)
                    if prior != source_sha:
                        raise BuildError(f"PDF URL has conflicting source hashes: {url}")
                    fragment_id = f"pdf-fragment:{span['page_id']}:{span['run_start']}:{span['run_end_exclusive']}"
                    conn.execute("INSERT INTO pdf_unassigned_fragment VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (fragment_id, pdf_snapshot, span["volume"], span["printed_page"],
                                  span["page_id"], span["canonical_object"], url, source_sha,
                                  span["visible_body_sha256"], span["run_start"], span["run_end_exclusive"],
                                  span["segment_role"], span["source_text_sha256"], span["source_faithful_text"],
                                  span["derived_reading_text"], canon(span["unknown_glyphs"])))
                    conn.execute("INSERT INTO pdf_unassigned_fragment_fts VALUES (?, ?)",
                                 (fragment_id, span["derived_reading_text"]))
            conn.executemany("INSERT INTO source_object VALUES (?, ?, ?, ?)",
                             [(pdf_snapshot, "badw:pdf:" + url, source_sha, url)
                              for url, source_sha in sorted(pdf_source_objects.items())])
        pdf_candidate_counts: dict[str, int] = {}
        if pdf_structure is not None and pdf_lexical_candidates is not None:
            pdf_candidate_counts = _import_pdf_candidates(
                conn, pdf_article_root / "pdf_article_witnesses.jsonl.gz",
                pdf_structure, pdf_lexical_candidates)
            if pdf_candidate_counts.get("articles") != pdf_count:
                raise BuildError("PDF candidate count differs from verified witnesses")
        metadata = {
            "builder_version": BUILDER_VERSION,
            "cache_manifest_index_sha256": verified_source["cache_manifest_index_sha256"],
            "contract_version": CONTRACT_VERSION,
            "parsed_articles_sha256": verified_source["parsed_articles_sha256"],
            "source_snapshot_sha256": verified_source["source_snapshot_sha256"],
            "verified_lexical_source_sha256": verified_manifest_hash,
        }
        if siglum_candidates is not None and siglum_occurrences is not None:
            metadata["badw_siglum_candidates_sha256"] = sha256(siglum_candidates)
            metadata["badw_siglum_occurrences_sha256"] = sha256(siglum_occurrences)
        if pdf_summary is not None:
            metadata["pdf_article_logical_sha256"] = pdf_summary["article_logical_sha256"]
            metadata["pdf_unassigned_logical_sha256"] = pdf_summary["unassigned_logical_sha256"]
            metadata["pdf_article_summary_sha256"] = sha256(pdf_article_root / "summary.json")
        if pdf_structure is not None and pdf_lexical_candidates is not None:
            metadata["pdf_structure_sha256"] = sha256(pdf_structure)
            metadata["pdf_lexical_candidates_sha256"] = sha256(pdf_lexical_candidates)
        conn.executemany("INSERT INTO metadata VALUES (?, ?)", sorted(metadata.items()))
        conn.commit(); conn.execute("VACUUM"); conn.commit()
        report = {"builder_version":BUILDER_VERSION,"contract_version":CONTRACT_VERSION,"input_sha256":input_hash,"records_manifest_sha256":manifest_hash,"verified_lexical_source_sha256":verified_manifest_hash,"source_snapshot_sha256":verified_source["source_snapshot_sha256"],"cache_manifest_index_sha256":verified_source["cache_manifest_index_sha256"],"source_span_audit":span_audit,"schema_sha256":schema_hash,"sigla_registry_sha256":sigla_hash,"source_snapshot_id":snapshot,"record_counts":dict(sorted(Counter(r["record_type"] for r in records).items())),"source_object_count":len(objects),"badw_siglum_candidate_count":len(tooltip_candidates),"badw_siglum_occurrence_count":len(tooltip_occurrences),"badw_bibliographic_authority_count":conn.execute("SELECT count(*) FROM badw_bibliographic_authority").fetchone()[0],"citation_siglum_badw_authority_count":conn.execute("SELECT count(*) FROM citation_siglum_badw_authority").fetchone()[0],"citation_siglum_unlinked_count":conn.execute("SELECT count(*) FROM citation_siglum AS cs WHERE NOT EXISTS (SELECT 1 FROM citation_siglum_badw_authority AS ba WHERE ba.citation_id=cs.citation_id AND ba.siglum_ordinal=cs.ordinal)").fetchone()[0],"logical_sha256":logical_digest(conn)}
        if pdf_summary is not None:
            report.update({"pdf_source_snapshot_id": pdf_snapshot, "pdf_article_count": pdf_count,
                           "pdf_unassigned_fragment_count": pdf_fragment_count,
                           "pdf_source_object_count": len(pdf_source_objects), "pdf_source_audit": pdf_audit,
                           "pdf_article_logical_sha256": pdf_summary["article_logical_sha256"]})
        if pdf_structure is not None and pdf_lexical_candidates is not None:
            report.update({"pdf_structure_sha256": sha256(pdf_structure),
                           "pdf_lexical_candidates_sha256": sha256(pdf_lexical_candidates),
                           "pdf_candidate_counts": pdf_candidate_counts})
    finally: conn.close()
    os.replace(temp, database)
    report["database_sha256"] = sha256(database); report["database_bytes"] = database.stat().st_size
    manifest.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    return report

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("records",type=Path); p.add_argument("database",type=Path); p.add_argument("manifest",type=Path); p.add_argument("--records-manifest",type=Path,required=True); p.add_argument("--verified-source-manifest",type=Path,required=True); p.add_argument("--schema",type=Path,default=DEFAULT_SCHEMA); p.add_argument("--sigla",type=Path,default=DEFAULT_SIGLA); p.add_argument("--siglum-candidates",type=Path); p.add_argument("--siglum-occurrences",type=Path); p.add_argument("--pdf-article-root",type=Path); p.add_argument("--pdf-canonical-root",type=Path); p.add_argument("--pdf-structure",type=Path); p.add_argument("--pdf-lexical-candidates",type=Path); p.add_argument("--force",action="store_true"); a=p.parse_args()
    try: print(json.dumps(build(a.records,a.database,a.manifest,schema=a.schema,sigla=a.sigla,records_manifest=a.records_manifest,verified_source_manifest=a.verified_source_manifest,siglum_candidates=a.siglum_candidates,siglum_occurrences=a.siglum_occurrences,pdf_article_root=a.pdf_article_root,pdf_canonical_root=a.pdf_canonical_root,pdf_structure=a.pdf_structure,pdf_lexical_candidates=a.pdf_lexical_candidates,force=a.force),ensure_ascii=False,sort_keys=True))
    except (BuildError, ValueError, sqlite3.Error) as e: print(f"error: {e}"); return 2
    return 0
if __name__ == "__main__": raise SystemExit(main())
