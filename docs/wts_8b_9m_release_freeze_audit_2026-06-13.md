# WtS 8-b / WtS 9-m Release-Freeze Audit

Date: 2026-06-13

## Scope

This note consolidates the final reviewed state of the WtS 8-b and WtS 9-m
Google-witness QA bundles after the WtS 9-m exact `dṅos` follow-up.

No OCR correction heuristics were added in this audit pass. Google Vision
remains an alternate witness only, and the base OCR remains authoritative.

## Repository State

- Branch: `main`
- Current commit: `791ef2861e Update WtS 8-b and 9-m release readiness handoff`
- Regression command: `python3 -m pytest tests/test_postprocess_regressions.py -q`
- Expected/current result: `89 passed`
- Compile command:
  `python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py`
- Compile result: passed

## Trusted Local Artifact Roots

- WtS 8-b QA bundle:
  `work/postprocess_new_volumes_google_qa_20260613T013443Z/wts_8_b`
- WtS 9-m superseding QA bundle:
  `work/postprocess_wts_9m_dngos_exact_fix_20260613T071502Z/wts_9_m`
- Superseded WtS 9-m bundle:
  `work/postprocess_new_volumes_google_qa_20260613T013443Z/wts_9_m`

The `work/` outputs are local generated artifacts and are not versioned in the
repository. The WtS 9-m superseding bundle is the trusted bundle for release
review because the earlier diagnostic bundle still included bad `dnos -> dños`
alternate-witness adoptions.

## Current QA Counts

| Volume | Alternate adoptions | Unresolved rows | Changes TSV rows | Watchdog rows | Sanskrit review suggestions | Reviewed Tibetan exact changes | Corrected text checksum |
|---|---:|---:|---:|---:|---:|---:|---|
| `wts_8_b` | 3 | 900 | 2383 | 31 | 22 | 0 | `89fbf4754e5f2a16d960861c0a8b288372396716eaf3c8b359b111cab2f47fe2` |
| `wts_9_m` | 853 | 1135 | 1560 | 16 | 14 | 4 | `0c72843d09fd40148965822729e7a2f97090bc94d733427db87636d5dfdb6b7f` |

## Adoption Reasons

| Volume | Reason | Count |
|---|---|---:|
| `wts_8_b` | `alternate_witness_google_loc_fricative_upgrade` | 1 |
| `wts_8_b` | `alternate_witness_google_loc_nasal_upgrade` | 1 |
| `wts_8_b` | `alternate_witness_initial_i_to_l_translit` | 1 |
| `wts_9_m` | `alternate_witness_google_loc_nasal_upgrade` | 422 |
| `wts_9_m` | `alternate_witness_initial_i_to_l_translit` | 238 |
| `wts_9_m` | `alternate_witness_google_loc_fricative_upgrade` | 98 |
| `wts_9_m` | `alternate_witness_citation_siglum` | 66 |
| `wts_9_m` | `alternate_witness_google_loc_velar_nasal_upgrade` | 21 |
| `wts_9_m` | `alternate_witness_hyphenated_initial_i_to_l_translit` | 5 |
| `wts_9_m` | `alternate_witness_citation_cleanup` | 2 |
| `wts_9_m` | `alternate_witness_strict_translit` | 1 |

## Alignment Attribution

| Volume | Alignment attribution | Resynchronization attribution |
|---|---|---|
| `wts_8_b` | `rewrapped_page_alignment`: 3 | `direct_page_alignment`: 3 |
| `wts_9_m` | `recovered_rewrapped_fallback`: 825; `rewrapped_page_alignment`: 28 | `direct_recovered_rewrapped_fallback`: 825; `direct_page_alignment`: 28 |

The WtS 9-m recovered-fallback count remains a QA visibility issue, not a
license to treat Google Vision as an authority.

## Manual Audit Performed

All three WtS 8-b adoptions were inspected:

| Page | Line | Change | Decision |
|---:|---:|---|---|
| 3 | 18 | `bses -> bśes` | Good fricative upgrade in Wylie-like context. |
| 3 | 25 | `sPan-lun -> sPañ-lun` | Good nasal upgrade in Wylie-like context. |
| 3 | 32 | `Iha -> lha` | Good initial-I-to-l transliteration cleanup. |

For WtS 9-m, the audit sampled all high-density adoption pages and the rare
direct/low-count adoption classes:

- High-density pages sampled: 126, 268, 272, 326, 187, 58, 79, 112, 120, 146,
  173, and 389.
- High-density rows reviewed: 117.
- Additional rare/direct rows reviewed: 35, covering all 28 direct same-page
  alignment rows, all 5 hyphenated initial-I rows, both citation-cleanup rows,
  and the single strict-transliteration row.

No bad or release-blocking adoption was found in this audit sample. The accepted
patterns were common Tibetan nasal upgrades, initial `I` to `l` in Wylie-like
context, fricative upgrades, and a small number of citation/siglum cleanups.
Citation/siglum rows remain policy-sensitive diagnostics and should not be used
as evidence for new OCR rules.

## Prior Issue Checks

- The known bad `dnos -> dños` output is no longer present in the trusted WtS
  9-m corrected text.
- The earlier `gañ dag` concern resolves in the trusted corrected text as
  `gaṅ dag`.
- The accepted `gNa-khri -> gÑa-khri` change remains present where reviewed.
- One separate `gNa-khri` occurrence remains unchanged. It should not be
  changed during this freeze pass without source review.

## Diagnostic Queues Left Unpromoted

| Volume | Unresolved confusable pairs | Promote-labeled bucket rows | Hold bucket rows | Release-freeze decision |
|---|---:|---:|---:|---|
| `wts_8_b` | 133 | 3 | 130 | `miñ -> miṅ`, `Myañ -> Myaṅ`, and `sañ -> saṅ` remain review diagnostics only. |
| `wts_9_m` | 106 | 1 | 105 | `Vi$T -> ViśT` is citation/siglum-like and was not an OCR promotion candidate in this release-freeze pass. Later source-list review resolves `ViśT` as the canonical siglum. |

No further correction was promoted from these queues. They should be handled in
a later source-review pass, not during release freeze.

## Release-Freeze Decision

WtS 8-b is suitable for release QA handoff with the trusted bundle above.

WtS 9-m is suitable for release QA handoff using the superseding `dṅos` fix
bundle. The known bad `dños` issue has been removed, and the four exact
`dnos -> dṅos` reviewed corrections are documented. Watchdog counts did not
increase, and the sampled high-density/rare adoption rows did not reveal a
release blocker.

Stop refining the WtS 8-b / WtS 9-m Google-witness diagnostics unless a real
inconsistency appears. The next useful work is release packaging or a separate
source-review pass for the remaining diagnostic bucket rows.

## Final Checksums

### WtS 8-b

```text
89fbf4754e5f2a16d960861c0a8b288372396716eaf3c8b359b111cab2f47fe2  wts_8_b_corrected_full.txt
974958162bc81d44e6bc017e7de754f984e1a674f7f7a946ae2e420b12ef26de  wts_8_b_changes.tsv
780d489b06159ec4d89c9922cd008a7f3075e394e53dbf4b2dbe7c6aca392a8e  wts_8_b_alternate_witness_adoptions.tsv
aae222f8815f6ae0efe25da58f38570af3ac3a2bd145e62701f8bf65dd845da8  wts_8_b_alternate_witness_unresolved.tsv
0217906680d9ec356760537214f73fbaba81bc8c09eea78a9f3ed9b8201293b9  bucket_report.unresolved_pairs.tsv
1f3a8e382bdd369a6bfe3b4546fa6509343da87a319b40f53a090ca672b22467  bucket_report.artifact_tokens.tsv
dadb790feb449e51075c34871150683b5e76386ea0c3c372e88d297a13ac75ec  bucket_report.summary.md
```

### WtS 9-m

```text
0c72843d09fd40148965822729e7a2f97090bc94d733427db87636d5dfdb6b7f  wts_9_m_corrected_full.txt
4636d2d599a0b238a01a5f8e65affde75e87a557283082fd90c5006ca96fad43  wts_9_m_changes.tsv
a05615c3629941273f22b16c1d2a5c9d7a93b31074e8c34a50093ca87d8fc931  wts_9_m_alternate_witness_adoptions.tsv
636f9311b87e1eade713c7e5c997b15a542f375cd9cbf9635d8372184eae6071  wts_9_m_alternate_witness_unresolved.tsv
c39193c9e69d3dff9cfb548a94277e5d9df2b97c9e41bd0a7e74fc5f0e173fa6  bucket_report.unresolved_pairs.tsv
ad149ea3e2201841b82da6efe9b2c958d26443b16bef7e3d17a012e348dd1699  bucket_report.artifact_tokens.tsv
8af60709724a986f1cbe6e549cf62ea62f86ac9017582c5fb0fcad0f2942165c  bucket_report.summary.md
```
