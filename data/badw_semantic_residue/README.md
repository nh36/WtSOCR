# Semantic residue and header accounting

Pinned completion of the `252f90d0d4` semantic baseline. Source text and `release/current` are unchanged.

## Reproduction

Run from the repository root with the pinned ignored source cache available:

```sh
python3 scripts/finalize_badw_corpus_structure.py --output data/badw_semantic_residue --work work/badw_semantic_residue --contextual-semantics --baseline-store work/badw_contextual_semantics/semantic.sqlite --holdout-manifest data/badw_contextual_semantics/holdout.json
python3 scripts/verify_badw_semantic_replay.py --output data/badw_semantic_residue --work work/badw_semantic_residue --baseline data/badw_contextual_semantics --refine-boundaries
python3 scripts/close_badw_semantic_residue.py
python3 scripts/classify_badw_header_accounting.py
```

The manifest pins source inputs, implementation and generated outputs. Large decoded sources and the semantic SQLite store remain in ignored `work/` storage. Review artifacts are retained here; regeneration does not substitute for facsimile review.

## Semantic closure

All 29,877 witnesses project without reader integrity failure or accepted bibliography identity loss. Citations increase from 109,395 to 109,425; accepted identities from 109,045 to 109,075; established owners from 108,991 to 109,017. There are 109,004 passage owners and 13 reviewed component owners; 47,038 citations have sense ownership and 61,979 have entry-level structural ownership. The 408 unresolved owners include all 404 baseline residuals and four additional cases. Exact occurrence transitions and structural reasons are retained in `ownership_transitions.jsonl` and `residue_closure.json`.

All 28 reviewed missed cues are extracted: 23 have accepted identities and 24 owners. Identity remains unresolved for dBe’uD, Achard 2015, Schwieger without year and the two implicit Abteilung references. Ownership remains unresolved for HINÜBER, two sKal citations and Schwieger. The five unresolved identities are retained rather than guessed. Sixteen remaining ignored cues are previously reviewed diagnostic false positives.

Reviewed occurrence aliases preserve literal spelling, including g.Yu, and point to existing authorities. Compound-author, bounded bare author-year and layout-interrupted matching operate without rewriting source text. Implicit references without a defensible inherited source remain unresolved.

The three remaining language indicators were individually inspected against PDF facsimiles. Exact glyph reviews recover √sphaṭ and Uccaiḥśravas while retaining raw decoded observations. No explicit indicator remains anonymously untyped. The general italic Lex. correspondence rule also captures lokāloka and the second timi. `sanskrit_recall_review.json` records these targeted facsimile checks. All 384 raw overlaps remain provenance evidence: 149 broad Tibetan envelopes with precise Sanskrit subspans and 235 legitimate nested observations; effective unresolved conflicts remain zero.

Lex. objects and xrefs retain their baseline relationships: 39,688 Lex. items, no canonical duplicates or overlaps, 7,484 resolved xrefs and 852 explicitly unresolved xrefs. The 114 frozen holdout entries replay successfully.

## Header structure and accounting

Source-bound header fields are canonical, queryable objects: 2,938 homonym markers, 1,960 alternate headwords, 1,456 grammatical labels and 159 verb-form fields. Source heading structure and explicit labels establish these fields; they are not folded into definitions. `header_fresh_review.json` records eleven fresh HTML source reviews with zero observed false fields. One parallel-alias list remains incompletely typed. These reviews do not establish comprehensive PDF header adaptation.

All 131,068 originally unassigned alphabetic characters are partitioned by exact spans. They comprise 47,836 source structural-label characters, 11,739 newly typed header/language/citation characters, 11,195 decoding-residue characters and 60,298 characters pending meaningful structural review. The latter are 9,091 heading characters, 18,928 unparsed Lex.-clause characters and 32,279 lexical-prose candidates. Candidate classification is not a claim that each span is genuine lost prose. The original 28,912 gap runs and raw accounting totals remain unchanged; no warning was suppressed or definition widened.

All 144 PDF unassigned candidates belong to printed correction apparatus: 110 anchored corrections, 21 multiword corrections, six placeholders and seven unresolved targets. They are not silently promoted to lexical entries.

The next engineering tranche should repair recurring lexical and header boundaries, beginning with the classified PDF Lex./prose and pending heading families. Historical-print adaptation and reader work can then use a more complete accounting contract.
