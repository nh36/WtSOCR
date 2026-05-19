# Production QA Triage - 2026-05-19

Release candidate directory: `work/production_release_candidate_20260519T145339Z/`

This note summarizes the generated QA artifacts into reviewable next steps. It does not propose any new broad OCR heuristic.

## Release Candidate

| Volume | Release candidate | SHA256 |
| --- | --- | --- |
| WtS 1-34 | `work/production_release_candidate_20260519T145339Z/final/WtS_1-34_release_candidate.txt` | `19bf4103b88d1f975024597ac3688865a409a9575cedc610e3e3f5924fa10695` |
| WtS 35-51 | `work/production_release_candidate_20260519T145339Z/final/WtS_35-51_release_candidate.txt` | `0d27126ae0cba4768eeb47ec219f0fc4bdfd9444ea12b92a07ae9c87ac924dc9` |

Inputs used:

| Volume | Base OCR | Audit CSV | Google witness |
| --- | --- | --- | --- |
| WtS 1-34 | `work/line_anchor_full_20260225T165417Z_locked/WtS_1-34/WtS 1-34_lineanchored_merged_sample.txt` | `work/line_anchor_full_20260225T165417Z_locked/WtS_1-34/WtS 1-34_lineanchored_audit.csv` | `pdfs/WtS 1-34.vision.txt` |
| WtS 35-51 | `work/line_anchor_full_20260225T165417Z_locked/WtS_35-51/WtS 35-51_lineanchored_merged_sample.txt` | `work/line_anchor_full_20260225T165417Z_locked/WtS_35-51/WtS 35-51_lineanchored_audit.csv` | `pdfs/WtS 35-51.vision.txt` |

## Current Totals

### WtS 1-34

- Scope: 1,352 pages, 180,208 lines seen, 12,014 entries detected.
- Postprocess changes: 11,197 total.
- Top change reasons: `explicit_case_sensitive_allowlist` 3,197; `explicit_user_allowlist` 2,650; `citation_siglum_confusable_map` 1,543; `confusable_dollar_to_sacute_shape_safe` 869; `confusable_nya_coda_safe` 648; `confusable_initial_I_to_l_marked_context` 504; `confusable_initial_I_to_l_lexicon` 425; `confusable_dollar_to_sacute_lexicon` 183; `confusable_hyphenated_I_to_l_translit` 157; `citation_author_lexicon` 154; `german_numeric_function_word_confusion` 147; `confusable_to_headword` 131; `sanskrit_high_freq_allowlist` 102; `tibetan_translit_phrase_allowlist` 100; `confusable_initial_I_to_l_strong_context` 87; `citation_isv_dollar_abbrev_map` 62; `confusable_dollar_to_sacute_name_anchor` 52; `confusable_initial_I_to_l_headword` 33; `citation_english_spacing_loss_map` 25; `sanskrit_char_normalize` 21.
- Review queue: 130 total. Reasons: `sanskrit_char_normalize` 59; `sanskrit_jn_cluster_contextual` 59; `discover_medium_context` 4; `confusable_context` 3; `initial_i_manual_context_review` 3; `confusable_global_lexicon` 2.
- Google alternate-witness adoptions: 38 total. Reasons: `alternate_witness_google_loc_nasal_upgrade` 15; `alternate_witness_citation_siglum` 8; `alternate_witness_google_loc_fricative_upgrade` 7; `alternate_witness_hyphenated_initial_i_to_l_translit` 3; `alternate_witness_initial_i_to_l_translit` 2; `alternate_witness_google_loc_velar_nasal_upgrade` 2; `alternate_witness_citation_cleanup` 1.
- Google adoption alignment methods: `recovered_rewrapped_page` 32; `ordinary_page_alignment` 4; `rewrapped_page_alignment` 2.
- Unresolved Google rows: 3,322 total. Reasons: `unalignable_rewrapped_page` 1,316; `token_count_mismatch` 1,105; `unsafe_token_disagreement` 507; `non_translit_context` 381; `line_count_mismatch` 9; `unalignable_page_content` 2; `nonempty_line_count_mismatch` 2.

### WtS 35-51

- Scope: 1,128 pages, 91,855 lines seen, 6,148 entries detected.
- Postprocess changes: 5,537 total.
- Top change reasons: `explicit_user_allowlist` 1,568; `explicit_case_sensitive_allowlist` 1,328; `citation_siglum_confusable_map` 709; `confusable_initial_I_to_l_lexicon` 352; `confusable_nya_coda_safe` 338; `confusable_dollar_to_sacute_shape_safe` 328; `confusable_initial_I_to_l_marked_context` 243; `confusable_initial_I_to_l_strong_context` 102; `citation_author_lexicon` 88; `confusable_hyphenated_I_to_l_translit` 69; `german_numeric_function_word_confusion` 57; `sanskrit_high_freq_allowlist` 48; `confusable_dollar_to_sacute_lexicon` 46; `german_dotless_i_safe_map` 43; `confusable_to_headword` 41; `tibetan_translit_phrase_allowlist` 31; `citation_isv_dollar_abbrev_map` 30; `citation_roman_l_to_I` 23; `sanskrit_jn_cluster_contextual` 15; `confusable_dollar_to_sacute_name_anchor` 13.
- Review queue: 48 total. Reasons: `sanskrit_jn_cluster_contextual` 31; `sanskrit_char_normalize` 11; `confusable_context` 3; `initial_i_manual_context_review` 2; `discover_medium_context` 1.
- Google alternate-witness adoptions: 1,164 total. Reasons: `alternate_witness_google_loc_nasal_upgrade` 719; `alternate_witness_initial_i_to_l_translit` 218; `alternate_witness_google_loc_fricative_upgrade` 131; `alternate_witness_citation_siglum` 47; `alternate_witness_google_loc_velar_nasal_upgrade` 40; `alternate_witness_citation_cleanup` 4; `alternate_witness_strict_translit` 3; `alternate_witness_hyphenated_initial_i_to_l_translit` 2.
- Google adoption alignment methods: `recovered_rewrapped_page` 1,086; `rewrapped_page_alignment` 77; `ordinary_page_alignment` 1.
- Unresolved Google rows: 1,893 total. Reasons: `unalignable_rewrapped_page` 931; `token_count_mismatch` 384; `unsafe_token_disagreement` 287; `non_translit_context` 259; `unalignable_page_content` 18; `nonempty_line_count_mismatch` 7; `line_count_mismatch` 7.

## Validator / Suspicious Token Triage

Source: `top_suspicious_tokens.tsv`. Counts below are the summed `count` field within the top-100 suspicious-token rows, so duplicated validator issue types for the same token can double-count a surface form.

| Bucket | Approx. count in top rows | Representative examples | Triage |
| --- | ---: | --- | --- |
| Likely Tibetan transliteration needing diacritic restoration | 8,360 | `Ita` -> `lta`, `Iha` -> `lha`, `Idan` -> `ldan`, `yañ` -> `yaṅ`, `dañ` -> `daṅ`, `$es` -> `śes` | Highest-impact future pass, but only with context gates. This bucket includes real Tibetan corrections and contexts where sigla/German prose can make a simple surface rule unsafe. |
| Possible German words / false positives | 1,576 | `Abkürzungsverzeichnisse`, `Übersetzung`, `Überlieferung`, `Rüstung`, `Bewußtsein`, `Anhänger` | Mostly validator noise, not OCR correction targets. Prefer validator/reporting suppression or zone-aware classification, not text edits. |
| Citation/siglum material | 557 | `Li$` -> `Liś`, `Y$` -> `YŚ`, `P$` -> `PŚ`, `L$dz-K` -> `Lśdz-K`, `Vi$T` -> `ViśT` | Worth a narrow whitelist-backed citation pass after manual spot checks. Avoid broad `$` rules outside known sigla/citation contexts. |
| Sanskrit or Indic forms | Not prominent in top-100 suspicious-token rows | Review queue examples include `Prajnā` -> `Prajñā`, `śrävaka` -> `śrāvaka`, `Arya-astasähasrikä` -> `Arya-astasāhasrikā` | Appears mainly in review queue, not the suspicious-token top list. Promote only lexicon-backed or exact-pattern Sanskrit fixes. |
| OCR garbage/noise | Not a top bucket in this sample | noisy digits appear in some line excerpts, not as adopted tokens | Keep manual/report-only. Do not use raw Google lines or noisy numeric context as replacement text. |
| Uncertain | 17 | `g$egs` -> `gśegs` | Needs local context review before any rule promotion. |

## Review-Queue Triage

Source: `sample_review_queue_for_manual_review.tsv` with 148 sampled rows.

Classification of sampled review items:

| Classification | Count | Notes |
| --- | ---: | --- |
| Clearly/probably good | 133 | Mostly `sanskrit_jn_cluster_contextual` and `sanskrit_char_normalize`: `Prajnapāramitā` -> `Prajñapāramitā`, `Prajnāsataka` -> `Prajñāsataka`, `Arya-astasähasrikä` -> `Arya-astasāhasrikā`. |
| Doubtful / needs local review | 8 | Mixed confusable contexts such as `siñha` -> `siṅha`, `ñwa` -> `ṅwa`, `gyañńs` -> `gyaṅńs`, and `dera-Iha` -> `dera-lha`. Some may be good, but the sample does not justify auto-application. |
| Bad if auto-applied | 7 | Examples include `Irāgheit` -> `lrāgheit`, `Irdo'i` -> `lrdo'i`, `Irgyu'i` -> `lrgyu'i`, Chinese `ch'a` -> `cha'`, and `ishod` -> `ishal`. These confirm that manual-review-only queues are doing useful work. |
| Unclear | 0 | The doubtful set is small enough for direct manual review. |

Review reasons that look safe enough for a future rule-promotion pass: `sanskrit_jn_cluster_contextual` and selected `sanskrit_char_normalize`, but only with exact Sanskrit/Indic context gates.

Review reasons that should remain manual-only for now: `discover_medium_context`, `initial_i_manual_context_review`, `confusable_global_lexicon`, and most `confusable_context`.

## Google Adoption QA

Source: `sample_google_adoptions_for_manual_review.tsv` with 138 sampled rows.

Classification of sampled Google adoptions:

| Classification | Count | Notes |
| --- | ---: | --- |
| Clearly good | 123 | Nasal, velar nasal, fricative, and initial `I` -> `l` upgrades were token-gated and consistent with surrounding transliteration, e.g. `dañ` -> `daṅ`, `bzañ` -> `bzaṅ`, `Ita` -> `lta`, `gZon` -> `gŹon`. |
| Probably good | 15 | Citation/siglum/cleanup rows such as `$PS` -> `SPS`, `Doll` -> `Dol1`, and strict transliteration rows. These are bounded and should remain spot-checkable. |
| Doubtful | 0 | No sampled doubtful Google adoption. |
| Bad | 0 | No sampled bad Google adoption. |
| Unclear | 0 | No sampled unclear Google adoption. |

The Google witness layer still looks safe in this release-candidate run. Some sampled line excerpts contain surrounding numerals or OCR noise, but no sampled adoption imported leading digit garbage or replaced a full Google line. The fallback remains token-gated.

## Pages With Many Changes

Source: `pages_with_many_changes.tsv`.

Top pages by postprocess change count:

| Volume | Top pages |
| --- | --- |
| WtS 1-34 | p404: 52; p629: 42; p403: 41; p405: 34; p54: 29; p63: 27; p59: 27; p796: 26; p928: 24; p121: 24 |
| WtS 35-51 | p690: 21; p734: 19; p683: 17; p953: 15; p729: 14; p153: 14; p674: 14; p650: 13; p434: 13; p1119: 13 |

These look like normal dense correction pages rather than suspicious overcorrection clusters. WtS 1-34 has a few concentrated pages in the 403-405 range and p629, but the page-level review queue counts remain low. WtS 35-51 is less concentrated; the highest page has 21 changes.

## Recommended Next Correction Passes

1. Target: high-frequency Tibetan transliteration confusables (`Ita`, `Iha`, `Idan`, `yañ`, `dañ`, `$es`). Approximate affected rows: 8,360 occurrences in the top suspicious-token rows alone. Worth doing because it dominates remaining validator output. Safety risk: medium. Mode: suggest-only first, then auto-apply only for tightly gated headword/transliteration contexts.
2. Target: Sanskrit/Indic review-queue normalization (`Prajna` -> `Prajñā`, `ä` -> `ā` in known Sanskrit forms). Approximate affected rows: 133 of 148 sampled review rows; 178 total review rows across both volumes are mostly Sanskrit-related. Worth doing because the sample is highly regular. Safety risk: low-to-medium. Mode: narrow auto-apply for exact lexicon-backed forms; otherwise suggest-only.
3. Target: citation/siglum `$` cleanup (`Li$`, `Y$`, `P$`, `L$dz-K`, `$PS`). Approximate affected rows: 557 occurrences in top suspicious-token rows plus existing citation adoption/change evidence. Worth doing because the forms are bounded and recurrent. Safety risk: medium if generalized. Mode: auto-apply only from a whitelist of known sigla/citation forms.
4. Target: German validator false positives. Approximate affected rows: 1,576 occurrences in the top suspicious-token rows. Worth doing because it reduces review noise without changing OCR text. Safety risk: low if implemented as reporting/validator classification only. Mode: report-only or validator suppression, not correction.
5. Target: dense-page manual QA. Approximate affected rows: top change pages listed above plus pages with high `alternate_unresolved` attention in the generated QA package. Worth doing because it checks for overcorrection clusters and page-level artifacts. Safety risk: low. Mode: manual-review only.

## Stop Condition

The release candidate is usable for manual scholarly review now: the locked base OCR remains the primary text, Google Vision is only a token-gated alternate witness, and sampled Google adoptions showed no bad cases.

Before calling this final, the main remaining work is to decide which high-frequency Tibetan confusable and Sanskrit review-queue patterns can be promoted safely. Broad Google alignment work, unresolved page-row reduction, and German validator false-positive cleanup can wait; unresolved page rows are not themselves the success metric.
