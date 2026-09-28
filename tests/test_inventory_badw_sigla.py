"""Small, offline authority-inventory tests."""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from badw_article_parser import parse_database_article
from inventory_badw_sigla import InventoryError, inventory


FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "badw" / "article.html").read_bytes()
URL = "https://wts-digital.badw.de/lemma/ka/2"


def article(body: bytes = FIXTURE):
    return parse_database_article(body, source_metadata={
        "sha256": hashlib.sha256(body).hexdigest(),
        "delivery_type": "database_article", "valid_resource": True,
        "final_url": URL, "requested_url": URL, "content_classification": "database_article",
    })


def test_source_provenance_and_deterministic_candidate_identity():
    one = article()
    candidates, occurrences, summary = inventory([one])
    assert summary["article_count"] == 1
    assert summary["siglum_count"] == 2
    assert summary["occurrences_without_tooltip"] == 1
    assert any(row["expansion"] == "Test-Siglum Langform" for row in candidates)
    assert all(row["candidate_status"] == "single_observed_expansion" for row in candidates)
    assert any(row["tooltip_span"] and row["tooltip_span"]["field"] == "dom_full_text" for row in occurrences)
    assert inventory([one]) == (candidates, occurrences, summary)


def test_multiple_expansions_are_candidates_not_silently_merged():
    second = article(FIXTURE.replace(b"Test-Siglum Langform", b"Different expansion"))
    second["source_identifier"] = "badw:https://wts-digital.badw.de/lemma/kha/1"
    second["source_object"]["final_url"] = "https://wts-digital.badw.de/lemma/kha/1"
    candidates, _, summary = inventory([article(), second])
    assert summary["candidate_count"] == 3
    assert summary["sigla_with_multiple_expansions"] == 1
    assert sum(row["candidate_status"] == "multiple_observed_expansions" for row in candidates) == 2


def test_tampered_tooltip_source_span_is_rejected():
    item = article()
    item["sigla"][0]["expanded_source_text"] = "not in source"
    with pytest.raises(InventoryError, match="bad dom_full_text source span"):
        inventory([item])
