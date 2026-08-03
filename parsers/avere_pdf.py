"""PDF parser pentru declarații de avere ANI.

Funcția principală: parse_pdf(pdf_path) -> dict
Returnează un dict cu toate câmpurile AvereDeclaratie (fără data_depunere/pdf_url).
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore[assignment]

RE_AMOUNT = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"\s*(RON|EUR|EURO|USD|GBP|CHF|lei|euro|dolari)\b",
    re.IGNORECASE,
)
RE_MP = re.compile(r"(\d+(?:[.,]\d+)?)\s*m\s*²?", re.IGNORECASE)
# Some PDFs lay out tables as "CURRENCY YEAR BALANCE" (currency before amount).
RE_AMOUNT_REV = re.compile(
    r"\b(RON|EUR|EURO|USD|GBP|CHF|lei|euro|dolari)\b\s+\d{4}\s+(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

RATES_TO_RON: dict[str, float] = {
    "RON": 1.0, "LEI": 1.0,
    "EUR": 5.05, "EURO": 5.05,
    "USD": 4.50, "DOLARI": 4.50,
    "GBP": 5.80, "CHF": 5.40,
}

MARKERS = [
    "I. Bunuri imobile",
    "II. Bunuri mobile",
    "III. Bunuri mobile",
    "IV. Active financiare",
    "V. Datorii",
    "VI. Cadouri",
    "VII. Venituri",
]

AUTO_RE = re.compile(
    r"^(autoturism|autovehicul|motociclet|tractor|remorc|iaht|şalup|salup|alt mijloc)\w*",
    re.IGNORECASE | re.MULTILINE,
)


def _parse_amount(num_str: str) -> float | None:
    s = num_str.replace(" ", "")
    if "." in s and "," in s:
        s = (
            s.replace(".", "").replace(",", ".")
            if s.rindex(",") > s.rindex(".")
            else s.replace(",", "")
        )
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",", ".") if len(parts[-1]) <= 2 else s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if len(parts[-1]) == 3 and len(parts) >= 2:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def normalize_to_ron(amount: float, currency: str) -> float:
    return amount * RATES_TO_RON.get(currency.upper(), 1.0)


def extract_section(text: str, marker: str, next_markers: list[str]) -> str:
    start = text.find(marker)
    if start < 0:
        return ""
    end = len(text)
    for nm in next_markers:
        idx = text.find(nm, start + len(marker))
        if 0 < idx < end:
            end = idx
    return text[start:end]


def _scan_amounts(text: str, threshold: float = 100.0) -> float:
    """Sum all amount+currency matches (both directions) in text."""
    total = 0.0
    for m in RE_AMOUNT.finditer(text):
        num = _parse_amount(m.group(1))
        if num and num > threshold:
            total += normalize_to_ron(num, m.group(2))
    for m in RE_AMOUNT_REV.finditer(text):
        num = _parse_amount(m.group(2))
        if num and num > threshold:
            total += normalize_to_ron(num, m.group(1))
    return total


def _detect_imobil_categorie(block: str, tip: str) -> str:
    """Detect category from a property block string."""
    b = block.lower()
    if "luciu de ap" in b:
        return "luciu_apa"
    if "extravilan" in b:
        return "extravilan"
    if "forestier" in b:
        return "forestier"
    if "agricol" in b:
        return "agricol"
    if "intravilan" in b:
        return "intravilan"
    if tip == "cladire":
        if "comerciale" in b or "producti" in b:
            return "comercial"
        if "vacan" in b:
            return "vacanta"
        if "locuit" in b or ("cas" in b and "locuit" in b):
            return "locuinta"
        if "apartament" in b:
            return "apartament"
        if "bunuri imobile" in b:
            return "alte_cladiri"
    return "necunoscuta"


def _detect_mod_dobandire(block: str) -> str | None:
    b = block.lower()
    if "mostenire" in b or "moștenire" in b:
        return "mostenire"
    if "donati" in b or "donație" in b:
        return "donatie"
    if "vânzare" in b or "vanzare" in b:
        return "cumparare"
    if "altele" in b:
        return "altele"
    return None


def _parse_imobile_details(
    sec_terenuri: str, sec_cladiri: str
) -> tuple[list[dict], dict[str, float]]:
    """Parse per-row imobile details. Returns (rows_as_dicts, suprafata_by_category)."""
    from schemas.avere import AvereImobil

    CAT_TO_FIELD = {
        "agricol": "suprafata_agricol_mp",
        "forestier": "suprafata_forestier_mp",
        "intravilan": "suprafata_intravilan_mp",
        "luciu_apa": "suprafata_luciu_mp",
        "extravilan": "suprafata_alte_mp",
    }
    aggregates: dict[str, float] = {
        "suprafata_agricol_mp": 0.0,
        "suprafata_forestier_mp": 0.0,
        "suprafata_intravilan_mp": 0.0,
        "suprafata_luciu_mp": 0.0,
        "suprafata_alte_mp": 0.0,
        "suprafata_cladiri_mp": 0.0,
    }
    rows: list[dict] = []

    for tip, section in [("teren", sec_terenuri), ("cladire", sec_cladiri)]:
        if not section:
            continue
        # Split into blocks: each property entry starts with "Tara:"
        blocks = re.split(r"(?im)^Tara\s*:", section)
        for block in blocks[1:]:  # skip header
            m_mp = RE_MP.search(block)
            if not m_mp:
                continue
            suprafata = _parse_amount(m_mp.group(1))
            if not suprafata or suprafata <= 5:
                continue

            # Judet
            m_j = re.search(r"Judet\s*:\s*([^\n]+)", block, re.IGNORECASE)
            judet = m_j.group(1).strip().split()[0] if m_j else None

            # Year — look on the line containing m²
            line_s = block.rfind("\n", 0, m_mp.start()) + 1
            line_e = block.find("\n", m_mp.end())
            mp_line = block[line_s: len(block) if line_e < 0 else line_e]
            years = re.findall(r"\b(19\d{2}|20[0-3]\d)\b", mp_line)
            an = int(years[0]) if years else None

            # Cota-parte
            m_cota = re.search(r"\b(\d+/\d+)\b", mp_line)
            cota = m_cota.group(1) if m_cota else None

            categorie = _detect_imobil_categorie(block, tip)
            mod = _detect_mod_dobandire(block)

            rows.append(
                AvereImobil(
                    tip=tip,
                    categorie=categorie,
                    suprafata_mp=suprafata,
                    judet=judet,
                    an_dobandirii=an,
                    cota_parte=cota,
                    modul_dobandirii=mod,
                ).model_dump()
            )

            # Aggregate
            if tip == "cladire":
                aggregates["suprafata_cladiri_mp"] += suprafata
            else:
                field = CAT_TO_FIELD.get(categorie, "suprafata_alte_mp")
                aggregates[field] += suprafata

    return rows, aggregates


def _parse_vehicule(sec_mobile: str) -> list[dict]:
    """Parse per-row vehicle details from section II.1."""
    from schemas.avere import VehiculDetail

    rows: list[dict] = []
    lines = sec_mobile.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = AUTO_RE.match(line)
        if not m:
            i += 1
            continue
        natura = m.group(1).strip()
        # Try to find year on current line or next 3 lines
        search_text = "\n".join(lines[i: i + 4])
        years = re.findall(r"\b(19\d{2}|20[0-3]\d)\b", search_text)
        an = int(years[0]) if years else None
        # Marca: text on current line after natura, before first digit sequence
        rest = line[m.end():].strip()
        marca_m = re.match(r"([A-Za-zÀ-ž\s\-\.]+?)(?:\s+\d)", rest)
        marca = marca_m.group(1).strip() or None if marca_m else (rest.split()[0] if rest.split() else None)
        # Mod dobandire
        mod_text = search_text.lower()
        if "vânzare" in mod_text or "vanzare" in mod_text:
            mod = "cumparare"
        elif "mostenire" in mod_text or "moștenire" in mod_text:
            mod = "mostenire"
        elif "donati" in mod_text:
            mod = "donatie"
        else:
            mod = None
        rows.append(
            VehiculDetail(
                natura=natura, marca=marca, an_fabricatie=an, mod_dobandire=mod
            ).model_dump()
        )
        i += 1
    return rows


def _parse_conturi_detaliate(sec_conturi1: str) -> list[dict]:
    """Parse per-row account details from section IV.1 only (not IV.2)."""
    from schemas.avere import ContDetail

    rows: list[dict] = []
    # RE_AMOUNT_REV: groups are (currency, amount)
    for m in RE_AMOUNT_REV.finditer(sec_conturi1):
        num = _parse_amount(m.group(2))
        if not num or num <= 0:
            continue
        currency = m.group(1).upper()
        sold_ron = normalize_to_ron(num, currency)

        # Year from the match context (pattern: CURRENCY YYYY AMOUNT)
        year_m = re.search(
            r"\b(RON|EUR|EURO|USD|GBP|CHF|lei|euro|dolari)\b\s+(\d{4})\s+",
            sec_conturi1[max(0, m.start() - 5): m.end()],
            re.IGNORECASE,
        )
        an_deschis = int(year_m.group(2)) if year_m else None

        # Institution: last line ending with comma before this match
        context_before = sec_conturi1[max(0, m.start() - 300): m.start()]
        inst = None
        for line in reversed(context_before.splitlines()):
            line = line.strip()
            if line.endswith(",") and len(line) > 3 and not any(
                kw in line.lower() for kw in ["cont", "depozit", "fond", "echival", "inclusiv"]
            ):
                inst = line.rstrip(",").strip()
                break

        # Account type
        tip_context = sec_conturi1[max(0, m.start() - 200): m.start()].lower()
        if "fond" in tip_context or "pensii" in tip_context:
            tip = "fond_investitii"
        elif "depozit" in tip_context:
            tip = "depozit"
        else:
            tip = "cont_curent"

        rows.append(
            ContDetail(
                institutie=inst, tip=tip, valuta=currency,
                an_deschis=an_deschis, sold_ron=sold_ron,
            ).model_dump()
        )

    # Also catch forward-order amounts (amount RON) — rare in IV.1 but possible
    seen_positions: set[int] = {m.start() for m in RE_AMOUNT_REV.finditer(sec_conturi1)}
    for m in RE_AMOUNT.finditer(sec_conturi1):
        if m.start() in seen_positions:
            continue
        num = _parse_amount(m.group(1))
        if not num or num <= 100:
            continue
        currency = m.group(2).upper()
        rows.append(
            ContDetail(
                institutie=None, tip=None, valuta=currency,
                an_deschis=None,
                sold_ron=normalize_to_ron(num, currency),
            ).model_dump()
        )

    return rows


def _parse_plasamente(sec_plasamente: str) -> list[dict]:
    """Parse per-row investment/stake/loan details from section IV.2."""
    from schemas.avere import PlasamentDetail

    rows: list[dict] = []
    if not sec_plasamente or "- - -" in sec_plasamente:
        return rows

    for m in RE_AMOUNT.finditer(sec_plasamente):
        num = _parse_amount(m.group(1))
        if not num or num <= 100:
            continue
        currency = m.group(2).upper()
        valoare_ron = normalize_to_ron(num, currency)

        # The value line: emitent + nr_titluri + amount + currency all on one line
        line_s = sec_plasamente.rfind("\n", 0, m.start()) + 1
        line_e = sec_plasamente.find("\n", m.end())
        val_line = sec_plasamente[line_s: len(sec_plasamente) if line_e < 0 else line_e]

        # Remove the amount+currency suffix, rest is emitent + nr_titluri
        prefix = val_line[: val_line.rfind(m.group(0))].strip()
        # Nr titluri: "100 %" or "1/3" or similar at end of prefix
        nr_m = re.search(r"(\d+\s*%|\d+\s*/\s*\d+|\d+\s+parti?|\d+\s+titluri?|\d+\s+actiuni?)\s*$", prefix, re.IGNORECASE)
        nr_titluri = nr_m.group(1).strip() if nr_m else None
        emitent = prefix[: nr_m.start()].strip() if nr_m else prefix.strip()
        emitent = emitent or None

        # Tip from nearby context (lines before/after)
        context = sec_plasamente[max(0, m.start() - 200): m.end() + 50].lower()
        if "imprumut" in context or "împrumut" in context:
            tip = "imprumut"
        elif "acti" in context and "parti" not in context:
            tip = "actiuni"
        elif "parti social" in context or "parți social" in context:
            tip = "parti_sociale"
        elif "titluri" in context or "obligati" in context or "certificate" in context:
            tip = "titluri_stat"
        else:
            tip = None

        rows.append(
            PlasamentDetail(
                emitent=emitent, tip=tip, nr_titluri=nr_titluri, valoare_ron=valoare_ron,
            ).model_dump()
        )

    return rows


def parse_pdf(pdf_path: Path) -> dict:
    """Parse an ANI wealth declaration PDF. Returns a dict matching AvereDeclaratie fields."""
    result: dict = {
        "terenuri_count": 0,
        "cladiri_count": 0,
        "suprafata_total_mp": 0.0,
        "suprafata_agricol_mp": 0.0,
        "suprafata_forestier_mp": 0.0,
        "suprafata_intravilan_mp": 0.0,
        "suprafata_luciu_mp": 0.0,
        "suprafata_alte_mp": 0.0,
        "suprafata_cladiri_mp": 0.0,
        "conturi_total_ron": 0.0,
        "plasamente_total_ron": 0.0,
        "venituri_anuale_ron": 0.0,
        "datorii_total_ron": 0.0,
        "bijuterii_total_ron": 0.0,
        "bunuri_instrainate_count": 0,
        "bunuri_instrainate_total_ron": 0.0,
        "cadouri_total_ron": 0.0,
        "auto_count": 0,
        "imobile_detaliate": [],
        "vehicule": [],
        "conturi_detaliate": [],
        "plasamente_detaliate": [],
        "text_extracted": False,
        "error": None,
        "total_active_monetare_ron": 0.0,
        "avere_neta_ron": 0.0,
        "nr_judete": 0,
        "nr_companii": 0,
        "terenuri_forestiere_count": 0,
        "terenuri_agricole_count": 0,
        "an_prima_proprietate": None,
    }

    if pdfplumber is None:
        result["error"] = "pdfplumber not installed"
        return result

    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        result["error"] = f"PDF read failed: {e}"
        return result

    if len(full_text.strip()) < 100:
        result["error"] = "PDF scanat (text < 100 chars)"
        return result

    result["text_extracted"] = True

    # ── I. Bunuri imobile ─────────────────────────────────────────────────────
    sec_imobile = extract_section(full_text, "I. Bunuri imobile", MARKERS)
    sec_terenuri = extract_section(sec_imobile, "1. Terenuri", ["2. Clădiri", "II. Bunuri mobile"])
    sec_cladiri = extract_section(sec_imobile, "2. Clădiri", ["II. Bunuri mobile"])

    teren_matches = list(RE_MP.finditer(sec_terenuri))
    cladire_matches = list(RE_MP.finditer(sec_cladiri))
    result["terenuri_count"] = len(teren_matches)
    result["cladiri_count"] = len(cladire_matches)
    for m in teren_matches + cladire_matches:
        mp = _parse_amount(m.group(1))
        if mp and mp > 5:
            result["suprafata_total_mp"] += mp

    imobile_rows, suprafata_cats = _parse_imobile_details(sec_terenuri, sec_cladiri)
    result["imobile_detaliate"] = imobile_rows
    result.update(suprafata_cats)

    # ── II. Bunuri mobile ─────────────────────────────────────────────────────
    sec_mobile = extract_section(full_text, "II. Bunuri mobile", MARKERS)

    result["auto_count"] = len(AUTO_RE.findall(sec_mobile))
    result["vehicule"] = _parse_vehicule(sec_mobile)

    # II.2 Bijuterii / metale prețioase / artă
    sec_bij = extract_section(sec_mobile, "2. Bunuri sub", ["III. Bunuri", "IV. Active"])
    result["bijuterii_total_ron"] = _scan_amounts(sec_bij)

    # ── III. Bunuri înstrăinate ───────────────────────────────────────────────
    sec_instr = extract_section(full_text, "III. Bunuri mobile", MARKERS)
    if sec_instr and "- - -" not in sec_instr:
        dates = re.findall(r"\b\d{1,2}[./]\d{1,2}[./]\d{4}\b", sec_instr)
        result["bunuri_instrainate_count"] = len(dates)
        result["bunuri_instrainate_total_ron"] = _scan_amounts(sec_instr)

    # ── IV. Active financiare — split IV.1 conturi from IV.2 plasamente ───────
    sec_iv = extract_section(full_text, "IV. Active financiare", MARKERS)
    sec_conturi1 = extract_section(sec_iv, "1. Conturi", ["2. Plasamente", "3. Alte active"])
    sec_plasamente = extract_section(sec_iv, "2. Plasamente", ["3. Alte active", "V. Datorii"])

    conturi_rows = _parse_conturi_detaliate(sec_conturi1)
    result["conturi_detaliate"] = conturi_rows
    result["conturi_total_ron"] = sum(c["sold_ron"] for c in conturi_rows)

    plasamente_rows = _parse_plasamente(sec_plasamente)
    result["plasamente_detaliate"] = plasamente_rows
    result["plasamente_total_ron"] = sum(p["valoare_ron"] for p in plasamente_rows)

    # ── V. Datorii ────────────────────────────────────────────────────────────
    sec_datorii = extract_section(full_text, "V. Datorii", MARKERS)
    result["datorii_total_ron"] = _scan_amounts(sec_datorii)

    # ── VI. Cadouri ───────────────────────────────────────────────────────────
    sec_cadouri = extract_section(full_text, "VI. Cadouri", MARKERS)
    result["cadouri_total_ron"] = _scan_amounts(sec_cadouri)

    # ── VII. Venituri ─────────────────────────────────────────────────────────
    sec_venituri = extract_section(full_text, "VII. Venituri", MARKERS)
    if not sec_venituri:
        sec_venituri = extract_section(full_text, "Venituri ale declarantului", MARKERS)
    for m in RE_AMOUNT.finditer(sec_venituri):
        num = _parse_amount(m.group(1))
        if num and num > 100:
            result["venituri_anuale_ron"] += normalize_to_ron(num, m.group(2))

    # ── Derived aggregates ────────────────────────────────────────────────────
    result["total_active_monetare_ron"] = (
        result["conturi_total_ron"]
        + result["plasamente_total_ron"]
        + result["bijuterii_total_ron"]
    )
    result["avere_neta_ron"] = (
        result["total_active_monetare_ron"] - result["datorii_total_ron"]
    )
    result["nr_judete"] = len(
        {r["judet"] for r in result["imobile_detaliate"] if r.get("judet")}
    )
    result["nr_companii"] = len(result["plasamente_detaliate"])
    result["terenuri_forestiere_count"] = sum(
        1 for r in result["imobile_detaliate"] if r.get("categorie") == "forestier"
    )
    result["terenuri_agricole_count"] = sum(
        1 for r in result["imobile_detaliate"] if r.get("categorie") == "agricol"
    )
    _ani = [r["an_dobandirii"] for r in result["imobile_detaliate"] if r.get("an_dobandirii")]
    result["an_prima_proprietate"] = min(_ani) if _ani else None

    return result
