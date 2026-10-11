# Source-bound semantic hierarchy replay

Baseline: `d99f6c51c2`, frozen diagnostics in `data/badw_corpus_structure`.
Scope: 18,037 HTML and 11,840 acquired online-PDF witnesses. This is not a
new adaptation of the historical printed volumes. Bibliography reconciliation
and `release/current` remain unchanged.

## Result

| Measurement | Baseline | This replay |
| --- | ---: | ---: |
| Successful projections | 29,875 | 29,877 |
| Projection exceptions | 2 | 0 |
| Citation occurrences | 109,087 | 109,090 |
| Accepted bibliography identities | 108,764 | 108,767 |
| Exact passage-owned citations | 0 | 81,853 |
| Total owned citations, including reviewed relationships | 13 | 81,866 |
| Unresolved citation ownership | 109,074 | 27,224 |
| Resolved HTML xrefs | 4,649 | 4,649 |
| Unresolved HTML xrefs | 629 | 633 |
| Resolved PDF xrefs | 0 | 2,176 |
| Ambiguous PDF xrefs | 120 candidates | 120 |
| PDF xrefs without an exact index label | 758 | 758 |
| PDF reader xrefs missing their source binding | 3,054 | 0 |
| Canonical Lex. item overlaps | 564 raw indicators | 0 |
| Explicit-language indicators still untyped | 601 | 601 |
| Contradictory raw language observations | 384 | 384 retained |
| Contradictory effective language assignments | 384 | 0 |

There are 21,876 Lex. blocks, 39,688 individual items and 82,052 citable
passages. Items have 13,242 sense owners and 26,446 entry owners. The 8,190
HTML Lex. clauses formerly outside numbered sense nodes now have explicit
division membership; entry-level blocks remain entry-level. Ownership is
derived structural evidence, not a claim of manual scholarly verification.
Citation sense ownership totals 36,777; entry-only ownership totals 45,088.
Reviewed relationships can carry a different degree of hierarchy information.

The two additional successful witnesses explain three additional citations,
four additional unresolved HTML arrows and seven additional unassigned lexical
characters. On the 29,875 common witnesses, unassigned alphabetic content is
unchanged at 131,061 characters; unassigned characters remain 2,203,090 across
28,910 runs. Crossing spans (1,063), later-structure boundary warnings (1,289),
PDF definition-boundary warnings (74) and empty numbered senses (3) are unchanged.
The hierarchy does not improve accounting by widening definitions.

## Contracts and limitations

`badw_semantic_hierarchy.py` retains exact literals, half-open source spans,
source hashes and stable IDs derived from witness identity, text hash, kind and
span. Observations, reviewed annotations, canonical relationships and reader
segments remain separate. Blocks govern delimiter-bounded Lex. items; typed
fields retain observed Tibetan, Sanskrit, translation and citation spans.
Unexpressed grammatical relationships remain unresolved.

Sense ownership uses explicit HTML division membership or an exact PDF
numbered/unsegmented division envelope. Citation ownership uses unique Lex.
item containment or explicit HTML attestation/example association. Malformed
Lex. delimiters and competing passage candidates fail closed. PDF example
candidate edges and generic proximity are not accepted ownership evidence.
There are 64,429 HTML and 17,424 PDF passage-owned citations. The remaining
27,224 owners require stronger evidence; bibliography identity does not supply it.

PDF arrows preserve stable source node IDs through adaptation and reader
projection. Exact resolution requires one indexed witness for the literal
target label; homonyms/multiple witnesses retain candidates. Lexical entity IDs
are separate from target witness IDs, allowing cross-manifestation navigation.
`pdf_xref_residuals.jsonl` preserves all 878 unresolved PDF edges. Qualifiers and
wrapped targets are review candidates; no exact label is not proof that the
target is outside the acquired corpus.

Explicit Sanskrit structure overrides a broader Tibetan envelope only in the
derived language partition. All 384 contradictory observations remain intact.
The 601 untyped explicit indicators are not solved. The next engineering tranche
should type Sanskrit through explicit correspondence relations and typography.
Historical-print adaptation and residual header/accounting cleanup follow that.

Both `ka chen/1` and `kos sñuṅ/1` now project: nested arrow/link construction
was corrected without relaxing duplicate-span validation. Twelve reviewed
overlays apply; one PDF overlay remains rejected for a stale source-view binding.
Its source hash must be re-reviewed before reuse. Reader data integrity and
bibliography preservation pass across the corpus; this is not browser visual
certification.

## Validation samples

The frozen original 30-entry set passes exact reader concatenation and authority
preservation. Previously observed Sanskrit and malformed-source limitations
remain; this is not a claim that all 30 are scholarly-clean.

The second stratified holdout excludes earlier review material and development
examples. Its 30 source-bound reviews are in `holdout_review.jsonl`: 25 clean,
four defects, one unresolved case. Fourteen HTML witnesses and sixteen PDF
witnesses were inspected; PDF facsimile inspection covered 19 pages including
continuations. No false citation owner, over-segmentation, incorrect resolved
xref or language overreach was observed. Residuals are Sanskrit correspondences
`eta/yūyam`, `mahārauravaḥ`, `luñcate`, a stray PDF layout numeral in `bgyis`,
and the qualified/wrapped unresolved target in `träge`. These observations were
recorded after implementation and were not used to tune the rules.

## Reproduction and queries

Pinned inputs/code/output hashes are in `manifest.json`. Raw cache objects,
projections, facsimiles and derived SQLite stay in ignored `work/` storage.
Checked-in outputs contain compact diagnostics and review provenance.

```sh
python3 scripts/audit_badw_corpus_structure.py --work work/badw_semantic_hierarchy --output data/badw_semantic_hierarchy
python3 scripts/finalize_badw_corpus_structure.py --work work/badw_semantic_hierarchy --output data/badw_semantic_hierarchy
python3 scripts/verify_badw_semantic_replay.py --refine-boundaries
python3 scripts/badw_semantic_store.py --db work/badw_semantic_hierarchy/semantic.sqlite lex --siglum Dagy
python3 scripts/badw_semantic_store.py --db work/badw_semantic_hierarchy/semantic.sqlite lex --sanskrit
python3 scripts/badw_semantic_store.py --db work/badw_semantic_hierarchy/semantic.sqlite passages --authority AUTHORITY_ID
python3 scripts/badw_semantic_store.py --db work/badw_semantic_hierarchy/semantic.sqlite citations --sense SENSE_ID
python3 scripts/badw_semantic_store.py --db work/badw_semantic_hierarchy/semantic.sqlite citations --unresolved
python3 scripts/badw_semantic_store.py --db work/badw_semantic_hierarchy/semantic.sqlite xrefs --target ENTRY_OR_ENTITY_ID
```

The derived store has 81,853 citation/passage joins and zero foreign-key
violations. Query commands read canonical records rather than rendered text.
Manual holdout verdicts are retained separately from generated selection files.
