"""Weekly intentions and scheduling gaps; effort never becomes earned credit."""

from datetime import date, datetime, timedelta

from .models import day
from .planner import free_intervals


def week_start(selected_date):
    """Normalize any ISO date to the Monday of its calendar week."""
    selected = date.fromisoformat(day(selected_date))
    return (selected - timedelta(days=selected.weekday())).isoformat()


def weekly_plan(state, selected_date, now=None):
    """Compare explicit course targets with appointments and completed effort.

    Targets are set by the user, not inferred from credits or task deadlines.
    Scheduled minutes include completed appointments in this week. Actual minutes
    belong to completion date and are displayed separately, never added to plans.
    """
    start = week_start(selected_date)
    now = now or datetime.now().astimezone()
    today = now.date().isoformat()
    dates = [
        (date.fromisoformat(start) + timedelta(days=n)).isoformat() for n in range(7)
    ]
    targets = {
        row["outcome_id"]: row["minutes"]
        for row in state["weekly_targets"]
        if row["week_start"] == start
    }
    tasks = {t["id"]: t for t in state["tasks"]}
    rows = []
    for outcome in state["outcomes"]:
        milestone = next(
            m for m in state["milestones"] if m["id"] == outcome["milestone_id"]
        )
        goal = next(g for g in state["goals"] if g["id"] == milestone["goal_id"])
        if goal.get("archived"):
            continue
        associated = [t for t in tasks.values() if t["outcome_id"] == outcome["id"]]
        scheduled = sum(
            b["end"] - b["start"]
            for b in state["blocks"]
            if b["date"] in dates and tasks[b["task_id"]]["outcome_id"] == outcome["id"]
        )
        actual = sum(
            t["actual_minutes"]
            for t in associated
            if t["status"] == "done" and t["completed_at"][:10] in dates
        )
        target = targets.get(outcome["id"], 0)
        rows.append(
            {
                "outcome_id": outcome["id"],
                "title": outcome["title"],
                "milestone": milestone["title"],
                "goal": goal["title"],
                "target_minutes": target,
                "scheduled_minutes": scheduled,
                "actual_minutes": actual,
                "unplanned_minutes": max(0, target - scheduled),
                "remaining_task_minutes": sum(
                    t["minutes"] for t in associated if t["status"] == "open"
                ),
            }
        )
    days = []
    for current in dates:
        setting = next(
            (s for s in state["day_settings"] if s["date"] == current),
            {"start": 540, "end": 1080},
        )
        blocks = [
            b
            for b in state["blocks"] + state.get("fixed_blocks", [])
            if b["date"] == current
        ]
        gaps = free_intervals(setting["start"], setting["end"], blocks)
        free = sum(b - a for a, b in gaps)
        remaining = free
        if current < today:
            remaining = 0
        elif current == today:
            remaining = sum(
                max(0, b - max(a, now.hour * 60 + now.minute)) for a, b in gaps
            )
        days.append(
            {"date": current, "free_minutes": free, "remaining_minutes": remaining}
        )
    return {
        "start": start,
        "end": dates[-1],
        "courses": rows,
        "days": days,
        "free_minutes": sum(d["free_minutes"] for d in days),
        "remaining_free_minutes": sum(d["remaining_minutes"] for d in days),
        "unplanned_minutes": sum(r["unplanned_minutes"] for r in rows),
    }
