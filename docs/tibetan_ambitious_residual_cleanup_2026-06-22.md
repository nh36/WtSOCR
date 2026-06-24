# Tibetan Ambitious Residual Cleanup - 2026-06-22

## Scope

This pass continues the WtS 8-b / WtS 9-m residual Tibetan cleanup after
`docs/tibetan_residual_context_cleanup_2026-06-22.md`.

Policy used:

- base OCR remains authoritative;
- Google Vision is corroborating evidence only;
- no Google adoption gates were loosened;
- no broad character rules were added;
- every promoted correction is exact page-line-token gated in
  `data/reviewed_tibetan_exact_overrides.tsv`;
- validator-only residue and residual Sanskrit queues were not used as correction
  evidence.

Production output:

`work/tibetan_ambitious_residual_cleanup_20260622T094238Z`

Baseline used for comparison:

`work/tibetan_residual_context_cleanup_20260622T082855Z`

## Promoted Families

### WtS 8-b

| Page | Line | From | To | Reason |
| --- | ---: | --- | --- | --- |
| 57 | 43 | gañńs | gaṅs | final nasal cleanup in Tibetan context |
| 94 | 7 | khuñń | khuṅ | final nasal cleanup in lexicon context |
| 229 | 12 | Itar | ltar | exact initial-l Tibetan reading |
| 229 | 12 | byuñń | byuṅ | final nasal cleanup in Tibetan context |
| 247 | 16 | bźiń | bźiṅ | final nasal cleanup in Tibetan context |
| 324 | 47 | khruñńs | khruṅs | final nasal cleanup in Tibetan context |
| 340 | 61 | gsañń | gsaṅ | final nasal cleanup in Tibetan context |
| 370 | 31 | bañńs | baṅs | final nasal cleanup in Tibetan context |

### WtS 9-m

| Page | Line | From | To | Reason |
| --- | ---: | --- | --- | --- |
| 52 | 67 | biens | bźens | Google-corroborated Tibetan context |
| 178 | 75 | Mu-khyuñń-rgyan | Mu-khyuṅ-rgyan | proper-name cleanup; removes residual bad final cluster |
| 198 | 32 | graris | graṅs | lexicon context, Abt. graṅs can |
| 198 | 32 | gi | gyi | same lexicon context |
| 232 | 51 | Ses | śes | śes / rnam par śes pa context |
| 233 | 20 | tab | rab | śes rab context |
| 233 | 35 | dan | daṅ | dṅos daṅ dṅos context |
| 233 | 35 | drios | dṅos | dṅos daṅ dṅos context |
| 233 | 74 | yal | yul | yul / spraṅ por context |
| 285 | 53 | dpur | dpun | dpun rgyab context |
| 318 | 32 | dari | daṅ | Tibetan connective context |
| 318 | 32 | la'añń | la'aṅ | exact local nasal cleanup |
| 343 | 34 | Zin | źiṅ | lexicon context |
| 343 | 34 | saam | sa'am | lexicon context |
| 343 | 34 | Zin | źiṅ | lexicon context |
| 343 | 34 | źinń | źiṅ | lexicon context |

## Corrected Text Diffs

### WtS 8-b

| Page | Line | Before | After |
| --- | ---: | --- | --- |
| 57 | 43 | `gañńs ti sei ~ byon "er begab sich zum Glet-` | `gaṅs ti sei ~ byon "er begab sich zum Glet-` |
| 94 | 7 | `Lex. i khuñń nam bu ga "Loch oder Offnung"` | `Lex. i khuṅ nam bu ga "Loch oder Offnung"` |
| 229 | 12 | `Itar byuñń "welche sind jene 18 Schulen, wie` | `ltar byuṅ "welche sind jene 18 Schulen, wie` |
| 247 | 16 | `bytu) zul byed de dper na chu la bya ba bźiń` | `bytu) zul byed de dper na chu la bya ba bźiṅ` |
| 324 | 47 | `mo phag gi lo la sku khruñńs "er hieß Blo` | `mo phag gi lo la sku khruṅs "er hieß Blo` |
| 340 | 61 | `gsañń ba on chen skye (metr.) "wenn man kei.` | `gsaṅ ba on chen skye (metr.) "wenn man kei.` |
| 370 | 31 | `1001); bañńs nas yar bton ~ yi mchod gnas` | `1001); baṅs nas yar bton ~ yi mchod gnas` |

### WtS 9-m

| Page | Line | Before | After |
| --- | ---: | --- | --- |
| 52 | 67 | `mes thugs dam biens pa' 'phro thams cad` | `mes thugs dam bźens pa' 'phro thams cad` |
| 178 | 75 | `beiden Brüder Khyun-po Mu-khyuṅń-rgyan` | `beiden Brüder Khyun-po Mu-khyuṅ-rgyan` |
| 198 | 32 | `Lex. tamab (Mvy 4552, Abt. graris can gi` | `Lex. tamab (Mvy 4552, Abt. graṅs can gyi` |
| 232 | 51 | `śes rnam par Ses pa rdzas $// yod dam ~ "gibt` | `śes rnam par śes pa rdzas $// yod dam ~ "gibt` |
| 233 | 20 | `śes tab — pa'i phun sum tshogs (metr.) "die` | `śes rab — pa'i phun sum tshogs (metr.) "die` |
| 233 | 35 | `anidra)' (Ahs 1.5.23d); dṅos dan drios —` | `anidra)' (Ahs 1.5.23d); dṅos daṅ dṅos —` |
| 233 | 74 | `entsteht" (KunK 55,10); yal ~ spraṅ por 'gro` | `entsteht" (KunK 55,10); yul ~ spraṅ por 'gro` |
| 285 | 53 | `(Tär 186,9); dpur rgyab kyi — źus nas "nach-` | `(Tär 186,9); dpun rgyab kyi — źus nas "nach-` |
| 318 | 32 | `dari yid chad pa la'añń "viel Glück und Leid er-` | `daṅ yid chad pa la'aṅ "viel Glück und Leid er-` |
| 343 | 34 | `Lex. Zin saam sa Zin (brDa); źinń sa (Dagy).` | `Lex. źiṅ sa'am sa źiṅ (brDa); źiṅ sa (Dagy).` |

The corrected-text diff changes 7 lines in WtS 8-b and 10 lines in WtS
9-m. The change TSV records 8 exact reviewed token changes in WtS 8-b and
16 in WtS 9-m.

## Deferrals

The following candidates were deliberately not promoted:

- WtS 9-m p52 l67 `pa' -> pa'i`: the current token layer sees the source
  token as `pa`, so this would need punctuation/apostrophe-aware handling rather
  than a safe exact token override.
- WtS 9-m p232 l51 `$// -> su`: the token layer sees the source token as `$`;
  the correction would require punctuation/slash handling and was not promoted.
- Generic dollar, slash, initial-I, and nasal repairs remain deferred. This pass
  does not add broad character substitutions.

## Counts

| Metric | WtS 8-b before | WtS 8-b after | WtS 9-m before | WtS 9-m after |
| --- | ---: | ---: | ---: | ---: |
| alternate-witness adoptions | 3 | 3 | 842 | 842 |
| alternate-witness unresolved | 900 | 900 | 1134 | 1134 |
| reviewed Tibetan exact changes | 63 | 71 | 149 | 164 |
| Sanskrit review suggestions | 1 | 1 | 1 | 1 |
| tier B suggestions | 3 | 3 | 3 | 3 |
| validator issues | 2350 | 2344 | 1555 | 1554 |
| uncaptured Tibetan prefix lines | 1134 | 1134 | 1028 | 1028 |
| watchdog rows | 31 | 31 | 16 | 16 |
| review queue rows | 3 | 3 | 3 | 3 |
| changes TSV rows | 2534 | 2542 | 1760 | 1775 |
| unresolved bucket pairs | 125 | 125 | 38 | 38 |
| bucket promote rows | 0 | 0 | 0 | 0 |

No alternate-witness adoption or unresolved counts changed. Watchdog and review
queue row counts did not increase.

## Diagnostic Counts

| Diagnostic | WtS 8-b before | WtS 8-b after | WtS 9-m before | WtS 9-m after |
| --- | ---: | ---: | ---: | ---: |
| tibetan_variant_families.tsv | 35 | 28 | 88 | 85 |
| tibetan_orthography_damage_candidates.tsv | 158 | 151 | 124 | 121 |
| tibetan_google_candidate_readings.tsv | 12 | 12 | 90 | 90 |
| tibetan_google_adoption_patterns.tsv | 3 | 3 | 239 | 239 |
| sigla_variant_candidates.tsv | 75 | 75 | 119 | 119 |
| residual_sanskrit_low_confidence_candidates.tsv | 228 | 228 | 223 | 223 |

The combined residual triage TSV moved from 361 to 351 rows.

## Checksums

```text
d306c8eeae128a53c0b6155b93691ae8c808797b74476fbbc112c914e5cbd3ff  work/tibetan_ambitious_residual_cleanup_20260622T094238Z/wts_8_b/wts_8_b_corrected_full.txt
64820e2e14302f5f8505d8e84dcc3821019f22232897584115e339066354c904  work/tibetan_ambitious_residual_cleanup_20260622T094238Z/wts_8_b/wts_8_b_changes.tsv
f1aff5e4bb29b980eb3ece1644fbb86f7d1188aed20ed0bf42515a295bc48cfd  work/tibetan_ambitious_residual_cleanup_20260622T094238Z/wts_8_b/wts_8_b_watchdog_flags.tsv
9b9108034d30df29cdbf5eecdfb76ebe112cb09882f388b55052e961767bdd6a  work/tibetan_ambitious_residual_cleanup_20260622T094238Z/wts_8_b/wts_8_b_review_queue.tsv
9bdb70838480e052f91b717878ac34d06e4d98a05c91f1ccc6e46a963de09977  work/tibetan_ambitious_residual_cleanup_20260622T094238Z/wts_9_m/wts_9_m_corrected_full.txt
192aa8aacfe4922a5543a8e592742fda61a9dbc681a54d79b3650590cdab10cb  work/tibetan_ambitious_residual_cleanup_20260622T094238Z/wts_9_m/wts_9_m_changes.tsv
f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c  work/tibetan_ambitious_residual_cleanup_20260622T094238Z/wts_9_m/wts_9_m_watchdog_flags.tsv
502a19e723b2e536cc6b25accd65731deac06c256b696538993783d696411f2a  work/tibetan_ambitious_residual_cleanup_20260622T094238Z/wts_9_m/wts_9_m_review_queue.tsv
1239ad0fda1aac6636ba1d9af7f260bdf9c4a1862504ce10d8848cf0c47a4206  work/tibetan_ambitious_residual_cleanup_20260622T094238Z/tibetan_residual_triage.tsv
```

## Verification

Commands run:

```sh
python3 -m pytest tests/test_postprocess_regressions.py -q
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/build_tibetan_residual_triage_report.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Results:

- `109 passed in 1.17s`
- py_compile passed
- `122 passed, 6 subtests passed in 1.16s`
