# Sanskrit Residual Review 2026-05-29

This note records the residual Sanskrit cleanup pass after the large batch. Google Vision adoption gates were not changed, validator-only residue was not used as correction evidence, and all promoted changes went through exact overrides with context gates and regression tests.

## Remaining Review Suggestions

| volume | page | line | from_token | current_suggestion | proposed_final_to_token | context | decision | reason | evidence_tag |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| WtS 9-m | 190 | 5 | `anantäparyantab` | `anantāparyantab` | `anantāparyantaḥ` | `anantäparyantab "ohne Ende und Umgrenzung" (Mvy 6480).` | promote full correction now | Mvy context supports macron and final visarga; exact token only. | `residual_visarga_term_normalization` |
| WtS 35-51 | 901 | 22 | `Aryaratnakäta` | `Aryaratnakāta` | `Āryaratnakūṭa` | `Aryaratnakäta` with Avataṃsaka/Samajaratna title context. | defer for source-image review | Probable title form, but the vowel sequence needs source confirmation. | `reviewed_sanskrit_title` |
| WtS 35-51 | 301 | 24 | `Buddhasöh` | `Buddhasoh` |  | German fragment `Buddhasöh-`. | reject as not Sanskrit/OCR-normalisation | German hyphenation fragment, not a Sanskrit normalisation target. |  |
| WtS 8-b | 55 | 60 | `dnantaryamärgab` | `dnantaryamārgab` | `ānantaryamārgaḥ` | `"dnantaryamärgab" "Weg ohne Hindernisse"` | defer for source-image review | Likely Sanskrit path term, but leading damage is too uncertain without image review. | `residual_visarga_term_normalization` |
| WtS 1-34 | 1007 | 104 | `jnaurasab` | `jñaurasab` | `jinaurasaḥ` | `jnaurasab "Sohn des Buddha"` | defer for source-image review | Likely term, but full reconstruction needs source confirmation. | `reviewed_sanskrit_term` |
| WtS 1-34 | 266 | 33 | `Käśy` | `Kāśy` | `Kāśy` | Short bibliographic abbreviation. | defer for source-image review | Citation abbreviation is too short for automatic promotion. | `reviewed_sanskrit_title` |
| WtS 35-51 | 158 | 34 | `pratikäülasamjnä` | `pratikāulasamjñā` | `pratikūlasaṃjñā` | `āhāre pratikäülasamjnä` | promote full correction now | Standard Buddhist Sanskrit term in direct Sanskrit context; exact token only. | `residual_sanskrit_damage_family` |
| WtS 9-m | 18 | 49 | `śinaväsika` | `śinavāsika` | `Śāṇavāsika` | `edlen śinaväsika aus Śrāvastī` | defer for source-image review | Probable proper name, but current OCR is too damaged for source-free promotion. | `reviewed_sanskrit_proper_name` |
| WtS 1-34 | 175 | 48 | `śosa-räpasya` | `śosa-rāpasya` | `śoṣa-rūpasya` | `Austrocknung (śosa-räpasya maranasya)` | defer for source-image review | Likely Sanskrit phrase, but several characters need confirmation. | `reviewed_sanskrit_term` |
| WtS 1-34 | 23 | 33 | `śrijhäna` | `śrijhāna` | `śrījñāna` | `śrijhäna). 1. Teil: Einführung...` | defer for source-image review | Probably a Jñāna proper-name fragment, but token boundary/context need source check. | `review_queue_sanskrit_jn_family` |
| WtS 35-51 | 680 | 20 | `ucchanganäam` | `ucchanganāam` | `ucchanganāam` | `Satam ucchanganäam...` | defer for source-image review | Macron is plausible, but the full form is not certain enough. | `reviewed_sanskrit_term` |

After promotion, `all_sanskrit_review_suggestions.tsv` fell from 11 to 9 data rows.

## Google Candidate Review

The 3 `review_only` rows in `google_sanskrit_candidate_readings.tsv` were reviewed:

| volume | page | line | from_token | alternate_token | decision | reason |
| --- | ---: | ---: | --- | --- | --- | --- |
| WtS 9-m | 362 | 30 | `Käsy` | `Kāśy` | defer | Short bibliographic abbreviation; source-image review needed. |
| WtS 35-51 | 145 | 73 | `VisT` | `VisṬ` | defer | Short citation abbreviation; not safe as Sanskrit normalisation. |
| WtS 9-m | 211 | 8 | `puspavrksab` | `puspavykṣaḥ` | promote fuller correction | The line glosses `Blütenbaum` with Mvy context; final override uses `puṣpavṛkṣaḥ`, supported by Sanskrit/context knowledge rather than pure Google adoption. |

Ten rejected Google candidates were sampled. They were dominated by Tibetan/Wylie forms, all-caps names, citation abbreviations, or German/prose tokens, so the reject logic does not appear too conservative for this pass.

## Residual Damage Miner

The QA generator now writes `residual_sanskrit_damage_candidates.tsv` from corrected full text. It scans for Sanskrit-like damaged tokens in context, including macron damage, `$`/ś damage, `jn`/`jñ` damage, final-visarga candidates, and damaged sūtra/title forms.

The first production run produced 29,830 diagnostic rows. They are review rows only; the miner does not auto-promote corrections.

## Promoted Overrides

| from_token | to_token | support | evidence_tag | example_ref |
| --- | --- | --- | --- | --- |
| `anantäparyantab` | `anantāparyantaḥ` | review queue plus Mvy context | `residual_visarga_term_normalization` | `wts_9_m:190:5` |
| `pratikäülasamjnä` | `pratikūlasaṃjñā` | review queue plus Sanskrit term context | `residual_sanskrit_damage_family` | `wts_35_51:158:34` |
| `puspavrksab` | `puṣpavṛkṣaḥ` | Google candidate plus Mvy/gloss context | `google_unresolved_sanskrit_term` | `wts_9_m:211:8` |

This yielded 4 corrected-text line changes because the full `anantäparyantab` override also replaced a prior partial normalisation in WtS 1-34.

## Corrected-Text Diffs

```diff
 ananta (in Mvy 409 u. 6.); ~ mu med =
-anantāparyantab (Mvy 6480).
+anantāparyantaḥ (Mvy 6480).
```

```diff
-pa — = āhāre pratikäülasamjnä "beim Essen
+pa — = āhāre pratikūlasaṃjñā "beim Essen
```

```diff
-anantäparyantab "ohne Ende und Umgren-
+anantāparyantaḥ "ohne Ende und Umgren-
```

```diff
-win 2 puspavrksab "Blütenbaum" (Mvy
+win 2 puṣpavṛkṣaḥ "Blütenbaum" (Mvy
```

Fewer than 20 further corrections were promoted because the remaining candidates were source-image uncertain, short bibliographic abbreviations, Tibetan/Wylie or citation noise, or damaged compounds whose full reconstruction needs source confirmation. The evidence did not support a larger exact batch without weakening the safeguards.

## Production QA

Output directory:

`work/production_release_candidate_residual_sanskrit_cleanup_20260529T100325Z`

Test commands:

```bash
python3 -m py_compile scripts/generate_production_qa_report.py scripts/postprocess_entry_map.py
python3 -m pytest tests/test_postprocess_regressions.py
```

Result: `116 passed in 1.81s`.

| metric | previous large batch | residual cleanup |
| --- | ---: | ---: |
| total Sanskrit changes | 559 | 562 |
| WtS 1-34 Sanskrit changes | 304 | 304 |
| WtS 35-51 Sanskrit changes | 150 | 151 |
| WtS 8-b Sanskrit changes | 53 | 53 |
| WtS 9-m Sanskrit changes | 52 | 54 |
| all_watchdog_rows.tsv data rows | 285 | 285 |
| live_validator_only_residue.tsv data rows | 1 | 1 |
| live_policy_or_false_positive.tsv data rows | 4 | 4 |
| google_sanskrit_candidate_readings.tsv data rows | 40 | 39 |
| all_sanskrit_review_suggestions.tsv data rows | 11 | 9 |
| possible_missed_google_readings.tsv data rows | 0 | 0 |

Google Vision gates were unchanged. Each postprocess run reported `google_vision_rewrites=0`.

## Checksums

| file | previous large batch | residual cleanup |
| --- | --- | --- |
| `WtS_1-34_release_candidate.txt` | `403a344b76e0fa6098046a89fd412201cbce20c36802b50897a2d8ad27be4cd6` | `5a78587e83650659da898b6f3650e0b430a86b0913fed537d0d4eb833d536a0d` |
| `WtS_35-51_release_candidate.txt` | `876840aa6a78746c9ee26bac409f8cdf3a14d51a9d1b0fb1d55a5f33da7510d4` | `122db1c160cecd12b4d0180f9da1f8dc5aa0fbe201154c843a726e4f99000e12` |
| `WtS_8-b_release_candidate.txt` | `fe8824485396840ad4b0bf659652c1ac3ed1f11f202560793c454d18c0c892ab` | `fe8824485396840ad4b0bf659652c1ac3ed1f11f202560793c454d18c0c892ab` |
| `WtS_9-m_release_candidate.txt` | `7d289afb84cce689e566303803ea77fe969b518b89102f4d180f45f6a07f99f7` | `cc8e9a861257d5d39e230809c49b9dd645a526c690ace090a96803fb62826591` |
