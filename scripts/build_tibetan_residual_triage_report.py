#!/usr/bin/env python3
"""Build a ranked residual Tibetan cleanup triage report.

The per-volume Tibetan cleanup diagnostics intentionally overlap: for example,
the same token family can appear in the raw orthography scan and in the grouped
variant-family file. This report groups by family/source-token/target and uses
the strongest per-volume support count from overlapping queues instead of
blindly summing diagnostic inventories.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


DIAGNOSTIC_FILES = (
    "tibetan_variant_families.tsv",
    "tibetan_orthography_damage_candidates.tsv",
    "tibetan_google_candidate_readings.tsv",
    "tibetan_google_adoption_patterns.tsv",
    "sigla_variant_candidates.tsv",
)

VOLUME_ORDER = ("wts_8_b", "wts_9_m")

GOOGLE_PATTERN_FAMILIES = {
    ("dan", "daṅ"),
    ("Ita", "lta"),
    ("Iha", "lha"),
    ("Ina", "lṅa"),
    ("Idan", "ldan"),
}

EXPLICIT_SOURCE_REVIEW_TOKENS = {
    "la'añń",
}

SIGLUM_POLICY_TOKENS = {
    "Gś-H",
    "GS-H",
    "Gs-H",
    "Yś",
    "Y$",
    "Lsdz-K",
    "Lsdz",
    "L$dz-K",
    "L$dz",
    "Lśdz",
    "Bu-$z",
    "Li$",
    "Liś",
    "Lis",
    "lis",
    "LiS",
    "LIS",
    "gZ1",
    "Vi$T",
    "ViST",
    "VisT",
    "VisṬ",
    "ViśT",
    "ViśsT",
    "visT",
    "Tär",
}


def clean_counted_token(value: str) -> str:
    """Strip the display count suffix used by grouped diagnostics."""
    value = value.strip()
    return re.sub(r"\s+\(\d+\)$", "", value)


def split_display_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for part in re.split(r";\s*", value or ""):
        token = clean_counted_token(part)
        if token:
            tokens.append(token)
    return tokens


def infer_volume(path: Path, row: dict[str, str]) -> str:
    volume = (row.get("volume") or "").strip()
    if volume:
        return volume
    text = str(path)
    if "wts_8_b" in text:
        return "wts_8_b"
    if "wts_9_m" in text:
        return "wts_9_m"
    return "unknown"


def int_field(row: dict[str, str], name: str, default: int = 1) -> int:
    value = (row.get(name) or "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def compact_context(value: str, limit: int = 130) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


@dataclass
class ResidualGroup:
    key: str
    family: str
    source_tokens: Counter[str] = field(default_factory=Counter)
    proposed_targets: Counter[str] = field(default_factory=Counter)
    queue_sources: Counter[str] = field(default_factory=Counter)
    counts_by_volume_source: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    examples: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    evidence: Counter[str] = field(default_factory=Counter)
    confidence: Counter[str] = field(default_factory=Counter)
    suggested_actions: Counter[str] = field(default_factory=Counter)
    google_status: Counter[str] = field(default_factory=Counter)

    def add(
        self,
        *,
        volume: str,
        queue_source: str,
        count: int,
        source_token: str = "",
        proposed_target: str = "",
        example: str = "",
        context: str = "",
        evidence: str = "",
        confidence: str = "",
        suggested_action: str = "",
        google_status: str = "",
    ) -> None:
        if source_token:
            self.source_tokens[source_token] += count
        if proposed_target:
            self.proposed_targets[proposed_target] += count
        self.queue_sources[queue_source] += count
        self.counts_by_volume_source[volume][queue_source] += count
        if example and example not in self.examples and len(self.examples) < 8:
            self.examples.append(example)
        if context:
            context = compact_context(context)
            if context and context not in self.contexts and len(self.contexts) < 5:
                self.contexts.append(context)
        if evidence:
            self.evidence[evidence] += count
        if confidence:
            self.confidence[confidence] += count
        if suggested_action:
            self.suggested_actions[suggested_action] += count
        if google_status:
            self.google_status[google_status] += count

    def volume_count(self, volume: str) -> int:
        """Use strongest source support per volume to avoid double counting."""
        counts = self.counts_by_volume_source.get(volume, Counter())
        return max(counts.values(), default=0)

    @property
    def combined_count(self) -> int:
        return sum(self.volume_count(volume) for volume in VOLUME_ORDER)

    def display_sources(self) -> str:
        return "; ".join(self.queue_sources.keys())

    def display_tokens(self) -> str:
        return "; ".join(token for token, _ in self.source_tokens.most_common(6))

    def display_targets(self) -> str:
        return "; ".join(token for token, _ in self.proposed_targets.most_common(4))

    def display_evidence(self) -> str:
        return "; ".join(item for item, _ in self.evidence.most_common(5))

    def display_confidence(self) -> str:
        return "; ".join(item for item, _ in self.confidence.most_common(3))

    def display_google_status(self) -> str:
        if not self.google_status:
            return "not_google"
        return "; ".join(item for item, _ in self.google_status.most_common(4))


def canonical_family(family: str) -> str:
    family = (family or "unknown").strip() or "unknown"
    if family.lower() in {
        "citation_siglum",
        "citation_or_siglum",
        "siglum",
        "sigla",
    }:
        return "citation_or_siglum"
    return family


def token_is_siglum_policy_case(token: str) -> bool:
    token = clean_counted_token(token)
    return token in SIGLUM_POLICY_TOKENS


def canonical_family_for_tokens(family: str, *tokens: str) -> str:
    family = canonical_family(family)
    if any(token_is_siglum_policy_case(token) for token in tokens if token):
        return "citation_or_siglum"
    return family


def family_key(family: str, source_token: str, target: str) -> str:
    family = canonical_family(family)
    folded_source = re.sub(r"\d+", "0", source_token or "unknown")
    folded_target = re.sub(r"\d+", "0", target or "")
    return "|".join(
        [
            family,
            folded_source,
            folded_target,
        ]
    ).lower()


def load_reviewed_exact_overrides(path: Path | None) -> set[tuple[str, str, str, str, str, str]]:
    if not path or not path.exists():
        return set()
    reviewed: set[tuple[str, str, str, str, str, str]] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            reviewed.add(
                (
                    (row.get("volume") or "").strip(),
                    (row.get("page") or "").strip(),
                    (row.get("line") or "").strip(),
                    (row.get("token_index") or "").strip(),
                    (row.get("from_token") or "").strip(),
                    (row.get("to_token") or "").strip(),
                )
            )
    return reviewed


def is_reviewed_exact_row(
    reviewed_overrides: set[tuple[str, str, str, str, str, str]],
    row: dict[str, str],
    *,
    volume: str,
    source_token: str,
    target: str,
) -> bool:
    key = (
        volume,
        (row.get("page") or "").strip(),
        (row.get("line") or "").strip(),
        (row.get("token_index") or "").strip(),
        source_token.strip(),
        target.strip(),
    )
    return key in reviewed_overrides


def update_from_variant_file(
    groups: dict[str, ResidualGroup],
    path: Path,
    queue_counts: Counter[str],
    reviewed_overrides: set[tuple[str, str, str, str, str, str]],
) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            queue_counts[path.name] += 1
            volume = infer_volume(path, row)
            family = canonical_family(
                row.get("candidate_family") or row.get("family_key") or "unknown"
            )
            sources = split_display_tokens(row.get("source_tokens", ""))
            targets = split_display_tokens(row.get("proposed_targets", ""))
            source_token = sources[0] if sources else ""
            target = targets[0] if targets else ""
            family = canonical_family_for_tokens(family, source_token, target)
            key = family_key(family, source_token, target)
            group = groups.setdefault(key, ResidualGroup(key=key, family=family))
            count = int_field(row, "occurrence_count", 1)
            sample_refs = split_display_tokens(row.get("sample_refs", ""))
            contexts = split_display_tokens(row.get("sample_contexts", ""))
            group.add(
                volume=volume,
                queue_source="variant_families",
                count=count,
                source_token=source_token,
                proposed_target=target,
                example=sample_refs[0] if sample_refs else "",
                context=contexts[0] if contexts else "",
                evidence=row.get("evidence_summary", ""),
                confidence=row.get("confidence_summary", ""),
                suggested_action=row.get("suggested_action", ""),
                google_status="alternate_candidate"
                if "google" in (row.get("evidence_summary") or "").lower()
                else "",
            )


def update_from_orthography_file(
    groups: dict[str, ResidualGroup],
    path: Path,
    queue_counts: Counter[str],
    reviewed_overrides: set[tuple[str, str, str, str, str, str]],
) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            queue_counts[path.name] += 1
            volume = infer_volume(path, row)
            family = canonical_family(row.get("candidate_family") or "unknown")
            token = row.get("token", "")
            target = row.get("proposed_target", "")
            family = canonical_family_for_tokens(family, token, target)
            key = family_key(family, token, target)
            group = groups.setdefault(key, ResidualGroup(key=key, family=family))
            ref = f"{volume}:{row.get('page','')}:{row.get('line','')}:{token}"
            group.add(
                volume=volume,
                queue_source="orthography_scan",
                count=1,
                source_token=token,
                proposed_target=target,
                example=ref,
                context=row.get("context_excerpt", ""),
                evidence=row.get("evidence", ""),
                confidence=row.get("confidence", ""),
                suggested_action=row.get("suggested_action", ""),
            )


def update_from_google_candidate_file(
    groups: dict[str, ResidualGroup],
    path: Path,
    queue_counts: Counter[str],
    reviewed_overrides: set[tuple[str, str, str, str, str, str]],
) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            queue_counts[path.name] += 1
            volume = infer_volume(path, row)
            family = canonical_family(row.get("candidate_family") or "google_candidate")
            token = row.get("base_token", "")
            target = row.get("proposed_target") or row.get("alternate_token", "")
            family = canonical_family_for_tokens(family, token, target)
            key = family_key(family, token, target)
            group = groups.setdefault(key, ResidualGroup(key=key, family=family))
            token_index = row.get("token_index", "")
            ref = f"{volume}:{row.get('page','')}:{row.get('line','')}:{token_index}:{token}"
            evidence = row.get("evidence", "")
            if is_reviewed_exact_row(
                reviewed_overrides,
                row,
                volume=volume,
                source_token=token,
                target=target,
            ):
                evidence = ";".join(part for part in [evidence, "already_reviewed_exact"] if part)
            group.add(
                volume=volume,
                queue_source="google_candidate_readings",
                count=1,
                source_token=token,
                proposed_target=target,
                example=ref,
                context=row.get("context_excerpt", ""),
                evidence=evidence,
                confidence=row.get("confidence", ""),
                suggested_action=row.get("suggested_action", ""),
                google_status="alternate_candidate",
            )


def update_from_adoption_file(
    groups: dict[str, ResidualGroup],
    path: Path,
    queue_counts: Counter[str],
    reviewed_overrides: set[tuple[str, str, str, str, str, str]],
) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            queue_counts[path.name] += 1
            volume = infer_volume(path, row)
            token = row.get("base_token", "")
            target = row.get("alternate_token", "")
            reason = row.get("reason") or "google_adoption"
            family = canonical_family(reason.replace("alternate_witness_", ""))
            family = canonical_family_for_tokens(family, token, target)
            key = family_key(family, token, target)
            group = groups.setdefault(key, ResidualGroup(key=key, family=family))
            count = int_field(row, "count", 1)
            sample_refs = split_display_tokens(row.get("sample_refs", ""))
            contexts = split_display_tokens(row.get("sample_contexts", ""))
            group.add(
                volume=volume,
                queue_source="google_adoption_patterns",
                count=count,
                source_token=token,
                proposed_target=target,
                example=sample_refs[0] if sample_refs else "",
                context=contexts[0] if contexts else "",
                evidence=reason,
                confidence="accepted_by_current_gates",
                suggested_action="already_google_gated",
                google_status="existing_adoption",
            )


def update_from_sigla_file(
    groups: dict[str, ResidualGroup],
    path: Path,
    queue_counts: Counter[str],
    reviewed_overrides: set[tuple[str, str, str, str, str, str]],
) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            queue_counts[path.name] += 1
            volume = infer_volume(path, row)
            token = row.get("source_token", "")
            target = row.get("proposed_canon", "")
            family = canonical_family("citation_or_siglum")
            key = family_key(family, token, target)
            group = groups.setdefault(key, ResidualGroup(key=key, family=family))
            source_queue = row.get("source_queue", "")
            google_status = ""
            if source_queue == "alternate_witness_adoptions":
                google_status = "existing_adoption"
            elif source_queue == "alternate_witness_unresolved":
                google_status = "alternate_candidate"
            ref = f"{volume}:{row.get('page','')}:{row.get('line','')}:{token}"
            group.add(
                volume=volume,
                queue_source="sigla_variant_candidates",
                count=1,
                source_token=token,
                proposed_target=target,
                example=ref,
                context=row.get("context_excerpt", ""),
                evidence=row.get("status", "sigla_registry"),
                confidence="policy",
                suggested_action=row.get("suggested_action", ""),
                google_status=google_status,
            )


def recommended_action(group: ResidualGroup) -> str:
    tokens = set(group.source_tokens)
    targets = set(group.proposed_targets)
    actions = set(group.suggested_actions)
    family = group.family
    lower_family = family.lower()
    evidence_text = " ".join(group.evidence)

    if lower_family == "citation_or_siglum" or "sigla_variant_candidates" in group.queue_sources:
        return "siglum policy review"
    if "already_reviewed_exact" in evidence_text and "dngos" in lower_family:
        return "already reviewed"
    if tokens & EXPLICIT_SOURCE_REVIEW_TOKENS or "stacked_nasal" in lower_family:
        return "source-image review"
    if any("$" in token for token in tokens) and lower_family == "dollar_ś":
        return "sample further"
    if not targets or targets == {""}:
        return "source-image review"
    if (next(iter(tokens), ""), next(iter(targets), "")) in GOOGLE_PATTERN_FAMILIES:
        return "sample further"
    if "google_adoption_patterns" in group.queue_sources:
        return "sample further"
    if "exact_promotion_candidate" in actions:
        return "promote exact rows"
    if "dngos" in lower_family:
        return "promote exact rows"
    if "source_review" in actions:
        return "source-image review"
    if "review" in actions or "orthography_scan" in group.queue_sources:
        return "sample further"
    return "ignore"


def ranking_key(group: ResidualGroup) -> tuple[int, int, str]:
    action = recommended_action(group)
    google = group.display_google_status()
    if action == "promote exact rows":
        bucket = 0
    elif action == "already reviewed":
        bucket = 5
    elif "existing_adoption" in google or "alternate_candidate" in google:
        bucket = 1
    elif action == "sample further":
        bucket = 2
    elif action == "siglum policy review":
        bucket = 3
    elif action == "source-image review":
        bucket = 4
    else:
        bucket = 6
    return (bucket, -group.combined_count, group.key)


def collect_groups(
    diagnostics_dirs: list[Path],
    reviewed_overrides: set[tuple[str, str, str, str, str, str]],
) -> tuple[list[ResidualGroup], Counter[str]]:
    groups: dict[str, ResidualGroup] = {}
    queue_counts: Counter[str] = Counter()
    updaters = {
        "tibetan_variant_families.tsv": update_from_variant_file,
        "tibetan_orthography_damage_candidates.tsv": update_from_orthography_file,
        "tibetan_google_candidate_readings.tsv": update_from_google_candidate_file,
        "tibetan_google_adoption_patterns.tsv": update_from_adoption_file,
        "sigla_variant_candidates.tsv": update_from_sigla_file,
    }
    for diag_dir in diagnostics_dirs:
        for file_name in DIAGNOSTIC_FILES:
            path = diag_dir / file_name
            if not path.exists():
                continue
            updaters[file_name](groups, path, queue_counts, reviewed_overrides)
    return sorted(groups.values(), key=ranking_key), queue_counts


def write_tsv(groups: list[ResidualGroup], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "family_or_pattern",
        "queue_source",
        "wts_8_b_count",
        "wts_9_m_count",
        "combined_count",
        "source_tokens",
        "proposed_targets",
        "representative_examples",
        "google_status",
        "evidence_summary",
        "confidence_summary",
        "recommended_action",
        "sample_contexts",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for group in groups:
            writer.writerow(group_to_row(group))


def group_to_row(group: ResidualGroup) -> dict[str, str]:
    return {
        "family_or_pattern": group.family,
        "queue_source": group.display_sources(),
        "wts_8_b_count": str(group.volume_count("wts_8_b")),
        "wts_9_m_count": str(group.volume_count("wts_9_m")),
        "combined_count": str(group.combined_count),
        "source_tokens": group.display_tokens(),
        "proposed_targets": group.display_targets(),
        "representative_examples": "; ".join(group.examples[:5]),
        "google_status": group.display_google_status(),
        "evidence_summary": group.display_evidence(),
        "confidence_summary": group.display_confidence(),
        "recommended_action": recommended_action(group),
        "sample_contexts": " | ".join(group.contexts[:3]),
    }


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        escaped = [cell.replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def manual_sampling_rows() -> list[list[str]]:
    """Summarize the manual review decisions for the top residual groups."""
    return [
        [
            "`dan -> daṅ`",
            "Sampled rows are Tibetan contexts and already appear as existing Google-gated adoptions.",
            "Keep Google-gated; do not promote a source-independent exact/global rule.",
        ],
        [
            "`Ita -> lta`",
            "Sampled rows are ordinary Tibetan `lta` contexts and already adopted through the existing gates.",
            "Keep Google-gated; do not add a broad initial-I rule.",
        ],
        [
            "`Iha -> lha`",
            "Sampled rows are mostly clear `lha` contexts, but at least one sampled line also contains nearby siglum noise.",
            "Keep Google-gated; promote no ungated family.",
        ],
        [
            "`Ina -> lṅa`",
            "Sampled rows are clear Tibetan numeral contexts and already adopted through existing gates.",
            "Keep Google-gated; no additional override needed.",
        ],
        [
            "`Idan -> ldan`",
            "Sampled rows are clear `ldan` contexts and already adopted through existing gates.",
            "Keep Google-gated; no additional override needed.",
        ],
        [
            "`zes -> źes`",
            "Existing adoptions are visible, but the row is transliteration-policy sensitive rather than a simple OCR family.",
            "Defer; do not promote as a cleanup rule.",
        ],
        [
            "`bzan/snan/gron -> bzaṅ/snaṅ/groṅ`",
            "These are existing Google-gated nasal upgrades in Tibetan contexts.",
            "Leave under existing adoption gates; do not duplicate as reviewed overrides.",
        ],
        [
            "`dnos -> dṅos`",
            "The remaining high-confidence candidate rows match exact rows already present in `data/reviewed_tibetan_exact_overrides.tsv`.",
            "Already reviewed; no new correction work.",
        ],
        [
            "Sigla families",
            "`Liś`, `Gś-H`, `L$dz-K`, `Bu-$z`, `gZ1`, and related forms require bibliographic policy decisions.",
            "Siglum policy review, not Tibetan lexical cleanup.",
        ],
        [
            "`$ -> ś`",
            "High-volume residue is too broad and mixes Tibetan, Sanskrit, and siglum contexts.",
            "Sample/source-review only; no generic replacement.",
        ],
        [
            "`la'añń` and nasal-damage-looking rows",
            "The local shape is suspicious, but the current diagnostics do not establish a safe exact family.",
            "Source-image review.",
        ],
    ]


def write_markdown(
    groups: list[ResidualGroup],
    queue_counts: Counter[str],
    diagnostics_dirs: list[Path],
    path: Path,
    tsv_path: Path | None,
    reviewed_overrides_path: Path | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    action_counts = Counter(recommended_action(group) for group in groups)
    source_rows = [
        [name, str(queue_counts[name])] for name in sorted(queue_counts)
    ]
    top_rows = []
    for group in groups[:60]:
        row = group_to_row(group)
        top_rows.append(
            [
                row["family_or_pattern"],
                row["queue_source"],
                row["wts_8_b_count"],
                row["wts_9_m_count"],
                row["combined_count"],
                row["source_tokens"],
                row["proposed_targets"],
                row["google_status"],
                row["recommended_action"],
                row["representative_examples"],
            ]
        )
    action_rows = [[action, str(count)] for action, count in action_counts.most_common()]

    lines = [
        "# Tibetan Cleanup Residual Triage",
        "",
        "Date: 2026-06-19",
        "",
        "This report combines the regenerated WtS 8-b and WtS 9-m Tibetan cleanup diagnostics after the audited medium cleanup batch. It is a triage aid only: it does not add OCR correction heuristics and does not treat Google Vision as an authority.",
        "",
        "Counts are normalized by residual family/pattern. When the same family appears in overlapping diagnostic queues, the per-volume count uses the strongest support count from those queues rather than summing inventories. This avoids treating grouped diagnostics and raw candidate rows as simple subtraction counts.",
        "",
        "## Inputs",
        "",
    ]
    lines.extend(f"- `{diag_dir}`" for diag_dir in diagnostics_dirs)
    if reviewed_overrides_path:
        lines.append(f"- reviewed exact overrides: `{reviewed_overrides_path}`")
    if tsv_path:
        lines.extend(["", f"Full TSV: `{tsv_path}`"])
    lines.extend(
        [
            "",
            "## Queue Inventory",
            "",
            markdown_table(["Queue", "Rows"], source_rows),
            "",
            "## Recommended Actions",
            "",
            markdown_table(["Recommended action", "Family groups"], action_rows),
            "",
            "## Ranked Residual Families",
            "",
            markdown_table(
                [
                    "Family/pattern",
                    "Queue source",
                    "WtS 8-b",
                    "WtS 9-m",
                    "Combined",
                    "Source token(s)",
                    "Proposed target(s)",
                    "Google status",
                    "Recommended action",
                    "Representative examples",
                ],
                top_rows,
            ),
            "",
            "## Manual Sampling and Second-Tranche Decision",
            "",
            "No second correction tranche was promoted from this report. The largest safe-looking Tibetan families are already accepted through the existing Google token gates, and converting them into source-independent exact rows would reduce auditability without changing corrected text. The remaining high-volume residue is either policy-sensitive, noisy across contexts, or already covered by reviewed exact overrides.",
            "",
            markdown_table(
                ["Family", "Sampling result", "Decision"],
                manual_sampling_rows(),
            ),
            "",
            "## Triage Notes",
            "",
            "- `dan -> daṅ`, `Ita -> lta`, `Iha -> lha`, `Ina -> lṅa`, and `Idan -> ldan` remain high-priority Google-gated families for sampling. They should not become source-independent global rules.",
            "- Rows already present in `data/reviewed_tibetan_exact_overrides.tsv` are marked as already reviewed rather than treated as a fresh promotion queue.",
            "- `$ -> ś` remains too broad as a Tibetan/Sanskrit cleanup rule. It belongs in targeted row review or siglum policy, not a generic character substitution.",
            "- Sigla such as `Gś-H`, `Yś/Y$`, `Lsdz-K/L$dz-K`, `Bu-$z`, `Li$`, and `gZ1` are reported separately as bibliographic-policy cases.",
            "- `la'añń` and similar nasal-looking rows require source-image review; no broad `ń -> ṅ` or `n -> ñ` repair is implied.",
            "- Residual Sanskrit low-confidence rows are intentionally outside this Tibetan tranche.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--diagnostics-dir",
        action="append",
        required=True,
        type=Path,
        help="Per-volume Tibetan cleanup diagnostics directory. Pass once per volume.",
    )
    parser.add_argument("--out-md", required=True, type=Path)
    parser.add_argument("--out-tsv", type=Path)
    parser.add_argument("--reviewed-overrides", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reviewed_overrides = load_reviewed_exact_overrides(args.reviewed_overrides)
    groups, queue_counts = collect_groups(args.diagnostics_dir, reviewed_overrides)
    if args.out_tsv:
        write_tsv(groups, args.out_tsv)
    write_markdown(
        groups,
        queue_counts,
        args.diagnostics_dir,
        args.out_md,
        args.out_tsv,
        args.reviewed_overrides,
    )


if __name__ == "__main__":
    main()
