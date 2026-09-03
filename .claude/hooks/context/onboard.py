#!/usr/bin/env python3
"""First touch of a context epoch: say what this session already owns.

WHY THIS EXISTS. The Stop hook already tells a session what to do -- but only
once it tries to stop, which is after the work. A fresh session, and above all a
POST-COMPACTION session, arrives with no memory of the store and learns the rules
by hitting the wall: it finishes a job, writes a `## Remaining` section from
memory, and the hook refuses it. The operator's words were that these sessions
"hit the wall and repeat the same mistakes like completing the job without
updating the remainings by invoking stop hook's commands with specific
arguments".

WHERE IT FIRES, and both alternatives were measured rather than argued (see
agent/PLAN-session-onboarding-marker.md section 4):

  * NOT SessionStart. Its output lands behind a large system prompt and two
    other blocks, and this repo has already concluded a wall of text there is
    skimmed.
  * NOT the first Edit. Session 74de73ca's first Edit was at +600 minutes and
    its first stop refusal at +17.8; its third tool call, at +1.1 minutes, was a
    Bash heredoc writing a repo file. An Edit matcher delivers ten hours late.
  * The first TOOL CALL of the epoch. Across four working sessions those landed
    at +0.3, +3.0, +0.1 and +0.3 minutes -- before every observed refusal.

THE ANTI-NAG RULE IS THE LOAD-BEARING PART. In the corpus 38 of 41 sessions never
edited a file and used 6-39 tool calls each. An unconditional first-tool-call
notice would have fired on all 38 with nothing to say, and a notice that is noise
38 times out of 41 is a notice nobody reads on the other three. So:

  arm (a)  the session OWNS open items -> speak at tool call #1.
  arm (b)  it owns nothing -> stay silent until it edits a file, then speak once.

Never both, at most one emission per epoch.

SAFETY. This is a PostToolUse hook, so it must never break a tool call: every
path exits 0, every exception is swallowed and written to state/errors.log, and
stdout stays empty unless there is genuinely something to say.
"""

import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx_budget as B

# One compaction fires SessionStart AND PostCompact. Re-arming twice would reset
# the machine and emit twice, so an arm inside this window is a no-op.
ARM_DEBOUNCE_S = 120
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def marker_file(session_id):
    """Its OWN file, deliberately not a key in the band state.

    band-notice.py load/saves that file on every tool call. Two hooks on one
    event may run in parallel, and a last-writer-wins clobber would silently
    lose either this marker or the band ladder -- a failure that looks like
    "the notice just didn't fire".
    """
    return B.state_dir() / ("%s-onboard.json" % B.session_slug(session_id))


def load_marker(session_id):
    try:
        return json.loads(marker_file(session_id).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- absent or corrupt both mean "not armed"
        return {}


def save_marker(session_id, data):
    f = marker_file(session_id)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, f)


def current_epoch(session_id):
    """Read-only peek at the band state's epoch counter.

    THE ASYMMETRY THIS EXISTS FOR: an in-place compaction can fire NEITHER
    SessionStart nor PostCompact. It still moves the epoch, through the
    usage-drop backstop in band-notice.py -- the only thing in the tree that
    sees that case. So a marker whose recorded epoch differs from the current
    one re-arms itself, and that mismatch is how this marker learns about a
    compaction no hook saw.
    """
    try:
        return int(B.load_state(session_id).get("epoch", 0))
    except Exception:  # noqa: BLE001
        return 0


def my_open_items(session_id):
    """(rows, count) for THIS session's open slice, or ([], None) if unknown.

    None is not zero. A worklist that cannot be run must not read as "you own
    nothing" -- that is arm (b)'s condition, and firing it on a broken store
    would deliver the wrong notice with confidence.
    """
    hook = Path(__file__).resolve().parents[1] / "stop" / "worklist.py"
    if not hook.is_file():
        return [], None
    try:
        r = subprocess.run(
            [sys.executable, str(hook), "--list", "--open", str(session_id)[:8]],
            capture_output=True,
            text=True,
            timeout=20,
            stdin=subprocess.DEVNULL,
            # A non-zero exit is DATA here, not an error: --list --open exits 1
            # on an EMPTY slice, which is a real answer and not a failure.
            check=False,
        )
    except Exception:  # noqa: BLE001
        return [], None
    rows = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("- [")]
    if rows:
        return rows, len(rows)
    # EXIT CODE ALONE CANNOT ANSWER THIS, and reading it as if it could was a
    # real bug here: `--list --open <session-with-nothing>` exits 1, so a plain
    # `returncode != 0 -> unknown` collapsed "owns nothing" into "cannot say"
    # and arm (b) could never fire. The empty slice announces itself in words,
    # so key on those; anything else genuinely is unknown.
    blob = (r.stdout or "") + (r.stderr or "")
    if "no actionable items" in blob or "nothing open" in blob:
        return [], 0
    return [], None


def text_owns(rows, me, store):
    verbs = (
        "  worklist.py --tick %s <id> '<evidence>'   close it; evidence is mandatory\n"
        "  worklist.py --update %s <id> <text>       progress; resets the liveness ladder\n"
        "  worklist.py --defer %s <id> <q... DEFAULT: <action>>\n" % (me, me, me)
    )
    return (
        "This session already owns %d open worklist item(s). They are in the store at\n"
        "%s, not in your context, and they survive a restart and a compaction.\n\n"
        "%s\n"
        "The Stop hook compares these rows against your last `## Remaining` section and\n"
        "refuses the turn while any remains open, so write that section FROM THIS LIST\n"
        "rather than from memory. The prefix below is already yours -- a wrong identity\n"
        "argument is the most common error and the identity check refuses it.\n\n"
        "%s" % (len(rows), store, "\n".join(rows[:12]), verbs)
    )


def text_fresh(me):
    return (
        "This session owns 0 worklist items, and you have just edited a file.\n"
        "Findings are part of the deliverable here: track one before you fix it, so it\n"
        "survives a compaction and so the Stop hook can hold the turn open for it.\n\n"
        "  worklist.py --add %s <text...>            prints its #id\n"
        "  worklist.py --tick %s <id> '<evidence>'   evidence is MANDATORY and is\n"
        "        checked: a sha, a run id, a file:line that resolves, an exit code or\n"
        "        a URL. A tick without one is refused.\n\n"
        "Measured on this repo: 38 of 41 sessions never edited a file, which is why\n"
        "this notice waited until you did rather than firing on tool call #1." % (me, me)
    )


def emit(text):
    json.dump(
        {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}},
        sys.stdout,
    )
    sys.stdout.write("\n")


def arm(session_id):
    """SessionStart / PostCompact. epoch is written as null ON PURPOSE.

    At PostCompact the registered hooks may run in parallel, so this cannot know
    whether the epoch counter has been bumped yet, and reading it here would be
    a race. The next tool call adopts whatever epoch it sees, in a
    single-writer context.
    """
    m = load_marker(session_id)
    now = time.time()
    if (
        m.get("state") in ("armed", "await-edit")
        and now - float(m.get("armed_at", 0)) < ARM_DEBOUNCE_S
    ):
        return  # one compaction fires both hooks; this is the same arming
    save_marker(session_id, {"state": "armed", "epoch": None, "armed_at": now})


def main():
    if os.environ.get("ONBOARD_NOTICE") == "off":
        sys.exit(0)
    ev = B.read_event()
    session_id = ev.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    if not session_id:
        sys.exit(0)

    if "--arm" in sys.argv:
        arm(session_id)
        sys.exit(0)
    if "--audit" in sys.argv:
        print(json.dumps(load_marker(session_id), sort_keys=True))
        sys.exit(0)

    # A subagent has its own id and its own short life; it is not the session
    # that will face the Stop hook, so telling it about the store is pure noise.
    if ev.get("parent_tool_use_id") or os.environ.get("CLAUDE_AGENT_TYPE"):
        sys.exit(0)

    m = load_marker(session_id)
    if not m:
        sys.exit(0)  # never armed: nothing to say
    epoch = current_epoch(session_id)
    if m.get("state") == "delivered" and m.get("epoch") == epoch:
        sys.exit(0)
    if m.get("state") == "delivered":
        m = {"state": "armed", "epoch": None, "armed_at": time.time()}  # epoch moved: re-arm

    tool = ev.get("tool_name") or ""
    rows, n = my_open_items(session_id)
    if n is None:
        sys.exit(0)  # cannot say; silence beats the wrong notice

    me = str(session_id)[:8]
    if n > 0:
        store = (Path.cwd() / ".claude" / "hooks" / "stop" / "worklist.py").as_posix()
        emit(text_owns(rows, me, store))
    elif tool in EDIT_TOOLS:
        emit(text_fresh(me))
    else:
        # Arm (b): owns nothing and has not edited yet. Stay armed, say nothing.
        m["state"] = "await-edit"
        m["epoch"] = epoch
        save_marker(session_id, m)
        sys.exit(0)

    save_marker(
        session_id, {"state": "delivered", "epoch": epoch, "armed_at": m.get("armed_at", 0)}
    )
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- a PostToolUse hook must never break a tool call
        with contextlib.suppress(Exception):
            B.log_error("onboard", exc)
        sys.exit(0)
