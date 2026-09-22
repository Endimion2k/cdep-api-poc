"""Parserul de transcrieri: delimitarea intervențiilor și găsirea paginii cu textul integral."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.stenograme import (  # noqa: E402
    html_to_text,
    parse_interventions,
    transcript_ids,
)

TRANSCRIPT_HTML = """
<html><head><style>p{margin:0}</style></head><body><div id="olddiv">
<p><b>Domnul Adrian-Felician Cozma:</b></p>
<p>Bună dimineaţa, stimaţi colegi! Declar deschisă prima parte a şedinţei.</p>
<p><b>Doamna Natalia-Elena Intotero (PSD):</b></p>
<p>Mulţumesc, domnule preşedinte.</p><p>Supun votului dumneavoastră raportul.</p>
<p><b>Domnul preşedinte de şedinţă Ion Popescu:</b></p><p>Da.</p>
<p><b>Domnul ministru George Ionescu:</b></p><p>Guvernul susţine proiectul în forma comisiei.</p>
<p><b>Domnul Vasile Pop (din sală):</b></p><p>Nu este adevărat, domnule preşedinte!</p>
<p><b>Domnul Mihai Radu (senator):</b></p><p>Mulţumesc pentru invitaţie, dragi colegi.</p>
</div></body></html>
"""


def test_parse_interventions_splits_by_speaker() -> None:
    out = parse_interventions(html_to_text(TRANSCRIPT_HTML))
    # "Da." are sub 4 caractere, deci nu e o intervenție
    assert [iv.vorbitor for iv in out] == [
        "Adrian-Felician Cozma",
        "Natalia-Elena Intotero",
        "George Ionescu",
        "Vasile Pop",
        "Mihai Radu",
    ]
    assert out[0].partid is None and out[0].rol is None
    assert out[1].partid == "PSD"
    assert "Supun votului" in out[1].text
    assert out[2].rol == "ministru"
    assert "style" not in out[0].text and "margin" not in out[0].text
    # paranteza nu e mereu partidul
    assert out[3].partid is None and out[3].rol is None
    assert out[4].partid is None and out[4].rol == "senator"


def test_parse_interventions_without_speakers() -> None:
    assert parse_interventions("") == []
    assert parse_interventions("text fara vorbitori") == []


def test_transcript_ids_from_index_page() -> None:
    index_html = '<a href="/ords/pls/steno/steno2015.sumar?ids=9069&cam=2&idl=2">Sumar</a>'
    assert transcript_ids(index_html) == "9069"
    assert transcript_ids("<html>fara link</html>") is None
