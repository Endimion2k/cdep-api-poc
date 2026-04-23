# sitemap.md — Inventar URL-uri cdep.ro

Documentul sursă al scraperilor. Fiecare secțiune din API-ul nostru mapează pe una sau mai multe rute cdep.ro. Construit din crawl-ul din Ziua 2 (S1).

> **Legenda**: ✅ verificat din crawl · 🟡 pattern presupus, de confirmat · ❓ necunoscut, de investigat manual · ⚠️ particularitate importantă

---

## Arhitectura generală a cdep.ro

Site-ul este servit de **Oracle HTTP Server 12c** cu **PHP 7.1.7** ca gateway pe procedurile PL/SQL. Majoritatea URL-urilor sunt în formatul:

```
https://www.cdep.ro/pls/<schema>/<procedure>?param1=X&param2=Y
```

**Schema-uri observate**:
- `/pls/parlam/` — structura parlamentară, interpelări, moțiuni
- `/pls/steno/` — voturi electronice, stenograme
- `/pls/proiecte/` — proiecte legislative, documente comisii
- `/pls/legis/` — acte legislative adoptate
- `/pls/dic/` — conducere, declarații, contact (dicționar/meta)
- `/pls/caseta/` — agendă, ordine de zi
- `/pls/personal/` — resurse umane
- `/pls/parlam/sanctiuni_parlam.*` — sancțiuni (schema non-2015, dar tot pe `parlam`)

**Encoding HTTP**: `ISO-8859-2` (Latin-2). `requests` îl decodează automat din header; nu e nevoie să intervii manual. Diacriticele românești (ă â î ș ț) sunt corect reprezentate.

---

## Parametri recurenți

| Param | Valori | Semnificație |
|---|---|---|
| `cam` | `1`, `2`, `0` | 2 = Camera Deputaților · 1 = Senat · 0 = ambele |
| `leg` | `1990`, `1992`, `1996`, `2000`, `2004`, `2008`, `2012`, `2016`, `2020`, `2024` | Anul începutului legislaturii (8 legislaturi istorice + 2 curente) |
| `idl` | `1`, `2`, `3` | Limba: 1=RO, 2=EN, 3=FR (mereu `idl=1` la noi) |
| `idm` | integer | ID intern deputat — ⚠️ **NU e secvențial** (idm=1 → „Adomnicai Mirela Elena" în 2024, nu deputatul #1 cronologic) |
| `idg` | string (ex. `AUR`, `PNL`) sau int | ID grup parlamentar |
| `idp` | integer (ex. `40`) | ID formațiune politică (partid) |
| `idv` | integer (ex. `4699`) | ID eveniment de vot |
| `ida` | integer | ID act legislativ (HCD, lege) |
| `std` | string (`DZ` etc.) | Stadiu proiect legislativ — ❓ toate codurile de descoperit |
| `tpc` | integer | Tip comisie — ❓ de descoperit valorile |
| `par` | `A`–`Z` | Litera alfabetică (listări paginate) |
| `pag` | integer | Paginare generică |
| `poz` | integer | Poziție într-o listă (ex. membru Birou Permanent) |

---

## 1. Deputați (`/deputati`) — procedures `structura2015.*`

### Listare

✅ **Alfabetic, pe litere** — una din metodele stabile de enumerare exhaustivă:
```
https://www.cdep.ro/pls/parlam/structura2015.ab?cam=2&leg=2024&idl=1&par=A
... pentru par=A până la par=Z (26 pagini)
```

✅ **După formațiune politică**:
```
https://www.cdep.ro/pls/parlam/structura2015.fp?leg=2024
→ listează partidele cu link-uri la .fp?idp=X&cam=2&leg=2024&idl=1 pentru fiecare
```

✅ **După circumscripție electorală (județ)**:
```
https://www.cdep.ro/pls/parlam/structura2015.ce?cam=2&leg=2024&idl=1
```

✅ **Homepage legislatură** (arhivă până în 1990):
```
https://www.cdep.ro/pls/parlam/structura2015.home?leg=2024&idl=1
```

🟡 **Ordine alfabetică globală** (fallback):
```
https://www.cdep.ro/pls/parlam/structura2015.de?idl=1
```

### Profil individual

✅ **Profil deputat**:
```
https://www.cdep.ro/pls/parlam/structura2015.mp?idm=1&cam=2&leg=2024
→ Titlu pagină conține numele: "Adomnicai Mirela Elena"
→ 29KB HTML cu bio, comisii, activitate parlamentară linked
```

### Strategia de scraping

**Recomandată**: iterează prin `par=A..Z` pe ruta `.ab`, extrage `idm` din fiecare link, apoi scrape profilele prin `.mp`. Verificare cross-cu `.fp` (după partid) ca să nu pierdem cazuri (ex: independenți).

---

## 2. Voturi (`/voturi`) — procedures `evot2015.*`

### Listare / intrare

✅ **Home voturi electronice**:
```
https://www.cdep.ro/pls/steno/evot2015.data?idl=1
```

✅ **Istoric voturi per deputat** (paginat):
```
https://www.cdep.ro/pls/steno/evot2015.mp?idm=1&cam=2&leg=2024&pag=1&idl=1
```

❓ **Listă sesiuni / indexul tuturor voturilor per legislatură** — de descoperit. Probabil o procedură `.lista` sau similar. Poate fi construită reverse din istoricul individual al câtorva deputați.

### Observații

⚠️ **idv ajunge deja la 4699 în legislatura 2024** — dimensiune mare a dataset-ului, paginarea e critică.

⚠️ Ruta `.mp` dă voturile unui deputat (perspectiva persoană). Pentru voturi nominale per ședință (perspectiva eveniment), avem nevoie de procedura complementară — probabil `evot2015.data?idv=X` sau similar. De confirmat.

### Stenograme legate (`steno2015.*`, `steno2024.*`)

✅ **Home stenograme**:
```
https://www.cdep.ro/pls/steno/steno2015.home
```

✅ **Listă luări de cuvânt per eveniment**:
```
https://www.cdep.ro/pls/steno/steno2015.lista?idv=4699&leg=2024&idl=1
https://www.cdep.ro/pls/steno/steno2024.lista?idv=4699&leg=2024&idl=1  ⚠️ procedura nouă pt 2024
```

✅ **Înregistrări audio/video**:
```
https://www.cdep.ro/pls/steno/steno2015.video?sursa=1
```

---

## 3. Proiecte legislative (`/proiecte-lege`) — procedures `upl_pck2015.*`, `legis_pck.*`

### Listare

✅ **Home proces legislativ**:
```
https://www.cdep.ro/pls/proiecte/upl_pck2015.home
```

✅ **Listă pe stadiu**:
```
https://www.cdep.ro/pls/proiecte/upl_pck2015.lista?std=DZ
→ std=DZ = dezbatere
❓ Celelalte coduri de stadiu de descoperit: probabil IN=inițiat, CO=comisie, AD=adoptat, RE=respins, RT=retras
```

✅ **Documente comisii** (rapoarte, avize):
```
https://www.cdep.ro/pls/proiecte/upl_com2015.home
```

✅ **Act individual** (cu ID):
```
https://www.cdep.ro/pls/legis/legis_pck.htp_act?ida=210366
→ ex: "HCD nr.109/2024"
```

❓ **Amendamente** — de descoperit. Posibil `upl_pck2015.amendamente?ida=X` sau integrate în pagina detaliu a proiectului.

---

## 4. Comisii (`/comisii`) — procedure `structura2015.co`

✅ **Listă comisii**:
```
https://www.cdep.ro/pls/parlam/structura2015.co?cam=2&leg=2024
→ ❓ filtrabil prin tpc (tip comisie): permanentă / specială / comună
```

❓ **Detaliu comisie** — de investigat structura URL. Probabil `.co?idc=X&cam=2&leg=YYYY` sau similar.

❓ **Activitate comisie** (ședințe, rapoarte) — probabil `/co/sedinte2015.comisii?care=X` (observat în crawl).

### Subsecțiuni structură parlamentară înrudite

✅ **Președintele Camerei**:
```
https://www.cdep.ro/pls/parlam/structura2015.ch?idl=1
```

✅ **Biroul Permanent**:
```
https://www.cdep.ro/pls/parlam/structura2015.bp?idl=1&poz=1
```

✅ **Comitetul liderilor de grup**:
```
https://www.cdep.ro/pls/parlam/structura2015.cl?idl=1
```

✅ **Delegații parlamentare**:
```
https://www.cdep.ro/pls/parlam/structura2015.dp
```

✅ **Grupurile de prietenie** (cu alte parlamente):
```
https://www.cdep.ro/pls/parlam/structura2015.pr
```

---

## 5. Grupuri parlamentare (`/grupuri-parlamentare`) — `structura2015.gp`

✅ **Listă grupuri**:
```
https://www.cdep.ro/pls/parlam/structura2015.gp?idl=1
→ link-uri spre fiecare grup (AUR, PNL, PSD, UDMR, USR, MINO, NEAFIL)
```

✅ **Detaliu grup**:
```
https://www.cdep.ro/pls/parlam/structura2015.gp?idg=AUR&idl=1
```

---

## 6. Interpelări și întrebări (`/interpelari`) — `interpelari2015.*`

✅ **Home**:
```
https://www.cdep.ro/pls/parlam/interpelari2015.home
```

❓ **Listare** și **detaliu** — de investigat. Probabil `.lista?cam=2&leg=2024` și o procedură pentru item individual.

---

## 7. Moțiuni (`/motiuni`) — `motiuni2015.*`

✅ **Home**:
```
https://www.cdep.ro/pls/parlam/motiuni2015.home
```

✅ **Listă moțiuni**:
```
https://www.cdep.ro/pls/parlam/motiuni2015.lista?cam=0
→ cam=0 = ambele camere (moțiunile sunt comune)
→ ⚠️ „Moţiuni simple şi de cenzură" sunt pe aceeași listă; diferențierea se face din conținut
```

---

## 8. Agendă și Ordinea de zi — `eCaseta2015.*`

✅ **Program de lucru / agendă**:
```
https://www.cdep.ro/pls/caseta/eCaseta2015.Agenda
```

✅ **Ordine de zi**:
```
https://www.cdep.ro/pls/caseta/eCaseta2015.OrdineZi
```

✅ **Note și informări**:
```
https://www.cdep.ro/pls/caseta/eCaseta2015.Informari
```

---

## 9. Sancțiuni deputați (`/sanctiuni`) — `sanctiuni_parlam.*`

✅ **Listă sancționați**:
```
https://www.cdep.ro/pls/parlam/sanctiuni_parlam.lista_sanctionati?leg=2024&cam=2
```

**Status**: în scope, Faza 5. Endpoint `/sanctiuni`. Câmpuri așteptate: `deputat_id`, `data`, `tip_sanctiune`, `motivatie`, `sursa` (probabil link către decizia BP sau votul plenului).

---

## 10. Declarații de avere și interese — `declaratii2015.*`

✅ **Home**:
```
https://www.cdep.ro/pls/dic/declaratii2015.home?idl=1
```

⚠️ Probabil redirect către portalul ANI (Agenția Națională de Integritate). De confirmat dacă sunt date locale pe cdep.ro sau doar link-uri către ani.md. Dacă doar link-uri, **rămâne explicit out of scope** (per decizia din plan).

---

## 11. Urmăriri adiționale

- `/pls/parlam/relatii_externe2015.adunari` — adunări internaționale (AP NATO, CoE etc.)
- `/pls/parlam/relatii_externe2015.bilaterale` — cooperare bilaterală
- `/pls/parlam/informatii_economice2015.home` — informații economice (achiziții?)
- `/pls/dic/legis_acte_parlam2015` — acte adoptate (complementar cu `legis_pck.htp_act`)
- `/co/sedinte2015.comisii` — ședințe comisii (schema diferită!)

---

## 12. Open questions — de verificat manual

Lista pentru sesiunea ta de explorare de 15 minute:

- [ ] Cum se listează **toate voturile** pentru o legislatură (nu doar voturile unui deputat)?
- [ ] Ce coduri există pentru parametrul `std` (stadiu proiect)? De găsit pe pagina `upl_pck2015.home` un dropdown sau link-uri.
- [ ] Ce valori poate lua `tpc` (tip comisie)?
- [ ] Există URL pentru **amendamentele** unui proiect? În caz afirmativ, cum arată.
- [ ] `steno2024.lista` vs `steno2015.lista` — care e diferența? Pare că 2024 are propria procedură pentru legislatura curentă.
- [ ] Cum arată `interpelari2015` — listă, detalii, filtre?
- [ ] Declarații de avere și interese — link-uri locale sau redirect ANI?
- [ ] Există `idm` duplicate între legislaturi? (Deputatul X din 2020 și deputatul Y din 2024 pot avea ambii idm=1?) — **presupunere da**, deci nu e unic global, doar în context `(leg, idm)`.

---

## 13. Strategie de canonical ID

Având în vedere că **`idm` nu e stabil între legislaturi**, pentru `canonical_id` al deputatului propun:

```python
canonical_id = hash(
    normalize(nume_complet)  # diacritice normalizate
    + "|" + data_nastere_iso  # dacă e disponibilă
)[:16]
```

Fallback dacă data nașterii lipsește: `hash(normalize(nume_complet))` — cu warning explicit în cazul deputaților cu nume identice (rar, dar posibil).

Păstrăm `cdep_idm` ca câmp separat pe record, pentru fiecare legislatură, pentru a putea reveni la sursă.

---

*Ultima actualizare: 2026-04-23 (Ziua 2) · compilat din crawl automat + verificare manuală parțială*
