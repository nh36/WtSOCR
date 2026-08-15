# Tibetan Cleanup Exploratory Diagnostics

This is a diagnostics-only packet. It does not add OCR correction heuristics, does not loosen Google Vision adoption gates, and does not modify corrected text.

## Row Counts

- `tibetan_google_candidate_readings.tsv`: 81
- `tibetan_orthography_damage_candidates.tsv`: 87
- `guarded_dollar_to_sacute_candidates.tsv`: 476
- `tibetan_script_ng_witness_candidates.tsv`: 0
- `reference_marker_candidates.tsv`: 858
- `reference_marker_token_families.tsv`: 353
- `tibetan_initial_i_residual_candidates.tsv`: 0
- `sigla_variant_candidates.tsv`: 285
- `residual_sanskrit_low_confidence_candidates.tsv`: 663
- `tibetan_variant_families.tsv`: 183
- `tibetan_google_adoption_patterns.tsv`: 313

## Top Candidate Families

| Family | Sources | Targets | Count | Action |
|---|---|---|---:|---|
| guarded_dollar_to_sacute | $ (376) | ś (376) | 376 | defer |
| unknown | rol (92) | Rol (92) | 92 | siglum_policy_review |
| unknown | ins (42) | Ins (42) | 42 | siglum_policy_review |
| unknown | Lis (33), Li$ (6), lis (3) | Liś (42) | 42 | siglum_policy_review |
| unknown | VisT (19), ViST (7), VisṬ (1) | ViśT (27) | 27 | siglum_policy_review |
| guarded_dollar_to_sacute | $77 (15) | ś77 (15) | 15 | defer |
| unknown | Gs-H (10), GS-H (1) | Gś-H (11) | 11 | siglum_policy_review |
| guarded_dollar_to_sacute | $7 (10) | ś7 (10) | 10 | defer |
| unknown | gs (9), g$ (1) | Gs (10) | 10 | siglum_policy_review |
| unknown | Y$ (5), Ys (4), YŚ (1) | Yś (10) | 10 | siglum_policy_review |
| guarded_dollar_to_sacute | $5 (9) | ś5 (9) | 9 | defer |
| unknown | Bu-Sz (9) | Bu-śz (9) | 9 | siglum_policy_review |
| guarded_dollar_to_sacute | 0$ (8) | 0ś (8) | 8 | defer |
| unknown | gzi (8) | gZi (8) | 8 | siglum_policy_review |
| unknown | P$ (4), PS (3), ps (1) | Ps (8) | 8 | siglum_policy_review |
| loc_nasal_damage | bźeńs (7) | bźeṅs (7) | 7 | review |
| loc_nasal_damage | nań (7) | naṅ (7) | 7 | review |
| unknown | Lsdz-K (6), L$dz-K (1) | Lśdz-K (7) | 7 | siglum_policy_review |
| unknown | Viś (5), Vi$ (2) | Vis (7) | 7 | siglum_policy_review |
| guarded_dollar_to_sacute | 9$ (6) | 9ś (6) | 6 | defer |

## Top Google Adoption Patterns

| Reason | Base | Alternate | Count |
|---|---|---|---:|
| alternate_witness_google_loc_nasal_upgrade | dan | daṅ | 211 |
| alternate_witness_initial_i_to_l_translit | Ita | lta | 93 |
| alternate_witness_initial_i_to_l_translit | Iha | lha | 45 |
| alternate_witness_google_loc_nasal_upgrade | bzan | bzaṅ | 25 |
| alternate_witness_google_loc_nasal_upgrade | dban | dbaṅ | 24 |
| alternate_witness_google_loc_nasal_upgrade | nid | ñid | 18 |
| alternate_witness_google_loc_velar_nasal_upgrade | dañ | daṅ | 16 |
| alternate_witness_google_loc_nasal_upgrade | kyan | kyaṅ | 15 |
| alternate_witness_citation_siglum | Lis | Liś | 14 |
| alternate_witness_google_loc_nasal_upgrade | ran | raṅ | 14 |
| alternate_witness_google_loc_nasal_upgrade | ston | stoṅ | 14 |
| alternate_witness_google_loc_fricative_upgrade | gsegs | gśegs | 13 |
| alternate_witness_initial_i_to_l_translit | Idan | ldan | 12 |
| alternate_witness_google_loc_fricative_upgrade | bzin | bźin | 11 |
| alternate_witness_initial_i_to_l_translit | Iha'i | lha'i | 11 |

## Interpretation

- `tibetan_google_candidate_readings.tsv` contains unresolved Google-witness disagreements that may deserve manual review.
- `tibetan_orthography_damage_candidates.tsv` scans the current corrected text directly for Tibetan-looking damage patterns.
- `guarded_dollar_to_sacute_candidates.tsv` scans current corrected text for exact `$ -> ś` candidates and explicitly blocks sigla, numeric/noise, Sanskrit, German/prose, and weak-context rows.
- `tibetan_script_ng_witness_candidates.tsv` scans corrected text for exact Latin `n`/`ṅ` disagreements backed by a same-line Tibetan-script `ང` witness. It is diagnostic only; it is not a broad `n -> ṅ` rule.
- `tibetan_initial_i_residual_candidates.tsv` scans corrected text for exact known Tibetan initial-`l` forms where OCR has capital `I`. It is diagnostic only; it is not a broad `I -> l` rule.
- `reference_marker_candidates.tsv` inventories actual reference markers and likely OCR substitutes (`T`, `I`, `/`, `\`) near Tibetan transliteration contexts. It is diagnostic only; it is not a broad marker-normalisation rule.
- `sigla_variant_candidates.tsv` separates bibliography/siglum policy cases from Tibetan and Sanskrit normalisation.
- `residual_sanskrit_low_confidence_candidates.tsv` is a small exploratory queue for Sanskrit-like residue outside the previous Sanskrit watch list.
- Promotion should happen only in a later audited batch, using exact tokens and context gates.
