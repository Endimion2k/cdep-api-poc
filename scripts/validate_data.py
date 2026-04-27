"""Validator post-scrape. Exit 0 = OK, exit 1 = blocker.

Auto-descopera toate fisierele legislatura-*.json si valideaza fiecare.
Un singur fisier eronat ridica exit 1.

Check-uri (per fisier):
1. JSON valid
2. meta.count == len(data)
3. Nr. deputati in interval asteptat (300-340)
4. Coverage minim pe campuri critice
5. Fara duplicate de canonical_id
6. Partide in setul cunoscut
7. Unicitate persoana pe (family, given, birth)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# Force UTF-8 stdout pe Windows (console default = cp1252, sparge la diacritice)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "v1" / "deputati"

# Range larg ca să acoperim variații istorice.
# Camera curentă ~329-335, legislaturile cu mandate complete ajung la ~360+
# (incluse înlocuitori care preiau de la cei plecați mid-term).
EXPECTED_COUNT_MIN = 280
EXPECTED_COUNT_MAX = 400

# Partide cunoscute pe diverse legislaturi. Mai laxe pentru istoric.
KNOWN_PARTY_PREFIXES = {
    # Curent (2024)
    "Partidul Social Democrat",
    "Partidul Naţional Liberal",
    "Alianţa pentru Unirea Românilor",
    "Uniunea Salvaţi România",
    "Uniunea Democrată Maghiară",
    "Partidul S.O.S. România",
    "Partidul Oamenilor Tineri",
    "Fără adeziune",
    # Istoric (2020, 2016, 2012) — variante cu prefix scurt + nume complet
    "PSD",
    "PNL",
    "USR",
    "USR PLUS",
    "AUR",
    "PMP",
    "ALDE",
    "UDMR",
    "PRO România",
    "Pro România",
    "Uniunea Democrat Maghiară",
    "Partidul Mişcarea Populară",
    "Partidul Mișcarea Populară",
    "Alianţa Liberalilor şi Democraţilor",
    "Partidul România Mare",
    "Partidul Conservator",
    "Forumul Democrat al Germanilor",
    "Partidul Democrat",
    "Partidul Democrat-Liberal",
    "Partidul Liberal Reformator",
    "PER",
    "Independent",
    "Neafiliat",
}

MIN_COVERAGE = {
    "name": 1.00,
    "cdep_idm": 1.00,
    "legislatura": 1.00,
    "profile_url": 1.00,
    "birth_date": 0.85,  # legislaturile vechi au date de naștere mai puțin complete
    "judet": 0.80,
    "circumscriptie": 0.80,
    "current_party": 0.80,
    "current_group": 0.90,
    "image": 0.85,  # poze pot lipsi pentru legislaturile vechi
    "comisii": 0.85,
}


def ok(msg):
    print(f"  \033[32mOK\033[0m  {msg}")


def warn(msg):
    print(f"  \033[33mWARN\033[0m  {msg}")


def fail(msg):
    print(f"  \033[31mFAIL\033[0m  {msg}")


def validate_file(path: Path) -> tuple[int, int]:
    """Returneaza (errors, warnings) pentru un singur fisier."""
    errors = 0
    warnings = 0

    print("\n" + "=" * 60)
    print(f"Validating: {path.name}")
    print("=" * 60)

    # 1. File loadable
    print("\n[1] JSON valid")
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"JSON invalid: {e}")
        return (1, 0)
    if "meta" not in d or "data" not in d:
        fail("lipseste meta sau data")
        return (1, 0)
    ok(f"fisier incarcat ({path.stat().st_size:,} bytes)")

    # 2. Meta consistency
    print("\n[2] Meta consistent")
    declared = d["meta"].get("count")
    actual = len(d["data"])
    if declared != actual:
        fail(f"meta.count={declared} != len(data)={actual}")
        errors += 1
    else:
        ok(f"meta.count = len(data) = {actual}")

    # 3. Count range
    print("\n[3] Nr. deputati in interval")
    n = len(d["data"])
    if n < EXPECTED_COUNT_MIN or n > EXPECTED_COUNT_MAX:
        fail(f"{n} deputati (interval {EXPECTED_COUNT_MIN}-{EXPECTED_COUNT_MAX})")
        errors += 1
    else:
        ok(f"{n} deputati")

    # 4. Coverage
    print("\n[4] Coverage campuri")
    data = d["data"]
    total = len(data)
    if total:
        for field, threshold in MIN_COVERAGE.items():
            filled = sum(1 for row in data if row.get(field) not in (None, "", [], 0))
            ratio = filled / total
            msg = f"{field}: {filled}/{total} = {ratio:.1%} (min {threshold:.0%})"
            if ratio >= threshold:
                ok(msg)
            else:
                fail(msg)
                errors += 1

    # 5. Duplicates
    print("\n[5] Fara duplicate canonical_id")
    ids = [row["id"] for row in data]
    dup = {i: c for i, c in Counter(ids).items() if c > 1}
    if dup:
        fail(f"{len(dup)} duplicate: {list(dup)[:5]}")
        errors += 1
    else:
        ok(f"{len(ids)} ID-uri unice")

    # 6. Known parties
    print("\n[6] Partide cunoscute")
    unknown = Counter()
    for row in data:
        party = row.get("current_party")
        if party and not any(party.startswith(p) for p in KNOWN_PARTY_PREFIXES):
            unknown[party] += 1
    if unknown:
        for p, c in unknown.most_common(5):
            warn(f"partid necunoscut ({c}x): {p!r}")
            warnings += 1
    else:
        ok("toate in setul cunoscut")

    # 7. Unique persons
    print("\n[7] Unicitate persoana")
    seen = Counter()
    for row in data:
        key = (row.get("family_name"), row.get("given_name"), row.get("birth_date"))
        seen[key] += 1
    dup = {k: c for k, c in seen.items() if c > 1 and all(k)}
    if dup:
        warn(f"{len(dup)} coliziuni: {list(dup)[:3]}")
        warnings += 1
    else:
        ok("toate persoanele unice")

    return (errors, warnings)


def main():
    print("=" * 60)
    print("CDEP API - Data Validation (multi-legislature)")
    print("=" * 60)

    if not DATA_DIR.exists():
        fail(f"director lipsa: {DATA_DIR}")
        return 1

    files = sorted(DATA_DIR.glob("legislatura-*.json"))
    if not files:
        fail(f"niciun fisier legislatura-*.json gasit in {DATA_DIR}")
        return 1

    print(f"\nGasite {len(files)} fisier(e): {[f.name for f in files]}")

    total_errors = 0
    total_warnings = 0
    for path in files:
        e, w = validate_file(path)
        total_errors += e
        total_warnings += w

    print("\n" + "=" * 60)
    print(f"SUMAR: {len(files)} fisier(e) verificate")
    if total_errors:
        print(f"\033[31mFAIL: {total_errors} errors, {total_warnings} warnings\033[0m")
        return 1
    elif total_warnings:
        print(f"\033[33mOK cu {total_warnings} warnings\033[0m")
        return 0
    else:
        print("\033[32mAll checks passed\033[0m")
        return 0


if __name__ == "__main__":
    sys.exit(main())
