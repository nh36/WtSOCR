# WtS 8-b / WtS 9-m Release-Readiness Handoff

Date: 2026-06-13

## Repository State

- Branch: `main`
- Latest reviewed commit: `ff4037d648 Document WtS 9-m recovered fallback audit`
- Regression check: `python3 -m pytest tests/test_postprocess_regressions.py -q`
  - Result: `85 passed in 0.49s`
- Compile check:
  - `python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py`
  - Result: passed

No OCR correction heuristics were added during this handoff pass. Google Vision remains an alternate witness only.

## Local Artifact Roots

- Line-anchor run: `work/line_anchor_new_volumes_20260605T154602Z`
- Postprocess QA bundle: `work/postprocess_new_volumes_google_qa_20260613T013443Z`

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

python3 scripts/report_unresolved_buckets.py --run-dir "$OUT/wts_8_b" --out-prefix "$OUT/wts_8_b/bucket_report"
python3 scripts/report_unresolved_buckets.py --run-dir "$OUT/wts_9_m" --out-prefix "$OUT/wts_9_m/bucket_report"
```

## QA Bundle Summary

| Volume | Pages | Entries | Alternate adoptions | Unresolved rows | Watchdog rows | Sanskrit review suggestions | Corrected text checksum |
|---|---:|---:|---:|---:|---:|---:|---|
| `wts_8_b` | 585 | 3125 | 3 | 900 | 31 | 22 | `89fbf4754e5f2a16d960861c0a8b288372396716eaf3c8b359b111cab2f47fe2` |
| `wts_9_m` | 401 | 1791 | 857 | 1131 | 16 | 14 | `b710be12455e80962ace30e4b163f8a1a8c244188b420ed7cb624f499abde765` |

## Readiness Decision

WtS 8-b is suitable for QA handoff. It has only three alternate-witness adoptions, all manually audited in the existing sample.

WtS 9-m is not yet suitable as a final corrected-text release candidate. The QA bundle is useful diagnostic output, but four final corrected lines contain the known-bad target `dños`. These should be handled before release by an exact, test-backed Tibetan correction pass. The right direction is not `dnos -> dños`; in reviewed Tibetan contexts it should be `dnos -> dṅos`.

## Known Bad WtS 9-m Adoption Targets

| Page | Line | Current adoption | Final corrected context | Decision |
|---:|---:|---|---|---|
| 68 | 2 | `dnos -> dños` | `Lex. la sogs pa = dños su gsal por ma ston par` | Bad target; review as `dnos -> dṅos`. |
| 143 | 10 | `dnos -> dños` | `_ la gser gym sogs dños po' rigs tshon` | Bad target; review as `dnos -> dṅos`. |
| 190 | 77 | `dnos -> dños` | `sa' dños gi tsbig don gñis ka - la soxs` | Bad target; review as `dnos -> dṅos`. |
| 381 | 57 | `dnos -> dños` | `drug gi iamis len gyi bya bas dños su ma zin` | Bad target; review as `dnos -> dṅos`. |

The unresolved TSV also contains a useful diagnostic row at WtS 9-m p229 l33: `dnos -> dṅos`. That supports the expected Tibetan direction but was not adopted by the current gates.

## Accepted And Review-Only Diagnostics

| Item | Status |
|---|---|
| WtS 9-m p72 l12 `gNa-khri -> gÑa-khri` | Good change. Keep it. Another `gNa-khri` occurrence remains elsewhere and should be source-reviewed separately before any broader promotion. |
| WtS 9-m p196 l64 adoption `gan -> gañ` | The adoption TSV records the intermediate Google-supported step; final corrected text contains `gaṅ dag`, which is the accepted final output. |
| `Vi$T -> ViśT` / `Vi$T` rows | Citation/siglum diagnostics only. Do not treat as Sanskrit or Tibetan normalization evidence. Existing citation-siglum handling maps related rows to `VisT`. |
| WtS 8-b `miñ -> miṅ`, `Myañ -> Myaṅ`, `sañ -> saṅ` | Review diagnostics only. They are not correction evidence without source/context review. |

## Next Implementation Target

1. Add a targeted regression-backed guard or exact correction path so Google Vision does not promote `dnos -> dños`.
2. Promote `dnos -> dṅos` only in reviewed Tibetan contexts; do not add a broad nasal rule.
3. Rerun WtS 9-m postprocess and verify the four final `dños` lines disappear.
4. Confirm adoption counts, unresolved counts, watchdog rows, and corrected-text checksums change only because of the intended Tibetan corrections.
5. Reassess release readiness after the corrected WtS 9-m bundle is produced.
