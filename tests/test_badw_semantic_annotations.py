"""Synthetic evidence only: no downloaded HTML/PDF fixtures or network calls."""
import copy
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import badw_semantic_annotations as annotations


def put(root, body):
    sha = hashlib.sha256(body).hexdigest()
    path = root / "objects" / "sha256" / sha[:2] / sha
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return sha, str(path.relative_to(root))


def packet(tmp_path, kind="html"):
    sha, path = put(tmp_path, b"synthetic source bytes, not a real PDF")
    text = "Viṣṇus für\nulkā ཀ"
    source = {"source_object": {"sha256": sha, "object_path": path},
              "article_source_text": text, "dom_full_text": text}
    if kind == "pdf":
        page = tmp_path / "page.json.gz"
        page.write_bytes(b"synthetic positioned provenance")
        source = {"source_objects": [{"pdf_sha256": sha, "page_id": "page-1",
                    "canonical_object": page.name, "canonical_object_sha256":
                    hashlib.sha256(page.read_bytes()).hexdigest()}],
                  "source_faithful_text": text, "visual_lines": []}
        for index, line in enumerate(text.split("\n")):
            source["visual_lines"].append({"page_id": "page-1", "text": line,
                "run_start": index*10, "run_end_exclusive": index*10+1,
                "style_spans": [{"start": 0, "end": len(line), "font_id": "synthetic-font",
                                  "family": "synthetic", "style": "italic"}]})
    return {"contract_version": annotations.PACKET_VERSION, "identity": "witness-1",
            "source_kind": kind, "source": source, "review_text": text,
            "review_text_sha256": annotations.digest(text)}


def claim(p, *, kind="language_span", ranges=None, status="accepted", id="claim-1"):
    ranges = ranges or [{"start": 11, "end": 15, "literal": "ulkā"}]
    return {"contract_version": annotations.VERSION, "annotation_id": id,
        "identity": p["identity"], "binding": annotations.binding(p), "ranges": ranges,
        "physical_selectors": annotations.physical_selectors(p, ranges), "kind": kind,
        "claim": {"language": "sa"} if kind == "language_span" else {
            "base_form": "Viṣṇu", "base_language": "sa", "context_language": "de",
            "relation": "inflected_name_mention"}, "status": status,
        "review": {"reviewer": "synthetic reviewer", "reviewed_at": "2026-10-04T12:00:00+00:00",
                   "mode": "same_agent_source_review", "method_version": "synthetic-v1",
                   "evidence": "Synthetic context reviewed, not independent gold."}, "supersedes": []}


def run(tmp_path, p, claims):
    return annotations.validate([p], claims, cache=tmp_path, canonical_root=tmp_path)


@pytest.mark.parametrize("kind", ["html", "pdf"])
def test_source_bound_unicode_reproducibility(tmp_path, kind):
    p = packet(tmp_path, kind)
    a = claim(p)
    original = copy.deepcopy(p)
    first = run(tmp_path, p, [a])
    assert first == run(tmp_path, p, [a])
    assert first[0]["ranges"][0]["literal"] == "ulkā"
    assert first[0]["effective_status"] == "accepted"
    assert p == original


def test_discontinuous_ranges_preserve_literal_and_order(tmp_path):
    p = packet(tmp_path, "pdf")
    a = claim(p, ranges=[{"start": 0, "end": 6, "literal": "Viṣṇus"},
                         {"start": 11, "end": 15, "literal": "ulkā"}])
    assert len(run(tmp_path, p, [a])[0]["physical_selectors"]) == 2


def test_inflected_name_is_not_language_rewrite(tmp_path):
    p = packet(tmp_path)
    a = claim(p, kind="form_mention", ranges=[{"start": 0, "end": 6, "literal": "Viṣṇus"}])
    row = run(tmp_path, p, [a])[0]
    assert row["ranges"][0]["literal"] == "Viṣṇus"
    assert row["claim"]["base_form"] == "Viṣṇu"
    assert "language" not in row["claim"]


def test_candidates_never_promote_and_ids_sort(tmp_path):
    p = packet(tmp_path)
    result = run(tmp_path, p, [claim(p, id="z", status="candidate"), claim(p, id="a", status="rejected")])
    assert [(r["annotation_id"], r["effective_status"]) for r in result] == [("a", "rejected"), ("z", "candidate")]


def test_explicit_supersession_retains_old_claim(tmp_path):
    p = packet(tmp_path)
    a, b = claim(p, id="old"), claim(p, id="new")
    b["supersedes"] = ["old"]
    result = run(tmp_path, p, [a, b])
    assert {r["annotation_id"]: r["effective_status"] for r in result} == {"new": "accepted", "old": "superseded"}


@pytest.mark.parametrize("mutation", [
    lambda a: a.update(contract_version="future"),
    lambda a: a.update(kind="citation_owner"),
    lambda a: a.update(identity="canonical-entry-not-source"),
    lambda a: a.update(status="auto_accepted"),
    lambda a: a.update(extra_field=True),
    lambda a: a["binding"].update(view_version="future"),
    lambda a: a["binding"].update(view_sha256="0"*64),
    lambda a: a["ranges"][0].update(start=True),
    lambda a: a["ranges"][0].update(end=1000),
    lambda a: a["ranges"][0].update(literal="ulka"),
    lambda a: a.update(ranges=[]),
    lambda a: a.update(physical_selectors=[]),
    lambda a: a["claim"].update(language="unknown"),
    lambda a: a["review"].update(evidence=""),
    lambda a: a["review"].update(reviewed_at="2026-10-04"),
    lambda a: a["review"].update(mode="automatic_gold"),
    lambda a: a.update(supersedes=["missing"]),
])
def test_fail_closed(tmp_path, mutation):
    p = packet(tmp_path)
    a = claim(p)
    mutation(a)
    with pytest.raises(ValueError):
        run(tmp_path, p, [a])


@pytest.mark.parametrize("ranges", [
    [{"start": 11, "end": 15, "literal": "ulkā"}, {"start": 0, "end": 6, "literal": "Viṣṇus"}],
    [{"start": 0, "end": 6, "literal": "Viṣṇus"}, {"start": 5, "end": 8, "literal": "s f"}],
])
def test_bad_range_order(tmp_path, ranges):
    p = packet(tmp_path)
    with pytest.raises(ValueError):
        run(tmp_path, p, [claim(p, ranges=ranges)])


def test_changed_physical_provenance_invalidates_binding(tmp_path):
    p = packet(tmp_path, "pdf")
    a = claim(p)
    p["source"]["visual_lines"][1]["style_spans"][0]["font_id"] = "another-font"
    with pytest.raises(ValueError, match="stale"):
        run(tmp_path, p, [a])


@pytest.mark.parametrize("kind", ["html", "pdf"])
def test_corrupt_raw_object(tmp_path, kind):
    p = packet(tmp_path, kind)
    obj = p["source"]["source_object"] if kind == "html" else p["source"]["source_objects"][0]
    sha = obj.get("sha256", obj.get("pdf_sha256"))
    (tmp_path / "objects" / "sha256" / sha[:2] / sha).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash mismatch"):
        run(tmp_path, p, [claim(p)])


def test_corrupt_canonical_page(tmp_path):
    p = packet(tmp_path, "pdf")
    (tmp_path / "page.json.gz").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash mismatch"):
        run(tmp_path, p, [claim(p)])


def test_supersession_cycle_and_duplicate_ids(tmp_path):
    p = packet(tmp_path)
    a, b = claim(p, id="a"), claim(p, id="b")
    a["supersedes"], b["supersedes"] = ["b"], ["a"]
    with pytest.raises(ValueError, match="cycle"):
        run(tmp_path, p, [a, b])
    with pytest.raises(ValueError, match="duplicate annotation"):
        run(tmp_path, p, [a, a])


def test_path_escape_and_stale_view_text(tmp_path):
    p = packet(tmp_path)
    a = claim(p)
    p["source"]["source_object"]["object_path"] = "../outside"
    with pytest.raises(ValueError, match="escapes"):
        run(tmp_path, p, [a])
    p = packet(tmp_path)
    p["review_text"] += "changed"
    with pytest.raises(ValueError, match="text hash"):
        run(tmp_path, p, [claim(p)])


def test_cross_witness_supersession_rejected(tmp_path):
    first = packet(tmp_path)
    second = copy.deepcopy(first)
    second["identity"] = "witness-2"
    old, new = claim(first, id="old"), claim(second, id="new")
    new["supersedes"] = ["old"]
    with pytest.raises(ValueError, match="same-witness"):
        annotations.validate([first, second], [old, new], cache=tmp_path)


def test_cli_rejects_output_outside_actual_work_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["validator", "--packets", "absent",
        "--annotations", "absent", "--cache", "absent", "--output",
        str(tmp_path / "elsewhere" / "work" / "result.jsonl")])
    with pytest.raises(SystemExit) as error:
        annotations.main()
    assert error.value.code == 2
    assert not (tmp_path / "elsewhere").exists()
