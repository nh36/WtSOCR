# Tibetan `dan` -> `daṅ` Phrase Batch

Date: 2026-06-25

## Purpose

This batch resolves a recurring subset of the Tibetan transliteration
`dan` -> `daṅ` residue by promoting exact phrase families whose local
context is Tibetan. It does not add a standalone `dan` rewrite, does not
loosen Google Vision adoption gates, and does not introduce a broad nasal
repair rule.

The implementation extends the existing
`tibetan_translit_phrase_allowlist` mechanism in `scripts/postprocess_entry_map.py`.
That mechanism only runs when the line passes the Tibetan direct-phrase
context gate.

## Inputs And Outputs

Baseline local output:

- `work/tibetan_second_ambitious_cleanup_20260624T212313Z`

New local output:

- `work/tibetan_dan_dang_phrase_batch_20260625T214120Z`

The `work/` directories are local artifacts and are not versioned in the
repository.

## Promoted Phrase Families

The promoted families are exact phrase patterns, not character-level rules.

| family | WtS 8-b added rows | WtS 9-m added rows |
|---|---:|---:|
| `dan 'dra` -> `daṅ 'dra` | 21 | 15 |
| `dan bcas pa` -> `daṅ bcas pa` | 16 | 2 |
| `dan bcas pa'i` -> `daṅ bcas pa'i` | 3 | 2 |
| `dan bcas pas` -> `daṅ bcas pas` | 2 | 1 |
| `dan bcas par` -> `daṅ bcas par` | 2 | 1 |
| `dan bcas kyi` -> `daṅ bcas kyi` | 0 | 1 |
| `dan bral ba` -> `daṅ bral ba` | 4 | 4 |
| `dan bral ba'i` -> `daṅ bral ba'i` | 2 | 3 |
| `dan bral bas` -> `daṅ bral bas` | 0 | 1 |
| `dan lhan cig` -> `daṅ lhan cig` | 1 | 3 |
| `dan mthun pa` -> `daṅ mthun pa` | 5 | 1 |
| `dan mthun par` -> `daṅ mthun par` | 2 | 0 |
| `dan mthun pas` -> `daṅ mthun pas` | 0 | 0 |
| `dan mthunpa` -> `daṅ mthunpa` | 0 | 0 |
| `dan ldan pa'i` -> `daṅ ldan pa'i` | 3 | 3 |
| `dan ldan pas` -> `daṅ ldan pas` | 1 | 2 |
| `dan ldan par` -> `daṅ ldan par` | 4 | 1 |

Focused phrase-allowlist rows increased from 16 to 79 in WtS 8-b and
from 9 to 46 in WtS 9-m. The net focused increase is therefore 63 rows
for WtS 8-b and 37 rows for WtS 9-m.

## Representative Examples

WtS 8-b examples:

| page | line | before | after |
|---:|---:|---|---|
| 25 | 57 | `rus pa'am / - la gzugs su brkos pa dan 'dra` | `rus pa'am / - la gzugs su brkos pa daṅ 'dra` |
| 26 | 4 | `dan bcas pa achtsam; ~ dañ ldan pa unbeirrt.` | `daṅ bcas pa achtsam; ~ dañ ldan pa unbeirrt.` |
| 26 | 7 | `dan bcas pa'i las kyis` | `daṅ bcas pa'i las kyis` |
| 31 | 54 | `... dan igs pa dan bcas par` | `... dan igs pa daṅ bcas par` |
| 59 | 10 | `... yani de dan 'dra'o` | `... yani de daṅ 'dra'o` |
| 79 | 27 | `... 'khor beu drug dan bcas pa ...` | `... 'khor beu drug daṅ bcas pa ...` |

WtS 9-m examples:

| page | line | before | after |
|---:|---:|---|---|
| 6 | 35 | `dan bcas pa "die Gottheit Hāriti...` | `daṅ bcas pa "die Gottheit Hāriti...` |
| 25 | 47 | `- khrani dan bcas pa 'dis ...` | `- khrani daṅ bcas pa 'dis ...` |
| 33 | 42 | `... 'khor dan bcas pas bsu ba...` | `... 'khor daṅ bcas pas bsu ba...` |
| 65 | 22 | `dan bral ba'i gdun ba...` | `daṅ bral ba'i gdun ba...` |
| 77 | 14 | `dod pa dan 'dra la...` | `dod pa daṅ 'dra la...` |
| 79 | 73 | `- dan lhan cig ...` | `- daṅ lhan cig ...` |

## Guardrail Counts

| output | WtS 8-b | WtS 9-m |
|---|---:|---:|
| alternate-witness adoptions | 3 | 842 |
| alternate-witness unresolved | 900 | 1134 |
| unresolved bucket pairs | 125 | 38 |
| unresolved bucket promote rows | 0 | 0 |
| reviewed Tibetan exact changes | 91 | 209 |
| Sanskrit changes | 72 | 89 |
| Sanskrit review suggestions | 8 | 10 |

The alternate-witness adoption and unresolved row counts did not change
from the baseline output. Google Vision remains an alternate witness only.

Compared with the older baseline output directory, WtS 8-b has three
additional watchdog rows and both volumes have additional Sanskrit review
queue rows. Those are current-main rerun effects from earlier exact
cleanup work, not consequences of the `dan` phrase-family changes.

## Checksums

WtS 8-b:

| file | rows | sha256 |
|---|---:|---|
| `wts_8_b_corrected_full.txt` | - | `11a8b13ee6bea007ba3db29fa642b6b666ced7d18eedf400369ab981061eb8a8` |
| `wts_8_b_changes.tsv` | 2641 | `c415135939400ef3dbd88c86a3372372ef4f528f6c5c27fec196bd58d789e45d` |
| `wts_8_b_watchdog_flags.tsv` | 34 | `2b04067f976caa4d551f64ec795fd5963f75f53f4c6146c5c1a452dd2b00cac6` |
| `wts_8_b_review_queue.tsv` | 10 | `d19f785f7a3eff22059ba0ca7d49cad276e8cdb5e7dd31034415fa7b22357d1f` |
| `wts_8_b_alternate_witness_adoptions.tsv` | 3 | `780d489b06159ec4d89c9922cd008a7f3075e394e53dbf4b2dbe7c6aca392a8e` |
| `wts_8_b_alternate_witness_unresolved.tsv` | 900 | `aae222f8815f6ae0efe25da58f38570af3ac3a2bd145e62701f8bf65dd845da8` |

WtS 9-m:

| file | rows | sha256 |
|---|---:|---|
| `wts_9_m_corrected_full.txt` | - | `9df2413bf258c82a8d79eb665dded51c737b0a4e8ef7d7c72ab2ae2d79efd4cc` |
| `wts_9_m_changes.tsv` | 1898 | `3b388a809f75548b90ef337f9b048919bc23e544183e8ae386460ebb3efc0121` |
| `wts_9_m_watchdog_flags.tsv` | 16 | `f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c` |
| `wts_9_m_review_queue.tsv` | 12 | `f3597df34a75790a0c7c448ae7c03288fc5e16926094a57cd4a58c5568e0b10b` |
| `wts_9_m_alternate_witness_adoptions.tsv` | 842 | `ebe47ca9a4e8e1b15f7b8287fc6c465d593080e35b597493117487543ddd97b4` |
| `wts_9_m_alternate_witness_unresolved.tsv` | 1134 | `79a3dce4ee4f4caebe07e3af277c01af00732f0480d35a2c6e7175b566e59481` |

## Verification

Commands:

```sh
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_four_volume_residual_error_ledger.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_four_volume_residual_error_ledger.py -q
```

Result before commit: `124 passed`.
