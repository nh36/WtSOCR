Structural German Quote Wrap Repair Guardrails

Scope:
- Only run on entry-body lines that look like German prose, not on bibliography or front matter.
- Only target open German quotation segments marked with `„` and lacking a matching `“` on the same line segment.
- Only target line-final Latin-script word fragments split by a terminal hyphen.

Allowed repair shapes:
- Direct wrap: `... „sie vortra-` + next line `gen ...“`
- Citation-interrupted wrap: `... „sie tra-`, then one short citation head like `(Gir`, then a coordinate prefix like `24,24);`, then later a lower-case continuation like `gen ...“`

Hard limits:
- Stay inside one page.
- Short lookahead window only.
- Do not touch lines with Tibetan script.
- Do not rewrite bibliography-like author-year lines or sigla lists.
- Only accept a joined form when it is plausibly German:
  - either the joined token already occurs elsewhere in the corpus, or
  - it ends in a common German prose ending and the continuation fragment is short.

Audit:
- Every structural repair must emit its own change row with a dedicated reason code.
- After any structural repair, reparsing is mandatory before later token-level heuristics run.

Non-goals for this pass:
- General sentence reflow
- Bibliography rewrapping
- Sanskrit title reconstruction
- Tibetan transliteration joining outside German quoted prose
