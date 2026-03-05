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

## Plan for Mixed Sanskrit+German Compounds

### Problem
Tokens like `Mahäyäna-Buddhismus`, `Mädhyamika-Kommentar`, and `paryastikä-Haltung` combine Sanskrit transliteration and German prose in one surface token. Whole-token scoring can over-queue or misclassify these.

### Target behavior
- Normalize Sanskrit subparts safely (`Mahäyäna -> Mahāyāna`).
- Preserve German subparts exactly (`Buddhismus`, `Kommentar`, `Haltung`).
- Prevent pure-German queue noise.

### Proposed workflow
1. Compound segmentation
- Split candidate tokens on hyphen and slash boundaries.
- Keep punctuation and original case shape for round-trip reconstruction.

2. Segment language typing
- For each segment, assign `sanskrit`, `german`, or `unknown` using:
  - Sanskrit markers: `$`, transliteration diacritics, Sanskrit cluster patterns.
  - German markers: umlaut + German suffix lexicon (`-ung`, `-keit`, `-ismus`, etc.) and stopword hints.

3. Segment-level rewrite policy
- Apply Sanskrit char-map rewrites only on `sanskrit` segments.
- Do not rewrite `german` segments.
- If all rewritten segments are Sanskrit and at least one changed, emit a single compound-level suggestion with segment evidence.

4. Queue policy
- `pure_german`: drop from Sanskrit review queue.
- `mixed`: keep in Sanskrit queue only if at least one Sanskrit segment has a valid rewrite.
- `unknown-only`: hold for manual review, no auto-promotion.

5. Promotion policy for rare items
- Allow singleton promotion only when:
  - rewrite class is `safe_char_map`,
  - changed segment(s) are Sanskrit-typed,
  - no changed segment is German-typed,
  - no hard German-risk substring appears in changed segment(s).

6. Validation
- Track metrics separately for `pure_sanskrit`, `mixed`, and `pure_german` buckets:
  - queue size,
  - auto-apply count,
  - false-positive sample rate.
- Add a fixed regression set of known mixed compounds and expected outputs.

### Rollout steps
1. Add a small segmenter + segment typer helper module in `postprocess_entry_map.py`.
2. Wire segment-level normalization into `sanskrit_char_normalize`.
3. Re-run both volumes and compare bucketed metrics.
4. Promote only after mixed-bucket audit passes.
