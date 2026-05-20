# Initial I→l Population Audit

Audit source: `work/production_release_candidate_applied_audit_fix_20260520T_ingwerZ/`

This audit reviewed every applied correction in the current fixed verification output where an initial `I`/`i` token was changed to initial `l`, limited to the initial-I correction reasons and Google initial-I adoption reasons.

## Scope

| Metric | Count |
| --- | ---: |
| Applied I→l rows audited | 2,731 |
| Distinct from→to/reason groups | 477 |
| Clearly/probably good Tibetan/transliteration rows | 2,726 |
| German/prose false positives | 3 |
| Citation/proper-name risks | 2 |
| Unclear rows | 0 |

## Counts by Volume

| Volume | Rows |
| --- | ---: |
| WtS 1-34 | 1,079 |
| WtS 35-51 | 960 |
| WtS 8-b | 267 |
| WtS 9-m | 425 |

## Counts by Reason

| Reason | Rows |
| --- | ---: |
| `confusable_initial_I_to_l_marked_context` | 965 |
| `confusable_initial_I_to_l_lexicon` | 912 |
| `alternate_witness_initial_i_to_l_translit` | 459 |
| `confusable_initial_I_to_l_strong_context` | 211 |
| `confusable_hyphenated_I_to_l_translit` | 179 |
| `alternate_witness_hyphenated_initial_i_to_l_translit` | 5 |

## Top Applied Pairs

| From | To | Reason | Rows |
| --- | --- | --- | ---: |
| `Idan` | `ldan` | `confusable_initial_I_to_l_lexicon` | 620 |
| `Iha'i` | `lha'i` | `confusable_initial_I_to_l_lexicon` | 200 |
| `Ita` | `lta` | `alternate_witness_initial_i_to_l_translit` | 196 |
| `Ihun` | `lhun` | `confusable_initial_I_to_l_marked_context` | 183 |
| `Iha` | `lha` | `alternate_witness_initial_i_to_l_translit` | 100 |
| `Ihag` | `lhag` | `confusable_initial_I_to_l_marked_context` | 71 |
| `Ina'i` | `lna'i` | `confusable_initial_I_to_l_marked_context` | 71 |

These high-frequency rows are normal Tibetan transliteration corrections and should remain enabled.

## False Positives and Risks Found

| From | To | Volume/Page/Line | Classification | Excerpt |
| --- | --- | --- | --- | --- |
| `Indra'` | `lndra'` | WtS 1-34 p534 l123 | German/prose false positive | `Worte, das ist als 'Grammatik des Indra'` |
| `Indrāni` | `lndrāni` | WtS 8-b p346 l72 | German/prose false positive | `1. die Gattin Indras, skt. Indrāni.` |
| `Insekt'` | `lnsekt'` | WtS 35-51 p856 l79 | German/prose false positive | `sen, auch für das 'Insekt' Spinne" (brDa,` |
| `IS$varas` | `lSśvaras` | WtS 1-34 p895 l110 | Citation/proper-name risk | `3. Beiname IS$varas.` |
| `ITu'i` | `lTu'i` | WtS 8-b p109 l49 | Citation/proper-name risk | `kyi Ber-chun, ITu'i rGyan-gon und gTam-` |

The exact source tokens above were added to the initial-I protected-token list. This is deliberately not a broad capital-I block, because broad blocking would suppress valid Tibetan corrections such as `Ita→lta`, `Iha→lha`, and `Idan→ldan`.

## German/Prose Search

The targeted German/prose search found no applied corrections for `Ingwer`, `Indien`, `Indisch`, `Indische`, `Inder`, `Inhalt`, `Insel`, `Inner-`, `Inschrift`, `Institut`, `Interesse`, `Interpretation`, `Index`, `Initial`, `Imperativ`, or `Infinitiv`.

Observed matches for `Indien` and `Inner` were excerpt-only hits where the corrected token was a separate Tibetan transliteration token, not a German word. The previous `Ingwer` guard remains correct.

## Recommendation

Keep the initial-I correction machinery. The population is overwhelmingly Tibetan/transliteration material, and the remaining problems are a small set of exact non-Tibetan tokens. The appropriate fix is exact protection for those observed source tokens, not a broader rule.

The work-table used for this audit is:

`work/production_release_candidate_applied_audit_fix_20260520T_ingwerZ/initial_i_to_l_population_audit.tsv`
