# Current Release Workflow

`release/current` is the repository-level best current WtS OCR snapshot. It
contains the corrected text files that should be treated as the deployable
etext, plus compact QA artifacts, a manifest, and SHA-256 checksums.

The large production directories under `work/` are local artifacts. They remain
ignored by Git, so every accepted cleanup pass should end by rebuilding
`release/current` and committing the updated snapshot.

The 2026-06-28 refresh deploys the current override tables into
`release/current` for all four volumes, including the latest exact
user-reported Tibetan, siglum, Initial-I/l, and Tibetan-script `ང` witness
cleanup. Earlier tracked bundles were useful QA snapshots, but this bundle is
the repository's best current etext target.

## Current Sources

The current bundle is built from these trusted local outputs:

| Volume | Local output directory |
| --- | --- |
| `wts_1_34` | `work/current_release_four_volume_refresh_20260628T193714Z/wts_1_34` |
| `wts_35_51` | `work/current_release_four_volume_refresh_20260628T193714Z/wts_35_51` |
| `wts_8_b` | `work/current_release_four_volume_refresh_20260628T193714Z/wts_8_b` |
| `wts_9_m` | `work/current_release_four_volume_refresh_20260628T193714Z/wts_9_m` |

The Tibetan cleanup diagnostics are copied from:

| Volume | Local diagnostics directory |
| --- | --- |
| `wts_1_34` | `work/current_release_four_volume_refresh_20260628T193714Z/tibetan_cleanup_diagnostics_wts_1_34` |
| `wts_35_51` | `work/current_release_four_volume_refresh_20260628T193714Z/tibetan_cleanup_diagnostics_wts_35_51` |
| `wts_8_b` | `work/current_release_four_volume_refresh_20260628T193714Z/tibetan_cleanup_diagnostics_wts_8_b` |
| `wts_9_m` | `work/current_release_four_volume_refresh_20260628T193714Z/tibetan_cleanup_diagnostics_wts_9_m` |

These `work/` paths are local, unversioned artifacts. They are recorded here so
the accepted bundle can be reproduced on this machine; the tracked deployment
artifact is `release/current`.

## Rebuild

After a production or postprocess run has been reviewed and accepted, rebuild
the tracked snapshot:

```bash
python3 scripts/build_current_release_bundle.py
```

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
