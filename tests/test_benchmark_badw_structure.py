"""Synthetic whole-entry annotations: no actual benchmark accuracy claim."""
import copy
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_badw_structure import VERSION, graph, score


def packet():
    text = "ka ṅa Deutsch (A: 1)"
    return dict(contract_version=VERSION, identity="entry1", source_kind="pdf",
                source={"sha256": "a" * 64}, group="pdf3", stratum="long", split="holdout",
                review_text=text, review_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                review_status="pending_independent_review", reviewed_nodes=[], reviewed_edges=[], reviewer=None)


def nodes():
    return [dict(id="s", kind="sense", start=0, end=20, parent=None),
            dict(id="e", kind="example", start=3, end=20, parent="s"),
            dict(id="t", kind="tibetan", start=3, end=5, parent="e"),
            dict(id="g", kind="translation", start=6, end=13, parent="e"),
            dict(id="c", kind="citation", start=14, end=20, parent="e")]


def edges():
    return [dict(kind="citation_of", **{"from": "c", "to": "e"}),
            dict(kind="translation_of", **{"from": "g", "to": "t"})]


def records():
    source = packet()
    gold = dict(source, review_status="reviewed_complete", reviewer="synthetic test",
                review_mode="same_agent_source_review", reviewed_nodes=nodes(), reviewed_edges=edges())
    predicted = dict(source, nodes=nodes(), edges=edges())
    return source, gold, predicted


def test_pending_packets_are_not_accuracy():
    result = score([packet()], [], [])
    assert result["counts"] == {"pending": 1}
    assert result["review_modes"] == {}


def test_unicode_exact_nesting_and_edges_deterministic():
    source, gold, predicted = records()
    result = score([source], [gold], [predicted])
    assert result["counts"]["whole_entry_exact"] == 1
    assert result["counts"]["nodes:correct"] == 5
    predicted["nodes"].reverse()
    predicted["edges"].reverse()
    assert score([source], [gold], [predicted]) == result
    predicted["edges"] = []
    changed = score([source], [gold], [predicted])
    assert changed["counts"]["whole_entry_exact"] == 0
    assert changed["counts"]["edges:correct"] == 0
    assert len(changed["disagreements"][0]["differences"]["edges"]["missing"]) == 2
    assert changed["kinds"]["citation"]["correct"] == 1


@pytest.mark.parametrize("field,value", [("split", "development"), ("source", {}), ("review_text", "changed")])
def test_reviews_cannot_change_source_or_holdout(field, value):
    source, gold, predicted = records()
    gold[field] = value
    with pytest.raises(ValueError, match="changed pinned"):
        score([source], [gold], [predicted])


def test_stale_duplicate_missing_prediction():
    source, gold, predicted = records()
    with pytest.raises(ValueError, match="duplicate"):
        score([source, source], [], [])
    with pytest.raises(ValueError, match="missing or stale"):
        score([source], [gold], [])
    source["review_text_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="stale packet"):
        score([source], [], [])


def test_invalid_boundaries_and_ownership():
    for mutate, message in (
        (lambda n: n[2].update(end=21), "outside source"),
        (lambda n: n[2].update(parent="s"), "parent kind"),
        (lambda n: n[4].update(parent="s"), "ownership"),
        (lambda n: n[0].update(parent="s"), "cyclic"),
    ):
        values = copy.deepcopy(nodes())
        mutate(values)
        with pytest.raises(ValueError, match=message):
            graph(values, edges(), packet()["review_text"])


def test_reviewer_mode_is_mandatory():
    source, gold, predicted = records()
    del gold["review_mode"]
    with pytest.raises(ValueError, match="attributed"):
        score([source], [gold], [predicted])


def test_prediction_provenance_cannot_change():
    source, gold, predicted = records()
    predicted["source"] = {"sha256": "b" * 64}
    with pytest.raises(ValueError, match="prediction changed pinned"):
        score([source], [gold], [predicted])
