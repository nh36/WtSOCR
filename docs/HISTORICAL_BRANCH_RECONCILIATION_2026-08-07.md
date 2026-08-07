# Historical Branch Reconciliation — 2026-08-07

Historical audit record. The branch comparisons below were made against `main` at
`2d0905aa6a39363cf5e57ab70159b98c173bb907`. For the current operational state,
see `docs/STATUS.md`.

## Outcome

Both remaining branch heads should be preserved by annotated archival tags and
their branch refs deleted. Neither branch contains executable work that should be
merged into the current pipeline. One missing historical document cited by the
current status ledger is restored in concise form by this reconciliation PR.

## `loc-end-to-end-audit`

- Head: `bda9306f77ef9e881b764940be8dd3aabf65c68f`
- Merge base with current `main`: `9a9b35826ee0c8682c63e45d633b7bbf8472f46b`
- Unique commits by ancestry: 35
- Reconciliation: PR #1 produced the one-parent squash commit
  `f35811e825cad284101aa5d98e0c25215de03bb2`. The tree at that commit is
  byte-identical to the historical branch head. Thus all 35 patches are already
  represented on `main`, even though their individual SHAs are not ancestors.

Every unique commit is classified below as **patch-equivalent to work already on
`main` through the tree-identical PR #1 squash**:

| Theme | Commits |
| --- | --- |
| LoC heuristics and exact regression fixes | `b8ee34d`, `5875983`, `4f9a646`, `86e9ac6`, `1dd717f`, `e0801ae`, `8f34605` |
| Source inventory, OCR planning, sigla research, and cache policy | `68bc078`, `51d6f59` |
| Google preclean and curated Tibetan `daṅ` handling | `678243a`, `19bfb11`, `2b6f31e`, `6c12328`, `e299506` |
| Alternate-witness arbitration, alignment, guarded adoption, and diagnostics | `93b37bb`, `2ef2272`, `117013d`, `aaea50a`, `952aaa5`, `9ca7771`, `4d295ef`, `9147c0a`, `fadbf20`, `a6a24bf`, `a92a95d`, `866dd7d`, `3a7be1d`, `7526b72`, `76619d5`, `ff96e99`, `9632bd2`, `43724be`, `c5fb3f4` |
| Final PR finding fixes | `00db977`, `bda9306` |

File checks confirm that `data/source_pdfs.tsv`, the Google fallback audit,
OCR plan, sigla research, and line-anchor scripts were incorporated exactly by
`f35811e`. `data/tibetan_dang_phrase_overrides.tsv`, `postprocess_entry_map.py`,
and their tests have since been materially extended on `main`; the historical
versions must not be reintroduced.

**Recommendation:** create `archive-loc-end-to-end-audit`, then delete the local
and remote branch refs.

## `production-qa-release-candidate`

- Head: `f591b5790a0ef3f8e910dfeaf47128ddc4cc8423`
- Merge base with current `main`: `f35811e825cad284101aa5d98e0c25215de03bb2`
- Unique commits by ancestry: 28
- Reconciliation: the branch is a historical production-QA and Sanskrit-review
  experiment. Its dated `work/` inputs and report generators were not merged.
  Current release locks, `release/current/qa`, `build_status.py`, and the
  four-volume residual ledger supersede that workflow.

| Commit | Classification | Current disposition |
| --- | --- | --- |
| `969144e` | Substantively superseded | Old production-QA generator replaced by current release/QA builders. |
| `781344f` | Historical documentation | Old production triage report; preserve in archive only. |
| `41f2038` | Historical decision provenance | Sanskrit proposals predate current reviewed authority; do not import. |
| `566a7f8` | Substantively superseded | Citation/siglum behavior now has narrower registries and tests. |
| `3c97fc0` | Obsolete experiment | `production_volume_inputs.tsv` names dated ignored `work/` paths; input locks supersede it. |
| `70834e0` | Historical documentation | Old all-volume priority snapshot; counts are stale. |
| `07cccd7` | Substantively superseded | Tibetan confusable handling is now exact-reviewed and ledger-backed. |
| `73fdef7` | Historical documentation | Suspicious-token audit snapshot; current queues replace it. |
| `97fc9ac` | Substantively superseded | Old QA classifier replaced by current generated queue/status machinery. |
| `e22ca2b` | Historical documentation | Release-candidate readiness snapshot, not current guidance. |
| `4a3f158` | Obsolete experiment | Manual-package script is tied to a dated `work/` bundle and fixed filenames. |
| `f36f5e6` | Substantively superseded | Narrowing logic and regression intent are covered by later pipeline safeguards. |
| `db3c28b` | Substantively superseded | Initial-I German controls are covered by the current gated model and tests. |
| `8a53d36` | Substantively superseded | Initial-I/Sanskrit edge handling was replaced by later exact reviews. |
| `7ac7001` | Substantively superseded | Its regression intent is present in the expanded current test suite. |
| `ecce264` | Historical decision provenance | Old `īśvara` recovery is preserved for history; current rules govern release text. |
| `8b7bf00` | Historical documentation | Postprocess audit snapshot; archive only. |
| `f5004a4` | Substantively superseded | Old QA/report consolidation replaced by current immutable release workflow. |
| `876a1f4` | Substantively superseded | Live-remaining classifier and report are replaced by current queues. |
| `e1d9452` | Substantively superseded | Old QA provenance fields are replaced by current ledgers and locks. |
| `c354e8c` | Historical decision provenance | Exact Sanskrit-title proposals require current review before reuse. |
| `738198f` | Obsolete experiment | Google candidate miner is non-authoritative and tied to obsolete QA outputs. |
| `949e652` | Historical decision provenance | Prajñāpāramitā proposals are not current reusable authority. |
| `08eae37` | Historical decision provenance | Large-batch decisions remain historical; only their cited audit summary is restored. |
| `ba446fa` | Historical decision provenance | Residual Sanskrit review and QA are stale; do not import old corrections. |
| `b66a71a` | Substantively superseded | Grouped residual outputs are covered by current residual ledgers. |
| `96eed12` | Historical decision provenance | Promotable-candidate decisions are not current reviewed authority. |
| `f591b57` | Historical decision provenance | Final postcheck is preserved by tag, not merged into active decisions. |

The branch has 377 Sanskrit override rows versus 272 on current `main`; 121
source-target pairs are branch-only. Many corresponding source tokens remain in
the current release. This is evidence that the branch decisions were not adopted,
not permission to restore them: importing them would change linguistic decisions
and release text outside this reconciliation task. The tracked
`work/sanskrit_large_batch_decisions_20260528.tsv` remains archival material.

The only current-file gap is the historical audit named by `docs/STATUS.md` and
`data/correction_families.tsv`. A concise, explicitly historical
`docs/sanskrit_large_batch_cleanup_2026-05-28.md` is restored; no override,
generator, test, `work/` artifact, or release output is imported.

**Recommendation:** create `archive-production-qa-release-candidate`, then delete
the local and remote branch refs.

## Preservation and integration boundary

The archival tags preserve every otherwise unreachable commit, including old
reports and experiments. `main` receives only this reconciliation record and the
missing cited historical synopsis. No release text, reviewed ledger, correction
rule, generated QA table, or release snapshot changes in this reconciliation.
