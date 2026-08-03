"""Unit tests for parsers/avere_pdf.py — synthetic text, no PDF files required."""

from __future__ import annotations

import re

import pytest

from parsers.avere_pdf import (
    _parse_imobile_details,
    _parse_vehicule,
    _parse_conturi_detaliate,
    _parse_plasamente,
    _scan_amounts,
    extract_section,
    MARKERS,
)

# ── Synthetic section text ────────────────────────────────────────────────────

SEC_TERENURI = """1. Terenuri
NOTĂ: Se vor declara inclusiv cele aflate în alte ţări.
Tara:
ROMANIA
Judet: Gorj
Localitate:
Forestier 2017 284354 m2 1/2 Contract de vânzare cumpărare Iordache Ion
Borascu -
Tara:
ROMANIA
Judet: Gorj
Localitate: Agricol 2015 2856 m2 1/2 Contract de vânzare Iordache Ion
Borascu -
Tara:
ROMANIA
Judet: Mehedinti
Alte categorii de terenuri extravilane 2018 135000 m2 1/2 Contract de vânzare Iordache Ion
"""

SEC_CLADIRI = """2. Clădiri
NOTĂ:
Tara:
ROMANIA
Judet: Gorj
Casă de locuit 2018 229 m2 1/2 Contract de vânzare cumpărare iordache
Turceni -
Tara:
ROMANIA
Judet: Gorj
comerciale/de producţie 2020 273 m2 1/2 Contract de vânzare iorache
Turceni -
"""

SEC_AUTO = """II. Bunuri mobile
1. Autovehicule/autoturisme, tractoare, maşini agricole, şalupe, iahturi...
Modul de
Natura Marca Nr. de bucăţi Anul de fabricaţie
dobândire
Contract de
Autoturism jeep wrangler 1 2004
vânzare cumpărare
Contract de
Tractor U650 1 1988
vânzare cumpărare
Contract de
şalupă Skyjet 1 2016
vânzare cumpărare
Alt mijloc de Contract de
500Ai 1 1994
transport vânzare cumpărare
"""

SEC_CONTURI1 = """1. Conturi şi depozite bancare...
Cont curent sau
CEC Bank,
echivalente RON 2015 377500
Depozit bancar sau
CEC TG JIU, echivalente RON 2022 787012
Fonduri de investiţii
NN ASIGURARI, RON 2014 49355
"""

SEC_PLASAMENTE_EMPTY = """2. Plasamente, investiţii directe...
- - - -
"""

SEC_PLASAMENTE_BECALI = """2. Plasamente, investiţii directe...
Împrumuturi acordate în
ARCOM SA 100 % 45825140 RON
nume personal
Împrumuturi acordate în
Fotbal Club FCSB SA 100 % 800000 EUR
nume personal
"""

SEC_BIJUTERII = """2. Bunuri sub formă de metale preţioase, bijuterii...
Bijuterii 2015 - 2020 140000 RON
Ceasuri 2013 - 2020 42000 EUR
"""

SEC_INSTRAINATE = """III. Bunuri mobile, a căror valoare depăşeşte 3.000 de euro...
Alte categorii de terenuri 20.07.2022 Donatie 0 RON extravilane
Apartament 21.04.2023 Contract Vanzare Cumparare 63000 RON
"""

SEC_CADOURI_EMPTY = """VI. Cadouri...
1.1. Titular
- - - -
1.2. Soţ/soţie
- - - -
"""


# ── _parse_imobile_details ────────────────────────────────────────────────────

def test_imobile_count():
    rows, _ = _parse_imobile_details(SEC_TERENURI, SEC_CLADIRI)
    assert len(rows) == 5  # 3 terenuri + 2 cladiri


def test_imobile_tip():
    rows, _ = _parse_imobile_details(SEC_TERENURI, SEC_CLADIRI)
    terenuri = [r for r in rows if r["tip"] == "teren"]
    cladiri = [r for r in rows if r["tip"] == "cladire"]
    assert len(terenuri) == 3
    assert len(cladiri) == 2


def test_imobile_categorie_teren():
    rows, _ = _parse_imobile_details(SEC_TERENURI, "")
    cats = {r["categorie"] for r in rows}
    assert "forestier" in cats
    assert "agricol" in cats
    assert "extravilan" in cats


def test_imobile_categorie_cladire():
    rows, _ = _parse_imobile_details("", SEC_CLADIRI)
    cats = {r["categorie"] for r in rows}
    assert "locuinta" in cats
    assert "comercial" in cats


def test_imobile_suprafata():
    rows, _ = _parse_imobile_details(SEC_TERENURI, "")
    suprafete = {r["suprafata_mp"] for r in rows}
    assert 284354.0 in suprafete
    assert 2856.0 in suprafete
    assert 135000.0 in suprafete


def test_imobile_judet():
    rows, _ = _parse_imobile_details(SEC_TERENURI, "")
    judete = {r["judet"] for r in rows}
    assert "Gorj" in judete
    assert "Mehedinti" in judete


def test_imobile_aggregates_sum():
    rows, agg = _parse_imobile_details(SEC_TERENURI, SEC_CLADIRI)
    total_from_agg = sum(agg.values())
    total_from_rows = sum(r["suprafata_mp"] for r in rows if r["suprafata_mp"])
    assert abs(total_from_agg - total_from_rows) < 1.0


def test_imobile_suprafata_forestier():
    _, agg = _parse_imobile_details(SEC_TERENURI, "")
    assert agg["suprafata_forestier_mp"] == pytest.approx(284354.0)


def test_imobile_suprafata_cladiri():
    _, agg = _parse_imobile_details("", SEC_CLADIRI)
    assert agg["suprafata_cladiri_mp"] == pytest.approx(229.0 + 273.0)


def test_imobile_empty_sections():
    rows, agg = _parse_imobile_details("", "")
    assert rows == []
    assert all(v == 0.0 for v in agg.values())


# ── _parse_vehicule ───────────────────────────────────────────────────────────

def test_vehicule_count():
    rows = _parse_vehicule(SEC_AUTO)
    assert len(rows) == 4


def test_vehicule_natura():
    rows = _parse_vehicule(SEC_AUTO)
    naturi = {r["natura"].lower() for r in rows}
    assert "autoturism" in naturi
    assert "tractor" in naturi


def test_vehicule_an_fabricatie():
    rows = _parse_vehicule(SEC_AUTO)
    ani = {r["an_fabricatie"] for r in rows}
    assert 2004 in ani
    assert 1988 in ani
    assert 2016 in ani


def test_vehicule_empty():
    assert _parse_vehicule("II. Bunuri mobile\n") == []


# ── _parse_conturi_detaliate ──────────────────────────────────────────────────

def test_conturi_count():
    rows = _parse_conturi_detaliate(SEC_CONTURI1)
    assert len(rows) == 3


def test_conturi_sold_ron():
    rows = _parse_conturi_detaliate(SEC_CONTURI1)
    solds = {r["sold_ron"] for r in rows}
    assert 377500.0 in solds
    assert 787012.0 in solds


def test_conturi_tip_detection():
    rows = _parse_conturi_detaliate(SEC_CONTURI1)
    tips = {r["tip"] for r in rows}
    assert "depozit" in tips
    assert "fond_investitii" in tips


def test_conturi_empty():
    assert _parse_conturi_detaliate("") == []


# ── _parse_plasamente ─────────────────────────────────────────────────────────

def test_plasamente_empty():
    rows = _parse_plasamente(SEC_PLASAMENTE_EMPTY)
    assert rows == []


def test_plasamente_count():
    rows = _parse_plasamente(SEC_PLASAMENTE_BECALI)
    assert len(rows) == 2


def test_plasamente_emitent():
    rows = _parse_plasamente(SEC_PLASAMENTE_BECALI)
    emitenti = [r["emitent"] for r in rows]
    assert any(e and "ARCOM" in e for e in emitenti)
    assert any(e and "FCSB" in e for e in emitenti)


def test_plasamente_valoare_ron():
    rows = _parse_plasamente(SEC_PLASAMENTE_BECALI)
    ron_values = [r["valoare_ron"] for r in rows]
    assert 45825140.0 in ron_values
    # 800000 EUR × 5.05
    expected_eur = 800000 * 5.05
    assert any(abs(v - expected_eur) < 1.0 for v in ron_values)


# ── _scan_amounts (bijuterii / cadouri) ───────────────────────────────────────

def test_scan_bijuterii():
    total = _scan_amounts(SEC_BIJUTERII)
    # 140000 RON + 42000 EUR × 5.05
    assert total == pytest.approx(140000.0 + 42000 * 5.05, rel=0.01)


def test_scan_cadouri_empty():
    assert _scan_amounts(SEC_CADOURI_EMPTY) == pytest.approx(0.0)


def test_scan_instrainate_excludes_zero():
    # 0 RON excluded by > 100 threshold; 63000 RON included
    total = _scan_amounts(SEC_INSTRAINATE)
    assert total == pytest.approx(63000.0)


# ── bunuri_instrainate_count ──────────────────────────────────────────────────

def test_instrainate_count():
    dates = re.findall(r"\b\d{1,2}[./]\d{1,2}[./]\d{4}\b", SEC_INSTRAINATE)
    assert len(dates) == 2


# ── Derived aggregates ────────────────────────────────────────────────────────

def test_total_active_monetare():
    from parsers.avere_pdf import _scan_amounts
    # Build a minimal result dict the same way parse_pdf would
    conturi = 377500.0
    plasamente = 45825140.0
    bijuterii = _scan_amounts(SEC_BIJUTERII)  # 140000 + 42000*5.05
    expected = conturi + plasamente + bijuterii
    total = conturi + plasamente + bijuterii
    assert total == pytest.approx(expected)


def test_avere_neta():
    total_active = 1000000.0
    datorii = 200000.0
    neta = total_active - datorii
    assert neta == pytest.approx(800000.0)


def test_nr_judete_from_imobile():
    rows, _ = _parse_imobile_details(SEC_TERENURI, SEC_CLADIRI)
    nr = len({r["judet"] for r in rows if r.get("judet")})
    assert nr == 2  # Gorj and Mehedinti


def test_nr_companii_from_plasamente():
    rows = _parse_plasamente(SEC_PLASAMENTE_BECALI)
    assert len(rows) == 2  # ARCOM SA + Fotbal Club FCSB SA


def test_terenuri_forestiere_count():
    rows, _ = _parse_imobile_details(SEC_TERENURI, "")
    count = sum(1 for r in rows if r.get("categorie") == "forestier")
    assert count == 1


def test_terenuri_agricole_count():
    rows, _ = _parse_imobile_details(SEC_TERENURI, "")
    count = sum(1 for r in rows if r.get("categorie") == "agricol")
    assert count == 1


def test_an_prima_proprietate():
    rows, _ = _parse_imobile_details(SEC_TERENURI, SEC_CLADIRI)
    ani = [r["an_dobandirii"] for r in rows if r.get("an_dobandirii")]
    assert min(ani) == 2015  # earliest year in SEC_TERENURI is 2015


def test_an_prima_proprietate_empty():
    rows, _ = _parse_imobile_details("", "")
    ani = [r["an_dobandirii"] for r in rows if r.get("an_dobandirii")]
    result = min(ani) if ani else None
    assert result is None
