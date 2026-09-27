"""One-time translation of unchanged stock labels in pre-English demo spaces."""

# Historical strings use Unicode escapes; these are migration inputs, not UI text.
# Match both the original record ID and original field value. Never translate
# user-added records, edited text, dates, results, or stored change history.
LEGACY_DEMO_TEXT = [
    (
        "goals",
        1,
        "title",
        ("\u4e24\u5e74\u5b8c\u6210\u7855\u58eb\uff08\u793a\u4f8b\uff09"),
        ("Finish a master’s degree in two years (demo)"),
    ),
    (
        "goals",
        1,
        "notes",
        (
            "\u865a\u6784\u7684 120 "
            "\u5b66\u5206\u793a\u4f8b\uff1b\u8bf7\u6309\u81ea"
            "\u5df1\u7684\u57f9\u517b\u65b9\u6848\u8bbe\u7f6e"
            "\u76ee\u6807\u4e0e\u5b8c\u6210\u6761\u4ef6\u3002"
        ),
        (
            "Fictional 120-credit example. Set targets and conditions for your "
            "actual degree programme."
        ),
    ),
    (
        "goals",
        1,
        "unit",
        ("\u5b66\u5206"),
        ("credits"),
    ),
    (
        "milestones",
        1,
        "title",
        ("\u7b2c 1 \u5b66\u671f"),
        ("Semester 1"),
    ),
    (
        "milestones",
        2,
        "title",
        ("\u7b2c 2 \u5b66\u671f"),
        ("Semester 2"),
    ),
    (
        "milestones",
        3,
        "title",
        ("\u7b2c 3 \u5b66\u671f"),
        ("Semester 3"),
    ),
    (
        "milestones",
        4,
        "title",
        ("\u7b2c 4 \u5b66\u671f"),
        ("Semester 4"),
    ),
    (
        "outcomes",
        1,
        "title",
        ("\u5df2\u901a\u8fc7\u8bfe\u7a0b\u6c47\u603b\uff08\u793a\u4f8b\uff09"),
        ("Previously passed courses (demo)"),
    ),
    (
        "outcomes",
        1,
        "notes",
        (
            "\u6f14\u793a\u6c47\u603b\u3002\u771f\u5b9e\u4f7f"
            "\u7528\u65f6\u5efa\u8bae\u9010\u95e8\u8bfe\u7a0b"
            "\u5f55\u5165\uff0c\u907f\u514d\u91cd\u590d\u8ba1"
            "\u7b97\u3002"
        ),
        (
            "Demo total. In your personal space, record each course separately "
            "to avoid duplicate credit."
        ),
    ),
    (
        "outcomes",
        2,
        "title",
        ("IIP \u9879\u76ee\uff08\u793a\u4f8b\uff09"),
        ("IIP project (demo)"),
    ),
    (
        "requirements",
        1,
        "title",
        (
            "\u5b8c\u6210\u57f9\u517b\u65b9\u6848\u89c4\u5b9a"
            "\u7684\u5fc5\u4fee\u6a21\u5757"
        ),
        ("Complete all required modules"),
    ),
    (
        "requirements",
        2,
        "title",
        ("\u8bba\u6587\u4e0e\u7b54\u8fa9\u901a\u8fc7"),
        ("Pass the thesis and defence"),
    ),
    (
        "tasks",
        1,
        "title",
        ("\u5b8c\u6210\u4efb\u52a1\u4fdd\u5b58\u6a21\u5757"),
        ("Implement task persistence"),
    ),
    (
        "tasks",
        2,
        "title",
        ("\u9605\u8bfb Python \u7b2c 5 \u7ae0"),
        ("Read Python chapter 5"),
    ),
    (
        "tasks",
        3,
        "title",
        ("\u5348\u9910\u4e0e\u4f11\u606f"),
        ("Lunch and a break"),
    ),
    (
        "tasks",
        4,
        "title",
        ("\u4e70\u83dc\uff0c\u4e3a\u665a\u9910\u505a\u51c6\u5907"),
        ("Buy groceries for dinner"),
    ),
    (
        "tasks",
        5,
        "title",
        ("\u51fa\u95e8\u6563\u6b65"),
        ("Go for a walk"),
    ),
    (
        "tasks",
        6,
        "title",
        ("\u6574\u7406\u672c\u5468\u8bfe\u5802\u7b14\u8bb0"),
        ("Organise this week’s lecture notes"),
    ),
    (
        "tasks",
        7,
        "title",
        ("\u6d17\u8863\u670d"),
        ("Do the laundry"),
    ),
]


def upgrade_demo_language(workbench):
    """Translate once, atomically, and only for explicitly seeded demo data."""
    with workbench.db.connect(write=True) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if not metadata.get("demo_seeded") or metadata.get("demo_language") == "en":
            return
        for table, row_id, field, old, new in LEGACY_DEMO_TEXT:
            # Identifiers come exclusively from the internal constant above.
            connection.execute(
                f"UPDATE {table} SET {field}=? WHERE id=? AND {field}=?",
                (new, row_id, old),
            )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("demo_language", "en"),
        )
