# WtS 9-m Recovered Fallback Audit

Date: 2026-06-13

## Scope

This note is a follow-up audit of `WtS 9-m` in the local QA bundle:

`work/postprocess_new_volumes_google_qa_20260613T013443Z/wts_9_m`

No OCR correction heuristics were added or changed. Google Vision remains an
alternate witness only, and the base OCR remains authoritative.

## Counts Checked

| Metric | Count |
| --- | ---: |
| Alternate-witness adoptions | 857 |
| Alternate-witness unresolved rows | 1131 |
| Watchdog rows | 16 |
| Sanskrit changes | 28 |
| Sanskrit review suggestions | 14 |

Adoption attribution:

| Attribution | Count |
| --- | ---: |
| `recovered_rewrapped_fallback` | 829 |
| `rewrapped_page_alignment` | 28 |

Resynchronization attribution:

| Attribution | Count |
| --- | ---: |
| `direct_recovered_rewrapped_fallback` | 829 |
| `direct_page_alignment` | 28 |

Top adoption reasons:

| Reason | Count |
| --- | ---: |
| `alternate_witness_google_loc_nasal_upgrade` | 426 |
| `alternate_witness_initial_i_to_l_translit` | 238 |
| `alternate_witness_google_loc_fricative_upgrade` | 98 |
| `alternate_witness_citation_siglum` | 66 |
| `alternate_witness_google_loc_velar_nasal_upgrade` | 21 |
| `alternate_witness_hyphenated_initial_i_to_l_translit` | 5 |
| `alternate_witness_citation_cleanup` | 2 |
| `alternate_witness_strict_translit` | 1 |

Highest-density adoption pages remain moderate:

| Page | Adoptions |
| ---: | ---: |
| 126 | 11 |
| 268 | 11 |
| 272 | 11 |
| 326 | 11 |
| 187 | 10 |
| 58 | 9 |
| 68 | 9 |
| 79 | 9 |

## Sample Reviewed

A deterministic sample of 107 adoption rows was inspected, covering:

- 20 nasal-upgrade rows
- 15 initial `I` to `l` transliteration rows
- 10 fricative-upgrade rows
- 10 citation/siglum rows
- 5 velar-nasal rows
- all adoption reasons with fewer than 10 rows
- sample rows from the highest-density pages listed above

The sampled rows were token-level changes under the existing gates. The sample
did not show raw Google line replacement or a runaway page-scale rewrite.

## Findings

The recovered-fallback class is high-volume for this volume, but the sampled
rows are consistent with the expected conservative token-level adoption
patterns: Tibetan nasal upgrades, initial `I` to `l` in Wylie-like context,
fricative upgrades, and citation/siglum cleanup.

Citation/siglum rows remain policy-sensitive diagnostics. They should not be
used as evidence for a broader Sanskrit or Tibetan correction rule.

One sampled adoption row, page 196 line 64, records `gan -> gañ` in the
alternate-witness adoption TSV. The final corrected text was checked separately
and does not contain `gañ dag`; it contains `gaṅ dag` on the corresponding
line. This is a useful reminder that adoption TSV rows are intermediate
token-level diagnostics and final corrected text must be checked before judging
the release output.

Other source-sensitive examples in the sample, such as `gNa-khri -> gÑa-khri`
and `dnos -> dños`, did not show a systematic hazard, but they should still be
treated as source-review material rather than evidence for new broad rules.

## Decision

The WtS 9-m recovered-fallback adoptions are acceptable as diagnostics for this
QA bundle. No new correction rule should be promoted from this audit alone.

The next useful work is release-readiness documentation and any targeted
source-image review of policy-sensitive rows, not another broad correction
mining pass.
