# Sanskrit Batch Promotion - Prajnaparamita Sutra Full Titles - 2026-05-28

## Scope

This pass promoted exact full-token normalisations for damaged Prajnaparamita-sutra title forms. It did not add a broad `jn` -> `jñ` rule, a broad `Sata` -> `Śata` rule, or a general damaged-sutra repair.

The promotions are gated by exact source token, reviewed volume/page/line, and local title context. Google Vision adoption gates were unchanged. Validator-only residue was ignored.

Exact Google support was not present for these reviewed rows, so no `google_unresolved_prajnaparamita_title` evidence tag was added.

## Overrides Added

| Source token | Target token | Evidence tag | Example ref |
| --- | --- | --- | --- |
| `Hunderttausender-Prajnāpāramitāsūrtra` | `Hunderttausender-Prajñāpāramitāsūtra` | `prajnaparamita_sutra_full_title_normalization` | `wts_8_b:444:85` |
| `Prajnāpāramitāfsūtras` | `Prajñāpāramitāsūtras` | `prajnaparamita_sutra_full_title_normalization` | `wts_1_34:699:76` |
| `prajnāparamitāsiitra` | `prajñāpāramitāsūtra` | `prajnaparamita_sutra_full_title_normalization` | `wts_35_51:1031:69` |
| `Prajnapāramitāsiitra` | `Prajñāpāramitāsūtra` | `prajnaparamita_sutra_full_title_normalization` | `wts_9_m:129:20` |
| `Satasāhasrikāprajnāpāramitāsātra` | `Śatasāhasrikāprajñāpāramitāsūtra` | `prajnaparamita_sutra_full_title_normalization` | `wts_8_b:444:80` |
| `Prajnāpāramitāsūtra` | `Prajñāpāramitāsūtra` | `prajnaparamita_sutra_full_title_normalization` | `wts_8_b:444:14;wts_8_b:444:82` |
| `prajnāpāramitāsūtra` | `prajñāpāramitāsūtra` | `prajnaparamita_sutra_full_title_normalization` | `wts_8_b:492:56` |
| `Satasāhasrikāprajnāpāramitā-Lesung` | `Śatasāhasrikāprajñāpāramitā-Lesung` | `prajnaparamita_sutra_full_title_normalization` | `wts_8_b:444:10` |

## Corrected Text Diff

Compared with `work/production_release_candidate_google_sanskrit_candidate_promotions_20260528T072220Z`, the new corrected text changed only these title-family lines:

| Volume | Corrected text line | Before | After |
| --- | ---: | --- | --- |
| `wts_1_34` | 102726 | `tragenden des Prajnāpāramitāfsūtras] ein` | `tragenden des Prajñāpāramitāsūtras] ein` |
| `wts_35_51` | 83934 | `hasrikä[prajnāparamitāsiitra]" (Nel 12a5); lo` | `hasrikä[prajñāpāramitāsūtra]" (Nel 12a5); lo` |
| `wts_8_b` | 36505 | `Satasāhasrikāprajnāpāramitā-Lesung bereit-` | `Śatasāhasrikāprajñāpāramitā-Lesung bereit-` |
| `wts_8_b` | 36509 | `Prajnāpāramitāsūtra, das der Vater für Glin` | `Prajñāpāramitāsūtra, das der Vater für Glin` |
| `wts_8_b` | 36575 | `Satasāhasrikāprajnāpāramitāsātra.` | `Śatasāhasrikāprajñāpāramitāsūtra.` |
| `wts_8_b` | 36577 | `Prajnāpāramitāsūtra" (Debm 546); ne` | `Prajñāpāramitāsūtra" (Debm 546); ne` |
| `wts_8_b` | 36580 | `Hunderttausender-Prajnāpāramitāsūrtra, die` | `Hunderttausender-Prajñāpāramitāsūtra, die` |
| `wts_8_b` | 40618 | `Acavimśatikasahasrikä[prajnāpāramitāsūtra]` | `Acavimśatikasahasrikä[prajñāpāramitāsūtra]` |
| `wts_9_m` | 10626 | `es im Prajnapāramitāsiitra, es seien Kopf-` | `es im Prajñāpāramitāsūtra, es seien Kopf-` |

Two older `Prajñāpāramitāsūtras` high-frequency allowlist changes still appear in per-volume change logs, but they were already present before this pass and are not part of this diff.

## Production Rerun

Output directory:

`work/production_release_candidate_prajnaparamita_sutra_full_titles_20260528T081635Z`

Postprocess summaries:

| Volume | Sanskrit changes | Sanskrit review suggestions |
| --- | ---: | ---: |
| `wts_1_34` | 298 | 9 |
| `wts_35_51` | 129 | 8 |
| `wts_8_b` | 46 | 7 |
| `wts_9_m` | 39 | 8 |

QA counts:

| File | Rows |
| --- | ---: |
| `all_watchdog_rows.tsv` | 285 |
| `live_validator_only_residue.tsv` | 1 |
| `live_policy_or_false_positive.tsv` | 4 |
| `google_sanskrit_candidate_readings.tsv` | 65 |
| `possible_missed_google_readings.tsv` | 12 |
| `all_sanskrit_review_suggestions.tsv` | 32 |

`all_watchdog_rows.tsv` did not increase. `live_validator_only_residue.tsv` and `live_policy_or_false_positive.tsv` are unchanged apart from embedded output-directory paths.

## Checksums

| Volume | Previous corrected text checksum | New corrected text checksum |
| --- | --- | --- |
| `wts_1_34` | `e7afa48e6b9dd9e68943f51015968e1ac434bbdb7f99159a8d14391798ac658a` | `54c22c0e1ad4372ada7a96c93126fe25c5453278bb510d412bca14bc33e942da` |
| `wts_35_51` | `ed4fccf7eb93ae792dc3c34b8c33482bb6c7be7d58fba339c608f72f7c65677c` | `d069d96c51b6cbf10b43fa184287d7988f0bfec51aac15b514e5d88c6e810bc5` |
| `wts_8_b` | `2748722b46f9a9b361cc3dde8cadcc9a384508589079f8fd4fba2a5df5c5ff40` | `64a28b6393ab0d290099fb8e309470e95c35853a113610f464968df48267a0fe` |
| `wts_9_m` | `e2fb058adb61d9c9ddf65af99240f3c26398d27b766c9f0f5e51ad8a928c04cc` | `1ba3b1afac8dc0bcf35c7b2d9d8b2f25404a8e0a224de8f79ed99b41c92d5896` |

## Verification

Focused Prajnaparamita title regression tests:

`python3 -m unittest tests.test_postprocess_regressions.PostprocessRegressionTests.test_prajnaparamita_sutra_full_title_promotions_apply_in_reviewed_context tests.test_postprocess_regressions.PostprocessRegressionTests.test_prajnaparamita_sutra_full_title_promotions_need_reviewed_context`

Result: `Ran 2 tests ... OK`

Full postprocess regression suite:

`python3 -m unittest tests.test_postprocess_regressions`

Result: `Ran 112 tests ... OK`
