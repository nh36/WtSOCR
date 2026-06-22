# Tibetan Residual Context Cleanup

Date: 2026-06-22

This note records a small exact Tibetan cleanup tranche following the third Tibetan cleanup pass. The goal was to resolve a few high-signal residual WtS 9-m rows by reviewing the base line, Google alternate witness line, and local Tibetan meaning/context.

No Google Vision adoption gates were loosened. No broad OCR rules were added: in particular, this tranche does not add generic `ń -> ṅ`, `n -> ñ`, `I -> l`, `snar -> sṅar`, `gtsan -> gtsaṅ`, or `$ -> ś` behavior. Every promoted row is an exact page/line/token override.

## Inputs and Outputs

- baseline output root: `work/tibetan_third_cleanup_tranche_20260621T191118Z`
- new output root: `work/tibetan_residual_context_cleanup_20260622T082855Z`
- WtS 8-b output: `work/tibetan_residual_context_cleanup_20260622T082855Z/wts_8_b`
- WtS 9-m output: `work/tibetan_residual_context_cleanup_20260622T082855Z/wts_9_m`
- residual triage TSV: `work/tibetan_residual_context_cleanup_20260622T082855Z/tibetan_residual_triage.tsv`
- reviewed override data: `data/reviewed_tibetan_exact_overrides.tsv`

## Promoted Exact Rows

Ten reviewed exact WtS 9-m rows were added under `reviewed_tibetan_exact_residual_context_google`.

| Volume | Page | Line | Token | From | To | Review note |
| --- | ---: | ---: | ---: | --- | --- | --- |
| WtS 9-m | 229 | 70 | 7 | `rkani` | `rkaṅ` | Google alternate reads `rkaṅ`; local Tibetan phrase confirms foot/leg context. |
| WtS 9-m | 229 | 87 | 7 | `rkani` | `rkaṅ` | Google alternate reads `rkaṅ`; paired with `rṅa` in the same phrase. |
| WtS 9-m | 229 | 87 | 9 | `rria` | `rṅa` | Google alternate and local context support `rkaṅ khal rṅa`. |
| WtS 9-m | 232 | 21 | 6 | `zani` | `zaṅ` | Google alternate supports `zaṅ`; adjacent `ziri` remains deferred as too noisy. |
| WtS 9-m | 233 | 69 | 6 | `sriar` | `sṅar` | Google has `snar`, but local meaning supports `sṅar gyi ñams`; promoted to `sṅar`, not plain `snar`. |
| WtS 9-m | 233 | 69 | 7 | `gi` | `gyi` | Same reviewed phrase: `sṅar gyi ñams`. |
| WtS 9-m | 233 | 69 | 8 | `Nlams` | `ñams` | Same reviewed phrase: `sṅar gyi ñams`. |
| WtS 9-m | 285 | 67 | 1 | `gtsani` | `gtsaṅ` | Google has `gtsan`; nearby context identifies gTsaṅ/mNga' ris region, so the final is normalized to `ṅ`. |
| WtS 9-m | 285 | 67 | 3 | `nina` | `mña` | Token-level replacement leaves the following apostrophe in place, producing `mña'`. |
| WtS 9-m | 362 | 53 | 1 | `giun` | `gźun` | Google alternate and local phrase support `gźun don`. |

The `sriar/snar` and `gtsani/gtsan` decisions intentionally follow Tibetan context rather than mechanically copying the Google alternate. They are still exact local overrides, not new families.

## Corrected Text Effect

WtS 8-b corrected text is unchanged. WtS 9-m has six corrected-text line diffs:

| Page/line | Before | After |
| --- | --- | --- |
| 229:70 | `140,10); sa 'bol steṅ na rkani rjes — na 'chi` | `140,10); sa 'bol steṅ na rkaṅ rjes — na 'chi` |
| 229:87 | `gibt keine Spur" (gZer 652,1); rkani khal rria` | `gibt keine Spur" (gZer 652,1); rkaṅ khal rṅa` |
| 232:21 | `heimlichen habe" (Mil 27,8); zani ziri gi 'bul` | `heimlichen habe" (Mil 27,8); zaṅ ziri gi 'bul` |
| 233:69 | `kurrenzlos ist" (Mil 95,33); sriar gi Nlams` | `kurrenzlos ist" (Mil 95,33); sṅar gyi ñams` |
| 285:67 | `gtsani khul nina' ris dan bcas kyi — bskul` | `gtsaṅ khul mña' ris dan bcas kyi — bskul` |
| 362:53 | `giun don ses / las rnams mthon źiṅ gtsaṅ ba` | `gźun don ses / las rnams mthon źiṅ gtsaṅ ba` |

The p362:53 line already had earlier exact reviewed corrections for `Zin -> źiṅ` and `gtsari -> gtsaṅ`; this tranche adds only `giun -> gźun` there.

## Production Counts

| Volume | State | Alternate-witness adoptions | Alternate-witness unresolved | Reviewed Tibetan exact changes | Sanskrit changes | Sanskrit review suggestions | Watchdog rows | Review queue rows | Bucket promote rows | Bucket hold rows |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| WtS 8-b | before | 3 | 900 | 63 | 47 | 1 | 31 | 3 | 0 | 131 |
| WtS 8-b | after | 3 | 900 | 63 | 47 | 1 | 31 | 3 | 0 | 131 |
| WtS 9-m | before | 842 | 1134 | 139 | 41 | 1 | 16 | 3 | 0 | 39 |
| WtS 9-m | after | 842 | 1134 | 149 | 41 | 1 | 16 | 3 | 0 | 39 |

The only production-count change is the expected increase of ten reviewed Tibetan exact changes in WtS 9-m. Alternate-witness adoption/unresolved counts, watchdog rows, review queues, and bucket promote rows are stable.

The combined residual triage report has 361 grouped rows after this tranche.

## Deferrals

The following remain out of scope for this tranche:

- `ziri` on WtS 9-m p232 l21, because the Google alternate is noisy and the intended target was not clear enough for a local exact override;
- broad `snar/sṅar` or `gtsan/gtsaṅ` treatment outside the reviewed rows above;
- `la'añń` and similar nasal-damage-looking rows pending source/context review;
- generic `$ -> ś` outside already reviewed sigla cases;
- residual Sanskrit low-confidence candidates and Sanskrit backstop diagnostics.

## Checksums

```text
f824f7f0ea4fe41258fed810fd4a6976e602abf572973208cb521224b4fe5fe7  work/tibetan_residual_context_cleanup_20260622T082855Z/wts_8_b/wts_8_b_corrected_full.txt
5fd16dab8fc8a32a4f5468b852cad0d171947f2ae44df64aa178a288245388f5  work/tibetan_residual_context_cleanup_20260622T082855Z/wts_9_m/wts_9_m_corrected_full.txt
3b7f92f4c6677cd9f67603627d58de03db626dacac0adb71d836ab3081f89635  work/tibetan_residual_context_cleanup_20260622T082855Z/wts_8_b/wts_8_b_changes.tsv
e22ef30ec2f375aa06bb838a956d51e8fd11ffda3053753789f675465375cbd1  work/tibetan_residual_context_cleanup_20260622T082855Z/wts_9_m/wts_9_m_changes.tsv
f1aff5e4bb29b980eb3ece1644fbb86f7d1188aed20ed0bf42515a295bc48cfd  work/tibetan_residual_context_cleanup_20260622T082855Z/wts_8_b/wts_8_b_watchdog_flags.tsv
f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c  work/tibetan_residual_context_cleanup_20260622T082855Z/wts_9_m/wts_9_m_watchdog_flags.tsv
9b9108034d30df29cdbf5eecdfb76ebe112cb09882f388b55052e961767bdd6a  work/tibetan_residual_context_cleanup_20260622T082855Z/wts_8_b/wts_8_b_review_queue.tsv
502a19e723b2e536cc6b25accd65731deac06c256b696538993783d696411f2a  work/tibetan_residual_context_cleanup_20260622T082855Z/wts_9_m/wts_9_m_review_queue.tsv
cf620cee0f453ef625b0a6c5f249626c4494c553b20088ef296dfe1f22d80b02  work/tibetan_residual_context_cleanup_20260622T082855Z/tibetan_cleanup_diagnostics_wts_8_b/tibetan_variant_families.tsv
41a958b3bafb49a078cbbb2aa766b33c264f2c80e7fca3d9a64bb251ad60506f  work/tibetan_residual_context_cleanup_20260622T082855Z/tibetan_cleanup_diagnostics_wts_9_m/tibetan_variant_families.tsv
97dc954174c4bb0c35cad320090aa63da69e9042a26afe8b70ef8999513d5659  work/tibetan_residual_context_cleanup_20260622T082855Z/tibetan_residual_triage.tsv
```

## Verification

Verification commands:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/build_tibetan_residual_triage_report.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result: compile check passed; regression tests reported `119 passed, 6 subtests passed in 0.97s`.
