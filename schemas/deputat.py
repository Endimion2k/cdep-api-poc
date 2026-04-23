"""Deputat — aliniat la Popolo `Person` + extensii CDEP.

Vezi INTEGRATIONS.md §1 pentru mapping-ul Popolo adoptat.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .common import Gender


class ComisieMembership(BaseModel):
    """Apartenența la o comisie — Popolo `Membership`."""

    model_config = ConfigDict(str_strip_whitespace=True)

    comisia: str = Field(..., description="Numele complet al comisiei")
    tip: str = Field(..., description="permanenta | speciala | speciala_comuna")
    rol: Optional[str] = Field(
        None, description='Rolul: "Președinte", "Vicepreședinte", "Secretar", "Membru"'
    )


class Deputat(BaseModel):
    """Un membru al Camerei Deputaților. Popolo-aligned cu `Person`.

    `id` (canonical) este stabil peste legislaturi. `cdep_idm` e ID-ul nativ
    cdep.ro, care se schimbă între legislaturi.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    # --- Popolo Person fields ---
    id: str = Field(..., description="Canonical ID stabil (hash din nume+data_nașterii)")
    name: str = Field(..., description='Nume complet (ex: "Adomnicăi Mirela Elena")')
    given_name: Optional[str] = Field(None, description='Prenume (ex: "Mirela Elena")')
    family_name: Optional[str] = Field(None, description='Nume de familie (ex: "Adomnicăi")')
    gender: Optional[Gender] = Field(None, description="Inferat lingvistic din ales/aleasă")
    birth_date: Optional[date] = Field(None, description='Parsat din "n. 15 aug. 1970"')
    image: Optional[HttpUrl] = Field(None, description="URL fotografie oficială")

    # --- CDEP-specific extensions ---
    cdep_idm: int = Field(..., description="ID intern cdep.ro (NU stabil peste legislaturi)")
    legislatura: int = Field(..., description="Anul începerii mandatului")
    judet: Optional[str] = Field(None, description='Județul')
    circumscriptie: Optional[int] = Field(None, description="Nr. circumscripției electorale")
    profile_url: HttpUrl = Field(..., description="URL profil cdep.ro")
    data_validare: Optional[date] = Field(None, description="Data validării mandatului")
    hcd_validare: Optional[str] = Field(None, description='Hotărâre CD (ex: "HCD nr.109/2024")')

    # --- Current political affiliations ---
    current_party: Optional[str] = Field(None, description="Partidul curent")
    current_group: Optional[str] = Field(None, description="Grupul parlamentar curent")
    group_role: Optional[str] = Field(None, description='Rol în grup: "Lider", "Vicelider"...')

    # --- Committee memberships ---
    comisii: list[ComisieMembership] = Field(default_factory=list)

    # --- International ---
    delegatii: list[str] = Field(default_factory=list)
    grupuri_prietenie: list[str] = Field(default_factory=list)

    # --- Activity stats ---
    activitate_luari_cuvant: Optional[int] = None
    activitate_sedinte: Optional[int] = None
    activitate_declaratii_politice: Optional[int] = None
    activitate_propuneri_legislative: Optional[int] = None
    activitate_legi_promulgate: Optional[int] = None
    activitate_intrebari_interpelari: Optional[int] = None

    # --- Office (cdep.ro nu publică email personal) ---
    birou_parlamentar: Optional[str] = Field(None, description="Adresă birou parlamentar")
