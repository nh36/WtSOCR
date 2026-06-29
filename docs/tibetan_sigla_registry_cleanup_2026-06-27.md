> Historical audit record. This file is not the current to-do list. See `docs/STATUS.md` for the current operational status.

# Tibetan Sigla Registry Cleanup

Date: 2026-06-27

This pass promotes exact, reviewed citation-siglum normalisations in WtS 8-b
and WtS 9-m. It does not add a generic `$` to `ś` rule, does not broaden
Google Vision adoption gates, and does not use validator-only residue as
correction evidence.

`work/` outputs are local artifacts and are not versioned in the repository.

## Inputs And Outputs

- Baseline: `work/tibetan_bzhin_bzhugs_batch_20260626T090121Z`
- Final run: `work/tibetan_sigla_registry_cleanup_20260627T000000Z`
- Override reason: `reviewed_siglum_exact_registry_canonicalization`
- Evidence tag: `tibetan_sigla_registry_cleanup_20260627`

## Promoted Rows

| Volume | Source token | Target token | Rows |
| --- | --- | --- | ---: |
| WtS 8-b | `Bu-Sz` | `Bu-śz` | 13 |
| WtS 8-b | `Lis` | `Liś` | 6 |
| WtS 8-b | `Lsdz-K` | `Lśdz-K` | 3 |
| WtS 8-b | `Ys` | `Yś` | 3 |
| WtS 8-b | `Sambh` | `Śambh` | 1 |
| WtS 8-b | `Bu-S` | `Bu-śz` | 1 |
| WtS 9-m | `Lsdz-K` | `Lśdz-K` | 3 |
| WtS 9-m | `Lis` | `Liś` | 3 |
| WtS 9-m | `Bu-Sz` | `Bu-śz` | 2 |
| WtS 9-m | `Gs-H` | `Gś-H` | 2 |
| WtS 9-m | `GS-H` | `Gś-H` | 1 |
| WtS 9-m | `Bu-$z` | `Bu-śz` | 1 |
| **Total** |  |  | **39** |

All 39 changes are exact row/token overrides in citation-siglum contexts. The
`Bu-S` row is treated as a clipped instance of the same `Bu-śz` siglum family;
it is still row-gated and does not create a broader clipping rule.

## Corrected-Text Audit

Corrected text changed lines:

- WtS 8-b: 27
- WtS 9-m: 12
- Total: 39

Representative changed lines:

| Volume | Line | Before | After |
| --- | ---: | --- | --- |
| WtS 8-b | 567 | `ba dan" (Lis` | `ba dan" (Liś` |
| WtS 8-b | 3417 | `dBus-gtsañ mit den vier Hörnern" (Sambh` | `dBus-gtsañ mit den vier Hörnern" (Śambh` |
| WtS 8-b | 6228 | `hat noch keinen Zahn" (Bu-Sz` | `hat noch keinen Zahn" (Bu-śz` |
| WtS 8-b | 9608 | `der Mantras und des Geistes" (Lsdz-K` | `der Mantras und des Geistes" (Lśdz-K` |
| WtS 8-b | 31615 | `Atemnot und Hämorrhoiden" (Ys` | `Atemnot und Hämorrhoiden" (Yś` |
| WtS 8-b | 31961 | `Atiśa ging allmählich nach dBus" (Bu-S;` | `Atiśa ging allmählich nach dBus" (Bu-śz;` |
| WtS 9-m | 1892 | `nicht zu unterscheiden" (GS-H` | `nicht zu unterscheiden" (Gś-H` |
| WtS 9-m | 20525 | `Lsdz-K` | `Lśdz-K` |
| WtS 9-m | 23118 | `vergeht schnell" (Gs-H` | `vergeht schnell" (Gś-H` |
| WtS 9-m | 26431 | `sei er ein Gott" (Bu-$z` | `sei er ein Gott" (Bu-śz` |
| WtS 9-m | 28406 | `blun po (Lis` | `blun po (Liś` |

The full corrected-text diff contains only the 39 isolated siglum
normalisations listed above by family. Punctuation and spacing remain
unchanged around the edited tokens.

## Guardrail Counts

| Volume | Metric | Baseline | Final |
| --- | --- | ---: | ---: |
| WtS 8-b | alternate witness adoptions | 3 | 3 |
| WtS 8-b | alternate witness unresolved | 900 | 900 |
| WtS 8-b | reviewed Tibetan exact changes | 143 | 170 |
| WtS 8-b | Sanskrit changes | 72 | 72 |
| WtS 8-b | Sanskrit review suggestions | 8 | 8 |
| WtS 8-b | tier B suggestions | 10 | 10 |
| WtS 8-b | validator issues | 2344 | 2344 |
| WtS 8-b | citation-name changes | 459 | 459 |
| WtS 8-b | changes TSV rows | 2693 | 2720 |
| WtS 8-b | watchdog rows | 34 | 34 |
| WtS 8-b | review queue rows | 10 | 10 |
| WtS 8-b | unresolved bucket pairs | 125 | 125 |
| WtS 8-b | bucket promote rows | 0 | 0 |
| WtS 9-m | alternate witness adoptions | 842 | 842 |
| WtS 9-m | alternate witness unresolved | 1134 | 1134 |
| WtS 9-m | reviewed Tibetan exact changes | 262 | 274 |
| WtS 9-m | Sanskrit changes | 89 | 89 |
| WtS 9-m | Sanskrit review suggestions | 10 | 10 |
| WtS 9-m | tier B suggestions | 12 | 12 |
| WtS 9-m | validator issues | 1554 | 1554 |
| WtS 9-m | citation-name changes | 276 | 276 |
| WtS 9-m | changes TSV rows | 1951 | 1963 |
| WtS 9-m | watchdog rows | 16 | 16 |
| WtS 9-m | review queue rows | 12 | 12 |
| WtS 9-m | unresolved bucket pairs | 38 | 38 |
| WtS 9-m | bucket promote rows | 0 | 0 |

Alternate-witness adoption and unresolved counts are unchanged. The only
intended count movement is the 39-row increase in reviewed Tibetan exact
changes and changes TSV rows.

## Diagnostic Counts

| Volume | Diagnostic file | Baseline rows | Final rows |
| --- | --- | ---: | ---: |
| WtS 8-b | `tibetan_variant_families.tsv` | 28 | 23 |
| WtS 8-b | `tibetan_orthography_damage_candidates.tsv` | 151 | 151 |
| WtS 8-b | `tibetan_google_candidate_readings.tsv` | 12 | 12 |
| WtS 8-b | `tibetan_google_adoption_patterns.tsv` | 3 | 3 |
| WtS 8-b | `sigla_variant_candidates.tsv` | 84 | 57 |
| WtS 8-b | `residual_sanskrit_low_confidence_candidates.tsv` | 235 | 239 |
| WtS 9-m | `tibetan_variant_families.tsv` | 85 | 85 |
| WtS 9-m | `tibetan_orthography_damage_candidates.tsv` | 123 | 123 |
| WtS 9-m | `tibetan_google_candidate_readings.tsv` | 90 | 90 |
| WtS 9-m | `tibetan_google_adoption_patterns.tsv` | 239 | 239 |
| WtS 9-m | `sigla_variant_candidates.tsv` | 126 | 114 |
| WtS 9-m | `residual_sanskrit_low_confidence_candidates.tsv` | 233 | 233 |

The WtS 8-b residual Sanskrit low-confidence increase is a diagnostic backstop
artifact from newly normalised `ś`-bearing sigla. It is not a Sanskrit
correction queue and did not drive this batch.

## Deferred Sigla-Like Cases

The following remain deliberately out of scope:

- `rol -> Rol`, `ins -> Ins`, and `gs -> Gs`: mixed ordinary prose/citation
  noise, not a clear siglum normalisation family.
- Lowercase `gzi -> gZi` and lowercase `lis -> Liś`: can be ordinary lexical
  text unless the local row is clearly a citation siglum.
- `LIS -> Liś`: deferred in `AA_LIS_LY`-style contexts because those are not
  normal citation contexts.
- `P$`, `MS$`, `As$vins`, `b$ad`, `Viś -> Vis`, `Vi$ -> Vis`, `ISK`, `Inl2`,
  and similar rows: not registry-backed clear citation-siglum repairs in this
  pass.

These deferrals preserve the policy distinction between exact reviewed siglum
canonicalisation and generic `$`/`s`/capitalisation repair.

## Checksums

| Volume | File | SHA-256 |
| --- | --- | --- |
| WtS 8-b | corrected full text | `970f114777bdf6d40beb1be6b66b6a40240089001b9c9fbcdd814994e86a95e7` |
| WtS 8-b | changes TSV | `042714db4aa42a6e0ec9d390405959365659b7d1ae6ae39a03b4625bb5a474d5` |
| WtS 8-b | watchdog TSV | `2b04067f976caa4d551f64ec795fd5963f75f53f4c6146c5c1a452dd2b00cac6` |
| WtS 8-b | review queue TSV | `d19f785f7a3eff22059ba0ca7d49cad276e8cdb5e7dd31034415fa7b22357d1f` |
| WtS 9-m | corrected full text | `dee67f2f3b294434bf5b7a341ead79d630b20e65e647aa4c53ec770d8a172b1f` |
| WtS 9-m | changes TSV | `7b9f02ec33fc56f897397c86eb455d8b9ea1ea1bc6cd3a7b83de66315b63910a` |
| WtS 9-m | watchdog TSV | `f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c` |
| WtS 9-m | review queue TSV | `f3597df34a75790a0c7c448ae7c03288fc5e16926094a57cd4a58c5568e0b10b` |

## Verification

Commands:

```sh
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_tibetan_cleanup_diagnostics.py scripts/report_unresolved_buckets.py scripts/build_qa_packet_v6.py
python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q
```

Result:

```text
139 passed, 6 subtests passed
```
