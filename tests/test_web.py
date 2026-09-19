from focusdesk.web import create_app


def test_home_assets_and_guarded_mutations(tmp_path):
    app = create_app(tmp_path / "web.sqlite3")
    client = app.test_client()
    page = client.get("/")
    assert page.status_code == 200
    assert "今日安排" in page.text
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
