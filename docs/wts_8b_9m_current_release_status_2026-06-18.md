# WtS 8-b / WtS 9-m Current Release Status

Date: 2026-06-18

Current commit:

- `471d605c83 Normalize ViśT citation siglum`

Current refreshed output root:

- `work/postprocess_wts8b_9m_current_main_20260618T080923Z`

Previous comparison root:

- `work/postprocess_wts9_final_ng_batch_20260614T065617Z`

The `work/` outputs are local verification artifacts. They are not versioned in the repository.

## Verification

Commands run:

```bash
python3 -m pytest tests/test_postprocess_regressions.py -q
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py
```

Result:

- `96 passed in 0.75s`
- `py_compile` completed with no errors.

No OCR correction heuristics were added in this refresh. Google Vision remains an alternate witness only, and adoption gates were not loosened.

## Reproduction Commands

```bash
OUT_ROOT=work/postprocess_wts8b_9m_current_main_20260618T080923Z

python3 scripts/postprocess_entry_map.py \
  --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_8-b/WtS 8-b_lineanchored_merged_full.txt" \
  --outdir "$OUT_ROOT/wts_8_b" \
  --label wts_8_b \
  --alternate-merged "pdfs/WtS 8-b.vision.txt" \
  --alternate-google-vision

python3 scripts/postprocess_entry_map.py \
  --merged "work/line_anchor_new_volumes_20260605T154602Z/WtS_9-m/WtS 9-m_lineanchored_merged_full.txt" \
  --outdir "$OUT_ROOT/wts_9_m" \
  --label wts_9_m \
  --alternate-merged "pdfs/WtS 9-m.vision.txt" \
  --alternate-google-vision

python3 scripts/report_unresolved_buckets.py \
  --run-dir "$OUT_ROOT/wts_8_b" \
  --out-prefix "$OUT_ROOT/wts_8_b/bucket_report"

python3 scripts/report_unresolved_buckets.py \
  --run-dir "$OUT_ROOT/wts_9_m" \
  --out-prefix "$OUT_ROOT/wts_9_m/bucket_report"
```

## WtS 8-b Counts

| Metric | Current |
|---|---:|
| Entries detected | 3125 |
| Non-empty lines | 48290 |
| Validator issues | 2350 |
| Alternate-witness adoptions | 3 |
| Alternate-witness unresolved | 900 |
| Tier A applied | 2418 |
| Tier B suggestions | 24 |
| Citation/name changes | 421 |
| Reviewed Tibetan exact changes | 16 |
| Sanskrit changes | 25 |
| Sanskrit review suggestions | 22 |
| Watchdog rows | 31 |
| Review queue rows | 24 |
| Bucket report unresolved pairs | 131 |
| Bucket report promote pairs | 0 |

Current checksums:

| Artifact | SHA-256 |
|---|---|
| corrected_full | `5c35cc6c674b174292858ecb0fc561407dfb72d5d27113b1098bcfc083fa876e` |
| changes | `ee27a5efb308fe0fbefb0c417039e9e0b8c588f28ab843cee50064e350089a84` |
| alternate_witness_adoptions | `780d489b06159ec4d89c9922cd008a7f3075e394e53dbf4b2dbe7c6aca392a8e` |
| alternate_witness_unresolved | `aae222f8815f6ae0efe25da58f38570af3ac3a2bd145e62701f8bf65dd845da8` |
| watchdog | `f1aff5e4bb29b980eb3ece1644fbb86f7d1188aed20ed0bf42515a295bc48cfd` |
| review_queue | `cfb2d9fa8a8f33218cd5252319920fe75d133739ae59ed840fef17ce962685c7` |
| sanskrit_report | `071163fa59e44366d899be3e5cc03ba4bff4823d432525b36d2c0c22756fb518` |
| citation_name_report | `d7ce98afe3f3743951e98dbb3301b44e9497339858b7c7b5ba60e735c1c37880` |

Compared with `work/postprocess_wts9_final_ng_batch_20260614T065617Z`, the adoption, unresolved, watchdog, review queue, Sanskrit report, and citation/name report checksums are unchanged. The corrected text differs in 76 splitlines, all explained by the project-wide `ViśT` citation-siglum normalization.

## WtS 9-m Counts

| Metric | Current |
|---|---:|
| Entries detected | 1791 |
| Non-empty lines | 33664 |
| Validator issues | 1555 |
| Alternate-witness adoptions | 851 |
| Alternate-witness unresolved | 1135 |
| Tier A applied | 1663 |
| Tier B suggestions | 16 |
| Citation/name changes | 255 |
| Reviewed Tibetan exact changes | 93 |
| Sanskrit changes | 28 |
| Sanskrit review suggestions | 14 |
| Watchdog rows | 16 |
| Review queue rows | 16 |
| Bucket report unresolved pairs | 40 |
| Bucket report promote pairs | 0 |

Current checksums:

| Artifact | SHA-256 |
|---|---|
| corrected_full | `f8117c4bf033c5fb0e3b8c479baf984754f0d2f56d3dca0e2c38378f926dd228` |
| changes | `5f37237afd05053790417f2ff101722f19e56a7f55e6392586b03b6c5973afe9` |
| alternate_witness_adoptions | `e404266001740850f4db9e4500b3c68a1f1b5755ad0bcbfa3488e322f0b8831f` |
| alternate_witness_unresolved | `636f9311b87e1eade713c7e5c997b15a542f375cd9cbf9635d8372184eae6071` |
| watchdog | `f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c` |
| review_queue | `22d023d77fb837c984ab0cf9147c5a79beb0471edc4b42df66a32291fc199b9c` |
| sanskrit_report | `1a0a50f2f7480eabf49c115a8c325728363db4d4b810da12ec38811a0a6452b4` |
| citation_name_report | `dc522fe83cd6419c2eaf1ead4cfcff2c9cf9b9c321c3e9db2aeac20a8f40eefd` |

Compared with `work/postprocess_wts9_final_ng_batch_20260614T065617Z`, the unresolved, watchdog, review queue, Sanskrit report, and citation/name report checksums are unchanged. The corrected text differs in 65 splitlines, all explained by the project-wide `ViśT` citation-siglum normalization.

The alternate-witness adoption count changed from 853 to 851. The two removed rows were old Google-supported citation-siglum adoptions:

- p242 l6: `ViST -> VisT`
- p41 l60: `ViST -> VisT`

Current main now normalizes these directly to canonical `ViśT`, so they no longer appear as alternate-witness adoptions. No unresolved rows changed.

## Attribution Breakdown

WtS 8-b:

| Field | Count |
|---|---:|
| `alignment_method=rewrapped_page_alignment` | 3 |
| `resynchronization_attribution=direct_page_alignment` | 3 |

WtS 9-m:

| Field | Count |
|---|---:|
| `alignment_method=recovered_rewrapped_fallback` | 823 |
| `alignment_method=rewrapped_page_alignment` | 28 |
| `resynchronization_attribution=direct_recovered_rewrapped_fallback` | 823 |
| `resynchronization_attribution=direct_page_alignment` | 28 |

The WtS 9-m adoption count drop is confined to the two obsolete `ViST -> VisT` siglum adoptions. The high recovered-fallback count is unchanged in character from the previous WtS 9-m review and remains a diagnostic feature of this volume's alignment, not a new correction rule.

## Adoption Reasons

WtS 8-b:

| Reason | Count |
|---|---:|
| `alternate_witness_google_loc_fricative_upgrade` | 1 |
| `alternate_witness_google_loc_nasal_upgrade` | 1 |
| `alternate_witness_initial_i_to_l_translit` | 1 |

WtS 9-m:

| Reason | Count |
|---|---:|
| `alternate_witness_google_loc_nasal_upgrade` | 422 |
| `alternate_witness_initial_i_to_l_translit` | 238 |
| `alternate_witness_google_loc_fricative_upgrade` | 98 |
| `alternate_witness_citation_siglum` | 64 |
| `alternate_witness_google_loc_velar_nasal_upgrade` | 21 |
| `alternate_witness_google_loc_hyphenated_initial` | 5 |
| `alternate_witness_citation_cleanup` | 2 |
| `alternate_witness_strict_translit` | 1 |

## Bucket Report Status

Both current bucket reports have zero promote pairs.

No full `Vi$T`, `Vi$ST`, `Vis$T`, `VisT`, `ViST`, `VisST`, `VIST`, or `VIiST` siglum rows remain in the WtS 8-b or WtS 9-m bucket report outputs. Shorter residual rows such as `Vi$ -> Viś` can still appear as unresolved diagnostics, but those are not the already-resolved full `ViśT` citation siglum.

## Caveats

- The earlier `la'añń` item remains deferred. Both the old and proposed forms look suspect, and it should not be promoted without source/context review.
- WtS 9-m still has high recovered-rewrapped-fallback attribution. The refreshed output did not introduce a new pattern; it preserved the existing alignment behavior while reflecting the `ViśT` siglum normalization.
- The current WtS 8-b and WtS 9-m comparison shows no unexpected corrected-text differences beyond `ViśT` normalization.

## Release-Readiness Position

For WtS 8-b and WtS 9-m, the current-main postprocess bundle is consistent with the previous trusted new-volume bundle, except for the intended `ViśT` citation-siglum normalization and the resulting removal of two obsolete WtS 9-m Google adoption rows.

For the main two volumes, continue to use the trusted refined-attribution QA root:

- `work/postprocess_google_attribution_qa_refined_20260604T231518Z`

For WtS 8-b and WtS 9-m, use:

- `work/postprocess_wts8b_9m_current_main_20260618T080923Z`
