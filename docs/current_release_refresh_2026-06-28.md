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
- Curated `gan dan yani -> gan daṅ yaṅ` line override.
- Existing `dan mthunpa` phrase override tightened to `daṅ mthun pa`.
- Tibetan-context `tin rre/ne/ñe 'dzin -> tiṅ ṅe 'dzin` phrase repair.
- Exact reviewed `Tär -> Tār` siglum rows.

All are exact or context-gated rows; no broad `ä -> ā`, nasal, or Google-gate
change was introduced.

## Postprocess Counts

| Volume | Entries | Non-empty lines | Validator issues | Google adoptions | Google unresolved | Citation changes | Reviewed Tibetan exact changes | Sanskrit changes | Sanskrit review suggestions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `wts_1_34` | 12014 | 180208 | 9365 | 38 | 3322 | 2020 | 1 | 401 | 70 |
| `wts_35_51` | 6148 | 91855 | 4522 | 1168 | 1895 | 919 | 10 | 149 | 31 |
| `wts_8_b` | 3125 | 48290 | 2344 | 3 | 900 | 459 | 171 | 72 | 8 |
| `wts_9_m` | 1791 | 33664 | 1554 | 842 | 1134 | 276 | 283 | 89 | 10 |

## Bucket Reports

| Volume | Unresolved pairs | Promote | Hold |
| --- | ---: | ---: | ---: |
| `wts_1_34` | 201 | 7 | 194 |
| `wts_35_51` | 177 | 7 | 170 |
| `wts_8_b` | 125 | 0 | 125 |
| `wts_9_m` | 38 | 0 | 38 |

## Verification

Commands run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py scripts/build_current_release_bundle.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result before rebuilding `release/current`:

`142 passed, 6 subtests passed in 1.81s`

## Deployment Note

`release/current` is the tracked best-current etext bundle. The `work/`
directories are local, unversioned production artifacts used to reproduce the
bundle on this machine.
