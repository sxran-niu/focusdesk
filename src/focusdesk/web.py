"""Local Flask interface; all calculations and persistence stay in Python."""

import secrets
import sqlite3

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException

from .backup import BackupStore
from .models import ValidationError
from .service import Workbench


def create_app(database_path, demo=False):
    """Application factory used by the CLI and isolated integration tests."""
    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"],
    )
    workbench = Workbench(database_path)
    app.config["WORKBENCH"] = workbench
    backups = BackupStore(workbench, demo=demo)
    csrf_token = secrets.token_urlsafe(32)
    app.config["CSRF_TOKEN"] = csrf_token

    @app.before_request
    def protect_writes():
        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            if not secrets.compare_digest(
                request.headers.get("X-FocusDesk-Token", ""), csrf_token
            ):
                return jsonify(
                    error="This page has expired. Refresh and try again."
                ), 403
            if not request.is_json:
                return jsonify(error="The request must use JSON."), 415

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(ValidationError)
    def validation_error(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(sqlite3.IntegrityError)
    def conflict(_error):
        return jsonify(
            error=(
                "The record conflicts with existing data. Refresh and "
                "check its relationships."
            )
        ), 409

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error="Invalid request or resource not found."), error.code
        return error

    def payload():
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValidationError("The request must contain a JSON object.")
        return data

    @app.get("/")
    def index():
        return render_template("index.html", csrf_token=csrf_token, demo=demo)

    @app.get("/api/state")
    def state():
        return jsonify(workbench.snapshot(request.args.get("date")))

    @app.post("/api/tasks")
    def add_task():
        return jsonify(id=workbench.add_task(payload())), 201

    @app.post("/api/recurring")
    def recurring():
        return jsonify(id=workbench.calendar.add(payload())), 201

    @app.delete("/api/recurring/<int:record_id>")
    def stop_recurring(record_id):
        workbench.calendar.stop(record_id)
        return jsonify(ok=True)

    @app.delete("/api/fixed-blocks/<int:record_id>")
    def cancel_fixed(record_id):
        workbench.calendar.cancel(record_id)
        return jsonify(ok=True)

    @app.patch("/api/tasks/<int:record_id>")
    def update_task(record_id):
        workbench.update_task(record_id, payload())
        return jsonify(ok=True)

    @app.post("/api/tasks/<int:record_id>/complete")
    def complete_task(record_id):
        workbench.complete_task(record_id, payload())
        return jsonify(ok=True)

    @app.delete("/api/tasks/<int:record_id>")
    def delete_task(record_id):
        workbench.delete_task(record_id)
        return jsonify(ok=True)

    @app.put("/api/days/<selected_date>")
    def set_day(selected_date):
        workbench.set_day(selected_date, payload())
        return jsonify(ok=True)

    @app.post("/api/days/<selected_date>/blocks")
    def schedule(selected_date):
        workbench.schedule_task(selected_date, payload())
        return jsonify(ok=True), 201

    @app.delete("/api/blocks/<int:record_id>")
    def unschedule(record_id):
        workbench.unschedule(record_id)
        return jsonify(ok=True)

    @app.patch("/api/blocks/<int:record_id>")
    def reschedule(record_id):
        workbench.reschedule(record_id, payload())
        return jsonify(ok=True)

    @app.post("/api/days/<selected_date>/auto-plan")
    def auto_plan(selected_date):
        return jsonify(workbench.auto_plan(selected_date))

    @app.post("/api/goals")
    def add_goal():
        return jsonify(id=workbench.add_goal(payload())), 201

    @app.post("/api/milestones")
    def add_milestone():
        return jsonify(id=workbench.add_milestone(payload())), 201

    @app.patch("/api/goals/<int:record_id>")
    def update_goal(record_id):
        workbench.update_goal(record_id, payload())
        return jsonify(ok=True)

    @app.put("/api/goals/<int:record_id>/archive")
    def archive_goal(record_id):
        workbench.archive_goal(record_id, payload().get("archived"))
        return jsonify(ok=True)

    @app.get("/api/backup")
    def backup():
        response = jsonify(backups.export())
        response.headers["Content-Disposition"] = (
            'attachment; filename="focusdesk-backup.json"'
        )
        return response

    @app.get("/api/backups")
    def recovery_copies():
        return jsonify(files=backups.list_files())

    @app.get("/api/backups/<name>")
    def recovery_copy(name):
        return send_file(backups.file_path(name), as_attachment=True)

    @app.post("/api/restore")
    def restore():
        data = payload()
        if data.get("confirmation") != "RESTORE":
            raise ValidationError(
                "Explicit confirmation is required to restore a backup."
            )
        try:
            filename = backups.restore(data.get("backup"))
        except OSError:
            raise ValidationError(
                "The recovery copy could not be saved. No data was "
                "replaced. Check storage and permissions."
            ) from None
        except sqlite3.Error:
            raise ValidationError(
                "Restoration failed and current data was rolled back. "
                "Check the backup file."
            ) from None
        return jsonify(
            ok=True,
            recovery_copy=filename,
            message="Data restored. Download the recovery copy from Backups if needed.",
        )

    @app.patch("/api/milestones/<int:record_id>")
    def revise_milestone(record_id):
        workbench.revise_milestone(record_id, payload())
        return jsonify(ok=True)

    @app.post("/api/outcomes")
    def add_outcome():
        return jsonify(id=workbench.add_outcome(payload())), 201

    @app.put("/api/outcomes/<int:record_id>/result")
    def result(record_id):
        workbench.record_outcome(record_id, payload())
        return jsonify(ok=True)

    @app.patch("/api/outcomes/<int:record_id>")
    def update_outcome(record_id):
        workbench.update_outcome(record_id, payload())
        return jsonify(ok=True)

    @app.post("/api/requirements")
    def add_requirement():
        return jsonify(id=workbench.add_requirement(payload())), 201

    @app.patch("/api/requirements/<int:record_id>")
    def requirement(record_id):
        workbench.set_requirement(record_id, payload().get("done"))
        return jsonify(ok=True)

    @app.get("/api/report")
    def report():
        from .analytics import weekly_report

        return jsonify(weekly_report(workbench, request.args.get("date")))

    @app.get("/api/weekly-plan")
    def weekly_plan():
        from .weekly import weekly_plan

        state = workbench.snapshot(request.args.get("date"))
        return jsonify(weekly_plan(state, state["day"]["date"]))

    @app.put("/api/weeks/<selected_date>/outcomes/<int:record_id>")
    def weekly_target(selected_date, record_id):
        workbench.set_weekly_target(selected_date, record_id, payload())
        return jsonify(ok=True)

    @app.get("/api/export/<kind>")
    def export(kind):
        from .analytics import export_content

        content, mime, filename = export_content(
            workbench, kind, request.args.get("date")
        )
        return app.response_class(
            content,
            mimetype=mime,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app
