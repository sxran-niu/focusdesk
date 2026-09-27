"""Weekly effort reports and portable, file-backed CSV/Markdown/SVG exports."""

import csv
import io
from datetime import date, timedelta
from html import escape
from pathlib import Path

from .models import ValidationError, clock_label, day


def weekly_report(workbench, selected_date=None):
    """Aggregate the Monday–Sunday week containing selected_date.

    Planned time belongs to its scheduled date. Actual time belongs to the
    recorded completion date. Task completion is not evidence of goal attainment.
    """
    selected = date.fromisoformat(day(selected_date or date.today().isoformat()))
    start = selected - timedelta(days=selected.weekday())
    end = start + timedelta(days=6)
    snapshot = workbench.snapshot(selected.isoformat())
    tasks = {task["id"]: task for task in snapshot["tasks"]}
    days = [
        {
            "date": (start + timedelta(days=offset)).isoformat(),
            "planned": 0,
            "actual": 0,
            "completed": 0,
        }
        for offset in range(7)
    ]
    by_day = {row["date"]: row for row in days}
    categories = {
        category: {"planned": 0, "actual": 0} for category in ("study", "life", "rest")
    }
    for block in snapshot["blocks"]:
        if block["date"] in by_day:
            minutes = block["end"] - block["start"]
            by_day[block["date"]]["planned"] += minutes
            categories[tasks[block["task_id"]]["category"]]["planned"] += minutes
    completed = []
    for block in snapshot["fixed_blocks"]:
        if block["date"] in by_day:
            minutes = block["end"] - block["start"]
            by_day[block["date"]]["planned"] += minutes
            categories[block["category"]]["planned"] += minutes
    for task in tasks.values():
        completed_day = (task["completed_at"] or "")[:10]
        if task["status"] == "done" and completed_day in by_day:
            by_day[completed_day]["actual"] += task["actual_minutes"]
            by_day[completed_day]["completed"] += 1
            categories[task["category"]]["actual"] += task["actual_minutes"]
            completed.append(task)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "categories": categories,
        "completed": len(completed),
        "planned_minutes": sum(row["planned"] for row in days),
        "actual_minutes": sum(row["actual"] for row in days),
        "estimate_difference": sum(
            t["actual_minutes"] - t["minutes"] for t in completed
        ),
    }


def _csv_safe(value):
    """Prevent text fields being interpreted as formulas by spreadsheet programs."""
    value = str(value or "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_content(workbench, kind, selected_date=None):
    """Return content, MIME type and a stable filename for disk/browser export."""
    report = weekly_report(workbench, selected_date)
    state = workbench.snapshot(selected_date)
    if kind == "csv":
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "date",
                "start",
                "end",
                "task",
                "category",
                "planned_minutes",
                "status",
                "actual_minutes",
                "completed_at",
            ]
        )
        tasks = {task["id"]: task for task in state["tasks"]}
        for block in sorted(state["blocks"], key=lambda b: (b["date"], b["start"])):
            if report["start"] <= block["date"] <= report["end"]:
                task = tasks[block["task_id"]]
                writer.writerow(
                    [
                        block["date"],
                        clock_label(block["start"]),
                        clock_label(block["end"]),
                        _csv_safe(task["title"]),
                        task["category"],
                        block["end"] - block["start"],
                        task["status"],
                        task["actual_minutes"],
                        task["completed_at"],
                    ]
                )
        for block in sorted(
            state["fixed_blocks"], key=lambda b: (b["date"], b["start"])
        ):
            if report["start"] <= block["date"] <= report["end"]:
                writer.writerow(
                    [
                        block["date"],
                        clock_label(block["start"]),
                        clock_label(block["end"]),
                        _csv_safe(block["title"]),
                        block["category"],
                        block["end"] - block["start"],
                        "fixed",
                        "",
                        "",
                    ]
                )
        return "\ufeff" + buffer.getvalue(), "text/csv", "focusdesk-schedule.csv"
    if kind == "md":
        lines = [
            "# FocusDesk weekly report",
            "",
            f"Week: {report['start']} — {report['end']}",
            "",
            f"- Completed tasks: {report['completed']}",
            f"- Planned minutes: {report['planned_minutes']}",
            f"- Actual minutes: {report['actual_minutes']}",
            f"- Actual minus estimated minutes (completed tasks): "
            f"{report['estimate_difference']}",
            "",
            "## Goal outcomes (current snapshot)",
            "",
        ]
        for goal in state["goals"]:
            title = goal["title"].replace("\n", " ")
            lines.append(
                f"- {title}: {goal['earned']:g} / {goal['target']:g} "
                f"{goal['unit']} confirmed; "
                f"additional conditions met: {goal['conditions_met']}"
            )
        lines.extend(
            [
                "",
                "Task completion never awards goal credit.",
                "Planned time uses schedule date; actual time uses completion date.",
                "The CSV contains this week's scheduled blocks; the report also "
                "counts completed tasks that were never scheduled.",
                "",
                "Chart: focusdesk-week.svg. Schedule: focusdesk-schedule.csv.",
            ]
        )
        return "\n".join(lines) + "\n", "text/markdown", "focusdesk-report.md"
    if kind == "svg":
        maximum = max(60, max(row["actual"] for row in report["days"]))
        marks = []
        for index, row in enumerate(report["days"]):
            x = 95 + index * 84
            height = row["actual"] / maximum * 155
            marks.append(
                f'<rect x="{x}" y="{245 - height:g}" width="34" height="{height:g}" '
                f'fill="#477862"/><text x="{x + 17}" y="{232 - height:g}" '
                f'text-anchor="middle">{row["actual"]}</text>'
                f'<text x="{x + 17}" y="270" text-anchor="middle">'
                f"{escape(row['date'][5:])}</text>"
            )
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="315" '
            'viewBox="0 0 720 315" role="img" aria-labelledby="title desc">'
            '<title id="title">FocusDesk weekly recorded effort</title>'
            f'<desc id="desc">Actual minutes per day, {report["start"]} '
            f'to {report["end"]}</desc><rect width="720" height="315" fill="white"/>'
            '<g font-family="sans-serif" font-size="13" fill="#233b30">'
            '<text x="48" y="30" font-size="18">Recorded effort · minutes</text>'
            f'<text x="48" y="53">{report["start"]} — {report["end"]}</text>'
            '<path d="M70 90V245H680" fill="none" stroke="#bcc8bf"/>'
            '<text x="58" y="249" text-anchor="end">0</text>'
            f'<text x="58" y="99" text-anchor="end">{maximum}</text>'
            + "".join(marks)
            + '<text x="375" y="302" text-anchor="middle">Completion date</text>'
            "</g></svg>"
        )
        return svg, "image/svg+xml", "focusdesk-week.svg"
    raise ValidationError("Unsupported export format.")


def save_report(workbench, directory, selected_date=None):
    """Save all outputs and return their paths, including the nontext chart."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for kind in ("md", "csv", "svg"):
        content, _mime, filename = export_content(workbench, kind, selected_date)
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths
