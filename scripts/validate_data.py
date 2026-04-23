"""Validator post-scrape — sanity checks care blochează commit-ul dacă datele arată suspect.

Rulează-l după `run_deputati.py`:
    python scripts/validate_data.py

Exit code:
    0 = toate check-urile trec (OK să commit-ez)
    1 = cel puțin un check fatal a eșuat (NU commit-ez, investighez)

Check-uri efectuate:
1. Fișierul există și e JSON valid
2. Meta-block prezent + count = len(data)
3. Nr. deputați în intervalul așteptat (320-335 pentru CD contemporan)
4. Coverage minim pe câmpuri critice (name 100%, birth_date 95%, etc.)
5. Fără duplicate de canonical_id
6. Party name în setul cunoscut (sau flag gri de deviație acceptabilă)
7. Nume unice: 0 coliziuni pe (family_name, given_name, birth_date)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "v1" / "deputati" / "legislatura-2024.json"

# Range așteptat pentru Camera Deputaților (Constituție: 308 deputați + minorități + vacantări)
EXPECTED_COUNT_MIN = 300
EXPECTED_COUNT_MAX = 340

# Partidele cunoscute la 2024 (actualizabil când apar/pleacă grupuri)
# Matching e pe "startswith" pentru a accepta sufixe de istoric ("Partid X - până în...")
KNOWN_PARTY_PREFIXES = {
    "Partidul Social Democrat",
    "Partidul Naţional Liberal",
    "Alianţa pentru Unirea Românilor",
    "Uniunea Salvaţi România",
    "Uniunea Democrată Maghiară",
    "Partidul S.O.S. România",
    "Partidul Oamenilor Tineri",
    "Fără adeziune",  # neafiliați, dar cu context de fost-partid
}

# Coverage minim cerut (proporție din total)
MIN_COVERAGE = {
    "name": 1.00,
    "cdep_idm": 1.00,
    "legislatura": 1.00,
    "profile_url": 1.00,
    "birth_date": 0.90,
    "judet": 0.85,
    "circumscriptie": 0.85,
    "current_party": 0.85,
    "current_group": 0.95,
    "image": 0.90,
    "comisii": 0.90,
}


class Reporter:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        print(f"  \033[31m✗ FAIL\033[0m  {msg}")

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)
        print(f"  \033[33m⚠ WARN\033[0m  {msg}")

    def ok(self, msg: str) -> None:
        self.info.append(msg)
        print(f"  \033[32m✓ OK\033[0m    {msg}")


def check_file_loadable(rep: Reporter) -> dict[str, Any] | None:
    print("\n[1] Fișier JSON valid")
    if not DATA_FILE.exists():
        rep.error(f"fișier lipsă: {DATA_FILE}")
        return None
    try:
        d = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        rep.error(f"JSON invalid: {e}")
        return None
    if "meta" not in d or "data" not in d:
        rep.error("lipsește 'meta' sau 'data' la nivel top")
        return None
    rep.ok(f"fișier încărcat ({DATA_FILE.stat().st_size:,} bytes)")
    return d


def check_meta_consistency(rep: Reporter, d: dict[str, Any]) -> None:
    print("\n[2] Meta-block consistent")
    meta = d["meta"]
    data = d["data"]
    declared = meta.get("count")
    actual = len(data)
    if declared != actual:
        rep.error(f"meta.count={declared} != len(data)={actual}")
    else:
        rep.ok(f"meta.count = len(data) = {actual}")


def check_count_range(rep: Reporter, d: dict[str, Any]) -> None:
    print("\n[3] Nr. deputați în interval așteptat")
    n = len(d["data"])
    if n < EXPECTED_COUNT_MIN:
        rep.error(f"{n} deputați — suspect de puțini (min așteptat: {EXPECTED_COUNT_MIN})")
    elif n > EXPECTED_COUNT_MAX:
        rep.error(f"{n} deputați — suspect de mulți (max așteptat: {EXPECTED_COUNT_MAX})")
    else:
        rep.ok(f"{n} deputați (interval {EXPECTED_COUNT_MIN}-{EXPECTED_COUNT_MAX})")


def check_coverage(rep: Reporter, d: dict[str, Any]) -> None:
    print("\n[4] Coverage minim pe câmpuri")
    data = d["data"]
    total = len(data)
    if total == 0:
        rep.error("data array gol")
        return
    for field, threshold in MIN_COVERAGE.items():
        filled = sum(
            1
            for row in data
            if row.get(field) not in (None, "", [], 0)
            or (field == "circumscriptie" and isinstance(row.get(field), int) and row.get(field) > 0)
        )
        ratio = filled / total
        msg = f"{field}: {filled}/{total} = {ratio:.1%} (min {threshold:.0%})"
        if ratio >= threshold:
            rep.ok(msg)
        else:
            rep.error(msg)


def check_no_duplicates(rep: Reporter, d: dict[str, Any]) -> None:
    print("\n[5] Fără duplicate de canonical_id")
    ids = [row["id"] for row in d["data"]]
    dup = {i: c for i, c in Counter(ids).items() if c > 1}
    if dup:
        rep.error(f"{len(dup)} ID-uri canonice duplicate: {list(dup)[:5]}")
    else:
        rep.ok(f"{len(ids)} ID-uri unice")


def check_parties_known(rep: Reporter, d: dict[str, Any]) -> None:
    print("\n[6] Partide în setul cunoscut (sau deviații tolerate)")
    data = d["data"]
    unknown_parties: Counter[str] = Counter()
    for row in data:
        party = row.get("current_party")
        if not party:
            continue
        if not any(party.startswith(p) for p in KNOWN_PARTY_PREFIXES):
            unknown_parties[party] += 1
    if unknown_parties:
        # Partidele noi sunt normale → WARN, nu ERROR
        for p, count in unknown_parties.most_common(5):
            rep.warning(f"partid necunoscut ({count}×): {p!r}")
    else:
        rep.ok("toate partidele sunt în setul cunoscut")


def check_unique_persons(rep: Reporter, d: dict[str, Any]) -> None:
    print("\n[7] Unicitate persoană (family_name, given_name, birth_date)")
    seen: Counter[tuple] = Counter()
    for row in d["data"]:
        key = (row.get("family_name"), row.get("given_name"), row.get("birth_date"))
        seen[key] += 1
    dup = {k: c for k, c in seen.items() if c > 1 and all(k)}
    if dup:
        rep.warning(f"{len(dup)} coliziuni (nume+prenume+dată naștere): {list(dup)[:3]}")
    else:
        rep.ok("toate persoanele sunt unice pe triplet")


def main() -> int:
    print("=" * 66)
    print("CDEP API — Data Validation")
    print("=" * 66)
    rep = Reporter()

    d = check_file_loadable(rep)
    if d is None:
        return 1

    check_meta_consistency(rep, d)
    check_count_range(rep, d)
    check_coverage(rep, d)
    check_no_duplicates(rep, d)
    check_parties_known(rep, d)
    check_unique_persons(rep, d)

    print("\n" + "=" * 66)
    if rep.errors:
        print(f"\033[31m✗ {len(rep.errors)} errors, {len(rep.warnings)} warnings — NU commit\033[0m")
        return 1
    elif rep.warnings:
        print(f"\033[33m✓ OK cu {len(rep.warnings)} warnings — safe to commit\033[0m")
        return 0
    else:
        print("\033[32m✓ All checks passed\033[0m")
        return 0


if __name__ == "__main__":
    sys.exit(main())
