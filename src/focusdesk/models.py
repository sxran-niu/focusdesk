"""Validated, reusable domain objects. Credits and task effort are independent."""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite


class ValidationError(ValueError):
    """A user-facing input or relationship error."""


def text(value, label, limit=160, optional=False):
    """Normalize a bounded text field without accepting arbitrary objects."""
    if not isinstance(value, str):
        raise ValidationError(f"{label}需要填写文字。")
    value = value.strip()
    if (not value and not optional) or len(value) > limit:
        raise ValidationError(f"{label}不能为空，且最多 {limit} 个字符。")
    return value


def number(value, label, low=0, high=100000):
    """Validate finite quantities, rejecting booleans and nonnumeric input."""
    if isinstance(value, bool):
        raise ValidationError(f"{label}必须是数字。")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label}必须是数字。") from None
    if not isfinite(value) or not low <= value <= high:
        raise ValidationError(f"{label}需要在 {low}–{high} 之间。")
    return value


def integer(value, label, low=1, high=100000):
    value = number(value, label, low, high)
    if value != int(value):
        raise ValidationError(f"{label}必须是整数。")
    return int(value)


def day(value, label="日期", optional=False):
    if optional and value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{label}格式应为 YYYY-MM-DD。")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{label}格式应为 YYYY-MM-DD。") from None
    if parsed.isoformat() != value:
        raise ValidationError(f"{label}格式应为 YYYY-MM-DD。")
    return value


def clock_minutes(value):
    """Convert HH:MM to integer minutes since midnight."""
    if not isinstance(value, str):
        raise ValidationError("时间格式应为 HH:MM。")
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError:
        raise ValidationError("时间格式应为 HH:MM。") from None
    return parsed.hour * 60 + parsed.minute


def clock_label(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class Task:
    """One actionable unit of work, optionally linked to a course/outcome."""

    title: str
    category: str = "study"
    minutes: int = 60
    priority: int = 2
    due_date: str | None = None
    outcome_id: int | None = None
    notes: str = ""

    def __post_init__(self):
        object.__setattr__(self, "title", text(self.title, "任务名称"))
        if self.category not in ("study", "life", "rest"):
            raise ValidationError("任务类型应为学习、生活或休息。")
        object.__setattr__(self, "minutes", integer(self.minutes, "预计用时", 5, 720))
        object.__setattr__(self, "priority", integer(self.priority, "优先级", 1, 3))
        object.__setattr__(self, "due_date", day(self.due_date, optional=True))
        if self.outcome_id not in (None, ""):
            object.__setattr__(self, "outcome_id", integer(self.outcome_id, "关联成果"))
        else:
            object.__setattr__(self, "outcome_id", None)
        object.__setattr__(self, "notes", text(self.notes, "备注", 2000, True))


@dataclass(frozen=True)
class TimeBlock:
    """A nonzero interval within a single day."""

    task_id: int
    start: int
    end: int

    def __post_init__(self):
        if not 0 <= self.start < self.end <= 1440:
            raise ValidationError("时间段必须在同一天内，结束时间晚于开始时间。")
