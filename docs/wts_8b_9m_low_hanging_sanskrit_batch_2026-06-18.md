# WtS 8-b / WtS 9-m Low-Hanging Sanskrit Batch

Date: 2026-06-18

Baseline output root:

- `work/postprocess_wts8b_9m_current_main_20260618T080923Z`

Batch output root:

- `work/postprocess_wts8b_9m_low_hanging_sanskrit_casefix_20260618T091506Z`

The `work/` outputs are local verification artifacts and are not versioned in the repository.

## Scope

This pass adds exact promoted Sanskrit overrides for low-hanging WtS 8-b and WtS 9-m candidates already visible in the Sanskrit review queues. It does not loosen Google Vision adoption gates, does not use validator-only residue as correction evidence, and does not add broad rules such as `ä -> ā`, `jn -> jñ`, `Sata -> Śata`, or damaged-sūtra repair.

The promoted override loader was also made case-aware:

- exact promoted override rows preserve the target spelling exactly;
- folded fallback remains available only for simple all-lower, all-upper, or titlecase source tokens;
- ambiguous or internally cased source tokens are not folded into a broad case fallback.

This prevents exact lowercase Sanskrit forms such as `prajnāpāramitāsūtra` from being reshaped to titlecase when they occur inside a compound or bracketed title.

## Verification

Commands run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py
python3 -m pytest tests/test_postprocess_regressions.py -q
```

Result:

- `py_compile` completed with no errors.
- `99 passed in 0.98s`

## Metrics

### WtS 8-b

| Metric | Baseline | Batch |
|---|---:|---:|
| Alternate-witness adoptions | 3 | 3 |
| Alternate-witness unresolved | 900 | 900 |
| Tier A applied | 2418 | 2440 |
| Tier B suggestions | 24 | 3 |
| Sanskrit changes | 25 | 47 |
| Sanskrit review suggestions | 22 | 1 |
| Watchdog rows | 31 | 31 |
| Review queue rows | 24 | 3 |
| Bucket report promote pairs | 0 | 0 |

### WtS 9-m

| Metric | Baseline | Batch |
|---|---:|---:|
| Alternate-witness adoptions | 851 | 851 |
| Alternate-witness unresolved | 1135 | 1135 |
| Tier A applied | 1663 | 1676 |
| Tier B suggestions | 16 | 3 |
| Sanskrit changes | 28 | 41 |
| Sanskrit review suggestions | 14 | 1 |
| Watchdog rows | 16 | 16 |
| Review queue rows | 16 | 3 |
| Bucket report promote pairs | 0 | 0 |

The batch changes 35 corrected-text lines: 22 in WtS 8-b and 13 in WtS 9-m. Adoption, unresolved, watchdog, and bucket-promote counts did not change.

## Corrected-Text Diff Audit

### WtS 8-b

| Line | Before | After |
|---:|---|---|
| 56 | `(Madhyamaka, Prajnāpāramitā, Vinaya, Abhidharma und Pramäna) und zahlreiche,` | `(Madhyamaka, Prajñāpāramitā, Vinaya, Abhidharma und Pramäna) und zahlreiche,` |
| 2806 | `'Dab ms. L) pa = sarvajnatāpragbhārab "der` | `'Dab ms. L) pa = sarvajñatāpragbhārab "der` |
| 5650 | `me) zer "der Scher Vaiśvänara, dessen Sohn` | `me) zer "der Scher Vaiśvānara, dessen Sohn` |
| 13102 | `śrävaka, eines Pratyekabuddha und eines un-` | `śrāvaka, eines Pratyekabuddha und eines un-` |
| 13887 | `Dichters śäntideva, skt. Bodhisattvacaryaāva-` | `Dichters śāntideva, skt. Bodhisattvacaryaāva-` |
| 15661 | `"für den śrävaka gibt es acht [Stufen]: die` | `"für den śrāvaka gibt es acht [Stufen]: die` |
| 19271 | `les aus der Prajnāpāramitā zitiert ist" (Nel` | `les aus der Prajñāpāramitā zitiert ist" (Nel` |
| 19419 | `send [Strophen umfassende] Prajnāpāramitā` | `send [Strophen umfassende] Prajñāpāramitā` |
| 29000 | `pa'i stobs = indriyaparāparajnānabalam "die` | `pa'i stobs = indriyaparāparajñānabalam "die` |
| 30032 | `pa'! - "weil er [die Lehrgebiete] Prajnāpāra-` | `pa'! - "weil er [die Lehrgebiete] Prajñāpāra-` |
| 31547 | `śväsayema "wir wollen die entmutigten Le-` | `śvāsayema "wir wollen die entmutigten Le-` |
| 35480 | `ms. L) pa = sarvajnatāprāgbhārab "der All-` | `ms. L) pa = sarvajñatāprāgbhārab "der All-` |
| 36494 | `emplare der [Prajnāpāramitā in] hunderttau-` | `emplare der [Prajñāpāramitā in] hunderttau-` |
| 36500 | `phen umfassende] Prajnāpāramitā abschrei-` | `phen umfassende] Prajñāpāramitā abschrei-` |
| 36505 | `Satasāhasrikāprajnāpāramitā-Lesung bereit-` | `Śatasāhasrikāprajñāpāramitā-Lesung bereit-` |
| 36509 | `Prajnāpāramitāsūtra, das der Vater für Glin` | `Prajñāpāramitāsūtra, das der Vater für Glin` |
| 36575 | `Satasāhasrikāprajnāpāramitāsātra.` | `Śatasāhasrikāprajñāpāramitāsūtra.` |
| 36577 | `Prajnāpāramitāsūtra" (Debm 546); ne` | `Prajñāpāramitāsūtra" (Debm 546); ne` |
| 36580 | `Hunderttausender-Prajnāpāramitāsūrtra, die` | `Hunderttausender-Prajñāpāramitāsūtra, die` |
| 40618 | `Acavimśatikasahasrikä[prajnāpāramitāsūtra]` | `Acavimśatikasahasrikä[prajñāpāramitāsūtra]` |
| 41781 | `ni sprin sgra'o "im Prajnaptisāstra heist es:` | `ni sprin sgra'o "im Prajñaptisāstra heist es:` |
| 46023 | `'dodla "wenn er diese Prajnāpāramitā geben` | `'dodla "wenn er diese Prajñāpāramitā geben` |

### WtS 9-m

| Line | Before | After |
|---:|---|---|
| 4931 | `in [das Fahrzeug] der śrävakas eingetreten` | `in [das Fahrzeug] der śrāvakas eingetreten` |
| 5668 | `tras, Upadesas, Śästras usw." (Nigu 41,3);` | `tras, Upadesas, Śāstras usw." (Nigu 41,3);` |
| 5679 | `le Leseermächtigungen von śästras [zusam-` | `le Leseermächtigungen von śāstras [zusam-` |
| 6365 | `nas "in der Stadt śrävasti im Lande Kosa-` | `nas "in der Stadt śrāvasti im Lande Kosa-` |
| 8842 | `dam -'am mi snan ba = na prajnāyate "wird` | `dam -'am mi snan ba = na prajñāyate "wird` |
| 10626 | `es im Prajnapāramitāsiitra, es seien Kopf-` | `es im Prajñāpāramitāsūtra, es seien Kopf-` |
| 12209 | `rvijnānadhātub "der Bereich des Schbewußt-` | `rvijñānadhātub "der Bereich des Schbewußt-` |
| 15744 | `anantäparyantab "ohne Ende und Umgren-` | `anantāparyantab "ohne Ende und Umgren-` |
| 17232 | `11. npr. der Feuergott Vaiśvänara.` | `11. npr. der Feuergott Vaiśvānara.` |
| 21617 | `"Sum-pa Jnānagarbha erbaute den Mon-ir.-` | `"Sum-pa Jñānagarbha erbaute den Mon-ir.-` |
| 24882 | `Stufen im Fahrzeug der śräva-` | `Stufen im Fahrzeug der śrāva-` |
| 25966 | `pbhyir = buddhajnanāadhyalambanatāyii "da-` | `pbhyir = buddhajñanāadhyalambanatāyii "da-` |
| 33055 | `par bya ba = vādavidhijnena bhavitavyani "es` | `par bya ba = vādavidhijñena bhavitavyani "es` |

## Checksums

### WtS 8-b

| Artifact | SHA-256 |
|---|---|
| corrected_full | `c07ce1fe95a04e36541c779b1356594b700710f4aeb1b8b2708f84e85983f82c` |
| changes | `bf57806fd12f7d4ca4dd4ff409556e02dce491382dd675e88849f3e387ac9628` |
| alternate_witness_adoptions | `780d489b06159ec4d89c9922cd008a7f3075e394e53dbf4b2dbe7c6aca392a8e` |
| alternate_witness_unresolved | `aae222f8815f6ae0efe25da58f38570af3ac3a2bd145e62701f8bf65dd845da8` |
| watchdog | `f1aff5e4bb29b980eb3ece1644fbb86f7d1188aed20ed0bf42515a295bc48cfd` |
| review_queue | `9b9108034d30df29cdbf5eecdfb76ebe112cb09882f388b55052e961767bdd6a` |

### WtS 9-m

| Artifact | SHA-256 |
|---|---|
| corrected_full | `590e5a545a8445d3eb2a4dfe380a5b47c74cdefc6c1b35223e842429c4b022c6` |
| changes | `7998bd41a13441bc41d0f14d421de85dba3cf2a18165137fec7fa8847368b589` |
| alternate_witness_adoptions | `e404266001740850f4db9e4500b3c68a1f1b5755ad0bcbfa3488e322f0b8831f` |
| alternate_witness_unresolved | `636f9311b87e1eade713c7e5c997b15a542f375cd9cbf9635d8372184eae6071` |
| watchdog | `f729eefba21530870247107a40a712610f568807de999cc7390bb21095e1749c` |
| review_queue | `502a19e723b2e536cc6b25accd65731deac06c256b696538993783d696411f2a` |

## Remaining Queue

The post-batch review queues are intentionally small:

- WtS 8-b: 3 review queue rows, 1 Sanskrit review suggestion.
- WtS 9-m: 3 review queue rows, 1 Sanskrit review suggestion.
- Both bucket reports still have 0 promote pairs.

The remaining rows should be handled by source/context review, not by broad normalization rules.
