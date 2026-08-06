# Integration status — 2026-08-06

## Scope and branch relationship

This stabilization started from the clean, synchronized head of
`codex-reference-marker-next-pass` at
`4d6bb15290b67b70a97779c6fb97d34b27f13b44`. The stabilization branch is
`codex-stabilize-current-release-20260806`.

At branch creation:

- `main` was `7397901eb447fb45f8bad282af42f4cef9ad0e5e`;
- the merge base of `main` and the integration head was the same SHA;
- `main...HEAD` was `0` commits on the main-only side and `277` commits on
  the integration-only side;
- local and remote integration heads both resolved to `4d6bb152...`;
- the worktree was clean; and
- GitHub had no open PR with `codex-reference-marker-next-pass` as its head.

The release manifest records a 29 July full-bundle build observed at
`d407bf522ae6645c50dd7ba9ce4d5b42721d1097`. That is release-input
provenance, not the current repository revision. Later commits, ending with
the six exact duplicated-`p` repairs in `4d6bb152...`, updated tracked release
files. The commit that checks in generated files is necessarily later than
the checkout observed while staging them; per-file Git history records those
later updates.

## Thematic account of the integration branch

The 277 commits are best reviewed in five themes rather than as an undifferentiated
commit list:

1. **Pipeline, hygiene, and tests.** Repository status generation, release
   packaging, exact-token safeguards, ledger reconciliation, development
   dependencies, CI collection, and broad regression coverage were added or
   strengthened.
2. **Final-ṅ and exact-review infrastructure.** The branch built positional,
   same-entry, cross-volume, historical-witness, source-compatible, collision,
   and transcription-integrity gates, while keeping broad substitutions
   forbidden.
3. **Tibetan/Latin evidence and feature authority.** Canonical teaching
   provenance, orthographic parsing, role-conditioned composition, strict
   leave-one-out checks, domain authority, structural OCR attribution, source
   convention review, and anti-circular dependency checks were introduced.
4. **Reviewed correction ledgers.** Exact Latin and Tibetan corrections,
   occurrence-identity checks, supersessions, immutable decision provenance,
   signature decisions, and correction-authority backaudits were persisted.
5. **Generated diagnostics and `release/current`.** The branch tracks the
   deployable four-volume text snapshot, compact QA, checksums, current status,
   canonical/feature/signature evidence tables, and active-versus-historical
   queues.

Relative to `main`, the integration changes 259 files (117 under
`release/`, 103 under `data/`, 23 under `scripts/`, and 13 under `tests/`) with
approximately 362,567 insertions and 21,445 deletions before this stabilization
commit.

## Inputs, generated evidence, and deployable outputs

| Class | Current paths | Notes |
| --- | --- | --- |
| Authoritative human-reviewed inputs | `data/reviewed_*.tsv`, `data/final_ng_alignment_review_exceptions.tsv`, `data/sanskrit_promote_overrides.tsv`, `data/sigla_registry.tsv`, `data/tibetan_dang_phrase_overrides.tsv`, `data/tibetan_latin_feature_registry.tsv`, code under `scripts/` | Exact decisions and policy/configuration inputs. Generated files with `reviewed` in their names are exceptions only where their builder explicitly owns them; provenance fields distinguish teaching permission. |
| Generated diagnostic/evidence tables | most `data/tibetan_*.tsv`, `data/final_ng_*.tsv`, `data/correction_families.tsv`, and `docs/STATUS.md` | Rebuilt from tracked release text/QA plus reviewed registries. They diagnose or revalidate authority; they are not independent correction evidence merely because they are checked in. |
| Deployable release outputs | `release/current/text`, `release/current/qa`, `release/current/manifest.md`, `release/current/checksums.tsv` | 162 tracked files, about 85 MiB. The checksum ledger covers 161 files (everything except itself). All 161 hashes and sizes validate. |
| Ignored production prerequisites | `work/final_ng_seed_clean_20260719T210000Z/{wts_1_34,wts_35_51,wts_8_b,wts_9_m}` and the four sibling `tibetan_cleanup_diagnostics_*` directories | Present in the stabilization workspace but absent from a fresh checkout. Volume outputs are produced by the postprocess pipeline; diagnostics are produced by `build_tibetan_cleanup_diagnostics.py`, `build_tibetan_final_ng_consensus.py`, and `build_tibetan_latin_integrity.py`. |

## Release reproducibility and provenance

### Fresh-checkout result

A local no-sharing clone of `4d6bb152...` was used as a committed-input-only
checkout. Running:

```bash
python3 scripts/build_current_release_bundle.py
```

failed at the first missing required source:

```text
work/final_ng_seed_clean_20260719T210000Z/wts_1_34
```

The other unavailable defaults are the remaining three volume directories and
the four `tibetan_cleanup_diagnostics_*` directories listed above. The builder
now preflights all required volume directories and corrected-text files before
cleaning its destination, so this failure no longer destroys the tracked
release in a fresh checkout.

The four volume directories are required to recopy corrected text and the root
QA artifacts. The diagnostics directories are required for the complete QA
bundle, although their absence is reported as optional by the copier. A future
fully reproducible release needs content-addressed or versioned upstream
postprocess outputs (or the raw merged OCR/alternate inputs plus a documented
command that regenerates them). These inputs must include each
`*_corrected_full.txt` and the QA files selected by
`build_current_release_bundle.py`.

### What can be reproduced from committed inputs

The committed release text and QA were assembled into the run-directory layout
expected by the diagnostic builder. Two runs of each available deterministic
generator produced byte-identical output:

```bash
python3 scripts/build_tibetan_cleanup_diagnostics.py --run-dir RUN --out-dir OUT
python3 scripts/build_tibetan_latin_integrity.py --out-root OUT
python3 scripts/build_tibetan_latin_syllable_concordance.py
python3 scripts/build_tibetan_role_transcription_model.py
python3 scripts/build_tibetan_latin_ocr_signature_evidence.py
python3 scripts/build_tibetan_latin_gate0_audits.py
python3 scripts/build_tibetan_final_ng_consensus.py --release-root release/current --out-root OUT
python3 scripts/build_status.py
```

The cleanup diagnostics regenerated from committed text/QA match their tracked
counterparts exactly. Refreshing the tracked QA required two dependency-
propagation passes through integrity, concordance, role, signature, Gate 0, and
status generation; the following complete pass produced an identical aggregate
SHA-256 and therefore established the fixed point. The first converged
transcription pass exposed six stale, omitted historical observations
(`ppad`, `pphaṅ`, `pphyaṅ`, `pphyis`, `pphar`, and `pphral`). They are now
retained as zero-current, non-teaching audit rows; no authority changed.

With the ignored production directories available, two release-bundle runs
copied identical text and QA payloads, and that payload matched
`release/current`. Only `Generated UTC` in the manifest, and consequently the
manifest checksum row, changed. This timestamp is intentional build metadata,
so the bundle command is not byte-for-byte deterministic without freezing its
time. The checked-in checksum ledger itself validates every current file and is
the available fresh-checkout verification mechanism.

## Focused head audit

### Six duplicated-`p` corrections

Commit `4d6bb152...` changes exactly six release-text lines in `wts_35_51`:

| Page:line | Tibetan | Source | Target | Independent clean target observations |
| --- | --- | --- | --- | ---: |
| 683:4 | པད | `ppad` | `pad` | 22 across `wts_1_34`, `wts_35_51` |
| 884:3 | ཕང | `pphaṅ` | `phaṅ` | 5 in `wts_35_51` |
| 972:48 | ཕྱང | `pphyaṅ` | `phyaṅ` | 9 in `wts_35_51` |
| 1020:39 | ཕྱིས | `pphyis` | `phyis` | 24 across `wts_1_34`, `wts_35_51` |
| 1090:34 | འཕར | `pphar` | `phar` | 5 in `wts_35_51` |
| 1113:2 | འཕྲལ | `pphral` | `phral` | 7 in `wts_35_51` |

All six are headword lines with secure complete Tibetan/Latin spans, secure
token boundaries, no marker/damage, and token index 1. The line-zone diff changes
only the token text at the same six coordinates; no entry, token ordinal, or
following alignment shifts. The evidence registry reports six reviewed
syllables, six conditioned reviews, zero conditioned conflict, and 226
legitimate controls. Persistent `DEL p` remains `D` / `candidate_review`, so
these rows cannot authorize unconstrained initial-`p` deletion. Regression tests
reconcile the six exact overrides, six release changes, the `D` decision, and
the control count.

### Reviewed source-convention authority

`ROOT_NYA_TO_NTILDE` remains authoritative on an explicit WTS source-convention
basis, not an empirical-rule threshold exemption. Current revalidation requires:

- the reviewed source convention and exact root role/feature still match;
- independent, pre-existing, ordinary-Tibetan teaching observations corroborate
  root ཉ → `ñ`;
- reviewed targets, derived corrections, alternate-only evidence, unresolved
  alignments, foreign domains, generic `n`, and non-root Tibetan identities do
  not corroborate;
- no qualifying competing realization survives; and
- strict leave-one-syllable-out still leaves independent corroboration.

The current ledger records 29 qualifying syllables across all four volumes,
zero conflict, and a leave-one-out minimum of 28. Focused tests now cover
independent-corroboration filtering, exclusion of derived targets, strict
leave-one-syllable-out, empirical-threshold enforcement, contradiction failure,
and prevention of authority leakage to an unrelated reviewed feature. The
feature-composition backtest remains 434 exact, 164 partial, 57 role-parse
unresolved, and **zero wrong predictions**.

## Validation

Development dependencies were installed from `requirements-dev.txt` into the
repository-local Python 3.13 environment. The clean baseline and final
stabilization commands produced:

```text
python3 scripts/check_repo_hygiene.py                         PASS
python3 scripts/build_status.py --check                      PASS (5 review warnings)
python3 -m compileall -q scripts                             PASS
python3 -m pytest tests -q                                   464 passed
python3 -m unittest discover -s tests                        462 passed
release/current/checksums.tsv                                161/161 valid
git status --short                                           clean
```

The five non-fatal status warnings are the existing large partially-applied
queues: guarded dollar-to-ś (2,229), canonical syllables (4,848), OCR confusion
signatures (2,386), reference-marker diagnostics (2,795), and Initial-I/ldan
(5,774). Pytest is the authoritative complete suite; unittest discovery is a
compatibility subset because the module-level pytest functions
`test_glang_batch_reconciles_to_44_plus_2` and
`test_final_ng_source_token_collision_controls_pass` are not
unittest-discoverable.

## Current active queues and risks

| Queue | All families | Current families | Current exact occurrences | Historical-only families |
| --- | ---: | ---: | ---: | ---: |
| Alignment or damage | 3,340 | 18 | 34 | 3,322 |
| Domain risk | 133 | 133 | 543 | 0 |
| Gloss alignment noise | 108 | 0 | 0 | 108 |
| Historical echo decision block | 7 | 0 | 0 | 7 |
| Multiple signatures missing | 269 | 269 | 270 | 0 |
| One signature missing | 735 | 735 | 1,027 | 0 |

The final-ṅ diagnostic has 511 historical rows, 495 current extant source rows,
184 target-ready rows, 36 signature-ready rows, 102 alignment-ready rows, 124
domain-ready rows, and **0 final-action-ready rows**. These dimensions are not
interchangeable; no new candidate was promoted in this stabilization.

Primary integration risks are the size of the generated diff, dependence of a
full release rebuild on ignored production artifacts, intentional timestamp
nondeterminism in release metadata, and the substantial residual diagnostic
queues above. Checksums and independent evidence ledgers mitigate corruption and
circularity risks but do not replace linguistic review.

## Integration recommendation

Preserve the complete 277-commit history and integrate with a normal merge
commit after review and CI. Do **not** squash the entire branch: exact decision
ledgers and supersession records cite historical commit SHAs, and the sequence
documents how broad hypotheses were narrowed or reversed. A thematic review can
use the five groups above without rewriting ancestry. If maintainers later want
fewer presentation units, construct additive thematic merge commits on another
branch while retaining the original integration branch and its reachable
history; do not rebase or force-push the reviewed chain.
