"""The `orphan` suite: an orphan the daemon executor leaves behind is named by the ops tool and by the CLI listing (PLAN-rmcp-orphan-recovery.md, Design 5, box OR-OP1).

The scenario creates a repository through the daemon, drops its config entry (the state a pre-write-back executor left behind: an image on the machine, no record), then requires two things. `executor_orphans list --target onprem --sqlite <the stack's account database>` prints the daemon's `repo create` event for that repo name, and `rdc repo admin orphan list <machine> --executor-events <that output>` marks the image as executor-created.

THE GUID. The audit schema carries no GUID, so a real event joins the image on its repo name only after the GUID is known. The scenario reads the GUID from the config entry before dropping it and writes it into the events file it hands the listing, which is the step a sweep performs from a host-side image list. The tool's own output must still name the repo, so a missing event fails the scenario.

The scenario needs the machines of a `--machines vm` stack and runs against the stack only.
"""

from __future__ import annotations

import json
import pathlib
import re
import secrets
import sys
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci.testrun.onprem_suites import Result, failed, passed, scenario

if TYPE_CHECKING:
    import subprocess

    from rediacc_ci.testrun.onprem_scenarios import Context

REPO_SIZE = "1G"
GUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
EXECUTOR_REASON = "executor"


def _tail(done: subprocess.CompletedProcess[str]) -> str:
    return (done.stderr.strip() or done.stdout.strip())[-200:]


def _daemon(ctx: Context) -> dict:
    return {"token": ctx.token("executor"), "proxy": ctx.value("ONPREM_DAEMON_URL")}


def entry_pointer(name: str) -> str:
    return "/resources/repositories/%s" % name


def entry_guid(listing: str, name: str) -> str | None:
    """The GUID of repository `name` in `rdc --output json repo list`: the first GUID inside its entry."""
    try:
        data = json.loads(listing)
    except ValueError:
        return None
    entries = data if isinstance(data, list) else data.get("repositories", [])
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") == name:
            found = GUID_RE.search(json.dumps(entry))
            return found.group(0) if found else None
    return None


def tool_events(ctx: Context) -> tuple[list[dict], str]:
    """The `executor_orphans list --target onprem --json` lines read from the stack's account database, and its stderr."""
    done = ctx.exec(
        [
            sys.executable,
            "-m",
            "rediacc_ci.ops.executor_orphans",
            "list",
            "--target",
            "onprem",
            "--sqlite",
            ctx.value("ONPREM_ACCOUNT_SQLITE"),
            "--json",
        ],
        env={"PYTHONPATH": str(ctx.root / ".ci"), "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    if done.returncode != 0:
        raise RuntimeError("executor_orphans exited %d: %s" % (done.returncode, _tail(done)))
    return [json.loads(line) for line in done.stdout.splitlines() if line.strip()], done.stderr


def named_by_tool(events: list[dict], name: str) -> dict | None:
    return next((e for e in events if e.get("repo") == name), None)


def listing_marks(ctx: Context, events_file: pathlib.Path, guid: str) -> str | None:
    """The listing's reason for `guid` when it is an executor orphan, or None; raises when the listing itself fails."""
    done = ctx.rdc(
        "--output",
        "json",
        "repo",
        "admin",
        "orphan",
        "list",
        ctx.value("ONPREM_MACHINE_NAME"),
        "--executor-events",
        str(events_file),
    )
    if done.returncode != 0:
        raise RuntimeError("repo admin orphan list exited %d: %s" % (done.returncode, _tail(done)))
    for row in json.loads(done.stdout):
        if str(row.get("guid", "")).lower() == guid and row.get("verdict") == "orphaned":
            reason = str(row.get("reason", ""))
            return reason if EXECUTOR_REASON in reason else None
    return None


def settle(ctx: Context, guid: str) -> None:
    """Remove the planted image; a failure is reported by the next run's listing, not hidden."""
    ctx.rdc(
        "repo",
        "admin",
        "orphan",
        "delete",
        "%s@%s" % (guid, ctx.value("ONPREM_MACHINE_NAME")),
        "--yes",
        "--force-delete-mounted",
    )


@scenario("orphan", "planted_orphan_is_named_by_tool_and_listing")
def planted_orphan_is_named_by_tool_and_listing(ctx: Context) -> Result:
    name = "orph-%s" % secrets.token_hex(3)
    machine = ctx.value("ONPREM_MACHINE_NAME")
    made = ctx.rdc(
        "repo", "create", name, "--machine", machine, "--size", REPO_SIZE, **_daemon(ctx)
    )
    if made.returncode != 0:
        return failed(
            "setup: repo create exited %d: %s" % (made.returncode, _tail(made)), made.returncode
        )
    listed = ctx.rdc("--output", "json", "repo", "list")
    guid = entry_guid(listed.stdout, name) if listed.returncode == 0 else None
    if guid is None:
        ctx.rdc("repo", "delete", name, "--yes")
        return failed("setup: no GUID in the config entry of %s" % name, listed.returncode)
    dropped = ctx.rdc("config", "field", "unset", "--pointer", entry_pointer(name))
    if dropped.returncode != 0:
        ctx.rdc("repo", "delete", name, "--yes")
        return failed(
            "planting: dropping the config entry exited %d: %s"
            % (dropped.returncode, _tail(dropped)),
            dropped.returncode,
        )
    try:
        events, _ = tool_events(ctx)
        event = named_by_tool(events, name)
        if event is None:
            return failed(
                "executor_orphans did not name %s among %d event(s)" % (name, len(events)), 0
            )
        with tempfile.TemporaryDirectory() as scratch:
            events_file = pathlib.Path(scratch) / "events.jsonl"
            events_file.write_text(json.dumps({**event, "guid": guid}) + "\n", encoding="utf-8")
            reason = listing_marks(ctx, events_file, guid)
        if reason is None:
            return failed("the listing did not mark %s as an executor orphan" % guid, 0)
        return passed(reason)
    except (RuntimeError, ValueError) as exc:
        return failed(str(exc), None)
    finally:
        settle(ctx, guid)
