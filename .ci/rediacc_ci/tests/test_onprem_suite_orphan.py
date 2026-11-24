"""Tests for the `orphan` on-premise suite: a stateful fake of the CLI and the daemon, the REAL `executor_orphans` tool reading a real SQLite file the fake seeds when the daemon creates a repository.

The control is the planted orphan whose audit event is absent: the tool then does not name it and the suite must fail.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.testrun import onprem_scenarios as scenarios
from rediacc_ci.testrun import onprem_stack, onprem_suites
from rediacc_ci.testrun.onprem_suites import orphan

if TYPE_CHECKING:
    import pathlib

GUID = "e9304ffc-0c96-47f2-a2fb-6076c1df6f52"
EXECUTOR = "tok-executor-value"
SCHEMA = (
    "CREATE TABLE event_log (id TEXT PRIMARY KEY, type TEXT NOT NULL, source TEXT NOT NULL, "
    "org_id TEXT, data TEXT, timestamp TEXT NOT NULL)"
)
SCENARIO = "planted_orphan_is_named_by_tool_and_listing"


def done(argv: list[str], rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, rc, out, err)


class FakeStack(onprem_stack.Runtime):
    def __init__(self, sqlite_path: pathlib.Path) -> None:
        super().__init__()
        self.sqlite_path = sqlite_path
        self.entries: dict[str, str] = {}
        self.images: set[str] = set()
        self.emit_event = True
        self.listing_ignores_events = False
        self.unset_fails = False

    def seed_event(self, name: str) -> None:
        data = {"machineName": "onprem-1", "repoName": name, "commandPath": "repo create"}
        conn = sqlite3.connect(self.sqlite_path)
        with conn:
            conn.execute(
                "INSERT INTO event_log VALUES (?, 'cli.repo.create', 'cli', 'org12345678', ?, ?)",
                ("e-%s" % name, json.dumps(data), "2026-11-24T10:00:00Z"),
            )
        conn.close()

    def run(self, argv, env=None, cwd=None, timeout=600) -> subprocess.CompletedProcess:
        if argv[0] == sys.executable:
            # The real tool, on the real SQLite file.
            return subprocess.run(
                argv, env=env, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout
            )
        args = argv[argv.index("--config") + 2 :]
        if args[0] == "--proxy":
            args = args[2:]
        if args[0] == "--output":
            args = args[2:]
        if args[:2] == ["repo", "create"]:
            self.entries[args[2]] = GUID
            self.images.add(GUID)
            if self.emit_event:
                self.seed_event(args[2])
            return done(argv)
        if args[:2] == ["repo", "list"]:
            listing = [
                {"name": n, "tags": {"latest": {"repositoryGuid": g}}}
                for n, g in self.entries.items()
            ]
            return done(argv, 0, json.dumps(listing))
        if args[:3] == ["config", "field", "unset"]:
            if self.unset_fails:
                return done(argv, 1, "", "refused")
            self.entries.pop(args[4].rsplit("/", 1)[1], None)
            return done(argv)
        if args[:4] == ["repo", "admin", "orphan", "list"]:
            events = []
            if "--executor-events" in args and not self.listing_ignores_events:
                path = args[args.index("--executor-events") + 1]
                with open(path, encoding="utf-8") as handle:
                    events = [json.loads(line) for line in handle if line.strip()]
            rows = []
            for image in sorted(self.images - set(self.entries.values())):
                hit = any(e.get("guid") == image for e in events)
                reason = (
                    "Created by the hosted executor, config write discarded"
                    if hit
                    else "not in any config"
                )
                rows.append({"guid": image, "verdict": "orphaned", "reason": reason})
            return done(argv, 0, json.dumps(rows))
        if args[:4] == ["repo", "admin", "orphan", "delete"]:
            self.images.discard(args[4].split("@")[0])
            return done(argv)
        if args[:2] == ["repo", "delete"]:
            self.entries.pop(args[2], None)
            return done(argv)
        return done(argv, 2, "", "unscripted: %s" % " ".join(args))


@pytest.fixture
def stack(tmp_path: pathlib.Path) -> FakeStack:
    sqlite_path = tmp_path / "account.sqlite"
    conn = sqlite3.connect(sqlite_path)
    with conn:
        conn.execute(SCHEMA)
    conn.close()
    return FakeStack(sqlite_path)


def _ctx(stack: FakeStack, tmp_path: pathlib.Path) -> scenarios.Context:
    (tmp_path / "executor.token").write_text(EXECUTOR + "\n", encoding="utf-8")
    env = {
        "ONPREM_DAEMON_URL": "http://127.0.0.1:8480",
        "ONPREM_DAEMON_HOME": str(tmp_path),
        "ONPREM_ACCOUNT_URL": "http://127.0.0.1:4910",
        "ONPREM_CONFIG_NAME": "onprem-stack",
        "ONPREM_MACHINE_NAME": "onprem-1",
        "ONPREM_EXECUTOR_TOKEN_FILE": str(tmp_path / "executor.token"),
        "ONPREM_ACCOUNT_SQLITE": str(stack.sqlite_path),
    }
    return scenarios.Context("onprem", env, paths.repo_root(), stack)


def _run(stack: FakeStack, tmp_path: pathlib.Path) -> dict:
    return scenarios.run_scenario(
        onprem_suites.load_all()["orphan"][SCENARIO], _ctx(stack, tmp_path)
    )


def test_the_suite_registers_one_onprem_only_scenario() -> None:
    suite = onprem_suites.load_all()["orphan"]
    assert set(suite) == {SCENARIO}
    assert suite[SCENARIO].targets == ("onprem",)


def test_a_planted_orphan_is_named_by_the_tool_and_the_listing(
    stack: FakeStack, tmp_path: pathlib.Path
) -> None:
    verdict = _run(stack, tmp_path)
    assert verdict["ok"] is True, verdict
    assert stack.images == set()
    assert stack.entries == {}


def test_a_planted_orphan_without_an_event_fails_the_control(
    stack: FakeStack, tmp_path: pathlib.Path
) -> None:
    stack.emit_event = False
    verdict = _run(stack, tmp_path)
    assert verdict["ok"] is False
    assert "did not name" in verdict["detail"]
    assert stack.images == set()


def test_a_listing_that_ignores_the_events_fails(stack: FakeStack, tmp_path: pathlib.Path) -> None:
    stack.listing_ignores_events = True
    verdict = _run(stack, tmp_path)
    assert verdict["ok"] is False
    assert "did not mark" in verdict["detail"]


def test_a_config_entry_that_cannot_be_dropped_fails_setup(
    stack: FakeStack, tmp_path: pathlib.Path
) -> None:
    stack.unset_fails = True
    verdict = _run(stack, tmp_path)
    assert verdict["ok"] is False
    assert "dropping the config entry" in verdict["detail"]


def test_entry_guid_reads_the_named_entry_only() -> None:
    listing = json.dumps([{"name": "a", "guid": GUID}, {"name": "b"}])
    assert orphan.entry_guid(listing, "a") == GUID
    assert orphan.entry_guid(listing, "b") is None
    assert orphan.entry_guid("not json", "a") is None
