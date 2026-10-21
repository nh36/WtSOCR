# Full acquired-corpus WTS reader

The full reader retains the connected preview's visual design and source conventions.
It includes all **29,877 acquired witnesses (18,037 HTML; 11,840 PDF)**.
This is the complete acquired corpus, not a claim that upstream editorial coverage
is complete. There is no translation or change to the OCR release.

## Open or rebuild the full reader

```sh
python3 scripts/build_badw_full_reader.py --output work/badw_full_reader_fresh
python3 -m http.server 8767 --bind 127.0.0.1 --directory work/badw_full_reader_fresh
```

For the current local build with the bounded script experiment, serve
`work/badw_full_reader_20261020/loc10` instead (`run18` retains the LoC-only parent).
Open <http://127.0.0.1:8767>. Try **mkhar ’gro**, **ṅar**, **rños**, and **ṅu**,
then search any acquired LoC or Tibetan headword. Previous/next follows Unicode
LoC order, homonym, then stable source identity; this is not Tibetan collation.

The complete lightweight headword catalog is searchable locally. Only 100 index
rows are mounted at once; entry contents load as individual hash-verified files,
with at most 24 cached entries. Citation details travel with their entry, rather
than a monolithic dictionary payload. Established lexical identities with multiple
witnesses open an explicit witness selection. Ambiguous homonyms remain unresolved.
Deep links, browser history, keyboard navigation, source access and the existing
83-witness fixture remain available.

The build streams the frozen corpus through the current adapters and reviewed
source-bound annotations. It verifies cached HTML/PDF/canonical hashes, preserves
accepted citation identities and relationships from the frozen SQLite baseline,
and checks all 23 reviewed occurrences, 50 members and 47 accepted destinations.
It refuses existing output directories. Its manifest pins inputs and code and
reports citations, ownership, references and incompatible annotation bindings.
An annotation tied to a different source view is recorded in
`annotation_conflicts.json`; its frozen projection is retained without rebinding.
All output remains ignored under `work/`; acquired sources are never overwritten.
Local source/cache/projection/bibliography/baseline inputs named in the script
must be present. No network acquisition is part of the build.

The 83-witness fixture has **113 accepted target units, all with included
destinations**. Its remaining nine unresolved and two ambiguous target units
lack an established destination identity or qualifier; none of those failures
is caused solely by sample restriction. Expanding the catalog must not turn
these uncertainties into arbitrary links. In particular, the wrapped target in
**brñan** parses correctly as **gzugs brñan** but has no exact indexed destination.
The two ambiguous references are in **btug** and **tal la**. Missing identities
occur in **bka’ gter**, **bka’ ma**, **brñan**, **gtogs**, **gtugs**, **thig**
(two occurrences), **ṅar**, and **ṅu**. Subsequent facsimile inspection established
a parsing failure in **ṅar**: printed p. 15 continues the list through **ṅar mi,
ṅar zan**, beyond the frozen target extent. The reviewed span correction below repairs this parser defect; it is not a printing error. The fixture below is retained intact.

Run focused Python/Node tests listed below, adding `tests/test_badw_full_reader.py`.
For full-corpus browser journeys, use:

```sh
BADW_READER_URL=http://127.0.0.1:8767 \
  NODE_PATH=work/badw_reader_browser_tools/node_modules \
  node tests/badw_full_reader.browser.cjs
```

The browser suite uses the independent 83-witness fixture for all 47 reviewed
member journeys, source and citation checks, plus full-catalog pagination, search,
history, keyboard, integrity failures and mobile layouts.

## Reference census and shared-anchor parser family

The old 852 unresolved parent occurrences become 825 unresolved **target units**
under the current resolver: seven italic-numeral repairs and replacing 23 plural
parents with their 50 members (47 resolved, three unresolved). Before this parser
family: HTML 4,706 resolved / 576 unresolved; PDF 2,832 resolved / 131 unresolved /
118 ambiguous target units. Three exact HTML labels inside malformed shared
anchors now resolve: **ka chen bźi**, **ko sko**, **sko cig pa**. The fourth empty
label crosses the frozen arrow extent and remains unresolved. No span is widened.
After: HTML 4,709 / 573; PDF unchanged; total **7,541 resolved / 822 residual**.
Full differential: 29,875 identical witnesses; only three reference records in two
witnesses change. Citations, components, relationships and source bindings agree.

```sh
python3 scripts/census_badw_reader_references.py \
  --reader work/badw_full_reader_20261020/run18 \
  --output work/badw_residual_fresh.jsonl.gz
```

The compact ledger retains every residual occurrence, literal source component,
source span/binding, facsimile/source links and exact candidate identities.
Its diagnostic buckets are **provisional**, not seven-way scholarly adjudications:
336 HTML and three PDF identity/manifestation mismatches; 221 HTML and 120 PDF
missing exact identities; two HTML and 118 PDF ambiguities. The diagnosed empty-label parser
boundary has now been repaired.
These are the current post-review groups; the family-specific counts below retain
comparable intermediate checkpoints.
Missing identities do not establish acquisition gaps or printed errors. No printed
or editorial correction is asserted by this census. These cases still need review.

Five malformed editorial hrefs containing a literal `<tib>` opening tag are
individually reviewed in the existing semantic annotation ledger. Exact raw HTML,
visible labels, explicit homonym numbers, source hashes, physical selectors and
unchanged arrow extents bind each interpretation. Four now link: **ldaṅs² →
ldaṅ²**, **nod → mno¹**, **rbas → sba²**, **snom² → nom²**. The target **bslab pa
kun las btus pa¹**, cited in **kun las btus pa**, remains absent. Original URLs
and source readings are retained; this is evidence of malformed editorial HTML,
not a claim about printing errors. No general URL normalization is applied.
After this family: HTML **4,713 resolved / 569 unresolved**; PDF unchanged;
total **7,545 resolved / 818 residual**. The corresponding ledger has 344 HTML
identity mismatches, 224 HTML missing identities and one HTML parser-boundary
failure; PDF remains 118 ambiguities, 128 missing identities and three identity
mismatches. These are provisional diagnostic groups, with the absent reviewed
editorial target explicitly distinguished. The remaining scholarly source review
has not been completed.

Three PDF references put their comma-separated targets in a single continuous
italic run: **chos kyi sku** (printed p. 285: **sku bźi, sku gsum**), **groṅs**
(p. 277: **bkroṅ, bkroṅs**) and **rjes su thob** (p. 416: **rjes thob, rjes la
thob pa**). Facsimile inspection confirms that these are parser defects, not
printing errors. Commas inside a single original italic target extent now delimit
independent members; empty members fail closed. Existing multi-run collections
retain their reviewed segmentation, including the frozen **ṅar** collection.
Every member still passes the
existing source-binding, exact-span, typography and printed-target gates. Parents
remain unresolved and have no single destination. Three unresolved target units
become six accepted members. After this family:
HTML **4,713 resolved / 569 unresolved**; PDF **2,838 resolved / 128 unresolved /
118 ambiguous**; total **7,551 resolved / 815 residual**. The full-corpus
differential finds 29,874 identical witnesses and three changed references.
It verifies every source/display character and structural tag across the new
clickable member boundaries; citations, components, source bindings and all
previously accepted destinations agree. The browser suite exercises all six new links
in addition to the original 47 reviewed member journeys.

Eight further malformed HTML hrefs contain a nested `span` whose quotes truncate
the DOM URL. Individually reviewed raw attributes identify **dkar nag¹**, **dkar
dmar¹**, **dkar gsum¹** (in **dkar¹**), **koṅ rje dkar po¹** (in **dkar po**),
**dka’ thub can¹**, **dka’ thub pa¹** (in **dka’ thub**), **dar dir ku co¹** (in
**ku co**) and **mun pa’i smag rum¹** (in **smag rum**). Seven exact destinations
are acquired; **dar dir ku co¹** is absent and remains explicitly unresolved.
The existing reviewed-annotation mechanism retains original malformed URLs,
source hashes and partial visible labels without widening frozen spans. This
establishes malformed editorial HTML, not an error in the printed dictionary.
After this family: HTML **4,720 resolved / 562 unresolved**; PDF unchanged;
total **7,558 resolved / 808 residual**. All remaining diagnostic classifications
still require scholarly review; no printed error has been asserted.

A reviewed PDF span extension repairs **ṅar** (printed p. 15): the frozen
188:212 arrow extent stopped inside **ṅar phye, ṅar**. The cached facsimile,
continuous italic typography and same-page/division geometry establish the exact
188:224 extent with **ṅar glud, ṅar phye, ṅar mi, ṅar zan**. All four now resolve
independently; the plural parent remains unresolved. The existing annotation
ledger binds both extents and the superseded component identity. Ordinary parser
replay retains frozen extents; only this accepted review permits the extension.
The original 23-occurrence/50-member fixture remains intact, and every previously
accepted member is checked for unchanged source span, binding and destination.
After this family: HTML **4,720 resolved / 562 unresolved**; PDF **2,841 resolved /
127 unresolved / 118 ambiguous**; total **7,561 resolved / 807 residual**.

Six individually facsimile-reviewed tilde references repeat the current printed
headword. Exact expanded targets **kun brjod pa’i cho ’phrul**, **bag la ñal**, and
**kha lta** now navigate. **rjes su bstan pa’i cho ’phrul**, **rdzu ’phrul gyi cho
’phrul**, and **yoṅs su gtugs** have no exact acquired destination and remain
unresolved. Evidence is printed pp. **275** (cho ’phrul), **454** (ñal), **42**
(gtugs), and **110** (lta), bound to cached PDF hashes, exact spans, typography,
current headword and page/run selectors in the existing annotation ledger.
The literal tilde and source text remain unchanged; neither a printing error nor
an acquisition gap is inferred. No general abbreviation expansion is enabled.
After this family: HTML **4,720 resolved / 562 unresolved**; PDF **2,844 resolved /
124 unresolved / 118 ambiguous**; total **7,564 resolved / 804 residual**.

The second arrow in the malformed shared anchor of **ka chen** ends at
678:679; its exact Tibetan-typed target **bka’ chen** occupies the adjacent
679:688 DOM span outside that arrow. A strict boundary rule now retains these
two separate locations and recovers the target without widening the arrow,
inheriting the malformed URL or assuming a homonym. Immediate adjacency,
explicit Tibetan typing, terminal punctuation and an unqualified lexical form
are required. The full-corpus differential changes this one reference only;
29,876 witness shards, all source characters, components, citations and accepted
destinations are unchanged. This is an extraction boundary defect, not a
printing-error finding. After this family: HTML **4,721 resolved / 561 unresolved**;
PDF unchanged; total **7,565 resolved / 803 residual**.

Six editorial anchors contain comma-separated lists in **bu ram chaṅ**, **drag
po**, **rmyaṅ**, **skya thal**, **’byor ba**, and **’dul**. Exact DOM boundaries,
raw-object and text hashes, literal commas and any adjacent superscript now bind
12 separate targets. Eight resolve; two homonym sets remain ambiguous and two
exact labels remain absent. Only a visible superscript qualifies the first
member; the combined URL's homonym suffix never qualifies the entire list.
Literal nonbreaking spaces are preserved and not silently normalized. Plural
parents remain unresolved. This is a parser repair, not a printed-error finding.
After this family: HTML **4,729 resolved / 557 unresolved / two ambiguous**;
PDF unchanged; total **7,573 resolved / 801 residual**. The full differential
finds exactly six changed references and 29,871 identical witnesses; source
characters, citation identities, structural metadata and accepted destinations
remain unchanged. Browser tests follow all eight new links and explain all four
uncertain members, in addition to the original 47-member regression fixture.

The facsimile of **kha kha khyer** (printed p. 4, right column) confirms that
the upright final **r** belongs to the target **kha khyer**. The frozen italic
extent stopped at **kha khye**. One accepted source-bound annotation extends
1:10 to 1:11, requiring the same line and font family, consecutive source runs,
a single terminal letter and a printed stop. Ordinary parser replay does not
enable this extension. The destination appears below on the same printed page.
This is a parser extent defect, not a printing error. After this repair: HTML
**4,729 resolved / 557 unresolved / two ambiguous**; PDF **2,845 resolved /
123 unresolved / 118 ambiguous**; total **7,574 resolved / 800 residual**.
The full differential finds one changed reference and 29,876 byte-identical
witnesses; source characters, citations and all accepted destinations are
preserved. The browser suite follows the repaired reference and returns through
history. The residual classification remains provisional and requires further
source review.

## Bounded historical LoC script experiment

The optional **Both / LoC / Tibetan** control changes derived display only. Both
retains the existing headword layout. Source headwords remain in the adjacent
disclosure in every mode; original passage transliteration remains available in
the title and source evidence. IDs, source spans, references and citations stay
unchanged. Only conversions which exactly match an independently paired Tibetan
headword are eligible. Whole exclusively `bo`-typed spans may reuse those exact
attested forms; substrings and mixed-language spans are excluded. Unavailable
headwords explicitly explain the limitation. This is not a Wylie converter.

```sh
python3 scripts/experiment_wts_loc.py --reader work/badw_full_reader_20261020/run18 \
  --output work/wts_loc_experiment_fresh
python3 scripts/build_badw_loc_reader.py --reader work/badw_full_reader_20261020/run18 \
  --experiment work/wts_loc_experiment_fresh --output work/badw_loc_reader_fresh
python3 -m http.server 8769 --bind 127.0.0.1 --directory work/badw_loc_reader_fresh
```

Both commands refuse existing outputs. The derived build verifies experiment
input hashes and every parent shard, and copies sources without overwriting them.
The converter recombines 151 onset and 14 coda templates from 2,035 training
syllables, using previously reviewed historical LoC role mappings. A deterministic
Tibetan-syllable split holds out entire syllables from template training; this
does **not** independently test discovery of the fixed role mappings.

| Evaluation set | Forms | Converted | Exact among converted | Coverage |
|---|---:|---:|---:|---:|
| Held-out, independently corroborated clean pairs | 364 | 241 | 241/241 (100%) | 66.2% |
| Held-out, problematic or uncorroborated pairs | 689 | 289 | 289/289 (100%) | 41.9% |
| Damaged-source stress set, not independent holdout | 2,041 | 670 | 175/670 (26.1%) | 32.8% |

Clean abstentions comprise 119 unattested structures and four unsupported inputs;
the second group has 397 and three respectively. Stress-set errors comprise 495
different attested forms, with 1,343 unattested and 28 unsupported inputs. A
damaged source occurrence does not prove its transliteration is corrupt. Neither
valid uncommon orthography nor ambiguous root parsing is silently repaired.
Period-conditioned onsets, unsupported Sanskrit stacks and unsupported characters
abstain. Multiple inverse candidates also abstain. The weak stress-set accuracy
rules out unrestricted conversion; independent agreement gates reader display.
The current build enables 4,968 headword witnesses (4,547 distinct LoC headwords)
and 2,281 exact spans. Try **ka** and switch all three modes. Metrics, per-case
outcomes, attestations and input hashes stay in the ignored experiment directory.

Run `python3 -m pytest tests/test_wts_loc_converter.py -q` in addition to reader
tests. The full browser suite also exercises all three display modes when enabled.

---

# Connected WTS reader preview

This is a bounded demonstration of the scholarly dictionary, generated from the
current parser, source-bound cross-reference resolver, semantic projection and
bibliography bridge. It replaces the five-entry snapshot as the current reader
preview. Source evidence and generated exports remain in ignored `work/`;
no OCR release or acquired source is changed.

## Open the current preview

From the repository root:

```sh
python3 -m http.server 8766 --bind 127.0.0.1 \
  --directory work/badw_connected_reader_20261020/run8/reader
```

Open <http://127.0.0.1:8766>. Start with the suggested entries in “About this
collection”, or search for:

- **mkhar ’gro**: independently linked targets in a complete collection.
- **ṅar**: a partial collection, preserved uncertainty, examples and citation dialogs.
- **rños** or **ṅu**: further multiple-target journeys and their destination entries.

“Read the source” opens the original PDF facsimile or BAdW editorial page in a
new tab. PDF facsimiles are local, hash-verified copies, so inspecting print does
not depend on BAdW being online. Editorial HTML and print witnesses are labelled
separately. Duplicate headwords may represent distinct source witnesses.

The current corpus contains **83 witnesses (74 PDF, 9 HTML)**: the **23 reviewed
multiple-target occurrences** and the closure of all uniquely resolved entry
links reachable from them. All **47 resolved members** have destinations;
**3 members remain unresolved**, in **3 partial collections**. The remaining
**20 collections are complete**. Plural parents retain their unresolved status.
This is neither the whole dictionary nor a new certification of every structure
in the included destination entries.

## Navigation and scholarly conventions

Entry URLs use stable source identities in the fragment. Browser Back/Forward,
reload, copyable deep links and previous/next links work without a server router.
Previous/next and the index use **Unicode order of LoC headword, then homonym,
then source identity**; this is explicitly not traditional Tibetan collation.
The index highlights the selected witness and searches Tibetan, LoC and accepted
alternate headwords. Arrow keys, Home/End and Enter navigate the index; the skip
link moves to the reading. Escape closes dialogs and returns focus.

Dotted reference buttons explain unresolved, ambiguous or unavailable targets;
no destination is invented. Citation dialogs distinguish accepted bibliographic
components from full citation coverage and independently report passage
ownership. A source passage is displayed only for an accepted `citation_of`
relationship. **[unread sign]** preserves an undecoded source glyph; activating
the marker opens the facsimile link and extraction evidence. Source strings and
identities remain intact in the data. Other provisional source structures remain
provisional. The provenance disclosure retains witness identities and hashes.

Tibetan uses the bundled **Noto Serif Tibetan** variable font, with system
fallbacks. The unmodified font is from
[Google Fonts](https://github.com/google/fonts/tree/main/ofl/notoseriftibetan),
under the [SIL Open Font License](fonts/OFL.txt); the preview requires no external
font service. German prose, transliteration, grammatical labels, examples and
citations have distinct, restrained treatments. Mobile layouts retain the index,
source links and dialogs.

## Rebuild from validated local inputs

Choose a **new** output directory:

```sh
python3 scripts/build_badw_connected_reader.py \
  --output work/badw_connected_reader_fresh
python3 -m http.server 8766 --bind 127.0.0.1 \
  --directory work/badw_connected_reader_fresh/reader
```

The recipe names the existing acquisition/cache, pinned identity index, reviewed
occurrence set, canonical PDF replay and current bibliography bundle at its top.
These ignored local inputs must be present; the build performs no acquisition.
It replays current code, verifies PDF/canonical/HTML hashes and reviewed annotation
bindings, checks the exact 23 occurrence spans and 50 member outcomes, and follows
only accepted unique destinations. A 150-entry ceiling prevents accidental
expansion. The HTML citation-review ledger is scoped by selected source identity
without changing any review row or weakening the existing completeness check.
Existing output paths are rejected, including incomplete builds. Preserve them
and choose another output path after a failure.

`reader/manifest.json` records input/implementation hashes, corpus selection,
ordering and export hashes. The static reader, facsimiles and font can be served
with any HTTP server; opening `index.html` directly is insufficient. This local
demonstration does not publish or redistribute the acquired dictionary corpus.
The lower-level `build_badw_dictionary_prototype.py` remains available for other
explicitly selected projection/index inputs.

## Validation

```sh
python3 -m pytest tests/test_badw_connected_reader.py \
  tests/test_badw_dictionary_target_members.py \
  tests/test_badw_dictionary_prototype.py tests/test_badw_dictionary_entry_view.py \
  tests/test_badw_cross_reference_resolution.py -q
node --test tests/badw_dictionary_prototype.test.cjs
```

For browser journeys, install `playwright-core@1.56.1` in an ignored tools directory
(or use an existing installation) and run against a freshly served preview:

```sh
npm install --prefix work/badw_reader_browser_tools --no-save playwright-core@1.56.1
BADW_READER_URL=http://127.0.0.1:8766 \
  NODE_PATH=work/badw_reader_browser_tools/node_modules \
  node tests/badw_connected_reader.browser.cjs
```

The browser harness uses installed Google Chrome on macOS; set `CHROME_PATH` for
another Chromium executable. It traverses every reviewed member link, tests
Back/Forward and uncertain-reference dialogs, visits every entry, verifies local
facsimile hashes, opens citations by keyboard, checks index navigation and
320/390/768/1440-pixel layouts, and saves screenshots under ignored `work/`.
These integration tests require the local corpus; synthetic Python/Node tests do
not. Repository-wide mandatory validation in `AGENTS.md` also applies.
