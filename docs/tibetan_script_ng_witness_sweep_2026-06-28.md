> Historical audit record. This file is not the current to-do list. See `docs/STATUS.md` for the current operational status.

# Tibetan Script NG Witness Sweep - 2026-06-28

## Purpose

This pass responds to the observation that lines such as `གང་དང་ཡང་ gan dan yaṅ`
still contained Latin `n` where the same line's Tibetan script has the letter
`ང`. The implementation remains exact and evidence-backed: it does not add a
broad `n -> ṅ` rule.

## Exact Corrections Promoted

| Source line | Corrected line | Evidence |
| --- | --- | --- |
| `གང་དང་གང་ gan dan gan Tgan gan.` | `གང་དང་གང་ gaṅ daṅ gaṅ Tgaṅ gaṅ.` | same-line Tibetan `གང`/`དང` script witness |
| `གང་དང་ཡང་ gan dan yani \gan yan.` | `གང་དང་ཡང་ gaṅ daṅ yaṅ \gaṅ yaṅ.` | same-line Tibetan `གང`/`དང`/`ཡང` script witness plus prior reviewed `yani -> yaṅ` |

## Prior Release-Refresh Confirmation

The current release-refresh pipeline already carries the previously planned
user-reported fixes:

- exact reviewed `yani -> yaṅ` rows;
- exact `dan mthunpa -> daṅ mthun pa`;
- Tibetan-context `tin rre/ne/ñe 'dzin -> tiṅ ṅe 'dzin`;
- exact reviewed `Tär -> Tār` siglum rows.

## New Diagnostic Output

`build_tibetan_cleanup_diagnostics.py` now writes
`tibetan_script_ng_witness_candidates.tsv`. It scans corrected text for exact
Latin `n`/`ṅ` disagreements only where the same line contains a Tibetan-script
`ང` witness. Rows are review candidates, not automatic corrections.

Current candidate counts:

| Volume | Candidate rows |
| --- | ---: |
| `wts_1_34` | 134 |
| `wts_35_51` | 15 |
| `wts_8_b` | 1 |
| `wts_9_m` | 2 |

## Deployed Line Check

`release/current/text/wts_1_34_corrected_full.txt` now contains:

- line 64743: `གང་དང་གང་ gaṅ daṅ gaṅ Tgaṅ gaṅ.`
- line 64744: `གང་དང་ཡང་ gaṅ daṅ yaṅ \gaṅ yaṅ.`
- line 126388: `ཆུ་དང་ལྡན་པ་ chu daṅ ldan pa mit Wasser`

## Verification

- `python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py scripts/build_current_release_bundle.py`
- `python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q`
- `python3 scripts/build_current_release_bundle.py`

Result:

- `145 passed, 6 subtests passed in 1.77s`
- `release/current` rebuilt with Tibetan cleanup diagnostic directories for all
  four volumes.
