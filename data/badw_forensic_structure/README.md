# Forensic source-structure replay

Baseline: `a4f42b3af9` (after the Schwieger publication correction). Source hashes and runtime code hashes are pinned in
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

Header extraction now produces **11,305 fields**, including **2,166 relations**,
4,352 aliases, 2,938 homonym markers, 1,464 grammatical labels and 385 labelled
verb forms. Whole composite targets, shared tense markers and ordered comma/und/
`bzw.` alias groups retain exact marker/member spans. HTML and PDF use the same
canonical header contract. PDF rules require explicit opening connectives,
source typography and line/column continuity.

PDF recovery adds exact opening-definition fragments after typed headers and
explicit hyphenated continuations of observed definitions. Existing definition
nodes are preserved: new fragments record the source division, geometry and
boundary evidence, and are available in the semantic store's `fragments` query.
The rules stop at competing examples, Lex., citations, Sanskrit, sense markers,
column changes, semicolons and unbalanced quotation boundaries. No generic prose
container, proximity owner or unverified glyph mapping was introduced.

The unchanged **131,068 alphabetic gap characters** now partition into **40,267
semantically typed**, **66,331 structural-label**, **10,387 decoding-placeholder**
and **13,960 pending meaningful characters**. Meaningful residue fell from
22,825 by **8,865 characters (38.8%)**: HTML 6,401 → **3,766**, PDF 16,424 → **10,194**.
The remaining PDF families are 6,379 lexical-prose characters without proven
boundaries, 1,778 header candidates, 779 alias candidates, 1,101 quotation/gloss
candidates and 157 reference-clause characters. Every pending span retains its
source hash, exact location, local context, nearby components and concrete reason
for remaining unresolved. Classification alone does not recover structure.
The reference-clause contexts were inspected in full; dictionary-key references
and insufficient clause envelopes do not justify additional passage claims.
Placeholder counts measure diagnostic syntax, not printed glyphs; the decrease
reflects precise header accounting, not new glyph-decoding mappings.

`fresh_structural_review.jsonl` records **16 fresh witnesses (14 HTML, two PDF)**,
separate from all 114 frozen witnesses and the earlier 12-header review. Source
inspection found no false relation, over-wide recovered definition or duplicate
content in this sample. PDF review directly checks the opening-definition rule;
it does **not** complete the requested fresh coverage of nested quotations and
mixed continuation families. This limited sample is not a corpus accuracy estimate.

`integration.json` and `frozen_holdout_replay.jsonl` record reader checks, preserved
baseline relationships and **114 passing frozen witnesses**. All 108,732 baseline
citation-owner relationships and 6,825 baseline xref edges survive. Citation
owners remain 109,017 accepted / 408 unresolved; no proximity inference was added.
Lex. remains 39,688 items with zero canonical overlap; bibliography, xrefs and
language metrics remain unchanged. The rejected stale-source PDF overlay remains
rejected. `release/current` remains untouched.

**Not structurally mature.** The next coherent engineering family is the **6,379
PDF lexical-prose alphabetic characters** lacking proven boundaries. It requires
a typography-driven mixed-clause and continuation grammar that can distinguish
Roman explanations, Tibetan examples and their translations within one source
layout unit. The conservative opening/header grammar implemented here cannot
establish those boundaries. That capability should precede historical-print
canonical adaptation or full reader/product development.

## Reproduction

Run from the repository root with the acquired source cache and baseline SQLite:

```sh
python3 scripts/finalize_badw_corpus_structure.py --output data/badw_forensic_structure --work work/badw_forensic_structure --contextual-semantics --baseline-store work/badw_forensic_structure/schwieger_baseline.sqlite --baseline-commit a4f42b3af9 --holdout-manifest data/badw_contextual_semantics/holdout.json --citation-reviews data/bibliography_forensic_citation_reviews.tsv
python3 scripts/classify_badw_header_accounting.py --work work/badw_forensic_structure --output data/badw_forensic_structure
python3 scripts/verify_badw_semantic_replay.py --output data/badw_forensic_structure --work work/badw_forensic_structure --baseline data/badw_semantic_residue --refine-boundaries
python3 scripts/classify_badw_forensic_residue.py
python3 scripts/build_status.py
```

Manual review files are scholarly observations retained separately from generated
diagnostics. Runtime code hashes describe the replay; postprocessing hashes
describe subsequent classification/status generation.
