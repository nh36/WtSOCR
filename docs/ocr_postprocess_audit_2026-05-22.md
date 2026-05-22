# OCR Postprocess Audit - 2026-05-22

## Current Pipeline Summary
The current pipeline keeps the line-anchor/Tesseract merged text as the authoritative base. Google Vision is prepared as an alternate witness and can only contribute token-level changes after page/line alignment plus `alternate_witness_reason` safety gates. Full Google line replacement remains forbidden.

Recent commits show a sequence of narrow, test-backed changes: Google alternate-witness integration and diagnostics, guarded fallback for rewrapped Google pages, manifest-driven all-volume QA, Sanskrit exact promotions including the īśvara family, citation/siglum dollar cleanup, safe Tibetan transliteration confusable pairs, suspicious-token QA classification, manual-review packaging, and population audits for applied initial-I corrections.

In `scripts/postprocess_entry_map.py`, the main stages are: tolerant witness text loading; optional Google Vision page-marker and LoC/diacritic precleaning; alternate witness preparation and arbitration; entry parsing and line-zone classification; trusted lexicon and discovery-pattern construction; entry-aware Tier A/Tier B correction passes; citation/siglum normalization; Sanskrit normalization and reporting; stale review filtering; watchdog checks; and final TSV/JSON/text output generation.

`run_one` writes each volume into its output directory as `*_corrected_full.txt`, `*_entry_map.jsonl`, `*_line_zones.tsv`, `*_changes.tsv`, `*_review_queue.tsv`, `*_validator_issues.tsv`, `*_citation_name_report.tsv`, `*_sanskrit_report.tsv`, `*_watchdog_flags.tsv`, `*_alternate_witness_adoptions.tsv`, `*_alternate_witness_unresolved.tsv`, and `*_summary.json`. The production QA generator also writes final copied release-candidate texts, SHA256 checksums, manual-review samples, suspicious-token classification TSVs, and a Markdown QA report.

## Latest Output Directory Used
Used `work/production_release_candidate_sanskrit_isvara_recovery_20260522T163207Z` as the newest plausible all-volume production run. It contains all four ready volumes and all requested artifacts: summaries, changes, review queues, Sanskrit reports, watchdog flags, and Google adoption/unresolved TSVs.

Release-candidate checksums:
- `work/production_release_candidate_sanskrit_isvara_recovery_20260522T163207Z/final/WtS_1-34_release_candidate.txt`: `cc7618319891c41bf342187d02a571960526893fd9e019c49bc128791344a1ab`
- `work/production_release_candidate_sanskrit_isvara_recovery_20260522T163207Z/final/WtS_35-51_release_candidate.txt`: `ba33aadc7f4867efdb134190e820a916ae369fe436e5dbca079c1c15e3f75d2d`
- `work/production_release_candidate_sanskrit_isvara_recovery_20260522T163207Z/final/WtS_8-b_release_candidate.txt`: `2748722b46f9a9b361cc3dde8cadcc9a384508589079f8fd4fba2a5df5c5ff40`
- `work/production_release_candidate_sanskrit_isvara_recovery_20260522T163207Z/final/WtS_9-m_release_candidate.txt`: `e2fb058adb61d9c9ddf65af99240f3c26398d27b766c9f0f5e51ad8a928c04cc`

Audit TSVs written under `work/audit_20260522/`: `metrics_by_volume.tsv`, `reason_counts_by_volume.tsv`, `google_adoption_audit_samples.tsv`, `google_unresolved_audit_samples.tsv`, `sanskrit_normalization_audit.tsv`, `watchdog_audit.tsv`, and `release_candidate_checksums.tsv`.

## Metrics By Volume
| Volume | Entries | Non-empty lines | Validator issues | Trusted lexicon | Discovered patterns | Google used | Google adoptions | Google unresolved | Tier A | Tier B | Citation changes | Sanskrit changes | Sanskrit reviews | Watchdog flagged |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| WtS 1-34 | 12014 | 180208 | 17069 | 1347 | 51 | True | 38 | 3322 | 11330 | 22 | 1770 | 292 | 10 | 167 |
| WtS 35-51 | 6148 | 91855 | 8121 | 800 | 50 | True | 1164 | 1893 | 5577 | 15 | 828 | 124 | 9 | 71 |
| WtS 8-b | 3125 | 48290 | 3846 | 465 | 38 | True | 3 | 900 | 2396 | 15 | 402 | 40 | 13 | 31 |
| WtS 9-m | 1791 | 33664 | 2534 | 299 | 28 | True | 857 | 1131 | 1566 | 11 | 241 | 38 | 9 | 16 |

### WtS 1-34 Top Reasons
- Top Tier A reasons: [['explicit_case_sensitive_allowlist', 3197], ['explicit_user_allowlist', 2650], ['citation_siglum_confusable_map', 1546], ['confusable_dollar_to_sacute_shape_safe', 869], ['confusable_nya_coda_safe', 647], ['confusable_initial_I_to_l_marked_context', 502], ['confusable_initial_I_to_l_lexicon', 425], ['sanskrit_high_freq_allowlist', 225], ['confusable_dollar_to_sacute_lexicon', 183], ['confusable_hyphenated_I_to_l_translit', 157], ['citation_author_lexicon', 154], ['german_numeric_function_word_confusion', 147]]
- Top Tier B reasons: [['sanskrit_jn_cluster_contextual', 6], ['discover_medium_context', 4], ['sanskrit_char_normalize', 4], ['confusable_context', 3], ['initial_i_manual_context_review', 3], ['confusable_global_lexicon', 2]]
- Top validator issues: [['confusable_char', 8571], ['invalid_translit_shape', 4249], ['german_umlaut_in_translit_context', 4249]]
### WtS 35-51 Top Reasons
- Top Tier A reasons: [['explicit_user_allowlist', 1568], ['explicit_case_sensitive_allowlist', 1328], ['citation_siglum_confusable_map', 709], ['confusable_initial_I_to_l_lexicon', 352], ['confusable_nya_coda_safe', 338], ['confusable_dollar_to_sacute_shape_safe', 328], ['confusable_initial_I_to_l_marked_context', 242], ['confusable_initial_I_to_l_strong_context', 102], ['citation_author_lexicon', 88], ['sanskrit_high_freq_allowlist', 81], ['confusable_hyphenated_I_to_l_translit', 69], ['german_numeric_function_word_confusion', 57]]
- Top Tier B reasons: [['sanskrit_jn_cluster_contextual', 6], ['confusable_context', 3], ['sanskrit_char_normalize', 3], ['initial_i_manual_context_review', 2], ['discover_medium_context', 1]]
- Top validator issues: [['confusable_char', 4051], ['invalid_translit_shape', 2035], ['german_umlaut_in_translit_context', 2035]]
### WtS 8-b Top Reasons
- Top Tier A reasons: [['explicit_user_allowlist', 621], ['explicit_case_sensitive_allowlist', 573], ['citation_siglum_confusable_map', 332], ['confusable_dollar_to_sacute_shape_safe', 184], ['confusable_initial_I_to_l_marked_context', 125], ['confusable_nya_coda_safe', 83], ['confusable_initial_I_to_l_lexicon', 82], ['citation_author_lexicon', 63], ['confusable_hyphenated_I_to_l_translit', 60], ['citation_roman_l_to_I', 33], ['confusable_dollar_to_sacute_lexicon', 32], ['german_dotless_i_safe_map', 31]]
- Top Tier B reasons: [['sanskrit_jn_cluster_contextual', 10], ['sanskrit_char_normalize', 3], ['discover_medium_context', 2]]
- Top validator issues: [['confusable_char', 1718], ['invalid_translit_shape', 1064], ['german_umlaut_in_translit_context', 1064]]
### WtS 9-m Top Reasons
- Top Tier A reasons: [['explicit_user_allowlist', 507], ['explicit_case_sensitive_allowlist', 254], ['citation_siglum_confusable_map', 206], ['confusable_dollar_to_sacute_shape_safe', 117], ['confusable_initial_I_to_l_marked_context', 92], ['confusable_nya_coda_safe', 80], ['german_dotless_i_safe_map', 57], ['confusable_initial_I_to_l_lexicon', 53], ['confusable_hyphenated_I_to_l_translit', 48], ['citation_author_lexicon', 29], ['sanskrit_high_freq_allowlist', 27], ['citation_roman_l_to_I', 24]]
- Top Tier B reasons: [['sanskrit_jn_cluster_contextual', 5], ['sanskrit_char_normalize', 4], ['discover_medium_context', 1], ['confusable_context', 1]]
- Top validator issues: [['confusable_char', 1062], ['invalid_translit_shape', 736], ['german_umlaut_in_translit_context', 736]]

## Google Vision Adoption Audit
Adoption counts by reason and alignment method show that Google is acting as a token-level witness, not a replacement text. The largest adoption reasons are conservative LoC/diacritic upgrades, nasal/velar nasal upgrades, initial-I transliteration corrections, and citation/siglum fixes. Recovered rewrapped pages contribute many adoptions, but the TSV now records the alignment method and page-match metrics for each row.

- WtS 1-34 adoption reasons: alternate_witness_google_loc_nasal_upgrade=15, alternate_witness_citation_siglum=8, alternate_witness_google_loc_fricative_upgrade=7, alternate_witness_hyphenated_initial_i_to_l_translit=3, alternate_witness_initial_i_to_l_translit=2, alternate_witness_google_loc_velar_nasal_upgrade=2, alternate_witness_citation_cleanup=1
- WtS 1-34 alignment methods: recovered_rewrapped_page=32, ordinary_page_alignment=4, rewrapped_page_alignment=2
- WtS 35-51 adoption reasons: alternate_witness_google_loc_nasal_upgrade=719, alternate_witness_initial_i_to_l_translit=218, alternate_witness_google_loc_fricative_upgrade=131, alternate_witness_citation_siglum=47, alternate_witness_google_loc_velar_nasal_upgrade=40, alternate_witness_citation_cleanup=4, alternate_witness_strict_translit=3, alternate_witness_hyphenated_initial_i_to_l_translit=2
- WtS 35-51 alignment methods: recovered_rewrapped_page=1086, rewrapped_page_alignment=77, ordinary_page_alignment=1
- WtS 8-b adoption reasons: alternate_witness_google_loc_fricative_upgrade=1, alternate_witness_google_loc_nasal_upgrade=1, alternate_witness_initial_i_to_l_translit=1
- WtS 8-b alignment methods: rewrapped_page_alignment=3
- WtS 9-m adoption reasons: alternate_witness_google_loc_nasal_upgrade=426, alternate_witness_initial_i_to_l_translit=238, alternate_witness_google_loc_fricative_upgrade=98, alternate_witness_citation_siglum=66, alternate_witness_google_loc_velar_nasal_upgrade=21, alternate_witness_hyphenated_initial_i_to_l_translit=5, alternate_witness_citation_cleanup=2, alternate_witness_strict_translit=1
- WtS 9-m alignment methods: recovered_rewrapped_page=829, rewrapped_page_alignment=28

Stratified sample classifications from `work/audit_20260522/google_adoption_audit_samples.tsv`: good=101, uncertain=4.
No bad Google adoption was confirmed in the deterministic sample. Low-score and low-overlap rows were mostly classified as uncertain rather than unsafe, because they still passed token-level gates.

Manual-review priority: inspect low `page_match_score` / low `canonical_overlap` recovered-rewrapped rows first, especially where the alternate line contains digits or other OCR garbage. Do not loosen Google adoption gates based only on unresolved counts.

## Google Vision Unresolved Audit
- WtS 1-34 unresolved reasons: unalignable_rewrapped_page=1316, token_count_mismatch=1105, unsafe_token_disagreement=507, non_translit_context=381, line_count_mismatch=9, unalignable_page_content=2, nonempty_line_count_mismatch=2
- WtS 35-51 unresolved reasons: unalignable_rewrapped_page=931, token_count_mismatch=384, unsafe_token_disagreement=287, non_translit_context=259, unalignable_page_content=18, nonempty_line_count_mismatch=7, line_count_mismatch=7
- WtS 8-b unresolved reasons: unalignable_rewrapped_page=568, non_translit_context=117, token_count_mismatch=113, unsafe_token_disagreement=92, unalignable_page_content=6, line_count_mismatch=3, nonempty_line_count_mismatch=1
- WtS 9-m unresolved reasons: unsafe_token_disagreement=358, token_count_mismatch=308, non_translit_context=272, unalignable_rewrapped_page=192, unalignable_page_content=1

Unresolved sample classifications from `work/audit_20260522/google_unresolved_audit_samples.tsv`: manual-review=47, held correctly=25, alignment/manual-review=25, possible missed good reading=3.
Recurring possible missed good readings in the sample:
- `Mahävyutpatti` -> `Mahāvyutpatti` (unsafe_token_disagreement), sample count 2
- `Nyayabindutika` -> `Nyāyabinduṭīkā` (unsafe_token_disagreement), sample count 1

Recommended gate policy: only add a new Google adoption gate if a repeated pair is source-supported, context-gated, and has negative tests for German prose, citation/sigla, and unsafe transliteration contexts.

## Sanskrit Normalisation Audit
Applied Sanskrit-related changes: 490. Sanskrit review suggestions: 41. Promoted override rows loaded from `data/sanskrit_promote_overrides.tsv`: 312.
Override reasons: =312.

- WtS 1-34 top applied Sanskrit pairs: ('Nägärjuna', 'Nāgārjuna', 'sanskrit_high_freq_allowlist')=35, ('śrävakas', 'śrāvakas', 'sanskrit_high_freq_allowlist')=14, ('śrävaka', 'śrāvaka', 'sanskrit_high_freq_allowlist')=14, ('Prajnāpāramitā', 'Prajñāpāramitā', 'sanskrit_high_freq_allowlist')=10, ('śäkyamuni', 'śākyamuni', 'sanskrit_high_freq_allowlist')=9, ('śramana', 'śramaṇa', 'sanskrit_high_freq_allowlist')=7, ('Arya', 'Ārya', 'sanskrit_high_freq_allowlist')=6, ('Isvara', 'Īśvara', 'sanskrit_isvara_family_recovery')=6
- WtS 1-34 top Sanskrit review pairs: ('śrijhäna', 'śrijhāna', 'sanskrit_char_normalize')=1, ('prabhā-mandala-vyaha-jnā', 'prabhā-mandala-vyaha-jñā', 'sanskrit_jn_cluster_contextual')=1, ('śosa-räpasya', 'śosa-rāpasya', 'sanskrit_char_normalize')=1, ('Käśy', 'Kāśy', 'sanskrit_char_normalize')=1, ('parināmanavidkijnāh', 'parināmanavidkijñāh', 'sanskrit_jn_cluster_contextual')=1, ('Prajnāpāramitāfsūtras', 'Prajñāpāramitāfsūtras', 'sanskrit_jn_cluster_contextual')=1, ('śräva', 'śrāva', 'sanskrit_char_normalize')=1, ('sarvatragäminipratipajjnanabalam', 'sarvatragāminipratipajjñanabalam', 'sanskrit_jn_cluster_contextual')=1
- WtS 35-51 top applied Sanskrit pairs: ('Nägärjuna', 'Nāgārjuna', 'sanskrit_high_freq_allowlist')=8, ('Mahäsattva', 'Mahāsattva', 'sanskrit_high_freq_allowlist')=7, ('Prajnāpāramitā', 'Prajñāpāramitā', 'sanskrit_high_freq_allowlist')=7, ('Aksobhya', 'Akṣobhya', 'sanskrit_high_freq_allowlist')=4, ('samādhi', 'Samādhi', 'sanskrit_family_canonicalize')=4, ('Mahäsattvas', 'Mahāsattvas', 'sanskrit_high_freq_allowlist')=3, ('Arya', 'Ārya', 'sanskrit_high_freq_allowlist')=3, ('arya', 'ārya', 'sanskrit_high_freq_allowlist')=3
- WtS 35-51 top Sanskrit review pairs: ('Prajnāpāra', 'Prajñāpāra', 'sanskrit_jn_cluster_contextual')=1, ('pratikäülasamjnä', 'pratikāulasamjñā', 'sanskrit_jn_cluster_contextual')=1, ('sarvatathāgatavajrābhisckajniā', 'sarvatathāgatavajrābhisckajñiā', 'sanskrit_jn_cluster_contextual')=1, ('Buddhasöh', 'Buddhasoh', 'sanskrit_char_normalize')=1, ('ktijnānadarsanaskandhab', 'ktijñānadarsanaskandhab', 'sanskrit_jn_cluster_contextual')=1, ('navijnānadhātuh', 'navijñānadhātuh', 'sanskrit_jn_cluster_contextual')=1, ('ucchanganäam', 'ucchanganāam', 'sanskrit_char_normalize')=1, ('Aryaratnakäta', 'Aryaratnakāta', 'sanskrit_char_normalize')=1
- WtS 8-b top applied Sanskrit pairs: ('Prajnāpāramitā', 'Prajñāpāramitā', 'sanskrit_high_freq_allowlist')=6, ('Nägärjuna', 'Nāgārjuna', 'sanskrit_high_freq_allowlist')=5, ('śrävaka', 'śrāvaka', 'sanskrit_high_freq_allowlist')=2, ('Mahäsattva', 'Mahāsattva', 'sanskrit_high_freq_allowlist')=2, ('Mahäsattvas', 'Mahāsattvas', 'sanskrit_high_freq_allowlist')=2, ('śramana', 'śramaṇa', 'sanskrit_high_freq_allowlist')=2, ('isvara', 'īśvara', 'sanskrit_isvara_family_recovery')=2, ('Isvara', 'Īśvara', 'sanskrit_isvara_family_recovery')=2
- WtS 8-b top Sanskrit review pairs: ('Prajnāpāramitāsūtra', 'Prajñāpāramitāsūtra', 'sanskrit_jn_cluster_contextual')=2, ('sarvajnatāpragbhārab', 'sarvajñatāpragbhārab', 'sanskrit_jn_cluster_contextual')=1, ('dnantaryamärgab', 'dnantaryamārgab', 'sanskrit_char_normalize')=1, ('śäntideva', 'śāntideva', 'sanskrit_char_normalize')=1, ('indriyaparāparajnānabalam', 'indriyaparāparajñānabalam', 'sanskrit_jn_cluster_contextual')=1, ('Prajnāpāra', 'Prajñāpāra', 'sanskrit_jn_cluster_contextual')=1, ('śväsayema', 'śvāsayema', 'sanskrit_char_normalize')=1, ('sarvajnatāprāgbhārab', 'sarvajñatāprāgbhārab', 'sanskrit_jn_cluster_contextual')=1
- WtS 9-m top applied Sanskrit pairs: ('Aksobhya', 'Akṣobhya', 'sanskrit_high_freq_allowlist')=9, ('Nägärjuna', 'Nāgārjuna', 'sanskrit_high_freq_allowlist')=5, ('aksobhya', 'akṣobhya', 'sanskrit_high_freq_allowlist')=5, ('Isvaras', 'Īśvaras', 'sanskrit_isvara_family_recovery')=3, ('prajnāyate', 'prajñāyate', 'sanskrit_high_freq_allowlist')=2, ('Iśvaras', 'Īśvaras', 'sanskrit_isvara_family_recovery')=1, ('jnäne', 'jñāne', 'sanskrit_jn_cluster_contextual')=1, ('Mahājnāna', 'Mahājñāna', 'sanskrit_jn_cluster_context_gate')=1
- WtS 9-m top Sanskrit review pairs: ('śinaväsika', 'śinavāsika', 'sanskrit_char_normalize')=1, ('Prajnapāramitāsiitra', 'Prajñapāramitāsiitra', 'sanskrit_jn_cluster_contextual')=1, ('rvijnānadhātub', 'rvijñānadhātub', 'sanskrit_jn_cluster_contextual')=1, ('anantäparyantab', 'anantāparyantab', 'sanskrit_char_normalize')=1, ('Vaiśvänara', 'Vaiśvānara', 'sanskrit_char_normalize')=1, ('Jnānagarbha', 'Jñānagarbha', 'sanskrit_jn_cluster_contextual')=1, ('śräva', 'śrāva', 'sanskrit_char_normalize')=1, ('buddhajnanāadhyalambanatāyii', 'buddhajñanāadhyalambanatāyii', 'sanskrit_jn_cluster_contextual')=1

Sanskrit audit classifications from `work/audit_20260522/sanskrit_normalization_audit.tsv`: needs human review=885, safe to keep/promote=366, suspicious/hold=7.
The Sanskrit layer is mostly exact or context-gated: promoted high-frequency allowlist forms, jn/jñ contextual fixes, char normalization such as ä/ā and dotless ı/i, and the recent īśvara-family recovery. Remaining Sanskrit review suggestions should be handled family-by-family, not with broad character substitutions.

Specific watch areas: avoid treating Tibetan transliteration strings as Sanskrit; avoid changing German compounds containing Sanskrit-looking substrings; keep `$ -> ś`, `ä -> ā`, dotless `ı -> i`, final `ḥ`, and anusvāra fixes exact/context-backed.

## Watchdog/Safety Audit
- WtS 1-34 watchdog flags: high_edit_distance_drift=167
- WtS 1-34 watchdog reasons: german_numeric_function_word_confusion=147, citation_isv_dollar_abbrev_map=20
- WtS 35-51 watchdog flags: high_edit_distance_drift=71
- WtS 35-51 watchdog reasons: german_numeric_function_word_confusion=57, citation_isv_dollar_abbrev_map=14
- WtS 8-b watchdog flags: high_edit_distance_drift=31
- WtS 8-b watchdog reasons: german_numeric_function_word_confusion=30, citation_isv_dollar_abbrev_map=1
- WtS 9-m watchdog flags: high_edit_distance_drift=16
- WtS 9-m watchdog reasons: german_numeric_function_word_confusion=15, citation_isv_dollar_abbrev_map=1

Watchdog rows written to `work/audit_20260522/watchdog_audit.tsv`: 285 total, 0 marked serious/manual-review by this audit script.
The hard guards are doing useful work: they surface high-risk shape changes for manual review without automatically proving the correction is bad. Any Tier A row with serious flags should be manually sampled before expanding the corresponding rule family.

## Bad Readings Found
- No bad Google adoption was confirmed in the current deterministic sample.
- Sanskrit audit has 7 suspicious/hold rows, mostly review suggestions or prose-like contexts; these are not automatic approvals.
- Prior applied-correction audits already found and narrowed the initial-I false-positive family, including German/prose protection and the IS$varas/ITu'i edge-case handling.

## Good Readings Currently Missed
The unresolved Google sample contains possible good readings, but no new family was strong enough for an immediate automatic gate. Candidate future work should start from repeated unresolved pairs with source evidence and add one exact/context-gated family at a time.

For Sanskrit, the remaining review queue and `*_sanskrit_report.tsv` rows are the best source of future safe promotions. The next likely Sanskrit pass should target one family only, such as a specific `śāstra`, `prajñā`, `īśvara`-adjacent, final `ḥ`, or anusvāra pattern if the report shows repeated exact forms with consistent context.

## Recommended Next Code Changes
1. Do not loosen Google alignment or adoption gates. If changing Google behaviour, start with a report-only sample of recurring unresolved pairs and promote only one exact family with negative tests.
2. Add a small reviewer-facing report for serious watchdog rows by reason and page, because this is now the cleanest way to find overcorrections.
3. Continue Sanskrit recovery family-by-family using exact overrides and context gates; the next code change should be based on a full-population audit of one Sanskrit family, not a general character rule.
4. Keep initial-I-to-l broadening off the table. It has already produced the clearest false-positive risk, so only exact protected tokens or exact source-supported title/name cases should be changed.
5. If machine-readability becomes the next target, separate that from OCR correction: build structured entry extraction and bibliographic/siglum normalization as a downstream parser, not as OCR text rewriting.

## Recommended Manual-Review Tasks
1. Review `watchdog_audit.tsv` serious/manual-review rows, starting with high-volume reasons and dense pages.
2. Review low-score and low-overlap Google adoption samples, especially `recovered_rewrapped_page` rows with noisy alternate lines.
3. Review unresolved Google rows classified as possible missed good readings before adding any new adoption family.
4. Review remaining Sanskrit queue rows family-by-family and decide whether each is exact-promotable, review-only, or suspicious/hold.
5. Review dense-page excerpts from the manual package; dense pages are more likely to expose mechanical overcorrection or alignment drift.

## Distance From Clean OCR Text
The current output is usable for manual scholarly review: four volumes are covered, QA noise is classified, Google witness adoptions are token-gated and attributable, and recent audits have narrowed the most obvious overcorrection family. It is not yet final clean OCR text because watchdog rows, Sanskrit review suggestions, unresolved Google disagreements, and dense-page clusters still need targeted review.

## Distance From A Machine-Readable Dictionary
The project is farther from a genuinely machine-readable dictionary than from clean readable OCR. The postprocess pipeline now produces strong corrected text plus line zones and entry IDs, but full machine readability will require reliable structured entry parsing, headword/sense segmentation, bibliographic/siglum semantics, German gloss parsing, and durable identifiers. Those should be built as a downstream data-extraction layer after OCR correction stabilizes.

