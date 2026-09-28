# What's next

Current version: 0.3.0. I keep finished features here alongside the limits I may
want to revisit.

| Feature | What works | Current limit |
| --- | --- | --- |
| Cross-day tasks | Carryover list, rescheduling and appointment history | One block per task; split longer work into separate tasks |
| Weekly planning | Course effort targets, planned/actual time and gaps | No automatic conversion from credits to study time |
| Fixed schedules | Weekly recurrence, single cancellations and stopping future appointments | One availability window per day; replace a series by stopping it and creating another |
| Editing and recovery | Stage revisions, course moves, archiving and backups | No cross-goal moves or hard deletion of goals/stages/courses; restore replaces a whole space |
| English edition | English interface, demo, guides, examples and screenshots | Personal text and history keep their original language |

The [development notes](DEVELOPMENT.md) explain the decisions behind these features.
The [checks](VALIDATION.md) page records the results and test environments.

## Before submission

- Publish the prepared repository as Public on GitHub.
- Check the repository page and confirm that the install/run instructions work
  from a fresh download or clone.
- Confirm the exact Moodle deadline, submit the repository URL and keep the receipt.
- Review the Git-history requirement in the [course checklist](COURSE_CHECKLIST.md).
  Review the milestone commits and release tags, and keep future work in meaningful
  commits.

## Things I want to try

- Run with an actual Python 3.10 interpreter and on another computer or Linux.
- Use the app over several weeks to see how estimates, carryover and revisions hold up.
- Try multiple availability windows, task splitting or editing a recurring series
  if everyday use shows a need for them.
- Keep personal data out of the repository while collecting that feedback.

A notebook walkthrough and Matplotlib/Seaborn charts are possible additions,
not requirements for the current app.
