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
