"""Tests for `rediacc_ci.ops.repair_org_customer_ids` against an in-memory SQLite D1.

No Cloudflare credential and no network: the fake runner executes the tool's real SQL on a SQLite database holding the three tables' relevant columns, and records every statement and the bookmark call in one ordered log.
"""

from __future__ import annotations

import argparse
import sqlite3

import pytest

from rediacc_ci.ops import repair_org_customer_ids as mod

SCHEMA = """
CREATE TABLE users (id TEXT PRIMARY KEY, customer_id TEXT);
CREATE TABLE organizations (id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, customer_id TEXT NOT NULL);
CREATE TABLE subscriptions (id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, plan_code TEXT);
"""


class FakeD1:
    def __init__(self, stuck: bool = False) -> None:
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.events: list[str] = []
        self.stuck = stuck

    def seed(self, org: str, user: str, user_cust: str | None, org_cust: str, sub: str | None):
        self.db.execute("INSERT INTO users VALUES (?, ?)", (user, user_cust))
        self.db.execute("INSERT INTO organizations VALUES (?, ?, ?)", (org, user, org_cust))
        if sub:
            self.db.execute("INSERT INTO subscriptions VALUES (?, ?, 'BUSINESS')", (sub, user_cust))

    def run(self, sql: str) -> list[dict]:
        self.events.append(sql)
        if sql.startswith("UPDATE") and self.stuck:
            return []
        cur = self.db.execute(sql)
        return [dict(r) for r in cur.fetchall()]

    def bookmark(self) -> str:
        self.events.append("BOOKMARK")
        return "00000001-00000002-00000003-" + "a" * 16

    def writes(self) -> list[str]:
        return [e for e in self.events if e.startswith("UPDATE")]

    def org_customer(self, org: str) -> str:
        return self.db.execute(
            "SELECT customer_id FROM organizations WHERE id=?", (org,)
        ).fetchone()[0]


def _populated(stuck: bool = False) -> FakeD1:
    d1 = FakeD1(stuck)
    d1.seed("org-a", "user-a", "cus_AAA", "user-a", "sub-a")  # the pre-fix shape
    d1.seed("org-b", "user-b", "cus_BBB", "cus_OTHER", "sub-b")  # deliberately elsewhere
    d1.seed("org-c", "user-c", None, "user-c", None)  # owner has no cus_ id
    d1.seed("org-d", "user-d", "user-d", "user-d", "sub-d")  # owner id is not a cus_ id
    d1.seed("org-e", "user-e", "cus_EEE", "user-e", None)  # cus_ id but no subscription row
    d1.seed("org-f", "user-f", "cus_FFF", "cus_FFF", "sub-f")  # already repaired
    return d1


def _args(target: str = "bench", region: str | None = None, **kw: bool) -> argparse.Namespace:
    return argparse.Namespace(
        target=target,
        region=region,
        write=kw.get("write", False),
        confirm_stable=kw.get("confirm_stable", False),
    )


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "x")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "y")


def test_selects_only_the_pre_fix_shape() -> None:
    found = mod.find(_populated().run)
    assert [m["org_id"] for m in found] == ["org-a"]
    assert found[0]["old_customer_id"] == "user-a"
    assert found[0]["new_customer_id"] == "cus_AAA"
    assert found[0]["sub_id"] == "sub-a"
    assert found[0]["plan_code"] == "BUSINESS"


def test_org_pointed_at_another_cus_id_is_not_selected() -> None:
    d1 = FakeD1()
    d1.seed("org-b", "user-b", "cus_BBB", "cus_OTHER", "sub-b")
    assert mod.find(d1.run) == []


def test_owner_without_cus_id_is_not_selected() -> None:
    d1 = FakeD1()
    d1.seed("org-c", "user-c", None, "user-c", None)
    d1.seed("org-d", "user-d", "user-d", "user-d", "sub-d")
    assert mod.find(d1.run) == []


def test_dry_run_writes_nothing_and_exits_zero() -> None:
    d1 = _populated()
    assert mod.repair(_args(), d1.run, d1.bookmark) == 0
    assert d1.writes() == []
    assert d1.org_customer("org-a") == "user-a"


def test_write_issues_the_guarded_update_per_org() -> None:
    d1 = _populated()
    d1.seed("org-g", "user-g", "cus_GGG", "user-g", "sub-g")
    assert mod.repair(_args(write=True), d1.run, d1.bookmark) == 0
    assert d1.writes() == [
        "UPDATE organizations SET customer_id = 'cus_AAA' WHERE id = 'org-a' AND customer_id = 'user-a'",
        "UPDATE organizations SET customer_id = 'cus_GGG' WHERE id = 'org-g' AND customer_id = 'user-g'",
    ]
    assert d1.org_customer("org-a") == "cus_AAA"
    assert d1.org_customer("org-b") == "cus_OTHER"
    assert mod.find(d1.run) == []


def test_write_fails_when_a_match_remains() -> None:
    d1 = _populated(stuck=True)
    assert mod.repair(_args(write=True), d1.run, d1.bookmark) == 1


def test_stable_write_without_confirm_is_refused_before_any_sql() -> None:
    d1 = _populated()
    rc = mod.run(_args("stable", "eu", write=True), runner=d1.run, bookmarker=d1.bookmark)
    assert rc == 1
    assert d1.events == []


@pytest.mark.parametrize("target", ["stable", "edge"])
def test_bookmark_is_recorded_before_the_write(target: str) -> None:
    d1 = _populated()
    rc = mod.run(
        _args(target, "eu", write=True, confirm_stable=True),
        runner=d1.run,
        bookmarker=d1.bookmark,
    )
    assert rc == 0
    assert d1.events.index("BOOKMARK") < d1.events.index(d1.writes()[0])


def test_bench_write_records_no_bookmark() -> None:
    d1 = _populated()
    assert mod.run(_args(write=True), runner=d1.run, bookmarker=d1.bookmark) == 0
    assert "BOOKMARK" not in d1.events


def test_unsafe_id_never_reaches_sql() -> None:
    bad = {
        "org_id": "o'; DROP TABLE users;--",
        "owner_id": "u",
        "old_customer_id": "u",
        "new_customer_id": "cus_X",
        "sub_id": "s",
    }
    with pytest.raises(mod.RefusedError):
        mod.update_sql(bad)
