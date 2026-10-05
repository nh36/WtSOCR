"""Synthetic sidecar queries: accepted links are never conflated with candidates."""
import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from query_badw_bibliography import Bibliography


def test_readonly_queries_and_separate_target_states(tmp_path):
    path = tmp_path / "bibliography.sqlite"
    db = sqlite3.connect(path)
    db.executescript(Path("data/bibliography_database.schema.sql").read_text())
    authority = {"id": "w", "kind": "work", "label": "śPW", "status": "first_party_source_row"}
    db.execute("INSERT INTO authority VALUES (?,?,?,?,?,?)",
               ("w", "work", "śPW", "online", authority["status"], json.dumps(authority)))
    db.execute("INSERT INTO occurrence VALUES (?,?,?,?,?)", ("o", "w", "hash", "url", '{"text":"original"}'))
    db.execute("INSERT INTO print_occurrence VALUES (?,?,?,?,?,?)",
               ("print", "w", "o", "pdfhash", "ocrhash", '{"verified_transcription":"printed variant"}'))
    db.execute("INSERT INTO relation VALUES (?,?,?,?,?)",
               ("o", 1, "w", "unmatched", '{"relation_kind":"edition_or_containment_unreviewed"}'))
    for identity, status in (("good", "accepted_identity"), ("maybe", "candidate")):
        db.execute("INSERT INTO citation_resolution VALUES (?,?,?,?)", ("pdf", identity, status,
            json.dumps({"text": "Author 2000: 42"})))
        db.execute("INSERT INTO citation_target VALUES (?,?,?,?,?,?,?)", ("pdf", identity, 1, "w", 0, 3, status))
    db.commit()
    db.close()
    before = path.read_bytes()
    reader = Bibliography(path)
    try:
        assert reader.search("ś") == [authority]
        assert reader.search("%") == []
        assert reader.search("ś", "publication") == []
        assert reader.authority("missing") is None
        assert reader.authority("w")["occurrences"] == [{"text": "original"}]
        assert reader.authority("w")["print_occurrences"] == [{"verified_transcription": "printed variant"}]
        assert reader.authority("w")["relations"][0]["relation_kind"].endswith("unreviewed")
        assert reader.citation("pdf", "good")["candidate_targets"] == []
        assert reader.citation("pdf", "maybe")["accepted_targets"] == []
        assert reader.citation("html", "good") is None
        assert len(reader.citations_for("w")) == 1
        assert len(reader.citations_for("w", True)) == 2
        assert len(reader.literal_citations("Author 2000")) == 2
        assert reader.literal_citations("Author 2001") == []
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.db.execute("DELETE FROM authority")
    finally:
        reader.close()
    assert path.read_bytes() == before


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "absent.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        Bibliography(path)
    assert not path.exists()
