"""Unit tests for Varsity TV client (no network)."""

from datetime import date
from unittest import mock

from agents import varsity_client as varsity_client_mod
from agents.varsity_client import (
    cheer_mvp_meet_covers_calendar_day,
    compute_hub_results_snapshot_hash,
    extract_event_display_title_from_hub_payload,
    infer_team_level_from_division_label,
    merge_events_by_id,
    normalize_event_card,
    parse_event_hub_table_section,
    parse_varsity_event_id_from_meet_key,
    parse_varsity_view_all_results_html,
)


def test_events_path_segment_from_slug_uri():
    fn = varsity_client_mod._events_path_segment_from_slug_uri
    assert fn("/events/14478900-2026-one-up-grand-nationals", 14478900) == (
        "14478900-2026-one-up-grand-nationals"
    )
    assert fn("/events/999-wrong", 14478900) is None
    assert fn(None, 14478900) is None


def test_normalize_event_card():
    card = {
        "type": "card:event",
        "title": "Test Meet",
        "subtitle1": "Gym · City, ST",
        "action": {
            "url": "/events/123-slug",
            "analytics": {"nodeId": 123, "slugUri": "/events/123-slug"},
        },
        "label1Parts": {
            "status": "PRE-AIR",
            "startDateTime": "2026-03-27T18:00:00+0000",
            "endDateTime": "2026-03-30T04:59:59+0000",
        },
        "cta2": {"title": "Results", "url": "/events/123/results"},
    }
    row = normalize_event_card(card)
    assert row is not None
    assert row["event_id"] == 123
    assert row["title"] == "Test Meet"
    assert row["results_path"] == "/events/123/results"
    assert row["start_at"] is not None
    assert row["start_at"].year == 2026


def test_merge_events_by_id_prefers_later():
    a = {"event_id": 1, "title": "A"}
    b = {"event_id": 1, "title": "B"}
    merged = merge_events_by_id([a], [b])
    assert len(merged) == 1
    assert merged[0]["title"] == "B"


def test_parse_event_hub_table_section():
    section = {
        "id": "id-table-1-Finals",
        "type": "collection",
        "title": "L1 Tiny - Novice Finals",
        "items": [
            {
                "type": "table",
                "rows": [
                    {
                        "type": "table:row",
                        "action": {
                            "url": "/events/99/videos?playing=1",
                            "mergeParams": {"playing": "1"},
                        },
                        "cells": [
                            {
                                "key": "rank",
                                "data": {"type": "text", "text": "Excellent"},
                            },
                            {
                                "key": "program-team",
                                "data": {
                                    "type": "text",
                                    "text": "Gym A",
                                    "subText": "Team B",
                                },
                            },
                            {
                                "key": "raw-score",
                                "data": {"type": "text", "text": "8.5"},
                            },
                            {
                                "key": "deductions",
                                "data": {"type": "text", "text": "0.1"},
                            },
                            {
                                "key": "performance-score",
                                "data": {"type": "text", "text": "85.0"},
                            },
                            {
                                "key": "event-score",
                                "data": {"type": "text", "text": "84.9"},
                            },
                        ],
                    }
                ],
            }
        ],
    }
    rows = parse_event_hub_table_section(99, section)
    assert len(rows) == 1
    r0 = rows[0]
    assert r0["event_id"] == 99
    assert r0["division_round"] == "L1 Tiny - Novice Finals"
    assert r0["program"] == "Gym A"
    assert r0["team"] == "Team B"
    assert r0["raw_score"] == 8.5
    assert r0["event_score"] == 84.9
    assert r0["video_playing_id"] == "1"


def test_compute_hub_results_snapshot_hash_stable_under_row_order():
    a = {
        "division_round": "L1 Finals",
        "program": "Gym A",
        "team": "Team A",
        "rank": 1,
        "event_score": 90.0,
        "raw_score": 1.0,
        "performance_score": 2.0,
        "deductions": 0.0,
    }
    b = {
        "division_round": "L1 Finals",
        "program": "Gym B",
        "team": "Team B",
        "rank": 2,
        "event_score": 89.0,
        "raw_score": 1.0,
        "performance_score": 2.0,
        "deductions": None,
    }
    h1 = compute_hub_results_snapshot_hash([a, b])
    h2 = compute_hub_results_snapshot_hash([b, a])
    assert h1 == h2


def test_extract_event_display_title_from_hub_payload():
    payload = {
        "type": "partial:list",
        "data": {
            "type": "layout:list",
            "sections": [
                {
                    "id": "filters",
                    "items": [
                        {
                            "options": [
                                {
                                    "action": {
                                        "analytics": {
                                            "slugUri": "/events/14478875-2026-cheersport-national-all-star-cheerleading-championship",
                                            "name": "Novice",
                                        }
                                    }
                                }
                            ]
                        }
                    ],
                },
                {
                    "id": "id-table-x",
                    "title": "L1 Tiny Finals",
                    "action": {
                        "analytics": {
                            "slugUri": "/events/14478875-2026-cheersport-national-all-star-cheerleading-championship",
                            "name": "2026 CHEERSPORT National All Star Cheerleading Championship",
                        }
                    },
                },
            ],
        },
    }
    title = extract_event_display_title_from_hub_payload(payload, 14478875)
    assert title == "2026 CHEERSPORT National All Star Cheerleading Championship"


def test_infer_team_level_from_division_label():
    assert (
        infer_team_level_from_division_label("L1 Tiny - Novice - Restrictions Finals")
        == "L1 Tiny - Novice"
    )
    assert infer_team_level_from_division_label("L2 Youth - D2 - Small - B Prelims") == "L2 Youth - D2"
    assert infer_team_level_from_division_label("CheerABILITIES - Elite Finals") == "CheerABILITIES - Elite"


def test_iter_event_hub_table_sections_paginates_by_section_count_not_table_count():
    """Regression: stopping when ``len(tables) < limit`` hid all pages after the first."""

    def fake_fetch(event_id, limit, offset, facets=None):
        assert event_id == 42
        assert limit == 100
        if offset == 0:
            tables = [{"id": f"id-table-a{i}", "title": f"A{i}"} for i in range(5)]
            filler = [{"id": "filters", "items": []}] * (100 - len(tables))
            return {"data": {"sections": tables + filler}}
        if offset == 100:
            return {
                "data": {
                    "sections": [
                        {"id": "id-table-b0", "title": "B0"},
                    ]
                }
            }
        return {"data": {"sections": []}}

    with mock.patch.object(
        varsity_client_mod, "fetch_event_hub_results_page", side_effect=fake_fetch
    ):
        sections = list(
            varsity_client_mod.iter_event_hub_result_table_sections(42, page_size=100)
        )
    assert len(sections) == 6
    assert sections[-1]["title"] == "B0"


def test_parse_varsity_view_all_results_html_minimal():
    """Angular-style view-all table: seven cells per row (RNK … ES)."""
    html = """<!DOCTYPE html>
<html><body>
<h2>L2 Youth - D2 - Small - B Prelims</h2>
<table><tr>
<td data-test="row-0-table-cell-0"><a href="/events/1/videos?playing=15702551">
  <div class="text-truncate text">5</div></a></td>
<td data-test="row-0-table-cell-1"></td>
<td data-test="row-0-table-cell-2"><a href="/events/1/videos?playing=15702551">
  <div class="text-truncate text">Crush Athletics</div>
  <div class="text-truncate sub-text">Apple Crush</div></a></td>
<td data-test="row-0-table-cell-3"><div class="text-truncate text">47.1667</div></td>
<td data-test="row-0-table-cell-4"><div class="text-truncate text">0</div></td>
<td data-test="row-0-table-cell-5"><div class="text-truncate text">94.3333</div></td>
<td data-test="row-0-table-cell-6"><div class="text-truncate text">23.5833</div></td>
</tr></table></body></html>"""
    parsed = parse_varsity_view_all_results_html(html, 14478900)
    assert parsed is not None
    title, rows = parsed
    assert title == "L2 Youth - D2 - Small - B Prelims"
    assert len(rows) == 1
    r0 = rows[0]
    assert r0["program"] == "Crush Athletics"
    assert r0["team"] == "Apple Crush"
    assert r0["rank"] == 5
    assert r0["event_score"] == 23.5833
    assert r0["video_playing_id"] == "15702551"


def test_parse_varsity_event_id_from_meet_key():
    assert parse_varsity_event_id_from_meet_key("VARSITY-14479023") == 14479023
    assert parse_varsity_event_id_from_meet_key("DEMO-ATL-2026") is None
    assert parse_varsity_event_id_from_meet_key("VARSITY-abc") is None


def test_cheer_mvp_meet_covers_calendar_day():
    d0 = date(2026, 3, 21)
    d1 = date(2026, 3, 22)
    d2 = date(2026, 3, 23)
    assert cheer_mvp_meet_covers_calendar_day(d0, d1, d0)
    assert cheer_mvp_meet_covers_calendar_day(d0, d1, d1)
    assert not cheer_mvp_meet_covers_calendar_day(d0, d1, d2)
    assert cheer_mvp_meet_covers_calendar_day(d0, None, d0)
    assert not cheer_mvp_meet_covers_calendar_day(None, None, d0, include_undated=False)
    assert cheer_mvp_meet_covers_calendar_day(None, None, d0, include_undated=True)
