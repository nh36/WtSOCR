# Current Release Refresh 2026-06-27

This pass refreshes the tracked `release/current` bundle from a fresh
four-volume postprocess run:

`work/current_release_four_volume_refresh_20260627T170423Z`

The goal was deployment, not new OCR behavior. No Google Vision gates were
loosened and no correction heuristics were added in this pass.

## Inputs

| Volume | Line-anchor source | Google alternate witness |
| --- | --- | --- |
| `wts_1_34` | `work/line_anchor_new_volumes_20260605T154602Z/WtS_1-34/WtS 1-34_lineanchored_merged_full.txt` | `pdfs/WtS 1-34.vision.txt` |
| `wts_35_51` | `work/line_anchor_new_volumes_20260605T154602Z/WtS_35-51/WtS 35-51_lineanchored_merged_full.txt` | `pdfs/WtS 35-51.vision.txt` |
| `wts_8_b` | `work/line_anchor_new_volumes_20260605T154602Z/WtS_8-b/WtS 8-b_lineanchored_merged_full.txt` | `pdfs/WtS 8-b.vision.txt` |
| `wts_9_m` | `work/line_anchor_new_volumes_20260605T154602Z/WtS_9-m/WtS 9-m_lineanchored_merged_full.txt` | `pdfs/WtS 9-m.vision.txt` |

## Postprocess Counts

| Volume | Entries | Non-empty lines | Validator issues | Google adoptions | Unresolved | Citation/name changes | Reviewed Tibetan exact changes | Sanskrit changes | Sanskrit review suggestions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `wts_1_34` | 12014 | 180208 | 17070 | 38 | 3322 | 2020 | 0 | 401 | 70 |
| `wts_35_51` | 6148 | 91855 | 8118 | 1168 | 1895 | 919 | 0 | 149 | 31 |
| `wts_8_b` | 3125 | 48290 | 2344 | 3 | 900 | 459 | 170 | 72 | 8 |
| `wts_9_m` | 1791 | 33664 | 1554 | 842 | 1134 | 276 | 274 | 89 | 10 |

## Bucket Reports

| Volume | Unresolved pairs | Promote rows | Hold rows |
| --- | ---: | ---: | ---: |
| `wts_1_34` | 204 | 7 | 197 |
| `wts_35_51` | 177 | 8 | 169 |
| `wts_8_b` | 125 | 0 | 125 |
| `wts_9_m` | 38 | 0 | 38 |

The main-volume bucket promote rows are inherited diagnostics and were not
promoted in this deployment refresh.

## Deployment Notes

`release/current` now contains the fresh corrected text and compact QA artifacts
for all four volumes. The source `work/` directory remains local and ignored by
Git; `release/current` is the versioned best-current etext snapshot.

The changes TSVs show the current accepted families being applied, including
reviewed Tibetan exact rows in WtS 8-b and WtS 9-m, Sanskrit normalisations, and
the reviewed ViśT siglum family. Some suspicious-looking strings remain in the
corrected text where context gates did not fire or where the case is still
unreviewed; this pass did not override those safeguards.

## Verification

Run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py scripts/build_current_release_bundle.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result on 2026-06-27: `py_compile` passed; `pytest` reported
`139 passed, 6 subtests passed in 1.62s`.

Checksums for the deployed bundle are in `release/current/checksums.tsv`.
