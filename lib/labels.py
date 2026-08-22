"""Render divider and sleeve labels as monochrome PNGs and print them on a
Brother QL over USB. 62mm continuous roll: printable width 696px at 300dpi."""

import io
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

WIDTH = 696  # printable dots across a 62mm roll
DIVIDER_HEIGHT = 300
SLEEVE_HEIGHT = 400
MARGIN = 24

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


def render_divider(name: str, genre_line: str, qr_url: str) -> Image.Image:
    img = Image.new("L", (WIDTH, DIVIDER_HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    qr_size = 200
    qr_x = WIDTH - MARGIN - qr_size
    text_width = qr_x - 2 * MARGIN

    title = name.upper()
    title_font = _fit_font(draw, title, "bold", 120, text_width)
    draw.text((MARGIN, 60), title, font=title_font, fill=0)
    if genre_line:
        genre_font = _fit_font(draw, genre_line, "italic", 36, text_width)
        draw.text((MARGIN, 200), genre_line, font=genre_font, fill=0)

    img.paste(_qr(qr_url, qr_size), (qr_x, (DIVIDER_HEIGHT - qr_size) // 2))
    return img


SLEEVE_TOP = 210  # fixed-height top section: title / artist·year / style + QR right


def render_sleeve(item: dict, qr_url: str, include_paid: bool = False) -> Image.Image:
    img = Image.new("L", (WIDTH, SLEEVE_HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    # top section — fixed box, QR pinned right
    qr_size = SLEEVE_TOP - 2 * MARGIN + 20
    qr_x = WIDTH - MARGIN - qr_size
    text_width = qr_x - 2 * MARGIN
    y = MARGIN

    title_font = _fit_font(draw, item["title"], "bold", 52, text_width)
    draw.text((MARGIN, y), item["title"], font=title_font, fill=0)
    y += title_font.size + 12

    byline = item["artist"] + (f" · {item['year']}" if item.get("year") else "")
    byline_font = _fit_font(draw, byline, "regular", 42, text_width)
    draw.text((MARGIN, y), byline, font=byline_font, fill=0)
    y += byline_font.size + 12

    if item.get("style"):
        style_font = _fit_font(draw, item["style"], "italic", 28, text_width)
        draw.text((MARGIN, y), item["style"], font=style_font, fill=0)

    img.paste(_qr(qr_url, qr_size), (qr_x, (SLEEVE_TOP - qr_size) // 2))
    draw.line([(MARGIN, SLEEVE_TOP), (WIDTH - MARGIN, SLEEVE_TOP)], fill=0, width=2)

    # lower half — the long description, full width
    y = SLEEVE_TOP + 14
    full_width = WIDTH - 2 * MARGIN
    # provenance line: notes, optionally with the paid price alongside its source
    provenance = [item.get("notes")] if item.get("notes") else []
    if include_paid and item.get("paid_price") is not None:
        provenance.append(f"paid ${item['paid_price']:,.0f}")
    provenance_line = " · ".join(provenance)
    if item.get("summary"):
        sum_font = _font("italic", 28)
        max_lines = 4 if provenance_line else 5
        for line in _wrap(draw, item["summary"], sum_font, full_width, max_lines=max_lines):
            draw.text((MARGIN, y), line, font=sum_font, fill=0)
            y += sum_font.size + 6
        y += 6
    if provenance_line:
        notes_font = _fit_font(draw, provenance_line, "italic", 24, full_width)
        draw.text((MARGIN, y), provenance_line, font=notes_font, fill=0)
    return img


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
