# Tibetan Cleanup Exploratory Diagnostics

This is a diagnostics-only packet. It does not add OCR correction heuristics, does not loosen Google Vision adoption gates, and does not modify corrected text.

## Row Counts

- `tibetan_google_candidate_readings.tsv`: 12
- `tibetan_orthography_damage_candidates.tsv`: 151
- `tibetan_script_ng_witness_candidates.tsv`: 0
- `reference_marker_candidates.tsv`: 457
- `reference_marker_token_families.tsv`: 225
- `tibetan_initial_i_residual_candidates.tsv`: 0
- `sigla_variant_candidates.tsv`: 57
- `residual_sanskrit_low_confidence_candidates.tsv`: 239
- `tibetan_variant_families.tsv`: 23
- `tibetan_google_adoption_patterns.tsv`: 3

## Top Candidate Families

| Family | Sources | Targets | Count | Action |
|---|---|---|---:|---|
| dollar_ś | $ (146) | ś (146) | 146 | review |
| unknown | rol (24) | Rol (24) | 24 | siglum_policy_review |
| unknown | ins (23) | Ins (23) | 23 | siglum_policy_review |
| unknown | gs (4) | Gs (4) | 4 | siglum_policy_review |
| unknown | gzi (3) | gZi (3) | 3 | siglum_policy_review |
| dollar_ś | '$ (2) | 'ś (2) | 2 | review |
| unknown | lis (2) | Liś (2) | 2 | siglum_policy_review |
| citation_or_siglum | auf (1) | rGyud (1) | 1 | already_canonical_siglum |
| citation_or_siglum | die (1) | P (1) | 1 | already_canonical_siglum |
| citation_or_siglum | für (1) | K (1) | 1 | already_canonical_siglum |
| citation_or_siglum | I.MU (1) | LMU (1) | 1 | already_canonical_siglum |
| citation_or_siglum | Liyl (1) | Liyl (1) | 1 | already_canonical_siglum |
| citation_or_siglum | mdud (1) | VaiNth (1) | 1 | already_canonical_siglum |
| citation_or_siglum | Mūlasarvāstivādavinaya (1) | kā (1) | 1 | already_canonical_siglum |
| citation_or_siglum | Neu (1) | ChagNth (1) | 1 | already_canonical_siglum |
| citation_or_siglum | sie (1) | śel (1) | 1 | already_canonical_siglum |
| citation_or_siglum | VaiNth (1) | VaiNth (1) | 1 | already_canonical_siglum |
| dollar_ś | $rT (1) | śrT (1) | 1 | review |
| google_tibetan_diacritic_disagreement | 1 (1) | snaṅ (1) | 1 | review |
| google_tibetan_diacritic_disagreement | Blo-bzan (1) | Blo-bzaṅ (1) | 1 | review |

## Top Google Adoption Patterns

| Reason | Base | Alternate | Count |
|---|---|---|---:|
| alternate_witness_google_loc_fricative_upgrade | bses | bśes | 1 |
| alternate_witness_google_loc_nasal_upgrade | sPan-lun | sPañ-lun | 1 |
| alternate_witness_initial_i_to_l_translit | Iha | lha | 1 |

## Interpretation

- `tibetan_google_candidate_readings.tsv` contains unresolved Google-witness disagreements that may deserve manual review.
- `tibetan_orthography_damage_candidates.tsv` scans the current corrected text directly for Tibetan-looking damage patterns.
- `tibetan_script_ng_witness_candidates.tsv` scans corrected text for exact Latin `n`/`ṅ` disagreements backed by a same-line Tibetan-script `ང` witness. It is diagnostic only; it is not a broad `n -> ṅ` rule.
- `tibetan_initial_i_residual_candidates.tsv` scans corrected text for exact known Tibetan initial-`l` forms where OCR has capital `I`. It is diagnostic only; it is not a broad `I -> l` rule.
- `reference_marker_candidates.tsv` inventories actual reference markers and likely OCR substitutes (`T`, `I`, `/`, `\`) near Tibetan transliteration contexts. It is diagnostic only; it is not a broad marker-normalisation rule.
- `sigla_variant_candidates.tsv` separates bibliography/siglum policy cases from Tibetan and Sanskrit normalisation.
- `residual_sanskrit_low_confidence_candidates.tsv` is a small exploratory queue for Sanskrit-like residue outside the previous Sanskrit watch list.
- Promotion should happen only in a later audited batch, using exact tokens and context gates.
