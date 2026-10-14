"""wl_soakedpins: the Stop hook's "soaked pins available" advisory (agent/plans/PLAN-pins-command.md, T11).

`.github/workflows/pins-soaked.yml` runs `npm run pins -- apply-soaked --json --out pins-soaked/` daily and uploads the directory as the `pins-soaked` artifact. A session that downloads it (`gh run download -n pins-soaked -D .ci/cache/pins-soaked`) or runs the verb itself with `--out .ci/cache/pins-soaked` leaves a `report.json` there. This module reads that file and nothing else: no network call, no subprocess, no git. A missing, unreadable, empty or stale report is silence, because the advisory describes work that could be done and "not measured" must never become a refusal to stop.

The advisory is report-only. Its effort row (`soaked-pins` in .claude/config/effort.json) puts it at the smart level and above, and the check never blocks at any level.
"""

import datetime
import json
import pathlib

REPORT_REL = ".ci/cache/pins-soaked/report.json"

# The job runs daily; a report older than this describes a tree that has since moved on.
MAX_AGE_H = 72

MAX_LISTED = 8


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
