"""Application rules shared by the command line and the web interface."""

import json
from dataclasses import asdict
from datetime import date, datetime

from .database import Database
from .models import (
    Task,
    ValidationError,
    clock_minutes,
    day,
    integer,
    number,
    text,
)
from .planner import free_intervals, suggest_schedule
from .recurring import RecurringCalendar, occupied
from .weekly import week_start


class Workbench:
    """Manage actions, plans and verified results without conflating their metrics."""

    def __init__(self, path):
        self.db = Database(path)
        self.calendar = RecurringCalendar(self.db)

    def require(self, table, record_id, connection=None):
        record_id = integer(record_id, "Record ID")
        query = f"SELECT * FROM {table} WHERE id = ?"
        rows = (
            connection.execute(query, (record_id,)).fetchall()
            if connection
            else self.db.rows(query, (record_id,))
        )
        if not rows:
            raise ValidationError(
                "This record no longer exists. Refresh the page and try again."
            )
        return dict(rows[0])

    def add_goal(self, data):
        return self.db.insert(
            "goals",
            {
                "title": text(data.get("title"), "Goal name"),
                "target": number(data.get("target"), "Goal target", 0.01),
                "unit": text(data.get("unit", "credits"), "Unit", 20),
                "target_date": day(data.get("target_date"), "Goal date"),
                "notes": text(data.get("notes", ""), "Completion notes", 2000, True),
            },
        )

    def add_milestone(self, data):
        goal = self.require("goals", data.get("goal_id"))
        if goal["archived"]:
            raise ValidationError("Unarchive this goal before editing its contents.")
        start = day(data.get("start_date"), "Stage start date")
        end = day(data.get("end_date"), "Stage end date")
        if start > end or end > goal["target_date"]:
            raise ValidationError(
                "Stage dates must be in order and must not end after the goal date."
            )
        target = number(data.get("target"), "Stage target", 0.01)
        return self.db.insert(
            "milestones",
            {
                "goal_id": goal["id"],
                "title": text(data.get("title"), "Stage name"),
                "start_date": start,
                "end_date": end,
                "target": target,
                "original_target": target,
            },
        )

    def update_goal(self, record_id, data):
        old = self.require("goals", record_id)
        if old["archived"]:
            raise ValidationError("Unarchive this goal before editing its contents.")
        values = {
            "title": text(data.get("title", old["title"]), "Goal name"),
            "target": number(data.get("target", old["target"]), "Goal target", 0.01),
            "unit": text(data.get("unit", old["unit"]), "Unit", 20),
            "target_date": day(data.get("target_date", old["target_date"])),
            "notes": text(
                data.get("notes", old["notes"]), "Completion notes", 2000, True
            ),
        }
        with self.db.connect(write=True) as connection:
            later = connection.execute(
                "SELECT 1 FROM milestones WHERE goal_id=? AND end_date>?",
                (record_id, values["target_date"]),
            ).fetchone()
            if later:
                raise ValidationError(
                    "The goal date cannot be earlier than an existing stage end date."
                )
            if (
                values["unit"] != old["unit"]
                and connection.execute(
                    "SELECT 1 FROM milestones WHERE goal_id=?", (record_id,)
                ).fetchone()
            ):
                raise ValidationError(
                    "The unit cannot change once stages exist. Create "
                    "a new goal instead."
                )
            connection.execute(
                "UPDATE goals SET title=?,target=?,unit=?,target_date=?,notes=? "
                "WHERE id=?",
                (*values.values(), record_id),
            )
            if old["target"] != values["target"]:
                connection.execute(
                    "INSERT INTO changes(entity,entity_id,old_value,new_value) "
                    "VALUES('goal',?,?,?)",
                    (record_id, str(old["target"]), str(values["target"])),
                )

    def revise_milestone(self, record_id, data):
        with self.db.connect(write=True) as connection:
            old = self.require("milestones", record_id, connection)
            goal = self._active_goal(connection, old["goal_id"])
            target = number(data.get("target", old["target"]), "Stage target", 0.01)
            details = {
                "title": text(data.get("title", old["title"]), "Stage name"),
                "start_date": day(data.get("start_date", old["start_date"])),
                "end_date": day(data.get("end_date", old["end_date"])),
            }
            if (
                details["start_date"] > details["end_date"]
                or details["end_date"] > goal["target_date"]
            ):
                raise ValidationError(
                    "Stage dates must be in order and must not end after the goal date."
                )
            previous = {key: old[key] for key in details}
            if details != previous:
                self._change(
                    connection, "milestone_details", record_id, previous, details
                )
                connection.execute(
                    "UPDATE milestones SET title=?,start_date=?,end_date=? WHERE id=?",
                    (*details.values(), record_id),
                )
            if old["target"] != target:
                connection.execute(
                    "INSERT INTO changes(entity, entity_id, old_value, new_value) "
                    "VALUES ('milestone', ?, ?, ?)",
                    (record_id, str(old["target"]), str(target)),
                )
                connection.execute(
                    "UPDATE milestones SET target = ? WHERE id = ?", (target, record_id)
                )

    def add_outcome(self, data):
        milestone = self.require("milestones", data.get("milestone_id"))
        if self.require("goals", milestone["goal_id"])["archived"]:
            raise ValidationError("Unarchive this goal before editing its contents.")
        return self.db.insert(
            "outcomes",
            {
                "milestone_id": milestone["id"],
                "title": text(data.get("title"), "Course or outcome name"),
                "amount": number(data.get("amount"), "Outcome amount", 0.01),
            },
        )

    def record_outcome(self, record_id, data):
        status = data.get("status")
        if status not in ("pending", "passed", "failed"):
            raise ValidationError("Invalid outcome status.")
        result_date = day(data.get("result_date"), "Confirmation date", optional=True)
        if status != "pending" and not result_date:
            raise ValidationError(
                "Enter the result or confirmation date when confirming an outcome."
            )
        if result_date and result_date > date.today().isoformat():
            raise ValidationError("The confirmation date cannot be in the future.")
        values = {
            "status": status,
            "result_date": None if status == "pending" else result_date,
            "grade": text(data.get("grade", ""), "Grade", 40, True),
            "notes": text(data.get("notes", ""), "Outcome notes", 2000, True),
        }
        with self.db.connect(write=True) as connection:
            old = self.require("outcomes", record_id, connection)
            milestone = self.require("milestones", old["milestone_id"], connection)
            self._active_goal(connection, milestone["goal_id"])
            previous = {key: old[key] for key in values}
            if previous != values:
                connection.execute(
                    "INSERT INTO changes(entity, entity_id, old_value, new_value) "
                    "VALUES ('outcome', ?, ?, ?)",
                    (record_id, json.dumps(previous), json.dumps(values)),
                )
                connection.execute(
                    "UPDATE outcomes SET status=?, result_date=?, grade=?, notes=? "
                    "WHERE id=?",
                    (*values.values(), record_id),
                )

    def update_outcome(self, record_id, data):
        with self.db.connect(write=True) as connection:
            old = self.require("outcomes", record_id, connection)
            current = self.require("milestones", old["milestone_id"], connection)
            self._active_goal(connection, current["goal_id"])
            destination = self.require(
                "milestones", data.get("milestone_id", old["milestone_id"]), connection
            )
            if destination["goal_id"] != current["goal_id"]:
                raise ValidationError(
                    "Courses can only move between stages of the same goal."
                )
            title = text(data.get("title", old["title"]), "Course or outcome name")
            amount = number(data.get("amount", old["amount"]), "Outcome amount", 0.01)
            if old["status"] == "passed" and amount != old["amount"]:
                raise ValidationError(
                    "Set the outcome back to pending before changing "
                    "its confirmed amount."
                )
            connection.execute(
                "UPDATE outcomes SET title=?,amount=?,milestone_id=? WHERE id=?",
                (title, amount, destination["id"], record_id),
            )
            previous = {key: old[key] for key in ("title", "amount", "milestone_id")}
            values = {
                "title": title,
                "amount": amount,
                "milestone_id": destination["id"],
            }
            if previous != values:
                self._change(connection, "outcome_details", record_id, previous, values)

    def add_requirement(self, data):
        goal = self.require("goals", data.get("goal_id"))
        if goal["archived"]:
            raise ValidationError("Unarchive this goal before editing its contents.")
        return self.db.insert(
            "requirements",
            {
                "goal_id": goal["id"],
                "title": text(data.get("title"), "Completion condition"),
            },
        )

    def set_requirement(self, record_id, done):
        if not isinstance(done, bool):
            raise ValidationError("Invalid completion status.")
        with self.db.connect(write=True) as connection:
            requirement = self.require("requirements", record_id, connection)
            self._active_goal(connection, requirement["goal_id"])
            connection.execute(
                "UPDATE requirements SET done=? WHERE id=?", (int(done), record_id)
            )

    def add_task(self, data):
        data = {"title": None, **data}
        task = Task(
            **{
                key: value
                for key, value in data.items()
                if key in Task.__dataclass_fields__
            }
        )
        if task.outcome_id:
            self.require("outcomes", task.outcome_id)
        return self.db.insert("tasks", asdict(task))

    def update_task(self, record_id, data):
        old = self.require("tasks", record_id)
        values = {key: data.get(key, old[key]) for key in Task.__dataclass_fields__}
        task = Task(**values)
        if task.outcome_id:
            self.require("outcomes", task.outcome_id)
        with self.db.connect(write=True) as connection:
            blocks = connection.execute(
                "SELECT 1 FROM blocks WHERE task_id=?", (record_id,)
            ).fetchall()
            if blocks and old["minutes"] != task.minutes:
                raise ValidationError(
                    "Remove this task from the schedule before changing its estimate."
                )
            connection.execute(
                "UPDATE tasks SET title=?,category=?,minutes=?,priority=?,"
                "due_date=?,outcome_id=?,notes=? WHERE id=?",
                (*asdict(task).values(), record_id),
            )

    def complete_task(self, record_id, data):
        done = data.get("done")
        if not isinstance(done, bool):
            raise ValidationError("Invalid completion status.")
        with self.db.connect(write=True) as connection:
            old = self.require("tasks", record_id, connection)
            # Repeated completion calls must not change its date or count work twice.
            if done and old["status"] == "done":
                return
            actual = (
                integer(
                    data.get("actual_minutes", old["minutes"]),
                    "Actual minutes",
                    0,
                    1440,
                )
                if done
                else None
            )
            connection.execute(
                "UPDATE tasks SET status=?, completed_at=?, actual_minutes=? "
                "WHERE id=?",
                (
                    "done" if done else "open",
                    datetime.now().astimezone().isoformat() if done else None,
                    actual,
                    record_id,
                ),
            )

    def delete_task(self, record_id):
        with self.db.connect(write=True) as connection:
            self.require("tasks", record_id, connection)
            connection.execute(
                "INSERT INTO metadata(key,value) VALUES('retired_task_id',?) "
                "ON CONFLICT(key) DO UPDATE SET value="
                "max(cast(value AS INTEGER),cast(excluded.value AS INTEGER))",
                (record_id,),
            )
            connection.execute("DELETE FROM tasks WHERE id=?", (record_id,))

    def _active_goal(self, connection, goal_id):
        goal = self.require("goals", goal_id, connection)
        if goal["archived"]:
            raise ValidationError("Unarchive this goal before editing its contents.")
        return goal

    def _change(self, connection, entity, entity_id, old, new):
        connection.execute(
            "INSERT INTO changes(entity,entity_id,old_value,new_value) VALUES(?,?,?,?)",
            (entity, entity_id, json.dumps(old), json.dumps(new)),
        )

    def archive_goal(self, record_id, archived):
        """Hide a completed goal without deleting or duplicating its outcomes."""
        if not isinstance(archived, bool):
            raise ValidationError("Invalid archive status.")
        with self.db.connect(write=True) as connection:
            old = self.require("goals", record_id, connection)
            if archived:
                earned = connection.execute(
                    "SELECT coalesce(sum(o.amount),0) FROM outcomes o "
                    "JOIN milestones m "
                    "ON o.milestone_id=m.id WHERE m.goal_id=? AND o.status='passed'",
                    (record_id,),
                ).fetchone()[0]
                pending = connection.execute(
                    "SELECT 1 FROM requirements WHERE goal_id=? AND done=0",
                    (record_id,),
                ).fetchone()
                if round(earned, 2) < old["target"] or pending:
                    raise ValidationError(
                        "Meet the quantity target and all additional "
                        "conditions before archiving."
                    )
            if bool(old["archived"]) != archived:
                connection.execute(
                    "UPDATE goals SET archived=? WHERE id=?", (int(archived), record_id)
                )
                self._change(
                    connection, "archive", record_id, bool(old["archived"]), archived
                )

    def day_settings(self, selected_date):
        day(selected_date)
        rows = self.db.rows("SELECT * FROM day_settings WHERE date=?", (selected_date,))
        return rows[0] if rows else {"date": selected_date, "start": 540, "end": 1080}

    def set_day(self, selected_date, data):
        day(selected_date)
        start, end = clock_minutes(data.get("start")), clock_minutes(data.get("end"))
        if end <= start:
            raise ValidationError(
                "The end time must follow the start time. Overnight "
                "appointments are not supported."
            )
        with self.db.connect(write=True) as connection:
            outside = any(
                b["start"] < start or b["end"] > end
                for b in occupied(connection, selected_date)
            )
            if outside:
                raise ValidationError(
                    "Existing appointments fall outside these hours. "
                    "Move or remove them first."
                )
            connection.execute(
                "INSERT INTO day_settings VALUES(?,?,?) ON CONFLICT(date) DO UPDATE "
                "SET start=excluded.start,end=excluded.end",
                (selected_date, start, end),
            )

    def schedule_task(self, selected_date, data):
        day(selected_date)
        start = clock_minutes(data.get("start"))
        with self.db.connect(write=True) as connection:
            task = self.require("tasks", data.get("task_id"), connection)
            if task["status"] == "done":
                raise ValidationError(
                    "Completed tasks do not need to be scheduled again."
                )
            settings = connection.execute(
                "SELECT * FROM day_settings WHERE date=?", (selected_date,)
            ).fetchone() or {"start": 540, "end": 1080}
            end = start + task["minutes"]
            if start < settings["start"] or end > settings["end"]:
                raise ValidationError(
                    "This task falls outside the available hours for this day."
                )
            exists = connection.execute(
                "SELECT 1 FROM blocks WHERE task_id=?", (task["id"],)
            ).fetchone()
            if exists:
                raise ValidationError(
                    "This task is already scheduled. Move or remove "
                    "its existing appointment first."
                )
            overlap = any(
                b["start"] < end and b["end"] > start
                for b in occupied(connection, selected_date)
            )
            if overlap:
                raise ValidationError(
                    "This time overlaps an existing appointment. Choose a free slot."
                )
            connection.execute(
                "INSERT INTO blocks(date,task_id,start,end) VALUES(?,?,?,?)",
                (selected_date, task["id"], start, end),
            )

    def unschedule(self, record_id):
        with self.db.connect(write=True) as connection:
            old = self.require("blocks", record_id, connection)
            self._schedule_change(connection, old, None)
            connection.execute("DELETE FROM blocks WHERE id=?", (record_id,))

    def _schedule_change(self, connection, old, new):
        """Retain the previous appointment when explicitly moving/removing it."""
        connection.execute(
            "INSERT INTO changes(entity,entity_id,old_value,new_value) "
            "VALUES('schedule',?,?,?)",
            (old["task_id"], json.dumps(old), json.dumps(new)),
        )

    def reschedule(self, record_id, data):
        """Move an open task atomically; conflicts leave its old block intact."""
        selected_date = day(data.get("date"))
        start = clock_minutes(data.get("start"))
        with self.db.connect(write=True) as connection:
            old = self.require("blocks", record_id, connection)
            task = self.require("tasks", old["task_id"], connection)
            if task["status"] != "open":
                raise ValidationError(
                    "Reopen this completed task before moving its appointment."
                )
            settings = connection.execute(
                "SELECT * FROM day_settings WHERE date=?", (selected_date,)
            ).fetchone() or {"start": 540, "end": 1080}
            end = start + task["minutes"]
            if start < settings["start"] or end > settings["end"]:
                raise ValidationError(
                    "This task falls outside the available hours on "
                    "the destination date."
                )
            overlap = any(
                b["start"] < end and b["end"] > start
                for b in occupied(connection, selected_date, record_id)
            )
            if overlap:
                raise ValidationError(
                    "This time overlaps an existing appointment. Choose a free slot."
                )
            new = {**old, "date": selected_date, "start": start, "end": end}
            if new == old:
                return
            connection.execute(
                "UPDATE blocks SET date=?,start=?,end=? WHERE id=?",
                (selected_date, start, end, record_id),
            )
            self._schedule_change(connection, old, new)

    def auto_plan(self, selected_date):
        day(selected_date)
        with self.db.connect(write=True) as connection:
            settings = connection.execute(
                "SELECT * FROM day_settings WHERE date=?", (selected_date,)
            ).fetchone() or {"start": 540, "end": 1080}
            existing = occupied(connection, selected_date)
            candidates = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM tasks WHERE status='open' AND id NOT IN "
                    "(SELECT task_id FROM blocks)"
                )
            ]
            scheduled, unplaced = suggest_schedule(
                candidates, settings["start"], settings["end"], existing
            )
            connection.executemany(
                "INSERT INTO blocks(date,task_id,start,end) VALUES(?,?,?,?)",
                [
                    (selected_date, block.task_id, block.start, block.end)
                    for block in scheduled
                ],
            )
        return {"scheduled": len(scheduled), "unplaced": len(unplaced)}

    def set_weekly_target(self, selected_date, outcome_id, data):
        """Set one explicit effort target per course and Monday–Sunday week."""
        start = week_start(selected_date)
        minutes = integer(data.get("minutes"), "Weekly target in minutes", 0, 10080)
        with self.db.connect(write=True) as connection:
            outcome = self.require("outcomes", outcome_id, connection)
            milestone = self.require("milestones", outcome["milestone_id"], connection)
            self._active_goal(connection, milestone["goal_id"])
            connection.execute(
                "INSERT INTO weekly_targets VALUES(?,?,?) "
                "ON CONFLICT(week_start,outcome_id) DO UPDATE "
                "SET minutes=excluded.minutes",
                (start, outcome_id, minutes),
            )

    def snapshot(self, selected_date=None):
        """Read a consistent snapshot; recompute progress from unique outcome rows."""
        selected_date = day(selected_date or date.today().isoformat())
        with self.db.connect() as connection:
            connection.execute("BEGIN")
            data = {
                table: [
                    dict(row)
                    for row in connection.execute(
                        f"SELECT * FROM {table} ORDER BY rowid"
                    )
                ]
                for table in (
                    "goals",
                    "milestones",
                    "outcomes",
                    "requirements",
                    "tasks",
                    "blocks",
                    "changes",
                    "weekly_targets",
                    "day_settings",
                    "recurring_rules",
                    "fixed_blocks",
                )
            }
            settings = connection.execute(
                "SELECT * FROM day_settings WHERE date=?", (selected_date,)
            ).fetchone()
        data["day"] = (
            dict(settings)
            if settings
            else {"date": selected_date, "start": 540, "end": 1080}
        )
        for milestone in data["milestones"]:
            outcomes = [
                o for o in data["outcomes"] if o["milestone_id"] == milestone["id"]
            ]
            milestone["earned"] = round(
                sum(o["amount"] for o in outcomes if o["status"] == "passed"), 2
            )
            milestone["pending"] = round(
                sum(o["amount"] for o in outcomes if o["status"] == "pending"), 2
            )
        for goal in data["goals"]:
            milestones = [m for m in data["milestones"] if m["goal_id"] == goal["id"]]
            goal["earned"] = round(sum(m["earned"] for m in milestones), 2)
            goal["planned"] = round(sum(m["target"] for m in milestones), 2)
            goal["pending"] = round(sum(m["pending"] for m in milestones), 2)
            requirements = [
                r for r in data["requirements"] if r["goal_id"] == goal["id"]
            ]
            goal["conditions_met"] = all(r["done"] for r in requirements)
            goal["achieved"] = (
                goal["earned"] >= goal["target"] and goal["conditions_met"]
            )
        for block in data["fixed_blocks"]:
            rule = next(
                r for r in data["recurring_rules"] if r["id"] == block["rule_id"]
            )
            block.update(title=rule["title"], category=rule["category"])
        today_blocks = [
            b
            for b in data["blocks"] + data["fixed_blocks"]
            if b["date"] == selected_date
        ]
        data["gaps"] = free_intervals(
            data["day"]["start"], data["day"]["end"], today_blocks
        )
        data["today"] = date.today().isoformat()
        open_ids = {t["id"] for t in data["tasks"] if t["status"] == "open"}
        data["carryover"] = sorted(
            (
                b
                for b in data["blocks"]
                if b["date"] < selected_date and b["task_id"] in open_ids
            ),
            key=lambda b: (b["date"], b["start"]),
        )
        return data
