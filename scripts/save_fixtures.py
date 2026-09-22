"""Salvează HTML fixture-uri din cdep.ro pentru snapshot testing.

Fixture-urile sunt commit-ate în `tests/fixtures/` și folosite de teste pentru a
detecta regresii de parsing dacă cdep.ro schimbă structura HTML.

Rulează această comandă o singură dată (sau periodic) pentru a actualiza fixture-urile:
    python scripts/save_fixtures.py

ID-urile alese sunt entități stabile, bine-cunoscute, din legislatura 2024.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers._http import get  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
FIXTURES.mkdir(parents=True, exist_ok=True)

# Entități stabile (alese pentru a fi rare să dispară)
TARGETS = [
    # (nume_fișier, url)
    (
        "deputat_189.html",
        "https://www.cdep.ro/ords/pls/parlam/structura2015.mp?idm=189&cam=2&leg=2024",
    ),
    (
        "deputat_22_baisanu.html",  # istoric de partid multiplu (SOS -> neafiliat -> PUSL)
        "https://www.cdep.ro/ords/pls/parlam/structura2015.mp?idm=22&cam=2&leg=2024",
    ),
    (
        "deputat_3_albu.html",  # delegații + roluri în grupurile de prietenie
        "https://www.cdep.ro/ords/pls/parlam/structura2015.mp?idm=3&cam=2&leg=2024",
    ),
    (
        "vot_36892.html",  # Bugetul de stat 2025 - vot final
        "https://www.cdep.ro/ords/pls/steno/evot2015.nominal?idv=36892&idl=1",
    ),
    (
        "interpelare_77316.html",
        "https://www.cdep.ro/ords/pls/parlam/interpelari2015.detalii?idi=77316&idl=1",
    ),
    (
        "motiune_1583.html",  # Dreptate pentru România
        "https://www.cdep.ro/ords/pls/parlam/parlament.motiuni2015.detalii?leg=2024&cam=2&idm=1583",
    ),
    (
        "sanctiuni_2024.html",  # Lista sancțiuni - sursă pentru test parser
        "https://www.cdep.ro/ords/pls/parlam/sanctiuni_parlam.lista_sanctionati?leg=2024&cam=2",
    ),
    # proiect_22201.html există deja, nu re-salvez
]


def main() -> int:
    print(f"Salvez fixture-uri în {FIXTURES}/")
    saved = 0
    for filename, url in TARGETS:
        path = FIXTURES / filename
        try:
            r = get(url, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"  ⚠ {filename}: {e}")
            continue
        path.write_text(r.text, encoding="utf-8")
        size_kb = path.stat().st_size / 1024
        print(f"  ✓ {filename}: {size_kb:.1f} KB")
        saved += 1

    print(f"\nOK: {saved}/{len(TARGETS)} fixture-uri salvate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
