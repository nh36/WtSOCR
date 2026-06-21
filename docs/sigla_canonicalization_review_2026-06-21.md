# Sigla Canonicalization Review, 2026-06-21

## Scope

This pass reviews the non-ViśT `$` siglum families surfaced by the WtS 8-b / WtS 9-m Tibetan cleanup diagnostics:

- `Bu-$z` and related variants
- `Y$`, `Yś`, and related variants
- `G$-H`, `Gś-H`, and related variants

This is a citation/siglum canonicalization change only. It does not add a generic `$ -> ś` rule.

## Evidence

- `docs/ocr_diagnostics_2026-03-05.md` records `Bu-$z -> Bu-śz`.
- `docs/tibetan_medium_cleanup_batch_2026-06-19.md` left `Gś-H`, `Yś/Y$`, `Bu-$z`, `Li$`, and `gZ1` for bibliographic policy review.
- `docs/visht_siglum_correction_2026-06-18.md` resolves `ViśT` from `Viśeṣastavatīkā`, supporting the policy that sigla should preserve `ś` when the title/context supports it.
- Residual diagnostics contain ś-bearing contextual forms such as `Gś-H` and `Yś`; normalizing these to `Gs-H` or `Ys` would erase the attested `ś`.
- The reviewed forms occur in citation/siglum contexts. Plain `Gs` remains a distinct siglum from the `Gś-H` family.

## Decisions

| Family | Canonical | Variants handled | Decision |
| --- | --- | --- | --- |
| `Bu-$z` | `Bu-śz` | `Bu-$`, `Bu-$z`, `Bu-$2`, `Bu-$sz`, `Bu-Sz`, `Bu-śz`, OCR digit variants | Preserve `ś`; do not canonicalize to `Bu-Sz`. |
| `Y$` / `Yś` | `Yś` | `Y$`, `Ys$`, `Ys`, `Y5`, `Yś` | Preserve `ś`; require siglum context for plain `Ys`. |
| `G$-H` / `Gś-H` | `Gś-H` | `G$-H`, `G$s-H`, `Gs-H`, `Gś-H` | Preserve `ś`; keep plain `Gs` distinct. |
| `Li$` | `Liś` | existing registry variants | Straightforward existing siglum policy. |
| `gZ1` | `gZi` | existing registry variants | Straightforward existing siglum policy. |

## Guardrails

- Normalization is routed through the siglum registry and confusable-map logic.
- Plain variants such as `Ys` require citation/siglum context before they are treated as sigla.
- No Tibetan lexical cleanup, Sanskrit cleanup, or Google Vision adoption gate changes are included in this pass.
- No broad `$ -> ś`, `s -> ś`, or other character-level rule is introduced.

## Verification

Commands run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/build_tibetan_residual_triage_report.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result:

```text
113 passed, 6 subtests passed
```
