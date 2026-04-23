# INTEGRATIONS.md

Decizii externe adoptate pentru proiect: standarde, biblioteci, referințe. Documentez aici **de ce** și **cum**, astfel încât un contributor viitor (sau tu peste 3 luni) să nu repete analiza.

---

## 1. Popolo — standard internațional de date legislative

### Ce e

[Popolo](https://www.popoloproject.com/) — specificație deschisă (din 2014, maintained) pentru reprezentarea datelor legislative: persoane, organizații, apartenențe, ședințe, voturi, moțiuni. Definit ca:

- un **data model** (ce câmpuri are o `Person`, un `VoteEvent` etc.)
- un **serialization format** (JSON-LD cu `@context` Popolo)

Folosit de: **OpenStates** (USA, 50 state legislatures), **EveryPolitician** (global archive), **OpenParliament.ca**, **Parliamentary Monitoring Group** (South Africa). E standardul de facto pentru civic tech legislativ.

### De ce-l adoptăm

- **Interoperabilitate**. Orice unealtă internațională care înțelege Popolo poate consuma instant datele CDEP fără layer de traducere.
- **Modelare corectă din start**. Popolo a rezolvat deja probleme subtile pe care altfel le-am redescoperi: cum modelezi că un deputat își schimbă partidul (→ `Membership` cu `start_date`/`end_date`, NU un câmp `party` pe `Person`); cum distingi o comisie permanentă de una specială (→ `Organization.classification`); cum lege voturile nominale de moțiuni (→ `VoteEvent.motion_id`).
- **Onboarding mai ușor** pentru contributori din civic tech — dacă vin din OpenStates, recunosc imediat schema.

### Ce adoptăm (subset pragmatic)

Adoptăm **numele câmpurilor**, nu formatul JSON-LD complet. JSON-urile noastre rămân plate, fără `@context` / `@type`. Doar convenția de denumire urmează Popolo.

| Resursa noastră | Popolo echivalent | Câmpuri aliniate |
|---|---|---|
| `Deputat` | `Person` | `id`, `name`, `given_name`, `family_name`, `gender`, `birth_date`, `email`, `image`, `biography` |
| `Partid`, `Comisie`, `Grup` | `Organization` | `id`, `name`, `classification`, `founding_date`, `dissolution_date` |
| (afiliere deputat la partid/comisie) | `Membership` | `person_id`, `organization_id`, `role`, `start_date`, `end_date`, `on_behalf_of_id` |
| `Proiect` / `Moțiune` | `Motion` | `id`, `organization_id`, `text`, `date`, `requirement`, `result` |
| `Vot` (ședință + rezultat) | `VoteEvent` | `id`, `motion_id`, `start_date`, `result`, `counts`, `votes` |
| (vot individual deputat) | `Vote` (sub-obiect) | `voter_id`, `option` (enum: `yes`, `no`, `abstain`, `absent`) |
| `SedintaPlen`, `SedintaComisie` | `Event` | `id`, `name`, `start_date`, `end_date`, `organization_id` |

### Ce NU adoptăm

- **JSON-LD format** (`@context`, `@type`, `@id`) — prea verbos; JSON-urile noastre rămân plate.
- **Câmpuri obscure**: `Contact_detail`, `Identifier.scheme`, `Link.note`. Le omitem până când cineva le cere.
- **Endpoint-uri Popolo-native** (`/people`, `/events`). Păstrăm denumirea românească (`/deputati`, `/voturi`) pentru că e mai accesibilă pentru publicul-țintă local.

### Cum verificăm conformitatea

Nu adăugăm dependență obligatorie. Opțional, în Faza 0 evaluăm `python-popolo` sau scriem un simplu test de regresie care verifică prezența câmpurilor-cheie. Dacă subsetul adoptat crește, adăugăm validare automată.

---

## 2. Pagefind — căutare pe site static

### Ce e

[Pagefind](https://pagefind.app) — generator de indecși de căutare pentru site-uri statice. Scris în Rust, ~5,2k stele GitHub. Filozofie: *„search, but for sites that don't have a backend"*.

Cum funcționează:
1. La **build time**, rulează peste conținutul tău și produce fișiere de index fragmentate (`_pagefind/`).
2. La **runtime**, un JS mic (~30KB) descarcă doar fragmentele necesare pentru query-ul curent.

### De ce-l adoptăm

- **Construit exact pentru cazul nostru**: site static pe GitHub Pages, fără backend posibil.
- **Performanță**: indecșii sunt fragmentați, deci funcționează și pe colecții mari fără să încarce tot dataset-ul în browser.
- **UI gata făcut** (`<PagefindUI />`) cu stil personalizabil; sau API programatic dacă vrem design custom.
- Alternativa — index invertit scris manual — ar fi costat ~6h de implementare, ~2h de UI, și ar fi fost inferior funcțional.

### Cum îl integrăm

**Pas 1 — în `.github/workflows/scrape.yml`**, după ce scraperul salvează JSON-urile:

```yaml
- name: Build Pagefind search index
  run: |
    npx -y pagefind@latest \
      --site data/v1 \
      --output-path data/v1/_pagefind \
      --glob "**/*.json"
```

**Pas 2 — în landing page sau `/search.html`**:

```html
<link href="/data/v1/_pagefind/pagefind-ui.css" rel="stylesheet">
<script src="/data/v1/_pagefind/pagefind-ui.js"></script>
<div id="search"></div>
<script>
  new PagefindUI({
    element: "#search",
    showSubResults: true,
    translations: { placeholder: "Caută deputat, vot, proiect..." }
  });
</script>
```

**Pas 3 — commit-ul zilnic** include și folder-ul `_pagefind`, deci user-ul primește indecși proaspeți la fiecare scrape.

### Alternative considerate

- **Lunr.js** (9k stele) — ok, dar index monolit; nu se fragmentează bine peste dataset-uri mari.
- **FlexSearch** (13,7k stele) — mai puternic decât Pagefind, dar ~200KB JS; overkill pentru noi.
- **Algolia/MeiliSearch/Typesense** — necesită backend; afară din scope (Opțiunea A).

---

## 3. Proiecte de referință (studiu, nu import)

Nu importăm cod din ele (stack-uri diferite), dar le citim înainte de a începe să scriem scraper-ii. Fiecare are ceva valoros de învățat.

### OpenStates (USA) — [openstates/openstates-scrapers](https://github.com/openstates/openstates-scrapers) · 897 ⭐

Canonical civic tech project, ~10 ani de dezvoltare, scrape pentru 50 de legislaturi de stat. De la ei copiem:

- **Pattern arhitectural**: `scrape → normalize → validate → serialize`, fiecare pas izolat.
- **Structura de teste**: snapshot tests peste istoricul HTML, cu posibilitatea de a reejuca scrape-ul pe un commit vechi.
- **`canonical_id`** stabil peste legislaturi — ne rezolvă problema că ID-urile cdep.ro se schimbă.

Repo complementar: [openstates/openstates-core](https://github.com/openstates/openstates-core) — data model + framework. Merită o oră de lectură.

### Belgium Federal Parliament — [Parliament-in-Data/Federal-Parliament-Scraper](https://github.com/Parliament-in-Data/Federal-Parliament-Scraper) · 22 ⭐

**Scope aproape identic cu al nostru**: parlament național, Python, plen + comisii + voturi. Repo mic, concis — model realist pentru „cât cod e nevoie" la scară comparabilă. De citit tot codul, nu doar README-ul.

### Code for Romania — [code4romania/czl-scrape](https://github.com/code4romania/czl-scrape) · 12 ⭐

Precedent local de scraping legislativ românesc. Valoros pentru:

- Patterns specifici românești (diacritice în HTML, encoding-uri inconsistente)
- Structura tipică a PDF-urilor oficiale .gov.ro
- Potențial contributori — Code for Romania are comunitate activă

După M2 din TIMELINE, merită să facem un issue de pe repo-ul lor cu mesaj scurt „salut, am folosit patternuri de aici, iată ce am construit" — posibil cross-promotion.

---

## 4. Biblioteci noi adăugate la stack

| Bibliotecă | Scop | Fază introdusă |
|---|---|---|
| `pagefind` (npm, via `npx`) | Index de căutare static | Faza 5 |
| `python-popolo` (opțional) | Validare conformitate Popolo | Faza 0, doar dacă subsetul adoptat devine extins |

Fără dependințe noi față de planul inițial în alte faze — scheme Popolo se implementează pur cu Pydantic, fără lib externă.

---

## 5. Decizii rejectate (pentru memoria viitoare)

### OpnTec/parliament-scraper (apare cu 1,407 stele)

Suspect: are un repo paralel „artwork" cu 1,375 stele (aproape identic număr), fără nicio explicație plauzibilă pentru un repo de „artwork" să aibă mii de stele. Sugerează star-farming sau fork scheme, nu un proiect serios. **Nu importăm, nu referim.**

### FlexSearch

Mai puternic decât Pagefind pe query-uri complexe, dar costul de ~200KB JS + configurare manuală a indexului depășește beneficiul pentru cazul nostru.

### Datasette (simonw)

Excelent proiect — transformă SQLite în API browsabil cu plugin-uri. **Relevant doar dacă migrăm la Opțiunea B/C** din planul arhitectural. Pentru stack-ul actual (static), Pagefind + JSON-uri plate e suficient. Reevaluăm dacă proiectul obține adoptare serioasă.

### Scrapy

Framework matur de scraping (47k stele). Pentru scala noastră (mii de pagini, nu milioane) e overkill — `requests` + `parsel` e suficient și mai ușor de debugat. Reconsiderăm dacă numărul de URL-uri depășește ~50k.

---

*Versiune: 1.0 · Ultima actualizare: 2026-04-23*
