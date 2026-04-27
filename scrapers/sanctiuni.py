"""Scraper pentru sancțiunile aplicate deputaților (în plen, Birou Permanent).

Sursa: cdep.ro/pls/parlam/sanctiuni_parlam.lista_sanctionati?leg=YYYY&cam=2

Strategia:
1. O singură cerere HTTP per legislatură.
2. Conținutul vine în `<div class="grup-parlamentar-list">`.
3. Sancțiunile sunt delimitate de `<hr>`. Split pe hr → bloc per sancțiune.
4. Pentru fiecare bloc: extrag header `<b>` cu „DECIZIE", parsez data, numele,
   tipul, procentul/durata, apoi extrag link-uri PDF + stenogramă.

Vezi sitemap.md §9 + INTEGRATIONS.md pentru detalii.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import date
from urllib.parse import urljoin

from parsel import Selector

from schemas.common import Gender
from schemas.sanctiune import Sanctiune, TipSanctiune
from scrapers._http import get

logger = logging.getLogger(__name__)

BASE = "https://www.cdep.ro"
LIST_URL = BASE + "/pls/parlam/sanctiuni_parlam.lista_sanctionati?leg={leg}&cam={cam}"

ROMANIAN_MONTHS = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4,
    "mai": 5, "iunie": 6, "iulie": 7, "august": 8,
    "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
}

# Header pattern: "23 martie 2026 - DECIZIE privind aplicarea unei sancțiuni domnului|doamnei deputat NUME"
RE_HEADER = re.compile(
    r"(\d{1,2})\s+(ianuarie|februarie|martie|aprilie|mai|iunie|iulie|august|septembrie|octombrie|noiembrie|decembrie)\s+(\d{4})"
    r"\s*-\s*"
    r"(?:DECIZIE|HOT[ĂA]R[ÂA]RE|Informare|Retragerea|Chemarea)\s+",
    re.IGNORECASE,
)

RE_NAME = re.compile(
    r"(domnului|doamnei)\s+deputat\s+"
    r"(.+?)"  # nume — non-greedy
    r"(?:"
    r"\s+(?:de|e)\s+(?:diminuare|reducere|aplicare)"  # stop la „de/e diminuare" (sau glitch TOADER)
    r"|\s+pentru\s"
    r"|\s+prin\s"
    r"|,"  # virgulă (Anamaria Gavrilă, membră...)
    r"|\.\s"
    r"|\.$"
    r"|\s+HCD"
    r"|\s+membr[ăa]"
    r")",
    re.IGNORECASE,
)

RE_DIMINUARE = re.compile(
    r"diminuare(?:a)?\s+(?:a\s+)?indemniza[ţt]iei\s+cu\s+(\d+)%\s+pe\s+o\s+perioad[ăa]\s+de\s+(\d+)\s+lun[ăi]?",
    re.IGNORECASE,
)

RE_NR_DECIZIE = re.compile(r"vezi\s+decizia\s+Nr\.\s*(\d+/\d{1,2}-\d{1,2}-\d{4})", re.IGNORECASE)


def _parse_ro_date(day: str, month: str, year: str) -> date | None:
    m = ROMANIAN_MONTHS.get(month.lower())
    if not m:
        return None
    try:
        return date(int(year), m, int(day))
    except (ValueError, TypeError):
        return None


def _strip_diacritics(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


def _canonical_id(data: date, name: str, nr_decizie: str | None) -> str:
    key = f"{data.isoformat()}|{_strip_diacritics(name).lower().strip()}|{nr_decizie or ''}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _deputy_canonical_id(name: str) -> str:
    """Reproduce canonical_id-ul din scrapers/deputati.py (fără birth_date — best-effort)."""
    norm = " ".join(_strip_diacritics(name).lower().split())
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def _detect_tip(text: str) -> tuple[TipSanctiune, int | None, int | None]:
    """Returnează (tip, procent, durată_luni)."""
    lower = text.lower()
    m = RE_DIMINUARE.search(text)
    if m:
        return TipSanctiune.DIMINUARE_INDEMNIZATIE, int(m.group(1)), int(m.group(2))
    if "avertisment" in lower:
        return TipSanctiune.AVERTISMENT_SCRIS, None, None
    if "chemar" in lower and "ordine" in lower:
        return TipSanctiune.CHEMARE_ORDINE, None, None
    if "retragere" in lower and "cuv" in lower:
        return TipSanctiune.RETRAGERE_CUVANT, None, None
    return TipSanctiune.OTHER, None, None


def _detect_gender(text: str) -> Gender | None:
    if re.search(r"\bdoamnei\b|\bdoamna\b", text, re.IGNORECASE):
        return Gender.FEMALE
    if re.search(r"\bdomnului\b|\bdomnul\b", text, re.IGNORECASE):
        return Gender.MALE
    return None


def parse_block(block_html: str, leg: int) -> Sanctiune | None:
    """Parsează un bloc HTML care conține o sancțiune (între `<hr>`-uri)."""
    sel = Selector(text=block_html)

    # Header text — prima `<b>` cu data + DECIZIE
    bold_texts = [t.strip() for t in sel.css("b::text").getall() if t.strip()]
    header = next((t for t in bold_texts if RE_HEADER.search(t)), None)
    if not header:
        return None

    m = RE_HEADER.search(header)
    if not m:
        return None
    data = _parse_ro_date(m.group(1), m.group(2), m.group(3))
    if not data:
        return None

    # Name + gender
    nm = RE_NAME.search(header)
    if not nm:
        return None
    deputat_nume = " ".join(nm.group(2).split()).strip()
    if not deputat_nume:
        return None
    gender = _detect_gender(header)

    # Tip sancțiune
    tip, procent, durata = _detect_tip(header)

    # PDF decizie + nr decizie
    decizie_pdf = None
    nr_decizie = None
    for a in sel.css("a"):
        href = a.css("::attr(href)").get() or ""
        text = " ".join(a.css("*::text").getall()).strip()
        if "vezi decizia" in text.lower() and ".pdf" in href.lower():
            decizie_pdf = urljoin(BASE, href)
            m2 = RE_NR_DECIZIE.search(text)
            if m2:
                nr_decizie = m2.group(1)
            break

    # Stenogramă
    stenograma_url = None
    for href in sel.css("a::attr(href)").getall():
        if "steno" in href and "stenograma" in href:
            stenograma_url = urljoin(BASE, href)
            break

    return Sanctiune(
        id=_canonical_id(data, deputat_nume, nr_decizie),
        legislatura=leg,
        data=data,
        deputat_nume=deputat_nume,
        deputat_canonical_id=_deputy_canonical_id(deputat_nume),
        gender_hint=gender,
        tip=tip,
        procent=procent,
        durata_luni=durata,
        descriere=header,
        nr_decizie=nr_decizie,
        decizie_pdf_url=decizie_pdf,
        stenograma_url=stenograma_url,
    )


def scrape(leg: int = 2024, cam: int = 2) -> list[Sanctiune]:
    """Scrape toate sancțiunile pentru o legislatură."""
    url = LIST_URL.format(leg=leg, cam=cam)
    logger.info(f"sanctiuni scrape: leg={leg} cam={cam}")
    r = get(url)
    r.raise_for_status()
    sel = Selector(text=r.text)

    # Container — preferabil cu clasa specifică
    container = sel.css("div.grup-parlamentar-list").get() or sel.css("body").get()
    if not container:
        logger.error("no container found")
        return []

    # Split pe `<hr ... >` — fiecare segment = o sancțiune
    blocks = re.split(r"<hr[^>]*/?>", container, flags=re.IGNORECASE)

    results = []
    for i, block in enumerate(blocks):
        try:
            sanctiune = parse_block(block, leg=leg)
            if sanctiune:
                results.append(sanctiune)
                logger.info(f"  [{len(results)}] {sanctiune.data} - {sanctiune.deputat_nume} ({sanctiune.tip})")
        except Exception as e:
            logger.warning(f"  block {i} failed: {e}")

    logger.info(f"total: {len(results)} sancțiuni")
    return results
