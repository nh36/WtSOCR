# Google Sanskrit Candidate Miner - 2026-05-28

## Scope

This pass adds a diagnostic miner for Google-supported Sanskrit or Indic candidates in unresolved alternate-witness rows. Google Vision remains an alternate witness only. The miner ranks review candidates; it does not auto-promote readings and does not loosen Google adoption gates.

The existing exact Mahāvyutpatti and Nyāyabinduṭīkā title overrides were left unchanged.

## Miner Output

The production QA report now writes:

- `google_sanskrit_candidate_readings.tsv`
- `possible_missed_google_readings.tsv`, now derived from the general miner's `exact_promotion_candidate` rows

The miner scans `alternate_witness_unresolved.tsv` rows and scores cases where the base and alternate tokens are compatible after Sanskrit-safe normalization, the alternate has better Sanskrit quality, and the surrounding line has Sanskrit, title, or bibliographic cues. It excludes obvious all-caps sigla, Roman numerals, Tibetan/Wylie apostrophe particles, and bibliographic noise.

Each row records the base and alternate tokens, normalized keys, unresolved reason, base and alternate lines, alignment method, candidate score, score explanation, and suggested action.

## Exact Promotions Added

The following reviewed title/proper-name readings were promoted through `data/sanskrit_promote_overrides.tsv`:

| Source token | Target token | Evidence tags | Reviewed refs |
| --- | --- | --- | --- |
| `Prajiapäramitä` | `Prajñāpāramitā` | `google_unresolved_sanskrit_title,prajnaparamita_title_context` | `wts_35_51:164:19` |
| `Mahäsamnipäta` | `Mahāsamnipāta` | `google_unresolved_sanskrit_title,mahasamnipata_title_context` | `wts_35_51:177:78;wts_35_51:177:83` |
| `Mahäsamäja` | `Mahāsamāja` | `google_unresolved_sanskrit_title,mahasamaja_title_context` | `wts_35_51:177:90` |

These remain exact source-token promotions with reviewed page/line evidence and title or bibliographic context gates.

## Before And After

| Ref | Before | After |
| --- | --- | --- |
| WtS 35-51 p164 l19 | `sahasrikä Prajiapäramitä" (1SK 1: 215,1,6);` | `sahasrikä Prajñāpāramitā" (1SK 1: 215,1,6);` |
| WtS 35-51 p177 l78 | `653, 1062) bzw. Mahäsamnipäta (vgl. Toh` | `653, 1062) bzw. Mahāsamnipāta (vgl. Toh` |
| WtS 35-51 p177 l83 | `Mahäsamnipäta gelesen hat" (Liyl 172b3);` | `Mahāsamnipāta gelesen hat" (Liyl 172b3);` |
| WtS 35-51 p177 l90 | `Mahäsamäja sind neun Abschnitte erhalten"` | `Mahāsamāja sind neun Abschnitte erhalten"` |

## Production QA

Production rerun directory:

`work/production_release_candidate_google_sanskrit_candidate_promotions_20260528T072220Z`

Compared with `work/production_release_candidate_sanskrit_google_title_promotions_exact_20260527T211204Z`:

- `possible_missed_google_readings.tsv`: 16 rows to 12 rows
- `google_sanskrit_candidate_readings.tsv`: 69 rows to 65 rows
- exact-promotion candidate rows: 16 rows to 12 rows
- `all_watchdog_rows.tsv`: 285 rows to 285 rows, content-identical apart from output-directory paths
- `live_validator_only_residue.tsv`: 1 row to 1 row, content-identical apart from output-directory paths
- `live_policy_or_false_positive.tsv`: 4 rows to 4 rows, content-identical apart from output-directory paths

Only `wts_35_51_corrected_full.txt` changed. The other corrected text files were byte-identical to the previous production run.

Corrected text checksums after the rerun:

| Volume | Checksum |
| --- | --- |
| WtS 1-34 | `e7afa48e6b9dd9e68943f51015968e1ac434bbdb7f99159a8d14391798ac658a` |
| WtS 35-51 | `ed4fccf7eb93ae792dc3c34b8c33482bb6c7be7d58fba339c608f72f7c65677c` |
| WtS 8-b | `2748722b46f9a9b361cc3dde8cadcc9a384508589079f8fd4fba2a5df5c5ff40` |
| WtS 9-m | `e2fb058adb61d9c9ddf65af99240f3c26398d27b766c9f0f5e51ad8a928c04cc` |

The WtS 35-51 checksum changed from `ba33aadc7f4867efdb134190e820a916ae369fe436e5dbca079c1c15e3f75d2d` because of the four intended title normalizations above.

## Remaining Candidate Queue

The remaining `possible_missed_google_readings.tsv` rows were not promoted in this pass:

| Ref | Base | Alternate |
| --- | --- | --- |
| WtS 1-34 p17 l24 | `Dharmakirti` | `Dharmakīrti` |
| WtS 35-51 p18 l73 | `Srävakas` | `Śrāvakas` |
| WtS 35-51 p73 l20 | `saptotsadah` | `saptotsadaḥ` |
| WtS 35-51 p73 l69 | `Taksaka` | `Takṣaka` |
| WtS 35-51 p164 l19 | `sahasrikä` | `sāhasrikā` |
| WtS 35-51 p177 l8 | `vrndah` | `vṛndaḥ` |
| WtS 35-51 p177 l32 | `Düramgamä` | `Dūramgamā` |
| WtS 35-51 p177 l74 | `samnipätab` | `samnipātaḥ` |
| WtS 35-51 p217 l25 | `paräkarsayati` | `parākarṣayati` |
| WtS 9-m p198 l76 | `tamala` | `tamāla` |
| WtS 9-m p229 l69 | `Näga` | `Nāga` |
| WtS 9-m p233 l88 | `apadal` | `apadaḥ` |

These require the same exact, source-supported review before any promotion.

## Verification

Regression command:

```bash
python3 -m unittest tests.test_postprocess_regressions
```

Result: 110 tests passed.

Google adoption gates were not changed. Validator-only live rows and policy/false-positive rows were ignored for correction promotion.
