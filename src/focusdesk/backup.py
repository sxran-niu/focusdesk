"""Versioned JSON backups, isolated validation, and transactional restoration."""

import json
import os
import re
import sqlite3
import tempfile
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from .models import Task, ValidationError, day, integer, number, text
from .weekly import week_start

# Parent tables precede foreign-key dependants; input never supplies SQL names.
TABLES = (
    "goals",
    "milestones",
    "outcomes",
    "requirements",
    "tasks",
    "day_settings",
    "blocks",
    "changes",
    "metadata",
    "weekly_targets",
    "recurring_rules",
    "fixed_blocks",
)
MAX_BYTES = 8 * 1024 * 1024
AUTOMATIC_NAME = re.compile(r"before-restore-\d{8}T\d{6}-[a-f0-9]{12}\.json")


def _document(connection, space):
    return {
        "format": "focusdesk-backup",
        "version": 1,
        "space": space,
        "created_at": datetime.now().astimezone().isoformat(),
        "tables": {
            table: [
                dict(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ]
            for table in TABLES
        },
    }


def _insert(connection, tables):
    for table in TABLES:
        columns = [r["name"] for r in connection.execute(f"PRAGMA table_info({table})")]
        rows = tables[table]
        if not isinstance(rows, list) or len(rows) > 50000:
            raise ValidationError("备份表内容或记录数量无效。")
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(columns):
                raise ValidationError("备份字段不符合当前版本。")
            if any(
                value is not None and type(value) not in (str, int, float)
                for value in row.values()
            ):
                raise ValidationError("备份字段类型无效。")
        marks = ",".join("?" for _ in columns)
        connection.executemany(
            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({marks})",
            [tuple(row[c] for c in columns) for row in rows],
        )


def _validate(candidate):
    """Check domain invariants in addition to SQLite constraints/foreign keys."""
    state = candidate.snapshot()
    goals = {g["id"]: g for g in state["goals"]}
    milestones = {m["id"]: m for m in state["milestones"]}
    tasks = {t["id"]: t for t in state["tasks"]}
    for collection in (
        "goals",
        "milestones",
        "outcomes",
        "requirements",
        "tasks",
        "blocks",
        "changes",
        "recurring_rules",
        "fixed_blocks",
    ):
        for row in state[collection]:
            integer(row["id"], "编号")
    for goal in goals.values():
        text(goal["title"], "目标名称")
        text(goal["unit"], "单位", 20)
        text(goal["notes"], "说明", 2000, True)
        number(goal["target"], "目标数量", 0.01)
        day(goal["target_date"])
        if goal["archived"] and not goal["achieved"]:
            raise ValidationError("备份中的归档目标未满足完成条件。")
    for milestone in milestones.values():
        text(milestone["title"], "阶段名称")
        number(milestone["target"], "阶段目标", 0.01)
        number(milestone["original_target"], "原始目标", 0.01)
        if (
            not day(milestone["start_date"])
            <= day(milestone["end_date"])
            <= goals[milestone["goal_id"]]["target_date"]
        ):
            raise ValidationError("备份中的阶段日期不合法。")
    for outcome in state["outcomes"]:
        text(outcome["title"], "课程名称")
        number(outcome["amount"], "成果数量", 0.01)
        text(outcome["grade"], "成绩", 40, True)
        text(outcome["notes"], "备注", 2000, True)
        if outcome["status"] == "pending":
            if outcome["result_date"] is not None:
                raise ValidationError("待确认成果不能带确认日期。")
        elif day(outcome["result_date"]) > date.today().isoformat():
            raise ValidationError("成果确认日期不能在未来。")
    for requirement in state["requirements"]:
        text(requirement["title"], "附加条件")
    for task in tasks.values():
        Task(**{field: task[field] for field in Task.__dataclass_fields__})
        if task["status"] == "done":
            stamp = datetime.fromisoformat(task["completed_at"])
            if stamp.date() > date.today():
                raise ValidationError("完成时间不能在未来。")
            integer(task["actual_minutes"], "实际分钟", 0, 1440)
        elif task["completed_at"] is not None or task["actual_minutes"] is not None:
            raise ValidationError("未完成任务不能有完成记录。")
    for target in state["weekly_targets"]:
        integer(target["minutes"], "周计划分钟", 0, 10080)
        if week_start(target["week_start"]) != target["week_start"]:
            raise ValidationError("周目标日期必须是周一。")
    rules = {r["id"]: r for r in state["recurring_rules"]}
    for rule in rules.values():
        integer(rule["weekday"], "星期", 0, 6)
        integer(rule["start"], "开始分钟", 0, 1439)
        integer(rule["end"], "结束分钟", 1, 1440)
        text(rule["title"], "固定安排名称")
        first = date.fromisoformat(day(rule["start_date"]))
        last = date.fromisoformat(day(rule["end_date"]))
        if not 0 <= (last - first).days <= 365:
            raise ValidationError("重复规则范围无效。")
    for block in state["fixed_blocks"]:
        rule = rules[block["rule_id"]]
        if (
            not rule["start_date"] <= block["date"] <= rule["end_date"]
            or date.fromisoformat(day(block["date"])).weekday() != rule["weekday"]
            or (block["start"], block["end"]) != (rule["start"], rule["end"])
        ):
            raise ValidationError("固定时段与规则不一致。")
    for block in state["blocks"]:
        if block["end"] - block["start"] != tasks[block["task_id"]]["minutes"]:
            raise ValidationError("任务时段与预计用时不一致。")
    settings = {day(s["date"]): s for s in state["day_settings"]}
    for setting in settings.values():
        integer(setting["start"], "开始分钟", 0, 1439)
        integer(setting["end"], "结束分钟", 1, 1440)
    previous = {}
    for block in sorted(
        state["blocks"] + state["fixed_blocks"], key=lambda b: (b["date"], b["start"])
    ):
        current = day(block["date"])
        integer(block["start"], "开始分钟", 0, 1439)
        integer(block["end"], "结束分钟", 1, 1440)
        setting = settings.get(current, {"start": 540, "end": 1080})
        if (
            block["start"] < previous.get(current, setting["start"])
            or block["end"] > setting["end"]
        ):
            raise ValidationError("备份中存在时间冲突或超出可用范围的安排。")
        previous[current] = block["end"]
    for change in state["changes"]:
        text(change["entity"], "变更类型", 40)
        text(change["old_value"], "原值", MAX_BYTES, True)
        text(change["new_value"], "新值", MAX_BYTES, True)
        datetime.fromisoformat(change["created_at"].replace("Z", "+00:00"))
        if change["entity"] == "schedule":
            for key in ("old_value", "new_value"):
                block = json.loads(change[key])
                if block is not None:
                    day(block["date"])
                    if not 0 <= block["start"] < block["end"] <= 1440:
                        raise ValidationError("安排历史时间无效。")
    for item in candidate.db.rows("SELECT * FROM metadata"):
        text(item["key"], "元数据键", 160)
        text(item["value"], "元数据值", 2000, True)
        if item["key"] == "retired_task_id":
            integer(item["value"], "保留的任务编号")


class BackupStore:
    """Export only app tables; restore after staging and saving a recovery copy."""

    def __init__(self, workbench, demo=False):
        self.workbench = workbench
        self.db = workbench.db
        self.space = (
            "demo"
            if demo or self.db.rows("SELECT 1 FROM metadata WHERE key='demo_seeded'")
            else "personal"
        )
        self.directory = self.db.path.parent / (self.db.path.name + ".backups")

    def export(self):
        with self.db.connect() as connection:
            connection.execute("BEGIN")
            return _document(connection, self.space)

    def list_files(self):
        if not self.directory.exists():
            return []
        return sorted(
            (
                p.name
                for p in self.directory.iterdir()
                if AUTOMATIC_NAME.fullmatch(p.name) and p.is_file()
            ),
            reverse=True,
        )

    def file_path(self, name):
        if not AUTOMATIC_NAME.fullmatch(name) or name not in self.list_files():
            raise ValidationError("恢复前副本不存在。")
        return self.directory / name

    def restore(self, document):
        """Validate in a throwaway database; atomically replace live table rows."""
        from .service import Workbench

        try:
            encoded = json.dumps(document, ensure_ascii=False, allow_nan=False)
            if len(encoded.encode("utf-8")) > MAX_BYTES:
                raise ValidationError("备份文件最多 8 MB。")
            if (
                not isinstance(document, dict)
                or document.get("format") != "focusdesk-backup"
                or type(document.get("version")) is not int
                or document["version"] != 1
                or not isinstance(document.get("tables"), dict)
                or set(document["tables"]) != set(TABLES)
            ):
                raise ValidationError("不支持的备份格式或版本。")
            if document.get("space") != self.space:
                raise ValidationError("个人空间和示例空间的备份不能混合恢复。")
            with tempfile.TemporaryDirectory(prefix="focusdesk-restore-") as directory:
                candidate = Workbench(Path(directory) / "validate.sqlite3")
                with candidate.db.connect(write=True) as connection:
                    _insert(connection, document["tables"])
                    if connection.execute("PRAGMA foreign_key_check").fetchall():
                        raise ValidationError("备份中存在断开的关联。")
                _validate(candidate)
                tables = BackupStore(candidate).export()["tables"]
        except (KeyError, TypeError, ValueError, OverflowError, sqlite3.Error) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError("备份校验失败，当前数据没有改变。") from None
        with self.db.connect(write=True) as connection:
            previous = _document(connection, self.space)
            self.directory.mkdir(parents=True, exist_ok=True)
            filename = (
                f"before-restore-{datetime.now():%Y%m%dT%H%M%S}-{uuid4().hex[:12]}.json"
            )
            descriptor = os.open(
                self.directory / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as backup:
                json.dump(previous, backup, ensure_ascii=False, allow_nan=False)
                backup.flush()
                os.fsync(backup.fileno())
            for table in reversed(TABLES):
                connection.execute(f"DELETE FROM {table}")
            _insert(connection, tables)
            self.workbench._change(
                connection,
                "restore",
                0,
                {"recovery_copy": filename},
                {"format_version": 1},
            )
        return filename
