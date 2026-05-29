#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


SAMPLE_SIZE = 100
RANDOM_SEED = 20260519
MANIFEST_PATH = Path("data/production_volume_inputs.tsv")
MANIFEST_COLUMNS = [
    "label",
    "display",
    "source_pdf",
    "merged",
    "audit",
    "google_vision",
    "final_name",
    "status",
    "note",
]
SUSPICIOUS_CLASS_ORDER = [
    "live_remaining",
    "manual_review_only",
    "sanskrit_or_indic_policy_case",
    "citation_or_siglum",
    "german_or_prose_false_positive",
    "already_corrected_or_stale",
]
SUSPICIOUS_CLASS_PRIORITY = {name: idx for idx, name in enumerate(SUSPICIOUS_CLASS_ORDER)}
LOW_GOOGLE_PAGE_MATCH_SCORE = 0.60
LOW_GOOGLE_CANONICAL_OVERLAP = 0.35
SUSPICIOUS_MARKDOWN_HEADERS = [
    "classification",
    "source",
    "token",
    "reason_or_issue",
    "count",
    "heuristic_suggestion",
    "evidence",
    "sample_page",
    "sample_line",
    "sample_excerpt",
]
LIVE_HEURISTIC_WARNING = (
    "The suggestion field is produced by validator/canonicalisation heuristics. "
    "It is not OCR-witness evidence and should not be treated as a correction direction unless independently supported."
)
LIVE_VALIDATOR_ONLY_NOTE = (
    "`validator_only=yes` means no Google alternate-witness support is recorded; "
    "withheld review-queue presence is provenance, not independent OCR-witness evidence."
)
LIVE_BUCKET_VALIDATOR_ONLY = "live_validator_only_residue"
LIVE_BUCKET_REVIEW_QUEUE = "live_review_queue_candidates"
LIVE_BUCKET_GOOGLE = "live_google_supported_candidates"
LIVE_BUCKET_POLICY_FALSE_POSITIVE = "live_policy_or_false_positive"
LIVE_BUCKET_OUTPUTS = [
    (LIVE_BUCKET_VALIDATOR_ONLY, "live_validator_only_residue.tsv"),
    (LIVE_BUCKET_REVIEW_QUEUE, "live_review_queue_candidates.tsv"),
    (LIVE_BUCKET_GOOGLE, "live_google_supported_candidates.tsv"),
    (LIVE_BUCKET_POLICY_FALSE_POSITIVE, "live_policy_or_false_positive.tsv"),
]
LIVE_ROW_ADJUDICATIONS = {
    ("ch'a", "cha'"): (
        LIVE_BUCKET_POLICY_FALSE_POSITIVE,
        "non-Tibetan romanisation / validator false positive; likely Wade-Giles or another romanisation context; do not promote",
    ),
    ("źwa", "ziṅ"): (
        LIVE_BUCKET_POLICY_FALSE_POSITIVE,
        "validator false positive; źwa and ziṅ are distinct Tibetan forms; do not promote",
    ),
    ("mkha'i", "mkhai"): (
        LIVE_BUCKET_POLICY_FALSE_POSITIVE,
        "validator false positive / wrong direction; mkha'i is valid Tibetan/Wylie; do not promote",
    ),
    ("mkhai", "mkha'i"): (
        LIVE_BUCKET_REVIEW_QUEUE,
        "manual review only; possible local OCR/transliteration error only if page context confirms; no general apostrophe rule",
    ),
    ("ishod", "ishal"): (
        LIVE_BUCKET_VALIDATOR_ONLY,
        "validator-only/manual-review; not a correction candidate unless independently supported by source image or Google unresolved evidence",
    ),
    ("dzā", "dza"): (
        LIVE_BUCKET_POLICY_FALSE_POSITIVE,
        "orthographic/transcription policy or validator-only; do not promote automatically",
    ),
}
TOKEN_EDGE_CHARS = " \t\r\n\f\v.,;:!?()[]{}<>\"“”‘’‚‹›«»"
GERMAN_UMLAUT_CHARS = set("äöüÄÖÜß")
GERMAN_FALSE_POSITIVE_TOKENS = {
    "abkürzungsverzeichnisse",
    "abhängigkeit",
    "anhänger",
    "bewußtsein",
    "erklärung",
    "fülle",
    "gefühle",
    "glück",
    "körper",
    "könig",
    "königs",
    "länge",
    "öffnung",
    "prüfung",
    "rückkehr",
    "rüstung",
    "unglück",
    "übersetzung",
    "überlieferung",
    "verfügung",
    "wörterbuch",
}
SANSKRIT_INDIC_HINTS = (
    "ācāry",
    "acary",
    "āgama",
    "agama",
    "avalok",
    "bodhisatt",
    "dharma",
    "gangä",
    "gangā",
    "jñ",
    "jn",
    "mahā",
    "mahä",
    "mantra",
    "nāg",
    "näg",
    "nyāya",
    "nyaya",
    "praj",
    "pāram",
    "päram",
    "śāstr",
    "śästr",
    "śrāv",
    "śräv",
    "sūtr",
    "sutra",
    "tantra",
    "ṭīkā",
    "tika",
    "vajra",
    "vyutpatti",
)
SANSKRIT_REVIEW_REASONS = {
    "sanskrit_char_normalize",
    "sanskrit_jn_cluster_contextual",
    "sanskrit_jn_cluster_plus_allowlist",
    "sanskrit_singleton_context_gate",
}
SANSKRIT_FAMILY_FOLD = str.maketrans(
    {
        "ā": "a",
        "ä": "a",
        "â": "a",
        "á": "a",
        "à": "a",
        "ã": "a",
        "ī": "i",
        "ı": "i",
        "ï": "i",
        "ū": "u",
        "ü": "u",
        "ṛ": "r",
        "ṝ": "r",
        "ḷ": "l",
        "ṅ": "n",
        "ñ": "n",
        "ṇ": "n",
        "ṭ": "t",
        "ḍ": "d",
        "ś": "s",
        "ṣ": "s",
        "ḥ": "h",
        "ṃ": "m",
        "ṁ": "m",
    }
)
PAGE_MARKER_RE = re.compile(
    r"^\s*(?:[-=]+\s*)?(?:\[?\s*)?page\s+0*(\d+)(?:\s*\]?)(?:\s*[-=]+)?\s*$",
    re.IGNORECASE,
)
DIACRITIC_OR_CONFUSABLE_RE = re.compile(
    r"[āīūṛṝḷṅñṇṭḍśṣḥṃṁĀĪŪṚṜḶṄÑṆṬḌŚṢḤṂ$ı]"
)
SANSKRIT_DIACRITIC_CHARS = set("āīūṛṝḷṅñṇṭḍśṣḥṃṁĀĪŪṚṜḶṄÑṆṬḌŚṢḤṂ")
SANSKRIT_DEGRADATION_CHARS = set("äã$ıÄÃ")
SANSKRIT_CONTEXT_CUE_RE = re.compile(
    r"(?:\b(?:skt\.?|sanskrit|mvy|lex\.?|dagy|sgra|title|s[ūu]tra|siitra|"
    r"śāstra|śastra|shastra|t[īi]k[āa]|tika|vyutpatti|ny[āa]ya|"
    r"praj[nñ]?|jñ[āa]|jn[āa]|vajra|bodhi|dharma|mah[āaä]|p[āaä]ram|"
    r"mantra|tantra|ārya|arya|nāg|näg|garbha)\b|[/：:])",
    re.IGNORECASE,
)
ROMAN_NUMERAL_TOKEN_RE = re.compile(r"(?i)^[ivxlcdm]+$")
ALL_CAPS_SIGLUM_RE = re.compile(r"^[A-ZÄÖÜŚṢṬḌṆṄÑČŠŽ]{2,16}\.?$")
TIBETAN_WYLIE_APOSTROPHE_RE = re.compile(r"(?i)^[a-z]+(?:'[a-z]+)+$")
SANSKRIT_TOKEN_HINT_RE = re.compile(
    r"(?:praj|pāram|päram|param|jñ|jn|mah[āaä]|vyutpatti|ny[āa]ya|"
    r"ṭīk|tik|dharm|k[īi]rti|śr[āaä]v|sr[āaä]v|ś[āaä]str|s[ūu]tr|"
    r"bodhi|vajra|garbha|nāg|näg|taks|takṣ|samnip|samnipa|saptotsad|"
    r"d[ūu]ram|acala|par[āaä]kar|vṛnd|vrnd|tamal|apad|sahasrik|"
    r"paryant|m[āaä]rg|sa[ṃm]jñ|samjn|v[ṛr]k[ṣs]|pu[ṣs]p|ratnak)",
    re.IGNORECASE,
)
RESIDUAL_SANSKRIT_DAMAGE_FIELDS = [
    "volume",
    "source_file",
    "page",
    "line",
    "token",
    "candidate_family",
    "proposed_target",
    "context_excerpt",
    "evidence",
    "confidence",
    "suggested_action",
]
RESIDUAL_STRONG_SANSKRIT_CONTEXT_RE = re.compile(
    r"(?<!\w)(?:skt\.?|Sanskrit|Mvy|Lex\.?|Dagy|sGra|Toh|Samv|Dīp|Atisa|"
    r"Buddha|Bodhisattva|Praj|J(?:n|ñ)[aā]|śr[āaä]va|sr[āaä]va|"
    r"Vai[śs]v|M[äā]ra|N[äā]ga|Ratnak[äāuū]t|Bl[üu]tenbaum|"
    r"Weg ohne Hindernisse|fu[ßs]los|Steuermann|Bez\.|npr\.?)(?!\w)",
    re.IGNORECASE,
)
RESIDUAL_SUTRA_DAMAGE_RE = re.compile(
    r"(?:siitra|s[ūu]rtra|s[āa]tra|fs[ūu]tras?|s[ūu]trta)", re.IGNORECASE
)
RESIDUAL_JN_DAMAGE_RE = re.compile(r"jn(?=[aāiīuūeoṛṝḷ])", re.IGNORECASE)
RESIDUAL_FINAL_VISARGA_RE = re.compile(
    r"^[A-Za-zāīūṛṝḷṅñṇṭḍśṣṃṁäÄüÜöÖāīūĀĪŪ]+[bl]$", re.IGNORECASE
)
RESIDUAL_PROMOTE_TOKEN_TARGETS = {
    "anantäparyantab": "anantāparyantaḥ",
    "pratikäülasamjnä": "pratikūlasaṃjñā",
    "puspavrksab": "puṣpavṛkṣaḥ",
}
RESIDUAL_REVIEW_TOKEN_TARGETS = {
    "Aryaratnakäta": "Āryaratnakūṭa",
    "dnantaryamärgab": "ānantaryamārgaḥ",
    "jnaurasab": "jinaurasaḥ",
    "Käśy": "Kāśy",
    "Käsy": "Kāśy",
    "śinaväsika": "Śāṇavāsika",
    "śosa-räpasya": "śoṣa-rūpasya",
    "śrijhäna": "śrījñāna",
    "ucchanganäam": "ucchanganāam",
    "VisT": "VisṬ",
}
TIBETAN_WYLIE_CANDIDATE_KEYS = {
    "dan",
    "dani",
    "dari",
    "den",
    "dnul",
    "gispa",
    "gnan",
    "gnari",
    "gnis",
    "gnispa",
    "granas",
    "graris",
    "gtsan",
    "gtsari",
    "han",
    "in",
    "kyan",
    "kyani",
    "mkhai",
    "nan",
    "nani",
    "nas",
    "nin",
    "nl",
    "sam",
    "sel",
    "ses",
    "sie",
    "sin",
    "snam",
    "zin",
}


@dataclass(frozen=True)
class VolumeSpec:
    label: str
    display: str
    source_pdf: str
    merged: str
    audit: str
    google_vision: str
    final_name: str
    status: str
    note: str

    @property
    def alternate(self) -> str:
        return self.google_vision


def load_volume_manifest(path: Path = MANIFEST_PATH) -> list[VolumeSpec]:
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        missing = [column for column in MANIFEST_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
        volumes: list[VolumeSpec] = []
        for row in reader:
            if not any((value or "").strip() for value in row.values()):
                continue
            values = {column: (row.get(column, "") or "").strip() for column in MANIFEST_COLUMNS}
            volumes.append(VolumeSpec(**values))
    return volumes


def manifest_path_state(path_text: str) -> str:
    if not path_text:
        return "blank"
    return "present" if Path(path_text).exists() else "missing"


def missing_ready_inputs(spec: VolumeSpec) -> list[str]:
    missing: list[str] = []
    for field in ["source_pdf", "merged", "audit", "google_vision"]:
        path_text = getattr(spec, field)
        if not path_text or not Path(path_text).exists():
            missing.append(field)
    return missing


def select_ready_volumes(volumes: list[VolumeSpec]) -> tuple[list[VolumeSpec], list[str]]:
    ready: list[VolumeSpec] = []
    warnings: list[str] = []
    for spec in volumes:
        if spec.status != "ready":
            warnings.append(f"Skipping {spec.display}: status={spec.status} ({spec.note})")
            continue
        missing = missing_ready_inputs(spec)
        if missing:
            warnings.append(f"Skipping {spec.display}: ready row has missing inputs: {', '.join(missing)}")
            continue
        ready.append(spec)
    return ready, warnings


def volume_coverage_rows(volumes: list[VolumeSpec], included: set[str]) -> list[list[object]]:
    rows: list[list[object]] = []
    for spec in volumes:
        rows.append(
            [
                spec.display,
                spec.status,
                "yes" if spec.label in included else "no",
                manifest_path_state(spec.source_pdf),
                manifest_path_state(spec.merged),
                manifest_path_state(spec.audit),
                manifest_path_state(spec.google_vision),
                spec.note,
            ]
        )
    return rows


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_by(rows: list[dict[str, str]], key: str) -> Counter[str]:
    return Counter(row.get(key, "") or "(blank)" for row in rows)


def top_by_page(rows: list[dict[str, str]], limit: int = 20) -> list[tuple[str, int]]:
    return Counter(row.get("page", "") or "(blank)" for row in rows).most_common(limit)


def stratified_sample(
    rows: list[dict[str, str]],
    key: str,
    sample_size: int,
    rng: random.Random,
) -> list[dict[str, str]]:
    if len(rows) <= sample_size:
        result = list(rows)
        rng.shuffle(result)
        return result
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row.get(key, "") or "(blank)"].append(row)
    total = len(rows)
    selected: list[dict[str, str]] = []
    seen: set[int] = set()
    for group_rows in sorted(groups.values(), key=len, reverse=True):
        quota = max(1, round(sample_size * len(group_rows) / total))
        picks = rng.sample(group_rows, min(quota, len(group_rows)))
        for row in picks:
            row_id = id(row)
            if row_id not in seen:
                selected.append(row)
                seen.add(row_id)
    if len(selected) > sample_size:
        selected = rng.sample(selected, sample_size)
    elif len(selected) < sample_size:
        remaining = [row for row in rows if id(row) not in seen]
        selected.extend(rng.sample(remaining, min(sample_size - len(selected), len(remaining))))
    selected.sort(key=lambda r: (safe_int(r.get("page", "")), safe_int(r.get("line", "")), r.get("reason", "")))
    return selected


def safe_int(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return 0


def safe_float(value: str | None) -> float:
    try:
        return float(value or "nan")
    except ValueError:
        return float("nan")


def normalized_numeric_key(value: str | None) -> str:
    match = re.search(r"\d+", value or "")
    return str(int(match.group(0))) if match else ""


def truncate(value: str, limit: int = 110) -> str:
    value = (value or "").replace("\n", " ").replace("\r", " ")
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."


def md_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def md_table(headers: list[str], rows: list[list[object]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(md_escape(cell) for cell in row) + " |")
    return out


def reason_table(counter: Counter[str]) -> list[list[object]]:
    return [[reason, count] for reason, count in counter.most_common()]


def normalize_report_token(token: str) -> str:
    return (token or "").strip(TOKEN_EDGE_CHARS)


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def page_line_token_key(row: dict[str, str], token: str) -> tuple[str, str, str]:
    page = normalized_numeric_key(row.get("sample_page") or row.get("page"))
    line = normalized_numeric_key(row.get("sample_line") or row.get("line"))
    token = normalize_report_token(token)
    if not page or not line or not token:
        return ("", "", "")
    return (page, line, token)


def page_line_token_index(rows: list[dict[str, str]], token_fields: tuple[str, ...]) -> set[tuple[str, str, str]]:
    index: set[tuple[str, str, str]] = set()
    for row in rows:
        page = normalized_numeric_key(row.get("page"))
        line = normalized_numeric_key(row.get("line"))
        if not page or not line:
            continue
        for field in token_fields:
            token = normalize_report_token(row.get(field, ""))
            if token:
                index.add((page, line, token))
    return index


def withheld_review_token_index(rows: list[dict[str, str]]) -> set[tuple[str, str, str]]:
    withheld = [
        row
        for row in rows
        if (row.get("applied", "") or "").strip().lower() not in {"1", "true", "yes"}
    ]
    return page_line_token_index(withheld, ("from_token", "to_token"))


def corrected_token_counter(text: str) -> Counter[str]:
    tokens: Counter[str] = Counter()
    for piece in re.split(r"\s+", text or ""):
        token = normalize_report_token(piece)
        if token:
            tokens[token] += 1
    return tokens


def corrected_scope_token_counters(
    text: str,
) -> tuple[Counter[str], dict[str, Counter[str]], dict[str, Counter[str]]]:
    global_tokens: Counter[str] = Counter()
    page_tokens: dict[str, Counter[str]] = defaultdict(Counter)
    line_tokens: dict[str, Counter[str]] = defaultdict(Counter)
    global_line = 0
    for page_index, page_text in enumerate((text or "").split("\f"), start=1):
        current_page = str(page_index)
        page_line = 0
        for raw_line in page_text.splitlines():
            marker = PAGE_MARKER_RE.match(raw_line)
            if marker:
                current_page = str(int(marker.group(1)))
                page_line = 0
                continue
            global_line += 1
            page_line += 1
            line_counter = corrected_token_counter(raw_line)
            if not line_counter:
                continue
            global_tokens.update(line_counter)
            page_tokens[current_page].update(line_counter)
            for key in {str(global_line), f"{current_page}:{page_line}", f"{current_page}:{global_line}"}:
                line_tokens[key].update(line_counter)
    return global_tokens, dict(page_tokens), dict(line_tokens)


def corrected_presence_for_row(
    row: dict[str, str],
    token: str,
    corrected_tokens: Counter[str],
    corrected_page_tokens: dict[str, Counter[str]],
    corrected_line_tokens: dict[str, Counter[str]],
) -> tuple[int, str]:
    page = normalized_numeric_key(row.get("sample_page") or row.get("page"))
    line = normalized_numeric_key(row.get("sample_line") or row.get("line"))
    if page:
        if line:
            page_line_key = f"{page}:{line}"
            if corrected_line_tokens.get(page_line_key, Counter())[token]:
                return corrected_line_tokens[page_line_key][token], f"line:{page_line_key}"
        return corrected_page_tokens.get(page, Counter())[token], f"page:{page}"
    if line:
        return corrected_line_tokens.get(line, Counter())[token], f"line:{line}"
    return corrected_tokens[token], "global"


def corrected_line_text_for_row(corrected_text: str, row: dict[str, str]) -> str | None:
    page = normalized_numeric_key(row.get("sample_page") or row.get("page"))
    line = normalized_numeric_key(row.get("sample_line") or row.get("line"))
    if not page or not line:
        return None
    target_line = int(line)
    for page_index, page_text in enumerate((corrected_text or "").split("\f"), start=1):
        current_page = str(page_index)
        page_line = 0
        for raw_line in page_text.splitlines():
            marker = PAGE_MARKER_RE.match(raw_line)
            if marker:
                current_page = str(int(marker.group(1)))
                page_line = 0
                continue
            page_line += 1
            if current_page == page and page_line == target_line:
                return raw_line
    return None


def corrected_line_resolves_google_candidate(corrected_text: str, row: dict[str, str]) -> bool:
    corrected_line = corrected_line_text_for_row(corrected_text, row)
    if corrected_line is None:
        return False
    tokens = corrected_token_counter(corrected_line)
    base_token = normalize_report_token(row.get("base_token", ""))
    alternate_token = normalize_report_token(row.get("alternate_token", ""))
    if base_token and tokens[base_token]:
        return False
    if alternate_token and tokens[alternate_token]:
        return True
    return bool(base_token)


def applied_from_token_counter(changes: list[dict[str, str]], adoptions: list[dict[str, str]]) -> Counter[str]:
    tokens: Counter[str] = Counter()
    for row in changes:
        if row.get("applied", "1") == "0":
            continue
        token = normalize_report_token(row.get("from_token", ""))
        if token:
            tokens[token] += 1
    for row in adoptions:
        token = normalize_report_token(row.get("base_token", ""))
        if token:
            tokens[token] += 1
    return tokens


def looks_like_sanskrit_or_indic(token: str, reason: str, excerpt: str) -> bool:
    token_l = normalize_report_token(token).lower()
    context_l = f"{reason} {excerpt}".lower()
    if "sanskrit" in context_l or "indic" in context_l or "skt" in context_l:
        return True
    return any(hint in token_l or hint in context_l for hint in SANSKRIT_INDIC_HINTS)


def is_sanskrit_review_suggestion(row: dict[str, str]) -> bool:
    reason = (row.get("reason", "") or "").strip().lower()
    return reason in SANSKRIT_REVIEW_REASONS


def sanskrit_review_family_key(row: dict[str, str]) -> str:
    token = normalize_report_token(row.get("to_token") or row.get("from_token", ""))
    folded = token.lower().translate(SANSKRIT_FAMILY_FOLD)
    family = re.sub(r"[^a-z]+", "", folded)
    return family or normalize_report_token(row.get("from_token", "")).lower()


def looks_like_german_or_prose(token: str, reason: str, excerpt: str) -> bool:
    token_l = normalize_report_token(token).lower()
    reason_l = (reason or "").lower()
    if "german" in reason_l:
        return True
    if token_l in GERMAN_FALSE_POSITIVE_TOKENS:
        return True
    return any(char in token for char in GERMAN_UMLAUT_CHARS)


def looks_like_citation_or_siglum(token: str, reason: str, excerpt: str) -> bool:
    token_s = normalize_report_token(token)
    reason_l = (reason or "").lower()
    excerpt_l = (excerpt or "").lower()
    if "citation" in reason_l or "siglum" in reason_l:
        return True
    if "$" in token_s and any(char.isupper() for char in token_s):
        return True
    if re.fullmatch(r"[A-Z][A-Za-z$Śś-]{1,12}(?:-[A-Z])?", token_s):
        return any(cue in excerpt_l for cue in ["lex.", "sigl", "mahāvy", "mahavy", "t.", "p.", "liś", "viś"])
    return False


def looks_manual_review_only(token: str, reason: str, suggestion: str) -> bool:
    token_s = normalize_report_token(token)
    reason_l = (reason or "").lower()
    if not suggestion or normalize_report_token(suggestion) == token_s:
        return False
    if "review" in reason_l:
        return True
    if "confusable" in reason_l:
        return True
    if "$" in token_s or "ñ" in token_s or "ṅ" in token_s:
        return True
    return bool(re.match(r"I[a-z]", token_s))


def classify_suspicious_token(
    row: dict[str, str],
    scoped_count: int,
    scoped_scope: str,
    global_count: int,
    applied_count: int,
) -> tuple[str, str]:
    token = normalize_report_token(row.get("token", ""))
    reason = row.get("reason_or_issue", "")
    suggestion = normalize_report_token(row.get("suggestion", ""))
    excerpt = row.get("sample_excerpt", "")
    if not token:
        return "manual_review_only", "blank token in source QA row"
    if applied_count and not scoped_count:
        return (
            "already_corrected_or_stale",
            f"appears as applied from_token {applied_count} time(s) and not in corrected text for {scoped_scope}",
        )
    if not scoped_count:
        if global_count:
            return (
                "already_corrected_or_stale",
                f"not found in corrected text for {scoped_scope}; exact token occurs {global_count} time(s) elsewhere",
            )
        return "already_corrected_or_stale", f"not found as an exact token in corrected text for {scoped_scope}"
    if looks_like_sanskrit_or_indic(token, reason, excerpt):
        return "sanskrit_or_indic_policy_case", f"still present in {scoped_scope}; Sanskrit/Indic lexical or context cue"
    if looks_like_german_or_prose(token, reason, excerpt):
        return "german_or_prose_false_positive", f"still present in {scoped_scope}; German/prose token flagged by transliteration validator"
    if looks_like_citation_or_siglum(token, reason, excerpt):
        return "citation_or_siglum", f"still present in {scoped_scope}; citation/siglum-shaped token or context"
    if applied_count:
        return "manual_review_only", f"still present in {scoped_scope} and also appears as applied from_token {applied_count} time(s)"
    if looks_manual_review_only(token, reason, suggestion):
        return "manual_review_only", f"still present in {scoped_scope}; context-sensitive or unsafe for automatic correction"
    if suggestion and suggestion != token:
        return "live_remaining", f"still present in {scoped_scope} with a heuristic suggestion"
    return "manual_review_only", f"still present in {scoped_scope}; no safe automatic classification evidence"


def live_row_bucket(row: dict[str, str]) -> tuple[str, str]:
    token = normalize_report_token(row.get("token", ""))
    suggestion = normalize_report_token(row.get("suggestion", ""))
    adjudicated = LIVE_ROW_ADJUDICATIONS.get((token, suggestion))
    if adjudicated:
        return adjudicated
    if (
        row.get("alternate_witness_adoption_match") == "yes"
        or row.get("alternate_witness_unresolved_match") == "yes"
    ):
        return (
            LIVE_BUCKET_GOOGLE,
            "Google alternate-witness evidence exists at the same page/line/token; review source before promotion",
        )
    if row.get("review_queue_withheld_match") == "yes":
        return (
            LIVE_BUCKET_REVIEW_QUEUE,
            "withheld review-queue heuristic; requires source/context review before promotion",
        )
    if row.get("validator_only") == "yes":
        return (
            LIVE_BUCKET_VALIDATOR_ONLY,
            "validator/canonicalisation heuristic only; not a correction candidate without independent support",
        )
    return (
        LIVE_BUCKET_VALIDATOR_ONLY,
        "no independent OCR-witness support recorded; not a correction candidate without source review",
    )


def sort_suspicious_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            SUSPICIOUS_CLASS_PRIORITY.get(row.get("classification", "manual_review_only"), 99),
            -safe_int(row.get("count", "")),
            row.get("volume", ""),
            row.get("token", ""),
            row.get("source", ""),
        ),
    )


def suspicious_summary_rows(rows: list[dict[str, str]], volume: str = "") -> list[dict[str, str]]:
    row_counts: Counter[str] = Counter()
    occurrence_counts: Counter[str] = Counter()
    for row in rows:
        classification = row.get("classification", "manual_review_only") or "manual_review_only"
        row_counts[classification] += 1
        occurrence_counts[classification] += safe_int(row.get("count", ""))
    return [
        {
            "volume": volume,
            "classification": classification,
            "rows": str(row_counts[classification]),
            "occurrences": str(occurrence_counts[classification]),
        }
        for classification in SUSPICIOUS_CLASS_ORDER
        if row_counts[classification]
    ]


def sample_change_row(volume: str, source_file: Path, row: dict[str, str]) -> dict[str, str]:
    return {
        "volume": volume,
        "source_file": str(source_file),
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "reason": row.get("reason", ""),
        "from_token": row.get("from_token", ""),
        "to_token": row.get("to_token", ""),
        "line_excerpt": row.get("line_excerpt", ""),
        "zone": row.get("zone", ""),
        "tier": row.get("tier", ""),
        "alignment_method": row.get("alignment_method", ""),
        "alternate_page": row.get("alternate_page", ""),
    }


def sample_adoption_row(volume: str, source_file: Path, row: dict[str, str]) -> dict[str, str]:
    return {
        "volume": volume,
        "source_file": str(source_file),
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "reason": row.get("reason", ""),
        "from_token": row.get("base_token", ""),
        "to_token": row.get("alternate_token", ""),
        "line_excerpt": row.get("base_line", ""),
        "zone": "",
        "tier": "",
        "alignment_method": row.get("alignment_method", ""),
        "alternate_page": row.get("alternate_page", ""),
    }


def watchdog_review_row(volume: str, source_file: Path, row: dict[str, str]) -> dict[str, str]:
    return {
        "volume": volume,
        "source_file": str(source_file),
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "entry_id": row.get("entry_id", ""),
        "zone": row.get("zone", ""),
        "from_token": row.get("from_token", ""),
        "to_token": row.get("to_token", ""),
        "tier": row.get("tier", ""),
        "reason": row.get("reason", ""),
        "watchdog_flags": row.get("watchdog_flags", ""),
        "line_excerpt": row.get("line_excerpt", ""),
    }


def sanskrit_review_row(volume: str, source_file: Path, row: dict[str, str]) -> dict[str, str]:
    return {
        "volume": volume,
        "source_file": str(source_file),
        "family_key": sanskrit_review_family_key(row),
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "entry_id": row.get("entry_id", ""),
        "zone": row.get("zone", ""),
        "from_token": row.get("from_token", ""),
        "to_token": row.get("to_token", ""),
        "tier": row.get("tier", ""),
        "reason": row.get("reason", ""),
        "applied": row.get("applied", ""),
        "line_excerpt": row.get("line_excerpt", ""),
    }


def google_review_row(volume: str, source_file: Path, row: dict[str, str], bucket: str, evidence: str) -> dict[str, str]:
    return {
        "volume": volume,
        "source_file": str(source_file),
        "bucket": bucket,
        "evidence": evidence,
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "token_index": row.get("token_index", ""),
        "base_token": row.get("base_token", ""),
        "alternate_token": row.get("alternate_token", ""),
        "reason": row.get("reason", ""),
        "base_key": row.get("base_key", ""),
        "alternate_key": row.get("alternate_key", ""),
        "alignment_method": row.get("alignment_method", ""),
        "alternate_page": row.get("alternate_page", ""),
        "page_match_score": row.get("page_match_score", ""),
        "canonical_overlap": row.get("canonical_overlap", ""),
        "base_line": row.get("base_line", ""),
        "alternate_line": row.get("alternate_line", ""),
    }


def low_confidence_google_adoption_row(
    volume: str,
    source_file: Path,
    row: dict[str, str],
) -> dict[str, str] | None:
    page_match_score = safe_float(row.get("page_match_score"))
    canonical_overlap = safe_float(row.get("canonical_overlap"))
    evidence: list[str] = []
    if page_match_score == page_match_score and page_match_score < LOW_GOOGLE_PAGE_MATCH_SCORE:
        evidence.append(f"page_match_score={row.get('page_match_score', '')}")
    if canonical_overlap == canonical_overlap and canonical_overlap < LOW_GOOGLE_CANONICAL_OVERLAP:
        evidence.append(f"canonical_overlap={row.get('canonical_overlap', '')}")
    if not evidence:
        return None
    return google_review_row(volume, source_file, row, "low_confidence_google_adoption", "; ".join(evidence))


def sanskrit_candidate_key(token: str) -> str:
    folded = normalize_report_token(token).lower().translate(SANSKRIT_FAMILY_FOLD)
    return re.sub(r"[^a-z0-9]+", "", folded)


def levenshtein_limited(left: str, right: str, limit: int = 2) -> int:
    if left == right:
        return 0
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        row_min = i
        for j, right_char in enumerate(right, 1):
            cost = 0 if left_char == right_char else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


def google_sanskrit_keys_compatible(row: dict[str, str], base_token: str, alternate_token: str) -> tuple[bool, str]:
    base_key = (row.get("base_key", "") or "").strip()
    alternate_key = (row.get("alternate_key", "") or "").strip()
    if base_key and alternate_key and base_key == alternate_key:
        return True, "report keys match"

    base_safe_key = sanskrit_candidate_key(base_key or base_token)
    alternate_safe_key = sanskrit_candidate_key(alternate_key or alternate_token)
    if base_safe_key and alternate_safe_key and base_safe_key == alternate_safe_key:
        return True, "Sanskrit-safe keys match"
    if base_safe_key and alternate_safe_key and levenshtein_limited(base_safe_key, alternate_safe_key, 2) <= 2:
        return True, "Sanskrit-safe keys are within edit distance 2"
    return False, "keys differ after Sanskrit-safe normalisation"


def token_has_sanskrit_diacritic(token: str) -> bool:
    return any(char in SANSKRIT_DIACRITIC_CHARS for char in token)


def token_has_sanskrit_degradation(token: str) -> bool:
    return any(char in SANSKRIT_DEGRADATION_CHARS for char in token)


def sanskrit_token_quality(token: str) -> int:
    lowered = token.lower()
    score = 0
    score += sum(2 for char in token if char in SANSKRIT_DIACRITIC_CHARS)
    if "jñ" in lowered:
        score += 3
    score -= sum(2 for char in token if char in SANSKRIT_DEGRADATION_CHARS)
    if "$" in token:
        score -= 3
    if ALL_CAPS_SIGLUM_RE.match(token) or ROMAN_NUMERAL_TOKEN_RE.match(token):
        score -= 4
    return score


def alternate_repairs_sanskrit_damage(base_token: str, alternate_token: str) -> bool:
    base_lower = base_token.lower()
    alternate_lower = alternate_token.lower()
    if "jn" in base_lower and "jñ" in alternate_lower:
        return True
    if token_has_sanskrit_degradation(base_token) and token_has_sanskrit_diacritic(alternate_token):
        return True
    if sanskrit_candidate_key(base_token) == sanskrit_candidate_key(alternate_token) and token_has_sanskrit_diacritic(
        alternate_token
    ):
        return True
    return False


def token_has_sanskrit_candidate_hint(token: str) -> bool:
    return bool(SANSKRIT_TOKEN_HINT_RE.search(token))


def looks_like_tibetan_wylie_candidate(base_token: str, alternate_token: str) -> bool:
    tokens = [base_token, alternate_token]
    if any(TIBETAN_WYLIE_APOSTROPHE_RE.match(token) for token in tokens):
        return True
    if any(sanskrit_candidate_key(token) in TIBETAN_WYLIE_CANDIDATE_KEYS for token in tokens):
        return True
    if any("-" in token for token in tokens) and not any(token_has_sanskrit_candidate_hint(token) for token in tokens):
        return True
    return False


def looks_like_bibliographic_name_noise(base_token: str, alternate_token: str) -> bool:
    tokens = [base_token, alternate_token]
    if any(ALL_CAPS_SIGLUM_RE.match(token) for token in tokens):
        return True
    if any(re.search(r"[ČŠŽčšž]", token) for token in tokens) and any(
        token.replace(".", "").isupper() and len(token.replace(".", "")) >= 4 for token in tokens
    ):
        return True
    return False


def looks_like_short_bibliographic_abbreviation(token: str, row: dict[str, str]) -> bool:
    token_s = normalize_report_token(token)
    if not token_s or not token_s[0].isupper() or len(token_s) > 5:
        return False
    context = f"{row.get('base_line', '')} {row.get('alternate_line', '')}"
    if re.search(r"\(\s*[^)]*\d+\s*,\s*\d+", context):
        return True
    return bool(re.search(r"\b(?:vgl\.|ed\.|lex\.|p\.|pp\.)\b", context, re.IGNORECASE))


def has_sanskrit_candidate_context(row: dict[str, str], base_token: str, alternate_token: str) -> bool:
    context = " ".join(
        [
            row.get("reason", ""),
            row.get("base_line", ""),
            row.get("alternate_line", ""),
            base_token,
            alternate_token,
        ]
    )
    return bool(SANSKRIT_CONTEXT_CUE_RE.search(context) or looks_like_sanskrit_or_indic(base_token, alternate_token, context))


def google_sanskrit_candidate_reject_reason(base_token: str, alternate_token: str, row: dict[str, str]) -> str:
    context = " ".join([row.get("base_line", ""), row.get("alternate_line", "")])
    contextual_sanskrit = has_sanskrit_candidate_context(row, base_token, alternate_token)
    if ROMAN_NUMERAL_TOKEN_RE.match(base_token) or ROMAN_NUMERAL_TOKEN_RE.match(alternate_token):
        return "Roman numeral or section marker"
    if looks_like_bibliographic_name_noise(base_token, alternate_token):
        return "bibliographic name or all-caps siglum"
    if TIBETAN_WYLIE_APOSTROPHE_RE.match(base_token) or TIBETAN_WYLIE_APOSTROPHE_RE.match(alternate_token):
        return "Tibetan/Wylie apostrophe token"
    if looks_like_tibetan_wylie_candidate(base_token, alternate_token):
        return "Tibetan/Wylie token pattern"
    if looks_like_citation_or_siglum(base_token, row.get("reason", ""), context) and not contextual_sanskrit:
        return "citation or siglum context"
    if looks_like_german_or_prose(base_token, row.get("reason", ""), context) and not contextual_sanskrit:
        return "German/prose token"
    return ""


def looks_like_google_sanskrit_candidate_noise(base_token: str, alternate_token: str, row: dict[str, str]) -> bool:
    return bool(google_sanskrit_candidate_reject_reason(base_token, alternate_token, row))


def google_sanskrit_candidate_reading_row(
    volume: str,
    source_file: Path,
    row: dict[str, str],
    corrected_text: str = "",
) -> dict[str, str] | None:
    base_token = normalize_report_token(row.get("base_token", ""))
    alternate_token = normalize_report_token(row.get("alternate_token", ""))
    if not base_token or not alternate_token or base_token == alternate_token:
        return None
    if corrected_text and corrected_line_resolves_google_candidate(corrected_text, row):
        return None

    keys_compatible, key_evidence = google_sanskrit_keys_compatible(row, base_token, alternate_token)
    if not keys_compatible:
        return None

    alternate_has_diacritic = token_has_sanskrit_diacritic(alternate_token)
    base_has_degradation = token_has_sanskrit_degradation(base_token)
    repairs_damage = alternate_repairs_sanskrit_damage(base_token, alternate_token)
    context_cue = has_sanskrit_candidate_context(row, base_token, alternate_token)
    alternate_quality = sanskrit_token_quality(alternate_token)
    base_quality = sanskrit_token_quality(base_token)
    if not (alternate_has_diacritic or repairs_damage):
        return None
    if alternate_quality <= base_quality:
        return None
    if not (context_cue or base_has_degradation):
        return None

    score = 0
    explanation: list[str] = []
    score += 2
    explanation.append(key_evidence)
    if alternate_has_diacritic:
        score += 3
        explanation.append("alternate has Sanskrit diacritics")
    if alternate_quality > base_quality:
        score += 2
        explanation.append(f"alternate quality {alternate_quality} > base quality {base_quality}")
    if context_cue:
        score += 2
        explanation.append("Sanskrit/title/bibliographic context cue")
    if base_has_degradation:
        score += 1
        explanation.append("base has likely OCR degradation")
    if "jn" in base_token.lower() and "jñ" in alternate_token.lower():
        score += 2
        explanation.append("alternate repairs jn to jñ")
    if repairs_damage:
        score += 1
        explanation.append("alternate repairs Sanskrit-like OCR damage")

    reject_reason = google_sanskrit_candidate_reject_reason(base_token, alternate_token, row)
    clear_sanskrit_token = token_has_sanskrit_candidate_hint(base_token) or token_has_sanskrit_candidate_hint(alternate_token)
    short_bib_abbrev = looks_like_short_bibliographic_abbreviation(
        base_token, row
    ) or looks_like_short_bibliographic_abbreviation(alternate_token, row)
    if reject_reason:
        suggested_action = "reject"
        explanation.append(f"rejected: {reject_reason}")
    elif short_bib_abbrev:
        suggested_action = "review_only"
        explanation.append("short bibliographic abbreviation needs source review")
    elif score >= 8 and context_cue and clear_sanskrit_token:
        suggested_action = "exact_promotion_candidate"
    else:
        suggested_action = "review_only"
    return {
        "volume": volume,
        "source_file": str(source_file),
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "token_index": row.get("token_index", ""),
        "base_token": row.get("base_token", ""),
        "alternate_token": row.get("alternate_token", ""),
        "base_key": row.get("base_key", ""),
        "alternate_key": row.get("alternate_key", ""),
        "reason": row.get("reason", ""),
        "base_line": row.get("base_line", ""),
        "alternate_line": row.get("alternate_line", ""),
        "alignment_method": row.get("alignment_method", ""),
        "candidate_score": str(score),
        "score_explanation": "; ".join(explanation),
        "suggested_action": suggested_action,
    }


def possible_missed_google_reading_row(
    volume: str,
    source_file: Path,
    row: dict[str, str],
    corrected_text: str = "",
) -> dict[str, str] | None:
    candidate = google_sanskrit_candidate_reading_row(volume, source_file, row, corrected_text)
    if candidate is None or candidate.get("suggested_action") != "exact_promotion_candidate":
        return None
    return google_review_row(
        volume,
        source_file,
        row,
        "possible_missed_good_reading",
        candidate["score_explanation"],
    )


def load_sanskrit_override_source_tokens(path: Path = Path("data/sanskrit_promote_overrides.tsv")) -> set[str]:
    if not path.exists():
        return set()
    tokens: set[str] = set()
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            source_token = normalize_report_token(row.get("from_token", ""))
            if source_token:
                tokens.add(source_token)
    return tokens


def residual_candidate_family(token: str) -> str:
    token_l = normalize_report_token(token).lower()
    if "praj" in token_l or "pāram" in token_l or "päram" in token_l:
        return "Prajñā / Prajñāpāramitā"
    if "jn" in token_l or "jñ" in token_l or "samjn" in token_l or "saṃjñ" in token_l:
        return "jñāna / sarvajñatā / vijñāna"
    if "srav" in token_l or "śrav" in token_l or "śrāv" in token_l:
        return "śrāvaka / śrāva"
    if any(fragment in token_l for fragment in ("näg", "nāg", "mār", "mär", "dharm", "kīrti", "taks", "takṣ")):
        return "Sanskrit proper names and titles"
    if RESIDUAL_SUTRA_DAMAGE_RE.search(token_l) or "sūtra" in token_l or "sutra" in token_l:
        return "sūtra title families"
    if RESIDUAL_FINAL_VISARGA_RE.search(token):
        return "final-visarga Sanskrit terms"
    if "mah" in token_l or "ratnak" in token_l or "ārya" in token_l or "arya" in token_l:
        return "Mahā- / Ārya title families"
    if any(fragment in token_l for fragment in ("bala", "dhātu", "dhatu", "skandha", "marga", "märga", "mārga")):
        return "Buddhist technical compounds"
    return "Sanskrit-like residual damage"


def residual_candidate_has_strong_context(line: str, token: str) -> bool:
    if RESIDUAL_STRONG_SANSKRIT_CONTEXT_RE.search(line or ""):
        return True
    if SANSKRIT_CONTEXT_CUE_RE.search(line or ""):
        return True
    if token_has_sanskrit_candidate_hint(token):
        return True
    return False


def residual_token_has_damage(token: str) -> bool:
    token_s = normalize_report_token(token)
    if not token_s:
        return False
    if any(char in token_s for char in ("ä", "Ä", "ı", "$")):
        return True
    if RESIDUAL_JN_DAMAGE_RE.search(token_s):
        return True
    if RESIDUAL_FINAL_VISARGA_RE.search(token_s):
        return True
    return bool(RESIDUAL_SUTRA_DAMAGE_RE.search(token_s))


def residual_candidate_evidence(
    token: str,
    review_tokens: set[str],
    google_tokens: set[str],
    override_tokens: set[str],
    strong_context: bool,
) -> str:
    evidence: list[str] = []
    if token in google_tokens:
        evidence.append("google")
    if token in review_tokens:
        evidence.append("review_queue")
    if token in override_tokens:
        evidence.append("existing_override_family")
    if token in RESIDUAL_PROMOTE_TOKEN_TARGETS or token in RESIDUAL_REVIEW_TOKEN_TARGETS or strong_context:
        evidence.append("language_knowledge")
    return " / ".join(evidence) if evidence else "unknown"


def residual_candidate_suggested_action(token: str, confidence: str) -> str:
    if token in RESIDUAL_PROMOTE_TOKEN_TARGETS:
        return "promote"
    if confidence in {"high", "medium"}:
        return "review"
    return "reject"


def collect_residual_sanskrit_damage_candidates(
    volume: str,
    source_file: Path,
    corrected_text: str,
    review_tokens: set[str],
    google_tokens: set[str],
    override_tokens: set[str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for page_index, page_text in enumerate((corrected_text or "").split("\f"), start=1):
        current_page = str(page_index)
        page_line = 0
        for raw_line in page_text.splitlines():
            marker = PAGE_MARKER_RE.match(raw_line)
            if marker:
                current_page = str(int(marker.group(1)))
                page_line = 0
                continue
            page_line += 1
            for piece in re.split(r"\s+", raw_line):
                token = normalize_report_token(piece)
                if not token:
                    continue
                exact_known = token in RESIDUAL_PROMOTE_TOKEN_TARGETS or token in RESIDUAL_REVIEW_TOKEN_TARGETS
                if not exact_known:
                    if ROMAN_NUMERAL_TOKEN_RE.fullmatch(token) or ALL_CAPS_SIGLUM_RE.fullmatch(token):
                        continue
                    if TIBETAN_WYLIE_APOSTROPHE_RE.fullmatch(token):
                        continue
                    if looks_like_german_or_prose(token, "", raw_line) and not residual_candidate_has_strong_context(raw_line, token):
                        continue
                    if not residual_token_has_damage(token):
                        continue
                strong_context = residual_candidate_has_strong_context(raw_line, token)
                if not exact_known and not strong_context:
                    continue
                key = (current_page, str(page_line), token)
                if key in seen:
                    continue
                seen.add(key)
                proposed_target = RESIDUAL_PROMOTE_TOKEN_TARGETS.get(token) or RESIDUAL_REVIEW_TOKEN_TARGETS.get(token, "")
                evidence = residual_candidate_evidence(token, review_tokens, google_tokens, override_tokens, strong_context)
                if token in RESIDUAL_PROMOTE_TOKEN_TARGETS:
                    confidence = "high"
                elif token in RESIDUAL_REVIEW_TOKEN_TARGETS:
                    confidence = "medium"
                elif strong_context and evidence != "unknown":
                    confidence = "medium"
                else:
                    confidence = "low"
                rows.append(
                    {
                        "volume": volume,
                        "source_file": str(source_file),
                        "page": current_page,
                        "line": str(page_line),
                        "token": token,
                        "candidate_family": residual_candidate_family(token),
                        "proposed_target": proposed_target,
                        "context_excerpt": truncate(raw_line, 180),
                        "evidence": evidence,
                        "confidence": confidence,
                        "suggested_action": residual_candidate_suggested_action(token, confidence),
                    }
                )
    rows.sort(
        key=lambda row: (
            {"promote": 0, "review": 1, "reject": 2}.get(row.get("suggested_action", ""), 9),
            {"high": 0, "medium": 1, "low": 2}.get(row.get("confidence", ""), 9),
            row.get("candidate_family", ""),
            row.get("volume", ""),
            safe_int(row.get("page", "")),
            safe_int(row.get("line", "")),
            row.get("token", ""),
        )
    )
    return rows


def collect_suspicious_tokens(
    volume: str,
    validator_path: Path,
    validator_rows: list[dict[str, str]],
    review_path: Path,
    review_rows: list[dict[str, str]],
    corrected_text: str,
    changes: list[dict[str, str]],
    adoptions: list[dict[str, str]],
    unresolved: list[dict[str, str]],
    limit: int | None = None,
) -> list[dict[str, str]]:
    buckets: dict[tuple[str, str, str], dict[str, str]] = {}
    counts: Counter[tuple[str, str, str]] = Counter()
    corrected_tokens, corrected_page_tokens, corrected_line_tokens = corrected_scope_token_counters(corrected_text)
    applied_from_tokens = applied_from_token_counter(changes, adoptions)
    adoption_token_index = page_line_token_index(adoptions, ("base_token", "alternate_token"))
    unresolved_token_index = page_line_token_index(unresolved, ("base_token", "alternate_token"))
    withheld_review_index = withheld_review_token_index(review_rows)

    def add(source: str, token: str, reason: str, suggestion: str, row: dict[str, str], source_file: Path) -> None:
        token = token.strip()
        if not token:
            return
        key = (source, token, reason or "(blank)")
        counts[key] += 1
        buckets.setdefault(
            key,
            {
                "volume": volume,
                "source": source,
                "source_file": str(source_file),
                "token": token,
                "reason_or_issue": reason,
                "suggestion": suggestion,
                "sample_page": row.get("page", ""),
                "sample_line": row.get("line", ""),
                "sample_excerpt": row.get("line_excerpt", ""),
            },
        )

    for row in validator_rows:
        add("validator", row.get("token", ""), row.get("issue", ""), row.get("suggestion", ""), row, validator_path)
    for row in review_rows:
        add("review_queue_from", row.get("from_token", ""), row.get("reason", ""), row.get("to_token", ""), row, review_path)
        add("review_queue_to", row.get("to_token", ""), row.get("reason", ""), row.get("from_token", ""), row, review_path)

    out: list[dict[str, str]] = []
    for key, count in counts.items():
        item = dict(buckets[key])
        item["count"] = str(count)
        token = normalize_report_token(item["token"])
        scoped_count, scoped_scope = corrected_presence_for_row(
            item,
            token,
            corrected_tokens,
            corrected_page_tokens,
            corrected_line_tokens,
        )
        classification, evidence = classify_suspicious_token(
            item,
            scoped_count,
            scoped_scope,
            corrected_tokens[token],
            applied_from_tokens[token],
        )
        evidence_key = page_line_token_key(item, token)
        adoption_match = bool(evidence_key != ("", "", "") and evidence_key in adoption_token_index)
        unresolved_match = bool(evidence_key != ("", "", "") and evidence_key in unresolved_token_index)
        review_match = bool(evidence_key != ("", "", "") and evidence_key in withheld_review_index)
        item["classification"] = classification
        item["evidence"] = evidence
        item["evidence_scope"] = scoped_scope
        item["alternate_witness_adoption_match"] = yes_no(adoption_match)
        item["alternate_witness_unresolved_match"] = yes_no(unresolved_match)
        item["review_queue_withheld_match"] = yes_no(review_match)
        item["validator_only"] = yes_no(not adoption_match and not unresolved_match)
        item["corrected_text_exact_count"] = str(corrected_tokens[token])
        item["corrected_text_scoped_count"] = str(scoped_count)
        item["corrected_text_scope"] = scoped_scope
        item["applied_change_count"] = str(applied_from_tokens[token])
        if classification == "live_remaining":
            live_bucket, live_interpretation = live_row_bucket(item)
            item["live_evidence_bucket"] = live_bucket
            item["live_interpretation"] = live_interpretation
        else:
            item["live_evidence_bucket"] = ""
            item["live_interpretation"] = ""
        out.append(item)
    out = sort_suspicious_rows(out)
    return out if limit is None else out[:limit]


def page_attention_rows(
    volume: str,
    changes: list[dict[str, str]],
    reviews: list[dict[str, str]],
    validators: list[dict[str, str]],
    unresolved: list[dict[str, str]],
    limit: int = 50,
) -> list[dict[str, str]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for name, rows in [
        ("changes", changes),
        ("review_queue", reviews),
        ("validator_issues", validators),
        ("alternate_unresolved", unresolved),
    ]:
        for row in rows:
            page = row.get("page", "") or "(blank)"
            counts[page][name] += 1
    ranked = sorted(
        counts.items(),
        key=lambda kv: (-(kv[1]["changes"] + kv[1]["review_queue"] + kv[1]["validator_issues"] + kv[1]["alternate_unresolved"]), safe_int(kv[0])),
    )
    out: list[dict[str, str]] = []
    for page, c in ranked[:limit]:
        total = c["changes"] + c["review_queue"] + c["validator_issues"] + c["alternate_unresolved"]
        out.append(
            {
                "volume": volume,
                "page": page,
                "changes": str(c["changes"]),
                "review_queue": str(c["review_queue"]),
                "validator_issues": str(c["validator_issues"]),
                "alternate_unresolved": str(c["alternate_unresolved"]),
                "total_attention_rows": str(total),
            }
        )
    return out


def markdown_sample_rows(rows: list[dict[str, str]]) -> list[list[object]]:
    return [
        [
            row.get("page", ""),
            row.get("line", ""),
            truncate(row.get("reason", ""), 45),
            truncate(row.get("from_token", ""), 35),
            truncate(row.get("to_token", ""), 35),
            truncate(row.get("alignment_method", ""), 30),
            truncate(row.get("line_excerpt", ""), 90),
        ]
        for row in rows
    ]


def markdown_suspicious_rows(rows: list[dict[str, str]], limit: int = 50) -> list[list[object]]:
    return [
        [
            row.get("classification", ""),
            row.get("source", ""),
            truncate(row.get("token", ""), 30),
            truncate(row.get("reason_or_issue", ""), 45),
            row.get("count", ""),
            truncate(row.get("suggestion", ""), 30),
            truncate(row.get("evidence", ""), 80),
            row.get("sample_page", ""),
            row.get("sample_line", ""),
            truncate(row.get("sample_excerpt", ""), 80),
        ]
        for row in rows[:limit]
    ]


def markdown_live_suspicious_rows(rows: list[dict[str, str]], limit: int = 50) -> list[list[object]]:
    return [
        [
            row.get("live_evidence_bucket", ""),
            row.get("source", ""),
            truncate(row.get("token", ""), 30),
            truncate(row.get("reason_or_issue", ""), 45),
            row.get("count", ""),
            truncate(row.get("suggestion", ""), 30),
            row.get("evidence_scope", ""),
            row.get("alternate_witness_adoption_match", ""),
            row.get("alternate_witness_unresolved_match", ""),
            row.get("review_queue_withheld_match", ""),
            row.get("validator_only", ""),
            truncate(row.get("live_interpretation", ""), 90),
            row.get("sample_page", ""),
            row.get("sample_line", ""),
            truncate(row.get("sample_excerpt", ""), 80),
        ]
        for row in rows[:limit]
    ]


def run(output_dir: Path, sample_size: int, seed: int, manifest_path: Path = MANIFEST_PATH) -> None:
    volumes = load_volume_manifest(manifest_path)
    ready_volumes, warnings = select_ready_volumes(volumes)
    if not ready_volumes:
        raise ValueError(f"No ready production volumes found in {manifest_path}")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    rng = random.Random(seed)
    final_dir = output_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    all_change_samples: list[dict[str, str]] = []
    all_review_samples: list[dict[str, str]] = []
    all_adoption_samples: list[dict[str, str]] = []
    all_suspicious: list[dict[str, str]] = []
    all_pages_attention: list[dict[str, str]] = []
    all_watchdog_rows: list[dict[str, str]] = []
    all_sanskrit_review_rows: list[dict[str, str]] = []
    all_low_google_adoptions: list[dict[str, str]] = []
    all_possible_missed_google_rows: list[dict[str, str]] = []
    all_google_sanskrit_candidate_rows: list[dict[str, str]] = []
    all_residual_sanskrit_damage_rows: list[dict[str, str]] = []
    override_tokens = load_sanskrit_override_source_tokens()
    report: list[str] = [
        "# Production Release-Candidate OCR QA Report",
        "",
        f"Output directory: `{output_dir}`",
        f"Volume manifest: `{manifest_path}`",
        f"Sample seed: `{seed}`",
        "",
        "## Volume Coverage",
        "",
    ]
    report.extend(
        md_table(
            [
                "volume",
                "status",
                "included",
                "source_pdf",
                "merged",
                "audit",
                "google_vision",
                "note",
            ],
            volume_coverage_rows(volumes, {spec.label for spec in ready_volumes}),
        )
    )
    report.append("")
    checksums: list[tuple[str, str]] = []

    for spec in ready_volumes:
        volume_dir = output_dir / spec.label
        corrected = volume_dir / f"{spec.label}_corrected_full.txt"
        final_text = final_dir / spec.final_name
        if not corrected.exists():
            raise FileNotFoundError(f"missing corrected text: {corrected}")
        corrected_text = corrected.read_text(encoding="utf-8", errors="replace")
        shutil.copy2(corrected, final_text)
        checksum = sha256_file(final_text)
        checksums.append((checksum, final_text.name))

        summary_path = volume_dir / f"{spec.label}_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8", errors="replace"))
        changes_path = volume_dir / f"{spec.label}_changes.tsv"
        review_path = volume_dir / f"{spec.label}_review_queue.tsv"
        validator_path = volume_dir / f"{spec.label}_validator_issues.tsv"
        adoptions_path = volume_dir / f"{spec.label}_alternate_witness_adoptions.tsv"
        unresolved_path = volume_dir / f"{spec.label}_alternate_witness_unresolved.tsv"
        watchdog_path = volume_dir / f"{spec.label}_watchdog_flags.tsv"
        changes = read_tsv(changes_path)
        reviews = read_tsv(review_path)
        validators = read_tsv(validator_path)
        adoptions = read_tsv(adoptions_path)
        unresolved = read_tsv(unresolved_path)
        watchdogs = read_tsv(watchdog_path)
        sanskrit_reviews = [row for row in reviews if is_sanskrit_review_suggestion(row)]

        change_samples = [
            sample_change_row(spec.display, changes_path, row)
            for row in stratified_sample(changes, "reason", sample_size, rng)
        ]
        review_samples = [
            sample_change_row(spec.display, review_path, row)
            for row in stratified_sample(reviews, "reason", sample_size, rng)
        ]
        adoption_samples = [
            sample_adoption_row(spec.display, adoptions_path, row)
            for row in stratified_sample(adoptions, "reason", sample_size, rng)
        ]
        watchdog_rows = [watchdog_review_row(spec.display, watchdog_path, row) for row in watchdogs]
        sanskrit_review_rows = [sanskrit_review_row(spec.display, review_path, row) for row in sanskrit_reviews]
        low_google_adoptions = [
            row
            for row in (low_confidence_google_adoption_row(spec.display, adoptions_path, source) for source in adoptions)
            if row is not None
        ]
        possible_missed_google_rows = [
            row
            for row in (
                possible_missed_google_reading_row(spec.display, unresolved_path, source, corrected_text)
                for source in unresolved
            )
            if row is not None
        ]
        google_sanskrit_candidate_rows = [
            row
            for row in (
                google_sanskrit_candidate_reading_row(spec.display, unresolved_path, source, corrected_text)
                for source in unresolved
            )
            if row is not None
        ]
        review_token_index = {normalize_report_token(row.get("from_token", "")) for row in sanskrit_reviews}
        review_token_index.update(normalize_report_token(row.get("to_token", "")) for row in sanskrit_reviews)
        review_token_index.discard("")
        google_token_index = {normalize_report_token(row.get("base_token", "")) for row in google_sanskrit_candidate_rows}
        google_token_index.update(normalize_report_token(row.get("alternate_token", "")) for row in google_sanskrit_candidate_rows)
        google_token_index.discard("")
        residual_sanskrit_damage_rows = collect_residual_sanskrit_damage_candidates(
            spec.display,
            corrected,
            corrected_text,
            review_token_index,
            google_token_index,
            override_tokens,
        )
        suspicious = collect_suspicious_tokens(
            spec.display,
            validator_path,
            validators,
            review_path,
            reviews,
            corrected_text,
            changes,
            adoptions,
            unresolved,
        )
        attention = page_attention_rows(spec.display, changes, reviews, validators, unresolved)
        all_change_samples.extend(change_samples)
        all_review_samples.extend(review_samples)
        all_adoption_samples.extend(adoption_samples)
        all_suspicious.extend(suspicious)
        all_pages_attention.extend(attention)
        all_watchdog_rows.extend(watchdog_rows)
        all_sanskrit_review_rows.extend(sanskrit_review_rows)
        all_low_google_adoptions.extend(low_google_adoptions)
        all_possible_missed_google_rows.extend(possible_missed_google_rows)
        all_google_sanskrit_candidate_rows.extend(google_sanskrit_candidate_rows)
        all_residual_sanskrit_damage_rows.extend(residual_sanskrit_damage_rows)

        report.extend(
            [
                f"## {spec.display}",
                "",
                "### Inputs",
                "",
                f"- Source PDF: `{spec.source_pdf}`",
                f"- Base merged: `{spec.merged}`",
                f"- Audit CSV: `{spec.audit}`",
                f"- Google alternate witness: `{spec.google_vision}`",
                "",
                "### Output Summary",
                "",
            ]
        )
        report.extend(
            md_table(
                ["metric", "value"],
                [
                    ["corrected_full", str(corrected)],
                    ["release_candidate", str(final_text)],
                    ["sha256", checksum],
                    ["pages", summary.get("pages", "")],
                    ["total_lines_seen", summary.get("total_lines_seen", "")],
                    ["non_empty_lines", summary.get("non_empty_lines", "")],
                    ["entries_detected", summary.get("entries_detected", "")],
                    ["alternate_witness_adoptions", len(adoptions)],
                    ["alternate_witness_unresolved", len(unresolved)],
                    ["watchdog_rows", len(watchdogs)],
                    ["sanskrit_review_suggestions", len(sanskrit_reviews)],
                    ["low_confidence_google_adoptions", len(low_google_adoptions)],
                    ["possible_missed_google_readings", len(possible_missed_google_rows)],
                    ["google_sanskrit_candidate_readings", len(google_sanskrit_candidate_rows)],
                    ["residual_sanskrit_damage_candidates", len(residual_sanskrit_damage_rows)],
                ],
            )
        )
        report.extend(["", "### Postprocess Changes By Reason", ""])
        report.extend(md_table(["reason", "count"], reason_table(count_by(changes, "reason"))))
        report.extend(["", "### Review Queue By Reason", ""])
        report.extend(md_table(["reason", "count"], reason_table(count_by(reviews, "reason"))))
        report.extend(["", "### Google Alternate-Witness Adoptions By Reason", ""])
        report.extend(md_table(["reason", "count"], reason_table(count_by(adoptions, "reason"))))
        report.extend(["", "### Google Alternate-Witness Adoptions By Alignment Method", ""])
        report.extend(md_table(["alignment_method", "count"], reason_table(count_by(adoptions, "alignment_method"))))
        report.extend(["", "### Unresolved Alternate-Witness Rows By Reason", ""])
        report.extend(md_table(["reason", "count"], reason_table(count_by(unresolved, "reason"))))
        report.extend(["", "### Suspicious Token Classification", ""])
        report.extend(
            md_table(
                ["classification", "rows", "occurrences"],
                [
                    [row["classification"], row["rows"], row["occurrences"]]
                    for row in suspicious_summary_rows(suspicious)
                ],
            )
        )
        live_suspicious = [row for row in suspicious if row.get("classification") == "live_remaining"]
        manual_suspicious = [row for row in suspicious if row.get("classification") == "manual_review_only"]
        sanskrit_suspicious = [row for row in suspicious if row.get("classification") == "sanskrit_or_indic_policy_case"]
        citation_suspicious = [row for row in suspicious if row.get("classification") == "citation_or_siglum"]
        german_suspicious = [row for row in suspicious if row.get("classification") == "german_or_prose_false_positive"]
        stale_suspicious = [row for row in suspicious if row.get("classification") == "already_corrected_or_stale"]
        live_bucket_counts = Counter(row.get("live_evidence_bucket", "") for row in live_suspicious)
        report.extend(["", "### Manual Review Buckets", ""])
        report.extend(
            md_table(
                ["bucket", "rows"],
                [
                    ["watchdog_rows", len(watchdog_rows)],
                    ["sanskrit_review_suggestions", len(sanskrit_review_rows)],
                    ["low_confidence_google_adoptions", len(low_google_adoptions)],
                    ["possible_missed_google_readings", len(possible_missed_google_rows)],
                    ["google_sanskrit_candidate_readings", len(google_sanskrit_candidate_rows)],
                    ["residual_sanskrit_damage_candidates", len(residual_sanskrit_damage_rows)],
                ],
            )
        )
        if google_sanskrit_candidate_rows:
            report.extend(["", "### Top Google-Supported Sanskrit Candidate Readings", ""])
            report.extend(
                md_table(
                    [
                        "action",
                        "score",
                        "page",
                        "line",
                        "base",
                        "alternate",
                        "score explanation",
                    ],
                    [
                        [
                            row.get("suggested_action", ""),
                            row.get("candidate_score", ""),
                            row.get("page", ""),
                            row.get("line", ""),
                            truncate(row.get("base_token", ""), 28),
                            truncate(row.get("alternate_token", ""), 28),
                            truncate(row.get("score_explanation", ""), 90),
                        ]
                        for row in sorted(
                            google_sanskrit_candidate_rows,
                            key=lambda item: -safe_int(item.get("candidate_score", "0")),
                        )[:10]
                    ],
                )
            )
        if residual_sanskrit_damage_rows:
            report.extend(["", "### Top Residual Sanskrit Damage Candidates", ""])
            report.extend(
                md_table(
                    [
                        "action",
                        "confidence",
                        "family",
                        "page",
                        "line",
                        "token",
                        "proposed",
                        "evidence",
                        "context",
                    ],
                    [
                        [
                            row.get("suggested_action", ""),
                            row.get("confidence", ""),
                            row.get("candidate_family", ""),
                            row.get("page", ""),
                            row.get("line", ""),
                            truncate(row.get("token", ""), 28),
                            truncate(row.get("proposed_target", ""), 28),
                            row.get("evidence", ""),
                            truncate(row.get("context_excerpt", ""), 90),
                        ]
                        for row in sorted(
                            residual_sanskrit_damage_rows,
                            key=lambda item: (
                                item.get("suggested_action") != "promote",
                                item.get("confidence") != "high",
                                item.get("candidate_family", ""),
                                safe_int(item.get("page", "")),
                                safe_int(item.get("line", "")),
                                item.get("token", ""),
                            ),
                        )[:10]
                    ],
                )
            )
        report.extend(["", "### Live Remaining Evidence Buckets", ""])
        report.extend(
            md_table(
                ["bucket", "rows"],
                [
                    [bucket, live_bucket_counts.get(bucket, 0)]
                    for bucket, _filename in LIVE_BUCKET_OUTPUTS
                ],
            )
        )
        report.extend(
            [
                "",
                "### Top 20 Live Remaining Validator Candidates",
                "",
                LIVE_HEURISTIC_WARNING,
                "",
                LIVE_VALIDATOR_ONLY_NOTE,
                "",
            ]
        )
        report.extend(
            md_table(
                [
                    "bucket",
                    "source",
                    "token",
                    "reason_or_issue",
                    "count",
                    "heuristic_suggestion",
                    "evidence_scope",
                    "alternate_witness_adoption_match",
                    "alternate_witness_unresolved_match",
                    "review_queue_withheld_match",
                    "validator_only",
                    "interpretation",
                    "sample_page",
                    "sample_line",
                    "sample_excerpt",
                ],
                markdown_live_suspicious_rows(live_suspicious, limit=20),
            )
        )
        report.extend(["", "### Top Manual-Review-Only Suspicious Tokens", ""])
        report.extend(
            md_table(
                SUSPICIOUS_MARKDOWN_HEADERS,
                markdown_suspicious_rows(manual_suspicious, limit=20),
            )
        )
        report.extend(["", "### Top Sanskrit/Indic Policy Suspicious Tokens", ""])
        report.extend(
            md_table(
                SUSPICIOUS_MARKDOWN_HEADERS,
                markdown_suspicious_rows(sanskrit_suspicious, limit=20),
            )
        )
        report.extend(["", "### Top Citation/Siglum Suspicious Tokens", ""])
        report.extend(
            md_table(
                SUSPICIOUS_MARKDOWN_HEADERS,
                markdown_suspicious_rows(citation_suspicious, limit=20),
            )
        )
        report.extend(["", "### Top German/Prose Validator False Positives", ""])
        report.extend(
            md_table(
                SUSPICIOUS_MARKDOWN_HEADERS,
                markdown_suspicious_rows(german_suspicious, limit=20),
            )
        )
        report.extend(["", "### Top Stale Or Already-Corrected Suspicious Tokens", ""])
        report.extend(
            md_table(
                SUSPICIOUS_MARKDOWN_HEADERS,
                markdown_suspicious_rows(stale_suspicious, limit=20),
            )
        )
        report.extend(["", "### Top Pages By Number Of Changes", ""])
        report.extend(md_table(["page", "changes"], top_by_page(changes)))
        report.extend(["", "### Top Pages By Unresolved Alternate-Witness Rows", ""])
        report.extend(md_table(["page", "unresolved_rows"], top_by_page(unresolved)))
        report.extend(["", f"### Random Sample Of {min(sample_size, len(change_samples))} Changes", ""])
        report.extend(md_table(["page", "line", "reason", "from", "to", "alignment", "excerpt"], markdown_sample_rows(change_samples)))
        report.extend(["", f"### Random Sample Of {min(sample_size, len(review_samples))} Review-Queue Items", ""])
        report.extend(md_table(["page", "line", "reason", "from", "to", "alignment", "excerpt"], markdown_sample_rows(review_samples)))
        report.extend(["", f"### Random Sample Of {min(sample_size, len(adoption_samples))} Google Adoptions", ""])
        report.extend(md_table(["page", "line", "reason", "from", "to", "alignment", "excerpt"], markdown_sample_rows(adoption_samples)))
        report.extend(
            [
                "",
                "### Short Risk Assessment",
                "",
                f"- Highest validator issue: `{count_by(validators, 'issue').most_common(1)[0][0] if validators else 'none'}`.",
                f"- Highest review-queue reason: `{count_by(reviews, 'reason').most_common(1)[0][0] if reviews else 'none'}`.",
                f"- Highest unresolved alternate-witness reason: `{count_by(unresolved, 'reason').most_common(1)[0][0] if unresolved else 'none'}`.",
                "- Google witness adoptions remain token-gated; raw Google line replacement is not used.",
                "",
            ]
        )

    checksum_path = final_dir / "SHA256SUMS.txt"
    checksum_path.write_text(
        "".join(f"{checksum}  {name}\n" for checksum, name in checksums),
        encoding="utf-8",
    )

    manual_fields = [
        "volume",
        "source_file",
        "page",
        "line",
        "reason",
        "from_token",
        "to_token",
        "line_excerpt",
        "zone",
        "tier",
        "alignment_method",
        "alternate_page",
    ]
    write_tsv(output_dir / "sample_changes_for_manual_review.tsv", all_change_samples, manual_fields)
    write_tsv(output_dir / "sample_review_queue_for_manual_review.tsv", all_review_samples, manual_fields)
    write_tsv(output_dir / "sample_google_adoptions_for_manual_review.tsv", all_adoption_samples, manual_fields)
    suspicious_fields = [
        "volume",
        "source",
        "source_file",
        "token",
        "reason_or_issue",
        "count",
        "suggestion",
        "classification",
        "evidence",
        "evidence_scope",
        "alternate_witness_adoption_match",
        "alternate_witness_unresolved_match",
        "review_queue_withheld_match",
        "validator_only",
        "live_evidence_bucket",
        "live_interpretation",
        "sample_page",
        "sample_line",
        "sample_excerpt",
        "corrected_text_exact_count",
        "corrected_text_scoped_count",
        "corrected_text_scope",
        "applied_change_count",
    ]
    write_tsv(
        output_dir / "top_suspicious_tokens.tsv",
        all_suspicious,
        suspicious_fields,
    )
    write_tsv(
        output_dir / "live_remaining_suspicious_tokens.tsv",
        [row for row in all_suspicious if row.get("classification") == "live_remaining"],
        suspicious_fields,
    )
    live_rows = [row for row in all_suspicious if row.get("classification") == "live_remaining"]
    for bucket, filename in LIVE_BUCKET_OUTPUTS:
        write_tsv(
            output_dir / filename,
            [row for row in live_rows if row.get("live_evidence_bucket") == bucket],
            suspicious_fields,
        )
    write_tsv(output_dir / "residual_real_suspicious_tokens.tsv", [], suspicious_fields)
    write_tsv(
        output_dir / "stale_or_already_corrected_suspicious_tokens.tsv",
        [row for row in all_suspicious if row.get("classification") == "already_corrected_or_stale"],
        suspicious_fields,
    )
    write_tsv(
        output_dir / "german_false_positive_validator_tokens.tsv",
        [row for row in all_suspicious if row.get("classification") == "german_or_prose_false_positive"],
        suspicious_fields,
    )
    write_tsv(
        output_dir / "manual_review_only_suspicious_tokens.tsv",
        [row for row in all_suspicious if row.get("classification") == "manual_review_only"],
        suspicious_fields,
    )
    write_tsv(
        output_dir / "sanskrit_or_indic_policy_suspicious_tokens.tsv",
        [row for row in all_suspicious if row.get("classification") == "sanskrit_or_indic_policy_case"],
        suspicious_fields,
    )
    write_tsv(
        output_dir / "citation_or_siglum_suspicious_tokens.tsv",
        [row for row in all_suspicious if row.get("classification") == "citation_or_siglum"],
        suspicious_fields,
    )
    write_tsv(
        output_dir / "suspicious_token_classification_summary.tsv",
        [
            row
            for volume in sorted({row.get("volume", "") for row in all_suspicious})
            for row in suspicious_summary_rows(
                [item for item in all_suspicious if item.get("volume", "") == volume],
                volume,
            )
        ],
        [
            "volume",
            "classification",
            "rows",
            "occurrences",
        ],
    )
    write_tsv(
        output_dir / "pages_with_many_changes.tsv",
        all_pages_attention,
        [
            "volume",
            "page",
            "changes",
            "review_queue",
            "validator_issues",
            "alternate_unresolved",
            "total_attention_rows",
        ],
    )
    watchdog_fields = [
        "volume",
        "source_file",
        "page",
        "line",
        "entry_id",
        "zone",
        "from_token",
        "to_token",
        "tier",
        "reason",
        "watchdog_flags",
        "line_excerpt",
    ]
    write_tsv(output_dir / "all_watchdog_rows.tsv", all_watchdog_rows, watchdog_fields)
    sanskrit_fields = [
        "volume",
        "source_file",
        "family_key",
        "page",
        "line",
        "entry_id",
        "zone",
        "from_token",
        "to_token",
        "tier",
        "reason",
        "applied",
        "line_excerpt",
    ]
    all_sanskrit_review_rows.sort(
        key=lambda row: (
            row.get("family_key", ""),
            row.get("volume", ""),
            safe_int(row.get("page", "")),
            safe_int(row.get("line", "")),
            row.get("from_token", ""),
        )
    )
    write_tsv(output_dir / "all_sanskrit_review_suggestions.tsv", all_sanskrit_review_rows, sanskrit_fields)
    google_review_fields = [
        "volume",
        "source_file",
        "bucket",
        "evidence",
        "page",
        "line",
        "token_index",
        "base_token",
        "alternate_token",
        "reason",
        "base_key",
        "alternate_key",
        "alignment_method",
        "alternate_page",
        "page_match_score",
        "canonical_overlap",
        "base_line",
        "alternate_line",
    ]
    write_tsv(output_dir / "low_confidence_google_adoptions.tsv", all_low_google_adoptions, google_review_fields)
    write_tsv(output_dir / "possible_missed_google_readings.tsv", all_possible_missed_google_rows, google_review_fields)
    google_sanskrit_candidate_fields = [
        "volume",
        "source_file",
        "page",
        "line",
        "token_index",
        "base_token",
        "alternate_token",
        "base_key",
        "alternate_key",
        "reason",
        "base_line",
        "alternate_line",
        "alignment_method",
        "candidate_score",
        "score_explanation",
        "suggested_action",
    ]
    all_google_sanskrit_candidate_rows.sort(
        key=lambda row: (
            -(safe_int(row.get("candidate_score", "0"))),
            row.get("suggested_action", ""),
            row.get("volume", ""),
            safe_int(row.get("page", "")),
            safe_int(row.get("line", "")),
            row.get("base_token", ""),
        )
    )
    write_tsv(
        output_dir / "google_sanskrit_candidate_readings.tsv",
        all_google_sanskrit_candidate_rows,
        google_sanskrit_candidate_fields,
    )
    all_residual_sanskrit_damage_rows.sort(
        key=lambda row: (
            row.get("suggested_action") != "promote",
            row.get("confidence") != "high",
            row.get("candidate_family", ""),
            row.get("volume", ""),
            safe_int(row.get("page", "")),
            safe_int(row.get("line", "")),
            row.get("token", ""),
        )
    )
    write_tsv(
        output_dir / "residual_sanskrit_damage_candidates.tsv",
        all_residual_sanskrit_damage_rows,
        RESIDUAL_SANSKRIT_DAMAGE_FIELDS,
    )

    report.extend(
        [
            "## Manual Review Package",
            "",
            f"- `{output_dir / 'sample_changes_for_manual_review.tsv'}`",
            f"- `{output_dir / 'sample_review_queue_for_manual_review.tsv'}`",
            f"- `{output_dir / 'sample_google_adoptions_for_manual_review.tsv'}`",
            f"- `{output_dir / 'top_suspicious_tokens.tsv'}`",
            f"- `{output_dir / 'live_remaining_suspicious_tokens.tsv'}`",
            f"- `{output_dir / 'live_validator_only_residue.tsv'}`",
            f"- `{output_dir / 'live_review_queue_candidates.tsv'}`",
            f"- `{output_dir / 'live_google_supported_candidates.tsv'}`",
            f"- `{output_dir / 'live_policy_or_false_positive.tsv'}`",
            f"- `{output_dir / 'manual_review_only_suspicious_tokens.tsv'}`",
            f"- `{output_dir / 'sanskrit_or_indic_policy_suspicious_tokens.tsv'}`",
            f"- `{output_dir / 'citation_or_siglum_suspicious_tokens.tsv'}`",
            f"- `{output_dir / 'stale_or_already_corrected_suspicious_tokens.tsv'}`",
            f"- `{output_dir / 'german_false_positive_validator_tokens.tsv'}`",
            f"- `{output_dir / 'all_watchdog_rows.tsv'}`",
            f"- `{output_dir / 'all_sanskrit_review_suggestions.tsv'}`",
            f"- `{output_dir / 'low_confidence_google_adoptions.tsv'}`",
            f"- `{output_dir / 'possible_missed_google_readings.tsv'}`",
            f"- `{output_dir / 'google_sanskrit_candidate_readings.tsv'}`",
            f"- `{output_dir / 'residual_sanskrit_damage_candidates.tsv'}`",
            f"- `{output_dir / 'suspicious_token_classification_summary.tsv'}`",
            f"- `{output_dir / 'pages_with_many_changes.tsv'}`",
            "",
            "Warning: stale/already-corrected suspicious-token artifacts, German/prose false positives, and Sanskrit/Indic policy cases should not drive broad OCR correction rules.",
            "",
            "## Cross-Volume Top Risk Categories",
            "",
            "1. Live remaining suspicious-token rows are the only validator/review rows that still occur at their corrected-text page or line.",
            "2. The live suggestion field is heuristic validator/canonicalisation output, not OCR-witness evidence.",
            "3. Only Google-supported rows and clearly source-supported review-queue rows should be considered for OCR-rule promotion.",
            "4. Watchdog rows and Sanskrit review suggestions should be reviewed before promoting any family-specific rule.",
            "5. Low-confidence Google adoptions, possible missed good Google readings, and Google-supported Sanskrit candidates are reviewer-facing diagnostics, not a reason to loosen Google adoption.",
            "6. Stale/already-corrected rows, German/prose false positives, citations/sigla, and Sanskrit/Indic policy cases are separated from live OCR candidates.",
            "7. Any promoted text correction should remain exact, source-supported, and test-backed.",
            "",
        ]
    )
    (output_dir / "production_release_candidate_report.md").write_text("\n".join(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate production OCR QA report from postprocess outputs.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()
    run(args.output_dir, args.sample_size, args.seed, args.manifest)


if __name__ == "__main__":
    main()
