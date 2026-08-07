# Sanskrit Large-Batch Cleanup — 2026-05-28

> Historical audit record. Counts, proposed corrections, and recommendations in
> the original production-QA branch were not adopted wholesale and may have been
> superseded. For the current state, see `docs/STATUS.md`. The complete original
> report and decision artifact are preserved by the archival tag
> `archive-production-qa-release-candidate`.

## Historical scope

The production-QA branch reviewed exact Sanskrit normalisation candidates from
two sources:

- Google alternate-witness candidates checked against local context;
- curated title, proper-name, and technical-term rows from the then-current
  Sanskrit review queue.

The pass explicitly did not authorize broad `jn -> jñ`, `Sata -> Śata`,
`ä -> ā`, damaged-`sūtra`, or Google-witness replacement rules. Its working
decision ledger was `work/sanskrit_large_batch_decisions_20260528.tsv` on the
historical branch.

## Historical result

The branch report recorded 47 exact token normalisations across all four
volumes: 6 in WtS 1–34, 21 in WtS 35–51, 7 in WtS 8-b, and 13 in WtS 9-m.
Candidates were deferred or rejected when the suggested target remained damaged,
needed a source image, was German or Tibetan/Wylie material, or was an ambiguous
short siglum.

That branch ultimately contained 377 rows in
`data/sanskrit_promote_overrides.tsv`. Current `main` contains a separately
reviewed 272-row registry and current release text still contains many source
tokens proposed for change by the historical branch. Therefore the old decision
set is provenance, not current correction authority, and was intentionally not
copied during branch reconciliation.

## Current replacement

Current Sanskrit state and evidence are represented by:

- `data/sanskrit_promote_overrides.tsv`;
- `data/correction_families.tsv`;
- `release/current/qa/*/*_sanskrit_report.tsv`;
- `release/current/qa/*/tibetan_cleanup_diagnostics/`;
- `docs/STATUS.md`.

The historical production paths, QA generator, manual-review-package generator,
and tracked `work/` decision artifact remain available through
`archive-production-qa-release-candidate`; they are not active build inputs.
