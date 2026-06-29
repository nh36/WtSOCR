> Historical audit record. This file is not the current to-do list. See `docs/STATUS.md` for the current operational status.

# Tibetan Initial-I and Script-NG Cleanup - 2026-06-28

## Scope

This pass promotes exact reviewed Tibetan cleanup rows found during the
four-volume release refresh. It does not add broad OCR heuristics, does not
loosen Google Vision adoption gates, and does not introduce general `I -> l`,
`n -> ṅ`, or nasal-substitution behavior.

Latest production output root:

`work/current_release_four_volume_refresh_20260628T193714Z`

## Promoted Families

### Exact Initial-I/l Rows

The pass adds 213 exact reviewed rows with reason tag
`reviewed_tibetan_exact_initial_i_l_family` and evidence
`initial_i_residual_trusted_full_twopass_20260628`.

Representative promoted forms include:

| Source | Target | Rationale |
| --- | --- | --- |
| `Ina` | `lṅa` | Tibetan lexical context; exact reviewed row. |
| `Itar` | `ltar` | Tibetan lexical context; exact reviewed row. |
| `Ipags` | `lpags` | Tibetan lexical context; exact reviewed row. |
| `Ius` | `lus` | Tibetan lexical context; exact reviewed row. |
| `Ikog` | `lkog` | Tibetan lexical context; exact reviewed row. |

### Same-Line Tibetan-Script `ང` Witness Rows

The pass adds 23 exact reviewed rows with reason tag
`reviewed_tibetan_exact_script_ng_witness` and evidence
`tibetan_script_ng_witness_trusted_full_twopass_20260628`.

Representative promoted forms include:

| Source | Target | Rationale |
| --- | --- | --- |
| `ran` | `raṅ` | Same-line Tibetan-script `ང` witness supports final `ṅ`. |
| `snar` | `sṅar` | Same-line Tibetan-script `ང` witness supports `sṅ`. |
| `gan` | `gaṅ` | Reviewed `gan dan yan` phrase with Tibetan-script `ང` witness. |
| `dan` | `daṅ` | Reviewed conjunction context with Tibetan-script `ང` witness. |
| `yan` | `yaṅ` | Reviewed phrase context with Tibetan-script `ང` witness. |

## Deferrals

The diagnostic queue still holds a small number of source-sensitive rows:

| Row | Decision |
| --- | --- |
| `wts_1_34` p338 l83 token 3 `Tgan -> Tgaṅ` | Deferred; abbreviation/noisy context needs separate review. |
| `wts_1_34` p543 l114 token 1 `dan -> daṅ` | Deferred; Tibetan script shows `དངན་འཐེན་`, so this is not the ordinary conjunction row. |
| `wts_1_34` p1111 l20 token 6 `Tdan -> Tdaṅ` | Deferred; shorthand/noisy context needs separate review. |

The same diagnostic remains source-review-only, not a rule source.

## Results

| Volume | Reviewed Tibetan exact changes | Initial-I residual rows | Script-NG residual rows |
| --- | ---: | ---: | ---: |
| `wts_1_34` | 914 | 0 | 3 |
| `wts_35_51` | 445 | 0 | 3 |
| `wts_8_b` | 373 | 0 | 0 |
| `wts_9_m` | 394 | 0 | 0 |

The tracked deployable snapshot is rebuilt through `release/current`.

## Verification

Commands:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py scripts/build_current_release_bundle.py
python3 -m pytest tests/test_tibetan_cleanup_diagnostics.py tests/test_postprocess_regressions.py -q
```

Result:

`151 passed, 14 subtests passed`
