# Branch Audit: current-release-refresh

> Historical audit record. This file is not the current to-do list. See `docs/STATUS.md` for the current operational status.

Branch under review: `codex-current-release-refresh`

Base branch: `main`

Audit date: 2026-06-29

## Commits Ahead Of `main`

| Commit | Subject | Classification | Merge? | Notes |
| --- | --- | --- | --- | --- |
| `cf66f05dd6` | refresh current release | OCR/correction behavior; release/current regeneration | yes | Establishes a tracked four-volume current release snapshot from the then-current correction layer. |
| `37ae97affe` | Add Tibetan script ng witness sweep | OCR/correction behavior; tests/tooling; release/current regeneration | yes | Adds reviewed Tibetan script-`ṅ` witness cleanup support and related diagnostics/tests. |
| `eceb3a2803` | Consolidate current OCR correction status | status/consolidation only; documentation/history note | yes, after refresh | Adds the first current-status consolidation layer; it should be regenerated after the final committed release snapshot. |

## Working Tree At Audit

The branch had important unstaged changes at audit time, including:

- `data/reviewed_tibetan_exact_overrides.tsv`
- `release/current/**`
- `scripts/build_current_release_bundle.py`
- `scripts/build_tibetan_cleanup_diagnostics.py`
- `tests/test_postprocess_regressions.py`
- `tests/test_tibetan_cleanup_diagnostics.py`
- `docs/current_release_refresh_2026-06-28.md`
- `docs/current_release_workflow.md`
- `docs/tibetan_initial_i_ng_cleanup_2026-06-28.md`

These changes are not disposable scratch work. They represent accepted current-release cleanup inputs, diagnostics, tests, and generated release artifacts, and should be committed or regenerated into a coherent branch state before merge.

## Merge Readiness Requirement

Before this branch is merge-ready, the final committed state must have:

- a committed `release/current` snapshot generated from accepted code and override tables;
- a regenerated `docs/STATUS.md`;
- a regenerated `data/correction_families.tsv`;
- historical banners on major dated cleanup reports;
- a clean working tree;
- passing status, compile, and regression checks.
