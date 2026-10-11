import json
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_bibliography_current_online import classify, findings


def test_refresh_fails_closed_and_only_accepts_exact_reviewed_hashes():
    item = {"id": "test", "source": {"url": "article", "sha256": "old"},
            "apparatus_sources": [{"url": "texte", "sha256": "list"}]}
    seen = {"article": {"valid": True, "sha256": "old"}, "texte": {"valid": True, "sha256": "list"}}
    assert classify(item, seen) == "still_present"
    seen["article"]["sha256"] = "new"
    assert classify(item, seen) == "source_changed_needs_review"
    correction = {"id": "test", "source_sha256": "new", "apparatus_sha256": {"texte": "list"}, "evidence": "reviewed replacement"}
    assert classify(item, seen, correction) == "corrected_upstream"
    seen["texte"]["sha256"] = "another"
    assert classify(item, seen, correction) == "source_changed_needs_review"
    seen["article"]["valid"] = False
    assert classify(item, seen, correction) == "source_changed_needs_review"


def test_findings_preserve_sources_and_counts():
    items = findings()
    assert len(items) == 49
    assert len({x["id"] for x in items}) == len(items)
    for item in items:
        assert len(item["source"]["sha256"]) == 64
        assert item["literal"]
        assert item["source_span"]["end"] - item["source_span"]["start"] == len(item["literal"])
        assert len(item["apparatus_sources"]) == 3
    assert sum(x["category"] == "wrong_citation_year" for x in items) == 4
    assert {x["label"] for x in items if x["category"] == "undefined_source_siglum"} == {"Mim1", "Mim2"}
    review = json.loads((Path(__file__).resolve().parents[1] / "data/bibliography_current_online_review.json").read_text())
    assert review["counts"]["print_only_actionable"] == 26


def test_dispositions_and_usage_inventory_cover_the_reviewed_populations():
    root = Path(__file__).resolve().parents[1] / "data"
    with (root / "bibliography_current_online_authorities.tsv").open() as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 116
    assert sum(x["population"] == "print_only" for x in rows) == 68
    assert sum(x["population"] == "online_without_print" for x in rows) == 48
    ids = {x["id"] for x in findings()}
    actionable = [x for x in rows if x["disposition"] == "actionable_current_online_gap"]
    assert len(actionable) == 26
    assert all(x["qa_ids"] and set(x["qa_ids"].split(";")) <= ids for x in actionable)
    with (root / "bibliography_current_online_siglum_usage.tsv").open() as handle:
        usage = list(csv.DictReader(handle, delimiter="\t"))
    assert len(usage) == 477
    assert sum(int(x["marked_html_occurrences"] or 0) for x in usage) == 66633
    pointer = next(x for x in findings() if x["category"] == "wrong_bibliography_pointer")
    assert "Saddharmapuṇḍarīkasūtra" in pointer["tooltip_evidence"]["literal"]
    span = pointer["tooltip_evidence"]["raw_html_span"]
    assert span["end"] - span["start"] == len(span["literal"])
