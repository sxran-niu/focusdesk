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
from .weekly import week_start


class Workbench:
    """Manage actions, plans and verified results without conflating their metrics."""

    def __init__(self, path):
        self.db = Database(path)

    def require(self, table, record_id, connection=None):
        record_id = integer(record_id, "记录编号")
        query = f"SELECT * FROM {table} WHERE id = ?"
        rows = (
            connection.execute(query, (record_id,)).fetchall()
            if connection
            else self.db.rows(query, (record_id,))
        )
        if not rows:
            raise ValidationError("记录不存在，可能已被删除，请刷新后重试。")
        return dict(rows[0])

    def add_goal(self, data):
        return self.db.insert(
            "goals",
            {
                "title": text(data.get("title"), "目标名称"),
                "target": number(data.get("target"), "目标数量", 0.01),
                "unit": text(data.get("unit", "学分"), "计量单位", 20),
                "target_date": day(data.get("target_date"), "目标日期"),
                "notes": text(data.get("notes", ""), "完成条件说明", 2000, True),
            },
        )

    def add_milestone(self, data):
        goal = self.require("goals", data.get("goal_id"))
        start = day(data.get("start_date"), "阶段开始日期")
        end = day(data.get("end_date"), "阶段结束日期")
        if start > end or end > goal["target_date"]:
            raise ValidationError("阶段日期需按先后排列，且不晚于目标日期。")
        target = number(data.get("target"), "阶段目标", 0.01)
        return self.db.insert(
            "milestones",
            {
                "goal_id": goal["id"],
                "title": text(data.get("title"), "阶段名称"),
                "start_date": start,
                "end_date": end,
                "target": target,
                "original_target": target,
            },
        )

    def update_goal(self, record_id, data):
        old = self.require("goals", record_id)
        values = {
            "title": text(data.get("title", old["title"]), "目标名称"),
            "target": number(data.get("target", old["target"]), "目标数量", 0.01),
            "unit": text(data.get("unit", old["unit"]), "计量单位", 20),
            "target_date": day(data.get("target_date", old["target_date"])),
            "notes": text(data.get("notes", old["notes"]), "完成条件说明", 2000, True),
        }
        with self.db.connect(write=True) as connection:
            later = connection.execute(
                "SELECT 1 FROM milestones WHERE goal_id=? AND end_date>?",
                (record_id, values["target_date"]),
            ).fetchone()
            if later:
                raise ValidationError("目标日期不能早于已有阶段的结束日期。")
            if (
                values["unit"] != old["unit"]
                and connection.execute(
                    "SELECT 1 FROM milestones WHERE goal_id=?", (record_id,)
                ).fetchone()
            ):
                raise ValidationError("已有阶段时不能更改计量单位，请创建新目标。")
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
        target = number(data.get("target"), "阶段目标", 0.01)
        with self.db.connect(write=True) as connection:
            old = self.require("milestones", record_id, connection)
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
        return self.db.insert(
            "outcomes",
            {
                "milestone_id": milestone["id"],
                "title": text(data.get("title"), "课程或成果名称"),
                "amount": number(data.get("amount"), "成果数量", 0.01),
            },
        )

    def record_outcome(self, record_id, data):
        status = data.get("status")
        if status not in ("pending", "passed", "failed"):
            raise ValidationError("成果状态无效。")
        result_date = day(data.get("result_date"), "确认日期", optional=True)
        if status != "pending" and not result_date:
            raise ValidationError("确认成果时请填写出分或确认日期。")
        if result_date and result_date > date.today().isoformat():
            raise ValidationError("确认日期不能晚于今天。")
        values = {
            "status": status,
            "result_date": None if status == "pending" else result_date,
            "grade": text(data.get("grade", ""), "成绩", 40, True),
            "notes": text(data.get("notes", ""), "成果备注", 2000, True),
        }
        with self.db.connect(write=True) as connection:
            old = self.require("outcomes", record_id, connection)
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
            title = text(data.get("title", old["title"]), "课程或成果名称")
            amount = number(data.get("amount", old["amount"]), "成果数量", 0.01)
            if old["status"] == "passed" and amount != old["amount"]:
                raise ValidationError("修改已确认的数量前，请先将成果恢复为待确认。")
            connection.execute(
                "UPDATE outcomes SET title=?,amount=? WHERE id=?",
                (title, amount, record_id),
            )

    def add_requirement(self, data):
        goal = self.require("goals", data.get("goal_id"))
        return self.db.insert(
            "requirements",
            {
                "goal_id": goal["id"],
                "title": text(data.get("title"), "完成条件"),
            },
        )

    def set_requirement(self, record_id, done):
        if not isinstance(done, bool):
            raise ValidationError("完成状态无效。")
        with self.db.connect(write=True) as connection:
            self.require("requirements", record_id, connection)
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
                raise ValidationError("请先移出日程，再修改预计用时。")
            connection.execute(
                "UPDATE tasks SET title=?,category=?,minutes=?,priority=?,"
                "due_date=?,outcome_id=?,notes=? WHERE id=?",
                (*asdict(task).values(), record_id),
            )

    def complete_task(self, record_id, data):
        done = data.get("done")
        if not isinstance(done, bool):
            raise ValidationError("完成状态无效。")
        with self.db.connect(write=True) as connection:
            old = self.require("tasks", record_id, connection)
            # Repeated completion calls must not change its date or count work twice.
            if done and old["status"] == "done":
                return
            actual = (
                integer(data.get("actual_minutes", old["minutes"]), "实际用时", 0, 1440)
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
            connection.execute("DELETE FROM tasks WHERE id=?", (record_id,))

    def day_settings(self, selected_date):
        day(selected_date)
        rows = self.db.rows("SELECT * FROM day_settings WHERE date=?", (selected_date,))
        return rows[0] if rows else {"date": selected_date, "start": 540, "end": 1080}

    def set_day(self, selected_date, data):
        day(selected_date)
        start, end = clock_minutes(data.get("start")), clock_minutes(data.get("end"))
        if end <= start:
            raise ValidationError("结束时间必须晚于开始时间，暂不支持跨午夜安排。")
        with self.db.connect(write=True) as connection:
            outside = connection.execute(
                "SELECT 1 FROM blocks WHERE date=? AND (start<? OR end>?)",
                (selected_date, start, end),
            ).fetchone()
            if outside:
                raise ValidationError("已有安排超出新时间范围，请先调整或移出日程。")
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
                raise ValidationError("已完成任务无需再次安排。")
            settings = connection.execute(
                "SELECT * FROM day_settings WHERE date=?", (selected_date,)
            ).fetchone() or {"start": 540, "end": 1080}
            end = start + task["minutes"]
            if start < settings["start"] or end > settings["end"]:
                raise ValidationError("任务超出当日可安排时间。")
            exists = connection.execute(
                "SELECT 1 FROM blocks WHERE task_id=?", (task["id"],)
            ).fetchone()
            if exists:
                raise ValidationError("任务已在日程中，请先移出原安排。")
            overlap = connection.execute(
                "SELECT 1 FROM blocks WHERE date=? AND start<? AND end>?",
                (selected_date, end, start),
            ).fetchone()
            if overlap:
                raise ValidationError("这个时间段与已有安排重叠，请选择空闲时段。")
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
                raise ValidationError("已完成任务请先重新打开，再调整安排。")
            settings = connection.execute(
                "SELECT * FROM day_settings WHERE date=?", (selected_date,)
            ).fetchone() or {"start": 540, "end": 1080}
            end = start + task["minutes"]
            if start < settings["start"] or end > settings["end"]:
                raise ValidationError("任务超出目标日期的可安排时间。")
            overlap = connection.execute(
                "SELECT 1 FROM blocks WHERE date=? AND start<? AND end>? AND id!=?",
                (selected_date, end, start, record_id),
            ).fetchone()
            if overlap:
                raise ValidationError("这个时间段与已有安排重叠，请选择空闲时段。")
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
            occupied = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM blocks WHERE date=?", (selected_date,)
                )
            ]
            candidates = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM tasks WHERE status='open' AND id NOT IN "
                    "(SELECT task_id FROM blocks)"
                )
            ]
            scheduled, unplaced = suggest_schedule(
                candidates, settings["start"], settings["end"], occupied
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
        minutes = integer(data.get("minutes"), "本周计划分钟", 0, 10080)
        with self.db.connect(write=True) as connection:
            self.require("outcomes", outcome_id, connection)
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
        today_blocks = [b for b in data["blocks"] if b["date"] == selected_date]
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
