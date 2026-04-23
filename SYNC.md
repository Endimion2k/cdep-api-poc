# Sincronizare cu GitHub — pași pentru Windows

Folder-ul conține acum toate fișierele din repo-ul public plus adăugirile noi:

```
api-cdep/
├── .git/                                 # PARȚIAL — trebuie șters, vezi pasul 1
├── api/openapi.yaml                      # din repo (nemodificat)
├── docs/swagger.html                     # din repo (nemodificat)
├── index.html                            # din repo (nemodificat)
├── README.md                             # NOU — înlocuiește vechiul README minimal
├── TIMELINE.md                           # NOU — planul de 24 săptămâni
├── CDEP_API_Plan_Implementare.docx       # NOU — planul detaliat (17 pagini)
└── SYNC.md                               # NOU — acest fișier
```

## Pasul 1 — șterge `.git` parțial (o singură dată)

Există un folder `.git` incomplet rămas de la un clone eșuat pe un file system cu permisiuni restrictive. Trebuie șters din Windows (care nu are problema asta).

**În PowerShell:**
```powershell
cd C:\Users\Maia\Downloads\python\altele\api-cdep
Remove-Item -Recurse -Force .git
```

Sau prin File Explorer: activează afișarea fișierelor ascunse, șterge folder-ul `.git`.

## Pasul 2 — inițializează git curat și leagă la GitHub

```powershell
cd C:\Users\Maia\Downloads\python\altele\api-cdep

git init
git branch -M main
git remote add origin https://github.com/Endimion2k/cdep-api-poc.git
git fetch origin
git reset --soft origin/main    # aduce istoricul remote, păstrează fișierele locale
```

Acum ai: istoricul complet de pe GitHub + fișierele locale gata să fie comit-ate ca modificări noi.

## Pasul 3 — verifică ce vede git

```powershell
git status
```

Ar trebui să vezi:
- `modified: README.md` (l-ai înlocuit cu versiunea nouă)
- `new file: TIMELINE.md`
- `new file: CDEP_API_Plan_Implementare.docx`
- `new file: SYNC.md` (opțional — poți să-l pui în `.gitignore` dacă nu vrei să fie în repo)

## Pasul 4 — commit și push

### Varianta A — direct pe main (simplu)

```powershell
git add README.md TIMELINE.md CDEP_API_Plan_Implementare.docx
git commit -m "docs: add 24-week implementation roadmap and refresh README"
git push origin main
```

### Varianta B — branch dedicat + Pull Request (recomandat, istoric mai curat)

```powershell
git checkout -b docs/roadmap
git add README.md TIMELINE.md CDEP_API_Plan_Implementare.docx
git commit -m "docs: add 24-week implementation roadmap and refresh README"
git push -u origin docs/roadmap
```

Apoi deschide un PR pe GitHub din interfață, revezi, și merge-uiește.

## Opțional — exclude `.docx` și `SYNC.md` din repo

Dacă preferi ca documentul Word să nu fie versionat (rămâne doar local ca referință) și SYNC.md să nu apară public, creează `.gitignore`:

```powershell
@"
*.docx
SYNC.md
.vscode/
.venv/
__pycache__/
*.pyc
"@ | Out-File -Encoding utf8 .gitignore

git add .gitignore
```

## După primul push

- Verifică pe https://github.com/Endimion2k/cdep-api-poc că README-ul nou și TIMELINE-ul apar corect.
- GitHub redă `- [ ]` din TIMELINE.md ca checkbox-uri interactive — bifabile direct din browser (doar pentru owner).
- Următoarele modificări se fac direct din folder-ul local, cu ciclul normal: `git add` / `commit` / `push`.

---

*Dacă vreun pas eșuează, spune-mi eroarea exactă și te ajut să o rezolvi.*
