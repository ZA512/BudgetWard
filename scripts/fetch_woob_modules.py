"""Installe le seul module bancaire retenu, depuis une archive officielle vérifiée."""

import argparse
import hashlib
import io
import tarfile
import urllib.request
from pathlib import Path

REVISION = "3bc0f159c65fc2685c8b8787d0e25ff55f896f73"
SHA256 = "147b7d39bb12a7ef1750fceba0999a8acdff8382e01cbb734b5fd9f17e989e2e"
URL = f"https://gitlab.com/woob/woob/-/archive/{REVISION}/woob-{REVISION}.tar.gz"


def install(destination: Path):
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read(30_000_001)
    if len(data) > 30_000_000 or hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("L'archive Woob ne correspond pas à la version approuvée.")
    root = f"woob-{REVISION}/"
    files = {
        f"modules/cragr/{name}": f"cragr/{name}"
        for name in ("__init__.py", "browser.py", "pages.py", "module.py", "requirements.txt")
    }
    files.update({"COPYING": "COPYING", "COPYING.LESSER": "COPYING.LESSER"})
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        # Pas d'extraction générique : seuls ces fichiers réguliers sont écrits.
        for source, target in files.items():
            member = archive.getmember(root + source)
            if not member.isfile():
                raise RuntimeError("Archive Woob invalide.")
            path = destination / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
    (destination / "SOURCE.txt").write_text(f"{URL}\nSHA256 {SHA256}\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=Path("bank_modules"))
    install(parser.parse_args().destination)
