# Checks

I keep the check results here so I know what has been tried and what still needs
attention. The dates below are the dates of the checks. I use temporary databases
for automated and browser tests, keeping them separate from personal data.

## 2026-09-26 — first version, v0.1.0

My initial test environment was macOS, Python 3.12.13 and headless Chrome.
I organised these results on September 27.

| What I checked | Result |
| --- | --- |
| Automated tests | 24 passed: validation, effort vs outcomes, repeated results, conditions, revisions, conflicts, concurrency, persistence, reports and HTTP writes |
| Python style | Ruff lint and formatting passed |
| Python 3.10 syntax | AST parsing passed; no runtime test on 3.10 |
| JavaScript syntax | `node --check src/focusdesk/static/app.js` passed |
| Main browser flows | Tasks, scheduling, conflicts, completion, actual time, results, target revisions and new goals/stages/outcomes/conditions worked |
| Text handling | HTML in task names displayed as text |
| Progress | Completing tasks added no credits; confirming a course counted once |
| Layout | No horizontal overflow at 1440/390/320px |
| Reports | Weekly report and SVG downloads worked; Markdown/CSV/SVG examples were saved |
| Editable install | `uv pip install -e .` and `uv run -m focusdesk ...` worked |
| Build | Wheel and source package built with the expected fixtures, docs and examples |
| Separate wheel install | Isolated import loaded site-packages; page, CSS, JS, favicon, state API and CLI summary worked |
| Packaged files | Wheel app files and assets matched the tested source byte for byte |

I use fictional data in the [daily](images/today.png) and [goal](images/goals.png)
screenshots and [example reports](../examples/report/focusdesk-report.md).
The screenshots were later refreshed for the English version.

I kept the Python tests in the repository. The earliest browser helpers were tied
to the development environment; I added a reusable script in the next iteration.

## 2026-09-27 — documentation and package contents

I compared the running source with the existing 0.1.0 wheel and checked the docs,
manifest and ignore rules. Whitespace and 20 local links passed. A temporary source
package included docs and test fixtures while excluding personal data, reports and
the virtual environment. Existing release files stayed intact.

I didn't repeat the app tests or separate wheel installation for this docs update.
The code and package/lock versions stayed at 0.1.0.

## 2026-09-27 — cross-day tasks

I extended the checks to cover moves, failed-move rollback, repeated saves,
completed-task restrictions and history. The suite reached **27 passing tests**,
and Ruff passed.

I added `scripts/browser_smoke.cjs` for moves and history at 1440/390/320px. It ran
with temporary data on macOS/Python 3.12.13/Chrome, with no script errors or
horizontal overflow.

## 2026-09-27 — weekly planning

I added cases for week boundaries, target updates, planning gaps, separate actual
effort and protected API writes. **30 tests passed**, along with Ruff lint and
formatting. The browser checks covered saving targets and displaying gaps, plus
the existing carryover and narrow-layout flows.

## 2026-09-27 — recurring appointments

I added coverage for fixed-time conflicts, rollback, automatic avoidance, saved
cancellations, past appointments and weekly/CSV time. **39 tests passed**, and
Ruff lint and formatting passed.

In the browser checks, I covered creating a series, cancelling one occurrence and
stopping future ones. All routes passed at 1440/390/320px without page script errors.

## 2026-09-27 — editing and recovery, v0.2.0

I expanded the suite to **59 passing tests**. Ruff lint, formatting and JavaScript
syntax also passed. The new cases covered:

- Stage edits and course moves that keep IDs, credits, task links and targets.
- Archiving, older-database upgrades and retired task IDs.
- Backup round trips and recovery copies, including invalid relationships, fields,
  dates, conflicts, versions, spaces and NaN values.
- Failed recovery-copy writes and rollback, with appointments and history preserved.
- Token and confirmation requirements for HTTP restore.
- Remaining weekly capacity on Sunday at 15:00, excluding time already gone.

I included backup download, file selection and restore in the browser flows.
All routes passed at 1440/390/320px without errors or overflow. I also reviewed
the desktop goal, weekly and backup screenshots.

Packaging checks covered the offline lock, wheel/source builds and a fresh wheel
installation with isolated imports. Pages, assets, state, weekly/backup/list APIs,
CLI summary and `uv run -m focusdesk` worked. Wheel runtime files matched source;
the source package included tests, docs and the browser script without personal data.

I compared the preview database before and after upgrading: original records and
fields across nine demo tables matched, and the new schema fields were present.
Python 3.10 syntax passed; runtime checks still used macOS/Python 3.12.13.

## What I still want to try

- Run the app and tests on an actual Python 3.10 interpreter.
- Try a separate computer, Linux and other browsers.
- Use the app over several weeks.

Backup imports above 8 MB are currently unsupported.
