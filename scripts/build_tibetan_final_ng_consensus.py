#!/usr/bin/env python3
"""Build corpus-consensus diagnostics for Tibetan final-ṅ OCR variants."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


LATIN_TOKEN_RE = re.compile(
    r"[A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷŃńŇň"
    r"ČčŽžŠšǸǹı'’.\-\u0300-\u036f]+"
)
POSTPROCESS_TOKEN_RE = re.compile(
    r"[0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňß$]+"
    r"(?:['’.$-][0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňß$]+)*"
)
TIBETAN_BLOCK_RE = re.compile(r"[\u0F00-\u0FFF][\u0F00-\u0FFF\s]*")
TIBETAN_SYLLABLE_RE = re.compile(r"[\u0F40-\u0FBC]+")
SOURCE_FINALS = "nñńňh"
SOURCE_COMPATIBLE_FINALS = frozenset(SOURCE_FINALS + "ṅ")
VISIBLE_DAMAGE_RE = re.compile(r"[{}?¡£$%]|\d{2,}|SQ")
SUBJOINED_CONSONANTS = {
    "ྲ": "r",
    "ྱ": "y",
    "ླ": "l",
    "ྭ": "w",
}
LITERAL_TIBETAN_FEATURES = {
    "ར": "r",
    "ེ": "e",
    "ི": "i",
    "ོ": "o",
    "ུ": "u",
}
LATIN_VOWEL_RE = re.compile(r"[aeiouāīūAEIOUĀĪŪ]")
EXACT_TIBETAN_STEM_PREFIXES = {
    # Conservative exclusion checks for observed alignments where the Latin
    # token has an extra or missing consonantal feature.  This is deliberately
    # not a general Tibetan transliterator.
    "ཁང": "kha",
    "སྤང": "spa",
}
GERMAN_STOP_WORDS = {
    "auch", "bez", "die", "der", "das", "ein", "eine", "einer", "für",
    "kurzf", "lex", "macht", "npr", "oder", "und", "vgl",
}
FEATURE_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1]
    / "data/tibetan_latin_feature_registry.tsv"
)
TRANSCRIPTION_EXCEPTIONS_PATH = (
    Path(__file__).resolve().parents[1]
    / "data/reviewed_tibetan_transcription_exceptions.tsv"
)
CANONICAL_SYLLABLES_PATH = (
    Path(__file__).resolve().parents[1]
    / "data/tibetan_latin_canonical_syllables.tsv"
)
_FEATURE_REGISTRY: list[dict[str, str]] | None = None


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


def transcription_integrity_for_target(
    tibetan_syllable: str, target: str,
) -> tuple[str, str]:
    """Apply only reviewed/high-confidence registry features to a target."""
    global _FEATURE_REGISTRY
    if _FEATURE_REGISTRY is None:
        _FEATURE_REGISTRY = (
            read_tsv(FEATURE_REGISTRY_PATH)
            if FEATURE_REGISTRY_PATH.exists() else []
        )
    violations: list[str] = []
    exceptions = (
        read_tsv(TRANSCRIPTION_EXCEPTIONS_PATH)
        if TRANSCRIPTION_EXCEPTIONS_PATH.exists() else []
    )
    for row in exceptions:
        if row["tibetan_syllable"] != tibetan_syllable:
            continue
        source = row["source_token"]
        same_stem = (
            target.endswith("ṅ") and source[-1:] in SOURCE_FINALS
            and target[:-1] == source[:-1]
        )
        if (target == source or same_stem) and row["status"] in {
            "known_multi_error_source", "source_variant_requires_manual_review",
            "foreign_or_alternate_transcription",
        }:
            return "reviewed_transcription_exception", row["status"]
    canonical = {
        item
        for row in (
            read_tsv(CANONICAL_SYLLABLES_PATH)
            if CANONICAL_SYLLABLES_PATH.exists() else []
        )
        if row.get("tibetan_syllable") == tibetan_syllable
        and row.get("canonical_status") == "canonical"
        for item in row.get("canonical_forms", "").split(";") if item
    }
    if canonical and target not in canonical:
        return "canonical_syllable_mismatch", ";".join(sorted(canonical))
    checked = False
    for rule in _FEATURE_REGISTRY:
        if (
            rule["review_status"] not in {"reviewed", "high_confidence"}
            or rule["confidence"] != "high"
            or rule["tibetan_feature"] not in tibetan_syllable
        ):
            continue
        if rule["feature_type"] == "suffix_coda":
            continue  # The source-compatible diagnostic checks this separately.
        checked = True
        if rule["expected_latin_feature"] not in target:
            violations.append(
                f"{rule['feature_type']}:{rule['tibetan_feature']}->"
                f"{rule['expected_latin_feature']}"
            )
    if violations:
        return "nonfinal_feature_mismatch", ";".join(violations)
    return (
        "transcription_integrity_pass" if checked
        else "insufficient_feature_coverage",
        "",
    )


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


def is_genuine_dotted_final_ng_anchor(token: str, syllable: str) -> bool:
    """Require the relevant coda itself to be dotted final-ṅ."""
    if syllable.endswith("ངས"):
        return token.endswith("ṅs")
    return token.endswith("ṅ")


def nasal_skeleton(token: str) -> str:
    if not token:
        return token
    lower = token.lower()
    if lower.endswith("ṅs"):
        return lower[:-2] + "ns"
    if lower[-1:] in set(SOURCE_FINALS + "ṅ"):
        return lower[:-1] + "n"
    return lower


def source_compatible_signature(token: str) -> str | None:
    """Preserve the complete token except for a permitted final-nasal glyph."""
    if not token or token[-1] not in SOURCE_COMPATIBLE_FINALS:
        return None
    return token[:-1] + "<FINAL_NASAL>"


def source_compatible_pair(source: str, target: str) -> bool:
    """Return true only when source and target differ at the final nasal."""
    source_signature = source_compatible_signature(source)
    target_signature = source_compatible_signature(target)
    return (
        source != target
        and source_signature is not None
        and source_signature == target_signature
        and source[-1] in SOURCE_FINALS
        and target.endswith("ṅ")
    )


def source_variant_for_target(source: str, target: str) -> bool:
    if source == target or "ṅ" not in target.lower():
        return False
    if nasal_skeleton(source) != nasal_skeleton(target):
        return False
    return source.lower().endswith(tuple(SOURCE_FINALS))


def syllable_identity_guard(syllable: str, target: str) -> tuple[str, str]:
    """Reject consensus targets that omit an explicit subjoined consonant."""
    missing = [
        latin
        for tibetan, latin in SUBJOINED_CONSONANTS.items()
        if tibetan in syllable and latin not in target.lower()
    ]
    if missing:
        return (
            "consonantal_structure_mismatch",
            "Proposed target omits explicit Tibetan subjoined "
            + ", ".join(missing)
            + "; requires a syllable-specific analysis.",
        )
    return "exact_same_tibetan_syllable", ""


def source_compatible_identity_guard(
    syllable: str,
    target: str,
) -> tuple[str, str]:
    status, note = syllable_identity_guard(syllable, target)
    if status != "exact_same_tibetan_syllable":
        return status, note
    missing = []
    if "ྙ" in syllable and "ny" not in target.lower():
        missing.append("ny")
    required_prefix = EXACT_TIBETAN_STEM_PREFIXES.get(syllable)
    if required_prefix and not target.lower().startswith(required_prefix):
        missing.append(f"stem_{required_prefix}")
    missing.extend(
        latin
        for tibetan, latin in LITERAL_TIBETAN_FEATURES.items()
        if tibetan in syllable and latin not in target.lower()
    )
    tibetan_vowel = next(
        (
            latin
            for tibetan, latin in {
                "ི": "i", "ུ": "u", "ེ": "e", "ོ": "o"
            }.items()
            if tibetan in syllable
        ),
        "a",
    )
    latin_vowels = LATIN_VOWEL_RE.findall(target)
    if latin_vowels and latin_vowels[-1].lower().replace("ā", "a").replace(
        "ī", "i"
    ).replace("ū", "u") != tibetan_vowel:
        missing.append(f"vowel_{tibetan_vowel}")
    if missing:
        return (
            "transcription_structure_requires_review",
            "The target is not supported as a final-ng-only counterpart because "
            "an explicit Tibetan consonant or vowel feature is not represented: "
            + ", ".join(missing)
            + ". This does not by itself prove a bad alignment.",
        )
    return status, note


def load_alignment_review_exceptions() -> dict[tuple[str, str], dict[str, str]]:
    path = (
        Path(__file__).resolve().parents[1]
        / "data/reviewed_tibetan_transcription_exceptions.tsv"
    )
    if not path.exists():
        return {}
    return {
        (row["tibetan_syllable"], row["source_token"]): row
        for row in read_tsv(path)
    }


def alignment_review_status(
    syllable: str,
    source: str,
    supported_target: str,
    *,
    damage_scope: str = "none",
    marker_attached: bool = False,
) -> str:
    """Describe review evidence modestly; this is not a transliteration model."""
    if marker_attached or damage_scope in {
        "tibetan_headword_overlap",
        "latin_headword_overlap",
        "damage_before_latin_alignment",
    }:
        return "marker_or_damage"
    exception = load_alignment_review_exceptions().get((syllable, source))
    if exception:
        return exception["status"]
    if len(source) > 12 or source.lower() in {
        "noch", "dach", "wildschwein", "mannsh",
    }:
        return "obvious_gloss_or_alignment_noise"
    if supported_target and source_compatible_pair(source, supported_target):
        return "exact_source_signature_supported"
    if supported_target:
        return "source_variant_requires_manual_review"
    return "unresolved"


def zero_anchor_source_state(
    syllable: str,
    source: str,
    supported_target: str,
    rows: list[dict[str, str]],
) -> str:
    if supported_target:
        return ""
    statuses = {row.get("alignment_review_status", "") for row in rows}
    if "marker_or_damage" in statuses:
        return "marker_or_damage"
    if "obvious_gloss_or_alignment_noise" in statuses:
        return "obvious_alignment_or_gloss_noise"
    if "known_multi_error_source" in statuses:
        return "additional_nonfinal_ocr_damage_possible"
    if "source_variant_requires_manual_review" in statuses:
        return "additional_nonfinal_ocr_damage_possible"
    if source and source[-1:] in SOURCE_FINALS:
        return "no_anchor_clean_source_shape"
    return "manual_unresolved"


def classify_damage_scope(
    line: str,
    tibetan_end: int,
    latin_phrase_start: int,
    latin_phrase_end: int,
) -> str:
    matches = list(VISIBLE_DAMAGE_RE.finditer(line))
    if not matches:
        return "none"
    if any(match.start() < tibetan_end for match in matches):
        return "tibetan_headword_overlap"
    if any(
        latin_phrase_start <= match.start() < latin_phrase_end
        for match in matches
    ):
        return "latin_headword_overlap"
    if any(match.start() < latin_phrase_start for match in matches):
        return "damage_before_latin_alignment"
    return "later_gloss_or_commentary"


def token_has_attached_marker(
    line: str,
    token_index: int,
) -> bool:
    matches = list(POSTPROCESS_TOKEN_RE.finditer(line))
    if token_index < 1 or token_index > len(matches):
        return False
    match = matches[token_index - 1]
    if match.group(0)[:1] in {"T", "I"}:
        return True
    return match.start() > 0 and line[match.start() - 1] in {"\\", "/"}


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
            latin_phrase_start = tail_start + latin[0][1]
            last_token, last_start = latin[len(syllables) - 1]
            latin_phrase_end = tail_start + last_start + len(last_token)
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
                    "tibetan_end": str(tail_start),
                    "latin_phrase_start": str(latin_phrase_start),
                    "latin_phrase_end": str(latin_phrase_end),
                }
                aligned.append(aligned_row)
                if is_genuine_dotted_final_ng_anchor(token, syllable):
                    accepted[syllable][token] += 1
    return aligned, accepted


def collect_anchor_provenance(
    release_root: Path,
    aligned: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Reconstruct how each current exact dotted anchor entered the release."""
    if aligned is None:
        aligned, _accepted = collect_aligned_rows(release_root)
    root = Path(__file__).resolve().parents[1]
    exact_path = root / "data/reviewed_tibetan_exact_overrides.tsv"
    exact_rows = read_tsv(exact_path) if exact_path.exists() else []
    verification_path = (
        root / "data/final_ng_direct_base_anchor_verification.tsv"
    )
    verification_rows = (
        read_tsv(verification_path) if verification_path.exists() else []
    )
    verification_by_key = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["tibetan_syllable"], row["dotted_token"],
        ): row
        for row in verification_rows
    }
    exact_by_key: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in exact_rows:
        exact_by_key[
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["to_token"],
            )
        ].append(row)

    google_by_key: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    changes_by_line_target: dict[tuple[str, ...], list[dict[str, str]]] = (
        defaultdict(list)
    )
    for volume_dir in sorted((release_root / "qa").glob("wts_*")):
        volume = volume_dir.name
        adoption_path = volume_dir / f"{volume}_alternate_witness_adoptions.tsv"
        if adoption_path.exists():
            for row in read_tsv(adoption_path):
                google_by_key[
                    (
                        volume, row.get("page", ""), row.get("line", ""),
                        row.get("token_index", ""), row.get("alternate_token", ""),
                    )
                ].append(row)
        changes_path = volume_dir / f"{volume}_changes.tsv"
        if changes_path.exists():
            for row in read_tsv(changes_path):
                changes_by_line_target[
                    (volume, row["page"], row["line"], row["to_token"])
                ].append(row)

    provenance: list[dict[str, str]] = []
    for row in aligned:
        token = row["latin_token"]
        syllable = row["tibetan_syllable"]
        if not is_genuine_dotted_final_ng_anchor(token, syllable):
            continue
        exact_key = (
            row["volume"], row["page"], row["line"], row["token_index"], token,
        )
        exact = exact_by_key.get(exact_key, [])
        google = google_by_key.get(exact_key, [])
        changes = changes_by_line_target.get(
            (row["volume"], row["page"], row["line"], token), []
        )
        verification = verification_by_key.get(
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                syllable, token,
            )
        )
        if exact:
            classification = "reviewed_exact_final_ng"
            reason = ";".join(sorted({item["reason"] for item in exact}))
            evidence = ";".join(sorted({item["evidence"] for item in exact}))
            source_tokens = ";".join(
                sorted({item["from_token"] for item in exact})
            )
        elif google:
            classification = "google_adopted"
            reason = ";".join(sorted({item.get("reason", "") for item in google}))
            evidence = "alternate_witness_adoption"
            source_tokens = ";".join(
                sorted({item.get("base_token", "") for item in google})
            )
        elif changes:
            current_occurrences = sum(
                match.group(0).strip(".-'’") == token
                for match in LATIN_TOKEN_RE.finditer(row["context_excerpt"])
            )
            if len(changes) == 1 and current_occurrences == 1:
                classification = "other_postprocess"
                reason = changes[0].get("reason", "")
                evidence = changes[0].get("tier", "")
                source_tokens = changes[0].get("from_token", "")
            else:
                classification = "unknown"
                reason = "ambiguous_change_or_token_position"
                evidence = ""
                source_tokens = ";".join(
                    sorted({item.get("from_token", "") for item in changes})
                )
        elif (
            verification
            and verification["verification_status"]
            == "directly_verified_base_ocr"
        ):
            classification = "base_ocr_dotted"
            reason = verification["rationale"]
            evidence = verification["evidence"]
            source_tokens = token
        else:
            classification = "base_provenance_unverified"
            reason = (
                verification["rationale"]
                if verification
                else "No direct authoritative base-OCR verification is recorded."
            )
            evidence = (
                verification["evidence"]
                if verification
                else "current_release_presence_only"
            )
            source_tokens = token
        provenance.append(
            {
                "volume": row["volume"],
                "page": row["page"],
                "line": row["line"],
                "token_index": row["token_index"],
                "tibetan_syllable": syllable,
                "current_dotted_token": token,
                "provenance_class": classification,
                "source_token_or_tokens": source_tokens,
                "correction_reason": reason,
                "correction_evidence": evidence,
                "context_excerpt": row["context_excerpt"].rstrip(),
            }
        )
    return sorted(
        provenance,
        key=lambda row: (
            row["volume"], int(row["page"]), int(row["line"]),
            int(row["token_index"]),
        ),
    )


def collect_google_witness_evidence(
    release_root: Path,
) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    specifications = (
        ("adopted", "{volume}_alternate_witness_adoptions.tsv"),
        ("unresolved", "{volume}_alternate_witness_unresolved.tsv"),
        (
            "candidate",
            "tibetan_cleanup_diagnostics/tibetan_google_candidate_readings.tsv",
        ),
    )
    for volume_dir in sorted((release_root / "qa").glob("wts_*")):
        volume = volume_dir.name
        for status, pattern in specifications:
            path = volume_dir / pattern.format(volume=volume)
            if not path.exists():
                continue
            for row in read_tsv(path):
                base = row.get("base_token", "")
                alternate = row.get("alternate_token", "")
                if not base or not alternate:
                    continue
                evidence.append(
                    {
                        "volume": volume,
                        "page": row.get("page", ""),
                        "line": row.get("line", ""),
                        "token_index": row.get("token_index", ""),
                        "base_token": base,
                        "alternate_token": alternate,
                        "witness_status": status,
                        "reason": row.get("reason", ""),
                    }
                )
    return evidence


def build_malformed_anchor_audit(
    release_root: Path,
    aligned: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    if aligned is None:
        aligned, _accepted = collect_aligned_rows(release_root)
    valid_counts = Counter(
        row["tibetan_syllable"]
        for row in aligned
        if is_genuine_dotted_final_ng_anchor(
            row["latin_token"], row["tibetan_syllable"]
        )
    )
    frozen_targets = set()
    for manifest in (
        Path(__file__).resolve().parents[1] / "data"
    ).glob("final_ng_*prepass_manifest_*.tsv"):
        for row in read_tsv(manifest):
            if row["candidate_status"] == "positional":
                frozen_targets.add((row["tibetan_syllable"], row["target"]))
    rows = []
    for row in aligned:
        token = row["latin_token"]
        if "ṅ" not in token or is_genuine_dotted_final_ng_anchor(
            token, row["tibetan_syllable"]
        ):
            continue
        rows.append(
            {
                "volume": row["volume"],
                "page": row["page"],
                "line": row["line"],
                "token_index": row["token_index"],
                "tibetan_syllable": row["tibetan_syllable"],
                "malformed_dotted_token": token,
                "valid_anchor_count_for_tibetan_syllable": str(
                    valid_counts[row["tibetan_syllable"]]
                ),
                "matches_historical_frozen_target": (
                    "yes"
                    if (row["tibetan_syllable"], token) in frozen_targets
                    else "no"
                ),
                "audit_decision": "exclude_internal_ng_not_final_coda",
                "context_excerpt": row["context_excerpt"].rstrip(),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["volume"], int(row["page"]), int(row["line"]),
            int(row["token_index"]),
        ),
    )


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
        identity_status, identity_note = syllable_identity_guard(
            row["tibetan_syllable"],
            target,
        )
        damage_scope = classify_damage_scope(
            row["context_excerpt"],
            int(row["tibetan_end"]),
            int(row["latin_phrase_start"]),
            int(row["latin_phrase_end"]),
        )
        aligned_damage = damage_scope in {
            "tibetan_headword_overlap",
            "latin_headword_overlap",
            "damage_before_latin_alignment",
        }
        marker = source[:1] in {"T", "I", "\\", "/"}
        if marker:
            category = "marker_attached"
            confidence = "manual"
            action = "separate_marker_and_final_ng_review"
            deferred = "Reference-marker reconstruction requires independent evidence."
        elif identity_status == "consonantal_structure_mismatch":
            category = "syllable_structure_mismatch"
            confidence = "manual"
            action = "syllable_specific_analysis"
            deferred = identity_note
        elif aligned_damage:
            category = "damaged_context"
            confidence = "manual"
            action = "manual_alignment_review"
            deferred = "OCR damage overlaps or precedes the aligned headword phrase."
        elif dominant:
            category = "dominant_internal_consensus"
            confidence = "high"
            action = "exact_review_candidate"
            deferred = ""
        elif target_count == 1 and not competing:
            category = "insufficient_consensus"
            confidence = "low"
            action = "defer"
            deferred = "Only one accepted aligned target attestation is available."
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
                "syllable_identity_guard": identity_status,
                "consensus_basis": (
                    "strong_accepted_form_consensus"
                    if dominant
                    else "single_accepted_attestation"
                    if target_count == 1 and not competing
                    else "non_dominant_accepted_forms"
                ),
                "damage_scope": damage_scope,
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


def build_family_rankings(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                row["tibetan_syllable"],
                nasal_skeleton(row["source_latin_token"]),
                row["proposed_latin_target"],
            )
        ].append(row)
    rankings: list[dict[str, str]] = []
    for (syllable, normalized_source, target), family_rows in grouped.items():
        categories = Counter(row["alignment_category"] for row in family_rows)
        source_variants = Counter(row["source_latin_token"] for row in family_rows)
        accepted_counts = sorted(
            {int(row["accepted_form_count"]) for row in family_rows},
            reverse=True,
        )
        rankings.append(
            {
                "tibetan_syllable": syllable,
                "normalized_source_variant": normalized_source,
                "source_variants_and_counts": "; ".join(
                    f"{variant}:{count}"
                    for variant, count in source_variants.most_common()
                ),
                "proposed_target": target,
                "candidate_count": str(len(family_rows)),
                "dominant_count": str(categories["dominant_internal_consensus"]),
                "damaged_count": str(categories["damaged_context"]),
                "insufficient_count": str(categories["insufficient_consensus"]),
                "competing_count": str(categories["competing_latin_forms"]),
                "structure_mismatch_count": str(
                    categories["syllable_structure_mismatch"]
                ),
                "marker_attached_count": str(categories["marker_attached"]),
                "accepted_form_evidence": "; ".join(map(str, accepted_counts)),
                "volumes": ";".join(
                    sorted({row["volume"] for row in family_rows})
                ),
            }
        )
    return sorted(
        rankings,
        key=lambda row: (
            -int(row["candidate_count"]),
            row["tibetan_syllable"],
            row["normalized_source_variant"],
            row["proposed_target"],
        ),
    )


def format_counts(forms: Counter[str]) -> str:
    return "; ".join(
        f"{form}:{count}" for form, count in forms.most_common()
    )


def build_source_compatible_rows(
    release_root: Path,
) -> list[dict[str, str]]:
    """Classify every aligned undotted token independently of legacy targets."""
    aligned, accepted = collect_aligned_rows(release_root)
    old_rows = build_consensus_rows(release_root)
    old_by_key = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["tibetan_syllable"], row["source_latin_token"],
        ): row
        for row in old_rows
    }
    compatible_rows: list[dict[str, str]] = []
    for aligned_row in aligned:
        source = aligned_row["latin_token"]
        if not source or source[-1] not in SOURCE_FINALS:
            continue
        key = (
            aligned_row["volume"], aligned_row["page"], aligned_row["line"],
            aligned_row["token_index"], aligned_row["tibetan_syllable"], source,
        )
        old = old_by_key.get(key, {})
        signature = source_compatible_signature(source)
        forms = accepted.get(aligned_row["tibetan_syllable"], Counter())
        if not forms:
            continue
        compatible = Counter(
            {
                form: count
                for form, count in forms.items()
                if source_compatible_signature(form) == signature
            }
        )
        incompatible = Counter(forms)
        for form in compatible:
            incompatible.pop(form, None)
        if compatible:
            target, target_count = compatible.most_common(1)[0]
        else:
            target = ""
            target_count = 0
        competing = Counter(compatible)
        competing.pop(target, None)
        if target:
            identity_status, identity_note = source_compatible_identity_guard(
                aligned_row["tibetan_syllable"], target
            )
        else:
            identity_status = "target_unresolved_no_anchor"
            identity_note = (
                "No compatible dotted target exists, so transcription structure "
                "cannot be evaluated by the final-ng-only diagnostic."
            )
        exact_variant = source_compatible_pair(source, target) if target else False
        old_category = old.get(
            "alignment_category", "not_emitted_by_legacy_global_target"
        )
        damage_scope = classify_damage_scope(
            aligned_row["context_excerpt"],
            int(aligned_row["tibetan_end"]),
            int(aligned_row["latin_phrase_start"]),
            int(aligned_row["latin_phrase_end"]),
        )
        aligned_damage = damage_scope in {
            "tibetan_headword_overlap",
            "latin_headword_overlap",
            "damage_before_latin_alignment",
        }
        attached_marker = token_has_attached_marker(
            aligned_row["context_excerpt"], int(aligned_row["token_index"])
        )
        integrity_status, integrity_violations = (
            transcription_integrity_for_target(
                aligned_row["tibetan_syllable"], target
            ) if target else ("target_unresolved_no_anchor", "")
        )
        if old_category == "marker_attached" or attached_marker:
            category = "source_compatible_marker_attached"
            confidence = "manual"
            action = "separate_marker_and_final_ng_review"
            deferred = "Reference-marker reconstruction requires independent evidence."
        elif identity_status in {
            "consonantal_structure_mismatch",
            "transcription_structure_requires_review",
        }:
            category = "source_compatible_not_final_ng_only"
            confidence = "manual"
            action = "syllable_specific_analysis"
            deferred = identity_note
        elif aligned_damage:
            category = "source_compatible_damaged_context"
            confidence = "manual"
            action = "manual_alignment_review"
            deferred = "OCR damage overlaps or precedes the aligned headword phrase."
        elif integrity_status == "nonfinal_feature_mismatch":
            category = "source_compatible_transcription_integrity_blocked"
            confidence = "manual"
            action = "repair_or_resolve_stem_before_final_ng"
            deferred = (
                "Historical/current dotted target violates a reviewed "
                f"transcription feature: {integrity_violations}."
            )
        elif target_count == 0:
            category = "source_compatible_no_anchor"
            confidence = "diagnostic"
            action = "alignment_and_target_discovery"
            deferred = (
                "No case-sensitive compatible dotted anchor is available; "
                "this diagnostic establishes no canonical target."
            )
        elif not exact_variant or target_count == 1:
            category = "source_compatible_single_anchor"
            confidence = "low"
            action = "defer"
            deferred = (
                "Only one case-sensitive compatible dotted anchor is available."
            )
        elif competing:
            category = "source_compatible_competing_evidence"
            confidence = "low"
            action = "defer"
            deferred = "More than one dotted target competes within the exact source signature."
        else:
            category = "source_compatible_dominant_consensus"
            confidence = "high"
            action = "exact_review_candidate"
            deferred = "none"
        compatible_rows.append(
            {
                "volume": aligned_row["volume"],
                "page": aligned_row["page"],
                "line": aligned_row["line"],
                "token_index": aligned_row["token_index"],
                "tibetan_syllable": aligned_row["tibetan_syllable"],
                "source_latin_token": source,
                "source_signature": signature or "",
                "proposed_latin_target": target,
                "compatible_accepted_target_count": str(target_count),
                "compatible_competing_form_counts": format_counts(competing),
                "incompatible_dotted_form_counts": format_counts(incompatible),
                "same_tibetan_dotted_evidence_total": str(sum(forms.values())),
                "old_alignment_category": old_category,
                "source_compatible_category": category,
                "damage_scope": damage_scope,
                "syllable_identity_guard": identity_status,
                "confidence": confidence,
                "suggested_action": action,
                "alignment_review_status": alignment_review_status(
                    aligned_row["tibetan_syllable"],
                    source,
                    target,
                    damage_scope=damage_scope,
                    marker_attached=attached_marker,
                ),
                "transcription_integrity_status": integrity_status,
                "transcription_integrity_violations": integrity_violations,
                "context_excerpt": aligned_row["context_excerpt"].rstrip(),
                "reason_for_deferral": deferred,
            }
        )
    return sorted(
        compatible_rows,
        key=lambda row: (
            row["proposed_latin_target"],
            row["volume"],
            int(row["page"]),
            int(row["line"]),
            int(row["token_index"]),
        ),
    )


def build_source_compatible_rankings(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                row["tibetan_syllable"],
                row["source_latin_token"],
                row["source_signature"],
                row["proposed_latin_target"],
            )
        ].append(row)
    rankings: list[dict[str, str]] = []
    for (syllable, source, signature, target), family_rows in grouped.items():
        categories = Counter(
            row["source_compatible_category"] for row in family_rows
        )
        rankings.append(
            {
                "tibetan_syllable": syllable,
                "source_variant": source,
                "source_signature": signature,
                "proposed_target": target,
                "candidate_count": str(len(family_rows)),
                "old_categories": format_counts(
                    Counter(row["old_alignment_category"] for row in family_rows)
                ),
                "new_categories": format_counts(categories),
                "compatible_accepted_target_count": max(
                    (
                        row["compatible_accepted_target_count"]
                        for row in family_rows
                    ),
                    key=int,
                ),
                "compatible_competing_forms": next(
                    (
                        row["compatible_competing_form_counts"]
                        for row in family_rows
                        if row["compatible_competing_form_counts"]
                    ),
                    "",
                ),
                "incompatible_dotted_forms_excluded": next(
                    (
                        row["incompatible_dotted_form_counts"]
                        for row in family_rows
                        if row["incompatible_dotted_form_counts"]
                    ),
                    "",
                ),
                "damage_count": str(
                    categories["source_compatible_damaged_context"]
                ),
                "volumes": ";".join(
                    sorted({row["volume"] for row in family_rows})
                ),
                "transcription_integrity_status": ";".join(sorted({
                    row.get("transcription_integrity_status", "")
                    for row in family_rows
                    if row.get("transcription_integrity_status")
                })),
                "transcription_integrity_blocked_count": str(
                    categories[
                        "source_compatible_transcription_integrity_blocked"
                    ]
                ),
            }
        )
    return sorted(
        rankings,
        key=lambda row: (
            -int(row["compatible_accepted_target_count"]),
            -int(row["candidate_count"]),
            row["tibetan_syllable"],
            row["source_variant"],
        ),
    )


def build_source_compatible_reclassifications(
    rankings: list[dict[str, str]],
) -> list[dict[str, str]]:
    equivalent = {
        "dominant_internal_consensus": "source_compatible_dominant_consensus",
        "insufficient_consensus": "source_compatible_insufficient_evidence",
        "competing_latin_forms": "source_compatible_competing_evidence",
        "damaged_context": "source_compatible_damaged_context",
        "syllable_structure_mismatch": "source_compatible_not_final_ng_only",
        "marker_attached": "source_compatible_marker_attached",
    }
    def changed(row: dict[str, str]) -> bool:
        old = Counter(
            dict(
                item.rsplit(":", 1)
                for item in row["old_categories"].split("; ")
                if item
            )
        )
        new = Counter(
            dict(
                item.rsplit(":", 1)
                for item in row["new_categories"].split("; ")
                if item
            )
        )
        mapped = Counter({equivalent.get(key, key): value for key, value in old.items()})
        return mapped != new
    return [
        row
        for row in rankings
        if changed(row)
    ]


def build_source_compatible_coverage_audit(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    categories = Counter(row["source_compatible_category"] for row in rows)
    anchor_counts = Counter()
    for row in rows:
        count = int(row["compatible_accepted_target_count"])
        anchor_counts["no_compatible_anchor" if count == 0 else
                      "one_compatible_anchor" if count == 1 else
                      "two_or_more_compatible_anchors"] += 1
    metrics = {
        "aligned_undotted_candidates_considered": len(rows),
        **anchor_counts,
        "identity_guard_excluded": categories[
            "source_compatible_not_final_ng_only"
        ],
        "damaged": categories["source_compatible_damaged_context"],
        "marker_attached": categories["source_compatible_marker_attached"],
        "dominant": categories["source_compatible_dominant_consensus"],
        "single_anchor": categories["source_compatible_single_anchor"],
        "no_anchor": categories["source_compatible_no_anchor"],
        "competing": categories["source_compatible_competing_evidence"],
        "accounted_category_total": sum(categories.values()),
    }
    if metrics["accounted_category_total"] != len(rows):
        raise ValueError("Source-compatible coverage categories do not reconcile")
    return [
        {"metric": metric, "count": str(count)}
        for metric, count in metrics.items()
    ]


def source_candidate_key(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row["volume"], row["page"], row["line"], row["token_index"],
        row["tibetan_syllable"], row["source_latin_token"],
    )


def build_source_compatible_coverage_comparison(
    baseline: list[dict[str, str]],
    current: list[dict[str, str]],
) -> list[dict[str, str]]:
    before = {source_candidate_key(row): row for row in baseline}
    after = {source_candidate_key(row): row for row in current}
    comparison: list[dict[str, str]] = []
    for key in sorted(set(before) | set(after)):
        old = before.get(key)
        new = after.get(key)
        if old is None:
            change = "newly_discovered"
        elif new is None:
            change = "disappeared"
        elif old["proposed_latin_target"] != new["proposed_latin_target"]:
            change = "target_changed"
        elif old["source_compatible_category"] != new["source_compatible_category"]:
            change = "category_changed"
        else:
            continue
        exemplar = new or old
        assert exemplar is not None
        comparison.append(
            {
                "change_type": change,
                "volume": exemplar["volume"],
                "page": exemplar["page"],
                "line": exemplar["line"],
                "token_index": exemplar["token_index"],
                "tibetan_syllable": exemplar["tibetan_syllable"],
                "source_latin_token": exemplar["source_latin_token"],
                "old_target": old["proposed_latin_target"] if old else "",
                "new_target": new["proposed_latin_target"] if new else "",
                "old_category": old["source_compatible_category"] if old else "",
                "new_category": new["source_compatible_category"] if new else "",
                "compatible_anchor_count": (
                    new["compatible_accepted_target_count"] if new else ""
                ),
                "context_excerpt": exemplar["context_excerpt"],
            }
        )
    return comparison


def build_anchor_count_change_audit(
    baseline: list[dict[str, str]],
    current: list[dict[str, str]],
) -> list[dict[str, str]]:
    before = {source_candidate_key(row): row for row in baseline}
    after = {source_candidate_key(row): row for row in current}
    rows = []
    for key in sorted(set(before) & set(after)):
        old = before[key]
        new = after[key]
        old_count = int(old["compatible_accepted_target_count"])
        new_count = int(new["compatible_accepted_target_count"])
        if old_count == new_count:
            continue
        rows.append(
            {
                "volume": new["volume"],
                "page": new["page"],
                "line": new["line"],
                "token_index": new["token_index"],
                "tibetan_syllable": new["tibetan_syllable"],
                "source_latin_token": new["source_latin_token"],
                "old_target": old["proposed_latin_target"],
                "new_supported_target": new["proposed_latin_target"],
                "old_anchor_count": str(old_count),
                "new_anchor_count": str(new_count),
                "audit_conclusion": (
                    "malformed_internal_ng_anchor_removed"
                    if old_count > new_count
                    else "valid_anchor_added"
                ),
                "context_excerpt": new["context_excerpt"],
            }
        )
    return rows


def build_one_anchor_pilot_evidence_audit() -> list[dict[str, str]]:
    """Separate family authorization from evidence actually present per row."""
    root = Path(__file__).resolve().parents[1]
    manifest_path = (
        root
        / "data/final_ng_source_compatible_one_anchor_pilot_prepass_manifest_63a9742.tsv"
    )
    if not manifest_path.exists():
        return []
    manifest = read_tsv(manifest_path)
    positional = [row for row in manifest if row["candidate_status"] == "positional"]
    echoes = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["tibetan_syllable"], row["source_token"], row["target"],
        ): row
        for row in manifest
        if row["candidate_status"] == "echo"
    }
    family_identity = {
        "ཀྲོང": "direct_repeated_tibetan_alignment",
        "རྟིང": "explicit_same_entry_repetition;cross_reference_review",
        "བགྲང": "explicit_same_entry_repetition;cross_reference_review",
    }
    audit: list[dict[str, str]] = []
    for row in positional:
        key = (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["tibetan_syllable"], row["source_token"], row["target"],
        )
        local = echoes.get(key)
        audit.append(
            {
                "tibetan_syllable": row["tibetan_syllable"],
                "volume": row["volume"],
                "page": row["page"],
                "line": row["line"],
                "token_index": row["token_index"],
                "source_token": row["source_token"],
                "target": row["target"],
                "family_target_evidence": (
                    "current dotted anchor present; authoritative base OCR "
                    "source unavailable for direct verification"
                ),
                "anchor_provenance_status": "base_provenance_unverified",
                "family_identity_evidence": family_identity[
                    row["tibetan_syllable"]
                ],
                "row_exact_tibetan_alignment": "reviewed_exact",
                "row_damage_status": row["damage_category"],
                "row_marker_status": "none",
                "row_local_lemma_cue": (
                    local["alignment_category"] if local else "none"
                ),
                "audit_decision": (
                    "preserve_reviewed_correction_but_do_not_reuse_as_"
                    "direct_base_anchor"
                ),
                "context_excerpt": row["context_excerpt"],
            }
        )
    return audit


def build_zero_anchor_variant_audit(
    compatible_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    zero = [
        row for row in compatible_rows
        if row["source_compatible_category"] == "source_compatible_no_anchor"
    ]
    by_syllable: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in compatible_rows:
        by_syllable[row["tibetan_syllable"]].append(row)
    audit: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in zero:
        key = (row["tibetan_syllable"], row["source_latin_token"])
        if key in seen:
            continue
        seen.add(key)
        siblings = by_syllable[row["tibetan_syllable"]]
        audit.append(
            {
                "tibetan_syllable": key[0],
                "source_variant": key[1],
                "source_state": zero_anchor_source_state(
                    key[0], key[1], "", [item for item in zero if (
                        item["tibetan_syllable"], item["source_latin_token"]
                    ) == key]
                ),
                "supported_target": "",
                "other_source_variants": ";".join(sorted({
                    item["source_latin_token"] for item in siblings
                    if item["source_latin_token"] != key[1]
                })),
                "same_tibetan_dotted_forms": next(
                    (
                        item["incompatible_dotted_form_counts"]
                        for item in siblings
                        if item["incompatible_dotted_form_counts"]
                    ),
                    "",
                ),
                "reviewed_canonical_target": load_alignment_review_exceptions()
                .get(key, {}).get("reviewed_canonical_target", ""),
                "review_evidence": load_alignment_review_exceptions()
                .get(key, {}).get("evidence_type", ""),
                "sample_context": row["context_excerpt"],
            }
        )
    return sorted(audit, key=lambda row: (
        row["source_state"], row["tibetan_syllable"], row["source_variant"]
    ))


def build_multi_error_transcription_review(
    compatible_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    exceptions = load_alignment_review_exceptions()
    rows: list[dict[str, str]] = []
    for row in compatible_rows:
        key = (row["tibetan_syllable"], row["source_latin_token"])
        exception = exceptions.get(key)
        if not exception or exception["status"] != "known_multi_error_source":
            continue
        rows.append(
            {
                "volume": row["volume"],
                "page": row["page"],
                "line": row["line"],
                "token_index": row["token_index"],
                "tibetan_syllable": key[0],
                "source_token": key[1],
                "reviewed_canonical_target": exception[
                    "reviewed_canonical_target"
                ],
                "evidence_type": exception["evidence_type"],
                "review_status": "resolved_by_exact_manual_multi_error"
                if exception["reviewed_canonical_target"] else "manual_unresolved",
                "rationale": exception["rationale"],
                "context_excerpt": row["context_excerpt"],
            }
        )
    root = Path(__file__).resolve().parents[1]
    overrides_path = root / "data/reviewed_tibetan_exact_overrides.tsv"
    if overrides_path.exists():
        existing = {
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["source_token"],
            )
            for row in rows
        }
        for override in read_tsv(overrides_path):
            if override.get("reason") != "reviewed_tibetan_exact_manual_multi_error":
                continue
            key = (
                override["volume"], override["page"], override["line"],
                override["token_index"], override["from_token"],
            )
            if key in existing:
                continue
            exception_key, exception = next(
                (
                    (key, value)
                    for key, value in exceptions.items()
                    if key[1] == override["from_token"]
                    and value.get("reviewed_canonical_target")
                    == override["to_token"]
                ),
                (("", ""), {}),
            )
            rows.append(
                {
                    "volume": override["volume"],
                    "page": override["page"],
                    "line": override["line"],
                    "token_index": override["token_index"],
                    "tibetan_syllable": exception_key[0],
                    "source_token": override["from_token"],
                    "reviewed_canonical_target": override["to_token"],
                    "evidence_type": override["evidence"],
                    "review_status": "resolved_by_exact_manual_multi_error",
                    "rationale": exception.get("rationale", ""),
                    "context_excerpt": override.get("review_note", ""),
                }
            )
    return rows


def build_legacy_mechanical_variant_audit(
    compatible_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in compatible_rows:
        if row["source_compatible_category"] != "source_compatible_no_anchor":
            continue
        source = row["source_latin_token"]
        mechanical = source[:-1] + "ṅ" if source else ""
        priority = (
            "malformed_internal_nasal"
            if "ṅ" in source
            else "long_or_gloss_like"
            if len(source) > 8 or row["alignment_review_status"]
            == "obvious_gloss_or_alignment_noise"
            else "different_stem_or_multi_error"
            if row["alignment_review_status"] in {
                "known_multi_error_source",
                "source_variant_requires_manual_review",
            }
            else "ordinary_manual_review"
        )
        rows.append(
            {
                "tibetan_syllable": row["tibetan_syllable"],
                "source_variant": source,
                "former_mechanical_variant_nonsemantic": mechanical,
                "audit_priority": priority,
                "alignment_review_status": row["alignment_review_status"],
                "note": (
                    "Mechanical string transformation only; not a proposed "
                    "correction and not evidence of the canonical transcription."
                ),
                "context_excerpt": row["context_excerpt"],
            }
        )
    priority_order = {
        "malformed_internal_nasal": 0,
        "long_or_gloss_like": 1,
        "different_stem_or_multi_error": 2,
        "ordinary_manual_review": 3,
    }
    return sorted(rows, key=lambda row: (
        priority_order[row["audit_priority"]],
        -len(row["source_variant"]),
        row["tibetan_syllable"],
    ))


def build_focused_gzhung_ljang_variant_review(
    release_root: Path,
    compatible_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    focus = {"གཞུང", "ལྗང"}
    rows: list[dict[str, str]] = []
    provenance = collect_anchor_provenance(release_root)
    provenance_by_key = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["tibetan_syllable"], row["current_dotted_token"],
        ): row["provenance_class"]
        for row in provenance
    }
    for row in compatible_rows:
        if row["tibetan_syllable"] not in focus:
            continue
        disposition = "manual_unresolved"
        if (
            row["tibetan_syllable"] == "ལྗང"
            and row["source_latin_token"] == "ldan"
        ):
            disposition = (
                "final_ng_only_candidate_withheld_base_provenance_unverified"
            )
        elif row["proposed_latin_target"]:
            disposition = "target_supported_but_row_not_authorized"
        rows.append(
            {
                "record_type": "residual_source",
                "volume": row["volume"],
                "page": row["page"],
                "line": row["line"],
                "token_index": row["token_index"],
                "tibetan_syllable": row["tibetan_syllable"],
                "source_or_current_token": row["source_latin_token"],
                "supported_target": row["proposed_latin_target"],
                "provenance": "",
                "disposition": disposition,
                "context_excerpt": row["context_excerpt"],
            }
        )
    aligned, _accepted = collect_aligned_rows(release_root)
    for row in aligned:
        if row["tibetan_syllable"] not in focus:
            continue
        token = row["latin_token"]
        if not is_genuine_dotted_final_ng_anchor(
            token, row["tibetan_syllable"]
        ):
            continue
        key = (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["tibetan_syllable"], token,
        )
        rows.append(
            {
                "record_type": "current_dotted_form",
                "volume": row["volume"],
                "page": row["page"],
                "line": row["line"],
                "token_index": row["token_index"],
                "tibetan_syllable": row["tibetan_syllable"],
                "source_or_current_token": token,
                "supported_target": token,
                "provenance": provenance_by_key.get(key, "unknown"),
                "disposition": (
                    "explicit_user_correction"
                    if provenance_by_key.get(key)
                    == "reviewed_exact_final_ng"
                    else "anchor_provenance_requires_direct_verification"
                ),
                "context_excerpt": row["context_excerpt"].rstrip(),
            }
        )
    return sorted(rows, key=lambda row: (
        row["tibetan_syllable"], row["record_type"], row["volume"],
        int(row["page"]), int(row["line"]), int(row["token_index"]),
    ))


def validate_positional_echo_dual_identities() -> None:
    """A positional/echo duplicate must be resolved, never double-applied."""
    root = Path(__file__).resolve().parents[1]
    decisions_path = root / "data/reviewed_final_ng_echo_decisions.tsv"
    decisions = read_tsv(decisions_path) if decisions_path.exists() else []
    decision_by_key = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["tibetan_syllable"], row["source_token"],
            row["proposed_target"],
        ): row
        for row in decisions
    }
    for path in (root / "data").glob("*final_ng*manifest*.tsv"):
        manifest = read_tsv(path)
        positional = {
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["tibetan_syllable"], row["source_token"], row["target"],
            )
            for row in manifest
            if row.get("candidate_status") == "positional"
        }
        echoes = {
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["tibetan_syllable"], row["source_token"], row["target"],
            )
            for row in manifest
            if row.get("candidate_status") == "echo"
        }
        for key in positional & echoes:
            decision = decision_by_key.get(key)
            # Immutable tranche manifests intentionally include future
            # families before their echo review has happened.  Enforce the
            # no-double-application rule once a decision is recorded, while
            # allowing an as-yet-unreviewed frozen identity to remain queued.
            if decision and decision["decision"] != "resolved_elsewhere":
                raise ValueError(
                    f"{path.name}: dual positional/echo identity {key} must "
                    "be resolved_elsewhere"
                )


def entry_series_cluster_count(rows: list[dict[str, str]]) -> int:
    locations = sorted(
        {
            (row["volume"], int(row["page"]), int(row["line"]))
            for row in rows
        }
    )
    clusters = 0
    previous: tuple[str, int, int] | None = None
    in_cluster = False
    for location in locations:
        adjacent = (
            previous is not None
            and location[0] == previous[0]
            and location[1] == previous[1]
            and location[2] - previous[2] <= 3
        )
        if adjacent and not in_cluster:
            clusters += 1
            in_cluster = True
        elif not adjacent:
            in_cluster = False
        previous = location
    return clusters


def build_insufficient_evidence_matrix(
    release_root: Path,
    compatible_rows: list[dict[str, str]] | None = None,
    echo_rows: list[dict[str, str]] | None = None,
    override_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Expose independent evidence channels without converting them to a score."""
    compatible_rows = (
        compatible_rows
        if compatible_rows is not None
        else build_source_compatible_rows(release_root)
    )
    echo_rows = (
        echo_rows
        if echo_rows is not None
        else build_same_entry_echo_rows(release_root)
    )
    if override_rows is None:
        override_path = (
            Path(__file__).resolve().parents[1]
            / "data/reviewed_tibetan_exact_overrides.tsv"
        )
        override_rows = read_tsv(override_path) if override_path.exists() else []
    override_keys = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["from_token"], row["to_token"],
        )
        for row in override_rows
        if "final_ng" in row.get("reason", "")
    }
    reviewed_identities: set[tuple[str, str, str, str, str, str, str]] = set()
    for manifest in (
        Path(__file__).resolve().parents[1] / "data"
    ).glob("final_ng_*prepass_manifest_*.tsv"):
        for row in read_tsv(manifest):
            identity_key = (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["source_token"], row["target"],
            )
            if identity_key in override_keys:
                reviewed_identities.add(
                    (
                        row["volume"], row["page"], row["line"],
                        row["token_index"], row["tibetan_syllable"],
                        row["source_token"], row["target"],
                    )
                )
    aligned, _accepted = collect_aligned_rows(release_root)
    provenance = collect_anchor_provenance(release_root, aligned)
    google_evidence = collect_google_witness_evidence(release_root)
    root = Path(__file__).resolve().parents[1]
    historical_path = root / "data/final_ng_historical_witness_audit.tsv"
    historical_rows = read_tsv(historical_path) if historical_path.exists() else []
    historical_by_family: dict[
        tuple[str, str, str], list[dict[str, str]]
    ] = defaultdict(list)
    for historical_row in historical_rows:
        historical_by_family[
            (
                historical_row["tibetan_syllable"],
                historical_row["source_variant"],
                historical_row["target"],
            )
        ].append(historical_row)
    reviewed_path = root / "data/final_ng_reviewed_target_propagation.tsv"
    reviewed_rows = read_tsv(reviewed_path) if reviewed_path.exists() else []
    reviewed_by_family = {
        (
            row["tibetan_syllable"], row["source_variant"], row["target"],
        ): row
        for row in reviewed_rows
    }
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in compatible_rows:
        if row["source_compatible_category"] not in {
            "source_compatible_single_anchor",
            "source_compatible_no_anchor",
        }:
            continue
        grouped[
            (
                row["tibetan_syllable"],
                row["source_latin_token"],
                row["proposed_latin_target"],
            )
        ].append(row)

    matrix: list[dict[str, str]] = []
    for (syllable, source, target), family in grouped.items():
        historical_matches = historical_by_family.get(
            (syllable, source, target), []
        )
        historical_anchor = next(
            (
                row for row in historical_matches
                if row["historical_anchor_present"] == "yes"
            ),
            historical_matches[0] if historical_matches else {},
        )
        reviewed_target = reviewed_by_family.get(
            (syllable, source, target), {}
        )
        family_volumes = {row["volume"] for row in family}
        family_anchors = [
            row
            for row in provenance
            if row["tibetan_syllable"] == syllable
            and target
            and row["current_dotted_token"] == target
        ]
        provenance_counts = Counter(
            row["provenance_class"] for row in family_anchors
        )
        raw_anchors = [
            row for row in family_anchors
            if row["provenance_class"] == "base_ocr_dotted"
        ]
        unverified_base_anchors = [
            row for row in family_anchors
            if row["provenance_class"] == "base_provenance_unverified"
        ]
        same_volume_raw = [
            row for row in raw_anchors if row["volume"] in family_volumes
        ]
        cross_volume_raw = [
            row for row in raw_anchors if row["volume"] not in family_volumes
        ]
        family_echoes = [
            row
            for row in echo_rows
            if row["tibetan_syllable"] == syllable
            and row["additional_source_token"] == source
            and row["proposed_target"] == target
        ]
        echo_categories = Counter(row["echo_category"] for row in family_echoes)
        prior_same_source = {
            identity[:4]
            for identity in reviewed_identities
            if identity[4:] == (syllable, source, target)
        } if target else set()
        prior_different_source = {
            identity[:4]
            for identity in reviewed_identities
            if identity[4] == syllable
            and identity[6] == target
            and identity[5] != source
        } if target else set()
        google_matches = [
            item
            for item in google_evidence
            for row in family
            if (
                item["volume"], item["page"], item["line"],
                item["token_index"], item["base_token"],
            ) == (
                row["volume"], row["page"], row["line"],
                row["token_index"], source,
            )
        ]
        google_status = Counter(
            item["witness_status"]
            for item in google_matches
            if target and item["alternate_token"] == target
        )
        google_conflicting = sum(
            bool(target) and item["alternate_token"] != target
            for item in google_matches
        )
        target_channels = []
        if raw_anchors:
            target_channels.append("base_ocr_dotted_anchor")
        if provenance_counts["google_adopted"]:
            target_channels.append("google_adopted_anchor")
        independently_reviewed = [
            row for row in family_anchors
            if row["provenance_class"] == "reviewed_exact_final_ng"
            and "consensus" not in (
                row["correction_reason"] + row["correction_evidence"]
            )
        ]
        circular_reviewed = [
            row for row in family_anchors
            if row["provenance_class"] == "reviewed_exact_final_ng"
            and row not in independently_reviewed
        ]
        if independently_reviewed:
            target_channels.append("independently_reviewed_exact_anchor")
        if google_status["unresolved"]:
            target_channels.append("google_unresolved_exact_target")
        if google_status["candidate"]:
            target_channels.append("google_candidate_exact_target")
        lemma_channels = []
        if echo_categories["explicit_same_lemma_repetition"]:
            lemma_channels.append("explicit_same_entry_repetition")
        if echo_categories["direct_repeated_tibetan_alignment"]:
            lemma_channels.append("direct_repeated_tibetan_alignment")
        if echo_categories["cross_reference_probable"]:
            lemma_channels.append("probable_cross_reference_requires_review")
        clusters = entry_series_cluster_count(family)
        recurrence_channels = [f"undotted_rows:{len(family)}"]
        if clusters:
            recurrence_channels.append(f"entry_series_clusters:{clusters}")
        if not target:
            tier = "no_anchor_alignment_triage"
        elif target_channels and any(
            channel in lemma_channels
            for channel in {
                "explicit_same_entry_repetition",
                "direct_repeated_tibetan_alignment",
            }
        ):
            tier = "manual_one_anchor_pilot_candidate"
        elif raw_anchors:
            tier = "base_anchor_identity_review"
        elif circular_reviewed and not target_channels:
            tier = "circular_reviewed_anchor_dependency"
        else:
            tier = "anchor_provenance_or_identity_review"
        matrix.append(
            {
                "tibetan_syllable": syllable,
                "source_variant": source,
                "source_signature": source_compatible_signature(source) or "",
                "supported_target": target,
                "historical_baseline_sha": historical_anchor.get(
                    "historical_baseline_sha", ""
                ),
                "historical_anchor_present": historical_anchor.get(
                    "historical_anchor_present", ""
                ),
                "historical_anchor_location": (
                    ":".join(
                        historical_anchor.get(field, "")
                        for field in (
                            "historical_volume", "historical_page",
                            "historical_line", "historical_token_index",
                        )
                    ).strip(":")
                ),
                "historical_anchor_provenance_class": historical_anchor.get(
                    "historical_anchor_provenance_class", ""
                ),
                "historical_anchor_change_reason": historical_anchor.get(
                    "historical_anchor_change_reason", ""
                ),
                "reviewed_same_tibetan_target_count": reviewed_target.get(
                    "reviewed_same_tibetan_target_count", "0"
                ),
                "undotted_clean_row_count": str(len(family)),
                "base_ocr_dotted_anchor_count": str(len(raw_anchors)),
                "reviewed_exact_dotted_anchor_count": str(
                    provenance_counts["reviewed_exact_final_ng"]
                ),
                "google_adopted_anchor_count": str(
                    provenance_counts["google_adopted"]
                ),
                "other_postprocess_anchor_count": str(
                    provenance_counts["other_postprocess"]
                ),
                "unknown_provenance_anchor_count": str(
                    provenance_counts["unknown"]
                ),
                "base_provenance_unverified_anchor_count": str(
                    len(unverified_base_anchors)
                ),
                "same_volume_raw_anchor_count": str(len(same_volume_raw)),
                "cross_volume_raw_anchor_count": str(len(cross_volume_raw)),
                "explicit_same_entry_repeat_count": str(
                    echo_categories["explicit_same_lemma_repetition"]
                ),
                "direct_repeated_tibetan_alignment_count": str(
                    echo_categories["direct_repeated_tibetan_alignment"]
                ),
                "probable_cross_reference_count": str(
                    echo_categories["cross_reference_probable"]
                ),
                "google_unresolved_exact_target_count": str(
                    google_status["unresolved"]
                ),
                "google_candidate_exact_target_count": str(
                    google_status["candidate"]
                ),
                "google_conflicting_reading_count": str(google_conflicting),
                "prior_reviewed_same_source_exact_count": str(
                    len(prior_same_source)
                ),
                "prior_reviewed_same_tibetan_target_different_source_count": str(
                    len(prior_different_source)
                ),
                "damaged_row_count": str(
                    sum(
                        row["source_compatible_category"]
                        == "source_compatible_damaged_context"
                        for row in compatible_rows
                        if row["tibetan_syllable"] == syllable
                        and row["source_latin_token"] == source
                    )
                ),
                "marker_row_count": str(
                    sum(
                        row["source_compatible_category"]
                        == "source_compatible_marker_attached"
                        for row in compatible_rows
                        if row["tibetan_syllable"] == syllable
                        and row["source_latin_token"] == source
                    )
                ),
                "tibetan_structure_status": family[0][
                    "syllable_identity_guard"
                ],
                "entry_series_cluster_count": str(clusters),
                "alignment_review_status": family[0][
                    "alignment_review_status"
                ],
                "zero_anchor_source_state": zero_anchor_source_state(
                    syllable,
                    source,
                    target,
                    family,
                ),
                "target_evidence_channels": ";".join(target_channels),
                "lemma_identity_channels": ";".join(lemma_channels),
                "recurrence_context_channels": ";".join(recurrence_channels),
                "circular_reviewed_anchor_count": str(len(circular_reviewed)),
                "suggested_review_tier": tier,
                "volumes": ";".join(sorted(family_volumes)),
                "sample_contexts": " || ".join(
                    row["context_excerpt"] for row in family[:3]
                ),
            }
        )
    return sorted(
        matrix,
        key=lambda row: (
            row["suggested_review_tier"],
            -int(row["undotted_clean_row_count"]),
            row["tibetan_syllable"],
            row["source_variant"],
        ),
    )


def build_same_entry_echo_rows(
    release_root: Path,
    decisions_path: Path | None = None,
) -> list[dict[str, str]]:
    aligned, accepted = collect_aligned_rows(release_root)
    if decisions_path is None:
        decisions_path = Path("data/reviewed_final_ng_echo_decisions.tsv")
    decisions = {}
    decisions_by_identity = {}
    if decisions_path.exists():
        for decision in read_tsv(decisions_path):
            key = (
                decision["volume"], decision["page"], decision["line"],
                decision["token_index"], decision["tibetan_syllable"],
                decision["source_token"], decision["proposed_target"],
            )
            decisions[key] = decision
            identity_key = key[:-1]
            if identity_key in decisions_by_identity:
                decisions_by_identity[identity_key] = {}
            else:
                decisions_by_identity[identity_key] = decision
    echoes: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, int]] = set()
    for row in aligned:
        forms = accepted.get(row["tibetan_syllable"], Counter())
        if not forms:
            continue
        line = row["context_excerpt"]
        tibetan_syllables, _tail, _tail_start = tibetan_syllables_and_tail(line)
        aligned_index = int(row["token_index"])
        matches = list(POSTPROCESS_TOKEN_RE.finditer(line))
        for token_index, match in enumerate(matches, start=1):
            if token_index <= aligned_index:
                continue
            source = match.group(0)
            compatible_targets = Counter(
                {
                    form: count
                    for form, count in forms.items()
                    if source_compatible_pair(source, form)
                }
            )
            if not compatible_targets:
                continue
            target, _count = compatible_targets.most_common(1)[0]
            compatible_target_competing = len(compatible_targets) > 1
            key = (row["volume"], row["page"], row["line"], token_index)
            if key in seen:
                continue
            seen.add(key)
            aligned_match = matches[aligned_index - 1]
            between = line[aligned_match.end():match.start()]
            if compatible_target_competing:
                category = "compatible_target_competing"
                status = "manual_review"
                reason = (
                    "Multiple dotted targets compete within the exact "
                    "case-sensitive source signature."
                )
            elif (
                token_index <= len(tibetan_syllables)
                and aligned_index <= len(tibetan_syllables)
                and tibetan_syllables[aligned_index - 1] == row["tibetan_syllable"]
                and tibetan_syllables[token_index - 1] == row["tibetan_syllable"]
                and not VISIBLE_DAMAGE_RE.search(between)
            ):
                category = "direct_repeated_tibetan_alignment"
                status = "manual_review"
                reason = (
                    "The Tibetan headword and Latin phrase repeat the same "
                    "syllable in the same position and order."
                )
            elif source[:1] in {"T", "I", "\\", "/"}:
                category = "marker_attached"
                status = "defer"
                reason = "Marker reconstruction requires independent evidence."
            elif VISIBLE_DAMAGE_RE.search(between) or VISIBLE_DAMAGE_RE.search(source):
                category = "damaged_reference"
                status = "defer"
                reason = "Damage obscures the relationship to the aligned lemma."
            elif re.search(r"\bauch\b", between, re.IGNORECASE):
                category = "explicit_same_lemma_repetition"
                status = "manual_review"
                reason = "The entry explicitly repeats an alternate form after auch."
            elif re.search(r"\bvgl\.|\bKurzf\.", between, re.IGNORECASE):
                category = "cross_reference_probable"
                status = "manual_review"
                reason = "Cross-reference language suggests, but does not prove, identity."
            elif re.search(r"[,()~]", between):
                category = "alternate_form_same_lemma"
                status = "manual_review"
                reason = "Entry punctuation suggests an alternate form of the same lemma."
            else:
                category = "uncertain"
                status = "defer"
                reason = "No explicit entry-structure cue establishes lemma identity."
            decision_key = (
                row["volume"], row["page"], row["line"], str(token_index),
                row["tibetan_syllable"], source, target,
            )
            decision = decisions.get(
                decision_key,
                decisions_by_identity.get(decision_key[:-1], {}),
            )
            echoes.append(
                {
                    "volume": row["volume"],
                    "page": row["page"],
                    "line": row["line"],
                    "token_index": str(token_index),
                    "tibetan_syllable": row["tibetan_syllable"],
                    "reviewed_canonical_target": target,
                    "aligned_source_token": row["latin_token"],
                    "additional_source_token": source,
                    "context_between": between,
                    "proposed_target": target,
                    "echo_category": category,
                    "evidence": "same_line_entry_structure_after_positional_alignment",
                    "review_status": status,
                    "reason": reason,
                    "prior_decision": decision.get("decision", ""),
                    "decision_rationale": decision.get("rationale", ""),
                    "active_queue": "no" if decision.get("decision") else "yes",
                    "context_excerpt": line,
                }
            )
    emitted_identities = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["tibetan_syllable"], row["additional_source_token"],
        )
        for row in echoes
    }
    aligned_by_identity = {
        (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["tibetan_syllable"], row["latin_token"],
        ): row
        for row in aligned
    }
    for decision in decisions.values():
        identity = (
            decision["volume"], decision["page"], decision["line"],
            decision["token_index"], decision["tibetan_syllable"],
            decision["source_token"],
        )
        if identity in emitted_identities:
            continue
        aligned_row = aligned_by_identity.get(identity)
        if not aligned_row:
            continue
        echoes.append({
            "volume": decision["volume"],
            "page": decision["page"],
            "line": decision["line"],
            "token_index": decision["token_index"],
            "tibetan_syllable": decision["tibetan_syllable"],
            "reviewed_canonical_target": decision["proposed_target"],
            "aligned_source_token": aligned_row["latin_token"],
            "additional_source_token": decision["source_token"],
            "context_between": "",
            "proposed_target": decision["proposed_target"],
            "echo_category": decision["echo_category"],
            "evidence": "persistent_historical_echo_decision",
            "review_status": (
                "accepted" if decision["decision"] == "accepted" else "defer"
            ),
            "reason": (
                "A historical explicit echo decision remains authoritative "
                "even when revised alignment discovery now treats the same "
                "identity positionally."
            ),
            "prior_decision": decision["decision"],
            "decision_rationale": decision["rationale"],
            "active_queue": "no",
            "context_excerpt": aligned_row["context_excerpt"],
        })
    return sorted(
        echoes,
        key=lambda row: (
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
    "syllable_identity_guard", "consensus_basis", "damage_scope", "confidence",
    "suggested_action", "context_excerpt", "reason_for_deferral", "accepted_total",
]
RANKING_FIELDS = [
    "tibetan_syllable", "normalized_source_variant",
    "source_variants_and_counts", "proposed_target", "candidate_count",
    "dominant_count", "damaged_count", "insufficient_count",
    "competing_count", "structure_mismatch_count", "marker_attached_count",
    "accepted_form_evidence", "volumes",
]
ECHO_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "reviewed_canonical_target", "aligned_source_token",
    "additional_source_token", "context_between", "proposed_target",
    "echo_category", "evidence", "review_status", "reason", "prior_decision",
    "decision_rationale", "active_queue", "context_excerpt",
]
SOURCE_COMPATIBLE_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "source_latin_token", "source_signature", "proposed_latin_target",
    "compatible_accepted_target_count", "compatible_competing_form_counts",
    "incompatible_dotted_form_counts", "same_tibetan_dotted_evidence_total",
    "old_alignment_category", "source_compatible_category", "damage_scope",
    "syllable_identity_guard", "confidence", "suggested_action",
    "transcription_integrity_status", "transcription_integrity_violations",
    "alignment_review_status", "context_excerpt", "reason_for_deferral",
]
SOURCE_COMPATIBLE_RANKING_FIELDS = [
    "tibetan_syllable", "source_variant", "source_signature",
    "proposed_target", "candidate_count",
    "old_categories", "new_categories",
    "compatible_accepted_target_count", "compatible_competing_forms",
    "incompatible_dotted_forms_excluded", "damage_count", "volumes",
    "transcription_integrity_status", "transcription_integrity_blocked_count",
]
COVERAGE_FIELDS = ["metric", "count"]
COVERAGE_COMPARISON_FIELDS = [
    "change_type", "volume", "page", "line", "token_index",
    "tibetan_syllable", "source_latin_token", "old_target", "new_target",
    "old_category", "new_category", "compatible_anchor_count",
    "context_excerpt",
]
INSUFFICIENT_EVIDENCE_FIELDS = [
    "tibetan_syllable", "source_variant", "source_signature",
    "supported_target", "historical_baseline_sha",
    "historical_anchor_present", "historical_anchor_location",
    "historical_anchor_provenance_class",
    "historical_anchor_change_reason",
    "reviewed_same_tibetan_target_count", "undotted_clean_row_count",
    "base_ocr_dotted_anchor_count", "reviewed_exact_dotted_anchor_count",
    "google_adopted_anchor_count", "other_postprocess_anchor_count",
    "unknown_provenance_anchor_count",
    "base_provenance_unverified_anchor_count",
    "same_volume_raw_anchor_count",
    "cross_volume_raw_anchor_count", "explicit_same_entry_repeat_count",
    "direct_repeated_tibetan_alignment_count",
    "probable_cross_reference_count", "google_unresolved_exact_target_count",
    "google_candidate_exact_target_count", "google_conflicting_reading_count",
    "prior_reviewed_same_source_exact_count",
    "prior_reviewed_same_tibetan_target_different_source_count",
    "damaged_row_count",
    "marker_row_count", "tibetan_structure_status",
    "entry_series_cluster_count", "alignment_review_status",
    "zero_anchor_source_state",
    "target_evidence_channels", "lemma_identity_channels",
    "recurrence_context_channels", "circular_reviewed_anchor_count",
    "suggested_review_tier",
    "volumes", "sample_contexts",
]
ANCHOR_PROVENANCE_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "current_dotted_token", "provenance_class", "source_token_or_tokens",
    "correction_reason", "correction_evidence", "context_excerpt",
]
MALFORMED_ANCHOR_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "malformed_dotted_token", "valid_anchor_count_for_tibetan_syllable",
    "matches_historical_frozen_target", "audit_decision", "context_excerpt",
]
ANCHOR_COUNT_CHANGE_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "source_latin_token", "old_target", "new_supported_target",
    "old_anchor_count", "new_anchor_count", "audit_conclusion",
    "context_excerpt",
]
PILOT_EVIDENCE_AUDIT_FIELDS = [
    "tibetan_syllable", "volume", "page", "line", "token_index",
    "source_token", "target", "family_target_evidence",
    "anchor_provenance_status", "family_identity_evidence",
    "row_exact_tibetan_alignment", "row_damage_status", "row_marker_status",
    "row_local_lemma_cue", "audit_decision", "context_excerpt",
]
ZERO_ANCHOR_VARIANT_AUDIT_FIELDS = [
    "tibetan_syllable", "source_variant", "source_state",
    "supported_target", "other_source_variants",
    "same_tibetan_dotted_forms", "reviewed_canonical_target",
    "review_evidence", "sample_context",
]
MULTI_ERROR_REVIEW_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "source_token", "reviewed_canonical_target", "evidence_type",
    "review_status", "rationale", "context_excerpt",
]
LEGACY_MECHANICAL_AUDIT_FIELDS = [
    "tibetan_syllable", "source_variant",
    "former_mechanical_variant_nonsemantic", "audit_priority",
    "alignment_review_status", "note", "context_excerpt",
]
FOCUSED_VARIANT_REVIEW_FIELDS = [
    "record_type", "volume", "page", "line", "token_index",
    "tibetan_syllable", "source_or_current_token", "supported_target",
    "provenance", "disposition", "context_excerpt",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=Path("release/current"))
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args()
    validate_positional_echo_dual_identities()
    baseline_path = Path(
        "data/final_ng_source_compatible_legacy_filtered_baseline_541f537.tsv"
    )
    if baseline_path.exists():
        baseline_rows = read_tsv(baseline_path)
    else:
        baseline_rows = []
        for path in sorted(
            (args.release_root / "qa").glob(
                "*/tibetan_cleanup_diagnostics/"
                "tibetan_final_ng_source_compatible_candidates.tsv"
            )
        ):
            baseline_rows.extend(read_tsv(path))
        write_tsv(baseline_path, baseline_rows, SOURCE_COMPATIBLE_FIELDS)
    anchor_baseline_path = Path(
        "data/final_ng_source_compatible_pre_anchor_hardening_c1ad4cc.tsv"
    )
    if anchor_baseline_path.exists():
        anchor_baseline_rows = read_tsv(anchor_baseline_path)
    else:
        anchor_baseline_rows = []
        for path in sorted(
            (args.release_root / "qa").glob(
                "*/tibetan_cleanup_diagnostics/"
                "tibetan_final_ng_source_compatible_candidates.tsv"
            )
        ):
            anchor_baseline_rows.extend(read_tsv(path))
        write_tsv(
            anchor_baseline_path,
            anchor_baseline_rows,
            SOURCE_COMPATIBLE_FIELDS,
        )
    rows = build_consensus_rows(args.release_root)
    compatible_rows = build_source_compatible_rows(args.release_root)
    compatible_rankings = build_source_compatible_rankings(compatible_rows)
    echo_rows = build_same_entry_echo_rows(args.release_root)
    aligned_rows, _accepted = collect_aligned_rows(args.release_root)
    anchor_provenance = collect_anchor_provenance(
        args.release_root, aligned_rows
    )
    malformed_anchor_rows = build_malformed_anchor_audit(
        args.release_root, aligned_rows
    )
    insufficient_matrix = build_insufficient_evidence_matrix(
        args.release_root,
        compatible_rows=compatible_rows,
        echo_rows=echo_rows,
    )
    anchor_count_changes = build_anchor_count_change_audit(
        anchor_baseline_rows, compatible_rows
    )
    write_tsv(
        Path("data/final_ng_one_anchor_pilot_evidence_audit.tsv"),
        build_one_anchor_pilot_evidence_audit(),
        PILOT_EVIDENCE_AUDIT_FIELDS,
    )
    write_tsv(
        Path("data/final_ng_zero_anchor_variant_audit.tsv"),
        build_zero_anchor_variant_audit(compatible_rows),
        ZERO_ANCHOR_VARIANT_AUDIT_FIELDS,
    )
    write_tsv(
        Path("data/final_ng_multi_error_transcription_review.tsv"),
        build_multi_error_transcription_review(compatible_rows),
        MULTI_ERROR_REVIEW_FIELDS,
    )
    write_tsv(
        Path("data/final_ng_zero_anchor_legacy_mechanical_audit.tsv"),
        build_legacy_mechanical_variant_audit(compatible_rows),
        LEGACY_MECHANICAL_AUDIT_FIELDS,
    )
    write_tsv(
        Path("data/final_ng_gzhung_ljang_variant_review.tsv"),
        build_focused_gzhung_ljang_variant_review(
            args.release_root, compatible_rows
        ),
        FOCUSED_VARIANT_REVIEW_FIELDS,
    )
    by_volume: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_volume[row["volume"]].append(row)
    for volume in ["wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"]:
        volume_out = args.out_root / f"tibetan_cleanup_diagnostics_{volume}"
        write_tsv(
            volume_out / "tibetan_final_ng_consensus_candidates.tsv",
            by_volume.get(volume, []),
            FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_family_rankings.tsv",
            build_family_rankings(rows),
            RANKING_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_same_entry_echo_candidates.tsv",
            [row for row in echo_rows if row["volume"] == volume],
            ECHO_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_source_compatible_candidates.tsv",
            [row for row in compatible_rows if row["volume"] == volume],
            SOURCE_COMPATIBLE_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_source_compatible_family_rankings.tsv",
            compatible_rankings,
            SOURCE_COMPATIBLE_RANKING_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_source_compatible_coverage.tsv",
            build_source_compatible_coverage_audit(compatible_rows),
            COVERAGE_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_source_compatible_coverage_comparison.tsv",
            build_source_compatible_coverage_comparison(
                baseline_rows, compatible_rows
            ),
            COVERAGE_COMPARISON_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_source_compatible_reclassifications.tsv",
            build_source_compatible_reclassifications(compatible_rankings),
            SOURCE_COMPATIBLE_RANKING_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_insufficient_evidence_matrix.tsv",
            insufficient_matrix,
            INSUFFICIENT_EVIDENCE_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_dotted_anchor_provenance.tsv",
            [
                row for row in anchor_provenance
                if row["volume"] == volume
            ],
            ANCHOR_PROVENANCE_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_malformed_anchor_audit.tsv",
            [
                row for row in malformed_anchor_rows
                if row["volume"] == volume
            ],
            MALFORMED_ANCHOR_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_anchor_hardening_comparison.tsv",
            build_source_compatible_coverage_comparison(
                anchor_baseline_rows, compatible_rows
            ),
            COVERAGE_COMPARISON_FIELDS,
        )
        write_tsv(
            volume_out / "tibetan_final_ng_anchor_count_changes.tsv",
            [
                row for row in anchor_count_changes
                if row["volume"] == volume
            ],
            ANCHOR_COUNT_CHANGE_FIELDS,
        )
    counts = Counter(row["alignment_category"] for row in rows)
    print(f"candidates={len(rows)}")
    for category, count in sorted(counts.items()):
        print(f"{category}={count}")


if __name__ == "__main__":
    main()
