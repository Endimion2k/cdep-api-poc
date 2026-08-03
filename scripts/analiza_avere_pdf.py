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
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Folosim helper-ul HTTP cu truststore + SSL adapter legacy (configurat
# pentru certificate Windows MITM de antivirus).
from scrapers._http import get as http_get  # noqa: E402
from parsers.avere_pdf import parse_pdf  # noqa: E402

DECL_FILE = ROOT / "data" / "v1" / "declaratii" / "legislatura-2024.json"
OUT_DIR = ROOT / "data" / "analize"
PDF_CACHE = OUT_DIR / "_pdfs"


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

            parsed = parse_pdf(pdf_path)
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
            "suprafata_total_mp,conturi_total_ron,plasamente_total_ron,venituri_anuale_ron,"
            "bijuterii_total_ron,bunuri_instrainate_total_ron,cadouri_total_ron,"
            "datorii_total_ron,auto_count,text_extracted,error\n"
        )
        for r in rezultate_pe_deputat:
            err = (r.get("error") or "").replace(",", ";")
            f.write(
                f"{r['partid']},{r['cdep_idm']},\"{r['nume']}\",{r.get('data_declaratie') or ''},"
                f"{r.get('terenuri_count', 0)},{r.get('cladiri_count', 0)},"
                f"{r.get('suprafata_total_mp', 0):.0f},"
                f"{r.get('conturi_total_ron', 0):.0f},{r.get('plasamente_total_ron', 0):.0f},"
                f"{r.get('venituri_anuale_ron', 0):.0f},"
                f"{r.get('bijuterii_total_ron', 0):.0f},{r.get('bunuri_instrainate_total_ron', 0):.0f},"
                f"{r.get('cadouri_total_ron', 0):.0f},"
                f"{r.get('datorii_total_ron', 0):.0f},"
                f"{r.get('auto_count', 0)},{r.get('text_extracted', False)},{err}\n"
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
