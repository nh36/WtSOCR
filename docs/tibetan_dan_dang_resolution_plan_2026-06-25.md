# Tibetan `dan` -> `daṅ` Resolution Plan

Date: 2026-06-25

## Immediate `dnos` status

The three requested WtS 9-m `dnos` rows are already present in
`data/reviewed_tibetan_exact_overrides.tsv` as exact reviewed
`dnos` -> `dṅos` overrides:

| volume | page | line | token | from | to |
|---|---:|---:|---:|---|---|
| wts_9_m | 143 | 10 | 5 | dnos | dṅos |
| wts_9_m | 190 | 77 | 2 | dnos | dṅos |
| wts_9_m | 381 | 57 | 8 | dnos | dṅos |

These remain row-level reviewed repairs. They are not represented as a
broad `n`/`ñ`/`ṅ` repair.

## Current `dan` evidence

The current code already has several conservative `dan` -> `daṅ`
mechanisms:

- exact reviewed row overrides in `data/reviewed_tibetan_exact_overrides.tsv`;
- curated phrase replacements in `data/tibetan_dang_phrase_overrides.tsv`;
- an allowlisted phrase-family gate for recurring Tibetan contexts such as
  `dan ldan pa`;
- a Tibetan-script witness gate when the alternate line visibly supports
  `དང་`.

The four-volume residual ledger shows that `dan` is not one uniform case:

| signal | count | current interpretation |
|---|---:|---|
| `tibetan_orthography` candidate `dan` -> `daṅ` in WtS 9-m | 140 | plausible residual queue; needs family/context triage |
| existing alternate-witness adoptions `dan` -> `daṅ` | 492 | already accepted by existing gates; should be spot-audited |
| existing alternate-witness adoptions `dañ` -> `daṅ` | 25 | separate local nasal-damage family |
| existing alternate-witness adoptions `dan` -> `dañ` | 8 | must be reviewed before trusting as a pattern |
| exact `dan` -> `daṅ` promotion rows in the current promotion-candidate TSV | 0 | no ready-made exact promotion batch yet |

Standalone `dan` remains high-volume in the latest WtS 8-b/WtS 9-m
corrected outputs: roughly 1,992 instances in WtS 8-b and 1,086 in WtS
9-m. These include genuine Tibetan conjunctions, bibliographic and German
contexts, meter/citation fragments, and OCR noise. That is why this family
needs a dedicated triage report rather than a direct global substitution.

## Plan To Resolve The Family

1. Build a dedicated `dan`/`daṅ` triage output from fresh four-volume
   corrected text and alternate-witness TSVs, for example
   `tibetan_dan_dang_triage.tsv`.

   Required fields:

   - volume, page, line, token_index;
   - current token and full corrected line;
   - alternate witness token/line if present;
   - whether Google is an adopted witness, unresolved witness, or only a
     candidate;
   - current mechanism: exact override, phrase override, phrase allowlist,
     Tibetan-script witness rewrite, or none;
   - context class: Tibetan phrase, Tibetan-script supported, German/prose,
     citation/siglum, meter example, uncertain;
   - suggested action: already_safe, promote_exact_row, promote_phrase_family,
     sample_further, defer, reject.

2. Start with the 140 WtS 9-m `dan` -> `daṅ` residual pattern rows.
   Review all distinct context templates and at least the first 30 concrete
   examples before promotion. If a template is homogeneous, promote it as a
   curated phrase family; if not, use exact page-line-token rows only.

3. Spot-audit the 492 already accepted `dan` -> `daṅ` adoptions. The aim is
   to validate the existing gates, not to loosen them. Sample across volumes,
   page ranges, and attribution types.

4. Promote only exact reviewed repairs or explicitly allowlisted phrase
   families. Do not add:

   - a global `dan` -> `daṅ` rule;
   - a broad final nasal repair;
   - a general rule based only on Google preference.

5. Regression coverage for each promoted family should include:

   - a positive Tibetan-context example;
   - a German/prose negative;
   - an apostrophe-sensitive negative such as `'dan`;
   - a citation/siglum or ambiguous-context negative where relevant.

## Success Criteria

- Every remaining standalone `dan` in the fresh four-volume output is either
  classified or deliberately deferred.
- The 140-row residual WtS 9-m pattern queue is reduced to promoted exact
  rows/families plus explicit deferrals.
- Existing `dan` -> `daṅ` Google adoptions pass a spot audit.
- Corrected-text diffs are explainable by named reviewed families.
- No Google Vision gate is loosened, and no broad character rule is added.
