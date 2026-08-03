"""Schema pentru averile parsate din PDF-urile ANI."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, HttpUrl


class AvereImobil(BaseModel):
    """Un teren sau o clădire declarată."""

    tip: str = Field(description="'teren' | 'cladire'")
    categorie: str = Field(
        description="agricol | forestier | intravilan | luciu_apa | extravilan"
        " | apartament | locuinta | vacanta | comercial | alte_cladiri | necunoscuta"
    )
    suprafata_mp: float | None = None
    judet: str | None = None
    an_dobandirii: int | None = None
    cota_parte: str | None = None
    modul_dobandirii: str | None = None


class VehiculDetail(BaseModel):
    """Un autovehicul / mijloc de transport declarat."""

    natura: str
    marca: str | None = None
    an_fabricatie: int | None = None
    mod_dobandire: str | None = None


class ContDetail(BaseModel):
    """Un cont bancar / depozit / fond declarat (IV.1)."""

    institutie: str | None = None
    tip: str | None = None  # "cont_curent" | "depozit" | "fond_investitii"
    valuta: str = "RON"
    an_deschis: int | None = None
    sold_ron: float = 0.0


class PlasamentDetail(BaseModel):
    """O investiție directă / acțiuni SRL / împrumut acordat (IV.2)."""

    emitent: str | None = None
    tip: str | None = None  # "actiuni" | "parti_sociale" | "titluri_stat" | "imprumut"
    nr_titluri: str | None = None  # e.g. "100 %" or "1/3"
    valoare_ron: float = 0.0


class AvereDeclaratie(BaseModel):
    """O declarație individuală depusă la o anumită dată."""

    data_depunere: date | None = Field(description="Data depunerii la ANI")
    pdf_url: HttpUrl
    text_extracted: bool = Field(description="True dacă pdfplumber a citit text")
    error: str | None = None

    # I. Imobile — agregate
    terenuri_count: int = 0
    cladiri_count: int = 0
    suprafata_total_mp: float = 0.0
    suprafata_agricol_mp: float = 0.0
    suprafata_forestier_mp: float = 0.0
    suprafata_intravilan_mp: float = 0.0
    suprafata_luciu_mp: float = 0.0
    suprafata_alte_mp: float = 0.0
    suprafata_cladiri_mp: float = 0.0

    # II.1 Auto
    auto_count: int = Field(default=0, description="Nr. vehicule declarate")

    # II.2 Metale prețioase / bijuterii / artă
    bijuterii_total_ron: float = 0.0

    # III. Bunuri înstrăinate (ultimele 12 luni)
    bunuri_instrainate_count: int = 0
    bunuri_instrainate_total_ron: float = 0.0

    # IV.1 Conturi
    conturi_total_ron: float = Field(default=0.0, description="Active financiare în RON")

    # IV.2 Plasamente / investiții / acțiuni
    plasamente_total_ron: float = 0.0

    # V. Datorii
    datorii_total_ron: float = 0.0

    # VI. Cadouri
    cadouri_total_ron: float = 0.0

    # VII. Venituri
    venituri_anuale_ron: float = Field(
        default=0.0, description="Suma veniturilor anuale (titular + familie)"
    )

    # Detail lists
    imobile_detaliate: list[AvereImobil] = Field(default_factory=list)
    vehicule: list[VehiculDetail] = Field(default_factory=list)
    conturi_detaliate: list[ContDetail] = Field(default_factory=list)
    plasamente_detaliate: list[PlasamentDetail] = Field(default_factory=list)

    # Derived aggregates — computed at parse time from the fields above
    total_active_monetare_ron: float = 0.0
    avere_neta_ron: float = 0.0
    nr_judete: int = 0
    nr_companii: int = 0
    terenuri_forestiere_count: int = 0
    terenuri_agricole_count: int = 0
    an_prima_proprietate: int | None = None


class AvereDeputat(BaseModel):
    """Un deputat cu toate declarațiile lui cronologic."""

    id: str = Field(description="sha256('{leg}|{cdep_idm}|avere')[:16]")
    cdep_idm: int
    deputat_nume: str
    deputat_canonical_id: str | None = None
    legislatura: int
    partid_short: str | None = None

    declaratii: list[AvereDeclaratie] = Field(
        default_factory=list, description="Sortate cronologic"
    )

    # Snapshot final (ultima declarație)
    ultima_data: date | None = None
    ultima_conturi_ron: float = 0.0
    ultima_venituri_ron: float = 0.0
    ultima_imobile_count: int = 0
    ultima_bijuterii_ron: float = 0.0
    ultima_plasamente_ron: float = 0.0
    ultima_datorii_ron: float = 0.0
    ultima_total_active_ron: float = 0.0
    ultima_avere_neta_ron: float = 0.0
    ultima_nr_judete: int = 0
    ultima_nr_companii: int = 0

    # Delta prima → ultima
    delta_conturi_ron: float = 0.0
    delta_imobile: int = 0


class AvereSummary(BaseModel):
    """Sumar pentru index — fără declarațiile complete."""

    id: str
    cdep_idm: int
    deputat_nume: str
    legislatura: int
    partid_short: str | None = None
    n_declaratii: int = 0
    ultima_data: date | None = None
    ultima_conturi_ron: float = 0.0
    ultima_venituri_ron: float = 0.0
    ultima_imobile_count: int = 0
    ultima_bijuterii_ron: float = 0.0
    ultima_plasamente_ron: float = 0.0
    ultima_datorii_ron: float = 0.0
    ultima_total_active_ron: float = 0.0
    ultima_avere_neta_ron: float = 0.0
    ultima_nr_judete: int = 0
    ultima_nr_companii: int = 0
    bunuri_instrainate_total_ron: float = 0.0
    delta_conturi_ron: float = 0.0
    delta_imobile: int = 0
    detail_url: str
