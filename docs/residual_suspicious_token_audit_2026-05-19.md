# Residual Suspicious Token Audit (2026-05-19)

Output audited: `work/production_release_candidate_tibetan_confusables_verify_20260519T224636Z/`

Detailed audit TSV: `work/production_release_candidate_tibetan_confusables_verify_20260519T224636Z/residual_suspicious_token_audit.tsv`

No OCR correction rules were changed for this audit.

## Main Finding

The residual suspicious-token burden is not currently a good proxy for remaining OCR text errors. In the top 100 suspicious-token rows, the high-count Tibetan confusable, lowercase `$`, and siglum `$` rows are already corrected by applied change rows and no longer appear as exact tokens in the corrected text. The remaining high-count rows are mostly German/prose validator false positives, plus the Indic name `Gangä`, which is intentionally still present.

| Classification | Top-100 rows | Occurrence count |
| --- | ---: | ---: |
| Already handled / stale validator issue | 67 | 10265 |
| German false positive / validator noise | 31 | 1215 |
| Sanskrit/Indic validator noise | 2 | 106 |
| Confirmed remaining real OCR error | 0 | 0 |

Across all 200 rows currently emitted in `top_suspicious_tokens.tsv`, the pattern is the same: 106 rows / 10743 occurrences are already-handled stale validator issues, 92 rows / 1948 occurrences are German false positives, and 2 rows / 106 occurrences are Sanskrit/Indic validator noise.

## Leading Residual Families

| Family | Top-100 rows | Occurrence count | Examples | Assessment |
| --- | ---: | ---: | --- | --- |
| Initial `I`/`l` | 25 | 6440 | `Ita`, `Iha`, `Idan`, `Ihan` | Already corrected in applied changes; exact source tokens are not present in corrected text. A new broad `I`→`l` pass would mainly reduce report noise, not improve OCR text. |
| `ñ`/`ṅ`/`n` confusables | 22 | 2372 | `yañ`, `dañ`, `nañ`, `gañ`, `chañ` | High-frequency forms are already corrected; remaining lower-frequency contexts should stay evidence-gated/manual. |
| German umlaut/prose | 31 | 1215 | `Abkürzungsverzeichnisse`, `Übersetzung`, `Überlieferung`, `Rüstung` | Valid German/prose orthography flagged by transliteration validators. Reporting-only cleanup is appropriate. |
| Lowercase `$`/`ś` Tibetan transliteration | 11 | 896 | `$es`, `$a`, `$i`, `$og`, `$in` | High-frequency forms are already corrected by exact rules. Do not add a global `$`→`ś` rule. |
| Citation/siglum `$` | 9 | 557 | `Li$`, `Y$`, `P$`, `L$dz-K`, `Vi$T` | Already corrected by exact siglum cleanup rows; residual counts are stale/reporting artifacts. |
| Sanskrit/Indic | 2 | 106 | `Gangä` | Present in corrected text, but not an OCR error for this pass. It should be handled, if at all, by Sanskrit/Indic reporting or manual policy, not Tibetan confusable rules. |

## Focus Families

Initial `I`/`l`: `Ita`, `Iha`, and `Idan` are still prominent in the validator summary, but exact-token checks show they are absent from the corrected text and accounted for by applied change rows. Broadening initial `I`/`l` rules is not justified from this report.

`ñ`/`ṅ`: `yañ`, `dañ`, `nañ`, and `gañ` are already handled by existing correction rules in the current release candidate. Remaining low-count `ñ` forms may still be real issues, but the top suspicious-token report does not identify them cleanly enough for an auto-rule.

Lowercase `$`/`ś`: `$es` and `g$egs` are already corrected where the current exact rules apply. Remaining `$` forms are ambiguous between Tibetan transliteration, citation/siglum material, Sanskrit/proper names, and OCR garbage, so the safe next step is better reporting rather than another text rule.

German umlaut/prose: the validator still flags ordinary German words and compounds because they contain characters that are suspicious in transliteration zones. These are not OCR errors and should be filtered or separately categorized in QA output.

Citation/siglum `$`: high-count forms such as `Li$`, `Y$`, `P$`, `L$dz-K`, and `Vi$T` are already corrected. Additional siglum work should remain exact-whitelist only and should not be mixed with Tibetan transliteration `$` cleanup.

## Recommendation

Recommended next move: **D. Validator/reporting-noise cleanup pass with no text changes.**

Expected affected rows: the current top-100 suspicious-token table contains 11586 occurrence-counts that are either stale applied-change artifacts, German/prose validator false positives, or Sanskrit/Indic validator noise. The all-row suspicious-token file shows the same pattern across 12797 occurrence-counts.

Expected effect on corrected text: none. This should improve QA accuracy by making suspicious-token summaries reflect live post-correction problems rather than pre-correction findings and known prose false positives.

Safety risk: low, provided the pass is reporting-only. It should not suppress raw validator files; it should add post-correction classification or filtered summaries so manual review can still inspect the underlying evidence.

Why this is more useful than another rule pass: the current leading suspicious-token counts are not showing uncorrected text. Adding more OCR rules would mostly chase report artifacts and risk overcorrection. Better QA attribution should come before any further Tibetan confusable, Sanskrit, or siglum promotions.

## Stop Condition

The release candidate is usable for manual scholarly review with the current correction rules. Before calling it final, the QA reports should distinguish live corrected-text issues from stale validator rows and German/prose false positives. Lower-frequency real OCR errors can safely wait for manual review or later evidence-backed exact-rule passes.
