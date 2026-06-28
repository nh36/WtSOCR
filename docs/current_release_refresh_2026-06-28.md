# Current Release Refresh - 2026-06-28

## Scope

This refresh deploys the latest exact/context-gated cleanup into the tracked
`release/current` bundle. It does not loosen Google Vision adoption gates, does
not add broad OCR heuristics, and keeps base OCR authoritative.

Local output root:

`work/current_release_four_volume_refresh_20260628T075036Z`

## Promoted Cleanup

The refresh includes these reviewed corrections:

- Exact reviewed `yani -> yaṅ` rows in Tibetan contexts.
- Curated `gan`/`dan`/`yani` line overrides now normalize same-line
  Tibetan-script `ང` witnesses as `gaṅ`/`daṅ`/`yaṅ`.
- Exact reviewed WtS 1-34 page 338 line 85 `gan -> gaṅ` and `yan -> yaṅ`
  rows backed by the same-line Tibetan-script `གང`/`ཡང` witness.
- Existing `dan mthunpa` phrase override tightened to `daṅ mthun pa`.
- Tibetan-context `tin rre/ne/ñe 'dzin -> tiṅ ṅe 'dzin` phrase repair.
- Exact reviewed `Tär -> Tār` siglum rows.

All are exact or context-gated rows; no broad `ä -> ā`, nasal, or Google-gate
change was introduced.

## Postprocess Counts

| Volume | Entries | Non-empty lines | Validator issues | Google adoptions | Google unresolved | Citation changes | Reviewed Tibetan exact changes | Sanskrit changes | Sanskrit review suggestions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `wts_1_34` | 13097 | 178435 | 13255 | 5470 | 3266 | 2069 | 3 | 675 | 39 |
| `wts_35_51` | 6148 | 91855 | 4522 | 1168 | 1895 | 919 | 10 | 149 | 31 |
| `wts_8_b` | 3125 | 48290 | 2344 | 3 | 900 | 459 | 171 | 72 | 8 |
| `wts_9_m` | 1791 | 33664 | 1554 | 842 | 1134 | 276 | 283 | 89 | 10 |

## Bucket Reports

| Volume | Unresolved pairs | Promote | Hold |
| --- | ---: | ---: | ---: |
| `wts_1_34` | 203 | 10 | 193 |
| `wts_35_51` | 177 | 7 | 170 |
| `wts_8_b` | 125 | 0 | 125 |
| `wts_9_m` | 38 | 0 | 38 |

## Tibetan Script NG Witness Diagnostics

The release bundle now includes Tibetan cleanup diagnostics for all four
volumes. `tibetan_script_ng_witness_candidates.tsv` is diagnostic only: it
lists remaining Latin `n`/`ṅ` disagreements on lines that contain a
Tibetan-script `ང` witness.

| Volume | Candidate rows |
| --- | ---: |
| `wts_1_34` | 134 |
| `wts_35_51` | 15 |
| `wts_8_b` | 1 |
| `wts_9_m` | 2 |

## Verification

Commands run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py scripts/build_current_release_bundle.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result before rebuilding `release/current`:

`145 passed, 6 subtests passed in 1.77s`

## Deployment Note

`release/current` is the tracked best-current etext bundle. The `work/`
directories are local, unversioned production artifacts used to reproduce the
bundle on this machine.
