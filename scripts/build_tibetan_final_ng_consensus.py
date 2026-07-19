#!/usr/bin/env python3
"""Build corpus-consensus diagnostics for Tibetan final-ṅ OCR variants."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


LATIN_TOKEN_RE = re.compile(
    r"[A-Za-zĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷŃńŇň'’.-]+"
)
POSTPROCESS_TOKEN_RE = re.compile(
    r"[0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňß$]+"
    r"(?:['’.$-][0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňß$]+)*"
)
TIBETAN_BLOCK_RE = re.compile(r"[\u0F00-\u0FFF][\u0F00-\u0FFF\s]*")
TIBETAN_SYLLABLE_RE = re.compile(r"[\u0F40-\u0FBC]+")
SOURCE_FINALS = "nñńňh"
GERMAN_STOP_WORDS = {
    "auch", "bez", "die", "der", "das", "ein", "eine", "einer", "für",
    "kurzf", "lex", "macht", "npr", "oder", "und", "vgl",
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def tibetan_syllables_and_tail(line: str) -> tuple[list[str], str, int]:
    blocks = list(TIBETAN_BLOCK_RE.finditer(line))
    if not blocks:
        return [], "", 0
    block = blocks[0]
    syllables = TIBETAN_SYLLABLE_RE.findall(block.group(0))
    tail_start = block.end()
    while tail_start < len(line) and line[tail_start].isspace():
        tail_start += 1
    return syllables, line[tail_start:], tail_start


def latin_headword_tokens(tail: str, limit: int) -> list[tuple[str, int]]:
    tokens: list[tuple[str, int]] = []
    for index, match in enumerate(LATIN_TOKEN_RE.finditer(tail), start=1):
        raw = match.group(0)
        token = raw.strip(".-'’")
        if not token:
            continue
        if token.lower() in GERMAN_STOP_WORDS:
            break
        leading = len(raw) - len(raw.lstrip(".-'’"))
        tokens.append((token, match.start() + leading))
        if len(tokens) >= limit:
            break
    return tokens


def ends_in_tibetan_ng(syllable: str) -> bool:
    return syllable.endswith("ང") or syllable.endswith("ངས")


def nasal_skeleton(token: str) -> str:
    if not token:
        return token
    lower = token.lower()
    if lower.endswith("ṅs"):
        return lower[:-2] + "ns"
    if lower[-1:] in set(SOURCE_FINALS + "ṅ"):
        return lower[:-1] + "n"
    return lower


def source_variant_for_target(source: str, target: str) -> bool:
    if source == target or "ṅ" not in target.lower():
        return False
    if nasal_skeleton(source) != nasal_skeleton(target):
        return False
    return source.lower().endswith(tuple(SOURCE_FINALS))


def collect_aligned_rows(
    release_root: Path,
) -> tuple[list[dict[str, str]], dict[str, Counter[str]]]:
    aligned: list[dict[str, str]] = []
    accepted: dict[str, Counter[str]] = defaultdict(Counter)
    for volume_dir in sorted((release_root / "qa").glob("wts_*")):
        volume = volume_dir.name
        zones_path = volume_dir / f"{volume}_line_zones.tsv"
        if not zones_path.exists():
            continue
        for row in read_tsv(zones_path):
            line = row.get("line_text", "")
            syllables, tail, tail_start = tibetan_syllables_and_tail(line)
            if not syllables:
                continue
            latin = latin_headword_tokens(tail, len(syllables))
            if len(latin) < len(syllables):
                continue
            for position, syllable in enumerate(syllables):
                if not ends_in_tibetan_ng(syllable):
                    continue
                token, tail_token_start = latin[position]
                absolute_start = tail_start + tail_token_start
                token_index = next(
                    (
                        index
                        for index, match in enumerate(
                            POSTPROCESS_TOKEN_RE.finditer(line),
                            start=1,
                        )
                        if match.start() == absolute_start
                    ),
                    None,
                )
                if token_index is None:
                    continue
                aligned_row = {
                    "volume": volume,
                    "page": row["page"],
                    "line": row["line"],
                    "token_index": str(token_index),
                    "tibetan_syllable": syllable,
                    "latin_token": token,
                    "context_excerpt": line,
                    "zone": row.get("zone", ""),
                }
                aligned.append(aligned_row)
                if "ṅ" in token.lower():
                    accepted[syllable][token] += 1
    return aligned, accepted


def build_consensus_rows(release_root: Path) -> list[dict[str, str]]:
    aligned, accepted = collect_aligned_rows(release_root)
    rows: list[dict[str, str]] = []
    for row in aligned:
        forms = accepted.get(row["tibetan_syllable"], Counter())
        if not forms:
            continue
        target, target_count = forms.most_common(1)[0]
        competing = Counter(forms)
        competing.pop(target, None)
        source = row["latin_token"]
        if not source_variant_for_target(source, target):
            continue
        total_accepted = sum(forms.values())
        dominant = target_count >= 2 and (
            not competing
            or target_count >= 3 * sum(competing.values())
        )
        damaged = bool(re.search(r"[{}?¡£$%]|\d{2,}|SQ", row["context_excerpt"]))
        marker = source[:1] in {"T", "I", "\\", "/"}
        if marker:
            category = "marker_attached"
            confidence = "manual"
            action = "separate_marker_and_final_ng_review"
            deferred = "Reference-marker reconstruction requires independent evidence."
        elif damaged:
            category = "damaged_context"
            confidence = "manual"
            action = "manual_alignment_review"
            deferred = "Other OCR damage remains on the aligned phrase."
        elif dominant:
            category = "dominant_internal_consensus"
            confidence = "high"
            action = "exact_review_candidate"
            deferred = ""
        else:
            category = "competing_latin_forms"
            confidence = "low"
            action = "defer"
            deferred = "Accepted dotted forms do not yet establish a dominant internal consensus."
        rows.append(
            {
                "volume": row["volume"],
                "page": row["page"],
                "line": row["line"],
                "token_index": row["token_index"],
                "tibetan_syllable": row["tibetan_syllable"],
                "source_latin_token": source,
                "proposed_latin_target": target,
                "accepted_form_count": str(target_count),
                "competing_form_counts": "; ".join(
                    f"{form}:{count}" for form, count in competing.most_common()
                ),
                "alignment_category": category,
                "evidence_type": "positionally_aligned_corpus_consensus",
                "confidence": confidence,
                "suggested_action": action,
                "context_excerpt": row["context_excerpt"],
                "reason_for_deferral": deferred,
                "accepted_total": str(total_accepted),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["proposed_latin_target"],
            row["volume"],
            int(row["page"]),
            int(row["line"]),
            int(row["token_index"]),
        ),
    )


FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "source_latin_token", "proposed_latin_target", "accepted_form_count",
    "competing_form_counts", "alignment_category", "evidence_type",
    "confidence", "suggested_action", "context_excerpt", "reason_for_deferral",
    "accepted_total",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=Path("release/current"))
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args()
    rows = build_consensus_rows(args.release_root)
    by_volume: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_volume[row["volume"]].append(row)
    for volume in ["wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"]:
        write_tsv(
            args.out_root / f"tibetan_cleanup_diagnostics_{volume}"
            / "tibetan_final_ng_consensus_candidates.tsv",
            by_volume.get(volume, []),
            FIELDS,
        )
    counts = Counter(row["alignment_category"] for row in rows)
    print(f"candidates={len(rows)}")
    for category, count in sorted(counts.items()):
        print(f"{category}={count}")


if __name__ == "__main__":
    main()
