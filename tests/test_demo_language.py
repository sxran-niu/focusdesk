"""English demo upgrades must preserve personal edits and planning state."""

from focusdesk.demo import seed_demo
from focusdesk.demo_legacy import upgrade_demo_language


def table_snapshot(desk):
    tables = desk.db.rows("SELECT name FROM sqlite_master WHERE type='table'")
    return {row["name"]: desk.db.rows(f"SELECT * FROM {row['name']}") for row in tables}


def test_new_demo_is_english_and_repeated_seed_preserves_edits(desk):
    seed_demo(desk)
    assert desk.snapshot()["goals"][0]["unit"] == "credits"
    assert desk.snapshot()["tasks"][0]["title"] == "Implement task persistence"
    desk.update_task(1, {"title": "My edited task"})
    before = table_snapshot(desk)
    seed_demo(desk)
    assert table_snapshot(desk) == before


def test_legacy_demo_translates_stock_fields_only(desk, today):
    seed_demo(desk)
    stock_title = "\u5b8c\u6210\u4efb\u52a1\u4fdd\u5b58\u6a21\u5757"
    with desk.db.connect(write=True) as connection:
        connection.execute("DELETE FROM metadata WHERE key='demo_language'")
        connection.execute("UPDATE tasks SET title=? WHERE id=1", (stock_title,))
        connection.execute("UPDATE goals SET unit=? WHERE id=1", ("\u5b66\u5206",))
    desk.update_task(2, {"title": "My own reading plan", "notes": "Keep my notes"})
    added = desk.add_task({"title": stock_title, "minutes": 30})
    desk.complete_task(1, {"done": True, "actual_minutes": 55})
    desk.record_outcome(2, {"status": "passed", "result_date": today})
    before = table_snapshot(desk)
    seed_demo(desk)
    after = table_snapshot(desk)
    assert after["tasks"][0]["title"] == "Implement task persistence"
    assert next(t for t in after["tasks"] if t["id"] == added)["title"] == stock_title
    assert after["goals"][0]["unit"] == "credits"
    # An exact comparison covers IDs, dates, credits, completed work, notes,
    # appointments, user-created tasks, relationships, and all audit records.
    after["tasks"][0]["title"] = stock_title
    after["goals"][0]["unit"] = "\u5b66\u5206"
    after["metadata"] = [r for r in after["metadata"] if r["key"] != "demo_language"]
    assert after == before
    once = table_snapshot(desk)
    seed_demo(desk)
    assert table_snapshot(desk) == once


def test_personal_data_is_never_translated(desk):
    desk.add_task({"title": "\u5b8c\u6210\u4efb\u52a1\u4fdd\u5b58\u6a21\u5757"})
    before = table_snapshot(desk)
    upgrade_demo_language(desk)
    assert table_snapshot(desk) == before
