"""Unit tests for Varsity TV client (no network)."""

from datetime import date

from agents.varsity_client import (
    cheer_mvp_meet_covers_calendar_day,
    extract_event_display_title_from_hub_payload,
    infer_team_level_from_division_label,
    merge_events_by_id,
    normalize_event_card,
    parse_event_hub_table_section,
    parse_varsity_event_id_from_meet_key,
)


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
