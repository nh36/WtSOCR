# Source-structural relationship closure

Baseline: `e53176838a`, frozen results in `data/badw_semantic_hierarchy`.
Scope: all 29,877 acquired online witnesses (18,037 HTML; 11,840 PDF).
No source readings, bibliography identities, or `release/current` changed.

## Results

| Measure | Baseline | Current |
|---|---:|---:|
| Successful projections | 29,877 | 29,877 |
| Resolved HTML xrefs | 4,649 | 4,706 |
| Unresolved HTML xrefs | 633 | 576 |
| Resolved PDF xrefs | 2,176 | 2,778 |
| Unresolved PDF xrefs | 878 | 276 |
| Citations with established owner | 81,866 | 108,728 |
| Unresolved HTML citation owners | 2,497 | 48 |
| Unresolved PDF citation owners | 24,727 | 314 |
| Citations with sense ownership | 36,777 | 46,946 |
| Citations without established sense, but with owner | 45,088 | 61,782 |

109,090 citations remain source-bound; 108,767 retain accepted bibliography
identities. Of the established owners, 108,715 are exact passages and 13 are
reviewed relationships. An owned passage without an established sense is an
entry-level structural relation, **not** a claim that its citation supports the
whole entry. All 81,866 baseline owners and 6,825 resolved xrefs are preserved.

Ownership evidence: Lex. containment 39,489; explicit HTML attestation 42,364;
PDF quotation 23,914; definition/comparison clause 2,948; reviewed relationship
13; unresolved 362. See `relationships.json` for HTML/PDF breakdowns and the
complete classification of the original 27,224 unresolved owners and 1,511
unresolved xrefs. `baseline_residue.jsonl.gz` retains individual source-bound
classifications and outcomes.

## Accepted relationships and limits

PDF xref target parsing separates the literal arrow span, lexical label,
homonym qualifier, and remaining qualifier. Raised numbers require matching
page, coordinates, regular numeral and italic target typography. Wrapped
targets require continuous italic target evidence. Changed extents with mixed
typography fail closed. Exact headword/homonym identities retain separate
witness candidates; homonyms are never merged. Missing HTML hyperlinks can
resolve across manifestations only when the decoded lemma label and explicit
homonym agree exactly. No fuzzy spelling resolution is asserted.

New PDF quotation ownership requires one Tibetan expression and one balanced
quoted German gloss in the same bounded source envelope, explicit citation
attachment, and no crossing sense or conflicting Lex. structure. Optional
metrical labels and punctuated citation groups remain literal. Candidate
example edges alone are insufficient. Definition/comparison ownership requires
exact unmixed DOM/source clause containment or an explicit bounded comparison;
mixed examples, overlapping Lex. material and sense crossings are rejected.
Grouped citations share their passage. Clause containment records a structural
owner; it does not assert that every reference supports every proposition in
that clause. Bibliographic identity and ownership remain independent.

Residual xrefs: HTML 572 missing explicit targets plus four absent unlinked
targets; PDF 128 absent exact targets, 118 ambiguous homonym candidate sets and
30 unestablished target extents. Two of the latter retain ambiguous status;
PDF status totals are therefore 120 ambiguous and 156 other unresolved. Each
record retains its reason/candidate evidence. Remaining citation owners are
explicitly unresolved, chiefly missing or malformed clause/example envelopes;
no nearest-preceding example or unrestricted proximity rule is used.

Reader and semantic-store records retain ownership evidence, candidate sets,
cross-manifestation identities and unresolved reasons without exposing debug
internals in normal text. Exact reader text and bibliography linkage survive
all 29,877 projections. Canonical Lex. duplicates/overlaps and store foreign-key
violations remain zero. Accounting gaps, boundary warnings and language typing
are unchanged; this tranche does not improve their metrics by widening spans.

## Validation and replay

All 60 previously frozen holdout entries replay without reader or bibliography
regressions. A fresh stratified sample of 54 entries (22 HTML, 32 PDF), including
two targeted PDF boundary controls, was reviewed against HTML source packets
and 35 PDF facsimile pages. Selection excludes previous review sets and rule
development cases. `holdout.json` freezes selection;
`fresh_holdout_review.jsonl` preserves per-entry observations and source hashes.
Observed false xref resolutions, false citation owners, over-wide passages and
incorrect passage boundaries: zero. This is a sample observation, not a
population accuracy estimate or browser presentation certification.

With the pinned ignored source cache and original projection packets present:

```sh
python3 scripts/finalize_badw_corpus_structure.py --output data/badw_relationship_closure --work work/badw_relationship_closure --holdout-manifest data/badw_relationship_closure/holdout.json
python3 scripts/verify_badw_semantic_replay.py --output data/badw_relationship_closure --work work/badw_relationship_closure --baseline data/badw_semantic_hierarchy --refine-boundaries
```

This streams the full frozen source/structural corpus through current canonical
relationships, reader and store; it does not reacquire upstream sources.
`manifest.json` pins source/input/parser hashes, baseline and current store
hashes, and diagnostic artifacts. Large source packets and SQLite stores remain
ignored in `work/`; checked-in outputs contain compact metrics and anomalies.

Query the generated store without scraping reader text:

```sh
python3 scripts/badw_semantic_store.py --db work/badw_relationship_closure/semantic.sqlite citations --unresolved
python3 scripts/badw_semantic_store.py --db work/badw_relationship_closure/semantic.sqlite citations --evidence PDF_example_quotation
python3 scripts/badw_semantic_store.py --db work/badw_relationship_closure/semantic.sqlite citations --passage PASSAGE_ID
python3 scripts/badw_semantic_store.py --db work/badw_relationship_closure/semantic.sqlite citations --sense SENSE_ID
python3 scripts/badw_semantic_store.py --db work/badw_relationship_closure/semantic.sqlite citations --entry-level
python3 scripts/badw_semantic_store.py --db work/badw_relationship_closure/semantic.sqlite xrefs --unresolved
python3 scripts/badw_semantic_store.py --db work/badw_relationship_closure/semantic.sqlite xrefs --status ambiguous
python3 scripts/badw_semantic_store.py --db work/badw_relationship_closure/semantic.sqlite xrefs --cross-manifestation
```

Cross-reference engineering is mature for mechanically recoverable exact
targets; genuine absence and ambiguous source qualifiers remain explicit.
Citation ownership is structurally mature for bounded source passages, with
362 cases left unasserted. The next tranche should address contextual Sanskrit
typing using these established structures, followed by residual accounting and
historical-print adaptation.
