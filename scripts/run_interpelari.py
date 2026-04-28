"""Rulează scraperul de interpelări/întrebări și salvează JSON.

Storage: data/v1/interpelari/legislatura-{leg}.json (un fișier per legislatură,
toate anii inclusi).

Utilizare:
    python scripts/run_interpelari.py                        # leg curentă, anul curent
    python scripts/run_interpelari.py --year 2025
    python scripts/run_interpelari.py --year 2025 --leg 2024
    python scripts/run_interpelari.py --years 2024 2025 2026 # multi-year
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.common import Meta  # noqa: E402
from scrapers.interpelari import scrape_year  # noqa: E402

SCRAPER_VERSION = "0.1.0"


def detect_legislatura(year: int) -> int:
    if year >= 2024:
        return 2024
    if year >= 2020:
        return 2020
    if year >= 2016:
        return 2016
    return 2012


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=None, help="An (default: anul curent)")
    parser.add_argument("--years", type=int, nargs="+", help="Multiple ani: --years 2024 2025 2026")
    parser.add_argument("--leg", type=int, default=None, help="Legislatura (default: detect din year)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    years = args.years or [args.year or date.today().year]
    leg = args.leg or detect_legislatura(max(years))

    out_path = ROOT / "data" / "v1" / "interpelari" / f"legislatura-{leg}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Citim existent
    existing_ids: set[int] = set()
    existing_data: list[dict] = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            existing_data = existing.get("data", [])
            existing_ids = {item["cdep_idi"] for item in existing_data}
            print(f"Index existent: {len(existing_ids)} interpelări")
        except (json.JSONDecodeError, KeyError):
            pass

    # Scrape ani
    all_new = []
    for year in years:
        print(f"\n=== Anul {year} ===")
        items = scrape_year(year, legislatura=leg)
        new_items = [i for i in items if i.cdep_idi not in existing_ids]
        print(f"  {len(items)} găsite, {len(new_items)} noi")
        all_new.extend(new_items)

    if not all_new:
        print("Nicio actualizare.")
        return 0

    # Merge cu existent
    new_dicts = [i.model_dump(mode="json", exclude_none=False) for i in all_new]
    all_data = existing_data + new_dicts
    # Sortez după data_inregistrare descrescător
    all_data.sort(key=lambda x: (x.get("data_inregistrare") or ""), reverse=True)

    meta = Meta(
        generated_at=datetime.now(UTC),
        source_url=f"https://www.cdep.ro/pls/parlam/interpelari2015.lista?dat={max(years)}",
        scraper_version=SCRAPER_VERSION,
        count=len(all_data),
    )
    payload = {"meta": meta.model_dump(mode="json"), "data": all_data}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nOK +{len(all_new)} noi. Total în fișier: {len(all_data)}.")
    print(f"   {out_path} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
