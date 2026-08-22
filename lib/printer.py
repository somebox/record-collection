"""Brother QL printer discovery. Label rendering/printing arrives in labels.py."""


def discover() -> list[str]:
    """Return identifiers of connected Brother QL printers (USB), e.g.
    ['usb://0x04f9:0x2042']. Empty list if none found or backend unavailable."""
    try:
        from brother_ql.backends.helpers import discover as ql_discover

        return [d["identifier"] for d in ql_discover("pyusb")]
    except Exception:
        return []
