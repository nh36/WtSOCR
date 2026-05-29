# Sanskrit Large Batch Cleanup - 2026-05-28

## Scope

This pass promotes exact Sanskrit normalisations from two reviewed sources:

- Google-supported unresolved/candidate readings that were manually checked in local context.
- Curated Sanskrit/Buddhist title, proper-name, and technical-term rows from the Sanskrit review queue.

Google Vision adoption gates were not loosened. Google remains an alternate witness, not an authority. Validator-only residue was ignored. No broad global rule was added for `jn -> jñ`, `Sata -> Śata`, `ä -> ā`, or damaged `sūtra` repair.

The decision ledger is `work/sanskrit_large_batch_decisions_20260528.tsv`.

## Promoted Rows

### Google-supported possible missed readings

These twelve rows were consumed from `possible_missed_google_readings.tsv`:

| Volume | Page | Line | Before | After | Support |
| --- | ---: | ---: | --- | --- | --- |
| WtS 1-34 | 17 | 24 | Dharmakirti | Dharmakīrti | Google unresolved proper-name evidence |
| WtS 35-51 | 18 | 73 | Srävakas | Śrāvakas | Google unresolved Buddhist term evidence |
| WtS 35-51 | 73 | 20 | saptotsadah | saptotsadaḥ | Google unresolved Sanskrit term evidence |
| WtS 35-51 | 73 | 69 | Taksaka | Takṣaka | Google unresolved proper-name evidence |
| WtS 35-51 | 164 | 19 | sahasrikä | sāhasrikā | Google unresolved title-family evidence |
| WtS 35-51 | 177 | 8 | vrndah | vṛndaḥ | Google unresolved Sanskrit term evidence |
| WtS 35-51 | 177 | 32 | Düramgamä | Dūramgamā | Google plus title/proper-name knowledge |
| WtS 35-51 | 177 | 74 | samnipätab | samnipātaḥ | Google plus Sanskrit title/term knowledge |
| WtS 35-51 | 217 | 25 | paräkarsayati | parākarṣayati | Google unresolved Sanskrit term evidence |
| WtS 9-m | 198 | 76 | tamala | tamāla | Google unresolved Sanskrit term evidence |
| WtS 9-m | 229 | 69 | Näga | Nāga | Google unresolved proper-name evidence |
| WtS 9-m | 233 | 88 | apadal | apadaḥ | Google plus Sanskrit term knowledge |

### Additional Google Sanskrit candidates

These eleven rows were promoted from `google_sanskrit_candidate_readings.tsv` after local review:

| Volume | Page | Line | Before | After | Support |
| --- | ---: | ---: | --- | --- | --- |
| WtS 35-51 | 177 | 32 | Acalä | Acalā | Google candidate and title/proper-name context |
| WtS 35-51 | 40 | 57 | rakab | rakaḥ | Google candidate plus Sanskrit term knowledge |
| WtS 9-m | 198 | 32 | tamab | tamaḥ | Google candidate plus Sanskrit lexical context |
| WtS 9-m | 198 | 74 | tamäla | tamāla | Google candidate and Sanskrit lexical context |
| WtS 9-m | 52 | 3 | mallikä | mallikā | Google candidate and Sanskrit lexical context |
| WtS 9-m | 285 | 17 | Mära | Māra | Google candidate and Buddhist proper-name context |
| WtS 35-51 | 18 | 51 | Märas | Māras | Google candidate and Buddhist proper-name context |
| WtS 35-51 | 164 | 9 | Ahalyä | Ahalyā | Google candidate and Sanskrit proper-name context |
| WtS 35-51 | 177 | 25, 31 | meläpaka | melāpaka | Google candidate and repeated Sanskrit term context |
| WtS 35-51 | 177 | 28, 33 | upameläpaka | upamelāpaka | Google candidate and repeated Sanskrit term context |
| WtS 35-51 | 177 | 28 | smasäna | śmaśāna | Google candidate plus Sanskrit lexical knowledge |

### Review queue and curated Sanskrit rows

These nineteen rows were promoted from review-queue or known-family evidence. They are exact overrides with Sanskrit/title/proper-name context gates; they are not broad `jn -> jñ` or `ä -> ā` rules.

| Volume | Page | Line | Before | After | Support |
| --- | ---: | ---: | --- | --- | --- |
| WtS 8-b | 353 | 6 | indriyaparāparajnānabalam | indriyaparāparajñānabalam | Review queue, `bala` technical context |
| WtS 9-m | 258 | 81 | Jnānagarbha | Jñānagarbha | Review queue, proper-name context |
| WtS 1-34 | 1206 | 87 | Prajnāpā | Prajñāpā | Prajñāpāramitā family context |
| WtS 35-51; WtS 8-b | 139; 365 | 15; 27 | Prajnāpāra | Prajñāpāra | Prajñāpāramitā family context |
| WtS 9-m | 394 | 82 | vādavidhijnena | vādavidhijñena | Review queue, Sanskrit technical context |
| WtS 8-b | 42 | 62 | sarvajnatāpragbhārab | sarvajñatāpragbhārab | Review queue, Buddhist technical context |
| WtS 8-b | 431 | 40 | sarvajnatāprāgbhārab | sarvajñatāprāgbhārab | Review queue, Buddhist technical context |
| WtS 35-51 | 613 | 68 | navijnānadhātuh | navijñānadhātuh | Review queue, `dhātu` context |
| WtS 9-m | 147 | 50 | rvijnānadhātub | rvijñānadhātub | Review queue, `dhātu` context |
| WtS 1-34 | 574 | 8 | parināmanavidkijnāh | parināmanavidkijñāh | Review queue, Sanskrit ritual/technical context |
| WtS 1-34 | 128 | 148 | prabhā-mandala-vyaha-jnā | prabhā-mandala-vyaha-jñā | Review queue, Sanskrit compound context |
| WtS 8-b | 174 | 12 | śäntideva | śāntideva | Review queue, proper-name context |
| WtS 1-34; WtS 9-m | 994; 297 | 71; 64 | śräva | śrāva | Review queue, Buddhist term fragment |
| WtS 8-b | 383 | 72 | śväsayema | śvāsayema | Review queue, Sanskrit verbal form |
| WtS 9-m | 207 | 67 | Vaiśvänara | Vaiśvānara | Review queue, proper-name context |
| WtS 35-51 | 572 | 75 | ktijnānadarsanaskandhab | ktijñānadarsanaskandhab | Review queue, `skandha` technical context |
| WtS 9-m | 310 | 62 | buddhajnanāadhyalambanatāyii | buddhajñanāadhyalambanatāyii | Review queue, Buddhist technical context |
| WtS 1-34 | 997 | 45 | sarvatragäminipratipajjnanabalam | sarvatragāminipratipajjñanabalam | Review queue, `sGra`/`bala` context |
| WtS 35-51 | 244 | 48 | sarvatathāgatavajrābhisckajniā | sarvatathāgatavajrābhisckajñiā | Review queue, Buddhist title/technical context |

## Deferred Or Rejected

Rows were deferred when the suggested target was only a partial repair, still visibly damaged, or required source-image adjudication. Rows were rejected when they were German fragments, Tibetan/Wylie tokens, or too short/ambiguous as bibliographic abbreviations.

Examples:

- Rejected `dNul -> dṄul`: Tibetan/Wylie token pattern, not Sanskrit normalisation.
- Rejected `Buddhasöh -> Buddhasoh`: German word fragment.
- Rejected `Käsy -> Kāśy`: short bibliographic abbreviation requiring source review.
- Deferred `pasmasäna`, `puspavrksab`, `pratikäülasamjnä`, `anantäparyantab`, `dnantaryamärgab`, and similar rows because the proposed target remains partial or uncertain.

The full promote/defer/reject list is in `work/sanskrit_large_batch_decisions_20260528.tsv`.

## Production Run

Output directory:

`work/production_release_candidate_sanskrit_large_batch_20260528T230800Z`

Baseline directory:

`work/production_release_candidate_prajnaparamita_sutra_full_titles_20260528T081635Z`

All four production volumes were rerun with the Google alternate witness files. `google_vision_rewrites` remained `0` in every volume, and the Google adoption/unresolved counts stayed unchanged. The postprocess layer used reviewed exact overrides only.

## QA Deltas

| QA output | Before | After |
| --- | ---: | ---: |
| `possible_missed_google_readings.tsv` | 12 | 0 |
| `google_sanskrit_candidate_readings.tsv` | 65 | 40 |
| `all_sanskrit_review_suggestions.tsv` | 32 | 11 |
| `all_watchdog_rows.tsv` | 285 | 285 |
| `live_validator_only_residue.tsv` | 1 | 1 |
| `live_policy_or_false_positive.tsv` | 4 | 4 |

`google_sanskrit_candidate_readings.tsv` by action:

| Suggested action | Before | After |
| --- | ---: | ---: |
| `exact_promotion_candidate` | 12 | 0 |
| `review_only` | 6 | 3 |
| `reject` | 47 | 37 |

Sanskrit change counts by volume:

| Volume | Before | After | Delta |
| --- | ---: | ---: | ---: |
| WtS 1-34 | 298 | 304 | +6 |
| WtS 35-51 | 129 | 150 | +21 |
| WtS 8-b | 46 | 53 | +7 |
| WtS 9-m | 39 | 52 | +13 |
| Total | 512 | 559 | +47 |

Corrected text changed lines: 45.

## Corrected Text Diffs

All changed corrected-text lines were intended Sanskrit normalisations.

WtS 1-34 changed six lines:

- `Dharmakirti` -> `Dharmakīrti`
- `prabhā-mandala-vyaha-jnā` -> `prabhā-mandala-vyaha-jñā`
- `parināmanavidkijnāh` -> `parināmanavidkijñāh`
- `śräva-` -> `śrāva-`
- `sarvatragäminipratipajjnanabalam` -> `sarvatragāminipratipajjñanabalam`
- `Prajnāpā-` -> `Prajñāpā-`

WtS 35-51 changed nineteen lines, with twenty-one token normalisations:

- `Märas` -> `Māras`
- `Srävakas` -> `Śrāvakas`
- `rakab` -> `rakaḥ`
- `saptotsadah` -> `saptotsadaḥ`
- `Taksaka` -> `Takṣaka`
- `Prajnāpāra-` -> `Prajñāpāra-`
- `Ahalyä` -> `Ahalyā`
- `sahasrikä` -> `sāhasrikā`
- `vrndah` -> `vṛndaḥ`
- `meläpaka` -> `melāpaka`
- `upameläpaka` -> `upamelāpaka`
- `smasäna` -> `śmaśāna`
- `Düramgamä` -> `Dūramgamā`
- `Acalä` -> `Acalā`
- `samnipätab` -> `samnipātaḥ`
- `paräkarsayati` -> `parākarṣayati`
- `sarvatathāgatavajrābhisckajniā` -> `sarvatathāgatavajrābhisckajñiā`
- `ktijnānadarsanaskandhab` -> `ktijñānadarsanaskandhab`
- `navijnānadhātuh` -> `navijñānadhātuh`

WtS 8-b changed seven lines:

- `sarvajnatāpragbhārab` -> `sarvajñatāpragbhārab`
- `Vaiśvänara` -> `Vaiśvānara`
- `śäntideva` -> `śāntideva`
- `indriyaparāparajnānabalam` -> `indriyaparāparajñānabalam`
- `Prajnāpāra-` -> `Prajñāpāra-`
- `śväsayema` -> `śvāsayema`
- `sarvajnatāprāgbhārab` -> `sarvajñatāprāgbhārab`

WtS 9-m changed thirteen lines:

- `mallikä` -> `mallikā`
- `rvijnānadhātub` -> `rvijñānadhātub`
- `tamab` -> `tamaḥ`
- `tamäla` -> `tamāla`
- `tamala` -> `tamāla`
- `Vaiśvänara` -> `Vaiśvānara`
- `Näga` -> `Nāga`
- `apadal` -> `apadaḥ`
- `Jnānagarbha` -> `Jñānagarbha`
- `Mära` -> `Māra`
- `śräva-` -> `śrāva-`
- `buddhajnanāadhyalambanatāyii` -> `buddhajñanāadhyalambanatāyii`
- `vādavidhijnena` -> `vādavidhijñena`

## Checksums

| Volume | Baseline SHA-256 | New SHA-256 |
| --- | --- | --- |
| WtS 1-34 | `54c22c0e1ad4372ada7a96c93126fe25c5453278bb510d412bca14bc33e942da` | `403a344b76e0fa6098046a89fd412201cbce20c36802b50897a2d8ad27be4cd6` |
| WtS 35-51 | `d069d96c51b6cbf10b43fa184287d7988f0bfec51aac15b514e5d88c6e810bc5` | `876840aa6a78746c9ee26bac409f8cdf3a14d51a9d1b0fb1d55a5f33da7510d4` |
| WtS 8-b | `64a28b6393ab0d290099fb8e309470e95c35853a113610f464968df48267a0fe` | `fe8824485396840ad4b0bf659652c1ac3ed1f11f202560793c454d18c0c892ab` |
| WtS 9-m | `1ba3b1afac8dc0bcf35c7b2d9d8b2f25404a8e0a224de8f79ed99b41c92d5896` | `7d289afb84cce689e566303803ea77fe969b518b89102f4d180f45f6a07f99f7` |

## Tests

Command:

```bash
python3 -m pytest tests/test_postprocess_regressions.py
```

Result:

`116 passed in 1.18s`

The new regression coverage is table-driven and checks:

- Google-supported exact candidates promote in reviewed Sanskrit context.
- Curated Sanskrit/title/proper-name corrections promote only in Sanskrit context.
- German prose remains unchanged.
- Tibetan/Wylie-like forms remain unchanged.
- Raw `jn` does not generally become `jñ`.
- Raw `Sata` does not generally become `Śata`.
- Damaged `sūtra`-like forms are repaired only through exact title-family overrides.
- Location-gated promotions do not apply on unreviewed page/line contexts.
