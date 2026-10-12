# Contextual language and inline references

Scope: the pinned 29,877 acquired online witnesses. Baseline: `0e4c724e21`.
Source readings and `release/current` are unchanged.

## Contracts

Sanskrit forms derive from explicit HTML Sanskrit fields, a literal `skt.`
label with a bounded form, or a printed italic correspondence with an explicit
equivalence/quoted gloss and Mvy reference. Typography alone, nearby source
names and Sanskrit-looking characters are insufficient. Parallel forms require
source connective and typography. German metalinguistic prose, edition locators
and damaged forms remain separately classified.

Original Tibetan/Sanskrit observations survive. Effective language partitions
retain exact Sanskrit subspans inside broad source containers, with evidence.
Lex. correspondences link source-bound forms to their containing item and
Tibetan expression where an explicit relation supports that link.

Inline references require registered author/source vocabulary **and** a local
balanced parenthesis or explicit comparison construction. Unknown editions
remain literal extracted citations without a fabricated bibliography identity.
The existing resolver supplies identities independently of passage ownership.
Existing citation envelopes take precedence; contained shorter vocabulary
matches do not become duplicate occurrences. Ordinary numbers are insufficient.

New citations use existing Lex., attestation, quotation and definition-clause
ownership. An inline correction reference inside a Tibetan expression does not
invalidate the separate terminal attribution of its quotation. Unsupported
local owners remain unresolved. The replay fails if any accepted baseline owner,
bibliography identity or resolved cross-reference is lost.

## Reproduction

With the ignored pinned source cache, frozen projections and baseline store:

```sh
python3 scripts/finalize_badw_corpus_structure.py --output data/badw_contextual_semantics --work work/badw_contextual_semantics --contextual-semantics --baseline-store work/badw_relationship_closure/semantic.sqlite --holdout-manifest data/badw_contextual_semantics/holdout.json
python3 scripts/verify_badw_semantic_replay.py --output data/badw_contextual_semantics --work work/badw_contextual_semantics --baseline data/badw_relationship_closure --refine-boundaries
```

`contextual_classification.jsonl.gz` preserves every frozen diagnostic, literal,
source hash/span, classification and outcome. Summary tables distinguish raw
observations, effective assignments, extracted occurrences and unresolved
identities/owners. `manifest.json` pins sources, code and derived outputs.
Large source packets and SQLite stores remain in ignored `work/` storage.

Query the generated store without scraping reader text:

```sh
python3 scripts/badw_semantic_store.py --db work/badw_contextual_semantics/semantic.sqlite language
python3 scripts/badw_semantic_store.py --db work/badw_contextual_semantics/semantic.sqlite language --lex --siglum Mvy
python3 scripts/badw_semantic_store.py --db work/badw_contextual_semantics/semantic.sqlite language --correspondences
python3 scripts/badw_semantic_store.py --db work/badw_contextual_semantics/semantic.sqlite language --effective
python3 scripts/badw_semantic_store.py --db work/badw_contextual_semantics/semantic.sqlite language --indicators --unresolved
python3 scripts/badw_semantic_store.py --db work/badw_contextual_semantics/semantic.sqlite language --conflicts
python3 scripts/badw_semantic_store.py --db work/badw_contextual_semantics/semantic.sqlite citations --unresolved
```

## Reviewed results and limitations

All 29,877 witnesses project with zero reader failures. Explicit untyped indicators
fall 601 → 3; raw conflicts remain 384 and effective conflicts remain zero.
The store contains 12,023 source-bound Sanskrit forms / 3,003 correspondences.
305 new citations include 278 accepted identities and 259 exact owners. Four
baseline owners are additionally established. Total citations: 109,395; accepted
identities: 109,045; owners: 108,991; unresolved owners: 404. Xrefs, Lex. counts
and lexical accounting remain unchanged. See `comparison.json` and `integration.json`.

The 792 frozen citation cues include 262 confirmed genuine misses: 234 now yield
citations and 28 remain unsupported. The other 530 were existing citation envelopes
or non-citation text. `residual_review.jsonl` supplies exact reviewed classifications
for the final 44 cues (28 genuine misses / 16 false positives), preserving hashes,
literals and source spans. These reviewed judgements are retained inputs, not a
regex interpretation of capitalized names. They do not invent authority identities.
`ownership_residue.jsonl.gz` records all 404 remaining owners with diagnostic reasons.

`holdout.json` records the post-implementation 19-witness scholarly review:
zero observed false claims, but two missed PDF Lex. forms (`lokāloka`, second
`timi`). No fresh PDF Mvy case survived exclusions. Rules were not tuned to those
misses. 114 frozen holdout witnesses pass replay. This is not an accuracy estimate.
Contextual explicit typing is reliable within its documented grammar; implicit
PDF correspondences and the 28 unsupported inline cues remain recall limitations.
Neither layer should be described as exhaustively complete.

`residual_review.jsonl` and the reviewed fields in `holdout.json` are preserved
scholarly review inputs. A replay regenerates diagnostic outputs; retain these
inputs and compare frozen identity/hash/span keys before carrying judgements forward.
`review_summary.json` reports reviewed counts separately from automated classification.
