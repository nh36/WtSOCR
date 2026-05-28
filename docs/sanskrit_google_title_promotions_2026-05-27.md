# Sanskrit Google Title Promotions 2026-05-27

## Scope

This pass promoted only exact Google-supported Sanskrit-title rows from `possible_missed_google_readings.tsv`.
Google Vision adoption gates were not loosened, and validator-only live residue was ignored.

## Reviewed Source Rows

| Volume | Page | Line | Base text | Google alternate | Adjudication |
| --- | ---: | ---: | --- | --- | --- |
| WtS 1-34 | 6 | 16 | `Mahavyutpatti` | `Mahāvyutpatti` | Sanskrit title in Wörterbuchprojekt/Mvy context |
| WtS 1-34 | 6 | 19 | `Mahävyutpatti` | `Mahāvyutpatti` | Sanskrit title in Mahāvyutpatti work context |
| WtS 1-34 | 10 | 58 | `Mahävyutpatti (Mvy)` | `Mahāvyutpatti (Mvy)` | Sanskrit title with explicit Mvy siglum |
| WtS 1-34 | 17 | 19 | `Mahävyutpatti` | `Mahāvyutpatti` | Sanskrit title in bibliographic title context |
| WtS 1-34 | 17 | 27 | `Nyayabindutika` | `Nyāyabinduṭīkā` | Sanskrit title after Dharmottara title context |

## Promoted Overrides

The following exact rows were added to `data/sanskrit_promote_overrides.tsv`:

```tsv
promote	Mahavyutpatti	Mahāvyutpatti	4	google_unresolved_sanskrit_title,mvy_context	wts_1_34:6:16
promote	Mahävyutpatti	Mahāvyutpatti	4	google_unresolved_sanskrit_title,mvy_context	wts_1_34:6:19;wts_1_34:10:58;wts_1_34:17:19
promote	Nyayabindutika	Nyāyabinduṭīkā	4	google_unresolved_sanskrit_title,title_context	wts_1_34:17:27
```

The postprocess requires both the exact promoted source token and a matching reviewed page/line with Sanskrit-title context.

## Before And After

```text
WtS 1-34 p6 l16  Mahavyutpatti  -> Mahāvyutpatti
WtS 1-34 p6 l19  Mahävyutpatti  -> Mahāvyutpatti
WtS 1-34 p10 l58 Mahävyutpatti  -> Mahāvyutpatti
WtS 1-34 p17 l19 Mahävyutpatti  -> Mahāvyutpatti
WtS 1-34 p17 l27 Nyayabindutika -> Nyāyabinduṭīkā
```

The WtS 1-34 corrected text diff against the previous release-candidate output contains only these five title normalisations. WtS 35-51, WtS 8-b, and WtS 9-m corrected text files are byte-identical to the previous output.

## Test And Production Run

Test command:

```sh
python3 -m unittest tests.test_postprocess_regressions
```

Result: passed, 105 tests.

Production rerun output:

```text
work/production_release_candidate_sanskrit_google_title_promotions_exact_20260527T211204Z
```

QA effect:

| File or metric | Previous | New | Delta |
| --- | ---: | ---: | ---: |
| WtS 1-34 Sanskrit changes | 292 | 297 | +5 |
| WtS 35-51 Sanskrit changes | 124 | 124 | 0 |
| WtS 8-b Sanskrit changes | 40 | 40 | 0 |
| WtS 9-m Sanskrit changes | 38 | 38 | 0 |
| `possible_missed_google_readings.tsv` rows | 5 | 0 | -5 |
| `all_watchdog_rows.tsv` rows | 285 | 285 | 0 |
| `live_validator_only_residue.tsv` rows | 1 | 1 | 0 |
| `live_policy_or_false_positive.tsv` rows | 4 | 4 | 0 |

The five target rows no longer appear in `possible_missed_google_readings.tsv`. No new watchdog rows appeared for these changes.

## Remaining Sanskrit Review Queue

`all_sanskrit_review_suggestions.tsv` still contains Prajñā/jñāna-family review rows, including forms around `Prajñāpāramitā`, `jñāna`, and `Jñānagarbha`. They were inspected only as a follow-up queue and were not promoted in this pass.
