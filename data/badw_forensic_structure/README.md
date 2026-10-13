# Forensic source-structure replay

Baseline: `53caa38e6d` (previous structural recovery). Source hashes and runtime code hashes are pinned in
`manifest.json`; raw sources, facsimiles and semantic SQLite remain in ignored
`work/`. No release text was changed.

## Results and evidence

All 29,877 witnesses project, with no reader integrity failures or accepted
bibliography identity loss. The preceding forensic citation reviews established
109,079 accepted identities; these and all 109,425 citation occurrences remain
unchanged in this structural replay.
The reviewed rows are in `../bibliography_forensic_citation_reviews.tsv`.

* Achard 2015: author HAL bibliography and RET publisher independently identify
  *The View of sPyi ti Yoga*, RET 31, pp. 1–20. This is an external authority,
  not a retrospectively invented WTS bibliography occurrence.
* Schwieger: supplied 2006 facsimile, scan 243–244 / printed 241–242, directly
  verifies the ergative/instrumental discussion. The citation now resolves to
  existing online publication `publication-44447794083fe19d6792b97d1c5b1c40`
  (Schwieger 2006). The pinned WTS bibliography registers this edition and no
  2009 second edition of the Handbuch; its Schwieger 2009 row is a different work.
  The user-reviewed first Lieferung (2005) kyis article lacks this citation.
  Together these establish a later digital/revised addition referring to 2006.
  The source literal remains `Schwieger 241 ff.`; 2009 is not an active candidate.
  This publication-level upgrade replaces an already accepted work-level match,
  so accepted identities remain 109,079 and unresolved identities remain 346.
* Mvy: 1989 facsimile scan 136 / printed 226 verifies Sakaki 4642 and its section;
  scan 102 / printed 159 verifies Sakaki 3129 and its section. The malformed
  online literals remain unchanged; reviewed work relationships supply Mvy.
  Their origin in print versus online conversion has not been established.
* `dBe’uD 212,4`: volume 3, printed 212 / scan 2166 genuinely prints the extra
  `d`. Be’uD's cited page was unavailable for content verification. No alias or
  decoding correction is accepted. This is the one unresolved focal identity;
  346 identities remain unresolved across the whole corpus.

External bibliographic URLs and PDF hashes are retained in the authority/review
TSVs. `badw_questions.tsv` contains four concise editorial questions: the Achard
online bibliography omission, unresolved source label and two confirmed malformed
online references. The Mvy identities are resolved; their source errors remain
editorial questions. Schwieger no longer requires editorial input. No message has been sent to BAdW.

The 408 owner residue is enumerated in `ownership_residue.jsonl.gz`, with frozen
family counts in `forensic_residue.json`. `ownership_context_review.jsonl`
records all 11 small-family contexts and 24 systematic prose/comparison contexts.
No new owner was inferred. Local variant parentheses and nested/malformed quotes
expose possible bounded-grammar work; the pass does not prove that every remaining
prose case is intrinsically unbounded.

The mixed-clause replay produces **11,543 header fields**, including **2,218
relations**, **4,355 aliases**, 2,938 homonym markers, 1,464 grammatical labels
and 568 verb forms. Explicit marker → italic target chains share the existing
HTML/PDF header model. Initial alias extraction is anchored to source position.

`badw_pdf_mixed_clauses.py` is separate from the unchanged narrow opening-gloss
rule. Its positive production is printed semicolon → italic tilde-bearing lexical
form → Roman gloss, with exact font/run and line geometry evidence. A second
production handles an unfinished observed German connective followed by a
same-font lowercase wrapped clause; it produces no corpus claims in this replay.
Competing examples, Lex., languages, citations, numbering, quotes and columns stop
recovery. Existing definitions remain immutable; exact fragments carry envelope
and continuation evidence and flow through the existing reader/store projection.
Thirty accounting runs recover **479 alphabetic characters** as mixed-clause
definitions. No generic prose container or proximity owner was introduced.

| Meaningful pending alphabetic characters | Before | After |
| --- | ---: | ---: |
| Total | 13,960 | 12,260 |
| HTML | 3,766 | 3,766 |
| PDF lexical prose | 6,379 | 5,806 |
| PDF header candidates | 1,778 | 738 |
| PDF aliases | 779 | 692 |
| PDF quotation/gloss | 1,101 | 1,101 |
| PDF reference clauses | 157 | 157 |
| PDF total | 10,194 | 8,494 |

The unchanged 131,068 raw alphabetic characters partition exactly into **42,211
typed**, **66,328 structural-label**, **10,269 decoding-placeholder**, and **12,260
pending meaningful** characters. This is 1,700 characters recovered, not a claim
that all residual categories now have proven canonical boundaries. No glyph mapping
was added. Placeholder syntax is separate from meaningful printed content.

The remaining 5,806 PDF prose characters have source-grammar reasons:

| Reason | Characters |
| --- | ---: |
| Quotation-adjacent fragment lacking a unique envelope | 2,175 |
| Reference target/comparison continuation | 1,568 |
| Lexical substitution clause with unresolved internal roles | 1,188 |
| Mixed/Roman clause lacking syntactic closure | 439 |
| Wrapped form/clause lacking a role boundary | 293 |
| Isolated form/clause fragment | 112 |
| Body/header alias continuation | 31 |

These diagnostic reasons preserve exact spans and nearby source/canonical context;
they are not semantic assignments. The separate 157 reference-clause characters
were rerun without a defensible new envelope. HTML's 2,793 other-heading characters
comprise 641 register/grammatical-label characters, 973 shared/composite heading
syntax and 1,179 unregistered heading wording. They must not all be forced into
relations. Other HTML residue remains 608 quotation/gloss, 234 aliases, 95 headers
and 36 reference characters.

`mixed_clause_holdout.json` freezes **36 previously unreviewed PDF entries on 36
independent physical pages**, twelve each from acquired volumes 2, 3 and 4, before
implementation outcomes. These are the acquired online PDF manifestations, not a
historical-print adaptation test. `mixed_clause_review.jsonl` records facsimile
inspection, exact accepted header/fragment spans, controls and misses. No false
claim from the **new** mixed/header rules was observed. The sample also exposes a
**pre-existing** opening-v3 false fragment `, vgl.` in the’u raṅ, and an opening
parenthesis boundary needing review in thos ldan. Missing shared pf./fut. grammar
and quotation/continuation recall remain explicit. This is not a zero-defect claim
for the whole parser or a statistical corpus accuracy estimate.

All **29,877 projections and 114 frozen witnesses pass**; reader integrity failures,
accepted bibliography identity loss and Lex. overlaps remain zero. Baseline owner
and xref edges survive. Citations remain 109,425; identities 109,079 accepted / 346
unresolved; owners 109,017 established / 408 unresolved. **No new citation owner**
was justified by these boundaries. Lex. remains 39,688 items; xrefs, language and
source text remain unchanged. `release/current` is untouched.

**Not structurally mature.** The largest coherent remaining boundary capability is
nested quotation/Tibetan excerpt → German translation parsing: **2,175
quotation-adjacent prose characters**, alongside **1,101 separately classified
quotation/gloss characters**. It needs balanced/nested quote and typography-aware
translation envelopes, not broader Roman-prose absorption. This specific grammar,
and the observed opening-v3 comparison-marker defect, should precede historical
print adaptation or full reader/product work.

## Reproduction

Run from the repository root with the acquired source cache and baseline SQLite:

```sh
python3 scripts/finalize_badw_corpus_structure.py --output data/badw_forensic_structure --work work/badw_forensic_structure --contextual-semantics --baseline-store work/badw_forensic_structure/baseline53caa.sqlite --baseline-commit 53caa38e6d --holdout-manifest data/badw_contextual_semantics/holdout.json --citation-reviews data/bibliography_forensic_citation_reviews.tsv
python3 scripts/classify_badw_header_accounting.py --work work/badw_forensic_structure --output data/badw_forensic_structure
python3 scripts/verify_badw_semantic_replay.py --output data/badw_forensic_structure --work work/badw_forensic_structure --baseline data/badw_semantic_residue --refine-boundaries
python3 scripts/classify_badw_forensic_residue.py
python3 scripts/build_status.py
```

Manual review files are scholarly observations retained separately from generated
diagnostics. Runtime code hashes describe the replay; postprocessing hashes
describe subsequent classification/status generation.
