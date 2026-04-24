"""Rulează scraperul de deputați și salvează JSON-ul.

    python scripts/run_deputati.py                    # toată legislatura 2024
    python scripts/run_deputati.py --limit 3          # test rapid
    python scripts/run_deputati.py --leg 2020         # altă legislatură

Env pentru paralelism (util pe CI):
    CDEP_SCRAPE_WORKERS=4
    CDEP_HTTP_THROTTLE_SECONDS=0.25
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.common import Meta  # noqa: E402
from scrapers.deputati import scrape  # noqa: E402

SCRAPER_VERSION = "0.1.0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leg", type=int, default=2024)
    parser.add_argument("--cam", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    deputati = scrape(leg=args.leg, cam=args.cam, limit=args.limit)

    out_path = (
        args.out
        or ROOT / "data" / "v1" / "deputati" / f"legislatura-{args.leg}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    new_data = [d.model_dump(mode="json", exclude_none=False) for d in deputati]

    # Semantic-diff: nu suprascriem dacă data e identică (doar timestamp)
    data_changed = True
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if existing.get("data") == new_data:
                data_changed = False
        except (json.JSONDecodeError, KeyError):
            pass

    if not data_changed:
        print(f"OK {len(deputati)} deputati - date identice, skip overwrite.")
        return 0

    meta = Meta(
        generated_at=datetime.now(timezone.utc),
        source_url=f"https://www.cdep.ro/pls/parlam/structura2015.home?leg={args.leg}",
        scraper_version=SCRAPER_VERSION,
        count=len(deputati),
    )
    payload = {"meta": meta.model_dump(mode="json"), "data": new_data}
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"OK {len(deputati)} deputati salvati in {out_path}")
    print(f"   File size: {out_path.stat().st_size:,} bytes")

    n = len(deputati)
    birth = sum(1 for d in deputati if d.birth_date)
    judet = sum(1 for d in deputati if d.judet)
    party = sum(1 for d in deputati if d.current_party)
    photo = sum(1 for d in deputati if d.image)
    comisii = sum(1 for d in deputati if d.comisii)
    print(
        f"   Coverage: birth={birth}/{n} judet={judet}/{n} "
        f"party={party}/{n} photo={photo}/{n} comisii={comisii}/{n}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
