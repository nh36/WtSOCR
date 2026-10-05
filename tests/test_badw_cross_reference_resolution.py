import copy
import json
import subprocess
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from resolve_badw_cross_references import EntryIndex


def entry(identifier="entry-1", lemma="ka", homonym="1", url="https://example/lemma/ka/1"):
    return dict(record_type="entry", id=identifier, stable_url=url,
                headword=dict(loc=lemma), homonym=homonym)


def reference(url="https://example/lemma/ka/1"):
    r = dict(record_type="cross_reference", id="ref-1", entry_id="source-entry",
             marker="↑", target_label="ka", resolution_status="resolved" if url else "unresolved",
             source_spans=[dict(source_id="source", source_sha256="a"*64, start=2, end=4)])
    if url:
        r["target_url"] = url
    return r


def reviewed(r, **kwargs):
    return dict(occurrence_id=r["id"],source_spans=r["source_spans"],literal=r["target_label"],
                lemma="ka",review=dict(reviewer="reviewer",reviewed_at="2026-10-05",evidence="Exact printed target inspected"),**kwargs)


def test_url_capture_and_canonical_resolution_separate_and_immutable():
    r = reference()
    before = copy.deepcopy(r)
    result = EntryIndex([entry()]).resolve(r)
    assert r == before
    assert {k:v for k,v in result.items() if k!="canonical_resolution"} == before
    assert result["canonical_resolution"]["target_entry_id"] == "entry-1"
    absent = EntryIndex([]).resolve(r)
    assert absent["resolution_status"] == "resolved"  # source URL is still captured
    assert absent["canonical_resolution"]["status"] == "unresolved"
    assert "target_entry_id" not in absent["canonical_resolution"]


def test_ambiguous_url_and_conflicting_entry_identity_fail_closed():
    assert EntryIndex([entry(),entry("entry-2")]).resolve(reference())["canonical_resolution"]["status"] == "ambiguous"
    with pytest.raises(ValueError, match="conflicting"):
        EntryIndex([entry(),entry(lemma="kha")])


def test_no_url_normalization_or_fallback_to_label():
    r = reference("https://example/lemma/ka/1/")
    assert EntryIndex([entry()]).resolve(r)["canonical_resolution"]["status"] == "unresolved"


def test_printed_homonyms_require_evidence_and_never_nearest_choice():
    r = reference(None)
    index = EntryIndex([entry(),entry("entry-2",homonym="2",url="https://example/lemma/ka/2")])
    assert index.resolve(r)["canonical_resolution"]["status"] == "unresolved"
    assert index.resolve(r,reviewed_target=reviewed(r))["canonical_resolution"]["status"] == "ambiguous"
    assert index.resolve(r,reviewed_target=reviewed(r,homonym="2"))["canonical_resolution"]["target_entry_id"] == "entry-2"


def test_review_bound_to_literal_and_source():
    r = reference(None)
    for field,value in [("literal","kha"),("source_spans",[]),("occurrence_id","other")]:
        review = reviewed(r)
        review[field] = value
        with pytest.raises(ValueError,match="bound"):
            EntryIndex([entry()]).resolve(r,reviewed_target=review)


def test_deterministic_index_and_resolution():
    a,b=entry(),entry("entry-2",lemma="kha",url="https://example/lemma/kha/1")
    assert EntryIndex([a,b]).resolve(reference()) == EntryIndex([b,a,a]).resolve(reference())
    with pytest.raises(ValueError,match="provenance"):
        EntryIndex([a]).resolve(dict(record_type="cross_reference"))


def test_cli_offline_unicode_and_byte_identical_replay(tmp_path):
    entries, refs, output = (tmp_path / name for name in ("entries.jsonl", "refs.jsonl", "output.jsonl"))
    entries.write_text(json.dumps(entry(), ensure_ascii=False)+"\n", encoding="utf-8")
    r = reference()
    r["target_label"] = "ka\u2028ཀ"
    refs.write_text(json.dumps(r, ensure_ascii=False)+"\n", encoding="utf-8")
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "resolve_badw_cross_references.py"),
               "--entries", str(entries), "--references", str(refs), "--output", str(output)]
    subprocess.run(command, check=True)
    first = output.read_bytes()
    subprocess.run(command, check=True)
    assert output.read_bytes() == first
    assert json.loads(first)["target_label"] == r["target_label"]
