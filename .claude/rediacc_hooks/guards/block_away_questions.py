"""Refuse an AskUserQuestion while the operator is away from the keyboard (`/awk`).

WHY. The operator sets `/awk` before leaving for the night: "it should avoid asking questions until the operator writes a messages" (2026-11-08T19:27Z). A question put to an absent operator holds the turn until morning, which is a night of work lost to one round trip. A decision that is genuinely the operator's is parked as a `[?]` with a DEFAULT, which executes on its timer when nobody answers; everything else the session settles itself.

WHAT IS READ. The away flag (`.claude/hooks/stop/wl_away.py`, one per checkout), and this session's transcript after the flag's `since`. An operator message there (a typed turn, an interrupt, or a message queued mid-turn) clears the flag and lets the question through, so the first word from the operator ends the mode with no command to remember.

FAILS OPEN. No flag, an unreadable flag, or a stop directory that cannot be imported lets the question through: blocking a question over this guard's own breakage would trade the feature's failure for a worse one.
"""

import json
import pathlib

from rediacc_hooks import hookio, syspath

CHAIN = "pre-ask"
OWN_SUITE = True
ORDER = 4

# The away test. With it forced off every question reaches an absent operator.
DEFECT = ("doc = wl_away.away(transcript)", "doc = None")


def _flag_world(path):
    """A flag set long before any record, so every payload meets an away operator."""
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    (pathlib.Path(path) / "away.json").write_text(
        json.dumps({"since": "2000-01-01T00:00:00.000000Z", "note": "fixture"})
    )
    return path


def _empty_world(path):
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    return path


FIXTURES = {"away-flag-set": _flag_world, "away-flag-none": _empty_world}

# Both worlds pin WL_AWAY_STATE: an unpinned one would read the live flag, and a session that ran `/awk` would flip every answer.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {"WL_AWAY_STATE": "{FIXTURE:away-flag-none}"}, {}),
    ("away", {"WL_AWAY_STATE": "{FIXTURE:away-flag-set}"}, {}),
]

EDGE_CASES = [
    ("a design question", "Which bucket should the restore test use?"),
    ("a permission question", "Should the edge deploy take the live key?"),
]

MESSAGE = (
    "BLOCKED: the operator is away from the keyboard (/awk, since %s), so this question\n"
    "would hold the turn until they return.\n"
    "\n"
    "Decide it: anything the code, the request, a ruling or a sensible default settles\n"
    "belongs to this session. A decision that is genuinely the operator's is parked\n"
    "instead, and its DEFAULT executes when the window closes unanswered:\n"
    "\n"
    "    .claude/hooks/stop/worklist.py --defer <me> <id> '<question> DEFAULT: <action> WHY: ... HOW: ...'\n"
    "\n"
    "Then keep working. The mode ends by itself at the operator's next message.\n"
)


def run(ev):
    try:
        syspath.on_sys_path(syspath.STOP_DIR)
        import wl_away
    except ImportError:
        return hookio.ALLOW
    transcript = ev.field("transcript_path")
    if transcript in ("", "null"):
        transcript = ""
    try:
        doc = wl_away.away(transcript)
    except (
        Exception
    ) as exc:  # A transcript this reader cannot parse fails open, like a missing flag.
        ev.warn(
            "block_away_questions: away check failed (%s); the question passes unexamined" % exc
        )
        return hookio.ALLOW
    if doc is None:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % doc["since"])
    return hookio.DENY
