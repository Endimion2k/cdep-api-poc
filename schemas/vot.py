"""Vot — eveniment de vot electronic în plen + breakdown nominal.

Aliniat la Popolo `VoteEvent` + `Vote`. Vezi INTEGRATIONS.md §1.
Sursa: cdep.ro/pls/steno/evot2015.{xml,nominal}
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .common import VoteOption


class VoteCounts(BaseModel):
    """Numărători agregate pentru un vot."""

    model_config = ConfigDict(str_strip_whitespace=True)

    prezenti: int = Field(..., ge=0, description="Total deputați prezenți")
    pentru: int = Field(..., ge=0, description="Voturi DA")
    contra: int = Field(..., ge=0, description="Voturi NU")
    abtineri: int = Field(..., ge=0, description="Abțineri (AB)")
    nu_au_votat: int = Field(..., ge=0, description="Prezenți dar n-au votat")


class VoteIndividual(BaseModel):
    """Vot nominal al unui deputat — Popolo `Vote`."""

    model_config = ConfigDict(str_strip_whitespace=True)

    voter_canonical_id: str | None = Field(
        None, description="Canonical ID al deputatului (cross-link cu /deputati)"
    )
    voter_name: str = Field(..., description="Nume complet")
    party: str | None = Field(None, description='Grup parlamentar la momentul votului (ex: "PSD", "AUR")')
    option: VoteOption = Field(..., description="Opțiunea votului: yes/no/abstain/not_voting")


class VoteEvent(BaseModel):
    """Eveniment de vot — Popolo `VoteEvent`. Reprezintă o decizie supusă plenului."""

    model_config = ConfigDict(str_strip_whitespace=True)

    # --- Identitate ---
    id: str = Field(..., description="Canonical ID stabil (hash din legislatura+idv)")
    cdep_idv: int = Field(..., description="ID nativ cdep.ro (idv din URL)")
    legislatura: int = Field(..., description="Anul legislaturii (2024, 2020, 2016)")
    cam: int = Field(2, description="2 = Camera Deputaților")

    # --- Conținut ---
    timestamp: datetime = Field(..., description="Data + ora exactă a votului")
    descriere: str = Field(..., description="Descriere scurtă (ex: 'PH CD 23/2026 - Vot final adoptare')")

    # --- Rezultate agregate ---
    counts: VoteCounts

    # --- Voturi nominale ---
    votes: list[VoteIndividual] = Field(
        default_factory=list,
        description="Lista nominală — un Vote per deputat care a participat",
    )

    # --- Referințe ---
    source_url: HttpUrl = Field(..., description="URL pagină nominal pe cdep.ro")


class VoteEventSummary(BaseModel):
    """Versiune compactă pentru `_index.json` — fără voturile nominale.

    Permite client-side filtering pe sumar (data, descriere, counts) fără
    a încărca toate cele ~330 voturi individuale.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    cdep_idv: int
    legislatura: int
    cam: int
    timestamp: datetime
    descriere: str
    counts: VoteCounts
    detail_url: str = Field(..., description='Path relativ către detaliu (ex: "voturi/2024/36875.json")')
