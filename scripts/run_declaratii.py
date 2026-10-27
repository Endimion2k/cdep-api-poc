"""Rulează scraperul de declarații de avere și interese.

Storage: data/v1/declaratii/legislatura-{leg}.json

Utilizare:
    python scripts/run_declaratii.py                 # leg=2024
    python scripts/run_declaratii.py --leg 2020
    python scripts/run_declaratii.py --all           # 2024 + 2020 + 2016

UN SINGUR HTTP request per legislatură — foarte rapid (sub 1s).
Pentru update zilnic e suficient să rulezi cu o singură leg = curentă.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.common import Meta  # noqa: E402
from scrapers.declaratii import scrape  # noqa: E402

SCRAPER_VERSION = "0.1.0"
ALL_LEGS = [2024, 2020, 2016]


def run_one(leg: int) -> int:
    items = scrape(leg=leg)
    if not items:
        print(f"leg={leg}: niciun rezultat.")
        return 1

    out_path = ROOT / "data" / "v1" / "declaratii" / f"legislatura-{leg}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    new_data = [d.model_dump(mode="json", exclude_none=False) for d in items]

    # Semantic-diff: skip overwrite dacă conținutul e identic
    data_changed = True
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if existing.get("data") == new_data:
                data_changed = False
        except (json.JSONDecodeError, KeyError):
            pass

    if not data_changed:
        print(f"OK leg={leg} {len(items)} declarații - identic, skip overwrite.")
        return 0

    meta = Meta(
        generated_at=datetime.now(UTC),
        source_url=f"https://www.cdep.ro/ords/pls/dic/declaratii2015.deputati?tip=ai&leg={leg}",
        scraper_version=SCRAPER_VERSION,
        count=len(items),
    )
    payload = {"meta": meta.model_dump(mode="json"), "data": new_data}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Stats
    total_avere = sum(len(d.avere) for d in items)
    total_interese = sum(len(d.interese) for d in items)
    print(
        f"OK leg={leg}: {len(items)} deputați · {total_avere} declarații avere · "
        f"{total_interese} declarații interese · {out_path.stat().st_size:,} bytes"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leg", type=int, default=2024)
    parser.add_argument("--all", action="store_true", help="Run 2024 + 2020")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.all:
        for leg in ALL_LEGS:
            run_one(leg)
    else:
        return run_one(args.leg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
