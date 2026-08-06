# Release reproducibility — 2026-08-06

## Previous gap

`release/current/checksums.tsv` allowed a clean checkout to verify the tracked
four-volume release, but `scripts/build_current_release_bundle.py` could only
copy its inputs from ignored directories under
`work/final_ng_seed_clean_20260719T210000Z`. Those directories were present in
the production workspace and absent from Git, so a fresh checkout could not
rebuild the bundle.

The stable integration point is merge commit
`8b9613a55f8d11359fbb15fa07fd6dc1ec3410f2`, annotated by tag
`wtsocr-stable-2026-08-06`. No OCR policy or reviewed linguistic decision is
changed by this reproducibility work.

## Locked production inputs

The committed lock is:

```text
release/inputs/wtsocr-stable-2026-08-06.lock.json
```

It records logical path, archive path, byte size, SHA-256, provenance, and the
known producer/process for every input. The exact inventory is the lock itself;
the minimum groups are:

| Logical directory | Files | Uncompressed bytes | Contents |
| --- | ---: | ---: | --- |
| `wts_1_34` | 15 | 33,212,627 | corrected text and selected postprocess QA |
| `wts_35_51` | 15 | 14,392,534 | corrected text and selected postprocess QA |
| `wts_8_b` | 15 | 7,304,560 | corrected text and selected postprocess QA |
| `wts_9_m` | 15 | 5,284,997 | corrected text and selected postprocess QA |
| `tibetan_cleanup_diagnostics_wts_1_34` | 25 | 15,331,067 | tracked cleanup/final-ṅ/integrity diagnostics |
| `tibetan_cleanup_diagnostics_wts_35_51` | 25 | 6,681,195 | tracked cleanup/final-ṅ/integrity diagnostics |
| `tibetan_cleanup_diagnostics_wts_8_b` | 25 | 3,546,014 | tracked cleanup/final-ṅ/integrity diagnostics |
| `tibetan_cleanup_diagnostics_wts_9_m` | 25 | 2,460,672 | tracked cleanup/final-ṅ/integrity diagnostics |
| **Total** | **160** | **88,213,666** | exact one-to-one source for all substantive release files |

The general-purpose `work/` tree, entry maps, and unselected intermediate
reports are not archived.

## Immutable archive

The inputs are attached to the GitHub release for the stable tag:

```text
https://github.com/nh36/WtSOCR/releases/tag/wtsocr-stable-2026-08-06
```

Asset:

```text
wtsocr-stable-2026-08-06-c6f74598ef22c738de638608cd3528dbdf65e8f347b0eca831ef28c6bd12a458.zip
```

- Compressed bytes: `20,442,926`
- SHA-256: `c6f74598ef22c738de638608cd3528dbdf65e8f347b0eca831ef28c6bd12a458`
- Format: deterministic ZIP with sorted members, fixed metadata, and a single
  `wtsocr-release-inputs/` root.

The filename is content-addressed and GitHub reports the same SHA-256 digest.
The committed lock remains authoritative: replacement or corruption of the
remote asset is detected before any file is used.

## Provenance

Three distinct facts are recorded:

1. `scripts/reproduce_current_release.py` reports the repository revision
   actually running the reproduction.
2. The bundle pins build-recipe revision
   `aef604d5f50a07d86a397b5199c259c866a5c179` so manifest output does not
   acquire a self-referential commit dependency.
3. The inputs came from production workspace
   `work/final_ng_seed_clean_20260719T210000Z`, observed with revision
   `d407bf522ae6645c50dd7ba9ce4d5b42721d1097`.

The exact historical commands that produced every postprocess QA artifact are
not recoverable. The lock states that limitation instead of reconstructing
decision-time provenance. Known diagnostic producers are recorded per file.

## Clean-clone procedure

```bash
git clone https://github.com/nh36/WtSOCR.git
cd WtSOCR
git switch codex-release-reproducibility-20260806
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
python3 scripts/reproduce_current_release.py
```

The reproducer:

1. downloads the filename and URL named by the lock, or locates the exact file
   in `work/release_input_cache`;
2. verifies archive byte size and SHA-256;
3. rejects duplicate, missing, or unexpected archive members;
4. verifies every file byte size and SHA-256 before writing it;
5. atomically materializes exactly the locked logical paths;
6. rebuilds into `work/reproduced_release`; and
7. compares the complete rebuilt tree, including manifest and checksum ledger,
   with `release/current`.

An already downloaded archive may be selected explicitly with `--archive`.
It receives the same verification and is never accepted by filename alone.

## Deterministic metadata

The lock fixes the release timestamp at `2026-07-29T16:22:11Z`. The bundle
builder accepts `--build-timestamp`; absent that option, it honors
`SOURCE_DATE_EPOCH`, and uses current UTC only when neither is supplied. Explicit
timestamps are normalized to UTC. Source and diagnostic paths in the manifest
use stable `locked://` identifiers rather than machine-specific paths.

## Reproduction evidence

Two independent clean output directories were rebuilt from the verified archive
with the fixed lock metadata. Each contained 162 files and differed from
`release/current` in zero files. A direct comparison of the two rebuilt trees
also reported zero differences. Archive creation itself was repeated in tests
and produced byte-identical ZIPs.

## CI

`.github/workflows/release-reproducibility.yml` installs the checked-in
development requirements, restores or downloads the content-addressed archive,
re-verifies it after cache restoration, materializes the lock, rebuilds into
`work/`, and compares against `release/current`. Tracked files are never
modified. The cache key includes the lock-file digest; checksum verification is
not skipped on a cache hit.

## Validation result

The committed branch passed:

```text
python3 scripts/check_repo_hygiene.py          PASS
python3 scripts/build_status.py --check       PASS (5 existing review warnings)
python3 -m compileall -q scripts              PASS
python3 -m pytest tests -q                    470 passed
python3 -m unittest discover -s tests         468 passed
release/current/checksums.tsv                 161/161 valid
locked release inputs                         160/160 valid
git diff --check                              PASS
```

Pytest remains the authoritative complete suite. The two-test difference is
the established pair of module-level pytest tests that unittest discovery does
not collect.

## Remaining limitations

- GitHub release administrators can technically replace an asset, but the
  content-addressed filename and committed archive/per-file hashes make any
  replacement fail closed.
- The historical upstream production pipeline is not fully reconstructible
  from raw OCR inputs because those large raw/intermediate inputs remain outside
  this archive. This system reproduces the accepted release bundle from its
  exact minimum production inputs.
- A future accepted OCR release needs a new lock and a new content-addressed
  asset; this lock must never be silently updated to point at different bytes.
