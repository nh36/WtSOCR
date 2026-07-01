# Tibetan Cleanup Exploratory Diagnostics

This is a diagnostics-only packet. It does not add OCR correction heuristics, does not loosen Google Vision adoption gates, and does not modify corrected text.

## Row Counts

- `tibetan_google_candidate_readings.tsv`: 90
- `tibetan_orthography_damage_candidates.tsv`: 123
- `tibetan_script_ng_witness_candidates.tsv`: 0
- `reference_marker_candidates.tsv`: 291
- `reference_marker_token_families.tsv`: 168
- `tibetan_initial_i_residual_candidates.tsv`: 0
- `sigla_variant_candidates.tsv`: 114
- `residual_sanskrit_low_confidence_candidates.tsv`: 233
- `tibetan_variant_families.tsv`: 85
- `tibetan_google_adoption_patterns.tsv`: 239

## Top Candidate Families

| Family | Sources | Targets | Count | Action |
|---|---|---|---:|---|
| dollar_ś | $ (124) | ś (124) | 124 | review |
| unknown | rol (20) | Rol (20) | 20 | siglum_policy_review |
| unknown | ins (19) | Ins (19) | 19 | siglum_policy_review |
| unknown | Lis (12), Li$ (3), LIS (1), LiS (1) | Liś (17) | 17 | siglum_policy_review |
| unknown | GS-H (5), G$-H (2), Gs-H (2) | Gś-H (9) | 9 | siglum_policy_review |
| unknown | gZ1 (7) | gZi (7) | 7 | siglum_policy_review |
| unknown | VisṬ (3), VisT (2), Vi$T (1), ViST (1) | ViśT (7) | 7 | siglum_policy_review |
| dngos_family | dnos (6) | dṅos (6) | 6 | review |
| unknown | L$dz (3), Lsdz (3) | Lśdz (6) | 6 | siglum_policy_review |
| citation_or_siglum | bZin (5) | bZin (5) | 5 | already_canonical_siglum |
| unknown | L$dz-K (3), Lsdz-K (2) | Lśdz-K (5) | 5 | siglum_policy_review |
| unknown | Viś (3), Vi$ (2) | Vis (5) | 5 | siglum_policy_review |
| citation_or_siglum | VisT (2), Vi$T (1), ViST (1) | ViśT (4) | 4 | siglum_policy_review |
| unknown | P$ (2), PS (1), Pś (1) | Ps (4) | 4 | siglum_policy_review |
| citation_or_siglum | Tär (3) | Tār (3) | 3 | already_canonical_siglum |
| google_tibetan_diacritic_disagreement | Zes (3) | źes (3) | 3 | review |
| google_tibetan_diacritic_disagreement | Zig (3) | źig (3) | 3 | review |
| unknown | gzi (3) | gZi (3) | 3 | siglum_policy_review |
| citation_or_siglum | brDa (2) | brDa (2) | 2 | already_canonical_siglum |
| citation_or_siglum | HMrg (2) | HMrg (2) | 2 | already_canonical_siglum |

## Top Google Adoption Patterns

| Reason | Base | Alternate | Count |
|---|---|---|---:|
| alternate_witness_google_loc_nasal_upgrade | dan | daṅ | 140 |
| alternate_witness_initial_i_to_l_translit | Ita | lta | 103 |
| alternate_witness_initial_i_to_l_translit | Iha | lha | 54 |
| alternate_witness_initial_i_to_l_translit | Ina | lṅa | 20 |
| alternate_witness_initial_i_to_l_translit | Idan | ldan | 15 |
| alternate_witness_google_loc_fricative_upgrade | zes | źes | 14 |
| alternate_witness_google_loc_nasal_upgrade | bzan | bzaṅ | 14 |
| alternate_witness_citation_siglum | Lis | Liś | 12 |
| alternate_witness_google_loc_nasal_upgrade | snan | snaṅ | 11 |
| alternate_witness_google_loc_nasal_upgrade | gron | groṅ | 10 |
| alternate_witness_initial_i_to_l_translit | Ihan | lhan | 9 |
| alternate_witness_google_loc_fricative_upgrade | gsegs | gśegs | 9 |
| alternate_witness_google_loc_nasal_upgrade | man | mañ | 9 |
| alternate_witness_google_loc_nasal_upgrade | nid | ñid | 9 |
| alternate_witness_initial_i_to_l_translit | Ihun | lhun | 8 |

## Interpretation

- `tibetan_google_candidate_readings.tsv` contains unresolved Google-witness disagreements that may deserve manual review.
- `tibetan_orthography_damage_candidates.tsv` scans the current corrected text directly for Tibetan-looking damage patterns.
- `tibetan_script_ng_witness_candidates.tsv` scans corrected text for exact Latin `n`/`ṅ` disagreements backed by a same-line Tibetan-script `ང` witness. It is diagnostic only; it is not a broad `n -> ṅ` rule.
- `tibetan_initial_i_residual_candidates.tsv` scans corrected text for exact known Tibetan initial-`l` forms where OCR has capital `I`. It is diagnostic only; it is not a broad `I -> l` rule.
- `reference_marker_candidates.tsv` inventories actual reference markers and likely OCR substitutes (`T`, `I`, `/`, `\`) near Tibetan transliteration contexts. It is diagnostic only; it is not a broad marker-normalisation rule.
- `sigla_variant_candidates.tsv` separates bibliography/siglum policy cases from Tibetan and Sanskrit normalisation.
- `residual_sanskrit_low_confidence_candidates.tsv` is a small exploratory queue for Sanskrit-like residue outside the previous Sanskrit watch list.
- Promotion should happen only in a later audited batch, using exact tokens and context gates.
