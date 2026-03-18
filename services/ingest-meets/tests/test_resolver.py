"""Tests for athlete identity resolution."""

import pytest
from core.athlete_resolver import AthleteResolver, compare_names


def test_same_athlete_different_formats():
    resolver = AthleteResolver()

    _, is_new1 = resolver.resolve("Jane Smith", gym="Indy Stars", level="8")
    assert is_new1 is True  # First time — creates new

    athlete_id, is_new2 = resolver.resolve("Smith, Jane", gym="Indy Stars", level="8")
    assert is_new2 is False  # Should match existing
    assert athlete_id is not None


def test_different_athletes_same_gym():
    resolver = AthleteResolver()

    id1, _ = resolver.resolve("Jane Smith", gym="Indy Stars", level="8")
    id2, _ = resolver.resolve("Emily Johnson", gym="Indy Stars", level="8")
    assert id1 != id2


def test_compare_names_similar():
    score = compare_names("Jane Smith", "smith, jane")
    assert score >= 85


def test_compare_names_different():
    score = compare_names("Jane Smith", "Emily Johnson")
    assert score < 60


def test_athlete_count():
    resolver = AthleteResolver()
    resolver.resolve("Jane Smith", gym="Gym A", level="8")
    resolver.resolve("Emily Johnson", gym="Gym A", level="8")
    assert resolver.athlete_count() == 2
