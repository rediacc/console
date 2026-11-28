"""wl_soakedpins: the Stop hook's "soaked pins available" advisory (agent/plans/PLAN-pins-command.md, T11).

`.github/workflows/ops-pins-soaked.yml` runs `npm run pins -- apply-soaked --json --out pins-soaked/` daily and uploads the directory as the `pins-soaked` artifact. A session that downloads it (`gh run download -n pins-soaked -D .ci/cache/pins-soaked`) or runs the verb itself with `--out .ci/cache/pins-soaked` leaves a `report.json` there. The advisory half reads that file and nothing else: no network call, no subprocess, no git. The daily route (`run_daily`, PLAN-ciquick-gate-contract K6) is the one exception: it claims the UTC day and starts the verb as a detached subprocess (`_spawn`), whose runner (`run_verb`) records the result in the stamp. A missing, unreadable, empty or stale report is silence, because the advisory describes work that could be done and "not measured" must never become a refusal to stop.

The advisory is report-only. Its effort row (`soaked-pins` in .claude/config/effort.json) puts it at the smart level and above, and the check never blocks at any level.
"""

import contextlib
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time

REPORT_REL = ".ci/cache/pins-soaked/report.json"

# The job runs daily; a report older than this describes a tree that has since moved on.
MAX_AGE_H = 72

MAX_LISTED = 8

# THE DAILY LOCAL ROUTE (agent/plans/PLAN-ciquick-gate-contract.md K6). The Stop hook of the development tree runs `npm run pins -- apply-soaked` once per UTC day, so a freshness bump lands at a loop boundary and never depends on a GitHub trigger. The verb edits files and never commits; the per-repo commits are the lead's. The stamp is written BEFORE the verb starts (a claim: a second stop on the same day finds it and does nothing, and a verb that dies is not retried until tomorrow), and the detached runner rewrites it with the result.
STAMP_REL = ".ci/cache/pins-soaked/last-run.json"
LANDING = "landing"
VERB = ["npm", "run", "pins", "--", "apply-soaked", "--json", "--out", ".ci/cache/pins-soaked"]
# The verb's own budget; the Stop hook's is 900 s and the hook only claims and spawns, so it spends milliseconds.
VERB_TIMEOUT_S = 600


def report_path(root):
    return pathlib.Path(root) / REPORT_REL


def _parse(stamp):
    try:
        return datetime.datetime.strptime(str(stamp), "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=datetime.UTC
        )
    except ValueError:
        pass
    try:
        return datetime.datetime.strptime(str(stamp), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.UTC
        )
    except ValueError:
        return None


def read(root, now=None):
    """The soaked pins in the latest report as [(id, from, to)], or [] when there is nothing to advise.

    `now` is a datetime (UTC) and defaults to the clock. A report with no parseable `now` stamp is treated as stale: its age is unknown.
    """
    try:
        doc = json.loads(report_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(doc, dict) or not isinstance(doc.get("pins"), list):
        return []
    made = _parse(doc.get("now"))
    if made is None:
        return []
    clock = now or datetime.datetime.now(datetime.UTC)
    if (clock - made).total_seconds() > MAX_AGE_H * 3600:
        return []
    return [
        (str(p["id"]), str(p.get("from") or "?"), str(p["to"]))
        for p in doc["pins"]
        if isinstance(p, dict) and p.get("id") and p.get("to")
    ]


def advisory(root, now=None):
    """The advisory text, or None when nothing is soaked."""
    pins = read(root, now)
    if not pins:
        return None
    lines = ["  %s: %s -> %s" % p for p in pins[:MAX_LISTED]]
    if len(pins) > MAX_LISTED:
        lines.append("  (+%d more)" % (len(pins) - MAX_LISTED))
    return (
        "SOAKED PINS AVAILABLE (%d, from %s):\n%s\n"
        "  Apply on this branch with `npm run pins -- apply-soaked --task <id>`; it never commits. "
        "Report-only: nothing here blocks."
    ) % (len(pins), REPORT_REL, "\n".join(lines))


def stamp_path(root):
    return pathlib.Path(root) / STAMP_REL


def _today(now):
    return (now or datetime.datetime.now(datetime.UTC)).strftime("%Y-%m-%d")


def _is_lease(root):
    return "/.claude/worktrees/" in str(pathlib.Path(root).resolve()).replace(os.sep, "/")


def due(root, role, now=None):
    """True when the daily route should run here now: a development (or record-less) tree, not a lease, with no stamp for today's UTC date. A stamp that is unreadable counts as absent."""
    if role == LANDING or _is_lease(root):
        return False
    try:
        doc = json.loads(stamp_path(root).read_text(encoding="utf-8"))
        return not (isinstance(doc, dict) and doc.get("day") == _today(now))
    except (OSError, ValueError):
        return True


def _write_stamp(root, doc):
    path = stamp_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run_daily(root, role, now=None, spawn=None):
    """Claim today's run and start the verb, at most once per UTC day. Returns the claim written, or None when nothing was due. `spawn(root)` starts the detached runner and defaults to this file's `--run`; a test passes a fake. Never raises: the route is housekeeping and must not stop a stop."""
    try:
        if not due(root, role, now):
            return None
        claim = {"day": _today(now), "state": "started", "rc": None}
        _write_stamp(root, claim)
        try:
            (spawn or _spawn)(str(root))
        except Exception as error:
            # Review 86953e7c.2: a spawn that fails must not consume the day. The claim is released so the next stop retries, and the failure is recorded beside it.
            with contextlib.suppress(OSError):
                _write_stamp(
                    root,
                    {
                        "day": None,
                        "state": "spawn-failed",
                        "rc": None,
                        "error": str(error)[:200],
                        "failed_day": claim["day"],
                    },
                )
            return None
        return claim
    except Exception:
        return None


def _spawn(root):
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--run", str(root)],
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def run_verb(root, runner=None, clock=time.monotonic):
    """Run the verb and record its result (rc, seconds, tail of its output) in the stamp, keeping the claim's day. `runner(root)` returns (rc, text) and defaults to the real verb."""
    day = _today(None)
    try:
        doc = json.loads(stamp_path(root).read_text(encoding="utf-8"))
        day = doc.get("day", day)
    except (OSError, ValueError):
        pass
    started = clock()

    def real(r):
        p = subprocess.run(
            VERB, cwd=r, capture_output=True, text=True, timeout=VERB_TIMEOUT_S, check=False
        )
        return p.returncode, p.stdout + p.stderr

    try:
        rc, text = (runner or real)(str(root))
    except Exception as exc:
        rc, text = 1, "%s: %s" % (type(exc).__name__, exc)
    result = {
        "day": day,
        "state": "done",
        "rc": rc,
        "seconds": round(clock() - started, 3),
        "tail": text[-400:],
    }
    _write_stamp(root, result)
    return result


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--run":
        run_verb(sys.argv[2])
