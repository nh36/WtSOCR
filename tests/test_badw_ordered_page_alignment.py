"""Independent small sequence fixtures: no source corpus required."""
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "ordered_pages", Path(__file__).parents[1] / "scripts/badw_ordered_page_alignment.py")
ordered = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ordered)


def rows(*words):
    return [{"headword": word} for word in words]


def test_normalization_preserves_linguistic_distinctions():
    assert ordered.key(" ‘Gyur  ") == "'gyur"
    assert ordered.key("e\u0301") == ordered.key("é")
    assert ordered.key("ṅ") != ordered.key("n")
    assert ordered.key("'gyur") != ordered.key("gyur")
    assert ordered.similarity("", "") == 0


def test_monotone_alignment_allows_editorial_and_print_gaps():
    assert ordered.align(rows("ka", "unmatched", "kha", "ga"),
                         rows("ka", "kha", "different", "ga")) == [
        (0, 0, 1.0), (2, 1, 1.0), (3, 3, 1.0)]


def test_fixed_anchors_cannot_be_replaced_by_better_spelling_match():
    assert ordered.align(rows("ka", "kha"), rows("ka", "ka", "kha"),
                         fixed=[(0, 1)]) == [(0, 1, 1.0), (1, 2, 1.0)]


@pytest.mark.parametrize("fixed", [[(0, 1), (1, 0)], [(0, 0), (0, 1)], [(2, 0)]])
def test_invalid_anchors_fail_explicitly(fixed):
    with pytest.raises(ValueError):
        ordered.align(rows("ka", "kha"), rows("ka", "kha"), fixed)


def test_repeated_headings_are_not_duplicated_or_reordered():
    result = ordered.align(rows("ka", "ka", "kha"), rows("ka", "ka", "kha"))
    assert result == [(0, 0, 1.0), (1, 1, 1.0), (2, 2, 1.0)]


def test_order_prevents_backtracking_to_an_isolated_ocr_match():
    result = ordered.align(rows("ka", "kha", "ga"), rows("ga", "ka", "kha", "ga"))
    assert result == [(0, 1, 1.0), (1, 2, 1.0), (2, 3, 1.0)]


def test_order_diagnostics_use_checksum_bound_manifest_and_report_inversions():
    html = [dict(sid=str(i), source_url=str(i), html_sha256='current',
                 collation_fallback=(i == 3)) for i in range(4)]
    manifest = {
        'pages': {'a': {'volume': 1, 'printed_page': 15},
                  'b': {'volume': 1, 'printed_page': 14}},
        'witnesses': [dict(source_url=str(i), html_sha256='current',
                           page='a' if i == 0 else 'b') for i in range(4)]
        + [dict(source_url='0', html_sha256='stale', page='a')]}
    result = ordered.ordering_diagnostics(html, manifest)
    assert result['stale_or_missing_identities'] == 1
    volume = result['volumes']['1']
    assert volume['reviewed'] == 4
    assert volume['fallback'] == 1
    assert volume['same_page_order_unchecked'] == 1
    assert volume['comparable_pairs'] == 2
    assert volume['page_inversions'] == 2
