# Internal scholarly bibliography reconciliation

The reconciliation is complete for the four registered WTS PDFs and three pinned online apparatus lists, with eight explicitly unresolved relationships. Historical evidence remains literal; reviewed identifications and corrections are separate relationships, never rewritten source records.

| Reviewed result | Count |
|---|---|
| Apparatus zones | 37 |
| Source-bound print occurrences | 2246 |
| Dictionary-source works | 432 |
| Bibliographic works | 460 |
| Publications / editions | 471 |
| Collections / composite sources | 8 |
| Literal sigla / abbreviation spellings | 723 |
| Accepted print–online crosswalks | 2059 |
| Repeated published occurrences | 1052 |
| Duplicate scan manifestations | 8 |
| Reviewed print-only authorities | 68 |
| Online authorities without reviewed print counterpart | 48 |
| Variant sets | 387 |
| Authorities with substantive variants | 122 |

Source-work and bibliographic-work counts are different scopes, not numbers to add. Publications include 399 online, 71 print and one externally established edition; eight collections/composites remain separate. Printed records include secondary/memorial material, which does not become citation authority by transcription alone.

## History and variants

The 37-zone inventory covers 109 distinct apparatus scan pages and 114 zone-page manifestations. Front matter, delivery boundaries, headings, neighbors and the complete OCR census establish coverage without manually inspecting thousands of lexical pages. Exact boundaries, contiguous residual accounting, inherited authors and cross-page records are preserved in the existing inventory/accounting/source-occurrence datasets.

Authority histories retain earliest **observed registered** occurrences, supplements, consolidated lists, later manifestations and online representations. Delivery order is chronology evidence; neither unavailable dates nor historical first introduction are invented. Exact repeated scans and repeated publication are counted separately.

The 387 variant sets retain both literal forms. Field categories overlap within sets:

| Variant field category | Count |
|---|---|
| author_name_variation | 26 |
| capitalization | 29 |
| edition_publication_difference | 71 |
| expanded_abbreviated_wording | 150 |
| probable_source_error | 3 |
| publisher_series_variation | 34 |
| siglum_difference | 9 |
| title_variation | 36 |
| transliteration_orthographic_variation | 33 |
| typography_layout_only | 21 |
| year_variation | 29 |

There are 122 authorities with substantive differences (139 fields); discrepancy is not automatically source error. Edition changes, abbreviations, orthography and publication sequences remain explicit instead of being flattened into cleaned strings.

## Historical errors and digital-edition clarification

- **T4090:** wrong printed locator `ku 144b6–147b7` → reviewed source location `ku 26b1–258a7 u. khu 1b1–95a7`. Current online /texte already gives the latter; retain the historical correction only.
- **Hoffmann:** printed `Jg. 150` → reviewed `Jg. 1950, 4`; online is already corrected.
- **gZi:** printed `ka bid ṅa` → probable `ka bis ṅa` reading. The current online description omits the clause, so this is not an outstanding online typo.
- **Maurer:** four literal printed `Maurer 2000` citations → reviewed Maurer 2001 identification, confirmed by Petra Maurer. All four corresponding generated online entries still have 2000 and belong in current feedback; do not rewrite the print evidence or independently assert locator correctness.
- **Mim1/Mim2:** no definition in the complete available WTS apparatus. Reviewed external Mimaki evidence establishes Mim1 = BDSN and Mim2 = CDSN. This is a digital-edition scholarly clarification, not information retrospectively attributed to WTS. Current online entries still use the undefined sigla. The 382 existing links and their source evidence remain untouched.

## Eight irreducible historical relationships

- **Karma-chags-med o. J.** (`print-occurrence-c499c031dde4588f2b0399639eea0fb2`): Printed Karma-chags-med undated ca. 1970 description versus online RiChos 1961: same work suggested, edition identity unestablished.
- **KHOCHHEN TULKU 1978** (`print-occurrence-4c431b4739281d18c9beabad68f881b3`): Printed Khochhen ca. 1978 versus online VaiNth 1977: dating variation or distinct edition remains unresolved.
- **Khri byaṅ Blo bzaṅ ye śes bstan ’dzin rgya mtsho** (`print-occurrence-adaee4cdaa67f95f7d90454775592dd6`): Printed KhriByang seven volumes versus online eight volumes, undated: publication extent conflict prevents edition merge.
- **KUN DGA’ BSOD NAMS 1977** (`print-occurrence-b95a6a824cba25072bf600c41ba38f95`): Printed KunDga 1977 versus online RolNś 1980: shared work does not establish the same publication.
- **Textbook 1966** (`print-occurrence-ea06dce1b6bb328b051aaeb651dbfa4b`): Printed Textbook 1966 reconstruction versus online TBFoundation 1966: publication identity not established by year alone.
- **TIBETAN BONPO MONASTIC CENTRE 1965** (`print-occurrence-73bd13758fca27a72ac67cea6c167b3f`): Printed Tibetan Bonpo Monastic Centre 1965 versus online gZi 1967: edition relationship unresolved; literal dates retained.
- **occurrence-b1803c86ec267424f6d8587445a77fbe:2** (`occurrence-b1803c86ec267424f6d8587445a77fbe:2`): Online Bca source description cites Vaidya 1960b, which has no independent bibliography target. Retained as an unresolved reference; no year-suffix substitution.
- **publication-relation-2b1218a4ae38c679bffcc211d664f885** (`publication-relation-2b1218a4ae38c679bffcc211d664f885`): Shared title suggests a work relationship, not edition equivalence. Online 2003 explicitly reprints 1993, not the distinct printed 1986 publication. Keep both source descriptions; no reprint-of-1986 assertion or citation-edition verification.

No additional historical relationships were silently merged during the current-online pass. Bca/Vaidya 1960b remains edition-sensitive, but its current tooltip pointing to a different work is independently established as a defect.

## Current-online disposition of historical populations

Of 68 reviewed print-only authorities, **26** have verified actionable current gaps: 24 missing/wrong publication targets plus `port.` and `postpos.`. The remaining 42 are retained as historical editions, inline definitions, alternate/part-volume representations, or cases with no verified current need for that exact missing edition. “No verified gap” does not prove absence of all possible future usage. Each individual disposition is recorded, with QA references for actionable members.

None of the 48 online-without-print authorities has an established current defect. Source/catalogue selections and online restructuring explain many work-level entries; independently described publications need no print counterpart to be legitimate. Their addition dates are not inferred from counterpart absence.

The current audit confirms seven undefined/malformed literal labels: Mim1, Mim2, Myv, Dag, brD, port., postpos. Myv is a transposition; Dag/brD are probable truncations requiring source confirmation. Alternate spellings, generic catalogue locators and decoder/layout artifacts are excluded explicitly. Fourteen additional unmatched author/year targets require editorial resolution rather than guessed edition equivalence. Two unrefreshed PDF-only candidates remain internal leads, not BAdW claims.

The available harvested corpus was searched systematically; actionable examples and apparatus pages were refreshed on 11 October. This does not assert a new exhaustive live crawl of every online URL. See the separate [current-online feedback](BIBLIOGRAPHY_CURRENT_ONLINE.md) and its machine-readable evidence for exact scope, hashes, literal spans, dispositions and conservative residuals.

Operational records: [reconciliation](../data/bibliography_apparatus_reconciliation.json), [questions ledger](../data/bibliography_apparatus_questions.tsv), [authority histories](../data/bibliography_authority_history.jsonl), [current authority dispositions](../data/bibliography_current_online_authorities.tsv). All completed obligations stay closed. `release/current` is unchanged.
