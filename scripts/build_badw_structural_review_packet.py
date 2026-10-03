#!/usr/bin/env python3
"""Build a blinded whole-article review packet, never parser-derived gold.

Selection uses source length/quotation density, not predicted semantic labels.
PDF visual lines retain typography and source anchors; HTML retains its raw
DOM-derived text and cached-object identity. All annotation fields start empty.
The default yields 90 PDFs (30 per volume) and 30 HTML articles, 24 held out.
Output contains source material and belongs exclusively in ignored work/.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

VERSION = "badw-structural-review-packet-v1"


def rows(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def select(pdf, html, per_group=30, seed="badw-whole-article-v1"):
    if per_group <= 0 or per_group % 3:
        raise ValueError("per_group must be positive and divisible by three")
    groups = {"pdf:2": [], "pdf:3": [], "pdf:4": [], "html": []}
    seen = set()
    for source_kind, articles in (("pdf", pdf), ("html", html)):
        for article in articles:
            identity = article["article_id"] if source_kind == "pdf" else article["source_identifier"]
            if (source_kind, identity) in seen:
                raise ValueError("duplicate source article identity")
            seen.add((source_kind, identity))
            if source_kind == "pdf":
                text = "\n".join(line["text"] for line in article["visual_lines"])
                group = "pdf:" + str(article["volume"])
                source = {"source_objects": article["source_objects"],
                          "visual_lines": article["visual_lines"],
                          "source_faithful_text": article["source_faithful_text"]}
            else:
                text = article["article_source_text"]
                group = "html"
                source = {"source_object": article["source_object"],
                          "article_source_text": text, "dom_full_text": article["dom_full_text"]}
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            rank = hashlib.sha256((seed + "\0" + identity).encode("utf-8")).hexdigest()
            groups[group].append({"identity": identity, "source_kind": source_kind,
                "source": source, "review_text": text, "review_text_sha256": digest,
                "selection_rank": rank})
    result = []
    count = per_group // 3
    for group, pool in sorted(groups.items()):
        if len(pool) < per_group:
            raise ValueError(f"insufficient source articles in {group}")
        ordered = sorted(pool, key=lambda r: (len(r["review_text"]), r["identity"]))
        pools = {"short": ordered[:max(count, len(pool)//3)],
                 "long": ordered[-max(count, len(pool)//3):]}
        selected = set()
        for stratum in ("short", "long", "quotation_dense"):
            candidates = (pools[stratum] if stratum in pools else
                          sorted(pool, key=lambda r: (-r["review_text"].count("„"), r["selection_rank"])))
            if stratum != "quotation_dense":
                candidates = sorted(candidates, key=lambda r: r["selection_rank"])
            chosen = [r for r in candidates if r["identity"] not in selected][:count]
            for index, row in enumerate(chosen):
                selected.add(row["identity"])
                result.append({"contract_version": VERSION, "group": group,
                    "stratum": stratum, "split": "holdout" if index < count//5 else "development",
                    **row, "review_status": "pending_independent_review",
                    "reviewed_nodes": [], "reviewed_edges": [], "reviewer": None})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite an existing review packet")
    packet = select(rows(args.pdf), rows(args.html))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in packet:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({"articles": len(packet), "holdout": sum(r["split"] == "holdout" for r in packet),
                      "reviewed": 0, "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
