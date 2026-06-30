# Tibetan Cleanup Exploratory Diagnostics

This is a diagnostics-only packet. It does not add OCR correction heuristics, does not loosen Google Vision adoption gates, and does not modify corrected text.

## Row Counts

- `tibetan_google_candidate_readings.tsv`: 357
- `tibetan_orthography_damage_candidates.tsv`: 1606
- `tibetan_script_ng_witness_candidates.tsv`: 1
- `tibetan_initial_i_residual_candidates.tsv`: 0
- `sigla_variant_candidates.tsv`: 775
- `residual_sanskrit_low_confidence_candidates.tsv`: 1630
- `tibetan_variant_families.tsv`: 762
- `tibetan_google_adoption_patterns.tsv`: 633

## Top Candidate Families

| Family | Sources | Targets | Count | Action |
|---|---|---|---:|---|
| dollar_ś | $ (902) | ś (902) | 902 | review |
| unknown | Lis (153), Li$ (42), lis (6) | Liś (201) | 201 | siglum_policy_review |
| unknown | rol (145) | Rol (145) | 145 | siglum_policy_review |
| unknown | VisT (90), VisṬ (4), ViST (2), ViśṬ (1), Vi$T (1) | ViśT (98) | 98 | siglum_policy_review |
| unknown | ins (85), INS (1) | Ins (86) | 86 | siglum_policy_review |
| unknown | Lsdz-K (33), L$dz-K (13) | Lśdz-K (46) | 46 | siglum_policy_review |
| unknown | Y$ (23), Ys (16) | Yś (39) | 39 | siglum_policy_review |
| dngos_family | dnos (38) | dṅos (38) | 38 | exact_promotion_candidate |
| unknown | gs (24), G$ (3), Gś (2) | Gs (29) | 29 | siglum_policy_review |
| unknown | gzi (28) | gZi (28) | 28 | siglum_policy_review |
| unknown | Lsdz (16), L$dz (10) | Lśdz (26) | 26 | siglum_policy_review |
| unknown | Bu-Sz (16) | Bu-śz (16) | 16 | siglum_policy_review |
| dotless_i | gZı (13), gzı (1) | gZi (13), gzi (1) | 14 | review |
| unknown | GS-H (5), G$-H (4), Gs-H (3) | Gś-H (12) | 12 | siglum_policy_review |
| unknown | P$ (8), PS (2), Pś (1) | Ps (11) | 11 | siglum_policy_review |
| citation_or_siglum | TAIC (10) | TAIC (10) | 10 | already_canonical_siglum |
| citation_or_siglum | Tär (10) | Tār (10) | 10 | already_canonical_siglum |
| dotless_i | garı (9) | gari (9) | 9 | review |
| dotless_i | kyanı (9) | kyani (9) | 9 | review |
| dotless_i | MıgTo (9) | MigTo (9) | 9 | review |

## Top Google Adoption Patterns

| Reason | Base | Alternate | Count |
|---|---|---|---:|
| alternate_witness_google_loc_nasal_upgrade | dan | daṅ | 871 |
| alternate_witness_initial_i_to_l_translit | Ita | lta | 636 |
| alternate_witness_initial_i_to_l_translit | Iha | lha | 196 |
| alternate_witness_google_loc_nasal_upgrade | nid | ñid | 149 |
| alternate_witness_google_loc_nasal_upgrade | bzan | bzaṅ | 108 |
| alternate_witness_citation_siglum | Lis | Liś | 106 |
| alternate_witness_google_loc_fricative_upgrade | bsad | bśad | 87 |
| alternate_witness_initial_i_to_l_translit | Idan | ldan | 81 |
| alternate_witness_google_loc_nasal_upgrade | kyan | kyaṅ | 79 |
| alternate_witness_google_loc_nasal_upgrade | snan | snaṅ | 75 |
| alternate_witness_initial_i_to_l_translit | Ina | lṅa | 64 |
| alternate_witness_google_loc_fricative_upgrade | gsegs | gśegs | 60 |
| alternate_witness_google_loc_fricative_upgrade | bzin | bźin | 57 |
| alternate_witness_google_loc_nasal_upgrade | dban | dbaṅ | 56 |
| alternate_witness_google_loc_nasal_upgrade | nan | naṅ | 54 |

## Interpretation

- `tibetan_google_candidate_readings.tsv` contains unresolved Google-witness disagreements that may deserve manual review.
- `tibetan_orthography_damage_candidates.tsv` scans the current corrected text directly for Tibetan-looking damage patterns.
- `tibetan_script_ng_witness_candidates.tsv` scans corrected text for exact Latin `n`/`ṅ` disagreements backed by a same-line Tibetan-script `ང` witness. It is diagnostic only; it is not a broad `n -> ṅ` rule.
- `tibetan_initial_i_residual_candidates.tsv` scans corrected text for exact known Tibetan initial-`l` forms where OCR has capital `I`. It is diagnostic only; it is not a broad `I -> l` rule.
- `sigla_variant_candidates.tsv` separates bibliography/siglum policy cases from Tibetan and Sanskrit normalisation.
- `residual_sanskrit_low_confidence_candidates.tsv` is a small exploratory queue for Sanskrit-like residue outside the previous Sanskrit watch list.
- Promotion should happen only in a later audited batch, using exact tokens and context gates.
