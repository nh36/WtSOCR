# Release-Candidate Readiness Review, 2026-05-20

Final release-candidate QA output reviewed:

`work/production_release_candidate_clean_qa_20260520T055946Z/`

This review inspected the cleaned QA `residual_real_candidate` rows. No
correction-rule changes were made: the remaining candidates are validator edge
cases, acceptable variants, or manual-review-only contexts rather than safe
exact OCR fixes.

## Release-Candidate Files

| Volume | Release-candidate text | SHA256 |
| --- | --- | --- |
| WtS 1-34 | `work/production_release_candidate_clean_qa_20260520T055946Z/final/WtS_1-34_release_candidate.txt` | `351ab94f9077154774d76a0713dc9cfb8b1afa07922d1a8b85659f923c5618ab` |
| WtS 35-51 | `work/production_release_candidate_clean_qa_20260520T055946Z/final/WtS_35-51_release_candidate.txt` | `331bad50324699db9d55eeddcf187b4c8e8508757242862beb1b6af88f07f312` |
| WtS 8-b | `work/production_release_candidate_clean_qa_20260520T055946Z/final/WtS_8-b_release_candidate.txt` | `586200174fcd73d79031010ae3ee9b757ec81de765dd14e2e198c993d6a3eb3f` |
| WtS 9-m | `work/production_release_candidate_clean_qa_20260520T055946Z/final/WtS_9-m_release_candidate.txt` | `a3fd725816b37bb16730218d56dde73955468ccae7ef76cb31973b42801001d9` |

The cleaned QA run is reporting-only. Corrected text is unchanged from the
prior Tibetan-confusables verification run.

## Cleaned QA Classification Totals

| Classification | Rows | Occurrences |
| --- | ---: | ---: |
| `already_corrected_or_stale` | 2,559 | 15,715 |
| `german_or_prose_false_positive` | 5,880 | 14,356 |
| `sanskrit_or_indic` | 317 | 906 |
| `manual_review_only` | 491 | 696 |
| `citation_or_siglum` | 10 | 13 |
| `residual_real_candidate` | 11 | 13 |

## Residual Candidate Decisions

| Volume | Page / line | Token | Suggested | Decision | Rationale |
| --- | --- | --- | --- | --- | --- |
| WtS 1-34 | 707 / 7 | `ch'a` | `cha'` | Leave as-is; manual note only | Chinese tea transliteration context. Apostrophe placement is citation/transliteration-sensitive, not a safe OCR fix. |
| WtS 1-34 | 707 / 7 | `cha'` | `ch'a` | Leave as-is; manual note only | Reciprocal validator suggestion for the same context. Do not add a global apostrophe rule. |
| WtS 1-34 | 1067 / 144 | `mkha'i` | `mkhai` | Leave as-is; manual note only | Tibetan transliteration apostrophe context. Existing text contains both forms; exact override would be unsafe. |
| WtS 1-34 | 1067 / 144 | `mkhai` | `mkha'i` | Leave as-is; manual note only | Reciprocal validator suggestion. Needs scholarly review if this line matters, not an automatic rule. |
| WtS 1-34 | 98 / 141 | `źwa` | `ziṅ` | False positive; leave as-is | Tibetan source `ཞྭ་` supports `źwa`; the suggested `ziṅ` is not appropriate here. |
| WtS 35-51 | 21 / 23 | `ishal` | `ishod` | Leave as-is; manual note only | Validator sees nearby competing forms. Context is transliteration-sensitive and not safe for exact automation. |
| WtS 35-51 | 21 / 23 | `ishod` | `ishal` | Leave as-is; manual note only | Reciprocal suggestion in the same line. No safe exact correction is established. |
| WtS 8-b | 337 / 23 | `bandha` | `buddha` | Acceptable Indic/name context; leave as-is | Excerpt has `bandha hor npr.`; changing to `buddha` would be a semantic substitution, not OCR cleanup. |
| WtS 8-b | 337 / 23 | `buddha` | `bandha` | Acceptable Indic/name context; leave as-is | Reciprocal validator noise around Indic forms. No exact fix. |
| WtS 9-m | 39 / 14 | `dza` | `dzā` | Leave as-is; manual note only | The line contains both short and long-vowel transliteration contexts across the volume. Avoid broad `dza`/`dzā` rules. |
| WtS 9-m | 39 / 14 | `dzā` | `dza` | Acceptable; leave as-is | Tibetan `ཛཱ` in the excerpt supports `dzā`; the suggested de-macronized form is not a correction. |

## Remaining Manual-Review-Only Categories

The remaining manual-review load is concentrated in context-sensitive cases
that should not drive broad rules:

- Initial `I`/`l` transliteration candidates outside already-reviewed exact contexts.
- Remaining `ñ`/`ṅ`/`n` transliteration suggestions that lack a safe local gate.
- Lowercase `$`/`ś` suggestions outside exact reviewed Tibetan or siglum allowlists.
- Citation/siglum edge cases where `$`, apostrophes, or abbreviated labels need source-aware review.
- Sanskrit/Indic forms where normalized and unnormalized forms can both be valid depending on context.

## Readiness Recommendation

The release candidate is ready for scholarly/manual review. The cleaned QA
output has reduced the apparent residual OCR problem set to 11 candidate rows,
and none of those rows is a safe exact correction to apply before release.

Before calling the text final, manual review should sample the
`manual_review_only` and `residual_real_candidate` queues, especially
apostrophe-sensitive transliteration, Indic names, and citation/siglum edge
cases. Broad heuristic expansion should wait until that review identifies a
recurrent, source-confirmed pattern.
