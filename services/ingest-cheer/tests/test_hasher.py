"""Tests for hash-based deduplication."""

import pytest
from core.hasher import compute_hash, is_duplicate, mark_seen, reset, seen_count


@pytest.fixture(autouse=True)
def clear_hashes():
    reset()
    yield
    reset()


def test_duplicate_detection():
    record = {
        "athlete_name": "Jane Smith",
        "gym": "Indy Stars",
        "meet_id": "MSO-123",
        "event": "vault",
        "score": 9.325,
        "level": "8",
        "session": 1,
    }
    assert not is_duplicate(record)
    mark_seen(record)
    assert is_duplicate(record)


def test_different_scores_not_duplicate():
    r1 = {"athlete_name": "Jane Smith", "gym": "A", "meet_id": "M1", "event": "vault", "score": 9.0, "level": "8", "session": 1}
    r2 = {"athlete_name": "Jane Smith", "gym": "A", "meet_id": "M1", "event": "vault", "score": 9.5, "level": "8", "session": 1}
    mark_seen(r1)
    assert not is_duplicate(r2)


def test_seen_count():
    r = {"athlete_name": "X", "gym": "Y", "meet_id": "Z", "event": "AA", "score": 9.0, "level": "8", "session": 1}
    assert seen_count() == 0
    mark_seen(r)
    assert seen_count() == 1
