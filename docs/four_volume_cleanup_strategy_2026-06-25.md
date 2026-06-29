> Historical audit record. This file is not the current to-do list. See `docs/STATUS.md` for the current operational status.

# Four-Volume Cleanup Strategy

Date: 2026-06-25

## Purpose

The next cleanup stage should be driven by a four-volume residual error ledger, not by
isolated hunches. The ledger is diagnostic only: it groups the existing Sanskrit,
Tibetan, siglum, Google-witness, validator, watchdog, and review-queue outputs into a
single ranked error budget.

This pass does not add OCR correction heuristics, does not loosen Google Vision
adoption gates, and does not treat validator-only residue as correction evidence.

## Inputs

Use the latest trusted Sanskrit and Tibetan diagnostic bundles:

- `work/production_release_candidate_residual_sanskrit_postcheck_20260531T190000Z`
- `work/tibetan_second_ambitious_cleanup_20260624T212313Z`

These are local `work/` artifacts. They are not versioned in the repository.

## Reproduction

```sh
OUT="work/four_volume_cleanup_strategy_$(date -u +%Y%m%dT%H%M%SZ)"
python3 scripts/build_four_volume_residual_error_ledger.py \
  --input-root work/production_release_candidate_residual_sanskrit_postcheck_20260531T190000Z \
  --input-root work/tibetan_second_ambitious_cleanup_20260624T212313Z \
  --output-dir "$OUT" \
  --report-date 2026-06-25
```

The generated bundle contains:

- `four_volume_residual_error_ledger.tsv`: every grouped residual diagnostic family.
- `four_volume_promotion_candidates.tsv`: exact reviewed candidates only; still not
  automatic corrections.
- `four_volume_source_review_needed.tsv`: rows that require source-image/PDF review.
- `four_volume_policy_decisions_needed.tsv`: bibliography, siglum, and editorial-policy
  decisions.
- `four_volume_google_sampling_targets.tsv`: Google-witness patterns that need sampling
  or adoption auditing.
- `four_volume_error_budget_summary.md`: concise counts and top ranked families.

## Working Rules

Treat Google Vision as an alternate witness, not an authority. A high-volume Google
pattern should be sampled before any exact reviewed row promotion.

Keep validator-only rows, already-corrected/stale rows, and policy false positives out
of the correction queue. They are useful for measuring report noise, not for changing
the text.

Keep siglum policy separate from Tibetan and Sanskrit lexical cleanup. For example, a
`$` in a siglum may be strong evidence for `ś`, but it should be handled as a
registry-backed siglum decision rather than as a generic character rule.

Future correction batches should be selected from the promotion, source-review, policy,
and Google-sampling outputs in that order:

1. Promote exact reviewed rows whose context and target are already clear.
2. Source-check medium-risk rows that look promising but ambiguous.
3. Resolve siglum and bibliography policy cases as registry updates.
4. Sample high-volume Google patterns and promote only exact rows or tightly gated
   families when the sample is homogeneous.

After any promotion batch, rerun the per-volume QA and regenerate the ledger so the
error budget shrinks in a measurable way.
