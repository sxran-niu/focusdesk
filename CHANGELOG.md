# Changelog

I keep the main changes here so I can quickly see what each version added.
My [development notes](docs/DEVELOPMENT.md) explain the choices behind them;
[checks](docs/VALIDATION.md) record the results, and the [roadmap](docs/ROADMAP.md)
holds ideas I haven't built yet.

## Unreleased

I added project notes, a check record and a roadmap so I can follow the work.

### Unfinished tasks

I added a carryover panel for tasks left on earlier days. Rescheduling keeps the
previous appointment in history, and a failed move leaves the original in place.
A completed task needs to be reopened before it can move.

## 0.1.0 — 2026-09-19

I started with a local Python, Flask and SQLite workbench: daily planning on the
home page, with long-term goals in a separate menu.

- Tasks for study, life and rest, with editing, scheduling, completion and reopening.
- Automatic planning that fits whole tasks around existing appointments.
- Goals split into stages and courses/outcomes, with optional completion conditions.
- Tasks linked to a course/outcome, or kept independent.
- Original stage targets and a history of revisions.
- Weekly Markdown, CSV and SVG reports.
- Separate personal and fictional demo spaces, plus a command-line interface.

My main rule was already in place: finishing a task records effort; confirming an
outcome records progress. Confirming the same result twice doesn't add it twice.

I kept the first planner simple: one block per task and one availability window per
day. Splitting tasks across days, overnight scheduling and hard deletion of goals,
stages or outcomes aren't supported in the current app.
