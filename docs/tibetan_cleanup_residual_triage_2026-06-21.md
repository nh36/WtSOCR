# Tibetan Cleanup Residual Triage

Date: 2026-06-21

This report combines the supplied WtS 8-b and WtS 9-m Tibetan cleanup diagnostics after the latest reviewed cleanup state. It is a triage aid only: it does not add OCR correction heuristics and does not treat Google Vision as an authority.

Counts are normalized by residual family/pattern. When the same family appears in overlapping diagnostic queues, the per-volume count uses the strongest support count from those queues rather than summing inventories. This avoids treating grouped diagnostics and raw candidate rows as simple subtraction counts.

## Inputs

- `work/tibetan_second_cleanup_tranche_20260621T180745Z/tibetan_cleanup_diagnostics_wts_8_b`
- `work/tibetan_second_cleanup_tranche_20260621T180745Z/tibetan_cleanup_diagnostics_wts_9_m`
- reviewed exact overrides: `data/reviewed_tibetan_exact_overrides.tsv`

Full TSV: `work/tibetan_second_cleanup_tranche_20260621T180745Z/tibetan_residual_triage.tsv`

## Queue Inventory

| Queue | Rows |
| --- | --- |
| sigla_variant_candidates.tsv | 194 |
| tibetan_google_adoption_patterns.tsv | 242 |
| tibetan_google_candidate_readings.tsv | 102 |
| tibetan_orthography_damage_candidates.tsv | 304 |
| tibetan_variant_families.tsv | 139 |

## Recommended Actions

| Recommended action | Family groups |
| --- | --- |
| sample further | 278 |
| siglum policy review | 78 |
| ignore | 16 |
| source-image review | 1 |
| already reviewed | 1 |

## Ranked Residual Families

| Family/pattern | Queue source | WtS 8-b | WtS 9-m | Combined | Source token(s) | Proposed target(s) | Google status | Recommended action | Representative examples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dollar_ś | variant_families; orthography_scan; google_candidate_readings | 146 | 122 | 268 | $ | ś | alternate_candidate | sample further | wts_8_b:14:80; wts_8_b:14:80:$; wts_8_b:17:50:$; wts_8_b:30:63:$; wts_8_b:38:65:$ |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 140 | 140 | dan | daṅ | existing_adoption | sample further | wts_9_m:6:43 |
| initial_i_to_l_translit | google_adoption_patterns | 0 | 103 | 103 | Ita | lta | existing_adoption | sample further | wts_9_m:7:37 |
| initial_i_to_l_translit | google_adoption_patterns | 1 | 54 | 55 | Iha | lha | existing_adoption | sample further | wts_8_b:3:32; wts_9_m:5:4 |
| citation_or_siglum | sigla_variant_candidates; google_adoption_patterns | 8 | 17 | 25 | Lis; lis; LiS; LIS | Liś | existing_adoption | siglum policy review | wts_8_b:15:10:Lis; wts_8_b:21:63:Lis; wts_8_b:43:6:Lis; wts_8_b:149:26:Lis; wts_8_b:174:63:lis |
| initial_i_to_l_translit | google_adoption_patterns | 0 | 20 | 20 | Ina | lṅa | existing_adoption | sample further | wts_9_m:7:87 |
| citation_or_siglum | variant_families; sigla_variant_candidates | 13 | 3 | 16 | Bu-Sz | Bu-śz | alternate_candidate | siglum policy review | wts_8_b:83:34; wts_8_b:83:34:Bu-Sz; wts_8_b:110:46:Bu-Sz; wts_8_b:122:78:Bu-Sz; wts_8_b:136:17:Bu-Sz |
| initial_i_to_l_translit | google_adoption_patterns | 0 | 15 | 15 | Idan | ldan | existing_adoption | sample further | wts_9_m:6:54 |
| google_loc_fricative_upgrade | google_adoption_patterns | 0 | 14 | 14 | zes | źes | existing_adoption | sample further | wts_9_m:18:2 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 14 | 14 | bzan | bzaṅ | existing_adoption | sample further | wts_9_m:56:31 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 11 | 11 | snan | snaṅ | existing_adoption | sample further | wts_9_m:120:64 |
| citation_or_siglum | google_adoption_patterns; sigla_variant_candidates | 0 | 10 | 10 | GS-H; Gs-H | Gś-H | existing_adoption | siglum policy review | wts_9_m:7:49; wts_9_m:233:9; wts_9_m:25:81:GS-H; wts_9_m:276:67:Gs-H; wts_9_m:297:25:Gs-H |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 10 | 10 | gron | groṅ | existing_adoption | sample further | wts_9_m:6:19 |
| google_loc_fricative_upgrade | google_adoption_patterns | 0 | 9 | 9 | gsegs | gśegs | existing_adoption | sample further | wts_9_m:18:22 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 9 | 9 | man | mañ | existing_adoption | sample further | wts_9_m:62:3 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 9 | 9 | nid | ñid | existing_adoption | sample further | wts_9_m:72:45 |
| initial_i_to_l_translit | google_adoption_patterns | 0 | 9 | 9 | Ihan | lhan | existing_adoption | sample further | wts_9_m:5:33 |
| citation_or_siglum | variant_families; sigla_variant_candidates; google_adoption_patterns | 3 | 5 | 8 | Lsdz-K | Lśdz-K | existing_adoption | siglum policy review | wts_8_b:124:23; wts_8_b:124:23:Lsdz-K; wts_8_b:153:33:Lsdz-K; wts_8_b:458:5:Lsdz-K; wts_9_m:72:20 |
| initial_i_to_l_translit | google_adoption_patterns | 0 | 8 | 8 | Ihun | lhun | existing_adoption | sample further | wts_9_m:20:3 |
| citation_or_siglum | variant_families; google_adoption_patterns; sigla_variant_candidates | 0 | 7 | 7 | gZ1 | gZi | existing_adoption | siglum policy review | wts_9_m:58:46; wts_9_m:58:46:gZ1; wts_9_m:136:33:gZ1; wts_9_m:178:70:gZ1; wts_9_m:231:10:gZ1 |
| google_loc_fricative_upgrade | google_adoption_patterns | 0 | 7 | 7 | bsad | bśad | existing_adoption | sample further | wts_9_m:117:27 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 7 | 7 | dban | dbaṅ | existing_adoption | sample further | wts_9_m:135:30 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 7 | 7 | spon | spoṅ | existing_adoption | sample further | wts_9_m:100:76 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 7 | 7 | ston | stoṅ | existing_adoption | sample further | wts_9_m:128:34 |
| citation_or_siglum | sigla_variant_candidates; variant_families; google_candidate_readings | 3 | 3 | 6 | gzi; gZi | gZi | alternate_candidate | siglum policy review | wts_8_b:28:62:gzi; wts_8_b:206:5:gzi; wts_8_b:436:52:gzi; wts_9_m:232:78; wts_9_m:232:78:5:gZi |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 6 | 6 | bzun | bzuṅ | existing_adoption | sample further | wts_9_m:28:62 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 6 | 6 | gton | gtoṅ | existing_adoption | sample further | wts_9_m:79:10 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 6 | 6 | ran | raṅ | existing_adoption | sample further | wts_9_m:120:13 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 6 | 6 | sten | steṅ | existing_adoption | sample further | wts_9_m:37:69 |
| citation_or_siglum | variant_families; google_candidate_readings | 0 | 5 | 5 | bZin | bZin | alternate_candidate | siglum policy review | wts_9_m:211:74; wts_9_m:211:74:2:bZin; wts_9_m:229:26:4:bZin; wts_9_m:229:83:8:bZin; wts_9_m:232:58:4:bZin |
| google_loc_fricative_upgrade | google_adoption_patterns | 0 | 5 | 5 | ses | śes | existing_adoption | sample further | wts_9_m:173:67 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 5 | 5 | btan | btaṅ | existing_adoption | sample further | wts_9_m:5:42 |
| initial_i_to_l_translit | google_adoption_patterns | 0 | 5 | 5 | Iho | lho | existing_adoption | sample further | wts_9_m:8:57 |
| citation_or_siglum | sigla_variant_candidates; google_adoption_patterns | 1 | 3 | 4 | Viś | Vis | existing_adoption | siglum policy review | wts_8_b:458:80:Viś; wts_9_m:344:75; wts_9_m:205:63:Viś; wts_9_m:235:76:Viś; wts_9_m:344:75:Viś |
| google_loc_fricative_upgrade | google_adoption_patterns | 1 | 3 | 4 | bses | bśes | existing_adoption | sample further | wts_8_b:3:18; wts_9_m:336:21 |
| google_loc_fricative_upgrade | google_adoption_patterns | 0 | 4 | 4 | bzin | bźin | existing_adoption | sample further | wts_9_m:50:46 |
| google_loc_fricative_upgrade | google_adoption_patterns | 0 | 4 | 4 | sel | śel | existing_adoption | sample further | wts_9_m:8:33 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 4 | 4 | gan | gañ | existing_adoption | sample further | wts_9_m:15:82 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 4 | 4 | gan | gaṅ | existing_adoption | sample further | wts_9_m:178:63 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 4 | 4 | glan | glaṅ | existing_adoption | sample further | wts_9_m:58:8 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 4 | 4 | khan | khaṅ | existing_adoption | sample further | wts_9_m:82:72 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 4 | 4 | na | ña | existing_adoption | sample further | wts_9_m:5:5 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 4 | 4 | sgan; sGan | sgaṅ; sGaṅ | existing_adoption | sample further | wts_9_m:45:39; wts_9_m:353:63 |
| google_loc_velar_nasal_upgrade | google_adoption_patterns | 0 | 4 | 4 | dañ | daṅ | existing_adoption | sample further | wts_9_m:28:7 |
| initial_i_to_l_translit | google_adoption_patterns | 0 | 4 | 4 | Iha'i | lha'i | existing_adoption | sample further | wts_9_m:138:34 |
| citation_or_siglum | google_adoption_patterns; sigla_variant_candidates | 0 | 3 | 3 | L$dz-K | Lśdz-K | existing_adoption | siglum policy review | wts_9_m:12:58; wts_9_m:12:58:L$dz-K; wts_9_m:20:51:L$dz-K; wts_9_m:173:61:L$dz-K |
| citation_or_siglum | google_adoption_patterns; sigla_variant_candidates | 0 | 3 | 3 | L$dz | Lśdz | existing_adoption | siglum policy review | wts_9_m:10:80; wts_9_m:10:80:L$dz; wts_9_m:14:43:L$dz; wts_9_m:169:61:L$dz |
| citation_or_siglum | google_adoption_patterns; sigla_variant_candidates | 0 | 3 | 3 | Li$ | Liś | existing_adoption | siglum policy review | wts_9_m:121:6; wts_9_m:121:6:Li$; wts_9_m:208:18:Li$; wts_9_m:254:28:Li$ |
| citation_or_siglum | google_adoption_patterns; sigla_variant_candidates | 0 | 3 | 3 | Lsdz | Lśdz | existing_adoption | siglum policy review | wts_9_m:200:16; wts_9_m:200:16:Lsdz; wts_9_m:211:57:Lsdz; wts_9_m:315:5:Lsdz |
| citation_or_siglum | variant_families; google_candidate_readings | 0 | 3 | 3 | Tär | Tār | alternate_candidate | siglum policy review | wts_9_m:211:37; wts_9_m:211:37:4:Tär; wts_9_m:211:39:7:Tär; wts_9_m:232:53:3:Tär |
| citation_or_siglum | google_candidate_readings; sigla_variant_candidates | 0 | 3 | 3 | VisT; ViST | ViśT | alternate_candidate | siglum policy review | wts_9_m:52:35:3:VisT; wts_9_m:198:26:8:VisT; wts_9_m:362:62:2:ViST; wts_9_m:52:35:VisT; wts_9_m:198:26:VisT |
| citation_or_siglum | sigla_variant_candidates | 0 | 3 | 3 | VisṬ | ViśT | alternate_candidate | siglum policy review | wts_9_m:52:35:VisṬ; wts_9_m:198:26:VisṬ; wts_9_m:233:40:VisṬ |
| google_loc_fricative_upgrade | google_adoption_patterns | 0 | 3 | 3 | bsul | bśul | existing_adoption | sample further | wts_9_m:272:1 |
| google_loc_fricative_upgrade | google_adoption_patterns | 0 | 3 | 3 | bzens | bźens | existing_adoption | sample further | wts_9_m:10:62 |
| google_loc_fricative_upgrade | google_adoption_patterns | 0 | 3 | 3 | sog | śog | existing_adoption | sample further | wts_9_m:143:29 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 3 | 3 | byun | byuṅ | existing_adoption | sample further | wts_9_m:58:62 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 3 | 3 | gnan | gnaṅ | existing_adoption | sample further | wts_9_m:109:16 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 3 | 3 | kyan | kyaṅ | existing_adoption | sample further | wts_9_m:231:65 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 3 | 3 | man | maṅ | existing_adoption | sample further | wts_9_m:60:17 |
| google_loc_nasal_upgrade | google_adoption_patterns | 0 | 3 | 3 | nan | ṅan | existing_adoption | sample further | wts_9_m:267:52 |

## Manual Sampling and Second-Tranche Decision

No second correction tranche was promoted from this report. The largest safe-looking Tibetan families are already accepted through the existing Google token gates, and converting them into source-independent exact rows would reduce auditability without changing corrected text. The remaining high-volume residue is either policy-sensitive, noisy across contexts, or already covered by reviewed exact overrides.

| Family | Sampling result | Decision |
| --- | --- | --- |
| `dan -> daṅ` | Sampled rows are Tibetan contexts and already appear as existing Google-gated adoptions. | Keep Google-gated; do not promote a source-independent exact/global rule. |
| `Ita -> lta` | Sampled rows are ordinary Tibetan `lta` contexts and already adopted through the existing gates. | Keep Google-gated; do not add a broad initial-I rule. |
| `Iha -> lha` | Sampled rows are mostly clear `lha` contexts, but at least one sampled line also contains nearby siglum noise. | Keep Google-gated; promote no ungated family. |
| `Ina -> lṅa` | Sampled rows are clear Tibetan numeral contexts and already adopted through existing gates. | Keep Google-gated; no additional override needed. |
| `Idan -> ldan` | Sampled rows are clear `ldan` contexts and already adopted through existing gates. | Keep Google-gated; no additional override needed. |
| `zes -> źes` | Existing adoptions are visible, but the row is transliteration-policy sensitive rather than a simple OCR family. | Defer; do not promote as a cleanup rule. |
| `bzan/snan/gron -> bzaṅ/snaṅ/groṅ` | These are existing Google-gated nasal upgrades in Tibetan contexts. | Leave under existing adoption gates; do not duplicate as reviewed overrides. |
| `dnos -> dṅos` | The remaining high-confidence candidate rows match exact rows already present in `data/reviewed_tibetan_exact_overrides.tsv`. | Already reviewed; no new correction work. |
| Reviewed `$` sigla canonicals | `Bu-$z`/`Bu-Sz`, `G$-H`/`Gs-H`/`Gś-H`, and `Y$`/`Ys`/`Yś` are citation sigla whose reviewed canonicals preserve `ś`: `Bu-śz`, `Gś-H`, and `Yś`. Plain `Gs` remains a distinct siglum. | Normalize only through siglum registry/confusable-map context; no generic `$ -> ś` rule. |
| Remaining sigla families | `L$dz-K` and related unresolved forms remain bibliographic-policy cases. `Li$ -> Liś` and `gZ1 -> gZi` follow existing registry policy. | Siglum policy review, not Tibetan lexical cleanup. |
| `$ -> ś` | High-volume residue is too broad and mixes Tibetan, Sanskrit, and siglum contexts. | Sample/source-review only; no generic replacement. |
| `la'añń` and nasal-damage-looking rows | The local shape is suspicious, but the current diagnostics do not establish a safe exact family. | Source-image review. |

## Triage Notes

- `dan -> daṅ`, `Ita -> lta`, `Iha -> lha`, `Ina -> lṅa`, and `Idan -> ldan` remain high-priority Google-gated families for sampling. They should not become source-independent global rules.
- Rows already present in `data/reviewed_tibetan_exact_overrides.tsv` are marked as already reviewed rather than treated as a fresh promotion queue.
- `$ -> ś` remains too broad as a Tibetan/Sanskrit cleanup rule. It belongs in targeted row review or siglum policy, not a generic character substitution.
- Reviewed `$` sigla families now prefer `ś`-bearing canonicals: `Bu-$z`/`Bu-Sz -> Bu-śz`, `G$-H`/`Gs-H`/`Gś-H -> Gś-H`, and `Y$`/`Ys`/`Yś -> Yś`. These are registry/context-gated siglum normalizations, not a generic `$ -> ś` rule.
- Remaining sigla families such as `Lsdz-K`/`L$dz-K` and other unresolved variants stay in bibliographic-policy review. `Li$ -> Liś` and `gZ1 -> gZi` remain existing registry decisions.
- `la'añń` and similar nasal-looking rows require source-image review; no broad `ń -> ṅ` or `n -> ñ` repair is implied.
- Residual Sanskrit low-confidence rows are intentionally outside this Tibetan tranche.
