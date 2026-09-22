"""Migrare unică a datelor după mutarea cdep.ro pe /ords/ (2026).

- Rescrie în toate fișierele JSON din data/v1 link-urile vechi
  ``https://www.cdep.ro/pls/`` -> ``https://www.cdep.ro/ords/pls/`` (vechile căi dau 404).
- Curăță ``adresant_grup`` din interpelări de sufixul "Destinatar:" / "Destinatari:" rămas
  de la un parser vechi (ex. "AUR Destinatar:" -> "AUR").

Operează pe text, nu prin re-serializare JSON, ca diff-ul să conțină doar valorile schimbate.

Utilizare:
    python scripts/migrate_ords_urls.py            # aplică
    python scripts/migrate_ords_urls.py --dry-run  # doar raportează
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "v1"

OLD_PREFIX = "https://www.cdep.ro/pls/"
NEW_PREFIX = "https://www.cdep.ro/ords/pls/"
RE_GRUP = re.compile(r'("adresant_grup": ")([^"]*?)\s*Destinatari?\s*:[^"]*(")')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    files_changed = 0
    urls = 0
    grupuri = 0
    for path in sorted(DATA.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        new_text = text.replace(OLD_PREFIX, NEW_PREFIX)
        n_urls = text.count(OLD_PREFIX)
        n_grup = 0
        if path.parent.name.startswith("interpelari") or path.parent.parent.name == "interpelari":
            new_text, n_grup = RE_GRUP.subn(r"\1\2\3", new_text)
        if new_text == text:
            continue
        files_changed += 1
        urls += n_urls
        grupuri += n_grup
        if not args.dry_run:
            path.write_text(new_text, encoding="utf-8")

    verb = "de rescris" if args.dry_run else "rescrise"
    print(
        f"{files_changed} fișiere {verb}: {urls} link-uri /pls/ -> /ords/pls/, {grupuri} adresant_grup curățate"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
