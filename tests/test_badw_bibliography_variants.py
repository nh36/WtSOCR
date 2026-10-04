"""Synthetic source evidence: editions remain distinct even with a reviewed relation."""
import csv
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from badw_bibliography_variants import publication_relations


def test_relations_require_exact_evidence_and_do_not_merge(tmp_path):
    authorities = [{"id": i, "kind": "publication"} for i in ("old", "new")]
    rows = [{"id": "new", "occurrence_id": "online", "source_sha256": "hash", "text": "Reprint of the revised edition"}]
    review = dict(source_id="new", target_id="old", relation_type="different_edition", status="candidate",
                  evidence_occurrence_id="online", evidence_sha256="hash", evidence_quote="revised edition",
                  evidence_note="Synthetic evidence, no pagination equivalence")
    path = tmp_path / "reviews.tsv"
    def write(reviews):
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=review, delimiter="\t")
            writer.writeheader()
            writer.writerows(reviews)
    write([review])
    a = publication_relations(path, authorities, rows, [])
    assert a == publication_relations(path, authorities, rows, [])
    assert a[0]["status"] == "candidate" and len(authorities) == 2
    for change in ({"evidence_sha256": "stale"}, {"evidence_quote": "invented"},
                   {"source_id": "missing"}, {"target_id": "new"},
                   {"relation_type": "possible_same_work", "status": "reviewed"}):
        write([{**review, **change}])
        with pytest.raises(ValueError):
            publication_relations(path, authorities, rows, [])
    write([review, review])
    with pytest.raises(ValueError, match="duplicate"):
        publication_relations(path, authorities, rows, [])
