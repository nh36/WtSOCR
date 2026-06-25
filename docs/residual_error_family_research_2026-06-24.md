# Residual Error Family Research - 2026-06-24

This pass reviews four reported residual error families and promotes only exact,
reviewed corrections. It does not add broad OCR heuristics, global character
rules, or loosened Google Vision adoption.

## Promoted Tibetan Rows

| volume | page | line | source token | target token | note |
| --- | ---: | ---: | --- | --- | --- |
| WtS 8-b | 464 | 42 | `dagkyań` | `dag kyaṅ` | Exact segmentation and nasal repair in Tibetan context. |
| WtS 8-b | 510 | 63 | `dilta` | `di lta` | Printed context is `'dilta`; the tokenizer keeps the apostrophe outside the token span. |
| WtS 9-m | 36 | 50 | `dilta` | `di lta` | Simple `'di lta ste` context. |
| WtS 9-m | 190 | 74 | `dilta` | `di lta` | Simple `'di lta ste` context. |
| WtS 9-m | 333 | 58 | `dilta` | `di lta` | Simple `'di lta ste` context. |

These are row-level reviewed Tibetan overrides. They do not imply a broad
spacing rule or a broad `ń -> ṅ` rule.

## Promoted Sanskrit Rows

| source token | target token | note |
| --- | --- | --- |
| `Säkyamuni` | `Śākyamuni` | Exact Sanskrit proper-name normalization. |
| `Śäkyamuni` | `Śākyamuni` | Exact Sanskrit proper-name normalization. |
| `Säkyamunis` | `Śākyamunis` | Exact inflected proper-name normalization. |
| `Säkyamunii` | `Śākyamuni` | Exact proper-name repair in reviewed context. |
| `Nirväna` | `Nirvāṇa` | Exact Sanskrit term normalization. |
| `Nirväru` | `Nirvāṇa` | Exact Sanskrit term repair in reviewed context. |

These overrides are exact-token promotions. They do not add a general
`ä -> ā` rule or a broader Saṃsāra/Nirvāṇa-family policy.

## Siglum Guard

Lowercase German/prose `ins` is now protected from citation-siglum
normalization. Exact siglum forms such as `Ins`, and OCR siglum artifacts such
as `In$`, still normalize through the existing siglum map.

This is a guardrail change only. It does not change the canonical siglum policy
for other `$` families.

## Deferred Rows

The embedded forms `'diltabuga`, `'diltabuszinna`, and `'diltabi` were deferred
in this pass because they needed separate source/context review. That follow-up
review was completed in
`docs/residual_deferred_family_audit_2026-06-25.md`; the exact safe rows were
promoted as row-gated `di lta bu` repairs, with no broad embedded-token
splitting rule.

The broader `Samsära` / `Samsāra` / `Saṃsāra` family was also deferred here
pending a separate convention and source-context decision. The follow-up review
promoted only exact damaged `Saṃsāra` tokens in clear Buddhist/Sanskrit context.
`Samskäras`, `desSamsära`, and broader already-readable spelling policy remain
out of scope for that follow-up.

## Verification

Commands run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py
python3 -m pytest tests/test_postprocess_regressions.py -q
```

Result: `117 passed`.
