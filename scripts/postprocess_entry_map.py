#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from difflib import SequenceMatcher
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
    r"\u00DF\u0131\u015F\u015E\u0146\u0145\u00E3\u00C3\u0148\u0147\u01F9\u01F8\u0144\u0143"
    r"\u017E\u017D\u0161\u0160"
)
OCR_CONFUSABLE_TOKEN_CHARS = r"\$"
TRANSLIT_CHARS = (
    r"A-Za-z"
    r"\u0100\u0101\u012A\u012B\u016A\u016B\u1E5A\u1E5B\u1E5C\u1E5D\u1E36\u1E37\u1E38\u1E39"
    r"\u1E44\u1E45\u00D1\u00F1\u1E6C\u1E6D\u1E0C\u1E0D\u1E46\u1E47\u015A\u015B\u1E62\u1E63"
    r"\u1E24\u1E25\u1E42\u1E43\u1E40\u1E41\u0179\u017A\u0131\u015F\u015E\u0146\u0145\u00E3\u00C3\$"
    r"\u0148\u0147\u01F9\u01F8\u0144\u0143\u017E\u017D\u0161\u0160"
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
    r"\u1E43\u1E41\u0148\u01F9\u0144\u017E\u0161\u2019']|(?:kh|tsh|ts|ph|th|dh|bh|dz|rdz|ṅ|ñ|ź|ś|lh|rg|rk|rt|rd)",
    re.IGNORECASE,
)
GOOGLE_VISION_LOC_CONFUSABLE_CHARS = "\u0148\u0147\u01F9\u01F8\u0144\u0143\u017E\u017D\u0161\u0160"
GOOGLE_VISION_LOC_CONFUSABLE_RE = re.compile(f"[{GOOGLE_VISION_LOC_CONFUSABLE_CHARS}]")
GOOGLE_VISION_NASAL_CONFUSABLES = {"ň", "ǹ", "ń"}
GOOGLE_VISION_NASAL_CONFUSABLES_UPPER = {"Ň", "Ǹ", "Ń"}
GOOGLE_VISION_NON_NASAL_CONFUSABLE_MAP = str.maketrans(
    {
        "ž": "ź",
        "Ž": "Ź",
        "š": "ś",
        "Š": "Ś",
    }
)
GOOGLE_VISION_LOC_POST_TOKEN_FIXES = {
    "sniṅ": "sñiṅ",
    "sniṅs": "sñiṅs",
}
GOOGLE_VISION_PAGE_MARKER_RE = re.compile(r"^\s*===\s*page\s+\d+\s*===\s*$", re.IGNORECASE)
GOOGLE_VISION_PROTECTED_SPAN_RE = re.compile(r"[Šš]č[^\s,.;:)\]]*")
TRANSLIT_DIACRITIC_RE = re.compile(
    r"[\u0101\u012B\u016B\u1E5B\u1E5D\u1E37\u1E39\u1E45\u1E6D\u1E0D\u1E47\u015B\u1E63\u1E25\u1E43\u1E41]",
    re.IGNORECASE,
)
STRONG_TRANSLIT_CLUSTER_RE = re.compile(r"(?:tsh|ts|ph|kh|dh|bh|dz|rdz|ź|ś|lh)", re.IGNORECASE)
ASCII_TIB_EVIDENCE_CLUSTER_RE = re.compile(r"(?:ny|ng|sh|zh)", re.IGNORECASE)
BOUNDARY_TRANSLIT_CLUSTER_RE = re.compile(
    r"(?:^|[-'’])(?:tsh|ts|ph|kh|dh|bh|dz|rdz|ź|ś|lh|rg|rk|rt|rd)",
    re.IGNORECASE,
)
DISTINCTIVE_TIB_CLUSTER_RE = re.compile(
    r"(?:^|[-'’])(?:"
    r"bsk|bsg|bst|brg|brk|brt|brd|"
    r"dṅ|dby|dbr|dgr|dkr|dpy|dpr|"
    r"mth|mkh|mch|mñ|"
    r"rgy|rts|rky|"
    r"sgr|sbr|sñ|sṅ|"
    r"rdz|gź|"
    r"ź|lh|ṅ|ñ|"
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
    r"^I(?:kh|khy|kr|gr|ph|phy|th|tsh|ts|dz|ź|ś|ch|ñ|ṅ|k|g|c|j|t|d|p|b|m|r|s|h|y|w|l)",
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
CITATION_NOISY_YEAR_RE = re.compile(
    r"\b(?:1[6-9]\d{2}|20\d{2})(?:\d|[a-z])?\b",
    re.IGNORECASE,
)
CITATION_CUE_RE = re.compile(
    r"\b(?:ed|hrsg|vgl|zit|zitiert|vol|bd|pp|pl|repr|index|indices)\b\.?",
    re.IGNORECASE,
)
CITATION_BIBLIO_AUTHOR_YEAR_RE = re.compile(
    rf"^\s*(?:[—–-]\s*)?(?:/)?"
    rf"[{LATIN_CHARS}][{LATIN_CHARS}'’.-]{{1,40}},\s+"
    rf"[{LATIN_CHARS}][{LATIN_CHARS}'’./ -]{{0,48}}?"
    rf"(?:1[6-9]\d{{2}}|20\d{{2}})(?:\d|[a-z])?[\.:]?",
    re.IGNORECASE,
)
CITATION_BIBLIO_CONTINUATION_HEAD_RE = re.compile(
    r"^\s*(?:and|for|from|in|of|the|to|with)\b",
    re.IGNORECASE,
)
CITATION_BIBLIO_CONTINUATION_CUE_RE = re.compile(
    r"(?:A\.D\.|\b(?:pp\.?|vol\.?|ed\.?|repr\.?|index|indices|london|berlin|wiesbaden|tokyo|halle|münchen|munich|roma|paris|oxford)\b)",
    re.IGNORECASE,
)
CITATION_BIBLIO_INLINE_CUE_RE = re.compile(
    r"(?:\breproduced\b|\bprepared\b|\bmanuscript\b|unter\s+Mitarbeit\s+von|\bhg\.?\s*v\.?)",
    re.IGNORECASE,
)
CITATION_SIGLUM_ARTIFACT_CUE_RE = re.compile(
    r"\((?:[^)\n]{0,32})(?<![A-Za-z])(?:L\$dz(?:-[A-Za-z$]*)?|L1\$|1\.\$dz|Vi\$s?T|Vis\$T|Li(?:\$|s\$)|Y\$|Ys\$|P\$|G\$(?:S?-H)?)(?=[^A-Za-z$]|$)",
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
CITATION_SIGLUM_ALNUM_TOKEN_RE = re.compile(
    rf"[{LATIN_CHARS}{OCR_CONFUSABLE_TOKEN_CHARS}0-9.]+"
    rf"(?:-[{LATIN_CHARS}{OCR_CONFUSABLE_TOKEN_CHARS}0-9.]+)*(?:[’'])?"
)
# Parenthetical siglum coordinate (e.g. "(1SK 5a)", "(Lśdz 293,17)").
CITATION_SIGLUM_COORD_PAREN_RE = re.compile(
    r"\((?:[^)\n]{0,24})(?<![A-Za-z0-9])"
    r"(?:[A-Za-z$][A-Za-z$0-9.-]{1,15})"
    r"(?=\s+\d{1,4}(?:[a-z]|[,:./]\d{1,4}[a-z]?)?)",
    re.IGNORECASE,
)
# Sigla index/list form in abbreviation sections (left-column siglum + body).
CITATION_SIGLUM_LEADING_LAYOUT_RE = re.compile(
    r"^\s*[A-Za-z$0-9.]+(?:-[A-Za-z$0-9.]+){0,2}\s{2,}[^\n]{6,}$"
)
# Safe siglum-specific normalization: only convert dotted g.Yu when it is
# clearly a parenthetical citation coordinate, e.g. "(g.Yu 293,17)".
CITATION_G_DOT_YU_COORD_RE = re.compile(
    r"(\(\s*)g\.Yu(?=\s+\d{1,4}[,:./]\d{1,4}(?:[^)\n]{0,24})\))"
)
# German citation shorthand OCR artifact: i.S.v. / i.S. frequently appears as
# i.$.v., 1.$. v., i1.$.v., 1, $.v., etc.
CITATION_DOTTED_DOLLAR_ABBREV_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:[iI1ı](?:1)?\s*[.,]\s*\$\s*\.(?:\s*(?P<trail>[vVxX])\s*\.)?)"
    r"(?![A-Za-z0-9])"
)
INITIAL_I_CANON_SHAPE_RE = re.compile(
    r"^l(?:['’](?:h|t|n|d|k|g|c|j|p|b|m|r|s|y|w|kh|ph|th|ts|dz|ź|ś|ñ|ṅ)"
    r"|(?:h|t|n|d|k|g|c|j|p|b|m|r|s|y|w|kh|ph|th|ts|dz|ź|ś|ñ|ṅ))",
    re.IGNORECASE,
)
TIBETAN_NAME_PIECE_PREFIX_RE = re.compile(
    r"^(?:"
    r"bs|bz|bsk|bst|brg|brk|brt|brd|"
    r"dṅ|dby|dgr|dkr|dpy|dpr|"
    r"mth|mkh|mch|mñ|mg|"
    r"rgy|rts|rky|"
    r"sgr|sbr|sñ|sṅ|"
    r"rdz|gź|"
    r"ź|lh|ṅ|ñ|"
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
GERMAN_QUOTE_WRAP_LINE_END_RE = re.compile(rf"(.*?)([{LATIN_CHARS}]{{2,20}})-\s*$")
GERMAN_QUOTE_WRAP_CONTINUATION_HEAD_RE = re.compile(rf"^\s*([{LATIN_CHARS}]{{2,8}})\b(.*)$")
GERMAN_QUOTE_WRAP_CITATION_HEAD_RE = re.compile(rf"^\s*\(([A-ZÄÖÜ][{LATIN_CHARS}.-]{{1,16}})\s*$")
GERMAN_QUOTE_WRAP_COORD_PREFIX_RE = re.compile(r"^\s*(\d{1,4}(?:[,:./]\d{1,4}|[a-z])\);\s*)(.*)$")
GERMAN_WRAP_COMMON_ENDINGS = (
    "ade",
    "bar",
    "chen",
    "eit",
    "en",
    "end",
    "ende",
    "er",
    "ern",
    "erns",
    "gen",
    "haft",
    "heit",
    "ieren",
    "ig",
    "isch",
    "keit",
    "lich",
    "lung",
    "nung",
    "ren",
    "schaft",
    "sten",
    "tion",
    "ung",
)
GERMAN_WRAP_NON_CONTINUATION_HEADS = {
    "aber",
    "als",
    "am",
    "an",
    "auch",
    "auf",
    "aus",
    "bei",
    "das",
    "dem",
    "den",
    "der",
    "des",
    "die",
    "dies",
    "doch",
    "ein",
    "eine",
    "einer",
    "eines",
    "er",
    "es",
    "für",
    "gegen",
    "im",
    "in",
    "ist",
    "man",
    "mit",
    "nach",
    "noch",
    "nur",
    "oder",
    "ohne",
    "schon",
    "selbst",
    "sie",
    "so",
    "über",
    "um",
    "und",
    "von",
    "vor",
    "wie",
    "wir",
    "zu",
    "zum",
    "zur",
}
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
    "rmams": "rnams",
    "breyud": "brgyud",
    "broyud": "brgyud",
    "broyad": "brgyad",
    "bsnal": "bsṅal",
    "biin": "bźin",
    "giien": "gñen",
    "giier": "gñer",
    "bsiien": "bsñen",
    "siian": "sñan",
    "giis": "gñis",
    "giiis": "gñis",
    "griis": "gñis",
    "miiam": "mñam",
    "yiin": "yin",
    "fiid": "ñid",
    "kyı": "kyi",
    "kyıs": "kyis",
    "gyı": "gyi",
    "gyıs": "gyis",
    "yın": "yin",
    "cıg": "cig",
    "gcıg": "gcig",
    "zıg": "zig",
    "sıg": "sig",
    "dkyıl": "dkyil",
    "kyanı": "kyaṅ",
    "yanı": "yaṅ",
    "byanı": "byaṅ",
    "gsarı": "gsaṅ",
    "snanı": "snaṅ",
    "sarıs": "saṅs",
    "garı": "gaṅ",
    "igarı": "lgaṅ",
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
    "Ita": "lta",
    "Iha": "lha",
    "Ihan": "lhan",
    "Iho": "lho",
    "Itos": "ltos",
    "bii": "bźi",
    "bii'": "bźi'",
    "bii’": "bźi’",
    "bii'an": "bźi'an",
    "bii’an": "bźi’an",
    "bii'o": "bźi'o",
    "bii’o": "bźi’o",
    "bii'i": "bźi'i",
    "bii’i": "bźi’i",
}

# High-confidence OCR confusable forms where "$" should be acute-s.
DOLLAR_SACUTE_TIER_A_ALLOWLIST = {
    "$es",
    "$es-rab",
    "$in",
    "g$egs",
}

# Exact Tibetan transliteration confusables promoted from all-volume QA.
# These remain context-gated in choose_rewrite; this is not a character map.
TIBETAN_TRANSLIT_CONFUSABLE_EXACT_REWRITES = {
    "$ar": "śar",
    "$is": "śis",
    "$os": "śos",
    "bzañ": "bzaṅ",
    "chañ": "chaṅ",
    "gsañ": "gsaṅ",
    "rañ": "raṅ",
    "snañ": "snaṅ",
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
    "ati$a": "atiśa",
    "mahes$vara": "maheśvara",
    "mahe$vara": "maheśvara",
    "dhäpayoga-ratnamaälä": "dhūpayogaratnamālā",
    "nägärjuna": "nāgārjuna",
    "astäpadikrtadhüpayoga": "aṣṭapadīkṛtadhūpayoga",
    "mahämäyürividyäräjni": "mahāmāyūrīvidyārājñī",
    "pramänakirtih": "pramāṇakīrtiḥ",
    "mülasarvästiväda": "mūlasarvāstivāda",
    "mülasarvästi": "mūlasarvāsti",
    "päramitäsamäsa": "pāramitāsamāsa",
    "uddänas": "uddānas",
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

# Exact high-frequency German OCR artifacts (mostly dotless-ı confusion).
# Keep this list strict and token-exact; these rewrites are only applied in
# German prose zones and are skipped on citation-like lines.
GERMAN_PROSE_SAFE_REWRITES = {
    "cine": "eine",
    "cinem": "einem",
    "cinen": "einen",
    "ciner": "einer",
    "cines": "eines",
    "seı": "sei",
    "eın": "ein",
    "ın": "in",
    "ım": "im",
    "ıst": "ist",
    "sınd": "sind",
    "nıcht": "nicht",
    "mıt": "mit",
    "sıch": "sich",
    "wıe": "wie",
    "dıe": "die",
    "dıes": "dies",
    "dıeser": "dieser",
    "dıesen": "diesen",
    "dıesem": "diesem",
    "dıeserlei": "dieserlei",
    "dıejenigen": "diejenigen",
    "ıch": "ich",
    "ıhn": "ihn",
    "ıhr": "ihr",
    "ıhre": "ihre",
    "ıhren": "ihren",
    "ıhrem": "ihrem",
    "ıhrer": "ihrer",
    "ıhm": "ihm",
    "mır": "mir",
    "beı": "bei",
    "beım": "beim",
    "weıl": "weil",
    "bıs": "bis",
    "beıde": "beide",
    "alleın": "allein",
    "beschleunıgen": "beschleunigen",
    "basıs": "basis",
    "iranıstik": "iranistik",
    "kommunıikation": "kommunikation",
    "verwaltıng": "verwaltung",
    "artıkel": "artikel",
    "lexıkographisch": "lexikographisch",
    "lexıkalisch": "lexikalisch",
    "bıographie": "biographie",
    "bıographisch": "biographisch",
    "nıeder": "nieder",
    "nıederlassen": "niederlassen",
    "vernıchten": "vernichten",
    "gelıngen": "gelingen",
    "wırd": "wird",
    "wırkung": "wirkung",
    "stıftung": "stiftung",
    "bıld": "bild",
    "schrıft": "schrift",
    "schrıftsprache": "schriftsprache",
    "tıbetisch": "tibetisch",
    "tıbetologen": "tibetologen",
    "publızıert": "publiziert",
}

# Exact-token prose rewrites for cases where generic case-shaping would preserve
# an OCR artifact or downcase a corrected capital.
GERMAN_PROSE_TOKEN_EXACT_SAFE_REWRITES = {
    "Iranıstik": "Iranistik",
}

# OCR digit/letter confusion in German prose: "111"/"1111" often stands for
# "in"/"im". Apply only with strict local context checks.
GERMAN_NUMERIC_FUNCTION_WORD_REWRITES = {
    "111": "in",
    "1111": "im",
    "6111": "ein",
    "€111": "ein",
    "©111": "ein",
}

# Frequent English bibliography spacing-loss artifacts.
ENGLISH_BIBLIO_SPACELOSS_REWRITES = {
    "ofthe": "of the",
    "inthe": "in the",
    "fromthe": "from the",
    "oftheindo-aryan": "of the Indo-Aryan",
    "accompaniedbya": "accompanied by a",
    "engliish": "english",
}

# Conservative bibliography-only proper-name fixes (exact token matches).
CITATION_NAME_SAFE_REWRITES = {
    "cürpers": "cüppers",
    "denwoop": "denwood",
    "dierz": "dietz",
    "granmatik": "grammatik",
    "hindn": "hindu",
    "manuseript": "manuscript",
    "pansiung": "panglung",
    "schwirger": "schwieger",
    "uesachh": "uebach",
    "uzsachh": "uebach",
    "vollkommenbeiten": "vollkommenheiten",
    "zongrtse": "zongtse",
    "tromas": "thomas",
    "wyrıe": "wylie",
    "wyrie": "wylie",
    "pangiunc": "panglung",
    "pangiung": "panglung",
    "sreingass": "steingass",
    "stem": "stein",
    "kvzrne": "kværne",
}

# Mixed-case and initial-confusion bibliography tokens that should normalize to
# an exact target rather than preserve OCR-shaped capitalization.
CITATION_TOKEN_EXACT_SAFE_REWRITES = {
    "Ihe": "The",
    "Into": "into",
    "Iwo": "Two",
    "PangLung": "Panglung",
    "SreinGass": "Steingass",
}

# Bibliography-only phrase rewrites for OCR that breaks or distorts token
# boundaries; keep these exact and conservative.
CITATION_PHRASE_SAFE_REWRITE_PATTERNS = (
    (re.compile(r"\bP\s+rsian-English\b"), "Persian-English", "citation_phrase_safe_map"),
    (re.compile(r"\bvice versä\b"), "vice versa", "citation_phrase_safe_map"),
)
TIBETAN_TRANSLIT_PHRASE_SAFE_REWRITE_PATTERNS = (
    (
        re.compile(rf"(?<![{LATIN_CHARS}0-9])tsbul(?P<space>[ \t]+)kbrims(?![{LATIN_CHARS}0-9])"),
        "tshul",
        "khrims",
        "tibetan_translit_phrase_allowlist",
    ),
)
TIBETAN_TRANSLIT_DIRECT_PHRASE_SAFE_REWRITE_PATTERNS = (
    (
        re.compile(rf"(?<![{LATIN_CHARS}0-9])skal ba dan ldan pa"),
        "skal ba daṅ ldan pa",
        "tibetan_translit_phrase_allowlist",
    ),
    (
        re.compile(rf"(?<![{LATIN_CHARS}0-9])stobs dan ldan pa"),
        "stobs daṅ ldan pa",
        "tibetan_translit_phrase_allowlist",
    ),
    (
        re.compile(rf"(?<![{LATIN_CHARS}0-9])chos dan ldan pa"),
        "chos daṅ ldan pa",
        "tibetan_translit_phrase_allowlist",
    ),
    (
        re.compile(rf"(?<![{LATIN_CHARS}0-9])dbaṅ dan ldan pa"),
        "dbaṅ daṅ ldan pa",
        "tibetan_translit_phrase_allowlist",
    ),
    (
        re.compile(rf"(?<![{LATIN_CHARS}0-9])dan ldan pa(?![{LATIN_CHARS}0-9])"),
        "daṅ ldan pa",
        "tibetan_translit_phrase_allowlist",
    ),
)
TIBETAN_DANG_WITNESS_RE = re.compile(r"(?:^|[\s\u0F0B-\u0F14])(?:དང་|འདང་)")
TIBETAN_DAN_TOKEN_RE = re.compile(rf"(?<!['’{LATIN_CHARS}0-9])dan(?![{LATIN_CHARS}0-9])")
GERMAN_NUMERIC_FUNCTION_WORD_TOKEN_RE = re.compile(
    r"(?<![0-9A-Za-z\u00C0-\u024F€©])(?P<token>6111|1111|€111|©111|111)(?![0-9A-Za-z\u00C0-\u024F€©])"
)


def line_has_german_numeric_function_word(line_text: str) -> bool:
    return GERMAN_NUMERIC_FUNCTION_WORD_TOKEN_RE.search(line_text) is not None


def line_has_tibetan_dang_witness(line_text: str) -> bool:
    return TIBETAN_DANG_WITNESS_RE.search(line_text) is not None

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
GERMAN_INITIAL_I_PROTECTED_WORDS = {
    "ingwer",
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

SIGLA_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "sigla_registry.tsv"
TIBETAN_DANG_PHRASE_OVERRIDES_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "tibetan_dang_phrase_overrides.tsv"
)


def load_sigla_registry(path: Path) -> tuple[set[str], dict[str, str]]:
    canonical: set[str] = set()
    confusable_map: dict[str, str] = {}
    if not path.exists():
        return canonical, confusable_map
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            canon = (row.get("canon") or "").strip()
            status = (row.get("status") or "active").strip().casefold()
            if not canon:
                continue
            if status in {"hold", "blocked", "disabled", "0", "false"}:
                continue
            canonical.add(canon)
            raw_variants = row.get("allowed_variants") or ""
            if not raw_variants.strip():
                continue
            for variant in re.split(r"[|,;]", raw_variants):
                variant = variant.strip()
                if not variant:
                    continue
                confusable_map[variant.casefold()] = canon
    return canonical, confusable_map


def load_tibetan_dang_phrase_overrides(path: Path) -> list[tuple[str, str]]:
    overrides: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if not path.exists():
        return overrides
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            from_phrase = (row.get("from_phrase") or "").strip()
            to_phrase = (row.get("to_phrase") or "").strip()
            if not from_phrase or not to_phrase or from_phrase == to_phrase:
                continue
            pair = (from_phrase, to_phrase)
            if pair in seen:
                continue
            seen.add(pair)
            overrides.append(pair)
    overrides.sort(key=lambda pair: len(pair[0]), reverse=True)
    return overrides

# Canonical source-text sigla found in abbreviation/citation sections.
# Keep this list narrow and explicit to avoid affecting normal transliteration.
CITATION_SIGLUM_CANONICAL_FALLBACK = {
    "1SK",
    "Bu-Sz",
    "Gs",
    "Gs-H",
    "Ins",
    "Lśdz",
    "Lśdz-K",
    "Lśdz-R",
    "Liś",
    "Mvy",
    "Ps",
    "RoINS",
    "SPS",
    "Śambh",
    "Vis",
    "VisT",
    "Xs",
    "Ys",
}

# OCR-confusable sigla variants observed in citations.
CITATION_SIGLUM_CONFUSABLE_MAP_FALLBACK = {
    # Explicit observed $ confusions.
    "p$": "Ps",
    "x$": "Xs",
    "bu-$": "Bu-Sz",
    "bu-$z": "Bu-Sz",
    "bu-$2": "Bu-Sz",
    "bu-$sz": "Bu-Sz",
    "vi$": "Vis",
    "vis$": "Vis",
    "$ambh": "Śambh",
    "$sambh": "Śambh",
    "$ps": "SPS",
    "roin$": "RoINS",
    "roins$": "RoINS",
    "roins": "RoINS",
    "roinss": "RoINS",
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
    # Unaccented OCR outputs still seen in citation contexts; keep scope
    # narrow by mapping only exact siglum tokens.
    "lis": "Liś",
    "lsdz": "Lśdz",
    "lsdz-k": "Lśdz-K",
    "lsdz-r": "Lśdz-R",
    "vi$t": "VisT",
    "vi$st": "VisT",
    "y$": "Ys",
    "ys$": "Ys",
    # Sa-skya pa chen po Kun dga' snying po (Bd. 1) siglum:
    # OCR often confuses leading digit "1" with capital "I".
    "1sk": "1SK",
    "isk": "1SK",
    "1isk": "1SK",
    # Safe case-noise sigla variants seen in citation contexts.
    "vist": "VisT",
    "visst": "VisT",
    "viist": "VisT",
    "ys": "Ys",
    "gs-h": "Gs-H",
    # Additional high-confidence sigla OCR confusions (directionality
    # validated against abbreviation-intro anchors).
    "migto": "MigTo",
    "kunk": "KunK",
    "śrkk": "Srkk",
    "bhukkh": "BhuKkh",
    "mdz0dg": "mDzodG",
    "md20dg": "mDzodG",
    "milgb": "MilGb",
    "bhul.g": "Bhulg",
    "śiknth": "SikNth",
    # Additional high-confidence sigla OCR confusions (digit/letter mixups).
    "gz1-sn": "gZi-Sn",
    "gz1": "gZi",
    "gz1-$n": "gZi-Sn",
    "g21-sn": "gZi-Sn",
    "g71-sn": "gZi-Sn",
    "g21": "gZi",
    "g71": "gZi",
    "g7i-sn": "gZi-Sn",
    "g7i": "gZi",
    "g7zi-sn": "gZi-Sn",
    "gzi1-sn": "gZi-Sn",
    "gz21": "gZi",
    "inl1": "In11",
    "inll": "In11",
    "ini1": "In11",
    "inl2": "In12",
    "inl3": "In13",
    "in1o": "In10",
    "inlo": "In10",
    "ro1": "Rol",
    "doll": "Dol1",
    "do14": "Dol4",
    "liy1": "Liyl",
    "liy1-2": "Liyl-2",
    "l3dz-k": "Lśdz-K",
    "ltdz-k": "Lśdz-K",
    "1.5dz": "Lśdz",
    "l5dz-k": "Lśdz-K",
    "bu-5z": "Bu-Sz",
    "bu-52": "Bu-Sz",
    "bu-57": "Bu-Sz",
    "bu-s7": "Bu-Sz",
    "p5": "Ps",
    "y5": "Ys",
    "ttj740": "ITJ740",
    "1tj730": "ITJ730",
    "1n7": "In7",
    # Keep Bhulg/BhuLg ambiguity unresolved; only fix duplicated-l OCR noise.
    "bhullg": "BhuLg",
}

# Narrow standalone replacements for sigla-list rows split into single tokens.
# Keep this explicit to avoid changing non-siglum standalone words.
CITATION_SIGLUM_STANDALONE_ALLOWLIST = {
    "$ambh",
    "$sambh",
    "doll",
    "roins",
}

_SIGLA_REGISTRY_CANONICAL, _SIGLA_REGISTRY_CONFUSABLE_MAP = load_sigla_registry(SIGLA_REGISTRY_PATH)
TIBETAN_DANG_PHRASE_OVERRIDES = load_tibetan_dang_phrase_overrides(
    TIBETAN_DANG_PHRASE_OVERRIDES_PATH
)
CITATION_SIGLUM_CANONICAL = set(CITATION_SIGLUM_CANONICAL_FALLBACK)
CITATION_SIGLUM_CANONICAL.update(_SIGLA_REGISTRY_CANONICAL)
CITATION_SIGLUM_CONFUSABLE_MAP = dict(CITATION_SIGLUM_CONFUSABLE_MAP_FALLBACK)
CITATION_SIGLUM_CONFUSABLE_MAP.update(_SIGLA_REGISTRY_CONFUSABLE_MAP)

CITATION_SIGLUM_CANONICAL_BY_KEY = {
    re.sub(r"[sś]+", "s", canon.casefold()): canon for canon in CITATION_SIGLUM_CANONICAL
}

# Keep narrowly-scoped, exact-case siglum fixes separate so lexical Tibetan
# forms like "gir" are never remapped.
CITATION_SIGLUM_CASE_SENSITIVE_MAP = {
    "GIr": "Glr",
    "Sambh": "Śambh",
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
    "brag",
    "bsod",
    "bstan",
    "bzaṅ",
    "chos",
    "dbaṅ",
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
    "saṅ",
    "saṅs",
    "byaṅ",
    "gsaṅ",
    "śes",
    "śis",
    "skal",
    "sprul",
    "ye",
}
SHORT_TIB_SYLLABLES = {
    "a",
    "ba",
    "bo",
    "bya",
    "byaṅ",
    "can",
    "cig",
    "chos",
    "dan",
    "de",
    "dkyil",
    "di",
    "du",
    "gcig",
    "gi",
    "gyi",
    "gyis",
    "gsaṅ",
    "ka",
    "kha",
    "khyi",
    "kyi",
    "kyis",
    "kyaṅ",
    "la",
    "las",
    "ldan",
    "lhan",
    "lha",
    "lho",
    "lhun",
    "lo",
    "lta",
    "ltos",
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
    "yaṅ",
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
    "źes",
}

# Recognition-only fallback for ASCII/Wylie-like OCR evidence. Canonical output stays LoC.
ASCII_TIB_EVIDENCE_MAP = str.maketrans({
    "ś": "sh",
    "Ś": "Sh",
    "ź": "zh",
    "Ź": "Zh",
    "ñ": "ny",
    "Ñ": "Ny",
    "ṅ": "ng",
    "Ṅ": "Ng",
})
ASCII_SHORT_TIB_SYLLABLES = {token.lower().translate(ASCII_TIB_EVIDENCE_MAP) for token in SHORT_TIB_SYLLABLES}
ASCII_TIBETAN_NAME_PIECE_HINTS = {
    token.lower().translate(ASCII_TIB_EVIDENCE_MAP) for token in TIBETAN_NAME_PIECE_HINTS
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


def dollar_to_sacute_preserve_case(token: str) -> str:
    if "$" not in token:
        return token
    letters = [ch for ch in token if ch.isalpha()]

    def should_emit_upper_sacute(idx: int) -> bool:
        if not letters:
            return False
        if all(ch.isupper() for ch in letters):
            return True
        # Preserve titlecase only when the acute-s belongs to the first
        # letter slot; internal mixed-caps OCR noise should collapse to lowercase.
        if letters[0].isupper() and all(ch.islower() for ch in letters[1:]):
            first_alpha_idx = next((i for i, ch in enumerate(token) if ch.isalpha()), 0)
            return idx <= first_alpha_idx
        return False

    out: list[str] = []
    n = len(token)
    idx = 0
    while idx < n:
        ch = token[idx]
        if ch in {"s", "S"} and idx + 1 < n and token[idx + 1] == "$":
            emit_upper = ch == "S" and should_emit_upper_sacute(idx)
            out.append("Ś" if emit_upper else "ś")
            idx += 2
            continue
        if ch == "$" and idx + 1 < n and token[idx + 1] in {"s", "S"}:
            emit_upper = token[idx + 1] == "S" and should_emit_upper_sacute(idx)
            out.append("Ś" if emit_upper else "ś")
            idx += 2
            continue
        if ch != "$":
            out.append(ch)
            idx += 1
            continue
        out.append("Ś" if should_emit_upper_sacute(idx) else "ś")
        idx += 1
    return "".join(out)


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
    if token_has_hard_translit_marker(token):
        return True
    if token_has_distinctive_tibetan_signature(token):
        return True
    if token_has_translit_cue(token):
        return True
    if tok in SHORT_TIB_SYLLABLES or tok in ASCII_SHORT_TIB_SYLLABLES:
        return True
    if token_is_likely_tibetan_name_piece(token):
        if line_has_tibetan or is_entry_start:
            return True
    if token_has_boundary_translit_cluster(token):
        if line_has_tibetan or is_entry_start:
            return True
    if line_has_tibetan and tok.islower():
        if TIB_MEDIAL_Y_RE.search(tok):
            return True
        if tok.endswith(("is", "ang", "ung", "ing")) and token_has_translit_cue(token):
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
    low = canonicalize_translit_token(token).lower()
    if TRANSLIT_DIACRITIC_RE.search(low):
        return True
    if "'" in low or "’" in low:
        return True
    if STRONG_TRANSLIT_CLUSTER_RE.search(low):
        return True
    if low in SHORT_TIB_SYLLABLES and len(low) >= 3:
        return True
    if low in ASCII_SHORT_TIB_SYLLABLES and len(low) >= 3:
        return True
    if ASCII_TIB_EVIDENCE_CLUSTER_RE.search(low):
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
    if low in ASCII_SHORT_TIB_SYLLABLES:
        return True
    if token_has_hard_translit_marker(low):
        return True
    if DISTINCTIVE_TIB_CLUSTER_RE.search(low):
        return True
    if ASCII_TIB_EVIDENCE_CLUSTER_RE.search(low):
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
    src_low = canonicalize_translit_token(src).lower()
    dst_low = canonicalize_translit_token(dst).lower()
    if src_low in SHORT_TIB_SYLLABLES or dst_low in SHORT_TIB_SYLLABLES:
        return False
    if src_low in ASCII_SHORT_TIB_SYLLABLES or dst_low in ASCII_SHORT_TIB_SYLLABLES:
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
    if low in GERMAN_INITIAL_I_PROTECTED_WORDS:
        return True
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
    if dst_low in SHORT_TIB_SYLLABLES:
        return True
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
        if low in TIBETAN_NAME_PIECE_HINTS:
            return True
        if low in ASCII_TIBETAN_NAME_PIECE_HINTS:
            return True
        if len(low) < 3:
            return False
        if token_has_hard_translit_marker(low):
            return True
        if DISTINCTIVE_TIB_CLUSTER_RE.search(low):
            return True
        if TIBETAN_NAME_PIECE_PREFIX_RE.search(low):
            return True
        if ASCII_TIB_EVIDENCE_CLUSTER_RE.search(low):
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
    if not any(ch.isalpha() for ch in src):
        return False
    expected = dollar_to_sacute_preserve_case(src)
    if dst != expected:
        return False
    if expected == src:
        return False

    # Re-scan source neighborhoods around replaced positions.
    replaced_at = [idx for idx, s_ch in enumerate(src) if s_ch == "$"]
    src_low = src.lower()
    dst_low = dst.lower()
    if DOLLAR_SACUTE_ARTIFACT_RE.search(dst_low):
        return False
    for idx in replaced_at:
        prev_ch = src_low[idx - 1] if idx > 0 else ""
        next_ch = src_low[idx + 1] if idx + 1 < len(src_low) else ""
        if prev_ch in {"ś", "ṣ"}:
            return False
        if next_ch in {"ś", "ṣ"}:
            return False
        if prev_ch in {"z", "ź", "ž"}:
            return False
        if next_ch in {"z", "ź", "ž"}:
            return False
    return True


def line_has_sanskrit_or_indic_cue(line_text: str) -> bool:
    return bool(
        SANSKRIT_MVY_CUE_RE.search(line_text)
        or SANSKRIT_GENERAL_CUE_RE.search(line_text)
        or SANSKRIT_LEX_CUE_RE.search(line_text)
    )


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


ALTERNATE_WITNESS_CANON_MAP = {
    "ž": "ź",
    "Ž": "Ź",
    "š": "ś",
    "Š": "Ś",
}


def canonicalize_alternate_witness_token(token: str) -> str:
    if GOOGLE_VISION_LOC_CONFUSABLE_RE.search(token):
        return rewrite_google_vision_loc_confusables(token)
    return "".join(ALTERNATE_WITNESS_CANON_MAP.get(ch, ch) for ch in token)


def token_is_alternate_witness_clean_translit(token: str) -> bool:
    if not TRANSLIT_TOKEN_RE.fullmatch(token):
        return False
    if token != canonicalize_alternate_witness_token(token):
        return False
    if GERMAN_UMLAUT_RE.search(token):
        return False
    if ALL_CAPS_RE.fullmatch(token):
        return False
    if token.lower() in GERMAN_HINT_WORDS:
        return False
    return True


def alternate_witness_distance_key(token: str) -> str:
    t = canonicalize_alternate_witness_token(token.lower())
    t = t.translate(SKELETON_MAP)
    t = t.replace("'", "").replace("’", "").replace("-", "")
    return t


GOOGLE_LOC_FRICATIVE_UPGRADE_PAIRS = {
    ("s", "ś"),
    ("S", "Ś"),
    ("z", "ź"),
    ("Z", "Ź"),
}


def token_is_google_loc_fricative_upgrade(base_token: str, alternate_token: str) -> bool:
    if len(base_token) != len(alternate_token):
        return False
    saw_upgrade = False
    for base_char, alternate_char in zip(base_token, alternate_token):
        if base_char == alternate_char:
            continue
        if (base_char, alternate_char) in GOOGLE_LOC_FRICATIVE_UPGRADE_PAIRS:
            saw_upgrade = True
            continue
        return False
    return saw_upgrade


GOOGLE_LOC_NASAL_UPGRADE_PAIRS = {
    ("n", "ṅ"),
    ("N", "Ṅ"),
    ("n", "ñ"),
    ("N", "Ñ"),
}

GOOGLE_LOC_VELAR_NASAL_UPGRADE_PAIRS = {
    ("ñ", "ṅ"),
    ("Ñ", "Ṅ"),
}

GOOGLE_LOC_VELAR_NASAL_BLOCKING_CLUSTERS = ("dz", "j", "c")


def token_is_google_loc_nasal_upgrade(base_token: str, alternate_token: str) -> bool:
    if len(base_token) != len(alternate_token):
        return False
    saw_upgrade = False
    for base_char, alternate_char in zip(base_token, alternate_token):
        if base_char == alternate_char:
            continue
        if (base_char, alternate_char) in GOOGLE_LOC_NASAL_UPGRADE_PAIRS:
            saw_upgrade = True
            continue
        return False
    return saw_upgrade


def token_is_google_loc_velar_nasal_upgrade(
    base_token: str, alternate_token: str
) -> bool:
    if len(base_token) != len(alternate_token):
        return False
    saw_upgrade = False
    for index, (base_char, alternate_char) in enumerate(
        zip(base_token, alternate_token)
    ):
        if base_char == alternate_char:
            continue
        if (base_char, alternate_char) not in GOOGLE_LOC_VELAR_NASAL_UPGRADE_PAIRS:
            return False
        tail = base_token[index + 1 : index + 3].lower()
        if any(tail.startswith(cluster) for cluster in GOOGLE_LOC_VELAR_NASAL_BLOCKING_CLUSTERS):
            return False
        saw_upgrade = True
    return saw_upgrade


ALTERNATE_WITNESS_TOKEN_RE = re.compile(
    r"[0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňß$]+(?:['’.$-][0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňß$]+)*"
)


def extract_alternate_witness_tokens(line: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in ALTERNATE_WITNESS_TOKEN_RE.finditer(line)]


def line_is_translit_context(info: "LineInfo | None") -> bool:
    if info is None:
        return False
    return info.has_tibetan or info.is_entry_start or len(info.translit_tokens) >= 2


def prepare_witness(
    text: str,
    audit_by_line: dict[tuple[int, int], dict[str, str]],
    *,
    google_vision: bool = False,
) -> dict[str, object]:
    if google_vision:
        text = normalize_google_vision_page_markers(text)
    text = normalize_form_feed_page_number_lines(text)
    (
        entries,
        line_infos,
        line_rows,
        validator_rows,
        summary,
        page_lines,
    ) = parse_entries(text, audit_by_line)
    google_vision_change_rows: list[list[str]] = []
    google_vision_rewrite_count = 0
    text, structural_change_rows, structural_rewrite_count = apply_structural_german_quote_wrap_repairs(
        page_lines,
        line_infos,
    )
    if structural_rewrite_count:
        (
            entries,
            line_infos,
            line_rows,
            validator_rows,
            summary,
            page_lines,
        ) = parse_entries(text, audit_by_line)
    if google_vision:
        text, google_vision_change_rows, google_vision_rewrite_count = apply_google_vision_loc_preclean(
            page_lines,
            line_infos,
        )
        if google_vision_rewrite_count:
            (
                entries,
                line_infos,
                line_rows,
                validator_rows,
                summary,
                page_lines,
            ) = parse_entries(text, audit_by_line)
    return {
        "text": text,
        "entries": entries,
        "line_infos": line_infos,
        "line_rows": line_rows,
        "validator_rows": validator_rows,
        "summary": summary,
        "page_lines": page_lines,
        "structural_change_rows": structural_change_rows,
        "structural_rewrite_count": structural_rewrite_count,
        "google_vision_change_rows": google_vision_change_rows,
        "google_vision_rewrite_count": google_vision_rewrite_count,
    }


def alternate_witness_reason(
    base_token: str,
    alternate_token: str,
    *,
    line_info: "LineInfo | None",
    line_text: str,
) -> str | None:
    if base_token == alternate_token:
        return None
    if token_is_alternate_witness_citation_siglum_upgrade(base_token, alternate_token):
        return "alternate_witness_citation_siglum"
    if line_is_citation_like(line_info, line_text):
        rewritten_base = citation_safe_confusable_rewrite(base_token)
        if rewritten_base == alternate_token:
            return "alternate_witness_citation_cleanup"
    if not line_is_translit_context(line_info):
        return None
    if token_is_safe_hyphenated_initial_i_to_l_translit(base_token, alternate_token):
        return "alternate_witness_hyphenated_initial_i_to_l_translit"
    if token_is_initial_i_translit_candidate(base_token, alternate_token):
        return "alternate_witness_initial_i_to_l_translit"
    if token_is_german_like(base_token):
        return None
    if ALL_CAPS_RE.fullmatch(base_token) or ALL_CAPS_RE.fullmatch(alternate_token):
        return None
    if token_is_alternate_witness_clean_translit(base_token):
        if alternate_witness_distance_key(base_token) == alternate_witness_distance_key(
            alternate_token
        ):
            if token_is_google_loc_fricative_upgrade(base_token, alternate_token):
                return "alternate_witness_google_loc_fricative_upgrade"
            if token_is_google_loc_velar_nasal_upgrade(base_token, alternate_token):
                return "alternate_witness_google_loc_velar_nasal_upgrade"
            if token_is_google_loc_nasal_upgrade(base_token, alternate_token):
                return "alternate_witness_google_loc_nasal_upgrade"
    if not token_is_alternate_witness_clean_translit(alternate_token):
        return None
    base_canon = canonicalize_alternate_witness_token(base_token)
    alternate_canon = canonicalize_alternate_witness_token(alternate_token)
    if not base_canon or base_canon != alternate_canon:
        return None
    if token_is_alternate_witness_clean_translit(base_token):
        return None
    return "alternate_witness_strict_translit"


def arbitrate_alternate_witness(
    base_page_lines: list[list[str]],
    base_line_infos: list["LineInfo"],
    alternate_page_lines: list[list[str]],
    alternate_line_infos: list["LineInfo"],
    alternate_google_vision: bool = False,
) -> tuple[str, list[list[str]], list[list[str]], int]:
    def normalize_alignment_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        normalized = re.sub(r"\s+", " ", normalized).strip().lower()
        return normalized

    def canonical_alignment_line(line: str) -> str:
        tokens = extract_alternate_witness_tokens(line)
        if not tokens:
            return normalize_alignment_text(line)
        parts: list[str] = []
        cursor = 0
        for token, start, end in tokens:
            parts.append(normalize_alignment_text(line[cursor:start]))
            parts.append(canonicalize_alternate_witness_token(token) or normalize_alignment_text(token))
            cursor = end
        parts.append(normalize_alignment_text(line[cursor:]))
        return " ".join(part for part in parts if part)

    def is_google_alignment_junk_line(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if any(ch.isalnum() for ch in stripped):
            return False
        if re.search(r"[\u0F00-\u0FFF]", stripped):
            return False
        return bool(re.fullmatch(r"[-–—=~_*.,:;|/\\\\(){}\[\]<>\"'`]+", stripped))

    def line_similarity(base_line: str, alternate_line: str) -> float:
        return SequenceMatcher(
            None,
            canonical_alignment_line(base_line),
            canonical_alignment_line(alternate_line),
            autojunk=False,
        ).ratio()

    def page_similarity(
        base_page: list[str],
        alternate_page: list[str],
        alternate_google_vision: bool = False,
    ) -> float:
        base_nonempty = [line for line in base_page if line.strip()]
        alternate_nonempty = [
            line
            for line in alternate_page
            if line.strip()
            and not (
                alternate_google_vision
                and is_google_alignment_junk_line(line)
            )
        ]
        if not base_nonempty or not alternate_nonempty:
            return 1.0 if not base_nonempty and not alternate_nonempty else 0.0
        sample_size = min(3, len(base_nonempty), len(alternate_nonempty))
        if sample_size == 0:
            return 0.0
        base_samples = (
            base_nonempty[:sample_size]
            + base_nonempty[max(0, len(base_nonempty) - sample_size):]
        )[: sample_size * 2]
        alternate_samples = (
            alternate_nonempty[:sample_size]
            + alternate_nonempty[max(0, len(alternate_nonempty) - sample_size):]
        )[: sample_size * 2]
        comparisons = zip(base_samples, alternate_samples)
        scores = [line_similarity(base_line, alternate_line) for base_line, alternate_line in comparisons]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    base_info_by_key = {(info.page, info.line): info for info in base_line_infos}
    context_free_alternate_reasons = {
        "alternate_witness_citation_siglum",
        "alternate_witness_citation_cleanup",
    }

    def alternate_reason_allowed_for_line(
        reason: str,
        line_info: "LineInfo | None",
    ) -> bool:
        return line_is_translit_context(line_info) or reason in context_free_alternate_reasons

    def canonical_page_token_keys(
        page: list[str],
        *,
        google_vision: bool = False,
    ) -> list[str]:
        keys: list[str] = []
        for line in page:
            if not line.strip():
                continue
            if google_vision and is_google_alignment_junk_line(line):
                continue
            for token, _start, _end in extract_alternate_witness_tokens(line):
                key = alternate_witness_distance_key(token)
                if len(key) >= 2:
                    keys.append(key)
        return keys

    def page_token_overlap(
        base_page: list[str],
        alternate_page: list[str],
        *,
        alternate_google_vision: bool = False,
    ) -> tuple[int, float]:
        base_keys = set(canonical_page_token_keys(base_page))
        alternate_keys = set(
            canonical_page_token_keys(
                alternate_page,
                google_vision=alternate_google_vision,
            )
        )
        if not base_keys or not alternate_keys:
            return 0, 0.0
        shared = len(base_keys & alternate_keys)
        return shared, shared / min(len(base_keys), len(alternate_keys))

    @dataclass(frozen=True)
    class AlignmentDiagnostics:
        alignment_method: str = ""
        alternate_page: str = ""
        page_match_score: str = ""
        canonical_overlap: str = ""
        shared_canonical_tokens: str = ""
        base_nonempty_count: str = ""
        alternate_nonempty_count: str = ""
        line_count_ratio: str = ""

        def as_row(self) -> list[str]:
            return [
                self.alignment_method,
                self.alternate_page,
                self.page_match_score,
                self.canonical_overlap,
                self.shared_canonical_tokens,
                self.base_nonempty_count,
                self.alternate_nonempty_count,
                self.line_count_ratio,
            ]

    def build_alignment_diagnostics(
        alignment_method: str,
        base_page: list[str],
        alternate_page: list[str],
        *,
        alternate_page_no: int | None,
        page_match_score: float,
    ) -> AlignmentDiagnostics:
        base_nonempty_count = sum(1 for line in base_page if line.strip())
        alternate_nonempty_count = sum(
            1
            for line in alternate_page
            if line.strip()
            and not (
                alternate_google_vision
                and is_google_alignment_junk_line(line)
            )
        )
        line_count_ratio = ""
        if base_nonempty_count and alternate_nonempty_count:
            line_count_ratio = f"{base_nonempty_count / alternate_nonempty_count:.3f}"
        shared_tokens, overlap = page_token_overlap(
            base_page,
            alternate_page,
            alternate_google_vision=alternate_google_vision,
        )
        return AlignmentDiagnostics(
            alignment_method=alignment_method,
            alternate_page=str(alternate_page_no) if alternate_page_no is not None else "",
            page_match_score=f"{page_match_score:.3f}",
            canonical_overlap=f"{overlap:.3f}",
            shared_canonical_tokens=str(shared_tokens),
            base_nonempty_count=str(base_nonempty_count),
            alternate_nonempty_count=str(alternate_nonempty_count),
            line_count_ratio=line_count_ratio,
        )

    def guarded_rewrapped_page_fallback(
        base_page: list[str],
        alternate_page: list[str],
        *,
        base_page_no: int | None,
        alternate_page_no: int | None,
        candidate_score: float,
        base_nonempty_count: int,
        alternate_nonempty_count: int,
        alternate_google_vision: bool = False,
    ) -> list[str] | None:
        if base_page_no is None or alternate_page_no is None:
            return None
        if candidate_score < 0.50:
            return None
        if abs(alternate_page_no - base_page_no) > 2:
            return None
        if not base_nonempty_count or not alternate_nonempty_count:
            return None
        line_count_ratio = base_nonempty_count / alternate_nonempty_count
        if line_count_ratio < 0.5 or line_count_ratio > 2.0:
            return None
        shared_tokens, overlap = page_token_overlap(
            base_page,
            alternate_page,
            alternate_google_vision=alternate_google_vision,
        )
        if shared_tokens < 10 or overlap < 0.35:
            return None

        base_token_records: list[tuple[int, str, int, int, str]] = []
        for line_idx, line in enumerate(base_page, start=1):
            if not line.strip():
                continue
            for token, start, end in extract_alternate_witness_tokens(line):
                key = alternate_witness_distance_key(token)
                if key:
                    base_token_records.append((line_idx, token, start, end, key))

        alternate_token_records: list[tuple[str, str]] = []
        for line in alternate_page:
            if not line.strip():
                continue
            if alternate_google_vision and is_google_alignment_junk_line(line):
                continue
            for token, _start, _end in extract_alternate_witness_tokens(line):
                key = alternate_witness_distance_key(token)
                if key:
                    alternate_token_records.append((token, key))

        if not base_token_records or not alternate_token_records:
            return None

        replacements_by_line: dict[int, list[tuple[int, int, str]]] = defaultdict(list)
        base_keys = [record[4] for record in base_token_records]
        alternate_keys = [record[1] for record in alternate_token_records]
        matcher = SequenceMatcher(None, base_keys, alternate_keys, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                paired_indexes = zip(range(i1, i2), range(j1, j2))
            elif tag == "replace" and i2 - i1 == j2 - j1:
                paired_indexes = zip(range(i1, i2), range(j1, j2))
            else:
                continue
            for base_record_idx, alternate_record_idx in paired_indexes:
                line_idx, base_token, start, end, _key = base_token_records[base_record_idx]
                alternate_token = alternate_token_records[alternate_record_idx][0]
                if base_token == alternate_token:
                    continue
                line_info = base_info_by_key.get((base_page_no, line_idx))
                reason = alternate_witness_reason(
                    base_token,
                    alternate_token,
                    line_info=line_info,
                    line_text=base_page[line_idx - 1],
                )
                if reason is None:
                    continue
                if not alternate_reason_allowed_for_line(reason, line_info):
                    continue
                replacements_by_line[line_idx].append((start, end, alternate_token))

        if not replacements_by_line:
            return None

        aligned_page = base_page[:]
        for line_idx, replacements in replacements_by_line.items():
            line = base_page[line_idx - 1]
            for start, end, alternate_token in sorted(replacements, reverse=True):
                line = line[:start] + alternate_token + line[end:]
            aligned_page[line_idx - 1] = line
        return aligned_page

    def align_alternate_page(
        base_page: list[str],
        alternate_page: list[str],
        alternate_google_vision: bool = False,
        *,
        base_page_no: int | None = None,
        alternate_page_no: int | None = None,
    ) -> tuple[list[str] | None, str | None, str, str, float, str]:
        base_nonempty_count = sum(1 for line in base_page if line.strip())

        def line_has_compatible_structure(base_line: str, alternate_line: str) -> bool:
            if base_line.strip() == alternate_line.strip():
                return True
            base_tokens = extract_alternate_witness_tokens(base_line)
            alternate_tokens = extract_alternate_witness_tokens(alternate_line)
            if not base_tokens or not alternate_tokens:
                return False
            if len(base_tokens) != len(alternate_tokens):
                return False

            def non_token_fragments(line: str, tokens: list[tuple[str, int, int]]) -> list[str]:
                fragments: list[str] = []
                cursor = 0
                for _token, start, end in tokens:
                    fragments.append(normalize_alignment_text(line[cursor:start]))
                    cursor = end
                fragments.append(normalize_alignment_text(line[cursor:]))
                return fragments

            return non_token_fragments(base_line, base_tokens) == non_token_fragments(
                alternate_line,
                alternate_tokens,
            )

        def page_has_compatible_content(aligned_page: list[str]) -> bool:
            compatibility_hits = 0
            comparable_lines = 0
            for base_line, alternate_line in zip(base_page, aligned_page):
                base_text = base_line.strip()
                alternate_text = alternate_line.strip()
                if not base_text or not alternate_text:
                    continue
                comparable_lines += 1
                if line_has_compatible_structure(base_line, alternate_line) or line_similarity(base_line, alternate_line) >= 0.93:
                    compatibility_hits += 1
            if comparable_lines <= 1:
                return compatibility_hits == comparable_lines
            return compatibility_hits >= min(2, comparable_lines)

        def aligned_page_score(aligned_page: list[str]) -> float:
            total_similarity = 0.0
            compatibility_hits = 0
            comparable_lines = 0
            for base_line, alternate_line in zip(base_page, aligned_page):
                base_text = base_line.strip()
                alternate_text = alternate_line.strip()
                if not base_text or not alternate_text:
                    continue
                comparable_lines += 1
                total_similarity += line_similarity(base_line, alternate_line)
                if line_has_compatible_structure(base_line, alternate_line):
                    compatibility_hits += 1
            if comparable_lines == 0:
                return page_similarity(
                    base_page,
                    aligned_page,
                    alternate_google_vision=alternate_google_vision,
                )
            denominator = max(base_nonempty_count, 1)
            return (
                total_similarity / denominator
                + 0.05 * (compatibility_hits / denominator)
            )

        def align_nonempty_runs() -> list[str] | None:
            base_nonempty = [(idx, line) for idx, line in enumerate(base_page, start=1) if line.strip()]
            alternate_nonempty = [
                (idx, line)
                for idx, line in enumerate(alternate_page, start=1)
                if line.strip()
                and not (
                    alternate_google_vision
                    and is_google_alignment_junk_line(line)
                )
            ]
            if not base_nonempty and not alternate_nonempty:
                return [""] * len(base_page)
            if not base_nonempty or not alternate_nonempty:
                return None

            from functools import lru_cache

            def redistribute_grouped_alignment(
                base_lines: list[str],
                alternate_lines: list[str],
            ) -> tuple[str, ...] | None:
                normalized_alternate_lines = [line.strip() for line in alternate_lines if line.strip()]
                if not normalized_alternate_lines:
                    return None
                if len(base_lines) == 1:
                    return (" ".join(normalized_alternate_lines),)
                if len(base_lines) == len(normalized_alternate_lines):
                    direct_mapping = tuple(normalized_alternate_lines)
                    if all(
                        line_similarity(base_line, alternate_line) >= 0.55
                        for base_line, alternate_line in zip(base_lines, direct_mapping)
                    ):
                        return direct_mapping

                alternate_joined = " ".join(normalized_alternate_lines)
                alternate_tokens = alternate_joined.split()
                if len(alternate_tokens) < len(base_lines):
                    return None

                @lru_cache(maxsize=None)
                def best_partition(
                    base_offset: int,
                    token_offset: int,
                ) -> tuple[float, tuple[str, ...]] | None:
                    remaining_base = len(base_lines) - base_offset
                    remaining_tokens = len(alternate_tokens) - token_offset
                    if remaining_base == 0:
                        if remaining_tokens == 0:
                            return 0.0, ()
                        return None
                    if remaining_tokens < remaining_base:
                        return None

                    best: tuple[float, tuple[str, ...]] | None = None
                    max_end = len(alternate_tokens) - (remaining_base - 1)
                    base_line = base_lines[base_offset]
                    base_token_count = max(1, len(base_line.split()))
                    for end in range(token_offset + 1, max_end + 1):
                        candidate_line = " ".join(alternate_tokens[token_offset:end])
                        score = line_similarity(base_line, candidate_line)
                        if line_has_compatible_structure(base_line, candidate_line):
                            score += 0.15
                        score -= 0.02 * abs(len(candidate_line.split()) - base_token_count)
                        if score < 0.52:
                            continue
                        suffix = best_partition(base_offset + 1, end)
                        if suffix is None:
                            continue
                        total_score = score + suffix[0]
                        candidate = (total_score, (candidate_line,) + suffix[1])
                        if best is None or total_score > best[0]:
                            best = candidate
                    return best

                best = best_partition(0, 0)
                if best is None:
                    return None
                redistributed = best[1]
                if any(
                    line_similarity(base_line, alternate_line) < 0.55
                    for base_line, alternate_line in zip(base_lines, redistributed)
                ):
                    return None
                return redistributed

            @lru_cache(maxsize=None)
            def best_alignment(
                base_pos: int,
                alternate_pos: int,
            ) -> tuple[float, tuple[tuple[int, int, tuple[str, ...]], ...]] | None:
                if base_pos == len(base_nonempty):
                    if alternate_pos == len(alternate_nonempty):
                        return 0.0, ()
                    return None
                if alternate_pos == len(alternate_nonempty):
                    return None

                remaining_base = len(base_nonempty) - base_pos
                remaining_alternate = len(alternate_nonempty) - alternate_pos
                if max(remaining_base, remaining_alternate) > min(remaining_base, remaining_alternate) * 3:
                    return None

                best: tuple[float, tuple[tuple[int, int, str], ...]] | None = None
                max_base_take = min(3, remaining_base)
                max_alternate_take = min(3, remaining_alternate)
                for take_base in range(1, max_base_take + 1):
                    after_base = remaining_base - take_base
                    for take_alternate in range(1, max_alternate_take + 1):
                        after_alternate = remaining_alternate - take_alternate
                        if after_base > after_alternate * 3 or after_alternate > after_base * 3:
                            continue

                        base_group = " ".join(
                            base_nonempty[base_pos + offset][1].strip()
                            for offset in range(take_base)
                        )
                        alternate_group = " ".join(
                            alternate_nonempty[alternate_pos + offset][1].strip()
                            for offset in range(take_alternate)
                        )
                        score = line_similarity(base_group, alternate_group)
                        if line_has_compatible_structure(base_group, alternate_group):
                            score += 0.2
                        if score < 0.72:
                            continue
                        redistributed_lines = redistribute_grouped_alignment(
                            [
                                base_nonempty[base_pos + offset][1]
                                for offset in range(take_base)
                            ],
                            [
                                alternate_nonempty[alternate_pos + offset][1]
                                for offset in range(take_alternate)
                            ],
                        )
                        if redistributed_lines is None:
                            continue
                        suffix = best_alignment(base_pos + take_base, alternate_pos + take_alternate)
                        if suffix is None:
                            continue
                        total_score = score + suffix[0]
                        candidate = (
                            total_score,
                            ((take_base, take_alternate, redistributed_lines),) + suffix[1],
                        )
                        if best is None or total_score > best[0]:
                            best = candidate
                return best

            alignment = best_alignment(0, 0)
            if alignment is None:
                return None

            aligned_page = [""] * len(base_page)
            base_cursor = 0
            for take_base, _take_alternate, aligned_lines in alignment[1]:
                for offset, aligned_line in enumerate(aligned_lines):
                    base_idx, _base_line = base_nonempty[base_cursor + offset]
                    aligned_page[base_idx - 1] = aligned_line
                base_cursor += take_base
            return aligned_page

        def align_reordered_nonempty_lines() -> list[str] | None:
            base_nonempty = [(idx, line) for idx, line in enumerate(base_page, start=1) if line.strip()]
            alternate_nonempty = [
                (idx, line)
                for idx, line in enumerate(alternate_page, start=1)
                if line.strip()
                and not (
                    alternate_google_vision
                    and is_google_alignment_junk_line(line)
                )
            ]
            if not base_nonempty and not alternate_nonempty:
                return [""] * len(base_page)
            if not base_nonempty or not alternate_nonempty:
                return None
            if len(base_nonempty) != len(alternate_nonempty):
                return None

            scored_pairs: list[tuple[float, int, int]] = []
            for base_pos, (_base_idx, base_line) in enumerate(base_nonempty):
                for alternate_pos, (_alternate_idx, alternate_line) in enumerate(alternate_nonempty):
                    score = line_similarity(base_line, alternate_line)
                    compatible_structure = line_has_compatible_structure(base_line, alternate_line)
                    if compatible_structure:
                        score += 0.2
                    if score < 0.9:
                        continue
                    scored_pairs.append((score, base_pos, alternate_pos))

            if len(scored_pairs) < len(base_nonempty):
                return None

            scored_pairs.sort(reverse=True)
            used_base: set[int] = set()
            used_alternate: set[int] = set()
            matched_pairs: list[tuple[int, int]] = []
            for _score, base_pos, alternate_pos in scored_pairs:
                if base_pos in used_base or alternate_pos in used_alternate:
                    continue
                used_base.add(base_pos)
                used_alternate.add(alternate_pos)
                matched_pairs.append((base_pos, alternate_pos))
                if len(matched_pairs) == len(base_nonempty):
                    break

            if len(matched_pairs) != len(base_nonempty):
                return None

            aligned_page = [""] * len(base_page)
            for base_pos, alternate_pos in matched_pairs:
                base_idx, _base_line = base_nonempty[base_pos]
                _alternate_idx, alternate_line = alternate_nonempty[alternate_pos]
                aligned_page[base_idx - 1] = alternate_line.strip()
            return aligned_page

        if len(base_page) == len(alternate_page):
            if not page_has_compatible_content(alternate_page):
                reordered_page = align_reordered_nonempty_lines()
                if reordered_page is not None and page_has_compatible_content(reordered_page):
                    return (
                        reordered_page,
                        None,
                        "",
                        "",
                        aligned_page_score(reordered_page),
                        "reordered_page_alignment",
                    )
                return (
                    None,
                    "unalignable_page_content",
                    str(len(base_page)),
                    str(len(alternate_page)),
                    page_similarity(
                        base_page,
                        alternate_page,
                        alternate_google_vision=alternate_google_vision,
                    ),
                    "",
                )
            return (
                alternate_page,
                None,
                "",
                "",
                aligned_page_score(alternate_page),
                "ordinary_page_alignment",
            )
        base_nonempty = [(idx, line) for idx, line in enumerate(base_page, start=1) if line.strip()]
        alternate_nonempty = [
            (idx, line)
            for idx, line in enumerate(alternate_page, start=1)
            if line.strip()
            and not (
                alternate_google_vision
                and is_google_alignment_junk_line(line)
            )
        ]
        aligned_page = align_nonempty_runs()
        if aligned_page is None:
            mismatch_reason = "unalignable_rewrapped_page"
            if (
                abs(len(base_nonempty) - len(alternate_nonempty)) > 3
                and min(len(base_nonempty), len(alternate_nonempty)) <= 1
            ):
                mismatch_reason = "nonempty_line_count_mismatch"
            candidate_score = page_similarity(
                base_page,
                alternate_page,
                alternate_google_vision=alternate_google_vision,
            )
            if mismatch_reason == "unalignable_rewrapped_page":
                fallback_page = guarded_rewrapped_page_fallback(
                    base_page,
                    alternate_page,
                    base_page_no=base_page_no,
                    alternate_page_no=alternate_page_no,
                    candidate_score=candidate_score,
                    base_nonempty_count=len(base_nonempty),
                    alternate_nonempty_count=len(alternate_nonempty),
                    alternate_google_vision=alternate_google_vision,
                )
                if fallback_page is not None:
                    return (
                        fallback_page,
                        None,
                        str(len(base_nonempty)),
                        str(len(alternate_nonempty)),
                        candidate_score,
                        "recovered_rewrapped_page",
                    )
            return (
                None,
                mismatch_reason,
                str(len(base_nonempty)),
                str(len(alternate_nonempty)),
                candidate_score,
                "",
            )
        if not page_has_compatible_content(aligned_page):
            return (
                None,
                "unalignable_page_content",
                str(len(base_page)),
                str(len(alternate_page)),
                page_similarity(
                    base_page,
                    alternate_page,
                    alternate_google_vision=alternate_google_vision,
                ),
                "",
            )
        return (
            aligned_page,
            None,
            str(len(base_page)),
            str(len(alternate_page)),
            aligned_page_score(aligned_page),
            "rewrapped_page_alignment",
        )

    adoption_rows: list[list[str]] = []
    unresolved_rows: list[list[str]] = []
    aligned_alternate_pages: list[list[str]] = []
    aligned_alternate_page_diagnostics: list[AlignmentDiagnostics] = []
    empty_alignment_diagnostics = AlignmentDiagnostics()
    alternate_page_idx = 0
    for page_idx, base_page in enumerate(base_page_lines, start=1):
        matched_page_idx: int | None = None
        aligned_page: list[str] | None = None
        matched_alignment_diagnostics = empty_alignment_diagnostics
        reason = None
        left_count = ""
        right_count = ""
        best_score = -1.0
        search_idx = alternate_page_idx
        max_search_idx = min(len(alternate_page_lines), alternate_page_idx + 5)
        searched_alternate_pages: list[str] = []
        search_window = "searched_alternate_pages=none"
        if alternate_page_idx < max_search_idx:
            search_window = f"searched_alternate_pages={alternate_page_idx + 1}-{max_search_idx}"
        while search_idx < max_search_idx:
            (
                candidate_page,
                candidate_reason,
                candidate_left_count,
                candidate_right_count,
                candidate_score,
                candidate_alignment_method,
            ) = align_alternate_page(
                base_page,
                alternate_page_lines[search_idx],
                alternate_google_vision=alternate_google_vision,
                base_page_no=page_idx,
                alternate_page_no=search_idx + 1,
            )
            searched_alternate_pages.append(
                (
                    f"{search_idx + 1}:"
                    f"{candidate_reason or 'aligned'}"
                    f"({candidate_left_count or '-'}"
                    f"/{candidate_right_count or '-'})"
                )
            )
            if candidate_page is not None:
                if candidate_score > best_score:
                    matched_page_idx = search_idx
                    aligned_page = candidate_page
                    left_count = candidate_left_count
                    right_count = candidate_right_count
                    best_score = candidate_score
                    matched_alignment_diagnostics = build_alignment_diagnostics(
                        candidate_alignment_method,
                        base_page,
                        alternate_page_lines[search_idx],
                        alternate_page_no=search_idx + 1,
                        page_match_score=candidate_score,
                    )
            elif reason is None:
                reason = candidate_reason or "line_count_mismatch"
                left_count = candidate_left_count
                right_count = candidate_right_count
            search_idx += 1
        if aligned_page is None:
            unresolved_rows.append(
                [
                    str(page_idx),
                    "",
                    "",
                    "",
                    "",
                    reason or "line_count_mismatch",
                    left_count,
                    right_count,
                    search_window,
                    ";".join(searched_alternate_pages),
                ]
            )
            aligned_alternate_pages.append(base_page[:])
            aligned_alternate_page_diagnostics.append(empty_alignment_diagnostics)
            if alternate_page_idx < len(alternate_page_lines):
                alternate_page_idx += 1
            continue
        alternate_page_idx = matched_page_idx + 1
        aligned_alternate_pages.append(aligned_page)
        aligned_alternate_page_diagnostics.append(matched_alignment_diagnostics)
    rewritten_pages = [page[:] for page in base_page_lines]
    adoption_count = 0
    for page_idx, (base_page, alternate_page, alignment_diagnostics) in enumerate(
        zip(base_page_lines, aligned_alternate_pages, aligned_alternate_page_diagnostics),
        start=1,
    ):
        for line_idx, (base_line, alternate_line) in enumerate(zip(base_page, alternate_page), start=1):
            if base_line == alternate_line:
                continue
            line_info = base_info_by_key.get((page_idx, line_idx))
            translit_context = line_is_translit_context(line_info)
            base_tokens = extract_alternate_witness_tokens(base_line)
            alternate_tokens = extract_alternate_witness_tokens(alternate_line)
            if len(base_tokens) != len(alternate_tokens):
                unresolved_rows.append(
                    [
                        str(page_idx),
                        str(line_idx),
                        "",
                        "",
                        "",
                        "token_count_mismatch",
                        str(len(base_tokens)),
                        str(len(alternate_tokens)),
                        base_line,
                        alternate_line,
                    ]
                )
                continue
            rebuilt: list[str] = []
            cursor = 0
            line_adoptions = 0
            for token_index, (base_match, alternate_match) in enumerate(zip(base_tokens, alternate_tokens), start=1):
                base_token, start, end = base_match
                alternate_token = alternate_match[0]
                rebuilt.append(base_line[cursor:start])
                replacement = base_token
                if base_token != alternate_token:
                    reason = alternate_witness_reason(
                        base_token,
                        alternate_token,
                        line_info=line_info,
                        line_text=base_line,
                    )
                    if reason:
                        if translit_context or reason in context_free_alternate_reasons:
                            replacement = alternate_token
                            adoption_rows.append(
                                [
                                    str(page_idx),
                                    str(line_idx),
                                    str(token_index),
                                    base_token,
                                    alternate_token,
                                    reason,
                                    distance_key(base_token),
                                    distance_key(alternate_token),
                                    base_line,
                                    alternate_line,
                                    *alignment_diagnostics.as_row(),
                                ]
                            )
                            line_adoptions += 1
                        else:
                            unresolved_rows.append(
                                [
                                    str(page_idx),
                                    str(line_idx),
                                    str(token_index),
                                    base_token,
                                    alternate_token,
                                    "non_translit_context",
                                    distance_key(base_token),
                                    distance_key(alternate_token),
                                    base_line,
                                    alternate_line,
                                ]
                            )
                    elif token_is_ignorable_alternate_siglum_disagreement(
                        base_token,
                        alternate_token,
                        line_info=line_info,
                        base_line=base_line,
                        alternate_line=alternate_line,
                    ):
                        pass
                    else:
                        unresolved_rows.append(
                            [
                                str(page_idx),
                                str(line_idx),
                                str(token_index),
                                base_token,
                                alternate_token,
                                "unsafe_token_disagreement"
                                if translit_context
                                else "non_translit_context",
                                distance_key(base_token),
                                distance_key(alternate_token),
                                base_line,
                                alternate_line,
                            ]
                        )
                rebuilt.append(replacement)
                cursor = end
            rebuilt.append(base_line[cursor:])
            if line_adoptions:
                rewritten_pages[page_idx - 1][line_idx - 1] = "".join(rebuilt)
                adoption_count += line_adoptions
    return "\f".join("\n".join(page) for page in rewritten_pages), adoption_rows, unresolved_rows, adoption_count


def token_is_titlecase_or_lower_compound_shape(token: str) -> bool:
    def part_is_tibetan_mixed_caps_shape(part: str) -> bool:
        letters = [ch for ch in part if ch.isalpha()]
        if len(letters) < 3:
            return False
        if not letters[0].islower():
            return False
        upper_idxs = [idx for idx, ch in enumerate(letters) if ch.isupper()]
        if not upper_idxs or len(upper_idxs) > 2:
            return False
        if any(idx == 0 or idx > 3 for idx in upper_idxs):
            return False
        if max(upper_idxs) >= len(letters) - 1:
            return False
        for idx, ch in enumerate(letters):
            if idx in upper_idxs:
                continue
            if not ch.islower():
                return False
        return True

    for part in token.split("-"):
        if not part:
            continue
        letters = [ch for ch in part if ch.isalpha()]
        if not letters:
            continue
        if all(ch.islower() for ch in letters):
            continue
        if letters[0].isupper() and all(ch.islower() for ch in letters[1:]):
            continue
        if part_is_tibetan_mixed_caps_shape(part):
            continue
        return False
    return True


def token_is_relaxed_dollar_translit_shape(token: str) -> bool:
    if not LATIN_TOKEN_RE.fullmatch(token):
        return False
    canon = canonicalize_translit_token(token)
    if token != canon:
        changed = False
        for ch in token:
            mapped = CONFUSABLE_TO_CANON.get(ch, ch)
            if mapped == ch:
                continue
            changed = True
            if ch not in {"I", "ı", "ñ", "Ñ", "ş", "Ş", "ņ", "Ņ", "ã", "Ã"}:
                return False
        if not changed:
            return False
    if "$" in token:
        return False
    if token.lower() in GERMAN_HINT_WORDS:
        return False
    if ROMAN_NUMERAL_RE.fullmatch(token):
        return False
    if ALL_CAPS_RE.fullmatch(token):
        return False
    if not token_is_titlecase_or_lower_compound_shape(token):
        return False
    if GERMAN_UMLAUT_RE.search(token):
        low = token.lower()
        if low.endswith(GERMAN_WORD_SUFFIXES) and not (
            token_has_hard_translit_marker(token) or token_has_translit_cue(token)
        ):
            return False
    return True


def validate_translit_token(token: str) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    canon = canonicalize_translit_token(token)
    if "$" in token:
        canon = canonicalize_translit_token(dollar_to_sacute_preserve_case(token))
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


def line_has_siglum_context_cue(line_text: str) -> bool:
    if CITATION_SIGLUM_ARTIFACT_CUE_RE.search(line_text):
        return True
    if CITATION_SIGLUM_COORD_PAREN_RE.search(line_text):
        return True
    if CITATION_SIGLUM_DIGIT_ARTIFACT_RE.search(line_text):
        return True
    if CITATION_G_DOT_YU_COORD_RE.search(line_text):
        return True
    if CITATION_SIGLUM_LEADING_LAYOUT_RE.match(line_text):
        lead = line_text.lstrip().split(" ", 1)[0]
        if token_is_citation_siglum_candidate(lead):
            if (
                CITATION_YEAR_RE.search(line_text)
                or CITATION_SPLIT_YEAR_RE.search(line_text)
                or line_has_parenthetical_citation(line_text)
                or CITATION_CUE_RE.search(line_text)
            ):
                return True
    if line_has_allowlisted_siglum_context(line_text):
        return True
    return False


def line_is_citation_like(info: "LineInfo | None", line_text: str) -> bool:
    if info is not None and info.zone not in {
        "german_prose",
        "german_prose_with_translit",
        "latin_other",
        "other",
        "headword_line",
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
    if line_has_siglum_context_cue(line_text):
        return True
    if CITATION_BIBLIO_AUTHOR_YEAR_RE.match(line_text):
        return True
    if (
        CITATION_BIBLIO_CONTINUATION_HEAD_RE.match(line_text)
        and CITATION_BIBLIO_CONTINUATION_CUE_RE.search(line_text)
    ):
        return True
    if CITATION_BIBLIO_INLINE_CUE_RE.search(line_text):
        return True
    if CITATION_NOISY_YEAR_RE.search(line_text) and CITATION_CUE_RE.search(line_text):
        return True
    return bool(CITATION_CUE_RE.search(line_text))


def line_is_standalone_allowlisted_siglum(line_text: str) -> bool:
    stripped = line_text.strip()
    if not stripped:
        return False
    m = OCR_LATIN_TOKEN_RE.fullmatch(stripped)
    if m is None:
        return False
    token = m.group(0)
    core, _ = split_citation_siglum_token(token)
    if core.casefold() not in CITATION_SIGLUM_STANDALONE_ALLOWLIST:
        return False
    return token_is_citation_siglum_candidate(token)


def line_has_allowlisted_siglum_context(line_text: str) -> bool:
    if not line_text:
        return False
    allowlisted_hits: list[tuple[int, int]] = []
    for m in OCR_LATIN_TOKEN_RE.finditer(line_text):
        token = m.group(0)
        core, _ = split_citation_siglum_token(token)
        if core.casefold() not in CITATION_SIGLUM_STANDALONE_ALLOWLIST:
            continue
        allowlisted_hits.append((m.start(), m.end()))
        lead = line_text[max(0, m.start() - 3) : m.start()]
        tail = line_text[m.end() :]
        if "(" in lead or "[" in lead:
            if not tail or re.fullmatch(r"[\s\],.;:!?)]*", tail):
                return True
            # Wrapped citation where the siglum lands at a page break.
            if re.match(r"^\s*\f", tail):
                return True
    if not allowlisted_hits:
        return False
    if not re.search(r"\busw\.", line_text, re.IGNORECASE):
        return False
    if "(" not in line_text or ")" not in line_text:
        return False
    if not re.search(r"\b[A-Za-z$]{1,8}\d{1,4}\b", line_text):
        return False
    for start, end in allowlisted_hits:
        left = line_text[max(0, start - 2) : start]
        right = line_text[end : end + 2]
        if "," in left or "," in right:
            return True
    return False


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
    siglum = CITATION_SIGLUM_CASE_SENSITIVE_MAP.get(token)
    if siglum is not None:
        return siglum
    siglum = CITATION_SIGLUM_CANONICAL_BY_KEY.get(
        re.sub(r"[sś]+", "s", token.casefold())
    )
    if siglum is not None:
        return siglum
    siglum = CITATION_SIGLUM_CONFUSABLE_MAP.get(token.casefold())
    if siglum is not None:
        return siglum
    if "$" in token:
        # In sigla, `$` is more often OCR for acute-S (ś/Ś) than plain `s`.
        # Prefer that interpretation first, then fall back to plain `s` and
        # deletion for insertion-noise forms.
        for candidate in (
            token.replace("$", "Ś"),
            token.replace("$", "ś"),
            token.replace("$", "s"),
            token.replace("$", ""),
        ):
            collapsed_guess = re.sub(r"[sś]+", "s", candidate.casefold())
            siglum = CITATION_SIGLUM_CANONICAL_BY_KEY.get(collapsed_guess)
            if siglum is not None:
                return siglum
    # Allow wrapped/extended L$dz sigla forms such as L$dz-, L$dz-K, L$dz-R.
    if re.fullmatch(r"(?i)l\$dz(?:-[A-Za-z$]*)?", token):
        siglum = "Lśdz" + token[4:]
        return siglum.replace("$", "ś")
    return None


def token_is_ignorable_alternate_siglum_disagreement(
    base_token: str,
    alternate_token: str,
    *,
    line_info: LineInfo | None,
    base_line: str,
    alternate_line: str,
) -> bool:
    if not (
        line_is_citation_like(line_info, base_line)
        or line_is_citation_like(line_info, alternate_line)
        or line_has_parenthetical_citation(base_line)
        or line_has_parenthetical_citation(alternate_line)
    ):
        return False
    base_siglum = match_citation_siglum(base_token)
    alternate_siglum = match_citation_siglum(alternate_token)
    if base_siglum is None or alternate_siglum is None:
        return False
    base_siglum_key = re.sub(r"[sś]+", "s", base_siglum.casefold())
    alternate_siglum_key = re.sub(r"[sś]+", "s", alternate_siglum.casefold())
    if base_siglum_key != alternate_siglum_key:
        return False
    return base_token == base_siglum and alternate_token != alternate_siglum


def token_is_alternate_witness_citation_siglum_upgrade(
    base_token: str,
    alternate_token: str,
) -> bool:
    base_siglum = match_citation_siglum(base_token)
    alternate_siglum = match_citation_siglum(alternate_token)
    if base_siglum is None or alternate_siglum is None:
        return False
    base_siglum_key = re.sub(r"[sś]+", "s", base_siglum.casefold())
    alternate_siglum_key = re.sub(r"[sś]+", "s", alternate_siglum.casefold())
    if base_siglum_key != alternate_siglum_key:
        return False
    if base_token == base_siglum:
        return False
    return alternate_token == alternate_siglum


def split_citation_siglum_token(token: str) -> tuple[str, str]:
    core = token
    suffix = ""
    while core and core[-1] in ".,;:!?":
        suffix = core[-1] + suffix
        core = core[:-1]
    if core.endswith(("'", "’")):
        suffix = core[-1] + suffix
        core = core[:-1]
    return core, suffix


def citation_safe_confusable_rewrite(token: str) -> str:
    """Safe citation-only OCR fixes (no deletions, no translit remapping)."""
    out = token.replace("ı", "i")
    out, trail = split_citation_siglum_token(out)
    if not out:
        return token

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
    core, _ = split_citation_siglum_token(token)
    if len(core) < 2:
        return False
    collapsed_core = re.sub(r"[sś]+", "s", core.casefold())
    if CITATION_SIGLUM_CANONICAL_BY_KEY.get(collapsed_core) is not None:
        return True
    if CITATION_SIGLUM_CASE_SENSITIVE_MAP.get(core) is not None:
        return True
    if CITATION_SIGLUM_CONFUSABLE_MAP.get(core.casefold()) is not None:
        return match_citation_siglum(core) is not None
    if not re.fullmatch(
        rf"[{LATIN_CHARS}{OCR_CONFUSABLE_TOKEN_CHARS}0-9.]+"
        rf"(?:-[{LATIN_CHARS}{OCR_CONFUSABLE_TOKEN_CHARS}0-9.]*)?",
        core,
    ):
        return False
    if (
        "$" not in core
        and CITATION_SIGLUM_CONFUSABLE_MAP.get(core.casefold()) is None
        and CITATION_SIGLUM_CANONICAL_BY_KEY.get(collapsed_core) is None
    ):
        return False
    return match_citation_siglum(core) is not None


def line_has_citation_siglum_candidate(line_text: str) -> bool:
    if CITATION_SIGLUM_DIGIT_ARTIFACT_RE.search(line_text):
        return True
    for m in CITATION_SIGLUM_ALNUM_TOKEN_RE.finditer(line_text):
        if token_is_citation_siglum_candidate(m.group(0)):
            return True
    for m in OCR_LATIN_TOKEN_RE.finditer(line_text):
        if token_is_citation_siglum_candidate(m.group(0)):
            return True
    return False


def line_citation_siglum_candidate_count(line_text: str) -> int:
    count = 0
    for m in OCR_LATIN_TOKEN_RE.finditer(line_text):
        if token_is_citation_siglum_candidate(m.group(0)):
            count += 1
            if count >= 3:
                return count
    return count


def token_has_bracketed_siglum_context(line_text: str, token_core: str, start: int, end: int) -> bool:
    for opener, closer in (("(", ")"), ("[", "]")):
        open_idx = line_text.rfind(opener, 0, start + 1)
        if open_idx == -1:
            continue
        close_idx = line_text.find(closer, end)
        if close_idx == -1:
            continue
        if close_idx - open_idx > 72:
            continue
        if not (open_idx < start and end <= close_idx):
            continue
        segment = line_text[open_idx : close_idx + 1]
        if opener == "[":
            return True
        if (
            "$" in token_core
            or any(ch.isdigit() for ch in token_core)
            or token_has_initial_confusable_I(token_core)
        ):
            # Parenthetical short tokens with OCR-artifact cues are typically
            # bibliography sigla, even when they lack numeric coords.
            return True
        if CITATION_YEAR_RE.search(segment) or CITATION_SPLIT_YEAR_RE.search(segment):
            return True
        if re.search(r"\d{1,4}(?:[a-z]|[,:./]\d{1,4}[a-z]?)", segment, re.IGNORECASE):
            return True
        if CITATION_CUE_RE.search(segment):
            return True
    return False


def token_has_siglum_context(
    line_text: str,
    token: str,
    start: int,
    end: int,
    *,
    line_is_base_citation: bool,
    line_siglum_context_cue: bool,
    line_siglum_candidate_count: int,
) -> bool:
    token_core, _ = split_citation_siglum_token(token)
    token_core_folded = token_core.casefold()
    artifact_shape = (
        "$" in token_core
        or any(ch.isdigit() for ch in token_core)
        or token_has_initial_confusable_I(token_core)
    )
    if token_has_bracketed_siglum_context(line_text, token_core, start, end):
        return True
    if artifact_shape:
        lead = line_text[max(0, start - 3) : start]
        if "(" in lead or "[" in lead:
            return True
    if token_core_folded in CITATION_SIGLUM_STANDALONE_ALLOWLIST:
        lead = line_text[max(0, start - 3) : start]
        if "(" in lead or "[" in lead:
            tail = line_text[end:]
            if not tail or re.fullmatch(r"[\s\],.;:!?)]*", tail):
                return True
            if re.match(r"^\s*\f", tail):
                return True
    if line_siglum_candidate_count >= 2 and (line_is_base_citation or line_siglum_context_cue):
        return True
    if line_is_base_citation and token_occurrence_near_year(line_text, start, end):
        return True
    if line_is_base_citation and line_siglum_context_cue:
        return True
    if CITATION_SIGLUM_LEADING_LAYOUT_RE.match(line_text):
        lead = line_text.lstrip().split(" ", 1)[0]
        if token == lead and token_is_citation_siglum_candidate(lead):
            return True
    stripped = line_text.strip()
    if stripped == token:
        if token_core_folded in CITATION_SIGLUM_STANDALONE_ALLOWLIST:
            return True
    if not line_is_base_citation:
        if stripped == token:
            if (
                "$" in token_core
                or any(ch.isdigit() for ch in token_core)
                or token_has_initial_confusable_I(token_core)
            ):
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
    if low in TIBETAN_NAME_PIECE_HINTS:
        return True
    if low in ASCII_TIBETAN_NAME_PIECE_HINTS:
        return True
    if len(low) < 3:
        return False
    if token_has_distinctive_tibetan_signature(low):
        return True
    if TIBETAN_NAME_PIECE_PREFIX_RE.search(low):
        return True
    return False


def token_has_tibetan_name_piece_anchor(token: str) -> bool:
    parts = [part for part in token.split("-") if part]
    if len(parts) < 2:
        return False
    strong = 0
    for part in parts:
        if token_is_likely_tibetan_name_piece(part):
            strong += 1
    return strong >= 2


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
                    continue
                if "$" in tok:
                    canon_tok = dollar_to_sacute_preserve_case(tok)
                    if (
                        token_is_safe_dollar_to_sacute(tok, canon_tok)
                        and token_is_relaxed_dollar_translit_shape(canon_tok)
                        and not token_is_citation_siglum_candidate(tok)
                    ):
                        translit_tokens.append(tok)
                        continue
                if token_is_german_like(tok):
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


def page_lines_to_text(page_lines: list[list[str]]) -> str:
    return "\f".join("\n".join(lines) for lines in page_lines)


def normalize_form_feed_page_number_lines(text: str) -> str:
    """Drop page-number-only lines introduced immediately after form feeds."""
    if "\f" not in text:
        return text
    raw_pages = text.split("\f")
    if raw_pages and raw_pages[0] == "":
        raw_pages = raw_pages[1:]
    normalized_pages: list[str] = []
    for page in raw_pages:
        lines = page.splitlines()
        if lines and re.fullmatch(r"\d{1,4}", lines[0].strip()):
            lines = lines[1:]
        normalized_pages.append("\n".join(lines))
    return "\f".join(normalized_pages)


def normalize_google_vision_page_markers(text: str) -> str:
    """Convert Google Vision page marker lines into the form feeds used downstream."""
    if "\f" in text:
        return text
    pages: list[str] = []
    preamble: list[str] = []
    current: list[str] = []
    saw_marker = False
    for line in text.splitlines():
        if GOOGLE_VISION_PAGE_MARKER_RE.match(line):
            if saw_marker:
                pages.append("\n".join(current).strip("\n"))
            else:
                pre = "\n".join(preamble).strip("\n")
                if pre:
                    pages.append(pre)
            saw_marker = True
            current = []
        elif saw_marker:
            current.append(line)
        else:
            preamble.append(line)
    if not saw_marker:
        return text
    pages.append("\n".join(current).strip("\n"))
    return "\f".join(pages).strip("\n")


def line_has_unclosed_german_quote(line_text: str) -> bool:
    if "„" not in line_text:
        return False
    return "“" not in line_text.rsplit("„", 1)[-1]


def joined_wrap_candidate_is_safe(
    stem: str,
    continuation: str,
    corpus_counts: Counter[str],
) -> bool:
    candidate = (stem + continuation).strip()
    if len(candidate) < 4:
        return False
    if continuation.lower() in GERMAN_WRAP_NON_CONTINUATION_HEADS:
        return False
    # Structural quote-wrap repair already runs behind a narrow German-quote gate.
    # Here we only need to reject candidates that still carry obvious transliteration
    # markers, not plain ASCII German verbs like "vortragen".
    if re.search(r"[’'āīūṅñṭḍṇṣśṛḷṃṁ]", candidate.lower()):
        return False
    if token_is_german_like(candidate):
        return True
    lowered = candidate.lower()
    if corpus_counts.get(lowered, 0) >= 1:
        return True
    if len(continuation) > 4:
        return False
    return lowered.endswith(GERMAN_WRAP_COMMON_ENDINGS)


def line_is_structural_german_quote_context(info: LineInfo, line_text: str) -> bool:
    if info.has_tibetan:
        return False
    if info.zone not in {"german_prose", "german_prose_with_translit", "latin_other", "other"}:
        return False
    if not line_has_unclosed_german_quote(line_text):
        return False
    return GERMAN_QUOTE_WRAP_LINE_END_RE.search(line_text) is not None


def apply_structural_german_quote_wrap_repairs(
    page_lines: list[list[str]],
    line_infos: list[LineInfo],
) -> tuple[str, list[list[str]], int]:
    info_map = {(info.page, info.line): info for info in line_infos}
    corpus_counts: Counter[str] = Counter()
    for lines in page_lines:
        for line in lines:
            for m in OCR_LATIN_TOKEN_RE.finditer(line):
                corpus_counts[m.group(0).lower()] += 1

    structural_change_rows: list[list[str]] = []
    rewrite_count = 0
    updated_pages = [list(lines) for lines in page_lines]

    for page_idx, lines in enumerate(updated_pages, start=1):
        line_idx = 0
        while line_idx < len(lines):
            line = lines[line_idx]
            info = info_map.get((page_idx, line_idx + 1))
            if info is None or not line or not line_is_structural_german_quote_context(info, line):
                line_idx += 1
                continue

            base_match = GERMAN_QUOTE_WRAP_LINE_END_RE.search(line)
            if base_match is None:
                line_idx += 1
                continue
            prefix = base_match.group(1)
            stem = base_match.group(2)

            citation_author: str | None = None
            citation_coord: str | None = None
            citation_coord_line_idx: int | None = None
            continuation_line_idx: int | None = None
            continuation_line: str | None = None
            continuation_token: str | None = None
            continuation_rest: str = ""
            reason = "structural_german_quote_hyphen_wrap_direct"

            direct_idx = line_idx + 1
            if direct_idx < len(lines):
                direct_line = lines[direct_idx]
                if direct_line:
                    direct_match = GERMAN_QUOTE_WRAP_CONTINUATION_HEAD_RE.match(direct_line)
                    if direct_match is not None:
                        direct_head = direct_match.group(1)
                        if (
                            direct_head[:1].islower()
                            and joined_wrap_candidate_is_safe(stem, direct_head, corpus_counts)
                        ):
                            continuation_line_idx = direct_idx
                            continuation_line = direct_line
                            continuation_token = direct_head
                            continuation_rest = direct_match.group(2)

            if continuation_line_idx is None and direct_idx < len(lines):
                citation_match = GERMAN_QUOTE_WRAP_CITATION_HEAD_RE.match(lines[direct_idx] or "")
                if citation_match is not None:
                    citation_author = citation_match.group(1)
                    for lookahead_idx in range(direct_idx + 1, min(len(lines), line_idx + 9)):
                        candidate_line = lines[lookahead_idx]
                        if not candidate_line:
                            continue
                        if citation_coord is None:
                            coord_match = GERMAN_QUOTE_WRAP_COORD_PREFIX_RE.match(candidate_line)
                            if coord_match is not None:
                                citation_coord = coord_match.group(1).strip()
                                citation_coord_line_idx = lookahead_idx
                                candidate_line = coord_match.group(2)
                            else:
                                continue
                        continuation_match = GERMAN_QUOTE_WRAP_CONTINUATION_HEAD_RE.match(candidate_line)
                        if continuation_match is None:
                            continue
                        continuation_head = continuation_match.group(1)
                        if not continuation_head[:1].islower():
                            continue
                        if "“" not in candidate_line:
                            continue
                        if not joined_wrap_candidate_is_safe(stem, continuation_head, corpus_counts):
                            continue
                        continuation_line_idx = lookahead_idx
                        continuation_line = candidate_line
                        continuation_token = continuation_head
                        continuation_rest = continuation_match.group(2)
                        reason = "structural_german_quote_hyphen_wrap_citation"
                        break

            if continuation_line_idx is None or continuation_line is None or continuation_token is None:
                line_idx += 1
                continue

            joined_line = prefix + stem + continuation_token + continuation_rest
            if reason == "structural_german_quote_hyphen_wrap_citation":
                if citation_author is None or citation_coord is None or citation_coord_line_idx is None:
                    line_idx += 1
                    continue
                citation_coord_clean = citation_coord.strip()
                if citation_coord_clean.endswith(");"):
                    joined_line = f"{joined_line} ({citation_author} {citation_coord_clean}"
                else:
                    joined_line = f"{joined_line} ({citation_author} {citation_coord_clean})"
                coord_line = lines[citation_coord_line_idx]
                coord_match = GERMAN_QUOTE_WRAP_COORD_PREFIX_RE.match(coord_line)
                if coord_match is not None:
                    lines[citation_coord_line_idx] = coord_match.group(2).strip()
                if citation_author is not None:
                    for blank_idx in range(line_idx + 1, continuation_line_idx):
                        if lines[blank_idx] and GERMAN_QUOTE_WRAP_CITATION_HEAD_RE.match(lines[blank_idx]):
                            lines[blank_idx] = ""
                            break

            lines[line_idx] = joined_line
            lines[continuation_line_idx] = ""
            rewrite_count += 1
            structural_change_rows.append(
                [
                    str(page_idx),
                    str(line_idx + 1),
                    str(info.entry_id),
                    info.zone,
                    f"{stem}-/{continuation_token}",
                    stem + continuation_token,
                    "tier_a",
                    reason,
                    "1",
                    joined_line[:240],
                ]
            )
            line_idx = continuation_line_idx + 1
            continue
        line_idx += 1

    return page_lines_to_text(updated_pages), structural_change_rows, rewrite_count


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
    dollar_case_canon = dollar_to_sacute_preserve_case(token)
    dollar_canon = canonicalize_translit_token(dollar_case_canon).lower()
    confusable_dollar_to_sacute_safe = token_is_safe_dollar_to_sacute(token, dollar_case_canon)
    confusable_dollar_to_sacute_blocked = ("$" in token) and (not confusable_dollar_to_sacute_safe)
    dollar_relaxed_shape_ok = token_is_relaxed_dollar_translit_shape(dollar_case_canon)
    dollar_siglum_candidate = token_is_citation_siglum_candidate(token)
    dollar_backed = (
        dollar_canon in headword_mem or dollar_canon in entry_mem or dollar_canon in trusted_lexicon
    )
    dollar_name_anchor = token_has_tibetan_name_piece_anchor(dollar_case_canon)
    dollar_context_translit = (
        src_translit_like_here
        or info.has_tibetan
        or line_translit_dominant
        or src_has_hard_marker
        or src_has_cue
        or token_has_translit_cue(dollar_case_canon)
        or dollar_backed
        or dollar_name_anchor
    )
    dollar_zone_fallback = (
        info.zone == "german_prose"
        and info.entry_id != 0
        and not line_citation_like
        and not dollar_siglum_candidate
        and (dollar_backed or dollar_name_anchor)
    )
    dollar_auto_zone_ok = info.zone in AUTO_FIX_ZONES or dollar_zone_fallback
    exact_explicit_dst = EXPLICIT_CASE_SENSITIVE_TIER_A_REWRITES.get(token)
    explicit_dst = EXPLICIT_TIER_A_REWRITES.get(low)
    exact_tibetan_confusable_dst = TIBETAN_TRANSLIT_CONFUSABLE_EXACT_REWRITES.get(low)
    explicit_dst_has_tibetan_signature = (
        explicit_dst is not None
        and (
            token_has_distinctive_tibetan_signature(explicit_dst)
            or token_is_strict_clean_translit(canonicalize_translit_token(explicit_dst).lower())
        )
    )
    exact_explicit_dst_has_tibetan_signature = (
        exact_explicit_dst is not None and token_has_distinctive_tibetan_signature(exact_explicit_dst)
    )
    explicit_translit_zone_fallback = (
        info.zone in {"german_prose", "other"}
        and info.entry_id != 0
        and not line_citation_like
        and (
            src_translit_like_here
            or info.has_tibetan
            or line_translit_dominant
            or src_has_hard_marker
            or src_has_cue
            or canon in headword_mem
            or canon in entry_mem
            or explicit_dst_has_tibetan_signature
            or exact_explicit_dst_has_tibetan_signature
        )
    )
    explicit_auto_zone_ok = info.zone in AUTO_FIX_ZONES or explicit_translit_zone_fallback
    if exact_explicit_dst is not None and explicit_auto_zone_ok:
        return exact_explicit_dst, "A", "explicit_case_sensitive_allowlist"
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
    if explicit_dst is not None and (explicit_auto_zone_ok or "$" in low):
        return explicit_dst, "A", "explicit_user_allowlist"

    if exact_tibetan_confusable_dst is not None:
        exact_tibetan_shape_ok = (
            token_is_safe_coda_nya_to_nga(low, exact_tibetan_confusable_dst)
            or token_is_safe_dollar_to_sacute(low, exact_tibetan_confusable_dst)
        )
        exact_tibetan_zone_ok = (
            info.zone in ENTRY_STRONG_ZONES
            or (info.zone == "german_prose_with_translit" and info.has_tibetan)
        )
        exact_tibetan_anchor_ok = (
            info.has_tibetan
            or (
                line_translit_dominant
                and (src_has_hard_marker or src_has_cue or src_has_issue)
            )
        )
        if (
            exact_tibetan_shape_ok
            and token == low
            and exact_tibetan_zone_ok
            and exact_tibetan_anchor_ok
            and not src_umlaut_untrusted
            and not line_citation_like
            and not line_has_sanskrit_or_indic_cue(info.line_text)
            and not (("$" in low) and dollar_siglum_candidate)
        ):
            options.append(
                (
                    267,
                    exact_tibetan_confusable_dst,
                    "A",
                    "tibetan_translit_confusable_exact",
                )
            )

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
        and dollar_auto_zone_ok
        and not dollar_siglum_candidate
        and dollar_relaxed_shape_ok
        and dollar_context_translit
        and not (
            src_german_like
            and not (src_has_hard_marker or src_has_cue or token_has_translit_cue(dollar_case_canon))
        )
    ):
        if dollar_canon in headword_mem:
            options.append((258, dollar_case_canon, "A", "confusable_dollar_to_sacute_headword"))
        elif dollar_canon in entry_mem:
            options.append((248, dollar_case_canon, "A", "confusable_dollar_to_sacute_entry_memory"))
        elif dollar_canon in trusted_lexicon:
            options.append((242, dollar_case_canon, "A", "confusable_dollar_to_sacute_lexicon"))
        elif dollar_name_anchor:
            options.append((239, dollar_case_canon, "A", "confusable_dollar_to_sacute_name_anchor"))
        elif token_is_titlecase_or_lower_compound_shape(dollar_case_canon):
            options.append((237, dollar_case_canon, "A", "confusable_dollar_to_sacute_shape_safe"))
        elif token == token.lower():
            options.append((236, dollar_case_canon, "A", "confusable_dollar_to_sacute_context_safe"))

    if (
        canon != low
        and confusable_dollar_to_sacute_safe
        and low in DOLLAR_SACUTE_TIER_A_ALLOWLIST
        and dollar_relaxed_shape_ok
    ):
        options.append((238, dollar_case_canon, "A", "confusable_dollar_to_sacute_allowlist"))

    if (
        canon != low
        and confusable_dollar_to_sacute_safe
        and not dollar_siglum_candidate
        and dollar_auto_zone_ok
        and dollar_relaxed_shape_ok
        and token == token.lower()
        and dollar_context_translit
        and not (
            src_german_like
            and not (src_has_hard_marker or src_has_cue or token_has_translit_cue(dollar_case_canon))
        )
    ):
        options.append((237, dollar_case_canon, "A", "confusable_dollar_to_sacute_lowercase_safe"))

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


def choose_orphan_dollar_sacute_rewrite(
    token: str,
    *,
    line_has_tibetan: bool,
    line_has_citation_siglum: bool,
) -> tuple[str, str] | None:
    if "$" not in token:
        return None
    if token_is_citation_siglum_candidate(token):
        return None
    dst = dollar_to_sacute_preserve_case(token)
    if dst == token:
        return None
    if not token_is_safe_dollar_to_sacute(token, dst):
        return None
    if not token_is_relaxed_dollar_translit_shape(dst):
        return None
    # Keep citation-like all-caps sigla untouched when the line already
    # contains explicit siglum cues.
    if line_has_citation_siglum and token_upper_ratio(token) >= 0.45:
        return None
    # Require transliteration evidence to avoid touching plain German text.
    has_translit_evidence = (
        line_has_tibetan
        or token_has_hard_translit_marker(dst)
        or token_has_translit_cue(dst)
        or token_has_distinctive_tibetan_signature(dst)
    )
    if not has_translit_evidence:
        return None
    if token_is_german_like(token) and not (
        line_has_tibetan
        or token_has_hard_translit_marker(dst)
        or token_has_translit_cue(dst)
    ):
        return None
    return dst, "orphan_safe_dollar_to_sacute"


def line_is_german_prose_rewrite_context(
    info: "LineInfo",
    line_text: str,
    *,
    line_citation_like: bool,
) -> bool:
    if info.has_tibetan:
        return False
    if info.zone not in {"german_prose", "german_prose_with_translit", "latin_other", "other"}:
        return False
    if line_has_citation_siglum_candidate(line_text):
        return False
    if line_citation_like:
        stripped_line = re.sub(r"\([^)]*\)", " ", line_text)
        stripped_tokens = [m.group(0) for m in OCR_LATIN_TOKEN_RE.finditer(stripped_line)]
        stripped_has_safe_prose_token = any(
            tok in GERMAN_PROSE_TOKEN_EXACT_SAFE_REWRITES
            or tok.lower() in GERMAN_PROSE_SAFE_REWRITES
            or tok in GERMAN_NUMERIC_FUNCTION_WORD_REWRITES
            for tok in stripped_tokens
        ) or line_has_german_numeric_function_word(stripped_line)
        if (
            CITATION_BIBLIO_AUTHOR_YEAR_RE.match(line_text)
            or (
                CITATION_BIBLIO_CONTINUATION_HEAD_RE.match(line_text)
                and CITATION_BIBLIO_CONTINUATION_CUE_RE.search(line_text)
            )
            or CITATION_BIBLIO_INLINE_CUE_RE.search(line_text)
            or CITATION_YEAR_RE.search(line_text)
            or CITATION_SPLIT_YEAR_RE.search(line_text)
            or (
                line_has_siglum_context_cue(line_text)
                and not (stripped_has_safe_prose_token and len(stripped_tokens) >= 2)
            )
        ):
            return False
    german_count = len(info.german_tokens)
    translit_count = len(info.translit_tokens)
    if german_count >= 2 and german_count >= translit_count:
        return True
    if info.zone == "german_prose" and german_count >= 1 and translit_count == 0:
        return True
    if info.zone != "other" or translit_count != 0:
        return False

    latin_tokens = [m.group(0) for m in OCR_LATIN_TOKEN_RE.finditer(line_text)]
    if len(latin_tokens) < 2:
        return False
    if not any(
        tok in GERMAN_PROSE_TOKEN_EXACT_SAFE_REWRITES
        or tok.lower() in GERMAN_PROSE_SAFE_REWRITES
        or tok in GERMAN_NUMERIC_FUNCTION_WORD_REWRITES
        for tok in latin_tokens
    ) and not line_has_german_numeric_function_word(line_text):
        return False
    return True


def line_is_tibetan_translit_phrase_rewrite_context(info: "LineInfo", line_text: str) -> bool:
    if not line_text or info.entry_id == 0:
        return False
    if info.zone in AUTO_FIX_ZONES:
        return True
    if info.has_tibetan:
        return True
    return len(info.translit_tokens) >= max(2, len(info.german_tokens))


def line_is_tibetan_direct_phrase_rewrite_context(info: "LineInfo", line_text: str) -> bool:
    if not line_text or info.entry_id == 0:
        return False
    if info.zone in AUTO_FIX_ZONES:
        return True
    if info.has_tibetan:
        return True
    return bool(info.translit_tokens)


def apply_safe_tibetan_translit_phrase_rewrites(
    line: str,
    info: "LineInfo",
    *,
    page: int,
    line_no: int,
    change_rows: list[list[str]],
) -> str:
    if not line:
        return line

    original_excerpt = line[:240]
    updated = line
    if line_is_tibetan_direct_phrase_rewrite_context(info, line):
        for pattern, replacement, reason in TIBETAN_TRANSLIT_DIRECT_PHRASE_SAFE_REWRITE_PATTERNS:

            def repl_direct(match: re.Match[str]) -> str:
                src = match.group(0)
                change_rows.append(
                    [
                        str(page),
                        str(line_no),
                        str(info.entry_id),
                        info.zone,
                        src,
                        replacement,
                        "A",
                        reason,
                        "1",
                        original_excerpt,
                    ]
                )
                return replacement

            updated = pattern.sub(repl_direct, updated)

    if not line_is_tibetan_translit_phrase_rewrite_context(info, line):
        return updated

    for pattern, left_dst, right_dst, reason in TIBETAN_TRANSLIT_PHRASE_SAFE_REWRITE_PATTERNS:

        def repl(match: re.Match[str]) -> str:
            src = match.group(0)
            dst = f"{left_dst}{match.group('space')}{right_dst}"
            change_rows.append(
                [
                    str(page),
                    str(line_no),
                    str(info.entry_id),
                    info.zone,
                    src,
                    dst,
                    "A",
                    reason,
                    "1",
                    original_excerpt,
                ]
            )
            return dst

        updated = pattern.sub(repl, updated)

    for from_phrase, to_phrase in TIBETAN_DANG_PHRASE_OVERRIDES:
        occurrences = updated.count(from_phrase)
        if not occurrences:
            continue
        updated = updated.replace(from_phrase, to_phrase)
        for _ in range(occurrences):
            change_rows.append(
                [
                    str(page),
                    str(line_no),
                    str(info.entry_id),
                    info.zone,
                    from_phrase,
                    to_phrase,
                    "A",
                    "tibetan_dang_phrase_override",
                    "1",
                    original_excerpt,
                ]
            )

    if line_has_tibetan_dang_witness(updated):

        def dang_repl(match: re.Match[str]) -> str:
            src = match.group(0)
            dst = "daṅ"
            change_rows.append(
                [
                    str(page),
                    str(line_no),
                    str(info.entry_id),
                    info.zone,
                    src,
                    dst,
                    "A",
                    "tibetan_dang_witness_rewrite",
                    "1",
                    original_excerpt,
                ]
            )
            return dst

        updated = TIBETAN_DAN_TOKEN_RE.sub(dang_repl, updated)
    return updated


def apply_safe_prose_and_biblio_rewrites(
    line: str,
    info: "LineInfo",
    *,
    page: int,
    line_no: int,
    change_rows: list[list[str]],
) -> str:
    if not line:
        return line
    line_citation_like = line_is_citation_like(info, line)
    german_prose_context = line_is_german_prose_rewrite_context(
        info, line, line_citation_like=line_citation_like
    )
    if not line_citation_like and not german_prose_context:
        return line

    original_excerpt = line[:240]
    updated = line

    if line_citation_like:
        for pattern, dst, reason in CITATION_PHRASE_SAFE_REWRITE_PATTERNS:
            def repl_phrase(m: re.Match[str]) -> str:
                src = m.group(0)
                if src == dst:
                    return src
                change_rows.append(
                    [
                        str(page),
                        str(line_no),
                        str(info.entry_id),
                        info.zone,
                        src,
                        dst,
                        "A",
                        reason,
                        "1",
                        original_excerpt,
                    ]
                )
                return dst

            updated = pattern.sub(repl_phrase, updated)

    def repl_token(m: re.Match[str]) -> str:
        tok = m.group(0)
        low = tok.lower()
        dst: str | None = None
        reason: str | None = None

        if line_citation_like:
            citation_safe_tok = citation_safe_confusable_rewrite(tok)
            citation_safe_low = citation_safe_tok.casefold()
            exact_mapped = CITATION_TOKEN_EXACT_SAFE_REWRITES.get(tok)
            if exact_mapped is None and citation_safe_tok != tok:
                exact_mapped = CITATION_TOKEN_EXACT_SAFE_REWRITES.get(citation_safe_tok)
            if exact_mapped is not None:
                dst = exact_mapped
                reason = "citation_token_exact_safe_map"
            else:
                mapped = ENGLISH_BIBLIO_SPACELOSS_REWRITES.get(citation_safe_low)
                if mapped is not None:
                    dst = apply_case_pattern(tok, mapped)
                    reason = "citation_english_spacing_loss_map"
                else:
                    mapped = CITATION_NAME_SAFE_REWRITES.get(citation_safe_low)
                    if mapped is not None:
                        dst = apply_case_pattern(tok, mapped)
                        reason = "citation_name_safe_map"
        if dst is None and german_prose_context:
            exact_mapped = GERMAN_PROSE_TOKEN_EXACT_SAFE_REWRITES.get(tok)
            if exact_mapped is not None:
                dst = exact_mapped
                reason = "german_dotless_i_safe_map"
            else:
                mapped = GERMAN_PROSE_SAFE_REWRITES.get(low)
                if mapped is not None:
                    dst = apply_case_pattern(tok, mapped)
                    reason = "german_dotless_i_safe_map"

        if dst is None or reason is None or dst == tok:
            return tok
        change_rows.append(
            [
                str(page),
                str(line_no),
                str(info.entry_id),
                info.zone,
                tok,
                dst,
                "A",
                reason,
                "1",
                original_excerpt,
            ]
        )
        return dst

    updated = OCR_LATIN_TOKEN_RE.sub(repl_token, updated)

    if not german_prose_context:
        return updated

    def repl_numeric(m: re.Match[str]) -> str:
        tok = m.group("token")
        dst = GERMAN_NUMERIC_FUNCTION_WORD_REWRITES.get(tok)
        if dst is None:
            return tok
        start, end = m.start("token"), m.end("token")
        left = updated[:start]
        right = updated[end:]
        prev_non_space = left.rstrip()[-1:] if left else ""
        next_non_space = right.lstrip()[:1] if right else ""
        if prev_non_space in {"§", "#"} or prev_non_space.isdigit():
            return tok
        if next_non_space.isdigit():
            return tok
        prev_word = re.search(rf"[{LATIN_CHARS}]{{2,}}\W*$", left)
        next_word = re.match(rf"^\W*[{LATIN_CHARS}]{{2,}}", right)
        if prev_word is None and next_word is None:
            return tok
        change_rows.append(
            [
                str(page),
                str(line_no),
                str(info.entry_id),
                info.zone,
                tok,
                dst,
                "A",
                "german_numeric_function_word_confusion",
                "1",
                original_excerpt,
            ]
        )
        return dst

    return GERMAN_NUMERIC_FUNCTION_WORD_TOKEN_RE.sub(repl_numeric, updated)


def span_overlaps_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def google_vision_protected_spans(line: str) -> list[tuple[int, int]]:
    return [m.span() for m in GOOGLE_VISION_PROTECTED_SPAN_RE.finditer(line)]


def google_vision_nasal_is_palatal(tok: str, index: int) -> bool:
    """Google Vision often prints old-LoC ñ/ṅ as ň/ń/ǹ; choose ñ only in tight palatal clusters."""

    lower = tok.lower()
    before = lower[:index]
    after = lower[index + 1 :]
    return (
        (before.endswith("m") and after.startswith("am"))
        or (before.endswith("s") and (after.startswith("am") or after.startswith("i")))
        or (before.endswith("g") and (after.startswith("is") or after.startswith("en") or after.startswith("er")))
        or (before.endswith("br") and after.startswith("an"))
        or (before.endswith("bs") and after.startswith("en"))
    )


def rewrite_google_vision_loc_confusables(tok: str) -> str:
    chars: list[str] = []
    for index, ch in enumerate(tok):
        if ch in GOOGLE_VISION_NASAL_CONFUSABLES:
            chars.append("ñ" if google_vision_nasal_is_palatal(tok, index) else "ṅ")
        elif ch in GOOGLE_VISION_NASAL_CONFUSABLES_UPPER:
            chars.append("Ñ" if google_vision_nasal_is_palatal(tok, index) else "Ṅ")
        else:
            chars.append(ch.translate(GOOGLE_VISION_NON_NASAL_CONFUSABLE_MAP))
    rewritten = "".join(chars)
    fixed = GOOGLE_VISION_LOC_POST_TOKEN_FIXES.get(rewritten)
    if fixed is not None:
        return fixed
    lower_fixed = GOOGLE_VISION_LOC_POST_TOKEN_FIXES.get(rewritten.lower())
    if lower_fixed is not None and rewritten[:1].isupper():
        return lower_fixed[:1].upper() + lower_fixed[1:]
    return rewritten


def rewrite_google_vision_loc_token(tok: str) -> str | None:
    if not GOOGLE_VISION_LOC_CONFUSABLE_RE.search(tok):
        return None
    dst = rewrite_google_vision_loc_confusables(tok)
    if dst == tok:
        return None
    if not (
        token_has_hard_translit_marker(dst)
        or token_has_translit_cue(dst)
        or DISTINCTIVE_TIB_CLUSTER_RE.search(dst)
        or BOUNDARY_TRANSLIT_CLUSTER_RE.search(dst)
    ):
        return None
    return dst


def line_is_google_vision_loc_rewrite_context(info: LineInfo | None, line: str) -> bool:
    if not line or not GOOGLE_VISION_LOC_CONFUSABLE_RE.search(line):
        return False
    if info is not None and line_is_tibetan_translit_phrase_rewrite_context(info, line):
        return True
    protected = google_vision_protected_spans(line)
    for m in OCR_LATIN_TOKEN_RE.finditer(line):
        if span_overlaps_any(m.start(), m.end(), protected):
            continue
        if rewrite_google_vision_loc_token(m.group(0)) is not None:
            return True
    return False


def google_vision_loc_change_row_context(info: LineInfo | None, line: str) -> tuple[str, str]:
    if info is None:
        return "0", "google_vision_preclean"
    if not line_is_tibetan_translit_phrase_rewrite_context(info, line):
        return str(info.entry_id), "google_vision_preclean"
    return str(info.entry_id), info.zone


def apply_google_vision_loc_preclean(
    page_lines: list[list[str]],
    line_infos: list[LineInfo],
) -> tuple[str, list[list[str]], int]:
    info_by_key = {(li.page, li.line): li for li in line_infos}
    change_rows: list[list[str]] = []
    cleaned_pages: list[list[str]] = []
    for page_idx, lines in enumerate(page_lines, start=1):
        corrected_lines: list[str] = []
        for line_idx, line in enumerate(lines, start=1):
            info = info_by_key.get((page_idx, line_idx))
            if not line_is_google_vision_loc_rewrite_context(info, line):
                corrected_lines.append(line)
                continue
            protected = google_vision_protected_spans(line)
            original_excerpt = line[:240]
            entry_id, zone = google_vision_loc_change_row_context(info, line)

            def repl_token(m: re.Match[str]) -> str:
                if span_overlaps_any(m.start(), m.end(), protected):
                    return m.group(0)
                tok = m.group(0)
                dst = rewrite_google_vision_loc_token(tok)
                if dst is None or dst == tok:
                    return tok
                change_rows.append(
                    [
                        str(page_idx),
                        str(line_idx),
                        entry_id,
                        zone,
                        tok,
                        dst,
                        "A",
                        "google_vision_loc_confusable",
                        "1",
                        original_excerpt,
                    ]
                )
                return dst

            corrected_lines.append(OCR_LATIN_TOKEN_RE.sub(repl_token, line))
        cleaned_pages.append(corrected_lines)
    return page_lines_to_text(cleaned_pages), change_rows, len(change_rows)


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
            if not line:
                corrected_lines.append(line)
                continue
            info = info_by_key.get((page_idx, line_idx))
            if info is not None:
                line = apply_safe_prose_and_biblio_rewrites(
                    line,
                    info,
                    page=page_idx,
                    line_no=line_idx,
                    change_rows=change_rows,
                )
                line = apply_safe_tibetan_translit_phrase_rewrites(
                    line,
                    info,
                    page=page_idx,
                    line_no=line_idx,
                    change_rows=change_rows,
                )
            if info is None or info.entry_id == 0:
                line_has_tibetan = bool(TIB_RE.search(line))
                line_has_siglum = line_has_citation_siglum_candidate(line)

                def repl_orphan(m: re.Match[str]) -> str:
                    tok = m.group(0)
                    choice = choose_orphan_dollar_sacute_rewrite(
                        tok,
                        line_has_tibetan=line_has_tibetan,
                        line_has_citation_siglum=line_has_siglum,
                    )
                    if choice is None:
                        return tok
                    dst, reason = choice
                    guard_block_reason = rewrite_hard_guard_block_reason(
                        tok, dst, reason, stage="entry"
                    )
                    zone = info.zone if info is not None else "other"
                    entry_id = info.entry_id if info is not None else 0
                    line_excerpt = info.line_text[:240] if info is not None else line[:240]
                    if guard_block_reason is not None:
                        review_rows.append(
                            [
                                str(page_idx),
                                str(line_idx),
                                str(entry_id),
                                zone,
                                tok,
                                dst,
                                "B",
                                f"hard_guard_{guard_block_reason}__{reason}",
                                "0",
                                line_excerpt,
                            ]
                        )
                        return tok
                    change_rows.append(
                        [
                            str(page_idx),
                            str(line_idx),
                            str(entry_id),
                            zone,
                            tok,
                            dst,
                            "A",
                            reason,
                            "1",
                            line_excerpt,
                        ]
                    )
                    return dst

                corrected_lines.append(OCR_LATIN_TOKEN_RE.sub(repl_orphan, line))
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
                and (
                    line_is_citation_like(info, line)
                    or line_is_standalone_allowlisted_siglum(line)
                )
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

            def repl_dotted_abbrev(m: re.Match[str]) -> str:
                tok = m.group(0)
                dst = "i.S.v." if m.group("trail") else "i.S."
                guard_block_reason = rewrite_hard_guard_block_reason(
                    tok, dst, "citation_isv_dollar_abbrev_map", stage="citation"
                )
                if guard_block_reason is not None:
                    review_rows.append(
                        [
                            str(info.page),
                            str(info.line),
                            str(info.entry_id),
                            info.zone,
                            tok,
                            dst,
                            "B",
                            f"hard_guard_{guard_block_reason}__citation_isv_dollar_abbrev_map",
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
                        dst,
                        "A",
                        "citation_isv_dollar_abbrev_map",
                        "1",
                        line[:240],
                    ]
                )
                return dst

            line = CITATION_DOTTED_DOLLAR_ABBREV_RE.sub(repl_dotted_abbrev, line)
            lines[line_idx - 1] = line

            # Apply rewrites on the expanded citation mask as well so wrapped
            # bibliography lines within the same entry get normalized.
            if not citation_like_masks[page_idx][line_idx - 1]:
                continue
            line_is_base_citation = citation_like_base_masks[page_idx][line_idx - 1]
            line_siglum_context_cue = line_has_siglum_context_cue(line)
            line_siglum_candidate_count = line_citation_siglum_candidate_count(line)

            def repl(m: re.Match[str]) -> str:
                tok = m.group(0)
                tok_start = m.start()
                tok_end = m.end()

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
                    if token_has_siglum_context(
                        line,
                        tok,
                        tok_start,
                        tok_end,
                        line_is_base_citation=line_is_base_citation,
                        line_siglum_context_cue=line_siglum_context_cue,
                        line_siglum_candidate_count=line_siglum_candidate_count,
                    ):
                        return apply_guarded(safe_tok, "citation_siglum_confusable_map")
                    return tok
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
                if not token_has_siglum_context(
                    line,
                    tok,
                    m.start(2),
                    m.end(2),
                    line_is_base_citation=line_is_base_citation,
                    line_siglum_context_cue=line_siglum_context_cue,
                    line_siglum_candidate_count=line_siglum_candidate_count,
                ):
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

            def repl_alnum_siglum(m: re.Match[str]) -> str:
                tok = m.group(0)
                safe_tok = citation_safe_confusable_rewrite(tok)
                if not token_is_citation_siglum_candidate(tok) or safe_tok == tok:
                    return tok
                if not token_has_siglum_context(
                    line,
                    tok,
                    m.start(),
                    m.end(),
                    line_is_base_citation=line_is_base_citation,
                    line_siglum_context_cue=line_siglum_context_cue,
                    line_siglum_candidate_count=line_siglum_candidate_count,
                ):
                    return tok
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
                    return tok
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
                return safe_tok

            def repl_g_dot_yu(m: re.Match[str]) -> str:
                prefix = m.group(1)
                tok = "g.Yu"
                safe_tok = "gYu"
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

            line = CITATION_G_DOT_YU_COORD_RE.sub(repl_g_dot_yu, line)
            line = CITATION_SIGLUM_DIGIT_ARTIFACT_RE.sub(repl_digit_siglum, line)
            line = CITATION_SIGLUM_ALNUM_TOKEN_RE.sub(repl_alnum_siglum, line)
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
    google_vision: bool = False,
    alternate_merged: Path | None = None,
    alternate_google_vision: bool = False,
    merge_only: bool = False,
) -> dict[str, object]:
    audit_by_line = load_audit(audit)
    witness = prepare_witness(
        merged.read_text(encoding="utf-8", errors="replace"),
        audit_by_line=audit_by_line,
        google_vision=google_vision,
    )
    text = witness["text"]
    entries = witness["entries"]
    line_infos = witness["line_infos"]
    line_rows = witness["line_rows"]
    validator_rows = witness["validator_rows"]
    summary = witness["summary"]
    page_lines = witness["page_lines"]
    structural_change_rows = witness["structural_change_rows"]
    structural_rewrite_count = witness["structural_rewrite_count"]
    google_vision_change_rows = witness["google_vision_change_rows"]
    google_vision_rewrite_count = witness["google_vision_rewrite_count"]
    alternate_adoption_rows: list[list[str]] = []
    alternate_unresolved_rows: list[list[str]] = []
    alternate_adoption_count = 0
    if alternate_merged is not None:
        alternate_witness = prepare_witness(
            alternate_merged.read_text(encoding="utf-8", errors="replace"),
            audit_by_line=audit_by_line,
            google_vision=alternate_google_vision,
        )
        (
            text,
            alternate_adoption_rows,
            alternate_unresolved_rows,
            alternate_adoption_count,
        ) = arbitrate_alternate_witness(
            base_page_lines=page_lines,
            base_line_infos=line_infos,
            alternate_page_lines=alternate_witness["page_lines"],
            alternate_line_infos=alternate_witness["line_infos"],
            alternate_google_vision=alternate_google_vision,
        )
        entries, line_infos, line_rows, validator_rows, summary, page_lines = parse_entries(text, audit_by_line)
    if merge_only:
        trusted_lexicon: set[str] = set()
        discovered_rows: list[list[str]] = []
        corrected_text = text
        change_rows = structural_change_rows + google_vision_change_rows
        review_rows: list[list[str]] = []
        citation_change_rows = []
        citation_review_rows = []
        citation_report_rows = []
        citation_family_count = 0
        sanskrit_change_rows = []
        sanskrit_review_rows = []
        sanskrit_report_rows = []
        sanskrit_family_count = 0
        stale_review_rows_removed = 0
    else:
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
        change_rows = structural_change_rows + google_vision_change_rows + change_rows
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
    alternate_adoptions_tsv = outdir / f"{label}_alternate_witness_adoptions.tsv"
    alternate_unresolved_tsv = outdir / f"{label}_alternate_witness_unresolved.tsv"

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
    write_tsv(
        alternate_adoptions_tsv,
        [
            "page",
            "line",
            "token_index",
            "base_token",
            "alternate_token",
            "reason",
            "base_key",
            "alternate_key",
            "base_line",
            "alternate_line",
            "alignment_method",
            "alternate_page",
            "page_match_score",
            "canonical_overlap",
            "shared_canonical_tokens",
            "base_nonempty_count",
            "alternate_nonempty_count",
            "line_count_ratio",
        ],
        alternate_adoption_rows,
    )
    write_tsv(
        alternate_unresolved_tsv,
        [
            "page",
            "line",
            "token_index",
            "base_token",
            "alternate_token",
            "reason",
            "base_key",
            "alternate_key",
            "base_line",
            "alternate_line",
        ],
        alternate_unresolved_rows,
    )

    change_reason_counts = Counter(row[7] for row in change_rows)
    review_reason_counts = Counter(row[7] for row in review_rows)
    validator_issue_counts = Counter(row[5] for row in validator_rows)
    discovered_confidence_counts = Counter(row[5] for row in discovered_rows)
    summary = {
        **summary,
        "structural_rewrite_count": structural_rewrite_count,
        "google_vision_mode": google_vision,
        "google_vision_rewrites": google_vision_rewrite_count,
        "alternate_witness_used": alternate_merged is not None,
        "alternate_witness_path": str(alternate_merged) if alternate_merged is not None else "",
        "alternate_google_vision_mode": alternate_google_vision if alternate_merged is not None else False,
        "merge_only": merge_only,
        "alternate_witness_adoptions": alternate_adoption_count,
        "alternate_witness_unresolved": len(alternate_unresolved_rows),
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
        "alternate_witness_adoptions_tsv": str(alternate_adoptions_tsv),
        "alternate_witness_unresolved_tsv": str(alternate_unresolved_tsv),
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
    ap.add_argument(
        "--google-vision",
        action="store_true",
        help="Preclean Google Vision page markers and LoC diacritic confusions before normal postprocess.",
    )
    ap.add_argument(
        "--alternate-merged",
        default="",
        help="Optional second OCR witness to preclean and arbitrate against the base witness.",
    )
    ap.add_argument(
        "--alternate-google-vision",
        action="store_true",
        help="Treat the alternate witness as Google Vision OCR and run Google-specific LoC preclean on it.",
    )
    ap.add_argument(
        "--merge-only",
        action="store_true",
        help="Stop after witness preparation/arbitration and write the merged witness without downstream cleanup passes.",
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
        google_vision=args.google_vision,
        alternate_merged=Path(args.alternate_merged) if args.alternate_merged else None,
        alternate_google_vision=args.alternate_google_vision,
        merge_only=args.merge_only,
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
    print(f"google_vision_mode={result['google_vision_mode']}")
    print(f"google_vision_rewrites={result['google_vision_rewrites']}")
    print(f"alternate_witness_used={result['alternate_witness_used']}")
    if result["alternate_witness_used"]:
        print(f"alternate_witness_path={result['alternate_witness_path']}")
        print(f"alternate_google_vision_mode={result['alternate_google_vision_mode']}")
    print(f"merge_only={result['merge_only']}")
    print(f"alternate_witness_adoptions={result['alternate_witness_adoptions']}")
    print(f"alternate_witness_unresolved={result['alternate_witness_unresolved']}")
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
    print(f"watchdog_tsv={result['watchdog_tsv']}")
    print(f"alternate_witness_adoptions_tsv={result['alternate_witness_adoptions_tsv']}")
    print(f"alternate_witness_unresolved_tsv={result['alternate_witness_unresolved_tsv']}")
    print(f"summary_json={result['summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
