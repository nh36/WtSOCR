# Tibetan Second Ambitious Cleanup - 2026-06-24

## Scope

This pass continues the WtS 8-b / WtS 9-m Tibetan cleanup after `docs/tibetan_ambitious_residual_cleanup_2026-06-22.md`.

Policy remained unchanged:

- base OCR remains authoritative;
- Google Vision is corroborating evidence only;
- no Google adoption gates were loosened;
- no broad character rules were added;
- every correction is an exact page-line-token reviewed override in `data/reviewed_tibetan_exact_overrides.tsv`;
- residual Sanskrit and validator-only residue were not used as correction evidence.

Baseline output:

`work/tibetan_ambitious_residual_cleanup_20260622T094238Z`

New output:

`work/tibetan_second_ambitious_cleanup_20260624T212313Z`

## Promoted Families

| Family | Rows | Rationale |
| --- | ---: | --- |
| `lna`, `lna'am`, `lna'i` -> `lṅa`, `lṅa'am`, `lṅa'i` | 8 | `lna` is impossible Tibetan in these contexts; the local contexts identify the numeral `lṅa`. |
| `drios` -> `dṅos` | 6 | Contexts are ordinary `dṅos` readings, including `dṅos grub`, `dṅos su`, and `dṅos byon`. Existing reviewed rows were not duplicated. |
| `gtsan`, `gtsani` -> `gtsaṅ` | 17 | Contexts include `mi gtsaṅ`, `dbus gtsaṅ`, `gtsaṅ ma`, and related Tibetan lexical contexts. |
| `snani`, `snari` -> `snaṅ` | 26 | Contexts include `rnam snaṅ`, `bar snaṅ`, `snaṅ ba`, and comparable Tibetan lexical phrases. |
| `sriar` -> `sṅar` | 1 | The promoted row is the clear phrase `spyan sṅar`; no broad `sriar` rule was added. |

Total: 58 exact reviewed token replacements.

Per-volume change counts:

| Family | WtS 8-b | WtS 9-m |
| --- | ---: | ---: |
| `reviewed_tibetan_exact_second_ambitious_lnga` | 1 | 7 |
| `reviewed_tibetan_exact_second_ambitious_dngos` | 0 | 6 |
| `reviewed_tibetan_exact_second_ambitious_gtsang` | 5 | 12 |
| `reviewed_tibetan_exact_second_ambitious_snang` | 9 | 17 |
| `reviewed_tibetan_exact_second_ambitious_sngar` | 1 | 0 |

## Corrected Text Diffs

WtS 8-b had 15 corrected lines changed, containing 16 token replacements. Representative examples:

| Line | Before | After |
| ---: | --- | --- |
| 1054 | `te — gtsan ma'i mchod sbyin "ein gomedha,` | `te — gtsaṅ ma'i mchod sbyin "ein gomedha,` |
| 1732 | `(MigTo 255,1); mgo gtsani — rdzon ba la /` | `(MigTo 255,1); mgo gtsaṅ — rdzon ba la /` |
| 1866 | `blan dor 'od kyi snani ba ches gsal ba'i / —` | `blan dor 'od kyi snaṅ ba ches gsal ba'i / —` |
| 2719 | `Lex. snari ba — (brDa); sna tsbogs pa'am dza` | `Lex. snaṅ ba — (brDa); sna tsbogs pa'am dza` |
| 3031 | `zen würde" (sBa 54,4); mi gtsani ba'i don der` | `zen würde" (sBa 54,4); mi gtsaṅ ba'i don der` |
| 3626 | `sran beu nas bco lna' — "zwischen zehn und` | `sran beu nas bco lṅa' — "zwischen zehn und` |
| 4452 | `བར་སྣང་ bar snani Kurzf. für bar gi snari ba.` | `བར་སྣང་ bar snaṅ Kurzf. für bar gi snaṅ ba.` |
| 4702 | `de bcom ldan 'das kyi spyan sriar ma phyin Lex. bar 'dum byed pa po "jemand, der eine` | `de bcom ldan 'das kyi spyan sṅar ma phyin Lex. bar 'dum byed pa po "jemand, der eine` |

WtS 9-m had 42 corrected lines changed. Representative examples:

| Line | Before | After |
| ---: | --- | --- |
| 184 | `rnam snani mdzad` | `rnam snaṅ mdzad` |
| 1798 | `dug lna'` | `dug lṅa'` |
| 2411 | `drios grub` | `dṅos grub` |
| 6089 | `gtsani ma'` | `gtsaṅ ma'` |
| 8574 | `—r snari` | `—r snaṅ` |
| 10476 | `— drios su bkug` | `— dṅos su bkug` |
| 10599 | `mi gtsan` | `mi gtsaṅ` |
| 29361 | `dmar gtsani` | `dmar gtsaṅ` |
| 30236 | `'jam dbyans drios byon` | `'jam dbyans dṅos byon` |

## Deferrals

- `wts_9_m 81:61 lna'imtha` remains deferred because the fused token has spacing/title uncertainty. It may belong to the `lṅa` family, but it was not promoted without resolving the local segmentation.
- `wts_8_b 73:38 sriar` remains deferred. The promoted `sriar -> sṅar` row is restricted to the clear `spyan sṅar` context.
- Generic nasal repairs, broad initial-I repairs, broad Google-pattern adoption, residual Sanskrit low-confidence rows, and non-reviewed siglum variants remain out of scope for this batch.

## Counts

| Metric | WtS 8-b before | WtS 8-b after | WtS 9-m before | WtS 9-m after |
| --- | ---: | ---: | ---: | ---: |
| Alternate-witness adoptions | 3 | 3 | 842 | 842 |
| Alternate-witness unresolved rows | 900 | 900 | 1134 | 1134 |
| Reviewed Tibetan exact changes | 71 | 87 | 164 | 206 |
| Changes TSV rows | 2542 | 2558 | 1775 | 1817 |
| Sanskrit review suggestions | 1 | 1 | 1 | 1 |
| Tier-B suggestions | 3 | 3 | 3 | 3 |
| Validator issues | 2344 | 2344 | 1554 | 1554 |
| Uncaptured Tibetan prefix lines | 1134 | 1134 | 1028 | 1028 |
| Watchdog rows | 31 | 31 | 16 | 16 |
| Review queue rows | 3 | 3 | 3 | 3 |
| Bucket unresolved pairs | 125 | 125 | 38 | 38 |
| Bucket promote rows | 0 | 0 | 0 | 0 |
| Bucket hold rows | 125 | 125 | 38 | 38 |

## Diagnostic Counts

| Diagnostic | WtS 8-b before | WtS 8-b after | WtS 9-m before | WtS 9-m after |
| --- | ---: | ---: | ---: | ---: |
| Tibetan variant families | 28 | 28 | 85 | 85 |
| Tibetan orthography candidates | 151 | 151 | 121 | 123 |
| Tibetan Google candidates | 12 | 12 | 90 | 90 |
| Tibetan Google adoption patterns | 3 | 3 | 239 | 239 |
| Sigla variant candidates | 75 | 75 | 119 | 119 |
| Residual Sanskrit low-confidence candidates | 228 | 228 | 223 | 224 |
| Combined residual triage rows | 351 | 351 | 351 | 351 |

The WtS 9-m broad diagnostic inventories rose slightly for orthography candidates and residual Sanskrit low-confidence candidates. These files are broad scanners rather than subtraction inventories; the guardrails stayed stable, and the combined residual triage row count did not increase.

## Checksums

```text
460f9519e991ebb845e91a936895cc931a7df95cacab4ffdffe9a9513d88ea57  work/tibetan_second_ambitious_cleanup_20260624T212313Z/wts_8_b/wts_8_b_corrected_full.txt
69ccbb5191c42c6569ecb6fc56d7c8f5a130b7f799e681f5422cf771694a315b  work/tibetan_second_ambitious_cleanup_20260624T212313Z/wts_8_b/wts_8_b_changes.tsv
f1aff5e4bb29b980eb3ece1644fbb86f7d1188aed20ed0bf42515a295bc48cfd  work/tibetan_second_ambitious_cleanup_20260624T212313Z/wts_8_b/wts_8_b_watchdog_flags.tsv
9b9108034d30df29cdbf5eecdfb76ebe112cb09882f388b55052e961767bdd6a  work/tibetan_second_ambitious_cleanup_20260624T212313Z/wts_8_b/wts_8_b_review_queue.tsv
72036ce2da011d3091cf90511067aa736dcfdb40c13789a51ee4a397d8279381  work/tibetan_second_ambitious_cleanup_20260624T212313Z/wts_9_m/wts_9_m_corrected_full.txt
92312632db2af44f52c5a47c93833d22f2ce3152c543e617ce22c90c8152baf9  work/tibetan_second_ambitious_cleanup_20260624T212313Z/wts_9_m/wts_9_m_changes.tsv
f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c  work/tibetan_second_ambitious_cleanup_20260624T212313Z/wts_9_m/wts_9_m_watchdog_flags.tsv
502a19e723b2e536cc6b25accd65731deac06c256b696538993783d696411f2a  work/tibetan_second_ambitious_cleanup_20260624T212313Z/wts_9_m/wts_9_m_review_queue.tsv
aaf51612761164eb46d7bc36567cf13d9d886eb80e309d3d3445deb374bbb9b4  work/tibetan_second_ambitious_cleanup_20260624T212313Z/tibetan_residual_triage.tsv
```

## Verification

Commands run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result:

```text
125 passed, 6 subtests passed in 1.32s
```
