"""Round trips, invalid input, and recoverable replacement of existing data."""

import json
import sqlite3

import pytest

import focusdesk.backup as backup_module
from focusdesk import ValidationError
from focusdesk.backup import BackupStore
from focusdesk.demo import seed_demo
from focusdesk.web import create_app


def test_backup_roundtrip_and_recovery_copy(desk, course, today):
    task = desk.add_task({"title": "Original", "outcome_id": course[2]})
    desk.schedule_task(today, {"task_id": task, "start": "09:00"})
    desk.set_weekly_target(today, course[2], {"minutes": 360})
    desk.record_outcome(course[2], {"status": "passed", "result_date": today})
    desk.archive_goal(course[0], True)
    store = BackupStore(desk)
    original = store.export()
    desk.add_task({"title": "Keep in recovery copy"})
    filename = store.restore(original)
    assert filename in store.list_files()
    assert desk.snapshot()["goals"][0]["earned"] == 6
    assert desk.snapshot()["goals"][0]["archived"] == 1
    assert len(desk.snapshot()["tasks"]) == 1
    assert desk.snapshot()["tasks"][0]["outcome_id"] == course[2]
    previous = json.loads(store.file_path(filename).read_text())
    assert len(previous["tables"]["tasks"]) == 2
    store.restore(previous)
    assert len(desk.snapshot()["tasks"]) == 2
    assert len(store.list_files()) == 2


@pytest.mark.parametrize(
    "corruption",
    ["foreign_key", "task", "date", "overlap", "version", "field", "space", "nan"],
)
def test_invalid_backup_does_not_touch_current_data(desk, course, today, corruption):
    task = desk.add_task({"title": "Keep me", "outcome_id": course[2]})
    second = desk.add_task({"title": "Also keep"})
    desk.schedule_task(today, {"task_id": task, "start": "09:00"})
    desk.schedule_task(today, {"task_id": second, "start": "10:00"})
    store = BackupStore(desk)
    backup = store.export()
    tables = backup["tables"]
    if corruption == "foreign_key":
        tables["tasks"][0]["outcome_id"] = 999
    elif corruption == "task":
        tables["tasks"][0]["category"] = "bad"
    elif corruption == "date":
        tables["milestones"][0]["end_date"] = "invalid"
    elif corruption == "overlap":
        tables["blocks"][1].update(start=570, end=630)
    elif corruption == "version":
        backup["version"] = 99
    elif corruption == "field":
        tables["goals"][0]["unexpected"] = "value"
    elif corruption == "space":
        backup["space"] = "demo"
    elif corruption == "nan":
        tables["goals"][0]["target"] = float("nan")
    before = desk.snapshot()
    with pytest.raises(ValidationError):
        store.restore(backup)
    assert desk.snapshot() == before
    assert store.list_files() == []


def test_demo_backup_includes_new_schema_and_cannot_cross_spaces(desk, tmp_path):
    seed_demo(desk)
    store = BackupStore(desk)
    backup = store.export()
    store.restore(backup)
    assert desk.snapshot()["goals"][0]["earned"] == 24
    from focusdesk import Workbench

    with pytest.raises(ValidationError, match="cannot be restored"):
        BackupStore(Workbench(tmp_path / "personal.sqlite3")).restore(backup)


def test_restore_needs_csrf_and_confirmation_and_copy_can_be_downloaded(tmp_path):
    app = create_app(tmp_path / "web.sqlite3")
    client = app.test_client()
    headers = {"X-FocusDesk-Token": app.config["CSRF_TOKEN"]}
    backup = client.get("/api/backup").json
    assert client.post("/api/restore", json={"backup": backup}).status_code == 403
    assert (
        client.post(
            "/api/restore", json={"backup": backup}, headers=headers
        ).status_code
        == 400
    )
    response = client.post(
        "/api/restore",
        json={"backup": backup, "confirmation": "RESTORE"},
        headers=headers,
    )
    assert response.status_code == 200
    filename = response.json["recovery_copy"]
    copy = client.get(f"/api/backups/{filename}")
    assert copy.status_code == 200
    assert copy.json["format"] == "focusdesk-backup"
    assert filename in client.get("/api/backups").json["files"]
    assert client.get("/api/backups/unknown.json").status_code == 400


def test_failed_recovery_copy_write_prevents_restore(desk, monkeypatch):
    store = BackupStore(desk)
    backup = store.export()
    desk.add_task({"title": "Must remain"})
    before = desk.snapshot()

    def fail(*args, **kwargs):
        raise PermissionError("Unavailable backup storage")

    # tempfile also uses os.open, so fail only writes to the recovery directory.
    original = backup_module.os.open

    def selective_fail(path, *args, **kwargs):
        if str(path).startswith(str(store.directory)):
            return fail()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(backup_module.os, "open", selective_fail)
    with pytest.raises(PermissionError):
        store.restore(backup)
    assert desk.snapshot() == before


def test_restore_transaction_rolls_back_if_live_insert_fails(desk, monkeypatch):
    store = BackupStore(desk)
    backup = store.export()
    desk.add_task({"title": "Must remain after rollback"})
    before = desk.snapshot()
    original = backup_module._insert
    calls = 0

    def fail_live_insert(connection, tables):
        nonlocal calls
        calls += 1
        original(connection, tables)
        if calls == 2:
            raise sqlite3.OperationalError("Simulated failure after live replacement")

    monkeypatch.setattr(backup_module, "_insert", fail_live_insert)
    with pytest.raises(sqlite3.OperationalError):
        store.restore(backup)
    assert desk.snapshot() == before
    assert len(store.list_files()) == 1


def test_recurring_and_move_history_roundtrip(desk, today):
    from datetime import date, timedelta

    selected = date.fromisoformat(today)
    desk.calendar.add(
        {
            "title": "Fixed",
            "category": "life",
            "weekday": selected.weekday(),
            "start_date": today,
            "end_date": (selected + timedelta(days=14)).isoformat(),
            "start": "09:00",
            "end": "10:00",
        }
    )
    task = desk.add_task({"title": "Move"})
    desk.schedule_task(today, {"task_id": task, "start": "10:00"})
    block = desk.snapshot()["blocks"][0]
    desk.reschedule(block["id"], {"date": today, "start": "11:00"})
    store = BackupStore(desk)
    backup = store.export()
    store.restore(backup)
    assert len(desk.snapshot()["fixed_blocks"]) == 3
    assert desk.snapshot()["blocks"][0]["start"] == 660
    assert desk.snapshot()["changes"][0]["entity"] == "schedule"
