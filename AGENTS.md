# Agent Instructions for WtSOCR

## Source of truth

Use these files as the current operational truth:

- `docs/STATUS.md`
- `data/correction_families.tsv`
- `release/current`
- `release/current/qa`
- implementation TSVs under `data/`

Dated reports in `docs/` are historical records unless explicitly listed in `docs/STATUS.md`.

## Do not create new audit reports by default

Do not add new files such as:

- `docs/*audit*.md`
- `docs/*cleanup*.md`
- `docs/*triage*.md`
- `docs/*readiness*.md`
- `docs/*refresh*.md`

unless there is a substantial methodological decision that cannot be represented in:

- `data/correction_families.tsv`
- existing override TSVs
- `docs/STATUS.md`
- `release/current/qa`
- the commit message

Routine progress belongs in the TSV ledger and generated status, not in a new prose report.

## Cleanup policy

Work one residual family at a time.

Do not mix unrelated families in one pass. For example, do not combine `dnos -> dṅos`, `$ -> ś`, sigla, Sanskrit, validator, and Initial-I work.

Do not introduce broad OCR rules unless explicitly approved.

Prefer exact reviewed rows keyed by volume/page/line/token/source.

## Release policy

If corrected text changes, rebuild:

```bash
python3 scripts/build_current_release_bundle.py
python3 scripts/build_status.py
```

If corrected text does not change, do not rebuild `release/current` just to create churn.

## Validation

Before reporting success, run:

```bash
python3 scripts/check_repo_hygiene.py
python3 scripts/build_status.py --check
python3 -m py_compile scripts/build_status.py
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_current_release_bundle.py scripts/report_unresolved_buckets.py scripts/build_tibetan_cleanup_diagnostics.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
git status --short
```

Report exact results.
