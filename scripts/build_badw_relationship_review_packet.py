"""Freeze unseen, source-only relationship review cases, without predictions.

Cue strata are sampling prompts, not asserted relationships or correct answers.
Reviewers must select exact endpoints (or explicitly mark ambiguity). No parser
prediction input is accepted. Exclusions include every previously seen packet,
including untouched holdouts: they must not be recycled as fresh evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from build_badw_structural_review_packet import rows
from build_badw_entry_index import encode

VERSION = "badw-blind-relationship-review-v1"
CUES = {
    "lex_citation": lambda t: "Lex." in t and "(" in t,
    "definition_citation": lambda t: "(" in t and "Lex." not in t,
    "parallel_subspan": lambda t: "Lex." in t and t.count("(") >= 3,
    "definition_subspan": lambda t: "Lex." not in t and t.count("(") >= 2,
    "mixed_passage": lambda t: "(" in t and "\n" in t,
    "grouped_citations": lambda t: bool(re.search(r"\([^)]*[;,][^)]*\)", t)),
    "translation": lambda t: "„" in t,
    "gloss": lambda t: "≈" in t or "skt." in t,
    "cross_reference": lambda t: "↑" in t or "↓" in t,
    "complex_boundary": lambda t: "Lex." in t and "„" in t and "(" in t,
}


def excluded_identities(paths):
    ids = set()
    for path in paths:
        for record in rows(path):
            identity = record.get("identity")
            if not isinstance(identity, str):
                raise ValueError(f"exclusion record without identity: {path}")
            ids.add(identity)
    return ids


def packet(pdf, html, excluded, per_stratum=3, seed="badw-relationships-independent-v1"):
    if per_stratum < 1:
        raise ValueError("positive per-stratum count required")
    # Reuse source fields only, not semantic nodes or parser predictions.
    pool = []
    seen = set()
    for kind, articles in (("pdf", pdf), ("html", html)):
        for article in articles:
            identity = article["article_id"] if kind == "pdf" else article["source_identifier"]
            if identity in seen:
                raise ValueError("duplicate source identity")
            seen.add(identity)
            if identity in excluded:
                continue
            if kind == "pdf":
                text = "\n".join(line["text"] for line in article["visual_lines"])
                source = {k: article[k] for k in ("visual_lines", "source_objects", "source_faithful_text")}
            else:
                text = article["article_source_text"]
                source = {k: article[k] for k in ("source_object", "article_source_text", "dom_full_text")}
            pool.append(dict(identity=identity, source_kind=kind, source=source,
                             volume=article.get("volume"), review_text=text,
                             review_text_sha256=hashlib.sha256(text.encode()).hexdigest()))
    result, used = [], set()
    for cue, predicate in CUES.items():
        for kind in ("html", "pdf"):
            candidates = sorted((r for r in pool if r["source_kind"] == kind and
                                 r["identity"] not in used and predicate(r["review_text"])),
                                key=lambda r: hashlib.sha256((seed+"\0"+cue+"\0"+r["identity"]).encode()).hexdigest())
            chosen = []
            for i in range(per_stratum):
                # Balance PDF volume independently of predicted labels.
                eligible = [r for r in candidates if r not in chosen and
                            (kind != "pdf" or r["volume"] == 2+i % 3)]
                if not eligible:
                    raise ValueError(f"insufficient fresh sources: {kind}/{cue}")
                chosen.append(eligible[0])
            for row in chosen:
                used.add(row["identity"])
                result.append(dict(contract_version=VERSION, sampling_cue=cue,
                                   **row, review_status="pending_independent_review",
                                   reviewed_relationships=[], reviewer=None))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdf", type=Path, required=True)
    p.add_argument("--html", type=Path, required=True)
    p.add_argument("--exclude", type=Path, action="append", required=True)
    p.add_argument("--entry-index", type=Path, required=True,
                   help="pinned actual-entry index, recorded for later blind scoring")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--per-stratum", type=int, default=3,
                   help="positive cases per source kind/cue; PDF cases rotate volumes 2–4")
    p.add_argument("--seed", default="badw-relationships-independent-v1")
    args = p.parse_args()
    if args.output.exists() or args.output.with_suffix(".manifest.json").exists():
        p.error("refusing to overwrite frozen blind packet")
    excluded = excluded_identities(args.exclude)
    records = packet(rows(args.pdf), rows(args.html), excluded,
                     per_stratum=args.per_stratum, seed=args.seed)
    body = encode(records)
    manifest = dict(contract_version=VERSION, cases=len(records), excluded_identities=len(excluded),
                    per_stratum=args.per_stratum, seed=args.seed,
                    sha256=hashlib.sha256(body).hexdigest(), predictions_exposed=False,
                    instructions="Review full source first. Record exact supported passage(s), citation/translation/gloss/link relation, explicit evidence, alternatives and uncertainty. Mark absent phenomena explicitly. Sampling cues are not answers. Inspect cached HTML/PDF where needed; text alone may not settle structure. Do not tune frozen rules against these answers.",
                    inputs=[dict(path=str(x),sha256=hashlib.sha256(x.read_bytes()).hexdigest())
                            for x in [args.pdf,args.html,args.entry_index,*args.exclude]],
                    frozen_rule_files=[dict(path=str(x),sha256=hashlib.sha256(x.read_bytes()).hexdigest())
                        for x in (Path(__file__).resolve(),
                                  Path(__file__).with_name("badw_semantic_annotations.py"),
                                  Path(__file__).with_name("resolve_badw_cross_references.py"),
                                  Path(__file__).with_name("benchmark_badw_structure.py"))])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(body)
    args.output.with_suffix(".manifest.json").write_bytes(encode([manifest]))
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
