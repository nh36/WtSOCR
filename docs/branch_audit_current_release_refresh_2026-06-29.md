# Branch Audit: current-release-refresh

> Merge-readiness note for `codex-current-release-refresh`. For current OCR/correction status, see `docs/STATUS.md`.

Branch under review: `codex-current-release-refresh`

Base branch: `main`

Audit date: 2026-06-29

Last updated: 2026-06-30

## Scope

This branch is not merely documentation. It accepts reviewed OCR/correction changes, diagnostics/tests, and a rebuilt `release/current` bundle, then adds status and check machinery that describes the current deployable snapshot.

## Commits Ahead Of `main`

| Commit | Subject | Classification | Merge? | Notes |
| --- | --- | --- | --- | --- |
| `cf66f05dd6` | refresh current release | OCR/correction behavior; release/current regeneration | yes | Establishes a tracked four-volume current release snapshot from the then-current correction layer. |
| `37ae97affe` | Add Tibetan script ng witness sweep | OCR/correction behavior; tests/tooling | yes | Adds Tibetan script-`ṅ` witness diagnostics and related support/tests. |
| `eceb3a2803` | Consolidate current OCR correction status | status/consolidation; documentation/history note | yes | Adds the generated current-status consolidation layer and historical-report banners. |
| `237daeb259` | Promote initial-I and script-ng release cleanup | OCR/correction behavior; tests/tooling; release/current regeneration | yes | Promotes reviewed exact/context-gated Initial-I and script-ng cleanup without broad `I -> l` or `n -> ṅ` rules. |
| `b9e05093c8` | Rebuild current release snapshot | release/current regeneration | yes | Commits the coherent four-volume `release/current` snapshot generated from accepted code and override tables. |
| `5b86c183cc` | Harden current release status checks | status-check hardening; status/consolidation | yes | Makes `scripts/build_status.py --check` fail on stale generated status, hidden correction families, duplicate IDs, missing release/QA evidence, misleading applied labels, unsafe broad-rule applications, and dirty release/status paths. |
| `67b1c6d6e8` | Clarify current release merge readiness | status/consolidation; documentation/history note | yes | Clarifies current remaining work, diagnostic queues, Initial-I status, Sanskrit queues, final-ng/script-ng distinction, and merge-readiness status. |

## Authority Order

- `docs/STATUS.md` is the human operational status.
- `data/correction_families.tsv` is the machine-readable correction-family status ledger.
- `release/current` is the current deployable text snapshot and QA evidence.
- Code plus override TSVs are the implementation source for applied behavior.
- Dated cleanup reports are historical audit records only.

## Merge Strategy

The branch has already been published for review, so this audit preserves the visible stack instead of rewriting it locally. If the repository owner chooses a squash merge, the branch naturally groups into:

1. Apply reviewed Tibetan cleanup and diagnostics.
2. Rebuild current release snapshot.
3. Add current status ledger, release checks, and merge-readiness clarity.

## Merge Readiness Requirement

Before this branch is merge-ready, the final committed state must have:

- a committed `release/current` snapshot generated from accepted code and override tables;
- regenerated `docs/STATUS.md` and `data/correction_families.tsv` from the committed release artifacts;
- historical banners on major dated cleanup reports;
- a clean working tree;
- passing status, compile, and regression checks.
