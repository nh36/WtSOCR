import copy

import pytest

from badw_pdf_candidate_tree import project, COLLECTIONS


def fixture():
    record = {"text": "ཀ་ (r. ka)", "source_span": [2, 9]}
    lexical = {"article_id": "a", **{key: [] for key in COLLECTIONS}}
    lexical["citations"] = [record]
    nested = {"article_id": "a", "divisions": [{"kind": "sense_candidate",
        "text": "Original", "items": []}], "unassigned_source_candidates": [
        {"collection": "citations", "index": 0, "record": record}]}
    return nested, lexical


def test_lossless_unassigned_component_and_reproducibility():
    nested, lexical = fixture()
    original = copy.deepcopy((nested, lexical))
    nodes, edges = project(nested, lexical)
    assert edges == [{"node": "unassigned:0", "kind": "citation", "ordinal": 0}]
    assert nodes[-1]["payload"]["record"] == lexical["citations"][0]
    assert nodes[-1]["parent"] == "root"
    assert project(nested, lexical) == (nodes, edges)
    assert (nested, lexical) == original


def test_missing_duplicate_or_changed_components_fail_closed():
    nested, lexical = fixture()
    nested["unassigned_source_candidates"] = []
    with pytest.raises(ValueError, match="conservation"):
        project(nested, lexical)
    nested, lexical = fixture()
    nested["unassigned_source_candidates"] *= 2
    with pytest.raises(ValueError, match="duplicate"):
        project(nested, lexical)
    nested, lexical = fixture()
    nested = copy.deepcopy(nested)
    nested["unassigned_source_candidates"][0]["record"]["text"] = "changed"
    with pytest.raises(ValueError, match="changed"):
        project(nested, lexical)


def test_identity_mismatch_fails_closed():
    nested, lexical = fixture()
    lexical["article_id"] = "b"
    with pytest.raises(ValueError, match="identity"):
        project(nested, lexical)
