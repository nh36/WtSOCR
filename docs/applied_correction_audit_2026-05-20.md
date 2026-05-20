# Applied Correction Audit, 2026-05-20

Scope: applied postprocess changes and Google alternate-witness adoptions in `work/production_release_candidate_clean_qa_20260520T055946Z/`.

Sample output: `work/production_release_candidate_clean_qa_20260520T055946Z/applied_correction_audit_sample.tsv`.

## Summary

The audit reviewed automatic corrections that had already been applied, rather than residual validator warnings. Across the four release-candidate volumes there were 22,908 applied rows: 20,846 postprocess changes and 2,062 Google alternate-witness adoptions.

The stratified audit sample contained 695 rows:

| Classification | Count |
| --- | ---: |
| clearly good | 135 |
| probably good | 555 |
| doubtful | 0 |
| bad | 5 |
| unclear | 0 |

All five bad rows were the same pattern: German `Ingwer` was changed to `lngwer` by `confusable_initial_I_to_l_strong_context`. No sampled Sanskrit, citation/siglum, dollar-to-sacute, nya/ng, Tibetan exact-confusable, or Google alternate-witness adoption showed a bad correction pattern.

## Applied Reasons

Top applied reasons, including Google adoption reasons:

| Reason | Count | Volume distribution |
| --- | ---: | --- |
| explicit_case_sensitive_allowlist | 5352 | WtS 1-34: 3197; WtS 35-51: 1328; WtS 8-b: 573; WtS 9-m: 254 |
| explicit_user_allowlist | 5346 | WtS 1-34: 2650; WtS 35-51: 1568; WtS 8-b: 621; WtS 9-m: 507 |
| citation_siglum_confusable_map | 2793 | WtS 1-34: 1546; WtS 35-51: 709; WtS 8-b: 332; WtS 9-m: 206 |
| confusable_dollar_to_sacute_shape_safe | 1498 | WtS 1-34: 869; WtS 35-51: 328; WtS 8-b: 184; WtS 9-m: 117 |
| alternate_witness_google_loc_nasal_upgrade | 1161 | WtS 1-34: 15; WtS 35-51: 719; WtS 8-b: 1; WtS 9-m: 426 |
| confusable_nya_coda_safe | 1148 | WtS 1-34: 647; WtS 35-51: 338; WtS 8-b: 83; WtS 9-m: 80 |
| confusable_initial_I_to_l_marked_context | 965 | WtS 1-34: 504; WtS 35-51: 243; WtS 8-b: 126; WtS 9-m: 92 |
| confusable_initial_I_to_l_lexicon | 912 | WtS 1-34: 425; WtS 35-51: 352; WtS 8-b: 82; WtS 9-m: 53 |
| alternate_witness_initial_i_to_l_translit | 459 | WtS 1-34: 2; WtS 35-51: 218; WtS 8-b: 1; WtS 9-m: 238 |
| sanskrit_high_freq_allowlist | 363 | WtS 1-34: 225; WtS 35-51: 81; WtS 8-b: 30; WtS 9-m: 27 |
| confusable_hyphenated_I_to_l_translit | 334 | WtS 1-34: 157; WtS 35-51: 69; WtS 8-b: 60; WtS 9-m: 48 |
| citation_author_lexicon | 334 | WtS 1-34: 154; WtS 35-51: 88; WtS 8-b: 63; WtS 9-m: 29 |
| confusable_dollar_to_sacute_lexicon | 261 | WtS 1-34: 183; WtS 35-51: 46; WtS 8-b: 32 |
| german_numeric_function_word_confusion | 249 | WtS 1-34: 147; WtS 35-51: 57; WtS 8-b: 30; WtS 9-m: 15 |
| alternate_witness_google_loc_fricative_upgrade | 237 | WtS 1-34: 7; WtS 35-51: 131; WtS 8-b: 1; WtS 9-m: 98 |
| confusable_to_headword | 216 | WtS 1-34: 131; WtS 35-51: 41; WtS 8-b: 28; WtS 9-m: 16 |
| confusable_initial_I_to_l_strong_context | 216 | WtS 1-34: 87; WtS 35-51: 102; WtS 8-b: 22; WtS 9-m: 5 |
| tibetan_translit_phrase_allowlist | 156 | WtS 1-34: 100; WtS 35-51: 31; WtS 8-b: 16; WtS 9-m: 9 |
| german_dotless_i_safe_map | 141 | WtS 1-34: 10; WtS 35-51: 43; WtS 8-b: 31; WtS 9-m: 57 |
| alternate_witness_citation_siglum | 121 | WtS 1-34: 8; WtS 35-51: 47; WtS 9-m: 66 |

## Bad Examples

All bad examples were German `Ingwer` in lines that otherwise had Tibetan transliteration context:

| Volume | Page | Line | Reason | Bad change | Excerpt |
| --- | ---: | ---: | --- | --- | --- |
| WtS 1-34 | 489 | 18 | confusable_initial_I_to_l_strong_context | Ingwer -> lngwer | `གྒ་ ?sga auch lga Ingwer.` |
| WtS 1-34 | 492 | 6 | confusable_initial_I_to_l_strong_context | Ingwer -> lngwer | `སྒེའུ་གཤེར་ sge'u ger frischer Ingwer.` |
| WtS 1-34 | 569 | 79 | confusable_initial_I_to_l_strong_context | Ingwer -> lngwer | `རྫོ་སྒ་ sro sga eine Pflanze, frischer Ingwer` |
| WtS 1-34 | 1253 | 12 | confusable_initial_I_to_l_strong_context | Ingwer -> lngwer | `དོང་ཀྲ་ doṅ kra auch don gra eine Art Ingwer;` |
| WtS 8-b | 337 | 21 | confusable_initial_I_to_l_strong_context | Ingwer -> lngwer | `Atemnot [helfen] bharghi und Ingwer" (༽༼` |

## Fix Applied

The correction rule was not broadened. The fix protects exact German `Ingwer` as an initial-I German word before the initial `I` to `l` transliteration correction can apply. A regression test covers `frischer Ingwer` in a Tibetan/transliteration line.

Verification output: `work/production_release_candidate_applied_audit_fix_20260520T_ingwerZ/`.

| Volume | Old checksum | New checksum | Old changes | New changes | Ingwer -> lngwer old/new |
| --- | --- | --- | ---: | ---: | ---: |
| WtS 1-34 | `351ab94f9077154774d76a0713dc9cfb8b1afa07922d1a8b85659f923c5618ab` | `77d5523d5c2c1426552a7e708cb0285449e0e4a691ea694c6cdec1c5ce2e179f` | 11322 | 11318 | 4 / 0 |
| WtS 35-51 | `331bad50324699db9d55eeddcf187b4c8e8508757242862beb1b6af88f07f312` | `331bad50324699db9d55eeddcf187b4c8e8508757242862beb1b6af88f07f312` | 5570 | 5570 | 0 / 0 |
| WtS 8-b | `586200174fcd73d79031010ae3ee9b757ec81de765dd14e2e198c993d6a3eb3f` | `a14ac4708f8eea878fc280a2a915c8e7e9c8951888da3c3528bad134ba8a1ccc` | 2393 | 2392 | 1 / 0 |
| WtS 9-m | `a3fd725816b37bb16730218d56dde73955468ccae7ef76cb31973b42801001d9` | `a3fd725816b37bb16730218d56dde73955468ccae7ef76cb31973b42801001d9` | 1561 | 1561 | 0 / 0 |

Review queue totals, Google adoption totals, unresolved Google rows, and watchdog rows were unchanged in the verification run.

## Recommendations

Keep the current Sanskrit, citation/siglum, dollar-to-sacute, nya/ng, Tibetan exact-confusable, and Google alternate-witness correction rules. The sampled rows for those categories were clearly or probably good, with no bad or doubtful examples.

The only rule that needed narrowing was `confusable_initial_I_to_l_strong_context`, and the observed problem was an exact German lexical false positive rather than a broad failure of the initial-I guard. Continue treating initial `I` to `l` as a high-attention family in manual QA, but no broader rollback is indicated by this audit.
