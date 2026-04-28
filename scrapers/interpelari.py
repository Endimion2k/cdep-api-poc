"""Scraper pentru interpelări și întrebări parlamentare.

Strategia:
1. Pentru fiecare an, fetch `interpelari2015.lista?tip=&dat=YYYY` → listă cu link-uri detail.
2. Pentru fiecare detail (idi=N), fetch `interpelari2015.detalii?idi=N` → parsare info.

Sursa: cdep.ro/pls/parlam/interpelari2015.*
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import date
from urllib.parse import urljoin

from parsel import Selector

from schemas.interpelare import Interpelare
from scrapers._http import get

logger = logging.getLogger(__name__)

BASE = "https://www.cdep.ro"
LIST_URL = BASE + "/pls/parlam/interpelari2015.lista?tip=&dat={year}&idl=1"
DETAIL_URL = BASE + "/pls/parlam/interpelari2015.detalii?idi={idi}&idl=1"


def _strip_diacritics(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


def _voter_canonical_id(name: str) -> str:
    norm = " ".join(_strip_diacritics(name).lower().split())
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def _interpelare_id(legislatura: int, idi: int) -> str:
    return hashlib.sha256(f"{legislatura}|{idi}".encode()).hexdigest()[:16]


def _parse_iso_date(s: str) -> date | None:
    """Parsează data în format DD-MM-YYYY → date."""
    if not s:
        return None
    s = s.strip()
    m = re.match(r"(\d{1,2})-(\d{1,2})-(\d{4})", s)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except (ValueError, TypeError):
        return None


def list_idis_for_year(year: int) -> list[int]:
    """Returnează lista de idi pentru un an."""
    url = LIST_URL.format(year=year)
    try:
        r = get(url)
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"list year {year}: {e}")
        return []
    sel = Selector(text=r.text)
    idis = []
    for href in sel.css("a::attr(href)").getall():
        m = re.search(r"interpelari2015\.detalii\?idi=(\d+)", href)
        if m:
            idi = int(m.group(1))
            if idi not in idis:
                idis.append(idi)
    return idis


def parse_detail(idi: int, legislatura: int) -> Interpelare | None:
    """Fetch & parse o interpelare individuală."""
    url = DETAIL_URL.format(idi=idi)
    try:
        r = get(url)
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"  idi={idi}: {e}")
        return None

    sel = Selector(text=r.text)
    text = " ".join(sel.css("body *::text").getall())
    text = re.sub(r"\s+", " ", text).strip()

    # Header: "Interpelarea nr. 929B/10-02-2026 TITLU..."
    m_header = re.search(
        r"(?:Interpelarea|Întrebarea)\s+nr\.\s*([\dA-Za-z]+)/(\d{1,2}-\d{1,2}-\d{4})\s+([^\n]+?)(?=\s+Informa|$)",
        text,
    )
    if not m_header:
        logger.warning(f"  idi={idi}: header not found")
        return None
    nr_inregistrare = m_header.group(1)
    titlu_raw = m_header.group(3).strip()

    # Curăț titlul — elimin „Întrebări şi interpelări" și nr.929B repetat
    titlu = re.sub(r"^.*?nr\.\s*\S+\s+", "", titlu_raw, count=1).strip()
    if not titlu or titlu == titlu_raw:
        # fallback: ia primii 200 chars din titlu_raw
        titlu = titlu_raw[:200]

    # Câmpuri specifice — pattern „Label: value"
    def field(label: str, after: str = "") -> str | None:
        pattern = re.escape(label) + r"\s*:?\s*(.+?)(?=\s+(?:Nr\.|Data|Termen|Mod|Adresant|Destinatar|Textul|R[ăa]spuns|Camera|Informa|$))"
        m = re.search(pattern, text)
        return m.group(1).strip() if m else None

    data_inreg = _parse_iso_date(field("Data înregistrarii") or field("Data înregistrării") or "")
    data_prez = _parse_iso_date(field("Data prezentării") or "")
    data_com = _parse_iso_date(field("Data comunicării") or "")
    termen = _parse_iso_date(field("Termen primire răspuns") or "")
    mod_adresare = field("Mod adresare")

    # Adresant: "Călin-Florin Groza - deputat Neafiliaţi"
    adresant_nume = ""
    adresant_grup = None
    m_adr = re.search(r"Adresant:\s*([^-]+?)\s*-\s*deputat\s+([^\s]+(?:\s+[^\s]+)?)", text)
    if m_adr:
        adresant_nume = m_adr.group(1).strip()
        adresant_grup = m_adr.group(2).strip()
    else:
        adresant_nume = field("Adresant") or "?"

    destinatar = field("Destinatar") or "?"

    raspuns_solicitat = field("Răspuns solicitat")

    # Text PDF link
    text_pdf = None
    for href in sel.css('a::attr(href)').getall():
        if "pdf" in href.lower() and "Text" in (sel.css(f'a[href="{href}"]::text').get() or "") + str(href):
            text_pdf = urljoin(BASE, href)
            break
    # Mai simplu: primul PDF din pagină = textul interpelării
    if not text_pdf:
        for href in sel.css('a[href$=".pdf"]::attr(href)').getall():
            text_pdf = urljoin(BASE, href)
            break

    # Răspuns
    raspuns_primit = "Răspuns primit" in text
    raspuns_data = None
    raspuns_sursa = None
    raspuns_comunicat = None
    raspuns_pdf = None
    raspuns_nr = None
    if raspuns_primit:
        m_rasp = re.search(
            r"Informa[ţt]ii privind răspunsul\s+Nr\.\s*[îiî]nregistrare:?\s*(\S+)\s+Data\s+[îiî]nregistr[ăa]rii:?\s*(\d{1,2}-\d{1,2}-\d{4})",
            text,
        )
        if m_rasp:
            raspuns_nr = m_rasp.group(1)
            raspuns_data = _parse_iso_date(m_rasp.group(2))
        m_sursa = re.search(r"Răspuns primit de la:\s*([^\n]+?)\s+comunicat de:", text)
        if m_sursa:
            raspuns_sursa = m_sursa.group(1).strip()
        m_com = re.search(r"comunicat de:\s*([^\n]+?)\s+Textul răspunsului", text)
        if m_com:
            raspuns_comunicat = m_com.group(1).strip()
        # Al 2-lea PDF din pagină = textul răspunsului
        pdfs = sel.css('a[href$=".pdf"]::attr(href)').getall()
        if len(pdfs) >= 2:
            raspuns_pdf = urljoin(BASE, pdfs[1])

    # Build
    if not data_inreg:
        # Fallback din header
        data_inreg = _parse_iso_date(m_header.group(2))

    return Interpelare(
        id=_interpelare_id(legislatura, idi),
        cdep_idi=idi,
        legislatura=legislatura,
        nr_inregistrare=nr_inregistrare,
        data_inregistrare=data_inreg,
        data_prezentare=data_prez,
        data_comunicare=data_com,
        termen_raspuns=termen,
        titlu=titlu[:500],  # truncate la 500 chars
        mod_adresare=mod_adresare,
        adresant_nume=adresant_nume,
        adresant_canonical_id=_voter_canonical_id(adresant_nume) if adresant_nume != "?" else None,
        adresant_grup=adresant_grup,
        destinatar=destinatar,
        text_pdf_url=text_pdf,
        raspuns_solicitat=raspuns_solicitat,
        raspuns_primit=raspuns_primit,
        raspuns_nr_inregistrare=raspuns_nr,
        raspuns_data=raspuns_data,
        raspuns_sursa=raspuns_sursa,
        raspuns_comunicat_de=raspuns_comunicat,
        raspuns_pdf_url=raspuns_pdf,
        source_url=url,
    )


def scrape_year(year: int, legislatura: int) -> list[Interpelare]:
    idis = list_idis_for_year(year)
    logger.info(f"year={year}: {len(idis)} interpelări/întrebări")
    results = []
    for i, idi in enumerate(idis, 1):
        try:
            interp = parse_detail(idi, legislatura)
            if interp:
                results.append(interp)
                if i % 100 == 0:
                    logger.info(f"  [{i}/{len(idis)}] processed")
        except Exception as e:
            logger.warning(f"  idi={idi} failed: {e}")
    logger.info(f"year={year}: {len(results)} parsed successfully")
    return results
