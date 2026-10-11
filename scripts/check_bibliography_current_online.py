"""Check hash-pinned online bibliography findings; changed bytes require review.

Offline by default. --refresh uses the existing BAdW content-addressed cache.
An explicit reviewed-corrections JSONL can certify a correction at new hashes:
{"id": "finding-id", "source_sha256": "...", "apparatus_sha256":
 {"https://.../texte": "...", ...}, "evidence": "reviewed exact change"}.
No disappearance of a token, HTTP error or changed hash proves a correction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from badw_source_cache import RequestSpec, SourceCache

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QA = ROOT / "data/bibliography_current_online_qa.jsonl"


def findings(path=DEFAULT_QA):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def classify(finding, observed, correction=None):
    """Only unchanged valid resources or reviewed new evidence yield conclusions."""
    sources = [finding["source"], *finding["apparatus_sources"]]
    if any(not observed.get(s["url"], {}).get("valid") for s in sources):
        return "source_changed_needs_review"
    if all(observed[s["url"]]["sha256"] == s["sha256"] for s in sources):
        return "still_present"
    if correction and correction.get("id") == finding["id"] and correction.get("evidence"):
        expected = {finding["source"]["url"]: correction.get("source_sha256"),
                    **correction.get("apparatus_sha256", {})}
        if all(expected.get(s["url"]) == observed[s["url"]]["sha256"] for s in sources):
            return "corrected_upstream"
    return "source_changed_needs_review"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, default=DEFAULT_QA)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--reviewed-corrections", type=Path)
    args = parser.parse_args()
    items = findings(args.qa)
    corrections = {x["id"]: x for x in findings(args.reviewed_corrections)} if args.reviewed_corrections else {}
    cache = SourceCache(args.cache)
    sources = {s["url"] for i in items for s in [i["source"], *i["apparatus_sources"]]}
    observed = {}
    for url in sorted(sources):
        try:
            response = cache.fetch(RequestSpec(url), refresh=args.refresh, offline=not args.refresh)
            observed[url] = {"valid": response.is_valid_resource,
                             "sha256": response.metadata.get("sha256"),
                             "fetched_at_utc": response.metadata.get("fetch_timestamp_utc")}
        except Exception as exc:
            observed[url] = {"valid": False, "error": str(exc)}
    for item in items:
        print(json.dumps({"id": item["id"], "status": classify(item, observed, corrections.get(item["id"])),
                          "observed": {s["url"]: observed[s["url"]] for s in [item["source"], *item["apparatus_sources"]]}},
                         ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
