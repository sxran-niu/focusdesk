from datetime import date

import pytest

from focusdesk import Workbench


@pytest.fixture
def desk(tmp_path):
    return Workbench(tmp_path / "test.sqlite3")


@pytest.fixture
def today():
    return date.today().isoformat()


@pytest.fixture
def course(desk, today):
    goal = desk.add_goal(
        {
            "title": "Graduate",
            "target": 6,
            "unit": "ECTS",
            "target_date": "2099-12-31",
        }
    )
    phase = desk.add_milestone(
        {
            "goal_id": goal,
            "title": "Semester 1",
            "target": 6,
            "start_date": today,
            "end_date": "2099-01-01",
        }
    )
    outcome = desk.add_outcome({"milestone_id": phase, "title": "IIP", "amount": 6})
    return goal, phase, outcome
