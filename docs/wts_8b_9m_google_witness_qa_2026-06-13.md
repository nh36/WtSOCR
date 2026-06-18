# WtS 8-b and WtS 9-m Google Witness QA

Date: 2026-06-13

## Scope

This pass processed the two additional volumes through the existing conservative
postprocess path:

- `WtS 8-b`
- `WtS 9-m`

No OCR correction heuristics were added or changed. Google Vision was used only
as an alternate witness. The base OCR remains authoritative, and no raw Google
line replacement was performed.

## Repository Baseline

- Branch: `main`
- Baseline commit: `615a448274 Update refined attribution status doc`
- Regression check: `85 passed in 0.48s`
- Syntax check: `python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py`

## Local Output Roots

These `work/` directories are local generated artifacts and are not versioned in
the repository.

- Line-anchor input root: `work/line_anchor_new_volumes_20260605T154602Z`
- Postprocess QA root: `work/postprocess_new_volumes_google_qa_20260613T013443Z`
- Manual audit sample: `work/postprocess_new_volumes_google_qa_20260613T013443Z/manual_audit_sample.tsv`
- Checksums: `work/postprocess_new_volumes_google_qa_20260613T013443Z/checksums.sha256`

The QA root contains corrected text, changes TSVs, alternate-witness adoptions,
alternate-witness unresolved rows, bucket reports, summaries, watchdog flags,
and checksums for both volumes.

## Reproduction Commands

Regression and syntax checks:

```bash
python3 -m pytest tests/test_postprocess_regressions.py -q
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py
```

Optional PDF runner path used to produce the line-anchor inputs:

```bash
PDF_3="pdfs/WtS 8-b.pdf" \
LABEL_3="WtS_8-b" \
PDF_4="pdfs/WtS 9-m.pdf" \
LABEL_4="WtS_9-m" \
scripts/run_line_anchor_full_locked.sh "work/line_anchor_new_volumes_YYYYMMDDTHHMMSSZ"
```

Postprocess QA for the two new volumes:

```bash
OUT=work/postprocess_new_volumes_google_qa_20260613T013443Z

python3 scripts/postprocess_entry_map.py \
  --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_8-b/WtS 8-b_lineanchored_merged_full.txt" \
  --outdir "$OUT/wts_8_b" \
  --label wts_8_b \
  --alternate-merged "pdfs/WtS 8-b.vision.txt" \
  --alternate-google-vision

python3 scripts/postprocess_entry_map.py \
  --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_9-m/WtS 9-m_lineanchored_merged_full.txt" \
  --outdir "$OUT/wts_9_m" \
  --label wts_9_m \
  --alternate-merged "pdfs/WtS 9-m.vision.txt" \
  --alternate-google-vision

python3 scripts/report_unresolved_buckets.py \
  --run-dir "$OUT/wts_8_b" \
  --out-prefix "$OUT/wts_8_b/bucket_report"

python3 scripts/report_unresolved_buckets.py \
  --run-dir "$OUT/wts_9_m" \
  --out-prefix "$OUT/wts_9_m/bucket_report"
```

## Volume Results

| Volume | Pages | Entries | Corrected text checksum | Alternate adoptions | Unresolved rows | Watchdog rows | Sanskrit review suggestions |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| `wts_8_b` | 585 | 3125 | `89fbf4754e5f2a16d960861c0a8b288372396716eaf3c8b359b111cab2f47fe2` | 3 | 900 | 31 | 22 |
| `wts_9_m` | 401 | 1791 | `b710be12455e80962ace30e4b163f8a1a8c244188b420ed7cb624f499abde765` | 857 | 1131 | 16 | 14 |

## Adoption Attribution

| Volume | Rewrapped page alignment | Recovered rewrapped fallback | Direct page alignment | Direct recovered fallback |
| --- | ---: | ---: | ---: | ---: |
| `wts_8_b` | 3 | 0 | 3 | 0 |
| `wts_9_m` | 28 | 829 | 28 | 829 |

The `wts_9_m` adoption volume is dominated by recovered rewrapped fallback
alignment. The sampled rows are plausible token-level changes, but future
high-volume patterns from this volume should be sampled before being trusted.

## Top Adoption Reasons

| Volume | Reason | Count |
| --- | --- | ---: |
| `wts_8_b` | `alternate_witness_google_loc_fricative_upgrade` | 1 |
| `wts_8_b` | `alternate_witness_google_loc_nasal_upgrade` | 1 |
| `wts_8_b` | `alternate_witness_initial_i_to_l_translit` | 1 |
| `wts_9_m` | `alternate_witness_google_loc_nasal_upgrade` | 426 |
| `wts_9_m` | `alternate_witness_initial_i_to_l_translit` | 238 |
| `wts_9_m` | `alternate_witness_google_loc_fricative_upgrade` | 98 |
| `wts_9_m` | `alternate_witness_citation_siglum` | 66 |
| `wts_9_m` | `alternate_witness_google_loc_velar_nasal_upgrade` | 21 |

## High-Density Pages

`wts_8_b` has only one adoption page: page 3 with 3 adoptions.

The highest-density `wts_9_m` pages are still moderate; the maximum observed
density is 11 adoptions on a page.

| Volume | Page | Adoptions |
| --- | ---: | ---: |
| `wts_9_m` | 126 | 11 |
| `wts_9_m` | 268 | 11 |
| `wts_9_m` | 272 | 11 |
| `wts_9_m` | 326 | 11 |
| `wts_9_m` | 187 | 10 |
| `wts_9_m` | 58 | 9 |
| `wts_9_m` | 68 | 9 |
| `wts_9_m` | 79 | 9 |

## Unresolved Buckets

The bucket reports are diagnostic only. None of these rows were promoted in this
pass.

| Volume | Unresolved confusable pairs | Conservative promote candidates | Hold candidates |
| --- | ---: | ---: | ---: |
| `wts_8_b` | 133 | 3 | 130 |
| `wts_9_m` | 106 | 1 | 105 |

Top diagnostic promote candidates:

| Volume | From | To | Unresolved count | Score |
| --- | --- | --- | ---: | ---: |
| `wts_8_b` | `miñ` | `miṅ` | 6 | 4 |
| `wts_8_b` | `Myañ` | `Myaṅ` | 5 | 4 |
| `wts_8_b` | `sañ` | `saṅ` | 5 | 4 |
| `wts_9_m` | `Vi$T` | `ViśT` | 6 | 4 |

Later source-list review resolves `ViśT` as the canonical siglum for
`Viśeṣastavatīkā`; it is a citation-siglum normalization, not a Sanskrit or
Tibetan OCR rule.

Top hold examples include `$`/`Ś` citation-like forms, Tibetan nasal forms, and
line/page alignment mismatches. They remain review material, not correction
evidence.

## Manual Audit Sample

The manual audit sample contains 99 rows:

- `wts_8_b`: 25 rows
- `wts_9_m`: 74 rows

For `wts_8_b`, all three adopted rows were inspected. They are token-level
changes on page 3:

- `bses -> bśes`
- `sPan-lun -> sPañ-lun`
- `Iha -> lha`

For `wts_9_m`, the sample covers adoption reasons, recovered fallback rows,
high-density pages, and unresolved buckets. The observed accepted patterns were
mostly Tibetan nasal upgrades, initial `I` to `l` in Wylie-like context,
fricative upgrades, and citation siglum cleanups. The sample did not show raw
line replacement or a new correction heuristic being applied.

## Caveats

- `wts_9_m` has 829 adoptions through recovered rewrapped fallback alignment.
  The sampled rows look plausible, but this attribution class should remain
  visible in any release audit.
- The unresolved bucket promote candidates are diagnostics only. They are not
  evidence for new OCR rules without source or context review.
- No generated `work/` files are committed by this note.
- Google Vision gates were not loosened.
