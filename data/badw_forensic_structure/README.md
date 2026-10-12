# Forensic source-structure replay

Baseline: `26ba4c1344`. Source hashes and runtime code hashes are pinned in
`manifest.json`; raw sources, facsimiles and semantic SQLite remain in ignored
`work/`. No release text was changed.

## Results and evidence

All 29,877 witnesses project, with no reader integrity failures or accepted
bibliography identity loss. Four exact citation reviews raise accepted identities
from 109,075 to 109,079; the 109,425 citation occurrences remain unchanged.
The reviewed rows are in `../bibliography_forensic_citation_reviews.tsv`.

* Achard 2015: author HAL bibliography and RET publisher independently identify
  *The View of sPyi ti Yoga*, RET 31, pp. 1–20. This is an external authority,
  not a retrospectively invented WTS bibliography occurrence.
* Schwieger: supplied 2006 facsimile, scan 243–244 / printed 241–242, directly
  verifies the ergative/instrumental discussion. Work identified; edition remains
  ambiguous because 2009 pagination and entry preparation chronology were not
  established.
* Mvy: 1989 facsimile scan 136 / printed 226 verifies Sakaki 4642 and its section;
  scan 102 / printed 159 verifies Sakaki 3129 and its section. The malformed
  online literals remain unchanged; reviewed work relationships supply Mvy.
  Their origin in print versus online conversion has not been established.
* `dBe’uD 212,4`: volume 3, printed 212 / scan 2166 genuinely prints the extra
  `d`. Be’uD's cited page was unavailable for content verification. No alias or
  decoding correction is accepted. This is the one unresolved focal identity;
  346 identities remain unresolved across the whole corpus.

External bibliographic URLs and PDF hashes are retained in the authority/review
TSVs. `badw_questions.tsv` contains five concise editorial questions, including
the uncertain edition, unresolved source label and confirmed malformed online
references. No message has been sent to BAdW.

The 408 owner residue is enumerated in `ownership_residue.jsonl.gz`, with frozen
family counts in `forensic_residue.json`. `ownership_context_review.jsonl`
records all 11 small-family contexts and 24 systematic prose/comparison contexts.
No new owner was inferred. Local variant parentheses and nested/malformed quotes
expose possible bounded-grammar work; the pass does not prove that every remaining
prose case is intrinsically unbounded.

Header extraction now produces 9,360 fields, including 796 short-form, perfect,
future and imperative relations with exact marker/target evidence. Aliases retain
list grouping. `fresh_header_review.jsonl` records 12 fresh inspections, six PDF
facsimiles and six preserved HTML structures. No false relation was observed;
missed parallel aliases, shared tense connectives and composite targets remain
explicit recall/model limitations. This sample is not a corpus accuracy estimate.

Accounting partitions the unchanged 131,068 alphabetic gap characters into
30,990 typed characters, 66,412 structural-label characters, 10,841 characters of
decoding-placeholder syntax and **22,825 pending meaningful characters**.
`pending_structure.jsonl.gz` retains source-bound candidates; classification does
not itself assert semantic structure. Most former PDF Lex. gaps were `. Lex.`
labels beside already parsed Lex. items: their reclassification is not new Lex.
boundary recovery. Definitions were not widened and no catch-all was added.
Unknown glyph signatures are enumerated without accepting unverified mappings.

`integration.json` and `frozen_holdout_replay.jsonl` record reader checks, preserved
baseline relationships and 114 frozen witnesses. Lex., xrefs and language metrics
remain unchanged. The rejected stale-source PDF overlay remains rejected.
Structural extraction is not yet complete; bounded header/prose repair remains
necessary before historical-print adaptation or full reader/product work.

## Reproduction

Run from the repository root with the acquired source cache and baseline SQLite:

```sh
python3 scripts/finalize_badw_corpus_structure.py --output data/badw_forensic_structure --work work/badw_forensic_structure --contextual-semantics --baseline-store work/badw_semantic_residue/semantic.sqlite --baseline-commit 26ba4c1344 --holdout-manifest data/badw_contextual_semantics/holdout.json --citation-reviews data/bibliography_forensic_citation_reviews.tsv
python3 scripts/classify_badw_header_accounting.py --work work/badw_forensic_structure --output data/badw_forensic_structure
python3 scripts/verify_badw_semantic_replay.py --output data/badw_forensic_structure --work work/badw_forensic_structure --baseline data/badw_semantic_residue --refine-boundaries
python3 scripts/classify_badw_forensic_residue.py
python3 scripts/build_status.py
```

Manual review files are scholarly observations retained separately from generated
diagnostics. Runtime code hashes describe the replay; postprocessing hashes
describe subsequent classification/status generation.
