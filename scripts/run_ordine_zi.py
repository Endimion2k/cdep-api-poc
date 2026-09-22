"""Rulează scraperul pentru ordinea de zi a ședințelor plenului.

Storage: data/v1/ordine-zi/legislatura-{leg}.json

Utilizare:
    python scripts/run_ordine_zi.py                          # leg + anul curent, incremental
    python scripts/run_ordine_zi.py --year 2026
    python scripts/run_ordine_zi.py --years 2024 2025 2026
    python scripts/run_ordine_zi.py --year 2026 --leg 2024
    python scripts/run_ordine_zi.py --full                   # refetch toate sesiunile
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.common import Meta  # noqa: E402
from scrapers.ordine_zi import scrape_year  # noqa: E402

SCRAPER_VERSION = "0.1.0"

_RE_DAT = re.compile(r"dat=(\d{4})(\d{2})(\d{2})")


def _dedupe_by_id(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append(row)
    return out


def _covered_days(row: dict) -> set[date]:
    """Zilele de calendar deja acoperite de o sesiune: intervalul ei + ziua descărcată."""
    days: set[date] = set()
    with contextlib.suppress(ValueError, TypeError):
        start = date.fromisoformat(row.get("session_date"))
        end = date.fromisoformat(row.get("session_date_end") or row["session_date"])
        days.update(start + timedelta(n) for n in range((end - start).days + 1))
    m = _RE_DAT.search(row.get("source_url") or "")
    if m:
        with contextlib.suppress(ValueError):
            days.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return days


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
    parser.add_argument("--years", type=int, nargs="+", help="Multiple ani")
    parser.add_argument("--cam", type=int, default=2, help="Cameră (default: 2 = CD)")
    parser.add_argument(
        "--leg", type=int, default=None, help="Legislatura (default: detect din year)"
    )
    parser.add_argument(
        "--full", action="store_true", help="Refetch toate sesiunile (ignoră skip_dates)."
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    years = args.years or [args.year or date.today().year]
    leg = args.leg or detect_legislatura(max(years))

    out_path = ROOT / "data" / "v1" / "ordine-zi" / f"legislatura-{leg}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Citim existent — pentru incremental
    existing_dates: set[date] = set()
    existing_data: list[dict] = []
    if out_path.exists() and not args.full:
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            existing_data = _dedupe_by_id(existing.get("data", []))
            for d in existing_data:
                existing_dates.update(_covered_days(d))
            print(
                f"Index existent: {len(existing_data)} sesiuni, "
                f"{len(existing_dates)} zile acoperite (mod incremental)"
            )
        except (json.JSONDecodeError, KeyError):
            pass

    if args.full:
        print("Mod --full: refetch toate sesiunile.")

    # Scrape ani
    all_new = []
    for year in years:
        print(f"\n=== Anul {year} ===")
        items = scrape_year(year, legislatura=leg, cam=args.cam, skip_dates=existing_dates)
        all_new.extend(items)
        print(f"  {len(items)} sesiuni noi parsate")

    if not all_new and not existing_data:
        print("Niciun rezultat.")
        return 0

    # Merge — aceeași agendă multi-zi e descărcată o dată per zi din calendar, deci dedupe pe id
    new_dicts = _dedupe_by_id([oz.model_dump(mode="json", exclude_none=False) for oz in all_new])
    new_ids = {d["id"] for d in new_dicts}
    merged = [d for d in existing_data if d["id"] not in new_ids] + new_dicts
    merged.sort(key=lambda d: d.get("session_date") or "", reverse=True)

    meta = Meta(
        generated_at=datetime.now(UTC),
        source_url=f"https://www.cdep.ro/ords/pls/caseta/ecaseta2015.OrdineZi (leg={leg})",
        scraper_version=SCRAPER_VERSION,
        count=len(merged),
    )
    payload = {"meta": meta.model_dump(mode="json"), "data": merged}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nOK +{len(new_dicts)} noi. Total: {len(merged)} sesiuni.")
    print(f"   {out_path} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
