# Corpus structural health: pinned offline replay

The current pipeline was replayed over every acquired BAdW entry witness: **29,877 witnesses (18,037 HTML; 11,840 PDF)**. These are witness counts, not deduplicated dictionary headwords. **29,875 canonical projections succeed (99.9933%)**. Two HTML witnesses (`ka chen/1`, `kos sñuṅ/1`) fail duplicate typed-span validation. Bibliography reconciliation was not reopened; no parser rules or release text were changed.

## Results

| Measure | Result | Interpretation |
|---|---:|---|
| Source characters / alphabetic characters | 15,869,897 / 9,038,114 | Successful projections |
| Unassigned source characters / alphabetic characters | 2,203,090 / 131,061 | Includes layout and structural labels |
| Remaining lexical/header review gaps | 6,144 runs; 148,343 characters; 63,246 alphabetic | 0.70% of alphabetic text; includes aliases/verb headers, not a proven omission rate |
| Canonical nodes / numbered senses / definitions | 565,002 / 10,303 / 32,938 | Broad container coverage excluded from leaf accounting |
| Citations / accepted bibliography identities | 109,087 / 108,764 | 323 unresolved identities |
| Reviewed citation owners / unresolved owners | 13 / 109,074 | Known publication does not establish semantic ownership |
| Lex. components / language spans | 40,250 / 120,704 | Recognized structure does not prove boundaries or language accuracy |
| HTML xrefs resolved / unresolved | 4,649 / 629 | Explicit unresolved URLs absent from acquired exact index |
| PDF xrefs unresolved | 3,054 | 2,176 unique exact-label candidates; 120 ambiguous; 758 without exact-label candidate |
| Missing PDF reader xref bindings | 3,054 in 2,670 entries | Source nodes exist; reader binding fails |
| Reader projections / integrity failures / accepted-identity losses | 29,875 / 0 / 0 | Data projection and source recomposition; no browser/CSS accuracy claim |

The citation ownership result is a major remaining **model/review gap**, not evidence that 109,074 citations are attached incorrectly. Generic containment/proximity is never promoted to reviewed ownership. All PDF target candidates remain unresolved under the existing exact source binding; a unique label is not automatically an accepted target. HTML missing URLs may have alternate PDF witnesses, so absence from the index does not prove absence from WTS.

The four registered historical PDFs (3,466 pages) also ran through their existing legacy entry-zoning path: **24,528 entry groups**, including **103 groups over 150 lines**. Unassigned alphabetic material totals 43,328 characters, largely front matter. There is **no registered-print OCR-to-canonical adapter**: these are legacy zoning diagnostics, not an additional successful canonical reader run. This architectural gap prevents claiming full structural support for all acquired historical print witnesses. Original PDF hashes and unchanged corrected-text input hashes are pinned in `registered_print.json` and `manifest.json`.

## Prioritized engineering families

Counts below are candidate indicators, not confirmed defect totals; families overlap. Exact examples, spans, hashes, distributions, causes and actions are in `priorities.json` and `priorities.tsv`.

1. **Lex. sense envelopes and citable passages — parser/model.** 2,201 HTML entries have Lex. material outside numbered sense nodes (8,190 occurrences); 471 PDF entries have overlapping Lex. items (564 indicators). Reviewed examples expose duplicate Lex. representation and merged clauses after malformed source quotes. Build typed Lex. items inside sense envelopes and exact passage ownership first.
2. **PDF cross-reference binding — adapter/reader.** Restore stable node identifiers and carry qualified target extents through adaptation. Review unique candidates; preserve ambiguous and missing targets.
3. **Contextual language typing — parser/model.** 601 untyped explicit-language indicators and 384 contradictory assignments. Holdout confirms Sanskrit correspondences such as `Jetavana`, `na saṃtrasati`, `divasaḥ` remain untyped. Use structure/typography, not character-shape guesses.
4. **Registered historical-print adapter — model.** Preserve original coordinates and review long legacy groups before representing them as canonical entries.
5. **Unaccounted headers and clauses — parser/model/source decoding.** Separate alias/verb/header material from genuinely missing lexical structure. Displaced PDF homonym markers and unknown font tokens require source-aware treatment. A source token `⟦UNKNOWN:TGaramond:regular:0020:f958a53c825f⟧` remains in replay text; this is a decoding artifact, not a CSS fix.
6. **Inline citation grammar — parser/scholarly ambiguity.** 792 ignored-citation cues and 323 unresolved identities. Reviewed `vgl. PW 5.3` is missed; numeric parentheses also produce false positives. Do not fuzzy-resolve uncertain editions.
7. **Source contract failures — projection/integration.** Two duplicate-span exceptions plus one existing PDF semantic overlay rejected for missing/unsupported contract fields. Twelve overlays apply. Preserve fail-closed validation.
8. **Definition and numbered-sense boundaries — parser/source ambiguity.** 74 conservative later-structure cues and three empty numbered-sense candidates remain. Quote-only definitions and punctuation overlaps are frequently harmless: the 1,289 broad swallowing indicators and 1,063 crossing indicators are not confirmed corruption. No exact duplicate-component or nonmonotonic numbering indicator was found. Eighteen entries exceed ten senses; maximum 18 senses and maximum definition length 721 characters are outliers, not errors.

Reader sense collections contain both division and sense containers in 2,461 HTML and 1,440 PDF entries. This warrants model/projection review but does not establish duplicated rendered text. Source recomposition can pass while a definition swallows a later clause; accounting is not an accuracy score.

## Fresh holdout and adjudication

Thirty entries (14 HTML, 16 PDF), two per deliberately varied stratum, were deterministically selected before inspection, excluding 1,169 identities found in previous review/packet/gold/challenge records. Selection/exclusion evidence is in `holdout.json`. All selected PDF facsimiles, including three continuations, were visually inspected. **12 confirmed local defects, 17 with no observed local segmentation defect, and one unresolved target qualifier** are recorded with literal evidence in `holdout_review.jsonl`. This targeted sample is not a statistical corpus accuracy estimate; reviewed citation ownership is not implied. No parser tuning followed holdout inspection.

Eleven additional representative adjudications are in `representative_review.jsonl`, including harmless empty containers, quoted definitions and terminal `(Lex.)`, plus genuine missed citation/language typing. Further arbitrary review batches now give diminishing returns. Continue fresh stratified holdouts and anomaly-driven source review, especially for ambiguous source typography.

## Reproduce and inspect

Run from the repository root with the acquired ignored source cache present:

```sh
python3 scripts/audit_badw_corpus_structure.py
python3 scripts/finalize_badw_corpus_structure.py
python3 scripts/review_badw_corpus_structure.py
python3 scripts/summarize_badw_corpus_structure.py
python3 -m pytest tests/test_badw_corpus_structure.py -q
```

The first pass regenerates source-bound projections and diagnostics; the second applies existing exact bibliography/xref/semantic infrastructure and reader checks; the third refines accounting and runs registered-print zoning; the fourth verifies checked-in manual review against exact selected source hashes/spans, ranks families and seals output hashes. Changed holdout evidence fails closed. This is an offline replay of pinned acquired sources, not a refresh of live BAdW pages. `manifest.json` pins source/cache/implementation inputs and generated artifacts. `entries.tsv` and `print_entries.tsv` are compact per-witness metrics. `anomalies.jsonl.gz` retains exact source spans/hashes; large raw packets/projections remain ignored in `work/badw_corpus_structure/`. No release rebuild is required.

**Recommended next tranche:** typed Lex. items within sense envelopes, with explicit citable-passage relations and exact ownership contracts. Preserve all literal source evidence and accepted bibliography identities; validate against the frozen holdout before expanding rules.
