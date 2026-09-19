"""Command-line entry point, including headless grading and report commands."""

import argparse
import json
from datetime import date
from pathlib import Path

from .models import ValidationError
from .service import Workbench


def main(argv=None):
    parser = argparse.ArgumentParser(description="FocusDesk — study and life workbench")
    parser.add_argument("--db", type=Path, help="SQLite database file")
    parser.add_argument(
        "--demo", action="store_true", help="Use separate fictional demo data"
    )
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Open the local web workbench")
    serve.add_argument("--port", type=int, default=8765)
    commands.add_parser("summary", help="Print all goal progress as JSON")
    commands.add_parser("tasks", help="List tasks as JSON")
    add = commands.add_parser("add", help="Create a task")
    add.add_argument("title")
    add.add_argument("--minutes", type=int, default=60)
    add.add_argument("--category", choices=["study", "life", "rest"], default="study")
    add.add_argument("--due", dest="due_date")
    add.add_argument("--priority", type=int, choices=[1, 2, 3], default=2)
    done = commands.add_parser("done", help="Complete a task without awarding credits")
    done.add_argument("id", type=int)
    done.add_argument("--minutes", type=int, help="Actual time spent")
    plan = commands.add_parser(
        "plan", help="Fill free time without moving existing blocks"
    )
    plan.add_argument("--date", default=date.today().isoformat())
    report = commands.add_parser("report", help="Save Markdown, CSV and SVG reports")
    report.add_argument("--date", default=date.today().isoformat())
    report.add_argument("--output", type=Path, default=Path("generated"))
    args = parser.parse_args(argv)
    if args.demo and args.db:
        parser.error("Use either --demo or --db, not both.")
    path = args.db or Path(
        "data/demo.sqlite3" if args.demo else "data/focusdesk.sqlite3"
    )
    try:
        workbench = Workbench(path)
        if args.demo:
            from .demo import seed_demo

            seed_demo(workbench)
        if args.command in (None, "serve"):
            from .web import create_app

            port = getattr(args, "port", 8765)
            if not 1024 <= port <= 65535:
                parser.error("Port must be between 1024 and 65535.")
            print(f"FocusDesk: http://127.0.0.1:{port}", flush=True)
            create_app(path, demo=args.demo).run(
                host="127.0.0.1", port=port, debug=False, use_reloader=False
            )
        elif args.command == "summary":
            print(
                json.dumps(workbench.snapshot()["goals"], ensure_ascii=False, indent=2)
            )
        elif args.command == "tasks":
            print(
                json.dumps(workbench.snapshot()["tasks"], ensure_ascii=False, indent=2)
            )
        elif args.command == "add":
            print(
                workbench.add_task(
                    {
                        key: getattr(args, key)
                        for key in (
                            "title",
                            "minutes",
                            "category",
                            "due_date",
                            "priority",
                        )
                    }
                )
            )
        elif args.command == "done":
            data = {"done": True}
            if args.minutes is not None:
                data["actual_minutes"] = args.minutes
            workbench.complete_task(args.id, data)
            print("Task completed. Confirmed goal outcomes are unchanged.")
        elif args.command == "plan":
            print(json.dumps(workbench.auto_plan(args.date)))
        elif args.command == "report":
            from .analytics import save_report

            for file in save_report(workbench, args.output, args.date):
                print(file.resolve())
    except (ValidationError, OSError) as error:
        parser.exit(2, f"Error: {error}\n")
    return 0
