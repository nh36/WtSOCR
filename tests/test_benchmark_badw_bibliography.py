"""Synthetic blind-review benchmark contracts; no live sources."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_badw_bibliography as bench


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def predictions():
    return [{"layer": layer, "citation_id": layer, "resolution": {
        "text": "PW 12", "matches": [{"start": 0, "end": 2,
        "target_status": "accepted_identity", "authority_ids": ["work-1"]}]}}
        for layer in ("html", "pdf")]


def test_blind_sampling_reproducible_and_source_pinned(tmp_path):
    links = write(tmp_path / "links", predictions())
    challenge = write(tmp_path / "challenge", predictions()[:1])
    first, second = tmp_path / "work" / "first", tmp_path / "work" / "second"
    bench.sample(links, challenge, first, 1)
    bench.sample(links, challenge, second, 1)
    assert (first / "blind_packets.jsonl").read_bytes() == (second / "blind_packets.jsonl").read_bytes()
    packets = list(bench.records(first / "blind_packets.jsonl"))
    assert all("resolution" not in r and "authority_ids" not in r for r in packets)
    assert packets[0]["memberships"] == ["benchmark", "challenge"]
    with pytest.raises(ValueError, match="new ignored"):
        bench.sample(links, challenge, first, 1)
    write(challenge, [{**predictions()[0], "resolution": {"text": "changed"}}])
    with pytest.raises(ValueError, match="source text mismatch"):
        bench.sample(links, challenge, tmp_path / "work" / "third", 1)


def test_accuracy_requires_review_and_does_not_conflate_axes(tmp_path):
    links = write(tmp_path / "links", predictions())
    challenge = write(tmp_path / "challenge", [])
    output = tmp_path / "work" / "packets"
    bench.sample(links, challenge, output, 1)
    packets = list(bench.records(output / "blind_packets.jsonl"))
    review = packets[0]
    reviews = write(tmp_path / "reviews", [review])
    with pytest.raises(ValueError, match="exhaustive"):
        bench.score(output / "blind_packets.jsonl", reviews, links)
    review["review"].update(reviewer="independent", evidence_locator="scan:1",
        evidence_sha256="a" * 64, complete_identity_review=True,
        accepted_spans=[{"start": 0, "end": 2, "authority_id": "work-1"}],
        edition_checks=[{"start": 0, "end": 2, "value": "edition-1"}],
        locator_checks=[{"start": 3, "end": 5, "value": "12"}])
    write(reviews, [review])
    result = bench.score(output / "blind_packets.jsonl", reviews, links)
    assert result["identity_precision"] == result["identity_recall"] == 1
    assert result["unreviewed_packets"] == 1
    assert result["counts"]["edition_abstained"] == 1
    assert result["counts"]["locator_abstained"] == 1
    altered = predictions()
    altered[0]["resolution"]["matches"][0]["target_status"] = "candidate"
    write(links, altered)
    assert bench.score(output / "blind_packets.jsonl", reviews, links)["counts"]["identity_false_negative"] == 1
    review["text_sha256"] = "b" * 64
    write(reviews, [review])
    with pytest.raises(ValueError, match="hash mismatch"):
        bench.score(output / "blind_packets.jsonl", reviews, links)
