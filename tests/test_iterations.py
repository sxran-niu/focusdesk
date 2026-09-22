"""Regression coverage for the four post-prototype development milestones."""

import json
from datetime import date, timedelta

import pytest

from focusdesk import ValidationError


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
