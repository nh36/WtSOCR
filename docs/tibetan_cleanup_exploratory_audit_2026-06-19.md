# Tibetan Cleanup Exploratory Audit

Date: 2026-06-19

This pass is diagnostic only. It added review queues for Tibetan, sigla, and residual Sanskrit cleanup, but did not add OCR correction heuristics, did not loosen Google Vision adoption gates, and did not modify corrected text.

## Inputs

- `work/postprocess_wts8b_9m_low_hanging_sanskrit_casefix_20260618T091506Z/wts_8_b`
- `work/postprocess_wts8b_9m_low_hanging_sanskrit_casefix_20260618T091506Z/wts_9_m`

## Output

Output directory:

- `work/tibetan_cleanup_exploratory_20260619T092605Z`

Generated diagnostic files:

| File | Data rows |
|---|---:|
| `tibetan_google_candidate_readings.tsv` | 104 |
| `tibetan_orthography_damage_candidates.tsv` | 336 |
| `sigla_variant_candidates.tsv` | 107 |
| `residual_sanskrit_low_confidence_candidates.tsv` | 433 |
| `tibetan_variant_families.tsv` | 124 |
| `tibetan_google_adoption_patterns.tsv` | 244 |

## Main Findings

The clearest Tibetan candidate family is `dnos -> dṅos`: 38 occurrences across WtS 8-b and WtS 9-m. Six rows are Google-exposed or Google-supported, but several Google alternates propose `dños`, which is not the right Tibetan normalisation. The diagnostic queue therefore records the target as `dṅos`, not `dños`.

`gNa-khri -> gÑa-khri` is already present as a Google adoption pattern at WtS 9-m p72 l12. The diagnostic script keeps this as an exact Tibetan family, so any future non-adopted examples can be reviewed without creating a broad nasal rule.

`Vi$T`, `VisT`, `ViST`, `VisST`, `ViśsT`, `VisṬ`, and related variants are treated as citation/siglum policy cases pointing to canonical `ViśT`, the siglum for the `Viśeṣastavatīkā` source. They are deliberately kept out of the Tibetan lexical queue.

The siglum scan now rejects lowercase German registry false positives such as `ins`, while preserving case-sensitive canonical sigla such as `Ins` and dollar variants such as `in$` and `L$dz`.

`la'añń` appears once at WtS 9-m p318 l32. Both the current form and a mechanical `la'aṅń`-style repair look malformed, so this remains source-review-only.

The high-volume Google adoption patterns are promising but need manual sampling before any policy change. The largest are `dan -> daṅ`, `Ita -> lta`, `Iha -> lha`, `Ina -> lṅa`, and `Idan -> ldan`.

The direct corrected-text scan still finds many `$ -> ś` candidates, but the family is mixed across transliteration, sigla, and noisy contexts. It is not a correction rule by itself.

The residual Sanskrit low-confidence queue has 433 rows. It is useful as a backstop after the Sanskrit cleanup, but this pass did not identify an immediate Sanskrit promotion batch from it.

## Suggested Next Batch

1. Source/context-audit all 38 `dnos` rows and promote exact `dnos -> dṅos` only where Tibetan context is confirmed.
2. Decide a siglum policy batch for `ViśT` variants separately from Tibetan/Sanskrit lexical cleanup.
3. Source-review the single `la'añń` row before changing it.
4. Sample the top Tibetan Google adoption patterns before adopting broader exact families.

## Verification

Commands run:

```bash
python3 -m py_compile scripts/build_tibetan_cleanup_diagnostics.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
python3 scripts/build_tibetan_cleanup_diagnostics.py \
  --run-dir work/postprocess_wts8b_9m_low_hanging_sanskrit_casefix_20260618T091506Z/wts_8_b \
  --run-dir work/postprocess_wts8b_9m_low_hanging_sanskrit_casefix_20260618T091506Z/wts_9_m \
  --out-dir work/tibetan_cleanup_exploratory_20260619T092605Z
```

Result:

- `109 passed in 0.78s`
- `py_compile` completed with no errors.
