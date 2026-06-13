# WtS 9-m Exact dṅos Fix

Date: 2026-06-13

## Scope

This note documents the targeted WtS 9-m follow-up to the new-volume Google
witness QA bundle. The change is intentionally narrow:

- keep the accepted WtS 9-m `gNa-khri -> gÑa-khri` alternate-witness adoption;
- block the bad alternate-witness pair `dnos -> dños`;
- promote four reviewed local WtS 9-m `dnos -> dṅos` corrections by exact
  page, line, token index, and source token.

No broad OCR correction heuristic was added. There is no general `dnos` rule,
no general nasal rule, and no change to Google Vision adoption gates.

## Output Checked

Targeted QA output:

`work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z`

Compared against the earlier new-volume QA bundle:

`work/postprocess_new_volumes_google_qa_20260613T013443Z/wts_9_m`

| Metric | Before | After |
| --- | ---: | ---: |
| Alternate-witness adoptions | 857 | 853 |
| Alternate-witness unresolved rows | 1131 | 1135 |
| Reviewed Tibetan exact changes | 0 | 4 |
| Bucket-report unresolved pairs | 106 | 106 |
| Bucket-report promote pairs | 1 | 1 |
| Bucket-report hold pairs | 105 | 105 |

The four removed adoptions are the reviewed bad `dnos -> dños` rows. A fifth
`dnos -> dños` comparison at WtS 9-m p233 l35 is now classified as
`blocked_alternate_witness_wrong_nasal_dnos`, but it was already unresolved and
does not change corrected text.

WtS 9-m p229 l33 still has unresolved `dnos -> dṅos` with reason
`non_translit_context`. It was not promoted, which confirms that this pass did
not add a broad `dnos -> dṅos` rule.

## Corrected Text Diff

| Page | Line | Before | After |
| ---: | ---: | --- | --- |
| 68 | 2 | `Lex. la sogs pa = dños su gsal por ma ston par` | `Lex. la sogs pa = dṅos su gsal por ma ston par` |
| 143 | 10 | `_ la gser gym ... sogs dños po' rigs tshon` | `_ la gser gym ... sogs dṅos po' rigs tshon` |
| 190 | 77 | `sa' dños gi tsbig don gñis ka - la soxs` | `sa' dṅos gi tsbig don gñis ka - la soxs` |
| 381 | 57 | `drug gi iamis len gyi bya bas dños su ma zin` | `drug gi iamis len gyi bya bas dṅos su ma zin` |

The corresponding `wts_9_m_changes.tsv` rows use tier
`reviewed_tibetan_exact` and reason `reviewed_tibetan_exact_dngos`.

## Guardrails

- `gNa-khri -> gÑa-khri` remains an accepted Google-witness nasal upgrade at
  WtS 9-m p72 l12.
- `dnos -> dños` is blocked as a known bad exact alternate-witness pair.
- The replacement `dnos -> dṅos` is applied only to the four reviewed WtS 9-m
  page/line/token occurrences.
- Google Vision remains an alternate witness only.

## Verification

Commands run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py
python3 -m pytest tests/test_postprocess_regressions.py -q
```

Result:

`89 passed in 0.45s`

Targeted WtS 9-m postprocess command:

```bash
python3 scripts/postprocess_entry_map.py \
  --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_9-m/WtS 9-m_lineanchored_merged_full.txt" \
  --outdir "work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m" \
  --label wts_9_m \
  --alternate-merged "pdfs/WtS 9-m.vision.txt" \
  --alternate-google-vision
```

Bucket report command:

```bash
python3 scripts/report_unresolved_buckets.py \
  --run-dir "work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m" \
  --out-prefix "work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m/bucket_report"
```

## Checksums

```text
0c72843d09fd40148965822729e7a2f97090bc94d733427db87636d5dfdb6b7f  work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m/wts_9_m_corrected_full.txt
4636d2d599a0b238a01a5f8e65affde75e87a557283082fd90c5006ca96fad43  work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m/wts_9_m_changes.tsv
a05615c3629941273f22b16c1d2a5c9d7a93b31074e8c34a50093ca87d8fc931  work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m/wts_9_m_alternate_witness_adoptions.tsv
636f9311b87e1eade713c7e5c997b15a542f375cd9cbf9635d8372184eae6071  work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m/wts_9_m_alternate_witness_unresolved.tsv
c39193c9e69d3dff9cfb548a94277e5d9df2b97c9e41bd0a7e74fc5f0e173fa6  work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m/bucket_report.unresolved_pairs.tsv
ad149ea3e2201841b82da6efe9b2c958d26443b16bef7e3d17a012e348dd1699  work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m/bucket_report.artifact_tokens.tsv
8af60709724a986f1cbe6e549cf62ea62f86ac9017582c5fb0fcad0f2942165c  work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m/bucket_report.summary.md
```
