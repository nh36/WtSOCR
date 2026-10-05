"""Synthetic source-only packet: no copied dictionary text or live requests."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_badw_relationship_review_packet import packet, excluded_identities, main
from build_badw_entry_index import encode


def sources():
    # Two source patterns keep both Lex. and non-Lex. strata populated.
    pdf, html = [], []
    for lex in (False, True):
        text = ("Lex. " if lex else "") + "synthetic (A; B) (C) (D)\n„text“ ≈ skt. ↑target"
        for n in range(45):
            identity = f"{'lex' if lex else 'def'}:{n}"
            html.append(dict(source_identifier="html:"+identity,
                article_source_text=text, dom_full_text=text,
                source_object={"sha256": "synthetic"},
                nodes=[{"secret_prediction": True}], proposed_relationships=["secret"]))
            for volume in (2, 3, 4):
                pdf.append(dict(article_id=f"pdf:{volume}:{identity}", volume=volume,
                    visual_lines=[{"text": text, "page_id": "synthetic-page"}],
                    source_faithful_text=text, source_objects=[{"pdf_sha256": "synthetic"}],
                    nodes=[{"secret_prediction": True}], proposed_relationships=["secret"]))
    return pdf, html


def test_blind_unique_stratified_reproducible_and_excludes_seen():
    pdf, html = sources()
    excluded = {pdf[0]["article_id"], html[0]["source_identifier"]}
    records = packet(pdf, html, excluded)
    assert len(records) == 60
    assert len({r["identity"] for r in records}) == 60
    assert not excluded.intersection(r["identity"] for r in records)
    assert sum(r["source_kind"] == "html" for r in records) == 30
    for volume in (2, 3, 4):
        assert sum(r["volume"] == volume for r in records) == 10
    assert encode(records) == encode(packet(reversed(pdf), reversed(html), excluded))
    assert b"secret" not in encode(records)
    for r in records:
        assert r["reviewed_relationships"] == [] and r["reviewer"] is None
        assert r["review_text_sha256"] == hashlib.sha256(r["review_text"].encode()).hexdigest()


def test_insufficient_sources_duplicate_identity_and_invalid_count_fail():
    pdf, html = sources()
    with pytest.raises(ValueError, match="insufficient"):
        packet([], html, set())
    with pytest.raises(ValueError, match="duplicate"):
        packet(pdf+[pdf[0]], html, set())
    with pytest.raises(ValueError, match="positive"):
        packet(pdf, html, set(), per_stratum=0)


def test_exclusion_contract(tmp_path):
    path = tmp_path / "seen.jsonl"
    path.write_text(json.dumps({"identity": "seen"})+"\n", encoding="utf-8")
    assert excluded_identities([path]) == {"seen"}
    path.write_text('{}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="without identity"):
        excluded_identities([path])


def test_cli_freezes_existing_rule_files_and_refuses_overwrite(tmp_path, monkeypatch):
    pdf, html = sources()
    paths = [tmp_path / name for name in ("pdf.jsonl", "html.jsonl", "index.jsonl", "seen.jsonl")]
    for path, records in zip(paths, (pdf, html, [], [])):
        path.write_bytes(encode(records))
    output = tmp_path / "packet.jsonl"
    monkeypatch.setattr(sys, "argv", ["packet", "--pdf", str(paths[0]),
        "--html", str(paths[1]), "--entry-index", str(paths[2]),
        "--exclude", str(paths[3]), "--output", str(output)])
    main()
    manifest = json.loads(output.with_suffix(".manifest.json").read_text())
    assert manifest["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert manifest["predictions_exposed"] is False
    for rule in manifest["frozen_rule_files"]:
        assert rule["sha256"] == hashlib.sha256(Path(rule["path"]).read_bytes()).hexdigest()
    with pytest.raises(SystemExit):
        main()
