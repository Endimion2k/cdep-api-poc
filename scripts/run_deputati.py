"""Rulează scraperul de deputați și salvează JSON-ul în `data/v1/deputati/`.

Utilizare:
    python scripts/run_deputati.py                    # toată legislatura 2024
    python scripts/run_deputati.py --limit 3          # test rapid (primii 3)
    python scripts/run_deputati.py --leg 2020         # altă legislatură
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permite rulare de oriunde
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.common import Meta  # noqa: E402
from scrapers.deputati import scrape  # noqa: E402

SCRAPER_VERSION = "0.1.0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leg", type=int, default=2024, help="Legislatură (ex: 2024)")
    parser.add_argument("--cam", type=int, default=2, help="Cameră (2=Deputați)")
    parser.add_argument("--limit", type=int, default=None, help="Limitare nr. deputați (test)")
    parser.add_argument("--out", type=Path, default=None, help="Fișier output")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    deputati = scrape(leg=args.leg, cam=args.cam, limit=args.limit)

    out_path = args.out or ROOT / "data" / "v1" / "deputati" / f"legislatura-{args.leg}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    new_data = [d.model_dump(mode="json", exclude_none=False) for d in deputati]

    # Semantic-diff: dacă `data` e identic cu ce există pe disk, nu suprascriem.
    # Evităm commits zilnice fără valoare (doar schimbarea de timestamp).
    data_changed = True
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if existing.get("data") == new_data:
                data_changed = False
        except (json.JSONDecodeError, KeyError):
            pass  # fișier corupt → rewrite

    if not data_changed:
        print(f"✓ {len(deputati)} deputați — date identice, skip overwrite.")
        print(f"  File: {out_path}")
        return 0

    meta = Meta(
        generated_at=datetime.now(timezone.utc),
        source_url=f"https://www.cdep.ro/pls/parlam/structura2015.home?leg={args.leg}",
        scraper_version=SCRAPER_VERSION,
        count=len(deputati),
    )
    payload = {"meta": meta.model_dump(mode="json"), "data": new_data}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✓ {len(deputati)} deputați salvați în {out_path}")
    print(f"  File size: {out_path.stat().st_size:,} bytes")

    # Sanity summary
    with_birth = sum(1 for d in deputati if d.birth_date)
    with_judet = sum(1 for d in deputati if d.judet)
    with_party = sum(1 for d in deputati if d.current_party)
    with_photo = sum(1 for d in deputati if d.image)
    with_comisii = sum(1 for d in deputati if d.comisii)
    n = len(deputati)
    print(
        f"  Coverage: birth_date={with_birth}/{n} · judet={with_judet}/{n} · "
        f"party={with_party}/{n} · photo={with_photo}/{n} · comisii={with_comisii}/{n}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
