"""Tests of meaningful invariants shared by both interfaces."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest

from focusdesk import Task, ValidationError, Workbench
from focusdesk.analytics import export_content, save_report, weekly_report
from focusdesk.demo import seed_demo


@pytest.mark.parametrize(
    "field,value",
    [
        ("minutes", 0),
        ("minutes", True),
        ("minutes", 3.5),
        ("priority", 7),
        ("category", "invalid"),
        ("title", "  "),
        ("due_date", "2026-02-30"),
        ("minutes", float("nan")),
    ],
)
def test_invalid_tasks_rejected(field, value):
    with pytest.raises(ValidationError):
        Task(**{"title": "Study", field: value})


def test_tasks_do_not_award_credit_and_results_are_idempotent(desk, course, today):
    goal, phase, outcome = course
    task = desk.add_task({"title": "Study", "outcome_id": outcome})
    desk.complete_task(task, {"done": True, "actual_minutes": 45})
    assert desk.snapshot()["goals"][0]["earned"] == 0
    first_completion = desk.snapshot()["tasks"][0]["completed_at"]
    desk.complete_task(task, {"done": True, "actual_minutes": 120})
    assert desk.snapshot()["tasks"][0]["completed_at"] == first_completion
    assert desk.snapshot()["tasks"][0]["actual_minutes"] == 45
    data = {"status": "passed", "result_date": today, "grade": "1.0"}
    desk.record_outcome(outcome, data)
    desk.record_outcome(outcome, data)
    state = desk.snapshot()
    assert state["goals"][0]["earned"] == 6
    assert len(state["changes"]) == 1
    desk.complete_task(task, {"done": False})
    assert desk.snapshot()["goals"][0]["earned"] == 6
    desk.record_outcome(outcome, {"status": "failed", "result_date": today})
    assert desk.snapshot()["goals"][0]["earned"] == 0
    assert len(desk.snapshot()["changes"]) == 2


def test_goal_requires_both_quantity_and_additional_conditions(desk, course, today):
    goal, _, outcome = course
    condition = desk.add_requirement({"goal_id": goal, "title": "Thesis passed"})
    desk.record_outcome(outcome, {"status": "passed", "result_date": today})
    assert not desk.snapshot()["goals"][0]["achieved"]
    desk.set_requirement(condition, True)
    assert desk.snapshot()["goals"][0]["achieved"]


def test_plan_revision_preserves_original_and_history(desk, course):
    _, phase, _ = course
    desk.revise_milestone(phase, {"target": 10})
    desk.revise_milestone(phase, {"target": 10})
    snapshot = desk.snapshot()
    assert snapshot["milestones"][0]["original_target"] == 6
    assert snapshot["milestones"][0]["target"] == 10
    assert len(snapshot["changes"]) == 1


def test_confirmed_amount_cannot_be_silently_edited(desk, course, today):
    _, _, outcome = course
    desk.record_outcome(outcome, {"status": "passed", "result_date": today})
    with pytest.raises(ValidationError):
        desk.update_outcome(outcome, {"amount": 12})
    assert desk.snapshot()["goals"][0]["earned"] == 6


def test_result_needs_real_confirmation_date(desk, course):
    _, _, outcome = course
    with pytest.raises(ValidationError):
        desk.record_outcome(outcome, {"status": "passed"})
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValidationError):
        desk.record_outcome(outcome, {"status": "passed", "result_date": tomorrow})


def test_missing_relationships_and_invalid_goal_dates(desk, course, today):
    goal, _, _ = course
    with pytest.raises(ValidationError):
        desk.add_task({"title": "Bad association", "outcome_id": 999})
    with pytest.raises(ValidationError):
        desk.add_milestone(
            {
                "goal_id": goal,
                "title": "Bad range",
                "target": 5,
                "start_date": "2099-12-31",
                "end_date": today,
            }
        )
    with pytest.raises(ValidationError):
        desk.update_goal(goal, {"target_date": today})


def test_schedule_rejects_overlap_and_invalid_window(desk, today):
    first = desk.add_task({"title": "First", "minutes": 60})
    second = desk.add_task({"title": "Second", "minutes": 45})
    desk.schedule_task(today, {"task_id": first, "start": "09:00"})
    with pytest.raises(ValidationError):
        desk.schedule_task(today, {"task_id": second, "start": "09:30"})
    with pytest.raises(ValidationError):
        desk.schedule_task(today, {"task_id": second, "start": "17:45"})
    with pytest.raises(ValidationError):
        desk.set_day(today, {"start": "09:30", "end": "18:00"})
    desk.schedule_task(today, {"task_id": second, "start": "10:00"})
    assert len(desk.snapshot()["blocks"]) == 2


def test_auto_schedule_preserves_existing_blocks_and_reports_unplaced(desk, today):
    desk.set_day(today, {"start": "09:00", "end": "11:00"})
    fixed = desk.add_task({"title": "Fixed", "minutes": 30})
    desk.schedule_task(today, {"task_id": fixed, "start": "10:00"})
    too_big = desk.add_task({"title": "Too large", "minutes": 90, "priority": 3})
    urgent = desk.add_task({"title": "Urgent", "minutes": 45, "due_date": today})
    short = desk.add_task({"title": "Short", "minutes": 30})
    result = desk.auto_plan(today)
    blocks = {b["task_id"]: b for b in desk.snapshot()["blocks"]}
    assert result == {"scheduled": 2, "unplaced": 1}
    assert blocks[fixed]["start"] == 600
    assert blocks[urgent]["start"] == 540
    assert blocks[short]["start"] == 630
    assert too_big not in blocks
    assert desk.auto_plan(today) == {"scheduled": 0, "unplaced": 1}


def test_concurrent_scheduling_cannot_double_book(desk, today):
    tasks = [desk.add_task({"title": str(i)}) for i in range(2)]

    def attempt(task_id):
        try:
            desk.schedule_task(today, {"task_id": task_id, "start": "09:00"})
            return True
        except ValidationError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(attempt, tasks)) == 1
    assert len(desk.snapshot()["blocks"]) == 1


def test_task_edit_cannot_desynchronize_scheduled_duration(desk, today):
    task = desk.add_task({"title": "Study", "minutes": 60})
    desk.schedule_task(today, {"task_id": task, "start": "09:00"})
    with pytest.raises(ValidationError):
        desk.update_task(task, {"minutes": 120})
    desk.update_task(task, {"title": "Revised title"})
    desk.delete_task(task)
    assert desk.snapshot()["blocks"] == []


def test_persistence_survives_new_service_instance(desk):
    desk.add_task({"title": "Persistent"})
    reopened = Workbench(desk.db.path)
    assert reopened.snapshot()["tasks"][0]["title"] == "Persistent"


def test_reports_separate_planned_and_recorded_time(desk, today, tmp_path):
    task = desk.add_task({"title": '=HYPERLINK("bad")', "minutes": 60})
    desk.schedule_task(today, {"task_id": task, "start": "09:00"})
    desk.complete_task(task, {"done": True, "actual_minutes": 45})
    report = weekly_report(desk, today)
    assert report["actual_minutes"] == 45
    assert report["planned_minutes"] == 60
    assert report["estimate_difference"] == -15
    assert report["completed"] == 1
    csv, _, _ = export_content(desk, "csv", today)
    assert "'=HYPERLINK" in csv
    files = save_report(desk, tmp_path / "reports", today)
    assert {file.suffix for file in files} == {".csv", ".md", ".svg"}
    assert all(file.stat().st_size > 0 for file in files)


def test_demo_is_separate_idempotent_and_refuses_personal_data(desk):
    desk.add_task({"title": "Real task"})
    with pytest.raises(ValidationError):
        seed_demo(desk)


def test_seed_demo_is_idempotent(desk):
    seed_demo(desk)
    first = desk.snapshot()
    seed_demo(desk)
    second = desk.snapshot()
    assert first == second
    assert first["goals"][0]["earned"] == 24
