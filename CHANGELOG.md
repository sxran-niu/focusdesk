# Changelog

I keep the main changes here so I can quickly see what each version added.
My [development notes](docs/DEVELOPMENT.md) explain the choices behind them;
[checks](docs/VALIDATION.md) record the results, and the [roadmap](docs/ROADMAP.md)
holds ideas I haven't built yet.

## 0.3.0 — 2026-09-27

I switched the built-in interface and project materials to English: navigation,
forms, errors, demo labels, guides, screenshots and example reports.

- I kept personal text in its original language. Existing demo labels are translated
  only when they still match the original examples, so edits and added records stay put.
- I changed the backup confirmation word to **RESTORE**.
- I included English browser flows and narrow-screen forms in the release checks.

## 0.2.0 — 2026-09-26

I brought together four improvements that make everyday planning less fiddly.

### Editing and recovery

I added stage editing, moving courses between stages of the same goal, and archiving
completed goals. Original targets, revisions, task links and confirmed results stay
attached to the same records. An archived goal can be reopened before editing.

I also added JSON backup and restore. A restore checks the incoming data and saves
a recovery copy before replacing the current space. Personal and demo data stay
separate, and older databases upgrade without losing their records.

Two smaller fixes matter here: deleted task IDs are no longer reused, and weekly
free time no longer includes days or hours that have already passed.

### Recurring appointments

I added weekly classes, work and breaks over a date range. I can cancel one occurrence
or stop future ones while keeping the past. Fixed appointments now count when the
planner works out free time, weekly capacity and reports.

### Weekly planning

I added course effort targets by Monday–Sunday week, alongside scheduled time,
actual effort and the remaining gap. Open tasks help estimate the work; they aren't
all automatically due that week. Study hours still don't turn into credits.

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
