# Sigla Normalization Research (2026-03-13)

Purpose: re-check previously "high-confidence" sigla OCR families and identify the correct normalization target before applying any further substitutions.

Data sources:
- Variant families: `work/sigla_deepdiag_strict_20260313T165900Z/sigla_variant_groups.tsv`
- Context counts: `work/sigla_research_20260313/context_stats.txt`
- Context examples: `work/sigla_research_20260313/high_conf_contexts.txt`
- Corpus checked: `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt`, `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_35_51_corrected_full.txt`

## Family-by-family research

## 1) `MigTo` vs `Migto`
- Counts: `MigTo:744`, `Migto:2`
- Evidence: canonical bibliography marker `[MigTo]` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:10861`; `Migto` only appears in parenthetical citations.
- Decision: normalize `Migto -> MigTo`.
- Safety: high (global replacement acceptable).

## 2) `KunK` vs `Kunk`
- Counts: `KunK:470`, `Kunk:13`
- Evidence: canonical `[KunK]` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:17936`; `Kunk` appears in parenthetical citations only.
- Decision: normalize `Kunk -> KunK`.
- Safety: high (global replacement acceptable).

## 3) `Srkk` vs `Śrkk`
- Counts: `Srkk:284`, `Śrkk:1`
- Evidence: canonical `[Srkk]` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:17983`; singleton `Śrkk` appears as one citation form.
- Decision: normalize `Śrkk -> Srkk`.
- Safety: high in siglum/citation contexts.

## 4) `BhuKkh` vs `Bhukkh`
- Counts: `BhuKkh:185`, `Bhukkh:52`
- Evidence: canonical `[BhuKkh]` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2145`; `Bhukkh` appears as cite-form variant.
- Decision: normalize `Bhukkh -> BhuKkh`.
- Safety: high (global replacement acceptable).

## 5) `gYu` vs `g.Yu` (ambiguous)
- Counts: `gYu:148`, `g.Yu:11`
- Evidence for siglum usage: canonical `[gYu]` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:3147`; citation forms like `(g.Yu 293,17)` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:41866`.
- Evidence for non-siglum usage: lexical/title strings like `g.Yun-drun` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:19490` and `g.Yug` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_35_51_corrected_full.txt:49356`.
- Decision: do **not** globally replace `g.Yu`.
- Safe rule: only normalize in strict citation pattern, e.g. `(g.Yu <number>,<number>) -> (gYu <number>,<number>)`.
- Safety: medium with context gating; unsafe globally.

## 6) `Doll` vs `Dol1` (likely distinct)
- Counts: `Doll:114`, `Dol1:18`
- Evidence: bibliography includes `[Dol1-4]` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2958`; both `Doll` and `Dol1` appear as active citation forms.
- Decision: keep both for now; no normalization yet.
- Safety: low for replacement; likely not pure OCR noise.

## 7) `mDzodG` vs digit-noise variants
- Counts: `mDzodG:105`, `mDz0dG:9`, `mD20dG:5`
- Evidence: canonical `[mDzodG]` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2275`; variants occur in citations as `o/0/2` OCR confusions.
- Decision: normalize `mDz0dG -> mDzodG` and `mD20dG -> mDzodG`.
- Safety: high (global replacement acceptable).

## 8) `MilGb` vs `MilGB`
- Counts: `MilGb:102`, `MilGB:3`
- Evidence: canonical `[MilGb]` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:10864`; `MilGB` appears as rare citation variant.
- Decision: normalize `MilGB -> MilGb`.
- Safety: high (global replacement acceptable).

## 9) `Bhulg` vs `BhuLg` vs `Bhul.g` (partly ambiguous)
- Counts: `Bhulg:55`, `BhuLg:8`, `Bhul.g:3`
- Evidence:
  - `Bhulg` appears in abbreviation/citation usage, e.g. `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:705`, `...:2156`.
  - `BhuLg` also appears in bibliography variant lists, e.g. `.../wts_1_34_corrected_full.txt:2070` (`[BhuRkh, BhuLg]`).
  - `Bhul.g` is punctuation noise in citation contexts.
- Decision:
  - normalize `Bhul.g -> Bhulg` (safe),
  - hold `BhuLg` pending bibliography-level disambiguation (could be intentional variant token).
- Safety: mixed; only partial normalization is high-confidence now.

## 10) `SikNth` vs `śikNth`
- Counts: `SikNth:26`, `śikNth:2`
- Evidence: dominant canonical form is `SikNth`; lowercase-diacritic initial appears as rare anomaly.
- Decision: normalize `śikNth -> SikNth`.
- Safety: high in siglum/citation contexts.

## 11) `RoINS` vs `RoINs`
- Counts: `RoINS:22`, `RoINs:1`
- Evidence: `RoINS` dominates in citation flow and appears in bibliography markers (`[RoINS]` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2516`), but a second bibliography-style occurrence has `[RoINs]` (`...:167649`).
- Decision: hold for now; do not auto-normalize until facsimile check confirms which bibliography form is authoritative.
- Safety: medium (not high, due conflicting intro-like anchors).

## 12) `1SK` vs `ISK` (resolved)
- Counts in current postprocess corpus: `1SK:66`, `ISK:0`, `1ISK:0`
- Evidence: bibliography introduction uses `[1SK]` at `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2870`, for `Sa skya pa chen po Kun dga' snin po ... bSod nams rgya mtsho 1968-1969`.
- Decision: keep/normalize to `1SK`.
- Safety: high (the reverse direction now has zero support in current corpus).

## Updated proposal (post-research)

Apply now (high-confidence):
- `Migto -> MigTo`
- `Kunk -> KunK`
- `Śrkk -> Srkk`
- `Bhukkh -> BhuKkh`
- `mDz0dG -> mDzodG`
- `mD20dG -> mDzodG`
- `MilGB -> MilGb`
- `Bhul.g -> Bhulg`
- `śikNth -> SikNth`

Apply with strict context gating only:
- `(g.Yu <n>,<n>) -> (gYu <n>,<n>)`

Hold for deeper research (not safe yet):
- `Dol1` vs `Doll`
- `BhuLg` vs `Bhulg`
- `RoINs` vs `RoINS`

## Directionality Notes (Intro-anchor based)

These are the concrete "why this direction, not reverse" decisions from the current corpus.

1) `Migto -> MigTo`
- Intro anchor: `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:10860`-`10861`
  (`Lim, Shen-yu 2005 ... [MigTo]`).
- Variant evidence: `Migto` appears in citation-only contexts, e.g.
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:81219`.
- Why not reverse: only `MigTo` is introduced as bibliography siglum; `Migto` is a downstream case-collapse OCR form.

2) `Kunk -> KunK`
- Intro anchor: `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:17935`-`17936`
  (`KRETSCHMAR ... [KunK]` for the Kun-legs edition).
- Variant evidence: `Kunk` appears in citation-only contexts, e.g.
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:29829`.
- Why not reverse: bibliography form preserves internal capital segmentation; `Kunk` does not.

3) `Śrkk -> Srkk`
- Intro anchor: `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:17981`-`17983`
  (`ZIMMERMANN 1975 ... [Srkk]`).
- Variant evidence: `Śrkk` occurs as isolated citation noise, e.g.
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_35_51_corrected_full.txt:58579`.
- Why not reverse: the siglum is introduced as `Srkk`; adding `Ś` is unsupported by intro metadata.

4) `Bhukkh -> BhuKkh`
- Intro anchor: `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2145`
  (`bsTan 'dzin chos rgyal ... [BhuKkh]`, within Aris-linked Bhutan material).
- Variant evidence: `Bhukkh` appears in citation-only contexts, e.g.
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:24465`.
- Why not reverse: the bibliography introduces `BhuKkh`; `Bhukkh` is loss of internal capitalization.

5) `g.Yu` vs `gYu` (gated only)
- Intro anchor: `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:3147`
  (`Vairocana ... [gYu]`).
- Counter-evidence (non-siglum lexical forms): `g.Yun-drun` at
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:19490`,
  `g.Yug` at
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_35_51_corrected_full.txt:49356`.
- Why not reverse/globally replace: dotted forms are genuine lexical forms outside sigla; only parenthetical cite pattern is safe.

6) `mDz0dG/mD20dG -> mDzodG`
- Intro anchor: `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2275`
  (`Dran pa nam mkha' ... [mDzodG]`).
- Variant evidence: `mDz0dG` and `mD20dG` occur in citations only (e.g. `...:19894`, `...:185288`).
- Why not reverse: reverse would introduce digits into a bibliography-introduced alphabetic siglum; error shape matches OCR `o/z` vs `0/2`.

7) `MilGB -> MilGb`
- Intro anchor: `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:10864`
  (`Mi larras pa'i nam mgur ... [MilGb]`).
- Variant evidence: `MilGB` appears in citation-only contexts, e.g. `...:197732`.
- Why not reverse: bibliography anchor is `MilGb`; terminal-case flip is a typical OCR/casing artifact.

8) `śikNth -> SikNth`
- Intro anchor: `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_35_51_corrected_full.txt:34959`
  (`Nagwang Topgyal 1995 ... [SikNth]`).
- Variant evidence: `śikNth` appears only in citations, e.g. `...:97905`, `...:109537`.
- Why not reverse: only `SikNth` is introduced bibliographically.

9) `Bhul.g -> Bhulg` (but `BhuLg` held)
- Intro anchors are mixed:
  `Aris 1986 ... [BhuGr, BhuRkh, BhuLg]` at
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2068`-`2070`,
  while another Aris-linked line has `[BhuGr, Bhulg]` at `...:2156`.
- Variant evidence: `Bhul.g` appears in citation contexts, e.g.
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_35_51_corrected_full.txt:89590`.
- Why not force `BhuLg <-> Bhulg` yet: both alphabetic forms appear in intro-like contexts; only punctuation cleanup (`Bhul.g`) is clearly one-way.

10) `RoINs` vs `RoINS` (hold)
- Intro anchors conflict:
  `Kun DGA' ... [RoINS]` at
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2515`-`2516`,
  but another bibliography-style line has `[RoINs]` at `...:167649`.
- Why no auto-direction yet: unlike purely citation noise, both forms appear in intro/bibliography sections, so direction should be finalized from facsimile confirmation.

11) `Dol1` vs `Doll` (hold)
- Intro anchor: `SNELLGROVE 1967 ... [Dol1-4]` at
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2957`-`2958`.
- Counter-evidence: `Doll` is also present in siglum lists/citations (e.g. `...:792`, `...:21770`).
- Why hold: `1/l` confusion is likely, but we still need to confirm whether all `Doll` tokens are intended `Dol1` before global replacement.

12) `ISK/1ISK -> 1SK` (resolved)
- Intro anchor: `... [1SK]` at
  `work/postprocess_step123_1sk_siglum_fix_20260313T134559Z/wts_1_34_corrected_full.txt:2870`.
- Corpus status after normalization: `1SK` remains; `ISK` and `1ISK` are absent (`0` hits each).
- Why not reverse: the bibliography entry and all surviving citation usage support numeric-initial `1SK`.

## Implementation notes
- For safety, all sigla substitutions should run inside siglum-specific contexts first (bracket sigla and parenthetical cite patterns), except for digit-only confusable pairs with clear canonical anchors.
- Keep a per-rule delta log (`before_count`, `after_count`, sample lines changed) for auditability.
