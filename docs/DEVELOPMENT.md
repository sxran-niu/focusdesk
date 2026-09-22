# Development notes

I use this page to keep track of why I changed things, not just what I added.
The [changelog](../CHANGELOG.md) is the quick version, [checks](VALIDATION.md)
has the test details, and the [roadmap](ROADMAP.md) holds the ideas still waiting.

## 2026-09-19 — a place to plan the day

I wanted daily tasks and longer-term goals in the same app without making the home
page feel crowded. I put the day's schedule first and moved goals into their own
menu. Study, life and rest share the same available time.

I kept effort separate from results. An hour spent studying is useful to record,
but it doesn't mean a course is passed. Progress comes from explicitly confirmed
outcomes, and changing a result updates the same record rather than adding credits
again. I also kept original stage targets alongside later revisions.

I chose Flask and SQLite for a small local app. Python handles the calculations;
HTML, CSS and a little JavaScript handle the interface. Database writes keep conflict
checks and changes in one transaction, use bound SQL parameters, and require a
page token for API writes.

For planning, I started with a straightforward approach: keep existing appointments
and fit whole tasks into gaps. It doesn't split tasks or search for the best possible
schedule. There is one availability window each day, with breaks as fixed blocks.
Dates follow the local day, and completion timestamps include the timezone offset.

The initial checks caught spacing around an SVG chart title and missing fixtures
and docs in the source package. Those were fixed. The first test record, from
September 26, has 24 passing tests plus browser and installation checks on Python
3.12.13. Python 3.10 was checked for syntax only.

## 2026-09-20 — keeping notes I can come back to

I added a changelog, development notes, a check record and a roadmap, then updated
the README and package contents. I wanted enough context to pick the project up
again without reconstructing every decision from the code.

I kept personal reports out of Git and left small fictional examples in the repo.
The package stayed at 0.1.0.

The September 27 documentation checks covered source/wheel agreement, whitespace,
20 local links and source-package contents. App tests weren't repeated for this
edit. Cross-day tasks and weekly planning were the next things I wanted to improve.

## 2026-09-22 — bringing unfinished tasks back into view

Tasks left on an earlier day were too easy to lose track of. I added a carryover
panel and a way to move them from either the task list or the daily view.

I kept previous appointments in history. A move checks space and conflicts before
saving, so a failed move doesn't lose the old appointment. Repeated saves don't
create extra history, and completed tasks must be reopened before moving.

The September 27 checks reached 27 passing tests, with browser coverage for moves,
history and narrow layouts. Tasks still have one block each; I left splitting them
across days for later.

