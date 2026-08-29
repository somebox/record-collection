"""Render fixed-size monochrome labels for a 62 mm Brother QL roll."""

import io
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

DPI = 300
PX_PER_MM = DPI / 25.4


def mm(value: float) -> int:
    return round(value * PX_PER_MM)


# A 62 mm roll is 732 dots wide at 300 dpi, of which the QL-700 exposes 696
# printable dots. Images sent to the printer use WIDTH; PDFs add the side gutters.
PAPER_WIDTH = mm(62)
WIDTH = 696
SLEEVE_HEIGHT = mm(34)
DIVIDER_HEIGHT = mm(25)
MARGIN = mm(1)
QR_SIZE = mm(13)
MIN_TEXT_HEIGHT = mm(1.8)
PREFERRED_MAIN_LINE_HEIGHT = mm(12)
HEADER_TEXT_HEIGHT = mm(15)
TOP_SECTION_HEIGHT = mm(16)

TITLE_MAX_CHARS = 140
ARTIST_MAX_CHARS = 180
STYLE_MAX_CHARS = 180
SUMMARY_MAX_CHARS = 700
PROVENANCE_MAX_CHARS = 180

# Prefer Liberation Sans so printed output is consistent with Linux, then use
# metrically similar system sans fonts when running the web app on macOS/Windows.
_FONT_CANDIDATES = {
    "regular": (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ),
    "bold": (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ),
    "italic": (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "C:/Windows/Fonts/ariali.ttf",
    ),
}
FONTS = {
    style: next((Path(path) for path in paths if Path(path).is_file()), Path(paths[0]))
    for style, paths in _FONT_CANDIDATES.items()
}


class PrintError(Exception):
    pass


def _font(style: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS[style]), size)


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    """Full ascent + descent, including room for descenders."""
    ascent, descent = font.getmetrics()
    return ascent + descent


def _font_at_height(style: str, target_height: int) -> ImageFont.FreeTypeFont:
    """Largest font whose full line box is no taller than target_height."""
    size = max(1, target_height)
    while size > 1 and _line_height(_font(style, size)) > target_height:
        size -= 1
    while _line_height(_font(style, size + 1)) <= target_height:
        size += 1
    return _font(style, size)


def _truncate(text: str, max_chars: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _divider_title(name: str) -> str:
    """Preserve stored proper-name casing; uppercase lowercase categories.

    Folder naming is the source of truth: artist sections are entered as
    ``Miles Davis``/``Radiohead``/``XTC``, while category folders are entered as
    ``classic rock``/``brasil``. This keeps acronyms and intentional spelling
    intact without maintaining a second classification list.
    """
    name = " ".join((name or "").split())
    return name if any(char.isupper() for char in name) else name.upper()


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid].rstrip() + "…"
        if draw.textlength(candidate, font=font) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    """Word-wrap to a hard line cap; ellipsize overflow and pathological words."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    consumed = 0
    for index, word in enumerate(words):
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
            consumed = index + 1
            continue
        if current:
            lines.append(current)
            if len(lines) == max_lines:
                break
            current = ""
        if draw.textlength(word, font=font) > max_width:
            current = _ellipsize(draw, word, font, max_width)
            consumed = index + 1
        else:
            current = word
            consumed = index + 1
    if current and len(lines) < max_lines:
        lines.append(current)
    if consumed < len(words) and lines:
        lines[-1] = _ellipsize(draw, lines[-1].rstrip("…") + "…", font, max_width)
    return lines


def _single_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    style: str,
    max_width: int,
    max_height: int,
) -> tuple[ImageFont.FreeTypeFont, str]:
    """Largest one-line type that fits, never dropping below 1.8 mm."""
    for height in range(max_height, MIN_TEXT_HEIGHT - 1, -1):
        font = _font_at_height(style, height)
        if draw.textlength(text, font=font) <= max_width:
            return font, text
    font = _font_at_height(style, MIN_TEXT_HEIGHT)
    return font, _ellipsize(draw, text, font, max_width)


def _header_layout(draw: ImageDraw.ImageDraw, title: str, byline: str, style_text: str, width: int):
    """Scale the three semantic header lines into a shared 15 mm budget.

    Title and byline start from the requested 12 mm line box. The style line is
    deliberately smaller. All are reduced together when wrapping or the total
    header-height constraint requires it.
    """
    block_gap = 2
    for main_height in range(PREFERRED_MAIN_LINE_HEIGHT, MIN_TEXT_HEIGHT - 1, -1):
        main_fonts = (_font_at_height("bold", main_height), _font_at_height("regular", main_height))
        style_height = max(MIN_TEXT_HEIGHT, round(main_height * 0.58))
        style_font = _font_at_height("italic", style_height)
        blocks = [
            (main_fonts[0], _wrap(draw, title, main_fonts[0], width, 2)),
            (main_fonts[1], _wrap(draw, byline, main_fonts[1], width, 2)),
        ]
        if style_text:
            blocks.append((style_font, _wrap(draw, style_text, style_font, width, 2)))
        total = sum(_line_height(font) * len(lines) for font, lines in blocks)
        total += block_gap * (len(blocks) - 1)
        if total <= HEADER_TEXT_HEIGHT:
            return blocks, block_gap
    raise ValueError("header cannot fit at the minimum text size")


def _fit_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    style: str,
    max_width: int,
    max_height: int,
    max_lines: int,
    preferred_height: int,
):
    for height in range(preferred_height, MIN_TEXT_HEIGHT - 1, -1):
        font = _font_at_height(style, height)
        lines = _wrap(draw, text, font, max_width, max_lines)
        if len(lines) * _line_height(font) <= max_height:
            return font, lines
    font = _font_at_height(style, MIN_TEXT_HEIGHT)
    return font, _wrap(draw, text, font, max_width, max_lines)


def _draw_lines(draw: ImageDraw.ImageDraw, x: int, y: int, font, lines: list[str]) -> int:
    line_height = _line_height(font)
    for line in lines:
        draw.text((x, y), line, font=font, fill=0, anchor="lt")
        y += line_height
    return y


def _qr(url: str, size: int) -> Image.Image:
    """Square QR canvas with integer modules and its quiet zone included."""
    code = segno.make(url, error="m")
    modules = code.symbol_size(scale=1, border=2)[0]
    scale = max(1, size // modules)
    actual = modules * scale
    buf = io.BytesIO()
    code.save(buf, kind="png", scale=scale, border=2)
    qr = Image.open(buf).convert("L")
    canvas = Image.new("L", (size, size), 255)
    offset = (size - actual) // 2
    canvas.paste(qr, (offset, offset))
    return canvas


def _draw_qr(img: Image.Image, url: str, x: int, y: int) -> None:
    img.paste(_qr(url, QR_SIZE), (x, y))


def _draw_scaled_caption(
    img: Image.Image, text: str, x: int, y: int, width: int = QR_SIZE
) -> int:
    """Render a minimum-size Discogs ID and scale its ink box to exactly 13 mm."""
    text = _truncate(text, 24)
    font = _font_at_height("regular", MIN_TEXT_HEIGHT)
    probe = ImageDraw.Draw(img)
    bbox = probe.textbbox((0, 0), text, font=font, anchor="lt")
    text_width = max(1, bbox[2] - bbox[0])
    height = _line_height(font)
    strip = Image.new("L", (text_width, height), 255)
    ImageDraw.Draw(strip).text((0, 0), text, font=font, fill=0, anchor="lt")
    strip = strip.resize((width, height), Image.Resampling.LANCZOS)
    img.paste(strip, (x, y))
    return y + height


def render_divider(name: str, genre_line: str, qr_url: str, folder_id: int | None = None) -> Image.Image:
    """Fixed 62×25 mm divider: full-width folder name, then genres + 13 mm QR."""
    img = Image.new("L", (WIDTH, DIVIDER_HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    full_width = WIDTH - 2 * MARGIN
    qr_x = WIDTH - MARGIN - QR_SIZE
    row_top = DIVIDER_HEIGHT - MARGIN - QR_SIZE

    title = _truncate(_divider_title(name), 90)
    title_height = max(MIN_TEXT_HEIGHT, row_top - MARGIN - 3)
    title_font, title = _single_line(draw, title, "bold", full_width, title_height)
    draw.text((MARGIN, MARGIN), title, font=title_font, fill=0, anchor="lt")

    _draw_qr(img, qr_url, qr_x, row_top)
    genres = _truncate(genre_line, 240)
    if genres:
        genre_width = qr_x - 2 * MARGIN
        genre_font, genre_lines = _fit_block(
            draw, genres, "italic", genre_width, QR_SIZE, 4, mm(4.2)
        )
        genre_height = len(genre_lines) * _line_height(genre_font)
        genre_y = row_top + max(0, (QR_SIZE - genre_height) // 2)
        _draw_lines(draw, MARGIN, genre_y, genre_font, genre_lines)
    return img


def render_sleeve(item: dict, qr_url: str, include_paid: bool = False) -> Image.Image:
    """Fixed 62×34 mm sleeve label with a 16 mm header and fitted description."""
    img = Image.new("L", (WIDTH, SLEEVE_HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    qr_x = WIDTH - MARGIN - QR_SIZE
    text_width = qr_x - 2 * MARGIN

    title = _truncate(item["title"], TITLE_MAX_CHARS)
    byline = _truncate(item["artist"], ARTIST_MAX_CHARS)
    display_year = item.get("display_year", item.get("year"))
    if display_year:
        byline += f" · {display_year}"
    if item.get("country"):
        byline += f" · {item['country']}"
    style_text = _truncate(item.get("style") or "", STYLE_MAX_CHARS)

    blocks, block_gap = _header_layout(draw, title, byline, style_text, text_width)
    y = MARGIN
    for index, (font, lines) in enumerate(blocks):
        y = _draw_lines(draw, MARGIN, y, font, lines)
        if index < len(blocks) - 1:
            y += block_gap

    _draw_qr(img, qr_url, qr_x, MARGIN)
    _draw_scaled_caption(img, f"[r{item['release_id']}]", qr_x, MARGIN + QR_SIZE + 1)

    rule_y = TOP_SECTION_HEIGHT
    draw.line([(MARGIN, rule_y), (WIDTH - MARGIN, rule_y)], fill=0, width=1)

    description_y = rule_y + MARGIN
    available = SLEEVE_HEIGHT - MARGIN - description_y
    full_width = WIDTH - 2 * MARGIN
    provenance = [item.get("notes")] if item.get("notes") else []
    if include_paid and item.get("paid_price") is not None:
        provenance.append(f"paid ${item['paid_price']:,.0f}")
    provenance_text = _truncate(" · ".join(provenance), PROVENANCE_MAX_CHARS)

    provenance_font = None
    provenance_line = ""
    provenance_height = 0
    if provenance_text:
        provenance_font, provenance_line = _single_line(
            draw, provenance_text, "italic", full_width, mm(2.4)
        )
        provenance_height = _line_height(provenance_font) + 3

    summary = _truncate(item.get("summary") or "", SUMMARY_MAX_CHARS)
    if summary:
        summary_font, summary_lines = _fit_block(
            draw,
            summary,
            "italic",
            full_width,
            max(MIN_TEXT_HEIGHT, available - provenance_height),
            4,
            mm(3.6),
        )
        y = _draw_lines(draw, MARGIN, description_y, summary_font, summary_lines)
    else:
        y = description_y

    if provenance_line:
        provenance_y = min(SLEEVE_HEIGHT - MARGIN - _line_height(provenance_font), y + 3)
        draw.text((MARGIN, provenance_y), provenance_line, font=provenance_font, fill=0, anchor="lt")
    return img


def save_pdf(images: list[Image.Image], path) -> None:
    """One fixed-size label per page, including the 62 mm roll's side gutters."""
    pages = []
    for image in images:
        page = Image.new("L", (PAPER_WIDTH, image.height), 255)
        page.paste(image.convert("L"), ((PAPER_WIDTH - WIDTH) // 2, 0))
        pages.append(page)
    if not pages:
        raise PrintError("save_pdf: no images to write")
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=DPI)


def print_images(images: list[Image.Image], model: str = "QL-700") -> None:
    """Send images to the first Brother QL found on USB."""
    from brother_ql.backends.helpers import send
    from brother_ql.conversion import convert
    from brother_ql.raster import BrotherQLRaster

    from lib.printer import discover

    printers = discover()
    if not printers:
        raise PrintError("no Brother QL printer found on USB")
    try:
        qlr = BrotherQLRaster(model)
        # Unsupported commands are expected for older models such as the QL-700.
        # Raising lets brother-ql's converter omit them instead of logging warnings.
        qlr.exception_on_warning = True
        instructions = convert(qlr=qlr, images=images, label="62", dither=False, rotate="auto")
        result = send(
            instructions=instructions,
            printer_identifier=printers[0],
            backend_identifier="pyusb",
            blocking=True,
        )
    except Exception as exc:
        raise PrintError(f"Brother {model} print failed: {exc}") from exc
    if result.get("outcome") == "error":
        errors = (result.get("printer_state") or {}).get("errors") or ["printer reported an error"]
        raise PrintError(f"Brother {model} print failed: {', '.join(map(str, errors))}")
