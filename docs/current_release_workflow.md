# Current Release Workflow

`release/current` is the repository-level best current WtS OCR snapshot. It
contains the corrected text files that should be treated as the deployable
etext, plus compact QA artifacts, a manifest, and SHA-256 checksums.

The large production directories under `work/` remain ignored by Git. The
minimum accepted inputs for the current stable snapshot are stored separately
as a content-addressed GitHub release asset and described by the committed lock
at `release/inputs/wtsocr-stable-2026-08-06.lock.json`.

The 2026-06-28 refresh deploys the current override tables into
`release/current` for all four volumes, including the latest exact
user-reported Tibetan, siglum, Initial-I/l, and Tibetan-script `ང` witness
cleanup. Earlier tracked bundles were useful QA snapshots, but this bundle is
the repository's best current etext target.

## Locked Current Sources

The lock contains exactly 160 files: four corrected text files, the selected
postprocess QA files copied by the bundle builder, and four diagnostic
directories. It intentionally excludes `*_entry_map.jsonl` and every other
general-purpose `work/` artifact. See
`docs/RELEASE_REPRODUCIBILITY_2026-08-06.md` for the complete inventory,
checksums, provenance, and archive location.

## Clean-checkout reproduction

From a clean checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
python3 scripts/reproduce_current_release.py
```

The command downloads or reuses the exact asset named in the lock, verifies the
archive hash and all 160 per-file hashes, materializes only the locked paths,
builds into `work/reproduced_release`, and compares every file with
`release/current`. Missing, extra, or mismatched inputs fail closed.

## Rebuild

The historical local workflow remains available after a production or
postprocess run has been reviewed and accepted:

```bash
python3 scripts/build_current_release_bundle.py
```

An explicitly materialized input tree can instead be supplied with:

```bash
python3 scripts/build_current_release_bundle.py \
  --input-root work/materialized_release_inputs/wtsocr-stable-2026-08-06 \
  --input-lock-id wtsocr-stable-2026-08-06 \
  --build-timestamp 2026-07-29T16:22:11Z
```

`--build-timestamp` takes precedence over `SOURCE_DATE_EPOCH`; otherwise the
builder uses `SOURCE_DATE_EPOCH` when set and current UTC only as a final
fallback. The lock also pins build-recipe and production-input provenance.

Then run the usual lightweight verification:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py scripts/build_current_release_bundle.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Commit the source changes, docs, and `release/current` together so GitHub always
has a clear best-current etext.

If the QA artifacts become too large to keep expanded in Git, rebuild with:

```bash
python3 scripts/build_current_release_bundle.py --zip-qa
```

That keeps the corrected text expanded while compressing copied QA artifacts
into `release/current/qa_bundle.zip`.

## Policy

This workflow does not change OCR behavior. Base OCR remains authoritative,
Google Vision remains an alternate witness, and correction heuristics must still
be reviewed, tested, and audited before they affect the corrected text.

The bundle intentionally excludes the large `*_entry_map.jsonl` files by
default. Those remain available in the local `work/` outputs when a deeper audit
requires them.
