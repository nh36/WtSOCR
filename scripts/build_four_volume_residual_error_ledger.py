#!/usr/bin/env python3
"""Build a four-volume residual OCR cleanup ledger.

The project now has several narrower QA reports: Sanskrit residual reports,
Tibetan cleanup diagnostics, alternate-witness adoption/unresolved TSVs, review
queues, and watchdog files. This script normalizes those local inventories into
one grouped "error budget" so the next cleanup batch can be selected
systematically.

The output is diagnostic only. It does not change corrected text and it does not
promote Google Vision readings or validator suggestions.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable


VOLUME_ORDER = ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m", "unknown")

RELEVANT_EXACT_FILES = {
    "tibetan_variant_families.tsv",
    "tibetan_orthography_damage_candidates.tsv",
    "tibetan_google_candidate_readings.tsv",
    "tibetan_google_adoption_patterns.tsv",
    "sigla_variant_candidates.tsv",
    "residual_sanskrit_damage_candidates.tsv",
    "residual_sanskrit_damage_families.tsv",
    "residual_sanskrit_damage_top_candidates.tsv",
    "residual_sanskrit_promotable_candidates.tsv",
    "residual_sanskrit_low_confidence_candidates.tsv",
    "google_sanskrit_candidate_readings.tsv",
    "possible_missed_google_readings.tsv",
    "all_sanskrit_review_suggestions.tsv",
    "live_remaining_suspicious_tokens.tsv",
    "live_validator_only_residue.tsv",
    "live_review_queue_candidates.tsv",
    "live_google_supported_candidates.tsv",
    "live_policy_or_false_positive.tsv",
    "manual_review_only_suspicious_tokens.tsv",
    "sanskrit_or_indic_policy_suspicious_tokens.tsv",
    "citation_or_siglum_suspicious_tokens.tsv",
    "stale_or_already_corrected_suspicious_tokens.tsv",
    "german_false_positive_validator_tokens.tsv",
    "suspicious_token_classification_summary.tsv",
}

RELEVANT_SUFFIXES = (
    "_alternate_witness_adoptions.tsv",
    "_alternate_witness_unresolved.tsv",
    "_review_queue.tsv",
    "_watchdog_flags.tsv",
    "_watchdog_rows.tsv",
)

SIGLUM_FAMILY_RE = re.compile(r"(sigl|citation|bibliograph)", re.IGNORECASE)
SANSKRIT_FILE_RE = re.compile(r"sanskrit|prajna|samsara", re.IGNORECASE)
TIBETAN_FILE_RE = re.compile(r"tibetan", re.IGNORECASE)
VALIDATOR_FILE_RE = re.compile(r"validator|live_validator", re.IGNORECASE)
WATCHDOG_FILE_RE = re.compile(r"watchdog", re.IGNORECASE)
REVIEW_QUEUE_FILE_RE = re.compile(r"review_queue|review_suggestions", re.IGNORECASE)
GOOGLE_FILE_RE = re.compile(r"google|alternate_witness", re.IGNORECASE)
POLICY_FILE_RE = re.compile(r"policy|false_positive|german_false_positive|indic", re.IGNORECASE)
STALE_FILE_RE = re.compile(r"stale|already_corrected", re.IGNORECASE)

TOKEN_SPLIT_RE = re.compile(r";\s*")
COUNT_SUFFIX_RE = re.compile(r"\s+\(\d+\)$")
WHITESPACE_RE = re.compile(r"\s+")


def clean_counted_token(value: str) -> str:
    """Strip display-count suffixes such as ``dnos (38)``."""
    return COUNT_SUFFIX_RE.sub("", (value or "").strip())


def split_display_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for part in TOKEN_SPLIT_RE.split(value or ""):
        token = clean_counted_token(part)
        if token:
            tokens.append(token)
    return tokens


def compact(value: str, limit: int = 160) -> str:
    value = WHITESPACE_RE.sub(" ", (value or "").strip())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def int_field(row: dict[str, str], *names: str, default: int = 1) -> int:
    for name in names:
        value = (row.get(name) or "").strip()
        if not value:
            continue
        try:
            return max(0, int(value))
        except ValueError:
            continue
    return default


def first_field(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = (row.get(name) or "").strip()
        if value:
            return value
    return ""


def infer_volume(path: Path, row: dict[str, str]) -> str:
    explicit = (row.get("volume") or "").strip()
    if explicit:
        return normalize_volume(explicit)
    text = str(path).lower().replace("-", "_")
    for volume in VOLUME_ORDER:
        if volume != "unknown" and volume in text:
            return volume
    if "wts_8_b" in text or "wts_8b" in text:
        return "wts_8_b"
    if "wts_9_m" in text or "wts_9m" in text:
        return "wts_9_m"
    return "unknown"


def normalize_volume(value: str) -> str:
    value = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "wts_1_34": "wts_1_34",
        "wts1_34": "wts_1_34",
        "1_34": "wts_1_34",
        "wts_35_51": "wts_35_51",
        "wts35_51": "wts_35_51",
        "35_51": "wts_35_51",
        "wts_8_b": "wts_8_b",
        "wts_8b": "wts_8_b",
        "8_b": "wts_8_b",
        "wts_9_m": "wts_9_m",
        "wts_9m": "wts_9_m",
        "9_m": "wts_9_m",
    }
    return aliases.get(value, value or "unknown")


def relevant_tsv(path: Path) -> bool:
    name = path.name
    return name in RELEVANT_EXACT_FILES or any(name.endswith(suffix) for suffix in RELEVANT_SUFFIXES)


def collect_tsv_paths(input_roots: Iterable[Path]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in input_roots:
        if root.is_file() and relevant_tsv(root):
            candidate_paths = [root]
        elif root.is_dir():
            candidate_paths = sorted(path for path in root.rglob("*.tsv") if relevant_tsv(path))
        else:
            candidate_paths = []
        for path in candidate_paths:
            resolved = path.resolve()
            if resolved not in seen:
                paths.append(path)
                seen.add(resolved)
    return sorted(paths)


def queue_source_for_path(path: Path) -> str:
    name = path.name
    if name == "tibetan_variant_families.tsv":
        return "tibetan_variant_families"
    if name == "tibetan_orthography_damage_candidates.tsv":
        return "tibetan_orthography_damage"
    if name == "tibetan_google_candidate_readings.tsv":
        return "tibetan_google_candidates"
    if name == "tibetan_google_adoption_patterns.tsv":
        return "tibetan_google_adoption_patterns"
    if name == "sigla_variant_candidates.tsv":
        return "sigla_variants"
    if name.startswith("residual_sanskrit"):
        return name.removesuffix(".tsv")
    if name in {"google_sanskrit_candidate_readings.tsv", "possible_missed_google_readings.tsv"}:
        return name.removesuffix(".tsv")
    if name == "all_sanskrit_review_suggestions.tsv":
        return "sanskrit_review_suggestions"
    if name == "live_validator_only_residue.tsv":
        return "live_validator_only_residue"
    if name == "live_review_queue_candidates.tsv":
        return "live_review_queue_candidates"
    if name == "live_google_supported_candidates.tsv":
        return "live_google_supported_candidates"
    if name == "live_policy_or_false_positive.tsv":
        return "live_policy_or_false_positive"
    if name == "manual_review_only_suspicious_tokens.tsv":
        return "manual_review_only_suspicious_tokens"
    if name == "sanskrit_or_indic_policy_suspicious_tokens.tsv":
        return "sanskrit_or_indic_policy_suspicious_tokens"
    if name == "citation_or_siglum_suspicious_tokens.tsv":
        return "citation_or_siglum_suspicious_tokens"
    if name == "stale_or_already_corrected_suspicious_tokens.tsv":
        return "stale_or_already_corrected_suspicious_tokens"
    if name == "german_false_positive_validator_tokens.tsv":
        return "german_false_positive_validator_tokens"
    if name == "suspicious_token_classification_summary.tsv":
        return "suspicious_token_classification_summary"
    if name == "live_remaining_suspicious_tokens.tsv":
        return "live_remaining_suspicious_tokens"
    if name.endswith("_alternate_witness_adoptions.tsv"):
        return "alternate_witness_adoptions"
    if name.endswith("_alternate_witness_unresolved.tsv"):
        return "alternate_witness_unresolved"
    if name.endswith("_review_queue.tsv"):
        return "review_queue"
    if WATCHDOG_FILE_RE.search(name):
        return "watchdog"
    return "other_diagnostic"


def source_token_for_row(row: dict[str, str], queue_source: str) -> str:
    if queue_source == "tibetan_variant_families":
        return "; ".join(split_display_tokens(row.get("source_tokens", "")))
    if queue_source == "tibetan_google_adoption_patterns":
        return first_field(row, "base_token", "source_token", "token")
    return first_field(
        row,
        "source_token",
        "from_token",
        "base_token",
        "token",
        "source_tokens",
    )


def target_token_for_row(row: dict[str, str], queue_source: str) -> str:
    if queue_source == "tibetan_variant_families":
        return "; ".join(split_display_tokens(row.get("proposed_targets", "")))
    if queue_source == "tibetan_google_adoption_patterns":
        return first_field(row, "alternate_token", "proposed_target", "to_token")
    return first_field(
        row,
        "proposed_target",
        "final_to_token",
        "to_token",
        "proposed_canon",
        "alternate_token",
        "proposed_targets",
        "suggestion",
    )


def family_for_row(path: Path, row: dict[str, str], queue_source: str) -> str:
    family = first_field(row, "candidate_family", "family_key", "reason_family", "reason", "issue")
    text = " ".join(
        [
            family,
            source_token_for_row(row, queue_source),
            target_token_for_row(row, queue_source),
            path.name,
        ]
    )
    if SIGLUM_FAMILY_RE.search(text):
        return "citation_or_siglum"
    if not family:
        if "sanskrit" in queue_source:
            return "sanskrit_residual"
        if "tibetan" in queue_source:
            return "tibetan_residual"
        if "alternate_witness" in queue_source:
            return "alternate_witness_token"
        if queue_source == "review_queue":
            return "review_queue"
        if queue_source == "watchdog":
            return "watchdog"
        return "unknown"
    return family


def bucket_for_row(path: Path, queue_source: str, family: str) -> str:
    text = " ".join([path.name, queue_source, family])
    if queue_source == "suspicious_token_classification_summary":
        return "qa_summary"
    if STALE_FILE_RE.search(text):
        return "already_corrected_or_stale"
    if queue_source == "live_validator_only_residue":
        return "validator_only_noise"
    if POLICY_FILE_RE.search(text):
        return "policy_or_false_positive"
    if VALIDATOR_FILE_RE.search(text):
        return "validator_only_noise"
    if SIGLUM_FAMILY_RE.search(text):
        return "siglum_policy"
    if WATCHDOG_FILE_RE.search(text) or queue_source == "watchdog":
        return "watchdog_review"
    if queue_source == "live_google_supported_candidates":
        return "google_witness"
    if queue_source in {"live_review_queue_candidates", "manual_review_only_suspicious_tokens"}:
        return "review_queue"
    if queue_source == "review_queue" or REVIEW_QUEUE_FILE_RE.search(text):
        if SANSKRIT_FILE_RE.search(text):
            return "sanskrit_review_queue"
        return "review_queue"
    if SANSKRIT_FILE_RE.search(text):
        return "sanskrit_title_term"
    if TIBETAN_FILE_RE.search(text):
        return "tibetan_orthography"
    if GOOGLE_FILE_RE.search(text):
        return "google_witness"
    return "mixed_residual"


def evidence_for_row(row: dict[str, str], queue_source: str, bucket: str) -> str:
    explicit = first_field(row, "evidence", "evidence_summary", "support")
    if explicit:
        return explicit
    if queue_source.endswith("adoptions"):
        return "alternate_witness_adoption"
    if queue_source.endswith("unresolved"):
        return "alternate_witness_unresolved"
    if "google" in queue_source:
        return "google_candidate"
    if queue_source == "review_queue" or "review" in queue_source:
        return "review_queue"
    if queue_source == "watchdog":
        return "watchdog"
    if bucket == "siglum_policy":
        return "siglum_registry_or_context"
    return "diagnostic"


def action_for_row(
    row: dict[str, str],
    *,
    queue_source: str,
    bucket: str,
    source_token: str,
    target_token: str,
) -> str:
    explicit = first_field(row, "suggested_action", "decision", "source_review_decision")
    explicit_lower = explicit.lower()
    if bucket == "qa_summary":
        return "ignore_summary_row"
    if bucket == "already_corrected_or_stale":
        return "ignore_already_corrected_or_stale"
    if bucket == "policy_or_false_positive":
        return "ignore_policy_or_false_positive"
    if "validator" in bucket:
        return "ignore_validator_only"
    if bucket == "watchdog_review":
        return "source_image_review"
    if bucket == "siglum_policy":
        if "already_canonical" in explicit_lower:
            return "ignore_already_canonical"
        return "siglum_policy_review"
    if "source_review" in explicit_lower or "defer" in explicit_lower:
        return "source_image_review"
    if "reject" in explicit_lower:
        return "ignore_rejected"
    if "review" in explicit_lower and "promot" not in explicit_lower:
        return "sample_further"
    if "promot" in explicit_lower and target_token:
        return "promote_exact_reviewed_rows"
    if queue_source.endswith("adoptions"):
        return "audit_existing_google_adoption"
    if queue_source.endswith("unresolved") or "google" in queue_source:
        return "sample_further"
    if queue_source == "review_queue" and target_token:
        return "review_exact_suggestion"
    if target_token and source_token and source_token != target_token:
        return "sample_further"
    return "ignore_or_monitor"


def risk_for_row(bucket: str, action: str, count: int, source_token: str, target_token: str) -> str:
    if action in {
        "ignore_validator_only",
        "ignore_policy_or_false_positive",
        "ignore_already_corrected_or_stale",
        "ignore_summary_row",
        "ignore_rejected",
        "ignore_already_canonical",
    }:
        return "not_candidate"
    if action == "promote_exact_reviewed_rows" and source_token and target_token:
        return "low"
    if action in {"siglum_policy_review", "source_image_review", "review_exact_suggestion"}:
        return "medium"
    if action == "audit_existing_google_adoption" and count >= 25:
        return "medium"
    if bucket == "google_witness":
        return "medium"
    return "high" if not target_token else "medium"


def context_for_row(row: dict[str, str]) -> str:
    return compact(
        first_field(
            row,
            "context_excerpt",
            "sample_contexts",
            "base_line",
            "line_excerpt",
            "alternate_line",
        )
    )


def example_ref_for_row(volume: str, row: dict[str, str]) -> str:
    page = first_field(row, "page")
    line = first_field(row, "line")
    token_index = first_field(row, "token_index")
    if page and line and token_index:
        return f"{volume}:p{page}:l{line}:t{token_index}"
    if page and line:
        return f"{volume}:p{page}:l{line}"
    samples = first_field(row, "sample_refs", "example_ref")
    return compact(samples, limit=120)


@dataclass
class LedgerGroup:
    bucket: str
    family: str
    source_token: str
    target_token: str
    action: str
    risk: str
    queue_sources: Counter[str] = field(default_factory=Counter)
    evidence: Counter[str] = field(default_factory=Counter)
    confidence: Counter[str] = field(default_factory=Counter)
    volumes: Counter[str] = field(default_factory=Counter)
    examples: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    source_files: Counter[str] = field(default_factory=Counter)

    @property
    def combined_count(self) -> int:
        return sum(self.volumes.values())

    @property
    def volume_count(self) -> int:
        return sum(1 for volume in VOLUME_ORDER if self.volumes.get(volume, 0))

    def add(
        self,
        *,
        volume: str,
        count: int,
        queue_source: str,
        evidence: str,
        confidence: str,
        example: str,
        context: str,
        source_file: str,
    ) -> None:
        self.volumes[volume] += count
        self.queue_sources[queue_source] += count
        self.evidence[evidence] += count
        if confidence:
            self.confidence[confidence] += count
        if example and example not in self.examples and len(self.examples) < 6:
            self.examples.append(example)
        if context and context not in self.contexts and len(self.contexts) < 3:
            self.contexts.append(context)
        self.source_files[source_file] += count

    def row(self) -> dict[str, str]:
        return {
            "bucket": self.bucket,
            "family": self.family,
            "source_token": self.source_token,
            "target_token": self.target_token,
            "recommended_action": self.action,
            "risk": self.risk,
            "combined_count": str(self.combined_count),
            "volume_count": str(self.volume_count),
            "wts_1_34_count": str(self.volumes.get("wts_1_34", 0)),
            "wts_35_51_count": str(self.volumes.get("wts_35_51", 0)),
            "wts_8_b_count": str(self.volumes.get("wts_8_b", 0)),
            "wts_9_m_count": str(self.volumes.get("wts_9_m", 0)),
            "unknown_volume_count": str(self.volumes.get("unknown", 0)),
            "queue_sources": display_counter(self.queue_sources),
            "evidence": display_counter(self.evidence),
            "confidence": display_counter(self.confidence),
            "sample_refs": "; ".join(self.examples),
            "sample_contexts": " || ".join(self.contexts),
            "source_files": display_counter(self.source_files, limit=4),
        }


LEDGER_FIELDS = [
    "bucket",
    "family",
    "source_token",
    "target_token",
    "recommended_action",
    "risk",
    "combined_count",
    "volume_count",
    "wts_1_34_count",
    "wts_35_51_count",
    "wts_8_b_count",
    "wts_9_m_count",
    "unknown_volume_count",
    "queue_sources",
    "evidence",
    "confidence",
    "sample_refs",
    "sample_contexts",
    "source_files",
]


def display_counter(counter: Counter[str], limit: int = 6) -> str:
    return "; ".join(f"{key}={value}" for key, value in counter.most_common(limit) if key)


def normalize_key_piece(value: str) -> str:
    value = clean_counted_token(value)
    value = WHITESPACE_RE.sub(" ", value).strip().lower()
    return value or "none"


def group_key(
    bucket: str,
    family: str,
    source_token: str,
    target_token: str,
    action: str,
) -> tuple[str, str, str, str, str]:
    return (
        normalize_key_piece(bucket),
        normalize_key_piece(family),
        normalize_key_piece(source_token),
        normalize_key_piece(target_token),
        normalize_key_piece(action),
    )


def normalize_rows(paths: Iterable[Path]) -> list[LedgerGroup]:
    groups: dict[tuple[str, str, str, str, str], LedgerGroup] = {}
    for path in paths:
        queue_source = queue_source_for_path(path)
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                continue
            for row in reader:
                volume = infer_volume(path, row)
                source_token = source_token_for_row(row, queue_source)
                target_token = target_token_for_row(row, queue_source)
                family = family_for_row(path, row, queue_source)
                bucket = bucket_for_row(path, queue_source, family)
                count = int_field(row, "occurrence_count", "count", "combined_count", default=1)
                evidence = evidence_for_row(row, queue_source, bucket)
                action = action_for_row(
                    row,
                    queue_source=queue_source,
                    bucket=bucket,
                    source_token=source_token,
                    target_token=target_token,
                )
                risk = risk_for_row(bucket, action, count, source_token, target_token)
                key = group_key(bucket, family, source_token, target_token, action)
                if key not in groups:
                    groups[key] = LedgerGroup(
                        bucket=bucket,
                        family=family,
                        source_token=source_token,
                        target_token=target_token,
                        action=action,
                        risk=risk,
                    )
                groups[key].add(
                    volume=volume,
                    count=count,
                    queue_source=queue_source,
                    evidence=evidence,
                    confidence=first_field(row, "confidence", "confidence_summary"),
                    example=example_ref_for_row(volume, row),
                    context=context_for_row(row),
                    source_file=str(path),
                )
    return sorted(groups.values(), key=ranking_key)


ACTION_PRIORITY = {
    "promote_exact_reviewed_rows": 0,
    "review_exact_suggestion": 1,
    "source_image_review": 2,
    "siglum_policy_review": 3,
    "sample_further": 4,
    "audit_existing_google_adoption": 5,
    "ignore_or_monitor": 8,
    "ignore_validator_only": 9,
    "ignore_policy_or_false_positive": 9,
    "ignore_already_corrected_or_stale": 9,
    "ignore_summary_row": 9,
    "ignore_rejected": 9,
    "ignore_already_canonical": 9,
}

RISK_PRIORITY = {"low": 0, "medium": 1, "high": 2, "not_candidate": 9}


def ranking_key(group: LedgerGroup) -> tuple[int, int, int, str, str, str]:
    return (
        ACTION_PRIORITY.get(group.action, 7),
        RISK_PRIORITY.get(group.risk, 5),
        -group.combined_count,
        group.bucket,
        group.family,
        group.source_token,
    )


def write_tsv(path: Path, rows: Iterable[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def filtered_rows(groups: Iterable[LedgerGroup], actions: set[str]) -> list[dict[str, str]]:
    return [group.row() for group in groups if group.action in actions]


def write_summary(
    path: Path,
    *,
    groups: list[LedgerGroup],
    input_roots: list[Path],
    generated_date: str,
) -> None:
    bucket_counts = Counter()
    action_counts = Counter()
    risk_counts = Counter()
    volume_counts = Counter()
    for group in groups:
        bucket_counts[group.bucket] += group.combined_count
        action_counts[group.action] += group.combined_count
        risk_counts[group.risk] += group.combined_count
        for volume, count in group.volumes.items():
            volume_counts[volume] += count

    def table(counter: Counter[str], headers: tuple[str, str]) -> list[str]:
        lines = [f"| {headers[0]} | {headers[1]} |", "| --- | ---: |"]
        for key, count in counter.most_common():
            lines.append(f"| `{key}` | {count} |")
        if len(lines) == 2:
            lines.append("| none | 0 |")
        return lines

    def top_table(title: str, selected: list[LedgerGroup]) -> list[str]:
        lines = [f"## {title}", "", "| Bucket | Family | Source | Target | Count | Action | Risk | Evidence | Sample refs |", "| --- | --- | --- | --- | ---: | --- | --- | --- | --- |"]
        for group in selected[:20]:
            row = group.row()
            lines.append(
                "| {bucket} | {family} | `{source}` | `{target}` | {count} | {action} | {risk} | {evidence} | {refs} |".format(
                    bucket=row["bucket"],
                    family=row["family"],
                    source=row["source_token"],
                    target=row["target_token"],
                    count=row["combined_count"],
                    action=row["recommended_action"],
                    risk=row["risk"],
                    evidence=row["evidence"],
                    refs=row["sample_refs"],
                )
            )
        if len(lines) == 3:
            lines.append("| none | none | | | 0 | | | | |")
        return lines

    promotion = [group for group in groups if group.action in {"promote_exact_reviewed_rows", "review_exact_suggestion"}]
    source_review = [group for group in groups if group.action == "source_image_review"]
    policy = [group for group in groups if group.action == "siglum_policy_review"]
    google = [
        group
        for group in groups
        if group.action in {"sample_further", "audit_existing_google_adoption"}
        and ("google" in group.bucket or "google" in display_counter(group.queue_sources))
    ]

    lines = [
        f"# Four-volume residual OCR cleanup ledger ({generated_date})",
        "",
        "This is an error-budget report, not a list of confirmed OCR errors. It groups existing diagnostics so the next cleanup batch can be selected from named, auditable families.",
        "",
        "Google Vision remains an alternate witness only. Validator-only rows and broad character patterns are not correction evidence.",
        "",
        "## Inputs",
        "",
    ]
    for root in input_roots:
        lines.append(f"- `{root}`")
    lines.extend(["", "## Totals by bucket", ""])
    lines.extend(table(bucket_counts, ("Bucket", "Rows/count")))
    lines.extend(["", "## Totals by recommended action", ""])
    lines.extend(table(action_counts, ("Action", "Rows/count")))
    lines.extend(["", "## Totals by risk", ""])
    lines.extend(table(risk_counts, ("Risk", "Rows/count")))
    lines.extend(["", "## Totals by volume", ""])
    lines.extend(table(volume_counts, ("Volume", "Rows/count")))
    lines.extend([""])
    lines.extend(top_table("Top exact-promotion/review candidates", promotion))
    lines.extend([""])
    lines.extend(top_table("Top source-image review needs", source_review))
    lines.extend([""])
    lines.extend(top_table("Top siglum policy decisions", policy))
    lines.extend([""])
    lines.extend(top_table("Top Google-witness sampling targets", google))
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_outputs(input_roots: list[Path], output_dir: Path, generated_date: str | None = None) -> list[LedgerGroup]:
    generated_date = generated_date or date.today().isoformat()
    paths = collect_tsv_paths(input_roots)
    groups = normalize_rows(paths)
    rows = [group.row() for group in groups]
    write_tsv(output_dir / "four_volume_residual_error_ledger.tsv", rows, LEDGER_FIELDS)
    write_tsv(
        output_dir / "four_volume_promotion_candidates.tsv",
        filtered_rows(groups, {"promote_exact_reviewed_rows", "review_exact_suggestion"}),
        LEDGER_FIELDS,
    )
    write_tsv(
        output_dir / "four_volume_source_review_needed.tsv",
        filtered_rows(groups, {"source_image_review"}),
        LEDGER_FIELDS,
    )
    write_tsv(
        output_dir / "four_volume_policy_decisions_needed.tsv",
        filtered_rows(groups, {"siglum_policy_review"}),
        LEDGER_FIELDS,
    )
    write_tsv(
        output_dir / "four_volume_google_sampling_targets.tsv",
        [
            group.row()
            for group in groups
            if group.action in {"sample_further", "audit_existing_google_adoption"}
            and ("google" in group.bucket or "google" in display_counter(group.queue_sources))
        ],
        LEDGER_FIELDS,
    )
    write_summary(
        output_dir / "four_volume_error_budget_summary.md",
        groups=groups,
        input_roots=input_roots,
        generated_date=generated_date,
    )
    return groups


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-root",
        action="append",
        required=True,
        type=Path,
        help="Work output root or TSV file to include. May be supplied more than once.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory where the ledger TSVs and Markdown summary will be written.",
    )
    parser.add_argument(
        "--report-date",
        default=None,
        help="Date string to use in the Markdown title. Defaults to today's local date.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    groups = build_outputs(args.input_root, args.output_dir, args.report_date)
    print(f"Wrote {len(groups)} grouped residual entries to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
