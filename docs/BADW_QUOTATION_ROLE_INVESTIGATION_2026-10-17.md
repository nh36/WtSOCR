# BAdW quotation-role investigation

This report records a source review and parser diagnosis from certified
`d1bf8e2d9cd2e8b2b7f9c091b1f4db7f160c933f`. No ownership grammar, source
observation, PDF geometry threshold, or release file was changed. The seven
occurrence-level traces are in
`data/badw_forensic_structure/quotation_role_gate_trace.jsonl`; the original
packet and its hashes remain in `quotation_role_investigation.jsonl`.

## Linguistic re-evaluation

The seven citations previously grouped as
`form_substitution_with_quoted_definition_role_missing` are **textual
attestations with German translations**, not quoted scholarly definitions. The
old reason is retained as a historical diagnostic in the source packet and in
the new gate trace. The revised classifications distinguish six substitution
examples from one full-form attestation:

| Witness suffix | Printed page | Source construction | Revised classification |
| --- | ---: | --- | --- |
| `44` | 319 | `gtsug lag khaṅ brtsṛgs ~ gyi sde btsugs` + quoted German translation + `(S751 41b2)` | substitution attestation |
| `707` | 145 | `[l]ab gleṅ ~ gyi khrims gtugs` + quoted translation + `(MTH3/5/30 a2)` | substitution attestation |
| `1482` | 236 | `[su]m pa’ / mtha’ dag ~` + quoted translation + `(PT1288 2)` | substitution attestation |
| `1490` | 49 | `[lha] blo’i ~ rim bsgrub rgyu gyis` + quoted translation + `(Gesar 200,34)` | substitution attestation |
| `1780` | 372 | `[go]ṅ ’thus ~ bcas` + quoted translation + `(Wadd 135h 1)` | substitution attestation |
| `380` | 300 | `[l]am ~ gi sgrub cha …` + quoted translation + `(MTH3/5/16 17)` | substitution attestation inside sense 3 |
| `849` | 372 | `[sb]u[g] dam źu tho mgo mchan ma’i dgoṅs don ltar` + quoted translation + `(MTH3/5/16 19)` | full-form attestation, no tilde production |

The Tibetan wording, printed square-bracket substitution markers, German
quotation, line breaks, italic transitions, and citation spans are preserved in
the source packet; no OCR or punctuation was repaired. In `707`, the translation
is substantially the same as the accepted `khrims gtugs` positive. In `1482`,
`[su]m pa’ / mtha’ dag ~` parallels the accepted `mtha’ dag` positive. Both are
attestations, not definition-plus-authority constructions. The separate
`Lex.` material around `707` and `1490`, the preceding definition in `44`, and
the adjacent example material remain independent.

## Why the existing construction succeeds elsewhere

`badw_pdf_quotation_recovery.py` has two routes. If a balanced quote already
lies inside an existing canonical `example`/`Lex.` envelope, it can recover the
translation within that envelope. If no such envelope exists, it attempts to
construct a substitution example from contiguous italic runs, a `~`, the quote,
and one immediately following parenthesized citation, while requiring a
containing sense/source division and rejecting semantic-component overlaps.
The three facsimile-verified positives in
`quotation_positive_review.jsonl` establish the first route as a regression
control. The seven failures are in the second situation: the fallback must
recognize and create the example envelope before the hierarchy can attach its
citation. The final hierarchy is not rejecting an already recovered example;
quotation recovery emits no example/translation for any of these seven, so the
citation has no qualifying owner passage.

The gate trace identifies distinct causes from the actual cached projections:

- Five bracketed-initial forms (`707`, `1482`, `1490`, `1780`, and `380`) do not satisfy the fallback's exact three-run bracket pattern.
  The source runs do not align with the implementation's assumed `[`, italic
  letter, `]` boundaries. The literal form is nevertheless legible and
  independently bounded in the facsimile.
- In `1490` and `849`, italic `gto` and `mgo-mchan` terms occur inside the German
  translation. The current blanket `any(run.style != regular)` test rejects
  the quote. This is not evidence that the quote is not a translation; it is a
  typography restriction that conflates an italicized German lexical item with
  a role boundary.
- In `44`, maximal adjacent italic-run collection reaches backward into the
  preceding `skt. saṃgha.`/definition material. The existing competing-component
  guard correctly rejects that crossing. The false negative is the form-start
  reconstruction, not the overlap guard.
- In `849`, the form is a complete Tibetan phrase without a substitution tilde,
  and the guessed form span intersects a canonical definition. The no-tilde
  rejection is appropriate for the current substitution production; the case
  needs a different independently bounded ordinary-example production. The
  component-overlap rejection must remain until the start can be separated
  from the definition on source evidence.
- In `380`, the enclosing sense is present and the citation/quote are adjacent;
  the bracket-run assumption is the primary failure. The existing sense is
  not itself grounds to infer the example boundary.

The bracketed cases also show why simply removing a condition is unsafe: exact
run checks were meant to prevent truncated forms and borrowing brackets from
neighboring text. Likewise, accepting arbitrary italics inside quotes could
misclassify quoted editorial definitions or Lex glosses. Preserve both guards;
replace them only with source-span-aware productions validated on independent
positives and confusable negatives.

## Source and validation evidence

All seven original facsimiles were reviewed alongside adjacent material. Their
PDF page IDs, printed page and line data, style spans, citation spans, original
source hashes, and short source context are retained in the two JSONL packets.
The parallel `khrims gtugs` and `mtha’ dag` facsimiles are represented in the
existing three-case positive review; the 36-entry `quotation_holdout.json` and
`quotation_review.jsonl` remain unchanged and are still negative/recall
controls.

No parser rule is changed in this investigation, so there is no new candidate
grammar being certified against a newly frozen holdout. The current evidence is
sufficient to establish false-negative mechanisms, but not to generalize a
replacement rule: the seven targets are not an independent validation sample,
the existing three positives already enter through canonical envelopes, and the
36-entry holdout contained no new positive fragments. A follow-up implementation
must first freeze fresh positives and confusable negatives from independent
entries/pages across both PDF volumes. It must include bracketed and unbracketed
forms, italic terms in German, ordinary full-form examples, existing-envelope
controls, quoted editorial/Lex material, adjacent authorities/components, and
damaged quotation boundaries. The existing holdout remains frozen and separate.

The source evidence therefore supports a **parser capability gap**, not a
single safe generalized correction yet. No citation is newly owned, and no
meaningful residue is newly typed by this investigation. In particular, the
21 damaged Lex delimiter/decoding cases remain separate and unresolved; no
quote closure or source punctuation is inferred.

## Next bounded implementation plan

1. Build a fresh independent validation panel from stored PDF observations and
   facsimiles, stratified by volume, page and structural context; inspect every
   selected positive and negative before evaluating a change.
2. Fix bracketed-form reconstruction by matching exact source characters to
   observed run spans (including bracket runs that share a span with adjacent
   text), without changing source text or accepting a partial form. Require an
   independent boundary from an existing component edge or another established
   source marker.
3. Consider allowing italic runs within a translation only when they are
   internal lexical spans and the outer quote remains balanced, continuous,
   German-translation-shaped, and immediately followed by the existing exact
   citation node. Negative controls must include editorial definitions, Lex
   glosses, and intervening citations/components.
4. Keep full-form example recognition (`849`) separate from the tilde
   substitution production. First establish an independently bounded form span
   that does not cross the accepted definition; if the source layout cannot do
   so, retain it unresolved.
5. For `44`, correct run-start reconstruction only if source-aligned span
   boundaries exclude the prior Sanskrit definition without weakening the
   overlap guard.
6. Add actual-observation positive/negative tests, run targeted entry
   projections and preservation checks, then the full replay and all 114 frozen
   witnesses. Report owner and residue deltas separately.

Estimated maximum citation coverage for these source constructions is seven;
that is not a promised gain. Residue benefit is unmeasured. A general quotation
role parser is neither necessary nor supported by this evidence.

## Existing CI and accounting record

The certified baseline remains 29,877 projected witnesses, 109,359 established
owners, 66 unresolved citations, 9,740 meaningful pending alphabetic
characters, and 114 passing frozen witnesses. `release/current` remains
untouched. The previously recorded GitHub Actions result for `3e441902` remains
1,417 passing tests and 13 pre-existing failures; the release-reproduction
workflow remains 69 differences. These are separate from this parser diagnosis
and should not be hidden by changing historical expectations or the locked
release.
