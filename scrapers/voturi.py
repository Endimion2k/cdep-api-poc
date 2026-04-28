"""Scraper pentru voturile electronice (plen).

Strategia:
1. Iterăm prin weekday-uri în intervalul legislaturii (sărim sâmbete/duminici).
2. Pentru fiecare zi, fetch `evot2015.xml?par1=1&par2=YYYYMMDD` → listă agregate.
3. Pentru fiecare VOTID din XML, fetch `evot2015.nominal?idv=N` → tabel nominal.
4. Producem `VoteEvent` cu toate detaliile.

Sursa: cdep.ro/pls/steno/evot2015.{xml,nominal}
Vezi sitemap.md §2 pentru detalii URL.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from parsel import Selector

from schemas.common import VoteOption
from schemas.vot import VoteCounts, VoteEvent, VoteIndividual
from scrapers._http import get

logger = logging.getLogger(__name__)

BASE = "https://www.cdep.ro"
XML_URL = BASE + "/pls/steno/evot2015.xml?par1=1&par2={date_compact}"
NOMINAL_URL = BASE + "/pls/steno/evot2015.nominal?idv={idv}&idl=1"

# Mapare DA/NU/AB/- → VoteOption
VOTE_OPTION_MAP = {
    "DA": VoteOption.YES,
    "NU": VoteOption.NO,
    "AB": VoteOption.ABSTAIN,
    "-": VoteOption.NOT_VOTING,
}


def _strip_diacritics(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


def _voter_canonical_id(name: str) -> str:
    """Reproduce canonical_id din scrapers/deputati.py (best-effort, fără birth_date)."""
    norm = " ".join(_strip_diacritics(name).lower().split())
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def _vote_event_id(legislatura: int, idv: int) -> str:
    """ID stabil pentru eveniment de vot."""
    return hashlib.sha256(f"{legislatura}|{idv}".encode()).hexdigest()[:16]


def fetch_day_xml(d: date) -> list[dict]:
    """Returnează lista agregată de voturi dintr-o zi.

    Format per item: {idv, time_vot, descriere, camera, prezenti, da, nu, ab, nu_au_votat}.
    Returnează listă goală dacă ziua nu are voturi.
    """
    url = XML_URL.format(date_compact=d.strftime("%Y%m%d"))
    try:
        r = get(url)
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"day xml {d}: {e}")
        return []
    if not r.content or len(r.content) < 50:
        return []  # pagină goală, fără voturi
    try:
        # cdep.ro returnează XML codat ISO-8859-2; ElementTree decodează din declarație
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        logger.warning(f"day xml {d}: parse error {e}")
        return []

    rows = []
    for row in root.findall("ROW"):
        try:
            rows.append({
                "idv": int(row.findtext("VOTID", "0")),
                "time_vot": row.findtext("TIME_VOT", ""),
                "descriere": row.findtext("DESCRIERE", "").strip(),
                "camera": int(row.findtext("CAMERA", "0")),
                "prezenti": int(row.findtext("PREZENTI", "0")),
                "da": int(row.findtext("AU_VOTAT_DA", "0")),
                "nu": int(row.findtext("AU_VOTAT_NU", "0")),
                "ab": int(row.findtext("AU_VOTAT_AB", "0")),
                "nu_au_votat": int(row.findtext("NU_AU_VOTAT", "0")),
            })
        except (ValueError, TypeError) as e:
            logger.warning(f"  skip row in {d}: {e}")
    return rows


def parse_nominal_html(html: str, idv: int) -> list[VoteIndividual]:
    """Extrage tabelul deputat-vot din pagina nominal.

    Format: '# Nume si prenume Grup Vot' apoi rânduri '1. Nume Grup DA'.
    """
    sel = Selector(text=html)

    # Caut tabelul cu antetul „Nume si prenume" și „Vot"
    target_table = None
    for table in sel.css("table"):
        head_text = " ".join(table.css("th::text, tr:first-child *::text").getall())
        if "Nume" in head_text and "Vot" in head_text:
            target_table = table
            break

    if not target_table:
        # Fallback: cel mai mare tabel cu rânduri de 4 celule
        for table in sel.css("table"):
            rows = table.css("tr")
            if len(rows) > 50 and len(rows[1].css("td")) == 4:
                target_table = table
                break

    if not target_table:
        return []

    votes = []
    for row in target_table.css("tr"):
        cells = row.css("td")
        if len(cells) != 4:
            continue
        # Cell 0 = #, Cell 1 = nume, Cell 2 = grup, Cell 3 = vot
        nr_text = " ".join(cells[0].css("*::text").getall()).strip()
        if not nr_text or not nr_text[0].isdigit():
            continue
        name = " ".join(" ".join(cells[1].css("*::text").getall()).split()).strip()
        party = " ".join(" ".join(cells[2].css("*::text").getall()).split()).strip()
        vote_text = " ".join(cells[3].css("*::text").getall()).strip()

        if not name:
            continue

        option = VOTE_OPTION_MAP.get(vote_text)
        if option is None:
            # default fallback — log warning
            logger.debug(f"  idv={idv} unknown vote text: {vote_text!r}")
            option = VoteOption.NOT_VOTING

        votes.append(
            VoteIndividual(
                voter_canonical_id=_voter_canonical_id(name),
                voter_name=name,
                party=party or None,
                option=option,
            )
        )
    return votes


def fetch_vote_event(idv: int, day_meta: dict, legislatura: int) -> VoteEvent | None:
    """Construiește VoteEvent complet din metadata zilei + parsing nominal."""
    url = NOMINAL_URL.format(idv=idv)
    try:
        r = get(url)
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"  idv={idv}: fetch failed: {e}")
        return None

    votes = parse_nominal_html(r.text, idv)
    if not votes:
        logger.warning(f"  idv={idv}: no votes parsed")
        return None

    # Parse "22.04.2026 12:41" → datetime
    try:
        ts = datetime.strptime(day_meta["time_vot"], "%d.%m.%Y %H:%M")
    except (ValueError, KeyError):
        ts = datetime.combine(date.today(), datetime.min.time())

    return VoteEvent(
        id=_vote_event_id(legislatura, idv),
        cdep_idv=idv,
        legislatura=legislatura,
        cam=day_meta.get("camera", 2),
        timestamp=ts,
        descriere=day_meta.get("descriere", ""),
        counts=VoteCounts(
            prezenti=day_meta.get("prezenti", 0),
            pentru=day_meta.get("da", 0),
            contra=day_meta.get("nu", 0),
            abtineri=day_meta.get("ab", 0),
            nu_au_votat=day_meta.get("nu_au_votat", 0),
        ),
        votes=votes,
        source_url=url,
    )


def iter_weekdays(start: date, end: date) -> Iterator[date]:
    """Iterează doar Mon-Fri între start și end (inclusiv)."""
    d = start
    while d <= end:
        if d.weekday() < 5:  # 0=Mon .. 4=Fri
            yield d
        d += timedelta(days=1)


def scrape_range(
    start: date,
    end: date,
    legislatura: int,
    cam: int = 2,
    progress: bool = True,
) -> list[VoteEvent]:
    """Scrape toate voturile între start și end (inclusiv)."""
    events = []
    days_with_votes = 0
    total_votes = 0
    for d in iter_weekdays(start, end):
        rows = fetch_day_xml(d)
        rows = [r for r in rows if r.get("camera") == cam]
        if not rows:
            continue
        days_with_votes += 1
        if progress:
            logger.info(f"{d.isoformat()}: {len(rows)} voturi")
        for row in rows:
            ev = fetch_vote_event(row["idv"], row, legislatura)
            if ev:
                events.append(ev)
                total_votes += 1
    logger.info(f"Total: {total_votes} voturi în {days_with_votes} zile")
    return events
