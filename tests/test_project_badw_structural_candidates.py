"""Tiny synthetic Unicode/ownership examples; no copied BAdW source corpus."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from project_badw_structural_candidates import (
    citation_challenge, citation_inventory, digest, project, project_html, write,
)


def fixture():
    text = 'ka (r.ka) „Deutsch“ (A: 1)'
    source = {"source_objects": [{"sha256": "a" * 64}], "visual_lines": [{"text": text}]}
    packet = dict(identity="pdf:a", source_kind="pdf", source=source,
                  review_text=text, review_text_sha256=digest(text),
                  group="pdf:2", stratum="short", split="development")

    def span(start, end):
        return dict(visual_start=start, visual_end=end, text=text[start:end],
                    source_lines=[{"line_index": 0, "page_id": "p1"}])
    end = len(text)
    members = {"belegstellen": span(0, end), "tibetan_examples": span(0, 9),
               "translations": span(10, 19), "citations": span(20, end)}
    correction = dict(visual_start=3, visual_end=9, literal_text="(r.ka)",
                      proposed_reading="ka", interpretation="printed_apparatus_not_applied",
                      source_lines=[{"line_index": 0}])
    item = dict(kind="belegstelle_candidate", components=members,
                references={k: 0 for k in members}, corrections=[correction])
    nested = dict(article_id="pdf:a", volume=2, loc_headword="ka", visual_sha256=digest(text),
                  source_objects=source["source_objects"], unassigned_source_candidates=[],
                  divisions=[dict(division_index=0, kind="unsegmented_source_division", source_text=text,
                                  start_line_index=0, end_line_index_exclusive=1, items=[item])])
    return packet, nested


def test_lossless_unicode_apparatus_and_provenance():
    packet, nested = fixture()
    result = project(packet, nested)
    assert result == project(packet, copy.deepcopy(nested))
    assert result["source"] == packet["source"]
    assert result["nodes"][0]["kind"] == "source_division"
    assert not any(n["kind"] == "sense" for n in result["nodes"])
    assert any(n["kind"] == "correction" for n in result["nodes"])
    assert result["original_components"][-1]["component"]["literal_text"] == "(r.ka)"
    assert result["original_components"][-1]["component"]["proposed_reading"] == "ka"
    assert len(result["edges"]) == 2
    assert len(result["nested_record_sha256"]) == 64


@pytest.mark.parametrize("mutate", [
    lambda p, n: p.update(review_text_sha256="b" * 64),
    lambda p, n: n.update(article_id="other"),
    lambda p, n: n.update(source_objects=[]),
    lambda p, n: p["source"]["visual_lines"][0].update(text="other"),
    lambda p, n: n["divisions"][0]["items"][0]["components"]["citations"].update(text="invented"),
    lambda p, n: n["divisions"][0]["items"][0]["corrections"][0].update(literal_text="(r. ga)"),
])
def test_changed_source_fails(mutate):
    packet, nested = fixture()
    mutate(packet, nested)
    with pytest.raises(ValueError):
        project(packet, nested)


def test_unassigned_citation_remains_unassigned_and_inventory_deduplicates():
    packet, nested = fixture()
    item = nested["divisions"][0]["items"][0]
    item.update(kind="unassigned_citation_candidate", corrections=[],
                components={"citations": item["components"]["citations"]}, references={"citations": 0})
    result = project(packet, nested)
    assert result["edges"] == []
    assert result["unprojected"][0]["kind"] == "unassigned_citation_candidate"
    inventory = citation_inventory([nested])
    assert inventory[0]["ownership"] is None
    assert inventory[0]["citation"] == item["components"]["citations"]
    with pytest.raises(ValueError, match="duplicate unassigned citation"):
        citation_inventory([nested, nested])
    other = copy.deepcopy(nested)
    other["article_id"] = "pdf:z"
    assert citation_inventory([nested, other]) == citation_inventory([other, nested])


def test_definition_citation_is_not_promoted_to_example():
    packet, nested = fixture()
    item = nested["divisions"][0]["items"][0]
    item["kind"] = "definition_candidate"
    item["components"]["definitions"] = item["components"].pop("belegstellen")
    item["references"]["definitions"] = item["references"].pop("belegstellen")
    result = project(packet, nested)
    assert result["nodes"][1]["kind"] == "definition"
    assert result["edges"][-1]["to"] == result["nodes"][1]["id"]


def test_writer_is_deterministic_and_cannot_overwrite(tmp_path):
    paths = [tmp_path / "a.jsonl", tmp_path / "b.jsonl"]
    for path in paths:
        write(path, [{"tibetan": "ཀ", "loc": "ṅa"}])
    assert paths[0].read_bytes() == paths[1].read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        write(paths[0], [])


def html_fixture():
    text = 'ཀ་ ka\nSache. ka „Ding“ (A: 1)'
    source = {"article_source_text": text, "source_object": {"sha256": "a" * 64}}
    packet = dict(identity="html:a", source_kind="html", source=source, review_text=text,
                  review_text_sha256=digest(text), group="html", stratum="short", split="development")

    def span(value, start=0):
        a = text.index(value, start)
        return dict(start=a, end=a + len(value), field="article_source_text",
                    source_id=packet["identity"], source_sha256="a" * 64)

    records = [
        dict(id="entry", record_type="entry", headword={"loc": "ka", "tibetan": "ཀ་"},
             source_spans=[span("ka"), span("ཀ་")]),
        dict(id="sense", entry_id="entry", record_type="sense", ordinal=1, source_label="",
             definition="Sache.", source_spans=[span("Sache.")]),
        dict(id="example", entry_id="entry", record_type="attestation", sense_id="sense",
             association_status="explicit", citation_ids=["cite"], tibetan="ka",
             german_translation="„Ding“", source_spans=[span("ka", 6), span("„Ding“")]),
        dict(id="cite", entry_id="entry", record_type="citation", raw_text="(A: 1)",
             source_spans=[span("(A: 1)")]),
    ]
    return packet, records


def test_html_claim_adapter_preserves_exact_fields_and_original_records():
    packet, records = html_fixture()
    result = project_html(packet, records)
    assert result == project_html(packet, list(reversed(records)))
    assert len(result["original_records"]) == 4
    assert len(result["edges"]) == 2
    assert not any(n["kind"] == "sense" for n in result["nodes"])
    assert result["source"] == packet["source"]
    assert {n["kind"] for n in result["nodes"]} == {
        "headword", "source_division", "definition", "example", "tibetan", "translation", "citation"}


@pytest.mark.parametrize("mutate", [
    lambda p, r: r[2].update(tibetan="ga"),
    lambda p, r: r[0]["source_spans"][0].update(source_sha256="b" * 64),
    lambda p, r: r[0]["source_spans"][0].update(source_id="other"),
    lambda p, r: r[1].update(entry_id="other"),
    lambda p, r: r[2].update(citation_ids=["missing"]),
    lambda p, r: p["source"].update(article_source_text="other"),
])
def test_html_changed_or_orphan_claims_fail_closed(mutate):
    packet, records = html_fixture()
    mutate(packet, records)
    with pytest.raises(ValueError):
        project_html(packet, records)


def test_shared_html_citation_has_no_invented_single_owner():
    packet, records = html_fixture()
    other = copy.deepcopy(records[2])
    # A second claim for the same fields is malformed (duplicate typed spans)
    # rather than a reason to silently pick an owner.
    other["id"] = "other"
    with pytest.raises(ValueError, match="duplicate typed source span"):
        project_html(packet, records + [other])
    records[2]["association_status"] = "uncertain"
    result = project_html(packet, records)
    assert not result["edges"]
    assert any(x["reason"] == "citation owner not asserted" for x in result["unprojected"])


def test_challenge_is_balanced_deterministic_pending_and_not_gold():
    records = [dict(volume=v, loc_headword=str(i), article_id=f"{v}:{i}", citation_index=0,
                    review_status="pending_source_ownership_review", ownership=None)
               for v in (2, 3, 4) for i in range(40)]
    challenge = citation_challenge(records)
    assert challenge == citation_challenge(list(reversed(records)))
    assert len(challenge) == 60
    assert all(x["ownership"] is None for x in challenge)
    assert all(sum(x["volume"] == v for x in challenge) == 20 for v in (2, 3, 4))
    assert citation_challenge([]) == []
    with pytest.raises(ValueError):
        citation_challenge(records, 0)
