# Residual Sanskrit Promotable Batch, 2026-05-31

Production baseline:
`work/production_release_candidate_residual_sanskrit_cleanup_20260529T100325Z`

New production output:
`work/production_release_candidate_residual_sanskrit_promotable_batch_20260531T180412Z`

This pass refined the residual Sanskrit QA grouping and then promoted a small,
source-checked exact batch. Google Vision adoption gates were not changed.
Validator-only residue was not used as correction evidence. No broad rule was
added for `ä -> ā`, `jn -> jñ`, final `b/l -> ḥ`, `Sata -> Śata`, or damaged
`sūtra` repair.

## QA Refinement

The residual grouping now has a `citation_or_siglum` reason family. Short
bibliographic abbreviations and sigla such as `VisT -> VisṬ` are classified as
source-policy review cases, not Sanskrit proper-name or title-family correction
candidates.

A filtered queue was added:

`residual_sanskrit_promotable_candidates.tsv`

This queue is narrower than `residual_sanskrit_damage_top_candidates.tsv`.
It keeps only exact-token groups with a proposed target, excludes sigla,
German/prose and Tibetan/Wylie-like rows, and requires Google, review-queue, or
strong Sanskrit/Mvy/title context.

## Baseline Grouped Counts

After regenerating QA on the baseline directory with the refined grouping:

| output | rows |
| --- | ---: |
| `residual_sanskrit_damage_candidates.tsv` | 29,830 |
| `residual_sanskrit_damage_families.tsv` | 5,711 |
| `residual_sanskrit_damage_top_candidates.tsv` | 250 |
| `residual_sanskrit_promotable_candidates.tsv` | 7 |
| `all_watchdog_rows.tsv` | 285 |
| `live_validator_only_residue.tsv` | 1 |
| `live_policy_or_false_positive.tsv` | 4 |
| `google_sanskrit_candidate_readings.tsv` | 39 |
| `all_sanskrit_review_suggestions.tsv` | 9 |
| `possible_missed_google_readings.tsv` | 0 |

`VisT` and `Käsy/Käśy` appear in the broader top-candidate review queue as
`citation_or_siglum`; they do not appear in the promotable queue.

## Source Review

Source PDFs in `pdfs/` were inspected for the deferred rows.

| row | decision | source-review note |
| --- | --- | --- |
| `dnantaryamärgab -> ānantaryamārgaḥ` | promote | WtS 8-b p55 l60 has `ānantaryamārgaḥ` in the Mvy/gloss context `"Weg ohne Hindernisse"`. |
| `Aryaratnakäta -> Āryaratnakūṭa` | promote | WtS 35-51 p901 l22 is the title/proper-name context `Āryaratnakūṭa`, near Avataṃsaka and Samājaratna. |
| `śinaväsika -> Śāṇavāsika` | promote | WtS 9-m p18 l49 names the elder `Śāṇavāsika` from Śrāvastī. |
| `śrijhäna -> śrījñāna` | promote | WtS 1-34 p23 l33 is the bibliographic name `Dīpaṃkaraśrījñāna`. |
| `śosa-räpasya -> śoṣa-rūpasya` | promote | WtS 1-34 p175 l48 has the Sanskrit phrase `śoṣa-rūpasya maraṇasya`. |
| `jnaurasab -> jinaurasaḥ` | reject/defer | WtS 1-34 p1007 l104 source appears to support `yumrasab`, not `jinaurasaḥ`. |
| `ucchanganäam -> ucchanganāam` | defer | WtS 35-51 p680 l20 needs fuller source/language adjudication; proposed target is still under-normalized. |
| `Käsy/Käśy -> Kāśy` | defer | Citation abbreviation/source-policy case, not an OCR Sanskrit normalisation. |
| `VisT -> VisṬ` | defer | Siglum/source-policy case. It was not promoted. |

## Promoted Overrides

| from_token | to_token | evidence_tag | example_ref |
| --- | --- | --- | --- |
| `dnantaryamärgab` | `ānantaryamārgaḥ` | `residual_visarga_term_normalization` | `wts_8_b:55:60` |
| `Aryaratnakäta` | `Āryaratnakūṭa` | `residual_sanskrit_damage_family` | `wts_35_51:901:22` |
| `śinaväsika` | `Śāṇavāsika` | `residual_sanskrit_damage_family` | `wts_9_m:18:49` |
| `śrijhäna` | `śrījñāna` | `residual_sanskrit_damage_family` | `wts_1_34:23:33` |
| `śosa-räpasya` | `śoṣa-rūpasya` | `residual_sanskrit_damage_family` | `wts_1_34:175:48` |

## Corrected-Text Diffs

| volume | page | line | before | after |
| --- | ---: | ---: | --- | --- |
| WtS 1-34 | 23 | 33 | `śrijhäna). 1. Teil: Einführung, Inhaltsverzeichnis, Namensglossar. 2. Teil: Textmaterialien.` | `śrījñāna). 1. Teil: Einführung, Inhaltsverzeichnis, Namensglossar. 2. Teil: Textmaterialien.` |
| WtS 1-34 | 175 | 48 | `Austrocknung (śosa-räpasya maranasya)"` | `Austrocknung (śoṣa-rūpasya maranasya)"` |
| WtS 35-51 | 901 | 22 | `Aryaratnakäta sind zusammengerechnet 49,` | `Āryaratnakūṭa sind zusammengerechnet 49,` |
| WtS 8-b | 55 | 60 | `= .dnantaryamärgab "Weg ohne Hindernisse"` | `= .ānantaryamārgaḥ "Weg ohne Hindernisse"` |
| WtS 9-m | 18 | 49 | `dha luden den edlen śinaväsika aus Śrāvastī` | `dha luden den edlen Śāṇavāsika aus Śrāvastī` |

## QA Deltas

| output | baseline | new | delta |
| --- | ---: | ---: | ---: |
| `all_watchdog_rows.tsv` | 285 | 285 | 0 |
| `live_validator_only_residue.tsv` | 1 | 1 | 0 |
| `live_policy_or_false_positive.tsv` | 4 | 4 | 0 |
| `google_sanskrit_candidate_readings.tsv` | 39 | 39 | 0 |
| `all_sanskrit_review_suggestions.tsv` | 9 | 4 | -5 |
| `possible_missed_google_readings.tsv` | 0 | 0 | 0 |
| `residual_sanskrit_damage_candidates.tsv` | 29,830 | 29,825 | -5 |
| `residual_sanskrit_damage_families.tsv` | 5,711 | 5,706 | -5 |
| `residual_sanskrit_damage_top_candidates.tsv` | 250 | 250 | 0 |
| `residual_sanskrit_promotable_candidates.tsv` | 7 | 2 | -5 |

The remaining promotable-candidate rows are `jnaurasab` and `ucchanganäam`;
both remain deferred after source review.

Sanskrit change counts:

| volume | baseline | new | delta |
| --- | ---: | ---: | ---: |
| WtS 1-34 | 304 | 306 | +2 |
| WtS 35-51 | 151 | 152 | +1 |
| WtS 8-b | 53 | 54 | +1 |
| WtS 9-m | 54 | 55 | +1 |
| Total | 562 | 567 | +5 |

Every postprocess volume reported `google_vision_rewrites=0`.

## Checksums

| file | baseline SHA-256 | new SHA-256 |
| --- | --- | --- |
| `WtS_1-34_release_candidate.txt` | `5a78587e83650659da898b6f3650e0b430a86b0913fed537d0d4eb833d536a0d` | `59c27aa4ac6148635feab0bb1f294b8e9f29af933894ca25503f0ffe951ee65b` |
| `WtS_35-51_release_candidate.txt` | `122db1c160cecd12b4d0180f9da1f8dc5aa0fbe201154c843a726e4f99000e12` | `141fb95430bde94f0ffcf2a1a8a77bab9c73c4741bb51d3544de990610f02fe4` |
| `WtS_8-b_release_candidate.txt` | `fe8824485396840ad4b0bf659652c1ac3ed1f11f202560793c454d18c0c892ab` | `3436d0bb9e4bd0aa29ee4e9fbbc11794e8d67cc593903656e2ca46112c55df16` |
| `WtS_9-m_release_candidate.txt` | `cc8e9a861257d5d39e230809c49b9dd645a526c690ace090a96803fb62826591` | `03aa8df8c135de3b798a06a98d8d7b12a75407a981ee4b9f020eab83f7c01dcb` |

## Verification

Commands run:

```bash
python3 -m py_compile scripts/generate_production_qa_report.py scripts/postprocess_entry_map.py
python3 -m pytest tests/test_postprocess_regressions.py
python3 scripts/generate_production_qa_report.py --output-dir work/production_release_candidate_residual_sanskrit_cleanup_20260529T100325Z
python3 scripts/generate_production_qa_report.py --output-dir work/production_release_candidate_residual_sanskrit_promotable_batch_20260531T180412Z
```

Results:

- `py_compile` passed.
- `tests/test_postprocess_regressions.py` passed: 117 tests.
- Production QA report regenerated successfully for both the baseline and new output directories.
