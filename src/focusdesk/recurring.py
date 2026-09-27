"""Bounded weekly appointments with explicit exceptions and conflict checks."""

import json
from datetime import date, timedelta

from .models import ValidationError, clock_minutes, day, integer, text


def occupied(connection, selected_date, exclude_block=None):
    """Return task and fixed intervals from the caller's transaction."""
    return [
        dict(row)
        for row in connection.execute(
            "SELECT start,end FROM blocks WHERE date=? AND id!=? "
            "UNION ALL SELECT start,end FROM fixed_blocks WHERE date=?",
            (
                selected_date,
                exclude_block if exclude_block is not None else -1,
                selected_date,
            ),
        )
    ]


class RecurringCalendar:
    """Persist finite weekly rules; cancelled occurrences are never regenerated."""

    def __init__(self, database):
        self.db = database

    def add(self, data):
        title = text(data.get("title"), "Fixed appointment name")
        category = data.get("category", "study")
        if category not in ("study", "life", "rest"):
            raise ValidationError("Invalid fixed appointment category.")
        weekday = integer(data.get("weekday"), "Weekday", 0, 6)
        first = date.fromisoformat(day(data.get("start_date")))
        last = date.fromisoformat(day(data.get("end_date")))
        if not 0 <= (last - first).days <= 365:
            raise ValidationError(
                "Recurring appointments need a date range of no more than 366 days."
            )
        start, end = clock_minutes(data.get("start")), clock_minutes(data.get("end"))
        if end <= start:
            raise ValidationError(
                "The end time must follow the start time. Overnight "
                "appointments are not supported."
            )
        dates = [
            (first + timedelta(days=n)).isoformat()
            for n in range((last - first).days + 1)
            if (first + timedelta(days=n)).weekday() == weekday
        ]
        if not dates:
            raise ValidationError(
                "The selected weekday does not occur within this date range."
            )
        with self.db.connect(write=True) as connection:
            for current in dates:
                setting = connection.execute(
                    "SELECT * FROM day_settings WHERE date=?", (current,)
                ).fetchone() or {"start": 540, "end": 1080}
                if start < setting["start"] or end > setting["end"]:
                    raise ValidationError(
                        f"{current} falls outside the available hours. "
                        f"Adjust that day first."
                    )
                if any(
                    b["start"] < end and b["end"] > start
                    for b in occupied(connection, current)
                ):
                    raise ValidationError(
                        f"{current} conflicts with an existing "
                        f"appointment. The entire series was left "
                        f"unchanged."
                    )
            rule_id = connection.execute(
                "INSERT INTO recurring_rules(title,category,weekday,start_date,"
                "end_date,start,end) VALUES(?,?,?,?,?,?,?)",
                (
                    title,
                    category,
                    weekday,
                    first.isoformat(),
                    last.isoformat(),
                    start,
                    end,
                ),
            ).lastrowid
            connection.executemany(
                "INSERT INTO fixed_blocks(rule_id,date,start,end) VALUES(?,?,?,?)",
                [(rule_id, current, start, end) for current in dates],
            )
        return rule_id

    def cancel(self, record_id):
        """Cancel one occurrence without changing the other weeks."""
        with self.db.connect(write=True) as connection:
            old = connection.execute(
                "SELECT * FROM fixed_blocks WHERE id=?", (integer(record_id, "ID"),)
            ).fetchone()
            if not old:
                raise ValidationError(
                    "This fixed appointment no longer exists. Refresh the page."
                )
            connection.execute(
                "INSERT INTO changes(entity,entity_id,old_value,new_value) "
                "VALUES('fixed_block',?,?,?)",
                (record_id, json.dumps(dict(old)), "null"),
            )
            connection.execute("DELETE FROM fixed_blocks WHERE id=?", (record_id,))

    def stop(self, record_id):
        """Stop today and future occurrences, preserving past appointments."""
        with self.db.connect(write=True) as connection:
            old = connection.execute(
                "SELECT * FROM recurring_rules WHERE id=?",
                (integer(record_id, "ID"),),
            ).fetchone()
            if not old:
                raise ValidationError(
                    "This recurring rule no longer exists. Refresh the page."
                )
            if not old["active"]:
                return
            future = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM fixed_blocks WHERE rule_id=? AND date>=?",
                    (record_id, date.today().isoformat()),
                )
            ]
            connection.execute(
                "INSERT INTO changes(entity,entity_id,old_value,new_value) "
                "VALUES('recurring_rule',?,?,?)",
                (record_id, json.dumps(future), "[]"),
            )
            connection.execute(
                "UPDATE recurring_rules SET active=0 WHERE id=?", (record_id,)
            )
            connection.execute(
                "DELETE FROM fixed_blocks WHERE rule_id=? AND date>=?",
                (record_id, date.today().isoformat()),
            )
