# Residual Error Family Follow-Up Audit, 2026-06-25

## Scope

This pass audits the promoted and deferred families from
`docs/residual_error_family_research_2026-06-24.md`. The main unresolved items
were embedded Tibetan `'di lta bu...` damage and broader `Samsära` / `Samsāra` /
`Saṃsāra` normalisation.

No broad OCR rules were added. All actioned rows are exact source-token
normalisations under the existing reviewed override machinery.

## Prior Promotions Re-Audited

The June 24 Tibetan rows remain appropriate as exact row-gated repairs:
`dagkyań -> dag kyaṅ` and the three simple `'dilta -> 'di lta` rows are local
Tibetan spacing/orthography repairs and still do not imply broad spacing or
`ń -> ṅ` rules.

The June 24 Sanskrit rows also remain appropriate as exact Sanskrit
proper-name/term repairs: `Säkyamuni`, `Śäkyamuni`, `Säkyamunis`,
`Säkyamunii`, `Nirväna`, and `Nirväru`. The lowercase German/prose `ins` siglum
guard remains a guardrail rather than a broader siglum-policy change.

## Embedded `di lta bu` Rows

The following rows were actioned as exact Tibetan spacing/segmentation repairs.

| ref | source token | target | decision |
| --- | --- | --- | --- |
| `wts_8_b:117:77` | `kyis'diltabuga` | `kyis 'di lta bu ga` | promote |
| `wts_8_b:288:17` | `diltabuszinna` | `di lta bu źin na` | promote |
| `wts_8_b:510:62` | `diltabi` | `di lta bu'i` | promote |

The first token includes the preceding `kyis'` in the tokenizer span. In the
latter two rows, the leading apostrophe is outside the token span and is
preserved by replacing only `diltabuszinna` and `diltabi`.

No broad `diltabu` or apostrophe-spacing rule was added.

## `Saṃsāra` Rows

The following damaged Sanskrit term spellings were promoted to `Saṃsāra` in
clear Buddhist/Sanskrit context.

| example ref | source token | target | decision |
| --- | --- | --- | --- |
| `wts_8_b:96:78` | `Samsära` | `Saṃsāra` | promote |
| `wts_9_m:47:43` | `Sarnsära` | `Saṃsāra` | promote |
| `wts_9_m:10:56` | `Sanisära` | `Saṃsāra` | promote |
| `wts_9_m:121:55` | `Samisära` | `Saṃsāra` | promote |
| `wts_9_m:233:60` | `Samsara` | `Saṃsāra` | promote |
| `policy:samsara_20260625` | `Samsāra` | `Saṃsāra` | promote |

These are exact Sanskrit overrides tagged with
`residual_deferred_family_audit_20260625` or
`samsara_samskara_policy_audit_20260625`, plus `samsara_context`.

Readable `Samsara` and `Samsāra` are now treated as normalisation candidates
when the line context identifies the word as the Buddhist Sanskrit technical
term. They are still not handled by broad character rules.

## `Saṃskāra` And German-Spacing Rows

The earlier deferrals for `Samskäras` and `desSamsära` were reviewed as exact
rows rather than folded into the `Saṃsāra` family.

| example ref | source token | target | decision |
| --- | --- | --- | --- |
| `wts_8_b:240:18` | `Samskäras` | `Saṃskāras` | promote |
| `wts_8_b:296:38` | `desSamsära` | `des Saṃsāra` | promote |

`Samskäras` belongs to the separate `Saṃskāra` family, and `desSamsära`
combines German spacing with Sanskrit term normalisation. Both are now exact
reviewed overrides with Buddhist/Sanskrit term context gating.

## Remaining Non-Actions

The following remain deliberately unactioned:

- Any broad `ä -> ā`, `rn/ni/mi -> ṃ`, or embedded-Tibetan splitting rule.
- Generic `Sams*` normalisation outside an exact reviewed source token.
- Related compounds or nonce forms such as `Samsärafest`, `Samsarafest`,
  `Samskärasfest`, and `desSamsärafest`, unless they are separately reviewed.
- Any broader editorial Sanskrit spelling policy not represented by exact
  reviewed override rows.

## Verification

Commands:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py
python3 -m pytest tests/test_postprocess_regressions.py -q
```

Result: `118 passed`.
