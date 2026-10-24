# Full acquired-corpus WTS reader

The full reader retains the connected preview's visual design and source conventions.
It includes all **29,877 frozen acquired witnesses (18,037 HTML; 11,840 PDF)**
and one separately reviewed HTML acquisition: **29,878 witnesses** in total.
This is the complete acquired corpus, not a claim that upstream editorial coverage
is complete. There is no translation or change to the OCR release.

## Open or rebuild the full reader

```sh
python3 scripts/build_badw_full_reader.py --output work/badw_full_reader_fresh
python3 -m http.server 8767 --bind 127.0.0.1 --directory work/badw_full_reader_fresh
```

For the current cross-reference build, serve
`work/badw_full_reader_20261020/run43` instead. The earlier bounded script
experiment remains at `work/badw_full_reader_20261020/loc14`.
Open <http://127.0.0.1:8767>. Try **mkhar ’gro**, **ṅar**, **rños**, and **ṅu**,
then search any acquired LoC or Tibetan headword. Catalogue, search results and
previous/next use the Tibetan ordering described below.

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

## Tibetan ordering and search

The build requires Node.js and prepares the catalogue once with the vendored,
MIT-licensed BDRC `@buda-base/tibetan-sort` 2.3.1 Unicode comparator. There is
no runtime dependency download or per-keystroke catalogue sort. See
[`../vendor/tibetan-sort-js/README.md`](../vendor/tibetan-sort-js/README.md)
for the pinned commit, independent printed WTS fixtures and limitations.
Attested Tibetan keys take precedence, followed by numeric homonyms and stable
source-witness identifiers. HTML and PDF witnesses remain separate. WTS's
wa-zur convention is applied in a wrapper; upstream code is unchanged.

Missing, mixed-script or structurally unsupported Tibetan keys follow keyed
entries in deterministic NFC LoC code-point order, then numeric homonym and
source identity. This fallback makes no claim to Sanskrit alphabetical order.
No speculative spelling is generated. The generated preview records keyed and
fallback counts and reasons; each fallback catalogue row records its reason.

Search keys use NFC and lowercase, equating only ASCII apostrophe U+0027,
left/right single quotation marks U+2018/U+2019 and modifier apostrophe U+02BC.
Apostrophes remain present. Accents, spacing, hyphens and Tibetan distinctions
are preserved. Primary LoC, attested Tibetan and accepted alternative headwords
remain searchable. Generated search keys leave every source string unchanged;
reference resolution does not use them. Empty search restores the catalogue;
no-match feedback retains the current article without a result highlight.

Small fixtures require no acquired corpus:

```sh
python3 -m pytest tests/test_badw_full_reader.py -q
node --test tests/badw_dictionary_prototype.test.cjs
NODE_PATH=work/badw_reader_browser_tools/node_modules node tests/badw_reader_search.browser.cjs
```

The full browser suite additionally checks apostrophe equivalence, independent
Tibetan order, pagination without skipped/duplicated witnesses, selection,
history, keyboard navigation, mobile widths and absence of entry-body requests
while filtering/paging. It prints index-load, filter, render and pagination
timings. Use a fresh output directory and unused server port for concurrent work.
A cached catalogue may be reprocessed for integration testing without rebuilding
or modifying its entry shards; this does not replace a complete source rebuild.

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
  --reader work/badw_full_reader_20261020/run43 \
  --output work/badw_residual_fresh.jsonl.gz
```

The compact ledger retains every residual occurrence, literal source component,
source span/binding, facsimile/source links and exact candidate identities.
Its diagnostic buckets are **provisional**, not seven-way scholarly adjudications:
336 HTML and three PDF identity/manifestation mismatches; 208 HTML and 110 PDF
missing exact identities; two HTML and 93 PDF ambiguities. The diagnosed empty-label parser
boundary has now been repaired.
These are the current post-review groups; the family-specific counts below retain
comparable intermediate checkpoints.

The 340 identity/manifestation cases at run24 have now been partitioned against
their actual candidates and 257 distinct live editorial URLs. None is simply a
choice between witnesses of an already established lexical identity. There are
331 explicit HTML homonym-1 links to unnumbered PDF candidates, one reviewed
nonbreaking-space href with the same identity gap, five homonym-2 links with only
homonym-1 acquisitions, and three printed raised qualifiers with unnumbered PDF
targets. All 253 homonym-1 URLs return the identical “not yet released” page.
Three homonym-2 URLs are heading-only shells; they cannot supply entries.
Facsimiles of both ends of the three PDF references confirm the qualifier and
unnumbered heading; corresponding numbered senses do not prove homonym identity.
These 339 cases remain unresolved. No printed error is asserted.

The fourth homonym-2 URL, **dru gu²**, supplies a complete article with an explicit
numbered heading, a definition of a Turkic people and twelve examples. It is
distinct from acquired **dru gu¹**, a ball of thread. The exact new acquisition
resolves **drug² → dru gu²**. `data/badw_reader_supplements.jsonl` pins the cached
bytes, heading, URL, extracted text and stable identity; the build replays the
existing projection pipeline and rejects empty shells or changed bindings.
It neither modifies the frozen corpus nor equates blank PDF homonyms with 1.
Run25: HTML **4,735 resolved / 551 unresolved / 2 ambiguous**; PDF **2,849 /
119 / 118**; total **7,584 resolved / 790 residual**, versus **7,582 / 792**
before these two families. All 29,877 original witnesses preserve sources,
citations, relationships and accepted destinations. Apart from the index hash,
29,876 entry bodies are unchanged from run24; only the reference in drug² gains
a link. The 23/50/47 fixture remains intact. Browser validation passed keyboard
and history navigation to the new article, 56 member journeys, 82 citation
journeys, 58 facsimile checks and four viewport sizes with no browser errors.
Case-level source evidence stays in ignored
`work/badw_full_reader_20261020/investigation/identity_case_review.jsonl`.
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

Three separately reviewed PDF references now connect to exact indexed headings
which retain a printed line break: **ñu le ñab kyi lag riṅ → jo bo klu bdud mched
dgu** (destination p. 358), **cho ’phrul → rjes su bstan pa’i cho ’phrul** (p. 416),
and **ñer len phuṅ po → ñe bar len pa’i phuṅ po lṅa** (p. 496). Each annotation
binds both the source occurrence and the destination's canonical heading runs,
geometry, cached PDF and exact raw index key. The second combines its existing
reviewed tilde expansion with the destination proof. Neither the source text nor
the wrapped index keys change; no general whitespace aliases are introduced.
Three HTML references with explicit homonym 1 remain unresolved because these
PDF headings are unnumbered. No printed error is asserted.
After this family: HTML **4,729 resolved / 557 unresolved / two ambiguous**; PDF
**2,848 resolved / 120 unresolved / 118 ambiguous**; total **7,577 resolved /
797 residual**. The full differential finds exactly three changed reference
records, 29,874 structurally identical witnesses and 29,871 byte-identical files;
three other files differ only in annotation object key order. Source characters,
citations, components, identities and all prior accepted destinations are unchanged.
Browser tests follow all three new links, verify source access and history, and
retain uncertainty on the three qualified HTML references. The case ledger's
cause assignments remain provisional; exhaustive source review is unfinished.

One individually reviewed broken HTML anchor in **’drend** now links to
**’dren**. The cached DOM contains only **↑’** inside the anchor, immediately
followed by a Tibetan-typed **dren** and punctuation. The annotation binds both
exact spans and the cached HTML hash; validation reparses that DOM. The source
occurrence remains **59:61**, with its original label, URL and text unchanged.
The broken URL's homonym number is not inherited: the full exact lemma must
identify a unique lexical identity, with witness selection if needed. This is
an editorial HTML anchor defect; no claim about the printed dictionary is made.
After this family: HTML **4,730 resolved / 556 unresolved / two ambiguous**; PDF
unchanged; total **7,578 resolved / 796 residual**. The differential finds exactly
one changed reference and **29,876 byte-identical witnesses**; source text,
citations, components and prior accepted destinations are unchanged. Browser
validation follows the repaired link by keyboard, checks source access, and
returns through back/forward history.

Four individually reviewed editorial whitespace defects retain their original
HTML, labels, URLs, source spans and explicit homonym **1**. **piṇḍa pa → pe ña ba**
and **’brog ’brog → ’drog** now resolve to exact acquired destinations; each
destination's cached HTML also contains the reciprocal reference. **me loṅ lta
bu’i ye śes → ye śes lṅa** remains unresolved without an exact acquired identity.
**po ta la → gru ’dzin** remains unresolved because its numbered href does not
establish identity with the unnumbered PDF witness. These are source-bound
interpretations, not general whitespace normalization or claims of printing errors.
After this family: HTML **4,732 resolved / 554 unresolved / two ambiguous**; PDF
unchanged; total **7,580 resolved / 794 residual**. Exactly four reference records
change, with **29,873 byte-identical witnesses**. Source text, citations, components
and all prior accepted destinations are unchanged. Browser regression checks
cover both new destinations and both retained uncertainty explanations.

Two individually reviewed comma-list members contain a nonbreaking space in
both the visible editorial label and the combined href: **bu ram chaṅ → bu ram
śiṅ chaṅ** and **rmyaṅ → bya rmyaṅ byed**. Exact cached source and destination
HTML support each interpretation. The members resolve independently without
inheriting the combined href's homonym number. The first collection becomes
complete; the second remains partial because **rñaṅ** retains its two-way
ambiguity. Both plural parents remain unresolved. Original wording, source spans,
and URLs are preserved; no general whitespace rule or printed correction is added.
After this family: HTML **4,734 resolved / 552 unresolved / two ambiguous**; PDF
unchanged; total **7,582 resolved / 792 residual**. The differential checks two
changed members and **29,875 byte-identical witnesses**, preserving source text,
citations, components, neighboring members and all prior accepted destinations.
Browser checks cover keyboard navigation, source access and back/forward history.

The printed **dgra bla → ’go ba’i lha** reference (volume 2, p. 337, right
column) was truncated at an upright opening apostrophe before a font switch.
An intervening Arial italic CID 0003 (`ebbba6ed181c`) is independently verified
as nonprinting. Hash-checked PDF replay places the apostrophe and italic target
on one continuous baseline. The original 54-character reference extent did not
hit the 80-character limit. A separately named, source-bound extent review now
admits a narrow bridge, retaining the original placeholder, text, hashes and
offsets while deriving **’go ba’i lha** for exact lookup. Unknown ink, conflicting
typography, discontinuous geometry and crossing boundaries fail closed; logical
length is capped at 80 and source extent at 256 characters. No global UNKNOWN
stripping or headword normalization is introduced. One matching extraction defect
now links to its unique acquired PDF destination. Two other residual references
with nearby UNKNOWN tokens already end correctly and still lack exact targets.
After this family: HTML **4,734 resolved / 552 unresolved / two ambiguous**;
PDF **2,849 resolved / 119 unresolved / 118 ambiguous**; total **7,583 resolved /
791 residual**. The full differential finds **29,876 byte-identical witnesses**
and one repaired reference, preserving source text, citations, relationships and
all previously accepted destinations. Current-source physical replay reproduces
the built target. Browser validation includes the new keyboard/history journey
alongside all 47 independently accepted fixture members.

The **thig¹** reference on printed p. 246 exposed a separate parser defect:
comma-list continuation reabsorbed the following arrow after the initial
arrow-boundary check. A source-bound contraction retains **↑ka thig** and its
accepted destination; **↓tshaṅs thig** remains an independent unresolved occurrence.
The facsimile confirms both arrows. This removes a duplicated unresolved member,
not a missing destination. Run27: **7,584 resolved / 789 residual** (HTML
**4,735 / 551 unresolved / 2 ambiguous**; PDF **2,849 / 118 / 118**).
The differential verifies 29,877 byte-identical entry files out of 29,878,
unchanged source text, citations and relationships, the same accepted target span
and destination, and preservation of the independent second reference.

Six further facsimile-reviewed PDF references stop at a single upright space
between continuous italic target fragments: **mgon med**, **chos so so yaṅ dag
par rig pa**, **sñug**, **ta yas**, **rtiṅ du ’braṅs**, and **ltir**. The named
`reviewed_printed_upright_space` review requires exact source hashes, glyph/font
replay and a continuous physical baseline within one observation line. It does
not normalize source spaces or admit unknown ink, prose, arrows, incompatible
fonts, page crossings or discontinuous geometry. This repairs extraction, not
the published text. Five occurrences now provide six accepted destinations,
including both **lto ldir ba** and **¹ldir** in the recovered **ltir** list;
its plural parent remains unresolved. **so so yaṅ dag par rig pa bźi** is now
fully extracted but has no exact acquired destination and stays unresolved.
Run28: **7,590 resolved / 784 residual**, versus **7,584 / 789** before this
family (one additional target unit is exposed by the recovered list). HTML stays
**4,735 resolved / 551 unresolved / 2 ambiguous**; PDF becomes **2,855 / 115 /
116**. All other **29,872 entry files are byte-identical**. Source text,
citations, relationships, prior accepted destinations and the 23/50/47 fixture
are preserved. Browser validation covers the five new navigable occurrences,
the absent-target explanation, keyboard/history/source access, 82 citation
journeys, 58 facsimile checks and four viewport sizes, with no browser errors.

The facsimile-reviewed **thabs** reference continues from **↓pha** at the bottom
right of printed p. 228 to **rol tu phyin pa** at the top left of p. 229. Ordinary
extraction stopped at the page boundary and left the truncated **pha** ambiguous.
The named `reviewed_printed_page_continuation` annotation requires consecutive
article spans in the same hash-checked PDF, the same division and italic font,
and physically replayed bottom-right/top-left coordinates. It preserves the
literal newline and resolves the complete exact target **pha rol tu phyin pa**;
ordinary cross-page extraction stays disabled. This is a parser defect, not a
printing error. Run29: **7,591 resolved / 783 residual**; HTML remains **4,735 /
551 unresolved / 2 ambiguous**, PDF becomes **2,856 / 115 / 115**. All other
**29,877 entry files are byte-identical**, including previously accepted targets,
source text, citations and relationships. The 23/50/47 fixture remains intact.

The four **kiṅ śị** links in **ker śiṅ**, **keṅ śe**, **keṅ śi** and
**kin jaṅ hū** expose an editorial heading/link inconsistency. The original
volume 1 pp. 42–43 facsimile prints **kiṅ śị** in both the destination heading
and the kin jaṅ hū reference; BAdW retains that spelling in these links but
publishes the destination heading as **kiṅ śi**. Its explicit aliases establish
the first three identities, and the shared Ch’ang-an/T’ang-dynasty definitions
establish the fourth. Four `reviewed_editorial_headword_variant` annotations
pin the exact source DOM occurrences and hash-verified destination heading.
They preserve all printed readings, editorial labels and URLs; there is no
global spelling substitution and no claim of a printing error. Run30: **7,595
resolved / 779 residual**, versus **7,591 / 783**. HTML becomes **4,739 resolved /
547 unresolved / 2 ambiguous**; PDF remains **2,856 / 115 / 115**. All other
**29,874 entry files are byte-identical**. Source text, citations, components,
relationships, previously accepted destinations and the 23/50/47 fixture agree.
Browser validation follows all four repaired links by keyboard and checks
source access and back/forward history, alongside 82 citation journeys, 58
facsimile checks and four viewport sizes, with zero browser errors. Desktop and
mobile screenshots were inspected; the reader design is unchanged.

The **’khrud** paradigm on the original volume 2 printed p. 170 places an
arrow before the upright grammatical abbreviation: **↑fut. bkru**. The immediate
italic **bkru** is independently identified by the acquired washing entry and
its reciprocal ’khrud reference. A single `reviewed_printed_misplaced_arrow`
annotation binds both source ranges, typography, physical line and cached
source/destination hashes. It links the preserved **↑fut** occurrence to **bkru**
and displays the separate editorial interpretation **fut. ↑bkru**. This is a
facsimile-confirmed printed marker-placement error, not a parser defect or a
source-text correction. The numbered **¹khrus** reference and reverse HTML
homonym claim remain unresolved. Run31: **7,596 resolved / 778 residual**;
HTML remains **4,739 / 547 unresolved / 2 ambiguous**, PDF becomes **2,857 / 114 /
115**. No general abbreviation rewriting or homonym inference is permitted.

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
python3 scripts/experiment_wts_loc.py --reader work/badw_full_reader_20261020/run23 \
  --output work/wts_loc_experiment_fresh
python3 scripts/build_badw_loc_reader.py --reader work/badw_full_reader_20261020/run23 \
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

## Individually reviewed compound-headword links

Three HTML occurrences now navigate through exact, source-bound editorial
interpretations: **dug-mo-ñuṅ** in **ka ku bha ya** and **ka liṅ ka** to
**dug mo ñuṅ¹**, and **mu-stegs-pa** in **kā la yakṣa nag po** to
**mu stegs pa¹**. The destination's reciprocal equations independently identify
the first two; the matching deity-class definition and **Neb 282** establish
the third. These are editorial link-label variants, not parser defects or
confirmed printed errors. Literal labels, URLs, source spans and explicit
homonym numbers remain unchanged. No general hyphen-to-space rule is added.
Botanical descriptions are not harmonized. Other superficially similar labels
remain unresolved pending independent identity evidence.

Run33: **7,599 resolved / 775 residual** target units; HTML 4,742 resolved,
544 unresolved, two ambiguous; PDF unchanged at 2,857 resolved, 114 unresolved,
115 ambiguous. All previously accepted destinations and all 23 reviewed
collections / 50 members / 47 accepted member targets must remain unchanged.


One separately reviewed PDF occurrence, **↑gyad-mo** in **’jigs byed thabs ldan
’ug pa’i mgo can** (WTS III, p. 386), now links to the unnumbered **gyad mo**
(WTS II, p. 237). Both describe Bon-po deities and cite **Neb 313**; the destination
heading is independently checked against canonical PDF runs. This is a lexical
interpretation of a correctly extracted printed compound, not a parser defect
or a confirmed printing error. The original hyphen, arrow, source text and span
remain literal. The PDF-only review basis cannot discard a homonym qualifier,
change an accepted destination, or establish a general compound alias. The
separate HTML **gyad-mo¹** reference remains unresolved.

Run34: **7,600 resolved / 774 residual** target units; HTML unchanged at 4,742
resolved, 544 unresolved, two ambiguous; PDF 2,858 resolved, 113 unresolved,
115 ambiguous. The full differential permits only this one reference resolution;
all other witness contents, citations, source bindings and prior destinations,
including the 23 reviewed collections / 50 members / 47 accepted member targets,
remain unchanged.

One individually reviewed perfect-tense reference, **bcum → ’jum¹**, now links
using the printed reciprocal paradigm. WTS III p. 163 prints **pf. zu ↓’jum
zusammenziehen**; on p. 394, numbered **¹’jum** explicitly lists **pf. ↑bcum**,
whereas **²’jum** means *verstehen, wissen*. The exact numbered heading and
reciprocal passage are replayed against hash-pinned canonical PDF runs. This is
a homonym interpretation of a correctly extracted reference, not a parser defect
or a confirmed printing error. The literal unqualified source reference, component
and offsets remain unchanged. No default homonym is introduced; multiple witnesses
of the accepted identity still require explicit selection.

Run35: **7,601 resolved / 773 residual** target units; HTML unchanged at 4,742
resolved, 544 unresolved, two ambiguous; PDF 2,859 resolved, 113 unresolved,
114 ambiguous. Only this reference gains a destination; all previously accepted
destinations and the 23/50/47 fixture remain unchanged.

The same reviewed reciprocal-perfect family additionally identifies **gas →
’gas¹** (II pp. 203/368), **groṅs → ’groṅs¹** (II pp. 277/401), and **khol² →
’khol²** (II pp. 73/155). Each pair was checked in the printed facsimiles. The
competing homonyms have different paradigms or meanings: ’gas² has perfect bkas,
’groṅs² means Wundöffnung, and ’khol¹ has perfect bkol and concerns servitude.
The cooking paradigm selects ’khol², demonstrating that this mechanism does not
default to homonym 1. These are individually evidenced interpretations of intact
references, not asserted printing errors or changed source readings.

Run36: **7,604 resolved / 770 residual** target units; HTML unchanged at 4,742
resolved, 544 unresolved, two ambiguous; PDF 2,862 resolved, 113 unresolved,
111 ambiguous. Only these three reviewed references gain destinations. Source
text and all previously accepted destinations remain unchanged.


The individually reviewed reciprocal family also identifies **brgyas → brgya²**:
WTS II p. 508 prints **pf. zu ↑brgya sprechen**, and numbered **brgya²** on
p. 503 reciprocates **pf. ↓brgyas sprechen**. Competing **brgya¹** means hundred.
The review supports either reciprocal arrow direction. An optional exact
character offset of two selects past the literal comma-space within the first
PDF run containing `, p`; the entire run remains hash-bound and preserved.
No punctuation stripping or unreviewed homonym inference is introduced.

Run37: **7,605 resolved / 769 residual** target units; HTML unchanged at 4,742
resolved, 544 unresolved, two ambiguous; PDF 2,863 resolved, 113 unresolved,
110 ambiguous. Only this individually reviewed reference gains a destination;
source text, citations, previous destinations and the 23/50/47 fixture remain
unchanged. This is interpretation of an intact reference, not a printing error.


The individually reviewed reciprocal family additionally identifies **bsgrags →
sgrog¹** (II pp. 516/496) and **khyer¹ → ’khyer¹** (II pp. 93/160).
The source introductions are respectively **auch sgrags, pf. zu ↑sgrog** and
**pf. bzw. imp. zu ↓’khyer**. Their numbered destinations reciprocate
**pf. ↓bsgrags** and **pf. ↑khyer**. Both source and destination facsimiles were
checked. The alternate spelling `sgrags` is retained in the individually bound
claim; it does not become a lookup alias. Competing homonyms remain distinct.
The review admits these exact introductions, retaining the original spans and
literal arrows, and rejects incorrect spellings, intervening prose and stale
source bindings. No printing error is asserted.

Run39: **7,607 resolved / 767 residual** target units; HTML unchanged at 4,742
resolved, 544 unresolved, two ambiguous; PDF 2,865 resolved, 113 unresolved,
108 ambiguous. Only these two reviewed references gain destinations. Source
text, citations, previous destinations and the 23/50/47 fixture remain unchanged.


### Reviewed reciprocal perfect-and-future identities

Two individually reviewed references now connect **gtad¹ ↔ gtod¹**. WTS IV
p. 26 gives `pf. und fut. zu ↓gtod`; p. 55 reciprocates with
`pf. und fut. ↑gtad`. Both numbered entries concern giving, transferring and
entrusting. The competing gtad² concerns negative energy; gtod² gives the
perfect btod, while gtod³ is a deity causing muteness. These are exact identity
interpretations, not printed corrections or automatic homonym-1 selection.
The separate `reviewed_printed_reciprocal_perfect_future` basis replays both
complementary introductions, reciprocal arrow direction, numbered heading,
article bounds, positioned runs, immutable hashes and exact source occurrence.
It rejects mixed or noncomplementary paradigms and unbound alternate spellings.

Run40: **7,609 resolved / 765 residual** target units. HTML remains 4,742
resolved / 544 unresolved / 2 ambiguous; PDF is 2,867 resolved / 113 unresolved /
106 ambiguous. All previous accepted destinations, text, citations and the
23 reviewed collections / 50 members / 47 resolved targets remain unchanged.


### Reviewed raised reciprocal homonym qualifier

An individual review connects **thul¹ → ’thul¹**. WTS IV p. 282 prints
`pf. zu ↓’thul aufsteigen`; p. 376, under ’thul¹, explicitly reciprocates
`pf. ↑¹thul`. The printed raised numeral identifies thul¹ independently of
its competing homonyms. Both facsimiles were checked. The source reference
was correctly extracted; this is an identity interpretation, not a printing
correction. Other unresolved homonyms retain their uncertainty.

The separate `reviewed_printed_qualified_reciprocal_perfect` basis verifies the
source's numbered canonical heading and the destination's exact numbered
heading, reciprocal passage, upright raised numeral, adjacent italic target,
shared body baseline, article bounds and immutable hashes. The literal source
and reciprocal runs remain intact; no default homonym selection is introduced.

Run41: **7,610 resolved / 764 residual** target units. HTML remains 4,742
resolved / 544 unresolved / 2 ambiguous; PDF is 2,868 resolved / 113 unresolved /
105 ambiguous. Only this reviewed reference gains a destination; prior accepted
relationships, source text, citations and the 23/50/47 fixture remain unchanged.


### Reviewed perfect-and-imperative identities

Two source-bound reviews establish **gyur¹ ↔ ’gyur¹** from the complementary
`alttib. auch gyurd pf. und imp. zu ↓’gyur` (WTS II p. 239) and
`pf. und imp. ↑gyur` (p. 379). Both printed facsimiles were inspected. These
are correctly parsed references whose numbered identities needed review,
not errors in the printed dictionary. The alternate `gyurd` is preserved as
source evidence, never introduced as a lookup alias.

The `reviewed_printed_reciprocal_perfect_imperative` basis requires exact
introductions, numbered canonical headings, hashes, bounded article spans,
upright grammar/arrow and italic target runs. A reciprocal line wrap is
accepted only directly before the arrow after `zu`, with adjacent baselines
and a bounded return in the same column. Other prose, qualifiers, fonts,
distant geometry and unknown glyphs fail closed. No ordinary parsing rule
or automatic homonym preference is changed.

Run42: **7,612 resolved / 762 residual** target units. HTML remains 4,742
resolved / 544 unresolved / 2 ambiguous; PDF is 2,870 resolved / 113 unresolved /
103 ambiguous. Only these two reviewed references gain destinations; prior
accepted relationships, source text, citations and the 23/50/47 fixture remain
unchanged. The original 7,582 / 792 checkpoint remains the comparable baseline.

### Batched grammatical-reference review

`badw_grammatical_references.py` shares exact grammatical templates and
complementarity checks across reciprocal perfect, future and imperative reviews.
Historical annotation bases and their geometry contracts remain valid; their
records are unchanged. New reviews name a supported grammatical pattern and
still require individually inspected facsimiles, exact numbered headings,
source/destination hashes, article-bounded passages and positioned typography.
A return arrow alone never selects a homonym. A PDF run ending inside a longer
word is rejected as reciprocal evidence.

Run43 adds ten individually reviewed links: **bsgrag → sgrog¹**, **rgyoṅ →
brgyaṅs¹**, **ños → ño²**, **’groṅ¹ ↔ ’groṅs¹**, **’joms → bcom¹**, **’khol² →
khol²**, **’khon bzuṅ → ’khon ’dzin¹**, **’khu → ’khus¹**, and **’khyer¹ →
khyer¹**. These resolve identity ambiguities, not parser defects or printed
errors. All 103 PDF ambiguities were examined mechanically: 19 occurrences had
21 candidate return relationships; ten were accepted after source review.
The remaining 93 occurrences retain explicit deferral reasons in ignored
`work/badw_full_reader_20261020/grammatical_batch43/adjudicated_queue.jsonl`.
Two misleading return hints ended inside longer words and were rejected.
In particular, reciprocal arrows shared by competing **khrol/’khrol** homonyms
do not establish a unique identity.

Reproduce discovery against the certified pre-batch reader:

```sh
python3 scripts/discover_badw_grammatical_references.py \
  --reader work/badw_full_reader_20261020/run42 \
  --census work/badw_full_reader_20261020/residue_after_perfect_imperative_run42.jsonl.gz \
  --output work/badw_grammatical_queue_fresh
```

The queue pins the reader, census, entry index, canonical objects, source
occurrences, competing identities and bounded destination runs with PDF locations.
Its support classifications are discovery hints, never accepted annotations.
Discovery of all 103 cases took approximately six seconds.

During investigation, use the existing builder with a JSON list of affected
witness IDs and a certified baseline. An optional `--projections` file containing
only those existing projection records avoids streaming the complete corpus:

```sh
python3 scripts/build_badw_full_reader.py \
  --projections work/badw_full_reader_20261020/grammatical_batch43/affected_projections.jsonl \
  --witness-ids work/badw_full_reader_20261020/grammatical_batch43/affected_ids.json \
  --baseline-reader work/badw_full_reader_20261020/run42 \
  --output work/badw_affected_check_fresh
```

This reuses the full source verification, annotation replay, projection and
relationship checks, verifies baseline shard hashes, and checks destination
membership against the certified catalog. Its output is explicitly marked
`investigation_only`; it is not a complete reader or batch certification.
The ten-witness check took 3.5 seconds. Full builds still certify all witnesses,
accepted relationships, citations and the 23/50/47 checkpoint; phase costs are
recorded in `build_timing.json` before considering additional caching.

Run43 certification: **7,622 resolved / 752 residual** target units; PDF is
2,880 resolved / 113 unresolved / 93 ambiguous, and HTML is unchanged. The
29,878-witness differential found precisely ten improved references and 29,868
byte-identical entry files. Source text, citations, components, prior accepted
destinations and the 23/50/47 checkpoint are unchanged. Browser validation passed
all ten new keyboard/history/source journeys, 56 member journeys, 82 citation
journeys and 58 facsimile checks at desktop and three mobile/tablet widths,
with no browser errors. The rendered mobile page was visually inspected.

One complete build took 836 seconds: 767 seconds in projection/evidence
validation, 14 seconds in source verification/copying, and 19 seconds in
serialization. Projection/evidence validation is the measured bottleneck;
source-copy caching would not address it. The focused suite passed 673 tests;
the required release regressions passed 315 tests and 62 subtests. Existing
status warnings remain unchanged; no release artifacts were rebuilt.
