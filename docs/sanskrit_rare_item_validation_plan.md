# Sanskrit Rare-Item Validation Plan

## Goal
Promote low-frequency Sanskrit OCR corrections from review-only to safe auto-apply with quantified precision, while avoiding false positives in German prose and Tibetan transliteration.

## Scope
- Inputs:
  - `*_review_queue.tsv` rows with `reason` in `sanskrit_char_normalize` or `sanskrit_family_canonicalize`
  - `*_sanskrit_report.tsv` family confidence and variant counts
  - `*_changes.tsv` already auto-applied Sanskrit fixes
- Output:
  - Audited allowlist updates
  - Reproducible promotion report with before/after precision estimates

## Method
1. Candidate extraction
- Build a per-pair table: `from_token -> to_token`, with counts, number of distinct entries, and number of distinct pages.
- Split into buckets:
  - `high_freq`: count >= 8
  - `mid_freq`: count 3-7
  - `rare`: count 1-2

2. Evidence scoring per candidate
- Internal evidence:
  - Sanskrit context score distribution (`ctx`)
  - Family confidence (`high/medium/low`)
  - Edit distance and rewrite type (`$->ś`, `ä->ā`, etc.)
  - Zone profile (`german_prose_with_translit`, `latin_other`, `headword_line`)
- External evidence:
  - Lexeme lookup against Sanskrit reference lists (Wiktionary/Monier-Williams exported list).
  - If exact lookup fails, normalized lookup after diacritic repair.
- Each candidate gets a triage label:
  - `promote_now`
  - `needs_manual_sampling`
  - `hold`

3. Manual sampling protocol (for `mid_freq` + `rare`)
- Sample up to 20 contexts per candidate (or all if fewer).
- Review both local line and neighboring lines.
- Record judgment as `correct`, `incorrect`, or `uncertain`.
- Require:
  - Precision >= 98% for promotion to automatic Tier A
  - Precision 95-97% for guarded Tier A (only with strong context cues like `(Mvy)`)
  - Precision < 95% stays in Tier B

4. Promotion rules
- Promote only if one of:
  - `high_freq` + strong internal evidence + no sampled errors
  - `mid_freq` with passing manual precision
  - `rare` with passing manual precision and external lexicon support
- Add promoted pairs to explicit override map in `scripts/postprocess_entry_map.py`.
- Keep a changelog block in commit message listing every newly promoted pair.

5. Regression and safety checks
- Re-run postprocess for both volumes.
- Compute:
  - delta in Sanskrit Tier A changes
  - delta in Sanskrit review queue size
  - random audit sample of newly auto-applied rows (minimum 100 rows overall)
- Block merge if any high-impact false-positive pattern appears (e.g., German words rewritten as Sanskrit).

## Operational cadence
- Batch promotions once per review cycle.
- Never promote a rare candidate without either:
  - high-confidence external lexicon support, or
  - passing manual sample with documented evidence.

## Immediate next batch
- Current focus:
  - Consume top pending Sanskrit review pairs after high-frequency override pass.
  - Run evidence scoring and produce first `mid_freq`/`rare` triage report.
