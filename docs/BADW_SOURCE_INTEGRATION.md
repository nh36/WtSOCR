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

Parsing must preserve the original BAdW Unicode. WtSOCR OCR correction rules must never be applied to the cached or parsed BAdW source text.

## Generated PDFs for volumes 2–4

The per-article PDFs for volumes 2–4 are digitally encoded sources, not images to be sent directly to OCR. They use embedded subset fonts and CID-coded content without adequate `ToUnicode` maps. The current experiment has demonstrated complete recovery of sampled TGaramond/WTS body glyphs, including the WTS transliteration in the tested material. The mapping of Rabten Tibetan-heading glyphs remains incomplete.

The implementation must attempt deterministic font/content-stream decoding first. Rendered-page OCR is a fallback only for content that cannot be recovered at the font level.

## Staged implementation

### Stage A — harden the tools

Harden and test the catalogue/harvester, database-article parser, article reconciliation, and PDF font decoder. Define reproducible interfaces between cached source objects, parsed records, alignments, and evidence rows. Use only small, reviewable fixtures in tests.

### Stage B — acquire the public corpus

Resumably acquire the complete publicly exposed BAdW database/PDF corpus into the ignored content-addressed cache, retaining request URL, fetch time, response metadata, and content hash.

### Stage C — improve article identification

Improve WtSOCR entry segmentation and BAdW-to-local article identification substantially beyond the current 68.3% experimental success rate. Measure performance by volume, letter, delivery form, and ambiguity class.

### Stage D — reconcile the print-faithful corpus

Produce a corpus-scale ledger of exact differences and provenance. Automatically apply only source-backed OCR corrections that pass the confidence gates to the print-faithful layer, with deterministic rebuilds and audit checks.

### Stage E — expose editorial variants

Represent substantive post-print BAdW readings as a separate enhanced/editorial layer linked to their print-faithful counterparts. Preserve both readings and their provenance.
