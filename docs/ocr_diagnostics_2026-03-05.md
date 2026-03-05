# OCR Diagnostics Snapshot (2026-03-05)

## Scope
- Corpus snapshot:
  - `work/postprocess_step123_userlist_20260305T090811Z`
- Inputs inspected:
  - `*_summary.json`
  - `*_review_queue.tsv`
  - `*_validator_issues.tsv`
  - `*_changes.tsv`
  - `*_citation_name_report.tsv`
  - `*_sanskrit_report.tsv`
  - `*_corrected_full.txt`

## Headline Metrics
- Total changes applied (Tier A): `4774`
- Total review suggestions (Tier B): `5149`
- Total validator issues: `42233`
- Review queue reason mix:
  - `confusable_global_lexicon`: `4094`
  - `confusable_context`: `972`
  - `citation_confusable_I_to_l`: `67`
- Validator issue mix:
  - `invalid_translit_shape`: `18454`
  - `german_umlaut_in_translit_context`: `18454`
  - `confusable_char`: `5325`

## What Is Messiest (Ranked)

### 1) Dotless-`ı` confusables are still the largest unresolved bucket
- In review queue:
  - dotless-`ı` rows: `4474`
  - top pairs:
    - `kyı -> kyi` (`717`)
    - `yanı -> yani` (`538`)
    - `kyıs -> kyis` (`322`)
    - `yın -> yin` (`217`)
- In final corrected text:
  - dotless-`ı` token occurrences: `15926`
  - dotless-`ı` unique token forms: `3512` (combined volumes)
- Coverage gap (false negatives):
  - `confusable_char` validator rows with dotless-`ı`: `4115`
  - review rows with dotless-`ı`: `4474`
  - validator-only dotless tokens not entering review: `3019` occurrences, `992` token types
  - top missed forms:
    - `ba’ı` (`379`)
    - `pa’ı` (`336`)
    - `la’anı`/`la’anı` variants (`138+`)
    - `Sıddh` (`107`)

Diagnosis:
- The biggest missing class is apostrophe particle forms (`’ı`) and mixed Sanskrit/Tibetan noise forms.
- This is high-impact and mostly low-risk because rewrite is usually single-char `ı -> i` with no deletion.

### 2) `$` confusable handling is high-value but currently mixed precision
- In review queue:
  - `$` bucket rows: `568`
  - mostly `$ -> ś` (`535`)
- Validator-only (not in review):
  - `383` occurrences, `132` token types
  - top missed: `L$dz-K`, `L$dz`, `$es`, `$ambh`, `$a`, `g$egs`

Observed false-positive risk:
- Some current suggestions are mechanically valid but linguistically wrong:
  - `Ganes$a -> Ganesśa` (should be `Ganeśa`-type normalization, not `sś`)
  - `Mahes$vara -> Mahesśvara` (same class)
  - `Bu-$z -> Bu-śz`

Diagnosis:
- `$ -> ś` by itself is not enough. It needs Sanskrit/Tibetan token-shape guards and anti-`sś` safeguards.

### 3) Initial `I` vs `l` remains a significant residual class
- Applied successfully already:
  - changes in this bucket: `1904`
- Still missed by queue:
  - validator-only uppercase-`I` confusable rows: `763` occurrences, `251` token types
  - top forms: `Iha’i`, `Iha`, `Ina’i`, `Khri-Ide`, `Pho-Iha`

Diagnosis:
- Main system is catching much of this class, but entry/citation edge cases still leak.
- Remaining misses are likely recoverable with targeted lexical/context gates.

### 4) Citation capitalization noise remains non-trivial
- Citation families observed: `70`
- Non-canonical citation tokens: `223`
- Persistent families with noisy variants:
  - `SCHUH`: mixed forms (`SchuH`, `ScHuH`, `ScHUH`)
  - `SCHWIEGER`: mixed forms (`ScHwieger`, `ScHwIEGER`, etc.)
  - `LOKESH`, `CHANDRA`, `EMMERICK`, `LMAEDA`, `NOBEL`

Diagnosis:
- Existing citation normalization works, but canonicalization is still too conservative for mixed-case OCR junk.

### 5) Sanskrit pipeline is much cleaner now, but not perfect
- Sanskrit families: `259`
- Non-canonical Sanskrit totals: `44` (small compared with prior phases)
- Confidence on non-canonical families:
  - `high`: `10`
  - `medium`: `10`
  - `low`: `11`
- Sanskrit review queue is now small:
  - `8` total pending rows (mostly `jñ` and one long compound)

Diagnosis:
- Sanskrit is no longer the dominant mess.
- Remaining work is mostly targeted cleanup and canonical-form consistency.

## False Positives vs False Negatives (Current)

### Main false negatives
- Dotless-`ı` in apostrophe particles and mixed forms (`ba’ı`, `pa’ı`, `la’anı` patterns).
- `$` confusables in lexicalized forms not currently promoted (`$es`, `g$egs`, some citation-linked tokens).
- Residual `I -> l` translit forms in Tibetan-like contexts.

### Main false positives (or high-risk proposals)
- Raw `$ -> ś` replacements yielding `sś` artifacts.
- Over-broad translit validation in German-heavy lines.
- Duplicative validator issue spam obscuring true priorities.

## Validator Signal Quality Problem
- `invalid_translit_shape` and `german_umlaut_in_translit_context` are near-duplicate signals:
  - overlap on same token-site: `18417`
  - `invalid_only`: `0`
  - `umlaut_only`: `0`
- High concentration in `german_prose_with_translit` zone (`12527` for each).

Diagnosis:
- This doubles queue noise without adding discrimination.
- It makes triage metrics look worse than true residual OCR risk.

## Easiest Safe Improvements (Highest ROI)

### A) Expand dotless-`ı` rewrite coverage with strict no-deletion policy
Expected yield:
- Immediate reduction of the largest unresolved bucket (`4474` queue rows + `3019` validator-only misses).

Safety gates:
- Only one-char map `ı -> i`.
- Never remove apostrophe.
- Require translit-bearing zone or trusted Tibetan/translit context cues.

### B) Add guarded `$` normalization with anti-`sś` rule
Expected yield:
- Reduce `568` queued `$` rows plus a material part of `383` validator-only misses.

Safety gates:
- Block rewrites producing `sś`, `śz`, or other impossible clusters.
- Prefer allowlist/context-driven replacements in Tibetan/translit zones.
- Exclude numeric/citation-symbol tokens (`977/$`, `0/7/$`, etc.).

### C) Tighten citation mixed-case canonicalization
Expected yield:
- Remove most residual noise in high-frequency citation families (`SCHUH`, `SCHWIEGER`, etc.).

Safety gates:
- Apply only in citation-like masks and neighbor lines.
- Use family lexicon + year/cue context.
- Preserve non-name German tokens.

### D) Collapse duplicated validator issues
Expected yield:
- Major triage clarity improvement without changing text output.

Safety gates:
- Keep one merged issue code for umlaut/translit shape collision.
- Preserve full raw diagnostics in optional verbose mode.

## Harder, Next-Step Improvements
- Better Sanskrit canonical-family selection:
  - avoid noisy canonical bases like `$raddhä` as family canonical anchor.
- Mixed Sanskrit+German compound normalization:
  - segment-level language typing before rewrite.
- Rare-item promotion framework:
  - continue promote/hold table with sampled precision checks.

## Concrete Code Touchpoints
- `scripts/postprocess_entry_map.py`
  - confusable validation and gating:
    - `validate_translit_token`
    - `token_is_initial_i_confusable_noise`
    - `choose_rewrite`
  - citation normalization:
    - `apply_citation_name_normalization`
  - Sanskrit normalization:
    - `apply_sanskrit_normalization`
    - `token_is_pure_german_for_sanskrit_queue`

## Recommended Execution Order
1. Dotless-`ı` coverage expansion (apostrophe-aware, no deletion).
2. `$` guardrail pass (anti-`sś`, zone/context gating).
3. Citation mixed-case tightening for known families.
4. Validator deduplication for triage clarity.
5. Re-run postprocess and compare:
   - queue size by reason
   - validator issue counts by type
   - sampled precision on newly auto-applied rows.

## Acceptance Criteria For Next Iteration
- Dotless-`ı` review+validator combined backlog reduced by at least `35%`.
- `$` false-positive patterns (`sś` artifacts) reduced to `0`.
- Citation non-canonical totals reduced by at least `60%` for top families.
- No regressions on protected Tibetan particles (`'i`, `'o`) and protected Sanskrit clusters (`jñ` etc.).
