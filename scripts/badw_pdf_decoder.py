#!/usr/bin/env python3
"""Decode BAdW generated PDFs from embedded font data.

The decoder is intentionally source-faithful.  Legacy-font mappings are
accepted only when family, style, CID, and the embedded glyph-outline hash all
match the reviewed registry.  Unknown glyphs remain explicit in the output.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
import json
import logging
import numbers
from pathlib import Path
import re
import struct
import unicodedata
from typing import Iterable, Mapping, Sequence

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAPPING = ROOT / "data/badw_pdf_glyph_mappings.tsv"
DECODER_VERSION = "badw-generated-pdf-v2"
SUBSET_RE = re.compile(r"^([A-Z]{6})\+")
LEGACY_FAMILIES = frozenset({"RabtenTibetan", "TGaramond"})


class PDFDecodeError(ValueError):
    """The PDF is malformed or uses a structure the decoder cannot preserve."""


class UnsupportedPDFError(PDFDecodeError):
    """The PDF uses an unsupported font or text-stream structure."""


@dataclass(frozen=True)
class GlyphMapping:
    family: str
    style: str
    cid: int
    glyph_signature: str
    unicode: str
    evidence_method: str
    evidence_count: int
    evidence_note: str


@dataclass(frozen=True)
class FontIdentity:
    resource_name: str
    base_font: str
    family: str
    style: str
    subset_prefix: str
    program_kind: str
    program_sha256: str
    font_resource_sha256: str
    to_unicode_sha256: str
    cid_to_gid_kind: str
    font_subtype: str
    source_code_bytes: int


@dataclass(frozen=True)
class PositionedGlyph:
    cid: int
    cid_hex: str
    gid: int | None
    glyph_signature: str
    unicode: str
    mapping_method: str
    unknown: bool
    x: float
    y: float
    advance: float


@dataclass(frozen=True)
class PositionedTextRun:
    run_index: int
    operation_index: int
    operator: str
    font_id: str
    font_size: float
    x: float
    y: float
    source_cids: tuple[str, ...]
    decoded_unicode: str
    unknown_glyphs: int
    glyphs: tuple[PositionedGlyph, ...]


@dataclass
class _TextState:
    font_id: str = ""
    font_size: float = 0.0
    char_spacing: float = 0.0
    word_spacing: float = 0.0
    horizontal_scale: float = 1.0
    leading: float = 0.0
    line_x: float = 0.0
    line_y: float = 0.0
    x: float = 0.0
    y: float = 0.0


def _indirect(value):
    return value.get_object() if hasattr(value, "get_object") else value


def _stable_number(value: float) -> float:
    return round(float(value), 6)


def _canonical_outline_value(value):
    if isinstance(value, float):
        return _stable_number(value)
    if isinstance(value, (tuple, list)):
        return [_canonical_outline_value(item) for item in value]
    return value


def glyph_outline_signature(font: TTFont, gid: int) -> str:
    """Hash the decomposed outline independently of subset glyph names."""

    glyph_order = font.getGlyphOrder()
    if gid < 0 or gid >= len(glyph_order):
        return "out-of-range"
    name = glyph_order[gid]
    if "glyf" not in font:
        return "unsupported-outline"
    glyf = font["glyf"]

    class RawGlyph:
        def __init__(self, glyph_name: str) -> None:
            self.glyph_name = glyph_name

        def draw(self, pen) -> None:
            glyf[self.glyph_name].draw(pen, glyf)

    class RawGlyphSet:
        def __getitem__(self, glyph_name: str) -> RawGlyph:
            return RawGlyph(glyph_name)

    glyph_set = RawGlyphSet()
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)
    payload = {
        "commands": _canonical_outline_value(pen.value),
        "units_per_em": int(font["head"].unitsPerEm) if "head" in font else 1000,
    }
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(serialised).hexdigest()


class GlyphRegistry:
    """Reviewed glyph mappings guarded by exact outline identity."""

    def __init__(self, mappings: Iterable[GlyphMapping] = ()) -> None:
        self._mappings: dict[tuple[str, str, int, str], GlyphMapping] = {}
        for mapping in mappings:
            key = (
                mapping.family,
                mapping.style,
                mapping.cid,
                mapping.glyph_signature,
            )
            previous = self._mappings.get(key)
            if previous is not None and previous.unicode != mapping.unicode:
                raise PDFDecodeError(f"conflicting glyph registry row for {key}")
            self._mappings[key] = mapping
        canonical_rows = [
            asdict(self._mappings[key]) for key in sorted(self._mappings)
        ]
        self.sha256 = sha256(
            json.dumps(
                canonical_rows,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def from_tsv(cls, path: Path | str = DEFAULT_MAPPING) -> "GlyphRegistry":
        mappings = []
        with Path(path).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                mappings.append(
                    GlyphMapping(
                        family=row["family"],
                        style=row["style"],
                        cid=int(row["cid"], 16),
                        glyph_signature=row["glyph_signature"],
                        unicode=row["unicode"],
                        evidence_method=row["evidence_method"],
                        evidence_count=int(row["evidence_count"] or 0),
                        evidence_note=row["evidence_note"],
                    )
                )
        return cls(mappings)

    def lookup(
        self, family: str, style: str, cid: int, signature: str
    ) -> GlyphMapping | None:
        return self._mappings.get((family, style, cid, signature))


def _font_program(descendant: Mapping) -> tuple[str, bytes]:
    descriptor = _indirect(descendant.get("/FontDescriptor")) or {}
    for key in ("/FontFile", "/FontFile2", "/FontFile3"):
        reference = descriptor.get(key)
        if reference is not None:
            stream = _indirect(reference)
            if hasattr(stream, "get_data"):
                return key.lstrip("/"), stream.get_data()
    return "", b""


def _family_style(base_font: str, descriptor: Mapping) -> tuple[str, str, str]:
    raw = base_font.lstrip("/")
    match = SUBSET_RE.match(raw)
    subset = match.group(1) if match else ""
    clean = SUBSET_RE.sub("", raw)
    style = "italic" if "italic" in clean.casefold() else "regular"
    if float(descriptor.get("/ItalicAngle", 0) or 0) and style == "regular":
        style = "italic"
    family = re.sub(r"[,\-]?(?:Italic|Regular|Roman|Bold)$", "", clean, flags=re.I)
    return family, style, subset


def _cid_to_gid(descendant: Mapping, cid: int) -> int | None:
    mapping = descendant.get("/CIDToGIDMap", "/Identity")
    if str(mapping) == "/Identity":
        return cid
    stream = _indirect(mapping)
    if not hasattr(stream, "get_data"):
        return None
    data = stream.get_data()
    offset = cid * 2
    if offset + 2 > len(data):
        return None
    return struct.unpack(">H", data[offset : offset + 2])[0]


def parse_type0_cids(value) -> tuple[int, ...]:
    """Return the two-byte CIDs in a Type0 Identity-H string operand."""

    return parse_source_codes(value, 2)


def parse_source_codes(value, code_bytes: int) -> tuple[int, ...]:
    """Return fixed-width source codes without applying an inferred encoding."""

    if code_bytes not in {1, 2}:
        raise UnsupportedPDFError(f"unsupported source-code width {code_bytes}")

    if isinstance(value, bytes):
        data = value
    else:
        original = getattr(value, "original_bytes", None)
        if original is not None:
            data = bytes(original)
        elif isinstance(value, str):
            data = value.encode("latin-1")
        else:
            raise UnsupportedPDFError(f"unsupported PDF string operand {type(value)!r}")
    if len(data) % code_bytes:
        if code_bytes == 2:
            raise PDFDecodeError("Type0 text string has an odd number of bytes")
        raise PDFDecodeError(
            f"text string length is not divisible by source-code width {code_bytes}"
        )
    return tuple(
        int.from_bytes(data[offset : offset + code_bytes], "big")
        for offset in range(0, len(data), code_bytes)
    )


def _widths(descendant: Mapping) -> tuple[int, dict[int, float]]:
    default = int(descendant.get("/DW", 1000) or 1000)
    values = list(_indirect(descendant.get("/W")) or [])
    widths: dict[int, float] = {}
    index = 0
    while index < len(values):
        start = int(values[index])
        index += 1
        if index >= len(values):
            raise PDFDecodeError("malformed CID /W array")
        next_value = _indirect(values[index])
        index += 1
        if isinstance(next_value, Sequence) and not isinstance(next_value, (str, bytes)):
            for offset, width in enumerate(next_value):
                widths[start + offset] = float(width)
            continue
        end = int(next_value)
        if index >= len(values):
            raise PDFDecodeError("malformed CID /W range")
        width = float(values[index])
        index += 1
        for cid in range(start, end + 1):
            widths[cid] = width
    return default, widths


def _simple_widths(font: Mapping, descriptor: Mapping) -> tuple[int, dict[int, float]]:
    """Read widths for a simple font while retaining its byte codes verbatim."""

    default = int(descriptor.get("/MissingWidth", 0) or 0)
    first = int(font.get("/FirstChar", 0) or 0)
    values = list(_indirect(font.get("/Widths")) or [])
    return default, {
        first + offset: float(width) for offset, width in enumerate(values)
    }


def _embedded_cmap(font: TTFont) -> dict[int, str]:
    """Build an unambiguous GID-to-Unicode map from this exact font program."""

    candidates: dict[int, set[str]] = {}
    if "cmap" not in font:
        return {}
    glyph_order = font.getGlyphOrder()
    name_to_gid = {name: gid for gid, name in enumerate(glyph_order)}
    for table in font["cmap"].tables:
        if not table.isUnicode():
            continue
        for codepoint, glyph_name in table.cmap.items():
            gid = name_to_gid.get(glyph_name)
            if gid is not None and 0 <= codepoint <= 0x10FFFF:
                candidates.setdefault(gid, set()).add(chr(codepoint))
    return {
        gid: next(iter(values))
        for gid, values in candidates.items()
        if len(values) == 1
    }


_CMAP_HEX_RE = re.compile(rb"<\s*([0-9A-Fa-f\s]+?)\s*>")


def _cmap_hex_bytes(token: bytes) -> bytes:
    match = _CMAP_HEX_RE.fullmatch(token.strip())
    if match is None:
        raise PDFDecodeError(f"invalid ToUnicode hex token {token!r}")
    digits = re.sub(rb"\s+", b"", match.group(1))
    if len(digits) % 2:
        digits += b"0"
    try:
        return bytes.fromhex(digits.decode("ascii"))
    except ValueError as exc:
        raise PDFDecodeError(f"invalid ToUnicode hex token {token!r}") from exc


def _cmap_unicode(token: bytes) -> str:
    raw = _cmap_hex_bytes(token)
    if len(raw) % 2:
        raise PDFDecodeError("ToUnicode target is not UTF-16BE")
    try:
        return raw.decode("utf-16-be", errors="strict")
    except UnicodeDecodeError as exc:
        raise PDFDecodeError("invalid UTF-16BE in ToUnicode target") from exc


def parse_tounicode_cmap(data: bytes) -> dict[int, str]:
    """Parse the bfchar/bfrange mappings needed by a PDF ToUnicode CMap.

    Source codes are retained as integers because the generated files use
    two-byte Identity-H/V codes.  Conflicting rows and malformed ranges fail
    explicitly rather than falling through to a guessed legacy-font mapping.
    """

    cleaned = re.sub(rb"%[^\r\n]*", b"", data)
    token_re = re.compile(
        rb"<\s*[0-9A-Fa-f\s]+?\s*>|\[|\]|beginbfchar|endbfchar|"
        rb"beginbfrange|endbfrange|\d+"
    )
    tokens = token_re.findall(cleaned)
    result: dict[int, str] = {}

    def put(source: int, value: str) -> None:
        previous = result.get(source)
        if previous is not None and previous != value:
            raise PDFDecodeError(
                f"conflicting ToUnicode mappings for source code {source:04X}"
            )
        result[source] = value

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == b"beginbfchar":
            index += 1
            while index < len(tokens) and tokens[index] != b"endbfchar":
                if index + 1 >= len(tokens):
                    raise PDFDecodeError("truncated ToUnicode bfchar block")
                source = int.from_bytes(_cmap_hex_bytes(tokens[index]), "big")
                put(source, _cmap_unicode(tokens[index + 1]))
                index += 2
            if index >= len(tokens):
                raise PDFDecodeError("unterminated ToUnicode bfchar block")
        elif token == b"beginbfrange":
            index += 1
            while index < len(tokens) and tokens[index] != b"endbfrange":
                if index + 2 >= len(tokens):
                    raise PDFDecodeError("truncated ToUnicode bfrange block")
                start = int.from_bytes(_cmap_hex_bytes(tokens[index]), "big")
                end = int.from_bytes(_cmap_hex_bytes(tokens[index + 1]), "big")
                index += 2
                if end < start:
                    raise PDFDecodeError("descending ToUnicode bfrange")
                if tokens[index] == b"[":
                    index += 1
                    values = []
                    while index < len(tokens) and tokens[index] != b"]":
                        values.append(_cmap_unicode(tokens[index]))
                        index += 1
                    if index >= len(tokens):
                        raise PDFDecodeError("unterminated ToUnicode bfrange array")
                    if len(values) != end - start + 1:
                        raise PDFDecodeError("ToUnicode bfrange array has wrong length")
                    for offset, value in enumerate(values):
                        put(start + offset, value)
                    index += 1
                else:
                    target = _cmap_hex_bytes(tokens[index])
                    target_size = len(target)
                    target_int = int.from_bytes(target, "big")
                    for offset, source in enumerate(range(start, end + 1)):
                        try:
                            encoded = (target_int + offset).to_bytes(target_size, "big")
                        except OverflowError as exc:
                            raise PDFDecodeError("ToUnicode bfrange target overflow") from exc
                        put(source, _cmap_unicode(b"<" + encoded.hex().encode() + b">"))
                    index += 1
            if index >= len(tokens):
                raise PDFDecodeError("unterminated ToUnicode bfrange block")
        index += 1
    return result


def _serialise_pdf_object(value) -> object:
    value = _indirect(value)
    if hasattr(value, "get_data"):
        stream_dictionary = {
            str(key): _serialise_pdf_object(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) != "/Length"
        }
        return {
            "stream_dictionary": stream_dictionary,
            "stream_sha256": sha256(value.get_data()).hexdigest(),
        }
    if isinstance(value, Mapping):
        return {
            str(key): _serialise_pdf_object(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in {"/FontDescriptor", "/ToUnicode"}
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_serialise_pdf_object(item) for item in value]
    if isinstance(value, bytes):
        return {"bytes_sha256": sha256(value).hexdigest()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass
class _ResolvedFont:
    identity: FontIdentity
    descendant: Mapping
    ttfont: TTFont
    default_width: int
    widths: dict[int, float]
    cmap: dict[int, str]
    to_unicode: dict[int, str]
    signatures: dict[int, str]
    source_code_bytes: int
    deterministic_gid_mapping: bool

    def signature(self, gid: int) -> str:
        if gid not in self.signatures:
            self.signatures[gid] = glyph_outline_signature(self.ttfont, gid)
        return self.signatures[gid]


def _resolve_fonts(page) -> dict[str, _ResolvedFont]:
    resources = _indirect(page.get("/Resources")) or {}
    fonts = _indirect(resources.get("/Font")) or {}
    result = {}
    for resource_name, font_reference in fonts.items():
        top = _indirect(font_reference)
        subtype = str(top.get("/Subtype"))
        if subtype == "/Type0":
            encoding = str(top.get("/Encoding", ""))
            if encoding not in {"/Identity-H", "/Identity-V"}:
                raise UnsupportedPDFError(
                    f"font {resource_name} has unsupported Type0 encoding {encoding}"
                )
            descendants = _indirect(top.get("/DescendantFonts")) or []
            if len(descendants) != 1:
                raise UnsupportedPDFError(
                    f"font {resource_name} does not have exactly one descendant"
                )
            descendant = _indirect(descendants[0])
            descriptor = _indirect(descendant.get("/FontDescriptor")) or {}
            base_font = str(top.get("/BaseFont", descendant.get("/BaseFont", "")))
            default_width, widths = _widths(descendant)
            source_code_bytes = 2
            deterministic_gid_mapping = True
            cid_to_gid_kind = str(descendant.get("/CIDToGIDMap", "/Identity"))
        elif subtype == "/TrueType":
            # Some generated pages use a tiny embedded simple TrueType font for
            # an auxiliary symbol.  Its byte code is preserved, but without a
            # ToUnicode CMap or a deterministic Encoding-to-GID relation it
            # must remain an explicit unknown rather than aborting the page.
            descendant = top
            descriptor = _indirect(top.get("/FontDescriptor")) or {}
            base_font = str(top.get("/BaseFont", ""))
            default_width, widths = _simple_widths(top, descriptor)
            source_code_bytes = 1
            deterministic_gid_mapping = False
            cid_to_gid_kind = "unresolved-simple-true-type-code"
        else:
            raise UnsupportedPDFError(
                f"font {resource_name} has unsupported subtype {subtype}"
            )
        family, style, subset = _family_style(base_font, descriptor)
        program_kind, program = _font_program(descendant)
        if not program:
            raise UnsupportedPDFError(f"font {resource_name} has no embedded program")
        try:
            logging.getLogger("fontTools.ttLib.tables._h_m_t_x").setLevel(logging.ERROR)
            ttfont = TTFont(BytesIO(program), lazy=False, recalcBBoxes=False)
        except Exception as exc:
            raise UnsupportedPDFError(
                f"font {resource_name} program cannot be read: {exc}"
            ) from exc
        resource_payload = json.dumps(
            _serialise_pdf_object(top), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        to_unicode_reference = top.get("/ToUnicode")
        to_unicode_data = b""
        to_unicode = {}
        if to_unicode_reference is not None:
            to_unicode_stream = _indirect(to_unicode_reference)
            if not hasattr(to_unicode_stream, "get_data"):
                raise UnsupportedPDFError(
                    f"font {resource_name} has a non-stream ToUnicode resource"
                )
            to_unicode_data = to_unicode_stream.get_data()
            try:
                to_unicode = parse_tounicode_cmap(to_unicode_data)
            except PDFDecodeError as exc:
                raise PDFDecodeError(
                    f"font {resource_name} has an invalid ToUnicode CMap: {exc}"
                ) from exc
        identity = FontIdentity(
            resource_name=str(resource_name),
            base_font=base_font,
            family=family,
            style=style,
            subset_prefix=subset,
            program_kind=program_kind,
            program_sha256=sha256(program).hexdigest(),
            font_resource_sha256=sha256(resource_payload).hexdigest(),
            to_unicode_sha256=(
                sha256(to_unicode_data).hexdigest() if to_unicode_data else ""
            ),
            cid_to_gid_kind=cid_to_gid_kind,
            font_subtype=subtype,
            source_code_bytes=source_code_bytes,
        )
        result[str(resource_name)] = _ResolvedFont(
            identity=identity,
            descendant=descendant,
            ttfont=ttfont,
            default_width=default_width,
            widths=widths,
            cmap=_embedded_cmap(ttfont),
            to_unicode=to_unicode,
            signatures={},
            source_code_bytes=source_code_bytes,
            deterministic_gid_mapping=deterministic_gid_mapping,
        )
    return result


def _unknown_marker(font: FontIdentity, cid: int, signature: str) -> str:
    return (
        f"⟦UNKNOWN:{font.family}:{font.style}:"
        f"{cid:04X}:{signature[:12]}⟧"
    )


def _decode_cid(
    font: _ResolvedFont,
    cid: int,
    registry: GlyphRegistry,
) -> tuple[int | None, str, str, str, bool]:
    gid = _cid_to_gid(font.descendant, cid) if font.deterministic_gid_mapping else None
    signature = "missing-cid-to-gid" if gid is None else font.signature(gid)
    if cid in font.to_unicode:
        return gid, signature, font.to_unicode[cid], "pdf_to_unicode", False
    if gid is None:
        return gid, signature, _unknown_marker(font.identity, cid, signature), "unknown", True
    mapping = registry.lookup(
        font.identity.family, font.identity.style, cid, signature
    )
    if mapping is not None:
        return gid, signature, mapping.unicode, "reviewed_registry", False
    if font.identity.family not in LEGACY_FAMILIES and gid in font.cmap:
        return gid, signature, font.cmap[gid], "embedded_unicode_cmap", False
    return gid, signature, _unknown_marker(font.identity, cid, signature), "unknown", True


def _text_sequence(operator: str, operands: Sequence) -> list[object]:
    if operator in {"Tj", "'", '"'}:
        return [operands[-1]]
    if operator == "TJ":
        return list(operands[0])
    return []


def _reconstruct_page_text(runs: Sequence[PositionedTextRun]) -> str:
    parts: list[str] = []
    previous_y: float | None = None
    for run in runs:
        if previous_y is not None and abs(run.y - previous_y) > 0.5:
            parts.append("\n")
        parts.append(run.decoded_unicode)
        previous_y = run.y
    return "".join(parts)


def _reconstruct_visible_text(
    runs: Sequence[PositionedTextRun],
) -> tuple[str, int]:
    """Remove near-identical overprinting used to simulate bold type.

    The generated PDFs draw some glyphs several times with tiny offsets.  Raw
    runs above remain untouched; this derived reading suppresses only a glyph
    whose Unicode, font and position coincide with an earlier glyph to within
    five percent of the font size.
    """

    parts: list[str] = []
    seen: list[tuple[str, str, float, float, float]] = []
    previous_y: float | None = None
    overprinted = 0
    for run in runs:
        visible = []
        tolerance = max(run.font_size * 0.05, 0.000001)
        for glyph in run.glyphs:
            duplicate = any(
                character == glyph.unicode
                and font_id == run.font_id
                and abs(x - glyph.x) <= tolerance
                and abs(y - glyph.y) <= tolerance
                for character, font_id, x, y, _font_size in seen[-64:]
            )
            if duplicate:
                overprinted += 1
                continue
            visible.append(glyph.unicode)
            seen.append((glyph.unicode, run.font_id, glyph.x, glyph.y, run.font_size))
        if not visible:
            continue
        if previous_y is not None and abs(run.y - previous_y) > 0.5:
            parts.append("\n")
        parts.extend(visible)
        previous_y = run.y
    return "".join(parts), overprinted


def _tibetan_text_candidates(
    runs: Sequence[PositionedTextRun],
    fonts: Mapping[str, Mapping[str, object]],
    page_height: float,
) -> list[dict[str, object]]:
    """Group consecutive Rabten runs without claiming article segmentation."""

    candidates: list[dict[str, object]] = []
    current: list[PositionedTextRun] = []

    def finish() -> None:
        if not current:
            return
        text = "".join(run.decoded_unicode for run in current)
        candidates.append(
            {
                "candidate_index": len(candidates),
                "kind": (
                    "page_running_head"
                    if current[0].y >= page_height - 40.0
                    else "body_tibetan_text"
                ),
                "run_indices": [run.run_index for run in current],
                "x": _stable_number(current[0].x),
                "y": _stable_number(current[0].y),
                "decoded_unicode": text,
                "unknown_glyphs": sum(run.unknown_glyphs for run in current),
            }
        )
        current.clear()

    for run in runs:
        family = str(fonts[run.font_id]["family"])
        adjacent = (
            current
            and run.run_index == current[-1].run_index + 1
            and abs(run.y - current[-1].y) <= 0.05
        )
        if family == "RabtenTibetan":
            if current and not adjacent:
                finish()
            current.append(run)
        else:
            finish()
    finish()
    return candidates


def _normalised_reading(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", unicodedata.normalize("NFC", text))


def decode_pdf_bytes(
    body: bytes,
    *,
    canonical_url: str,
    catalogue_lemma: str,
    homonym: str = "",
    registry: GlyphRegistry | None = None,
) -> dict[str, object]:
    """Decode exact PDF bytes into a deterministic positioned-text contract."""

    source_sha = sha256(body).hexdigest()
    registry = registry or GlyphRegistry.from_tsv()
    try:
        reader = PdfReader(BytesIO(body), strict=False)
    except Exception as exc:
        raise PDFDecodeError(f"cannot parse PDF: {exc}") from exc
    if not reader.pages:
        raise PDFDecodeError("PDF contains no pages")

    page_records = []
    font_records: dict[str, dict[str, object]] = {}
    total_unknown = 0
    for page_number, page in enumerate(reader.pages, 1):
        fonts = _resolve_fonts(page)
        page_font_ids: dict[str, str] = {}
        for resource_name, font in fonts.items():
            identity_payload = asdict(font.identity)
            font_id = sha256(
                json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            page_font_ids[resource_name] = font_id
            font_records.setdefault(font_id, {"font_id": font_id, **identity_payload})

        state = _TextState()
        runs: list[PositionedTextRun] = []
        contents = page.get_contents()
        if contents is None:
            operations = []
        else:
            try:
                operations = contents.operations
            except Exception as exc:
                raise PDFDecodeError(
                    f"page {page_number} content stream cannot be parsed: {exc}"
                ) from exc
        for operation_index, (operands, raw_operator) in enumerate(operations):
            operator = raw_operator.decode("ascii", errors="strict")
            if operator == "BT":
                state = _TextState()
            elif operator == "Tf":
                resource_name = str(operands[0])
                if resource_name not in fonts:
                    raise UnsupportedPDFError(
                        f"page {page_number} selects unresolved font {resource_name}"
                    )
                state.font_id = page_font_ids[resource_name]
                state.font_size = float(operands[1])
            elif operator == "Tm":
                state.line_x = state.x = float(operands[4])
                state.line_y = state.y = float(operands[5])
            elif operator in {"Td", "TD"}:
                tx, ty = float(operands[0]), float(operands[1])
                if operator == "TD":
                    state.leading = -ty
                state.line_x += tx
                state.line_y += ty
                state.x, state.y = state.line_x, state.line_y
            elif operator == "T*":
                state.line_y -= state.leading
                state.x, state.y = state.line_x, state.line_y
            elif operator == "Tc":
                state.char_spacing = float(operands[0])
            elif operator == "Tw":
                state.word_spacing = float(operands[0])
            elif operator == "Tz":
                state.horizontal_scale = float(operands[0]) / 100.0
            elif operator == "TL":
                state.leading = float(operands[0])
            elif operator in {"'", '"'}:
                if operator == '"':
                    state.word_spacing = float(operands[0])
                    state.char_spacing = float(operands[1])
                state.line_y -= state.leading
                state.x, state.y = state.line_x, state.line_y

            text_sequence = _text_sequence(operator, operands)
            if not text_sequence:
                continue
            if not state.font_id:
                raise PDFDecodeError(
                    f"page {page_number} text operator {operation_index} has no font"
                )
            font_record = font_records[state.font_id]
            resource_name = str(font_record["resource_name"])
            font = fonts[resource_name]
            for value in text_sequence:
                if isinstance(value, numbers.Real):
                    state.x += (
                        -float(value)
                        / 1000.0
                        * state.font_size
                        * state.horizontal_scale
                    )
                    continue
                cids = parse_source_codes(value, font.source_code_bytes)
                glyphs = []
                run_start_x, run_start_y = state.x, state.y
                for cid in cids:
                    gid, signature, character, method, unknown = _decode_cid(
                        font, cid, registry
                    )
                    width = font.widths.get(cid, font.default_width)
                    word_spacing = state.word_spacing if character == " " else 0.0
                    advance = (
                        width / 1000.0 * state.font_size
                        + state.char_spacing
                        + word_spacing
                    ) * state.horizontal_scale
                    glyphs.append(
                        PositionedGlyph(
                            cid=cid,
                            cid_hex=f"{cid:04X}",
                            gid=gid,
                            glyph_signature=signature,
                            unicode=character,
                            mapping_method=method,
                            unknown=unknown,
                            x=_stable_number(state.x),
                            y=_stable_number(state.y),
                            advance=_stable_number(advance),
                        )
                    )
                    state.x += advance
                decoded = "".join(glyph.unicode for glyph in glyphs)
                unknown_count = sum(glyph.unknown for glyph in glyphs)
                total_unknown += unknown_count
                runs.append(
                    PositionedTextRun(
                        run_index=len(runs),
                        operation_index=operation_index,
                        operator=operator,
                        font_id=state.font_id,
                        font_size=_stable_number(state.font_size),
                        x=_stable_number(run_start_x),
                        y=_stable_number(run_start_y),
                        source_cids=tuple(f"{cid:04X}" for cid in cids),
                        decoded_unicode=decoded,
                        unknown_glyphs=unknown_count,
                        glyphs=tuple(glyphs),
                    )
                )
        source_stream_text = _reconstruct_page_text(runs)
        visible_text, overprinted_glyphs = _reconstruct_visible_text(runs)
        font_lookup = {
            font_id: font_records[font_id]
            for font_id in set(page_font_ids.values())
        }
        page_height = float(page.mediabox.height)
        page_records.append(
            {
                "page": page_number,
                "positioned_text_runs": [asdict(run) for run in runs],
                "source_stream_text": source_stream_text,
                "visible_text": visible_text,
                "normalized_reading": _normalised_reading(visible_text),
                "overprinted_glyphs": overprinted_glyphs,
                "tibetan_text_candidates": _tibetan_text_candidates(
                    runs, font_lookup, page_height
                ),
                "unknown_glyphs": sum(run.unknown_glyphs for run in runs),
            }
        )

    return {
        "contract_version": DECODER_VERSION,
        "catalogue_identity": {
            "lemma": catalogue_lemma,
            "homonym": homonym,
        },
        "canonical_url": canonical_url,
        "source_sha256": source_sha,
        "decoder_version": DECODER_VERSION,
        "glyph_registry_sha256": registry.sha256,
        "fonts": [font_records[key] for key in sorted(font_records)],
        "pages": page_records,
        "unknown_glyphs": total_unknown,
    }


def deterministic_json_bytes(record: Mapping[str, object]) -> bytes:
    return (
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--url", required=True)
    parser.add_argument("--lemma", required=True)
    parser.add_argument("--homonym", default="")
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    record = decode_pdf_bytes(
        args.pdf.read_bytes(),
        canonical_url=args.url,
        catalogue_lemma=args.lemma,
        homonym=args.homonym,
        registry=GlyphRegistry.from_tsv(args.mapping),
    )
    output = deterministic_json_bytes(record)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(output)
    else:
        print(output.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
