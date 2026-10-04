# BAdW Source Integration Architecture

## Status and scope

This document records the architecture for integrating the BAdW digital *Wörterbuch der tibetischen Schriftsprache* (WTS) with WtSOCR. It separates a print-faithful transcription from an enhanced editorial source layer. It does not authorize heuristic substitutions or the silent replacement of printed readings.

BAdW is a special source because the project describes its database as the editors' working system and states that the database generates the LaTeX templates used for publication. The database articles are therefore a primary, first-party machine-readable editorial source, not merely another OCR witness. See the BAdW descriptions of the [dictionary database](https://wts.badw.de/en/dictionary-database.html) and the [digital WTS](https://wts-digital.badw.de/).

## Observed public corpus, 2026-09-01

A systematic enumeration of the public search results found 28,245 distinct article results:

- 18,039 database-backed HTML articles;
- 10,206 generated article PDFs.

The observed delivery mode by published volume is:

| Volume | Published range | Public digital form |
| --- | --- | --- |
| 1 | ka–bskrod pa | Database articles |
| 2 | kha–bsgron | Generated PDFs |
| 3 | nga–bsnyol | Generated PDFs |
| 4 | ta–sthul | Generated PDFs |
| 5 | da– | Database articles |
| 6 | na– | Database articles |
| 7 | pa/pha tranche | Database articles |
| 8 | ba–sbron pa | Database articles |
| 9 | ma–smros | Database articles |

This empirical catalogue, rather than general informational copy on the site, is the operational description of current database/PDF coverage. Counts and coverage are observations at the date above and must be regenerated when the catalogue is refreshed.

## Source hierarchy and two layers

WtSOCR maintains two related but distinct products.

### 1. Print-faithful WTS

The existing corrected OCR and release remain a faithful digital representation of the published WTS. The registered scans of the published volumes are authoritative when deciding what the print-faithful layer should contain.

An aligned BAdW article may supply a correction automatically when it identifies OCR damage unambiguously, supplies the exact replacement, and is compatible with the printed source. BAdW must not silently replace a printed reading when the difference could be a post-publication editorial revision.

### 2. BAdW / editorial source layer

BAdW is the preferred clean, first-party machine-readable source for an enhanced editorial layer. WtSOCR intends to acquire as much of the publicly exposed database and generated-PDF corpus as practicable into an ignored, content-addressed local cache; parse it without OCR-style cleanup; and align it systematically with the print-faithful corpus.

Substantive BAdW-versus-print revisions are retained as structured variants. They are not discarded, but they do not alter the print-faithful layer unless the published page independently supports the change.

The resulting hierarchy is therefore layer-specific:

| Question | Controlling source | Supporting evidence |
| --- | --- | --- |
| What did the published WTS print? | Registered published scan | Confidently aligned BAdW text and exact reviewed evidence |
| What is the current BAdW editorial reading? | Public BAdW database article or generated PDF | Cached source object, parsed record, and alignment ledger |
| How are the readings related? | Exact span alignment with provenance | Difference classification and print-check status |

## Correction policy and confidence gates

The project forbids broad **heuristic** OCR rules such as global character substitutions. It does not forbid source-backed bulk corrections. Individual manual approval is not required for every change when all of the following are true:

1. BAdW article identity is unambiguous.
2. The corresponding BAdW and WtSOCR spans align unambiguously.
3. BAdW supplies the exact replacement reading.
4. The target field is not editorially mutable, or a print check establishes that BAdW reproduces the printed reading.
5. The difference is classified as OCR damage rather than presentation, structure, or substantive editorial revision.
6. Complete machine-verifiable provenance is retained.

Ambiguous identity, ambiguous span alignment, mutable semantic prose, and evidence of a print-versus-online change require a print check or review. BAdW has been observed to contain substantive post-print revisions, including changes to German meaning text, so database text cannot be treated as a blanket replacement for a diplomatic transcription of the printed edition.

## Provenance ledger

Every proposed or applied BAdW-backed difference must retain at least:

- the stable BAdW URL;
- UTC fetch time and cryptographic hash of the fetched source object;
- an exact source-record and source-span locator;
- the exact local volume, page, line, token, and intra-token span as applicable;
- the original and proposed readings;
- the article-identification and span-alignment methods and confidence values;
- the difference classification and target layer;
- print-check status and print-page reference when relevant; and
- parser/decoder versions sufficient to reproduce the evidence.

The proposed field contract is recorded in [`data/badw_correction_evidence.schema.tsv`](../data/badw_correction_evidence.schema.tsv). A future evidence ledger must be validated against that contract before it can drive corrections.

## Raw source and redistribution policy

Fetched BAdW HTML and PDFs, decoded bulk article text, rendered pages, and intermediate corpora stay under an ignored `work/` directory in a content-addressed cache. They are not committed or published as part of the repository. Tracked code, tests, small non-substantial fixtures, source metadata, and coordinate-level derived evidence may be considered separately.

Before an identity, parsing, or reconciliation run consumes that ignored material, it must pin an immutable offline source snapshot: designated canonical-page and crosswalk inputs, glyph-registry version, cache request/object integrity, and known page/glyph residuals. The reusable snapshot tool records hashes and source-quality observations without copying BAdW text into Git; later work must name the snapshot it used rather than treating `work/` as an unversioned current source.

Lexical extraction additionally requires a verified source contract: the frozen cache index, parsed database-article JSONL, and every emitted lexical span must agree on source identifier, object hash, source field, and offsets. SQLite construction rejects unverified or out-of-range spans and records the verification hashes in its local metadata.

Parsing must preserve the original BAdW Unicode. WtSOCR OCR correction rules must never be applied to the cached or parsed BAdW source text.

`scripts/refresh_badw_canonical_pages.py` refreshes canonical decoding offline into a new immutable tree, checks source hashes and positioned glyph geometry, and emits a page-ID crosswalk and fresh unknown-glyph census. Historical observations remain preserved; downstream witnesses, parses, and verified snapshots must be rebuilt against the new tree. `scripts/migrate_badw_pdf_reviews.py` proposes review migrations only where source identity, run anchors, and reviewed text remain unchanged. Changed text requires renewed source review. Exact source-hashed boundary evidence can describe malformed quotation punctuation without changing the literal text. Typography-supported quote-internal LoC/gloss pairs in `Lex.` sections remain lexicographic parallels, not Belegstellen; explicit reviewed semantic roles take precedence. Unknown ink remains a blocker, unlike reviewed zero-outline layout glyphs.

## Generated PDFs for volumes 2–4

The per-article PDFs for volumes 2–4 are digitally encoded sources, not images to be sent directly to OCR. They use embedded subset fonts and CID-coded content without adequate `ToUnicode` maps. The current experiment has demonstrated complete recovery of sampled TGaramond/WTS body glyphs, including the WTS transliteration in the tested material. The mapping of Rabten Tibetan-heading glyphs remains incomplete.

The implementation must attempt deterministic font/content-stream decoding first. Rendered-page OCR is a fallback only for content that cannot be recovered at the font level.

## Staged implementation

### Stage A — harden the tools

Harden and test the catalogue/harvester, database-article parser, article reconciliation, and PDF font decoder. Define reproducible interfaces between cached source objects, parsed records, alignments, and evidence rows. Use only small, reviewable fixtures in tests.

### Stage B — acquire the public corpus

Resumably acquire the complete publicly exposed BAdW database/PDF corpus into the ignored content-addressed cache, retaining request URL, fetch time, response metadata, and content hash.

### Stage C — improve article identification

Improve WtSOCR entry segmentation and BAdW-to-local article identification substantially beyond the current 68.3% experimental success rate. Measure performance by volume, letter, delivery form, and ambiguity class. The Latin transliteration in the WTS is the historical Library of Congress (LoC) system, not Wylie; source identity and normalization code must use that terminology.

The first Stage C2 deliverable is a deterministic source snapshot and identity graph. It keeps individual BAdW HTML/PDF witness occurrences, source provenance, and low-confidence candidate associations separate from provisional local-entry anchors. A local anchor is not a final canonical dictionary-entry identity, and no candidate association is silently promoted to one.

Stage C3 records the complete deterministic candidate set for every attempted BAdW-to-local identity association, including the exact LoC headword, Tibetan-heading, and printed-page evidence for each candidate. It deliberately does not collapse an ambiguous candidate set to its first-ranked member, compare article prose, or generate correction evidence.

Stage C4 begins from the local corpus alone: QA `headword_line` coordinates are materialized as stable provisional anchors (`volume:page:line`) while the legacy `entry_id` remains provenance. This exposes rare over-merged or unheaded QA groups without changing CURRENT text or inferring boundaries. A later reconciliation pass may use these exact anchors, but must still retain candidate ambiguity and source provenance.

Stage C5 replays source identity using those coordinate anchors rather than legacy QA grouping. It matches only the LoC/Tibetan headword and the anchor start page; coarse inferred anchor ranges are deliberately not treated as article boundaries or prose evidence. The C3 source snapshot remains frozen, and this identity-only work neither reconciles BAdW prose nor changes the print-faithful release.

Stage C6 replays C5 witnesses from that frozen candidate set through a stricter dual-evidence gate without changing a source or local reading. It preserves raw QA Tibetan, the raw LoC field, and the bounded LoC display reconstruction as distinct fields. A generated-PDF witness can be promoted only when one candidate has exact LoC and Tibetan identity plus exact printed-page support. A database witness with exact dual headings remains a candidate until an independent BAdW source discriminator resolves it; one-field and page-only matches never promote an identity. This is an identity gate, not prose reconciliation or correction evidence.

Stage C11 materializes the C6/C10 results as a snapshot-bound identity handoff. It verifies the immutable source snapshot, retains every candidate edge, and exposes a provisional local anchor only where the existing strict dual-evidence or two-sided-neighbourhood gate is met. Later lexical work may consume confident links only; candidate edges never populate a final entry-witness association. This remains identity work, not source-text reconciliation.

### Stage D — reconcile the print-faithful corpus

Produce a corpus-scale ledger of exact differences and provenance. Automatically apply only source-backed OCR corrections that pass the confidence gates to the print-faithful layer, with deterministic rebuilds and audit checks.

### Stage E — expose editorial variants

Represent substantive post-print BAdW readings as a separate enhanced/editorial layer linked to their print-faithful counterparts. Preserve both readings and their provenance.

The lexical-record contract is [`data/lexical_record_contract.schema.tsv`](../data/lexical_record_contract.schema.tsv). It represents entries, ordered senses, Tibetan attestations/Belegstellen, citations, bibliography records, cross-references, and editorial variants as separately identified, source-spanned records. The BAdW HTML extractor emits this contract from the ignored cached parser corpus, preserving unresolved citation authority and entry-level attestations rather than guessing a bibliographic or sense association. It does not assert that the existing OCR or source cache has already been fully reconciled or parsed into a shared edition.

## Nested candidate backend and bibliography gates

The local SQLite backend keeps HTML lexical records and PDF article witnesses separate. PDF analysis has an ordered article/division/item candidate tree, not a flat list presented as verified senses. Every extracted component must have exactly one tree owner, including explicit unassigned nodes; importing a lost, duplicated, or changed component fails. Unsegmented source divisions remain unsegmented, and candidate ownership does not assert a reviewed semantic relationship. Literal `(r. ...)` apparatus and source anchors remain attached without interrupting Tibetan examples.

HTML citation-to-authority links require the exact source DOM span. PDF siglum spelling matches against those first-party tooltip authorities are weaker, separately stored expansion candidates: they do not establish an edition, bibliography record, or owning example. Matching preserves original Unicode and offsets, uses no fuzzy/OCR rules, and retains overlapping labels and competing authorities as ambiguous. Every PDF citation receives a status, including unmatched citations. Bibliographic identification and semantic ownership must be evaluated separately.

Reviewed nonprinting glyph identities may be excluded from derived semantic text only with exact font/style/CID/outline evidence. Their raw unknown tokens remain in the source-faithful representation; this is neither a guessed Unicode mapping nor permission to ignore unknown ink.

Whole-article structural validation must precede promotion of PDF candidates to verified lexical records. `scripts/build_badw_structural_review_packet.py` selects a deterministic, source-only stratified packet across HTML and PDF volumes 2–4, with a held-out portion, source hashes, and empty annotation fields. The packet deliberately excludes predicted semantic labels. Generating a packet or eliminating unresolved quotation dispositions is not an independent review and does not prove sense boundaries or citation ownership correct. Completed source-bound annotations must test definitions, senses, Tibetan/German pairs, lexicographic parallels, apparatus, and citation edges before a shared production model or public interface treats these as facts.

Source-component extraction retains complete HTML Tibetan containers and their individually tagged segments, including explicit unresolved gaps when only a segment envelope is available. Lex. blocks retain their complete source extent, balanced-delimiter clauses, tagged language fields, and quotation candidates without inferring citation ownership. PDF Lex. extents ending at a source-division boundary remain candidate extents, not verified semantic boundaries. PDF italics alone do not identify a language: literal Sanskrit labels may establish bounded fields, while unlabeled italic spans remain explicit unresolved source material. The structural projection carries the original source structures alongside its candidate graph so a partial graph cannot conceal omitted material.

Terminal siglum-shaped parentheses in HTML Lex. clauses are explicit unresolved citation candidates, not accepted bibliography links or semantic ownership assertions. Explicit metrical tags retain their qualifier spans. A PDF German-gloss candidate is narrower than a complete source division or canonical sense envelope: opening aliases, adjacent reference material and Tibetan punctuation remain in the source representation rather than being relabelled German. Lost German continuation text must nevertheless be recovered, including before a reference that wraps onto subsequent lines. Reviewed wider definition envelopes remain exact-score disagreements; this distinction does not rewrite the benchmark or settle canonical sense boundaries.

The structural benchmark keeps exact-span and nesting/edge scores separate from a terminal-whitespace-only diagnostic. That diagnostic does not rewrite source text, join lines, remove punctuation, or excuse missing language fields, reference targets, or semantic relationships. Improved development scores do not open the production or citation-ownership gate until substantive omissions and source-bound review have been addressed.

## Scholarly data architecture

The intended product is a source-faithful, queryable scholarly dictionary, not merely cleaned OCR. The following four **logical** layers supply its conceptual spine. They are not four new databases, and they do not replace the existing source cache, lexical-record contract, bibliography authority model or SQLite backend. The print-faithful/BAdW-editorial distinction cuts across these layers: neither source witness silently replaces the other.

| Layer | Contents | Boundary |
| --- | --- | --- |
| Source observations | Immutable response bytes; source-faithful text; DOM/PDF locations, typography, explicit tags, links and literal apparatus | An extraction is a versioned observation of the bytes, not an infallible transcription or a semantic interpretation |
| Scholarly annotations | Language identification, form mentions, structural interpretation, citation resolution/ownership, grammar, corrections and review decisions | Candidates, accepted claims, rejected claims and supersessions remain distinguishable; an inferred claim must not masquerade as a source tag |
| Canonical entities and relationships | Entries, witness-specific senses, forms, works, editions/publications, source abbreviations and typed graph relationships | Entity identity is separate from a spelling, source occurrence, local OCR anchor or ranked candidate; containment is not semantic ownership |
| Derived representations | Corrected readings, normalized Wylie, Tibetan-script conversion, English translation, search indexes and presentation | Every transformation retains its input, method/version and provenance; no derived string overwrites its source |

Start with witness-specific senses rather than forcing print and online divisions into one canonical sense sequence. Alignments and editorial variants may relate them later. A headword spelling is not an entry identifier; a source URL alone is not a timeless witness identifier. Existing source hashes, occurrence IDs and accepted identity links should anchor migration. Do not invent a parallel entry schema or a generic entity/attribute framework to implement these distinctions.

### Selectors, review and versioning

An annotation must bind a particular witness and extraction view: raw source hash(s), view contract/version, view hash, text hash, exact literal text, ordered half-open Unicode ranges and available physical anchors. Discontinuous spans are legitimate. DOM locations and PDF page/run/glyph evidence must remain available even when a convenient review-text range is used. OCR coordinates retain their separate positive, 1-based token convention.

`data/badw_semantic_annotation.schema.tsv` and `scripts/badw_semantic_annotations.py` introduce only a small `language_span`/`form_mention` overlay on the existing frozen structural review packets. The validator replays text ranges and physical selectors, verifies cached source/canonical-page hashes and retains superseded claims. PDF run/style envelopes are not glyph-exact selectors; an HTML visible-text range is not a claimed DOM-node location. This pilot does not yet supply production semantic entities, ownership, transformations or a complete annotation framework. Its four reviewed records in `data/reviewed_badw_semantic_annotations.jsonl` are prediction-exposed development evidence, not independent benchmark gold or proof that extraction is complete.

Review status and evidence strength must stay separate. Acceptance records who reviewed what, how and against which source; it does not imply independent review. Frozen historical views are never rewritten to match a new extractor. New extraction versions require source-checked migration/review of annotations, not blind reuse of offsets. Supersession preserves the previous claim and reason/evidence for its replacement. Deterministic builds record input hashes and software/contract versions; fetch time establishes an observation date, not the date an editor changed the article.

Original transcription, reviewed OCR correction, normalization, script conversion and translation are distinct operations with distinct parents. A correction can derive a print-faithful reading only through the established print-compatibility gates. Normalized Wylie is a later derived layer: the literal WTS transliteration is historical LoC, not Wylie. Translation links an English rendering to a particular German span/version, not to an unversioned entry blob.

### Language and Sanskrit

Preserve literal source classifications and scholarly identifications separately. Explicit `skt.` labels and HTML tags are source evidence; unlabeled italics alone are not a language classifier. A reviewed Sanskrit span may overlay otherwise unclassified text without inventing a missing source tag. Wraps and hyphens, including `cai-\ntyāṅganaḥ`, remain literal; any joined reading is a separately justified derivation.

German-inflected `Viṣṇus` remains literal German-context text. A reviewed form-mention annotation can relate it to Sanskrit `Viṣṇu` without declaring the whole inflected token a literal Sanskrit passage or replacing the spelling. The same distinction generalizes to names, quotations and embedded forms: language, mention of a form and lexical identity are different claims.

### Cross-reference graph

Retain each reference occurrence with its literal arrow/link text, source span, direction, HTML href or printed target, and witness. An explicit href establishes a source link, not necessarily a unique canonical-entry resolution. Printed ↑/↓, other entry links, stem/form references and ambiguous homonyms require separately typed interpretations and target-resolution claims. Preserve candidate targets and unresolved occurrences; proximity or the first search result is not a resolution rule.

An accepted edge links an occurrence to a canonical target and records the evidence, relation type, method and review. Direction, target interpretation and entity resolution remain independently revisable. Queries can then traverse accepted edges while exposing ambiguous alternatives and the original source link. Related stems/forms need their own entities/relationships rather than being squeezed into entry identity. This is an extension of the existing cross-reference/source-span records, not a second graph maintained beside them.

### Bibliography and citation queries

Reuse the existing work/publication/abbreviation, print-only authority and publication-relation infrastructure. A literal citation occurrence, canonical work, edition/publication, printed year, locator and owning example/sense are separate claims. Resolving a work does not verify an edition or page; locating a citation inside a source division does not establish its semantic owner. An absent online author-year row must not erase a reviewed print-only authority or force a year substitution.

“Every citation of this book” should query resolved occurrence-to-work links, optionally restricted by edition, witness, locator-verification or review status. It must also expose unresolved candidates rather than count them as accepted links. Source-specific bibliography wording and editorial year/edition discrepancies remain recoverable as variants and reviewed relationships. BibTeX is an export of bibliography metadata, not the identity model or a replacement for source evidence.

## Roadmap from source corpus to scholarly dictionary

These are scholarly architecture stages, not a renumbering of the historical acquisition/reconciliation stages above. Each gate concerns correctness as well as coverage; later work must not erase uncertainty to meet a percentage.

| Stage | Build and completion evidence | Explicitly defer |
| --- | --- | --- |
| A — stable boundaries | Document the four layers; validate a small source-bound annotation pilot with exact Unicode ranges, cached hashes, anchors, review modes and supersession. Map existing structures to the layers rather than duplicate them | Universal annotation engine, database rewrite, inferred ownership |
| B — source fidelity | Finish source-component extraction for HTML/PDF; review complex boundaries, Lex., multi-segment Tibetan, Sanskrit and links. Keep exact structural scores, representational diagnostics and substantive losses separate. Independently reviewed stratified evidence and a tested lossless source-to-component path must justify opening the structural gate | Treating all development mismatches as conventions; production promotion |
| C — scholarly annotations | Add bounded, source-reviewed language/form, grammar and structure claims; then citation-ownership review/challenge only after B. Validate nesting, unresolved material and evidence-specific associations, with held-out accuracy by phenomenon | Proximity ownership; canonicalizing competing interpretations |
| D — canonical relationships | Reuse bibliography work/edition and entry/witness identity machinery; resolve explicit and printed references into typed edges. Test homonyms, ambiguous targets, edition/year discrepancies and locator correctness independently | Forcing one target or edition; collapsing editorial variants |
| E — production projection | Extend the existing lexical contract/SQLite schema only for demonstrated needs. Fail closed on missing provenance, lost components, invalid accepted links or stale versions; test reproducible imports and complete entry-page component addressability | A public entry view that treats candidate structure as fact; speculative technology migration |
| F — derived readings | Add versioned normalization/Wylie, Tibetan conversion and later German-to-English translation, each with reversible source links and independently tested difficult cases | Replacing literal LoC/German; using translation to infer source structure |
| G — queries and interface | Provide research queries over components, witnesses, senses, forms and sources; test graph traversal and provenance drill-down, then build a polished public dictionary | A UI hiding unresolved claims or presenting coverage as verified accuracy |

The next bounded tranche after the annotation pilot is to repair demonstrated source/projection losses and agree evidenced structural boundaries while retaining unchanged benchmark gold and exact scoring. Semantic annotations are reported separately from extractor matches. The 120-packet independent review, including its held-out portion, remains an outstanding gate; a four-span development overlay does not open citation ownership or production projection.
