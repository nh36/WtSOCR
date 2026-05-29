# Sanskrit Large Batch Postcheck 2026-05-29

This is an independent sanity check of the 45 corrected-text line changes from the previous large Sanskrit batch. The check compared the before/after corrected text, local line context, Google/review-queue evidence where available, and Sanskrit/Buddhist title or term context. Source images were not re-opened in this pass.

## Result

| classification | changed lines |
| --- | ---: |
| clearly good | 38 |
| probably good | 7 |
| questionable | 0 |
| bad | 0 |

All 45 changed corrected-text lines were classified as clearly or probably good. No line was found to require reversal.

## Higher-Risk Rows Checked

| ref | change | classification | note |
| --- | --- | --- | --- |
| wts_35_51:40:57 | `rakab` -> `rakaḥ` | probably good | Sanskrit/Mvy-style context supports final visarga; source image not rechecked. |
| wts_9_m:198:32 | `tamab` -> `tamaḥ` | probably good | Lexical/Mvy context supports the term; source image not rechecked. |
| wts_35_51:177:28 | `smasäna` -> `śmaśāna` | clearly good | Buddhist/Sanskrit context supports standard `śmaśāna`; nearby line remains mixed but the promoted token is sound. |
| wts_35_51:177:74 | `samnipätab` -> `samnipātaḥ` | probably good | Mvy/lexical context supports macron and final visarga; source image not rechecked. |
| wts_9_m:233:88 | `apadal` -> `apadaḥ` | probably good | Mvy/lexical context supports final visarga; source image not rechecked. |
| wts_35_51:244:56 | `sarvatathāgatavajrābhisckajniā` -> `sarvatathāgatavajrābhisckajñiā` | clearly good partial improvement | The `jñ` repair is justified, but the token remains otherwise damaged and should stay reviewable. |
| wts_9_m:305:19 | `buddhajnanāadhyalambanatāyii` -> `buddhajñanāadhyalambanatāyii` | clearly good partial improvement | The `jñ` repair is justified, but the token remains otherwise damaged and should stay reviewable. |

## Conclusion

The large batch did not introduce any identified bad Sanskrit normalisations. The mixed language-knowledge rows remain acceptable as exact, context-gated improvements, with the caveat that several are only partial repairs and should not be treated as fully normalized Sanskrit.
