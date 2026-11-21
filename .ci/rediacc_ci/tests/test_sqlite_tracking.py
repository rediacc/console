"""`sqlite_tracking.closing_every_connection`: the connections a block opens are closed on exit, and nothing else is."""

from __future__ import annotations

import sqlite3

import pytest

from rediacc_ci.tests import sqlite_tracking


def _is_closed(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


def test_a_connection_opened_in_the_block_is_closed_on_exit() -> None:
    with sqlite_tracking.closing_every_connection() as opened:
        conn = sqlite3.connect(":memory:")
        assert opened == [conn]
        assert not _is_closed(conn)
    assert _is_closed(conn)


def test_a_connection_opened_before_the_block_is_left_open() -> None:
    before = sqlite3.connect(":memory:")
    try:
        with sqlite_tracking.closing_every_connection() as opened:
            pass
        assert opened == []
        assert not _is_closed(before)
    finally:
        before.close()


def test_a_connection_opened_after_the_block_is_not_tracked() -> None:
    with sqlite_tracking.closing_every_connection() as opened:
        pass
    after = sqlite3.connect(":memory:")
    try:
        assert opened == []
        assert not _is_closed(after)
    finally:
        after.close()


def test_the_connections_are_closed_when_the_block_raises() -> None:
    seen: list[sqlite3.Connection] = []

    def fail_inside() -> None:
        with sqlite_tracking.closing_every_connection():
            seen.append(sqlite3.connect(":memory:"))
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        fail_inside()
    assert len(seen) == 1
    assert _is_closed(seen[0])
