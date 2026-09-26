"""Stable course identity, archived goals and non-destructive schema migration."""

import sqlite3

import pytest

from focusdesk import ValidationError, Workbench


def test_edit_stage_and_move_confirmed_course_keep_identity(desk, course, today):
    goal, phase, outcome = course
    task = desk.add_task({"title": "Review", "outcome_id": outcome})
    desk.set_weekly_target(today, outcome, {"minutes": 360})
    desk.record_outcome(outcome, {"status": "passed", "result_date": today})
    destination = desk.add_milestone(
        {
            "goal_id": goal,
            "title": "New term",
            "target": 6,
            "start_date": today,
            "end_date": "2099-10-01",
        }
    )
    desk.revise_milestone(
        phase, {"title": "Revised term", "end_date": "2098-12-01", "target": 5}
    )
    desk.update_outcome(outcome, {"milestone_id": destination})
    desk.update_outcome(outcome, {"milestone_id": destination})
    state = desk.snapshot()
    assert state["goals"][0]["earned"] == 6
    assert len(state["outcomes"]) == 1
    assert state["milestones"][0]["earned"] == 0
    assert state["milestones"][0]["original_target"] == 6
    assert state["milestones"][1]["earned"] == 6
    assert state["tasks"][0]["id"] == task
    assert state["tasks"][0]["outcome_id"] == outcome
    assert state["weekly_targets"][0]["outcome_id"] == outcome
    assert len([c for c in state["changes"] if c["entity"] == "outcome_details"]) == 1
    before = desk.snapshot()
    with pytest.raises(ValidationError):
        desk.revise_milestone(phase, {"title": "Bad", "end_date": "2000-01-01"})
    assert desk.snapshot() == before


def test_outcome_cannot_move_between_goals(desk, course, today):
    goal = desk.add_goal(
        {"title": "Other", "target": 1, "unit": "books", "target_date": "2099-12-31"}
    )
    phase = desk.add_milestone(
        {
            "goal_id": goal,
            "title": "Other term",
            "target": 1,
            "start_date": today,
            "end_date": "2099-01-01",
        }
    )
    with pytest.raises(ValidationError):
        desk.update_outcome(course[2], {"milestone_id": phase})


def test_archive_requires_completion_and_restore_keeps_results(desk, course, today):
    goal, phase, outcome = course
    condition = desk.add_requirement({"goal_id": goal, "title": "Thesis"})
    with pytest.raises(ValidationError):
        desk.archive_goal(goal, True)
    desk.record_outcome(outcome, {"status": "passed", "result_date": today})
    with pytest.raises(ValidationError):
        desk.archive_goal(goal, True)
    desk.set_requirement(condition, True)
    desk.archive_goal(goal, True)
    desk.archive_goal(goal, True)
    assert desk.snapshot()["goals"][0]["archived"] == 1
    for mutation in (
        lambda: desk.update_goal(goal, {"target": 10}),
        lambda: desk.revise_milestone(phase, {"target": 10}),
        lambda: desk.record_outcome(outcome, {"status": "pending"}),
        lambda: desk.update_outcome(outcome, {"title": "Changed"}),
        lambda: desk.set_requirement(condition, False),
        lambda: desk.set_weekly_target(today, outcome, {"minutes": 10}),
    ):
        with pytest.raises(ValidationError):
            mutation()
    desk.archive_goal(goal, False)
    assert desk.snapshot()["goals"][0]["earned"] == 6
    desk.record_outcome(outcome, {"status": "pending"})
    assert desk.snapshot()["goals"][0]["earned"] == 0


def test_old_database_migration_preserves_data(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE goals (id INTEGER PRIMARY KEY,title TEXT NOT NULL,"
            "target REAL NOT NULL,unit TEXT NOT NULL,target_date TEXT NOT NULL,"
            "notes TEXT NOT NULL DEFAULT '')"
        )
        connection.execute(
            "INSERT INTO goals VALUES(1,'Existing',6,'ECTS','2099-01-01','')"
        )
    for _ in range(2):
        goal = Workbench(path).snapshot()["goals"][0]
        assert goal["title"] == "Existing"
        assert goal["archived"] == 0


def test_deleted_task_id_cannot_inherit_schedule_history(desk, today):
    first = desk.add_task({"title": "First"})
    second = desk.add_task({"title": "Second"})
    desk.schedule_task(today, {"task_id": second, "start": "09:00"})
    block = desk.snapshot()["blocks"][0]
    desk.reschedule(block["id"], {"date": today, "start": "10:00"})
    desk.delete_task(second)
    desk.delete_task(first)
    new = desk.add_task({"title": "New"})
    assert new > second
    assert not any(c["entity_id"] == new for c in desk.snapshot()["changes"])
