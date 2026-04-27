"""Sanctiune — sancțiune disciplinară aplicată unui deputat în plen.

Sursa: cdep.ro/pls/parlam/sanctiuni_parlam.lista_sanctionati
Vezi sitemap.md §9 pentru detalii URL pattern și taxonomie.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .common import Gender


class TipSanctiune(StrEnum):
    """Taxonomie sancțiuni observate pe cdep.ro."""

    DIMINUARE_INDEMNIZATIE = "diminuare_indemnizatie"
    AVERTISMENT_SCRIS = "avertisment_scris"
    CHEMARE_ORDINE = "chemare_la_ordine"
    RETRAGERE_CUVANT = "retragere_cuvant"
    OTHER = "other"


class Sanctiune(BaseModel):
    """O sancțiune aplicată unui deputat."""

    model_config = ConfigDict(str_strip_whitespace=True)

    # ID stabil = hash(data + nume + nr_decizie)
    id: str = Field(..., description="Canonical ID stabil")

    # --- Context ---
    legislatura: int = Field(..., description="Anul legislaturii (2024, 2020, 2016)")
    data: date = Field(..., description='Data deciziei BP, parsată din "23 martie 2026"')

    # --- Deputat afectat ---
    deputat_nume: str = Field(..., description='Nume complet (ex: "Nini-Alexandru PASCALINI")')
    deputat_canonical_id: str | None = Field(
        None,
        description="Canonical ID al deputatului (cross-link cu /deputati). None dacă nu se rezolvă.",
    )
    gender_hint: Gender | None = Field(
        None, description='Inferat din "domnului"/"doamnei" în textul deciziei'
    )

    # --- Sancțiunea ---
    tip: TipSanctiune
    procent: int | None = Field(
        None, description="Procent din indemnizație (doar pentru DIMINUARE_INDEMNIZATIE)"
    )
    durata_luni: int | None = Field(
        None, description="Durată sancțiune în luni (doar pentru DIMINUARE_INDEMNIZATIE)"
    )
    descriere: str = Field(..., description="Textul integral al deciziei (rezumat scurt)")

    # --- Surse documentare ---
    nr_decizie: str | None = Field(None, description='Format "4/23-03-2026"')
    decizie_pdf_url: HttpUrl | None = Field(None, description="URL PDF decizie BP")
    stenograma_url: HttpUrl | None = Field(None, description="URL pagină stenogramă plen")
