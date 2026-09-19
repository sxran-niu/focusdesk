# Development notes

I use these notes to remember the choices behind FocusDesk.

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

