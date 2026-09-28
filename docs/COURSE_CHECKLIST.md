# IIP project checklist

I use this checklist to compare FocusDesk with the course requirements and keep
track of the remaining submission steps.

Source: Google Drive / IIP / Notebooks-20260809 /
[99-final-project.ipynb](https://drive.google.com/file/d/15-M1_uHMXV76Ay9D_BTRSebdOC9_H9qw/view),
checked on 2026-09-26 and 2026-09-27. This version includes saving nontext output
to files.

| Requirement | Where it stands |
| --- | --- |
| Python >= 3.10 | Declared in `pyproject.toml`; runtime checked on 3.12, syntax checked for 3.10 |
| Installable package with a modern build system | `pyproject.toml` and setuptools; no setup.py |
| `uv pip install -e .` | Editable installation checked |
| `uv run -m <package> <args>` | `uv run -m focusdesk summary`, `--demo summary` and `serve` |
| A useful problem | Daily planning linked to explicitly confirmed long-term outcomes |
| Multiple files and reusable functions/classes | Models, planner, database, service, analytics, CLI and web |
| Top-level imports | `Task`, `TimeBlock`, `Workbench` and planner functions |
| Clear documentation | README, beginner guide, docstrings and the three project logs |
| PEP 8 | Ruff lint and formatting checks |
| External data | No external dataset; small fictional demo included |
| Save nontext outputs | SVG reports saved to disk, with browser download and example files |
| Notebook demonstration | Optional; not included |
| Matplotlib / Seaborn | Optional; the current chart uses self-contained SVG |
| Public GitHub repository | Pending manual publication |
| Meaningful Git history | Separate milestone snapshots and release tags; public repository pending |
| Moodle repository URL before the deadline | Pending; I still need to confirm the exact time in Moodle |

The course describes a scope of around 50 hours, without a minimum number of
commits or development days. The notes describe my decisions and checks. I will keep future work in
meaningful commits and review the repository before submission.

See [the roadmap](ROADMAP.md) for remaining checks and possible improvements.
