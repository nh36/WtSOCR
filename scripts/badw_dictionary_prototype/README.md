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
`work/badw_full_reader_20261020/run45` instead. The earlier bounded script
experiment remains at `work/badw_full_reader_20261020/loc14`.
Open <http://127.0.0.1:8767>. Try **mkhar ’gro**, **ṅar**, **rños**, and **ṅu**,
then search any acquired LoC or Tibetan headword. The unfiltered catalogue and
previous/next use the Tibetan ordering described below. Nonempty searches rank
exact primary headwords, exact accepted alternatives, primary prefixes, alternative
prefixes, primary word/syllable boundaries, alternative boundaries, primary
substrings, and alternative substrings, in that order. Each bucket retains
Tibetan catalogue order. LoC whitespace and Tibetan tsheg/shad mark boundaries;
search keys retain punctuation and orthographic distinctions. Enter in the search
input opens the highest-ranked result; typing alone preserves the open entry.

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
  --reader work/badw_full_reader_20261020/run44 \
  --output work/badw_residual_fresh.jsonl.gz
```

The compact ledger retains every residual occurrence, literal source component,
source span/binding, facsimile/source links and exact candidate identities.
Its diagnostic buckets are **provisional**, not seven-way scholarly adjudications:
336 HTML and three PDF identity/manifestation mismatches; 208 HTML and 110 PDF
missing exact identities; two HTML and 91 PDF ambiguities. The diagnosed empty-label parser
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

Run44 continues with the bounded compound-future family: **rgyoṅ → brgyaṅ¹**
(WTS 2 pp. 461/505) and **’gyed → dgye¹** (WTS 2 pp. 382/333).
The printed source paradigms name a preceding perfect form; each numbered
destination explicitly returns to the source with `fut. zu`. All competing
homonyms were inspected. One bounded declarative production supports these two
individually bound reviews; no headword-specific validation branch is added.
Historical annotations remain byte-for-byte intact.

Current census: **7,624 resolved / 750 residual** target units. HTML remains
4,742 resolved / 544 unresolved / 2 ambiguous; PDF is 2,882 resolved / 113
unresolved / 91 ambiguous. Across the two batches, 12 of the original 103 PDF
ambiguities are accepted and 91 deferred. Decisions and explicit reasons are in
`work/badw_full_reader_20261020/grammatical_batch44/adjudicated_queue.jsonl`.
Semantic return references and shared returns remain insufficient evidence;
the interleaved sense-number typography in **’khris** requires a separately
guarded mechanism. No printed error is asserted.

The two-witness investigation check took 3.3 seconds. The second full build took
828 seconds (761 in projection/evidence validation). Its 29,878-witness
differential found exactly two improved references and 29,876 byte-identical
entries; source text, citations, existing destinations and the 23/50/47 checkpoint
remain unchanged. The focused suite passed 687 tests, Node passed 15 tests, and
the required regressions passed 315 tests and 62 subtests. Browser validation
passed all 12 batch journeys, 56 member journeys, 82 citation journeys and 58
facsimile checks at widths 1440, 320, 390 and 768, with no browser errors.
Two complete builds were performed across these batches, totaling about 28 minutes.

Run45 repairs two source-bound return references. **bkye → ’gyed** is explicit
in both the printed entry (WTS 1 p. 215) and its acquired HTML heading. Parsing
was correct; the unresolved numbered editorial URL did not establish identity
with the acquired unnumbered PDF witness. A new reviewed grammatical-identity
basis validates the exact DOM anchor and bounded heading introduction against
the complementary printed paradigm in ’gyed (WTS 2 p. 382). It does not equate
HTML homonym 1 with unnumbered PDFs generally. The accepted ’gyed → dgye¹
interpretation is unchanged.

**’khri → ’khris¹** (WTS 2 pp. 163/166) is established by the destination's
first sense, `pf. zu ↑’khri`; competing ’khris² lacks that paradigm. Overprinted
copies of the first sense number and period interleave with the grammatical
run, yielding `.  pf. zu ↑’khri`. The shared validator now admits the exact
reviewed lookup offset only with same-baseline overlapping glyph evidence at
the start of the destination article. Source literals and sense labels remain
intact; later senses, intervening text, incompatible fonts and displaced glyphs
are rejected. No parser rewrite, source correction or printed error is asserted.

Discovery screened all **91 PDF ambiguities** in 6.8 seconds: seven occurrences
have nine candidate return identities, but only ’khri has the verified
overprinted-first-sense structure. One is accepted and 90 remain deferred;
previous adjudications are retained in
`work/badw_full_reader_20261020/grammatical_batch45/adjudicated_queue.jsonl`.
The next family is HTML-to-PDF grammatical identity: screening the 336 baseline
HTML identity mismatches found 26 grammatical occurrences including bkye.
The other 25 are discovery candidates, not accepted links; their queue is
`grammatical_batch45/html_grammatical_identity_queue.jsonl` under the same work root.

Current census: **7,626 resolved / 748 residual** target units across 29,878
witnesses. HTML has 4,743 resolved / 543 unresolved / 2 ambiguous; PDF has
2,883 resolved / 113 unresolved / 90 ambiguous. The full differential finds
exactly two improved references and 29,876 byte-identical entry files. All
source text, citations, components, prior accepted destinations and the
23/50/47 multiple-target checkpoint remain unchanged. Historical annotation
rows are byte-for-byte unchanged; two reviews are appended.

The two-witness investigation check took 4.6 seconds. One complete build took
936 seconds, including 848 seconds in projection/evidence validation. The fast
path also now selects HTML witnesses using stable reader identities, matching
the catalog rather than the packet's editorial URL identity. The focused suite
passed 711 tests; Node passed 15 tests; the required regressions passed 315 tests
and 62 subtests. Existing status warnings remain unchanged; release artifacts
and frontend assets were not modified.

Browser certification passed all 14 grammatical batch journeys (including the
new bkye return link), keyboard/history navigation, 56 member journeys, 82
citation journeys and 58 facsimile checks at widths 1440, 320, 390 and 768,
with no browser errors. Initial catalog load took 298 milliseconds in the local
test. The rendered mobile page was visually inspected.

## Reviewed original printed pages for editorial HTML

The optional HTML facsimile layer uses `data/badw_html_print_pages.json`.
Each accepted record binds an exact acquired HTML URL and SHA-256, its own
homonym, and a checked printed heading/definition to a registered original
scan and a one-based physical PDF page. It performs no lexical matching and
never assigns pages to PDF-derived witnesses. Existing BAdW PDF sources are
unchanged. HTML entries without a reviewed match retain their editorial link.

Generate the shared single-page PDFs before building the reader:

```sh
python3 scripts/badw_html_print_facsimiles.py \
  --scans-root /path/to/checkout-containing-pdfs \
  --output work/html-print-pages
python3 scripts/build_badw_full_reader.py \
  --print-facsimiles work/html-print-pages/manifest.json \
  --output work/html-print-reader
python3 -m http.server 8806 --bind 127.0.0.1 --directory work/html-print-reader
```

The registered scans must be locally available; this does not download or
publish them. Derivatives and manifests stay in ignored `work/`. The reader
copies each distinct prepared page once to `sources/print/`. Complete original
scans remain in the private source cache and are never linked into the served
reader. Provenance retains source identities, checksums, physical pages and crop
coordinates without private paths. PDF page boxes provide a visual crop, not
redaction: neighbouring image data may remain in a derivative. These derivatives
are local research material; do not publish them externally without a separate
source-publication decision.

Preparation verifies the registry and original checksums. `pypdf` (the existing
`>=6.10,<7` development dependency) copies one physical page and sets its MediaBox
and CropBox to reviewed PDF coordinates, preserving image data and resolution.
It does not rasterise, rescale or recompress images. IDs hash the original
checksum, physical page, crop rectangle and transformation version
`pdf-page-boxes-v1`; repeated entries share the same derivative. Both manifest
and derivative hashes are checked at build time. Printed page numbers are
explicit reviewed records, never a volume-wide offset guessed from pagination.

The inspected WtS 1–34 scan has landscape spreads through physical page 1076
(the last has a blank right side), then portrait title matter and single pages;
physical page 1081 is volume 5 page 1. WtS 35–51 has single printed pages and
inserted fascicle/volume matter; physical page 350 is volume 6 page 1. WtS 8-b
and 9-m are single-page scans. Two text columns do not mean two printed pages.
These observations do not authorise automatic cropping of unreviewed pages.
The published spread at physical page 40 uses a reviewed noncentral gutter,
438 points from the left; full height and outer margins are retained. The two
sides are volume 1 pages 14 and 15. The new spreads at physical pages 41–44
use individually reviewed gutters at 441, 439, 438 and 439 points. Genuine
single pages retain their complete boxes. Rotated pages and invalid geometry
fail closed.

Current HTML-only coverage is **18,038 witnesses: 163 exact, 11,287 candidate-only,
and 6,588 without a usable candidate** (previously 32 / 11,418 / 6,588).
There are **48 distinct derivatives: nine cropped printed pages and 39 genuine
single pages**. After the article-boundary correction below, the expanded batch
retains 131 links on 38 pages from 40 inspected
printed pages across all four registered scan families. Two inspected pages
produce no accepted links. Thirteen proposals were rejected and seventeen deferred.
This is 3.275 retained verified entries per inspected page; it is not an automatic matching
accuracy estimate, since every acceptance still required scan inspection.

`data/badw_html_print_alignment.json` holds compact page certificates and explicit
negative decisions. `data/badw_html_print_alignment.generated.json` is their
reproducible expansion, separate from the initial manual ledger. Each accepted
witness pins an acquired HTML checksum, C6 heading anchor and definition component
checksum, heading column, explicit printed homonym (including absence), and a
scan-reviewed distinguishing definition. An absent printed numeral is never
defaulted to homonym 1. An unnumbered printed article may correspond to an editorial
number only through its individually reviewed definition, not the headword alone.
Candidate edges locate evidence; they confer no acceptance. Headers, continuation
text, competing meanings and weak short definitions are rejected or deferred.

Recompile or check the ledger against an existing complete reader and the pinned
C6/C11 ignored inputs (no source acquisition is performed):

```sh
python3 scripts/badw_html_print_alignment.py \
  --reader work/existing-reader --check --inventory work/html-print-inventory.json
```

Omit `--check` only after reviewing changed certificates to regenerate the expanded
ledger. The complete-reader build checks both ledger hashes; derivative preparation
checks registered original hashes. The compiler rejects stale anchors, HTML,
definition evidence and candidate input files. The inventory categorises all HTML
witnesses without silently certifying historical candidates. Current categories:
163 reviewed exact pages; 5,560 dual-script heading candidates with unverified
pages; 4,691 one-field lexical candidates; 1,036 competing exact headings; 6,588
without a usable candidate. The historical HTML handoff contains no independently
accepted lexical identities. Running-header and continuation counts outside the
reviewed batch are unknown; they cannot be inferred from candidate confidence.
Candidate volumes remain scan-family locators, not verified printed pagination.

Historical candidate locators break down as follows. A witness with edges in
several scans appears once in the multiple-family row; reviewed links may have
superseded those historical locators.

| Candidate scan family | Reviewed | Dual heading | One-field | Competing | No candidate |
| --- | ---: | ---: | ---: | ---: | ---: |
| WtS 1–34 | 52 | 1,810 | 1,056 | 392 | 0 |
| WtS 35–51 | 32 | 2,181 | 1,896 | 399 | 0 |
| WtS 8-b | 27 | 1,031 | 1,038 | 160 | 0 |
| WtS 9-m | 35 | 496 | 579 | 55 | 0 |
| Multiple families | 13 | 42 | 122 | 30 | 0 |
| No historical locator | 4 | 0 | 0 | 0 | 6,588 |

Accepted links by printed volume are 1: 26, 5: 61, 6: 5, 8: 32 and 9: 39.
By registered scan they are WtS 1–34: 57, WtS 35–51: 35, WtS 8-b: 32 and
WtS 9-m: 39. The new batch reviews volume 1 pp.16–23, volume 5 pp.3–10 and
354–361, volume 8 pp.2–9 and volume 9 pp.13–20. Volume 1 p.21 has no accepted
identity; volume 5 p.360 contains continuation text only. Examples include
kamalaśīla (1:17), kalapiṅka (1:23), ḍa ma ru (5:10), mda’ mo¹ (5:355),
ba thag¹/² (8:4), ba spu² (8:6) and ma gcig lab kyi sgron ma (9:18).
Ka riṅ is rejected for a printed/editorial sense mismatch; competing ka ru
homonyms and short insufficiently distinctive glosses remain deferred.

The four newly inspected spreads use gutters at 441, 439, 438 and 439 points
(physical pages 41–44), retaining full height and outer margins. Seven of their
eight printed sides have accepted links. These are explicit geometry reviews,
not a universal half-width rule. All other new pages retain their full boxes.
There are no additional exceptional transformation overrides or pending crop
reviews among published pages. The existing crosswalk covers volumes 2–4 and
must not be extrapolated across inserted titles or pagination changes. Physical
1076/1077 were separately checked as a blank-half/title transition; neither is
published by this batch.

The method removes repetitive page/provenance authoring and shares derivatives;
it does not remove scholarly identity review. A larger batch needs fresh heading,
definition, neighbour and folio inspection, particularly for homonyms and long
articles, plus reviewed gutter coordinates for each new spread. Manual review
elapsed time was not instrumented, so no links-per-hour claim is made. The next
batch should record review time separately from compiler/build time.
Certificate checking plus the complete HTML inventory took 16.75 seconds; the
fresh full-reader build took 829.33 seconds (mostly existing evidence projection).

The reviewed examples include ka ba¹ and its compounds (volume 1 pp. 14–15),
da¹/² and ḍā ki ma¹ (volume 5 p. 1), da ko¹ and da ci¹ (p. 2), mda’ rgyus¹
(p. 353), na¹/² (volume 6 p. 1), rnam byuṅ¹ (p. 251), ba¹/²/³ and ba ka¹
(volume 8 p. 1), ma¹/² (volume 9 p. 1), and ma⁵/ma ki ta¹ (p. 12).
Long entries link to their heading page. A running `ma` header on page 12 does
not identify the start of ma⁴. Raised `ka` beside ka ba is a cross-reference,
not a second homonym. **’gyur¹ is PDF-derived** in the current catalogue and
therefore retains its existing born-digital facsimile without an extra link.

Focused checks:

```sh
python3 -m pytest tests/test_badw_html_print_alignment.py tests/test_badw_html_print_facsimiles.py tests/test_badw_full_reader.py -q
node --test tests/badw_dictionary_prototype.test.cjs
BADW_READER_URL=http://127.0.0.1:8806 node tests/badw_html_print_facsimiles.browser.cjs
```

The browser command also needs Playwright and Chrome as described above. Its
screenshot directory is controlled by `BADW_SCREENSHOTS` (default:
`work/html-print-browser`). Full-reader certification and the source-integrity
differential must accompany changes at a corpus milestone.

The fresh 29,878-witness milestone build preserves catalogue order, search keys,
source text, all accepted relationships and the reference census (7,626 resolved
targets; 748 residuals). All 11,840 PDF witness bodies and 1,377 existing PDF
assets are byte-identical to the merged PR #9 baseline. Focused checks pass
(33 Python tests; 19 Node tests), as do the required 315 regressions with 62
subtests. The full Python suite has 2,064 passes and the two inherited failures
(external-publications checksum and WtS 8-b p. 409 line 73 evidence). Chrome
certification passes all 165 links, opens all 48 prepared PDFs, and checks
desktop/mobile views without browser errors. The existing full-reader Chrome
suite also passes search, history, keyboard and grammatical-reference journeys.


PR #10 independent evidence audit (historical; corrected below)

The earlier follow-up audit reported a reread of all 133 new assignments, including all 31 whose
HTML evidence has at most 12 alphanumeric characters, all six explicitly
numbered printed headings, every accepted spread side, and the remaining
records across all four scan families. Its claim that all 133 survived was
premature: review subsequently identified two running-header anchors and one
neighbouring-compound anchor. The correction below supersedes that conclusion
and its 165-link coverage figure. The existing 32 baseline links are unchanged.

Each compact assertion now separates `print_observation` (actual heading,
explicit numeral or absence, printed evidence and discriminating context) from
`definition_evidence` and its hashed HTML definition component. The editorial
primary headword remains in the expanded record. Every audited case has its own
printed observation and exclusion/context statement in
`data/badw_html_print_alignment.json`; the expanded ledger is generated, not an
independent source of scholarly authority. Eighteen printed headings differ
from the editorial primary form, mostly by alternatives or numeral notation.
One substantive reading is printed `mdud lha sum brgyad drug bcu`, versus HTML
`mdud lha sum brgya drug bcu`. Both readings are retained without changing the
reader headword. Numbered cases are da phan, ba dkar, ba thag 1/2 and ba spu 1/2.
Generic glosses such as `ein Vogel` require heading/context discrimination;
there is no arbitrary minimum quote length.

The compiler binds the observation to the same heading/evidence anchor, scan
family, physical page, printed folio, column and geometry, and verifies source,
anchor and HTML component hashes. It rejects conflicting anchor reuse unless an
explicit reviewed multi-witness relationship explains it. A previously negative
source/anchor pair requires a checksum-bound reconsideration. It also verifies
the complete reviewed projection in the expanded ledger before preparation.
These checks establish mechanical consistency, **not automatic verification of
printed wording**: a false transcription or an adjacent definition attributed
to the same anchor still requires human detection. The retained observations
are explicitly labelled human visual transcriptions.

All 48 shared derivatives remain byte-identical: nine cropped spread sides and
39 complete single-page views. No gutter, orientation, homonym assignment or
page-location correction was needed. Original scans remain private and unchanged.
The rendered contact sheets and ordinary Chrome PDF views supplement the
source-page reread. PDF page boxes are visual crops, not secure redaction;
these derivatives remain local research material pending a separate distribution
and rights decision.

The next queue is reproducible with:

```sh
python3 scripts/badw_html_print_alignment.py --bodies work/html-print-alignment-20261024/bodies.json --check --queue data/badw_html_print_review_queue.json
```

It prepares 48 unreviewed physical pages (12 per family), with 683 page-level
candidate incidences covering 678 distinct HTML witnesses, not accepted identities. Folios and crop geometry are
null until inspected. Each family contributes eight density-ranked pages, two
competing/numbered-homonym controls and two sparse-definition controls.

| Scan family | Proposed physical pages, in review priority | Candidate incidences |
| --- | --- | ---: |
| WtS 1–34 | 86, 159, 81, 120, 99, 62, 222, 215, 46, 36, 162, 1193 | 235 |
| WtS 35–51 | 682, 683, 733, 859, 377, 636, 616, 723, 1070, 1071, 1106, 1052 | 179 |
| WtS 8-b | 56, 322, 358, 480, 487, 186, 263, 227, 199, 410, 247, 284 | 154 |
| WtS 9-m | 74, 198, 359, 151, 360, 27, 316, 364, 372, 321, 152, 154 | 115 |

Dual-script agreement and candidate density rank preparation only. Competing
homonyms, continuation starts, running headers, sparse glosses and missing
crosswalk coverage remain likely obstacles. Each new spread needs its own gutter
review; no offset or geometry is extrapolated. The next batch must record separate
timers for selection, actual facsimile review, evidence entry, generation, tests
and full certification before making an acceptance-throughput claim.

The follow-up scan reread and evidence entry took a combined 8 min 49 s; those
phases were interleaved, so isolated visual-review time and accepted links per
hour of actual review are **not measured**. No pure-review throughput is inferred
from that interval. All 133 audited links were retained on 38 linked printed
pages (3.50 retained links/page); this is an audit retention rate, not new
acceptance throughput. The original batch inspected 40 printed pages, accepted
133 witness links and recorded 28 rejected/deferred cases (17.4% of 161 recorded
witness decisions). Queue preparation and build timings are computational costs,
not scholarly review time. Substantial new review remains outside PR #10.

Follow-up certification: 47 focused Python tests, 19 Node tests and the required
315 regressions (62 subtests) pass. The full Python run has 2,076 passes and the
same two inherited failures described above; two subsequent queue tests also
pass in the focused run. Repository hygiene, generated status and compilation
checks pass. Certificate/source-hash checking took 35.69 s and deterministic
queue preparation 34.24 s; neither measures visual review.

A fresh full reader retains all 29,878 witnesses and the 7,626 resolved / 748
residual reference census. Differential checks preserve every source body,
catalogue/search order, relationship, all 11,840 PDF witness bodies and 1,377
cached assets. Against the pre-audit reader, only the 133 new links' provenance
changes; all 48 derivative PDFs are byte-identical. Chrome checks exercise all
165 assignments and open all 48 PDFs, including desktop/mobile comparisons;
the full-reader search/history/keyboard/reference journeys pass without browser
errors. The local preview is http://127.0.0.1:8810/. Screenshots and build logs
remain in ignored `work/html-print-evidence-audit/`. The historical 69 release
reproduction differences were not rerun during this audit; `release/current`
is unchanged.

Both Chrome runners exited successfully. The facsimile runner took several
minutes to finish shutdown after emitting its assertion summary.


PR #10 article-boundary correction (supersedes the historical audit above)

The second source-image/QA audit covers every one of the original 133 new
assertions. It retains 130 unchanged, corrects one anchor on the same printed
page, and defers two. No printed-page destination or crop geometry changed.
The compact per-assertion results, previous assertion hashes and reasons are in
`article_boundary_audit` in the existing certificate; this preserves the errors
rather than rewriting their history.

| Witness | Incorrect binding | Source finding and disposition |
| --- | --- | --- |
| da yaṅ | WtS 1–34 physical 1090, line 55 | Running header. The article begins at 89 and its definition occupies 89–91. No C6 heading anchor exists at 89; deferred, editorial link retained. |
| mdun | WtS 35–51 physical 106, line 47 | Running header. The article begins at 59, with definition at 60. No C6 heading anchor exists at 59; deferred, editorial link retained. The following sense numeral is not a homonym numeral. |
| ba tshwa | WtS 8-b physical 17, line 77 | Neighbouring ba tshwa can, defined as salzig. Rebound to existing anchor 63, ba tshwa auch ba tsha, with its own Kuhsalz/Soda evidence at 63–66; 77–78 explicitly excluded. Same derivative. |

Each retained assertion now pins the actual reviewed heading line, its own
selected evidence lines, excluded adjacent lines where needed, and the SHA-256
of the exact source-faithful QA rows. The printed observation remains separate
from the editorial identity and hashed definition component. Two-column QA can
interleave articles: mdud pa at physical 105 line 40 uses definition lines
73–74, while ba gam at physical 16 line 41 uses 66–67. Intervening other-column
material is explicitly excluded. QA `headword_line` itself is not an article-start
classification and can include running headers and continuation text. The
compiler checks the reviewed spans and bindings; it cannot independently prove
a human transcription or article-boundary judgement from their declarations.

The generated ledger is compared against the complete deterministic projection
of the reviewed certificate, including source URL, editorial headword, homonym,
review basis, evidence identities and input hashes. Rehashing a modified expanded
record does not make it acceptable. The actual compiler `--check`, using private
source inputs and current HTML bodies, passes before derivative preparation.
Inventory and queue exclusion both use `(source_url, html_sha256)`, matching
reader attachment; a reacquired URL with changed HTML is no longer counted as a
current reviewed attachment. There are 131 accepted new certificate records and
32 baseline records; all 163 are attachable to the current acquired corpus.
Coverage is 163 verified / 11,287 candidate-only / 6,588 without candidates.
The 48-page next queue was regenerated, with no new acceptances.

All 48 existing single-page derivatives are retained with identical bytes:
nine cropped spread sides and 39 single pages. Their original scans remain
unchanged outside the served tree. Crop boxes are visual crops, not redaction;
derivatives remain authorised local research material.

Correction certification: 63 focused Python tests, 19 Node tests and the required
315 regression tests (62 subtests) pass. The full Python suite reports 2,094
passed (62 subtests) and the same two inherited failures: the bibliography
external-publications input checksum and residual ledger WtS 8-b p. 409 line 73.
The historical 69 release-reproduction differences were not rerun here.
Repository hygiene, generated-status check and required Python compilation pass.

A fresh 29,878-witness reader is served locally at http://127.0.0.1:8811/.
Differential checks preserve all 11,840 PDF witness bodies byte-for-byte, all
1,377 cached source assets, source text, citations, relationships, catalogue
order, search keys and the 32 PR #9 links. Cross-reference targets remain
7,626 resolved / 748 residual. Against the previous PR reader, changes are
limited to 131 provenance records and two removed/deferred print links; all
48 derivative PDFs are byte-identical. No private paths, original-volume routes
or symlinks are present. Local evidence and screenshots are under ignored
`work/html-print-boundary-correction/`; `release/current` is unchanged.

Chrome certification passes both runners: all 163 attached HTML assignments at
1440/390 pixels, all 48 single-page PDFs opened in Chrome, three mobile PDF
comparisons, no browser errors. The full reader journeys preserve 61 apostrophe
matches and 447 gyu matches, global navigation and grammatical/citation links.
Search issues no entry-body requests; mean filter time is 2.8–3.5 ms on this run.
The corrected ba tshwa page and desktop/mobile presentation were inspected;
da yaṅ and mdun correctly retain editorial-only source access.

### Full-corpus mechanical proposal engine (after PR #10)

PR #10 was merged normally at `7039a5bd62319b8119394263a54488c31ef7d707`.
The separate automation engine does not change its 163 attachable reviewed links,
manual certificates, reader, original scans, PDF witnesses or release files.
This is an executed proposal engine, **not a validated automatic link publisher**.

Run offline against the existing local acquisitions (Python 3, pypdf and Poppler):

```sh
python3 scripts/run_badw_html_print_alignment.py \
  --all-volumes --resume --output work/html-print-full-alignment
python3 scripts/render_badw_alignment_review.py --run work/html-print-full-alignment
python3 -m http.server 8812 --bind 127.0.0.1 \
  --directory work/html-print-full-alignment/report
```

Input preparation (infrastructure hardening, v2.1):

```sh
# Restore the complete private reader/acquisition assets, then optionally rebuild:
python3 scripts/build_badw_full_reader.py --output work/alignment-source-reader
python3 scripts/prepare_badw_alignment_inputs.py \
  --reader work/alignment-source-reader --output work/html-print-inputs
python3 scripts/run_badw_html_print_alignment.py \
  --all-volumes --inputs work/html-print-inputs --output work/alignment-run --resume
```

A public Git checkout alone cannot reconstruct private BAdW acquisitions. Restore
these from the registered local source/cache environment; this command does not
reacquire or redistribute the corpus. The reader build's acquisition dependencies
are listed at the start of `build_badw_connected_reader.py` (CACHE, CANON, INDEX,
SEEDS, PDF, HTML and BIB), plus the full-reader projection/baseline/supplement
arguments. They include reviewed semantic evidence, not just downloadable scans.
An already certified complete reader is an equivalent input; no OCR or reader
rebuild is required for alignment. The preparer verifies every HTML shard against
its catalogue checksum and requires exactly 29,878 entries / 18,038 HTML bodies.
It writes a portable `bodies.json`, `catalogue.json` and SHA-256 `manifest.json`.
The runner defaults to this bundle, never a historically named directory.
Duplicate, missing, extra, mismatched or malformed body identities fail explicitly.

Original source assets: restore the four files at the paths in
`data/source_pdfs.tsv`; that registry supplies their exact SHA-256 identities:

| Scan | Pages | SHA-256 |
| --- | ---: | --- |
| WtS 1–34 | 1352 | `20021354ae3c838a5641f59af4a4421c1e59e6b0d2c1760d5fe3f62faeb47c62` |
| WtS 35–51 | 1128 | `8babd045a04876d373631169677eff7fc033066a3ed1f5649aeaaad5eed67239` |
| WtS 8-b | 585 | `f9d94766c88362472576250c34dcc313c55e3036e19dcfe454e0a82b9d1d4263` |
| WtS 9-m | 401 | `7c9366616d41c2788088085208e5395111d19abb31bb801a03443af14910ffeb` |

The tracked `release/current/qa/*/*_line_zones.tsv` files and reviewed ledgers
supply the other mandatory source evidence. No source download occurs. Optional
historical corroboration can be included with preparer `--anchors` and `--edges`;
these are respectively the JSONL outputs of `badw_source_matcher.py` and
`badw_identity_handoff.py` (their `--help` documents reconstruction inputs).
Without them the runner explicitly records zero historical anchors/edges; all-QA
start discovery and matching still run, and C6-origin metrics mean “not supplied”.
Historical evidence is not essential truth or a hidden default dependency.

Input, PDF and implementation hashes and Python/pypdf/SQLite/Poppler versions
are pinned in `inputs.json`. Changed inputs require a fresh run directory.
Serve **only** the report subdirectory, never the run cache, prepared body bundle
or source directories. Images and derivatives remain local research material;
PDF crop boxes are not redaction. No complete source PDF is copied or linked.
Machine JSON is never an attachment ledger: only the separately reviewed
certificate and exact current HTML checksum can authorize reader attachment.

The single-worker runner streams HTML bodies into a SQLite index with a bounded
page cache. It indexes every QA line and physical PDF page, recording actual PDF
geometry and rotation. Embedded PDF OCR is aligned conservatively to QA text;
ambiguous coordinates remain unavailable. All QA lines can propose article starts,
including those absent from C6. Exact Tibetan and LoC indexes, flagged spacing
variants, IDF-weighted definition/citation evidence, competing-heading penalties
and a maximum-weight monotone **page-local** sequence check rank proposals.
C6/C11 evidence is retained as corroboration, never unquestioned boundary truth.
Repeated headings cannot borrow a later same-spelling article's definition;
prefixes of longer observed compounds are flagged. This is structural screening,
not proof that OCR segmentation or a lexical identity is correct.

Each stage commits its SQLite data and checkpoint together. Interrupted stages
roll back and restart; completed stages are reused by `--resume`. `--stop-after`
allows controlled interruption at a named stage (for example `history`). Output
JSON is replaced atomically. Intermediate work requires no agent or human action.
The final JSONL accounts for every HTML witness, including no-candidate cases,
retains ten ranked alternatives plus the omitted-alternative count, and binds
HTML components, QA spans, original checksums and available coordinates. The
private SQLite cache retains the remaining proposals. Stage timing is separate
from deterministic output; `timing-latest.json` describes the latest invocation.

The completed v2 run processed **18,038 HTML witnesses, 3,466 physical scan pages,
352,244 QA lines and 524,606 proposals** across all four registered scan families.
It detected **160,855 article-start hypotheses, 136,626 absent from C6**; these
counts include false and duplicate starts and must not be called printed articles.
Results: **2,342 mechanically supported provisional, 13,288 review-required,
2,408 unresolved**. The 163 reviewed attachable links are an overlapping existing
status, not an additional result category. No new reader links were generated.

| Proposed family | Supported provisional | Review-required |
| --- | ---: | ---: |
| WtS 1–34 | 840 | 4,280 |
| WtS 35–51 | 900 | 4,824 |
| WtS 8-b | 420 | 2,543 |
| WtS 9-m | 182 | 1,641 |

Execution after input hashing took **201.059 seconds**, with **455,835,648 bytes**
peak RSS on macOS. The original timing is saved locally as `timing-full.json`.
A second fresh run stopped after `history`, then resumed to completion. Its
manifest, witness JSONL, validation JSON and sample HTML hashes match the first
run byte-for-byte; a cached resume also reproduces them. The input identity is
`1188853a6888106be7abfa01efef80ef6cea449ebf4c882dca7318c1a085f7df`.
The witness JSONL SHA-256 is
`956b9ba43a650a677c0b7575c73f8df838ce151fe17759b7fd0f3f1693fca5d1`.

Validation deliberately separates boundary compatibility from lexical identity.
Against 131 previously reviewed new links, all expected starts were detected;
the top proposal has 126 correct physical pages and 120 exact starts. This is a
retrospective diagnostic, not independent precision. The eleven errors (five
wrong pages, six same-page wrong starts) are all in the review-required category:
generic evidence, OCR spacing and displaced/incidental headword prefixes cause
false rankings. That category remains quarantined from automatic promotion.

A deterministic, held-out-from-certificates sample of forty supported proposals
was rendered and visually inspected on its actual scan pages, with enlarged
checks of repeated-heading cases. All forty have compatible visible article
headings and physical pages (40/40; Wilson 95% lower bound 91.24%). This coarse
check **does not measure complete lexical or homonym precision**. The local
`report/assessment.json` records that distinction. Printed homonym readings,
complete article extents, unreviewed folios and spread sides remain unverified;
no crop geometry or pagination is extrapolated. Whole-volume sequence alignment
and reliable printed-homonym parsing are not implemented. Consequently **bulk
link promotion is not safe**. The next work is to annotate independent lexical,
homonym and negative boundary examples, evaluate these risk classes separately,
and improve segmentation before any promotion-policy decision.

`report/index.html` displays forty sampled scan images; `report/review.html`
contains their OCR/HTML evidence, alternatives and risk reasons.
`report/exceptions/index.html` paginates all 15,696 review or
unresolved records; their full source/coordinate records allow focused source
inspection, but only the forty sampled pages have rendered images. Complete
machine outputs are local under `work/html-print-full-alignment/`; a second run
is under `work/html-print-reproduction/`. The reader remains at port 8811 and
its source-link coverage remains 163 / 11,287 candidate-only / 6,588 no-candidate.

Certification: engine fixtures cover independent start discovery, a held-out
heading, running-header definition borrowing, neighbouring compounds, generic
definitions, dynamic programming, streamed input and transactional checkpoints.
Chrome passes the full reader journeys and all 163 reviewed links / 48 PDFs,
with no browser errors. Final full Python testing reported 2,105 passed,
62 subtests and the two inherited failures (bibliography
external-publications checksum; WtS 8-b p.409 line73 residual ledger). The known
69 release-reproduction differences remain inherited; release evidence was not
modified. The combined focused alignment/facsimile and repository regressions report
373 passed and 62 subtests passed. The Node suite reports 19 passed. Hygiene,
status and compilation pass. Chrome also passes the review gallery at
desktop/mobile widths and the 157-page exception index with its first page,
without browser errors.

Full-suite scope is `tests/`, excluding ignored worktree copies under `work/`.
On this machine an installed `scripts` package shadows the repository's namespace;
the final invocation explicitly bound that namespace before pytest collection:

```sh
python3 -c 'import sys, types, pathlib, pytest; package = types.ModuleType("scripts"); package.__path__ = [str(pathlib.Path("scripts").resolve())]; sys.modules["scripts"] = package; raise SystemExit(pytest.main(["tests", "-q"]))'
```

### Accuracy and segmentation milestone (engine v3)

PR #11 infrastructure was merged with merge commit
`130581e25e09ca5837d25b3fa61320183792a385`. That merge authorises no
machine-proposed original-print links. The following experiment remains separate
from the 163 reviewed, attachable HTML source links.

The input-preparation procedure above still applies. Run the complete experiment:

```sh
python3 scripts/run_badw_html_print_alignment.py --all-volumes --resume --output work/html-print-validation-final
python3 scripts/evaluate_badw_alignment.py --baseline work/html-print-hardened-final --run work/html-print-validation-final --labels data/badw_html_print_evaluation.json
python3 scripts/review_badw_alignment_cases.py --run work/html-print-validation-final --selection work/html-print-validation-final/evaluation-selection.json
# All page groups, retaining already cached images:
python3 scripts/review_badw_alignment_cases.py --run work/html-print-validation-final
# Explicit additional rendering, never a complete PDF link:
python3 scripts/review_badw_alignment_cases.py --run work/html-print-validation-final --page wts_8_b:17
python3 -m http.server 8813 --bind 127.0.0.1 --directory work/html-print-validation-final/report
```

Serve only `report/`, locally. `groups.html` groups proposals by top proposed
physical page, sorted by candidate density. Cards show OCR heading, coordinates,
provisional extent, HTML definition, competing locations and uncertainty classes.
Images are checksum-bound PNG caches rendered only when explicitly requested.
They are physical-page research views, **not certified single-page derivatives**.
No source PDF or symlink is placed in the report. Separate JSON decisions supplied
with `--decisions` bind HTML/scan/evidence hashes and anchor, require an observation
and accept/reject/defer, and remain ineligible for reader attachment. Changed
underlying evidence invalidates the decision instead of carrying it forward.

`badw_print_structure.py` bounds article text at independently plausible next
headings, including non-C6 headings. It uses horizontal box overlap when available
and excludes other columns; missing coordinates retain an explicitly uncertain
line-order fallback. Bare top-margin headings and repeated same-spelling headings
are flagged. This reduces neighbouring-definition borrowing but is not a complete
article reconstruction: cross-column/page continuations are deliberately not joined,
and a 48-line cap remains. No universal gutter or pagination offset is inferred.
The three-page weighted monotone chain allows skipped articles and supplies
section-consistency diagnostics; it does not force assignments or increase their
acceptance category. Missing geometry limits its interpretation.

Only a numeral before the leading Tibetan cluster is parsed as a *tentative OCR
homonym candidate*. Sense/citation numbers later in the line are excluded. Missing
numbering is unknown, never homonym 1. Neither this parser nor its output establishes
typographic homonym identity. The stricter supported predicate excludes unread or
conflicting homonyms, uncertain starts, coordinates and article extents. No proposal
in this run satisfies that predicate; no stricter automatic-publication class is
claimed.

Full execution processed all 18,038 HTML witnesses and 3,466 physical pages
(352,244 QA lines). It retained 160,855 start **hypotheses**, not articles:
24,229 C6-linked and 136,626 without C6; 524,606 correspondence proposals.
Against the hardened engine-v2 baseline:

| Result | Before | After |
| --- | ---: | ---: |
| Mechanically supported, provisional | 2,342 | 0 |
| Review required | 13,288 | 15,630 |
| Unresolved | 2,408 | 2,408 |
| Already reviewed reader links | 163 | 163 |

All 2,342 formerly supported cases are downgraded. There is no demonstrated new
automatic recovery from review. Top proposal anchors changed for 280 witnesses;
page-local chain membership is 9,991 versus 10,245 section-chain memberships,
with 1,830 membership changes. These are diagnostics, not correct-recovery counts.
The existing reviewed-anchor retrospective improves from 120 to 121 exact starts
and 126 to 127 correct physical pages out of 131 detected cases; it is not an
independent precision estimate.

`comparison.json` includes overlapping uncertainty counts by scan family. Totals:
unread/conflicting homonym 15,630; uncertain page/column 14,871; incomplete extent
14,182; unreviewed folio/crop 15,276; uncertain start 3,701; generic/absent definition
4,346; header/continuation risk 1,020; neighbouring compound 33; OCR spacing 968;
missing historical identity edge 5,564; competing location/identity 2,552.
These are deterministic screening flags, not independently adjudicated error counts.

The separate `data/badw_html_print_evaluation.json` contains 32 source observations:
four per scan family and baseline supported/review stratum, selected by fixed seed
`20261026-independent`. Alternating development/held-out assignments were fixed
before inspection; labels were not used to tune the algorithm. The labels include
scan, HTML, QA-line, render and evidence identities, actual observations, unknowns,
and distinct heading/start/page/lexical/homonym/own-evidence/crop judgments.
Changed predicted anchors or evidence do not inherit a positive judgment blindly.

| Independent diagnostic | Correct / known | Unknown | Wilson 95% interval |
| --- | ---: | ---: | --- |
| Heading / article start | 30 / 32 | 0 | 79.85–98.27% |
| Physical page | 29 / 31 | 1 | 79.28–98.21% |
| Lexical article identity | 26 / 31 | 1 | 67.37–92.91% |
| Printed homonym | 1 / 3 | 29 | 6.15–79.23% |
| Evidence belongs to article | 17 / 20 | 12 | 63.96–94.76% |
| Certified folio/crop | 0 / 0 | 32 | unavailable |

The 16 formerly supported sampled proposals have compatible starts/pages/lexical
identities (16/16, lower Wilson bound 80.64%), but only one known homonym and twelve
known own-evidence judgments. The held-out half has 15/16 correct lexical identities
(71.67–98.89%) and no established homonym labels. These small stratified samples
cannot establish population precision; no article-recall denominator is available.
Examples expose quotation-as-heading errors (`dpyid dus`, `’brog pa`), neighbouring
compound confusion (`dkor sruṅ`), and explicit homonym errors (`ldoṅs¹` versus printed
²ldoṅs; `’bum pa²` versus printed ³’bum pa). Unknowns are not counted as successes.
A larger independent held-out lexical/homonym/extent dataset remains necessary.

For exact historical-origin reproduction, retain the pinned portable input bundle
listed in `inputs.json`; rebuilding it must include the same optional anchor and
edge JSONL inputs. Omitting them remains supported but changes C6/history metrics.

Measured full-run wall time was 268.42 seconds and peak RSS 552,632,320 bytes.
A cached resume reproduced all canonical files. A separate stop-after-starts run
and resume also test stage checkpoint recovery; SQLite interruption rolls back
incomplete stage work. Timings are execution observations, not scholarly review
throughput. Canonical SHA-256 identities for the complete experiment:

- `witnesses.jsonl`: `fbdd8ee3dfb297e5f98bacd6c51d2f861f5b4e03984be7a0191e6c20330d1362`
- `validation.json`: `b27e3b687e8e837a0673bc047fb4228a1152bbdb24fb65e32b8402d23078776b`
- `report/review.html`: `381b59c39944b2cd55edfd15ee20c6bca2688c4722696472358d02d0c971f3e9`

Focused tests include real QA coordinates for da yaṅ 1090:55/89, mdun 106:47/59,
and ba tshwa 17:63 versus ba tshwa can 17:77, plus held-out synthetic boundaries,
column separation, numeral placement and monotone-chain equivalence. The full
Python suite reports 2,126 passed / 62 subtests, with the same two inherited
failures documented above. Required repository regressions report 315 passed /
62 subtests; Node reports 19 passed. No release evidence is changed.

A fresh full-reader build and source-integrity differential retain 29,878 witness
identities, 163 attached HTML print links, 11,840 byte-identical PDF witness bodies
and 1,377 unchanged source assets. Catalogue order/search keys, source strings,
citations and relationship census match the prior certified reader. All 48 print
derivatives match the reviewed cache; no complete-volume route, private path or
symlink is served. Chrome certification passes at widths 1440, 320, 390 and 768,
including 61 apostrophe-equivalent matches, 447 `gyu` matches, reference/citation
journeys and 58 facsimile checks, with zero browser errors. The separate grouped
review report also passes desktop/mobile Chrome checks.

**No defined class has yet been demonstrated safe for bulk publication.** The main
obstacles are incomplete coordinate coverage, uncertain article extents and
independent printed homonym identity, followed by unreviewed folio/crop mapping.
The next experiment should improve those source features and test on a larger
held-out dataset, without publishing additional reader links or repeatedly
hand-curating acceptance batches.

### PR #12 diagnostic classification correction (v3.1)

The complete rerun preserves strong lexical/sequence matches as provisional even
when printed homonyms or geometry remain unread. Explicit contradictory homonyms
block identity. Publication eligibility is an independent, always-false machine
policy; result metadata cannot grant reader attachment. The corpus contains 2,416
provisionally supported, 13,210 review-required, four contradictory and 2,408
unresolved identities; the 163 reviewed attachments remain separate. Against the
PR #11 population, 2,314 formerly supported cases remain supported, 28 are
downgraded, and 102 former review cases meet the provisional lexical criteria.

All 32 evaluation observations are bound to registered scan checksums, HTML
checksums, exact QA row/text hashes and coordinates, and rendered PNG identities.
These checks establish provenance, not the truth of human observations. Changed
prediction evidence or anchors require reassessment: 17 retained correct, three
explicit incorrect lexical/homonym identities, one insufficient ground truth and
11 changed predictions not yet assessable. No corrected/newly incorrect prediction
is claimed without fresh judgments. Development/held-out labels remain separate.

Full execution took 288.265 seconds, peak RSS 552,124,416 bytes; cached resume
reproduced canonical outputs. Witness output SHA-256:
`dd53836a3a748570db635f66d1b9e44acc7da2a781816d3671f8a54d644ceb47`.
Focused tests: 34 passed. Full Python: 2,129 passed / 62 subtests, with the same
inherited bibliography checksum and wts_8_b 409:73 failures. Required regressions:
315 passed / 62 subtests; Node: 19 passed. Chrome: zero errors across desktop and
mobile, 61 apostrophe-equivalent and 447 gyu results, no search body fetches, and
58 facsimile checks. Historical 69 release-reproduction differences are inherited,
not eliminated by changes to source evidence. No automatic publication class is
authorised by this diagnostic milestone.


### Printed-source reconstruction experiment (v4, publication disabled)

PR #12 was merged normally at `c6a8c46eeabee7c8352c092f0625ae2695925115`.
The reconstruction experiment extends that engine and its existing SQLite stages:

```bash
python3 scripts/run_badw_html_print_alignment.py --all-volumes --resume \
  --output work/html-print-reconstruction-certified
python3 scripts/evaluate_badw_alignment.py \
  --baseline work/html-print-hardened-final \
  --run work/html-print-reconstruction-certified \
  --labels data/badw_html_print_evaluation.json \
  --observed-renders work/html-print-validation-final/report/pages \
  --prepare-calibration
```

Repeated body-line left edges in embedded PDF OCR supply candidate column clusters;
uniquely mapped QA lines receive page/column/y/x reading positions. Landscape pages
require four clusters and portrait pages two, with rotation/irregular layouts left
ambiguous. Candidate inter-page gutters come from the whitespace between the two
central content columns, rather than a universal midpoint. These are geometric
hypotheses: margins, folios and page-side identities remain uncertified.

Article intervals extend to the next plausible heading in reconstructed order,
including cross-column/page alternatives. In this run **zero intervals satisfy the
complete-coordinate coverage checks**. Matching therefore still uses the existing
uncertain 48-line fallback. This experiment does not claim solved article ownership.

Heading-prefix numeral parsing distinguishes agreeing QA/embedded OCR, single-OCR
readings, conflicts, intact unnumbered QA prefixes and unread prefixes. Punctuation,
senses and trailing numerals do not become homonym numbers; unnumbered never means
homonym 1. Two OCR readings of the same scan are not independent scholarly witnesses.
Source regressions include damaged `ldoṅs` and `’bum pa` prefixes, which remain unread.

Distinctive dual-script local matches with a ranking margin can bracket another
candidate between two *other* witnesses over at most ten physical pages. This adds
one ranking point only to an already existing candidate with distinctive definition
features; it cannot create identity or erase a contradiction. Of 907 anchors,
1,866 proposals receive bracket support and 40 top predictions change. Fresh
independent assessment of those changed predictions remains outstanding.

The full run processes 18,038 HTML witnesses, 3,466 physical pages and 352,244 QA
lines: 160,855 start hypotheses (136,626 non-C6) and 524,606 proposals. Start hypotheses
are not established articles. Results: 2,387 provisionally supported, 13,040 requiring
review, 203 contradictory identities and 2,408 unresolved. Against PR #11, 2,284 of
the 2,342 supported cases remain supported, 29 become contradictory and 29 require
review; 103 former review cases become provisionally supported. The 163 reviewed
reader attachments remain entirely separate and unchanged.

| Source family | Column-cluster pages / ambiguous | Content-gap spread candidates | Single mediabox / reviewed physical pages | Agreeing numeral OCR / unread hypotheses |
| --- | ---: | ---: | ---: | ---: |
| wts_1_34 | 812 / 540 | 742 | 266 / 15 | 1,102 / 73,554 |
| wts_35_51 | 1,090 / 38 | 0 | 1,118 / 10 | 108 / 38,177 |
| wts_8_b | 570 / 15 | 0 | 576 / 9 | 69 / 19,766 |
| wts_9_m | 395 / 6 | 0 | 391 / 10 | 72 / 13,470 |

Across all hypotheses there are 1,351 agreeing numeral OCR observations, 4,594
single-OCR numeral readings, eight conflicting readings, 9,935 assessable unnumbered
QA prefixes and 144,967 unread prefixes. There are 56,700 alternative coordinate
intervals, 103,217 unlocated starts and 938 top-furniture candidates; 31,628 intervals
cross a column/page. These counts measure reconstructed evidence, not its independently
verified accuracy. No new PDF derivatives or reader links are generated.

The existing 32 source-observation records remain diagnostic, not a new gold standard.
Their prediction accounting is 17 retained correct, 11 changed/unassessed, three
explicitly incorrect and one insufficient; no newly corrected prediction is claimed.
For assessable predictions the article-start result is 19/21 (Wilson 95% 71.1–97.3%),
page 18/20 (69.9–97.2%), lexical identity 17/20 (64.0–94.8%), and homonym 1/2
(9.5–90.5%). These are small, incomplete diagnostic denominators, not population
precision. Extent/crop accuracy and fresh reranking precision are not established.

A deterministic 200-case calibration queue is generated separately, stratified by
four families and supported/difficult populations, excluding existing cases and
preserving development/held-out splits. Its labels and inspected-render hashes are
**empty**. Preparing this queue does not constitute independent adjudication of
200 cases. Independent source inspection and frozen held-out judgments are required
before any automatic-acceptance policy can be evaluated.

Full execution took 542.891 seconds with peak RSS 710,901,760 bytes. Cached resume
executed no stages and reproduced canonical witness output SHA-256
`1f4e43423e51ef6b63776c2f8024ea2223c16cf0eb43fa5f8c7dbaa05dfd6b45`.
Focused tests: 48 passed. Full Python: 2,140 passed / 62 subtests, with only the two
inherited failures (bibliography checksum and wts_8_b 409:73). Required regressions:
315 passed / 62 subtests; Node: 19 passed. Historical release-reproduction differences
were not rerun or altered. No release source evidence changes.

A separate stop-after-starts run followed by resume reproduced `witnesses.jsonl`,
`validation.json` and `report/review.html` byte for byte. The fresh full-reader
differential retains all 29,878 witness identities, all 11,840 byte-identical PDF
bodies, all 163 reviewed HTML links, all 48 derivative files and the 7,626 resolved /
748 residual reference census. Source text, relationships, catalogue order and search
keys are unchanged. The served tree contains no private paths, volume routes or
symlinks. Chrome reader journeys pass across desktop/mobile sizes, including 61
apostrophe-equivalent matches, 447 `gyu` matches, source/citation/reference journeys
and zero unnecessary search body requests or browser errors. Page-grouped review
checks also pass at desktop/mobile widths. Local previews use ports 8816 (reader)
and 8815 (review); these local research outputs are not uploaded with the branch.

**This is a partial reconstruction milestone, not a demonstrated automatic publication
system.** Missing QA coordinate coverage prevents certified article ownership;
printed numerals remain OCR observations; unreviewed folios/margins and absent
independent calibration labels prevent publication. All machine publication decisions
remain false. The next work must improve coordinate reconciliation and article-boundary
ownership, then independently assess frozen predictions, rather than rename provisional
classes or publish another manually curated page batch.

PR #13 bounded hardening distinguishes tentative OCR disputes from verified print
contradictions. Of the previous 203 contradictory top predictions, 174 have only
one OCR numeral conflicting with HTML, 28 have agreeing QA/embedded-OCR numerals
conflicting with HTML, and one has disagreeing OCR readings. None has independently
verified contradictory print evidence. All 29 formerly-supported cases in that
population have single-OCR conflicts; they remain provisionally supported with
explicit outstanding homonym requirements, never publication authority. The new
full run has 2,416 provisionally supported, 13,214 review-required and 2,408 unresolved
witnesses. The two OCR readings are dependent observations of one printed source.

Every witness retains both local and sequence-adjusted rankings. Each adjustment
records scores, ranks and the source IDs/positions of its provisional supporting
witnesses. `--disable-sequence-reranking` leaves local scores authoritative while
retaining sequence diagnostics; it is pinned in the run configuration. The same
907 provisional anchors still change 40 tops, without any claim of correct recovery.
`work/html-print-reconstruction-hardening/sequence-changes.json` enumerates all 40
changes and their evidence. These changes remain unassessed, not confirmed recoveries.
The publication decision is independent of both scores and remains false.
