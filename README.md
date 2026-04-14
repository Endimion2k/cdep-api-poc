# Camera Deputaților — API Deschis · Proof of Concept

> **Propunere de inițiativă administrativă** pentru transparentizarea și digitalizarea accesului la datele publice ale Camerei Deputaților din România.

**Demo live:** https://[username].github.io/cdep-api-poc  
**Swagger UI:** https://[username].github.io/cdep-api-poc/docs/swagger.html  
**OpenAPI spec:** [api/openapi.yaml](api/openapi.yaml)

---

## Despre acest proiect

Datele activității parlamentare din România sunt **deja publice** pe [cdep.ro](https://cdep.ro), dar accesibile doar în format HTML — imposibil de procesat automat de jurnaliști, ONG-uri, cercetători sau cetățeni.

Acest proof of concept demonstrează cum ar arăta un **API REST deschis** care expune aceleași date în format JSON structurat, fără autentificare, gratuit pentru oricine.

### Problema

- Voturi, prezențe și proiecte de lege există pe cdep.ro dar nu sunt machine-readable
- Jurnaliștii copiază manual tabele HTML pentru a face analize
- ONG-urile nu pot monitoriza automat activitatea parlamentară
- Cetățenii nu au acces real la date, chiar dacă ele sunt tehnic publice

### Soluția propusă

Un API REST care expune datele existente într-un format standardizat:

```
GET /api/v1/deputati?partid=USR&judet=Cluj
GET /api/v1/voturi?keyword=inteligenta+artificiala&adoptat=true
GET /api/v1/deputati/87/prezenta?an=2025
GET /api/v1/proiecte-lege?stadiu=dezbatere&comisie=informatii-comunicatii
```

---

## Endpoint-uri

| Endpoint | Descriere |
|----------|-----------|
| `GET /deputati` | Listă deputați cu filtrare după partid, județ, legislatură |
| `GET /deputati/{id}` | Profil complet al unui deputat |
| `GET /deputati/{id}/prezenta` | Statistici de prezență la ședințe |
| `GET /voturi` | Voturi în plen cu rezultate agregate |
| `GET /voturi/{id}` | Vot individual per deputat |
| `GET /proiecte-lege` | Proiecte legislative cu stadiu curent |
| `GET /comisii` | Lista comisiilor parlamentare |
| `GET /comisii/{slug}/activitate` | Activitatea unei comisii |

---

## Structura proiectului

```
cdep-api-poc/
├── index.html          # Demo interactiv + documentație
├── docs/
│   └── swagger.html    # Swagger UI
├── api/
│   └── openapi.yaml    # Specificație OpenAPI 3.0
└── README.md
```

---

## Cum deploy-ezi pe GitHub Pages

1. Fork sau clonează acest repo
2. Mergi la **Settings → Pages**
3. Source: `Deploy from a branch` → `main` → `/ (root)`
4. Salvează. Site-ul va fi live în ~2 minute.

---

## Impactul potențial

- **Jurnaliști** — pot construi instrumente de monitorizare a deputaților din circumscripțiile lor
- **ONG-uri** — pot alerta automat când un proiect de lege relevant intră în dezbatere
- **Cetățeni** — pot verifica prezența și voturile reprezentanților lor
- **Developeri** — pot construi aplicații civice pe baza datelor parlamentare

---

## Context

Propunere elaborată în cadrul candidaturii pentru **Programul de Internship la Camera Deputaților, Ediția I/2026**, Comisia pentru Tehnologia Informației și Comunicațiilor.

**Autor:** Cătălin Popa  
**Referință:** [bikestylish.ro](https://bikestylish.ro) — proiect similar de API deschis pentru industria de ciclism din România

---

## Licență

Open Government License v3.0 — date publice, utilizare liberă.
