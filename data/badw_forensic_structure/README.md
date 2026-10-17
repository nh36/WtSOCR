# Source-bounded ownership grammar tranche (e26c885e06 baseline)

The full replay projects **29,877/29,877 witnesses**, establishing **109,234
citation owners** and leaving **191 unresolved** (50 HTML / 141 PDF). The 43 new
owners comprise 18 Lex assertion owners, 18 HTML heading assertion owners, four
PDF punctuated comparison-list owners and three balanced-comparison owners.
Citations remain 109,425; bibliography identities remain 109,079 accepted / 346
unresolved. `release/current` is untouched.

Meaningful untyped alphabetic residue falls **579 characters**, from **11,651 to
11,072** (HTML 3,219; PDF 7,853). Raw alphabetic gaps remain 131,068: 43,049 typed,
66,331 structural labels, 10,616 decoding-placeholder syntax and 11,072 pending.
Ownership and lexical accounting are separate measurements.

## Complete occurrence census and batch disposition

`owner_review.jsonl.gz` contains all 234 baseline survivors, including source
identity/headword, exact citation and local context, bibliography status, source
and canonical nodes, punctuation/enclosures, markers, DOM or PDF styles/geometry,
Lex subclause diagnostics, proposed grammar and final disposition.
`owner_review.json` gives all 24 structural clusters, representative contexts,
the entire 16-occurrence finite-family packet and the final reason counts.
The frozen `passage_after_short_variant.jsonl.gz` is the 234-occurrence input,
not the current survivor count. Earlier passage censuses remain historical.

The Lex grammar recovers locally balanced semicolon assertions after a damaged
preceding item, requiring an explicit equivalence/gloss production and a terminal
source enclosure. It preserves canonical Lex items and delimiter diagnostics.
Heading assertions require the HTML lemma-heading DOM envelope and a complete
gloss or narrow grammatical-label production. PDF comparison lists require an
explicit marker, independent terminal punctuation, accepted semantic containment,
continuous layout and a reference-list grammar. Balanced short comparisons retain
the explicit comparison marker requirement. Citations acquire owners only through
exact containment in these recovered passages. No broad Lex ownership, proximity,
bibliography-derived boundary or generic prose envelope is introduced.

All 43 gains were source-validated: 33 HTML occurrences against raw DOM and all
ten PDF occurrences across nine facsimiles. Exact spans, productions, source
bindings and decisions are in `owner_grammar_positive_review.jsonl`. No false
owners were observed. Raw HTML, PDFs and rendered pages remain ignored in `work/`.
Positive and negative tests cover the production and rejection boundaries.

The 191 survivors remain **parser capability or boundary review pending**;
**zero are proven to lack an exact citable passage**. Ownership is not closed.
The largest precise reason groups are parenthetical source prose without a
canonical clause (47), PDF comparison layout continuity not established (36),
source-language/etymological statements (30), heading grammatical assertions (21),
missing comparison scope (13), and damaged Lex quotation/source delimiters (21).
The layout label records a failed conservative guard, not proven source damage.
The remaining 23 have the finer boundary/role reasons in the machine-readable
census. All 88 original failed comparisons and 91 unbounded cases are classified;
negative classification is not a scholarly finding that ownership is impossible.

The largest coherent remaining residue family is PDF quotation-adjacent unbounded
fragments (**2,108 alphabetic characters**), followed by reference/comparison
continuations (1,539) and lexical-substitution clauses (1,092). The next parser
tranche should recover quotation/gloss roles and nested source-note boundaries,
using the structural clusters to select source validation.

## Reproduction

Use the acquired immutable witness projections and a semantic-store snapshot of
clean `e26c885e06` in ignored storage. Run one full projection after the grammar
tranche stabilizes; the census itself can be regenerated without a full replay.

```bash
python3 scripts/finalize_badw_corpus_structure.py --output data/badw_forensic_structure --work work/badw_forensic_structure --contextual-semantics --baseline-store work/badw_forensic_structure/baseline_e26.sqlite --baseline-commit e26c885e06 --holdout-manifest data/badw_contextual_semantics/holdout.json --citation-reviews data/bibliography_forensic_citation_reviews.tsv
python3 scripts/build_badw_owner_review.py --store work/badw_forensic_structure/semantic.sqlite
python3 scripts/classify_badw_header_accounting.py --work work/badw_forensic_structure --output data/badw_forensic_structure
python3 scripts/classify_badw_forensic_residue.py
python3 scripts/verify_badw_semantic_replay.py --output data/badw_forensic_structure --work work/badw_forensic_structure --baseline data/badw_semantic_residue --baseline-store work/badw_forensic_structure/baseline_e26.sqlite --refine-boundaries
python3 scripts/build_status.py
```

## Historical provenance

The sections below preserve earlier tranches and their then-current counts.
They do not describe the current 191 survivors.

## Fresh positive source validation

`passage_positive_selection.json` freezes 37 feature-stratified positive passages
from the 159 gains (152 unique passages): 24 terminal comparisons, eight each
from PDF volumes 2–4; ten bounded comparisons; and all three rare productions
(variant-reading parenthesis, quoted translation, definition-source note).
Multiple citations, internal parentheses, wrapping and adjacent semantic structures
are represented. No terminal-semicolon-ended positive existed in this output;
semicolon-introduced comparisons are represented.

`passage_positive_review.jsonl` records the completed decisions, exact spans,
containers, citation identifiers, boundary evidence and source provenance.
Thirty-five PDF facsimiles and two raw HTML DOM examples were inspected.
No false ownership claims were observed in this sample. This is sample validation,
not inspection of every one of the 159 gains or completion of the 246-owner census.
The selection's pending status preserves its pre-inspection state; the separate
review decisions are authoritative.

Three source-review bindings were corrected explicitly: the neighboring PDF for
`tha dad du gnas pa` was replaced by the correct witness; `rtags` was checked on
printed p. 90 rather than the first candidate, p. 89; and `ṅed` was verified on
printed p. 24 while retaining the packet's reported p. 22. These are review
provenance corrections, not changes to runtime ownership or literal source text.

Reproduce the frozen selection with:

```bash
python3 scripts/select_badw_passage_positive_review.py --output /tmp/passage_positive_selection.json
```

The selector pins hashes of its ignored gain and source-packet inputs. Raw HTML,
PDFs and rendered images remain in ignored `work/` storage.

## Semicolon comparison implementation and replay

`semicolon_positive_review.jsonl` records all ten new passages, containing eleven
citations across nine independent PDF entries/pages. Actual facsimiles were
reviewed; no false owners were observed. The explicit `vgl.` marker and balanced
top-level semicolon bound a comparison within an accepted definition. Parenthetical
comparisons, malformed delimiters, full-sentence stops and crossing example/Lex./sense
components fail closed. Bibliography identity and citation position never supply
the boundary. Positive and negative tests exercise these exclusions.

The full 29,877-witness replay and all 114 frozen witnesses pass. All prior citation
owners, bibliography identities, xref bindings, language forms and source spans
are preserved. Meaningful untyped text remains 11,651 characters: this gain
surrounds already-accounted text rather than recovering missing lexical content.
The eleven gains were definition-contained citations in the preceding census;
definition-contained residue falls 20 to 9. The 88 coarse comparison rejections,
39 Lex-contained cases and other surviving families still require their broader
individual review. This is a tested implementation stopping point, not completion
of that review.

## Historical preceding tranche documentation

# Forensic source-structure replay

Baseline: `b677c3196c` (mixed-clause recovery). Source hashes and runtime code hashes are pinned in
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

The historical 405 unresolved owners are enumerated in `ownership_residue.jsonl.gz`.
The earlier `ownership_context_review.jsonl` retains the 408-case baseline review.
Three citations acquired owners through independently bounded quotation passages;
no proximity ownership was added. The remaining families are: explicit comparison
167, entry prose 155, no envelope 52, sense prose 20, PDF example candidates 6,
HTML example envelopes 3, and definition clauses 2.

## Definition integrity and quotation recovery

`definition_backaudit.json` records all **163 existing recovered definition
fragments**: **15 withdrawn or shortened**, with **zero remaining integrity
errors**. The source observations remain unchanged. Opening recovery now stops
before comparison/reference and grammatical introducers; `, vgl.` is withdrawn
and `tümer (` stops before the unmatched opener. Shared validation checks balanced
parentheses, brackets and quotation delimiters for recovered fragments. Unknown
decoding placeholders cannot become definition claims.

The separate `pdf-bounded-quotation-v1` grammar uses balanced nested quotation,
font runs, same-column line continuity and existing example/Lex. envelopes.
A conservative additional production requires an italic tilde-bearing example,
Roman quoted translation and immediately following existing citation. Hard sense,
Lex. and column boundaries stop recovery. Citation text is not translation text.
The corpus produces **three example–translation pairs and three new citation
owners**. Source text, source punctuation and original nodes remain immutable.

The header grammar also recovers chained fields across explicitly observed arrow
and superscript lines. It now produces **11,563 header fields**, including **2,218
relations**, **4,355 aliases**, 2,938 homonym markers, 1,464 grammatical labels and
588 verb forms. Twenty verb-form fields were added; relations and aliases did not
increase. Shared tense/list grammar remains conservative.

| Meaningful pending alphabetic characters | Before | After |
| --- | ---: | ---: |
| Total | 12,260 | 11,670 |
| HTML | 3,766 | 3,766 |
| PDF lexical prose | 5,806 | 5,527 |
| PDF header candidates | 738 | 668 |
| PDF aliases | 692 | 615 |
| PDF quotation/gloss | 1,101 | 937 |
| PDF reference clauses | 157 | 157 |
| PDF total | 8,494 | 7,904 |

The unchanged 131,068 raw alphabetic characters partition exactly into **42,433
typed**, **66,349 structural-label**, **10,616 decoding-placeholder**, and **11,670
pending meaningful** characters. The 590-character pending reduction includes
accounting changes and withdrawals; it is not 590 newly interpreted semantic
characters. No reviewed glyph mapping was added.

The remaining 5,527 PDF prose characters have explicit reasons:

| Reason | Characters |
| --- | ---: |
| Quotation-adjacent fragment lacking a unique role/envelope | 2,108 |
| Reference target/comparison continuation | 1,558 |
| Lexical substitution clause with unresolved internal roles | 1,092 |
| Mixed/Roman clause lacking syntactic closure | 333 |
| Wrapped form/clause lacking a role boundary | 293 |
| Isolated form/clause fragment | 112 |
| Body/header alias continuation | 31 |

All quotation, comparison, substitution and header candidates were replayed through
the new rules. Most do not satisfy the conservative productions. No broader
comparison or substitution grammar was accepted without sufficient source evidence.
The separate 157 reference-clause characters remain unresolved. HTML's 2,793
other-heading characters still comprise 641 register/grammatical-label characters,
973 shared/composite syntax and 1,179 unregistered wording. Other HTML residue is
608 quotation/gloss, 234 aliases, 95 headers and 36 reference characters. These
are retained diagnostics, not newly accepted semantic relations or labels.

## Validation and limits

`quotation_holdout.json` freezes **36 fresh PDF entries on 36 independent pages**,
twelve each from acquired volumes 2, 3 and 4, before implementation outcomes.
`quotation_review.jsonl` records facsimile review and explicit recall limitations.
No false new structural claim was observed, but **none of these 36 entries received
a new fragment**. This is negative/control and retention evidence, not independent
positive validation of the three new corpus pairs. All three actual positive corpus outputs were separately checked against their
facsimiles (khrims gtugs p. 110, thub p. 275, mtha’ dag p. 334), with correct
roles and boundaries and no swallowed citation or neighboring example.
`quotation_positive_review.jsonl` preserves exact spans and source hashes. This
is a complete positive-output census, not a fresh independent positive holdout.
Broader positive validation remains necessary before expanding recall. The previous mixed-clause holdout and
all frozen relationships remain unchanged.

All **29,877 projections and 114 frozen witnesses pass**; reader integrity failures,
accepted bibliography identity loss and Lex. overlaps remain zero. Citations remain
109,425; identities 109,079 accepted / 346 unresolved. Owners rise **109,017 →
109,020**, unresolved **408 → 405**. Passage owners number 109,007 plus 13 reviewed
relationships; 47,039 sense-owned and 61,981 entry-only citations are a separate
ownership dimension, not additional citation counts. Lex. remains 39,688 items;
xrefs remain 7,484 resolved / 852 unresolved; Sanskrit remains 12,364 forms and
3,003 correspondences, with zero effective conflicts and 384 preserved source
observation overlaps. `release/current` is untouched.

**Not structurally mature.** The single remaining coherent capability is
**quotation-role disambiguation beyond explicit tilde/example envelopes**: 2,108
quotation-adjacent prose characters plus 937 separate quotation/gloss candidates.
Balanced punctuation now supplies boundaries, but does not by itself establish
translation/example/definition roles. Additional typography-and-layout productions
need independently reviewed positive examples. Neither broad quote absorption nor
generic boundary cleanup is justified. This tranche implements a safe subset;
it does not claim completion of the requested quotation recall.

## Reproduction

Run from the repository root with the acquired source cache and baseline SQLite:

```sh
python3 scripts/finalize_badw_corpus_structure.py --output data/badw_forensic_structure --work work/badw_forensic_structure --contextual-semantics --baseline-store work/badw_forensic_structure/baseline_dcac.sqlite --baseline-commit dcac807f73 --holdout-manifest data/badw_contextual_semantics/holdout.json --citation-reviews data/bibliography_forensic_citation_reviews.tsv
python3 scripts/classify_badw_header_accounting.py --work work/badw_forensic_structure --output data/badw_forensic_structure
python3 scripts/verify_badw_semantic_replay.py --output data/badw_forensic_structure --work work/badw_forensic_structure --baseline data/badw_semantic_residue --baseline-store work/badw_forensic_structure/baseline_dcac.sqlite --refine-boundaries
python3 scripts/classify_badw_forensic_residue.py
python3 scripts/backaudit_badw_recovered_definitions.py
python3 scripts/build_status.py
```

Manual review files are scholarly observations retained separately from generated
diagnostics. Runtime code hashes describe the replay; postprocessing hashes
describe subsequent classification/status generation.

## Exact short variant correction

A balanced short variant note is accepted only with an explicit `r.` or `v. l.`
introducer, an exactly coincident source correction node, and containment in an
existing example. No broad Lex./definition containment or proximity is used. The
sole new corpus output is `gleb mo`, volume 2, printed page 298 (scan page 1 of
`/pdf/glo`), inspected against the facsimile and recorded in
`passage_positive_review.jsonl`. Its correction note is separate from the German
translation and outer K1 citation. One owner is gained; meaningful accounting is
unchanged. Negative tests cover absent/misaligned corrections, definition-only
containers, malformed delimiters and already-owned citations.

Reproduce the current census after the documented replay with:

```sh
python3 scripts/census_badw_passage_residue.py --work work/badw_forensic_structure --output data/badw_forensic_structure --store semantic.sqlite --name passage_after_short_variant
```
