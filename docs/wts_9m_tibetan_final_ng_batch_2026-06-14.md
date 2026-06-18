# WtS 9-m Tibetan Final-Ng Batch, 2026-06-14

## Scope

This pass promotes a reviewed exact WtS 9-m Tibetan final-ng batch and keeps the earlier WtS 8-b exact reviewed rows. It does not add a broad `ñ -> ṅ` rule and does not change Google Vision adoption gates.

The reviewed exact overrides now live in `data/reviewed_tibetan_exact_overrides.tsv` and are loaded by `scripts/postprocess_entry_map.py`. Each promotion is keyed by exact volume, page, line, token index, and source token.

## Inputs And Outputs

Line-anchor inputs:

- `work/line_anchor_new_volumes_20260605T154602Z/WtS_8-b/WtS 8-b_lineanchored_merged_full.txt`
- `work/line_anchor_new_volumes_20260605T154602Z/WtS_9-m/WtS 9-m_lineanchored_merged_full.txt`

Alternate witnesses:

- `pdfs/WtS 8-b.vision.txt`
- `pdfs/WtS 9-m.vision.txt`

Output root:

- `work/postprocess_wts9_final_ng_batch_20260614T065617Z`

## Promotion Summary

WtS 8-b was unchanged from the previous exact cleanup bundle. WtS 9-m gained 87 reviewed exact token repairs across 86 corrected-text lines. Page 66 line 24 has two repaired tokens.

The WtS 9-m changes are exact reviewed final-ng repairs, plus the already-reviewed local `dnos -> dṅos` and `gNa-khri -> gÑa-khri` rows retained from the previous exact cleanup. The bad direction `dnos -> dños` remains rejected.

Representative WtS 9-m examples:

- `mi sna tshañ -> mi sna tshaṅ`
- `ri khañ-dmar -> ri khaṅ-dmar`
- `Myañ Mañ-po-rje -> Myaṅ Maṅ-po-rje`
- `ba lañ dkar -> ba laṅ dkar`
- `dBus-gtsañ -> dBus-gtsaṅ`
- `gNa-khri -> gÑa-khri`
- `dnos -> dṅos`

Deferred, rejected, or handled outside this Tibetan batch:

- `Vi$T -> ViśT` remains a short bibliography/siglum/citation-policy case, not a Tibetan correction. Later source-list review resolves `ViśT` as the canonical siglum for `Viśeṣastavatīkā`.
- `la'añń -> la'aṅń` remains deferred.
- `dnos -> dños` is rejected; the reviewed correction is `dnos -> dṅos`.

## Count Checks

Compared with `work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z`:

| Volume | Metric | Before | After |
| --- | ---: | ---: | ---: |
| WtS 8-b | alternate-witness adoptions | 3 | 3 |
| WtS 8-b | alternate-witness unresolved | 900 | 900 |
| WtS 8-b | Tier A changes | 2399 | 2399 |
| WtS 8-b | reviewed Tibetan exact changes | 16 | 16 |
| WtS 8-b | Sanskrit changes | 25 | 25 |
| WtS 8-b | watchdog rows | 31 | 31 |
| WtS 9-m | alternate-witness adoptions | 853 | 853 |
| WtS 9-m | alternate-witness unresolved | 1135 | 1135 |
| WtS 9-m | Tier A changes | 1562 | 1649 |
| WtS 9-m | reviewed Tibetan exact changes | 6 | 93 |
| WtS 9-m | Sanskrit changes | 28 | 28 |
| WtS 9-m | Sanskrit review suggestions | 14 | 14 |
| WtS 9-m | review queue rows | 16 | 16 |
| WtS 9-m | watchdog rows | 16 | 16 |
| WtS 9-m | unresolved bucket pairs | 106 | 41 |
| WtS 9-m | validator issues | 1642 | 1555 |

The alternate-witness adoption and unresolved counts did not change. The watchdog count did not increase. The WtS 9-m validator issue count fell because reviewed final-ng rows are no longer left as live validator residue.

## Bucket Report Notes

The regenerated WtS 9-m unresolved bucket report still marks `Vi$T -> ViśT` as a high-scoring promote candidate. This batch did not promote it because the batch scope was Tibetan final-ng cleanup; a later source-list review resolves the siglum separately as `ViśT`, not `VisṬ`. The `la'añń -> la'aṅń` singleton also remains held.

## Commands

Postprocess:

```bash
OUT="work/postprocess_wts9_final_ng_batch_20260614T065617Z"
mkdir -p "$OUT"
python3 scripts/postprocess_entry_map.py --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_8-b/WtS 8-b_lineanchored_merged_full.txt" --outdir "$OUT/wts_8_b" --label wts_8_b --alternate-merged "pdfs/WtS 8-b.vision.txt" --alternate-google-vision
python3 scripts/postprocess_entry_map.py --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_9-m/WtS 9-m_lineanchored_merged_full.txt" --outdir "$OUT/wts_9_m" --label wts_9_m --alternate-merged "pdfs/WtS 9-m.vision.txt" --alternate-google-vision
```

Bucket reports:

```bash
python3 scripts/report_unresolved_buckets.py --run-dir work/postprocess_wts9_final_ng_batch_20260614T065617Z/wts_8_b --out-prefix work/postprocess_wts9_final_ng_batch_20260614T065617Z/wts_8_b/bucket_report
python3 scripts/report_unresolved_buckets.py --run-dir work/postprocess_wts9_final_ng_batch_20260614T065617Z/wts_9_m --out-prefix work/postprocess_wts9_final_ng_batch_20260614T065617Z/wts_9_m/bucket_report
```

Verification:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/report_unresolved_buckets.py
python3 -m pytest tests/test_postprocess_regressions.py -q
```

Result: `96 passed in 0.78s`; py_compile produced no errors.

## Checksums

WtS 8-b:

- corrected full text: `53360c37f74527623c6dab67ebefd723003c76637451b083fb910c3f20d99624`
- changes TSV: `c782acf946f07bbb84227774bc15a89fc689b534f4fe115f619921bf44306a98`
- alternate-witness adoptions TSV: `780d489b06159ec4d89c9922cd008a7f3075e394e53dbf4b2dbe7c6aca392a8e`
- alternate-witness unresolved TSV: `aae222f8815f6ae0efe25da58f38570af3ac3a2bd145e62701f8bf65dd845da8`
- watchdog TSV: `f1aff5e4bb29b980eb3ece1644fbb86f7d1188aed20ed0bf42515a295bc48cfd`

WtS 9-m:

- corrected full text: `81de1410c0f9d25e35f57a5d0935709c47363cbe8a3e5cf14811667978ee33bd`
- changes TSV: `be1621966426adead7139df1e7d821ade6b8dcfb687c53403bc0af7b8e6c47e4`
- alternate-witness adoptions TSV: `a05615c3629941273f22b16c1d2a5c9d7a93b31074e8c34a50093ca87d8fc931`
- alternate-witness unresolved TSV: `636f9311b87e1eade713c7e5c997b15a542f375cd9cbf9635d8372184eae6071`
- watchdog TSV: `f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c`
