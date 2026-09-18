from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from badw_article_parser import parse_database_article  # noqa: E402
from extract_badw_lexical_records import extract_article, extract_jsonl  # noqa: E402
from validate_lexical_record_contract import validate  # noqa: E402


ARTICLE_BYTES = (ROOT / "tests" / "fixtures" / "badw" / "article.html").read_bytes()
SOURCE = {
    "sha256": __import__("hashlib").sha256(ARTICLE_BYTES).hexdigest(),
    "delivery_type": "database_article",
    "valid_resource": True,
    "content_classification": "database_article",
    "final_url": "https://wts-digital.badw.de/lemma/ka/2",
}


def article() -> dict[str, object]:
    return parse_database_article(ARTICLE_BYTES, source_metadata=SOURCE)


def test_emits_source_faithful_semantic_records_without_bibliography_guesses() -> None:
    records = extract_article(article(), snapshot_id="snapshot", extraction_run_id="run")
    assert validate(records) == []
    entry = records[0]
    assert entry["layer"] == "badw_editorial"
    assert entry["headword"] == {"loc": "kā", "tibetan": "ཀ་"}
    assert entry["homonym"] == "2"
    senses = [record for record in records if record["record_type"] == "sense"]
    assert [sense["source_label"] for sense in senses] == ["1", "2"]
    assert "erste Bedeutung" in senses[0]["definition"]
    attestations = [record for record in records if record["record_type"] == "attestation"]
    assert len(attestations) == 1
    assert attestations[0]["association_status"] == "explicit"
    assert attestations[0]["tibetan"] == "ཀ་ཁ་"
    citations = [record for record in records if record["record_type"] == "citation"]
    assert len(citations) == 1
    assert citations[0]["siglum"] == "TS"
    assert citations[0]["authority_status"] == "unresolved"
    assert "bibliographic_source_id" not in citations[0]
    refs = [record for record in records if record["record_type"] == "cross_reference"]
    assert [(record["marker"], record["target_label"]) for record in refs] == [("↑", "kha"), ("↓", "ga")]
    assert all(span["field"] == "article_source_text" for record in records for span in record["source_spans"])
    source_text = article()["article_source_text"]
    assert all(
        source_text[span["start"]:span["end"]]
        for record in records
        for span in record["source_spans"]
    )


def test_jsonl_emission_is_deterministic_and_keeps_structural_failures_as_diagnostics() -> None:
    good = article()
    broken = article()
    broken["lemma_field"] = None
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        input_path = root / "articles.jsonl"
        input_path.write_text("\n".join(json.dumps(value, ensure_ascii=False) for value in [broken, good]) + "\n", encoding="utf-8")
        paths = [(root / f"records-{number}.jsonl", root / f"diagnostics-{number}.jsonl", root / f"manifest-{number}.json") for number in (1, 2)]
        first = extract_jsonl(input_path, *paths[0], snapshot_id="fixture")
        second = extract_jsonl(input_path, *paths[1], snapshot_id="fixture")
        assert first == second == {"articles": 2, "diagnostics": 1, "records": 7, "snapshot_id": "fixture"}
        assert paths[0][0].read_bytes() == paths[1][0].read_bytes()
        assert paths[0][1].read_bytes() == paths[1][1].read_bytes()
        diagnostics = [json.loads(line) for line in paths[0][1].read_text(encoding="utf-8").splitlines()]
        assert diagnostics == [{"reason": "lemma lacks source_text", "source_identifier": "badw:https://wts-digital.badw.de/lemma/ka/2"}]
