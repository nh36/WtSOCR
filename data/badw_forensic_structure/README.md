# Source-supported assertion tranche (cfd770283e baseline)

The full replay projects **29,877/29,877 witnesses** and establishes **109,293
citation owners**, leaving **132 unresolved** (29 HTML / 103 PDF), down from 191.
The **59 gains** comprise **29 source-supported assertions** (17 definition,
11 source-language and one grammatical assertion), **21 HTML heading assertions**
and **nine PDF punctuated comparison lists**. All 114 frozen witnesses pass;
baseline owners, bibliography relationships, xrefs, language observations, Lex.
items, source spans and reader integrity are preserved. `release/current` is untouched.
Citations remain 109,425; bibliography identities remain 109,079 accepted / 346 unresolved.

Meaningful alphabetic residue falls **995 characters: 11,072 → 10,077**.
HTML heading grammar accounts for **613** (3,219 → 2,606); PDF assertion and
comparison grammars account for **382** (7,853 → 7,471). Raw alphabetic gaps
remain 131,068, partitioned into **44,692 typed, 66,298 structural labels,
10,001 decoding-placeholder syntax and 10,077 pending**. The typed increase
also includes characters previously counted as labels or placeholder syntax;
that increase is not reported as meaningful-residue reduction.

## Frozen current-survivor census and source validation

`assertion_baseline_cfd.jsonl.gz` freezes the actual **191** survivors from clean
`cfd770283ecbb21758b9e2eb16fbc00dde5525fd`: 50 HTML and 141 PDF. Its summary
records HTML comparison 19, example one, Lex 15, missing component 15; PDF
comparison 55, definition nine, example three, Lex six, missing component 68.
The earlier 234-row census is historical, not current input.

`assertion_owner_review.jsonl.gz` retains every baseline occurrence, exact citation
span, local source context, canonical components, punctuation/enclosure, raw DOM
or PDF run/line geometry, structural diagnostics and final disposition.
`assertion_owner_review.json` reports all 23 source-grammar clusters and the
finite leftover packet. `assertion_after.jsonl.gz` is the fresh 132-survivor census.
All **59 gains** have exact source bindings and decisions in
`assertion_positive_review.jsonl`: all **38 PDF positives** were inspected in
facsimiles, and all **21 HTML positives** against raw descriptive-sibling DOM.
Raw sources and renderings remain ignored in `work/`.

The 47 parenthetical-source cases were clustered before implementation:
31 sentence-terminal, seven semicolon-bounded, six comma continuations and
three source parentheses followed by comparison. The new coherent
`source_supported_assertion` production requires an accepted sense/division
scope, a definition opening or explicit language/grammatical production,
independent top-level sentence/semicolon punctuation and physical continuity.
Only then does the balanced terminal source parenthesis validate the assertion.
Citations, definitions, linguistic forms and language identifications remain
separate leaves. Competing examples, Lex, xrefs, translations and multiple
source-note subclauses block promotion. Citation identity supplies no boundary.

HTML extensions require the descriptive sibling of the lemma and a complete
finite heading construction (category, function, register or coordinated label).
Legacy accepted narrower owners take priority. Arbitrary heading prose is rejected.

The original 36 PDF layout failures comprise **14 same-baseline font-run splits,
two ordinary wraps and 20 combining both**. The old observation coordinates
used unscaled text moves. Exact cached PDF decoding supplies derived physical
geometry only after run indices, CIDs, fonts and Unicode match the immutable
observations. Same-page/column, forward-baseline and ordinary leading checks
replace the false discontinuity guard; source observations are never rewritten.
Negative controls cover new senses, examples, Lex, columns and entries.
The existing independent comparison punctuation/reference grammar remains required.

## Final unresolved reasons

All **132** remain parser-capability or source-boundary-review cases.
**Zero are established to genuinely lack an exact citable passage**; ownership
is not closed. A failed delimiter or current scope guard is not proof of
intrinsic unownability. Exact per-occurrence evidence is in the review JSONL.

| Reason | Occurrences |
| --- | ---: |
| Lex local quotation delimiter failure | 10 |
| Lex local source parenthesis failure | 10 |
| Lex source decoding and quotation failure | 1 |
| assertion competing semantic components | 9 |
| assertion continuation or editorial opening grammar missing | 37 |
| assertion independent punctuation or delimiter recovery missing | 2 |
| assertion multiple source notes require subclauses | 1 |
| comparison canonical scope missing | 13 |
| comparison competing source components | 1 |
| comparison independent right boundary missing | 8 |
| comparison reference label split across font runs | 29 |
| comparison reference or prose grammar incomplete | 5 |
| example nested or damaged translation quotes | 3 |
| example nested variant note role missing | 1 |
| scholar led etymological assertion grammar missing | 2 |

The 29 split-label comparisons need PDF reference-run composition, not wider
citation-based boundaries. Reference locators, additional prose and xref scope
remain separate grammar gaps. The 21 Lex failures cluster into ten malformed
source parentheses, ten quotation delimiters and one decoding/quotation failure;
no additional independent local assertion survives the existing segmentation.
Malformed punctuation is preserved, including when sound later assertions exist.
Four example leftovers require nested variant-note or translation-quotation roles.

## Remaining structural capability and next tranche

The largest coherent residue remains **PDF quotation-adjacent unbounded fragments
(1,946 characters)**, followed by **reference/comparison continuations (1,501)**
and **lexical-substitution clauses (1,092)**; PDF quotation/gloss candidates are
815. These counts do not justify a neutral quotation absorber.

One further online-parser tranche is justified before historical-print adaptation
or reader-product work: compose PDF reference labels across font runs, then
recover independently bounded assertion continuations and multiple-source-note
subclauses using fresh positive validation. Broad quotation-role inference should
follow a focused typography/delimiter investigation only after those safer
capabilities are exhausted.

## Reproduction

Use immutable acquired projections and the clean baseline semantic-store snapshot
in ignored storage. Freeze the baseline census before modifying grammars. Run
one full projection after the batch stabilizes, then regenerate final evidence.

```bash
python3 scripts/finalize_badw_corpus_structure.py --output data/badw_forensic_structure --work work/badw_forensic_structure --contextual-semantics --baseline-store work/badw_forensic_structure/baseline_cfd.sqlite --baseline-commit cfd770283ecbb21758b9e2eb16fbc00dde5525fd --holdout-manifest data/badw_contextual_semantics/holdout.json --citation-reviews data/bibliography_forensic_citation_reviews.tsv
python3 scripts/build_badw_owner_review.py --census data/badw_forensic_structure/assertion_baseline_cfd.jsonl.gz --packets work/badw_forensic_structure/assertion_survivor_packets.jsonl --output data/badw_forensic_structure/assertion_owner_review --baseline-commit cfd770283ecbb21758b9e2eb16fbc00dde5525fd --store work/badw_forensic_structure/semantic.sqlite --prior-review data/badw_forensic_structure/owner_review.jsonl.gz
python3 scripts/census_badw_passage_residue.py --store work/badw_forensic_structure/semantic.sqlite --name assertion_after
python3 scripts/classify_badw_header_accounting.py --work work/badw_forensic_structure --output data/badw_forensic_structure
python3 scripts/classify_badw_forensic_residue.py
python3 scripts/verify_badw_semantic_replay.py --output data/badw_forensic_structure --work work/badw_forensic_structure --baseline data/badw_semantic_residue --baseline-store work/badw_forensic_structure/baseline_cfd.sqlite --refine-boundaries
python3 scripts/build_status.py
```

## Historical provenance

The sections below preserve earlier tranches and their then-current counts.
They do not describe the current 132 survivors.

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
