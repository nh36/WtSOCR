# BAdW dictionary reader prototype

This is a presentation-only five-entry development sample. It contains the
existing HTML and PDF projections for `bkri`, `bog re`, `ce śa`, `groṅ phyi
ñug ma`, and `chos ’khor`; it preserves their source strings and relationship
records. The source export SHA-256 and selected entries are recorded in
`data.json` under `sample_provenance`.

Serve this directory with any static HTTP server, for example:

```sh
python3 -m http.server 8000 --directory scripts/badw_dictionary_prototype
```

Then open `http://localhost:8000`. Citation buttons show a concise authority
description on hover or keyboard focus. Activating one opens a single reusable
detail dialog; Escape closes it and returns focus to the citation. Unresolved
identity and partial coverage remain explicit. A passage is shown only where
the projection contains a reviewed `citation_of` relationship.

The view does not resolve identities, alter ownership, or infer source
relationships. The regression tests run with `node --test
tests/badw_dictionary_prototype.test.cjs`.
