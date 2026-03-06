#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


SAFE_CHAR_MAP = {
    "$": "ś",
    "ı": "i",
    "I": "l",
    "ñ": "ṅ",
    "ä": "ā",
    "Ä": "Ā",
    "ö": "o",
    "Ö": "O",
    "ü": "u",
    "Ü": "U",
    "ã": "ā",
    "Ã": "Ā",
}
TOKEN_RE = re.compile(r"[A-Za-z\u00C0-\u024F\u1E00-\u1EFF\$][A-Za-z\u00C0-\u024F\u1E00-\u1EFF\$'’-]*")
TRANSLIT_CUE_RE = re.compile(
    r"[\u0101\u012B\u016B\u1E5B\u1E5D\u1E37\u1E39\u1E45\u00F1\u1E6D\u1E0D\u1E47\u015B\u1E63\u1E25\u1E43\u1E41]|"
    r"(?:kh|tsh|ts|ph|th|dh|bh|dz|rdz|ng|ny|zh|sh|lh)",
    re.IGNORECASE,
)
GERMAN_UMLAUT_RE = re.compile(r"[äöüÄÖÜß]")
INITIAL_CONFUSABLE_I_RE = re.compile(r"^I(?=[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]{2,})")
ROMAN_NUMERAL_RE = re.compile(r"^(?=[ivxlcdmIVXLCDM]+$)[IVXLCDMivxlcdm]+$")
GERMAN_SUFFIXES = (
    "ung",
    "keit",
    "heit",
    "schaft",
    "lich",
    "isch",
    "chen",
    "tion",
    "ismus",
    "igkeit",
    "weise",
)


@dataclass
class PairStats:
    volume: str
    from_token: str
    to_token: str
    validator_hits: int
    applied_hits: int
    unresolved_hits: int
    rewrite_class: str
    has_translit_cue: bool
    german_risk: bool
    score: int
    decision: str


def classify_rewrite(src: str, dst: str) -> str:
    if src == dst:
        return "none"
    if len(src) != len(dst):
        return "length_change"
    changed = False
    for s_ch, d_ch in zip(src, dst):
        if s_ch == d_ch:
            continue
        if SAFE_CHAR_MAP.get(s_ch) == d_ch:
            changed = True
            continue
        return "other_char_map"
    return "safe_char_map" if changed else "none"


def is_german_risk(token: str) -> bool:
    low = token.lower()
    if GERMAN_UMLAUT_RE.search(token):
        return True
    if any(low.endswith(suffix) for suffix in GERMAN_SUFFIXES):
        return True
    if low[:1].isupper() and low[1:].islower() and TRANSLIT_CUE_RE.search(token) is None:
        return True
    return False


def score_pair(src: str, dst: str, unresolved_hits: int, validator_hits: int) -> tuple[int, str, bool, bool]:
    rewrite_class = classify_rewrite(src, dst)
    has_translit_cue = bool(TRANSLIT_CUE_RE.search(dst) or TRANSLIT_CUE_RE.search(src))
    german_risk = is_german_risk(src) or is_german_risk(dst)

    score = 0
    if rewrite_class == "safe_char_map":
        score += 2
    if unresolved_hits >= 10:
        score += 2
    elif unresolved_hits >= 5:
        score += 1
    if validator_hits >= 25:
        score += 1
    if has_translit_cue:
        score += 1
    if german_risk:
        score -= 3
    if src.isupper() or dst.isupper():
        score -= 1

    decision = "promote" if (not german_risk and unresolved_hits >= 3 and score >= 4) else "hold"
    return score, decision, has_translit_cue, german_risk


def read_tsv(path: str) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def build_pair_stats(run_dir: str) -> list[PairStats]:
    validator_paths = sorted(glob.glob(os.path.join(run_dir, "*_validator_issues.tsv")))
    out: list[PairStats] = []
    for validator_path in validator_paths:
        volume = os.path.basename(validator_path).replace("_validator_issues.tsv", "")
        changes_path = os.path.join(run_dir, f"{volume}_changes.tsv")
        validator_rows = read_tsv(validator_path)
        change_rows = read_tsv(changes_path) if os.path.exists(changes_path) else []

        validator_pairs: Counter[tuple[str, str]] = Counter()
        for row in validator_rows:
            if row.get("issue") != "confusable_char":
                continue
            src = row.get("token", "")
            dst = row.get("suggestion", "")
            if not src or not dst or src == dst:
                continue
            validator_pairs[(src, dst)] += 1

        applied_pairs: Counter[tuple[str, str]] = Counter()
        for row in change_rows:
            if row.get("applied", "1") != "1":
                continue
            src = row.get("from_token", "")
            dst = row.get("to_token", "")
            if not src or not dst or src == dst:
                continue
            applied_pairs[(src, dst)] += 1

        for (src, dst), validator_hits in validator_pairs.items():
            applied_hits = applied_pairs.get((src, dst), 0)
            unresolved_hits = max(0, validator_hits - applied_hits)
            if unresolved_hits == 0:
                continue
            score, decision, has_translit_cue, german_risk = score_pair(
                src=src,
                dst=dst,
                unresolved_hits=unresolved_hits,
                validator_hits=validator_hits,
            )
            out.append(
                PairStats(
                    volume=volume,
                    from_token=src,
                    to_token=dst,
                    validator_hits=validator_hits,
                    applied_hits=applied_hits,
                    unresolved_hits=unresolved_hits,
                    rewrite_class=classify_rewrite(src, dst),
                    has_translit_cue=has_translit_cue,
                    german_risk=german_risk,
                    score=score,
                    decision=decision,
                )
            )
    out.sort(
        key=lambda r: (
            r.decision != "promote",
            -r.unresolved_hits,
            -r.score,
            r.volume,
            r.from_token,
        )
    )
    return out


def extract_artifact_tokens(run_dir: str) -> list[dict[str, str]]:
    corrected_paths = sorted(glob.glob(os.path.join(run_dir, "*_corrected_full.txt")))
    bucket_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for corrected_path in corrected_paths:
        volume = os.path.basename(corrected_path).replace("_corrected_full.txt", "")
        text = Path(corrected_path).read_text(encoding="utf-8", errors="replace")
        for tok in TOKEN_RE.findall(text):
            if "$" in tok:
                bucket_counts[f"{volume}:dollar_artifact"][tok] += 1
            if "ı" in tok:
                bucket_counts[f"{volume}:dotless_i_artifact"][tok] += 1
            if INITIAL_CONFUSABLE_I_RE.match(tok) and not ROMAN_NUMERAL_RE.fullmatch(tok):
                bucket_counts[f"{volume}:initial_confusable_I"][tok] += 1
            if GERMAN_UMLAUT_RE.search(tok) and TRANSLIT_CUE_RE.search(tok):
                bucket_counts[f"{volume}:umlaut_translit_candidate"][tok] += 1

    rows: list[dict[str, str]] = []
    for bucket, counts in sorted(bucket_counts.items()):
        for token, count in counts.most_common(200):
            rows.append(
                {
                    "bucket": bucket,
                    "token": token,
                    "count": str(count),
                }
            )
    return rows


def write_pair_tsv(path: Path, pair_stats: list[PairStats]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "decision",
            "volume",
            "unresolved_hits",
            "validator_hits",
            "applied_hits",
            "score",
            "rewrite_class",
            "has_translit_cue",
            "german_risk",
            "from_token",
            "to_token",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in pair_stats:
            writer.writerow(
                {
                    "decision": row.decision,
                    "volume": row.volume,
                    "unresolved_hits": row.unresolved_hits,
                    "validator_hits": row.validator_hits,
                    "applied_hits": row.applied_hits,
                    "score": row.score,
                    "rewrite_class": row.rewrite_class,
                    "has_translit_cue": "1" if row.has_translit_cue else "0",
                    "german_risk": "1" if row.german_risk else "0",
                    "from_token": row.from_token,
                    "to_token": row.to_token,
                }
            )


def write_artifacts_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["bucket", "token", "count"], delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_summary_md(path: Path, pair_stats: list[PairStats], artifact_rows: list[dict[str, str]], run_dir: str) -> None:
    promote = [r for r in pair_stats if r.decision == "promote"]
    hold = [r for r in pair_stats if r.decision == "hold"]
    artifact_bucket_counts = Counter(row["bucket"] for row in artifact_rows)

    lines = [
        "# Unresolved Bucket Report",
        "",
        f"- run_dir: `{run_dir}`",
        f"- unresolved confusable pairs: `{len(pair_stats)}`",
        f"- promote candidates (conservative): `{len(promote)}`",
        f"- hold candidates: `{len(hold)}`",
        "",
        "## Top Promote Candidates",
    ]
    if not promote:
        lines.append("- none")
    else:
        lines.append("|volume|from|to|unresolved|score|flags|")
        lines.append("|---|---|---|---:|---:|---|")
        for row in promote[:25]:
            flags = []
            if row.german_risk:
                flags.append("german_risk")
            if row.rewrite_class != "safe_char_map":
                flags.append(row.rewrite_class)
            lines.append(
                f"|{row.volume}|{row.from_token}|{row.to_token}|{row.unresolved_hits}|{row.score}|{','.join(flags) or '-'}|"
            )

    lines.extend(
        [
            "",
            "## Top Hold Candidates",
            "|volume|from|to|unresolved|score|reason|",
            "|---|---|---|---:|---:|---|",
        ]
    )
    for row in hold[:25]:
        reason = []
        if row.german_risk:
            reason.append("german_risk")
        if row.rewrite_class != "safe_char_map":
            reason.append(row.rewrite_class)
        if row.unresolved_hits < 3:
            reason.append("low_count")
        lines.append(
            f"|{row.volume}|{row.from_token}|{row.to_token}|{row.unresolved_hits}|{row.score}|{','.join(reason) or '-'}|"
        )
    if not hold:
        lines.append("|-|-|-|0|0|none|")

    lines.extend(["", "## Residual Artifact Buckets"])
    if not artifact_bucket_counts:
        lines.append("- none")
    else:
        for bucket, count in artifact_bucket_counts.most_common():
            lines.append(f"- `{bucket}`: `{count}` distinct tokens")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Report unresolved OCR buckets and conservative promote/hold candidates.")
    parser.add_argument("--run-dir", required=True, help="Postprocess output directory")
    parser.add_argument("--out-prefix", required=True, help="Output file prefix path (without extension)")
    args = parser.parse_args()

    run_dir = args.run_dir
    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    pair_stats = build_pair_stats(run_dir)
    artifact_rows = extract_artifact_tokens(run_dir)

    pairs_tsv = out_prefix.with_suffix(".unresolved_pairs.tsv")
    artifacts_tsv = out_prefix.with_suffix(".artifact_tokens.tsv")
    summary_md = out_prefix.with_suffix(".summary.md")

    write_pair_tsv(pairs_tsv, pair_stats)
    write_artifacts_tsv(artifacts_tsv, artifact_rows)
    write_summary_md(summary_md, pair_stats, artifact_rows, run_dir)

    promote_count = sum(1 for r in pair_stats if r.decision == "promote")
    hold_count = sum(1 for r in pair_stats if r.decision == "hold")
    print(f"run_dir={run_dir}")
    print(f"unresolved_pairs={len(pair_stats)} promote={promote_count} hold={hold_count}")
    print(f"pairs_tsv={pairs_tsv}")
    print(f"artifact_tokens_tsv={artifacts_tsv}")
    print(f"summary_md={summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
