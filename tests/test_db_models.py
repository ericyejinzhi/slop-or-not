from sloppy.db import models  # noqa: F401  (registers models on Base.metadata)
from sloppy.db.base import Base


def test_all_tables_registered():
    assert set(Base.metadata.tables) == {
        "channels",
        "videos",
        "comments",
        "thumbnails",
        "labels",
    }


def test_foreign_keys_point_at_expected_tables():
    fk_targets = {
        (fk.parent.table.name, fk.column.table.name)
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
    }
    assert fk_targets == {
        ("videos", "channels"),
        ("comments", "videos"),
        ("thumbnails", "videos"),
        ("labels", "videos"),
    }
