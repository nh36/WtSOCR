# Tibetan Medium Cleanup Batch

Date: 2026-06-19

This pass used the committed Tibetan cleanup diagnostics to promote exact, reviewed corrections for WtS 8-b and WtS 9-m. It did not add broad OCR heuristics, did not loosen Google Vision adoption gates, and did not use Google as an authority. Google remained an alternate witness only.

## Inputs

- Exploratory diagnostics: `work/tibetan_cleanup_exploratory_20260619T092605Z`
- Previous postprocess baseline: `work/postprocess_wts8b_9m_low_hanging_sanskrit_casefix_20260618T091506Z`
- Batch output: `work/tibetan_medium_cleanup_batch_20260619T103042Z`
- Review queues used:
  - `tibetan_variant_families.tsv`
  - `tibetan_orthography_damage_candidates.tsv`
  - `tibetan_google_candidate_readings.tsv`
  - `tibetan_google_adoption_patterns.tsv`
  - `sigla_variant_candidates.tsv`

`residual_sanskrit_low_confidence_candidates.tsv` was not used as a promotion queue in this pass.

## Promoted Families

| Family | Scope | Output effect | Reason |
| --- | --- | ---: | --- |
| `dnos -> dṅos` | exact reviewed page/line/token rows | 37 applied output changes | Normal Tibetan `dṅos`, including `dṅos po`, `dṅos su`, and `dṅos grub` contexts. The rejected Google-style direction `dnos -> dños` was not used. |
| `VisT`/`VisST`/`ViST`/`ViśsT`/`visT -> ViśT` | exact reviewed citation-siglum rows | 17 applied output changes | `ViśT` is the siglum for `Viśeṣastavatīkā`; `$`/`s`/case variants in this family were normalized only at reviewed citation sites. |

The generated corrected text changed on 49 lines compared with `work/postprocess_wts8b_9m_low_hanging_sanskrit_casefix_20260618T091506Z`: 32 in WtS 8-b and 17 in WtS 9-m. The reason count is 54 because five WtS 9-m `dnos -> dṅos` rows had already been covered by earlier exact cleanup and therefore did not produce new line diffs against that baseline.

No broad `ń -> ṅ`, `n -> ñ`, `dnos -> dṅos`, or siglum-wide character rule was added. The changes are exact rows in `data/reviewed_tibetan_exact_overrides.tsv`.

## Representative Diff Audit

All changed corrected-text lines were checked against the intended families.

| Volume | Before | After |
| --- | --- | --- |
| WtS 8-b | `Lex. ba ku (v.\|. kku) la'am dnos su bZag (v..` | `Lex. ba ku (v.\|. kku) la'am dṅos su bZag (v..` |
| WtS 8-b | `dnos grub tu 'dzin pa sh re rje "was für` | `dṅos grub tu 'dzin pa sh re rje "was für` |
| WtS 8-b | `dern des Körpers bewegen sich nicht" (VisT` | `dern des Körpers bewegen sich nicht" (ViśT` |
| WtS 8-b | `dich darum, einen Sohn zu zeugen!" (VisST` | `dich darum, einen Sohn zu zeugen!" (ViśT` |
| WtS 9-m | `dnos mi len "sie sollen nur die festgesetzten` | `dṅos mi len "sie sollen nur die festgesetzten` |
| WtS 9-m | `anidra)' (Ahs 1.5.23d); dnos dan drios —` | `anidra)' (Ahs 1.5.23d); dṅos dan drios —` |
| WtS 9-m | `Unvergängliche kann niemand töten" (VisT` | `Unvergängliche kann niemand töten" (ViśT` |
| WtS 9-m | `bar bcom pa "vom Fluch überwältigt" (ViśsT` | `bar bcom pa "vom Fluch überwältigt" (ViśT` |

## Production Counts

| Volume | Alternate-witness adoptions | Unresolved alternate rows | Reviewed Tibetan exact changes | Watchdog rows | Sanskrit review suggestions | Corrected text SHA-256 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| WtS 8-b | 3 | 900 | 48 | 31 | 1 | `9ce64d02f8feadf1de40442d35142c6e01ef9459283dfd017ab50bcaa7e09c1e` |
| WtS 9-m | 851 | 1135 | 110 | 16 | 1 | `847dfe53ffa7de0967fcbb14e3e86375066b1dce191e99327f86336249db4d29` |

Target-family reason counts in the generated changes TSVs:

| Volume | `reviewed_tibetan_exact_dngos` | `reviewed_siglum_exact_visht` |
| --- | ---: | ---: |
| WtS 8-b | 25 | 7 |
| WtS 9-m | 12 | 10 |

## Residual Diagnostics

The exploratory diagnostics were combined across WtS 8-b and WtS 9-m. After this batch, diagnostics were regenerated per volume under `work/tibetan_medium_cleanup_batch_20260619T103042Z`.

| Queue | Exploratory combined rows | WtS 8-b rows after batch | WtS 9-m rows after batch |
| --- | ---: | ---: | ---: |
| `tibetan_variant_families.tsv` | 124 | 39 | 93 |
| `tibetan_orthography_damage_candidates.tsv` | 336 | 172 | 132 |
| `tibetan_google_candidate_readings.tsv` | 104 | 12 | 92 |
| `tibetan_google_adoption_patterns.tsv` | 244 | 3 | 241 |
| `sigla_variant_candidates.tsv` | 107 | 14 | 76 |
| `residual_sanskrit_low_confidence_candidates.tsv` | 433 | 219 | 218 |

These are diagnostic inventories, not one-to-one subtraction counts. The batch intentionally changed correction data only; it did not change the diagnostic miner logic.

## Google Pattern Sampling

The largest Google adoption patterns in the exploratory audit were sampled before deciding whether to promote more exact rows:

| Pattern | Count | Decision |
| --- | ---: | --- |
| `dan -> daṅ` | 140 | Already adopted under existing alternate-witness gates in WtS 9-m; not converted to a source-independent override in this batch. |
| `Ita -> lta` | 103 | Plausible Tibetan contexts, but left as Google-gated adoption pending row-level review. |
| `Iha -> lha` | 55 | Plausible Tibetan contexts, including one WtS 8-b row; left as Google-gated adoption. |
| `Ina -> lṅa` | 20 | Plausible but some contexts are noisy; deferred. |
| `Idan -> ldan` | 15 | Plausible; deferred pending row-level review. |

These high-volume patterns remain candidates for a later audit, but this pass did not loosen Google alignment or adoption rules.

## Deferrals

- `$ -> ś` remains review-only. It is high-volume and often Sanskrit/Tibetan-adjacent, but too broad for a medium audited batch.
- Non-`ViśT` sigla families such as `Gś-H`, `Yś/Y$`, `Lsdz-K/L$dz-K`, `Bu-$z`, `Li$`, and `gZ1` were left for bibliographic policy review.
- `la'añń` and other nasal-damage-looking rows remain deferred; no broad nasal repair rule was introduced.
- Sanskrit low-confidence rows remain a backstop queue, not a promotion source for this Tibetan cleanup batch.

## Verification

Commands run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result: `110 passed`.

Production commands:

```bash
python3 scripts/postprocess_entry_map.py --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_8-b/WtS 8-b_lineanchored_merged_full.txt" --outdir work/tibetan_medium_cleanup_batch_20260619T103042Z/wts_8_b --label wts_8_b --alternate-merged "pdfs/WtS 8-b.vision.txt" --alternate-google-vision
python3 scripts/postprocess_entry_map.py --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_9-m/WtS 9-m_lineanchored_merged_full.txt" --outdir work/tibetan_medium_cleanup_batch_20260619T103042Z/wts_9_m --label wts_9_m --alternate-merged "pdfs/WtS 9-m.vision.txt" --alternate-google-vision
python3 scripts/build_tibetan_cleanup_diagnostics.py --run-dir work/tibetan_medium_cleanup_batch_20260619T103042Z/wts_8_b --out-dir work/tibetan_medium_cleanup_batch_20260619T103042Z/tibetan_cleanup_diagnostics_wts_8_b
python3 scripts/build_tibetan_cleanup_diagnostics.py --run-dir work/tibetan_medium_cleanup_batch_20260619T103042Z/wts_9_m --out-dir work/tibetan_medium_cleanup_batch_20260619T103042Z/tibetan_cleanup_diagnostics_wts_9_m
```
