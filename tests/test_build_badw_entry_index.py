from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_badw_entry_index import build, encode
from resolve_badw_cross_references import EntryIndex


def witness(identifier="pdf:one"):
    return dict(contract_version="badw-pdf-article-witness-v1", id=identifier,
                loc_headword="bcag", loc_headword_reading="bcag", homonym="2",
                volume=2, source_spans=[{"page_id": "page"}],
                entry_start_source_span={"run_start": 1})


def test_actual_entries_only_and_no_invented_urls():
    records = build([{"record_type": "citation"}], [witness()])
    index = EntryIndex(records)
    assert index.identities[("bcag", "2")] == {"pdf:one"}
    assert not index.urls
    assert records[0]["entry_start_source_span"] == {"run_start": 1}


def test_deterministic_order_and_duplicate_labels_remain_ambiguous():
    a, b = witness("pdf:a"), witness("pdf:b")
    assert encode(build([], [b, a])) == encode(build([], [a, b]))
    assert len(EntryIndex(build([], [a, b])).labels["bcag"]) == 2
    with pytest.raises(ValueError, match="duplicate"):
        build([], [a, a])


def test_missing_source_and_unrecognized_contract_fail_closed():
    a = witness()
    a["source_spans"] = []
    with pytest.raises(ValueError, match="source-bound"):
        build([], [a])
    with pytest.raises(ValueError, match="unsupported"):
        build([], [{"contract_version": "catalogue-result"}])
