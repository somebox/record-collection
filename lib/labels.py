"""Render divider and sleeve labels as monochrome PNGs and print them on a
Brother QL over USB. 62mm continuous roll: printable width 696px at 300dpi."""

import io
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

WIDTH = 696  # printable dots across a 62mm roll
DIVIDER_HEIGHT = 300
MARGIN = 24

# Continuous roll: length along the tape is variable, so sleeve labels grow to fit.
SLEEVE_MIN_HEIGHT = 300
SLEEVE_MAX_HEIGHT = 600

QR_SIZE = 150  # fixed on both label types
TITLE_MAX, TITLE_MIN = 48, 34  # shrink between these; wrap to 2 lines below the floor

FONT_DIR = Path("/usr/share/fonts/truetype/liberation")
FONTS = {
    "regular": FONT_DIR / "LiberationSans-Regular.ttf",
    "bold": FONT_DIR / "LiberationSans-Bold.ttf",
    "italic": FONT_DIR / "LiberationSans-Italic.ttf",
}


class PrintError(Exception):
    pass


def _font(style: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS[style]), size)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, style: str, size: int, max_width: int):
    """Largest font ≤ size that fits text on one line."""
    while size > 12:
        font = _font(style, size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 4
    return _font(style, 12)


def _fit_or_wrap(
    draw: ImageDraw.ImageDraw, text: str, style: str,
    max_size: int, min_size: int, max_width: int, max_lines: int = 2,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Shrink between max and min size on one line; below the floor, wrap instead."""
    size = max_size
    while size >= min_size:
        font = _font(style, size)
        if draw.textlength(text, font=font) <= max_width:
            return font, [text]
        size -= 2
    font = _font(style, min_size)
    return font, _wrap(draw, text, font, max_width, max_lines=max_lines)


def _qr_block(img: Image.Image, draw: ImageDraw.ImageDraw, url: str, caption: str, y: int) -> int:
    """QR at fixed size, top-right, with the Discogs id below. Returns block bottom."""
    x = WIDTH - MARGIN - QR_SIZE
    img.paste(_qr(url, QR_SIZE), (x, y))
    font = _font("regular", 20)
    caption_w = draw.textlength(caption, font=font)
    draw.text((x + (QR_SIZE - caption_w) // 2, y + QR_SIZE + 4), caption, font=font, fill=0)
    return y + QR_SIZE + 4 + font.size


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            lines.append(line)
            line = word
            if len(lines) == max_lines:
                break
    if line and len(lines) < max_lines:
        lines.append(line)
    if len(lines) == max_lines and words and not " ".join(lines).endswith(words[-1]):
        lines[-1] = lines[-1][: max(0, len(lines[-1]) - 1)] + "…"
    return lines


def _qr(url: str, size: int) -> Image.Image:
    code = segno.make(url, error="m")
    modules = code.symbol_size(scale=1, border=2)[0]
    buf = io.BytesIO()
    code.save(buf, kind="png", scale=max(1, size // modules), border=2)
    return Image.open(buf).convert("L").resize((size, size), Image.NEAREST)


def render_divider(name: str, genre_line: str, qr_url: str, folder_id: int | None = None) -> Image.Image:
    """Title across the full top row; genres (left) and QR (right) below."""
    img = Image.new("L", (WIDTH, 520), 255)
    draw = ImageDraw.Draw(img)
    full_width = WIDTH - 2 * MARGIN
    y = MARGIN

    title_font, title_lines = _fit_or_wrap(draw, name.upper(), "bold", 110, 60, full_width)
    for line in title_lines:
        draw.text((MARGIN, y), line, font=title_font, fill=0)
        y += title_font.size + 8
    y += 12
    row_top = y

    qr_bottom = _qr_block(img, draw, qr_url, f"[f{folder_id}]" if folder_id else "", row_top)

    genre_bottom = row_top
    if genre_line:
        genre_width = WIDTH - QR_SIZE - 3 * MARGIN
        genre_font, genre_lines = _fit_or_wrap(draw, genre_line, "italic", 56, 44, genre_width, max_lines=3)
        gy = row_top + 8
        for line in genre_lines:
            draw.text((MARGIN, gy), line, font=genre_font, fill=0)
            gy += genre_font.size + 8
        genre_bottom = gy

    height = min(520, max(DIVIDER_HEIGHT, max(qr_bottom, genre_bottom) + MARGIN))
    return img.crop((0, 0, WIDTH, height))


def render_sleeve(item: dict, qr_url: str, include_paid: bool = False) -> Image.Image:
    # Draw on an oversized canvas, then crop: label length along the tape is variable.
    img = Image.new("L", (WIDTH, SLEEVE_MAX_HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    text_width = WIDTH - MARGIN - QR_SIZE - 2 * MARGIN
    y = MARGIN

    title_font, title_lines = _fit_or_wrap(
        draw, item["title"], "bold", TITLE_MAX, TITLE_MIN, text_width
    )
    for line in title_lines:
        draw.text((MARGIN, y), line, font=title_font, fill=0)
        y += title_font.size + 8
    y += 4

    byline = item["artist"] + (f" · {item['year']}" if item.get("year") else "")
    byline_font, byline_lines = _fit_or_wrap(draw, byline, "regular", 40, 28, text_width)
    for line in byline_lines:
        draw.text((MARGIN, y), line, font=byline_font, fill=0)
        y += byline_font.size + 6
    y += 6

    if item.get("style"):
        style_font, style_lines = _fit_or_wrap(draw, item["style"], "italic", 28, 22, text_width)
        for line in style_lines:
            draw.text((MARGIN, y), line, font=style_font, fill=0)
            y += style_font.size + 4
        y -= 4

    qr_bottom = _qr_block(img, draw, qr_url, f"[r{item['release_id']}]", MARGIN)
    top = max(y, qr_bottom) + 14
    draw.line([(MARGIN, top), (WIDTH - MARGIN, top)], fill=0, width=2)

    # below the rule — the long description, full width
    y = top + 14
    full_width = WIDTH - 2 * MARGIN
    # provenance line: notes, optionally with the paid price alongside its source
    provenance = [item.get("notes")] if item.get("notes") else []
    if include_paid and item.get("paid_price") is not None:
        provenance.append(f"paid ${item['paid_price']:,.0f}")
    provenance_line = " · ".join(provenance)
    if item.get("summary"):
        sum_font = _font("italic", 28)
        for line in _wrap(draw, item["summary"], sum_font, full_width, max_lines=5):
            draw.text((MARGIN, y), line, font=sum_font, fill=0)
            y += sum_font.size + 6
        y += 6
    if provenance_line:
        notes_font = _fit_font(draw, provenance_line, "italic", 24, full_width)
        draw.text((MARGIN, y), provenance_line, font=notes_font, fill=0)
        y += notes_font.size

    height = min(SLEEVE_MAX_HEIGHT, max(SLEEVE_MIN_HEIGHT, y + MARGIN))
    return img.crop((0, 0, WIDTH, height))


def print_images(images: list[Image.Image], model: str = "QL-700") -> None:
    """Send images to the first Brother QL found on USB."""
    from brother_ql.backends.helpers import send
    from brother_ql.conversion import convert
    from brother_ql.raster import BrotherQLRaster

    from lib.printer import discover

    printers = discover()
    if not printers:
        raise PrintError("no Brother QL printer found on USB")
    qlr = BrotherQLRaster(model)
    instructions = convert(qlr=qlr, images=images, label="62", dither=False, rotate="auto")
    send(
        instructions=instructions,
        printer_identifier=printers[0],
        backend_identifier="pyusb",
        blocking=True,
    )
