# Tibetan Third Cleanup Tranche

Date: 2026-06-21

This note records the third Tibetan cleanup tranche for WtS 8-b and WtS 9-m. The tranche follows the residual triage report and promotes exact reviewed Tibetan rows rather than adding broad OCR correction rules.

Google Vision gates were not loosened. The new rows are exact page/line/token overrides with named review reasons. No generic `I -> l`, `ń -> ṅ`, `n -> ñ`, `$ -> ś`, or siglum-wide rule was added.

## Inputs and Outputs

- baseline output root: `work/tibetan_second_cleanup_tranche_20260621T180745Z`
- new output root: `work/tibetan_third_cleanup_tranche_20260621T191118Z`
- WtS 8-b output: `work/tibetan_third_cleanup_tranche_20260621T191118Z/wts_8_b`
- WtS 9-m output: `work/tibetan_third_cleanup_tranche_20260621T191118Z/wts_9_m`
- residual triage TSV: `work/tibetan_third_cleanup_tranche_20260621T191118Z/tibetan_residual_triage.tsv`
- reviewed override data: `data/reviewed_tibetan_exact_overrides.tsv`

## Promoted Exact Rows

279 reviewed exact rows were added to `data/reviewed_tibetan_exact_overrides.tsv`.

| Review reason | Rows added | Notes |
| --- | ---: | --- |
| `reviewed_tibetan_exact_initial_i_l_family` | 233 | Exact reviewed initial-I/l-family repairs such as `Ita -> lta`, `Iha -> lha`, `Ina -> lṅa`, `Idan -> ldan`, `Ihan -> lhan`, `Ihun -> lhun`, and related compounds. |
| `reviewed_tibetan_exact_google_tibetan_candidate` | 24 | Exact Google-supported Tibetan candidate rows promoted after local-context review, for example `Zabs -> źabs`, `Zes -> źes`, `Zig -> źig`, `kyan -> kyaṅ`, `run -> ruṅ`, and `Ses -> śes`. |
| `reviewed_tibetan_exact_residual_ng` | 22 | Exact residual nasal/final-ng repairs such as `dań -> daṅ`, `nań -> naṅ`, `bźeńs -> bźeṅs`, and `sñiń -> sñiṅ`. |

The initial-I/l rows are intentionally exact reviewed rows, not a source-independent rule. They make the reviewed decisions explicit and reproducible. Some of these forms were already corrected by existing guarded Google/adoption logic in the previous run, so the visible corrected-text delta is smaller than the number of newly recorded reviewed rows.

## Production Counts

| Volume | Alternate-witness adoptions | Alternate-witness unresolved | Reviewed Tibetan exact changes | Sanskrit changes | Sanskrit review suggestions | Watchdog rows | Review queue rows | Bucket promote rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| WtS 8-b before | 3 | 900 | 48 | 47 | 1 | 31 | 3 | 0 |
| WtS 8-b after | 3 | 900 | 63 | 47 | 1 | 31 | 3 | 0 |
| WtS 9-m before | 842 | 1134 | 110 | 41 | 1 | 16 | 3 | 0 |
| WtS 9-m after | 842 | 1134 | 139 | 41 | 1 | 16 | 3 | 0 |

Bucket reports remained held for review:

- WtS 8-b: 131 unresolved bucket pairs, 0 promote, 131 hold
- WtS 9-m: 39 unresolved bucket pairs, 0 promote, 39 hold

## Corrected Text Effect

The tranche produced 40 corrected-text line diffs:

- WtS 8-b: 15 line diffs
- WtS 9-m: 25 line diffs

Representative WtS 8-b changes:

| Line | Before | After |
| ---: | --- | --- |
| 37 | `pa Losang Panglung (Byams-pa Blo-bzan sPan-lun) Abschied genommen. Am 19.` | `pa Losang Panglung (Byams-pa Blo-bzaṅ sPan-lun) Abschied genommen. Am 19.` |
| 5172 | `nań der ~ gźon nu Zig OJtshan ste byun nas` | `naṅ der ~ gźon nu Zig OJtshan ste byun nas` |
| 11534 | `khri phrag ñi su dań / ~i ri la bar snar las` | `khri phrag ñi su daṅ / ~i ri la bar snar las` |
| 23171 | `(brDa, Dagy); ~" gtam = ńag 'khyal gtam Lex. ~ pa = breg pa pos ~ bZin pa'am gcod` | `(brDa, Dagy); ~" gtam = ṅag 'khyal gtam Lex. ~ pa = breg pa pos ~ bZin pa'am gcod` |
| 38196 | `du yan d ños rtags dan mtshan ma dagkyań ~` | `du yan d ños rtags dan mtshan ma dagkyaṅ ~` |

Representative WtS 9-m changes:

| Line | Before | After |
| ---: | --- | --- |
| 1026 | `lteba'i dkyil du bu ༡// {$ } srog thag dań —" sñiñ` | `lteba'i dkyil du bu ༡// {$ } srog thag daṅ —" sñiñ` |
| 4161 | `146b4); khyod kyi Zabs rdul lhun ba yis /` | `146b4); khyod kyi źabs rdul lhun ba yis /` |
| 16404 | `na bźngs "was seinen Aufenthalt angeht, so` | `na bźugs "was seinen Aufenthalt angeht, so` |
| 19328 | `tha 176b1); srion 'jug yod dam — kyan run` | `tha 176b1); srion 'jug yod dam — kyaṅ ruṅ` |
| 19335 | `Ses rnam par Ses pa rdzas $// yod dam ~ "gibt` | `śes rnam par Ses pa rdzas $// yod dam ~ "gibt` |
| 19349 | `Zib cha Zu rgyu yod — cha ma rtogs Zes "ob` | `źib cha źu rgyu yod — cha ma rtogs źes "ob` |
| 30301 | `giun don ses / las rnams mthon Zin gtsari ba` | `giun don ses / las rnams mthon źiṅ gtsaṅ ba` |

All changed lines are explained by one of the named reviewed exact families. The remaining line noise visible in some examples was not touched because this tranche only promotes exact reviewed tokens.

## Diagnostic Deltas

| Diagnostic queue | WtS 8-b before | WtS 8-b after | WtS 9-m before | WtS 9-m after |
| --- | ---: | ---: | ---: | ---: |
| `tibetan_variant_families.tsv` | 44 | 35 | 95 | 88 |
| `tibetan_orthography_damage_candidates.tsv` | 172 | 158 | 132 | 124 |
| `tibetan_google_candidate_readings.tsv` | 12 | 12 | 90 | 90 |
| `tibetan_google_adoption_patterns.tsv` | 3 | 3 | 239 | 239 |
| `sigla_variant_candidates.tsv` | 75 | 75 | 119 | 119 |
| `residual_sanskrit_low_confidence_candidates.tsv` | 228 | 228 | 223 | 223 |

The residual triage report changed from 374 to 361 family groups:

| Recommended action | Before | After |
| --- | ---: | ---: |
| sample further | 278 | 265 |
| siglum policy review | 78 | 78 |
| ignore | 16 | 16 |
| source-image review | 1 | 1 |
| already reviewed | 1 | 1 |

The largest residual groups still include existing Google-adoption patterns. Those rows are not automatically uncorrected residue: they remain visible in the diagnostic report because the report includes adoption-pattern inventories as well as candidate inventories.

## Deferrals

The following families remain out of this cleanup batch:

- broad `$ -> ś` residue, because it mixes Tibetan, Sanskrit, and siglum contexts;
- `la'añń` and similar stacked nasal-looking rows, pending source-image review;
- broad raw `ń -> ṅ`, `n -> ñ`, and initial `I -> l` rules;
- symbol-to-Tibetan rows such as `077`, `77`, and `2`;
- Sanskrit or siglum-policy cases such as `Käsy`, `graris`, and non-reviewed bibliographic abbreviations;
- unresolved noisy partials such as `rkani`, `rria`, `zani`, `rim`, `Nlams`, `nina`, and `giun`.

## Checksums

```text
f824f7f0ea4fe41258fed810fd4a6976e602abf572973208cb521224b4fe5fe7  work/tibetan_third_cleanup_tranche_20260621T191118Z/wts_8_b/wts_8_b_corrected_full.txt
3b7f92f4c6677cd9f67603627d58de03db626dacac0adb71d836ab3081f89635  work/tibetan_third_cleanup_tranche_20260621T191118Z/wts_8_b/wts_8_b_changes.tsv
f1aff5e4bb29b980eb3ece1644fbb86f7d1188aed20ed0bf42515a295bc48cfd  work/tibetan_third_cleanup_tranche_20260621T191118Z/wts_8_b/wts_8_b_watchdog_flags.tsv
9b9108034d30df29cdbf5eecdfb76ebe112cb09882f388b55052e961767bdd6a  work/tibetan_third_cleanup_tranche_20260621T191118Z/wts_8_b/wts_8_b_review_queue.tsv
40039c5d23100b0c3bde0bb4c276b32c527c4589ae198d83ad2b56952f162ac2  work/tibetan_third_cleanup_tranche_20260621T191118Z/wts_9_m/wts_9_m_corrected_full.txt
5d540f86f8cb1aa32fb04b1c3c61d8ab9e4c13d636e56684cfe5968212c3d28a  work/tibetan_third_cleanup_tranche_20260621T191118Z/wts_9_m/wts_9_m_changes.tsv
f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c  work/tibetan_third_cleanup_tranche_20260621T191118Z/wts_9_m/wts_9_m_watchdog_flags.tsv
502a19e723b2e536cc6b25accd65731deac06c256b696538993783d696411f2a  work/tibetan_third_cleanup_tranche_20260621T191118Z/wts_9_m/wts_9_m_review_queue.tsv
```

## Verification

Verification commands:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/build_tibetan_residual_triage_report.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result: compile check passed; regression tests reported `117 passed, 6 subtests passed in 0.91s`.
