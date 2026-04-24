"""Deputat — aliniat la Popolo `Person` + extensii CDEP.

Vezi INTEGRATIONS.md §1 pentru mapping-ul Popolo adoptat.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .common import Gender


class ComisieMembership(BaseModel):
    """Apartenența la o comisie — Popolo `Membership`."""

    model_config = ConfigDict(str_strip_whitespace=True)

    comisia: str = Field(..., description="Numele complet al comisiei")
    tip: str = Field(..., description="permanenta | speciala | speciala_comuna")
    rol: str | None = Field(
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
    given_name: str | None = Field(None, description='Prenume (ex: "Mirela Elena")')
    family_name: str | None = Field(None, description='Nume de familie (ex: "Adomnicăi")')
    gender: Gender | None = Field(None, description="Inferat lingvistic din ales/aleasă")
    birth_date: date | None = Field(None, description='Parsat din "n. 15 aug. 1970"')
    image: HttpUrl | None = Field(None, description="URL fotografie oficială")

    # --- CDEP-specific extensions ---
    cdep_idm: int = Field(..., description="ID intern cdep.ro (NU stabil peste legislaturi)")
    legislatura: int = Field(..., description="Anul începerii mandatului")
    judet: str | None = Field(None, description="Județul")
    circumscriptie: int | None = Field(None, description="Nr. circumscripției electorale")
    profile_url: HttpUrl = Field(..., description="URL profil cdep.ro")
    data_validare: date | None = Field(None, description="Data validării mandatului")
    hcd_validare: str | None = Field(None, description='Hotărâre CD (ex: "HCD nr.109/2024")')

    # --- Current political affiliations ---
    current_party: str | None = Field(None, description="Partidul curent")
    current_group: str | None = Field(None, description="Grupul parlamentar curent")
    group_role: str | None = Field(None, description='Rol în grup: "Lider", "Vicelider"...')

    # --- Committee memberships ---
    comisii: list[ComisieMembership] = Field(default_factory=list)

    # --- International ---
    delegatii: list[str] = Field(default_factory=list)
    grupuri_prietenie: list[str] = Field(default_factory=list)

    # --- Activity stats ---
    activitate_luari_cuvant: int | None = None
    activitate_sedinte: int | None = None
    activitate_declaratii_politice: int | None = None
    activitate_propuneri_legislative: int | None = None
    activitate_legi_promulgate: int | None = None
    activitate_intrebari_interpelari: int | None = None

    # --- Office (cdep.ro nu publică email personal) ---
    birou_parlamentar: str | None = Field(None, description="Adresă birou parlamentar")
