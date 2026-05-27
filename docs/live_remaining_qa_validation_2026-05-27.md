# Live-Remaining QA Validation (2026-05-27)

Input directory:
`work/production_release_candidate_sanskrit_isvara_recovery_20260522T163207Z`

This pass hardened the post-correction live-remaining classifier. When a suspicious-token row has both page and line metadata, exact page-line evidence is checked first. If that exact line is unavailable or the token is absent there, the classifier falls back only to page-level evidence. Bare line-number lookup is used only for rows with no page metadata. No OCR correction rules were promoted, and Google Vision adoption gates were not changed.

## Regenerated Outputs

- `production_release_candidate_report.md`
- `live_remaining_suspicious_tokens.tsv`
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

## Live-Remaining Tokens

| Volume | Token | Count | Page | Line | Suggestion | Evidence scope |
| --- | --- | ---: | ---: | ---: | --- | --- |
| WtS 1-34 | `ch'a` | 2 | 707 | 7 | `cha'` | `line:707:7` |
| WtS 1-34 | `mkha'i` | 1 | 1067 | 144 | `mkhai` | `page:1067` |
| WtS 1-34 | `mkhai` | 1 | 1067 | 144 | `mkha'i` | `line:1067:144` |
| WtS 1-34 | `źwa` | 1 | 98 | 141 | `ziṅ` | `line:98:141` |
| WtS 35-51 | `ishod` | 1 | 21 | 23 | `ishal` | `line:21:23` |
| WtS 9-m | `dzā` | 1 | 39 | 14 | `dza` | `line:39:14` |

The `mkha'i` row is intentionally reported with page-level evidence: the exact row line contains `mkhai`, while `mkha'i` remains elsewhere on page 1067. This is useful manual-review evidence, but it is not exact line-level proof of a remaining OCR error.

## Manual-Review Package Counts

| Output | Rows |
| --- | ---: |
| all_watchdog_rows.tsv | 285 |
| all_sanskrit_review_suggestions.tsv | 41 |
| low_confidence_google_adoptions.tsv | 758 |
| possible_missed_google_readings.tsv | 5 |

## Spot Check

The six live-remaining rows were manually spot-checked against the regenerated TSV output and corrected text search results. The line-scoped rows have token evidence at the reported page-line scope. The `mkha'i` row correctly uses page-level, not line-level, evidence. The new regression tests cover the off-page/global false-live case and applied-change stale classification.

No row from this validation pass justifies promoting a new OCR correction rule by itself.
