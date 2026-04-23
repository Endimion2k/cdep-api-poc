# CDEP API — Camera Deputaților, date deschise

Un API REST public, gratuit, care expune datele parlamentare ale **Camerei Deputaților** din România în format **JSON**. Construit deasupra surselor publice de pe [cdep.ro](https://www.cdep.ro), actualizat zilnic.

> **Status**: 🟡 proof-of-concept extins în implementare · prima fază a lansării publice: *S3–S6* · vezi [TIMELINE.md](./TIMELINE.md)

[![License: OGL v3.0](https://img.shields.io/badge/license-OGL%20v3.0-blue.svg)](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
[![Status: POC](https://img.shields.io/badge/status-POC%20%E2%86%92%20MVP-yellow.svg)](./TIMELINE.md)
[![Docs: Swagger](https://img.shields.io/badge/docs-Swagger%20UI-green.svg)](https://endimion2k.github.io/cdep-api-poc/docs/swagger.html)

---

## De ce există acest proiect

Camera Deputaților publică date de interes public vast — voturi nominale, prezență, proiecte legislative, activitate în comisii — dar exclusiv sub formă de pagini HTML și PDF-uri. Lipsește o interfață programatică care să permită:

- **jurnaliștilor** să monitorizeze rapid deputații din circumscripția lor,
- **ONG-urilor** să urmărească proiectele de lege relevante,
- **cercetătorilor** să facă analize cantitative,
- **dezvoltatorilor civici** să construiască dashboard-uri, boți, extensii de browser,
- **cetățenilor** să-și verifice propriul deputat.

Acest API transformă HTML-ul public în JSON structurat, versionat și documentat.

---

## Endpoint-uri (roadmap)

### ✅ În POC (documentație OpenAPI existentă)

| Endpoint | Descriere |
|---|---|
| `GET /deputati` | Listă deputați, filtre pe legislatură / partid / județ |
| `GET /deputati/{id}` | Profil individual (bio, mandat, comisii, contact) |
| `GET /deputati/{id}/prezenta` | Statistici prezență (plen + comisii, per an) |
| `GET /voturi` | Listă voturi plen (agregate: pentru / împotrivă / abțineri) |
| `GET /voturi/{id}` | Vot detaliat cu lista individuală a deputaților |
| `GET /proiecte-lege` | Listă proiecte legislative, filtru pe stadiu / cuvânt-cheie |
| `GET /comisii` | Listă comisii permanente / speciale / comune |
| `GET /comisii/{slug}/activitate` | Activitate comisie (ședințe, rapoarte) |

### 🆕 Extensii planificate (vezi TIMELINE.md)

| Endpoint | Valoare adăugată |
|---|---|
| `GET /interpelari`, `GET /intrebari-scrise` | Indicator-cheie de activitate, greu accesibil astăzi |
| `GET /amendamente` | Amendamente depuse pe proiecte, cu autor și soartă |
| `GET /motiuni` | Moțiuni simple + de cenzură, cu semnatari și rezultat |
| `GET /declaratii-politice` | Luări de cuvânt din plen |
| `GET /grupuri-parlamentare` | Componență, lideri, purtători de cuvânt |
| `GET /birou-permanent` | Componență și decizii publice |
| `GET /stenograme` | Transcripte ședințe plen |
| `GET /search?q=` | Căutare full-text peste tot corpus-ul |
| `GET /feed.atom`, `GET /feed.json` | Flux noutăți (voturi noi, proiecte schimbate) |

---

## Arhitectură

```
┌──────────────┐    cron        ┌───────────────┐    write      ┌──────────────────┐
│   cdep.ro    │ ──────────────►│  scraper-uri  │ ─────────────►│  /data/*.json    │
│  (HTML+PDF)  │  GitHub Actions│   (Python)    │   commit Git  │  (fișiere plate) │
└──────────────┘    zilnic      └───────────────┘               └────────┬─────────┘
                                                                         │
                                                                  GitHub Pages
                                                                         │
                                                                         ▼
                                                             ┌─────────────────────┐
                                                             │   consumatori:      │
                                                             │   journaliști, ONG, │
                                                             │   dezvoltatori      │
                                                             └─────────────────────┘
```

**Alegere deliberată**: Opțiunea *static snapshot* (scraper → JSON → GitHub Pages).
Avantaje: **cost zero**, zero server de întreținut, CDN global implicit, portabilitate totală.
Limitări acceptate: filtrarea complexă se face client-side; prospețimea datelor depinde de cron (tipic 24h).
Migrare viitoare spre backend cu DB este opțională, doar dacă proiectul obține adoptare.
Detalii complete și alternative comparate în `CDEP_API_Plan_Implementare.docx` (planul de 17 pagini).

---

## Stack tehnic

- **Python 3.11+** — scraperii, modele de date, teste
- **`requests` + `parsel`** — HTTP + CSS/XPath
- **`pdfplumber` (+ `tesseract` fallback)** — PDF parsing
- **`pydantic v2`** — modele de date = **sursă unică de adevăr** (OpenAPI se generează din ele)
- **`pytest` + `syrupy`** — teste + snapshot testing
- **`ruff`, `mypy --strict`, `pre-commit`** — igienă cod
- **GitHub Actions** — cron zilnic + workflow manual
- **GitHub Pages** — hosting static pentru JSON + docs

---

## Structură repo (țintă)

```
cdep-api-poc/
├── api/
│   └── openapi.yaml           # generat automat din /schemas (nu se editează manual)
├── data/                      # output JSON, commit automat
│   └── v1/
│       ├── deputati/
│       ├── voturi/
│       ├── proiecte-lege/
│       ├── comisii/
│       └── meta.json          # timestamp, versiune scraper
├── docs/
│   └── swagger.html           # Swagger UI
├── scrapers/                  # cod per-resursă
│   ├── deputati.py
│   ├── voturi.py
│   └── ...
├── schemas/                   # Pydantic models
│   ├── deputat.py
│   ├── vot.py
│   └── ...
├── scripts/                   # utilitare (validare, generare OpenAPI etc.)
├── tests/
│   ├── __snapshots__/
│   └── test_*.py
├── .github/workflows/
│   ├── scrape.yml             # cron zilnic 06:00 Europe/Bucharest
│   └── ci.yml                 # lint + typecheck + teste
├── sitemap.md                 # inventarul URL-urilor cdep.ro
├── TIMELINE.md                # planul de 24 săptămâni
├── BACKLOG.md                 # idei amânate pentru v1.1+
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── CHANGELOG.md
└── README.md
```

---

## Instalare locală (pentru dezvoltare)

```bash
git clone https://github.com/Endimion2k/cdep-api-poc.git
cd cdep-api-poc

python -m venv .venv
source .venv/bin/activate       # pe Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

pre-commit install

# rulează un scraper
python -m scrapers.deputati --legislatura 2024

# rulează testele
pytest

# generează OpenAPI din schemele Pydantic
python scripts/generate_openapi.py
```

---

## Utilizare (când endpoint-urile sunt live)

### Python
```python
import requests

deputati = requests.get(
    "https://endimion2k.github.io/cdep-api-poc/data/v1/deputati/legislatura-2024.json"
).json()

top_absenti = sorted(deputati["data"], key=lambda d: d["prezenta_pct"])[:10]
for d in top_absenti:
    print(d["nume"], d["partid"], d["prezenta_pct"], "%")
```

### JavaScript
```javascript
const res = await fetch(
  "https://endimion2k.github.io/cdep-api-poc/data/v1/deputati/legislatura-2024.json"
);
const { data } = await res.json();
console.log(data.filter(d => d.judet === "Cluj"));
```

### curl
```bash
curl -sL https://endimion2k.github.io/cdep-api-poc/data/v1/deputati/legislatura-2024.json \
  | jq '.data[] | select(.partid == "PNL")'
```

---

## Contribuie

Proiectul e în fază timpurie și orice ajutor este binevenit. Tipuri de contribuții căutate:

- **Scraperi** pentru secțiuni noi de pe cdep.ro (vezi `TIMELINE.md` fazele 3–5)
- **Teste de regresie** (snapshot tests care detectează schimbări HTML pe cdep.ro)
- **Exemple de utilizare** (notebook-uri, vizualizări, dashboard-uri)
- **Feedback** din partea jurnaliștilor / ONG-urilor — ce endpoint-uri lipsesc?

Vezi `CONTRIBUTING.md` pentru pași detaliați.

---

## Date & licență

- **Sursa datelor**: [www.cdep.ro](https://www.cdep.ro) — date publice ale Camerei Deputaților
- **Licență cod**: [Open Government License v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
- **Date colectate**: exclusiv date publice; **nu** colectăm CNP, telefon personal, adresă privată
- **GDPR**: datele parlamentarilor ca persoane publice în exercițiul mandatului sunt exceptate de la restricțiile GDPR standard. Totuși, orice cerere de rectificare / eliminare poate fi deschisă ca issue.

---

## Autor

**Cătălin Popa** · inițiativă în contextul candidaturii pentru internship la Camera Deputaților, Comisia pentru Tehnologia Informației și Comunicațiilor (2026).

Inspirat de [bikestylish.ro](https://bikestylish.ro) — model similar de API deschis pentru industria bicicletelor din România.

---

## Roadmap pe scurt

Vezi [**TIMELINE.md**](./TIMELINE.md) pentru planul complet de 24 săptămâni cu task-uri bifabile și [**CDEP_API_Plan_Implementare.docx**](./CDEP_API_Plan_Implementare.docx) pentru analiza arhitecturală completă (17 pagini).

| Milestone | Perioadă | Conținut |
|---|---|---|
| M0 — setup | S1–S2 | Repo + CI + primul push automat |
| M1 — deputați | S3–S6 | `/deputati` live cu date reale |
| M2 — voturi | S7–S11 | `/voturi` live — cel mai valoros |
| M3 — proiecte | S12–S15 | `/proiecte-lege` + amendamente |
| M4 — organizare | S16–S19 | Comisii, grupuri, Birou Permanent |
| M5 — accountability | S20–S22 | Interpelări, moțiuni, `/search` |
| M6 — lansare | S23–S24 | v1.0 public |
