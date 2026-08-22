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


def test_sleeve_dimensions_within_bounds():
    img = sleeve()
    assert img.size[0] == labels.WIDTH
    assert labels.SLEEVE_MIN_HEIGHT <= img.size[1] <= labels.SLEEVE_MAX_HEIGHT


def test_long_content_grows_the_label():
    short = sleeve(summary=None, style=None)
    long = sleeve(
        title="An Extremely Long Album Title That Will Certainly Wrap Around",
        artist="Someone, Someone Else, A Third Person, And An Entire Orchestra",
        summary="A much longer summary. " * 10,
        notes="bought somewhere memorable",
    )
    assert long.size[1] > short.size[1]
    assert long.size[1] <= labels.SLEEVE_MAX_HEIGHT


def test_divider_render():
    img = labels.render_divider("punk and goth", "New Wave · Post-Punk", QR, folder_id=42)
    assert img.size[0] == labels.WIDTH
    assert labels.DIVIDER_HEIGHT <= img.size[1] <= 520


def test_fit_or_wrap_respects_floor():
    from PIL import Image, ImageDraw

    draw = ImageDraw.Draw(Image.new("L", (10, 10)))
    font, lines = labels._fit_or_wrap(draw, "Short", "bold", 48, 34, 600)
    assert font.size == 48 and lines == ["Short"]
    font, lines = labels._fit_or_wrap(draw, "word " * 30, "bold", 48, 34, 600)
    assert font.size == 34 and 1 < len(lines) <= 2


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
