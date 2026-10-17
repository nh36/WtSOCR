# BAdW dictionary reader prototype

The tracked files in this directory are reusable presentation code. The
source-bearing `data.json` and `inspection.json` exports are generated locally
under ignored `work/` storage; they are not part of the repository. The current
workspace preview is preserved at `work/badw_dictionary_prototype_preview/`.

When the local source projections are available, build a fresh preview with
the projection and entry-index artifacts selected for that source snapshot:

```sh
python3 scripts/build_badw_dictionary_prototype.py \
  --projection work/<snapshot>/projection.jsonl \
  --entry-index work/<snapshot>/entry_index.jsonl \
  --output work/badw_dictionary_prototype_preview
```

Supply `--citation-links`, `--bibliography`, and the applicable source-cache
and review arguments when the projection includes citation details. The
builder verifies source hashes and accepted relationships before writing.

Serve this directory with any static HTTP server, for example:

```sh
python3 -m http.server 8000 --directory work/badw_dictionary_prototype_preview
```

Then open `http://localhost:8000`. Citation buttons show a concise authority
description on hover or keyboard focus. Activating one opens a single reusable
detail dialog; Escape closes it and returns focus to the citation. Unresolved
identity and partial coverage remain explicit. A passage is shown only where
the projection contains a reviewed `citation_of` relationship.

The view does not resolve identities, alter ownership, or infer source
relationships. The regression tests run with `node --test
tests/badw_dictionary_prototype.test.cjs`.
