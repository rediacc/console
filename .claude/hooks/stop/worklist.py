#!/usr/bin/env python3
"""Stop hook: refuse to end a turn while tracked work remains unhandled.

WHY: the failure this prevents is stopping to REPORT a discovery instead of
acting on it. The full design history (v1-v9: the [ ]/[x]/[?]/[>] state
machine, the harness task queue, cross-session requests, the regression
gate, the poll fast path) lives in the sibling modules beside each piece of
logic; this file is only the ENTRY POINT: the recursion guard, the CLI
dispatch, and the fail-closed wrapper.

v10 (2026-07-30, operator request): the item store moved from the markdown
file to an append-only JSONL event log (wl_store: the markdown stays as a
synced INBOX, so nothing written there is ever silently ignored); every item
carries start and last-update stamps; in-flight claims are verified against
the OS and walked up a 45/90/120-minute ladder (wl_liveness); deferrals
execute their DEFAULT after an autonomy window instead of nagging forever
(wl_checks); the handover budget grew to 250-1500 chars with world-keyed
staleness; and the judge caches identical verdicts (wl_judge). The one
3600-line file became nine modules; worklist_messages.py remains the
catalogue of user-facing prose.

MODULE MAP:
    wl_core       shared primitives (paths, git, regexes, tasks, transcript)
    wl_store      event log, markdown sync, sidecars, session state doc
    wl_requests   cross-session requests (.requests) and their CLI
    wl_liveness   worker verification against /proc|ps, the 45/90/120 ladder
    wl_ci         publish divergence, PR freshness, submodule pointers, CI
    wl_reggate    v7/v8 regression-gate machinery
    wl_judge      the stop-legitimacy judge and its verdict cache
    wl_checks     the static battery and the Stop orchestration (run_stop)
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

SIBLING IMPORTS ARE PROBED, NOT ASSUMED. A top-level ImportError would
crash before the fail-closed wrapper exists, print nothing to stdout, and
read as ALLOW. So every sibling is imported inside a probe; a broken one is
replaced by a shim whose every attribute access raises, naming EVERY broken
module. Query modes that need no sibling (--path, --help) keep working, and
the Stop path blocks loudly instead of failing open.

What still allows a stop:
  1. An empty world: no open items, no pending tasks, no obligations.
  2. Removing the hook from .claude/settings.json.
  3. A VERIFIED no-op inbox-poll stop (wl_checks.poll_fast_path), silent by
     design and bounded by POLL_FULL_MAX_MIN.
"""

import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_BROKEN = {}  # module name -> error string
_MODS = {}


class _BrokenModule:
    """Every attribute access raises, naming every unusable sibling, so the
    first USE fails into the crash handler with the full picture. The
    message lists all broken modules because the first attribute touched is
    rarely the interesting one."""

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
    "wl_core", "wl_store", "wl_requests", "wl_liveness", "wl_ci",
    "wl_reggate", "wl_judge", "wl_checks", "worklist_messages",
):
    try:
        _MODS[_name] = __import__(_name)
    except Exception as _exc:  # noqa: BLE001 -- a broken sibling must not crash the probe
        _BROKEN[_name] = "%s: %s" % (type(_exc).__name__, _exc)
        _MODS[_name] = _BrokenModule(_name)

C = _MODS["wl_core"]
S = _MODS["wl_store"]
R = _MODS["wl_requests"]
CK = _MODS["wl_checks"]
M = _MODS["worklist_messages"]

# Re-exported for direct importers (the suite drives these two as library
# functions; keeping them on this module is part of the compatibility
# surface). Absent when their module is broken, which is correct: a caller
# gets an AttributeError naming this module instead of a silent stub.
if "wl_checks" not in _BROKEN:
    cited_excerpts = _MODS["wl_checks"].cited_excerpts
    citation_state = _MODS["wl_checks"].citation_state
if "wl_ci" not in _BROKEN:
    submodule_pointer_moves = _MODS["wl_ci"].submodule_pointer_moves


def _local_worklist_path(start):
    """Self-contained twin of wl_core.worklist_for, used ONLY by --path, the
    self-contained append modes and the broken-sibling block, so the queries
    every script depends on work even when every sibling is missing. Keep in
    lockstep with wl_core.worklist_for."""
    p = pathlib.Path(start).resolve()
    root = p
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists():
            root = candidate
            break
    d = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist"
    d.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(root)).strip("_")
    return d / (slug + ".md")


def _emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def _read_event():
    try:
        ev = json.load(sys.stdin)
        return (ev, True) if isinstance(ev, dict) else ({}, False)
    except (json.JSONDecodeError, ValueError):
        # A malformed event used to degrade to {} silently, which quietly turns
        # EVERY check into "session_id is empty, nothing is configured" and
        # produces confusing advice. Fail loudly instead: a Stop payload this
        # hook cannot parse is a bug.
        return {}, False


USAGE_FALLBACK = "worklist.py: see --help (message catalogue unavailable: %s)"


def _item_cli(argv, worklist):
    """--add / --tick / --defer / --lease / --update / --list: the v10 item
    verbs. Exits non-zero on misuse, so a rejected write cannot be mistaken
    for a delivered one."""

    def die(msg):
        print(msg, file=sys.stderr)
        sys.exit(1)

    mode = argv[0]
    if mode == "--list":
        fold = S.load(worklist, sync=True)
        if argv[1:2] == ["--open"]:
            # The same actionable slice the Stop hook emits (v11), so a human
            # and the hook are never looking at different views. An optional
            # prefix scopes ownership and binds the printed verbs.
            me = argv[2] if len(argv) > 2 else ""
            print(CK.guided_slice(fold, me or None, None, me or None))
            return
        for rec in fold.items:
            age = C.stamp_age_min(rec.get("first", ""))
            upd = C.stamp_age_min(rec.get("upd", ""))
            print(
                "%s   [#%s %s age:%s upd:%s]"
                % (
                    rec["line"],
                    rec["id"],
                    rec["origin"],
                    "?" if age is None else "%dm" % age,
                    "?" if upd is None else "%dm" % upd,
                )
            )
        return
    if len(argv) < 3:
        die(M.CLI_ITEM_USAGE)
    me = argv[1]
    if not C.PREFIX_RE.match(me):
        die("bad prefix %r: pass YOUR session-id prefix first" % me)
    if mode == "--add":
        text = " ".join(argv[2:]).replace("\n", " ").strip()
        if not text:
            die("an empty item tracks nothing")
        rid = S.add_item(worklist, me, text)
        print("added #%s: %s" % (rid, text))
        return
    item_id = argv[2].lstrip("#")
    fold = S.load(worklist, sync=True)
    rec = fold.by_id.get(item_id)
    if rec is None:
        die("no item #%s (worklist.py --list shows ids)" % item_id)
    if rec["owner"] is not None and not C.same_session(rec["owner"], me):
        die("#%s is owned by %s; never tick or edit another session's tracking"
            % (item_id, rec["owner"]))
    rest = " ".join(argv[3:]).replace("\n", " ").strip()
    root = C.project_root(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if mode == "--tick":
        if not rest or not CK.completion_evidence(root, rest):
            die(M.CLI_TICK_NO_EVIDENCE % item_id)
        S.set_state(worklist, me, item_id, "x", rest)
        print("ticked #%s (%s)" % (item_id, rest[:80]))
        return
    if mode == "--defer":
        if not C.DEFAULT_TOKEN.search(rest):
            die("a [?] without a DEFAULT: is a note, not a decision; append "
                "'DEFAULT: <what you will do if unanswered>'")
        S.set_state(worklist, me, item_id, "?", rest)
        print("deferred #%s; it will be reported every stop and its DEFAULT "
              "executes after %d min" % (item_id, S.DEFER_WINDOW_MIN))
        return
    if mode == "--update":
        if not rest:
            die("an empty update updates nothing: one line of what moved")
        S.update_item(worklist, me, item_id, rest)
        print("updated #%s" % item_id)
        return
    if mode == "--lease":
        if len(argv) < 4:
            die(M.CLI_ITEM_USAGE)
        until_arg = argv[3]
        if until_arg.startswith("+") and until_arg[1:].isdigit():
            import datetime
            minutes = min(int(until_arg[1:]), C.MAX_LEASE_MIN)
            until = (C.utcnow() + datetime.timedelta(minutes=minutes)).strftime(
                "%Y-%m-%dT%H:%MZ"
            )
        else:
            until = until_arg.replace("until:", "")
        wm = next((a for a in argv[4:] if a.startswith("worker:")), "")
        if not wm:
            die("a [>] lease must name its worker (worker:<background-task-id>); "
                "an in-flight claim with no worker to trace is the gap this "
                "program exists to catch")
        note = " ".join(a for a in argv[4:] if not a.startswith("worker:")).strip()
        if C.lease_state("until:%s" % until) != "fresh":
            die("until:%s is not a valid fresh lease (ISO8601Z, at most %d min ahead)"
                % (until, C.MAX_LEASE_MIN))
        S.lease_item(worklist, me, item_id, until, wm.split(":", 1)[1], note)
        print("leased #%s until %s on %s" % (item_id, until, wm))
        return
    die("unknown item mode %s" % mode)


def main():
    # FIRST STATEMENT, DELIBERATELY. `claude -p` runs this hook again; the guard
    # is the only thing that works (--settings with empty hooks does not).
    if os.environ.get("STOPHOOK_CHILD"):
        sys.exit(0)

    # BEFORE every other arm. Asking a tool how to use it must never reach the
    # Stop-hook path, which reads stdin as JSON and, finding none, emits a block
    # telling the caller they have a hook bug. That happened, and the answer to
    # "how do I use this" was a wall of unrelated advice.
    if sys.argv[1:2] and sys.argv[1] in ("--help", "-h", "help"):
        try:
            print(M.USAGE)
        except Exception:  # noqa: BLE001 -- help must not crash on a broken catalogue
            print(USAGE_FALLBACK % "; ".join(sorted(_BROKEN)))
        return

    if len(sys.argv) > 1 and sys.argv[1] == "--path":
        # Self-contained: works with every sibling broken (see case 118).
        print(_local_worklist_path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--compact":
        S.compact(C.worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--handover":
        # `... --handover <prefix>` with the document on stdin. Whole-file
        # rewrite is correct here: unlike the store this file is per-session,
        # so there is no other writer to race. v10: the current world
        # signature is recorded beside it, so staleness can be world-keyed.
        wl = _local_worklist_path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        prefix = sys.argv[2]
        body = sys.stdin.read()
        wl.with_suffix(".handover-%s.md" % prefix[:8]).write_text(body, encoding="utf-8")
        try:
            root = C.project_root(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
            S.load(wl, sync=True)  # sync first, so the signature covers the synced world
            doc = S.load_state(wl, prefix)
            doc["handover_sig"] = S.world_sig(root, wl, prefix)
            S.save_state(wl, prefix, doc)
        except Exception:  # noqa: BLE001 -- the sig is an optimisation, never a gate on writing
            pass
        print("handover written for %s (%d chars)" % (prefix, len(body)))
        return
    if sys.argv[1:2] == ["--session-start"]:
        ev, _ok = _read_event()
        CK.handle_session_start(ev)
        return
    if sys.argv[1:2] == ["--post-compact"]:
        ev, _ok = _read_event()
        CK.handle_post_compact(ev)
        return
    if len(sys.argv) > 3 and sys.argv[1] == "--loop":
        # `worklist.py --loop <prefix> <next-ISO8601Z> <count> <label...>`
        # Self-contained append (works without siblings, like --brief).
        wl = _local_worklist_path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        with open(wl.with_suffix(".loop"), "a", encoding="utf-8") as fh:
            fh.write(
                "%s %s %s %s\n"
                % (
                    sys.argv[2],
                    sys.argv[3],
                    sys.argv[4] if len(sys.argv) > 4 else "1",
                    " ".join(sys.argv[5:]).replace("\n", " ")[:120],
                )
            )
        print("loop declared for %s, next fire %s" % (sys.argv[2], sys.argv[3]))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--brief":
        # `worklist.py --brief <session-prefix> <text...>` -- append, never
        # rewrite, for the same lost-update reason the store appends.
        # Self-contained so a broken sibling cannot take the brief channel down.
        import datetime
        wl = _local_worklist_path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        prefix = sys.argv[2]
        text = " ".join(sys.argv[3:]).replace("\n", " ").strip()[:200]
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(wl.with_suffix(".sessions"), "a", encoding="utf-8") as fh:
            fh.write("%s %s %s\n" % (prefix, stamp, text))
        print("brief recorded for %s (%d chars)" % (prefix, len(text)))
        return
    if sys.argv[1:2] and sys.argv[1] in ("--ask", "--answer", "--decline", "--ack", "--requests"):
        R.request_cli(
            sys.argv[1:], C.worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        )
        return
    if sys.argv[1:2] == ["--poll"]:
        R.poll_cli(
            C.worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()),
            sys.argv[2] if len(sys.argv) > 2 else "",
            __file__,
        )
        return
    if sys.argv[1:2] and sys.argv[1] in ("--add", "--tick", "--defer", "--lease", "--update", "--list"):
        _item_cli(
            sys.argv[1:], C.worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        )
        return

    # CI NO-OP, and it is placed HERE rather than beside the STOPHOOK_CHILD guard
    # on purpose. Everything above this line is a query or write mode that a
    # runner may legitimately want (`--path`, `--handover`); exiting at the top of
    # main() would break those silently. The thing that must not happen on a
    # runner is the BLOCK below: CLAUDE.md tells a session to track items and
    # this hook refuses to end a turn while any remain, so an unattended model
    # in Actions burns its turn budget against a gate no human will ever answer.
    # Required by the autopilot design (docs/ci-overhaul/03-v2-autonomy.md).
    if os.environ.get("GITHUB_ACTIONS") == "true":
        sys.exit(0)

    event, event_ok = _read_event()
    worklist = _local_worklist_path(
        os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    )
    if _BROKEN:
        # Fail CLOSED with the full list: a hook that cannot run its checks
        # must not wave the stop through, and the session that hits this is
        # the one positioned to fix it.
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
    CK.run_stop(event, event_ok, worklist, __file__)


# GUARDED, so the module can be imported and its re-exported helpers tested
# directly: a bare main() call once meant `import worklist` ran the whole Stop
# path against whatever happened to be on stdin.
if __name__ == "__main__":
    # FAIL CLOSED ON CRASH. This was the hook's global escape hatch and nobody
    # put it there on purpose: an unhandled exception prints a traceback to
    # stderr and NOTHING to stdout, the harness sees no decision, and the stop is
    # ALLOWED. So any bug anywhere in this file silently disabled EVERY check at
    # once, which is the exact opposite of the no-escape-hatch rule the rest of
    # it is built on. It is not hypothetical: a v8 cut crashed on a tuple unpack
    # and the stop sailed through; only a suite needle assertion caught it.
    #
    # A crash is now a BLOCK carrying the traceback, because a hook that cannot
    # decide must not be the way out, and the session that hits it is the one
    # positioned to fix it. Deliberately outside main() so it covers every mode.
    try:
        main()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - a bare crash must not become an allow
        import traceback

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
