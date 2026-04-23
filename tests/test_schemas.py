"""Teste pentru schemele Pydantic — verifică că modelele pornesc curat."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from schemas.common import Gender, Meta, MotionResult, OrgClassification, VoteOption


def test_meta_roundtrip() -> None:
    meta = Meta(
        generated_at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=timezone.utc),
        source_url="https://www.cdep.ro/",
        scraper_version="0.1.0",
        count=42,
    )
    restored = Meta.model_validate_json(meta.model_dump_json())
    assert restored == meta


def test_meta_rejects_negative_count() -> None:
    with pytest.raises(ValueError):
        Meta(
            generated_at=datetime.now(timezone.utc),
            source_url="https://x",
            scraper_version="0.1.0",
            count=-1,
        )


def test_enums_popolo_aligned() -> None:
    # Popolo VoteEvent.votes[].option — valorile canonice
    assert VoteOption.YES.value == "yes"
    assert VoteOption.NO.value == "no"
    assert VoteOption.ABSTAIN.value == "abstain"
    assert VoteOption.ABSENT.value == "absent"

    # Popolo Organization.classification
    assert OrgClassification.PARTY.value == "party"
    assert OrgClassification.COMMISSION.value == "commission"

    # Popolo Person.gender
    assert Gender.MALE.value == "male"

    # Result for motions / projects
    assert MotionResult.PASS.value == "pass"
