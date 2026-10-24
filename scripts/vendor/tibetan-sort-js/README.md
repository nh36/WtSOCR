# Vendored Tibetan collation

Unmodified `src/index.js` (renamed `index.mjs`) and `LICENSE` from BDRC
`@buda-base/tibetan-sort` **2.3.1**, commit
`6c664f5be95aa4c6684fb08fb7aeab30cfb80fe3`:
https://github.com/buda-base/tibetan-sort-js/tree/6c664f5be95aa4c6684fb08fb7aeab30cfb80fe3

MIT, copyright 2017 Buddhist Digital Resource Center; author Elie Roux.
Keep the accompanying licence when distributing the build tools. The reader
contains only the generated catalogue, with no runtime library fetch.

We use the dependency-free Unicode `compare(a, b)` API, not EWTS or Intl.
Upstream tests cover root/prefix order, vowels before subscripts, successive
syllables and visarga. Version 2.3.1 includes the vowel/subscript corrections
missing from the older Esukhia Python port (`TibetanSort.compare` / `sort_list`),
which was therefore not selected: https://github.com/Esukhia/tibetan-sort-python .

Upstream explicitly does not guarantee Sanskrit-stack ordering or normalize
Unicode (notably U+0F77 versus U+0FB2 U+0F71 U+0F80). Our wrapper uses NFC,
never compatibility normalization or invented Tibetan. Recognized native stacks
and native vowel signs are eligible; Sanskrit signs, other stacks, mixed-script
decoding and missing Tibetan fall back. This conservative structural check does
not identify Sanskrit loans written entirely with ordinary Tibetan letters.
Such loans retain native Tibetan order; exact Sanskrit ordering would require
separately reviewed lexical classifications and is outside this change.

Independent WTS check: *Wörterbuch der tibetischen Schriftsprache* I,
printed **pp. xv, xx–xxi**, locally inspected in `pdfs/WtS 1-34.pdf`, PDF pages
8 and 11 (two printed pages per scan). Page xxi supplies the native cluster
sequences used in `tests/fixtures/wts_tibetan_order.json`. Suffixes in the nga fixtures disambiguate the printed prefix skeletons;
the ga-series words instantiate the same printed cluster order. Page xx
supplies alphabet/vowel order; page xv explicitly gives `ka < kwa` and
`ku sa la < ku sa'i grong khyer` (LoC: `ku sa’i groṅ khyer`). These fixtures
are independent of upstream expected results.

WTS discrepancy: BDRC ordinarily places wa zur with subjoined consonants.
WTS p. xv places a wa-zur spelling immediately after its corresponding spelling
without wa. The wrapper compares a wa-free key first, then the complete key;
no source spelling or library code is changed. Terminal tsheg/shad are ignored
in keys so HTML/PDF presentation punctuation cannot outrank homonym numbers.
Numeric homonyms follow collation keys, then source kind and stable witness ID.
No witnesses are combined. Fallback entries follow all keyed entries, ordered
by NFC LoC code points, numeric homonym, source kind and ID; this is a stable
discovery order, not a claim to Tibetan or Sanskrit collation.
