"""Explicit, fictional demonstration data; never mixed into a personal database."""

from datetime import date, timedelta

from .models import ValidationError


def seed_demo(workbench):
    """Seed only a completely empty database; subsequent starts are idempotent."""
    if workbench.db.rows("SELECT 1 FROM metadata WHERE key='demo_seeded'"):
        return
    state = workbench.snapshot()
    if state["goals"] or state["tasks"]:
        raise ValidationError("示例数据只能写入空数据库，请使用独立的 --demo 空间。")
    today = date.today()
    goal = workbench.add_goal(
        {
            "title": "两年完成硕士（示例）",
            "target": 120,
            "unit": "学分",
            "target_date": (today + timedelta(days=730)).isoformat(),
            "notes": "虚构的 120 学分示例；请按自己的培养方案设置目标与完成条件。",
        }
    )
    terms = []
    for index in range(4):
        start = today + timedelta(days=index * 180 - 30)
        terms.append(
            workbench.add_milestone(
                {
                    "goal_id": goal,
                    "title": f"第 {index + 1} 学期",
                    "start_date": start.isoformat(),
                    "end_date": (start + timedelta(days=179)).isoformat(),
                    "target": 30,
                }
            )
        )
    baseline = workbench.add_outcome(
        {
            "milestone_id": terms[0],
            "title": "已通过课程汇总（示例）",
            "amount": 24,
        }
    )
    workbench.record_outcome(
        baseline,
        {
            "status": "passed",
            "result_date": (today - timedelta(days=7)).isoformat(),
            "notes": "演示汇总。真实使用时建议逐门课程录入，避免重复计算。",
        },
    )
    course = workbench.add_outcome(
        {
            "milestone_id": terms[0],
            "title": "IIP 项目（示例）",
            "amount": 6,
        }
    )
    for title in ("完成培养方案规定的必修模块", "论文与答辩通过"):
        workbench.add_requirement({"goal_id": goal, "title": title})
    task_specs = [
        ("完成任务保存模块", "study", 60, 3, 2, course, "09:00"),
        ("阅读 Python 第 5 章", "study", 45, 2, 1, course, "10:30"),
        ("午餐与休息", "rest", 60, 2, 0, None, "12:00"),
        ("买菜，为晚餐做准备", "life", 30, 2, 0, None, "16:00"),
        ("出门散步", "rest", 30, 1, 0, None, "17:00"),
        ("整理本周课堂笔记", "study", 45, 2, 3, course, None),
        ("洗衣服", "life", 30, 1, 1, None, None),
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
