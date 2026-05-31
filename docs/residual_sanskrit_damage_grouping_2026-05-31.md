# Residual Sanskrit Damage Grouping, 2026-05-31

Production directory:
`work/production_release_candidate_residual_sanskrit_cleanup_20260529T100325Z`

This pass changed QA reporting only. It did not change corrected text,
Sanskrit overrides, postprocess behavior, or Google Vision adoption gates.
Validator-only residue was not used as correction evidence.

## New grouped outputs

The raw residual diagnostic remains available as
`residual_sanskrit_damage_candidates.tsv`. Three grouped/ranked outputs were
added to make that raw file reviewable:

| output | rows | purpose |
| --- | ---: | --- |
| `residual_sanskrit_damage_candidates.tsv` | 29,830 | raw diagnostic rows |
| `residual_sanskrit_damage_families.tsv` | 5,708 | deduplicated token/family groups |
| `residual_sanskrit_damage_top_candidates.tsv` | 250 | ranked review slice |
| `residual_sanskrit_damage_summary.md` | n/a | Markdown summary and top groups |

The family ledger is intentionally broader than the top-candidate file. The
top-candidate file is the practical review queue; the full family ledger
preserves the grouped evidence for follow-up queries.

## Grouping Summary

| metric | count |
| --- | ---: |
| raw residual rows | 29,830 |
| grouped families | 5,708 |
| top candidate rows written | 250 |
| groups marked review | 24 |
| groups marked reject | 5,684 |

Reason-family counts:

| reason_family | grouped families |
| --- | ---: |
| `umlaut_macron` | 2,712 |
| `final_visarga` | 2,263 |
| `title_family` | 212 |
| `mixed_or_uncertain` | 181 |
| `proper_name` | 153 |
| `dollar_ś` | 145 |
| `sūtra_damage` | 30 |
| `jn_jñ` | 12 |

## Top-Candidate Inspection

I inspected the top 50 grouped candidates after the ranking change.

The highest-volume review groups are not safe automatic promotions:

| group | reason for no promotion |
| --- | --- |
| `VisT -> VisṬ` | high-volume siglum/bibliographic case; needs source-image or policy review |
| `Käsy/Käśy -> Kāśy` | high-volume Sanskrit-family case, but still listed for source-image review |
| `Tär` | likely bibliographic/name residue; no exact reviewed target in this pass |
| `Näga`, `Mära`, `Srävakas`, `Mahävyutpatti` | already have exact-family handling where safe; remaining contexts need review |
| `säin`, `dnul`, `Kävyäd`, `Räg`, `nl` | mixed/noisy contexts or no proposed target |

The remaining review groups include the already-deferred source-review queue:

| from_token | proposed target |
| --- | --- |
| `Aryaratnakäta` | `Āryaratnakūṭa` |
| `dnantaryamärgab` | `ānantaryamārgaḥ` |
| `jnaurasab` | `jinaurasaḥ` |
| `śinaväsika` | `Śāṇavāsika` |
| `śosa-räpasya` | `śoṣa-rūpasya` |
| `śrijhäna` | `śrījñāna` |
| `ucchanganäam` | `ucchanganāam` |
| `Käsy/Käśy` | `Kāśy` |
| `VisT/VisṬ` | source/policy decision needed |

Starting around rank 25, the ranked file is dominated by low-confidence
diagnostic residue such as German abbreviations, Tibetan/Wylie-like tokens,
or tokens without a proposed target. These are now marked `reject` instead of
being presented as a correction queue.

## Guardrail Counts

The regenerated report kept the existing QA guardrail counts unchanged:

| file | rows |
| --- | ---: |
| `all_watchdog_rows.tsv` | 285 |
| `live_validator_only_residue.tsv` | 1 |
| `live_policy_or_false_positive.tsv` | 4 |
| `google_sanskrit_candidate_readings.tsv` | 39 |
| `all_sanskrit_review_suggestions.tsv` | 9 |
| `possible_missed_google_readings.tsv` | 0 |

No promotion batch was made from this pass. The grouped output made the raw
29,830-row diagnostic actionable, but the top-ranked items either require
source-image/policy review or are already covered by exact-family handling in
safe contexts.

## Verification

Commands run:

```bash
python3 -m py_compile scripts/generate_production_qa_report.py scripts/postprocess_entry_map.py
python3 -m pytest tests/test_postprocess_regressions.py
python3 scripts/generate_production_qa_report.py --output-dir work/production_release_candidate_residual_sanskrit_cleanup_20260529T100325Z
```

Results:

- `py_compile` passed.
- `tests/test_postprocess_regressions.py` passed: 116 tests.
- Production QA report regenerated successfully.
