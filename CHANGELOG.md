# Changelog

Toate modificările notabile ale proiectului sunt documentate aici. Format bazat pe [Keep a Changelog](https://keepachangelog.com/) și [SemVer](https://semver.org/).

## [v0.4.2] — 2026-09-22 — Stenograme cu intervenții, migrare /ords/

### Schimbat

- **`/stenograme`**: `interventions[]` e populat (`vorbitor`, `partid`, `rol`, `text` trunchiat la 5000 de caractere). Pagina `steno2015.data` (fostul `source_url` unic) e doar cuprinsul ședinței; scraperul urmează acum link-ul `steno2015.stenograma?ids=` (câmp nou `transcript_url`), iar `text_complet_len` e lungimea transcrierii.
- Toate link-urile `https://www.cdep.ro/pls/...` din date sunt rescrise pe `/ords/pls/...`: cdep.ro a mutat aplicațiile PL/SQL sub `/ords/`, vechile căi dau 404 (`scripts/migrate_ords_urls.py`, ~96.000 de link-uri).
- `interpelari.adresant_grup` curățat de sufixul „Destinatar:” rămas de la un parser vechi (3.604 rânduri).
- `/ordine-zi`: aceeași agendă multi-zi nu se mai salvează o dată pentru fiecare zi din calendar (dedupe pe `id`).
- Parserul de deputați adaptat la HTML-ul nou al profilului (validare, birou parlamentar, istoricul formațiunii cu marcaje „din …”).

## [v0.4.1] — 2026-05-26 — Sub-endpoint /declaratii-avere cu PDF parsing

### Adăugat

- **`/declaratii-avere/legislatura-{leg}.json`** — sumar per deputat cu ultima declarație + delta față de prima.
- **`/declaratii-avere/legislatura-{leg}/{cdep_idm}.json`** — cronologie completă a declarațiilor per deputat, fiecare cu sume parsate din PDF.
- **`schemas/avere.py`** — `AvereDeputat`, `AvereDeclaratie`, `AvereImobil`, `AvereSummary`.
- **`scripts/build_declaratii_avere.py`** — orchestrator care:
  - Descarcă TOATE PDF-urile (avere) pentru fiecare deputat (cronologic)
  - Parsează cu pdfplumber categoriile standardizate ANI (I-VII)
  - Calculează delta (prima vs ultima declarație) pentru identificare "schimbări de avere în mandat"
  - Cache PDF local (`data/analize/_pdfs/`) — re-rulări instant
- **OpenAPI** 18 paths total (+2 noi).
- **Util pentru jurnalism**: identificare rapidă deputați cu creștere/scădere conturi în mandat, schimbări în nr. imobile.

### Limitări cunoscute

- Sume extrase BEST-EFFORT (regex pe text PDF) — pentru cifre precise verifică PDF-urile.
- Formularul ANI NU cere valoare RON pentru imobile — folosim suprafața (m²) ca proxy.
- PDF-urile scanate (fără text) sunt raportate cu `text_extracted: false`.

---

## [v0.4.0] — 2026-05-26 — 4 endpointuri noi: ordine-zi, declaratii, stenograme, doc-comisii

### Adăugat

- **`/ordine-zi`** — Ordinea de zi a ședințelor plenului (parser validat: 81 puncte extrase per ședință cu cross-link `idp` la /proiecte).
- **`/declaratii`** — Declarații de avere și interese ale deputaților (parser validat: 332 deputați × ~1.5 PDF-uri/tip = ~990 PDF-uri per legislatură).
- **`/stenograme`** — Stenograme ședințe plen (calendar validat: 28 ședințe în 2026; parser detail e WIP — necesită HTML real pentru calibrare exactă a intervențiilor).
- **`/doc-comisii`** — Documente comisii (rapoarte, avize, sinteze, procese verbale; parser validat: 98 documente/pagină cu tip auto-detect + cross-link `idp` pentru rapoarte/avize).

### Schema nouă

- `schemas/ordine_zi.py` — OrdineZi + OrdineZiItem
- `schemas/declaratie.py` — DeclaratieDeputat + DeclaratieFisier
- `schemas/stenograma.py` — Stenograma + StenogramaIntervention + StenogramaSummary
- `schemas/doc_comisie.py` — DocComisie

### Scraperi noi (toate cu suport incremental)

- `scrapers/ordine_zi.py` — descoperă datele via AJAX calendar + parse_session
- `scrapers/declaratii.py` — 1 request returnează lista completă per legislatură
- `scrapers/stenograme.py` — list_session_dates + parse_session (WIP)
- `scrapers/doc_comisii.py` — paginare 99/pagină + auto-stop incremental

### Runner scripts

- `scripts/run_ordine_zi.py` (incremental + `--full`)
- `scripts/run_declaratii.py` (1 req per leg + semantic-diff)
- `scripts/run_stenograme.py` (per-file storage + incremental + `--full`)
- `scripts/run_doc_comisii.py` (paginare + `--pages N` / `--full`)

---

## [v0.3.1] — 2026-05-26 — Endpoint /ordine-zi

### Adăugat

- **`/ords/pls/caseta/ecaseta2015.OrdineZi`** scrapper — Ordinea de zi a ședințelor plenului
- **Schema** `schemas/ordine_zi.py` — OrdineZi (cu items) + OrdineZiItem
- **Scraper** `scrapers/ordine_zi.py` — `list_session_dates_for_month()`, `parse_session()`, `scrape_year()`
- **Runner** `scripts/run_ordine_zi.py` cu suport `--years`, `--leg`, `--full`, incremental implicit
- **URL patterns descoperite**:
  - `/ords/pls/caseta/ecaseta2015.OrdineZi?dat=YYYYMMDD` — ordinea unei zile
  - `/ords/pls/caseta/ecaseta2015.zile_ordinezi?lu=MM&an=YYYY` — AJAX lista zilelor cu ședință
- **Cross-link cu /proiecte**: fiecare punct cu proiect de lege are `idp` extras din linkul `upl_pck2015.proiect?idp=N`
- **Validare offline**: 81 puncte extrase din ședința 26-27 mai 2026, cu cross-link la `idp=21060 (Pl-x 464/2023)`
- **Storage**: `data/v1/ordine-zi/legislatura-{leg}.json`

---

## [v0.3.0] — 2026-05-26 — Incremental complet pentru TOATE endpointurile

### Adăugat

- **Suport incremental EXTINS la toate scrape-fetch endpoint-urile** prin parametrul opțional `skip_ids`:
  - `scrapers/deputati.py:scrape()` — skip pe `cdep_idm`
  - `scrapers/interpelari.py:scrape_year()` — skip pe `cdep_idi`
  - `scrapers/proiecte.py:scrape_year()` — skip pe `cdep_idp`
  - `scrapers/motiuni.py:scrape_all()` — skip pe `cdep_idm`
- **Scripturile `run_*.py` rulează IMPLICIT incremental + flag `--full` pentru refetch complet**:
  - `run_deputati.py --full` — recomandat săptămânal (schimbări partid, comisii, activitate)
  - `run_proiecte.py --full` — recomandat săptămânal (schimbări stadiu, vot final, promulgare)
  - `run_motiuni.py --full` — necesar dacă vot final sau rezultatul se modifică
- **Merge logic** — toate scripturile fac acum merge corect: overwrite-uiesc idm/idi/idp-urile re-fetched și păstrează restul.
- **Voturi** — era deja incremental prin `_index.json` (păstrăm comportamentul).
- **Sancțiuni, comisii, amendamente** — nu necesită incremental (1 request total / derived).

### Așteptat (TIMP DAILY CRON)

| Endpoint | Înainte | Acum (incremental) |
|---|---|---|
| deputati | ~5 min (335 profiles) | ~0.5 min (doar noi) |
| voturi | ~1 min (incremental) | ~1 min (la fel) |
| interpelari | ~30-60 min | ~3-5 min |
| proiecte | ~30 min | ~2-5 min |
| motiuni | ~3 sec (mic) | ~3 sec |
| sanctiuni | ~1 sec (1 req) | ~1 sec |
| **TOTAL** | **~60-90 min** | **~5-10 min** |

Plus refresh săptămânal `--full` pe deputati + proiecte + motiuni (~30 min sâmbătă noaptea).

---

## [v0.2.9] — 2026-05-10 — Incremental update — economie 90%+ bandwidth (parțial)

### Adăugat

- **`scrape_year()` pentru interpelări + proiecte** acceptă `skip_ids` pentru a sări peste detail fetches.
- **`run_interpelari.py`** IMPLICIT incremental.
- **`run_proiecte.py`** IMPLICIT incremental + flag `--full`.
- **Voturi** — deja era incremental prin `_index.json` check.

### Așteptat

- Daily cron pe Windows runner: timp redus de la ~30-60 min la **3-5 min** (doar entitățile noi).
- Bandwidth cdep.ro: ~10% din anteriorul volum (economisim pentru cdep.ro și ne ferim de rate limiting).
- Pentru `--full` proiecte: păstrăm comportamentul vechi (toate proiectele refetched, ~20-30 min).

---

## [v0.2.8] — 2026-05-10 — Parser nou pentru interpelări (schema ORDS)

### Reparat

- **Parser-ul de interpelări** rescris complet pentru schema HTML nouă de pe ORDS:
  - Header extras din `<meta property="og:title">` (înainte căutam regex în body text)
  - Titlu din `<meta property="og:description">` (fallback h1 din `.boxTitle`)
  - Câmpurile (Data înregistrarii, Adresant, Destinatar, etc.) extrase prin parsare label/value din `<tr><td>Label:</td><td>Value</td></tr>`
  - `_parse_iso_date` acceptă acum și formatul `DD.MM.YYYY` (ORDS folosește puncte, înainte erau liniuțe)
  - Adresant și grup parlamentar extrase din `<a href="structura2015.mp">` și `<a href="structura2015.gp">`
  - `raspuns_pdf_url` deduplicat (PDF-ul apare de 2 ori în HTML: icon + text link)
  - `raspuns_sursa` curat (tăiat la "comunicat de:" — păstrăm doar instituția)
- **`scripts/test_interpelari_parser.py`** — test ofline pentru parser folosind un HTML local. Util pentru iterații rapide fără să atingem cdep.ro.

---

## [v0.2.7] — 2026-05-10 — cdep.ro URL migration: /pls/ → /ords/pls/

### Schimbat

- **Toate URL-urile cdep.ro au fost migrate** de pe Oracle PL/SQL Application Server (vechi, prefix `/pls/`) pe **Oracle ORDS** (REST Data Services, prefix `/ords/pls/`). Server-ul cdep.ro a făcut migrarea pe 10 mai 2026.
- **Semantic identic** — paginile, parametrii și structura HTML rămân identice; doar prefixul URL e schimbat.
- **Fix-uit în 11 locuri** (toate scraperele + run scripts + fixtures):
  - `scrapers/{deputati,interpelari,motiuni,proiecte,sanctiuni,voturi}.py` — LIST_URL, DETAIL_URL, NOMINAL_URL, PROFILE_URL, XML_URL
  - `scripts/run_*.py` — `source_url` din meta JSON-uri
  - `scripts/save_fixtures.py` — URL-urile pentru download fixtures
- **Datele existente sunt VALIDE** — nu pierdem nimic. Doar viitoarele scrape-uri folosesc URL-urile noi.
- **`source_url`-urile salvate în vechile JSON-uri** au prefixul `/pls/` (păstrate ca arhivă istorică); JSON-urile noi vor avea `/ords/pls/`.

---

## [v0.2.6] — 2026-04-30 — Toggle limbă RO/EN cu fade transition

### Adăugat

- **`i18n.js`** — sistem i18n cu ~110 chei traduse RO/EN, folosit de toate cele 8 pagini interactive (index, status, sanctiune, deputat, proiect, vot, motiune, search).
- **Buton toggle limbă** plasat în dreapta-sus în header. Persistent prin `localStorage` (`cdep_lang`).
- **Fade transition între limbi** — la click, body fade-out 250ms → reload → fade-in 400ms, marcat prin `sessionStorage` ca să nu apară fade-in la navigările normale.
- **Tradus complet** chrome UI-ul: nav, hero (titlu, descriere, butoane CTA), stats labels, sidebar, footer, search title/subtitle, profile sections (Vot final, Semnatari, Detalii, Comisii, Delegații, Activitate, etc.), tabel headere voturi nominale, filter placeholders.
- **140+ atribute `data-i18n`** distribuite pe pagini: index 28 · status 16 · sanctiune 12 · deputat 19 · proiect 12 · vot 30 · motiune 17 · search 6.
- **Convenție de markup**:
  - `data-i18n="key"` pe text (`<span data-i18n="back">← Înapoi</span>`)
  - `data-i18n-attr="placeholder:key"` pe atribute
  - `<span id="lang-toggle-slot">` în nav unde vrei butonul
  - apel `applyI18n()` după `innerHTML` pe pagini cu render dinamic
- **Datele propriu-zise** (nume deputați, titluri proiecte, descrieri voturi etc.) rămân în română — provin de la cdep.ro și au valoare de sursă oficială. Doar UI chrome-ul este tradus.

---

## [v0.2.5] — 2026-04-30 — SEO + a11y + pre-commit (B1-B4)

### Adăugat

- **`/sitemap.xml`** auto-generat — listează ~100 URL-uri (pagini statice + top 50 deputați + top 30 proiecte cu amendamente + endpoint-uri JSON). Generat de `scripts/build_sitemap_xml.py` în CI.
- **`/robots.txt`** cu sitemap reference + Disallow pe `/pages/` (folder de indexare Pagefind, nu user-facing).
- **Open Graph + Twitter meta tags** pe toate cele 7 pagini interactive — share-urile pe LinkedIn/Facebook arată corect titlu+descriere.
- **Accessibility** — `*:focus-visible` outline, skip link, `role` și `aria-label` pe nav/main, touch targets min 44px.
- **`.pre-commit-config.yaml`** — hooks ruff + checks standard (trailing whitespace, EOF, YAML/JSON valid, large files). Rulează automat la `git commit`.
- CONTRIBUTING.md actualizat cu instrucțiuni pre-commit.

---

## [v0.2.4] — 2026-04-30 — Complete profile pages + legal docs

### Adăugat

- **`/motiune.html?idm={N}`** — pagină profil moțiune cu vot final, rezultat (adoptată/respinsă/retrasă), listă semnatari nominali cu link-uri către search.
- **`/sanctiune.html?id={hash}`** — pagină detaliu sancțiune disciplinară (cu listă completă pe legislatură când lipsește id-ul).
- **`DATA_LICENSE.md`** — clarificare juridică completă: Legea 544/2001 (acces informații publice), GDPR (deputați ca persoane publice), licență OGL v3.0, atribuire recomandată, drept de rectificare prin issue templates.

### Total v0.2.4

8 endpoints + 2 feeds + **6 pagini interactive** (search, deputat, proiect, vot, motiune, sanctiune, status) · 42 tests · documentație juridică completă.

---

## [v0.2.3] — 2026-04-30 — Profile pages + reliability improvements

### Adăugat

- **Status page** (`/status.html` + `/data/v1/status.json`) — health check pentru API: prospețime date, distribuție pe endpoint-uri, mărime fișiere, scraper versions. Util pentru jurnaliști care vor să verifice că datele sunt actualizate.
- **Split fișiere mari pe an** — `/data/v1/interpelari/legislatura-{leg}/{year}.json` și aceleași pentru `proiecte`. Reducere transfer pe mobil de la 21MB la ~3MB/an. Backward compat: fișierele monolitice rămân.
- **`/proiect.html?idp={N}`** — pagină profil proiect legislativ cu timeline procedural, vot final, amendamente, link-uri PDF.
- **`/vot.html?idv={N}`** — pagină profil vot cu defalcare nominală vizualizată: 2 pie charts (overall + per partid), tabel sortabil cu filtre.
- **Snapshot tests pentru toate parserele** (`tests/test_snapshot_parsers.py`) — fixture-uri HTML salvate în `tests/fixtures/`, prind regresii dacă cdep.ro schimbă HTML-ul.
- **CONTRIBUTING.md + issue templates** (data correction, parser bug) — onboarding contributors externi.

### Total v0.2.3

**~38.000 entități** indexate · **8 endpoints JSON** + 2 feeds + **4 pagini interactive** (search, deputat, proiect, vot) + status page · **42 tests** · CI verde · cron zilnic activ.

---

## [v0.2.0] — 2026-04-30 — Multi-legislatură + endpoint-uri suplimentare

### Adăugat

- **Bootstrap legislatura 2020** completă: 354 deputați, 3.616 voturi (cu defalcare nominală), 8 sancțiuni, 18.040 interpelări, 54 comisii, 3.604 proiecte legislative, 721 proiecte cu amendamente (10.063 admise + 413 respinse).
- `/motiuni/legislatura-{leg}.json` — moțiuni simple și de cenzură cu vot final, rezultat (adoptată/respinsă/retrasă), semnatari nominali. Titlul extras din heading HTML, nu din label inexistent.
- `/deputat.html?id={cdep_idm}` — pagină profil deputat user-facing cu foto, partid, județ, contoare activitate, comisii cu rol, cross-link-uri către interpelări adresate și moțiuni semnate.
- Brand update: proiectul e prezentat ca dezvoltat în colaborare cu Comisia pentru Tehnologia Informației și Comunicațiilor (înlocuit textul „candidatura pentru internship" peste tot — README, OpenAPI, index.html, STORAGE.md).

### Total v0.2.0

**~38.000 entități** indexate cross-2-legislaturi · **8 endpoints JSON** + 2 feeds (Atom/JSON) + 2 pagini interactive (search, deputat) · **36 tests** · CI verde · cron zilnic activ.

---

## [v0.1.0] — 2026-04-29 — POC complet

Prima versiune funcțională a API-ului. 7 endpoint-uri live cu date reale, search full-text peste tot corpus-ul, infrastructură CI/CD cu auto-update zilnic.

### Adăugat

**Endpoint-uri**

- `/deputati/legislatura-{leg}.json` — 335 deputați legislatura 2024 cu profile complete (bio, partid, județ, comisii, contoare activitate). Suport și pentru legislaturile 2016 și 2020.
- `/voturi/{leg}/_index.json` + `/voturi/{leg}/{idv}.json` — 816 voturi cu defalcare nominală (DA/NU/abținere/nu au votat per deputat). Acoperire 2024–2026.
- `/sanctiuni/legislatura-{leg}.json` — sancțiuni disciplinare (diminuare indemnizație, avertisment scris, chemare la ordine, retragere cuvânt).
- `/interpelari/legislatura-{leg}.json` — 9.326 interpelări/întrebări parlamentare 2024–2026, cu tracking răspuns (86.4% rate de răspuns).
- `/comisii/legislatura-{leg}.json` — 37 comisii (32 permanente + 5 speciale comune) cu lista completă a membrilor și conducerea.
- `/proiecte/legislatura-{leg}.json` — 1.641 proiecte legislative 2024–2026 cu stadiu, inițiator, cameră decizională, timeline procedural complet, vot final, decret promulgare, **metadate amendamente** (admise/respinse, termen depunere, link PDF raport comisie).
- `/amendamente/legislatura-{leg}.json` — view derivat: 154 proiecte cu cele mai multe amendamente (1.669 admise + 151 respinse = 1.820 trackate), sortate descrescător. Util pentru identificarea celor mai disputate proiecte legislative.
- `/feed.atom` — Atom feed (RFC 4287) cu ultimele 50 evenimente cross-endpoint (voturi, proiecte, interpelări, sancțiuni). Auto-discovery prin `<link rel="alternate">` în landing page.
- `/feed.json` — JSON Feed v1.1 (https://jsonfeed.org/version/1.1/) cu aceleași evenimente.
- `/search.html` — căutare full-text peste ~12.500 entități, cu filter-e faceted (tip, partid, județ, an, stadiu, etc.).

**Infrastructură**

- Self-hosted GitHub Actions runner pe PC Windows din România (cdep.ro geo-blochează runner-ele cloud).
- Workflow `scrape.yml` cu cron zilnic 04:00 UTC: deputați → sancțiuni → voturi → interpelări → proiecte → comisii → HTML pages → Pagefind index → validare → commit.
- Workflow `ci.yml` pentru lint/format pe fiecare push (ruff strict).
- HTTP client cu adapter SSL legacy pentru SHA1 ciphers + truststore.inject_into_ssl() pentru certificate antivirus MITM.

**Modele de date**

- Schemele Pydantic v2 aliniate Popolo: `Deputat` (Person), `Comisie` (Organization), `VoteEvent`, `VoteIndividual`.
- 19 scheme totale documentate în `api/openapi.yaml` (OpenAPI 3.0.3).

**Documentație**

- `README.md` cu cifre live, arhitectură, exemple Python/JS/curl.
- `TIMELINE.md` cu istoric implementare + plan inițial 24 săptămâni.
- `STORAGE.md` (strategia de stocare static JSON cu plan de migrare).
- `INTEGRATIONS.md` (Popolo + Pagefind decision rationale).
- `sitemap.md` (inventarul URL patterns cdep.ro).
- Swagger UI live la `/docs/swagger.html`.
- Landing page interactivă cu demo + statistici live calculate din JSON-uri.

### Note tehnice

- Encoding: cdep.ro returnează ISO-8859-2 pentru voturi XML; gestionat automat de `requests` din declarația HTTP.
- Diacritice: cdep.ro folosește mix de `ţ` (U+0163) și `ț` (U+021B) — toate regex-urile sunt diacritics-insensitive.
- Storage: ~25MB total date JSON (interpelări 10.7MB + voturi 2.3MB index + 800 fișiere individuale ~150MB + proiecte 6.2MB + restul).
- Pagefind index: ~30MB pentru ~12.500 pagini.

### Securitate & licență

- Date publice exclusiv (cdep.ro). Nu se colectează CNP, telefon personal, adresă privată.
- Licență cod: Open Government License v3.0.

[v0.1.0]: https://github.com/Endimion2k/cdep-api-poc/releases/tag/v0.1.0
