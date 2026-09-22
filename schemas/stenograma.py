"""Schema pentru stenograme ședințe plen."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, HttpUrl


class StenogramaIntervention(BaseModel):
    """O intervenție (alocuțiune) dintr-o stenograma."""

    vorbitor: str = Field(description="Numele vorbitorului.")
    partid: str | None = Field(default=None, description="Grupul parlamentar/partid.")
    rol: str | None = Field(
        default=None, description="Rolul din stenogramă (preşedinte de şedinţă, ministru etc.)."
    )
    text: str = Field(description="Textul intervenției (truncat la 5000 caractere).")
    subiect: str | None = Field(default=None, description="Subiectul / punctul ordinii de zi.")


class Stenograma(BaseModel):
    """Stenograma unei zile de ședință."""

    id: str = Field(description="sha256('{cam}|{session_date}')[:16].")
    session_date: date
    cam: int = Field(description="2=CD, 1=Senat, 0=ședință comună")
    legislatura: int
    titlu: str | None = Field(default=None, description="Titlu din pagină (dacă există).")
    interventions: list[StenogramaIntervention] = Field(
        default_factory=list, description="Lista intervențiilor parlamentare."
    )
    text_complet_len: int | None = Field(
        default=None,
        description="Lungimea textului transcrierii (caractere) — util pentru estimare volum.",
    )
    source_url: HttpUrl = Field(description="Pagina-cuprins a ședinței (steno2015.data).")
    transcript_url: HttpUrl | None = Field(
        default=None, description="Pagina cu transcrierea integrală (steno2015.stenograma)."
    )


class StenogramaSummary(BaseModel):
    """Sumar pentru index — fără text complet."""

    id: str
    session_date: date
    cam: int
    legislatura: int
    titlu: str | None = None
    n_interventions: int = 0
    text_complet_len: int | None = None
    detail_url: str
