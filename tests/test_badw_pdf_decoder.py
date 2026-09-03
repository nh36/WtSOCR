import csv
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sys

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from badw_pdf_decoder import (  # noqa: E402
    FontIdentity,
    GlyphMapping,
    GlyphRegistry,
    PDFDecodeError,
    PositionedGlyph,
    PositionedTextRun,
    UnsupportedPDFError,
    _ResolvedFont,
    _cid_to_gid,
    _decode_cid,
    _reconstruct_page_text,
    _reconstruct_visible_text,
    _resolve_fonts,
    _text_sequence,
    decode_pdf_bytes,
    deterministic_json_bytes,
    glyph_outline_signature,
    parse_source_codes,
    parse_type0_cids,
    parse_tounicode_cmap,
)


class FakeStream(dict):
    def __init__(self, body, **values):
        super().__init__(values)
        self.body = body

    def get_data(self):
        return self.body


def tiny_font_bytes(*, second_x=500, family="TGaramond"):
    builder = FontBuilder(1000, isTTF=True)
    glyph_order = [".notdef", "one", "two"]
    builder.setupGlyphOrder(glyph_order)
    glyphs = {}
    for name, x in zip(glyph_order, (0, 300, second_x)):
        pen = TTGlyphPen(None)
        if x:
            pen.moveTo((0, 0))
            pen.lineTo((x, 0))
            pen.lineTo((x, 700))
            pen.lineTo((0, 700))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 0) for name in glyph_order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupCharacterMap({})
    builder.setupNameTable(
        {
            "familyName": family,
            "styleName": "Regular",
            "uniqueFontIdentifier": f"fixture-{family}",
            "fullName": family,
            "psName": family,
        }
    )
    builder.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWinAscent=800,
        usWinDescent=200,
    )
    builder.setupPost()
    builder.setupMaxp()
    output = BytesIO()
    builder.save(output)
    return output.getvalue()


def type0_page(
    program, *, subtype="/Type0", cid_to_gid="/Identity", to_unicode=None
):
    descriptor = {
        "/ItalicAngle": 0,
        "/FontFile2": FakeStream(program),
    }
    descendant = {
        "/BaseFont": "/ABCDEF+TGaramond-Regular",
        "/FontDescriptor": descriptor,
        "/CIDToGIDMap": cid_to_gid,
        "/DW": 500,
        "/W": [1, [600, 700]],
    }
    top = {
        "/Subtype": subtype,
        "/Encoding": "/Identity-H",
        "/BaseFont": "/ABCDEF+TGaramond-Regular",
        "/DescendantFonts": [descendant],
    }
    if to_unicode is not None:
        top["/ToUnicode"] = FakeStream(to_unicode)
    return {"/Resources": {"/Font": {"/F1": top}}}, descendant


def simple_truetype_page(program, *, to_unicode=None):
    descriptor = {
        "/ItalicAngle": 0,
        "/MissingWidth": 250,
        "/FontFile2": FakeStream(program),
    }
    top = {
        "/Subtype": "/TrueType",
        "/Encoding": "/WinAnsiEncoding",
        "/BaseFont": "/ABCDEF+MicrosoftSansSerif",
        "/FirstChar": 31,
        "/LastChar": 31,
        "/Widths": [293],
        "/FontDescriptor": descriptor,
    }
    if to_unicode is not None:
        top["/ToUnicode"] = FakeStream(to_unicode)
    return {"/Resources": {"/Font": {"/TT26": top}}}


def test_type0_cid_parsing_and_odd_input_failure():
    assert parse_type0_cids(b"\x00\x01\x12\x34") == (1, 0x1234)
    with pytest.raises(PDFDecodeError, match="odd number"):
        parse_type0_cids(b"\x00")


def test_fixed_width_source_code_parsing_preserves_simple_font_bytes():
    assert parse_source_codes(b"\x1f\x80", 1) == (0x1F, 0x80)
    with pytest.raises(UnsupportedPDFError, match="source-code width"):
        parse_source_codes(b"\x00", 3)


def test_type0_font_extraction_records_exact_identity_and_widths():
    program = tiny_font_bytes()
    page, _ = type0_page(program)
    font = _resolve_fonts(page)["/F1"]
    assert font.identity.family == "TGaramond"
    assert font.identity.style == "regular"
    assert font.identity.subset_prefix == "ABCDEF"
    assert font.identity.program_sha256 == sha256(program).hexdigest()
    assert font.identity.font_resource_sha256
    assert font.identity.to_unicode_sha256 == ""
    assert font.identity.cid_to_gid_kind == "/Identity"
    assert font.identity.font_subtype == "/Type0"
    assert font.identity.source_code_bytes == 2
    assert font.default_width == 500
    assert font.widths == {1: 600.0, 2: 700.0}


def test_cid_to_gid_stream_and_unsupported_font_failure():
    mapping = FakeStream(b"\x00\x00\x00\x02\x00\x01")
    assert _cid_to_gid({"/CIDToGIDMap": mapping}, 1) == 2
    assert _cid_to_gid({"/CIDToGIDMap": mapping}, 4) is None
    first_page, _ = type0_page(tiny_font_bytes(), cid_to_gid=mapping)
    second_page, _ = type0_page(
        tiny_font_bytes(), cid_to_gid=FakeStream(b"\x00\x00\x00\x01\x00\x02")
    )
    assert (
        _resolve_fonts(first_page)["/F1"].identity.font_resource_sha256
        != _resolve_fonts(second_page)["/F1"].identity.font_resource_sha256
    )
    page, _ = type0_page(tiny_font_bytes(), subtype="/Type1")
    with pytest.raises(UnsupportedPDFError, match="unsupported subtype"):
        _resolve_fonts(page)


def test_simple_truetype_font_is_preserved_as_explicit_unknown():
    program = tiny_font_bytes(family="MicrosoftSansSerif")
    font = _resolve_fonts(simple_truetype_page(program))["/TT26"]
    assert font.identity.family == "MicrosoftSansSerif"
    assert font.identity.font_subtype == "/TrueType"
    assert font.identity.source_code_bytes == 1
    assert font.identity.cid_to_gid_kind == "unresolved-simple-true-type-code"
    assert font.default_width == 250
    assert font.widths == {31: 293.0}
    gid, signature, marker, method, unknown = _decode_cid(
        font, 31, GlyphRegistry()
    )
    assert gid is None
    assert signature == "missing-cid-to-gid"
    assert marker.startswith("⟦UNKNOWN:MicrosoftSansSerif:regular:001F:")
    assert (method, unknown) == ("unknown", True)


def test_simple_truetype_tounicode_is_used_without_guessing_a_gid():
    cmap = b"1 beginbfchar <1F> <2192> endbfchar"
    font = _resolve_fonts(simple_truetype_page(tiny_font_bytes(), to_unicode=cmap))["/TT26"]
    assert _decode_cid(font, 31, GlyphRegistry()) == (
        None,
        "missing-cid-to-gid",
        "→",
        "pdf_to_unicode",
        False,
    )


def test_tounicode_bfchar_bfrange_and_exact_font_provenance():
    cmap = b"""
        2 beginbfchar
        <0001> <0041>
        <0004> <00610062>
        endbfchar
        2 beginbfrange
        <0002> <0003> <0062>
        <0005> <0006> [<03B3> <2191>]
        endbfrange
    """
    assert parse_tounicode_cmap(cmap) == {
        1: "A", 2: "b", 3: "c", 4: "ab", 5: "γ", 6: "↑"
    }
    page, _ = type0_page(tiny_font_bytes(), to_unicode=cmap)
    font = _resolve_fonts(page)["/F1"]
    assert font.identity.to_unicode_sha256 == sha256(cmap).hexdigest()
    assert _decode_cid(font, 2, GlyphRegistry())[2:] == (
        "b", "pdf_to_unicode", False
    )


def test_malformed_or_conflicting_tounicode_fails_explicitly():
    with pytest.raises(PDFDecodeError, match="conflicting ToUnicode"):
        parse_tounicode_cmap(
            b"1 beginbfchar <0001> <0041> endbfchar "
            b"1 beginbfchar <0001> <0042> endbfchar"
        )
    page, _ = type0_page(
        tiny_font_bytes(), to_unicode=b"1 beginbfrange <0002> <0001> <0041> endbfrange"
    )
    with pytest.raises(PDFDecodeError, match="descending ToUnicode"):
        _resolve_fonts(page)


def test_outline_identity_blocks_unsafe_cross_font_mapping():
    first_page, first_descendant = type0_page(tiny_font_bytes(second_x=500))
    second_page, _ = type0_page(tiny_font_bytes(second_x=650))
    first = _resolve_fonts(first_page)["/F1"]
    second = _resolve_fonts(second_page)["/F1"]
    first_signature = glyph_outline_signature(first.ttfont, 2)
    second_signature = glyph_outline_signature(second.ttfont, 2)
    assert first_signature != second_signature
    registry = GlyphRegistry(
        [
            GlyphMapping(
                family="TGaramond",
                style="regular",
                cid=2,
                glyph_signature=first_signature,
                unicode="ā",
                evidence_method="fixture",
                evidence_count=1,
                evidence_note="first embedded program only",
            )
        ]
    )
    gid, signature, character, method, unknown = _decode_cid(first, 2, registry)
    assert (gid, signature, character, method, unknown) == (
        2,
        first_signature,
        "ā",
        "reviewed_registry",
        False,
    )
    _, _, marker, method, unknown = _decode_cid(second, 2, registry)
    assert marker.startswith("⟦UNKNOWN:TGaramond:regular:0002:")
    assert (method, unknown) == ("unknown", True)
    assert first_descendant["/CIDToGIDMap"] == "/Identity"


def test_reviewed_registry_covers_wts_diacritics_arrows_latin_and_rabten():
    rows = list(
        csv.DictReader(
            (ROOT / "data/badw_pdf_glyph_mappings.tsv").open(encoding="utf-8"),
            delimiter="\t",
        )
    )
    characters = {row["unicode"] for row in rows}
    assert {"ā", "ḍ", "ṅ", "ś", "ṣ", "ṛ", "↑", "↓"} <= characters
    assert {"Ä", "Ö", "Ü", "ß", "é", "ç"} <= characters
    assert {"⟨", "⟩", "≈", "γ", "°"} <= characters
    assert {"ཀ", "ཁ", "་", "།"} <= characters


def test_tj_sequence_retains_positioning_adjustments_in_source_order():
    assert _text_sequence("TJ", [[b"\x00\x01", -120, b"\x00\x02"]]) == [
        b"\x00\x01",
        -120,
        b"\x00\x02",
    ]


def test_positioned_run_reconstruction_preserves_run_and_line_order():
    identity = FontIdentity(
        "/F1", "font", "family", "regular", "", "", "a", "b", "", "/Identity",
        "/Type0", 2,
    )
    glyph = PositionedGlyph(1, "0001", 1, "sig", "a", "reviewed_registry", False, 10, 20, 5)
    first = PositionedTextRun(0, 1, "Tj", "font", 10, 10, 20, ("0001",), "a", 0, (glyph,))
    second = PositionedTextRun(1, 2, "Tj", "font", 10, 15, 20, ("0001",), "b", 0, (glyph,))
    third = PositionedTextRun(2, 3, "Tj", "font", 10, 10, 8, ("0001",), "c", 0, (glyph,))
    assert identity.program_sha256 == "a"
    assert _reconstruct_page_text([first, second, third]) == "ab\nc"


def test_visible_reconstruction_suppresses_only_near_overprinting():
    overlay = PositionedGlyph(
        1, "0001", 1, "sig", "a", "reviewed_registry", False, 10.02, 20.02, 5
    )
    distinct = PositionedGlyph(
        1, "0001", 1, "sig", "a", "reviewed_registry", False, 15, 20, 5
    )
    runs = [
        PositionedTextRun(0, 1, "Tj", "font", 10, 10, 20, ("0001",), "a", 0, (
            PositionedGlyph(
                1, "0001", 1, "sig", "a", "reviewed_registry", False, 10, 20, 5
            ),
        )),
        PositionedTextRun(1, 2, "Tj", "font", 10, 10.02, 20.02, ("0001",), "a", 0, (overlay,)),
        PositionedTextRun(2, 3, "Tj", "font", 10, 15, 20, ("0001",), "a", 0, (distinct,)),
    ]
    assert _reconstruct_visible_text(runs) == ("aa", 1)


def test_deterministic_output_and_malformed_pdf_failure():
    record = {"unicode": "ཀā", "nested": {"b": 2, "a": 1}}
    assert deterministic_json_bytes(record) == deterministic_json_bytes(record)
    assert deterministic_json_bytes(record).decode() == '{"nested":{"a":1,"b":2},"unicode":"ཀā"}\n'
    mapping = GlyphMapping(
        "family", "regular", 1, "signature", "ཀ", "fixture", 1, "reviewed"
    )
    assert GlyphRegistry([mapping]).sha256 == GlyphRegistry([mapping]).sha256
    assert GlyphRegistry([mapping]).sha256 != GlyphRegistry().sha256
    with pytest.raises(PDFDecodeError, match="cannot parse PDF"):
        decode_pdf_bytes(
            b"not a PDF",
            canonical_url="https://example.invalid/pdf/ka",
            catalogue_lemma="ka",
            registry=GlyphRegistry(),
        )
