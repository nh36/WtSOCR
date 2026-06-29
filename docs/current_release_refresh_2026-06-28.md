> Historical audit record. This file is not the current to-do list. See `docs/STATUS.md` for the current operational status.

# Current Release Refresh - 2026-06-28

## Scope

This refresh deploys the latest exact/context-gated cleanup into the tracked
`release/current` bundle. It does not loosen Google Vision adoption gates, does
not add broad OCR heuristics, and keeps base OCR authoritative.

Local output root:

`work/current_release_four_volume_refresh_20260628T193714Z`

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
- Exact reviewed Initial-I/l rows, including forms such as `Ina -> lṅa`,
  `Itar -> ltar`, `Ipags -> lpags`, `Ius -> lus`, and `Ikog -> lkog`.
- Exact reviewed same-line Tibetan-script `ང` witness rows, including
  `ran -> raṅ`, `snar -> sṅar`, and the reviewed `gan dan yan` phrase as
  `gaṅ daṅ yaṅ`.

All are exact or context-gated rows; no broad `ä -> ā`, `I -> l`, `n -> ṅ`,
nasal, or Google-gate change was introduced.

## Postprocess Counts

| Volume | Entries | Non-empty lines | Validator issues | Google adoptions | Google unresolved | Citation changes | Reviewed Tibetan exact changes | Sanskrit changes | Sanskrit review suggestions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `wts_1_34` | 13122 | 178435 | 13259 | 5470 | 3266 | 2069 | 914 | 675 | 39 |
| `wts_35_51` | 6148 | 91855 | 4519 | 1168 | 1895 | 919 | 445 | 149 | 31 |
| `wts_8_b` | 3126 | 48290 | 2344 | 3 | 900 | 459 | 373 | 72 | 8 |
| `wts_9_m` | 1792 | 33664 | 1554 | 842 | 1134 | 276 | 394 | 89 | 10 |

## Bucket Reports

| Volume | Unresolved pairs | Promote | Hold |
| --- | ---: | ---: | ---: |
| `wts_1_34` | 205 | 10 | 195 |
| `wts_35_51` | 176 | 7 | 169 |
| `wts_8_b` | 125 | 0 | 125 |
| `wts_9_m` | 38 | 0 | 38 |

## Tibetan Script NG Witness Diagnostics

The release bundle now includes Tibetan cleanup diagnostics for all four
volumes. `tibetan_script_ng_witness_candidates.tsv` is diagnostic only: it
lists remaining Latin `n`/`ṅ` disagreements on lines that contain a
Tibetan-script `ང` witness.

| Volume | Candidate rows |
| --- | ---: |
| `wts_1_34` | 3 |
| `wts_35_51` | 3 |
| `wts_8_b` | 0 |
| `wts_9_m` | 0 |

The exact Initial-I/l residual diagnostic is exhausted in this bundle:
`tibetan_initial_i_residual_candidates.tsv` has no candidate rows after the
header for all four volumes.

## Verification

Commands run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py scripts/build_current_release_bundle.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result after rebuilding `release/current`:

`151 passed, 14 subtests passed`

## Deployment Note

`release/current` is the tracked best-current etext bundle. The `work/`
directories are local, unversioned production artifacts used to reproduce the
bundle on this machine.
