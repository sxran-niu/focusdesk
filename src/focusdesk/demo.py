"""Explicit, fictional demonstration data; never mixed into a personal database."""

from datetime import date, timedelta

from .demo_legacy import upgrade_demo_language
from .models import ValidationError


def seed_demo(workbench):
    """Seed an empty demo or translate unchanged legacy labels exactly once."""
    if workbench.db.rows("SELECT 1 FROM metadata WHERE key='demo_seeded'"):
        upgrade_demo_language(workbench)
        return
    state = workbench.snapshot()
    if state["goals"] or state["tasks"]:
        raise ValidationError(
            "Demo data requires an empty database. Use the separate --demo space."
        )
    today = date.today()
    goal = workbench.add_goal(
        {
            "title": "Finish a master’s degree in two years (demo)",
            "target": 120,
            "unit": "credits",
            "target_date": (today + timedelta(days=730)).isoformat(),
            "notes": (
                "Fictional 120-credit example. Set targets and conditions "
                "for your actual degree programme."
            ),
        }
    )
    terms = []
    for index in range(4):
        start = today + timedelta(days=index * 180 - 30)
        terms.append(
            workbench.add_milestone(
                {
                    "goal_id": goal,
                    "title": f"Semester {index + 1}",
                    "start_date": start.isoformat(),
                    "end_date": (start + timedelta(days=179)).isoformat(),
                    "target": 30,
                }
            )
        )
    baseline = workbench.add_outcome(
        {
            "milestone_id": terms[0],
            "title": "Previously passed courses (demo)",
            "amount": 24,
        }
    )
    workbench.record_outcome(
        baseline,
        {
            "status": "passed",
            "result_date": (today - timedelta(days=7)).isoformat(),
            "notes": (
                "Demo total. In your personal space, record each course "
                "separately to avoid duplicate credit."
            ),
        },
    )
    course = workbench.add_outcome(
        {
            "milestone_id": terms[0],
            "title": "IIP project (demo)",
            "amount": 6,
        }
    )
    for title in ("Complete all required modules", "Pass the thesis and defence"):
        workbench.add_requirement({"goal_id": goal, "title": title})
    task_specs = [
        ("Implement task persistence", "study", 60, 3, 2, course, "09:00"),
        ("Read Python chapter 5", "study", 45, 2, 1, course, "10:30"),
        ("Lunch and a break", "rest", 60, 2, 0, None, "12:00"),
        ("Buy groceries for dinner", "life", 30, 2, 0, None, "16:00"),
        ("Go for a walk", "rest", 30, 1, 0, None, "17:00"),
        ("Organise this week’s lecture notes", "study", 45, 2, 3, course, None),
        ("Do the laundry", "life", 30, 1, 1, None, None),
    ]
    for title, category, minutes, priority, offset, outcome_id, start in task_specs:
        task_id = workbench.add_task(
            {
                "title": title,
                "category": category,
                "minutes": minutes,
                "priority": priority,
                "due_date": (today + timedelta(days=offset)).isoformat(),
                "outcome_id": outcome_id,
            }
        )
        if start:
            workbench.schedule_task(
                today.isoformat(), {"task_id": task_id, "start": start}
            )
    workbench.db.insert("metadata", {"key": "demo_seeded", "value": "1"})
    workbench.db.insert("metadata", {"key": "demo_language", "value": "en"})
