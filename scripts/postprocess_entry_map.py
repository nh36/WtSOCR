#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

TIB_RE = re.compile(r"[\u0F00-\u0FFF]")
TIB_PREFIX_RE = re.compile(r"^\s*([\u0F00-\u0FFF\u0F0B-\u0F14\s]+)")
LATIN_CHARS = (
    r"A-Za-z"
    r"\u0100\u0101\u012A\u012B\u016A\u016B\u1E5A\u1E5B\u1E5C\u1E5D\u1E36\u1E37\u1E38\u1E39"
    r"\u1E44\u1E45\u00D1\u00F1\u1E6C\u1E6D\u1E0C\u1E0D\u1E46\u1E47\u015A\u015B\u1E62\u1E63"
    r"\u1E24\u1E25\u1E42\u1E43\u1E40\u1E41\u0179\u017A\u00C4\u00D6\u00DC\u00E4\u00F6\u00FC"
    r"\u00DF\u0131\u015F\u015E\u0146\u0145\u00E3\u00C3"
)
OCR_CONFUSABLE_TOKEN_CHARS = r"\$"
TRANSLIT_CHARS = (
    r"A-Za-z"
    r"\u0100\u0101\u012A\u012B\u016A\u016B\u1E5A\u1E5B\u1E5C\u1E5D\u1E36\u1E37\u1E38\u1E39"
    r"\u1E44\u1E45\u00D1\u00F1\u1E6C\u1E6D\u1E0C\u1E0D\u1E46\u1E47\u015A\u015B\u1E62\u1E63"
    r"\u1E24\u1E25\u1E42\u1E43\u1E40\u1E41\u0179\u017A\u0131\u015F\u015E\u0146\u0145\u00E3\u00C3\$"
)
LATIN_TOKEN_RE = re.compile(
    rf"[{LATIN_CHARS}]+(?:[’'][{LATIN_CHARS}]*)*(?:-[{LATIN_CHARS}]+(?:[’'][{LATIN_CHARS}]*)*)*"
)
OCR_LATIN_TOKEN_RE = re.compile(
    rf"[{LATIN_CHARS}{OCR_CONFUSABLE_TOKEN_CHARS}]+"
    rf"(?:[’'][{LATIN_CHARS}{OCR_CONFUSABLE_TOKEN_CHARS}]*)*"
    rf"(?:-[{LATIN_CHARS}{OCR_CONFUSABLE_TOKEN_CHARS}]+"
    rf"(?:[’'][{LATIN_CHARS}{OCR_CONFUSABLE_TOKEN_CHARS}]*)*)*"
)
TRANSLIT_TOKEN_RE = re.compile(
    rf"[{TRANSLIT_CHARS}]+(?:[’'][{TRANSLIT_CHARS}]*)*(?:-[{TRANSLIT_CHARS}]+(?:[’'][{TRANSLIT_CHARS}]*)*)*$"
)
TRANSLIT_CUE_RE = re.compile(
    r"[\u0101\u012B\u016B\u1E5B\u1E5D\u1E37\u1E39\u1E45\u00F1\u1E6D\u1E0D\u1E47\u015B\u1E63\u1E25"
    r"\u1E43\u1E41\u2019']|(?:kh|tsh|ts|ph|th|dh|bh|dz|rdz|ng|ny|zh|sh|lh|rg|rk|rt|rd)",
    re.IGNORECASE,
)
TRANSLIT_DIACRITIC_RE = re.compile(
    r"[\u0101\u012B\u016B\u1E5B\u1E5D\u1E37\u1E39\u1E45\u1E6D\u1E0D\u1E47\u015B\u1E63\u1E25\u1E43\u1E41]"
)
STRONG_TRANSLIT_CLUSTER_RE = re.compile(r"(?:tsh|ts|ph|kh|dh|bh|dz|rdz|zh|sh|lh)", re.IGNORECASE)
BOUNDARY_TRANSLIT_CLUSTER_RE = re.compile(
    r"(?:^|[-'’])(?:tsh|ts|ph|kh|dh|bh|dz|rdz|zh|sh|lh|rg|rk|rt|rd)",
    re.IGNORECASE,
)
DISTINCTIVE_TIB_CLUSTER_RE = re.compile(
    r"(?:^|[-'’])(?:"
    r"bsk|bsg|bst|brg|brk|brt|brd|"
    r"dng|dby|dbr|dgr|dkr|dpy|dpr|"
    r"mth|mkh|mch|mny|"
    r"rgy|rts|rky|"
    r"sgr|sbr|sny|sng|"
    r"rdz|gzh|"
    r"zh|lh|ng|ny|"
    r"kh|ph|th|dz|"
    r"rg|rk|rt|rd|db|dg|bk|bt|bd|mk|mt|md"
    r")",
    re.IGNORECASE,
)
TIB_MEDIAL_Y_RE = re.compile(r"[bcdfghjklmnpqrstvwxyz]y", re.IGNORECASE)
VOWEL_PARTICLE_SUFFIX_RE = re.compile(r"^(.*[aeiouāīūöü])(?:['’])(i|o)$", re.IGNORECASE)
TIBETAN_APOSTROPHE_PARTICLE_RE = re.compile(
    r"^[a-zāīūöüṛṝḷḹṅñṭḍṇśṣḥṃṁ]+(?:['’])(?:i|o|am|aṃ|aṁ|ang|aṅ)$",
    re.IGNORECASE,
)
SANSKRIT_NYA_CLUSTER_RE = re.compile(r"ñ(?=(?:d?z|d?zh|c|ch|j|jh|ts|tsh|ś|ṣ|sh|zh))", re.IGNORECASE)
PALATAL_NYA_ONSET_RE = re.compile(r"ñ(?=[aāiīuūeéoöüy])", re.IGNORECASE)
TIBETAN_NYA_CLUSTER_RE = re.compile(r"(?<![a-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁ-])(?:g|m|s)ñ", re.IGNORECASE)
INITIAL_CONFUSABLE_I_RE = re.compile(r"^I(?:(?=[a-zA-Zāīūṛṝḷḹṅñṭḍṇśṣ])|(?=['’]))")
INITIAL_I_TRANSLIT_ONSET_RE = re.compile(
    r"^I(?:kh|khy|kr|gr|ph|phy|th|tsh|ts|dz|zh|sh|ch|ny|ng|k|g|c|j|t|d|p|b|m|r|s|h|y|w|l)",
    re.IGNORECASE,
)
NOISE_RE = re.compile(r"[\d@#%^&*_=/\\|~]")
GERMAN_UMLAUT_RE = re.compile(r"[\u00E4\u00F6\u00FC\u00C4\u00D6\u00DC\u00DF]")
ALL_CAPS_RE = re.compile(r"^[A-ZÄÖÜ]{2,}$")
ROMAN_NUMERAL_RE = re.compile(r"^(?=[ivxlcdmIVXLCDM]+$)[IVXLCDMivxlcdm]+$")
SPACE_RE = re.compile(r"\s+")
VOWEL_RE = re.compile(r"[aeiouāīūöü]", re.IGNORECASE)
DOLLAR_SACUTE_ARTIFACT_RE = re.compile(r"(?:sś|śz|śś|ṣś)", re.IGNORECASE)
CITATION_YEAR_RE = re.compile(r"\b(?:1[6-9]\d{2}|20\d{2})(?:[a-z])?\b", re.IGNORECASE)
CITATION_SPLIT_YEAR_RE = re.compile(r"\b(?:1[6-9]|20)\s{1,2}\d{2}(?:[a-z])?\b", re.IGNORECASE)
CITATION_CUE_RE = re.compile(
    r"\b(?:ed|hrsg|vgl|zit|zitiert|skt|vol|bd|pp|pl|repr|index|indices)\b\.?",
    re.IGNORECASE,
)
CITATION_SIGLUM_ARTIFACT_CUE_RE = re.compile(
    r"\((?:[^)\n]{0,32})(?<![A-Za-z])(?:L\$dz(?:-[A-Za-z$]*)?|L1\$|1\.\$dz|Vi\$s?T|Vis\$T|Li(?:\$|s\$)|Y\$|Ys\$)(?=[^A-Za-z$]|$)",
    re.IGNORECASE,
)
SANSKRIT_MVY_CUE_RE = re.compile(r"\(\s*Mvy\b", re.IGNORECASE)
SANSKRIT_GENERAL_CUE_RE = re.compile(r"\b(?:skt|sanskrit|mahavyutpatti|mvy)\b\.?", re.IGNORECASE)
CITATION_PAREN_RE = re.compile(r"\([^)\n]{0,120}\)")
CITATION_PAREN_HINT_RE = re.compile(
    r"(?:\b(?:ed|hrsg|vol|bd|pp|pl|nr|no)\b|(?:1[6-9]\d{2}|20\d{2})(?:[a-z])?|\b\d{1,3}\b)",
    re.IGNORECASE,
)
CITATION_PAREN_NAME_PAGE_RE = re.compile(r"\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]{2,}\s*,\s*\d{1,3}\b")
CITATION_SIGLUM_DIGIT_ARTIFACT_RE = re.compile(
    r"(\(\s*)(L1\$|1\.\$dz)(?=\s+\d{1,4}(?:[,:./]\d{1,4}|[a-z])?)",
    re.IGNORECASE,
)
INITIAL_I_CANON_SHAPE_RE = re.compile(
    r"^l(?:['’](?:h|t|n|d|k|g|c|j|p|b|m|r|s|z|y|w|kh|ph|th|ts|dz|zh|sh|ny|ng)"
    r"|(?:h|t|n|d|k|g|c|j|p|b|m|r|s|z|y|w|kh|ph|th|ts|dz|zh|sh|ny|ng))",
    re.IGNORECASE,
)
TIBETAN_NAME_PIECE_PREFIX_RE = re.compile(
    r"^(?:"
    r"bs|bz|bsk|bst|brg|brk|brt|brd|"
    r"dng|dby|dgr|dkr|dpy|dpr|"
    r"mth|mkh|mch|mny|mg|"
    r"rgy|rts|rky|"
    r"sgr|sbr|sny|sng|"
    r"rdz|gzh|"
    r"zh|lh|ng|ny|"
    r"rg|rk|rt|rd|db|dg|bk|bt|bd|mk|mt|md"
    r")",
    re.IGNORECASE,
)
GERMAN_LHR_PRONOUN_RE = re.compile(r"^lhr(?:e|en|em|es)?$", re.IGNORECASE)
GERMAN_IHR_PRONOUN_RE = re.compile(r"^ihr(?:e|en|em|er|es)?$", re.IGNORECASE)
SANSKRIT_DIACRITIC_RE = re.compile(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁĀĪŪṚṜḶḸṄÑṬḌṆŚṢḤṂṀ]")
SANSKRIT_CLUSTER_RE = re.compile(
    r"(?:jñ|kṣ|ṣṭ|ṣṇ|śr|tva|dva|dhy|bhy|mvy|arya|vams|samtu)",
    re.IGNORECASE,
)
SANSKRIT_TOKEN_NOISE_RE = re.compile(r"[\$äöüÄÖÜãÃıI]")
SANSKRIT_UMLAUT_RE = re.compile(r"[äöüÄÖÜ]")
SANSKRIT_UMLAUT_LONG_VOWEL_MAP = str.maketrans(
    {
        "ä": "ā",
        "Ä": "Ā",
        "ö": "o",
        "Ö": "O",
        "ü": "u",
        "Ü": "U",
    }
)
SANSKRIT_SAFE_CHAR_MAP = str.maketrans(
    {
        "$": "ś",
        "ä": "ā",
        "Ä": "Ā",
        "ö": "o",
        "Ö": "O",
        "ü": "u",
        "Ü": "U",
        "ã": "ā",
        "Ã": "Ā",
        "ı": "i",
    }
)
# Strong ASCII clusters that are useful Sanskrit evidence and low-risk in German prose.
SANSKRIT_ASCII_CLUSTER_STRONG_RE = re.compile(
    r"(?:jn|ksh|tva|dva|dhy|bhy|mvy|cch|ddh|dbh|jñ)",
    re.IGNORECASE,
)
SANSKRIT_ASCII_CLUSTER_RE = re.compile(
    r"(?:jn|ksh|tva|dva|dhy|bhy|mvy|vams|arya|samt|sva|atm|krt|smr|cch|ddh|dbh|rth|jñ)",
    re.IGNORECASE,
)
SANSKRIT_JN_VOWEL_CLUSTER_RE = re.compile(r"jn(?=[aāiīuūeoṛṝḷ])", re.IGNORECASE)
COMPOUND_SEGMENT_SPLIT_RE = re.compile(r"([/-])")
SANSKRIT_ENDING_RE = re.compile(
    r"(?:am|ah|ab|as|ena|anam|asya|tva|maya|kara|mukha|atma|artha|sutra|vati|vat|ika|aka|iya)$",
    re.IGNORECASE,
)
SANSKRIT_LEX_CUE_RE = re.compile(r"\bLex\.", re.IGNORECASE)
GANS_RI_RE = re.compile(r"\bGans\s+ri\b")
RASTRAPA_SPLIT_PREV_RE = re.compile(r"R[äa]strapa-\s*$", re.IGNORECASE)
LAPARIPRCCHA_SPLIT_CURR_RE = re.compile(
    r"\blapariprcch[äaā]n[äaā]mamah[äaā]y[äaā]nas[üuū]tra\b",
    re.IGNORECASE,
)
SANSKRIT_AUTO_CONTEXT_MIN = 4

ENTRY_STRONG_ZONES = {"headword_line", "example_tibetan_latin", "tibetan_latin_mixed"}
AUTO_FIX_ZONES = {
    "headword_line",
    "example_tibetan_latin",
    "tibetan_latin_mixed",
    "german_prose_with_translit",
    "latin_other",
}

DISCOVER_MIN_SOURCE_COUNT = 2
DISCOVER_MIN_SUGGESTED_COUNT = 12
DISCOVER_RATIO_MIN_HIGH = 4.0
DISCOVER_RATIO_MIN_MEDIUM = 5.5

HARD_GUARD_BLOCK_FLAGS = {
    "particle_suffix_drop",
    "particle_suffix_mismatch",
    "apostrophe_drop",
    "trailing_shortening",
    "protected_nya_to_nga",
    "case_destructive_shift",
}

# Explicit user-approved rewrites that are safe to auto-apply in auto-fix zones.
EXPLICIT_TIER_A_REWRITES = {
    "$es": "śes",
    "$es-rab": "śes-rab",
    "$in": "śiṅ",
    "g$egs": "gśegs",
    "yañ": "yaṅ",
    "dañ": "daṅ",
    "nañ": "naṅ",
    "gañ": "gaṅ",
    "oñs": "oṅs",
    "lañs": "laṅs",
    "gtsañ": "gtsaṅ",
    "khri-ide": "khri-lde",
    "pho-iha": "pho-lha",
    "dgra-iba-gottheit": "dgra-lba-gottheit",
    "dpal-idan": "dpal-ldan",
    "zium": "zlum",
    "lidan": "lldan",
    "phrulgyiiha": "phrulgyilha",
    "bye'u": "bye’u",
    "dga'": "dga’",
    "rde'u": "rde’u",
    "padma'i": "padma’i",
}

# Case-sensitive surgical rewrites promoted from review queue after manual audit.
# Keep this list small and explicit to avoid broad false positives.
EXPLICIT_CASE_SENSITIVE_TIER_A_REWRITES = {
    "bIsan-rgod": "bTsan-rgod",
    "mTIshur": "mTshur",
    "mTIshur-phu-Ausgabe": "mTshur-phu-Ausgabe",
    "mTIshur-’bar": "mTshur-’bar",
    "m’TIshur": "m’Tshur",
    "m'TIshur": "m'Tshur",
    "tajnab": "tajñab",
    "gZIgS": "gZigS",
}

# High-confidence OCR confusable forms where "$" should be acute-s.
DOLLAR_SACUTE_TIER_A_ALLOWLIST = {
    "$es",
    "$es-rab",
    "$in",
    "g$egs",
}

# High-frequency Sanskrit normalization pairs validated on current corpus review queues.
# These are safe to auto-apply even when local context score is below the Sanskrit
# auto-threshold, as long as the token is already classified probable Sanskrit.
SANSKRIT_HIGH_FREQ_TIER_A_OVERRIDES = {
    "$raddhä": "śraddhā",
    "$ridharasena": "śridharasena",
    "$rijnäna": "śrijnāna",
    "$rivatsa": "śrivatsa",
    "äjneya": "ājneya",
    "abhyäsa": "abhyāsa",
    "adhyätma": "adhyātma",
    "arthasästra": "arthasāstra",
    "ayodhyä": "ayodhyā",
    "bodhisattvacaryavatärasamskära": "bodhisattvacaryavatārasamskāra",
    "buddhädhyesanakusalah": "buddhādhyesanakusalah",
    "isvasträcäryah": "isvastrācāryah",
    "madhyamaka-präsangika": "madhyamaka-prāsangika",
    "pärasvadhikah": "pārasvadhikah",
    "prajnä": "prajnā",
    "samdhyäbhasa": "samdhyābhasa",
    "säarthavaha": "sāarthavaha",
    "täräbhyudayatantra": "tārābhyudayatantra",
    "upädhyäya": "upādhyāya",
    "$rävaka": "śrāvaka",
    "$rävakas": "śrāvakas",
    "sädhya": "sādhya",
    "madhyäntika": "madhyāntika",
    "sıddh": "siddh",
    "bodhicaryavatära": "bodhicaryavatāra",
    "mahäsattva": "mahāsattva",
    "mahäsattvas": "mahāsattvas",
    "siddhärtha": "siddhārtha",
    "vai$ravana": "vaiśravana",
    "vai$ravanas": "vaiśravanas",
}


def load_sanskrit_promoted_overrides(path: Path) -> dict[str, str]:
    """Load promoted rare-pair Sanskrit overrides from a TSV file if present."""
    overrides: dict[str, str] = {}
    if not path.exists():
        return overrides
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                src = unicodedata.normalize("NFC", (row.get("from_token") or "").strip())
                dst = unicodedata.normalize("NFC", (row.get("to_token") or "").strip())
                if not src or not dst or src == dst:
                    continue
                decision = (row.get("decision") or "promote").strip().lower()
                if decision and decision != "promote":
                    continue
                overrides[src.lower()] = dst
    except OSError:
        return {}
    return overrides


SANSKRIT_PROMOTED_OVERRIDES_PATH = Path(__file__).resolve().parents[1] / "data" / "sanskrit_promote_overrides.tsv"
SANSKRIT_PROMOTED_TIER_A_OVERRIDES = load_sanskrit_promoted_overrides(SANSKRIT_PROMOTED_OVERRIDES_PATH)
SANSKRIT_TIER_A_OVERRIDES = {
    **SANSKRIT_HIGH_FREQ_TIER_A_OVERRIDES,
    **SANSKRIT_PROMOTED_TIER_A_OVERRIDES,
}

# Known dubious initial-I forms that should be queued for context review, not auto-applied.
INITIAL_I_MANUAL_REVIEW_BLOCKLIST = {
    "irāgheit",
    "igñid",
    "irde'n",
    "irdo'i",
    "irgyu'i",
}

GERMAN_HINT_WORDS = {
    "auch",
    "alte",
    "schreibung",
    "die",
    "der",
    "das",
    "ein",
    "eine",
    "einer",
    "einem",
    "einen",
    "eines",
    "und",
    "oder",
    "von",
    "zu",
    "im",
    "in",
    "am",
    "an",
    "mit",
    "ohne",
    "fur",
    "für",
    "als",
    "ist",
    "sind",
    "war",
    "bei",
    "dem",
    "den",
    "des",
    "bezeichnet",
    "bedeutet",
    "lex",
    "vgl",
    "siehe",
}

# Conservative set of high-frequency German function words where dotless-ı->i is safe.
DOTLESS_I_GERMAN_CORE_WORDS = {
    "im",
    "in",
    "ist",
    "sind",
    "bei",
    "mit",
    "die",
    "ein",
    "eine",
    "einer",
    "einem",
    "einen",
    "eines",
    "siehe",
}

# User-vetted high-frequency queue items where OCR dotless-ı should be plain i.
# Keep this conservative and corpus-driven; this list only promotes repeated pairs.
DOTLESS_I_TIER_A_ALLOWLIST = {
    "akanıstha",
    "akanısthas",
    "ajıramı",
    "ajıta",
    "amarasımha",
    "anırtodana",
    "anırta",
    "anupamaraksıita",
    "arıs",
    "asıta",
    "atıih",
    "atısas",
    "atınth",
    "avicı",
    "baı",
    "bäi’ı",
    "basıs",
    "bkıh",
    "bkıth",
    "bıbliotheque",
    "bıda",
    "bırda",
    "brajajıvan",
    "byanı",
    "cassıa",
    "candragomın",
    "cır",
    "corydalıs",
    "dolanjı",
    "dbyahıs",
    "ergatıv",
    "ferrarı",
    "gäl’ı",
    "gzanı",
    "gzeı",
    "gzurı",
    "gemahlın",
    "gzıs",
    "harı",
    "harın",
    "hımmelsrichtungen",
    "hırnschale",
    "janı",
    "jına",
    "jınamitra",
    "kalınga",
    "kapılavastu",
    "kapıstan",
    "maskarın",
    "manı",
    "mongolıan",
    "myanı",
    "mıgto",
    "namıs",
    "padın",
    "paranirmitavasavartın",
    "parnassıa",
    "reı",
    "relı",
    "rsı",
    "rıgzın",
    "rıtipa",
    "ryı",
    "sakakı",
    "sailamuktamı",
    "sanghavı",
    "sanı",
    "sarı",
    "särı'i",
    "särı'ı",
    "säkya’ı",
    "samjayın",
    "sikkım",
    "skyı",
    "sır",
    "sınnesorgans",
    "sıkkim",
    "sıtz",
    "stımmung",
    "vaınth",
    "vairocanaraksıta",
    "varanası",
    "vararucı",
    "vajrası",
    "vinayakarıka",
    "vinayapıtaka",
    "vıst",
    "wyuıe",
    "yidanıs",
    "yıin",
    "yıdam",
    "yogın",
    "yogıns",
    "täla’ı",
    "trıpathı",
    "trırarkn",
    "trırarthı",
    "zanı",
    "zıgs",
    "zımbel",
    "ziıg",
}

GERMAN_INITIAL_I_STOPWORDS = {
    "ich",
    "ihm",
    "ihn",
    "ihr",
    "ihre",
    "ihrem",
    "ihren",
    "ihres",
    "ihnen",
    "im",
    "in",
    "ins",
    "ist",
}

GERMAN_WORD_SUFFIXES = (
    "ung",
    "keit",
    "ismus",
    "chen",
    "isch",
    "lich",
    "heit",
    "schaft",
    "ieren",
    "ieren",
)

CITATION_NAME_STOPWORDS = {
    "bd",
    "bde",
    "ed",
    "eds",
    "hrsg",
    "index",
    "indices",
    "institute",
    "institut",
    "press",
    "publishing",
    "foundation",
    "university",
    "centre",
    "center",
    "series",
    "repr",
    "reprint",
    "skt",
    "vol",
    "pp",
    "nr",
    "no",
}

# Canonical source-text sigla found in abbreviation/citation sections.
# Keep this list narrow and explicit to avoid affecting normal transliteration.
CITATION_SIGLUM_CANONICAL = {
    "Bu-Sz",
    "Gs",
    "Gs-H",
    "Ins",
    "Lśdz",
    "Lśdz-K",
    "Liś",
    "Ps",
    "RoINS",
    "SPS",
    "Sambh",
    "Vis",
    "VisT",
    "Xs",
    "Ys",
}

CITATION_SIGLUM_CANONICAL_BY_KEY = {
    re.sub(r"[sś]+", "s", canon.casefold()): canon for canon in CITATION_SIGLUM_CANONICAL
}

# OCR-confusable sigla variants observed in citations.
CITATION_SIGLUM_CONFUSABLE_MAP = {
    # Explicit observed $ confusions.
    "p$": "Ps",
    "x$": "Xs",
    "bu-$": "Bu-Sz",
    "bu-$z": "Bu-Sz",
    "bu-$2": "Bu-Sz",
    "bu-$sz": "Bu-Sz",
    "vi$": "Vis",
    "vis$": "Vis",
    "$ambh": "Sambh",
    "$sambh": "Sambh",
    "$ps": "SPS",
    "roin$": "RoINS",
    "roins$": "RoINS",
    "in$": "Ins",
    "g$": "Gs",
    "g$-h": "Gs-H",
    "g$s-h": "Gs-H",
    "l$dz": "Lśdz",
    "l$dz-k": "Lśdz-K",
    "l$dz-r": "Lśdz-R",
    "l1$": "Liś",
    "1.$dz": "Lśdz",
    "li$": "Liś",
    "lis$": "Liś",
    "vi$t": "VisT",
    "vi$st": "VisT",
    "y$": "Ys",
    "ys$": "Ys",
    # Safe case-noise sigla variants seen in citation contexts.
    "vist": "VisT",
    "visst": "VisT",
    "viist": "VisT",
    "ys": "Ys",
    "gs-h": "Gs-H",
}

CITATION_AUTHOR_CANON_BY_KEY = {
    "bacot": "BACOT",
    "bailey": "BAILEY",
    "beyer": "BEYER",
    "chandra": "CHANDRA",
    "conze": "CONZE",
    "dorji": "DORJI",
    "eimer": "EIMER",
    "emmerick": "EMMERICK",
    "ensink": "ENSINK",
    "everding": "EVERDING",
    "filliozat": "FILLIOZAT",
    "filliozayr": "FILLIOZAT",
    "gruenwedel": "GRÜNWEDEL",
    "grunwedel": "GRÜNWEDEL",
    "imaeda": "IMAEDA",
    "lokesh": "LOKESH",
    "macdonald": "MACDONALD",
    "monastic": "MONASTIC",
    "mtsho": "MTSHO",
    "nobel": "NOBEL",
    "schneider": "SCHNEIDER",
    "schuh": "SCHUH",
    "schwieger": "SCHWIEGER",
    "snellgrove": "SNELLGROVE",
    "takeuchi": "TAKEUCHI",
    "tenzin": "TENZIN",
    "tsepak": "TSEPAK",
    "tucci": "TUCCI",
    "viehbeck": "VIEHBECK",
}

TIBETAN_NAME_PIECE_HINTS = {
    "bkra",
    "bsod",
    "bstan",
    "bzang",
    "chos",
    "dbang",
    "dpal",
    "ldan",
    "ldebs",
    "lde",
    "lde'u",
    "ldin",
    "ldih",
    "lcam",
    "lcog",
    "lha",
    "lhag",
    "lhas",
    "lna",
    "lho",
    "lhun",
    "lta",
    "mgon",
    "norbu",
    "rigs",
    "rgyal",
    "rgyas",
    "rin",
    "sang",
    "sangs",
    "shis",
    "skal",
    "sprul",
}
TIBETAN_LOC_TO_WYLIE_MAP = str.maketrans(
    {
        "ś": "sh",
        "Ś": "sh",
        "ź": "zh",
        "Ź": "zh",
        "ñ": "ny",
        "Ñ": "ny",
        "ṅ": "ng",
        "Ṅ": "ng",
    }
)

SHORT_TIB_SYLLABLES = {
    "a",
    "ba",
    "bo",
    "bya",
    "can",
    "chos",
    "dan",
    "de",
    "di",
    "du",
    "gi",
    "gyi",
    "ka",
    "kha",
    "khyi",
    "kyi",
    "la",
    "las",
    "lha",
    "lo",
    "ma",
    "mi",
    "na",
    "nas",
    "ni",
    "pa",
    "po",
    "ra",
    "rje",
    "rtse",
    "sa",
    "sems",
    "sku",
    "so",
    "ste",
    "su",
    "ta",
    "thar",
    "tu",
    "ya",
    "yan",
    "yin",
    "yul",
    "zhes",
}

DISCOVERY_GENERIC_SHORT_TARGETS = {
    "a",
    "ba",
    "bo",
    "de",
    "di",
    "du",
    "gi",
    "ka",
    "kha",
    "kyi",
    "la",
    "las",
    "lo",
    "ma",
    "na",
    "nas",
    "ni",
    "pa",
    "po",
    "ra",
    "sa",
    "so",
    "su",
    "ta",
    "tu",
    "ya",
    "yin",
}

CONFUSABLE_TO_CANON = {
    "$": "\u015B",  # ś
    "I": "l",
    "\u0131": "i",  # dotless i
    "\u015F": "\u1E63",  # ş -> ṣ
    "\u015E": "\u1E62",  # Ş -> Ṣ
    "\u0146": "\u1E47",  # ņ -> ṇ
    "\u0145": "\u1E46",  # Ņ -> Ṇ
    "\u00E3": "\u0101",  # ã -> ā
    "\u00C3": "\u0100",  # Ã -> Ā
    "\u00F1": "\u1E45",  # ñ -> ṅ
    "\u00D1": "\u1E44",  # Ñ -> Ṅ
}

SKELETON_MAP = str.maketrans(
    {
        "ā": "a",
        "Ā": "a",
        "ī": "i",
        "Ī": "i",
        "ū": "u",
        "Ū": "u",
        "ṛ": "r",
        "Ṛ": "r",
        "ṝ": "r",
        "Ṝ": "r",
        "ḷ": "l",
        "Ḷ": "l",
        "ḹ": "l",
        "Ḹ": "l",
        "ṅ": "n",
        "Ṅ": "n",
        "ñ": "n",
        "Ñ": "n",
        "ṭ": "t",
        "Ṭ": "t",
        "ḍ": "d",
        "Ḍ": "d",
        "ṇ": "n",
        "Ṇ": "n",
        "ś": "s",
        "Ś": "s",
        "ṣ": "s",
        "Ṣ": "s",
        "ḥ": "h",
        "Ḥ": "h",
        "ṃ": "m",
        "Ṃ": "m",
        "ṁ": "m",
        "Ṁ": "m",
        "ź": "z",
        "Ź": "z",
        "ä": "a",
        "Ä": "a",
        "ö": "o",
        "Ö": "o",
        "ü": "u",
        "Ü": "u",
        "ß": "s",
        "ı": "i",
        "ş": "s",
        "Ş": "s",
        "ņ": "n",
        "Ņ": "n",
        "ã": "a",
        "Ã": "a",
    }
)


def truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y"}


def normalize_line(s: str) -> str:
    return SPACE_RE.sub(" ", unicodedata.normalize("NFC", s)).strip()


def canonicalize_translit_token(token: str) -> str:
    canon = "".join(CONFUSABLE_TO_CANON.get(ch, ch) for ch in token)
    # OCR confusable special-case: "Ilh..." is often intended "lh...", not "llh...".
    canon = re.sub(r"(?:(?<=^)|(?<=-))llh", "lh", canon)
    return canon


def distance_key(token: str) -> str:
    t = canonicalize_translit_token(token.lower())
    t = t.translate(SKELETON_MAP)
    t = t.replace("'", "").replace("’", "").replace("-", "")
    return t


def token_is_translit_like(token: str, line_has_tibetan: bool, is_entry_start: bool) -> bool:
    tok = token.lower()
    if len(tok) < 2:
        return False
    if tok in GERMAN_HINT_WORDS:
        return False
    if ROMAN_NUMERAL_RE.fullmatch(tok):
        return False
    if ALL_CAPS_RE.fullmatch(token):
        return False
    if not OCR_LATIN_TOKEN_RE.fullmatch(token):
        return False
    if TRANSLIT_CUE_RE.search(token):
        return True
    if tok in SHORT_TIB_SYLLABLES:
        return True
    if is_entry_start and tok.islower() and len(tok) <= 14:
        return True
    if line_has_tibetan and tok.islower() and len(tok) <= 10:
        if not tok.endswith(GERMAN_WORD_SUFFIXES):
            return True
    return False


def token_is_german_like(token: str) -> bool:
    tok = token.lower()
    if tok in GERMAN_HINT_WORDS:
        return True
    if GERMAN_UMLAUT_RE.search(token):
        return True
    if token and token[0].isupper() and not ALL_CAPS_RE.fullmatch(token):
        return True
    if tok.endswith(GERMAN_WORD_SUFFIXES):
        return True
    return False


def token_has_translit_cue(token: str) -> bool:
    if not token:
        return False
    if TRANSLIT_DIACRITIC_RE.search(token):
        return True
    if "'" in token or "’" in token:
        return True
    if STRONG_TRANSLIT_CLUSTER_RE.search(token):
        return True
    if token.lower() in SHORT_TIB_SYLLABLES and len(token) >= 3:
        return True
    return False


def token_has_hard_translit_marker(token: str) -> bool:
    if not token:
        return False
    if TRANSLIT_DIACRITIC_RE.search(token):
        return True
    if "'" in token or "’" in token:
        return True
    return False


def token_has_boundary_translit_cluster(token: str) -> bool:
    if not token:
        return False
    return bool(BOUNDARY_TRANSLIT_CLUSTER_RE.search(token))


def token_has_distinctive_tibetan_signature(token: str) -> bool:
    if not token:
        return False
    low = canonicalize_translit_token(token).lower()
    if low in SHORT_TIB_SYLLABLES:
        return True
    if token_has_hard_translit_marker(low):
        return True
    if DISTINCTIVE_TIB_CLUSTER_RE.search(low):
        return True
    if TIB_MEDIAL_Y_RE.search(low):
        return True
    return False


def token_is_discovery_translit_candidate(token: str) -> bool:
    if not token:
        return False
    low = canonicalize_translit_token(token).lower()
    if not TRANSLIT_TOKEN_RE.fullmatch(low):
        return False
    if len(low) < 2:
        return False
    if token_is_initial_i_german_function_word(low):
        return False
    if low in SHORT_TIB_SYLLABLES:
        return True
    if token_has_translit_cue(low):
        return True
    if token_has_distinctive_tibetan_signature(low):
        return True
    return False


def token_is_discovery_generic_short_target(token: str) -> bool:
    low = canonicalize_translit_token(token).lower()
    return len(low) <= 3 and low in DISCOVERY_GENERIC_SHORT_TARGETS


def split_vowel_particle_suffix(token: str) -> tuple[str, str] | None:
    m = VOWEL_PARTICLE_SUFFIX_RE.fullmatch(token)
    if not m:
        return None
    base = m.group(1)
    suffix = m.group(2).lower()
    return base, suffix


def token_drops_vowel_particle_suffix(src: str, dst: str) -> bool:
    parts = split_vowel_particle_suffix(src)
    if parts is None:
        return False
    base, _ = parts
    return dst == base


def token_mismatches_vowel_particle_suffix(src: str, dst: str) -> bool:
    src_parts = split_vowel_particle_suffix(src)
    if src_parts is None:
        return False
    _, src_suffix = src_parts
    dst_parts = split_vowel_particle_suffix(dst)
    if dst_parts is None:
        return True
    _, dst_suffix = dst_parts
    return src_suffix != dst_suffix


def token_drops_apostrophe(src: str, dst: str) -> bool:
    src_has = ("'" in src) or ("’" in src)
    dst_has = ("'" in dst) or ("’" in dst)
    return src_has and not dst_has


def token_has_protected_sanskrit_nya(token: str) -> bool:
    low = token.lower()
    if "jñ" in low:
        return True
    return bool(SANSKRIT_NYA_CLUSTER_RE.search(low))


def token_has_protected_palatal_nya(token: str) -> bool:
    return bool(PALATAL_NYA_ONSET_RE.search(token.lower()))


def token_has_protected_tibetan_nya_cluster(token: str) -> bool:
    return bool(TIBETAN_NYA_CLUSTER_RE.search(token.lower()))


def token_has_initial_confusable_I(token: str) -> bool:
    return bool(INITIAL_CONFUSABLE_I_RE.match(token))


def token_blocks_nya_to_nga(src: str, dst: str) -> bool:
    src_low = src.lower()
    dst_low = dst.lower()
    src_nya_protected = token_has_protected_sanskrit_nya(src_low)
    src_palatal_nya_protected = token_has_protected_palatal_nya(src_low)
    src_tibetan_nya_cluster_protected = token_has_protected_tibetan_nya_cluster(src_low)
    return (
        (src_nya_protected or src_palatal_nya_protected or src_tibetan_nya_cluster_protected)
        and "ñ" in src_low
        and "ṅ" in dst_low
        and "ñ" not in dst_low
    )


def token_is_initial_i_confusable_noise(src: str, dst: str) -> bool:
    if not token_has_initial_confusable_I(src):
        return False
    if not dst.lower().startswith("l"):
        return False
    if token_has_hard_translit_marker(src) or token_has_hard_translit_marker(dst):
        return False
    if token_has_boundary_translit_cluster(src) or token_has_boundary_translit_cluster(dst):
        return False
    if src.lower() in SHORT_TIB_SYLLABLES or dst.lower() in SHORT_TIB_SYLLABLES:
        return False
    if not token_is_german_like(src):
        return False
    return True


def token_is_long_plain_initial_i_noise(src: str, dst: str) -> bool:
    if not token_has_initial_confusable_I(src):
        return False
    if not dst.lower().startswith("l"):
        return False
    if len(src) < 8:
        return False
    if "-" in src or "'" in src or "’" in src:
        return False
    if not (src[:1].isupper() and src[1:].islower()):
        return False
    if INITIAL_I_TRANSLIT_ONSET_RE.match(src):
        return False
    if token_has_hard_translit_marker(src) or token_has_hard_translit_marker(dst):
        return False
    if token_has_boundary_translit_cluster(src) or token_has_boundary_translit_cluster(dst):
        return False
    return True


def token_is_initial_i_german_function_word(token: str) -> bool:
    low = token.lower()
    if low in GERMAN_INITIAL_I_STOPWORDS:
        return True
    if GERMAN_IHR_PRONOUN_RE.fullmatch(low):
        return True
    return False


def token_is_mixed_caps_confusable_noise(src: str, dst: str) -> bool:
    if src.lower() == dst.lower():
        return False
    letters = [ch for ch in src if ch.isalpha()]
    if len(letters) < 4:
        return False
    if src.islower() or src.isupper():
        return False
    if token_has_translit_cue(src) or token_has_translit_cue(dst):
        return False
    if token_has_hard_translit_marker(src) or token_has_hard_translit_marker(dst):
        return False
    if "-" in src or "'" in src or "’" in src:
        return False
    uppers = sum(1 for ch in src if ch.isupper())
    lowers = sum(1 for ch in src if ch.islower())
    return uppers >= 2 and lowers >= 2


def token_is_allcaps_confusable_fragment(token: str) -> bool:
    stripped = token.replace("-", "").replace("'", "").replace("’", "")
    letters = [ch for ch in stripped if ch.isalpha()]
    if len(letters) < 4:
        return False
    return all(ch.isupper() for ch in letters)


def token_is_initial_i_translit_candidate(src: str, dst: str) -> bool:
    if not token_has_initial_confusable_I(src):
        return False
    dst_low = dst.lower()
    if not dst_low.startswith("l"):
        return False
    if token_is_initial_i_german_function_word(src):
        return False
    if GERMAN_LHR_PRONOUN_RE.fullmatch(dst_low):
        return False
    if not INITIAL_I_CANON_SHAPE_RE.match(dst_low):
        return False
    if not VOWEL_RE.search(dst_low):
        return False
    # Long plain titlecase I* words are usually German; keep these gated.
    if len(src) >= 8 and src[:1].isupper() and src[1:].islower():
        if not token_has_translit_cue(src) and not token_has_translit_cue(dst):
            return False
    if token_has_hard_translit_marker(src) or token_has_hard_translit_marker(dst):
        return True
    if token_has_boundary_translit_cluster(src) or token_has_boundary_translit_cluster(dst):
        return True
    if "-" in src or "'" in src or "’" in src or "-" in dst or "'" in dst or "’" in dst:
        return True
    if dst_low in SHORT_TIB_SYLLABLES:
        return True
    if len(dst_low) <= 6 and (token_has_translit_cue(src) or token_has_translit_cue(dst)):
        return True
    return (not token_is_german_like(src)) and len(dst_low) <= 7


def token_requires_manual_initial_i_review(src: str, dst: str) -> bool:
    low = src.lower()
    if low in INITIAL_I_MANUAL_REVIEW_BLOCKLIST:
        return True
    if not token_has_initial_confusable_I(src):
        return False
    if not dst.lower().startswith("l"):
        return False
    # Mixed translit+German compounds like *-gheit should be reviewed in context.
    if low.endswith(("gheit", "kheit")) and (token_has_hard_translit_marker(src) or "ñ" in low):
        return True
    return False


def token_is_citation_confusable_i_to_l_candidate(src: str, dst: str) -> bool:
    if src.lower() == dst.lower():
        return False
    if "I" not in src:
        return False
    if src.startswith("I"):
        return False
    if src.islower() or src.isupper():
        return False
    if src[:1].isupper() and src[1:].islower():
        return False
    if len(src) < 6:
        return False
    if token_has_hard_translit_marker(src) or token_has_hard_translit_marker(dst):
        return False
    if TRANSLIT_DIACRITIC_RE.search(src) or TRANSLIT_DIACRITIC_RE.search(dst):
        return False
    if sum(1 for ch in src if ch.isupper()) < 3:
        return False
    # Bibliographic surnames often appear in German prose/citation contexts.
    return token_is_german_like(src)


def token_is_safe_hyphenated_initial_i_to_l_translit(src: str, dst: str) -> bool:
    """Conservative auto-fix for hyphenated Tibetan name compounds.

    Primary target is segment-initial I->l (e.g. Rigs-Idan -> Rigs-ldan).
    Also allows co-occurring safe $->ś changes in other segments of the same
    token (e.g. Bkra-$is-Ihun-po -> Bkra-śis-lhun-po).
    """
    if src == dst:
        return False
    if "-" not in src or "-" not in dst:
        return False
    if src.count("-") != dst.count("-"):
        return False
    src_parts = src.split("-")
    dst_parts = dst.split("-")
    if len(src_parts) != len(dst_parts) or len(src_parts) < 2:
        return False

    def is_strong_tibetan_piece(piece: str) -> bool:
        low = canonicalize_translit_token(piece).lower()
        low_wylie = low.translate(TIBETAN_LOC_TO_WYLIE_MAP)
        if len(low_wylie) < 3:
            return False
        if low_wylie in TIBETAN_NAME_PIECE_HINTS:
            return True
        if token_has_hard_translit_marker(low) or token_has_hard_translit_marker(low_wylie):
            return True
        if DISTINCTIVE_TIB_CLUSTER_RE.search(low) or DISTINCTIVE_TIB_CLUSTER_RE.search(low_wylie):
            return True
        if TIBETAN_NAME_PIECE_PREFIX_RE.search(low_wylie):
            return True
        return False

    changed_parts = 0
    changed_i_parts = 0
    changed_dollar_parts = 0
    unchanged_strong_anchors = 0
    unchanged_short_syllable_anchors = 0
    changed_strong_parts = 0
    for src_part, dst_part in zip(src_parts, dst_parts):
        if not src_part or not dst_part:
            return False
        if src_part.casefold() == dst_part.casefold():
            unchanged_low = canonicalize_translit_token(src_part).lower()
            if is_strong_tibetan_piece(src_part) or is_strong_tibetan_piece(dst_part):
                unchanged_strong_anchors += 1
            elif unchanged_low in SHORT_TIB_SYLLABLES:
                unchanged_short_syllable_anchors += 1
            continue
        if len(src_part) != len(dst_part):
            return False
        # Allow segment-initial I -> l with exact tail preservation.
        if src_part.startswith("I") and dst_part.startswith("l"):
            if src_part[1:].casefold() != dst_part[1:].casefold():
                return False
            if len(src_part) < 3:
                return False
            if not dst_part[1:].islower():
                return False
            # Block mixed-language artifacts (e.g. Indo-Aryan -> lndo-Aryan).
            if not is_strong_tibetan_piece(dst_part):
                return False
            changed_strong_parts += 1
            changed_i_parts += 1
            changed_parts += 1
            continue
        # Permit safe $->ś changes in other segments of the same hyphen-chain.
        if token_is_safe_dollar_to_sacute(src_part, dst_part):
            changed_dollar_parts += 1
            changed_parts += 1
            continue
        return False

    if changed_parts == 0 or changed_parts > 3:
        return False
    if changed_i_parts == 0:
        return False
    # Allow two-part compounds where both parts are confidently Tibetan
    # confusable I->l segments, e.g. IHa-Icam -> lha-lcam.
    if (
        len(src_parts) == 2
        and changed_parts == 2
        and changed_strong_parts == 2
        and changed_dollar_parts == 0
    ):
        return True
    # Also allow fully-changed three-part chains when every changed segment is
    # a strong Tibetan I->l confusable (e.g. Iha-Icam-Ihun -> lha-lcam-lhun).
    if (
        len(src_parts) == 3
        and changed_parts == 3
        and changed_strong_parts == 3
        and changed_dollar_parts == 0
    ):
        return True
    if unchanged_strong_anchors > 0:
        return True
    # Allow two-part compounds like Iha-mo -> lha-mo when the second part is
    # a short Tibetan syllable and the changed part is strongly Tibetan.
    if len(src_parts) == 2 and unchanged_short_syllable_anchors > 0:
        return True
    # Also allow longer compounds when there is at least one short Tibetan
    # syllable anchor (e.g. $is-Ihun-po -> śis-lhun-po via unchanged "po").
    if unchanged_short_syllable_anchors > 0:
        return True
    return False


def token_is_safe_coda_nya_to_nga(src: str, dst: str) -> bool:
    src_low = src.lower()
    dst_low = dst.lower()
    if "ñ" not in src_low or "ṅ" not in dst_low:
        return False
    if token_blocks_nya_to_nga(src_low, dst_low):
        return False
    if len(src_low) != len(dst_low):
        return False
    for s_ch, d_ch in zip(src_low, dst_low):
        if s_ch == d_ch:
            continue
        if s_ch == "ñ" and d_ch == "ṅ":
            continue
        return False
    for idx, ch in enumerate(src_low):
        if ch != "ñ":
            continue
        if idx + 1 >= len(src_low):
            continue
        nxt = src_low[idx + 1]
        if nxt in {"-", "'", "’"}:
            continue
        # Keep this strictly coda-like for auto-fix; onset/palatal contexts stay in review.
        if nxt not in {"s", "g", "k", "t", "d", "p", "b", "m", "r", "l", "n"}:
            return False
    return True


def token_is_safe_dollar_to_sacute(src: str, dst: str) -> bool:
    if "$" not in src:
        return False
    if len(src) != len(dst):
        return False
    if not any(ch.isalpha() for ch in src):
        return False
    changed = False
    for s_ch, d_ch in zip(src, dst):
        if s_ch == d_ch:
            continue
        if s_ch == "$" and d_ch in {"ś", "Ś"}:
            changed = True
            continue
        return False
    if not changed:
        return False

    # Re-scan with indices for neighborhood checks around replaced positions.
    replaced_at = [idx for idx, s_ch in enumerate(src) if s_ch == "$"]
    dst_low = dst.lower()
    if DOLLAR_SACUTE_ARTIFACT_RE.search(dst_low):
        return False
    for idx in replaced_at:
        prev_ch = dst_low[idx - 1] if idx > 0 else ""
        next_ch = dst_low[idx + 1] if idx + 1 < len(dst_low) else ""
        if prev_ch in {"s", "ś", "ṣ"}:
            return False
        if next_ch in {"z", "ź", "ž", "ś", "ṣ"}:
            return False
    return True


def token_is_safe_dotless_i_to_i(src: str, dst: str) -> bool:
    if "ı" not in src:
        return False
    if len(src) != len(dst):
        return False
    changed = False
    for s_ch, d_ch in zip(src, dst):
        if s_ch == d_ch:
            continue
        if s_ch == "ı" and d_ch == "i":
            changed = True
            continue
        return False
    return changed


def token_is_safe_internal_confusable_I_to_i(src: str, dst: str) -> bool:
    if "I" not in src:
        return False
    if src.startswith("I"):
        return False
    if len(src) != len(dst):
        return False
    changed = False
    for idx, (s_ch, d_ch) in enumerate(zip(src, dst)):
        if s_ch == d_ch:
            continue
        if idx > 0 and s_ch == "I" and d_ch == "i":
            changed = True
            continue
        return False
    return changed


def normalize_roman_numeral_confusable_l(token: str) -> str:
    """Normalize lowercase OCR l to I in long roman numeral tokens."""
    if "l" not in token or len(token) < 4:
        return token
    if any(ch not in "ivxlcdmIVXLCDMl" for ch in token):
        return token
    cand = token.replace("l", "I")
    if not ROMAN_NUMERAL_RE.fullmatch(cand):
        return token
    # Keep short ambiguous forms untouched; target citation-style numerals.
    if not any(ch in cand for ch in "XVLCDM"):
        return token
    return cand


def token_is_trailing_shortening(src: str, dst: str) -> bool:
    # Only guard true shortenings where candidate drops a short trailing tail.
    if len(src) <= len(dst):
        return False
    if len(src) < 4 or len(dst) < 3:
        return False
    if src.startswith(dst) and 1 <= (len(src) - len(dst)) <= 2:
        if src.endswith(("i", "o", "'i", "’i", "'o", "’o")):
            return True
        if src.endswith("a") and dst.endswith(("r", "k")):
            return True
    return False


def token_has_case_destructive_shift(src: str, dst: str) -> bool:
    if src == dst:
        return False
    src_alpha = [ch for ch in src if ch.isalpha()]
    dst_alpha = [ch for ch in dst if ch.isalpha()]
    if not src_alpha or not dst_alpha:
        return False
    src_norm = canonicalize_translit_token(src).casefold()
    dst_norm = canonicalize_translit_token(dst).casefold()
    if src_norm != dst_norm:
        return False
    src_upper = sum(1 for ch in src_alpha if ch.isupper())
    dst_upper = sum(1 for ch in dst_alpha if ch.isupper())
    if src_upper >= 2 and dst_upper == 0:
        return True
    if "-" in src and "-" in dst:
        src_parts = src.split("-")
        dst_parts = dst.split("-")
        if len(src_parts) != len(dst_parts):
            return False
        for src_part, dst_part in zip(src_parts, dst_parts):
            if not src_part or not dst_part:
                continue
            src_title = src_part[:1].isupper() and src_part[1:].islower()
            dst_title = dst_part[:1].isupper() and dst_part[1:].islower()
            if src_title and not dst_title:
                if token_has_initial_confusable_I(src_part) and dst_part[:1] == "l" and dst_part[1:].islower():
                    continue
                return True
    return False


def rewrite_watchdog_flags(src: str, dst: str) -> list[str]:
    flags: list[str] = []
    src_low = canonicalize_translit_token(src).lower()
    dst_low = canonicalize_translit_token(dst).lower()

    if token_drops_vowel_particle_suffix(src_low, dst_low):
        flags.append("particle_suffix_drop")
    if token_mismatches_vowel_particle_suffix(src_low, dst_low):
        flags.append("particle_suffix_mismatch")
    if token_drops_apostrophe(src, dst):
        flags.append("apostrophe_drop")
    if token_is_trailing_shortening(src_low, dst_low):
        flags.append("trailing_shortening")
    if token_blocks_nya_to_nga(src_low, dst_low):
        flags.append("protected_nya_to_nga")
    if token_has_case_destructive_shift(src, dst):
        flags.append("case_destructive_shift")

    src_key = distance_key(src)
    dst_key = distance_key(dst)
    dist = levenshtein_limited(src_key, dst_key, 4)
    if dist is None:
        if abs(len(src_key) - len(dst_key)) >= 3:
            flags.append("high_edit_distance_drift")
    elif dist >= 3:
        flags.append("high_edit_distance_drift")
    return flags


def rewrite_hard_guard_block_reason(src: str, dst: str, reason: str, stage: str) -> str | None:
    del stage
    for flag in rewrite_watchdog_flags(src, dst):
        if flag not in HARD_GUARD_BLOCK_FLAGS:
            continue
        if flag == "case_destructive_shift" and reason == "citation_caps_name_normalize":
            continue
        return flag
    return None


def token_is_strict_clean_translit(token: str) -> bool:
    if not TRANSLIT_TOKEN_RE.fullmatch(token):
        return False
    if token != canonicalize_translit_token(token):
        return False
    if GERMAN_UMLAUT_RE.search(token):
        return False
    if ALL_CAPS_RE.fullmatch(token):
        return False
    if token.lower() in GERMAN_HINT_WORDS:
        return False
    return True


def validate_translit_token(token: str) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    canon = canonicalize_translit_token(token)
    confusable_dollar_blocked = ("$" in token) and (not token_is_safe_dollar_to_sacute(token, canon))
    confusable_blocked = (
        token_blocks_nya_to_nga(token, canon)
        or token_is_initial_i_confusable_noise(token, canon)
        or token_is_initial_i_german_function_word(token)
        or confusable_dollar_blocked
    )
    if canon != token and not confusable_blocked:
        issues.append(("confusable_char", canon))
    if not TRANSLIT_TOKEN_RE.fullmatch(canon):
        issues.append(("invalid_translit_shape", canon))
    if NOISE_RE.search(token):
        issues.append(("digit_or_symbol_noise", canon))
    if GERMAN_UMLAUT_RE.search(token):
        issues.append(("german_umlaut_in_translit_context", canon))
    return issues


def first_confusable_suggestion(issues: list[tuple[str, str]]) -> str | None:
    for issue, suggestion in issues:
        if issue == "confusable_char":
            return canonicalize_translit_token(suggestion).lower()
    return None


def extract_tibetan_prefix(line: str) -> tuple[str, int]:
    m = TIB_PREFIX_RE.match(line)
    if not m:
        return "", 0
    prefix = m.group(1).strip()
    if not prefix or not TIB_RE.search(prefix):
        return "", 0
    return SPACE_RE.sub(" ", prefix), m.end()


def extract_headword_latin(remainder: str) -> tuple[str, str]:
    tokens: list[str] = []
    used_cue = False
    prev_end = 0
    for m in OCR_LATIN_TOKEN_RE.finditer(remainder):
        if len(tokens) >= 10:
            break
        between = remainder[prev_end : m.start()]
        prev_end = m.end()
        if re.search(r"\d", between):
            break
        if re.search(r"[.;:!?]", between) and tokens:
            break
        tok = m.group(0)
        low = tok.lower()
        is_trans = token_is_translit_like(tok, line_has_tibetan=True, is_entry_start=True)
        if low in GERMAN_HINT_WORDS and tokens:
            break
        if not is_trans:
            if not tokens:
                continue
            break
        if TRANSLIT_CUE_RE.search(tok):
            used_cue = True
        tokens.append(tok)
    if not tokens:
        return "", "none"
    conf = "high" if used_cue else "medium"
    return " ".join(tokens), conf


def classify_zone(line: str, is_entry_start: bool, translit_tokens: int, german_tokens: int) -> str:
    has_tib = bool(TIB_RE.search(line))
    if is_entry_start:
        return "headword_line"
    if has_tib and translit_tokens > 0 and german_tokens > 0:
        return "example_tibetan_latin"
    if has_tib and translit_tokens > 0:
        return "tibetan_latin_mixed"
    if has_tib:
        return "tibetan_only"
    if german_tokens > 0 and translit_tokens > 0:
        return "german_prose_with_translit"
    if german_tokens > 0:
        return "german_prose"
    if translit_tokens > 0:
        return "latin_other"
    return "other"


def levenshtein_limited(a: str, b: str, max_dist: int) -> int | None:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > max_dist:
        return None
    if not a or not b:
        d = max(len(a), len(b))
        return d if d <= max_dist else None

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        row_min = cur[0]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if cur[j] < row_min:
                row_min = cur[j]
        if row_min > max_dist:
            return None
        prev = cur
    d = prev[-1]
    return d if d <= max_dist else None


def apply_case_pattern(src: str, dst: str) -> str:
    if src.isupper():
        return dst.upper()
    if len(src) == len(dst):
        out: list[str] = []
        for s_ch, d_ch in zip(src, dst):
            if not d_ch.isalpha():
                out.append(d_ch)
                continue
            # OCR confusable: uppercase I often stands for lowercase l in these tokens.
            if s_ch == "I" and d_ch.lower() == "l":
                out.append("l")
                continue
            # Internal OCR confusable: uppercase I can also be lowercase i.
            if s_ch == "I" and d_ch == "i":
                out.append("i")
                continue
            if s_ch.isupper():
                out.append(d_ch.upper())
                continue
            if s_ch.islower():
                out.append(d_ch.lower())
                continue
            out.append(d_ch)
        shaped = "".join(out)
        if token_has_initial_confusable_I(src) and shaped.startswith("L"):
            return "l" + shaped[1:]
        return shaped
    # OCR confusable: preserve corrected lowercase l* when source starts with mistaken I*.
    if token_has_initial_confusable_I(src) and dst.startswith("l"):
        return dst
    if src and src[0].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


def token_upper_ratio(token: str) -> float:
    letters = [ch for ch in token if ch.isalpha()]
    if not letters:
        return 0.0
    uppers = sum(1 for ch in letters if ch.isupper())
    return uppers / len(letters)


def token_occurrence_near_year(line: str, start: int, end: int) -> bool:
    left = max(0, start - 8)
    right = min(len(line), end + 24)
    snippet = line[left:right]
    return bool(CITATION_YEAR_RE.search(snippet) or CITATION_SPLIT_YEAR_RE.search(snippet))


def line_has_parenthetical_citation(line_text: str) -> bool:
    for m in CITATION_PAREN_RE.finditer(line_text):
        segment = m.group(0)
        if CITATION_PAREN_HINT_RE.search(segment):
            return True
        if CITATION_PAREN_NAME_PAGE_RE.search(segment):
            return True
    return False


def line_is_citation_like(info: "LineInfo", line_text: str) -> bool:
    if info.zone not in {
        "german_prose",
        "german_prose_with_translit",
        "latin_other",
        "other",
        "example_tibetan_latin",
        "tibetan_latin_mixed",
    }:
        return False
    if CITATION_YEAR_RE.search(line_text):
        return True
    if CITATION_SPLIT_YEAR_RE.search(line_text):
        return True
    if line_has_parenthetical_citation(line_text):
        return True
    if CITATION_SIGLUM_ARTIFACT_CUE_RE.search(line_text):
        return True
    if line_has_citation_siglum_candidate(line_text):
        return True
    return bool(CITATION_CUE_RE.search(line_text))


def token_is_citation_caps_name_candidate(token: str) -> bool:
    if len(token) < 4:
        return False
    if "'" in token or "’" in token:
        return False
    if ROMAN_NUMERAL_RE.fullmatch(token):
        return False
    lower_initial_confusable = token[:1].islower() and token[1:2].isupper()
    if not token.isupper() and token[:1].islower() and not lower_initial_confusable:
        return False
    low = token.casefold()
    if low in GERMAN_HINT_WORDS or low in CITATION_NAME_STOPWORDS:
        return False
    if token_has_distinctive_tibetan_signature(token):
        return False
    letters = [ch for ch in token if ch.isalpha()]
    if len(letters) < 4:
        return False
    uppers = sum(1 for ch in letters if ch.isupper())
    if uppers < 2:
        return False
    ratio = uppers / len(letters)
    if ratio >= 0.55:
        return True
    # Accept mixed-case OCR noise forms if they map to a known citation author family.
    if token_looks_like_known_citation_author(token):
        return True
    return lower_initial_confusable and ratio >= 0.45


def token_is_citation_author_lookup_candidate(token: str) -> bool:
    if len(token) < 4:
        return False
    if "'" in token or "’" in token:
        return False
    if ROMAN_NUMERAL_RE.fullmatch(token):
        return False
    if token.islower():
        return False
    low = token.casefold()
    if low in GERMAN_HINT_WORDS or low in CITATION_NAME_STOPWORDS:
        return False
    if token_has_distinctive_tibetan_signature(token):
        return False
    letters = [ch for ch in token if ch.isalpha()]
    if len(letters) < 4:
        return False
    if token_is_citation_caps_name_candidate(token):
        return True
    if token[:1].isupper() and token[1:].islower():
        return True
    # Mixed-case OCR noise forms should map only when they look like an
    # attested citation-author family.
    return token_is_mixed_case_ocr_variant(token) and token_looks_like_known_citation_author(token)


def match_citation_siglum(token: str) -> str | None:
    siglum = CITATION_SIGLUM_CONFUSABLE_MAP.get(token.casefold())
    if siglum is not None:
        return siglum
    if "$" in token:
        # Handle insertion-noise forms like Vis$T/Lis$ by collapsing repeated
        # s/ś after replacing $ with confusable values, then matching canon.
        for candidate in (token.replace("$", "s"), token.replace("$", "ś"), token.replace("$", "")):
            collapsed_guess = re.sub(r"[sś]+", "s", candidate.casefold())
            siglum = CITATION_SIGLUM_CANONICAL_BY_KEY.get(collapsed_guess)
            if siglum is not None:
                return siglum
    # Allow wrapped/extended L$dz sigla forms such as L$dz-, L$dz-K, L$dz-R.
    if re.fullmatch(r"(?i)l\$dz(?:-[A-Za-z$]*)?", token):
        siglum = "Lśdz" + token[4:]
        return siglum.replace("$", "ś")
    return None


def citation_safe_confusable_rewrite(token: str) -> str:
    """Safe citation-only OCR fixes (no deletions, no translit remapping)."""
    out = token.replace("ı", "i")
    # Normalize a trailing apostrophe around citation sigla without changing it.
    trail = ""
    if out.endswith(("'", "’")):
        trail = out[-1]
        out = out[:-1]

    siglum = match_citation_siglum(out)
    if siglum is not None:
        return siglum + trail

    if len(out) >= 2 and out[:1] == "l" and out[1:2].isupper():
        tail_alpha = [ch for ch in out[1:] if ch.isalpha()]
        if len(tail_alpha) >= 2:
            tail_uppers = sum(1 for ch in tail_alpha if ch.isupper())
            if tail_uppers >= max(1, len(tail_alpha) - 1):
                out = "I" + out[1:]
    return out + trail


def token_is_citation_siglum_candidate(token: str) -> bool:
    if len(token) < 2:
        return False
    core = token
    if core.endswith(("'", "’")):
        core = core[:-1]
    if not re.fullmatch(r"[A-Za-z$]+(?:-[A-Za-z$]*)?", core):
        return False
    if "$" not in core and CITATION_SIGLUM_CONFUSABLE_MAP.get(core.casefold()) is None:
        return False
    return match_citation_siglum(core) is not None


def line_has_citation_siglum_candidate(line_text: str) -> bool:
    if CITATION_SIGLUM_DIGIT_ARTIFACT_RE.search(line_text):
        return True
    for m in OCR_LATIN_TOKEN_RE.finditer(line_text):
        if token_is_citation_siglum_candidate(m.group(0)):
            return True
    return False


def citation_name_family_key(token: str) -> str:
    return citation_safe_confusable_rewrite(token).casefold().replace("’", "'")


def citation_author_key(token: str) -> str:
    norm = unicodedata.normalize("NFD", citation_safe_confusable_rewrite(token).casefold())
    out: list[str] = []
    for ch in norm:
        if unicodedata.category(ch) == "Mn":
            continue
        if ch in {"-", "'", "’"}:
            continue
        if ch == "ß":
            out.append("ss")
            continue
        if ch.isalpha():
            out.append(ch)
    return "".join(out)


def token_looks_like_known_citation_author(token: str) -> bool:
    src_key = citation_author_key(token)
    if len(src_key) < 4:
        return False
    if src_key in CITATION_AUTHOR_CANON_BY_KEY:
        return True
    max_dist = 1
    for key in CITATION_AUTHOR_CANON_BY_KEY:
        if abs(len(src_key) - len(key)) > max_dist:
            continue
        if levenshtein_limited(src_key, key, max_dist) is not None:
            return True
    return False


def token_is_likely_tibetan_name_piece(token: str) -> bool:
    low = canonicalize_translit_token(token).lower()
    low_wylie = low.translate(TIBETAN_LOC_TO_WYLIE_MAP)
    if len(low_wylie) < 3:
        return False
    if low_wylie in TIBETAN_NAME_PIECE_HINTS:
        return True
    if token_has_distinctive_tibetan_signature(low) or token_has_distinctive_tibetan_signature(low_wylie):
        return True
    if TIBETAN_NAME_PIECE_PREFIX_RE.search(low_wylie):
        return True
    return False


def token_is_citation_person_name_candidate(token: str) -> bool:
    if not token_is_citation_caps_name_candidate(token):
        return False
    if token_looks_like_known_citation_author(token):
        return True
    if token_is_likely_tibetan_name_piece(token):
        return False
    return True


def build_citation_author_lexicon(
    family_counts: dict[str, Counter[str]],
    family_year_hits: Counter[str],
) -> dict[str, str]:
    lexicon = dict(CITATION_AUTHOR_CANON_BY_KEY)
    for key, variants in family_counts.items():
        if family_year_hits.get(key, 0) == 0:
            continue
        top_tok, top_cnt = max(variants.items(), key=lambda kv: (kv[1], token_upper_ratio(kv[0]), len(kv[0])))
        if top_cnt < 2:
            continue
        if not token_is_citation_person_name_candidate(top_tok):
            continue
        if token_upper_ratio(top_tok) < 0.72:
            continue
        top_tok_norm = citation_safe_confusable_rewrite(top_tok)
        author_key = citation_author_key(top_tok_norm)
        if len(author_key) < 4:
            continue
        lexicon.setdefault(author_key, top_tok_norm.upper())
    return lexicon


def token_has_citation_ocr_noise_shape(token: str) -> bool:
    if token.isupper():
        letters = [ch for ch in token if ch.isalpha()]
        if len(letters) >= 2 and letters[0] == letters[1]:
            return True
        if len(letters) >= 2 and letters[-1] == letters[-2]:
            return True
        return False
    if token[:1].isupper() and token[1:].islower():
        return False
    return True


def token_is_mixed_case_ocr_variant(token: str) -> bool:
    letters = [ch for ch in token if ch.isalpha()]
    if len(letters) < 4:
        return False
    if token.isupper() or token.islower():
        return False
    if token[:1].isupper() and token[1:].islower():
        return False
    uppers = sum(1 for ch in letters if ch.isupper())
    lowers = sum(1 for ch in letters if ch.islower())
    return uppers > 0 and lowers > 0


def match_citation_author_lexicon(token: str, author_lexicon: dict[str, str]) -> str | None:
    src_key = citation_author_key(token)
    if len(src_key) < 4:
        return None
    exact = author_lexicon.get(src_key)
    if exact is not None:
        return exact

    if not token_has_citation_ocr_noise_shape(token):
        return None

    max_dist = 1
    best_dist = max_dist + 1
    best_targets: set[str] = set()
    for key, canon in CITATION_AUTHOR_CANON_BY_KEY.items():
        if abs(len(src_key) - len(key)) > max_dist:
            continue
        dist = levenshtein_limited(src_key, key, max_dist)
        if dist is None:
            continue
        if dist < best_dist:
            best_dist = dist
            best_targets = {canon}
            continue
        if dist == best_dist:
            best_targets.add(canon)
    if len(best_targets) != 1:
        return None
    return next(iter(best_targets))


@dataclass
class AuditStats:
    rows: int = 0
    candidates: int = 0
    replaced: int = 0
    reasons: Counter[str] = field(default_factory=Counter)


@dataclass
class Entry:
    entry_id: int
    start_page: int
    start_line: int
    headword_tibetan: str
    headword_latin: str
    headword_latin_confidence: str
    end_page: int
    end_line: int
    line_count: int = 0
    zone_counts: Counter[str] = field(default_factory=Counter)
    audit_candidate_lines: int = 0
    audit_replaced_lines: int = 0
    audit_reasons: Counter[str] = field(default_factory=Counter)

    def to_json(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "start_page": self.start_page,
            "start_line": self.start_line,
            "end_page": self.end_page,
            "end_line": self.end_line,
            "headword_tibetan": self.headword_tibetan,
            "headword_latin": self.headword_latin,
            "headword_latin_confidence": self.headword_latin_confidence,
            "line_count": self.line_count,
            "zone_counts": dict(self.zone_counts),
            "audit_candidate_lines": self.audit_candidate_lines,
            "audit_replaced_lines": self.audit_replaced_lines,
            "top_audit_reasons": self.audit_reasons.most_common(6),
        }


@dataclass
class LineInfo:
    page: int
    line: int
    entry_id: int
    zone: str
    line_text: str
    has_tibetan: bool
    is_entry_start: bool
    translit_tokens: list[str]
    german_tokens: list[str]


@dataclass
class DiscoveryPattern:
    source_token: str
    suggested_token: str
    source_count: int
    suggested_count: int
    edit_distance: int
    confidence: str
    ambiguous: bool
    example: str


def load_audit(path: Path | None) -> dict[tuple[int, int], AuditStats]:
    if path is None:
        return {}
    out: dict[tuple[int, int], AuditStats] = defaultdict(AuditStats)
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                page = int(row.get("page", "0"))
                line = int(row.get("line", "0"))
            except ValueError:
                continue
            key = (page, line)
            stats = out[key]
            stats.rows += 1
            if truthy(row.get("candidate")):
                stats.candidates += 1
            if truthy(row.get("replaced")):
                stats.replaced += 1
            reason = (row.get("reason") or "").strip()
            if reason:
                stats.reasons[reason] += 1
    return out


def parse_entries(
    merged_text: str,
    audit_by_line: dict[tuple[int, int], AuditStats],
) -> tuple[list[Entry], list[LineInfo], list[list[str]], list[list[str]], dict[str, object], list[list[str]]]:
    pages = merged_text.split("\f")
    page_lines: list[list[str]] = []
    entries: list[Entry] = []
    line_infos: list[LineInfo] = []
    line_rows: list[list[str]] = []
    validator_rows: list[list[str]] = []
    entry_id = 0
    current: Entry | None = None
    uncaptured_headword_like = 0
    total_lines = 0
    translit_token_total = 0

    for page_idx, page_text in enumerate(pages, start=1):
        lines = page_text.splitlines()
        norm_lines = [normalize_line(raw) for raw in lines]
        page_lines.append(norm_lines)
        for line_idx, line in enumerate(norm_lines, start=1):
            total_lines += 1
            if not line:
                continue

            tib_prefix, tib_end = extract_tibetan_prefix(line)
            headword_latin = ""
            headword_conf = "none"
            if tib_prefix:
                remainder = line[tib_end:].strip()
                headword_latin, headword_conf = extract_headword_latin(remainder)
            is_entry_start = bool(tib_prefix and headword_latin)

            if tib_prefix and not headword_latin:
                uncaptured_headword_like += 1

            if is_entry_start:
                entry_id += 1
                if current is not None:
                    entries.append(current)
                current = Entry(
                    entry_id=entry_id,
                    start_page=page_idx,
                    start_line=line_idx,
                    headword_tibetan=tib_prefix,
                    headword_latin=headword_latin,
                    headword_latin_confidence=headword_conf,
                    end_page=page_idx,
                    end_line=line_idx,
                )

            has_tibetan = bool(TIB_RE.search(line))
            latin_tokens = [m.group(0) for m in OCR_LATIN_TOKEN_RE.finditer(line)]
            translit_tokens: list[str] = []
            german_tokens: list[str] = []
            for tok in latin_tokens:
                if token_is_translit_like(tok, line_has_tibetan=has_tibetan, is_entry_start=is_entry_start):
                    translit_tokens.append(tok)
                elif token_is_german_like(tok):
                    german_tokens.append(tok)
            translit_token_total += len(translit_tokens)
            zone = classify_zone(line, is_entry_start, len(translit_tokens), len(german_tokens))

            audit = audit_by_line.get((page_idx, line_idx), AuditStats())
            if current is not None:
                current.end_page = page_idx
                current.end_line = line_idx
                current.line_count += 1
                current.zone_counts[zone] += 1
                if audit.candidates > 0:
                    current.audit_candidate_lines += 1
                if audit.replaced > 0:
                    current.audit_replaced_lines += 1
                current.audit_reasons.update(audit.reasons)

            info = LineInfo(
                page=page_idx,
                line=line_idx,
                entry_id=current.entry_id if current is not None else 0,
                zone=zone,
                line_text=line,
                has_tibetan=has_tibetan,
                is_entry_start=is_entry_start,
                translit_tokens=translit_tokens,
                german_tokens=german_tokens,
            )
            line_infos.append(info)

            line_rows.append(
                [
                    str(page_idx),
                    str(line_idx),
                    str(info.entry_id),
                    zone,
                    tib_prefix,
                    headword_latin,
                    headword_conf,
                    str(len(translit_tokens)),
                    str(len(german_tokens)),
                    str(audit.candidates),
                    str(audit.replaced),
                    line,
                ]
            )

            for tok in translit_tokens:
                for issue, suggestion in validate_translit_token(tok):
                    validator_rows.append(
                        [
                            str(page_idx),
                            str(line_idx),
                            str(info.entry_id),
                            zone,
                            tok,
                            issue,
                            suggestion,
                            line[:240],
                        ]
                    )

    if current is not None:
        entries.append(current)

    zone_counter = Counter(row[3] for row in line_rows)
    summary = {
        "pages": len(pages),
        "total_lines_seen": total_lines,
        "non_empty_lines": len(line_rows),
        "entries_detected": len(entries),
        "translit_tokens_detected": translit_token_total,
        "validator_issues": len(validator_rows),
        "uncaptured_tibetan_prefix_lines": uncaptured_headword_like,
        "zone_counts": dict(zone_counter),
    }
    return entries, line_infos, line_rows, validator_rows, summary, page_lines


def build_entry_memory(
    entries: list[Entry],
    line_infos: list[LineInfo],
) -> tuple[dict[int, set[str]], dict[int, set[str]]]:
    headword_mem: dict[int, set[str]] = defaultdict(set)
    memory_counts: dict[int, Counter[str]] = defaultdict(Counter)

    for ent in entries:
        for tok in OCR_LATIN_TOKEN_RE.findall(ent.headword_latin):
            c = canonicalize_translit_token(tok.lower())
            if token_is_strict_clean_translit(c):
                headword_mem[ent.entry_id].add(c)
                memory_counts[ent.entry_id][c] += 8

    for info in line_infos:
        if info.entry_id == 0:
            continue
        if info.zone in ENTRY_STRONG_ZONES:
            for tok in info.translit_tokens:
                c = canonicalize_translit_token(tok.lower())
                if token_is_strict_clean_translit(c):
                    memory_counts[info.entry_id][c] += 1

    entry_mem: dict[int, set[str]] = defaultdict(set)
    for ent in entries:
        cnt = memory_counts.get(ent.entry_id, Counter())
        out = set(headword_mem.get(ent.entry_id, set()))
        for tok, n in cnt.items():
            if n >= 2:
                out.add(tok)
        entry_mem[ent.entry_id] = out

    return headword_mem, entry_mem


def build_trusted_lexicon(
    entries: list[Entry],
    line_infos: list[LineInfo],
    min_freq: int,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for ent in entries:
        for tok in OCR_LATIN_TOKEN_RE.findall(ent.headword_latin):
            c = canonicalize_translit_token(tok.lower())
            if token_is_strict_clean_translit(c):
                counts[c] += 4
    for info in line_infos:
        if info.zone not in ENTRY_STRONG_ZONES and not info.has_tibetan:
            continue
        for tok in info.translit_tokens:
            c = canonicalize_translit_token(tok.lower())
            if token_is_strict_clean_translit(c):
                counts[c] += 1
    return {tok: n for tok, n in counts.items() if n >= min_freq}


def discover_common_errors(
    line_infos: list[LineInfo],
    trusted_lexicon: dict[str, int],
    max_edit: int,
    max_rare_freq: int,
) -> tuple[dict[str, DiscoveryPattern], list[list[str]]]:
    token_counts: Counter[str] = Counter()
    token_examples: dict[str, str] = {}
    token_issue_count: Counter[str] = Counter()

    for info in line_infos:
        if info.zone not in AUTO_FIX_ZONES:
            continue
        for tok in info.translit_tokens:
            low = tok.lower()
            token_counts[low] += 1
            if low not in token_examples:
                token_examples[low] = info.line_text
            if validate_translit_token(tok):
                token_issue_count[low] += 1

    trusted_by_len: dict[int, list[tuple[str, int, str]]] = defaultdict(list)
    for tok, cnt in trusted_lexicon.items():
        key = distance_key(tok)
        if len(key) < 2:
            continue
        trusted_by_len[len(key)].append((tok, cnt, key))

    discovered: dict[str, DiscoveryPattern] = {}
    discovered_rows: list[list[str]] = []

    for src, src_count in token_counts.items():
        if src in trusted_lexicon:
            continue
        src_issues = validate_translit_token(src)
        src_has_cue = token_has_translit_cue(src)
        src_has_hard_marker = token_has_hard_translit_marker(src)
        src_has_signature = token_has_distinctive_tibetan_signature(src)
        src_discovery_candidate = token_is_discovery_translit_candidate(src)
        src_has_issue = bool(src_issues)
        src_only_confusable_issue = bool(src_issues) and all(issue == "confusable_char" for issue, _ in src_issues)
        src_confusable_suggestion = first_confusable_suggestion(src_issues)
        src_issue_ratio = (token_issue_count[src] / src_count) if src_count else 0.0
        src_umlaut_untrusted = bool(GERMAN_UMLAUT_RE.search(src)) and not src_has_hard_marker
        if src_umlaut_untrusted:
            continue
        if not src_discovery_candidate and not src_has_issue:
            continue
        if (
            token_is_german_like(src)
            and not src_has_issue
            and not src_has_hard_marker
            and not src_has_signature
        ):
            continue
        if src_count < DISCOVER_MIN_SOURCE_COUNT and not src_has_issue:
            continue
        if token_is_german_like(src) and token_issue_count[src] == 0 and not src_has_hard_marker:
            continue
        src_canon = canonicalize_translit_token(src)
        src_key = distance_key(src)
        if len(src_key) < 2:
            continue
        if (
            len(src_key) < 3
            and src not in SHORT_TIB_SYLLABLES
            and not src_has_hard_marker
            and not src_has_issue
        ):
            continue
        if src_count > max_rare_freq and src_issue_ratio < 0.34:
            continue

        best: tuple[str, int, int, bool] | None = None
        best_dist = max_edit + 1
        ambiguous = False
        for cand_len in range(len(src_key) - max_edit, len(src_key) + max_edit + 1):
            for cand_tok, cand_count, cand_key in trusted_by_len.get(cand_len, []):
                if src_key[0] != cand_key[0]:
                    c0 = canonicalize_translit_token(src_key[0])
                    d0 = canonicalize_translit_token(cand_key[0])
                    if c0 != d0:
                        continue
                dist = levenshtein_limited(src_key, cand_key, max_edit)
                if dist is None:
                    continue
                if dist < best_dist:
                    best_dist = dist
                    ambiguous = False
                    best = (cand_tok, cand_count, dist, False)
                elif dist == best_dist and best is not None:
                    prev_tok, prev_count, _, _ = best
                    if cand_count > prev_count:
                        best = (cand_tok, cand_count, dist, True)
                    if cand_count >= int(prev_count * 0.7):
                        ambiguous = True
                    else:
                        _ = prev_tok

        if best is None:
            continue
        cand_tok, cand_count, dist, _ = best
        if dist > max_edit:
            continue
        if cand_count < DISCOVER_MIN_SUGGESTED_COUNT:
            continue
        cand_has_signature = token_has_distinctive_tibetan_signature(cand_tok)
        cand_discovery_candidate = token_is_discovery_translit_candidate(cand_tok)
        if not cand_discovery_candidate:
            continue
        cand_issues = validate_translit_token(cand_tok)
        if token_is_german_like(cand_tok) and not cand_has_signature and not token_has_hard_translit_marker(cand_tok):
            continue
        ratio = cand_count / max(src_count, 1)
        if ratio < 3.0:
            continue
        if src_canon == cand_tok:
            continue
        if len(cand_tok) < len(src):
            continue
        if token_drops_vowel_particle_suffix(src, cand_tok):
            continue
        if token_mismatches_vowel_particle_suffix(src, cand_tok):
            continue
        if token_is_trailing_shortening(src, cand_tok):
            continue
        if (
            (
                token_has_protected_sanskrit_nya(src)
                or token_has_protected_palatal_nya(src)
                or token_has_protected_tibetan_nya_cluster(src)
            )
            and "ñ" in src
            and "ṅ" in cand_tok
            and "ñ" not in cand_tok
        ):
            continue
        if token_drops_apostrophe(src, cand_tok):
            continue
        # Avoid discovery drift when both forms are already clean transliteration tokens.
        if (
            dist == 1
            and not src_has_issue
            and not cand_issues
            and token_is_strict_clean_translit(src_canon)
            and token_is_strict_clean_translit(cand_tok)
        ):
            continue
        # If validator already gives a single-char confusable fix, don't discover a different
        # one-char target (typical false positive: onset drift like smy* -> sky*).
        if (
            dist == 1
            and src_only_confusable_issue
            and src_confusable_suggestion is not None
            and cand_tok != src_confusable_suggestion
        ):
            continue

        confusable_i_to_l = token_has_initial_confusable_I(src) and cand_tok.startswith("l")
        if (
            dist == 1
            and not ambiguous
            and (src_has_issue or src_issue_ratio >= 0.4 or src_count <= 3 or confusable_i_to_l)
            and ratio >= DISCOVER_RATIO_MIN_HIGH
        ):
            confidence = "high"
        elif (
            dist <= max_edit
            and (src_has_issue or src_issue_ratio >= 0.55 or src_count <= 2)
            and ratio >= DISCOVER_RATIO_MIN_MEDIUM
        ):
            confidence = "medium"
        else:
            confidence = "low"

        if confidence == "low":
            continue

        patt = DiscoveryPattern(
            source_token=src,
            suggested_token=cand_tok,
            source_count=src_count,
            suggested_count=cand_count,
            edit_distance=dist,
            confidence=confidence,
            ambiguous=ambiguous,
            example=token_examples.get(src, ""),
        )
        discovered[src] = patt
        discovered_rows.append(
            [
                src,
                cand_tok,
                str(src_count),
                str(cand_count),
                str(dist),
                confidence,
                "1" if ambiguous else "0",
                token_examples.get(src, "")[:240],
            ]
        )

    discovered_rows.sort(
        key=lambda r: (
            {"high": 0, "medium": 1}.get(r[5], 9),
            -int(r[3]),
            int(r[4]),
            r[0],
        )
    )
    return discovered, discovered_rows


def choose_rewrite(
    token: str,
    info: LineInfo,
    headword_mem: set[str],
    entry_mem: set[str],
    trusted_lexicon: dict[str, int],
    discovered: dict[str, DiscoveryPattern],
) -> tuple[str, str, str] | None:
    exact_explicit_dst = EXPLICIT_CASE_SENSITIVE_TIER_A_REWRITES.get(token)
    if exact_explicit_dst is not None and info.zone in AUTO_FIX_ZONES:
        return exact_explicit_dst, "A", "explicit_case_sensitive_allowlist"
    low = token.lower()
    if len(low) == 1 and token.isupper():
        return None
    roman_norm = normalize_roman_numeral_confusable_l(token)
    if roman_norm != token and info.zone in {"german_prose", "german_prose_with_translit", "latin_other", "other"}:
        return roman_norm, "A", "citation_roman_l_to_I"
    options: list[tuple[int, str, str, str]] = []
    canon = canonicalize_translit_token(token).lower()
    internal_i_raw = token.replace("I", "i")
    internal_i_canon = canonicalize_translit_token(internal_i_raw).lower() if internal_i_raw != token else low
    explicit_dst = EXPLICIT_TIER_A_REWRITES.get(low)
    if explicit_dst is not None and (info.zone in AUTO_FIX_ZONES or "$" in low):
        return explicit_dst, "A", "explicit_user_allowlist"
    if token_requires_manual_initial_i_review(token, canon):
        return canon, "B", "initial_i_manual_context_review"
    src_translit_like_here = token_is_translit_like(token, info.has_tibetan, info.is_entry_start)
    line_translit_dominant = len(info.translit_tokens) >= max(2, len(info.german_tokens))
    src_has_cue = token_has_translit_cue(token)
    src_has_hard_marker = token_has_hard_translit_marker(token)
    src_has_issue = bool(validate_translit_token(token))
    src_german_like = token_is_german_like(token)
    src_umlaut_untrusted = bool(GERMAN_UMLAUT_RE.search(token)) and not src_has_hard_marker
    line_citation_like = line_is_citation_like(info, info.line_text)
    citation_author_lookup_candidate = token_is_citation_author_lookup_candidate(token)
    citation_safe_tok = citation_safe_confusable_rewrite(token)
    src_initial_i_confusable = token_has_initial_confusable_I(token)
    src_initial_i_german_function = token_is_initial_i_german_function_word(token)
    confusable_nya_to_nga_blocked = token_blocks_nya_to_nga(low, canon)
    canon_backed = canon in headword_mem or canon in entry_mem or canon in trusted_lexicon
    confusable_initial_i_unbacked_blocked = (
        src_initial_i_confusable and canon.startswith("l") and not canon_backed
    )
    canon_has_hard_marker = token_has_hard_translit_marker(canon)
    canon_has_cue = token_has_translit_cue(canon)
    confusable_context_anchor_ok = (
        canon_backed
        or token == token.lower()
        or src_has_hard_marker
        or src_has_cue
        or canon_has_cue
    )
    initial_i_translit_candidate = token_is_initial_i_translit_candidate(token, canon)
    strong_i_context_override = (
        info.zone in ENTRY_STRONG_ZONES
        and info.has_tibetan
        and src_translit_like_here
        and initial_i_translit_candidate
        and (src_has_hard_marker or src_has_cue or canon_has_cue)
    )
    confusable_initial_i_noise_blocked = token_is_initial_i_confusable_noise(token, canon)
    if src_initial_i_confusable and not initial_i_translit_candidate:
        confusable_initial_i_noise_blocked = True
    plain_initial_i_noise = token_is_long_plain_initial_i_noise(token, canon)
    if confusable_initial_i_noise_blocked and initial_i_translit_candidate and (
        canon in headword_mem
        or canon in entry_mem
        or strong_i_context_override
    ):
        # Keep long plain titlecase tokens blocked even if globally frequent.
        if not plain_initial_i_noise and (
            canon in headword_mem or canon in entry_mem or strong_i_context_override or canon_has_cue
        ):
            confusable_initial_i_noise_blocked = False
    confusable_vowel_particle_drop_blocked = token_drops_vowel_particle_suffix(low, canon)
    confusable_vowel_particle_mismatch_blocked = token_mismatches_vowel_particle_suffix(low, canon)
    confusable_shortening_blocked = token_is_trailing_shortening(low, canon)
    confusable_dollar_to_sacute_safe = token_is_safe_dollar_to_sacute(token, canon)
    confusable_dollar_to_sacute_blocked = ("$" in token) and (not confusable_dollar_to_sacute_safe)
    confusable_dotless_i_to_i_safe = token_is_safe_dotless_i_to_i(low, canon)
    confusable_internal_I_to_i_safe = token_is_safe_internal_confusable_I_to_i(token, internal_i_raw)
    internal_i_backed = (
        internal_i_canon in headword_mem
        or internal_i_canon in entry_mem
        or internal_i_canon in trusted_lexicon
    )
    confusable_mixed_caps_noise_blocked = (
        token_is_mixed_caps_confusable_noise(token, canon) and not canon_backed
    )
    confusable_allcaps_noise_blocked = token_is_allcaps_confusable_fragment(token) and not canon_backed

    if (
        internal_i_raw != token
        and confusable_internal_I_to_i_safe
        and info.zone in AUTO_FIX_ZONES
        and not line_citation_like
        and not src_initial_i_confusable
        and not src_umlaut_untrusted
        and internal_i_backed
        and token_is_strict_clean_translit(internal_i_canon)
        and (
            src_translit_like_here
            or info.has_tibetan
            or line_translit_dominant
            or src_has_hard_marker
            or src_has_cue
        )
    ):
        if internal_i_canon in headword_mem:
            options.append((322, internal_i_canon, "A", "confusable_internal_I_to_i_headword"))
        elif internal_i_canon in entry_mem:
            options.append((312, internal_i_canon, "A", "confusable_internal_I_to_i_entry_memory"))
        else:
            options.append((288, internal_i_canon, "A", "confusable_internal_I_to_i_lexicon"))

    if (
        src_initial_i_confusable
        and canon.startswith("l")
        and initial_i_translit_candidate
        and not src_initial_i_german_function
        and info.zone in AUTO_FIX_ZONES
        and (src_translit_like_here or info.has_tibetan or line_translit_dominant)
        and not confusable_initial_i_noise_blocked
        and not plain_initial_i_noise
    ):
        if canon in headword_mem:
            options.append((320, canon, "A", "confusable_initial_I_to_l_headword"))
        elif canon in entry_mem:
            options.append((310, canon, "A", "confusable_initial_I_to_l_entry_memory"))
        elif canon in trusted_lexicon:
            options.append((285, canon, "A", "confusable_initial_I_to_l_lexicon"))
        elif (
            info.zone in ENTRY_STRONG_ZONES
            and info.has_tibetan
            and (src_has_hard_marker or src_has_cue or canon_has_cue)
        ):
            options.append((275, canon, "A", "confusable_initial_I_to_l_strong_context"))
        elif (
            info.zone in {"german_prose_with_translit", "latin_other"}
            and (
                src_has_hard_marker
                or canon_has_hard_marker
                or "-" in token
                or token_has_boundary_translit_cluster(token)
                or token_has_boundary_translit_cluster(canon)
            )
        ):
            options.append((245, canon, "A", "confusable_initial_I_to_l_marked_context"))
        elif (
            info.zone in {"german_prose_with_translit", "latin_other"}
            and line_translit_dominant
            and (
                len(canon) <= 7
                or src_has_hard_marker
                or src_has_cue
                or canon_has_cue
                or "-" in token
                or "'" in token
                or "’" in token
            )
        ):
            options.append((235, canon, "A", "confusable_initial_I_to_l_translit_dominant"))
        else:
            options.append((175, canon, "B", "confusable_initial_I_to_l_context"))

    if (
        canon != low
        and token_is_safe_coda_nya_to_nga(low, canon)
        and info.zone in AUTO_FIX_ZONES
        and token == token.lower()
        and not src_umlaut_untrusted
        and (src_translit_like_here or info.has_tibetan or line_translit_dominant)
        and (canon in headword_mem or canon in entry_mem or canon in trusted_lexicon)
    ):
        options.append((265, canon, "A", "confusable_nya_coda_safe"))

    if (
        canon != low
        and confusable_dotless_i_to_i_safe
        and info.zone in AUTO_FIX_ZONES
        and not src_umlaut_untrusted
        and (
            src_translit_like_here
            or info.has_tibetan
            or line_translit_dominant
            or src_has_hard_marker
            or src_has_cue
            or canon_has_cue
            or (line_citation_like and citation_author_lookup_candidate and citation_safe_tok != token)
        )
    ):
        if canon in headword_mem:
            options.append((295, canon, "A", "confusable_dotless_i_to_i_headword"))
        elif canon in entry_mem:
            options.append((275, canon, "A", "confusable_dotless_i_to_i_entry_memory"))
        elif canon in trusted_lexicon:
            options.append((255, canon, "A", "confusable_dotless_i_to_i_lexicon"))
        elif (
            line_citation_like
            and citation_author_lookup_candidate
            and citation_safe_tok != token
        ):
            options.append((248, canon, "A", "confusable_dotless_i_to_i_citation_name"))
        elif low in DOTLESS_I_TIER_A_ALLOWLIST:
            options.append((247, canon, "A", "confusable_dotless_i_to_i_allowlist"))
        elif canon in DOTLESS_I_GERMAN_CORE_WORDS:
            options.append((245, canon, "A", "confusable_dotless_i_to_i_german_core"))
        elif token == token.lower() and canon in GERMAN_HINT_WORDS and len(canon) >= 3:
            options.append((242, canon, "A", "confusable_dotless_i_to_i_german_hint"))
        elif (
            token == token.lower()
            and token_is_strict_clean_translit(canon)
            and (src_translit_like_here or info.has_tibetan or line_translit_dominant)
            and not (src_german_like and not (src_has_hard_marker or src_has_cue or canon_has_cue))
        ):
            options.append((240, canon, "A", "confusable_dotless_i_to_i_translit_shape"))
        elif token_is_strict_clean_translit(canon) and (
            src_has_hard_marker
            or src_has_cue
            or canon_has_cue
            or "-" in token
            or "'" in token
            or "’" in token
        ):
            options.append((235, canon, "A", "confusable_dotless_i_to_i_context"))
        elif not (line_citation_like and citation_author_lookup_candidate):
            options.append((165, canon, "B", "confusable_dotless_i_to_i_review"))

    # Dotless-i (U+0131) is an OCR confusable in this corpus; the plain-i rewrite
    # is a one-character normalization and safe across auto-fix zones.
    if (
        canon != low
        and confusable_dotless_i_to_i_safe
        and info.zone in AUTO_FIX_ZONES
        and not src_umlaut_untrusted
        and not src_initial_i_confusable
    ):
        options.append((233, canon, "A", "confusable_dotless_i_to_i_safe_char_map"))

    if (
        canon != low
        and confusable_dollar_to_sacute_safe
        and canon in trusted_lexicon
        and info.zone in {"headword_line", "example_tibetan_latin", "tibetan_latin_mixed", "german_prose_with_translit", "latin_other"}
        and (src_translit_like_here or info.has_tibetan or line_translit_dominant)
        and not src_umlaut_untrusted
        and not (src_german_like and not (src_has_hard_marker or src_has_cue or canon_has_cue))
    ):
        options.append((240, canon, "A", "confusable_dollar_to_sacute_lexicon"))

    if (
        canon != low
        and confusable_dollar_to_sacute_safe
        and low in DOLLAR_SACUTE_TIER_A_ALLOWLIST
        and token_is_strict_clean_translit(canon)
        and not src_umlaut_untrusted
    ):
        options.append((238, canon, "A", "confusable_dollar_to_sacute_allowlist"))

    if (
        canon != low
        and confusable_dollar_to_sacute_safe
        and info.zone in ENTRY_STRONG_ZONES
        and token == token.lower()
        and token_is_strict_clean_translit(canon)
        and (src_translit_like_here or info.has_tibetan or line_translit_dominant)
        and not src_umlaut_untrusted
        and not (src_german_like and not (src_has_hard_marker or src_has_cue or canon_has_cue))
    ):
        options.append((237, canon, "A", "confusable_dollar_to_sacute_context_safe"))

    if (
        canon != low
        and token_is_safe_coda_nya_to_nga(low, canon)
        and info.zone in ENTRY_STRONG_ZONES
        and info.has_tibetan
        and (src_translit_like_here or src_has_hard_marker or src_has_issue or src_has_cue)
        and not src_umlaut_untrusted
    ):
        options.append((255, canon, "A", "confusable_nya_coda_safe_strong_context"))

    if (
        canon != low
        and (src_translit_like_here or src_has_hard_marker or src_has_issue)
        and (not src_initial_i_confusable or initial_i_translit_candidate)
        and not src_initial_i_german_function
        and not src_umlaut_untrusted
        and not confusable_nya_to_nga_blocked
        and not confusable_initial_i_noise_blocked
        and not confusable_vowel_particle_drop_blocked
        and not confusable_vowel_particle_mismatch_blocked
        and not confusable_shortening_blocked
        and not confusable_dollar_to_sacute_blocked
        and not confusable_initial_i_unbacked_blocked
        and not confusable_mixed_caps_noise_blocked
    ):
        if canon in headword_mem and info.zone in AUTO_FIX_ZONES:
            options.append((300, canon, "A", "confusable_to_headword"))
        elif canon in entry_mem and info.zone in AUTO_FIX_ZONES:
            options.append((260, canon, "A", "confusable_to_entry_memory"))
        elif (
            info.zone in ENTRY_STRONG_ZONES
            and info.has_tibetan
            and (src_translit_like_here or src_has_hard_marker or src_has_issue)
            and confusable_context_anchor_ok
            and not confusable_allcaps_noise_blocked
        ):
            options.append((180, canon, "B", "confusable_context"))
        elif (
            canon in trusted_lexicon
            and info.zone in {"german_prose_with_translit", "latin_other"}
            and token == token.lower()
            and (src_has_hard_marker or src_has_issue)
            and (src_translit_like_here or line_translit_dominant)
            and not (src_german_like and not (src_has_hard_marker or src_has_cue or canon_has_cue))
        ):
            options.append((150, canon, "B", "confusable_global_lexicon"))

    if (
        canon != low
        and info.zone
        in {
            "headword_line",
            "example_tibetan_latin",
            "tibetan_latin_mixed",
            "german_prose",
            "german_prose_with_translit",
            "latin_other",
        }
        and token_is_safe_hyphenated_initial_i_to_l_translit(token, canon)
    ):
        options.append((252, canon, "A", "confusable_hyphenated_I_to_l_translit"))

    if (
        canon != low
        and info.zone in {"german_prose", "german_prose_with_translit", "latin_other"}
        and token_is_citation_confusable_i_to_l_candidate(token, canon)
        and line_citation_like
        and token_looks_like_known_citation_author(token)
    ):
        options.append((140, canon, "B", "citation_confusable_I_to_l"))

    patt = discovered.get(low)
    if patt is not None:
        cand = patt.suggested_token
        cand_has_cue = token_has_translit_cue(cand)
        cand_has_hard_marker = token_has_hard_translit_marker(cand)
        cand_is_generic_short = token_is_discovery_generic_short_target(cand)
        src_discovery_candidate = token_is_discovery_translit_candidate(token)
        cand_discovery_candidate = token_is_discovery_translit_candidate(cand)
        discover_ratio = patt.suggested_count / max(patt.source_count, 1)
        discover_vowel_particle_drop_blocked = token_drops_vowel_particle_suffix(low, cand)
        discover_vowel_particle_mismatch_blocked = token_mismatches_vowel_particle_suffix(low, cand)
        discover_apostrophe_drop_blocked = token_drops_apostrophe(low, cand)
        discover_shortening_blocked = token_is_trailing_shortening(low, cand)
        discover_nya_to_nga_blocked = token_blocks_nya_to_nga(low, cand)
        discovery_auto_ok = (
            patt.confidence == "high"
            and not patt.ambiguous
            and patt.source_count >= DISCOVER_MIN_SOURCE_COUNT
            and patt.suggested_count >= DISCOVER_MIN_SUGGESTED_COUNT
            and discover_ratio >= DISCOVER_RATIO_MIN_HIGH
            and len(cand) >= 3
            and len(cand) >= len(low)
            and info.zone in AUTO_FIX_ZONES
            and token == token.lower()
            and (src_has_hard_marker or cand_has_hard_marker or src_has_issue)
            and not src_umlaut_untrusted
            and not (src_german_like and not src_has_cue)
            and not discover_vowel_particle_drop_blocked
            and not discover_vowel_particle_mismatch_blocked
            and not discover_apostrophe_drop_blocked
            and not discover_shortening_blocked
            and not discover_nya_to_nga_blocked
            and src_discovery_candidate
            and cand_discovery_candidate
        )
        if cand in headword_mem and discovery_auto_ok:
            options.append((290, cand, "A", "discover_to_headword"))
        elif cand in entry_mem and discovery_auto_ok:
            options.append((250, cand, "A", "discover_to_entry_memory"))
        elif (
            info.zone in ENTRY_STRONG_ZONES
            and info.has_tibetan
            and patt.confidence == "high"
            and not patt.ambiguous
            and token == token.lower()
            and patt.source_count >= DISCOVER_MIN_SOURCE_COUNT
            and patt.suggested_count >= DISCOVER_MIN_SUGGESTED_COUNT
            and discover_ratio >= DISCOVER_RATIO_MIN_HIGH
            and src_discovery_candidate
            and cand_discovery_candidate
            and (src_translit_like_here or src_has_hard_marker or src_has_issue or src_has_cue)
            and not (src_german_like and not (src_has_hard_marker or src_has_issue or src_has_cue))
            and not src_umlaut_untrusted
            and not discover_vowel_particle_drop_blocked
            and not discover_vowel_particle_mismatch_blocked
            and not discover_apostrophe_drop_blocked
            and not discover_shortening_blocked
            and not discover_nya_to_nga_blocked
            and (not cand_is_generic_short or cand in headword_mem or cand in entry_mem)
        ):
            options.append((225, cand, "A", "discover_high_context_translit"))
        elif (
            info.zone in ENTRY_STRONG_ZONES
            and info.has_tibetan
            and token == token.lower()
            and src_discovery_candidate
            and cand_discovery_candidate
            and (not patt.ambiguous or cand in headword_mem or cand in entry_mem)
            and (src_translit_like_here or src_has_hard_marker or src_has_issue or src_has_cue)
            and not (src_german_like and not (src_has_hard_marker or src_has_issue or src_has_cue))
            and not src_umlaut_untrusted
            and not discover_vowel_particle_drop_blocked
            and not discover_vowel_particle_mismatch_blocked
            and not discover_apostrophe_drop_blocked
            and not discover_shortening_blocked
            and patt.source_count >= DISCOVER_MIN_SOURCE_COUNT
            and patt.suggested_count >= DISCOVER_MIN_SUGGESTED_COUNT
            and discover_ratio >= DISCOVER_RATIO_MIN_MEDIUM
            and not discover_nya_to_nga_blocked
            and (not cand_is_generic_short or cand in headword_mem or cand in entry_mem)
        ):
            options.append((170, cand, "B", f"discover_{patt.confidence}_context"))
        elif (
            info.zone == "german_prose_with_translit"
            and cand in trusted_lexicon
            and patt.confidence == "high"
            and patt.source_count >= DISCOVER_MIN_SOURCE_COUNT
            and patt.suggested_count >= DISCOVER_MIN_SUGGESTED_COUNT
            and discover_ratio >= DISCOVER_RATIO_MIN_HIGH
            and token == token.lower()
            and src_discovery_candidate
            and cand_discovery_candidate
            and line_translit_dominant
            and (src_translit_like_here or src_has_hard_marker or src_has_issue)
            and (src_has_hard_marker or src_has_issue or (src_has_cue and len(low) >= 4))
            and not (src_german_like and not (src_has_hard_marker or src_has_issue or src_has_cue))
            and not src_umlaut_untrusted
            and not discover_vowel_particle_drop_blocked
            and not discover_vowel_particle_mismatch_blocked
            and not discover_apostrophe_drop_blocked
            and not discover_shortening_blocked
            and not discover_nya_to_nga_blocked
            and not cand_is_generic_short
        ):
            options.append((145, cand, "B", f"discover_{patt.confidence}_global"))

    if not options:
        return None
    options.sort(key=lambda x: x[0], reverse=True)
    _, dst, tier, reason = options[0]
    if dst == low:
        return None
    return dst, tier, reason


def apply_entry_aware_corrections(
    page_lines: list[list[str]],
    line_infos: list[LineInfo],
    headword_memory: dict[int, set[str]],
    entry_memory: dict[int, set[str]],
    trusted_lexicon: dict[str, int],
    discovered: dict[str, DiscoveryPattern],
) -> tuple[str, list[list[str]], list[list[str]]]:
    info_by_key = {(li.page, li.line): li for li in line_infos}
    change_rows: list[list[str]] = []
    review_rows: list[list[str]] = []
    corrected_pages: list[str] = []

    for page_idx, lines in enumerate(page_lines, start=1):
        corrected_lines: list[str] = []
        for line_idx, line in enumerate(lines, start=1):
            info = info_by_key.get((page_idx, line_idx))
            if info is None or info.entry_id == 0 or not line:
                corrected_lines.append(line)
                continue

            head = headword_memory.get(info.entry_id, set())
            mem = entry_memory.get(info.entry_id, set())

            def repl(m: re.Match[str]) -> str:
                tok = m.group(0)
                if ALL_CAPS_RE.fullmatch(tok):
                    return tok
                choice: tuple[str, str, str] | None = None
                if tok.lower() == "$in":
                    nxt = OCR_LATIN_TOKEN_RE.search(line, m.end())
                    if nxt is not None:
                        nxt_low = canonicalize_translit_token(nxt.group(0)).lower()
                        if nxt_low == "tu":
                            choice = ("śin", "A", "explicit_user_allowlist_in_tu")
                if choice is None:
                    choice = choose_rewrite(tok, info, head, mem, trusted_lexicon, discovered)
                if choice is None:
                    return tok
                dst, tier, reason = choice
                dst_case = apply_case_pattern(tok, dst)
                if dst_case == tok:
                    return tok
                guard_block_reason = rewrite_hard_guard_block_reason(
                    tok, dst_case, reason, stage="entry"
                )
                row = [
                    str(info.page),
                    str(info.line),
                    str(info.entry_id),
                    info.zone,
                    tok,
                    dst_case,
                    tier,
                    reason,
                    "1" if tier == "A" else "0",
                    info.line_text[:240],
                ]
                if tier == "A" and guard_block_reason is not None:
                    review_rows.append(
                        [
                            str(info.page),
                            str(info.line),
                            str(info.entry_id),
                            info.zone,
                            tok,
                            dst_case,
                            "B",
                            f"hard_guard_{guard_block_reason}__{reason}",
                            "0",
                            info.line_text[:240],
                        ]
                    )
                    return tok
                if tier == "A":
                    change_rows.append(row)
                    return dst_case
                if guard_block_reason is not None:
                    row[7] = f"hard_guard_{guard_block_reason}__{reason}"
                review_rows.append(row)
                return tok

            corrected_lines.append(OCR_LATIN_TOKEN_RE.sub(repl, line))
        corrected_pages.append("\n".join(corrected_lines))

    return "\f".join(corrected_pages), change_rows, review_rows


def apply_citation_name_normalization(
    corrected_text: str,
    line_infos: list[LineInfo],
) -> tuple[str, list[list[str]], list[list[str]], list[list[str]], int]:
    pages = [page.split("\n") for page in corrected_text.split("\f")]
    info_by_key = {(li.page, li.line): li for li in line_infos}
    family_counts: dict[str, Counter[str]] = defaultdict(Counter)
    family_year_hits: Counter[str] = Counter()
    family_examples: dict[str, str] = {}
    citation_like_masks: dict[int, list[bool]] = {}
    citation_like_base_masks: dict[int, list[bool]] = {}

    for page_idx, lines in enumerate(pages, start=1):
        base_mask: list[bool] = []
        for line_idx, line in enumerate(lines, start=1):
            info = info_by_key.get((page_idx, line_idx))
            is_like = bool(
                info is not None
                and line
                and line_is_citation_like(info, line)
            )
            base_mask.append(is_like)
        expanded_mask = base_mask[:]
        for idx, is_like in enumerate(base_mask):
            if is_like:
                continue
            line_idx = idx + 1
            info = info_by_key.get((page_idx, line_idx))
            line = lines[idx]
            if info is None or info.entry_id == 0 or not line:
                continue
            neighbor_citation = False
            lo = max(0, idx - 6)
            hi = min(len(base_mask), idx + 7)
            for neighbor_idx in range(lo, hi):
                if neighbor_idx == idx or not base_mask[neighbor_idx]:
                    continue
                neighbor_info = info_by_key.get((page_idx, neighbor_idx + 1))
                if neighbor_info is None:
                    continue
                if neighbor_info.entry_id != info.entry_id:
                    continue
                neighbor_citation = True
                break
            if not neighbor_citation:
                continue
            if OCR_LATIN_TOKEN_RE.search(line):
                expanded_mask[idx] = True
        citation_like_masks[page_idx] = expanded_mask
        citation_like_base_masks[page_idx] = base_mask

    for page_idx, lines in enumerate(pages, start=1):
        for line_idx, line in enumerate(lines, start=1):
            info = info_by_key.get((page_idx, line_idx))
            if info is None or info.entry_id == 0 or not line:
                continue
            if not citation_like_masks[page_idx][line_idx - 1]:
                continue
            for m in OCR_LATIN_TOKEN_RE.finditer(line):
                tok = m.group(0)
                if not token_is_citation_person_name_candidate(tok):
                    continue
                key = citation_name_family_key(tok)
                family_counts[key][tok] += 1
                if key not in family_examples:
                    family_examples[key] = line[:240]
                if token_occurrence_near_year(line, m.start(), m.end()):
                    family_year_hits[key] += 1

    author_lexicon = build_citation_author_lexicon(family_counts, family_year_hits)
    family_to_canon: dict[str, str] = {}
    family_report_rows: list[list[str]] = []
    for key, variants in family_counts.items():
        total = sum(variants.values())
        if total < 2:
            continue
        if family_year_hits[key] == 0:
            continue
        caps = [(tok, cnt) for tok, cnt in variants.items() if tok.isupper()]
        if caps:
            caps.sort(key=lambda kv: (kv[1], len(kv[0]), kv[0]), reverse=True)
            canon = caps[0][0]
        else:
            best_tok, _ = max(variants.items(), key=lambda kv: (kv[1], token_upper_ratio(kv[0]), len(kv[0])))
            if token_upper_ratio(best_tok) < 0.62:
                continue
            canon = best_tok.upper()
        non_canon_total = sum(cnt for tok, cnt in variants.items() if tok != canon)
        if non_canon_total == 0:
            continue
        family_to_canon[key] = canon
        top_variants = sorted(variants.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[:8]
        family_report_rows.append(
            [
                key,
                canon,
                str(total),
                str(family_year_hits[key]),
                str(len(variants)),
                str(non_canon_total),
                " | ".join(f"{tok}:{cnt}" for tok, cnt in top_variants),
                family_examples.get(key, ""),
            ]
        )

    change_rows: list[list[str]] = []
    review_rows: list[list[str]] = []
    for page_idx, lines in enumerate(pages, start=1):
        for line_idx, line in enumerate(lines, start=1):
            info = info_by_key.get((page_idx, line_idx))
            if info is None or not line:
                continue
            # Apply rewrites on the expanded citation mask as well so wrapped
            # bibliography lines within the same entry get normalized.
            if not citation_like_masks[page_idx][line_idx - 1]:
                continue
            line_is_base_citation = citation_like_base_masks[page_idx][line_idx - 1]

            def repl(m: re.Match[str]) -> str:
                tok = m.group(0)

                def apply_guarded(dst_tok: str, reason: str) -> str:
                    guard_block_reason = rewrite_hard_guard_block_reason(
                        tok, dst_tok, reason, stage="citation"
                    )
                    if guard_block_reason is not None:
                        review_rows.append(
                            [
                                str(info.page),
                                str(info.line),
                                str(info.entry_id),
                                info.zone,
                                tok,
                                dst_tok,
                                "B",
                                f"hard_guard_{guard_block_reason}__{reason}",
                                "0",
                                line[:240],
                            ]
                        )
                        return tok
                    change_rows.append(
                        [
                            str(info.page),
                            str(info.line),
                            str(info.entry_id),
                            info.zone,
                            tok,
                            dst_tok,
                            "A",
                            reason,
                            "1",
                            line[:240],
                        ]
                    )
                    return dst_tok

                safe_tok = citation_safe_confusable_rewrite(tok)
                if token_is_citation_siglum_candidate(tok) and safe_tok != tok:
                    return apply_guarded(safe_tok, "citation_siglum_confusable_map")
                if info.entry_id == 0:
                    return tok

                if not token_is_citation_author_lookup_candidate(tok):
                    return tok
                near_year = token_occurrence_near_year(line, m.start(), m.end())
                noisy_shape = token_has_citation_ocr_noise_shape(tok) or (safe_tok != tok)
                person_candidate = token_is_citation_person_name_candidate(safe_tok)
                lex_canon = None
                if person_candidate:
                    lex_canon = match_citation_author_lexicon(safe_tok, author_lexicon)
                if lex_canon is not None and tok != lex_canon:
                    # Keep lexicon promotion conservative off-year unless OCR-noisy.
                    if not near_year and not noisy_shape:
                        lex_canon = None
                    # Avoid forcing clean titlecase forms to all-caps unless the token
                    # shows an OCR-noise pattern (e.g. ScHuH, lMAEDA, Tuccı).
                    if (
                        lex_canon is not None
                        and
                        lex_canon.isupper()
                        and tok[:1].isupper()
                        and tok[1:].islower()
                        and not token_has_citation_ocr_noise_shape(tok)
                    ):
                        lex_canon = None
                if lex_canon is not None and tok != lex_canon:
                    return apply_guarded(lex_canon, "citation_author_lexicon")
                canon = None
                if person_candidate:
                    key = citation_name_family_key(safe_tok)
                    canon = family_to_canon.get(key)
                if canon is not None and tok != canon:
                    if not near_year and not noisy_shape:
                        canon = None
                    # Keep this step as a strict case normalization pass.
                    if canon is not None and safe_tok.casefold() == canon.casefold():
                        return apply_guarded(canon, "citation_caps_name_normalize")

                if safe_tok != tok:
                    # On non-base (neighbor-expanded) lines, keep this fallback
                    # mapping limited to OCR-noisy citation token shapes.
                    if not line_is_base_citation and not noisy_shape:
                        return tok
                    return apply_guarded(safe_tok, "citation_confusable_safe_map")

                return tok

            def repl_digit_siglum(m: re.Match[str]) -> str:
                prefix = m.group(1)
                tok = m.group(2)
                safe_tok = citation_safe_confusable_rewrite(tok)
                if safe_tok == tok:
                    return m.group(0)
                guard_block_reason = rewrite_hard_guard_block_reason(
                    tok, safe_tok, "citation_siglum_confusable_map", stage="citation"
                )
                if guard_block_reason is not None:
                    review_rows.append(
                        [
                            str(info.page),
                            str(info.line),
                            str(info.entry_id),
                            info.zone,
                            tok,
                            safe_tok,
                            "B",
                            f"hard_guard_{guard_block_reason}__citation_siglum_confusable_map",
                            "0",
                            line[:240],
                        ]
                    )
                    return m.group(0)
                change_rows.append(
                    [
                        str(info.page),
                        str(info.line),
                        str(info.entry_id),
                        info.zone,
                        tok,
                        safe_tok,
                        "A",
                        "citation_siglum_confusable_map",
                        "1",
                        line[:240],
                    ]
                )
                return prefix + safe_tok

            line = CITATION_SIGLUM_DIGIT_ARTIFACT_RE.sub(repl_digit_siglum, line)
            lines[line_idx - 1] = OCR_LATIN_TOKEN_RE.sub(repl, line)

    family_report_rows.sort(key=lambda r: (-int(r[5]), -int(r[2]), r[0]))
    normalized_text = "\f".join("\n".join(lines) for lines in pages)
    return normalized_text, change_rows, review_rows, family_report_rows, len(family_to_canon)


def sanskrit_safe_normalize_token(token: str) -> str:
    return token.translate(SANSKRIT_SAFE_CHAR_MAP)


def sanskrit_normalize_jn_cluster_token(token: str) -> str:
    def repl(m: re.Match[str]) -> str:
        src = m.group(0)
        if src.isupper():
            return "JÑ"
        if src[:1].isupper():
            return "Jñ"
        return "jñ"

    return SANSKRIT_JN_VOWEL_CLUSTER_RE.sub(repl, token)


def sanskrit_normalize_jn_cluster_compound_token(token: str) -> tuple[str, bool, bool]:
    parts = compound_token_parts(token)
    if len(parts) == 1:
        normalized = sanskrit_normalize_jn_cluster_token(token)
        return normalized, normalized != token, False

    out_parts: list[str] = []
    changed = False
    has_sanskrit_segment = False
    for part in parts:
        if part in {"-", "/"}:
            out_parts.append(part)
            continue
        seg_lang = classify_compound_segment_language(part)
        if seg_lang == "sanskrit":
            has_sanskrit_segment = True
            norm = sanskrit_normalize_jn_cluster_token(part)
            out_parts.append(norm)
            if norm != part:
                changed = True
            continue
        out_parts.append(part)

    return "".join(out_parts), changed, has_sanskrit_segment


def compound_token_parts(token: str) -> list[str]:
    if "-" not in token and "/" not in token:
        return [token]
    return [part for part in COMPOUND_SEGMENT_SPLIT_RE.split(token) if part]


def token_has_hard_sanskrit_marker(token: str) -> bool:
    low = sanskrit_safe_normalize_token(token).lower()
    if "$" in token:
        return True
    if SANSKRIT_DIACRITIC_RE.search(token):
        return True
    if SANSKRIT_CLUSTER_RE.search(low):
        return True
    if SANSKRIT_ASCII_CLUSTER_STRONG_RE.search(low):
        return True
    return False


def token_has_german_lexical_cue_for_sanskrit(segment: str) -> bool:
    low = segment.lower()
    low_norm = sanskrit_safe_normalize_token(segment).lower()
    if low in GERMAN_HINT_WORDS:
        return True
    if token_is_initial_i_german_function_word(segment):
        return True
    if "über" in low:
        return True
    if "gottheit" in low:
        return True
    if re.search(r"(?:^|-)verdienst", low_norm):
        return True
    if re.search(r"(?:^|-)haltung", low_norm):
        return True
    if re.search(r"(?:^|-)abgekl", low_norm):
        return True
    if re.search(r"l[äa]ndern?$", low):
        return True
    if low_norm.endswith(GERMAN_WORD_SUFFIXES):
        return True
    return False


def classify_compound_segment_language(segment: str) -> str:
    if not segment or segment in {"-", "/"}:
        return "unknown"
    hard_sanskrit = token_has_hard_sanskrit_marker(segment)
    german_lexical = token_has_german_lexical_cue_for_sanskrit(segment)
    low_norm = sanskrit_safe_normalize_token(segment).lower()
    soft_confusable = any(ch in segment for ch in "$ãÃıñÑäÄ")
    if token_has_distinctive_tibetan_signature(segment):
        return "sanskrit"
    if hard_sanskrit and not german_lexical:
        return "sanskrit"
    if german_lexical and not hard_sanskrit:
        return "german"
    if hard_sanskrit and german_lexical:
        return "german"
    if soft_confusable and re.search(r"[aāiīuūeo]$", low_norm):
        return "sanskrit"
    if token_is_german_like(segment):
        return "german"
    return "unknown"


def sanskrit_safe_normalize_compound_token(token: str) -> tuple[str, bool, bool]:
    parts = compound_token_parts(token)
    if len(parts) == 1:
        return sanskrit_safe_normalize_token(token), False, False

    out_parts: list[str] = []
    changed = False
    has_sanskrit_segment = False
    for part in parts:
        if part in {"-", "/"}:
            out_parts.append(part)
            continue
        seg_lang = classify_compound_segment_language(part)
        if seg_lang == "sanskrit":
            has_sanskrit_segment = True
            norm = sanskrit_safe_normalize_token(part)
            out_parts.append(norm)
            if norm != part:
                changed = True
            continue
        out_parts.append(part)

    return "".join(out_parts), changed, has_sanskrit_segment


def apply_case_shape(src: str, dst: str) -> str:
    if not src:
        return dst
    if src.isupper():
        return dst.upper()
    if src[0].isupper() and src[1:].islower():
        return dst[:1].upper() + dst[1:]
    return dst


def apply_sanskrit_override_chain(token: str, max_hops: int = 4) -> tuple[str, bool]:
    """Apply promoted/high-frequency overrides transitively for multi-step OCR forms."""
    current = token
    changed = False
    seen: set[str] = set()
    for _ in range(max_hops):
        key = current.lower()
        if key in seen:
            break
        seen.add(key)
        target = SANSKRIT_TIER_A_OVERRIDES.get(key)
        if not target:
            break
        nxt = apply_case_shape(current, target)
        if nxt == current:
            break
        current = nxt
        changed = True
    return current, changed


def sanskrit_family_key(token: str) -> str:
    norm = sanskrit_safe_normalize_token(token)
    norm = unicodedata.normalize("NFC", norm).lower()
    norm = norm.translate(SKELETON_MAP)
    return re.sub(r"[^a-z]", "", norm)


def sanskrit_token_signature_score(token: str) -> int:
    low = sanskrit_safe_normalize_token(token).lower()
    score = 0
    if SANSKRIT_DIACRITIC_RE.search(token):
        score += 3
    if SANSKRIT_CLUSTER_RE.search(low):
        score += 3
    if SANSKRIT_ASCII_CLUSTER_RE.search(low):
        score += 2
    if SANSKRIT_ENDING_RE.search(low):
        score += 1
    if SANSKRIT_TOKEN_NOISE_RE.search(token):
        score += 1
    if low in GERMAN_HINT_WORDS:
        score -= 5
    elif token_is_german_like(token) and not (
        SANSKRIT_DIACRITIC_RE.search(token)
        or SANSKRIT_CLUSTER_RE.search(low)
        or SANSKRIT_ASCII_CLUSTER_RE.search(low)
    ):
        score -= 2
    return score


def token_has_strong_sanskrit_marker(token: str) -> bool:
    low = sanskrit_safe_normalize_token(token).lower()
    if "$" in token:
        return True
    if SANSKRIT_DIACRITIC_RE.search(token):
        return True
    if SANSKRIT_CLUSTER_RE.search(low):
        return True
    if SANSKRIT_ASCII_CLUSTER_STRONG_RE.search(low):
        return True
    if SANSKRIT_ENDING_RE.search(low):
        return True
    return False


def token_is_pure_german_for_sanskrit_queue(token: str, line_text: str) -> bool:
    parts = compound_token_parts(token)
    if len(parts) > 1:
        has_sanskrit = False
        has_german = False
        has_unknown = False
        for part in parts:
            if part in {"-", "/"}:
                continue
            seg_lang = classify_compound_segment_language(part)
            if seg_lang == "sanskrit":
                has_sanskrit = True
            elif seg_lang == "german":
                has_german = True
            else:
                has_unknown = True
        if has_sanskrit:
            return False
        if has_german and not has_unknown:
            return True

    low = token.lower()
    low_norm = sanskrit_safe_normalize_token(token).lower()
    if low in GERMAN_HINT_WORDS:
        return True
    if token_is_initial_i_german_function_word(token):
        return True
    # Hard German lexical cues should override Sanskrit-marker heuristics.
    if token_has_german_lexical_cue_for_sanskrit(token):
        return True
    if token_has_strong_sanskrit_marker(token):
        return False
    if token_is_german_like(token):
        # Capitalization alone is not sufficient evidence; Sanskrit proper names
        # are often title-cased in bibliographic contexts.
        if token[:1].isupper() and not GERMAN_UMLAUT_RE.search(token) and not low.endswith(GERMAN_WORD_SUFFIXES):
            pass
        else:
            return True
    if low_norm.endswith(GERMAN_WORD_SUFFIXES):
        return True
    # In pure citation lines with year/citation cues, keep tokens unless they are clearly German.
    if (CITATION_YEAR_RE.search(line_text) or CITATION_CUE_RE.search(line_text)) and token_has_strong_sanskrit_marker(token):
        return False
    return False


def token_is_safe_sanskrit_char_map_rewrite(src: str, dst: str) -> bool:
    if src == dst or len(src) != len(dst):
        return False
    changed = False
    for s_ch, d_ch in zip(src, dst):
        if s_ch == d_ch:
            continue
        if SANSKRIT_SAFE_CHAR_MAP.get(ord(s_ch)) == d_ch:
            changed = True
            continue
        return False
    return changed


def line_has_singleton_sanskrit_gate(line_text: str, zone: str) -> bool:
    if SANSKRIT_MVY_CUE_RE.search(line_text):
        return True
    if zone in {"german_prose_with_translit", "latin_other"} and (
        CITATION_CUE_RE.search(line_text)
        or CITATION_YEAR_RE.search(line_text)
        or CITATION_SPLIT_YEAR_RE.search(line_text)
        or SANSKRIT_LEX_CUE_RE.search(line_text)
    ):
        return True
    return False


def sanskrit_token_quality(token: str) -> int:
    low = sanskrit_safe_normalize_token(token).lower()
    quality = 0
    if SANSKRIT_DIACRITIC_RE.search(token):
        quality += 4
    if SANSKRIT_CLUSTER_RE.search(low):
        quality += 3
    if SANSKRIT_ASCII_CLUSTER_RE.search(low):
        quality += 2
    if SANSKRIT_ENDING_RE.search(low):
        quality += 1
    if "$" in token:
        quality -= 3
    if SANSKRIT_UMLAUT_RE.search(token):
        quality -= 2
    if "ã" in token or "Ã" in token:
        quality -= 2
    if "ı" in token:
        quality -= 1
    if ALL_CAPS_RE.fullmatch(token):
        quality -= 3
    return quality


def token_is_probable_sanskrit(token: str, context_score: int, line_text: str) -> bool:
    if len(token) < 4:
        return False
    if not OCR_LATIN_TOKEN_RE.fullmatch(token):
        return False
    if ROMAN_NUMERAL_RE.fullmatch(token):
        return False
    if ALL_CAPS_RE.fullmatch(token):
        return False
    if TIBETAN_APOSTROPHE_PARTICLE_RE.fullmatch(token):
        return False
    low = token.lower()
    if low in GERMAN_HINT_WORDS:
        return False
    if token_is_initial_i_german_function_word(token):
        return False
    if token_is_pure_german_for_sanskrit_queue(token, line_text):
        return False
    sig = sanskrit_token_signature_score(token)
    if context_score >= SANSKRIT_AUTO_CONTEXT_MIN + 2:
        threshold = 2
    elif context_score >= SANSKRIT_AUTO_CONTEXT_MIN:
        threshold = 2
    elif context_score >= 2:
        threshold = 3
    else:
        threshold = 5
    if SANSKRIT_MVY_CUE_RE.search(line_text):
        threshold = max(1, threshold - 1)
    return sig >= threshold


def build_sanskrit_context_scores(
    pages: list[list[str]],
    line_infos: list[LineInfo],
) -> dict[tuple[int, int], int]:
    info_by_key = {(li.page, li.line): li for li in line_infos}
    base_scores: dict[tuple[int, int], int] = {}

    for page_idx, lines in enumerate(pages, start=1):
        for line_idx, line in enumerate(lines, start=1):
            key = (page_idx, line_idx)
            info = info_by_key.get(key)
            score = 0
            if info is not None and info.entry_id != 0 and line:
                if SANSKRIT_MVY_CUE_RE.search(line):
                    score += 5
                if SANSKRIT_GENERAL_CUE_RE.search(line):
                    score += 2
                if SANSKRIT_LEX_CUE_RE.search(line):
                    score += 1
                if info.zone in {"german_prose_with_translit", "latin_other", "other"}:
                    score += 1
            base_scores[key] = score

    context_scores = dict(base_scores)
    neighbor_boosts = {1: 2, 2: 1}
    for page_idx, lines in enumerate(pages, start=1):
        line_count = len(lines)
        for line_idx in range(1, line_count + 1):
            key = (page_idx, line_idx)
            base = base_scores.get(key, 0)
            if base < SANSKRIT_AUTO_CONTEXT_MIN:
                continue
            info = info_by_key.get(key)
            if info is None or info.entry_id == 0:
                continue
            for dist, boost in neighbor_boosts.items():
                for sign in (-1, 1):
                    n_line = line_idx + (sign * dist)
                    if n_line < 1 or n_line > line_count:
                        continue
                    n_key = (page_idx, n_line)
                    n_info = info_by_key.get(n_key)
                    if n_info is None or n_info.entry_id != info.entry_id:
                        continue
                    if not lines[n_line - 1]:
                        continue
                    candidate = base_scores.get(n_key, 0) + boost
                    if candidate > context_scores.get(n_key, 0):
                        context_scores[n_key] = candidate
    return context_scores


def apply_sanskrit_normalization(
    corrected_text: str,
    line_infos: list[LineInfo],
) -> tuple[str, list[list[str]], list[list[str]], list[list[str]], int]:
    pages = [page.split("\n") for page in corrected_text.split("\f")]
    info_by_key = {(li.page, li.line): li for li in line_infos}
    context_scores = build_sanskrit_context_scores(pages, line_infos)

    family_counts: dict[str, Counter[str]] = defaultdict(Counter)
    family_context: dict[str, Counter[str]] = defaultdict(Counter)
    family_examples: dict[str, str] = {}
    char_norm_pair_counts: Counter[tuple[str, str]] = Counter()

    for page_idx, lines in enumerate(pages, start=1):
        for line_idx, line in enumerate(lines, start=1):
            if not line:
                continue
            info = info_by_key.get((page_idx, line_idx))
            if info is None or info.entry_id == 0:
                continue
            ctx = context_scores.get((page_idx, line_idx), 0)
            for m in OCR_LATIN_TOKEN_RE.finditer(line):
                tok = m.group(0)
                if not token_is_probable_sanskrit(tok, ctx, line):
                    continue
                key = sanskrit_family_key(tok)
                if len(key) < 4:
                    continue
                safe_norm = sanskrit_safe_normalize_token(tok)
                if "-" in tok or "/" in tok:
                    compound_norm, _, has_sanskrit_segment = sanskrit_safe_normalize_compound_token(tok)
                    safe_norm = compound_norm if has_sanskrit_segment else tok
                if safe_norm != tok and token_is_safe_sanskrit_char_map_rewrite(tok, safe_norm):
                    char_norm_pair_counts[(tok.lower(), safe_norm.lower())] += 1
                family_counts[key][tok] += 1
                family_context[key][tok] += ctx
                family_examples.setdefault(key, line[:240])

    family_to_canon: dict[str, str] = {}
    family_confidence: dict[str, str] = {}
    family_report_rows: list[list[str]] = []
    for key, variants in family_counts.items():
        family_total = sum(variants.values())
        if family_total < 2:
            continue
        scored: list[tuple[int, int, int, int, str]] = []
        for tok, cnt in variants.items():
            qual = sanskrit_token_quality(tok)
            ctx_sum = family_context[key].get(tok, 0)
            weighted = (cnt * 10) + (ctx_sum * 2) + (qual * 3)
            scored.append((weighted, qual, cnt, ctx_sum, tok))
        scored.sort(reverse=True)
        canon = scored[0][4]
        family_to_canon[key] = canon
        noncanon_total = sum(cnt for tok, cnt in variants.items() if tok != canon)
        score_gap = scored[0][0] - (scored[1][0] if len(scored) > 1 else 0)
        if noncanon_total == 0:
            confidence = "none"
        elif score_gap >= 12 and scored[0][2] >= 2:
            confidence = "high"
        elif score_gap >= 6:
            confidence = "medium"
        else:
            confidence = "low"
        family_confidence[key] = confidence
        top_variants = sorted(variants.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[:10]
        family_report_rows.append(
            [
                key,
                canon,
                str(family_total),
                str(len(variants)),
                str(noncanon_total),
                confidence,
                " | ".join(f"{tok}:{cnt}" for tok, cnt in top_variants),
                family_examples.get(key, ""),
            ]
        )

    change_rows: list[list[str]] = []
    review_rows: list[list[str]] = []
    for page_idx, lines in enumerate(pages, start=1):
        for line_idx, line in enumerate(lines, start=1):
            if not line:
                continue
            info = info_by_key.get((page_idx, line_idx))
            zone = info.zone if info is not None else "other"
            entry_id = str(info.entry_id) if info is not None else "0"
            ctx = context_scores.get((page_idx, line_idx), 0)
            updated_line = line

            # Handle the known split citation form "Rästrapa-\nlapariprcch...":
            # normalize across the break to avoid duplicate-prefix rewrites.
            if line_idx > 1 and LAPARIPRCCHA_SPLIT_CURR_RE.search(updated_line):
                prev_line = lines[line_idx - 2]
                if RASTRAPA_SPLIT_PREV_RE.search(prev_line):
                    prev_replaced = RASTRAPA_SPLIT_PREV_RE.sub("rāṣṭrapāla", prev_line)
                    if prev_replaced != prev_line:
                        prev_info = info_by_key.get((page_idx, line_idx - 1))
                        prev_zone = prev_info.zone if prev_info is not None else "other"
                        prev_entry_id = str(prev_info.entry_id) if prev_info is not None else "0"
                        change_rows.append(
                            [
                                str(page_idx),
                                str(line_idx - 1),
                                prev_entry_id,
                                prev_zone,
                                "Rästrapa-",
                                "rāṣṭrapāla",
                                "A",
                                "explicit_rastrapala_split_prev",
                                "1",
                                prev_line[:240],
                            ]
                        )
                        lines[line_idx - 2] = prev_replaced
                    match = LAPARIPRCCHA_SPLIT_CURR_RE.search(updated_line)
                    src_tok = match.group(0) if match is not None else "lapariprcchānāmamahāyānasutra"
                    replaced_line = LAPARIPRCCHA_SPLIT_CURR_RE.sub(
                        "paripṛcchānāmamahāyānasūtra", updated_line
                    )
                    if replaced_line != updated_line:
                        change_rows.append(
                            [
                                str(page_idx),
                                str(line_idx),
                                entry_id,
                                zone,
                                src_tok,
                                "paripṛcchānāmamahāyānasūtra",
                                "A",
                                "explicit_rastrapala_split_curr",
                                "1",
                                line[:240],
                            ]
                        )
                        updated_line = replaced_line

            if GANS_RI_RE.search(updated_line):
                replaced_line = GANS_RI_RE.sub("Gaṅs ri", updated_line)
                if replaced_line != updated_line:
                    change_rows.append(
                        [
                            str(page_idx),
                            str(line_idx),
                            entry_id,
                            zone,
                            "Gans ri",
                            "Gaṅs ri",
                            "A",
                            "explicit_gans_ri",
                            "1",
                            line[:240],
                        ]
                    )
                    updated_line = replaced_line

            def repl(m: re.Match[str]) -> str:
                tok = m.group(0)
                explicit_override = SANSKRIT_TIER_A_OVERRIDES.get(tok.lower())
                if explicit_override is None and not token_is_probable_sanskrit(tok, ctx, updated_line):
                    return tok
                key = sanskrit_family_key(tok)
                if len(key) < 4:
                    return tok
                safe_norm = sanskrit_safe_normalize_token(tok)
                if "-" in tok or "/" in tok:
                    compound_norm, _, has_sanskrit_segment = sanskrit_safe_normalize_compound_token(tok)
                    safe_norm = compound_norm if has_sanskrit_segment else tok
                jn_changed = False
                if "jn" in safe_norm.lower() and token_is_probable_sanskrit(tok, ctx, updated_line):
                    if "-" in safe_norm or "/" in safe_norm:
                        jn_norm, jn_compound_changed, jn_has_sanskrit_segment = sanskrit_normalize_jn_cluster_compound_token(
                            safe_norm
                        )
                        if jn_has_sanskrit_segment and jn_compound_changed:
                            safe_norm = jn_norm
                            jn_changed = True
                    else:
                        jn_norm = sanskrit_normalize_jn_cluster_token(safe_norm)
                        if jn_norm != safe_norm:
                            safe_norm = jn_norm
                            jn_changed = True
                replacement = tok
                reason = ""
                if explicit_override:
                    replacement, _ = apply_sanskrit_override_chain(tok)
                    reason = "sanskrit_high_freq_allowlist"

                if replacement == tok and safe_norm != tok:
                    # Umlaut-only rewrites need clear Sanskrit signal.
                    if SANSKRIT_UMLAUT_RE.search(tok) and "$" not in tok and "ã" not in tok and "ı" not in tok:
                        if sanskrit_token_signature_score(tok) < 2:
                            safe_norm = tok
                    if safe_norm != tok:
                        replacement = safe_norm
                        reason = "sanskrit_jn_cluster_contextual" if jn_changed else "sanskrit_char_normalize"
                        chained, chained_changed = apply_sanskrit_override_chain(replacement)
                        if chained_changed:
                            replacement = chained
                            reason = (
                                "sanskrit_jn_cluster_plus_allowlist"
                                if jn_changed
                                else "sanskrit_char_normalize_plus_allowlist"
                            )

                if replacement == tok:
                    canon = family_to_canon.get(key)
                    conf = family_confidence.get(key, "low")
                    if (
                        canon is not None
                        and canon != tok
                        and conf == "high"
                        and ctx >= (SANSKRIT_AUTO_CONTEXT_MIN + 1)
                        and levenshtein_limited(distance_key(tok), distance_key(canon), 2) is not None
                    ):
                        replacement = canon
                        reason = "sanskrit_family_canonicalize"

                if replacement == tok or not reason:
                    return tok

                if explicit_override is None and token_is_pure_german_for_sanskrit_queue(tok, updated_line):
                    return tok

                auto_apply = ctx >= SANSKRIT_AUTO_CONTEXT_MIN or reason == "sanskrit_high_freq_allowlist"
                if (
                    not auto_apply
                    and reason in {"sanskrit_jn_cluster_contextual", "sanskrit_jn_cluster_plus_allowlist"}
                    and ctx >= 2
                    and (
                        SANSKRIT_MVY_CUE_RE.search(updated_line)
                        or SANSKRIT_GENERAL_CUE_RE.search(updated_line)
                        or SANSKRIT_LEX_CUE_RE.search(updated_line)
                    )
                ):
                    auto_apply = True
                    reason = "sanskrit_jn_cluster_context_gate"
                if (
                    not auto_apply
                    and reason == "sanskrit_char_normalize"
                    and token_is_safe_sanskrit_char_map_rewrite(tok, replacement)
                    and char_norm_pair_counts.get((tok.lower(), replacement.lower()), 0) == 1
                    and line_has_singleton_sanskrit_gate(updated_line, zone)
                ):
                    auto_apply = True
                    reason = "sanskrit_singleton_context_gate"

                if auto_apply:
                    guard_block_reason = rewrite_hard_guard_block_reason(
                        tok, replacement, reason, stage="sanskrit"
                    )
                    if guard_block_reason is not None:
                        review_rows.append(
                            [
                                str(page_idx),
                                str(line_idx),
                                entry_id,
                                zone,
                                tok,
                                replacement,
                                "B",
                                f"hard_guard_{guard_block_reason}__{reason}",
                                "0",
                                updated_line[:240],
                            ]
                        )
                        return tok
                    change_rows.append(
                        [
                            str(page_idx),
                            str(line_idx),
                            entry_id,
                            zone,
                            tok,
                            replacement,
                            "A",
                            reason,
                            "1",
                            updated_line[:240],
                        ]
                    )
                    return replacement

                review_rows.append(
                    [
                        str(page_idx),
                        str(line_idx),
                        entry_id,
                        zone,
                        tok,
                        replacement,
                        "B",
                        reason,
                        "0",
                        updated_line[:240],
                    ]
                )
                return tok

            lines[line_idx - 1] = OCR_LATIN_TOKEN_RE.sub(repl, updated_line)

    family_report_rows.sort(
        key=lambda r: (
            {"high": 0, "medium": 1, "low": 2, "none": 3}.get(r[5], 9),
            -int(r[4]),
            -int(r[2]),
            r[0],
        )
    )
    normalized_text = "\f".join("\n".join(lines) for lines in pages)
    return normalized_text, change_rows, review_rows, family_report_rows, len(family_to_canon)


def write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(header)
        w.writerows(rows)


def build_watchdog_rows(change_rows: list[list[str]]) -> tuple[list[list[str]], Counter[str]]:
    rows: list[list[str]] = []
    flag_counts: Counter[str] = Counter()
    for row in change_rows:
        if len(row) < 10:
            continue
        flags = rewrite_watchdog_flags(row[4], row[5])
        if not flags:
            continue
        for flag in flags:
            flag_counts[flag] += 1
        rows.append(
            [
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                ",".join(flags),
                row[9],
            ]
        )
    return rows, flag_counts


def filter_stale_review_rows(review_rows: list[list[str]], corrected_text: str) -> tuple[list[list[str]], int]:
    pages = [page.splitlines() for page in corrected_text.split("\f")]
    kept: list[list[str]] = []
    dropped = 0
    for row in review_rows:
        if len(row) < 10:
            kept.append(row)
            continue
        try:
            page_idx = int(row[0]) - 1
            line_idx = int(row[1]) - 1
        except ValueError:
            kept.append(row)
            continue
        if page_idx < 0 or line_idx < 0:
            kept.append(row)
            continue
        if page_idx >= len(pages) or line_idx >= len(pages[page_idx]):
            kept.append(row)
            continue
        from_token = row[4]
        to_token = row[5]
        if not from_token or not to_token or from_token == to_token:
            kept.append(row)
            continue
        final_line = pages[page_idx][line_idx]
        final_tokens = OCR_LATIN_TOKEN_RE.findall(final_line)
        # Drop rows whose source token is no longer present on the final line.
        # Later passes (citation/sanskrit normalization) may resolve these into
        # a third canonical form, so requiring an exact from->to match keeps
        # stale review noise around unnecessarily.
        if from_token not in final_tokens:
            dropped += 1
            continue
        kept.append(row)
    return kept, dropped


def run_one(
    merged: Path,
    audit: Path | None,
    outdir: Path,
    label: str,
    trusted_min_freq: int,
    discover_max_edit: int,
    discover_max_rare_freq: int,
) -> dict[str, object]:
    text = merged.read_text(encoding="utf-8", errors="replace")
    audit_by_line = load_audit(audit)
    entries, line_infos, line_rows, validator_rows, summary, page_lines = parse_entries(text, audit_by_line)
    headword_memory, entry_memory = build_entry_memory(entries, line_infos)
    trusted_lexicon = build_trusted_lexicon(entries, line_infos, min_freq=trusted_min_freq)
    discovered, discovered_rows = discover_common_errors(
        line_infos,
        trusted_lexicon=trusted_lexicon,
        max_edit=discover_max_edit,
        max_rare_freq=discover_max_rare_freq,
    )
    corrected_text, change_rows, review_rows = apply_entry_aware_corrections(
        page_lines=page_lines,
        line_infos=line_infos,
        headword_memory=headword_memory,
        entry_memory=entry_memory,
        trusted_lexicon=trusted_lexicon,
        discovered=discovered,
    )
    corrected_text, citation_change_rows, citation_review_rows, citation_report_rows, citation_family_count = (
        apply_citation_name_normalization(
            corrected_text=corrected_text,
            line_infos=line_infos,
        )
    )
    change_rows.extend(citation_change_rows)
    review_rows.extend(citation_review_rows)
    corrected_text, sanskrit_change_rows, sanskrit_review_rows, sanskrit_report_rows, sanskrit_family_count = (
        apply_sanskrit_normalization(
            corrected_text=corrected_text,
            line_infos=line_infos,
        )
    )
    change_rows.extend(sanskrit_change_rows)
    review_rows.extend(sanskrit_review_rows)
    review_rows, stale_review_rows_removed = filter_stale_review_rows(review_rows, corrected_text)

    entry_jsonl = outdir / f"{label}_entry_map.jsonl"
    line_tsv = outdir / f"{label}_line_zones.tsv"
    validator_tsv = outdir / f"{label}_validator_issues.tsv"
    summary_json = outdir / f"{label}_summary.json"
    corrected_txt = outdir / f"{label}_corrected_full.txt"
    changes_tsv = outdir / f"{label}_changes.tsv"
    review_tsv = outdir / f"{label}_review_queue.tsv"
    discovered_tsv = outdir / f"{label}_discovered_patterns.tsv"
    citation_report_tsv = outdir / f"{label}_citation_name_report.tsv"
    sanskrit_report_tsv = outdir / f"{label}_sanskrit_report.tsv"
    watchdog_tsv = outdir / f"{label}_watchdog_flags.tsv"

    with entry_jsonl.open("w", encoding="utf-8") as f:
        for ent in entries:
            f.write(json.dumps(ent.to_json(), ensure_ascii=False) + "\n")

    write_tsv(
        line_tsv,
        [
            "page",
            "line",
            "entry_id",
            "zone",
            "headword_tibetan",
            "headword_latin",
            "headword_latin_confidence",
            "translit_token_count",
            "german_token_count",
            "audit_candidates",
            "audit_replaced",
            "line_text",
        ],
        line_rows,
    )
    write_tsv(
        validator_tsv,
        ["page", "line", "entry_id", "zone", "token", "issue", "suggestion", "line_excerpt"],
        validator_rows,
    )
    corrected_txt.write_text(corrected_text, encoding="utf-8")
    write_tsv(
        changes_tsv,
        [
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
        ],
        change_rows,
    )
    write_tsv(
        review_tsv,
        [
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
        ],
        review_rows,
    )
    write_tsv(
        discovered_tsv,
        [
            "source_token",
            "suggested_token",
            "source_count",
            "suggested_count",
            "edit_distance",
            "confidence",
            "ambiguous",
            "example",
        ],
        discovered_rows,
    )
    write_tsv(
        citation_report_tsv,
        [
            "family_key",
            "canonical",
            "family_total",
            "near_year_hits",
            "variant_count",
            "non_canonical_total",
            "top_variants",
            "example_line",
        ],
        citation_report_rows,
    )
    write_tsv(
        sanskrit_report_tsv,
        [
            "family_key",
            "canonical",
            "family_total",
            "variant_count",
            "non_canonical_total",
            "confidence",
            "top_variants",
            "example_line",
        ],
        sanskrit_report_rows,
    )
    watchdog_rows, watchdog_flag_counts = build_watchdog_rows(change_rows)
    write_tsv(
        watchdog_tsv,
        [
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
        ],
        watchdog_rows,
    )

    change_reason_counts = Counter(row[7] for row in change_rows)
    review_reason_counts = Counter(row[7] for row in review_rows)
    validator_issue_counts = Counter(row[5] for row in validator_rows)
    discovered_confidence_counts = Counter(row[5] for row in discovered_rows)
    summary = {
        **summary,
        "trusted_lexicon_size": len(trusted_lexicon),
        "discovered_patterns": len(discovered_rows),
        "tier_a_applied": len(change_rows),
        "tier_b_suggestions": len(review_rows),
        "citation_name_families": citation_family_count,
        "citation_name_changes": len(citation_change_rows),
        "sanskrit_families": sanskrit_family_count,
        "sanskrit_promoted_overrides_loaded": len(SANSKRIT_PROMOTED_TIER_A_OVERRIDES),
        "sanskrit_changes": len(sanskrit_change_rows),
        "sanskrit_review_suggestions": len(sanskrit_review_rows),
        "stale_review_rows_removed": stale_review_rows_removed,
        "watchdog_flagged_changes": len(watchdog_rows),
        "watchdog_flag_counts": dict(sorted(watchdog_flag_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "discovered_confidence_counts": dict(discovered_confidence_counts),
        "top_tier_a_reasons": change_reason_counts.most_common(12),
        "top_tier_b_reasons": review_reason_counts.most_common(12),
        "top_validator_issues": validator_issue_counts.most_common(12),
    }
    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")

    result = {
        "label": label,
        "merged": str(merged),
        "audit": str(audit) if audit else "",
        "entry_map": str(entry_jsonl),
        "line_zones": str(line_tsv),
        "validator_issues_tsv": str(validator_tsv),
        "summary_json": str(summary_json),
        "corrected_full": str(corrected_txt),
        "changes_tsv": str(changes_tsv),
        "review_queue_tsv": str(review_tsv),
        "discovered_patterns_tsv": str(discovered_tsv),
        "citation_name_report_tsv": str(citation_report_tsv),
        "sanskrit_report_tsv": str(sanskrit_report_tsv),
        "watchdog_tsv": str(watchdog_tsv),
        **summary,
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Step 1+2+3 post-processing: transliteration validators, entry-aware zones, "
            "and confidence-tiered entry-consistency corrections."
        )
    )
    ap.add_argument("--merged", required=True, help="Merged full text file (form-feed page separated).")
    ap.add_argument("--audit", default="", help="Optional line-anchor audit CSV.")
    ap.add_argument("--outdir", required=True, help="Output directory.")
    ap.add_argument("--label", default="", help="Output label prefix; defaults to merged stem.")
    ap.add_argument("--trusted-min-freq", type=int, default=10, help="Min frequency for trusted translit lexicon.")
    ap.add_argument(
        "--discover-max-edit",
        type=int,
        default=2,
        help="Max Levenshtein distance for discovery-based suggestions.",
    )
    ap.add_argument(
        "--discover-max-rare-freq",
        type=int,
        default=6,
        help="Skip discovery for high-frequency tokens without validator issues.",
    )
    args = ap.parse_args()

    merged = Path(args.merged)
    audit = Path(args.audit) if args.audit else None
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    label = args.label if args.label else merged.stem.replace(" ", "_")

    result = run_one(
        merged=merged,
        audit=audit,
        outdir=outdir,
        label=label,
        trusted_min_freq=args.trusted_min_freq,
        discover_max_edit=args.discover_max_edit,
        discover_max_rare_freq=args.discover_max_rare_freq,
    )
    print(f"label={result['label']}")
    print(f"merged={result['merged']}")
    if result["audit"]:
        print(f"audit={result['audit']}")
    print(f"entries_detected={result['entries_detected']}")
    print(f"non_empty_lines={result['non_empty_lines']}")
    print(f"validator_issues={result['validator_issues']}")
    print(f"trusted_lexicon_size={result['trusted_lexicon_size']}")
    print(f"discovered_patterns={result['discovered_patterns']}")
    print(f"tier_a_applied={result['tier_a_applied']}")
    print(f"tier_b_suggestions={result['tier_b_suggestions']}")
    print(f"citation_name_families={result['citation_name_families']}")
    print(f"citation_name_changes={result['citation_name_changes']}")
    print(f"sanskrit_families={result['sanskrit_families']}")
    print(f"sanskrit_promoted_overrides_loaded={result['sanskrit_promoted_overrides_loaded']}")
    print(f"sanskrit_changes={result['sanskrit_changes']}")
    print(f"sanskrit_review_suggestions={result['sanskrit_review_suggestions']}")
    print(f"uncaptured_tibetan_prefix_lines={result['uncaptured_tibetan_prefix_lines']}")
    print(f"entry_map={result['entry_map']}")
    print(f"line_zones={result['line_zones']}")
    print(f"validator_issues_tsv={result['validator_issues_tsv']}")
    print(f"corrected_full={result['corrected_full']}")
    print(f"changes_tsv={result['changes_tsv']}")
    print(f"review_queue_tsv={result['review_queue_tsv']}")
    print(f"discovered_patterns_tsv={result['discovered_patterns_tsv']}")
    print(f"citation_name_report_tsv={result['citation_name_report_tsv']}")
    print(f"sanskrit_report_tsv={result['sanskrit_report_tsv']}")
    print(f"summary_json={result['summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
