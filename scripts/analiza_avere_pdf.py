"""Analiză comparativă PDF declarații avere — PSD vs USR.

Descarcă declarațiile de avere (PDF-urile cele mai recente) pentru deputații
PSD + USR, extrage cu pdfplumber valorile standardizate ANI și agregează
totaluri per grup parlamentar.

Cerințe:
    pip install pdfplumber requests

Utilizare:
    python scripts/analiza_avere_pdf.py                      # PSD vs USR (default)
    python scripts/analiza_avere_pdf.py --partide PSD USR PNL AUR  # mai multe partide
    python scripts/analiza_avere_pdf.py --limit 5            # doar primii 5 deputați per partid (test)

Output:
    - data/analize/avere_psd_vs_usr.json (rezultate raw)
    - data/analize/avere_psd_vs_usr.csv (per deputat, pentru Excel)
    - data/analize/_pdfs/<idm>.pdf (cache PDF-uri descărcate)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("EROARE: pdfplumber nu e instalat. Rulează: pip install pdfplumber")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Folosim helper-ul HTTP cu truststore + SSL adapter legacy (configurat
# pentru certificate Windows MITM de antivirus).
from scrapers._http import get as http_get  # noqa: E402

DECL_FILE = ROOT / "data" / "v1" / "declaratii" / "legislatura-2024.json"
OUT_DIR = ROOT / "data" / "analize"
PDF_CACHE = OUT_DIR / "_pdfs"

# Regex pentru sume — STRICT: prinde DOAR ultima secvență contiguă de cifre înainte
# de valută. Asta evită capturarea anilor din date (ex. "2024 2029 145738 RON" → 145738).
# Format românesc acceptat: "150.000", "75.500,50", "1234"
RE_AMOUNT = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(RON|EUR|EURO|USD|GBP|CHF|lei|euro|dolari)\b",
    re.IGNORECASE,
)

# Rate de schimb aproximative (mai 2026) pentru normalizare la RON
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


def _parse_amount(num_str: str) -> float | None:
    """'150.000', '1 200 000', '75.500,50' → float."""
    # Curăță spații
    s = num_str.replace(" ", "")
    # Dacă există atât . cât și ,
    if "." in s and "," in s:
        # Format românesc: . = mii, , = zecimale
        if s.rindex(",") > s.rindex("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Doar virgulă — verifică dacă e zecimal (1-2 cifre după) sau separator mii
        parts = s.split(",")
        s = s.replace(",", ".") if len(parts[-1]) <= 2 else s.replace(",", "")
    elif "." in s:
        # Punct — verifică ultima parte
        parts = s.split(".")
        if len(parts[-1]) == 3 and len(parts) >= 2:
            # Probabil 150.000 = 150000
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def normalize_to_ron(amount: float, currency: str) -> float:
    rate = RATES_TO_RON.get(currency.upper(), 1.0)
    return amount * rate


def extract_section(text: str, section_marker: str, next_markers: list[str]) -> str:
    """Extrage textul dintre un marker de secțiune și următorul marker."""
    start = text.find(section_marker)
    if start < 0:
        return ""
    end = len(text)
    for nm in next_markers:
        idx = text.find(nm, start + len(section_marker))
        if 0 < idx < end:
            end = idx
    return text[start:end]


def parse_declaratie_pdf(pdf_path: Path) -> dict:
    """Parsează un PDF de declarație ANI și extrage valori agregate.

    NOTĂ IMPORTANTĂ: formularul ANI NU cere valoarea în RON pentru imobile,
    ci doar suprafață, an, cotă, modul de dobândire. Pentru patrimoniu imobiliar
    folosim ca proxy: nr. terenuri + nr. clădiri + suprafață totală (m²).

    Returnează:
        {
            "terenuri_count": int,       # nr. terenuri declarate
            "cladiri_count": int,        # nr. clădiri/apartamente
            "suprafata_total_mp": float, # suma suprafețelor (proxy patrimoniu)
            "conturi_total_ron": float,  # active financiare în RON (norm.)
            "venituri_anuale_ron": float,
            "datorii_total_ron": float,
            "auto_count": int,
            "text_extracted": bool,
            "raw_amounts": [...],
            "error": str | None,
        }
    """
    result = {
        "terenuri_count": 0,
        "cladiri_count": 0,
        "suprafata_total_mp": 0.0,
        "conturi_total_ron": 0.0,
        "venituri_anuale_ron": 0.0,
        "datorii_total_ron": 0.0,
        "auto_count": 0,
        "text_extracted": False,
        "raw_amounts": [],
        "error": None,
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        result["error"] = f"PDF read failed: {e}"
        return result

    if len(full_text.strip()) < 100:
        result["error"] = "PDF gol sau scanat (text < 100 chars). Necesită OCR."
        return result

    result["text_extracted"] = True

    # Markeri pentru secțiunile ANI standardizate — observate empiric
    # Formularul folosește numerotare romană + minuscule:
    # I. Bunuri imobile · II. Bunuri mobile · III. Bunuri mobile valoare > 3.000 EUR
    # IV. Active financiare · V. Datorii · VI. Cadouri · VII. Venituri
    markers = [
        "I. Bunuri imobile",
        "II. Bunuri mobile",
        "III. Bunuri mobile",
        "IV. Active financiare",
        "V. Datorii",
        "VI. Cadouri",
        "VII. Venituri",
    ]

    # I — BUNURI IMOBILE (terenuri + clădiri)
    # Formularul NU cere valoare în RON — doar suprafață (m²) și caracteristici.
    sec_imobile = extract_section(full_text, "I. Bunuri imobile", markers)
    # Sub-secțiuni: "1. Terenuri" și "2. Clădiri"
    sec_terenuri = extract_section(sec_imobile, "1. Terenuri", ["2. Clădiri", "II. Bunuri mobile"])
    sec_cladiri = extract_section(sec_imobile, "2. Clădiri", ["II. Bunuri mobile"])
    # Numărăm rândurile cu m² (= un imobil declarat)
    re_mp = re.compile(r"(\d+(?:[.,]\d+)?)\s*m\s*²?", re.IGNORECASE)
    for sec_name, sec_text, count_key in [
        ("terenuri", sec_terenuri, "terenuri_count"),
        ("cladiri", sec_cladiri, "cladiri_count"),
    ]:
        matches = list(re_mp.finditer(sec_text))
        result[count_key] = len(matches)
        for m in matches:
            mp = _parse_amount(m.group(1))
            if mp and mp > 5:  # excludem cota-parte mică interpretată ca m²
                result["suprafata_total_mp"] += mp
                result["raw_amounts"].append({"section": sec_name, "amount": mp, "raw": m.group(0)})

    # IV — ACTIVE FINANCIARE (conturi + depozite + plasamente)
    sec_conturi = extract_section(full_text, "IV. Active financiare", markers)
    for m in RE_AMOUNT.finditer(sec_conturi):
        num = _parse_amount(m.group(1))
        if num and num > 100:
            normalized = normalize_to_ron(num, m.group(2))
            result["conturi_total_ron"] += normalized
            result["raw_amounts"].append(
                {"section": "conturi", "amount": normalized, "raw": m.group(0)}
            )

    # V — DATORII (credite, ipoteci)
    sec_datorii = extract_section(full_text, "V. Datorii", markers)
    for m in RE_AMOUNT.finditer(sec_datorii):
        num = _parse_amount(m.group(1))
        if num and num > 100:
            normalized = normalize_to_ron(num, m.group(2))
            result["datorii_total_ron"] += normalized
            result["raw_amounts"].append(
                {"section": "datorii", "amount": normalized, "raw": m.group(0)}
            )

    # VII — VENITURI (salarii, dividende, chirii — toate anuale)
    sec_venituri = extract_section(full_text, "VII. Venituri", markers)
    # Fallback dacă nu găsim cu "VII." — uneori formularul lipsește numerotarea
    if not sec_venituri:
        sec_venituri = extract_section(full_text, "Venituri ale declarantului", markers)
    for m in RE_AMOUNT.finditer(sec_venituri):
        num = _parse_amount(m.group(1))
        if num and num > 100:
            normalized = normalize_to_ron(num, m.group(2))
            result["venituri_anuale_ron"] += normalized
            result["raw_amounts"].append(
                {"section": "venituri", "amount": normalized, "raw": m.group(0)}
            )

    # Auto count — secțiunea II; anchor to line-start to exclude section header words
    sec_mobile = extract_section(full_text, "II. Bunuri mobile", markers)
    result["auto_count"] = len(
        re.findall(
            r"^(autoturism|autovehicul|motociclet|tractor|remorc|iaht|şalup|salup)\w*",
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partide", nargs="+", default=["PSD", "USR"])
    parser.add_argument("--limit", type=int, default=None, help="Limită per partid (test)")
    parser.add_argument("--no-cache", action="store_true", help="Forțează re-download")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_CACHE.mkdir(parents=True, exist_ok=True)

    if not DECL_FILE.exists():
        print(f"Lipsește {DECL_FILE}")
        return 1

    declaratii = json.loads(DECL_FILE.read_text(encoding="utf-8"))["data"]
    print(f"Total deputați în declaratii: {len(declaratii)}")

    # Filtrare după partid
    grupuri: dict[str, list] = defaultdict(list)
    for d in declaratii:
        p = d.get("partid_short")
        if p in args.partide:
            grupuri[p].append(d)

    print(f"Partide analizate: {', '.join(args.partide)}")
    for p in args.partide:
        print(f"  {p}: {len(grupuri[p])} deputați")
    print()

    rezultate_pe_deputat = []
    for partid in args.partide:
        deputați = grupuri[partid]
        if args.limit:
            deputați = deputați[: args.limit]
        print(f"\n=== Procesare {partid} ({len(deputați)} deputați) ===")

        for i, d in enumerate(deputați, 1):
            if not d.get("avere"):
                continue
            # Iau cel mai recent PDF de avere
            ultima_avere = sorted(d["avere"], key=lambda x: x.get("data") or "", reverse=True)[0]
            pdf_url = ultima_avere["url"]
            pdf_path = PDF_CACHE / f"{d['cdep_idm']}.pdf"

            if not download_pdf(pdf_url, pdf_path, force=args.no_cache):
                continue

            parsed = parse_declaratie_pdf(pdf_path)
            rezultate_pe_deputat.append(
                {
                    "partid": partid,
                    "cdep_idm": d["cdep_idm"],
                    "nume": d["deputat_nume"],
                    "data_declaratie": ultima_avere.get("data"),
                    "pdf_url": pdf_url,
                    **{k: v for k, v in parsed.items() if k != "raw_amounts"},
                }
            )

            if i % 10 == 0:
                print(f"  [{i}/{len(deputați)}] {d['deputat_nume']}")
            # Pauză mică ca să nu enervăm cdep.ro
            if i % 5 == 0:
                time.sleep(1)

    # Salvăm rezultate
    out_json = OUT_DIR / "avere_psd_vs_usr.json"
    out_json.write_text(
        json.dumps(rezultate_pe_deputat, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    out_csv = OUT_DIR / "avere_psd_vs_usr.csv"
    with out_csv.open("w", encoding="utf-8") as f:
        f.write(
            "partid,cdep_idm,nume,data_declaratie,terenuri_count,cladiri_count,"
            "suprafata_total_mp,conturi_total_ron,venituri_anuale_ron,"
            "datorii_total_ron,auto_count,text_extracted,error\n"
        )
        for r in rezultate_pe_deputat:
            err = (r.get("error") or "").replace(",", ";")
            f.write(
                f"{r['partid']},{r['cdep_idm']},\"{r['nume']}\",{r.get('data_declaratie') or ''},"
                f"{r.get('terenuri_count', 0)},{r.get('cladiri_count', 0)},"
                f"{r.get('suprafata_total_mp', 0):.0f},"
                f"{r['conturi_total_ron']:.0f},{r['venituri_anuale_ron']:.0f},"
                f"{r['datorii_total_ron']:.0f},"
                f"{r['auto_count']},{r['text_extracted']},{err}\n"
            )

    # Agregare statistici per partid
    print("\n" + "=" * 95)
    print("REZULTATE — AGREGATE PER PARTID")
    print("=" * 95)
    print(
        f"{'Partid':<8} {'N':>4} {'Tern':>5} {'Cld':>4} {'Mp tot':>10} "
        f"{'Conturi RON':>15} {'Venituri RON':>15} {'Auto avg':>9}"
    )
    print("-" * 95)
    for partid in args.partide:
        items = [r for r in rezultate_pe_deputat if r["partid"] == partid and r["text_extracted"]]
        if not items:
            print(f"{partid}: niciun rezultat extras (probabil PDF-uri scanate)")
            continue
        total_terenuri = sum(r.get("terenuri_count", 0) for r in items)
        total_cladiri = sum(r.get("cladiri_count", 0) for r in items)
        total_mp = sum(r.get("suprafata_total_mp", 0) for r in items)
        total_conturi = sum(r["conturi_total_ron"] for r in items)
        total_venituri = sum(r["venituri_anuale_ron"] for r in items)
        avg_auto = sum(r["auto_count"] for r in items) / len(items)
        print(
            f"{partid:<8} {len(items):>4} "
            f"{total_terenuri:>5} {total_cladiri:>4} {total_mp:>10,.0f} "
            f"{total_conturi:>15,.0f} {total_venituri:>15,.0f} {avg_auto:>9.2f}"
        )
    print()
    print("Notă:")
    print("  Tern/Cld = nr. terenuri / clădiri declarate (formularul nu cere valoare RON)")
    print("  Mp tot   = suma suprafețelor (m²) — proxy mărime patrimoniu")
    print("  Conturi  = suma activelor financiare din PDF, normalizată la RON")
    print("  Venituri = sume anuale declarate (salarii + dividende + chirii)")
    print()
    print(f"Detalii JSON: {out_json}")
    print(f"Tabel CSV:    {out_csv}")
    print()
    print("ATENȚIE: extragerea e BEST-EFFORT — PDF-urile scanate necesită OCR.")
    print("Verifică câmpul 'text_extracted' în CSV pentru a vedea câte au reușit.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
