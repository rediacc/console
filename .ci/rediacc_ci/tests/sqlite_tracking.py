"""Close the sqlite connections a test opens, whoever holds them.

The in-memory control planes the tests build keep their connections in fakes and helper factories that nothing closes. From Python 3.13 an unclosed `sqlite3.Connection` raises a ResourceWarning when it is finalised, which pytest reports as an unraisable exception against whichever test the worker happens to be running then, so a leak in one file fails an unrelated one and the failing test changes with the shard layout. Tracking every connection `sqlite3.connect` hands out inside one test, and closing them when it ends, puts the cleanup in one place.
"""

from __future__ import annotations

import contextlib
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextlib.contextmanager
def closing_every_connection() -> Iterator[list[sqlite3.Connection]]:
    """Yield the connections opened through `sqlite3.connect` inside the block, and close them all on the way out."""
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracked(*args, **kwargs) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    sqlite3.connect = tracked
    try:
        yield opened
    finally:
        sqlite3.connect = real_connect
        for conn in opened:
            conn.close()
