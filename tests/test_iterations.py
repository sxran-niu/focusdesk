"""Regression coverage for the four post-prototype development milestones."""

import json
from datetime import date, timedelta

import pytest

from focusdesk import ValidationError
from focusdesk.weekly import week_start, weekly_plan


def test_carryover_move_preserves_history_and_completion(desk, today, course):
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = desk.add_task({"title": "Unfinished", "outcome_id": course[2]})
    desk.schedule_task(yesterday, {"task_id": task, "start": "09:00"})
    old = desk.snapshot(today)["carryover"][0]
    desk.reschedule(old["id"], {"date": today, "start": "10:00"})
    state = desk.snapshot(today)
    assert state["carryover"] == []
    assert state["blocks"][0]["id"] == old["id"]
    assert state["blocks"][0]["start"] == 600
    assert json.loads(state["changes"][0]["old_value"]) == old
    assert state["goals"][0]["earned"] == 0
    desk.reschedule(old["id"], {"date": today, "start": "10:00"})
    assert len(desk.snapshot()["changes"]) == 1
    desk.complete_task(task, {"done": True, "actual_minutes": 40})
    with pytest.raises(ValidationError):
        desk.reschedule(old["id"], {"date": yesterday, "start": "09:00"})


def test_failed_move_is_atomic_and_postponement_is_visible(desk, today):
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    task = desk.add_task({"title": "Move me"})
    blocker = desk.add_task({"title": "Occupied"})
    desk.schedule_task(yesterday, {"task_id": task, "start": "09:00"})
    desk.schedule_task(today, {"task_id": blocker, "start": "10:00"})
    before = desk.snapshot(today)
    block = before["carryover"][0]
    for start in ("10:00", "18:00"):
        with pytest.raises(ValidationError):
            desk.reschedule(block["id"], {"date": today, "start": start})
        assert desk.snapshot(today) == before
    desk.reschedule(block["id"], {"date": tomorrow, "start": "11:00"})
    assert desk.snapshot(today)["carryover"] == []
    assert desk.snapshot(tomorrow)["blocks"][0]["date"] == tomorrow
    desk.unschedule(block["id"])
    state = desk.snapshot()
    assert len(state["changes"]) == 2
    assert json.loads(state["changes"][-1]["new_value"]) is None


def test_completed_past_tasks_are_not_carryover(desk, today):
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    task = desk.add_task({"title": "Done"})
    desk.schedule_task(yesterday, {"task_id": task, "start": "09:00"})
    desk.complete_task(task, {"done": True})
    assert desk.snapshot(today)["carryover"] == []


def test_weekly_plan_six_hours_two_scheduled_four_unplanned(desk, course, today):
    outcome = course[2]
    monday = week_start(today)
    task = desk.add_task({"title": "Revision", "minutes": 120, "outcome_id": outcome})
    desk.add_task({"title": "More revision", "minutes": 240, "outcome_id": outcome})
    desk.schedule_task(monday, {"task_id": task, "start": "09:00"})
    desk.set_weekly_target(today, outcome, {"minutes": 360})
    plan = weekly_plan(desk.snapshot(today), today)
    row = plan["courses"][0]
    assert (
        row["target_minutes"],
        row["scheduled_minutes"],
        row["unplanned_minutes"],
    ) == (360, 120, 240)
    assert row["remaining_task_minutes"] == 360
    assert plan["free_minutes"] == 7 * 540 - 120
    desk.complete_task(task, {"done": True, "actual_minutes": 100})
    row = weekly_plan(desk.snapshot(today), today)["courses"][0]
    assert row["actual_minutes"] == 100
    assert row["unplanned_minutes"] == 240  # actual is not added to scheduled time
    assert desk.snapshot()["goals"][0]["earned"] == 0


def test_weekly_targets_are_normalized_and_weeks_are_independent(desk, course):
    outcome = course[2]
    desk.set_weekly_target("2026-09-30", outcome, {"minutes": 180})
    desk.set_weekly_target("2026-10-04", outcome, {"minutes": 360})
    desk.set_weekly_target("2026-10-05", outcome, {"minutes": 60})
    task = desk.add_task({"title": "Next week", "outcome_id": outcome})
    desk.schedule_task("2026-10-05", {"task_id": task, "start": "09:00"})
    state = desk.snapshot("2026-09-30")
    assert len(state["weekly_targets"]) == 2
    first = weekly_plan(state, "2026-09-30")["courses"][0]
    second = weekly_plan(state, "2026-10-05")["courses"][0]
    assert first["unplanned_minutes"] == 360
    assert second["unplanned_minutes"] == 0
    desk.set_weekly_target("2026-09-30", outcome, {"minutes": 0})
    assert (
        weekly_plan(desk.snapshot(), "2026-09-30")["courses"][0]["target_minutes"] == 0
    )
    with pytest.raises(ValidationError):
        desk.set_weekly_target("2026-09-30", outcome, {"minutes": -1})
