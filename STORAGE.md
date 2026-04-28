# STORAGE.md — strategie de stocare a datelor

Decizii asumate pentru fiecare endpoint cu privire la volume, tipul de fișier
și plan de migrare.

---

## Stadiu curent (POC public, GitHub Pages)

| Endpoint | Format | Volum estimat |
|---|---|---|
| `/deputati/legislatura-{leg}.json` | un fișier per legislatură | ~600 KB / leg |
| `/sanctiuni/legislatura-{leg}.json` | un fișier per legislatură | ~5-15 KB / leg |
| `/voturi/{leg}/_index.json` | sumar tuturor voturilor | ~150 KB / leg |
| `/voturi/{leg}/{idv}.json` | un fișier per vot | ~40 KB × ~3900 = **~155 MB / leg curentă** |

**Total POC v1**: 3 legislaturi × deputați + 3 × sancțiuni + 1 × voturi 2024 ≈ **~160 MB**.

---

## Compromis acceptat pentru POC

✅ **Voturi acoperite în repo**: doar **legislatura 2024** (curentă, dec 2024 → prezent).

❌ **Voturi NU acoperite în repo**: legislaturile 2020, 2016, 2012, 2008 etc.

### Motivare

- GitHub recomandă <1 GB per repo
- Bootstrap voturi pentru toate legislaturile = **~1.5 GB** (3 legislaturi × ~500 MB)
- Repo-ul devine greu de clonat, lent în UI, pune presiune pe GitHub Pages bandwidth
- Pentru un POC de internship, perioada curentă e suficientă pentru toate cazurile de utilizare jurnalistic

---

## Plan de migrare la infrastructura Camerei Deputaților

Când proiectul e adoptat și migrat pe servere proprii ale Camerei (Faza 6 din TIMELINE.md
sau ulterior), se schimbă constrângerile fundamental:

| Constrângere | GitHub Pages (acum) | Server CDEP (viitor) |
|---|---|---|
| Storage | <1 GB recomandat | TB-uri disponibile |
| Bandwidth | quota lunară | nelimitat intern |
| Rate limit cdep.ro | 1 req/sec | 0ms (acces direct DB Oracle) |
| Procesare istorică | infeasibilă | trivială |

### Acțiuni la migrare

1. **Bootstrap istoric complet** pentru toate legislaturile începând cu 1990:
   ```bash
   python scripts/run_voturi.py --from 1990-01-01 --to 2024-12-12 --leg 1990
   python scripts/run_voturi.py --from 1992-12-21 --to 1996-11-21 --leg 1992
   # ... etc pentru fiecare legislatură
   ```
   Rezultat estimat: **~5-8 GB** date istorice complete (8 legislaturi × ~600 MB).

2. **Acces direct la DB Oracle** — eliminăm scraping HTML. Schemele Pydantic
   se mapează direct la tabelele Oracle (`evot_voturi`, `evot_voturi_dep`, etc).
   Performanță: >1000× mai rapidă, 0% risc de schimbare HTML.

3. **Storage backend** — opțiuni:
   - **A)** Continuăm cu fișiere JSON statice (CDN intern Cameră → blazing fast)
   - **B)** API live cu Postgres + cache Redis (filtre arbitrare, full-text search,
     agregări on-demand) — vezi planul de arhitectură Opțiunea C

4. **Date noi expuse** care nu au sens pentru POC:
   - Voturi din comisii (nu doar plen)
   - Voturi anulate/reluate cu istoric
   - Versiuni anterioare ale proiectelor (workflow editare)
   - Raporturi interne

### Compatibilitate API contract

⚠️ **Foarte important**: schimbarea backend-ului trebuie să fie **transparentă** pentru
consumatorii API. URL-urile publice rămân aceleași, schema JSON nu se schimbă.

Asta înseamnă:
- Toate aplicațiile civice construite pe v1 continuă să funcționeze
- Doar performanța și prospețimea datelor se îmbunătățesc
- Datele istorice devin disponibile la URL-uri previzibile (`legislatura-1996.json`, etc.)

---

## Decizii rejectate

❌ **Stocare voturi în Git LFS** — soluționează limita de 100 MB / fișier dar nu rezolvă
problema de UX (clonare lentă) și introduce dependență externă.

❌ **Bază de date Postgres pe POC** — overhead operațional, cost recurent, anulează
beneficiul „static = 0 cost" al Opțiunii A din plan.

❌ **Comprimare automată în .tar.gz lunar** — adaugă complexitate de procesare client-side
(decompresie pe mobile/browser), incompatibil cu CDN cache.

---

*Versiune: 1.0 · Ultima actualizare: 2026-04-28*
