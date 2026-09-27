# Getting started with FocusDesk

The home page shows your daily schedule. Long-term progress lives under
**Goals & reviews → Long-term progress** in the sidebar.

## Try the demo

From the project folder, run:

```sh
uv run -m focusdesk --demo serve
```

Open `http://127.0.0.1:8765`. The banner identifies the **Demo space**.
Its courses, 120-credit goal, tasks and dates are fictional. Explore freely:

1. Check the allocation of study, life and rest on the daily planner.
2. Create a **New task**, enter an estimate, then choose **Schedule** and a start time.
3. Try an occupied time to see the conflict message.
4. Tick a completed task and enter the actual time spent.
5. Open **Long-term progress**: task completion has not added credits.
6. Choose **Record result** on the IIP demo course and select
   **Passed — amount confirmed**.
7. Confirmed credits now increase. Saving the same result again adds no extra credit.

The interface, built-in demo and reports use English. When upgrading an older demo,
only unchanged stock labels are translated. Your own titles, notes, results and
history stay as entered. Subsequent launches preserve the demo's state.

## Create your personal space

Stop the server with Ctrl+C, then run:

```sh
uv run -m focusdesk serve
```

The same address now opens a separate personal database, initially empty.
Start under **Long-term progress**:

1. **Goal:** a name, target date, quantity and unit, such as your degree's credit requirement.
2. **Stages:** semester dates and planned credits.
3. **Courses / outcomes:** each course and the credits confirmed when it is passed.
4. **Additional conditions:** required modules, thesis, defence or other programme requirements.

Return to the daily planner and create actionable tasks. An optional course link
connects `Task → Course → Semester → Goal`. Groceries and breaks can stay independent.

## Plan a day

- Use the date picker or arrows to change the selected date.
- Click **Available 09:00–18:00** to change that day's available hours.
- Use **Schedule** to select a start time, or **Fill free time** to arrange open tasks
  by deadline and priority while preserving existing appointments.
- Reserve breaks and other commitments so available study time is realistic.
- Each task occupies at most one block. Split multi-day work into concrete tasks.
- **Remove from schedule** keeps the task. **Delete** on the task list also deletes its appointment.
- Tasks booked on another date are not automatically booked again. Use **Reschedule**
  on the task list or the carryover panel to move them directly.

## Handle unfinished work

**Unfinished from earlier days** lists open tasks scheduled before the selected date.
Choose **Move / reschedule**, then a target date and start time. A conflict or an
appointment outside the destination day's available hours leaves the original
appointment unchanged. Expand **Schedule history** on the task list to see moves
and removals. Completing work still records effort only.

## Set a weekly plan

Under **Goals & reviews → Weekly plan**, choose **Set weekly target** for a course,
for example 360 minutes. Schedule linked tasks during that week to reduce the
remaining gap. Enter 0 to clear the target. The date picker selects the Monday–Sunday
week. Planned minutes, actual effort and credits are separate measurements.
Actual effort belongs to the completion date; remaining capacity excludes past
days and elapsed minutes today. Open-task estimates may include work for other weeks.

## Reserve fixed appointments

Open **Fixed schedule** and add a weekly weekday, a date range, and start/end times.
Every occurrence is checked against existing appointments and available hours.
Any conflict rejects the whole series. Fixed blocks appear on the daily planner,
and automatic scheduling avoids them. A rule may cover up to 366 days.

Use **Cancel occurrence** for one exception. **Stop future appointments** removes
occurrences from today onward and keeps the past. To change a rule, stop it and
create a replacement. Fixed appointments reserve time only. Record actual effort
through a task separately; avoid scheduling a second block over the same time.

## Review results and revise plans

After results are released, confirm the course result and date manually. Leave an
unreleased result **Pending**. A stage's original target and subsequent revisions
remain visible. **Weekly review** downloads Markdown, CSV and SVG reports.
Planned time belongs to the appointment date, while actual time belongs to the
completion date; delayed work can therefore fall in different weeks.

The workbench tracks the rules you configure. It does not determine official
graduation eligibility. Additional conditions, such as a thesis, need separate
confirmation. Study time and completed-task counts never infer credits.

In long-term progress, **Edit stage** changes its name, dates and target while
preserving history. **Edit** on a course can move it to another stage of the same
goal. Reuse that course for a retake to avoid duplicate credit. Transfers between
different goals are unsupported.

Once the quantity target and all additional conditions are met, choose **Archive
completed goal**. View it under **Archived** or **Unarchive** it to edit its courses,
results or conditions again. Archiving does not delete records.

## Back up and restore

Open **Backups** to download a full JSON backup. To restore, select a backup from
the same type of space and type **RESTORE**. Restoration replaces all goals,
courses, tasks, appointments, weekly targets, fixed schedules and history in that
space. It does not merge files. Invalid formats, relationships or schedules leave
current data unchanged. The file-size limit is 8 MB; personal and demo backups
cannot be mixed.

Before replacement, the app saves the current data as a **Recovery copy** beside
the database in `<database-filename>.backups/`. Download it from the backup page
and restore it if you need to undo the replacement. If the recovery copy cannot
be saved, restoration does not proceed.

## Read the code

Start with `models.py` for task fields, then `planner.py` for finding free time.
`service.py` connects the rules; `database.py` persists them. The CLI and web
interface call the same core, so you can explore behaviour at the command line.
Try changing one rule, running its tests and explaining the expected result.
