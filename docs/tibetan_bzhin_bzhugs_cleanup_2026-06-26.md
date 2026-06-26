# Tibetan `bźugs` / `bźin` Exact Cleanup

Date: 2026-06-26

This pass promotes exact, reviewed Tibetan ź-family corrections in WtS 8-b
and WtS 9-m. It does not add a broad `bZ`/`bz` to `bź` rule, does not
change Google Vision adoption gates, and does not use validator-only residue as
correction evidence.

`work/` outputs are local artifacts and are not versioned in the repository.

## Inputs And Outputs

- Baseline: `work/tibetan_dan_dang_phrase_batch_20260625T214120Z`
- Final run: `work/tibetan_bzhin_bzhugs_batch_20260626T090121Z`
- Override reason: `reviewed_tibetan_exact_bzhin_bzhugs`
- Evidence tag: `tibetan_bzhin_bzhugs_cleanup_20260626`

## Promoted Rows

| Volume | Source token | Target token | Rows |
| --- | --- | --- | ---: |
| WtS 8-b | `bZugs` | `bźugs` | 41 |
| WtS 8-b | `bzugs` | `bźugs` | 11 |
| WtS 8-b | `bZin` | `bźin` | 0 |
| WtS 9-m | `bZugs` | `bźugs` | 13 |
| WtS 9-m | `bzugs` | `bźugs` | 8 |
| WtS 9-m | `bZin` | `bźin` | 32 |
| **Total** |  |  | **105** |

All 105 reviewed rows applied in the final run. An initial token-index audit
caught 21 row/index mismatches; those were fixed before the final postprocess
run.

## Representative Changed Lines

| Volume | Line | Before | After |
| --- | ---: | --- | --- |
| WtS 8-b | 622 | `rlun gzun ste — yani ma 'gul bar ... bZugs pas` | `rlun gzun ste — yani ma 'gul bar ... bźugs pas` |
| WtS 8-b | 1572 | `sku yi bZugs tshugs ... srrar dan mi 'dra ba ~s` | `sku yi bźugs tshugs ... srrar dan mi 'dra ba ~s` |
| WtS 8-b | 2359 | `btsan sgam po'i sku spur gyi 'dra brrian bZugs` | `btsan sgam po'i sku spur gyi 'dra brrian bźugs` |
| WtS 8-b | 2929 | `(gZer 669,6); bZugs pa'i spyi bor chal gyis bab` | `(gZer 669,6); bźugs pa'i spyi bor chal gyis bab` |
| WtS 8-b | 3261 | `net" (Hev 1.1.22); © - rnam par bZugs nas` | `net" (Hev 1.1.22); © - rnam par bźugs nas` |
| WtS 8-b | 3429 | `bzugs pa "die vier Gottheiten usw. befinden` | `bźugs pa "die vier Gottheiten usw. befinden` |
| WtS 8-b | 4105 | `ba stag rtse na bZugs bugs "bis hin zu Dri-` | `ba stag rtse na bźugs bugs "bis hin zu Dri-` |
| WtS 8-b | 4784 | `བར་ཞུགས་ bar Zugs auch bar bZugs "dazwischen` | `བར་ཞུགས་ bar Zugs auch bar bźugs "dazwischen` |
| WtS 9-m | 862 | `bans lare ba — 09 par / Zal bzugs tsbe na` | `bans lare ba — 09 par / Zal bźugs tsbe na` |
| WtS 9-m | 1307 | `bu deon geig na bZugs "dies ist das I laupt-` | `bu deon geig na bźugs "dies ist das I laupt-` |
| WtS 9-m | 1587 | `zad son ba na ma ciglab kyi sgron ma'i bzugs` | `zad son ba na ma ciglab kyi sgron ma'i bźugs` |
| WtS 9-m | 3269 | `bzugs (metr.) "auf einem Sitzpolster sitzt` | `bźugs (metr.) "auf einem Sitzpolster sitzt` |
| WtS 9-m | 3883 | `de dag med / ma runs pa rnams bses pa bZin` | `de dag med / ma runs pa rnams bses pa bźin` |
| WtS 9-m | 4037 | `ma la ya skyes khu ba sor mos bZin la byugs` | `ma la ya skyes khu ba sor mos bźin la byugs` |
| WtS 9-m | 4186 | `bzugs so "all diese hatte er sich dem Wortlaut` | `bźugs so "all diese hatte er sich dem Wortlaut` |
| WtS 9-m | 6903 | `077 .... skyag gtad geig yan med pa bZugs so` | `077 .... skyag gtad geig yan med pa bźugs so` |

## Guardrail Counts

| Volume | Metric | Baseline | Final |
| --- | --- | ---: | ---: |
| WtS 8-b | reviewed Tibetan exact changes | 91 | 143 |
| WtS 8-b | alternate witness adoptions | 3 | 3 |
| WtS 8-b | alternate witness unresolved | 900 | 900 |
| WtS 8-b | watchdog flagged changes | 34 | 34 |
| WtS 8-b | Sanskrit review suggestions | 8 | 8 |
| WtS 8-b | tier B suggestions | 10 | 10 |
| WtS 8-b | unresolved bucket pairs | 125 | 125 |
| WtS 8-b | bucket promote rows | 0 | 0 |
| WtS 9-m | reviewed Tibetan exact changes | 209 | 262 |
| WtS 9-m | alternate witness adoptions | 842 | 842 |
| WtS 9-m | alternate witness unresolved | 1134 | 1134 |
| WtS 9-m | watchdog flagged changes | 16 | 16 |
| WtS 9-m | Sanskrit review suggestions | 10 | 10 |
| WtS 9-m | tier B suggestions | 12 | 12 |
| WtS 9-m | unresolved bucket pairs | 38 | 38 |
| WtS 9-m | bucket promote rows | 0 | 0 |

Corrected text changed lines:

- WtS 8-b: 52
- WtS 9-m: 53
- Total: 105

## Checksums

| Volume | File | SHA-256 |
| --- | --- | --- |
| WtS 8-b | corrected full text | `9a8afb1fe8c4788521e00aa07b17a4d91e5cf11ac445f8344a0dd724b2b16aa8` |
| WtS 8-b | changes TSV | `4fbcfcc7e6f446abb219010dc7f272a834c4ba80c881b8baa5dfefb51cb39459` |
| WtS 8-b | watchdog TSV | `2b04067f976caa4d551f64ec795fd5963f75f53f4c6146c5c1a452dd2b00cac6` |
| WtS 8-b | review queue TSV | `d19f785f7a3eff22059ba0ca7d49cad276e8cdb5e7dd31034415fa7b22357d1f` |
| WtS 9-m | corrected full text | `471d3d9fe85c69182569794f0529364ef2784181c217801d3ec428138c424b3e` |
| WtS 9-m | changes TSV | `4dce900f13423f6f51f7ba0a547eafb7adce0fc4c355b7ab4e8dc4eee7537ea6` |
| WtS 9-m | watchdog TSV | `f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c` |
| WtS 9-m | review queue TSV | `f3597df34a75790a0c7c448ae7c03288fc5e16926094a57cd4a58c5568e0b10b` |

## Verification

Commands:

```sh
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result:

```text
136 passed, 6 subtests passed
```

## Deferred

This pass intentionally avoids a broad `bZ`/`bz` to `bź` mechanism. Remaining
ź-like families should be reviewed as separate exact batches with local context
and guardrail counts.
