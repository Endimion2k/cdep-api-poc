"""Tipuri și enum-uri partajate între resurse.

Aliniate la Popolo unde există corespondență directă.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Meta(BaseModel):
    """Metadata atașată la fiecare fișier JSON generat.

    Permite consumatorilor să știe când au fost colectate datele
    și din ce sursă exactă.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    generated_at: datetime = Field(..., description="UTC timestamp la momentul scrape-ului")
    source_url: str = Field(..., description="URL-ul sursă cdep.ro")
    scraper_version: str = Field(..., description="Versiunea scraper-ului (semver)")
    count: int = Field(..., ge=0, description="Numărul de înregistrări din fișier")


class Gender(str, Enum):
    """Popolo-aligned."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class VoteOption(str, Enum):
    """Popolo VoteEvent.votes[].option.

    `not_voting` e o extensie: unii deputați sunt în sală dar nu votează deloc
    (distinct de `absent`).
    """

    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"
    ABSENT = "absent"
    NOT_VOTING = "not_voting"


class OrgClassification(str, Enum):
    """Popolo Organization.classification — subset relevant pentru CDEP."""

    PARTY = "party"
    COMMISSION = "commission"
    PARLIAMENTARY_GROUP = "parliamentary_group"
    BUREAU = "bureau"
    CHAMBER = "chamber"


class MotionResult(str, Enum):
    """Rezultatul unei moțiuni / proiect supus la vot."""

    PASS = "pass"
    FAIL = "fail"
    WITHDRAWN = "withdrawn"
    PENDING = "pending"
