from lib.printer import normalize_identifier


def test_normalize_pyusb_identifier_strips_serial_suffix():
    assert (
        normalize_identifier("usb://0x04f9:0x2042_000A8Z720417")
        == "usb://0x04f9:0x2042"
    )


def test_normalize_leaves_other_identifiers_unchanged():
    assert normalize_identifier("tcp://printer.local:9100") == "tcp://printer.local:9100"
