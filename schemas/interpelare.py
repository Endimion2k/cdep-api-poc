"""Interpelare / Întrebare — adresări parlamentare către Guvern.

Sursa: cdep.ro/pls/parlam/interpelari2015.{lista,detalii}
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Interpelare(BaseModel):
    """O interpelare sau întrebare adresată Guvernului de un deputat."""

    model_config = ConfigDict(str_strip_whitespace=True)

    # --- Identitate ---
    id: str = Field(..., description="Canonical ID stabil (hash din legislatura+idi)")
    cdep_idi: int = Field(..., description="ID nativ cdep.ro (idi din URL)")
    legislatura: int
    nr_inregistrare: str = Field(..., description='Format: "929B" sau "1234A"')

    # --- Date cheie ---
    data_inregistrare: date | None = None
    data_prezentare: date | None = None
    data_comunicare: date | None = None
    termen_raspuns: date | None = None

    # --- Conținut ---
    titlu: str = Field(..., description="Subiectul interpelării/întrebării")
    mod_adresare: str | None = Field(None, description='"în scris" sau "oral"')

    # --- Adresant (deputatul care întreabă) ---
    adresant_nume: str
    adresant_canonical_id: str | None = Field(
        None, description="Cross-link cu /deputati"
    )
    adresant_grup: str | None = Field(None, description="Grup parlamentar la moment")

    # --- Destinatar ---
    destinatar: str = Field(..., description="Ministerul/instituția adresată")

    # --- Documentație ---
    text_pdf_url: HttpUrl | None = Field(None, description="PDF cu textul interpelării")
    raspuns_solicitat: str | None = Field(None, description='"în scris" sau "oral"')

    # --- Răspuns (opțional) ---
    raspuns_primit: bool = Field(False, description="True dacă există răspuns")
    raspuns_nr_inregistrare: str | None = None
    raspuns_data: date | None = None
    raspuns_sursa: str | None = Field(None, description="Cine a răspuns (ministerul)")
    raspuns_comunicat_de: str | None = Field(None, description="Persoana care a comunicat")
    raspuns_pdf_url: HttpUrl | None = None

    # --- Referință ---
    source_url: HttpUrl
