"""Build endpoint /declaratii-avere — parsare PDF-uri pentru toți deputații.

Pentru fiecare deputat, descarcă TOATE PDF-urile de avere (în ordinea datei) și
extrage cu pdfplumber valorile standardizate ANI. Salvează:

- ``data/v1/declaratii-avere/legislatura-{leg}.json``        — sumar/index
- ``data/v1/declaratii-avere/legislatura-{leg}/{idm}.json``  — detalii per deputat

Utilizare:
    python scripts/build_declaratii_avere.py                   # legislatura 2024
    python scripts/build_declaratii_avere.py --leg 2020
    python scripts/build_declaratii_avere.py --limit 10        # test rapid
    python scripts/build_declaratii_avere.py --no-cache        # re-download PDF-uri

NOTE:
- Folosește scrapers/declaratii.py ca sursă a listei (cdep_idm + URL-uri PDF)
- PDF-urile sunt cache-uite în data/analize/_pdfs/ ca să nu fie re-descărcate
- Procesare incrementală: dacă fișierul deputat-{idm}.json există + mtime PDF nu s-a
  schimbat, sare peste (poate fi forțat cu --no-cache).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("EROARE: pdfplumber nu e instalat. Rulează: pip install pdfplumber")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas.avere import AvereDeclaratie, AvereDeputat, AvereSummary  # noqa: E402
from schemas.common import Meta  # noqa: E402
from scrapers._http import get as http_get  # noqa: E402

SCRAPER_VERSION = "0.1.0"
ALL_LEGS = [2024, 2020, 2016]
PDF_CACHE = ROOT / "data" / "analize" / "_pdfs"

# Regex pentru sume — strict, prinde DOAR ultima secvență contiguă înainte de valută
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

# Curs RON aproximativ (mai 2026)
RATES_TO_RON = {
    "RON": 1.0,
    "LEI": 1.0,
    "EUR": 5.05,
    "EURO": 5.05,
    "USD": 4.50,
    "DOLARI": 4.50,
    "GBP": 5.80,
    "CHF": 5.40,
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


def _strip_diacritics(s: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


def _voter_canonical_id(name: str) -> str:
    norm = " ".join(_strip_diacritics(name).lower().split())
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def _avere_id(leg: int, idm: int) -> str:
    return hashlib.sha256(f"{leg}|{idm}|avere".encode()).hexdigest()[:16]


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
    rate = RATES_TO_RON.get(currency.upper(), 1.0)
    return amount * rate


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


def parse_pdf(pdf_path: Path) -> dict:
    """Parsează un PDF de declarație ANI, returnează dict cu categoriile."""
    result = {
        "terenuri_count": 0,
        "cladiri_count": 0,
        "suprafata_total_mp": 0.0,
        "conturi_total_ron": 0.0,
        "venituri_anuale_ron": 0.0,
        "datorii_total_ron": 0.0,
        "auto_count": 0,
        "text_extracted": False,
        "error": None,
    }
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

    # I. Imobile
    sec_imobile = extract_section(full_text, "I. Bunuri imobile", MARKERS)
    sec_terenuri = extract_section(sec_imobile, "1. Terenuri", ["2. Clădiri", "II. Bunuri mobile"])
    sec_cladiri = extract_section(sec_imobile, "2. Clădiri", ["II. Bunuri mobile"])
    for sec_text, count_key in [
        (sec_terenuri, "terenuri_count"),
        (sec_cladiri, "cladiri_count"),
    ]:
        matches = list(RE_MP.finditer(sec_text))
        result[count_key] = len(matches)
        for m in matches:
            mp = _parse_amount(m.group(1))
            if mp and mp > 5:
                result["suprafata_total_mp"] += mp

    # IV. Active financiare — table columns may be "CURRENCY YEAR BALANCE" (reversed order)
    sec_conturi = extract_section(full_text, "IV. Active financiare", MARKERS)
    for m in RE_AMOUNT.finditer(sec_conturi):
        num = _parse_amount(m.group(1))
        if num and num > 100:
            result["conturi_total_ron"] += normalize_to_ron(num, m.group(2))
    for m in RE_AMOUNT_REV.finditer(sec_conturi):
        num = _parse_amount(m.group(2))
        if num and num > 100:
            result["conturi_total_ron"] += normalize_to_ron(num, m.group(1))

    # V. Datorii — same dual-direction scan
    sec_datorii = extract_section(full_text, "V. Datorii", MARKERS)
    for m in RE_AMOUNT.finditer(sec_datorii):
        num = _parse_amount(m.group(1))
        if num and num > 100:
            result["datorii_total_ron"] += normalize_to_ron(num, m.group(2))
    for m in RE_AMOUNT_REV.finditer(sec_datorii):
        num = _parse_amount(m.group(2))
        if num and num > 100:
            result["datorii_total_ron"] += normalize_to_ron(num, m.group(1))

    # VII. Venituri
    sec_venituri = extract_section(full_text, "VII. Venituri", MARKERS)
    if not sec_venituri:
        sec_venituri = extract_section(full_text, "Venituri ale declarantului", MARKERS)
    for m in RE_AMOUNT.finditer(sec_venituri):
        num = _parse_amount(m.group(1))
        if num and num > 100:
            result["venituri_anuale_ron"] += normalize_to_ron(num, m.group(2))

    # II. Auto — anchor to line-start to exclude section header words
    # ("1. Autovehicule/autoturisme, tractoare, şalupe, iahturi..." inflates count otherwise)
    sec_mobile = extract_section(full_text, "II. Bunuri mobile", MARKERS)
    result["auto_count"] = len(
        re.findall(
            r"^(autoturism|autovehicul|motociclet|tractor|remorc|iaht|şalup|salup|alt mijloc)\w*",
            sec_mobile,
            re.IGNORECASE | re.MULTILINE,
        )
    )

    return result


def download_pdf(url: str, dest: Path, force: bool = False) -> bool:
    if dest.exists() and not force:
        return True
    try:
        r = http_get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        logging.warning(f"  download failed {url}: {e}")
        return False


def process_deputat(d: dict, leg: int, force: bool = False) -> AvereDeputat | None:
    """Procesează toate PDF-urile de avere ale unui deputat."""
    avere_pdfs = d.get("avere") or []
    if not avere_pdfs:
        return None

    # Sortăm cronologic (cele mai vechi întâi) ca să putem calcula evoluția
    avere_pdfs_sorted = sorted(avere_pdfs, key=lambda x: x.get("data") or "")

    declaratii = []
    for fis in avere_pdfs_sorted:
        url = fis["url"]
        data_dep = fis.get("data")
        try:
            data_obj = date.fromisoformat(data_dep) if data_dep else None
        except ValueError:
            data_obj = None

        # Cache local: nume = hash URL
        pdf_name = hashlib.sha1(url.encode()).hexdigest()[:12] + ".pdf"
        pdf_path = PDF_CACHE / pdf_name

        if not download_pdf(url, pdf_path, force=force):
            declaratii.append(
                AvereDeclaratie(
                    data_depunere=data_obj,
                    pdf_url=url,
                    text_extracted=False,
                    error="download failed",
                )
            )
            continue

        parsed = parse_pdf(pdf_path)
        declaratii.append(
            AvereDeclaratie(
                data_depunere=data_obj,
                pdf_url=url,
                **parsed,
            )
        )

    if not declaratii:
        return None

    # Snapshot final + delta
    ultima = declaratii[-1] if declaratii else None
    prima = declaratii[0] if declaratii else None

    return AvereDeputat(
        id=_avere_id(leg, d["cdep_idm"]),
        cdep_idm=d["cdep_idm"],
        deputat_nume=d["deputat_nume"],
        deputat_canonical_id=d.get("deputat_canonical_id")
        or _voter_canonical_id(d["deputat_nume"]),
        legislatura=leg,
        partid_short=d.get("partid_short"),
        declaratii=declaratii,
        ultima_data=ultima.data_depunere if ultima else None,
        ultima_conturi_ron=ultima.conturi_total_ron if ultima else 0.0,
        ultima_venituri_ron=ultima.venituri_anuale_ron if ultima else 0.0,
        ultima_imobile_count=(ultima.terenuri_count + ultima.cladiri_count) if ultima else 0,
        delta_conturi_ron=(ultima.conturi_total_ron - prima.conturi_total_ron)
        if ultima and prima
        else 0.0,
        delta_imobile=(
            (ultima.terenuri_count + ultima.cladiri_count)
            - (prima.terenuri_count + prima.cladiri_count)
        )
        if ultima and prima
        else 0,
    )


def run_leg(leg: int, args: argparse.Namespace) -> int:
    decl_file = ROOT / "data" / "v1" / "declaratii" / f"legislatura-{leg}.json"
    if not decl_file.exists():
        print(f"Lipsește {decl_file}")
        return 1

    PDF_CACHE.mkdir(parents=True, exist_ok=True)
    out_dir = ROOT / "data" / "v1" / "declaratii-avere" / f"legislatura-{leg}"
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = ROOT / "data" / "v1" / "declaratii-avere" / f"legislatura-{leg}.json"

    declaratii = json.loads(decl_file.read_text(encoding="utf-8"))["data"]
    if args.limit:
        declaratii = declaratii[: args.limit]
    print(f"Procesez {len(declaratii)} deputați pentru legislatura {leg}...")

    summaries: list[dict] = []
    stats = {"ok": 0, "err": 0, "skip": 0}
    for i, d in enumerate(declaratii, 1):
        try:
            av = process_deputat(d, leg, force=args.no_cache)
        except Exception as e:
            logging.warning(f"  {d['deputat_nume']}: {e}")
            stats["err"] += 1
            continue
        if not av:
            stats["skip"] += 1
            continue

        # Salvăm detaliile per deputat
        detail_path = out_dir / f"{av.cdep_idm}.json"
        payload = {
            "meta": Meta(
                generated_at=datetime.now(UTC),
                source_url=f"https://www.cdep.ro/ords/pls/dic/declaratii2015.deputati?tip=ai&leg={leg}",
                scraper_version=SCRAPER_VERSION,
                count=len(av.declaratii),
            ).model_dump(mode="json"),
            "data": av.model_dump(mode="json", exclude_none=False),
        }
        detail_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        # Adăugăm la sumar
        summaries.append(
            AvereSummary(
                id=av.id,
                cdep_idm=av.cdep_idm,
                deputat_nume=av.deputat_nume,
                legislatura=av.legislatura,
                partid_short=av.partid_short,
                n_declaratii=len(av.declaratii),
                ultima_data=av.ultima_data,
                ultima_conturi_ron=av.ultima_conturi_ron,
                ultima_venituri_ron=av.ultima_venituri_ron,
                ultima_imobile_count=av.ultima_imobile_count,
                delta_conturi_ron=av.delta_conturi_ron,
                delta_imobile=av.delta_imobile,
                detail_url=f"declaratii-avere/legislatura-{leg}/{av.cdep_idm}.json",
            ).model_dump(mode="json", exclude_none=False)
        )

        stats["ok"] += 1
        if i % 25 == 0:
            print(f"  [{i}/{len(declaratii)}] {d['deputat_nume']}")
        # Pauză mică
        if i % 10 == 0:
            time.sleep(1)

    # Sortează sumar după partid + nume
    summaries.sort(key=lambda x: (x.get("partid_short") or "ZZZ", x["deputat_nume"]))

    index_payload = {
        "meta": Meta(
            generated_at=datetime.now(UTC),
            source_url=f"https://endimion2k.github.io/cdep-api-poc/data/v1/declaratii/legislatura-{leg}.json",
            scraper_version=SCRAPER_VERSION,
            count=len(summaries),
        ).model_dump(mode="json"),
        "data": summaries,
    }
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"OK: {stats['ok']} deputați procesați.")
    print(f"   Skip (fără PDF avere): {stats['skip']}")
    print(f"   Erori: {stats['err']}")
    print(f"   Index: {index_path}")
    print(f"   Detalii: {out_dir}/")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leg", type=int, default=2024)
    parser.add_argument("--all", action="store_true", help="Build 2024 + 2020 + 2016")
    parser.add_argument("--limit", type=int, default=None, help="Limită deputați (test)")
    parser.add_argument("--no-cache", action="store_true", help="Forțează re-download PDF-uri")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    legs = ALL_LEGS if args.all else [args.leg]
    for leg in legs:
        ret = run_leg(leg, args)
        if ret != 0 and not args.all:
            return ret
    return 0


if __name__ == "__main__":
    sys.exit(main())
