"""Scraper pentru stenograme ședințe plen.

Strategia:
1. Calendar anual: `/ords/pls/steno/steno2015.calendar?cam=2&an=YYYY&TIP=0&idl=1`
   → returnează HTML cu link-uri la zilele cu ședință.
2. Cuprins: `/ords/pls/steno/steno2015.data?cam=2&dat=YYYYMMDD&idl=1`
   → doar sumarul ședinței, cu link-uri `steno2015.sumar?ids=<ids>`.
3. Transcriere: `/ords/pls/steno/steno2015.stenograma?ids=<ids>&idl=1`
   → textul integral; intervențiile se delimitează după "Domnul/Doamna NUME (PARTID):".

Sursa: cdep.ro/ords/pls/steno/steno2015.*
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from html.parser import HTMLParser
from typing import ClassVar

from parsel import Selector

from schemas.stenograma import Stenograma, StenogramaIntervention
from scrapers._http import get

logger = logging.getLogger(__name__)

BASE = "https://www.cdep.ro"
CAL_URL = BASE + "/ords/pls/steno/steno2015.calendar?cam={cam}&an={year}&TIP=0&idl=1"
DETAIL_URL = BASE + "/ords/pls/steno/steno2015.data?cam={cam}&dat={ymd}&idl=1"
TRANSCRIPT_URL = BASE + "/ords/pls/steno/steno2015.stenograma?ids={ids}&idl=1"

MAX_INTERVENTION_CHARS = 5000
MIN_INTERVENTION_CHARS = 4

_IDS_RE = re.compile(r"steno2015\.(?:sumar|stenograma)\?ids=(\d+)")

# Vorbitorul e la început de linie: "Domnul/Doamna [rol] Nume Prenume (PARTID):"
_SPEAKER_RE = re.compile(
    r"""
    ^\s*
    (?P<honorific>Domnul|Doamna)
    (?:\s+(?P<rol>
        (?:vice)?pre[şs]edinte(?:\s+de\s+[şs]edin[ţt][ăa])?
      | deputat(?:\s+(?:independent|neafiliat))?
      | senator
      | prim-?ministru
      | ministru
      | secretar(?:\s+de\s+stat)?
      | sub[şs]ef
      | primar
      | invitat
    ))?
    \s+
    (?P<nume>[A-ZĂÂÎȘȚŞŢ][\w\-\.]*(?:\s+[A-ZĂÂÎȘȚŞŢ\-][\w\-\.]*)*)
    (?:\s*\((?P<paranteza>[^)]{1,80})\))?
    \s*:\s*
    """,
    re.VERBOSE | re.MULTILINE,
)
# Paranteza de după nume e partidul doar când arată ca un cod ("PSD", "SOS RO"); altfel e un
# rol ("senator") sau context ("din sală").
_PARTY_CODE_RE = re.compile(r"[A-ZĂÂÎȘȚŞŢ][A-ZĂÂÎȘȚŞŢ\.\s\-]{1,20}")
_ROLE_WORDS = frozenset({"senator", "deputat", "ministru", "secretar de stat", "invitat"})


class _TextExtractor(HTMLParser):
    """Text cu o linie nouă la fiecare element bloc, ca să putem ancora vorbitorii pe linii."""

    _BLOCK_TAGS: ClassVar[frozenset[str]] = frozenset(
        {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
    )
    _DROP_TAGS: ClassVar[frozenset[str]] = frozenset({"script", "style", "head", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._buf: list[str] = []
        self._suppress = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._DROP_TAGS:
            self._suppress += 1
        elif tag in self._BLOCK_TAGS and self._suppress == 0:
            self._buf.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._DROP_TAGS:
            self._suppress = max(0, self._suppress - 1)
        elif tag in self._BLOCK_TAGS and self._suppress == 0:
            self._buf.append("\n")

    def handle_data(self, data: str) -> None:
        if self._suppress == 0:
            self._buf.append(data)

    def get_text(self) -> str:
        lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in "".join(self._buf).split("\n")]
        return "\n".join(ln for ln in lines if ln)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.get_text()


def transcript_ids(index_html: str) -> str | None:
    """`ids`-ul ședinței, din link-urile paginii-cuprins."""
    m = _IDS_RE.search(index_html)
    return m.group(1) if m else None


def parse_interventions(text: str) -> list[StenogramaIntervention]:
    """Împarte textul transcrierii în intervenții, în ordinea din document."""
    matches = list(_SPEAKER_RE.finditer(text))
    out: list[StenogramaIntervention] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip()
        if len(body) < MIN_INTERVENTION_CHARS:
            continue
        rol = (m.group("rol") or "").strip().lower() or None
        partid = None
        paranteza = (m.group("paranteza") or "").strip()
        if paranteza and _PARTY_CODE_RE.fullmatch(paranteza):
            partid = paranteza
        elif paranteza.lower() in _ROLE_WORDS and not rol:
            rol = paranteza.lower()
        out.append(
            StenogramaIntervention(
                vorbitor=m.group("nume").strip(),
                partid=partid,
                rol=rol,
                text=body[:MAX_INTERVENTION_CHARS],
            )
        )
    return out


def _steno_id(cam: int, session_date: date) -> str:
    return hashlib.sha256(f"{cam}|{session_date.isoformat()}".encode()).hexdigest()[:16]


def list_session_dates_for_year(year: int, cam: int = 2) -> list[date]:
    """Listează datele cu ședință de plen pentru un an.

    Parsează HTML-ul calendarului anual și extrage link-urile `steno2015.data?dat=YYYYMMDD`.
    """
    url = CAL_URL.format(cam=cam, year=year)
    try:
        r = get(url)
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"calendar {year} cam={cam}: {e}")
        return []
    sel = Selector(text=r.text)
    seen: set[date] = set()
    out: list[date] = []
    for href in sel.css('a[href*="steno2015.data"]::attr(href)').getall():
        m = re.search(r"dat=(\d{8})", href)
        if not m:
            continue
        ymd = m.group(1)
        try:
            d = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))
        except ValueError:
            continue
        if d in seen or d.year != year:
            continue
        seen.add(d)
        out.append(d)
    return sorted(out)


def parse_session(session_date: date, legislatura: int, cam: int = 2) -> Stenograma | None:
    """Fetch + parse stenograma pentru o zi: cuprinsul dă `ids`, transcrierea dă intervențiile."""
    ymd = session_date.strftime("%Y%m%d")
    url = DETAIL_URL.format(cam=cam, ymd=ymd)
    try:
        r = get(url)
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"  steno {session_date}: {e}")
        return None

    sel = Selector(text=r.text)
    titlu = (sel.css("div.boxTitle h1::text").get() or "").strip() or None
    index_text = re.sub(r"\s+", " ", " ".join(sel.css("#olddiv ::text").getall())).strip()

    interventions: list[StenogramaIntervention] = []
    transcript_url = None
    text_len = len(index_text)
    ids = transcript_ids(r.text)
    if ids:
        transcript_url = TRANSCRIPT_URL.format(ids=ids)
        try:
            rt = get(transcript_url)
            rt.raise_for_status()
            text = html_to_text(rt.text)
            interventions = parse_interventions(text)
            text_len = len(text)
        except Exception as e:
            logger.warning(f"  transcriere {session_date}: {e}")

    if not index_text and not interventions:
        return None

    return Stenograma(
        id=_steno_id(cam, session_date),
        session_date=session_date,
        cam=cam,
        legislatura=legislatura,
        titlu=titlu[:500] if titlu else None,
        interventions=interventions,
        text_complet_len=text_len,
        source_url=url,
        transcript_url=transcript_url,
    )


def scrape_year(
    year: int,
    legislatura: int,
    cam: int = 2,
    skip_dates: set[date] | None = None,
) -> list[Stenograma]:
    """Scrape toate stenogramele unui an."""
    skip = skip_dates or set()
    all_dates = list_session_dates_for_year(year, cam=cam)
    new_dates = [d for d in all_dates if d not in skip]
    skipped = len(all_dates) - len(new_dates)
    logger.info(
        f"year={year} cam={cam}: {len(all_dates)} sesiuni total, "
        f"{skipped} skip, {len(new_dates)} de procesat"
    )

    results: list[Stenograma] = []
    for i, d in enumerate(new_dates, 1):
        try:
            st = parse_session(d, legislatura=legislatura, cam=cam)
            if st:
                results.append(st)
                if i % 10 == 0:
                    logger.info(f"  [{i}/{len(new_dates)}] processed")
        except Exception as e:
            logger.warning(f"  {d}: {e}")

    logger.info(f"year={year}: {len(results)} parsed successfully")
    return results
