# WtS 8-b / WtS 9-m Release-Readiness Handoff

Date: 2026-06-13

## Repository State

- Branch: `main`
- Latest reviewed commit: `803bafab26 Add exact WtS 9-m dngos normalization`
- Regression check: `python3 -m pytest tests/test_postprocess_regressions.py -q`
  - Result: `89 passed in 0.52s`
- Compile check:
  - `python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py`
  - Result: passed

No OCR correction heuristics were added during this handoff pass. Google Vision
remains an alternate witness only.

## Local Artifact Roots

- Line-anchor run: `work/line_anchor_new_volumes_20260605T154602Z`
- WtS 8-b postprocess QA bundle: `work/postprocess_new_volumes_google_qa_20260613T013443Z/wts_8_b`
- WtS 9-m superseding postprocess QA bundle: `work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m`
- Superseded WtS 9-m diagnostic bundle: `work/postprocess_new_volumes_google_qa_20260613T013443Z/wts_9_m`

The `work/` outputs are local artifacts and are not versioned in the repository.

## Reproduction Commands

```bash
python3 -m pytest tests/test_postprocess_regressions.py -q
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py
```

```bash
PDF_3="pdfs/WtS 8-b.pdf" \
LABEL_3="WtS_8-b" \
PDF_4="pdfs/WtS 9-m.pdf" \
LABEL_4="WtS_9-m" \
scripts/run_line_anchor_full_locked.sh "work/line_anchor_new_volumes_YYYYMMDDTHHMMSSZ"
```

```bash
OUT8=work/postprocess_new_volumes_google_qa_20260613T013443Z
OUT9=work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z

python3 scripts/postprocess_entry_map.py \
  --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_8-b/WtS 8-b_lineanchored_merged_full.txt" \
  --outdir "$OUT8/wts_8_b" \
  --label wts_8_b \
  --alternate-merged "pdfs/WtS 8-b.vision.txt" \
  --alternate-google-vision

python3 scripts/postprocess_entry_map.py \
  --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_9-m/WtS 9-m_lineanchored_merged_full.txt" \
  --outdir "$OUT9/wts_9_m" \
  --label wts_9_m \
  --alternate-merged "pdfs/WtS 9-m.vision.txt" \
  --alternate-google-vision

python3 scripts/report_unresolved_buckets.py --run-dir "$OUT8/wts_8_b" --out-prefix "$OUT8/wts_8_b/bucket_report"
python3 scripts/report_unresolved_buckets.py --run-dir "$OUT9/wts_9_m" --out-prefix "$OUT9/wts_9_m/bucket_report"
```

## QA Bundle Summary

| Volume | Pages | Entries | Alternate adoptions | Unresolved rows | Watchdog rows | Sanskrit review suggestions | Reviewed Tibetan exact changes | Corrected text checksum |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `wts_8_b` | 585 | 3125 | 3 | 900 | 31 | 22 | 0 | `89fbf4754e5f2a16d960861c0a8b288372396716eaf3c8b359b111cab2f47fe2` |
| `wts_9_m` | 401 | 1791 | 853 | 1135 | 16 | 14 | 4 | `0c72843d09fd40148965822729e7a2f97090bc94d733427db87636d5dfdb6b7f` |

The WtS 9-m row uses the superseding `dṅos` fix bundle, not the earlier
diagnostic bundle that still contained bad `dños` corrected text.

## Adoption Reasons

| Volume | Top adoption reasons |
|---|---|
| `wts_8_b` | `alternate_witness_google_loc_nasal_upgrade`: 1; `alternate_witness_google_loc_fricative_upgrade`: 1; `alternate_witness_initial_i_to_l_translit`: 1 |
| `wts_9_m` | `alternate_witness_google_loc_nasal_upgrade`: 422; `alternate_witness_initial_i_to_l_translit`: 238; `alternate_witness_google_loc_fricative_upgrade`: 98; `alternate_witness_citation_siglum`: 66; `alternate_witness_google_loc_velar_nasal_upgrade`: 21; `alternate_witness_hyphenated_initial_i_to_l_translit`: 5; `alternate_witness_citation_cleanup`: 2; `alternate_witness_strict_translit`: 1 |

## Alignment Attribution

| Volume | Alignment attribution | Resynchronization attribution |
|---|---|---|
| `wts_8_b` | `rewrapped_page_alignment`: 3 | `direct_page_alignment`: 3 |
| `wts_9_m` | `recovered_rewrapped_fallback`: 825; `rewrapped_page_alignment`: 28 | `direct_recovered_rewrapped_fallback`: 825; `direct_page_alignment`: 28 |

WtS 9-m's high recovered-fallback count is an alignment diagnostic. It is not
evidence that Google Vision is being treated as an authority.

## Adoption Density

| Volume | Highest-density pages |
|---|---|
| `wts_8_b` | page 3: 3 adoptions |
| `wts_9_m` | pages 126, 268, 272, and 326: 11 adoptions each; page 187: 10; pages 58, 79, 112, 120, 146, 173, and 389: 9 each |

The WtS 9-m density is high enough that any release freeze should include a
small page-level sample from these pages, especially for nasal upgrades and
initial-I-to-l changes. No new high-volume rule was promoted here.

## Unresolved Bucket Reports

| Volume | Unresolved confusable pairs | Promote-labeled bucket rows | Hold bucket rows | Notes |
|---|---:|---:|---:|---|
| `wts_8_b` | 133 | 3 | 130 | `miñ -> miṅ`, `Myañ -> Myaṅ`, and `sañ -> saṅ` are review diagnostics only until source/context checked. |
| `wts_9_m` | 106 | 1 | 105 | `Vi$T -> ViśT` is a citation/siglum diagnostic only in this bundle, not a Sanskrit or Tibetan normalization target. Later source-list review resolves `ViśT` as the canonical siglum. |

## Manual Audit Sample

| Volume | Page | Line | Item | Decision |
|---|---:|---:|---|---|
| `wts_8_b` | 3 | 18 | `bses -> bśes` | Accepted alternate-witness fricative upgrade. |
| `wts_8_b` | 3 | 25 | `sPan-lun -> sPañ-lun` | Accepted alternate-witness nasal upgrade. |
| `wts_8_b` | 3 | 32 | `Iha -> lha` | Accepted initial-I-to-l transliteration cleanup. |
| `wts_9_m` | 68 | 2 | `dnos -> dṅos` | Exact reviewed Tibetan correction; bad `dños` target blocked. |
| `wts_9_m` | 143 | 10 | `dnos -> dṅos` | Exact reviewed Tibetan correction; bad `dños` target blocked. |
| `wts_9_m` | 190 | 77 | `dnos -> dṅos` | Exact reviewed Tibetan correction; bad `dños` target blocked. |
| `wts_9_m` | 381 | 57 | `dnos -> dṅos` | Exact reviewed Tibetan correction; bad `dños` target blocked. |
| `wts_9_m` | 72 | 12 | `gNa-khri -> gÑa-khri` | Good Google-witness nasal upgrade. Do not broaden to the other `gNa-khri` occurrence without source review. |

The WtS 9-m corrected text now has no remaining `dños` matches. Other `dnos`
occurrences remain intentionally unchanged because this pass added no broad
`dnos -> dṅos` rule.

## Readiness Decision

WtS 8-b is suitable for QA handoff. It has only three alternate-witness
adoptions, all manually audited in the sample above.

WtS 9-m is also suitable for QA handoff using the superseding `dṅos` fix bundle.
The known bad `dños` corrected text has been removed, adoption/unresolved
movement is explained by the four blocked bad Google adoptions plus four exact
reviewed Tibetan corrections, and watchdog rows did not increase.

This is still a QA handoff, not permission to promote new rules from the
diagnostic queues. Bucket-report candidates and validator-like residue remain
review-only until independently source-supported.

## Checksums

### WtS 8-b

```text
89fbf4754e5f2a16d960861c0a8b288372396716eaf3c8b359b111cab2f47fe2  wts_8_b_corrected_full.txt
974958162bc81d44e6bc017e7de754f984e1a674f7f7a946ae2e420b12ef26de  wts_8_b_changes.tsv
780d489b06159ec4d89c9922cd008a7f3075e394e53dbf4b2dbe7c6aca392a8e  wts_8_b_alternate_witness_adoptions.tsv
aae222f8815f6ae0efe25da58f38570af3ac3a2bd145e62701f8bf65dd845da8  wts_8_b_alternate_witness_unresolved.tsv
0217906680d9ec356760537214f73fbaba81bc8c09eea78a9f3ed9b8201293b9  bucket_report.unresolved_pairs.tsv
1f3a8e382bdd369a6bfe3b4546fa6509343da87a319b40f53a090ca672b22467  bucket_report.artifact_tokens.tsv
dadb790feb449e51075c34871150683b5e76386ea0c3c372e88d297a13ac75ec  bucket_report.summary.md
```

### WtS 9-m

```text
0c72843d09fd40148965822729e7a2f97090bc94d733427db87636d5dfdb6b7f  wts_9_m_corrected_full.txt
4636d2d599a0b238a01a5f8e65affde75e87a557283082fd90c5006ca96fad43  wts_9_m_changes.tsv
a05615c3629941273f22b16c1d2a5c9d7a93b31074e8c34a50093ca87d8fc931  wts_9_m_alternate_witness_adoptions.tsv
636f9311b87e1eade713c7e5c997b15a542f375cd9cbf9635d8372184eae6071  wts_9_m_alternate_witness_unresolved.tsv
c39193c9e69d3dff9cfb548a94277e5d9df2b97c9e41bd0a7e74fc5f0e173fa6  bucket_report.unresolved_pairs.tsv
ad149ea3e2201841b82da6efe9b2c958d26443b16bef7e3d17a012e348dd1699  bucket_report.artifact_tokens.tsv
8af60709724a986f1cbe6e549cf62ea62f86ac9017582c5fb0fcad0f2942165c  bucket_report.summary.md
```

## Remaining Caveats

- WtS 9-m has 853 alternate-witness adoptions, mostly recovered-rewrapped
  fallback alignments. The current safeguards held, but final release sign-off
  should still sample the highest-density pages and top adoption reasons.
- `miñ -> miṅ`, `Myañ -> Myaṅ`, and `sañ -> saṅ` are diagnostic bucket
  rows only. They should not drive text changes without source/context review.
  `Vi$T -> ViśT` was diagnostic in this bundle, then later source-list review
  resolved it as an exact citation-siglum normalization.
- Google Vision remains an alternate witness, not an authority. Raw Google line
  replacement remains out of scope.

## Next Step

If the project is moving from QA handoff to release packaging, use the two
trusted bundle roots above and sample WtS 9-m's high-density adoption pages
before freezing. Do not add more OCR correction rules from the diagnostic
queues unless a separate source-supported review identifies a narrow exact
pattern.
