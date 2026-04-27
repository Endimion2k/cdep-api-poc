"""Rulează scraperul de sancțiuni și salvează JSON.

    python scripts/run_sanctiuni.py                  # leg=2024
    python scripts/run_sanctiuni.py --leg 2020
    python scripts/run_sanctiuni.py --all            # toate legislaturile (2024+2020+2016)
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
from scrapers.sanctiuni import scrape  # noqa: E402

SCRAPER_VERSION = "0.1.0"
ALL_LEGS = [2024, 2020, 2016]


def run_one(leg: int, cam: int = 2) -> int:
    deputies = scrape(leg=leg, cam=cam)
    out_path = ROOT / "data" / "v1" / "sanctiuni" / f"legislatura-{leg}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    new_data = [d.model_dump(mode="json", exclude_none=False) for d in deputies]

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
        print(f"OK leg={leg} {len(deputies)} sanctiuni - identic, skip overwrite.")
        return 0

    meta = Meta(
        generated_at=datetime.now(UTC),
        source_url=f"https://www.cdep.ro/pls/parlam/sanctiuni_parlam.lista_sanctionati?leg={leg}&cam={cam}",
        scraper_version=SCRAPER_VERSION,
        count=len(deputies),
    )
    payload = {"meta": meta.model_dump(mode="json"), "data": new_data}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK leg={leg} {len(deputies)} sanctiuni salvate ({out_path.stat().st_size:,} bytes)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leg", type=int, default=2024)
    parser.add_argument("--cam", type=int, default=2)
    parser.add_argument("--all", action="store_true", help="Run pentru 2024+2020+2016")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.all:
        for leg in ALL_LEGS:
            run_one(leg, args.cam)
    else:
        run_one(args.leg, args.cam)
    return 0


if __name__ == "__main__":
    sys.exit(main())
