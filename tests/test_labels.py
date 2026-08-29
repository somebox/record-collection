from PIL import Image, ImageDraw

from lib import labels

QR = "https://www.discogs.com/release/555"


def sleeve(**overrides):
    item = {
        "title": "Kind Of Blue", "artist": "Miles Davis", "year": 1959,
        "release_id": 555, "style": "modal jazz, cool",
        "summary": "A short summary.", "notes": None,
    }
    item.update(overrides)
    return labels.render_sleeve(item, QR)


def test_sleeve_is_fixed_62_by_34_mm_layout():
    img = sleeve()
    assert img.size == (labels.WIDTH, labels.mm(34))
    assert labels.PAPER_WIDTH == labels.mm(62)
    assert labels.QR_SIZE == labels.mm(13)


def test_long_content_stays_fixed_and_is_safely_fitted():
    short = sleeve(summary=None, style=None)
    long = sleeve(
        title="An Extremely Long Album Title That Will Certainly Wrap Around " * 5,
        artist="Someone, Someone Else, A Third Person, And An Entire Orchestra " * 5,
        style="experimental electroacoustic post-minimal chamber improvisation " * 5,
        summary="A much longer summary. " * 100,
        notes="bought somewhere memorable " * 20,
    )
    assert short.size == long.size == (labels.WIDTH, labels.SLEEVE_HEIGHT)
    assert short.tobytes() != long.tobytes()


def test_header_respects_height_and_minimum_type_size():
    draw = ImageDraw.Draw(Image.new("L", (labels.WIDTH, labels.SLEEVE_HEIGHT)))
    blocks, gap = labels._header_layout(
        draw,
        "A very long title that needs to wrap without crowding out the byline",
        "A very long artist credit with orchestra · 2026 · United Kingdom",
        "ambient, electroacoustic, contemporary classical",
        labels.WIDTH - labels.QR_SIZE - 3 * labels.MARGIN,
    )
    total = sum(labels._line_height(font) * len(lines) for font, lines in blocks)
    total += gap * (len(blocks) - 1)
    assert total <= labels.HEADER_TEXT_HEIGHT
    assert all(labels._line_height(font) >= labels.MIN_TEXT_HEIGHT for font, _ in blocks)
    assert all(len(lines) <= 2 for _, lines in blocks)


def test_divider_is_fixed_62_by_25_mm_layout():
    img = labels.render_divider("punk and goth", "New Wave · Post-Punk", QR, folder_id=42)
    assert img.size == (labels.WIDTH, labels.mm(25))


def test_divider_casing_preserves_proper_names_and_uppercases_categories():
    assert labels._divider_title("Miles Davis") == "Miles Davis"
    assert labels._divider_title("Radiohead") == "Radiohead"
    assert labels._divider_title("XTC") == "XTC"
    assert labels._divider_title("brasil") == "BRASIL"
    assert labels._divider_title("classic rock") == "CLASSIC ROCK"


def test_wrap_caps_lines_and_ellipsizes_extreme_words():
    draw = ImageDraw.Draw(Image.new("L", (10, 10)))
    font = labels._font_at_height("regular", labels.MIN_TEXT_HEIGHT)
    lines = labels._wrap(draw, "x" * 1000, font, 120, max_lines=2)
    assert len(lines) <= 2
    assert draw.textlength(lines[-1], font=font) <= 120
    assert lines[-1].endswith("…")


def test_paid_price_joins_provenance():
    with_paid = labels.render_sleeve(
        {"title": "X", "artist": "Y", "year": 2000, "release_id": 1,
         "notes": "from Tom", "paid_price": 12.0, "summary": None, "style": None},
        QR, include_paid=True,
    )
    without = labels.render_sleeve(
        {"title": "X", "artist": "Y", "year": 2000, "release_id": 1,
         "notes": "from Tom", "paid_price": 12.0, "summary": None, "style": None},
        QR, include_paid=False,
    )
    assert with_paid.tobytes() != without.tobytes()


def test_country_appears_on_byline():
    assert sleeve(country="US").tobytes() != sleeve(country=None).tobytes()


def test_save_pdf(tmp_path):
    path = tmp_path / "out.pdf"
    labels.save_pdf([sleeve(), sleeve(title="Second")], path)
    assert path.stat().st_size > 1000
