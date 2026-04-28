"""Rulează scraperul de voturi și salvează JSON-uri.

Strategie incrementală: la fiecare rulare scrape ultimele N zile, dar salvăm
doar voturile cu idv > max_idv existent. Asta permite cron zilnic ieftin.

Storage:
    data/v1/voturi/{leg}/_index.json     -- toate evenimentele (sumar)
    data/v1/voturi/{leg}/{idv}.json      -- detaliu per vot (nominal complet)

Utilizare:
    python scripts/run_voturi.py                    # ultimele 7 zile
    python scripts/run_voturi.py --days 30
    python scripts/run_voturi.py --from 2024-12-13  # bootstrap istoric
    python scripts/run_voturi.py --from 2024-12-13 --to 2025-01-01
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.common import Meta  # noqa: E402
from schemas.vot import VoteEventSummary  # noqa: E402
from scrapers.voturi import scrape_range  # noqa: E402

SCRAPER_VERSION = "0.1.0"


def detect_legislatura(d: date) -> int:
    """Maparea aproximativă date → legislatură.

    Hardcoded pentru POC. La production se citește dintr-un config.
    """
    if d >= date(2024, 12, 13):
        return 2024
    if d >= date(2020, 12, 21):
        return 2020
    if d >= date(2016, 12, 21):
        return 2016
    return 2012


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="Zile înapoi (default 7)")
    parser.add_argument("--from", dest="from_date", type=str, help="Data de start (YYYY-MM-DD), override --days")
    parser.add_argument("--to", dest="to_date", type=str, help="Data de sfârșit (YYYY-MM-DD), default azi")
    parser.add_argument("--leg", type=int, default=None, help="Legislatura (default = detect din to_date)")
    parser.add_argument("--cam", type=int, default=2)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    end = date.fromisoformat(args.to_date) if args.to_date else date.today()
    if args.from_date:
        start = date.fromisoformat(args.from_date)
    else:
        start = end - timedelta(days=args.days)

    leg = args.leg or detect_legislatura(end)
    logger = logging.getLogger(__name__)
    logger.info(f"Scraping voturi: {start} → {end}, leg={leg}, cam={args.cam}")

    out_dir = ROOT / "data" / "v1" / "voturi" / str(leg)
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "_index.json"

    # Citim index existent — pentru a ști care idv-uri avem deja
    existing_ids: set[int] = set()
    existing_summaries: list[dict] = []
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
            existing_summaries = existing.get("data", [])
            existing_ids = {item["cdep_idv"] for item in existing_summaries}
            print(f"Index existent: {len(existing_ids)} voturi deja procesate")
        except (json.JSONDecodeError, KeyError):
            pass

    # Scrape interval
    events = scrape_range(start=start, end=end, legislatura=leg, cam=args.cam, progress=args.verbose)

    # Filter doar voturi noi
    new_events = [ev for ev in events if ev.cdep_idv not in existing_ids]
    print(f"Total voturi în interval: {len(events)}, noi: {len(new_events)}")

    if not new_events:
        print("Nicio actualizare.")
        return 0

    # Salvăm fiecare vot nou ca fișier individual
    for ev in new_events:
        detail_path = out_dir / f"{ev.cdep_idv}.json"
        payload = {
            "meta": Meta(
                generated_at=datetime.now(UTC),
                source_url=str(ev.source_url),
                scraper_version=SCRAPER_VERSION,
                count=len(ev.votes),
            ).model_dump(mode="json"),
            "data": ev.model_dump(mode="json"),
        }
        detail_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Actualizăm index
    new_summaries = [
        VoteEventSummary(
            id=ev.id,
            cdep_idv=ev.cdep_idv,
            legislatura=ev.legislatura,
            cam=ev.cam,
            timestamp=ev.timestamp,
            descriere=ev.descriere,
            counts=ev.counts,
            detail_url=f"voturi/{ev.legislatura}/{ev.cdep_idv}.json",
        ).model_dump(mode="json")
        for ev in new_events
    ]

    all_summaries = existing_summaries + new_summaries
    # Sortez după timestamp descrescător (cele mai noi primele)
    all_summaries.sort(key=lambda s: s["timestamp"], reverse=True)

    index_payload = {
        "meta": Meta(
            generated_at=datetime.now(UTC),
            source_url=f"https://www.cdep.ro/pls/steno/evot2015.data?leg={leg}",
            scraper_version=SCRAPER_VERSION,
            count=len(all_summaries),
        ).model_dump(mode="json"),
        "data": all_summaries,
    }
    index_path.write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"OK +{len(new_events)} voturi noi. Total în index: {len(all_summaries)}.")
    print(f"   {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
