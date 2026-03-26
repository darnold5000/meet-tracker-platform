"""Tests for cheer code target list (no network)."""

from datetime import date

from core.cheer_target_meets import target_var_event_active_on_day


def test_target_var_event_active_no_dates_always_true():
    assert target_var_event_active_on_day({"event_id": 1}, date(2020, 1, 1))


def test_target_var_event_active_window():
    entry = {
        "event_id": 2,
        "start_date": date(2026, 3, 21),
        "end_date": date(2026, 3, 22),
    }
    assert target_var_event_active_on_day(entry, date(2026, 3, 21))
    assert target_var_event_active_on_day(entry, date(2026, 3, 22))
    assert not target_var_event_active_on_day(entry, date(2026, 3, 20))
    assert not target_var_event_active_on_day(entry, date(2026, 3, 23))
