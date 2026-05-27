# Live-Remaining QA Validation (2026-05-27)

Input directory:
`work/production_release_candidate_sanskrit_isvara_recovery_20260522T163207Z`

This pass hardened the post-correction live-remaining classifier. When a suspicious-token row has both page and line metadata, exact page-line evidence is checked first. If that exact line is unavailable or the token is absent there, the classifier falls back only to page-level evidence. Bare line-number lookup is used only for rows with no page metadata. No OCR correction rules were promoted, and Google Vision adoption gates were not changed.

## Regenerated Outputs

- `production_release_candidate_report.md`
- `live_remaining_suspicious_tokens.tsv`
- `live_validator_only_residue.tsv`
- `live_review_queue_candidates.tsv`
- `live_google_supported_candidates.tsv`
- `live_policy_or_false_positive.tsv`
- `manual_review_only_suspicious_tokens.tsv`
- `sanskrit_or_indic_policy_suspicious_tokens.tsv`
- `citation_or_siglum_suspicious_tokens.tsv`
- `stale_or_already_corrected_suspicious_tokens.tsv`
- `german_false_positive_validator_tokens.tsv`
- `all_watchdog_rows.tsv`
- `all_sanskrit_review_suggestions.tsv`
- `low_confidence_google_adoptions.tsv`
- `possible_missed_google_readings.tsv`
- `suspicious_token_classification_summary.tsv`

## Suspicious-Token Counts

| Classification | Rows | Occurrences |
| --- | ---: | ---: |
| live_remaining | 6 | 7 |
| already_corrected_or_stale | 2,580 | 15,770 |
| german_or_prose_false_positive | 5,834 | 14,212 |
| sanskrit_or_indic_policy_case | 335 | 964 |
| citation_or_siglum | 9 | 9 |
| manual_review_only | 501 | 734 |

Live-remaining rows by volume:

| Volume | Rows | Occurrences |
| --- | ---: | ---: |
| WtS 1-34 | 4 | 5 |
| WtS 35-51 | 1 | 1 |
| WtS 8-b | 0 | 0 |
| WtS 9-m | 1 | 1 |

## Live-Remaining Evidence Buckets

| Bucket | Rows | Occurrences |
| --- | ---: | ---: |
| live_validator_only_residue | 1 | 1 |
| live_review_queue_candidates | 1 | 1 |
| live_google_supported_candidates | 0 | 0 |
| live_policy_or_false_positive | 4 | 5 |

## Live-Remaining Validator Candidates

The suggestion field is produced by validator/canonicalisation heuristics. It is not OCR-witness evidence and should not be treated as a correction direction unless independently supported.

`validator-only=yes` means no Google alternate-witness support is recorded; withheld review-queue presence is provenance, not independent OCR-witness evidence.

| Bucket | Volume | Source | Token | Count | Page | Line | Heuristic suggestion | Evidence scope | Google adoption | Google unresolved | Review withheld | Validator-only | Interpretation |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| live_policy_or_false_positive | WtS 1-34 | review_queue_from | `ch'a` | 2 | 707 | 7 | `cha'` | `line:707:7` | no | no | yes | yes | non-Tibetan romanisation / validator false positive; likely Wade-Giles or another romanisation context; do not promote |
| live_policy_or_false_positive | WtS 1-34 | review_queue_to | `mkha'i` | 1 | 1067 | 144 | `mkhai` | `page:1067` | no | no | yes | yes | validator false positive / wrong direction; `mkha'i` is valid Tibetan/Wylie; do not promote |
| live_review_queue_candidates | WtS 1-34 | review_queue_from | `mkhai` | 1 | 1067 | 144 | `mkha'i` | `line:1067:144` | no | no | yes | yes | manual review only; possible local OCR/transliteration error only if page context confirms; no general apostrophe rule |
| live_policy_or_false_positive | WtS 1-34 | review_queue_from | `źwa` | 1 | 98 | 141 | `ziṅ` | `line:98:141` | no | no | yes | yes | validator false positive; `źwa` and `ziṅ` are distinct Tibetan forms; do not promote |
| live_validator_only_residue | WtS 35-51 | review_queue_from | `ishod` | 1 | 21 | 23 | `ishal` | `line:21:23` | no | no | yes | yes | validator-only/manual-review; not a correction candidate unless independently supported by source image or Google unresolved evidence |
| live_policy_or_false_positive | WtS 9-m | review_queue_from | `dzā` | 1 | 39 | 14 | `dza` | `line:39:14` | no | no | yes | yes | orthographic/transcription policy or validator-only; do not promote automatically |

The `mkha'i` row is intentionally reported with page-level evidence: the exact row line contains `mkhai`, while `mkha'i` remains elsewhere on page 1067. This is useful manual-review evidence, but it is not exact line-level proof of a remaining OCR error.

## Interpretation of live_remaining rows

These six rows come from validator and review-queue reporting. They are not necessarily Google Vision evidence, and none of the current live rows appears in the Google-supported candidate bucket.

The current six live rows do not justify OCR-rule promotion. Four are policy or false-positive cases, one is validator-only residue, and one is a local manual-review candidate that would need page context or image evidence before any text change.

The useful next OCR-improvement stream remains `possible_missed_google_readings.tsv` and the Sanskrit-family review queue, not validator-only residue. Only `live_google_supported_candidates.tsv` rows and clearly source-supported review-queue rows should be considered for future promotion.

## Manual-Review Package Counts

| Output | Rows |
| --- | ---: |
| all_watchdog_rows.tsv | 285 |
| all_sanskrit_review_suggestions.tsv | 41 |
| low_confidence_google_adoptions.tsv | 758 |
| possible_missed_google_readings.tsv | 5 |

## Promising Queue Inspection

`possible_missed_google_readings.tsv` contains five unresolved Google-supported Sanskrit-family candidates:

| Volume | Page | Line | Base token | Alternate token |
| --- | ---: | ---: | --- | --- |
| WtS 1-34 | 6 | 16 | `Mahavyutpatti` | `Mahāvyutpatti` |
| WtS 1-34 | 6 | 19 | `Mahävyutpatti` | `Mahāvyutpatti` |
| WtS 1-34 | 10 | 58 | `Mahävyutpatti` | `Mahāvyutpatti` |
| WtS 1-34 | 17 | 19 | `Mahävyutpatti` | `Mahāvyutpatti` |
| WtS 1-34 | 17 | 27 | `Nyayabindutika` | `Nyāyabinduṭīkā` |

`all_sanskrit_review_suggestions.tsv` contains 41 withheld Sanskrit review suggestions. The directly relevant matches are jn/jñ and Prajñā-family rows, including Prajñāpāramitā/Prajñāpāra/Prajñāpā tokens. It does not contain Mahāvyutpatti or Nyāyabinduṭīkā rows; those currently appear in the possible-missed Google queue.

## Spot Check

The six live-remaining rows were manually spot-checked against the regenerated TSV output and corrected text search results. The line-scoped rows have token evidence at the reported page-line scope. The `mkha'i` row correctly uses page-level, not line-level, evidence. The reclassification was also checked against Google adoption/unresolved support and review-queue withheld status. The new regression tests cover the off-page/global false-live case, applied-change stale classification, validator-only residue splitting, reciprocal validator rows, and non-Tibetan romanisation false-positive handling.

No row from this validation pass justifies promoting a new OCR correction rule by itself.
