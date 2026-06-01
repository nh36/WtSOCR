# Residual Sanskrit Promotable Batch Postcheck (2026-05-31)

Previous output directory:
`work/production_release_candidate_residual_sanskrit_promotable_batch_20260531T180412Z`

Postcheck output directory:
`work/production_release_candidate_residual_sanskrit_postcheck_20260531T190000Z`

## Independent Source Check

The five promoted residual Sanskrit repairs were rechecked against the source PDF page images and the corrected output. All five remain justified as exact, source-supported repairs. Punctuation, spacing, and surrounding tokens are intact.

| Ref | Promotion | Source/output check | Assessment |
| --- | --- | --- | --- |
| WtS 8-b p55 l60 | `dnantaryamärgab` -> `ānantaryamārgaḥ` | Source supports `ānantaryamārgaḥ`; corrected line keeps `= .ānantaryamārgaḥ "Weg ohne Hindernisse"` with spacing and punctuation intact. | clearly good |
| WtS 35-51 p901 l22 | `Aryaratnakäta` -> `Āryaratnakūṭa` | Source supports `Āryaratnakūṭa sind zusammengerechnet 49,`; corrected output matches the source phrase. | clearly good |
| WtS 9-m p18 l49 | `śinaväsika` -> `Śāṇavāsika` | Source supports `Śāṇavāsika`; corrected line keeps `dha luden den edlen Śāṇavāsika aus Śrāvastī`. | clearly good |
| WtS 1-34 p23 l33 | `śrijhäna` -> `śrījñāna` | Source supports bibliographic `Dīpaṃkara-śrījñāna`; corrected output keeps the bibliographic sentence structure intact. | clearly good |
| WtS 1-34 p175 l48 | `śosa-räpasya` -> `śoṣa-rūpasya` | Source supports `śoṣa-rūpasya maraṇasya`; corrected output now keeps the full parenthetical Sanskrit phrase intact. | clearly good |

Each reviewed override replacement appears in the intended line only. No additional exact-token occurrence was changed without source support.

## Additional Local Correction

The WtS 1-34 p175 l48 source phrase is `śoṣa-rūpasya maraṇasya`. The previous corrected text still had:

```text
Austrocknung (śoṣa-rūpasya maranasya)"
```

All live occurrences of `maranasya` in the corrected output were inspected. The only live occurrence was this same WtS 1-34 p175 l48 line. I promoted a local, source-checked override:

```text
maranasya -> maraṇasya
```

The new corrected-text diff is exactly one final-text line:

```diff
-Austrocknung (śoṣa-rūpasya maranasya)"
+Austrocknung (śoṣa-rūpasya maraṇasya)"
```

The override uses evidence tag `source_checked_local_sanskrit_phrase` and example ref `wts_1_34:175:48`. It is location-gated to the reviewed page and line; tests cover both the positive reviewed line and a negative same-token occurrence on an unreviewed line.

## Deferred Queue Decisions

The residual promotable queue now has explicit source-review status fields. Source-reviewed rejected/deferred rows are no longer emitted as promotable candidates.

| Token | Prior proposed target | Decision | Reason |
| --- | --- | --- | --- |
| `jnaurasab` | `jinaurasaḥ` | source-reviewed rejected | Source image supports a different reading, `yumrasab`, rather than `jinaurasaḥ`; do not promote as Sanskrit correction. |
| `ucchanganäam` | `ucchanganāam` | source-reviewed deferred | Source image points to a fuller uncertain phrase, likely `śatam ucchaṅgūnām bahulam nāmocyate`; the proposed target is under-normalized. |
| `VisT` | `VisṬ` | source-policy deferred | Short bibliographic siglum; citation policy/source decision, not Sanskrit normalization. |
| `Käsy` / `Käśy` | `Kāśy` | source-policy deferred | Short bibliographic/citation form; citation policy/source decision, not Sanskrit normalization. |

`residual_sanskrit_promotable_candidates.tsv` is now header-only.

## Current Counts

Rows below exclude TSV headers.

| Artifact | Rows |
| --- | ---: |
| `all_watchdog_rows.tsv` | 285 |
| `live_validator_only_residue.tsv` | 1 |
| `live_policy_or_false_positive.tsv` | 4 |
| `google_sanskrit_candidate_readings.tsv` | 39 |
| `all_sanskrit_review_suggestions.tsv` | 4 |
| `possible_missed_google_readings.tsv` | 0 |
| `residual_sanskrit_damage_families.tsv` | 5706 |
| `residual_sanskrit_damage_top_candidates.tsv` | 250 |
| `residual_sanskrit_damage_candidates.tsv` | 29825 |
| `residual_sanskrit_promotable_candidates.tsv` | 0 |

## Sanskrit Change Counts

| Volume | Sanskrit changes |
| --- | ---: |
| WtS 1-34 | 307 |
| WtS 35-51 | 152 |
| WtS 8-b | 54 |
| WtS 9-m | 55 |
| Total | 568 |

## Final Checksums

| File | SHA-256 |
| --- | --- |
| `WtS_1-34_release_candidate.txt` | `ebea9fcba4f0747213fdd66148a0ea01055d6a882082605f17fc74558989f2cd` |
| `WtS_35-51_release_candidate.txt` | `141fb95430bde94f0ffcf2a1a8a77bab9c73c4741bb51d3544de990610f02fe4` |
| `WtS_8-b_release_candidate.txt` | `3436d0bb9e4bd0aa29ee4e9fbbc11794e8d67cc593903656e2ca46112c55df16` |
| `WtS_9-m_release_candidate.txt` | `03aa8df8c135de3b798a06a98d8d7b12a75407a981ee4b9f020eab83f7c01dcb` |

Only WtS 1-34 changed relative to `work/production_release_candidate_residual_sanskrit_promotable_batch_20260531T180412Z`; WtS 35-51, WtS 8-b, and WtS 9-m are byte-identical.

## Verification

Commands run:

```sh
python3 -m py_compile scripts/generate_production_qa_report.py scripts/postprocess_entry_map.py
python3 -m pytest tests/test_postprocess_regressions.py
python3 scripts/generate_production_qa_report.py --output-dir work/production_release_candidate_residual_sanskrit_promotable_batch_20260531T180412Z
python3 scripts/generate_production_qa_report.py --output-dir work/production_release_candidate_residual_sanskrit_postcheck_20260531T190000Z
```

Results:

- `py_compile` passed.
- `tests/test_postprocess_regressions.py`: 119 passed.
- Required QA report regeneration completed.
- Postcheck QA report generation completed.

Google adoption gates were unchanged. Validator-only residue was not used as correction evidence. No broad Sanskrit character rule was added.

With the source-checked local `maranasya` repair applied and the source-reviewed deferred/rejected rows suppressed from the promotable queue, there are no remaining exact source-supported rows in `residual_sanskrit_promotable_candidates.tsv`. The next work should move to release-readiness documentation for the current release candidate, not another Sanskrit mining pass.
