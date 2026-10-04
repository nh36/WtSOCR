#!/usr/bin/env python3
"""Offline blind bibliography review packets and source-reviewed scores.

Packets deliberately omit resolver predictions. Gold reviews must exhaustively
label identity spans; edition and locator checks are separate optional axes.
Bulk citation text, packets and reviews must remain in ignored work/ storage.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from badw_bibliography import dumps, file_digest, write_jsonl


def records(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def key(row):
    return row["layer"], row["citation_id"]


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stratum(text):
    if "⟦UNKNOWN:" in text:
        return "unknown_glyph"
    if "\n" in text:
        return "multiline"
    if re.search(r"(?:19|20)\d{2}", text):
        return "author_year"
    if "/" in text or ";" in text:
        return "compound"
    return "simple"


def sample(links: Path, challenge: Path, output: Path, per_layer=200):
    if per_layer < 1 or output.exists() or "work" not in output.resolve().parts:
        raise ValueError("positive sample size and new ignored work/ output required")
    pools, all_rows = defaultdict(list), {}
    for row in records(links):
        identity = key(row)
        if identity in all_rows:
            raise ValueError("duplicate citation identity")
        all_rows[identity] = row
        text = row["resolution"]["text"]
        pools[(row["layer"], stratum(text))].append(row)
    selected = {}
    for layer in ("html", "pdf"):
        groups = [sorted(pool, key=lambda r: text_hash(dumps(key(r))))
                  for (kind, _), pool in sorted(pools.items()) if kind == layer]
        count = 0
        while count < per_layer and any(groups):
            for group in groups:
                if group and count < per_layer:
                    row = group.pop(0)
                    selected[key(row)] = {"benchmark"}
                    count += 1
        if count != per_layer:
            raise ValueError("insufficient citations for layer " + layer)
    challenge_count = 0
    seen = set()
    for row in records(challenge):
        identity = key(row)
        if identity in seen or identity not in all_rows:
            raise ValueError("duplicate or unknown challenge citation")
        seen.add(identity)
        if row["resolution"]["text"] != all_rows[identity]["resolution"]["text"]:
            raise ValueError("challenge source text mismatch")
        selected.setdefault(identity, set()).add("challenge")
        challenge_count += 1
    packets = []
    for identity, memberships in sorted(selected.items()):
        row = all_rows[identity]
        text = row["resolution"]["text"]
        packets.append({"layer": identity[0], "citation_id": identity[1],
            "text": text, "text_sha256": text_hash(text), "stratum": stratum(text),
            "memberships": sorted(memberships), "review": {
                "reviewer": "", "review_mode": "unspecified", "evidence_locator": "", "evidence_sha256": "",
                "complete_identity_review": False, "accepted_spans": [],
                "edition_checks": [], "locator_checks": []}})
    output.mkdir(parents=True)
    write_jsonl(output / "blind_packets.jsonl", packets)
    manifest = {"version": "bibliography-benchmark-v1", "links_sha256": file_digest(links),
        "challenge_sha256": file_digest(challenge), "per_layer": per_layer,
        "challenge_count": challenge_count, "unique_packets": len(packets),
        "strata": dict(Counter(r["layer"] + ":" + r["stratum"] for r in packets)),
        "packets_sha256": file_digest(output / "blind_packets.jsonl"),
        "limitations": "Sampling is not accuracy. Complete blind source review is required before scoring."}
    (output / "manifest.json").write_text(dumps(manifest) + "\n", encoding="utf-8")
    return manifest


def score(packets: Path, reviews: Path, predictions: Path):
    packet_map = {key(r): r for r in records(packets)}
    if len(packet_map) != sum(1 for _ in records(packets)):
        raise ValueError("duplicate packets")
    predicted = {key(r): r for r in records(predictions)}
    if len(predicted) != sum(1 for _ in records(predictions)):
        raise ValueError("duplicate predictions")
    counts, seen, checked = Counter(), set(), set()
    groups = defaultdict(Counter)
    review_modes = Counter()
    for gold in records(reviews):
        identity = key(gold)
        if identity in seen or identity not in packet_map or identity not in predicted:
            raise ValueError("duplicate or unpinned review identity")
        seen.add(identity)
        packet, prediction = packet_map[identity], predicted[identity]["resolution"]
        if (gold["text_sha256"] != packet["text_sha256"] or
                text_hash(prediction["text"]) != packet["text_sha256"]):
            raise ValueError("source text hash mismatch")
        review = gold["review"]
        if (review["complete_identity_review"] is not True or not review["reviewer"].strip() or
                not review["evidence_locator"].strip() or
                not re.fullmatch("[0-9a-f]{64}", review["evidence_sha256"])):
            raise ValueError("exhaustive source review required")
        mode = review.get("review_mode", "unspecified")
        if mode not in {"unspecified", "same_agent_source_review", "independent_blind_review", "prediction_exposed_review"}:
            raise ValueError("unsupported review mode")
        review_modes[mode] += 1
        evidence = Path(review.get("evidence_path", ""))
        if not evidence.is_file():
            raise ValueError("review evidence file missing")
        evidence_key = str(evidence), review["evidence_sha256"]
        if evidence_key not in checked:
            if file_digest(evidence) != review["evidence_sha256"]:
                raise ValueError("review evidence hash mismatch")
            checked.add(evidence_key)
        expected = set()
        for span in review["accepted_spans"]:
            start, end = span["start"], span["end"]
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(packet["text"]):
                raise ValueError("gold span outside source text")
            expected.add((span["authority_id"], start, end))
        if len(expected) != len(review["accepted_spans"]):
            raise ValueError("duplicate gold spans")
        actual = {(a, m["start"], m["end"]) for m in prediction["matches"]
                  if m["target_status"] == "accepted_identity" for a in m["authority_ids"]}
        counts["reviewed"] += 1
        counts["identity_exact"] += actual == expected
        counts["identity_true_positive"] += len(actual & expected)
        counts["identity_false_positive"] += len(actual - expected)
        counts["identity_false_negative"] += len(expected - actual)
        for group in ("layer:" + packet["layer"], "stratum:" + packet["layer"] + ":" + packet["stratum"],
                      *("membership:" + m for m in packet["memberships"])):
            groups[group].update(reviewed=1, identity_exact=int(actual == expected),
                true_positive=len(actual & expected), false_positive=len(actual - expected),
                false_negative=len(expected - actual))
        for axis in ("edition", "locator"):
            # Future resolvers may supply verified checks. An identity match is
            # never promoted to a successful edition/locator check implicitly.
            outputs = prediction.get(axis + "_checks", [])
            axis_spans = set()
            for check in review[axis + "_checks"]:
                if (type(check["start"]) is not int or type(check["end"]) is not int or
                        not 0 <= check["start"] < check["end"] <= len(packet["text"])):
                    raise ValueError("gold check outside source text")
                span = check["start"], check["end"]
                if span in axis_spans or not check.get("value"):
                    raise ValueError("duplicate or empty gold check")
                axis_spans.add(span)
                counts[axis + "_reviewed"] += 1
                candidates = [p for p in outputs if p["start"] == check["start"] and p["end"] == check["end"]
                              and p.get("status") == "verified"]
                if not candidates:
                    counts[axis + "_abstained"] += 1
                else:
                    counts[axis + "_attempted"] += 1
                    counts[axis + "_correct"] += len(candidates) == 1 and candidates[0]["value"] == check["value"]
    tp = counts["identity_true_positive"]
    return {"counts": dict(sorted(counts.items())),
        "review_modes": dict(sorted(review_modes.items())),
        "independence_status": "declared_only_not_verified",
        "limitations": "Source review scores do not establish independence; edition/locator axes require their own reviewed checks.",
        "groups": {k: dict(sorted(v.items())) for k, v in sorted(groups.items())},
        "unreviewed_packets": len(packet_map) - len(seen),
        "identity_precision": tp / (tp + counts["identity_false_positive"]) if tp + counts["identity_false_positive"] else None,
        "identity_recall": tp / (tp + counts["identity_false_negative"]) if tp + counts["identity_false_negative"] else None,
        "packet_sha256": file_digest(packets), "review_sha256": file_digest(reviews),
        "prediction_sha256": file_digest(predictions)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("sample")
    for name in ("links", "challenge", "output"):
        make.add_argument("--" + name, type=Path, required=True)
    make.add_argument("--per-layer", type=int, default=200)
    check = sub.add_parser("score")
    for name in ("packets", "reviews", "predictions"):
        check.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = (sample(args.links, args.challenge, args.output, args.per_layer) if args.command == "sample"
              else score(args.packets, args.reviews, args.predictions))
    print(dumps(result))


if __name__ == "__main__":
    main()
