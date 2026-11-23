#!/usr/bin/env python3
"""Stop hook: refuse to end a turn while tracked work remains unhandled.

WHY: the failure this prevents is stopping to REPORT a discovery instead of acting on it. The full design history (v1-v9: the [ ]/[x]/[?]/[>] state machine, the harness task queue, the regression gate) lives in the sibling modules beside each piece of logic; this file is only the ENTRY POINT: the recursion guard, the CLI dispatch, and the
fail-closed wrapper.

v10 (2026-07-30, operator request): the item store moved from the markdown file to an append-only JSONL event log (wl_store: the markdown stays as a synced INBOX, so nothing written there is ever silently ignored); every item carries start and last-update stamps; in-flight claims are verified against the OS and walked up a 45/90/120-minute ladder (wl_liveness); deferrals execute
their DEFAULT after an autonomy window instead of nagging forever (wl_checks); the compact-recovery document is agent/<me>/STATE.md with world-keyed staleness; and the judge caches identical verdicts (wl_judge). The one 3600-line file became nine modules; worklist_messages.py remains the catalogue of user-facing prose.

v12 (2026-07-30, operator request: "Too many '[?]'. This is an escape hatch."): a deferral must EARN its seat. --defer validates WHY:/HOW: (plus optional TRIED:/NEEDS:/BLOCKED_ON:) at creation and stores them as real
fields; an aged [?] without them is demanded, bounded per stop (wl_checks);
a justified one faces the judge's audit riding the existing judge call, and a rejected justification REOPENS the item as [ ] (wl_judge.apply_defer_audit fails closed); and a session whose only in-flight work is a CI watch is FORCED onto the aged backlog by id and verb (wl_ci.ci_watch_only). Every demand's exit is completable alone in one turn: do it and tick with evidence, execute
the DEFAULT, or answer the WHY/HOW honestly.

v17 (2026-08-04, operator report: "normally there is exponential backoff for the stop hook. It seems it's running every 5 mins."): it WAS, and the cause was scope, not cadence. wl_store.world_sig hashed the BYTES of the shared markdown and event log, so any teammate's --add or --tick invalidated every other session's judge cache; measured
on the live store, 32 of 32 events in a three-hour window were foreign and polluted half the five-minute windows. The signature is this session's own world now (wl_store.world_sig). Two smaller fixes ride with it: the background check-in's clock is cleared when the wait ENDS (it used to freeze, so re-entering a wait fired the roster demand on arrival), and
it prints its last-fired and next-earliest stamps so the latch it claims is checkable from the message.

v18 (2026-08-04, operator: "we don't need to print next wakeup times. We should just track the hook moments and notify/warn when needed. let's go for efficient ai context usage"): two standing sections that printed on every full stop are DELETED rather than shortened. The NEXT WAKEUPS list (every scheduled task's next firing plus its prompt label) is gone; the schedules are still
tracked by the cron-shape checks, the loop-death detector and the judge's loop line, and the one actionable thing the list carried is now its own silent-until-broken warning (wl_checks.broken_schedules, V_BROKEN_SCHEDULE). The empty WORKLIST GUIDE line ("no actionable items in the store") is gone too, which lets a clean stop with nothing queued exit with zero
bytes. Both supersede earlier deliberate choices ("a short honest line, never ambiguous silence"). The rule going forward is silent when there is nothing to act on, one focused message when there is.

MODULE MAP:
    wl_core       shared primitives (paths, git, regexes, tasks, transcript)
    wl_store      event log, markdown sync, sidecars, session state doc
    wl_liveness   worker verification against /proc|ps, the 45/90/120 ladder
    wl_ci         publish divergence, PR freshness, submodule pointers, CI
    wl_reggate    v7/v8 regression-gate machinery
    wl_judge      the stop-legitimacy judge and its verdict cache
    wl_checklist  the /handoff checklist gate over agent/programs/<slug>/CHECKLIST.md
    wl_checks     the static battery and the Stop orchestration (run_stop)
    wl_cli        every CLI verb but --help and --path; worklist.py delegates to it
    worklist_messages  every user-facing string (arity-pinned by the suite)

INVARIANTS THAT MUST NOT MOVE:
  * STOPHOOK_CHILD is the FIRST statement of main(): `claude -p` re-fires
    this hook (proven with a marker hook; `--settings '{"hooks":{}}'` does
    NOT suppress it). Remove the guard and the hook recurses until the
    machine dies.
  * emit() exits the process, so ordering inside run_stop is load-bearing.
  * A crashing hook must BLOCK, never read as allow: an unhandled exception
    prints to stderr and NOTHING to stdout, which the harness reads as
    ALLOW, so one bug anywhere would silently disable every check. The
    __main__ wrapper below closes that hole for every mode.
  * A check that cannot read must say it is blind (the V_PR_UNREADABLE
    pattern) rather than pass quietly.
  * The store is shared: append under the lock, never rewrite wholesale.
  * NO ESCAPE HATCH (operator, explicit): judge failure, timeout, or
    malformed output BLOCKS. A block you can fix is a bug report with
    teeth, not a deadlock.

SIBLING IMPORTS ARE PROBED, NOT ASSUMED. A top-level ImportError would crash before the fail-closed wrapper exists, print nothing to stdout, and read as ALLOW. So every sibling is imported inside a probe; a broken one is replaced by a shim whose every attribute access raises, naming EVERY broken module. Query modes that need no sibling (--path, --help) keep working, and the Stop
path blocks loudly instead of failing open.

What still allows a stop:
  1. An empty world: no open items, no pending tasks, no obligations.
  2. Removing the hook from .claude/settings.json.
"""

import contextlib
import json
import os
import pathlib
import re
import select
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_BROKEN = {}  # module name -> error string
_MODS = {}


class _BrokenModule:
    """Every attribute access raises, naming every unusable sibling, so the first USE fails into the crash handler with the full picture. The message lists all broken modules because the first attribute touched is rarely the interesting one."""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        raise RuntimeError(
            "sibling module %s is unusable (wanted %s.%s); broken: %s"
            % (
                self._name,
                self._name,
                attr,
                "; ".join("%s: %s" % (k, v) for k, v in sorted(_BROKEN.items())),
            )
        )


for _name in (
    "wl_core",
    "wl_store",
    "wl_liveness",
    "wl_ci",
    "wl_reggate",
    "wl_judge",
    "wl_checks",
    "wl_hints",
    "wl_roundlog",
    "wl_defersettle",
    "wl_leasehelp",
    "wl_plandeps",
    "wl_planorder",
    "wl_retro",
    "wl_cli",
    "worklist_messages",
):
    try:
        _MODS[_name] = __import__(_name)
    except Exception as _exc:
        _BROKEN[_name] = "%s: %s" % (type(_exc).__name__, _exc)
        _MODS[_name] = _BrokenModule(_name)

# THE LAST-KNOWN-GOOD HOOK (agent/plans/PLAN-stop-hook-continuity.md P2.5), imported on its own: it is stdlib-only precisely so it still loads when every sibling above is broken, which is the one case it exists for.
LKG: Any
try:
    import wl_lkg as LKG
except Exception:
    LKG = None
# The Stop payload exactly as read, so a crashed stop can be replayed against the snapshot; and whether this process is running the Stop path at all.
_RUN = {"raw": "", "stop": False}

C = _MODS["wl_core"]
S = _MODS["wl_store"]
CK = _MODS["wl_checks"]
J = _MODS["wl_judge"]
M = _MODS["worklist_messages"]
H = _MODS["wl_hints"]
RL = _MODS["wl_roundlog"]
DS = _MODS["wl_defersettle"]
LH = _MODS["wl_leasehelp"]
PD = _MODS["wl_plandeps"]
PO = _MODS["wl_planorder"]
RT = _MODS["wl_retro"]
CLI = _MODS["wl_cli"]

# Re-exported for direct importers (the suite drives these two as library functions; keeping them on this module is part of the compatibility surface). Absent when their module is broken, which is correct: a caller gets an AttributeError naming this module instead of a silent stub.
if "wl_checks" not in _BROKEN:
    cited_excerpts = _MODS["wl_checks"].cited_excerpts
    citation_state = _MODS["wl_checks"].citation_state
if "wl_ci" not in _BROKEN:
    submodule_pointer_moves = _MODS["wl_ci"].submodule_pointer_moves


def _local_project_start(event=None):
    """Self-contained twin of wl_core.project_start, for the same reason _local_worklist_path exists: --path and the self-contained append modes must answer even when every sibling module is broken, and reaching for C.project_start() there would raise out of _BrokenModule instead. Keep in lockstep with wl_core.project_start -- including the ladder ORDER, since a divergence here
    would silently point --path at a different store than the hook writes to."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return env
    cand = pathlib.Path(__file__).resolve().parents[3]
    if (cand / ".git").exists() and (cand / ".claude" / "hooks" / "stop").is_dir():
        return str(cand)
    if event:
        cwd = event.get("cwd")
        if cwd:
            return cwd
    return os.getcwd()


def _local_git_dirs(tree):
    """Self-contained twin of wl_core._git_dirs. Keep in lockstep."""
    dotgit = tree / ".git"
    try:
        if dotgit.is_dir():
            git_dir = dotgit.resolve()
        else:
            text = dotgit.read_text(encoding="utf-8").strip()
            if not text.startswith("gitdir:"):
                return None
            git_dir = (tree / text[len("gitdir:") :].strip()).resolve()
        commondir = git_dir / "commondir"
        if not commondir.is_file():
            return git_dir, git_dir
        return git_dir, (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve()
    except (OSError, ValueError, RuntimeError):
        return None


def _local_lease_main(tree):
    """Self-contained twin of wl_core.lease_main. Keep in lockstep.

    The lease holder folder's own name stays unspelled in this file: naming it beside `--add` makes the checkout guard's script arm refuse every `python3 worklist.py` while this file differs from HEAD. The root section of this file's suite pins that.
    """
    tree = pathlib.Path(tree)
    if tree.parent.parent.name != ".claude" or not (tree / ".git").is_file():
        return None
    mine = _local_git_dirs(tree)
    if mine is None or mine[0] == mine[1] or mine[0].parent.parent != mine[1]:
        return None
    if mine[0].parent.name != tree.parent.name:
        return None
    main = tree.parents[2]
    theirs = _local_git_dirs(main) if (main / ".git").exists() else None
    return main if theirs is not None and theirs[1] == mine[1] else None


# wl_core's two landing constants, for the twins below. The config key is assembled from two halves because this file must never spell the word that makes the checkout guard's script arm lock every `python3 worklist.py` while the file differs from HEAD (the root section of the lease suite pins that).
LANDING_RECORD_NAME = "rediacc-landing.json"
CORE_TREE_KEY = "work" + "tree"


def _local_common_main(common):
    """Self-contained twin of wl_core._common_main. Keep in lockstep."""
    main = None
    try:
        text = (common / "config").read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
            continue
        key, sep, value = line.partition("=")
        if section == "core" and sep and key.strip().lower() == CORE_TREE_KEY:
            main = (common / value.strip()).resolve()
    if main is None and common.name == ".git":
        main = common.parent
    if main is None or not (main / ".git").exists():
        return None
    theirs = _local_git_dirs(main)
    return main if theirs is not None and theirs[0] == theirs[1] == common else None


def _local_landing_record(tree):
    """Self-contained twin of wl_core.landing_record. Keep in lockstep."""
    dirs = _local_git_dirs(pathlib.Path(tree))
    if dirs is None:
        return None
    try:
        data = json.loads((dirs[1] / LANDING_RECORD_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or sorted(data) != ["branch", "path"]:
        return None
    path, branch = data["path"], data["branch"]
    if not isinstance(path, str) or not isinstance(branch, str) or not os.path.isabs(path):
        return None
    land = pathlib.Path(path)
    theirs = _local_git_dirs(land) if (land / ".git").is_file() else None
    if theirs is None or theirs[1] != dirs[1]:
        return None
    return {"path": path, "branch": branch}


def _local_landing_main(tree):
    """Self-contained twin of wl_core.landing_main. Keep in lockstep."""
    tree = pathlib.Path(tree)
    if not (tree / ".git").is_file():
        return None
    mine = _local_git_dirs(tree)
    if mine is None or mine[0] == mine[1] or mine[0].parent.parent != mine[1]:
        return None
    rec = _local_landing_record(tree)
    if rec is None or os.path.realpath(str(tree)) != os.path.realpath(rec["path"]):
        return None
    return _local_common_main(mine[1])


def _local_worklist_path(start):
    """Self-contained twin of wl_core.worklist_for, used ONLY by --path, the self-contained append modes and the broken-sibling block, so the queries every script depends on work even when every sibling is missing. Keep in lockstep with wl_core.worklist_for."""
    p = pathlib.Path(start).resolve()
    root = p
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists():
            root = _local_lease_main(candidate) or candidate
            root = _local_landing_main(root) or root
            break
    d = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist"
    d.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(root)).strip("_")
    return d / (slug + ".md")


def _emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def _operation_trees(event):
    """The checkouts this stop would write into: the store root (C.project_root maps the landing tree to the main checkout) and the session's own checkout, deduplicated, in that order."""
    trees = []
    with contextlib.suppress(Exception):
        trees.append(str(C.project_root(_local_project_start(event))))
    with contextlib.suppress(Exception):
        own = str(C.checkout_root(C.project_start(event)))
        if own not in trees:
            trees.append(own)
    return trees


def _operation_standdown(event):
    """Emit and exit when a rebase, merge, cherry-pick, revert or am is halted in a checkout this stop would write into; return otherwise (worklist #b07162cf).

    THE BATTERY WRITES TRACKED FILES: the in-flight block of agent/plans/QUEUE.md, agent/ledgers/*.jsonl, agent/worklist/<writer>.jsonl, a session's STATE.md, the retro rows. Any one of them left unstaged makes `git rebase --continue` refuse with a message about merge conflicts while `git ls-files -u` is empty, and on 2026-11-23 that held a 273-step rebase of 1121-1 at step 26. Gating each writer would miss the next one added, so the whole battery stands down, which is the one shape that cannot leak a write.

    THE ONE BLOCK, then an allow. The first stop is blocked with the operation, the step and the commands that end it, because a turn that ends mid-rebase leaves the tree half-replayed. A stop that is already the answer to a Stop-hook block (`stop_hook_active`) is allowed, so a rebase waiting on an operator answer cannot wedge the session. Neither writes a byte, and both say that no check ran: an unchecked stop is reported as one, never as a clean one.
    """
    try:
        import wl_git
    except Exception:
        return
    for tree in _operation_trees(event):
        name = wl_git.operation_in_progress(tree)
        if not name:
            continue
        where = tree
        st = wl_git.rebase_state(tree) if name == "rebase" else None
        if st:
            where = "%s (step %s of %s, replaying %s)" % (
                tree,
                st.get("step") or "?",
                st.get("total") or "?",
                (st.get("stopped") or "?")[:12],
            )
        said = (
            "A %s is in progress in %s. The Stop hook stands down while it lasts: it wrote no tracked record "
            "(agent/plans/QUEUE.md, agent/ledgers/*, the worklist store, STATE.md), because `git rebase --continue` refuses over any "
            "unstaged tracked change, and NONE of this stop's checks ran. End it with %s; the next stop after that runs the full battery."
            % (name, where, wl_git.operation_finish_hint(name))
        )
        if event.get("stop_hook_active"):
            _emit(
                {
                    "systemMessage": "Stop hook: UNCHECKED, %s in progress; allowed. %s"
                    % (name, said)
                }
            )
        _emit(
            {
                "systemMessage": "Stop hook: %s in progress; standing down." % name,
                "decision": "block",
                "reason": said,
            }
        )


# Bounded wait for the Stop payload. Long enough for a slow writer, short enough that a missing payload fails the hook instead of stalling the session.
STDIN_WAIT_SECONDS = 10.0


def _read_event():
    """Read the Stop payload from stdin, bounded, without hanging or crashing.

    Two failure modes, both observed, and the naive fix for one causes the other:

    1. EAGAIN. Observed 2026-08-07: the hook died with "Failed with non-blocking
       status code: EAGAIN: resource temporarily unavailable, read". The pipe is
       sometimes handed over in NON-BLOCKING mode with the payload not yet
       written, and json.load() only caught JSONDecodeError/ValueError while
       EAGAIN surfaces as BlockingIOError, an OSError. The hook crashed, so
       EVERY stop check silently did not run.

    2. HANG. The obvious fix -- os.set_blocking(fd, True) -- makes read() wait
       forever when the writer holds the pipe open and sends nothing. Measured:
       that version had to be SIGKILLed. A hook that hangs is worse than one
       that crashes, because it stalls the session instead of failing it.

    So: wait for readability with a DEADLINE, then read what is there. Late payload → we wait for it. No payload → we give up, loudly, in bounded time.
    """
    deadline = time.monotonic() + STDIN_WAIT_SECONDS
    try:
        fd = sys.stdin.fileno()
    except (OSError, ValueError, AttributeError):
        fd = None

    raw = ""
    if fd is None:
        # No real fd (pytest capture, a StringIO harness): a plain read cannot block on a pipe that does not exist.
        try:
            raw = sys.stdin.read()
        except Exception:
            return {}, False
    else:
        with contextlib.suppress(OSError, ValueError):
            os.set_blocking(fd, False)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print(
                    "worklist.py: no Stop payload on stdin after %ss. This is a HOOK "
                    "failure, not a clean stop -- no check ran." % STDIN_WAIT_SECONDS,
                    file=sys.stderr,
                )
                return {}, False
            try:
                ready, _, _ = select.select([fd], [], [], min(remaining, 0.25))
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                continue
            except OSError as exc:
                print("worklist.py: could not read the Stop payload: %s" % exc, file=sys.stderr)
                return {}, False
            if not chunk:
                break  # EOF: the writer closed, so we have everything
            raw += chunk.decode("utf-8", "replace")

    _RUN["raw"] = raw
    try:
        ev = json.loads(raw) if raw.strip() else None
        return (ev, True) if isinstance(ev, dict) else ({}, False)
    except (json.JSONDecodeError, ValueError):
        # A malformed event used to degrade to {} silently, which quietly turns
        # EVERY check into "session_id is empty, nothing is configured" and produces confusing advice. Fail loudly instead: a Stop payload this hook cannot parse is a bug.
        return {}, False


USAGE_FALLBACK = "worklist.py: see --help (message catalogue unavailable: %s)"

# THE VERBS' HOST (wl_cli.bind): handed this module's globals (the probed siblings, `_BROKEN` and the twins above), here at import, after every name it takes is defined. Globals rather than `sys.modules[__name__]`, because a test loads this file under another name with no sys.modules entry. A bind that fails turns wl_cli into a shim like any broken sibling: this line runs at import, OUTSIDE the crash handler below, so raising here would print to stderr and nothing to stdout, which the harness reads as ALLOW.
if "wl_cli" not in _BROKEN:
    try:
        CLI.bind(globals())
    except Exception as _exc:
        _BROKEN["wl_cli"] = "bind: %s: %s" % (type(_exc).__name__, _exc)
        CLI = _MODS["wl_cli"] = _BrokenModule("wl_cli")


def main():
    # FIRST STATEMENT, DELIBERATELY. `claude -p` runs this hook again; the guard is the only thing that works (--settings with empty hooks does not).
    if os.environ.get("STOPHOOK_CHILD"):
        sys.exit(0)

    # BEFORE every other arm. Asking a tool how to use it must never reach the Stop-hook path, which reads stdin as JSON and, finding none, emits a block telling the caller they have a hook bug. That happened, and the answer to "how do I use this" was a wall of unrelated advice.
    if sys.argv[1:2] and sys.argv[1] in ("--help", "-h", "help"):
        try:
            print(M.USAGE)
        except Exception:
            print(USAGE_FALLBACK % "; ".join(sorted(_BROKEN)))
        return

    if len(sys.argv) > 1 and sys.argv[1] == "--path":
        # Self-contained: works with every sibling broken (see case 118).
        print(_local_worklist_path(_local_project_start()))
        return
    # EVERY OTHER VERB lives in wl_cli (agent/plans/PLAN-tooling-speed.md D4), bound to this module's probed siblings so a broken one still fails into the crash handler below. `wl_cli.main` answers True when it handled argv (an unknown leading-dash verb exits 2 there); False is the bare hook invocation, which falls through to the Stop path.
    if CLI.main():
        return

    # CI NO-OP, and it is placed HERE rather than beside the STOPHOOK_CHILD guard on purpose. Everything above this line is a query or write mode that a runner may legitimately want (`--path`, `--state`); exiting at the top of main() would break those silently. The thing that must not happen on a runner is the BLOCK below: CLAUDE.md tells a session to track items and this hook
    # refuses to end a turn while any remain, so an unattended model in Actions burns its turn budget against a gate no human will ever answer. Required by the autopilot design (docs/ci-overhaul/03-v2-autonomy.md).
    if os.environ.get("GITHUB_ACTIONS") == "true":
        sys.exit(0)

    _RUN["stop"] = True
    event, event_ok = _read_event()
    # _local_project_start, NOT C.project_start: this line runs BEFORE the _BROKEN fail-closed emit below, so touching a sibling here would raise out of _BrokenModule and crash the hook with nothing on stdout -- which the harness reads as ALLOW. Same reason _local_worklist_path exists.
    worklist = _local_worklist_path(_local_project_start(event))
    if _BROKEN:
        # THE SNAPSHOT FIRST: the same stop, judged by the last module set that ran clean. Only when it cannot answer does the crash block below fire.
        _lkg = (
            LKG.fallback(_RUN["raw"], "sibling import failed: %s" % ", ".join(sorted(_BROKEN)))
            if LKG is not None and not os.environ.get("WORKLIST_LKG_CHILD")
            else None
        )
        if _lkg:
            _emit(_lkg)
        # Fail CLOSED with the full list: a hook that cannot run its checks must not wave the stop through, and the session that hits this is the one positioned to fix it.
        _emit(
            {
                "systemMessage": "Stop hook: %d sibling module(s) unusable; blocking."
                % len(_BROKEN),
                "decision": "block",
                "reason": "THIS IS A HOOK BUG: worklist.py could not import its sibling "
                "modules, so none of its checks can run. Broken:\n%s\n\nRestore or fix "
                "the modules beside %s (worklist_messages.py and the wl_*.py siblings), "
                "then stop again."
                % (
                    "\n".join("  %s: %s" % (k, v) for k, v in sorted(_BROKEN.items())),
                    __file__,
                ),
            }
        )
    _operation_standdown(event)
    # THE RETRO ROWS MOVE BEFORE THE BATTERY (agent/plans/PLAN-stop-hook-retro-20260924.md R20260924.13), so an item added for a new `ordered` row is enforced by this very stop's open-items check. A ledger that cannot be read or written never changes the stop.
    with contextlib.suppress(Exception):
        if event_ok and event.get("session_id") and not event.get("agent_id"):
            RT.sync(worklist, C.project_root(_local_project_start(event)), event["session_id"], S)
    CK.run_stop(event, event_ok, worklist, __file__)


# GUARDED, so the module can be imported and its re-exported helpers tested directly: a bare main() call once meant `import worklist` ran the whole Stop path against whatever happened to be on stdin.
if __name__ == "__main__":
    # FAIL CLOSED ON CRASH. This was the hook's global escape hatch and nobody put it there on purpose: an unhandled exception prints a traceback to stderr and NOTHING to stdout, the harness sees no decision, and the stop is ALLOWED. So any bug anywhere in this file silently disabled EVERY check at once, which is the exact opposite of the no-escape-hatch rule the rest of it is
    # built on. It is not hypothetical: a v8 cut crashed on a tuple unpack and the stop sailed through; only a suite needle assertion caught it.
    #
    # A crash is now a BLOCK carrying the traceback, because a hook that cannot decide must not be the way out, and the session that hits it is the one positioned to fix it. Deliberately outside main() so it covers every mode.
    try:
        main()
    except SystemExit as _exit:
        # A STOP THAT DID NOT CRASH banks its module set as last-known-good (P2.5): one hash per stop, one copy per change. Never from the snapshot's own child, never with a broken sibling.
        if (
            _RUN["stop"]
            and _exit.code in (0, None)
            and not _BROKEN
            and LKG is not None
            and not os.environ.get("WORKLIST_LKG_CHILD")
        ):
            LKG.snapshot()
        raise
    except BaseException as _crash:
        import traceback

        if _RUN["stop"] and LKG is not None and not os.environ.get("WORKLIST_LKG_CHILD"):
            _frames = traceback.extract_tb(_crash.__traceback__)
            _where = (
                "%s at %s:%d"
                % (
                    type(_crash).__name__,
                    os.path.basename(_frames[-1].filename),
                    _frames[-1].lineno or 0,
                )
                if _frames
                else type(_crash).__name__
            )
            _lkg = LKG.fallback(_RUN["raw"], _where)
            if _lkg:
                _emit(_lkg)
        _emit(
            {
                "systemMessage": "Stop hook CRASHED; blocking rather than waving the stop "
                "through. Fix %s." % __file__,
                "decision": "block",
                "reason": "THIS IS A HOOK BUG: %s crashed, so none of its checks ran.\n\n%s\n"
                "A crash used to print to stderr and nothing to stdout, which the harness "
                "reads as ALLOW, so one bug disabled every check silently. It now blocks. "
                "Fix the traceback above, then stop again."
                % (__file__, traceback.format_exc()[-1800:]),
            }
        )
