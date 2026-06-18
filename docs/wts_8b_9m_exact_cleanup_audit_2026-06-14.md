# WtS 8-b / WtS 9-m Exact Cleanup Audit

Date: 2026-06-14

## Scope

This note documents the exact Tibetan cleanup batch that follows the
2026-06-13 release-freeze audit. It supersedes the corrected-text checksums in
that earlier note, but keeps the same conservative policy:

- Google Vision remains an alternate witness only.
- No Google adoption gates were loosened.
- No broad OCR correction heuristic was added.
- Validator-only residue was not used as correction evidence.
- All promoted rows are exact token/page/line/index entries.

The generated `work/` outputs are local artifacts and are not versioned in the
repository.

## Inputs And Output Root

- WtS 8-b line-anchor input:
  `work/line_anchor_new_volumes_20260605T154602Z/WtS_8-b/WtS 8-b_lineanchored_merged_full.txt`
- WtS 8-b alternate witness: `pdfs/WtS 8-b.vision.txt`
- WtS 9-m line-anchor input:
  `work/line_anchor_new_volumes_20260605T154602Z/WtS_9-m/WtS 9-m_lineanchored_merged_full.txt`
- WtS 9-m alternate witness: `pdfs/WtS 9-m.vision.txt`
- New output root:
  `work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z`

## Promoted Exact Rows

### WtS 8-b

The WtS 8-b changes are exact final-`ṅ` repairs in reviewed Tibetan/Wylie-like
contexts. This is not a broad `ñ -> ṅ` rule.

| Page | Line | Token index | From | To | Reason |
|---:|---:|---:|---|---|---|
| 69 | 16 | 2 | `sañ` | `saṅ` | `reviewed_tibetan_exact_final_ng` |
| 109 | 71 | 4 | `Myañ` | `Myaṅ` | `reviewed_tibetan_exact_final_ng` |
| 150 | 30 | 10 | `miñ` | `miṅ` | `reviewed_tibetan_exact_final_ng` |
| 186 | 65 | 3 | `miñ` | `miṅ` | `reviewed_tibetan_exact_final_ng` |
| 212 | 14 | 1 | `sañ` | `saṅ` | `reviewed_tibetan_exact_final_ng` |
| 232 | 30 | 8 | `sañ` | `saṅ` | `reviewed_tibetan_exact_final_ng` |
| 269 | 53 | 13 | `miñ` | `miṅ` | `reviewed_tibetan_exact_final_ng` |
| 309 | 57 | 2 | `Myañ` | `Myaṅ` | `reviewed_tibetan_exact_final_ng` |
| 436 | 53 | 8 | `miñ` | `miṅ` | `reviewed_tibetan_exact_final_ng` |
| 464 | 41 | 6 | `sañ` | `saṅ` | `reviewed_tibetan_exact_final_ng` |
| 522 | 60 | 4 | `miñ` | `miṅ` | `reviewed_tibetan_exact_final_ng` |
| 526 | 92 | 4 | `Myañ` | `Myaṅ` | `reviewed_tibetan_exact_final_ng` |
| 553 | 75 | 6 | `Myañ` | `Myaṅ` | `reviewed_tibetan_exact_final_ng` |
| 553 | 76 | 4 | `Myañ` | `Myaṅ` | `reviewed_tibetan_exact_final_ng` |
| 564 | 71 | 9 | `miñ` | `miṅ` | `reviewed_tibetan_exact_final_ng` |
| 572 | 82 | 1 | `sañ` | `saṅ` | `reviewed_tibetan_exact_final_ng` |

### WtS 9-m

Two additional WtS 9-m exact rows were promoted. The previously rejected
`dnos -> dños` direction remains rejected; reviewed `dnos` rows normalize only
to `dṅos`.

| Page | Line | Token index | From | To | Reason |
|---:|---:|---:|---|---|---|
| 229 | 33 | 6 | `dnos` | `dṅos` | `reviewed_tibetan_exact_dngos` |
| 351 | 41 | 1 | `gNa-khri` | `gÑa-khri` | `reviewed_tibetan_exact_gna_khri` |

The WtS 9-m reviewed exact set now contains five local `dnos -> dṅos` rows
(pages 68, 143, 190, 229, and 381) plus the reviewed `gNa-khri -> gÑa-khri`
row on page 351.

## Counts

### WtS 8-b

| Metric | Previous trusted bundle | New exact-cleanup bundle |
|---|---:|---:|
| Alternate-witness adoptions | 3 | 3 |
| Alternate-witness unresolved rows | 900 | 900 |
| Changes TSV rows | 2383 | 2399 |
| Watchdog rows | 31 | 31 |
| Review queue rows | 24 | 24 |
| Sanskrit review suggestions | 22 | 22 |
| Reviewed Tibetan exact changes | 0 | 16 |
| Unresolved bucket rows | 133 | 133 |

The regenerated `validator_issues.tsv` row count changed from 3847 to 2350
under the current reporting code. This did not drive text changes; the
corrected-text diff is limited to the 16 exact rows above.

### WtS 9-m

| Metric | Previous trusted bundle | New exact-cleanup bundle |
|---|---:|---:|
| Alternate-witness adoptions | 853 | 853 |
| Alternate-witness unresolved rows | 1135 | 1135 |
| Changes TSV rows | 1560 | 1562 |
| Watchdog rows | 16 | 16 |
| Review queue rows | 16 | 16 |
| Sanskrit review suggestions | 14 | 14 |
| Reviewed Tibetan exact changes | 4 | 6 |
| Unresolved bucket rows | 106 | 106 |

## Corrected-Text Diff Summary

WtS 8-b changed exactly 16 corrected-text lines:

- `sañ gsen -> saṅ gsen`
- `Myañ Zan-snan -> Myaṅ Zan-snan`
- `khyim bya'i miñ -> khyim bya'i miṅ`
- `gtogs pai miñ -> gtogs pai miṅ`
- `sañ Sari -> saṅ Sari`
- `sa sho sañ son -> sa sho saṅ son`
- `brtsi bæi miñ -> brtsi bæi miṅ`
- `~ pa "Myañ -> ~ pa "Myaṅ`
- `od kyi miñ -> od kyi miṅ`
- `den sañ gi bar -> den saṅ gi bar`
- `lbu bæi miñ -> lbu bæi miṅ`
- `Myañ und dBa's -> Myaṅ und dBa's`
- `[Myañ] -> [Myaṅ]`
- `fiir Myañ -> fiir Myaṅ`
- `miñ gi thog -> miṅ gi thog`
- `sañ ni -> saṅ ni`

WtS 9-m changed exactly 2 corrected-text lines:

- `(AA 3.9a); dnos -> (AA 3.9a); dṅos`
- `gNa-khri btsan-po -> gÑa-khri btsan-po`

## Diagnostic Queues Left Unpromoted

- WtS 8-b unresolved bucket rows are still diagnostic. No broad
  `sañ/Myañ/miñ -> saṅ/Myaṅ/miṅ` rule was added.
- WtS 9-m `Vi$T -> ViśT` remained a citation-or-siglum policy case in this
  cleanup pass, not a Sanskrit or Tibetan normalization candidate. Later
  source-list review resolves `ViśT` as the canonical siglum and rejects
  `VisṬ`.
- No validator-only residue drove a correction.

## Verification

Commands:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py
python3 -m pytest tests/test_postprocess_regressions.py -q
```

Result:

```text
93 passed in 0.72s
```

## Final Checksums

```text
53360c37f74527623c6dab67ebefd723003c76637451b083fb910c3f20d99624  work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z/wts_8_b/wts_8_b_corrected_full.txt
c782acf946f07bbb84227774bc15a89fc689b534f4fe115f619921bf44306a98  work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z/wts_8_b/wts_8_b_changes.tsv
780d489b06159ec4d89c9922cd008a7f3075e394e53dbf4b2dbe7c6aca392a8e  work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z/wts_8_b/wts_8_b_alternate_witness_adoptions.tsv
aae222f8815f6ae0efe25da58f38570af3ac3a2bd145e62701f8bf65dd845da8  work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z/wts_8_b/wts_8_b_alternate_witness_unresolved.tsv
f1aff5e4bb29b980eb3ece1644fbb86f7d1188aed20ed0bf42515a295bc48cfd  work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z/wts_8_b/wts_8_b_watchdog_flags.tsv
e61f439c7641bc2d961e7be79731316fa5f293460a35abf2dd795077b8c0dcbb  work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z/wts_9_m/wts_9_m_corrected_full.txt
49f77e2cefd9dd4104b3af405c3abfb0aff939cdab6b0953db90502171e9fa9a  work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z/wts_9_m/wts_9_m_changes.tsv
a05615c3629941273f22b16c1d2a5c9d7a93b31074e8c34a50093ca87d8fc931  work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z/wts_9_m/wts_9_m_alternate_witness_adoptions.tsv
636f9311b87e1eade713c7e5c997b15a542f375cd9cbf9635d8372184eae6071  work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z/wts_9_m/wts_9_m_alternate_witness_unresolved.tsv
f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c  work/postprocess_wts_8b_9m_exact_cleanup_20260613T231813Z/wts_9_m/wts_9_m_watchdog_flags.tsv
```
