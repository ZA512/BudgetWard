"""Server secrets supplied through environment variables or legacy mounted files."""

import os
from pathlib import Path


def read_secret(name: str) -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    filename = os.getenv(name + "_FILE")
    if not filename:
        return ""
    try:
        return Path(filename).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""
