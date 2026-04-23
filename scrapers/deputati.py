"""Scraper pentru lista de deputați + profilele individuale.

Strategia:
1. Iterez `structura2015.ab?par=A..Z&cam=2&leg=YYYY` pentru enumerare exhaustivă.
2. Pentru fiecare rând din tabelul principal, filtrez cele cu leg/cam corespunzătoare.
3. Fetch pagina de profil `structura2015.mp?idm=X&cam=2&leg=YYYY` și extrag datele.
4. Produc o listă de `Deputat`.

Rate: 1 req/sec (din `_http.py`). Pentru 2024 (~330 deputați + 26 litere) ≈ 6 minute.
"""

from __future__ import annotations

import hashlib
import logging
import re
import string
import unicodedata
from datetime import date
from typing import Optional
from urllib.parse import urljoin

from parsel import Selector

from scrapers._http import get
from schemas.common import Gender
from schemas.deputat import ComisieMembership, Deputat

logger = logging.getLogger(__name__)

BASE = "https://www.cdep.ro"
LIST_URL = BASE + "/pls/parlam/structura2015.ab?cam={cam}&leg={leg}&idl=1&par={par}"
PROFILE_URL = BASE + "/pls/parlam/structura2015.mp?idm={idm}&cam={cam}&leg={leg}"

# --- Parsing helpers ---

# "n. 15 aug. 1970"  →  (15, aug, 1970)
RE_BIRTH = re.compile(r"n\.\s*(\d{1,2})\s+([a-zăâîşţșț\.]+)\s+(\d{4})", re.IGNORECASE)

# "circumscripţia electorala nr.35 SUCEAVA"
RE_CIRC = re.compile(
    r"circumscripti(?:a|ia|ţia|ția)\s+electoral(?:a|ă)\s+nr\.\s*(\d+)\s+([A-ZĂÂÎȘŞȚŢ\- ]+?)(?=\s+data|\s+Grup|\s+Forma|$)",
    re.IGNORECASE,
)

# "data validarii: 21 decembrie 2024 - HCD nr.109/2024"
RE_VALIDARE = re.compile(
    r"data\s+validari[iî]\s*:\s*(\d{1,2})\s+([a-zăâîşţșț\.]+)\s+(\d{4})\s*-?\s*(HCD\s+nr\.\s*[\d/]+)?",
    re.IGNORECASE,
)

# "Formaţiunea politică: - Partidul Social Democrat Grupul parlamentar: ..."
RE_PARTY = re.compile(
    r"Forma[ţt]iunea politic[ăa]:\s*-?\s*(.+?)\s+Grup", re.IGNORECASE
)

# "Grupul parlamentar: Grupul parlamentar al Partidului Social Democrat Vicelider - din..."
# Capturez tot până la următoarea secțiune (Comisii / Delegatii / Activitate).
RE_GROUP = re.compile(
    r"Grupul parlamentar:\s*(.+?)(?=\s+Comisii\s+permanente|\s+Comisii\s+speciale|"
    r"\s+Delega[ţt]ii|\s+Grupuri\s+de\s+prietenie|\s+Activitatea\s+parlamentar)",
    re.IGNORECASE,
)
RE_GROUP_ROLE = re.compile(
    r"\s+(Lider|Vicelider|Pre[şs]edinte|Vicepre[şs]edinte|Secretar)"
    r"(?:\s+-\s+din|\s+din|\s*$)",
    re.IGNORECASE,
)

# Activity stats — "Luări de cuvânt: 17 la ... puncte ... (în 14 şedinţe)"
RE_LUARI = re.compile(r"Lu[ăa]ri de cuv[âa]nt:\s*(?:la\s+)?(\d+)\s+puncte.*?\(?\s*[îiî]n\s+(\d+)", re.IGNORECASE)
RE_DECLARATII = re.compile(r"Declara[ţt]ii politice.*?:\s*(\d+)", re.IGNORECASE)
RE_PROPUNERI = re.compile(
    r"Propuneri legislative.*?:\s*(\d+)\s*(?:,\s*din care\s+(\d+)\s+promulgate)?", re.IGNORECASE
)
RE_INTREBARI = re.compile(r"[ÎI]ntreb[ăa]ri [şs]i interpel[ăa]ri:\s*(\d+)", re.IGNORECASE)

# "Biroul parlamentar: Suceava, Str Meseriaşilor nr. 2..."
RE_BIROU = re.compile(r"Biroul\s+parlamentar:\s*(.+?)(?:\s+Camera\s+Deputa|$)", re.IGNORECASE)

ROMANIAN_MONTHS = {
    "ian": 1, "ianuarie": 1,
    "feb": 2, "februarie": 2,
    "mar": 3, "mart": 3, "martie": 3,
    "apr": 4, "aprilie": 4,
    "mai": 5,
    "iun": 6, "iunie": 6,
    "iul": 7, "iulie": 7,
    "aug": 8, "august": 8,
    "sep": 9, "septembrie": 9, "sept": 9,
    "oct": 10, "octombrie": 10,
    "noi": 11, "nov": 11, "noiembrie": 11,
    "dec": 12, "decembrie": 12,
}


def _parse_ro_date(day_str: str, month_str: str, year_str: str) -> Optional[date]:
    m = month_str.rstrip(".").lower()
    m = m.replace("ş", "s").replace("ţ", "t").replace("ș", "s").replace("ț", "t")
    month = ROMANIAN_MONTHS.get(m) or ROMANIAN_MONTHS.get(m[:3])
    if month is None:
        return None
    try:
        return date(int(year_str), month, int(day_str))
    except (ValueError, TypeError):
        return None


def _strip_diacritics(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


def _canonical_id(name: str, birth_date: Optional[date]) -> str:
    """Stable hash-based ID across legislatures."""
    norm = " ".join(_strip_diacritics(name).lower().split())
    key = norm
    if birth_date:
        key += "|" + birth_date.isoformat()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _clean_text(sel: Selector) -> str:
    """Concatenate all body text, collapse whitespace."""
    all_text = " ".join(sel.css("body *::text").getall())
    return re.sub(r"\s+", " ", all_text).strip()


# --- Listing ---


def list_current_deputies(leg: int = 2024, cam: int = 2) -> list[dict]:
    """Enumerate all deputies for (leg, cam) by iterating A-Z letter pages."""
    found: dict[int, dict] = {}  # idm -> row data
    for letter in string.ascii_uppercase:
        url = LIST_URL.format(cam=cam, leg=leg, par=letter)
        logger.info(f"listing: par={letter} → {url}")
        try:
            r = get(url)
            r.raise_for_status()
        except Exception as e:
            logger.warning(f"skip letter {letter}: {e}")
            continue
        sel = Selector(text=r.text)
        tables = sel.css("table")
        if len(tables) < 2:
            continue
        for row in tables[1].css("tr"):
            cells = row.css("td")
            if len(cells) != 4:
                continue
            name = " ".join(" ".join(cells[1].css("*::text").getall()).split()).strip()
            if not name:
                continue
            for href in cells[3].css("a::attr(href)").getall():
                params = dict(re.findall(r"(\w+)=(\d+)", href))
                if int(params.get("leg", 0)) == leg and int(params.get("cam", 0)) == cam:
                    idm = int(params["idm"])
                    if idm not in found:
                        found[idm] = {
                            "idm": idm,
                            "name": name,
                            "profile_url": urljoin(BASE, href),
                        }
                    break
    return list(found.values())


# --- Profile parsing ---


def parse_profile(idm: int, name_from_list: str, leg: int = 2024, cam: int = 2) -> Deputat:
    """Fetch & parse a single deputy profile page."""
    url = PROFILE_URL.format(idm=idm, cam=cam, leg=leg)
    r = get(url)
    r.raise_for_status()
    sel = Selector(text=r.text)
    text = _clean_text(sel)

    # --- Birth date ---
    birth_date = None
    m = RE_BIRTH.search(text)
    if m:
        birth_date = _parse_ro_date(m.group(1), m.group(2), m.group(3))

    # --- Photo ---
    image_url = None
    for img_src in sel.css("img::attr(src)").getall():
        if "/parlamentari/l" in img_src:
            image_url = urljoin(BASE, img_src)
            break

    # --- Circumscription & county ---
    judet = None
    circumscriptie = None
    m = RE_CIRC.search(text)
    if m:
        circumscriptie = int(m.group(1))
        judet = m.group(2).strip().title()

    # --- Validation date + HCD ---
    data_validare = None
    hcd_validare = None
    m = RE_VALIDARE.search(text)
    if m:
        data_validare = _parse_ro_date(m.group(1), m.group(2), m.group(3))
        if m.group(4):
            hcd_validare = m.group(4).strip()

    # --- Party & group ---
    current_party = None
    m = RE_PARTY.search(text)
    if m:
        current_party = m.group(1).strip(" -")
        # Strip trailing junk after party name
        current_party = re.sub(r"\s+(Vicelider|Lider|Pre[şs]edinte|Secretar|din\s+\w+).*$", "", current_party)

    current_group = None
    group_role = None
    m = RE_GROUP.search(text)
    if m:
        raw = m.group(1).strip()
        # Extract trailing role if present
        role_m = RE_GROUP_ROLE.search(raw)
        if role_m:
            group_role = role_m.group(1).replace("ş", "ș")
            raw = raw[: role_m.start()].strip()
        current_group = raw

    # --- Gender (linguistic) ---
    gender: Optional[Gender] = None
    lower = text.lower()
    # Look for the validation sentence: "ales deputat" / "aleasa deputat"
    if re.search(r"\baleasa\b", lower):
        gender = Gender.FEMALE
    elif re.search(r"\bales\b", lower):
        gender = Gender.MALE

    # --- Activity stats ---
    luari = sedinte = decl_pol = prop_leg = legi_prom = intrebari = None
    m = RE_LUARI.search(text)
    if m:
        luari = int(m.group(1))
        sedinte = int(m.group(2))
    m = RE_DECLARATII.search(text)
    if m:
        decl_pol = int(m.group(1))
    m = RE_PROPUNERI.search(text)
    if m:
        prop_leg = int(m.group(1))
        if m.group(2):
            legi_prom = int(m.group(2))
    m = RE_INTREBARI.search(text)
    if m:
        intrebari = int(m.group(1))

    # --- Office ---
    birou = None
    m = RE_BIROU.search(text)
    if m:
        birou = m.group(1).strip()

    # --- Committees ---
    comisii = _parse_committees(text)

    # --- Delegations & friendship groups ---
    delegatii = _extract_list_section(
        text,
        header=r"Delega[ţt]ii\s+ale\s+Parlamentului\s+Rom[âa]niei[^:]*:",
        stop=r"Grupuri\s+de\s+prietenie|Activitatea\s+parlamentar",
        item_prefix=r"Delega[ţt]ia\s+Parlamentului\s+Rom[âa]niei",
    )
    grupuri_prietenie = _extract_list_section(
        text,
        header=r"Grupuri\s+de\s+prietenie[^:]*:",
        stop=r"Activitatea\s+parlamentar",
        item_prefix=r"Grupul\s+parlamentar\s+de\s+prietenie",
    )

    # --- Name split ---
    parts = name_from_list.split()
    family_name = parts[0] if parts else None
    given_name = " ".join(parts[1:]) if len(parts) > 1 else None

    return Deputat(
        id=_canonical_id(name_from_list, birth_date),
        name=name_from_list,
        given_name=given_name,
        family_name=family_name,
        gender=gender,
        birth_date=birth_date,
        image=image_url,
        cdep_idm=idm,
        legislatura=leg,
        judet=judet,
        circumscriptie=circumscriptie,
        profile_url=url,
        data_validare=data_validare,
        hcd_validare=hcd_validare,
        current_party=current_party,
        current_group=current_group,
        group_role=group_role,
        comisii=comisii,
        delegatii=delegatii,
        grupuri_prietenie=grupuri_prietenie,
        activitate_luari_cuvant=luari,
        activitate_sedinte=sedinte,
        activitate_declaratii_politice=decl_pol,
        activitate_propuneri_legislative=prop_leg,
        activitate_legi_promulgate=legi_prom,
        activitate_intrebari_interpelari=intrebari,
        birou_parlamentar=birou,
    )


def _parse_committees(text: str) -> list[ComisieMembership]:
    """Best-effort extraction of committee memberships.

    Strategia: găsim segmentele "Comisii permanente ... Comisii speciale ... Delegatii"
    și split-uim după separatori tipici.
    """
    result: list[ComisieMembership] = []

    sections = [
        ("permanenta", r"Comisii permanente", r"(?:Comisii speciale|Delegatii|Grupuri de prietenie|Activitatea)"),
        ("speciala", r"Comisii speciale(?! comune)", r"(?:Comisii speciale comune|Delegatii|Grupuri de prietenie|Activitatea)"),
        ("speciala_comuna", r"Comisii speciale comune", r"(?:Delegatii|Grupuri de prietenie|Activitatea)"),
    ]

    for tip, header, stop in sections:
        m = re.search(header + r"(.*?)" + stop, text, re.IGNORECASE)
        if not m:
            continue
        body = m.group(1).strip()
        # Split on "Comisia " or "Comisii " to get individual entries
        # Each committee entry starts with "Comisia" or is separated by " - "
        # Simpler approach: split on the word "Comisia" boundary
        entries = re.findall(
            r"Comisia\s+(?:pentru|specială\s+comună|comună)?\s*[^\n]*?(?=\s+Comisia|\s+(?:Comisii|Delegat|Grupuri|Activit)|$)",
            body,
        )
        for entry in entries:
            entry = entry.strip()
            # Role? "- Secretar", "- Preşedinte", "- Vicepreşedinte", "- Membru"
            role_match = re.search(r"\s*-\s*(Secretar|Pre[şs]edinte|Vicepre[şs]edinte|Membru|Lider)", entry)
            if role_match:
                rol = role_match.group(1).replace("ş", "ș")
                comisia = entry[: role_match.start()].strip()
            else:
                rol = None
                comisia = entry
            if comisia:
                result.append(ComisieMembership(comisia=comisia, tip=tip, rol=rol))
    return result


def _extract_list_section(text: str, header: str, stop: str, item_prefix: str) -> list[str]:
    """Extract a list of items from a section delimited by header…stop.

    Splits the section on occurrences of `item_prefix` to find individual items.
    Trims trailing role words from each item.
    """
    m = re.search(header + r"(.*?)(?=" + stop + r"|$)", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    body = m.group(1).strip()
    # Split on the item prefix (using lookahead to keep the prefix in the item)
    parts = re.split(r"(?=" + item_prefix + r")", body, flags=re.IGNORECASE)
    items = []
    for part in parts:
        part = part.strip()
        if not part or not re.match(item_prefix, part, re.IGNORECASE):
            continue
        # Strip trailing role annotations
        cleaned = re.sub(
            r"\s+(supleant|titular|Vicepre[şs]edinte|Pre[şs]edinte|Secretar|Membru|Vicelider|Lider)\s*$",
            "",
            part,
            flags=re.IGNORECASE,
        ).strip()
        # Collapse whitespace
        cleaned = re.sub(r"\s+", " ", cleaned)
        items.append(cleaned)
    return items


# --- Main scrape ---


def scrape(leg: int = 2024, cam: int = 2, limit: Optional[int] = None) -> list[Deputat]:
    """Scrape all deputies for given legislature & chamber.

    Args:
        leg: legislature year (e.g., 2024).
        cam: chamber (2 = Camera Deputaților).
        limit: optional cap on number of profiles for testing.
    """
    logger.info(f"scrape start: leg={leg} cam={cam}")
    listings = list_current_deputies(leg=leg, cam=cam)
    logger.info(f"found {len(listings)} deputies in listings")
    if limit:
        listings = listings[:limit]

    results = []
    for i, row in enumerate(listings, 1):
        try:
            dep = parse_profile(row["idm"], row["name"], leg=leg, cam=cam)
            results.append(dep)
            logger.info(f"[{i}/{len(listings)}] {dep.name} (idm={dep.cdep_idm})")
        except Exception as e:
            logger.error(f"[{i}/{len(listings)}] FAILED idm={row['idm']} name={row['name']}: {e}")
    return results
