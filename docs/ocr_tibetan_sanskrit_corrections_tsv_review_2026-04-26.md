# OCR Tibetan/Sanskrit TSV Review 2026-04-26

Source: `/Users/nathanhill/Downloads/wts_ocr_tibetan_sanskrit_corrections.tsv`.

## Decision rule

Treat the TSV as a review queue, not as a literal import. Some suggested targets are Wylie-style (`ng`, `ny`, `zh`, `sh`). This project now normalizes Tibetan romanization in old LoC style, so Wylie-style suggestions must be converted before implementation:

- `ng` in Tibetan syllables becomes `ṅ`.
- `ny` in Tibetan syllables becomes `ñ`.
- `zh` in Tibetan syllables becomes `ź`.
- `sh` in Tibetan syllables becomes `ś`.

## Already active in LoC form

The high-volume Tibetan dotless-i rows are already implemented in `EXPLICIT_TIER_A_REWRITES` with Tibetan-context gating. Examples:

- `kyı -> kyi`
- `kyıs -> kyis`
- `gyı -> gyi`
- `gyıs -> gyis`
- `yın -> yin`
- `cıg -> cig`
- `gcıg -> gcig`
- `zıg -> zig`
- `sıg -> sig`
- `dkyıl -> dkyil`
- `kyanı -> kyaṅ`
- `yanı -> yaṅ`
- `byanı -> byaṅ`
- `gsarı -> gsaṅ`
- `snanı -> snaṅ`
- `sarıs -> saṅs`
- `garı -> gaṅ`

The Sanskrit high-confidence rows are also already implemented as Sanskrit overrides, including `Nägärjuna -> Nāgārjuna`, `Astäpadikrtadhüpayoga -> Aṣṭapadīkṛtadhūpayoga`, `Mahämäyürividyäräjni -> Mahāmāyūrīvidyārājñī`, `Pramänakirtih -> Pramāṇakīrtiḥ`, `Mülasarvästiväda -> Mūlasarvāstivāda`, `Päramitäsamäsa -> Pāramitāsamāsa`, and `Uddänas -> Uddānas`.

## Newly promoted

- `Igarı -> lgaṅ`
- `Dhäpayoga-ratnamaälä -> Dhūpayogaratnamālā`

The TSV suggested `lgang`, but this was promoted as LoC `lgaṅ`. It is handled by the existing explicit Tibetan allowlist, so it applies only in Tibetan/transliteration contexts and is covered by a negative regression test against plain German prose.

The Sanskrit title fix is handled by the existing high-frequency Sanskrit override path, rather than by a global umlaut rule.

## Deferred

- `[¬¢¿€¥#/]{1,}` deletion is too broad; these symbols also occur in structural noise, citation separators, and page artifacts. It needs a separate structural pass with protected citation/page spans.
- Broad `nı -> ni`, `rın -> rin`, and `rı -> ri` remain too risky outside clear Tibetan contexts.
- `Mālasarvāstivāda -> Mūlasarvāstivāda` is plausible, but it is medium-confidence and should be promoted only after checking live contexts or adding a Sanskrit-span-only rule.
- Conditional Sanskrit character maps such as `ä -> ā` and `ü -> ū` remain valid only inside Sanskrit-identified spans; they must not become global replacements because German names and prose need umlauts.
