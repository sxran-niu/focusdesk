from focusdesk.web import create_app


def test_home_assets_and_guarded_mutations(tmp_path):
    app = create_app(tmp_path / "web.sqlite3")
    client = app.test_client()
    page = client.get("/")
    assert page.status_code == 200
    assert "Daily planner" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert client.post("/api/tasks", json={"title": "No token"}).status_code == 403
    headers = {"X-FocusDesk-Token": app.config["CSRF_TOKEN"]}
    created = client.post("/api/tasks", json={"title": "From browser"}, headers=headers)
    assert created.status_code == 201
    task_id = created.json["id"]
    assert client.get("/api/state").json["tasks"][0]["title"] == "From browser"
    assert (
        client.patch(
            f"/api/tasks/{task_id}", json={"minutes": 0}, headers=headers
        ).status_code
        == 400
    )
    assert client.post("/api/tasks", json={}, headers=headers).status_code == 400
    assert client.post("/api/tasks", json=[], headers=headers).status_code == 400
    assert client.post("/api/tasks", data="bad", headers=headers).status_code == 415
    assert client.get("/api/state?date=invalid").status_code == 400
    assert (
        client.get("/api/state", headers={"Host": "attacker.example"}).status_code
        == 400
    )
    assert (
        client.delete(f"/api/tasks/{task_id}", json={}, headers=headers).status_code
        == 200
    )


def test_empty_report_and_exports_work(tmp_path):
    client = create_app(tmp_path / "empty.sqlite3").test_client()
    assert client.get("/api/report").json["completed"] == 0
    for kind in ("csv", "md", "svg"):
        response = client.get(f"/api/export/{kind}")
        assert response.status_code == 200
        assert "attachment" in response.headers["Content-Disposition"]
    assert client.get("/api/export/unknown").status_code == 400


def test_move_and_weekly_target_endpoints(tmp_path):
    app = create_app(tmp_path / "iterations.sqlite3")
    client = app.test_client()
    headers = {"X-FocusDesk-Token": app.config["CSRF_TOKEN"]}
    desk = app.config["WORKBENCH"]
    goal = desk.add_goal({"title": "Goal", "target": 6, "target_date": "2027-12-31"})
    phase = desk.add_milestone(
        {
            "goal_id": goal,
            "title": "Term",
            "target": 6,
            "start_date": "2026-01-01",
            "end_date": "2027-01-01",
        }
    )
    outcome = desk.add_outcome({"milestone_id": phase, "title": "Course", "amount": 6})
    target = f"/api/weeks/2026-09-30/outcomes/{outcome}"
    assert client.put(target, json={"minutes": 360}).status_code == 403
    assert client.put(target, json={"minutes": 360}, headers=headers).status_code == 200
    task = desk.add_task({"title": "Read", "outcome_id": outcome})
    desk.schedule_task("2026-09-29", {"task_id": task, "start": "09:00"})
    block = desk.snapshot()["blocks"][0]["id"]
    assert (
        client.patch(
            f"/api/blocks/{block}",
            json={"date": "2026-09-30", "start": "10:00"},
            headers=headers,
        ).status_code
        == 200
    )
    response = client.get("/api/weekly-plan?date=2026-09-30")
    assert response.json["courses"][0]["unplanned_minutes"] == 300
