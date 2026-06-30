## Scope

- [ ] One correction family only
- [ ] No broad OCR rule added
- [ ] No unrelated cleanup mixed in

## Source of truth

- [ ] Updated `data/correction_families.tsv` if family status changed
- [ ] Updated `docs/STATUS.md` via `scripts/build_status.py` if release/status changed
- [ ] Updated `release/current` only if corrected text or QA changed
- [ ] Did not add a new dated report unless justified below

## New docs / reports

New narrative report added?

- [ ] No
- [ ] Yes, justified here:

## Validation

Paste results:

```bash
python3 scripts/check_repo_hygiene.py
python3 scripts/build_status.py --check
python3 -m py_compile scripts/build_status.py
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_current_release_bundle.py scripts/report_unresolved_buckets.py scripts/build_tibetan_cleanup_diagnostics.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
git status --short
```
