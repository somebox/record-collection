"""Brother QL printer discovery and USB identifier handling."""


def normalize_identifier(identifier: str) -> str:
    """Strip the serial suffix emitted by brother-ql's pyusb discovery.

    Discovery returns ``usb://vendor:product_SERIAL``, while the backend parser
    only accepts hexadecimal product IDs (or a slash-delimited serial). Selecting
    by vendor/product is reliable for the first discovered printer and avoids the
    package's internally inconsistent serial format.
    """
    return identifier.partition("_")[0] if identifier.startswith("usb://") else identifier


def discover() -> list[str]:
    """Return identifiers of connected Brother QL printers (USB), e.g.
    ['usb://0x04f9:0x2042']. Empty list if none found or backend unavailable."""
    try:
        from brother_ql.backends.helpers import discover as ql_discover

        return [normalize_identifier(d["identifier"]) for d in ql_discover("pyusb")]
    except Exception:
        return []
