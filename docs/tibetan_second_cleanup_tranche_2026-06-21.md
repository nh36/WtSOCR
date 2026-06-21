# Tibetan Second Cleanup Tranche Decision

Date: 2026-06-21

This note records the follow-up pass after the reviewed Tibetan and siglum cleanup commit. The pass regenerated WtS 8-b and WtS 9-m postprocess outputs, rebuilt the Tibetan cleanup diagnostics, and produced a ranked residual triage report. No new OCR correction heuristics were added, and no additional exact override batch was promoted.

## Inputs and Outputs

- output root: `work/tibetan_second_cleanup_tranche_20260621T180745Z`
- WtS 8-b postprocess output: `work/tibetan_second_cleanup_tranche_20260621T180745Z/wts_8_b`
- WtS 9-m postprocess output: `work/tibetan_second_cleanup_tranche_20260621T180745Z/wts_9_m`
- residual triage report: `docs/tibetan_cleanup_residual_triage_2026-06-21.md`
- residual triage TSV: `work/tibetan_second_cleanup_tranche_20260621T180745Z/tibetan_residual_triage.tsv`

## Postprocess Counts

| Volume | Alternate-witness adoptions | Alternate-witness unresolved | Watchdog rows | Review queue rows | Bucket promote rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| WtS 8-b | 3 | 900 | 31 | 3 | 0 |
| WtS 9-m | 842 | 1134 | 16 | 3 | 0 |

Bucket reports held all unresolved pairs for review:

- WtS 8-b: 131 unresolved bucket pairs, 0 promote, 131 hold
- WtS 9-m: 39 unresolved bucket pairs, 0 promote, 39 hold

## Residual Triage Result

The combined residual report contains 374 family groups. The recommended-action distribution is:

| Recommended action | Family groups |
| --- | ---: |
| sample further | 278 |
| siglum policy review | 78 |
| ignore | 16 |
| source-image review | 1 |
| already reviewed | 1 |

No family was marked as ready for immediate exact-row promotion. The high-volume Tibetan families `dan -> daṅ`, `Ita -> lta`, `Iha -> lha`, `Ina -> lṅa`, and `Idan -> ldan` are already handled through the existing Google token gates in the current run. Promoting them as source-independent reviewed overrides would not improve corrected text and would reduce the audit boundary.

The largest remaining non-Google-gated residue is still policy-sensitive:

- `$ -> ś` mixes Tibetan, Sanskrit, and siglum contexts and is not a safe generic correction.
- `Bu-$z`/`Bu-Sz`, `G$-H`/`Gs-H`/`Gś-H`, and `Y$`/`Ys`/`Yś` stay under siglum registry or bibliography policy, not a broad OCR rule.
- `Lsdz-K`, `L$dz-K`, and related forms remain bibliographic-policy review items.
- `la'añń` and similar nasal-damage-looking rows remain source-image review cases.

## Decision

No second medium correction tranche was promoted from this report. This is an intentional stop point: the diagnostics are now ranked and reviewable, but the next substantive correction work needs either source-image review or a siglum-policy decision rather than another automated cleanup family.

The cleanup safeguards remain unchanged:

- Google Vision remains an alternate witness only.
- No broad global rules were added.
- Validator-only or noisy residual rows were not used as correction evidence.
- Residual Sanskrit low-confidence candidates remain out of scope for this Tibetan tranche.

## Checksums

```text
0536b4c0715da385b197ce44ca834ae2556a1991193297e7585cd7cf0206d50c  work/tibetan_second_cleanup_tranche_20260621T180745Z/wts_8_b/wts_8_b_corrected_full.txt
e6aa34db5a1946469e19739239e9ac21b4e2644506728b48d7bceb436ba97f6e  work/tibetan_second_cleanup_tranche_20260621T180745Z/wts_8_b/wts_8_b_changes.tsv
f1aff5e4bb29b980eb3ece1644fbb86f7d1188aed20ed0bf42515a295bc48cfd  work/tibetan_second_cleanup_tranche_20260621T180745Z/wts_8_b/wts_8_b_watchdog_flags.tsv
9b9108034d30df29cdbf5eecdfb76ebe112cb09882f388b55052e961767bdd6a  work/tibetan_second_cleanup_tranche_20260621T180745Z/wts_8_b/wts_8_b_review_queue.tsv
5ebddeb32ac8a9c3ad24ce67e5aef7850f0d496c31af5fb0e24ea2ff5507ab1b  work/tibetan_second_cleanup_tranche_20260621T180745Z/wts_9_m/wts_9_m_corrected_full.txt
9102040c6b0bc071a7837f4367b0e87ee40e05729796caad39582d394176fb4e  work/tibetan_second_cleanup_tranche_20260621T180745Z/wts_9_m/wts_9_m_changes.tsv
f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c  work/tibetan_second_cleanup_tranche_20260621T180745Z/wts_9_m/wts_9_m_watchdog_flags.tsv
502a19e723b2e536cc6b25accd65731deac06c256b696538993783d696411f2a  work/tibetan_second_cleanup_tranche_20260621T180745Z/wts_9_m/wts_9_m_review_queue.tsv
79bb0baadcf93fe3b57314cd3c09c9bc30a5dd6ac1c0a93ef3485b4ab5020e47  work/tibetan_second_cleanup_tranche_20260621T180745Z/tibetan_residual_triage.tsv
```

## Verification

Verification commands:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/build_tibetan_residual_triage_report.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result: compile check passed; regression tests reported `113 passed, 6 subtests passed in 0.79s`.
