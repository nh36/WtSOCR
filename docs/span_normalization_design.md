# Span-Level Normalization and Safe Canonicalization Design

## Goal

Improve OCR quality without over-normalizing by:

1. Moving from line-only logic to **span/token-scoped** decisions.
2. Keeping language-specific fixes isolated (Tibetan romanization vs Sanskrit vs German/bibliography).
3. Applying corpus-wide rewrites only from a **human-approved list**.

This design is for the current pipeline in `scripts/line_anchor_merge_pilot.py`.

## What Already Exists

Current code already provides:

- Block context: `classify_block_context(...)`
- Intra-line splitting: `split_line_spans(...)` into `tibetan_script`, `romanization`, `latin`
- Romanization repairs: `normalize_romanization_segment(...)`
- Tibetan-aligned `ṅ` enforcement: `enforce_ng_from_tibetan_prefix(...)`
- Sanskrit-aware token repairs for umlaut/macron and cedilla confusions
- Noise dropping in romanization tails: `drop_roman_tail_noise_after_tibetan(...)`

The remaining issue is mostly **scope precision** and **safe canonicalization workflow**.

## Core Design

### 1. Multi-pass candidates at span level (not whole-line)

For each line:

1. Run current normalization to get baseline output.
2. Build spans with `split_line_spans(...)`.
3. For each non-Tibetan span, generate candidates:
   - `identity` (minimal cleanup only)
   - `romanization_strict` (only if span is romanization)
   - `sanskrit_strict` (only if Sanskrit markers / token cues)
   - `german_safe` (bibliography/german context, no Sanskrit rewrites)
4. Score candidates and choose per span; then reassemble line.

This avoids one mode damaging unrelated text in the same line.

### 2. Deterministic gating rules

Apply repairs only when all scope checks pass:

- `romanization` fixes:
  - Requires Tibetan prefix + transliteration-like lead tokens.
  - Allows `ñ -> ṅ` only by existing positional rules and Tibetan-prefix alignment.
  - Drops digit/symbol noise tokens only inside romanization span.

- `sanskrit` fixes (`ä/ü -> ā/ū`, `ş->ṣ`, `ņ->ṇ`, etc.):
  - Only inside Sanskrit-marked spans (`skt.` markers, equals glosses, Sanskritic token cues).
  - Token-level and hyphen-segment-level; never blanket line replace.

- `german/bibliography`:
  - Prefer identity except known safe normalizations (`ı -> i`, quote normalization, stray symbol removal).
  - No automatic umlaut->macron conversion.

### 3. Confidence + audit for each changed token

Each token rewrite stores:

- `page`, `line`, `span_type`, `block_context`
- `before`, `after`, `rule_id`, `confidence`
- `anchor` fields if Tibetan alignment used

Confidence tiers:

- `high`: Tibetan glyph alignment supports change OR exact approved rewrite pair
- `medium`: strong scope + transliteration validity improvement
- `low`: heuristic only (not auto-applied corpus-wide)

Only `high` can flow directly into full output by default.

## Canonicalization Framework (Variant Families)

### 1. Build variant families by scope

Construct token families by normalized skeleton (`NFC`, casefolded, diacritics stripped), but split by scope:

- `romanization`
- `sanskrit`
- `german`
- `bibliography_name`

Never merge families across scopes.

### 2. Candidate canonical form

For each family:

- Rank by frequency, authority-list presence, script/diacritic validity.
- Emit proposal rows, not automatic rewrites:
  - `work/.../variant_report_*/human_approval_sheet.tsv`

### 3. Application policy

Corpus-wide rewrites must come from:

- `approved_rewrites.tsv` only
- Scope-restricted application (same scope as approved row)
- Exact token or regex with bounded context, never broad global substitution

This matches your “prefer small OCR mess over false positives” requirement.

## Data Files (authoritative)

Keep three maintained files:

1. `authority_people_and_sources.tsv`
2. `pattern_catalogue.tsv`
3. `regression_testset.txt`

Add fields:

- `scope`
- `rule_type` (`literal|regex|fuzzy|delete`)
- `apply_level` (`token|span|line`)

## Evaluation Protocol

For each pilot sample:

1. Run merge + normalization.
2. Emit anomaly reports (digit garbage, suspicious Sanskrit umlauts, symbol noise).
3. Emit variant families and approval sheet.
4. Apply only approved rewrites.
5. Re-run regression set.

Primary metrics:

- Romanization validity rate in headword tails
- Tibetan-aligned `ṅ` recall (where Tibetan syllable contains `ང`)
- False-change rate in German/bibliography spans
- Count of unresolved anomaly tokens per 1,000 lines

## Implementation Steps

1. Add per-span candidate scorer and chooser in `line_anchor_merge_pilot.py`.
2. Add token-change audit TSV output (`*_token_audit.tsv`).
3. Add scope-aware variant-family extractor script.
4. Extend approval workflow so rewrite application enforces scope gates.
5. Add regression runner command to fail on known regressions.

## Non-Goals

- No unconditional global rewrite rules beyond trivial Unicode cleanup.
- No cross-scope fuzzy rewriting.
- No replacement of existing OCR with a black-box model without audit trails.
