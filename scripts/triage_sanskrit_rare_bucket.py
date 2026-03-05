#!/usr/bin/env python3
import argparse
import csv
import glob
import os
import re
import unicodedata
from collections import Counter, defaultdict


SANSKRIT_REASONS = {"sanskrit_char_normalize", "sanskrit_family_canonicalize"}
TRANSLIT_ZONES = {
    "german_prose_with_translit",
    "example_tibetan_latin",
    "headword_line",
    "latin_other",
}
GERMAN_RISK_SUBSTRINGS = {
    "über",
    "sch",
    "ung",
    "keit",
    "heit",
    "schaft",
    "lich",
    "isch",
    "chen",
    "tion",
    "ismus",
    "gottheit",
    "länder",
    "landern",
}
SAFE_CHAR_MAP = {
    "$": "ś",
    "ä": "ā",
    "ö": "ō",
    "ü": "ū",
    "ı": "i",
    "ñ": "ṅ",
    "Ä": "Ā",
    "Ö": "Ō",
    "Ü": "Ū",
}
SANSKRIT_HINT_RE = re.compile(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁ]")
GERMAN_UMLAUT_RE = re.compile(r"[äöüß]")
GERMAN_INFLECTED_UMLAUT_RE = re.compile(r"[a-zäöüß]{4,}(?:en|ern|er|es|em)$")


def is_sanskrit_like(token: str) -> bool:
    t = unicodedata.normalize("NFC", token).strip()
    if not t:
        return False
    if SANSKRIT_HINT_RE.search(t):
        return True
    if any(ch in t for ch in "$äöüıñ"):
        return True
    lowered = t.lower()
    if any(chunk in lowered for chunk in ("bh", "dh", "kh", "th", "śr", "jñ", "carya", "sattva", "madhya")):
        return True
    return False


def german_risk(token: str) -> bool:
    lowered = unicodedata.normalize("NFC", token).lower()
    if "-" in lowered or "/" in lowered:
        segments = [s for s in re.split(r"[-/]+", lowered) if s]
        if any(is_sanskrit_like(seg) for seg in segments):
            # Mixed compounds with a Sanskrit-looking segment are handled as candidates.
            return False
    if any(s in lowered for s in GERMAN_RISK_SUBSTRINGS):
        return True
    if "-" not in lowered and "/" not in lowered:
        if GERMAN_UMLAUT_RE.search(lowered) and GERMAN_INFLECTED_UMLAUT_RE.search(lowered):
            return True
    return False


def classify_rewrite(src: str, dst: str) -> str:
    src = unicodedata.normalize("NFC", src)
    dst = unicodedata.normalize("NFC", dst)
    if src == dst:
        return "none"
    if len(src) != len(dst):
        return "length_change"
    changes = []
    for a, b in zip(src, dst):
        if a != b:
            changes.append((a, b))
    if not changes:
        return "none"
    if all(SAFE_CHAR_MAP.get(a) == b for a, b in changes):
        return "safe_char_map"
    return "other_char_map"


def load_sets(run_dir: str):
    to_in_changes = set()
    to_in_report = set()
    for path in glob.glob(os.path.join(run_dir, "*_changes.tsv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                reason = row.get("reason", "")
                if reason.startswith("sanskrit_"):
                    to_in_changes.add(row.get("to_token", ""))
    for path in glob.glob(os.path.join(run_dir, "*_sanskrit_report.tsv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                conf = row.get("confidence", "")
                if conf in {"high", "medium"}:
                    to_in_report.add(row.get("canonical", ""))
    return to_in_changes, to_in_report


def run_triage(run_dir: str, out_tsv: str):
    to_in_changes, to_in_report = load_sets(run_dir)
    grouped = defaultdict(list)

    for path in glob.glob(os.path.join(run_dir, "*_review_queue.tsv")):
        vol = os.path.basename(path).replace("_review_queue.tsv", "")
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                if row.get("reason") not in SANSKRIT_REASONS:
                    continue
                key = (row.get("from_token", ""), row.get("to_token", ""))
                grouped[key].append(
                    {
                        "vol": vol,
                        "zone": row.get("zone", ""),
                        "line_excerpt": row.get("line_excerpt", ""),
                        "page": row.get("page", ""),
                        "line": row.get("line", ""),
                        "reason": row.get("reason", ""),
                    }
                )

    rows = []
    for (src, dst), hits in grouped.items():
        count = len(hits)
        if count > 2:
            continue
        zones = Counter(h["zone"] for h in hits)
        translit_hits = sum(1 for h in hits if h["zone"] in TRANSLIT_ZONES)
        mvy_hits = sum(1 for h in hits if "(Mvy" in h["line_excerpt"])
        rewrite = classify_rewrite(src, dst)
        src_like = is_sanskrit_like(src)
        dst_like = is_sanskrit_like(dst)
        risky = german_risk(src) or german_risk(dst)
        in_changes = dst in to_in_changes
        in_report = dst in to_in_report

        score = 0
        if rewrite == "safe_char_map":
            score += 2
        if src_like or dst_like:
            score += 1
        if translit_hits == count:
            score += 1
        if mvy_hits > 0:
            score += 1
        if in_changes:
            score += 1
        if in_report:
            score += 1
        if risky:
            score -= 2

        singleton_safe_char_promote = (
            count == 1
            and rewrite == "safe_char_map"
            and translit_hits == count
            and (src_like or dst_like)
            and not risky
        )
        if count == 2:
            decision = "promote" if score >= 4 and not risky else "hold"
        else:
            decision = "promote" if (score >= 5 and not risky) or singleton_safe_char_promote else "hold"

        evidence = []
        if rewrite == "safe_char_map":
            evidence.append("safe_char_map")
        if translit_hits == count:
            evidence.append("translit_only")
        if mvy_hits:
            evidence.append("has_mvy")
        if in_changes:
            evidence.append("to_seen_in_changes")
        if in_report:
            evidence.append("to_seen_in_report")
        if risky:
            evidence.append("german_risk")
        if singleton_safe_char_promote:
            evidence.append("singleton_safe_char_map_promote")

        ex = hits[0]
        rows.append(
            {
                "decision": decision,
                "count": count,
                "score": score,
                "from_token": src,
                "to_token": dst,
                "rewrite_class": rewrite,
                "evidence": ",".join(evidence),
                "volumes": ",".join(sorted({h["vol"] for h in hits})),
                "zones": ",".join(f"{k}:{v}" for k, v in zones.items()),
                "mvy_hits": mvy_hits,
                "example_ref": f'{ex["vol"]}:{ex["page"]}:{ex["line"]}',
                "example_excerpt": ex["line_excerpt"][:220],
            }
        )

    rows.sort(key=lambda r: (r["decision"] != "promote", -r["score"], -r["count"], r["from_token"]))
    with open(out_tsv, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "decision",
            "count",
            "score",
            "from_token",
            "to_token",
            "rewrite_class",
            "evidence",
            "volumes",
            "zones",
            "mvy_hits",
            "example_ref",
            "example_excerpt",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    promote = sum(1 for r in rows if r["decision"] == "promote")
    hold = sum(1 for r in rows if r["decision"] == "hold")
    print(f"rare_pairs={len(rows)} promote={promote} hold={hold} out={out_tsv}")


def main():
    p = argparse.ArgumentParser(description="Triage rare Sanskrit review-queue candidates.")
    p.add_argument("--run-dir", required=True, help="Postprocess output dir containing *_review_queue.tsv")
    p.add_argument("--out-tsv", required=True, help="Output TSV path for promote/hold decisions")
    args = p.parse_args()
    run_triage(args.run_dir, args.out_tsv)


if __name__ == "__main__":
    main()
