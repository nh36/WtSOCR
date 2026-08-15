# Tibetan Cleanup Exploratory Diagnostics

This is a diagnostics-only packet. It does not add OCR correction heuristics, does not loosen Google Vision adoption gates, and does not modify corrected text.

## Row Counts

- `tibetan_google_candidate_readings.tsv`: 12
- `tibetan_orthography_damage_candidates.tsv`: 2
- `guarded_dollar_to_sacute_candidates.tsv`: 244
- `tibetan_script_ng_witness_candidates.tsv`: 0
- `reference_marker_candidates.tsv`: 457
- `reference_marker_token_families.tsv`: 224
- `tibetan_initial_i_residual_candidates.tsv`: 0
- `sigla_variant_candidates.tsv`: 57
- `residual_sanskrit_low_confidence_candidates.tsv`: 239
- `tibetan_variant_families.tsv`: 39
- `tibetan_google_adoption_patterns.tsv`: 3

## Top Candidate Families

| Family | Sources | Targets | Count | Action |
|---|---|---|---:|---|
| guarded_dollar_to_sacute | $ (205) | ś (205) | 205 | defer |
| unknown | rol (24) | Rol (24) | 24 | siglum_policy_review |
| unknown | ins (23) | Ins (23) | 23 | siglum_policy_review |
| guarded_dollar_to_sacute | $0 (5) | ś0 (5) | 5 | defer |
| guarded_dollar_to_sacute | $5 (4) | ś5 (4) | 4 | defer |
| guarded_dollar_to_sacute | $7 (4) | ś7 (4) | 4 | defer |
| guarded_dollar_to_sacute | $8212 (4) | ś8212 (4) | 4 | defer |
| unknown | gs (4) | Gs (4) | 4 | siglum_policy_review |
| guarded_dollar_to_sacute | 4$ (3) | 4ś (3) | 3 | defer |
| guarded_dollar_to_sacute | 70$ (3) | 70ś (3) | 3 | defer |
| unknown | gzi (3) | gZi (3) | 3 | siglum_policy_review |
| guarded_dollar_to_sacute | 0$ (2) | 0ś (2) | 2 | defer |
| guarded_dollar_to_sacute | 77$ (2) | 77ś (2) | 2 | defer |
| guarded_dollar_to_sacute | 7$ (2) | 7ś (2) | 2 | defer |
| guarded_dollar_to_sacute | 9$ (2) | 9ś (2) | 2 | defer |
| unknown | lis (2) | Liś (2) | 2 | siglum_policy_review |
| citation_or_siglum | auf (1) | rGyud (1) | 1 | already_canonical_siglum |
| citation_or_siglum | die (1) | P (1) | 1 | already_canonical_siglum |
| citation_or_siglum | für (1) | K (1) | 1 | already_canonical_siglum |
| citation_or_siglum | I.MU (1) | LMU (1) | 1 | already_canonical_siglum |

## Top Google Adoption Patterns

| Reason | Base | Alternate | Count |
|---|---|---|---:|
| alternate_witness_google_loc_fricative_upgrade | bses | bśes | 1 |
| alternate_witness_google_loc_nasal_upgrade | sPan-lun | sPañ-lun | 1 |
| alternate_witness_initial_i_to_l_translit | Iha | lha | 1 |

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
