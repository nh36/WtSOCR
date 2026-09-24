"""Offline tests for the provenance-first lexical SQLite builder."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from build_lexical_database import BuildError, build
from validate_lexical_record_contract import CONTRACT_VERSION

SHA = "a" * 64

def span():
    return [{"source_id":"badw:https://example.invalid/lemma/ka", "source_sha256":SHA,
             "field":"article_source_text", "start":0, "end":2}]

def records():
    common={"contract_version":CONTRACT_VERSION,"source_snapshot_id":"badw-html:test","extraction_run_id":"test","source_spans":span()}
    return [
      common | {"record_type":"entry","id":"e1","layer":"badw_editorial","headword":{"loc":"ka","tibetan":"ཀ"},"homonym":"","stable_url":"https://example.invalid/lemma/ka","witness_ids":["badw:https://example.invalid/lemma/ka"]},
      common | {"record_type":"sense","id":"s1","entry_id":"e1","ordinal":1,"source_label":"1.","definition":"erste Bedeutung"},
      common | {"record_type":"citation","id":"c1","entry_id":"e1","raw_text":"Liś 7","siglum":"Liś","locator":"7","authority_status":"unresolved"},
      common | {"record_type":"attestation","id":"a1","entry_id":"e1","sense_id":"s1","ordinal":1,"association_status":"explicit","tibetan":"ཀ་ཁ","german_translation":"Beleg","citation_ids":["c1"]},
      common | {"record_type":"cross_reference","id":"x1","entry_id":"e1","marker":"↑","target_label":"kha","target_url":"https://example.invalid/lemma/kha","resolution_status":"resolved"},
    ]

def write_inputs(tmp_path: Path):
    source=tmp_path/"records.jsonl"; source.write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in records()),encoding="utf-8")
    sigla=tmp_path/"sigla.tsv"; sigla.write_text("canon\twork_title\tintro_line_ref\tallowed_variants\tstatus\nLiś\tLi shi\tabbr_lit_3\tlis\tactive\n",encoding="utf-8")
    return source,sigla

def test_builds_provenance_fts_and_non_resolving_siglum_candidates(tmp_path: Path):
    source,sigla=write_inputs(tmp_path); db=tmp_path/"lexical.sqlite"; manifest=tmp_path/"manifest.json"
    report=build(source,db,manifest,sigla=sigla)
    assert report["record_counts"] == {"attestation":1,"citation":1,"cross_reference":1,"entry":1,"sense":1}
    conn=sqlite3.connect(db)
    assert conn.execute("select loc_headword,tibetan_headword from entry").fetchone()==("ka","ཀ")
    assert conn.execute("select source_sha256,start_offset,end_offset from record_source_span where record_id='e1'").fetchone()==(SHA,0,2)
    assert conn.execute("select id from sense_fts where sense_fts match 'erste'").fetchone()==("s1",)
    assert conn.execute("select id from citation_fts where citation_fts match 'Liś'").fetchone()==("c1",)
    assert conn.execute("select authority_status,bibliographic_source_id from citation").fetchone()==("unresolved",None)
    assert conn.execute("select match_method from citation_authority_candidate").fetchone()==("registry_canonical_exact",)
    conn.close()
    assert json.loads(manifest.read_text(encoding="utf-8"))["logical_sha256"] == report["logical_sha256"]

def test_repeat_build_has_identical_logical_content(tmp_path: Path):
    source,sigla=write_inputs(tmp_path)
    first=build(source,tmp_path/"one.sqlite",tmp_path/"one.json",sigla=sigla)
    second=build(source,tmp_path/"two.sqlite",tmp_path/"two.json",sigla=sigla)
    assert first["logical_sha256"] == second["logical_sha256"]

def test_invalid_contract_is_rejected(tmp_path: Path):
    source,sigla=write_inputs(tmp_path)
    bad=[json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    bad[0]["headword"]={"loc":"ka"}
    source.write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in bad),encoding="utf-8")
    with pytest.raises(BuildError,match="invalid lexical records"):
        build(source,tmp_path/"bad.sqlite",tmp_path/"bad.json",sigla=sigla)
