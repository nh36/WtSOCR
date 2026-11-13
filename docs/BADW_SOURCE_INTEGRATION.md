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

Where a tagged HTML field crosses a trimmed Lex. clause boundary, its exact source intersection may be projected while retaining the original field locator. This must not widen the clause or turn source containment into semantic ownership. A preserved unclassified PDF form is not a missing source string, but still requires a separately evidenced language/form annotation before semantic completeness can be claimed.

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

`data/badw_semantic_annotation.schema.tsv` and `scripts/badw_semantic_annotations.py` supply a bounded `language_span`/`form_mention`/`relationship` overlay on the existing frozen structural review packets. The validator replays text ranges and physical selectors, verifies cached source/canonical-page hashes and retains superseded claims. PDF run/style envelopes are not glyph-exact selectors; an HTML visible-text range is not a claimed DOM-node location. The structural projection may apply validated, accepted language claims without changing source text or inventing source tags. Reviewed relationships are emitted separately as `semantic_relationships`, not physical parents or benchmark edges. Exact endpoint types/ranges must each bind one extracted node; missing or ambiguous endpoints fail closed. A citation may have multiple explicitly reviewed targets, but neither proximity nor containment establishes ownership. The ledger's 18 active language claims (14 Tibetan, four Sanskrit), one form-mention claim, one superseded evidence note and 18 relationship claims are prediction-exposed development evidence, not independent benchmark gold or proof of corpus-wide accuracy. This overlay does not supply production semantic entities, transformations or a universal annotation framework.

Review status and evidence strength must stay separate. Acceptance records who reviewed what, how and against which source; it does not imply independent review. Frozen historical views are never rewritten to match a new extractor. New extraction versions require source-checked migration/review of annotations, not blind reuse of offsets. Supersession preserves the previous claim and reason/evidence for its replacement. Deterministic builds record input hashes and software/contract versions; fetch time establishes an observation date, not the date an editor changed the article.

Citation endpoints may also bind a reviewed `citable_passage`: one exact source-bound range with literal text, physical selectors and review provenance. These extents live in a separate annotation overlay, not the extracted node tree. They do not split a definition, invent a sense, or change Lex. containment. A relationship must bind exactly one accepted passage or extracted node; missing or duplicate extents fail closed. Grouped support uses multiple explicit targets rather than an enlarged envelope.

Original transcription, reviewed OCR correction, normalization, script conversion and translation are distinct operations with distinct parents. A correction can derive a print-faithful reading only through the established print-compatibility gates. Normalized Wylie is a later derived layer: the literal WTS transliteration is historical LoC, not Wylie. Translation links an English rendering to a particular German span/version, not to an unversioned entry blob.

### Language and Sanskrit

Preserve literal source classifications and scholarly identifications separately. Explicit `skt.` labels and HTML tags are source evidence; unlabeled italics alone are not a language classifier. A reviewed Sanskrit span may overlay otherwise unclassified text without inventing a missing source tag. Wraps and hyphens, including `cai-\ntyāṅganaḥ`, remain literal; any joined reading is a separately justified derivation.

German-inflected `Viṣṇus` remains literal German-context text. A reviewed form-mention annotation can relate it to Sanskrit `Viṣṇu` without declaring the whole inflected token a literal Sanskrit passage or replacing the spelling. The same distinction generalizes to names, quotations and embedded forms: language, mention of a form and lexical identity are different claims.

The reviewed language claims use lexical and contextual evidence: an identifiable Sanskrit counterpart in a Tibetan/German Lex. construction, or an old LoC Tibetan alias, parallel or quotation supported by its surrounding gloss/equivalent/siglum. These are bounded scholarly identifications, not general rules that label every italic span or every token with diacritics. `pradakṣiṇapaṭṭikā`, `cai-\ntyāṅganaḥ` and `ulkā` retain their literal source ranges. A claim can cover multiple ranges without joining or rewriting them; stale witness/view bindings fail validation.

Physical parents are the smallest supported source containers, not inferred semantic owners. An explicit Lex. container takes precedence over an equal-extent generic division. Tibetan aliases may be source-contained by a division rather than a German definition; tagged HTML Tibetan segments remain individually addressable inside their complete container. A Lex. citation can have a Lex. physical parent without asserting `citation_of`. Neither a wider reviewed envelope nor containment alone establishes `translation_of` or canonical sense ownership.

### Cross-reference graph

Retain each reference occurrence with its literal arrow/link text, source span, direction, HTML href or printed target, and witness. An explicit href establishes a source link, not necessarily a unique canonical-entry resolution. Printed ↑/↓, other entry links, stem/form references and ambiguous homonyms require separately typed interpretations and target-resolution claims. Preserve candidate targets and unresolved occurrences; proximity or the first search result is not a resolution rule.

An accepted edge links an occurrence to a canonical target and records the evidence, relation type, method and review. Direction, target interpretation and entity resolution remain independently revisable. Queries can then traverse accepted edges while exposing ambiguous alternatives and the original source link. Related stems/forms need their own entities/relationships rather than being squeezed into entry identity. This is an extension of the existing cross-reference/source-span records, not a second graph maintained beside them.

The optional `canonical_resolution` annotation on existing cross-reference records records the entry-index hash, method/version, sorted candidate IDs and resolved/ambiguous/unresolved status. `scripts/resolve_badw_cross_references.py` resolves only against supplied actual entry records: a unique exact explicit URL, or an individually source-bound reviewed printed target. It preserves literal text, source spans and URLs. The older source `resolution_status` describes URL capture, not canonical entry resolution. No URL normalization, nearest-lemma fallback, arrow-direction inference or morphological expansion is permitted. This is a bounded development tool, not production projection.

### Bibliography and citation queries

Reuse the existing work/publication/abbreviation, print-only authority and publication-relation infrastructure. A literal citation occurrence, canonical work, edition/publication, printed year, locator and owning example/sense are separate claims. Resolving a work does not verify an edition or page; locating a citation inside a source division does not establish its semantic owner. An absent online author-year row must not erase a reviewed print-only authority or force a year substitution.

An exact reviewed citation-year correction may resolve a publication identity while preserving the discrepant literal year as source evidence. Author confirmation reported by the user is a scholarly assertion with a report date, not cached public correspondence or page-level locator verification. Exact source-bound supplementary citation observations may expose reviewed citations absent from the candidate parser; they add no sense/example ownership. Literal-citation queries and canonical-publication reverse queries remain separate operations.

“Every citation of this book” should query resolved occurrence-to-work links, optionally restricted by edition, witness, locator-verification or review status. It must also expose unresolved candidates rather than count them as accepted links. Source-specific bibliography wording and editorial year/edition discrepancies remain recoverable as variants and reviewed relationships. BibTeX is an export of bibliography metadata, not the identity model or a replacement for source evidence.

### Whole-dictionary apparatus census and completion gate

The earlier `bibliography_print_ranges.tsv` is a bounded record-extraction input,
not a complete WTS apparatus inventory. The separate
`data/bibliography_apparatus_zones.tsv` records located printed source zones across
all four registered PDFs, including the earliest source lists, successive fascicle
supplements, later source-list/bibliography sequences, volume additions and memorial
bibliographies. The delivery-31 list has two registered scan manifestations; keep
both, without counting the scanned repetition as reviewed bibliographic duplication.
Delivery 17 continues onto WtS_1-34 scan 590. Printed foliation marked unverified
must be inspected rather than inferred from scan number.

**The registered-corpus reconciliation is complete, with eight named residual relationships.**
The completion review corrected exact boundaries and located a 37th zone, the
Herbert Franke memorial. `bibliography_apparatus_inventory_review.json` documents
full OCR heading searches plus contents, front matter, delivery-boundary and
neighboring-page facsimile review. This is closure for four registered PDFs, not a
claim that unavailable historical manifestations have been examined.
`bibliography_apparatus_accounting.jsonl` partitions every zone page into records,
continuations, headings, editorial/secondary material and layout. Raw OCR remains
unverified; facsimile transcriptions retain the source readings separately.

The offline capture command is:

```bash
python3 scripts/build_bibliography_apparatus.py \
  --cache work/wts_apparatus_20261010/cache \
  --output work/wts_apparatus_20261010/census_v3
```

The 2026-10-10 retrieval of `/texte`, `/bibliographie` and `/abkuerzungen` is
registered in `data/bibliography_apparatus_online_sources.tsv`. Its hashes match
the previous cached pages. Retrieval date establishes current observation, not
publication date or print equivalence. The builder uses the existing source cache
offline, checks PDF bytes against the source registry and OCR bytes against zone
provenance, and rejects missing, duplicated or reordered OCR pages. Snapshots are
immutable, built before publication and confined to ignored `work/` storage.

`ocr_pages.jsonl` preserves original UTF-8 text, CR/LF, Unicode offsets and page
markers. Prepending the `ocr_preamble` in `print_sources.jsonl` to that source's
ordered page texts reproduces the source OCR bytes. These readings are always
`unreviewed_ocr`. `online_occurrences.jsonl` retains the existing exact visible
wording and DOM spans; original HTML and acquisition metadata are retained too.
Neither OCR pages nor online source-authority IDs are reconciled print identities.
The census adds no canonical work, edition or siglum and changes no citation link.
Existing reviewed print occurrences, external identifications and publication
relations remain in the established bibliography backend.

The reviewed source-occurrence corpus is in `data/bibliography_apparatus_records.jsonl`.
It contains separate facsimile transcriptions and exact OCR source spans, including
cross-page records, printed foliation, inherited authors, edition statements,
field variants and explicitly reviewed online crosswalks. Layout line wraps and
purely typographical line-end divisions are joined in the facsimile transcription;
raw OCR is retained independently. Small capitals are represented by capitals.
Transcription-only records have no authority identity. This includes composite
records carrying separate source pointers and all secondary memorial/biography
bibliographies. Their presence in a bibliography never creates a citation target.

Import this ledger into the existing bibliography backend by adding
`--apparatus-records data/bibliography_apparatus_records.jsonl` to the established
`scripts/badw_bibliography.py` build command, with `--print-registry
 data/source_pdfs.tsv`. `--apparatus-zones` defaults to the checked-in inventory.
The importer checks registered PDF/OCR hashes, zone membership, exact OCR offsets,
facsimile bounds and the identity/text/hash of every online crosswalk. It rejects
unreviewed or stale identities and retains transcription-only records with a null
authority, without adding them to citation resolution. Existing six reviewed print
occurrences remain separate from these new occurrence records. Registered-corpus absence findings and chronology are now supported by the completed
review; historical first introduction remains distinct from earliest registered evidence.

The existing authority SQLite database now exposes both manifestations through
`authority_source_occurrence`; it is not a second authority system. For example:

```sql
-- All source occurrences of an existing authority, retaining every repetition.
SELECT id, manifestation, source_sha256, record_json
FROM authority_source_occurrence WHERE authority_id = :authority_id;
-- Transcribed records for which no canonical identity has been asserted.
SELECT id, json_extract(record_json, '$.candidate.zone_id') AS zone,
       json_extract(record_json, '$.verified_transcription') AS reading
FROM print_occurrence WHERE authority_id IS NULL;
-- Literal print/online differences are occurrence evidence, not corrections.
SELECT p.id, p.online_occurrence_id,
       json_extract(p.record_json, '$.candidate.variants') AS differences
FROM print_occurrence p
WHERE json_array_length(json_extract(p.record_json, '$.candidate.variants')) > 0;
```

The SQLite census supports direct evidence queries, for example:

```sql
-- Every located zone and its provenance/chronology notes.
SELECT id, source_label, start_page, end_page, data FROM zone;
-- Exact unreviewed text of a cross-page supplement, without losing continuation.
SELECT p.scan_page, p.raw_text FROM zone_page z JOIN ocr_page p
  USING (source_label, scan_page)
  WHERE z.zone_id = 'delivery17-additions' ORDER BY p.scan_page;
-- All online source occurrences with an exact literal label.
SELECT kind, label_text, raw_text, source_sha256, data FROM online_occurrence
  WHERE label_text = 'Mim1';
-- Review obligations and pages not yet classified by the visual census.
SELECT * FROM open_question;
SELECT source_label, scan_page FROM ocr_page
  WHERE apparatus_status = 'not_yet_classified_by_visual_census';
```

Corpus completion requires a visual apparatus census and exact multi-span record
transcription, including inherited authors and all residual text, before reviewed
reconciliation. Reuse the existing distinct work/publication/abbreviation,
source-occurrence and citation entities; add explicit siglum-denotes-work or
siglum-denotes-edition evidence rather than conflating them. Identity claims need
reviewed source occurrences; normalized author/title/year or fuzzy matches must
never merge records automatically. Record field variants with both occurrence
IDs and classify orthographic/editorial versus substantive differences explicitly.
First occurrence requires reviewed publication chronology, not scan ordering.

`data/bibliography_apparatus_editorial_pages.jsonl` preserves source-bound page
classifications for the editorial/memorial zones without standalone record
transcriptions. Its raw text is explicitly unverified OCR; facsimile review applies
to the page classification, not to an exact transcription of the prose. The mixed
scan 838 points to `delivery24-sources` for already ingested records. Secondary
prose references and source-policy references are classified explicitly. Reviewed
contextual links remain editorial references, rather than automatic citation authorities.

The existing authority database supports a bounded historical query:

```bash
python3 scripts/query_badw_bibliography.py --database work/wts_apparatus_20261010/ingested_v3/bibliography.sqlite apparatus-history AUTHORITY_ID
```

It orders reviewed occurrences by delivery range, retains variants and alternate
typesettings, and returns legacy occurrences lacking chronology separately.
`earliest_observed_occurrence_ids` means earliest within the reviewed identity's
current occurrence corpus; it does not establish an exhaustive WTS introduction.
Neither an absence of online occurrences nor an unmatched publication record proves
print-only status: online source-work descriptions can contain inline bibliographic
references without an independent `/bibliographie` publication record.

The completed results are checked in as `data/bibliography_apparatus_reconciliation.json`
and `data/bibliography_authority_history.jsonl`. The existing database schema adds
`canonical_membership`, `canonical_siglum`, `authority_history`,
`apparatus_reference`, `apparatus_annotation` and `apparatus_summary`; occurrence
and citation identities remain unchanged. Online bibliographic pointers preserve
candidate editions without silently promoting them to reviewed edition identities.
Eleven explicit reviewed edition/reprint relationships join bibliographic works
while retaining distinct publications.

The existing query command accepts `reconciliation`, `canonical-history ID` and
`scholarly-notes`. History includes earliest observed registered occurrences,
supplement/consolidation appearances and repeated scan manifestations. Publication
IDs return edition history; their `work-of-` membership IDs return the aggregate
bibliographic-work history. Delivery ranges supply order where dates are absent.
Counterpart classes are not claims of error. Eight irreducible relationships are
individually enumerated in the summary: six print edition cases, one legacy edition
case and the unmatched Bca/Vaidya 1960b online pointer.

The completed reviewed apparatus and all three online lists contain no definition
of Mim1/Mim2, including spacing, Roman numeral and plausible OCR variants. The
queryable `wts-undefined-mim1-mim2` annotation records the scoped WTS omission and
external Mimaki clarification Mim1=BDSN, Mim2=CDSN. The 382 existing citation links
are preserved. Three probable printed errors retain both literal forms; Maurer
literal source years and reviewed canonical identification continue to coexist.
The raw capture manifest remains a capture-stage artifact with null canonical
counts; the completed reconciliation summary supplies the reviewed figures.

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

The 2026-10-05 development replay retains unchanged benchmark gold and exact scoring: the extractor alone matches 71/121 nodes; validated reviewed language annotations raise this to 87/121 (95/121 under the separately reported terminal-whitespace diagnostic). All 16 previously missing typed language spans are represented. The remaining 34 node disagreements comprise eight terminal-whitespace cases and 26 documented envelope, punctuation, tagged-segment, headword or semantic-convention differences; no known reviewed literal omission remains. Physical Lex. parenting is corrected. Source review resolves the nine outstanding citations to complete Lex. items and the three language relationships as two lexical glosses and one translation. These accepted claims retain source selectors and review provenance separately from physical containment; they do not change exact benchmark scoring.

On this bounded reviewed evidence, the source-faithful extraction contract gate can open to **bounded citation-ownership/relationship review**, not bulk association or production promotion. The additional six HTML/six PDF development entries now support 40 source-reviewed relationships: 26 citations, ten translations and four glosses. General extraction recovers four previously missing citations from balanced, explicitly siglum-tagged HTML parentheses or a bounded terminal definition citation candidate. Two reviewed multilingual parallels permit one German gloss to apply explicitly to both Tibetan and Sanskrit forms; no nearest-phrase assignment is used. Two additional reviewed language spans bring the ledger to 18 active language claims and 18 relationship claims, plus the retained form mention and superseded claim.

The existing 60-case PDF citation challenge (20 cases per volume) contains 60 extracted citations. Source review supports 54 whole-Lex.-item relationships and two whole-definition relationships. Four reviewed citable passages now represent the narrower counterexamples: two citations support only one item within a Lex. group, one supports only an initial definition clause, and one supports a mixed German/Tibetan passage. All 60 relationships are representable without changing the source node tree. They remain counterexamples to blanket whole-container ownership: do not automate terminal-Lex. or whole-definition association. The review is prediction-exposed coding-agent development evidence, not an independent accuracy benchmark.

A separate bounded cross-reference pilot covers nine HTML entries and eight PDF entries. `scripts/build_badw_entry_index.py` pins all actual acquired HTML entries and source-bound PDF article witnesses, not search results or hypothetical URL aliases. The complete acquired index contains 18,037 HTML and 11,840 PDF entries. It resolves 11/15 HTML references by exact URL and 12/12 individually reviewed printed targets by exact headword/homonym identity. The four remaining HTML URLs (`yod/1`, `yin/1`, `bgyid/1`, `mdzad/1`) explicitly report unreleased data in a bounded live check; no cross-witness equivalence is invented for them. Unique exact explicit URLs identify a safe broader candidate class, subject to the pinned index and fail-closed ambiguity handling; citation and gloss rules still require review.

`scripts/build_badw_relationship_review_packet.py` freezes a fresh source-only 60-entry packet: 30 HTML and 30 PDF entries, ten from each PDF volume, enriched by ten source-text cue strata. Cues are sampling prompts, not asserted relationships or correct answers. Previously reviewed entries and existing holdouts are excluded. Source evidence, blank review fields, input hashes, index hash and frozen rule hashes are retained without predictions. Review must establish the exact supported endpoints (or ambiguity) before scoring; do not tune frozen rules against its answers. The older 120-packet independent review remains separate and unchanged. Independent accuracy evidence is required before broad citation assignment or production promotion.

HTML original-page certificates may use `cross_reference_only` evidence for an
independent printed reference article. This requires image inspection of the
article start, explicit printed homonym (including absence), column, folio and
source-bound QA boundary, the existing candidate edge or reviewed correction,
and exact agreement with the HTML cross-reference arrow and target. The entire
reference component is checksum-bound; any heading variant requires its own
component binding and printed observation. Only headwords, one cross-reference,
an optional bound heading variant and empty structural divisions are permitted;
definitions, examples, quotations and substantive divisions cannot enter this
path. Explicit review provenance is mandatory. Running headers, continuations
and references embedded in another article remain ineligible. These certificates
link pages; they do not modify cross-reference destinations or certify text
corrections. Missing C6 anchors or C11 identity edges still require deferral.

## HTML original-page production batch, 2026-11-06

The completed 298-link milestone contains **298 HTML-to-original-print attachments**,
up from 199: 99 additions on eight printed pages from seven physical scans.
Historical pilot reports showing zero new links describe earlier experiments.
`docs/STATUS.md` derives its current counts from the reviewed ledgers. This batch
uses the existing definition and cross-reference-only certificate paths; it does
not change their acceptance gates, the OCR release or dictionary relationships.

| Registered scan | Physical page | Printed volume/page | Distinct inventory witnesses | Accepted |
| --- | ---: | --- | ---: | ---: |
| WtS_1-34 | 86 | 1, 100–101 | 22 | 21 |
| WtS_35-51 | 682 | 6, 333 | 19 | 18 |
| WtS_35-51 | 683 | 6, 334 | 18 | 15 |
| WtS_8-b | 322 | 8, 312 | 12 | 12 |
| WtS_8-b | 358 | 8, 348 | 14 | 14 |
| WtS_9-m | 74 | 9, 70 | 11 | 10 |
| WtS_9-m | 151 | 9, 147 | 9 | 9 |
| **Total** | **7 scans** | **8 printed pages** | **105** | **99** |

Conversion is 99/105 (94.3%) for the original inventory witnesses, averaging
15 candidates and 14.1 acceptances per physical scan. Six additional proposals
were examined and deferred: 111 proposed identities were considered in all,
with 99 acceptances, one rejection and eleven deferrals. The page images were
read for article boundaries, running headers, continuations, printed homonyms
and lexical context; the review is not an exhaustive identification of every
unassociated heading on these pages. Eight source-bound derivatives are added;
the earlier 48 derivatives and 199 accepted attachments are preserved.

The rejected *pi* candidate on volume 6, page 333 is a fragment within another
article, not the independent article represented by the HTML witness (whose
definition concerns the number 43). Seven deferrals lack a usable C6 article
heading anchor: *kun rin*, *man luṅ*, *man ne*, *mig ’grim*, *mig rgyaṅ*,
*mig rgyan* and *mig sṅon*. *pad ma rā ga* has a C6 heading but lacks the
required C11 identity edge. Three volume-6 reference articles have no explicit
corresponding HTML cross-reference component: *pad ma’i mṅal byuṅ*,
*pad ma’i ’byuṅ gnas* and *pad ma’i ze ba*. The source-bound decisions in
`data/badw_html_print_alignment.json` retain the individual evidence and reasons.
Neither a running-header anchor nor a matching headword substitutes for the
missing evidence.

Certificate preparation used local, ignored helpers to copy authoritative source
URLs, HTML hashes, C6/C11 bindings, QA/component hashes and existing geometry.
Printed observations and acceptance judgments were entered after image
inspection. No additional attachment system or automatic identity adjudication
was introduced. The 199-link baseline fixture checks exact prior generated
witness identities, page assignments and certificate hashes; manual witnesses
and pages retain their frozen manifest checksums. These checks are additive,
rather than tied to a new milestone count.

A separate source-first reinspection covered twelve accepted entries across all
four scan families: *kun bzaṅ*, *kun la dmigs pa*, *kun las rgyal ba*;
*pad ma’i grogs po*, *pad ma’i spyan*, *pad ma’i ’od*;
*dbaṅ po’i rgyal mtshan*, *dbaṅ po’i rta*, *dbaṅ po’i sde*;
*mig brgya ma*, *mig ṅan phag rgod* and *mig can*. It checked the images
against the exact HTML components, including heading variants, short reference
articles and multiple numbered senses. Sense numbering in *kun bzaṅ*,
*dbaṅ po’i rgyal mtshan*, *dbaṅ po’i sde* and *mig can* was not promoted
to printed homonym numbering. This is a second inspection by the same coding
agent, not independent human review or an independent accuracy benchmark.
All new certificates explicitly disclose agent image inspection; historical
review provenance is unchanged.

Approximately 30 minutes of elapsed work covered source inspection and
certificate preparation, interleaved with compilation and focused checks.
Hands-on inspection and compilation were not separately clocked, so this is
not a measurement of pure reading time. Complete reader generation and browser
validation are recorded separately with the completed milestone below.

The main coverage limit remains missing historical associations. A future
alternative would need a distinct, versioned source-reviewed heading/identity
certificate: original-scan checksum, physical page and coordinates, heading
image evidence in both scripts, explicit printed homonym or its absence,
article-boundary negatives, exact HTML checksum and discriminating lexical
component bindings. Dedicated validation and negative controls would be needed
before it could replace either a missing C6 heading or a missing C11 edge.
No such alternative is enabled in this batch. A reviewed whole-page heading
inventory could generate clerical fields and direct attention to ambiguous
articles; it could not turn headword similarity into established identity.

The complete fresh reader built successfully in 841 seconds. Browser validation
opened all 99 new links and verified return navigation, with screenshots of each
entry and its PDF. Inspection of the rendered PDFs confirmed the headings on
all eight new printed pages. The full facsimile suite checked all 298 links at
1440- and 390-pixel widths, opened all 56 single-page PDFs and made three mobile
PDF comparisons. The full reader suite passed its search and navigation journeys
at widths 1440, 320, 390 and 768. All three browser processes exited normally
with status zero and no browser errors. Assertion work took approximately 144,
33 and 144 seconds respectively for the new-link, full-reader and facsimile
runs, measured from their log creation to final result; teardown is additional.

Preservation checks compared all 29,878 reader bodies: exactly the 99 intended
source attachments changed; all 11,840 PDF witness bodies and the reference-case
data remained byte-identical. Focused certificate/facsimile/reader tests passed
(98 tests), as did the required regressions (315 tests and 62 subtests) and the
two Node browser-cleanup tests. Generated-ledger checks, repository hygiene and
Python compilation passed. Two intermediate focused failures caused by a stale
generated ledger passed after regeneration, without changing their assertions.
The existing release validation warnings remain unchanged; this batch does not
rebuild or modify `release/current`. The validated local reader is
`work/page-link-scale-20261106/reader`, with ignored browser artifacts alongside
it; original scans and build artifacts are excluded from the commits.


## Continued page certification: 298 to 476

The reviewed ledger contains 476 attachments: the protected 298-link baseline
plus 178 source-image-reviewed assertions on fourteen physical scans, covering
sixteen printed pages. The first 61 additions were pushed as an evidence
checkpoint at `f77a671950`; complete reader validation is recorded below.

| Source | Physical page | Printed volume/page | Accepted | Observed independent starts | Identified HTML |
| --- | ---: | --- | ---: | ---: | ---: |
| WtS_8-b | 56 | 8/46 | 11 | 14 | 14 |
| WtS_8-b | 480 | 8/470 | 10 | 10 | 10 |
| WtS_8-b | 487 | 8/477 | 7 | 11 | 11 |
| WtS_8-b | 186 | 8/176 | 13 | 13 | 13 |
| WtS_9-m | 198 | 9/194 | 9 | 9 | 9 |
| WtS_9-m | 359 | 9/355 | 11 | 15 | 11 |
| WtS_9-m | 360 | 9/356 | 6 | 12 | 6 |
| WtS_35-51 | 733 | 7/384 | 15 | 15 | 15 |
| WtS_35-51 | 859 | 7/510 | 12 | 13 | 13 |
| WtS_35-51 | 377 | 5/28 | 13 | 14 | 13 |
| WtS_35-51 | 636 | 6/287 | 14 | 16 | 14 |
| WtS_35-51 | 616 | 6/267 | 12 | 15 | 12 |
| WtS_1-34 | 159 | 1/234 | 13 | 13 | 13 |
| WtS_1-34 | 159 | 1/235 | 12 | 12 | 12 |
| WtS_1-34 | 81 | 1/90 | 7 | 10 | 8 |
| WtS_1-34 | 81 | 1/91 | 13 | 14 | 14 |
| **Total** | **14 scans** | **16 printed pages** | **178** | **206** | **188** |

Each page's `heading_inventory` records the observed starts separately from
candidate conversion, with exclusions and unresolved associations. The entire
printed pages, including both columns and the two volume-1 spreads, were read
for independent starts, running headers, continuations and article boundaries.
The census is an agent observation, not independent human adjudication. Among
206 observed starts, 188 have identified HTML counterparts: 178 accepted and
ten deferred. Eighteen remain unassociated with exact acquired HTML witnesses.
The zero `without_acquired_html` counts mean no absence was established; they
do not prove that acquired counterparts exist for all eighteen.

Candidate conversion is a different denominator: 191 distinct historical HTML
candidates on these scans, with 178 accepted (93.2%), eight rejected and five
deferred. The rejected proposals are *du* (editorial homonyms 1, 2 and 3),
*bar du* 2, *dpal* 1, *sman* 1 and 2, and *nag po* 1. The proposed *du* anchor
is inside the *bar dag tu* article; the printed independent *bar du* explicitly
has homonym numeral 1 and spatial meanings, rather than editorial homonym 2.
The other rejected anchors head *dpal rdo rje nag po bstan bsruṅ yoṅs rdzogs*,
*sman sgro* and *nag po bdud*, respectively. Matching fragments of those names
cannot establish the shorter articles.

The five candidate deferrals are *bar rje khra bo*, *’bras ñag*, *spro skyid*
(missing usable article-start anchors), and *kun nas mnan pa* and *kun nas źal*
(independent print references versus expanded editorial definitions). Five
additional identified counterparts remain deferred outside the old candidate
packets: *bar gto*, *bar dag tu*, *’bras rdel* and *’bras sna gsum* lack usable
C6 starts; *’bras ltaṅ* has a C6 start but no appropriate C11 identity edge.
All page-specific reasons and the eighteen unassociated starts remain in the
reviewed page inventories. These are unresolved associations, not negative
claims about the existence of the printed articles or their HTML counterparts.

Original checksums were verified against the source registry. Sixteen new
source-bound derivatives use actual folios and geometry; the two spreads are
split at their observed central gutters. The previous 56 derivatives and all
298 attachments retain their exact assignments and bytes. Printed homonym
absence is explicit; sense numbering is not promoted to a printed homonym.

`prepare_badw_print_drafts.py` copies deterministic acquired-HTML, C6/C11,
component, QA, source-registry and existing geometry bindings into draft
envelopes. It reports missing bindings and rejects duplicate assignments. It
supplies no visual observations or approval. The certificate compiler rejects
draft status even when a draft is placed in an accepted list. Tests distinguish
preparation from publication. A compact second baseline fixture freezes the 99
additions at 9e547c8 by exact URL, acquired hash, generated-certificate hash and
page-identity hash, while retaining the legacy 199-link fixture unchanged.

Source-first quality control covered 32 distinct new acceptances across all
four scan families. A separate coding agent first read physical pages 56, 859,
360 and 81 without the accepted certificates or prior review notes, then checked
the acquired HTML. Its thirteen requested examples included eight acceptances
and five deferrals: numbered *bar du*; *spro khaṅ bde chen lcog* and *spro thuṅ ba*;
*sman gyi sbyor ba*, *sman gyi gtso mo* and *sman sgrub*; and the distinct
*kun nas mdzes* and *kun nas mdzes pa*. It confirmed the problematic article
starts and reference/expanded-definition differences among the deferred cases.
The primary coding agent separately reinspected another 24 acceptances on
volume 8 page 470, volume 7 page 384, volume 1 pages 234–235 and volume 9 page
194, reading the images before comparing HTML components. The sample includes
short definitions, explicit and absent homonym numerals, reference-only articles,
multiple senses and continuation boundaries. No identity discrepancies were
found. Neither agent inspection is independent human adjudication, and the
same-agent reinspection is not an independent accuracy estimate.

### Bounded missing-evidence design investigation

The eleven earlier deferrals remain unchanged: seven missing usable C6 starts
(*kun rin*, *man luṅ*, *man ne*, *mig ’grim*, *mig rgyaṅ*, *mig rgyan*,
*mig sṅon*), one missing C11 association (*pad ma rā ga*) and three references
represented through Tibetan HTML components. A direct source-reviewed heading
certificate would need a distinct, versioned input: registered original checksum,
physical page and reviewed geometry; precise heading coordinates and both
printed scripts; preceding/following article-boundary evidence; printed homonym
or explicit absence; exact acquired HTML identity/hash; and discriminating
lexical or reference-target components bound to the source. Review provenance
and an explicit acceptance decision must be required. Such a record must never
manufacture a historical C6/C11 row or reuse a running-header anchor. The known
cases still need that complete coordinate-bound evidence and replayable negative
controls before any alternative can grant attachment authority. No new pathway
is enabled in this batch; existing tests reject missing anchors and edges even
when a proposed observation and matching heading are supplied.

Reinspection of physical scan 683 confirms independent printed reference
headings for *pad ma’i mṅal byuṅ*, *pad ma’i ’byuṅ gnas* and *pad ma’i ze ba*.
Their exact acquired HTML has Tibetan target components rather than explicit
cross-reference components. The latter two retain downward arrows; the first
has an arrowless target. A possible narrow future extension would require an
explicit reviewed reference-target role bound to that exact component/hash,
the independent printed heading, the printed arrow/target and all ordinary
homonym and boundary gates. An arrow alone cannot license every Tibetan
component as a reference; the arrowless case additionally needs demonstrable
raw-source target semantics. Tests now retain all three deferrals and reject
these structures under the current validator, alongside existing running-header,
continuation, embedded-reference and wrong-homonym controls. No permissive
reinterpretation of Tibetan components was introduced. This investigation did
not hold up the 178 straightforward acceptances.

A whole-page inventory makes missing historical associations visible and can
supply deterministic clerical fields. It does not establish lexical identity
automatically. This batch averaged 14.7 observed starts and 12.7 acceptances per
physical scan; the 178/191 candidate conversion should not be presented as
178/206 complete page coverage or as evidence that every printed article has
an acquired HTML counterpart.

### Final reader and validation

The fresh complete reader at `work/page-link-500/reader` contains all 29,878
witnesses, with 476 certified HTML attachments to 72 printed-page derivatives.
It is locally served at `http://127.0.0.1:8897/`. The certificate expansion
contains 444 attachments; the unchanged manual ledger contributes 32. The
compiler's checked regeneration agrees with the reviewed inputs. Preservation
checks compared all reader bodies with the previous reader: exactly 178 HTML
attachments changed, all 11,840 PDF-derived witness bodies and reference cases
remain byte-identical, and all 298 previous assignments and decisions survive.

All 178 new entry journeys opened their PDF, retained the expected source label
and returned to the exact HTML identity. Browser screenshots of all sixteen
new printed pages were inspected for the rendered article headings. The full
facsimile suite checked all 476 entries on desktop and mobile, opened all 72
single-page PDFs and completed three mobile PDF comparisons. The full-reader
suite passed at widths 1440, 320, 390 and 768, including 82 citation journeys,
58 facsimile journeys and search checks. All three browser processes exited
normally with status zero and no browser errors.

Validation passed: 106 focused certificate/facsimile/reader/draft tests;
315 required regression tests and 62 subtests; 21 Node tests; compiler and
source-integrity checks; repository hygiene, Python compilation and diff
whitespace checks. The status checker retains the five inherited OCR QA warning
categories; this task does not alter the OCR release. Initial sandbox browser
launch and HTTP binding failures were resolved by running those same commands
with the necessary local execution permissions.

The main source-inspection and certificate-preparation window was 32.9 elapsed
minutes, followed by approximately eight minutes of source-first reinspection
interleaved with the build. These are roughly 40 minutes of elapsed review and
preparation windows, not a separately instrumented measure of active reading;
compilation and tests also occupied parts of those windows. The separate agent's
review effort was not individually timed. Full reader generation took 874.6
seconds, recorded separately from source review. Intermediate compilation used
the existing compiler without repeatedly rebuilding the complete reader.

## Historical production milestone: 583 links (2026-11-11)

The 476-link milestone above is historical. The reviewed ledger now adds 107
attachments, giving 551 generated and 32 unchanged manual links: **583 total**.
The legacy 199- and 298-link fixtures remain intact; the new
`tests/fixtures/badw_print_476_additions.json` freezes the later 178 assignments
and certificate hashes. Existing identities, original checksums, assignments and
review evidence remain protected rather than merely checking a growing count.

The seven newly inspected physical scans are WtS 1–34 pages 62, 99, 120 and
222 (volume 1, printed pages 58–59, 126–127, 162–163 and 352–353), WtS 8-b
page 199 (volume 8 page 189), WtS 9-m page 27 (volume 9 page 23), and WtS
35–51 page 1106 (volume 7 page 235). They contribute respectively 19, 17, 19,
17, 10, 7 and 18 attachments, using eleven new printed-page derivatives.
Whole-page inspection recorded 153 article starts: 147 associated with acquired
HTML and six unassociated. Of the associated starts, 107 passed certification
and 40 remain uncertified. The ledger adds 39 source-bound deferrals and eight
rejected candidate proposals; the merged *dkar* start remains unresolved without
a usable heading anchor. Six observed starts remain unassociated. Rejected
candidate identities include fragments of compound headings and competing
homonyms; rejection counts are candidate proposals, not additional article
starts. The page inventories and source-bound decisions preserve the individual
cases. A matching heading never overrides missing C6/C11 evidence.

These additions were inspected by the coding agent, not an external model or
independent human reviewer. Source-first reinspection across all four families
included short definitions, numbered homonyms, reference-only entries and
continuations. It confirmed, among others, the distinction between *byi brun* 1
and 2, the explicit fourth *byi bo* reference, the second *’phyid* reference,
and the disease sense of *dka’ ba*. The printed/HTML citation differences in
*dka’ zlog* and *skra śad ’dziṅs pa* are disclosed in their observations rather
than silently normalised. Same-agent reinspection is not an independent error
rate. Review/preparation time was not separately instrumented and cannot be
reliably reconstructed. Full reader generation took 811.935 seconds. The
preservation comparison checked every one of the 29,878 witness bodies: only
the 107 new HTML source attachments changed, all 11,840 PDF bodies were
byte-identical, reference cases were byte-identical, and the previous 72 page
derivatives retained their bytes and metadata.

Validation passed: 116 focused worker/certificate/draft/facsimile/reader tests;
315 required regression tests and 62 subtests; 21 Node tests; certificate
expansion and repository hygiene checks. The full-reader browser journeys exited
normally with status zero. All 107 new attachments separately opened their PDF
and returned to the exact HTML entry; displayed-page inspection covered all
eleven new derivatives. The full facsimile suite checked all 583 attachments at
desktop and mobile widths, opened all 83 page PDFs, and reported no browser
errors. Browser navigation is functional evidence, separate from the source
identity inspection described above. Five inherited status warnings remain;
they are not new test failures. No OCR release files changed.

## Historical production milestone: 688 links (2026-11-12)

The reader contains 656 generated and 32 manual attachments: **688 total**, an
increase of 105 over the protected 583-link baseline. The new fixture
`tests/fixtures/badw_print_583_additions.json` preserves the 107 assignments added
between 476 and 583, alongside the earlier baseline fixtures. Existing reviewed
assertions and negative decisions remain unchanged.

Thirty-three additions recover earlier deferrals on volume 1 pages 58–59,
126–127 and 352–353, volume 8 page 189 and volume 9 page 23. The remaining 72
are on volume 7 pages 114 and 199, volume 8 pages 4, 10, 375 and 400, and
volume 9 page 14. Five new page derivatives bring the total to 88; existing
reviewed geometry is reused on the other pages. Source inspection and certificate
preparation were interleaved and not separately instrumented; no precise active
review-time claim is made. These are coding-agent source-image reviews, not
independent human adjudications or automatically promoted model identifications.
The three deferred Tibetan-component reference cases remain deferred.

The batch records 110 reviewed inventory items on 15 printed folios (12 physical
scans). Seven folios have a complete inspected census: 77 article starts and
14 separately recorded exclusions; eight recovery-page inventories are partial
and contain 33 items. Five inventory items were already linked. All 105 new
attachments have exact acquired HTML counterparts; this does not establish a
complete census for the eight partial pages or the remaining dictionary.
Sixty new links use the direct-source pathway and 45 use historical bindings.

A further same-agent source-first check covered volume 1 pages 352–353, volume 7
page 114, volume 8 page 10 and volume 9 page 14, across all four scan families.
It included the skra compounds and their lexical citations, phyi thum and the
phyi reference articles, explicitly numbered ba la¹/² and ba laṅ¹, short ma gal
and ma gu ta definitions, and the ma ga dha pa article crossing columns. Running
headers and preceding continuations were distinguished from article starts.
This reinspection agreed with the recorded assignments; it is neither independent
human adjudication nor a statistical precision estimate.

The complete 29,878-witness reader built in 876.6 seconds. Preservation checks
compared every witness body: all 11,840 PDF-derived bodies and the reference-case
data are byte-identical, all 583 earlier attachments remain, and all 83 earlier
derivatives retain their bytes and metadata. Only the 105 newly attached HTML
witnesses acquired changed source attachments. The generated ledger passes its
compiler check against the acquired HTML bodies.

Validation passed: 121 focused certificate/draft/facsimile/worker tests;
342 reader/source/regression tests with 62 subtests; and 21 Node tests, exiting
normally. The required Python compilation checks, repository hygiene and
whitespace checks passed. Five existing release-validation warnings remain
unchanged. The full-reader desktop/mobile browser journeys passed with no
browser errors and exited normally. Chrome required execution outside the
filesystem sandbox; the initial sandbox launch failures were environmental.
The facsimile browser suite checked all 688 attachments at desktop and mobile
widths, opened all 88 distinct single-page PDFs and made three mobile PDF
comparisons, with no browser errors. A separate run opened all 105 new links,
captured their displayed printed pages and verified return to the correct HTML
entry. Both processes exited normally with status zero; facsimile Chrome teardown
was slow. Displayed headings were also inspected against the source reviews.

### Direct source-reviewed certificates and durable inventories

`direct-source-heading-v1` is a separate certificate pathway. It requires a
checksum-bound registered scan and reviewed page geometry, a stable reviewed
inventory item, heading and lexical-evidence coordinates within an article
region, explicit printed homonym treatment, neighbouring article context,
boundary and identity reasons, and exact acquired HTML/component bindings.
It records the absent or defective historical C6/C11 evidence and its hashes;
it never manufactures historical anchors or edges. Reconsidered negative decisions
are explicitly bound to their previous records. The compiler checks these
mechanical bindings; it cannot itself verify a printed transcription.

Reviewed page inventories retain stable item IDs, coordinates, actual readings,
source context, decisions and separate exclusions. A complete-census flag is
used only after examining the entire printed page. Provisional model inventories
remain in ignored run storage and are not substituted for reviewed inventories.
`prepare_badw_print_drafts.py` can prepare direct-source drafts, but cannot grant
publication authority. Tests reject running headers, embedded expressions,
competing homonyms, wrong pages, definition mismatches and tampered bindings.

### Model worker: live calls demonstrated, production accuracy not established

`scripts/badw_model_worker.py` now joins actual inventory and matching outputs
for evaluation without dropping unmatched or abstained inventory items. It
preserves item IDs, image hashes, source identities and coordinate transforms.
Targeted article crops map back to the original page; candidate HTML evidence is
bounded while retaining competing identities. Offline tests exercise
prepare → inventory → retrieve → match → evaluate → review. Evaluation requires
explicit source-reviewed reference provenance and a complete census for recall;
model agreement and unreviewed certificates are not gold-standard answers.

The user authorised external transmission and a US$10 ceiling. Real Responses
API calls to GPT-6 Luna and GPT-6.1 Terra completed on ten frozen physical-page
examples (five development and five held-out). Inventory inputs did not include
accepted certificates. Match prompt v2 was adjusted on a development page only.
At 240 DPI with original image detail and targeted match crops, the final strict
validation accepted Luna outputs on 5/10 pages and Terra outputs on 10/10.
Luna produced 43 supported matches, 35 agreeing with existing certified page
assignments and eight not previously certified; Terra produced 141, of which
104 agreed and 37 were not previously certified. No known wrong-page match
appeared in this concordance check. These numbers are **not independently
measured precision or recall**; unverified matches are neither accepted links
nor established errors. Some paid responses failed exact-quotation or identity
validation and remain rejected.

Source-first coding-agent reinspection of development volume 8 page 3 found
11 independent starts, two running headers and a preceding continuation. Both
models found the 11 starts and excluded the headers and continuation. Terra
supported all 11 correct identities; Luna's diagnostic response supported ten
and abstained on the short reference *ba glaṅ*. This small same-agent development
check is not held-out or independent human validation. Inventory box extents
also differ (heading versus whole article); region-IoU scores need a consistently
reviewed reference geometry before meaningful aggregate recall can be claimed.
No model response has been automatically promoted, and no new attachment is
counted as delivered through a validated model-assisted production workflow.
A controlled resolution comparison and independently reviewed held-out reference
census remain necessary before scaling production.

Returned usage accounts for approximately **US$1.48653**, including cache-write
pricing; two failed-request reservations remain unresolved, so this is not a
confirmed invoice total. The local spending ledger retains those reservations.
Live request bounds use the documented maximum input allowance at the long-context
and cache-write tariffs, rather than an assumed image-token formula. The run is
stopped with a local `STOP` file. Credentials, approvals, page images, raw model
responses and detailed usage records remain ignored under `work/`.

### Reproduce and resume

Install optional dependencies in an ignored virtual environment using
`requirements-badw-model.txt`. Supply acquired bodies from the existing source
acquisition, not from accepted certificates. Use a locator list of `family` and
`physical_page` records, optionally `page_key` for reviewed printed-side geometry.
The frozen development/held-out manifest remains
`data/badw_model_evaluation_pages.json`; it is a locator freeze, not a completed
gold standard. Do not tune prompts on held-out examples.

```bash
python3 scripts/badw_model_worker.py plan --work work/model-run --pages data/badw_model_evaluation_pages.json
python3 scripts/badw_model_worker.py prepare --work work/model-run --pages work/selected-pages.json --bodies work/acquired-bodies.json --dpi 240
python3 scripts/badw_model_worker.py run --work work/model-run --dry-run
python3 scripts/badw_model_worker.py run --work work/model-run --model gpt-6-luna --stage inventory --detail original --approval work/approval.json --cap-usd 10
python3 scripts/badw_model_worker.py run --work work/model-run --model gpt-6-luna --stage match --article-crops --bodies work/acquired-bodies.json --approval work/approval.json --cap-usd 10
python3 scripts/badw_model_worker.py evaluate --work work/model-run --model gpt-6-luna --page-pack work/model-run/PAGE/pack.json --bodies work/acquired-bodies.json --article-crops --reference work/reviewed-reference.json
python3 scripts/badw_model_worker.py review --work work/model-run --model gpt-6-luna --stage match --article-crops --bodies work/acquired-bodies.json
python3 scripts/badw_model_worker.py report --work work/model-run
```

Use the actual prepared pack path for `--page-pack`. Repeat with Terra on the same
frozen examples. A local approval record requires `approved_usd`, `approver`,
`rights_basis` and `transmission_authorized: true`; load `OPENAI_API_KEY` securely
into the process environment. Never commit it. Cache keys bind source, image,
HTML, model, prompt and schema inputs. Rerunning resumes completed requests;
rejected paid payloads remain private for diagnosis. An uncertain request retains
its budget reservation. `STOP` prevents subsequent requests; in-flight calls may
finish. A hundred-page run is not yet authorised by benchmark accuracy: complete
the held-out source-reviewed references and error assessment first.

After source review, compile and build through the established machinery:

```bash
python3 scripts/badw_html_print_alignment.py --bodies work/acquired-bodies.json --queue data/badw_html_print_review_queue.json
python3 scripts/badw_html_print_facsimiles.py --scans-root . --output work/model-production/pages
python3 scripts/build_badw_full_reader.py --output work/model-production/reader --print-facsimiles work/model-production/pages/manifest.json
```


## Persistent linking campaign (2026-11-12)

The current reviewed ledger contains **691 certified attachments** (659 generated,
32 manual) and 89 derivatives. The three additions are printed volume 8 page 11:
*²ba laṅ*, *ba laṅ dkar zal* and *ba laṅ rkaṅ pa*. The source image was checked
for each identity, homonym, neighbouring boundary and exact HTML evidence. Two
use direct-source certificates; the middle article uses its existing C6/C11
association. The running header for *ba laṅ rkaṅ pa* is explicitly excluded.
The entire printed page has a reviewed three-start census. These are coding-agent
image inspections following model proposals, not independent human adjudication.
`tests/fixtures/badw_print_688_additions.json` freezes the preceding 105 additions,
alongside all earlier preservation fixtures.

`scripts/run_badw_linking_campaign.py` is the persistent controller. SQLite/WAL
records the registered 3,466 physical scans, planned printed-page views, stage
checkpoints, errors, response IDs, usage, review provenance and publication state.
A single writer and one in-flight request bound concurrency. It reuses worker
caches across interruption; an uncertain request keeps its budget reservation.
An invalid paid response is retained for diagnosis rather than bought again.
Per-page failures continue to other pages, with at most three processing attempts.
`status.json` is refreshed after each stage pair and is readable without a chat.
Provisional inventories, source-reviewed decisions and published links have
separate counts. Model inventories are never labelled complete source censuses.

A 200-physical-scan campaign is stored privately in
`work/linking-campaign-20261112`. It spans all four families beyond the historical
48-page candidate queue. The following initial-run figures are historical;
consult private live status and spending records for current totals.
Its initial detached run completed inventories for 25
scans and matching for 21, producing 297 provisional article starts and 214
supported identity proposals. Four paid matching responses failed the exact
HTML-evidence quotation check and remain blocked and cached. The first 50 paid
requests, including those four rejected responses, returned US$1.71769125 in
usage; cumulative returned usage including the earlier benchmark was
US$3.204221645, with US$0.3868 still reserved for earlier uncertain requests.
These are measured usage charges, not a claim that the billing dashboard has
reconciled the uncertain requests. The continuing detached run has been launched
against the remaining 200-scan plan under the same cumulative US$10 cap.
STOP and resume were exercised on the real process,
as well as interruption immediately after inventory in offline tests. `tmux` is
unavailable on this host; detached execution with a new process session works.
Images, responses, approval records, the database and credentials stay ignored.

### Operate from another terminal

Use the optional dependencies in `requirements-badw-model.txt`, the acquired HTML
body map, and the existing private approval/spending directory. All campaigns
must share that spending directory while consuming the same authorisation.
The user subsequently authorised additional spending; the current explicit
cumulative ceiling is US$20. Renewed approval preserves paid requests and all
unresolved reservations rather than resetting expenditure.
Load `OPENAI_API_KEY` securely into the shell environment; do not put its value in
a command, source file or shell history. The examples use the existing local
body/dependency locations; another installation can substitute its own paths.

```bash
export PYTHONPATH=work/badw-model-deps
python3 scripts/run_badw_linking_campaign.py status --campaign work/linking-campaign-20261112
python3 scripts/run_badw_linking_campaign.py review --campaign work/linking-campaign-20261112
python3 scripts/run_badw_linking_campaign.py stop --campaign work/linking-campaign-20261112
python3 scripts/run_badw_linking_campaign.py resume --campaign work/linking-campaign-20261112 --drain
```

For a detached process, after securely loading the key:

```bash
nohup python3 -u scripts/run_badw_linking_campaign.py resume --campaign work/linking-campaign-20261112 --drain </dev/null >work/linking-campaign-20261112/terminal.log 2>&1 &
```

The shell returns immediately; the controller survives closing that terminal
while the host stays running. Inspect `status.json`, CLI `status`/`report` and
`terminal.log`. Issue `stop` from another terminal; the current request may finish,
but the next stage will not start. Resume after a crash with the same directory.
Do not delete uncertain reservations or use a new spending directory to evade
the cap. `--clear-budget-stop` clears the worker STOP marker only: it does not
increase the cap or forgive reserved spending. `--max-pages` bounds work per
invocation, including failed page attempts, rather than resetting campaign state.

During backlog review, leave the proposal-generation STOP marker in place.
The separate blind reading excludes the earlier inventory and favoured match:

```bash
python3 scripts/badw_campaign_review.py --campaign work/linking-campaign-20261112 --live
python3 scripts/badw_campaign_review.py --campaign work/linking-campaign-20261112 --report
touch work/linking-campaign-20261112/REVIEW_STOP
```

`REVIEW_STOP` finishes the current request before stopping. Remove it explicitly
before resuming the same review command; cached paid responses are reused.
The private HTML desk shows source crops, exact component bindings, both readings
and exceptions. Corroboration is labelled model-source-reviewed, never human
review or certification. This checkpoint does not implement automatic promotion.
Only unique whitespace differences in exact HTML quotations can be repaired;
other invalid quotations become abstentions with the raw response preserved.
Uncertain billing remains reserved and is never retried automatically.

To plan another bounded campaign with systematic round-robin physical selection:

```bash
python3 scripts/run_badw_linking_campaign.py plan --campaign work/next-campaign --max-pages 200 --bodies work/direct-source-20261111/compact-bodies.json --budget-root work/live-benchmark-20261111
```

Use `--starts work/starts.json` for a family-to-first-physical-page mapping to skip
known front matter, or `--pages work/pages.json` for explicit physical locators.
`page_key` selects an existing reviewed printed-page crop. Unreviewed spreads
remain provisional whole scans; a model's folio reading cannot confer reviewed
geometry. Selection retains partially certified scans and skips only explicitly
reviewed complete physical-scan censuses. It does not assume pagination
offsets or that every observed article has an acquired HTML counterpart.

### Review and publish a batch

`review` lists the private source packs. Inspect the original registered image,
precise article location and exact HTML components. Preserve the provisional
model response separately. Record stable reviewed inventory IDs, explicit print
homonyms/absence, boundary evidence, identity evidence, provenance and decisions.
A complete census needs inspection of the whole printed page, including exclusions.

`prepare_badw_print_drafts.bind_reviewed_direct()` removes deterministic clerical
work after review; it cannot invent observations or approve a proposal. The
controller's `review --bindings work/decisions.json --output work/proposed-ledger.json`
accepts an operator-authored object with `pages` (optional new reviewed page
records with empty `accepted` lists) and `bindings`. Each binding supplies
`source_id`, `page_key`, `item_id`, `component_index`, `historical_issue` and
`historical_reason`. It requires explicit source-inspection acceptance in the
reviewed inventory, binds authoritative hashes, runs the ordinary compiler and
checks preservation of the campaign baseline. Failure writes no proposed ledger.
It never edits the canonical ledger or publishes. Existing page records and
inventories are reused; duplicate assignments fail closed. Review the proposed
diff before installing it in `data/badw_html_print_alignment.json` and compiling:

```bash
python3 scripts/badw_html_print_alignment.py --bodies work/direct-source-20261111/compact-bodies.json --queue data/badw_html_print_review_queue.json
python3 scripts/run_badw_linking_campaign.py review --campaign work/linking-campaign-20261112 --sync-certificates
NODE_PATH=work/badw_reader_browser_tools/node_modules python3 scripts/run_badw_linking_campaign.py publish --campaign work/linking-campaign-20261112 --output work/campaign-publication-NEXT
```

Publication requires a fresh ignored directory. It checks the generated ledger,
prepares derivatives, builds the complete reader, and runs the full-reader and
all-attachment desktop/mobile browser suites against a managed local server.
Server teardown is in `finally`. A build/browser failure never marks links
published. Git publication remains a separate explicit commit/push operation;
local `publication.json` never claims a GitHub push.

If a complete build succeeded but browser execution was interrupted, repeat
`publish` with the same output and `--resume-build`. A checkpoint verifies the
certificate, reader manifests, reader data and facsimile manifest hashes before
reusing that build. It reruns the compiler and both browser suites; a changed
build fails closed. This avoids rebuilding 29,878 witnesses merely because a
browser needs to be restarted. The usual command still requires a fresh output.

Measured costs currently project approximately US$13–14 for the 200-scan plan,
excluding the earlier benchmark and unresolved reservations. This is a usage
projection, not a safe reservation bound or approval for additional spending.
The controller will stop at the existing cap, potentially earlier because of
conservative per-request reservations. Completing the plan may need a separately
approved higher cumulative cap; deleting reservations or changing spending
directories is not a legitimate way to continue. Wall-clock throughput includes
idle time between sessions; `api_service_seconds` separately totals recorded
request elapsed time, including rejected responses.

### Held-out source evidence and promotion policy

`data/badw_model_heldout_ma12_reference.json` freezes a source-first reinspection
of held-out WtS 9-m physical page 16, printed volume 9 page 12: 12 independent
starts, two running headers and an opening continuation. Its reviewer is a coding
agent, not a human. The source census and exact HTML checks preceded inspection
of the model outputs; accepted certificates were not supplied as answers.
Terra located and matched all 12 correctly, including explicit printed homonym
5 and short reference entries. Strict precision and heading recall were both
12/12; the Wilson 95% interval for each is approximately 0.758–1.000. Five extra
embedded-reference observations abstained rather than proposing attachments.

Luna merged *ma ke na* with *mā kra*. Its eight supported identities were
lexically correct on source inspection, but broad whole-article boxes failed
the frozen heading-box IoU criterion. The strict scorer therefore reports eight
false-positive *localized links* and zero matched reference regions: these are
localization failures, not eight demonstrated wrong lexical identities. A missed
homonym numeral on an excluded running header is another diagnostic error.
Do not tune the held-out geometry or silently reinterpret these strict metrics.
The remaining held-out pages are not yet independently censused. The earlier
10-page schema-validity comparison and certified-page concordance are not
substitutes for this lexical assessment.

Reproduce the strict comparison without paid calls (substitute `gpt-6-luna` for
the second model):

```bash
PYTHONPATH=work/badw-model-deps python3 scripts/badw_model_worker.py evaluate --work work/live-benchmark-20261111 --reference data/badw_model_heldout_ma12_reference.json --prediction work/live-benchmark-20261111/wts_9_m-16-ma12/prediction-gpt-6.1-terra.json
```

This evidence favours Terra for provisional production, but is insufficient for
a validated automatic-promotion policy. Every accepted attachment still requires
actual source review under existing provenance rules. Agreement of two model
calls, confidence scores and successful browser navigation grant no lexical
certification authority. Until a larger risk-stratified source assessment passes,
the detached campaign cannot generate thousands of certified links.
The first three delivered links demonstrate the checked publication route;
they do not establish 1,000-link throughput or completion of the larger campaign.

### Provisional reader links from paid observations

`data/badw_html_print_provisional.generated.json` is a separate machine-evidence
layer. It grants no certificate authority. The offline exporter
`scripts/badw_provisional_print_links.py` validates registered scan checksums,
physical page bounds, immutable request/result and image hashes, exact HTML
identities and component bindings. Publication requires corroborating blind
source reading, compatible headings and printed homonyms, and no conflicting
page assignment or previous evidence decision. Pending and disputed cases remain
in its explicit review queue. Certified identities always take precedence.

The first export recovers 262 additional suggestions on 35 physical scans from
344 paid supported proposals: 46 pending blind review, 32 disputed, one excluded
by an earlier evidence decision and three already certified. No duplicate or
competing-page survivors were found. These are provisional links, not 262 new
certificates. They use whole physical-page derivatives, including whole spreads;
no printed folio or side is inferred. The reader labels them “Suggested original
printed page — automatically matched, not yet verified.” A persistent checkbox
can hide them. Source and model evidence remain available in the generated file.

A coding-agent source-image check covered 55 suggestions on five scans across
all four families: WtS 1–34 physical 91 and 97, 35–51 physical 684, 8-b physical
22 and 9-m physical 25. It checked numbered homonyms, very short cross-references,
continuations, spreads and distinctive citations. No wrong page association was
found in this selected sample. This is neither a random accuracy estimate nor
an independent human audit; two readings from the same model can share errors.
Some first-pass heading fields contained positional descriptions instead of
transcription. Publication now requires an explicit matching headword in at
least one reading. No new automatic certificate type is justified by this sample.

Subsequent source-image checking covered 306 proposed associations source-first,
plus 47 checked after seeing candidate identities. The selected source-first pages
include WtS 1–34 physical 87, 91, 93, 94, 96, 97, 100 and 103–106;
35–51 physical 684, 697–699 and 701; 8-b physical 22 and 34–40; and 9-m physical
25 and 33–36 and 38. The additional candidate-visible checks covered 1–34 physical
92 and 95 and 9-m physical 32. No wrong physical-page association was found
in these selected checks, including short cross-references, numbered homonyms,
and printed entries whose HTML numbering differs. These are checks of proposals,
not a claim that every checked proposal was published. For example, physical 87
remains excluded because its independent reading contains an unknown HTML
identity. Physical 9-m 37 contains only a continuation; the matcher correctly
produced no new article association. Neither this selection nor model agreement
establishes a population accuracy estimate or automatic certification policy.

Cached rejected responses can be recovered without another API request when
schema, request, source and output hashes remain valid. A unique quotation span
may receive a whitespace-only repair. Invalid quotations, component locators or
missing substantive evidence become explicit abstentions, with before/after
records. Unknown identities and incomplete responses remain excluded. Original
paid responses are never rewritten. Eight previously rejected matching responses
contained 131 supported claims: 121 were recovered and ten quarantined; their
independent checking still controls publication. A nested reference abstention
no longer vetoes a unique corroborating article observation, while competing
supported identities of any classification continue to block publication.

The pre-handoff cache contains 454 distinct supported identity/page claims,
including rejected responses. Offline recovery and independent checking make
342 usable provisional links. The remaining claims comprise 46 awaiting review,
38 disputed, three already certified, one previous exclusion, seventeen on a
page with a failed independent identity binding, and seven invalid quotation or
component bindings. There are no duplicate claims in that count. It does not
count newly purchased observations as recovered pre-handoff work.

The first bounded production invocation completed generation, independent
checking, export, complete-reader refresh and all three browser suites in
25 minutes 31 seconds. It delivered 48 fresh provisional links and six additional
cache recoveries, taking the verified reader from 262 to 316 suggestions. That
is approximately 113 fresh links per wall-clock hour, including browser checks;
operator time was not instrumented. This run does not establish a thousand-link
campaign yield or automatic certification accuracy.

The existing ordering benchmark reproduced seven correct held-out identities and
one abstention out of eight. It can narrow candidates but cannot establish page
identity or safely extrapolate physical offsets through spreads and editorial
reordering.

Offline recovery, without API calls:

```bash
PYTHONPATH=work/badw-model-deps python3 scripts/badw_provisional_print_links.py --campaign work/linking-campaign-20261112 --prepare work/provisional-links-20261112/pages
```

Bounded production in the same campaign and spending ledger:

```bash
PYTHONPATH=work/badw-model-deps NODE_PATH=work/badw_reader_browser_tools/node_modules python3 scripts/run_badw_linking_campaign.py produce --campaign work/linking-campaign-20261112 --api-key-file work/openai-api-key --max-pages 5 --base-reader work/provisional-production-40-20261112/reader --output work/provisional-production-NEXT
```

Use a fresh output directory each time. `produce` runs generation, unfinished
blind reviews, provisional export, certificate validation and reader browser
checks. `--base-reader` reuses a complete reader and changes only suggestion
source lists, updating their hashes; full witness reconstruction is unnecessary
at every milestone. Without it the normal complete build runs. Interrupted
completed builds retain the existing `publish --resume-build` route.
Completed reviews are skipped, paid caches precede new requests, and failures
have bounded retry counts. `stop` controls generation; `REVIEW_STOP` separately
controls blind review. Reservations with uncertain billing are never cleared.

The recovered private configuration, approval and spending ledger all specify
the same cumulative US$20 cap. The planner now preserves the ledger's authorized
extension instead of reinstating US$10. At initial recovery, returned usage was
US$6.478751645, unresolved reservations US$5.2368 and available authorization
US$8.284448355. These reservations are retained. Status uses held process locks,
reports last successful progress and separates the 3,466-scan census from link
and processing counts. These figures are observations, not new spending approval.

The subsequent stopped generation batch drained fourteen independent page reviews
and exported 123 additional corroborated links. Together with offline backlog
recovery, the final dataset contains 532 provisional links on 62 physical scans,
plus the unchanged 691 certified links and 89 certified derivatives. Evidence
is retained for 68 scans, including six without published suggestions. The explicit
queue contains 50 pending claims, 44 disputed claims, one previous exclusion and
three already-certified claims; one whole page remains excluded for a failed
identity binding. These are dataset dispositions, not additional reader links.
Generation was stopped through the campaign stop file after its current page;
review and publication continued to completion. Status correctly reports the
publication lock separately from a stopped controller. Four matched pages remain
awaiting independent review, including two with uncertain prior billing.

Returned usage after this production is US$10.139691895 cumulatively, an increase
of US$3.660940250 from the recovered baseline. Four historical unresolved
reservations still total US$5.2368, leaving US$4.623508105 of the US$20 cumulative
authorization. No reservations were reset or new spending directory created.
The thousand-additional-link target is not achieved. At the observed cost and
with unresolved reservations, the remaining authorization does not support a
credible commitment to another 468 independently checked associations. The
cached blind identity error, invalid component quotations and an incomplete
response demonstrate why automatic promotion into the certified tier is not
justified by these observations. Complete drafts and source evidence remain
available for later source adjudication; model agreement alone is insufficient.

The final stopped production invocation completed in 47 minutes 52 seconds,
including its complete-reader refresh and all three browser suites. The reader
now exposes 532 suggestions. Comparison against the previous complete reader
checked all 29,878 witnesses, including 11,840 PDF witnesses: zero changes to
witness bodies, existing references or certified source attachments. All three
browser suites exited zero; the final focused suite passed 179 tests, and the
required text regressions passed 315 tests with 62 subtests. Python compilation
and repository hygiene passed. Browser success tests navigation and preservation,
not the lexical correctness of every suggested association.

All 532 suggestions also have non-publishable certificate drafts in ignored
`work/provisional-links-20261112/certificate-drafts.json`, assembled with the
existing draft preparer. They bind full HTML components, both source readings,
registered page provenance and historical evidence. 247 have a unique unassigned
C6 anchor on the proposed physical source page; the others retain missing or
ambiguous anchors explicitly. No source acceptance or reviewer identity was
invented, and every draft still requires source adjudication.


### Offline model-source certification, 2026-11-13

The frozen 92-candidate pool and 32 earlier crop inspection notes are preserved
in `data/badw_model_certification_controls.json`. The executable
`scripts/certify_badw_model_links.py` now accepts and compiles the bounded
`unique-unnumbered-lexical-v1` class as `model-source-verified-v1` certificates.
This supersedes the earlier blanket statement that model evidence has no
certification pathway; it does not make every model match certifiable.

Acceptance requires two independently requested source readings, a genuine
article heading in both, a unique acquired HTML headword, no printed numeral,
exact HTML URL/raw hash and component bindings, lexical evidence in both
readings, and observed preceding/following article boundaries. Both match
readings must support the exact identity and quote its actual lexical
component. At least one printed/HTML evidence pair must share 20 normalized
characters; that minimum is a corroboration check, not semantic proof.
Descriptive observations such as “No printed numeral visible” are accepted;
unknown uncertainty wording, genuine ambiguity, competing pages, prior
exclusions, running headers, continuations and numbered/split homonyms abstain.
Reference-only evidence is outside this initial class.

The compiler reconstructs each observation from its request/response cache,
checks independent request identities and exact packet contents, rehashes the
registered original PDF, and re-renders its physical page to reproduce the
paid source image byte for byte. It verifies image transforms and both heading
boxes, and publishes the exact original PDF media box. MuPDF float32 coordinate
roundoff is checked against the original PDF numbers, never used to enlarge a
crop. A whole physical scan makes no printed folio or spread-side assertion.
Each finished certificate retains the complete source readings, model/request
identities, image/HTML/component hashes, policy and empirical-control hash.
Its provenance explicitly says model reviewed, not human or agent adjudicated.

The initial offline run certified **92/92** candidates in **103.67 seconds**,
raising the canonical total from **691 to 783** with **131** derivatives.
No individual acceptance decision was authored. All historical certificates
and their page bindings remain unchanged. The corresponding 92 suggestions
were removed; 440 unresolved suggestions remain separately stored, and the
new complete reader is built without enabling suggestions. No new API calls
were made. Existing returned usage remains US$10.139691895, unresolved
reservations US$5.2368 and available authorised budget US$4.623508105.

Quality controls preserve the prior 32 successful crop inspections, without
pretending their selection was random. A further source-first audit selected
two identities per scan family from all 532 suggestions by a fixed SHA-256
ordering before applying the acceptance rules: eight correct identities,
including seven outside the accepted pool, and no observed identity errors.
These observations and exact HTML components are in
`tests/fixtures/badw_model_policy_examples.json`. The existing independent
ma12 held-out benchmark was replayed from cache: 12 correct links, no false
positives or homonym errors, and three correct abstentions. These small,
partly class-conditioned samples do not establish a whole-corpus error rate.
Tests additionally reject altered source headings, numerals, boundaries,
identities, hashes, quotations, unsupported matches, generic short evidence,
prior exclusions, duplicate headwords and a self-consistently hashed image
from the wrong physical scan. Browser navigation validates delivery, not
lexical accuracy.

Reproduce or resume entirely offline (the dependencies are already cached):

```bash
PYTHONPATH=work/badw-model-deps python3 scripts/certify_badw_model_links.py \
  --campaign work/linking-campaign-20261112 \
  --bodies work/direct-source-20261111/compact-bodies.json \
  --output work/model-certified-resume-20261113
PYTHONPATH=work/badw-model-deps python3 scripts/badw_html_print_facsimiles.py \
  --scans-root . --output work/model-certified-20261113/facsimiles
PYTHONPATH=work/badw-model-deps python3 scripts/build_badw_full_reader.py \
  --output work/model-certified-20261113/reader \
  --print-facsimiles work/model-certified-20261113/facsimiles/manifest.json
```

Already certified identities are skipped; the entire canonical ledger is
validated before replacement. Paid caches and billing reservations are never
modified. This command intentionally confines publication to the preserved
pool; it is not a claim that the remaining corpus can yet be certified by the
same untested rule. Extending to references and split homonyms requires explicit
source-target/sense controls and source-first validation of those classes.

The repeated offline invocation finished in **79.39 seconds**, skipped the 92
already certified identities and left both canonical and generated certificate
files byte-identical. A full reader build contains **29,878 witnesses**. An
exhaustive comparison against the preceding reader preserved all **18,038 HTML
bodies and references** and all **11,840 PDF-derived bodies**; only the 92 new
certified source attachments and removal of 440 displayed suggestions differ.
The 18,038 reader HTML records include the existing additional record beyond the
approximately 18,037 acquired witnesses.

Among the 440 remaining cached suggestions, the current policy's first failing
gate is: 201 unresolved source interpretations, 81 reference/nonlexical
components, 75 numbered or editorially split homonyms, 56 insufficient verbatim
lexical corroboration, 20 heading identities and seven missing/disputed independent
readings. These are abstentions, not established incorrect associations; the
counts do not imply that every uncertainty description represents real ambiguity.
No paid request has been made to re-observe these cases.

Validation: 142 focused policy/compiler/facsimile/campaign tests and 65 worker,
review, draft and reader tests passed. Required repository regressions passed
315 tests plus 62 subtests. Both browser suites passed: complete-reader search
and reference navigation over 29,878 witnesses, all 783 certified attachments
at desktop/mobile widths, all 131 distinct page PDFs opened in Chrome, and zero
browser errors. Repository hygiene, Python compilation and whitespace checks
passed. The generated operational status is checked after committing its update.
