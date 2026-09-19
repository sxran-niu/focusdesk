"""Deterministic scheduling: preserve existing blocks and fill free intervals."""

from .models import TimeBlock


def free_intervals(start, end, blocks):
    """Return free [start, end) intervals without introducing overlapping work."""
    cursor = start
    gaps = []
    for block in sorted(blocks, key=lambda item: item["start"]):
        if block["start"] > cursor:
            gaps.append((cursor, min(end, block["start"])))
        cursor = max(cursor, block["end"])
    if cursor < end:
        gaps.append((cursor, end))
    return [(left, right) for left, right in gaps if left < right]


def suggest_schedule(tasks, start, end, occupied=()):
    """Fit whole tasks by deadline, priority, then ID; this is not an optimizer.

    Tasks that do not fit are explicitly returned, never truncated or dropped.
    Completed tasks and tasks already scheduled on any date are excluded by caller.
    """
    gaps = free_intervals(start, end, occupied)
    scheduled, unplaced = [], []
    ordered = sorted(
        tasks,
        key=lambda task: (
            task["due_date"] or "9999-12-31",
            -task["priority"],
            task["id"],
        ),
    )
    for task in ordered:
        for index, (left, right) in enumerate(gaps):
            if task["minutes"] <= right - left:
                stop = left + task["minutes"]
                scheduled.append(TimeBlock(task["id"], left, stop))
                gaps[index] = (stop, right)
                break
        else:
            unplaced.append(task)
    return scheduled, unplaced
