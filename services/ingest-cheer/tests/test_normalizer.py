"""Tests for data normalization layer."""

import pytest
from core.normalizer import (
    normalize_event,
    normalize_level,
    normalize_athlete_name,
    normalize_gym_name,
    normalize_scorecat_record,
    normalize_mso_record,
)


def test_normalize_event_aliases():
    assert normalize_event("Vault") == "vault"
    assert normalize_event("vt") == "vault"
    assert normalize_event("uneven bars") == "uneven_bars"
    assert normalize_event("BB") == "balance_beam"
    assert normalize_event("floor exercise") == "floor_exercise"
    assert normalize_event("AA") == "AA"
    assert normalize_event("all around") == "AA"


def test_normalize_level():
    assert normalize_level("Level 8") == "8"
    assert normalize_level("Xcel Gold") == "xcel_gold"
    assert normalize_level("10") == "10"


def test_normalize_athlete_name_last_first():
    assert normalize_athlete_name("Smith, Jane") == "Jane Smith"


def test_normalize_athlete_name_uppercase():
    assert normalize_athlete_name("JANE SMITH") == "Jane Smith"


def test_normalize_athlete_name_normal():
    assert normalize_athlete_name("Jane Smith") == "Jane Smith"


def test_normalize_gym_name():
    assert normalize_gym_name("  indy stars  ") == "Indy Stars"


def test_normalize_scorecat_record():
    raw = {
        "athleteName": "smith, jane",
        "gymName": "indy stars",
        "event": "vault",
        "level": "level 8",
        "score": "9.325",
        "meetId": "12345",
        "sessionNumber": 2,
    }
    rec = normalize_scorecat_record(raw)
    assert rec["athlete_name"] == "Jane Smith"
    assert rec["gym"] == "Indy Stars"
    assert rec["event"] == "vault"
    assert rec["level"] == "8"
    assert rec["score"] == 9.325
    assert rec["source"] == "scorecat"


def test_normalize_mso_record():
    raw = {
        "athlete_name": "Smith, Jane",
        "gym": "Indy Stars",
        "event": "AA",
        "score": "37.825",
        "meet_id": "MSO-9876",
    }
    rec = normalize_mso_record(raw)
    assert rec["athlete_name"] == "Jane Smith"
    assert rec["score"] == 37.825
    assert rec["source"] == "mso"
