# All-Volume Production QA Priorities (2026-05-19)

Output audited: `work/production_release_candidate_all_ready_volumes_20260519T191811Z/`

Candidate audit TSV produced: `work/production_release_candidate_all_ready_volumes_20260519T191811Z/tibetan_confusable_candidate_audit.tsv`

No OCR correction rules were changed for this analysis.

## Release Candidate Coverage

| Volume | Pages | Lines | Entries | SHA256 |
| --- | ---: | ---: | ---: | --- |
| WtS 1-34 | 1352 | 180208 | 12014 | `351ab94f9077154774d76a0713dc9cfb8b1afa07922d1a8b85659f923c5618ab` |
| WtS 35-51 | 1128 | 91855 | 6148 | `331bad50324699db9d55eeddcf187b4c8e8508757242862beb1b6af88f07f312` |
| WtS 8-b | 585 | 48290 | 3125 | `586200174fcd73d79031010ae3ee9b757ec81de765dd14e2e198c993d6a3eb3f` |
| WtS 9-m | 401 | 33664 | 1791 | `a3fd725816b37bb16730218d56dde73955468ccae7ef76cb31973b42801001d9` |

The manifest-driven run now covers all four ready source volumes. Adding WtS 8-b and WtS 9-m adds 986 pages, 81954 lines, 4916 entries, 3954 postprocess changes, 26 review-queue rows, 860 Google alternate-witness adoptions, and 2031 unresolved Google rows to the QA picture.

## Main QA Totals

| Volume | Postprocess changes | Review queue rows | Google adoptions | Google unresolved | Leading suspicious tokens |
| --- | ---: | ---: | ---: | ---: | --- |
| WtS 1-34 | 11322 | 22 | 38 | 3324 | `Ita`, `Iha`, `yañ`, `Idan`, `$es`, `nañ` |
| WtS 35-51 | 5570 | 15 | 1164 | 1893 | `Ita`, `Iha`, `Idan`, `dañ`, `yañ`, `$es` |
| WtS 8-b | 2393 | 15 | 3 | 900 | `Ita`, `Iha`, `Idan`, `yañ`, `dañ`, `$es` |
| WtS 9-m | 1561 | 11 | 857 | 1131 | `Ita`, `Iha`, `dañ`, `yañ`, `Idan`, `$es` |

The new volumes confirm that the dominant remaining OCR-quality issue is still high-frequency Tibetan transliteration confusables, not Google alignment or Sanskrit cleanup. WtS 9-m has a strong Google-witness signal, mostly through recovered rewrapped-page alignment. WtS 8-b has only three Google adoptions and many unresolved rewrapped pages, so it should be treated as a manual-QA-heavy volume until more witness evidence is available.

## Candidate Correction Passes

| Priority | Candidate pass | Affected rows by volume | Evidence | Risk | Recommended action |
| ---: | --- | --- | --- | --- | --- |
| 1 | Tibetan transliteration confusables: exact I/l, ñ/ṅ, and lowercase `$`/ś pairs | WtS 1-34: 6558; WtS 35-51: 4050; WtS 8-b: 1716; WtS 9-m: 1060 | Top suspicious tokens and candidate audit agree across all four volumes. Common forms include `Iha`, `Idan`, `yañ`, `dañ`, `$es`, `nañ`, and `gañ`. | Medium. I/l has known bad contexts such as all-caps citations and German/proper-name material; ñ/ṅ and lowercase `$`/ś look safer but still need zone/context gates. | Next substantive pass. Start with exact candidate pairs and strict Tibetan transliteration-zone evidence; keep broad I/l suggest-only until risky contexts are filtered. |
| 2 | German validator/reporting noise | WtS 1-34: 8498; WtS 35-51: 4070; WtS 8-b: 2128; WtS 9-m: 1472 validator issue rows | Many high-count validator tokens are valid German words, compounds, or orthographic variants rather than OCR errors. | Low OCR risk if kept reporting-only; high risk if converted into corrections. | Reporting-only cleanup to reduce manual-review noise. Do not auto-correct. |
| 3 | Dense-page manual QA | Highest change pages include WtS 1-34 p404, p629, p403; WtS 35-51 p690, p734; WtS 8-b p247, p540; WtS 9-m p273, p147, p317 | Dense pages appear to be normal correction-heavy dictionary pages rather than obvious overcorrection clusters, but they are efficient manual-review targets. | Low if manual-only. | Manual QA package, not a rule pass. |
| 4 | Remaining Sanskrit/Indic review leftovers | WtS 1-34: 10; WtS 35-51: 9; WtS 8-b: 13; WtS 9-m: 9 | Remaining rows include `śrijhäna`, `Käśy`, and `Prajnāpāramitāfsūtras`-type items. Counts are small after the Sanskrit pass. | Low to medium for exact reviewed pairs; broad character rules remain unsafe. | Defer unless manual review wants these cleared. Exact allowlist only. |
| 5 | Remaining citation/siglum `$` cleanup | Broad uppercase/siglum-like evidence: WtS 1-34: 802; WtS 35-51: 242; WtS 8-b: 153; WtS 9-m: 74 | Examples include `Y$`, `G$`, `L$dz-K`, `$PS`, and mixed Sanskrit/proper-name forms. | Medium. These should not be mixed with Tibetan lowercase `$`/ś transliteration cleanup. | Manual-only or exact siglum whitelist after separate audit. |

## Next Single Codex Task

The next correction pass should be a narrow Tibetan transliteration confusable audit, not a broad rule. Use `tibetan_confusable_candidate_audit.tsv` as the evidence table and promote only exact pairs with clear Tibetan transliteration-zone support.

Recommended order within that task:

1. Start with high-frequency ñ→ṅ coda pairs where Tibetan context supports the velar nasal, such as `yañ`/`dañ`/`nañ`/`gañ` families.
2. Separately audit lowercase Tibetan transliteration `$`→ś forms such as `$es` and `$a`-style tokens.
3. Keep I→l candidates suggest-only until all-caps citation, German/proper-name, and non-transliteration contexts are explicitly excluded.

Success should be measured by reduced suspicious-token and review-queue burden with no increase in doubtful sampled corrections, not by eliminating all unresolved Google rows.
