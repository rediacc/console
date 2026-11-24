#!/usr/bin/env python3
"""Run one ported guard, or a whole chain, over a hook event on stdin.

    python3 .claude/rediacc_hooks/dispatch.py block_git_amend      one guard
    python3 .claude/rediacc_hooks/dispatch.py --chain pre-bash     the chain
    python3 .claude/rediacc_hooks/dispatch.py --list               what exists

WHAT IT IS FOR TODAY. The differential in `tests/` drives the port through this entry point rather than through an import, because the bash twin it is compared against is a PROCESS: it has an exit code, a stdout and a stderr, and comparing a Python return value against those three would be comparing something else. One process per case is also what `.claude/settings.json` does
today, so the measurement is of the thing that will actually run.

WHAT `--chain` IS FOR, AND IT IS LIVE. `--chain` runs every guard of one chain IN ONE PROCESS, in the ORDER those guards declare, stopping at the first refusal. That is the fork saving this workstream is measured by, and since the P7 cutover on 2026-09-06 it is what `.claude/settings.json` actually runs:

    PreToolUse/Bash   40 command entries -> 4, and 442 execs -> 25
    PreToolUse/Edit   11 command entries -> 4, and  38 execs -> 12
    PreToolUse/Ask     3 command entries -> 3, and  13 execs -> 11

Positions were preserved rather than renumbered: the jq and python3 toolchain checks still lead every chain as their own commands. One pre-bash guard stayed bash and sat AFTER the dispatcher entry until W7 P6 ported it; `guards/block_pathspecless_git_commit.py` declares the position it always ran at and now runs there inside the dispatcher, so nothing ahead of or behind it
moved. `ORDER` in each guard module is that position, and `tests/test_dispatch.py` derives it from settings.json rather than trusting the number.

WHY `sys.path` IS MANIPULATED HERE AND NOWHERE ELSE. `.claude/settings.json` invokes hooks as plain scripts, so there is no package context and no `pythonpath` from `pyproject.toml` (pytest supplies that, the harness does not). One hop, in the one file that is an entry point, is the alternative to every guard module carrying its own -- which is the arrangement `.claude/hooks/stop`
has and the arrangement `rediacc_hooks/__init__.py` says this package exists to end.

THE FIRE AND COST LEDGER (agent/plans/PLAN-tooling-code-reduction.md CR7). Before it, a refusal returned without the refusing guard's name and nothing timed a guard, so "which guard never fires" and "which guard is slow" were questions only a transcript dig could answer. `run_chain` now times every guard and, when handed a ledger path, appends ONE line per chain run:

    {"chain", "refused_by", "rc", "ms", "slow": [[stem, ms], ...], "crashed": [stem, ...], "session", "ts"}

`refused_by` is the refusing guard's stem or null; `slow` lists the guards over SLOW_MS. Only `main` hands a path (LEDGER_REL under the checkout holding this file), so the differential and every in-process test record nothing. The append is one O_APPEND `os.write` of one line, atomic below PIPE_BUF without a lock, and a failed append is named on stderr without changing the chain's answer: a cache directory that cannot be written must never refuse a tool call.
"""

import datetime
import json
import os
import pathlib
import sys
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from rediacc_hooks import _gitmemo, guards, hookio


def run_one(stem, payload, cwd=None, env=None):
    """One guard, as (rc, stdout, stderr). Pure enough for the differential."""
    module = guards.load(stem)
    event = hookio.Event(payload, cwd=cwd, env=env)
    rc = module.run(event)
    return event.result(rc)


# A chain that loads NO guard is the failure this whole cutover risks, so it is refused in code rather than trusted to a reader. Before P7 a broken glob in `guards.stems()` cost nothing: settings.json named 38 bash files and they ran whatever this package thought. Now settings.json names ONE command per chain, so an empty chain is 37 guards silently not running while every Bash
# call still looks clean -- which is exactly what chain-head.sh's header calls "strictly worse than having no hooks at all, because no-hooks is at least visible".
EMPTY_CHAIN = (
    "BLOCKED: the %s guard chain loaded ZERO guards.\n"
    "\n"
    "One command in .claude/settings.json now runs the whole chain, so this is not a\n"
    "cosmetic error: every guard that chain carries (force push, blanket git add,\n"
    "destructive restore, worktree add, admin merge, amend, and the rest) is not\n"
    "protecting this session at all, and nothing else would say so.\n"
    "\n"
    "Look at .claude/rediacc_hooks/guards/: `stems()` matches block_*.py, warn_*.py\n"
    "and require_*.py, and `by_chain` keeps only the modules declaring CHAIN = %r.\n"
    "Refusing every call is the fail-closed answer, the same one the chain head gives\n"
    "for a missing toolchain.\n"
)


# Where `main` appends, relative to the checkout holding this file; `.ci/cache/` is gitignored local state. PLAN-tooling-code-reduction.md CR8 reads it and commits a snapshot as `.ci/config/hook-ledger.json`.
LEDGER_REL = (".ci", "cache", "hook-ledger", "chains.jsonl")
# A guard slower than this, in milliseconds, is listed under `slow` (D6 of the plan above).
SLOW_MS = 20


def ledger_path():
    """The ledger `main` appends to. `repo_root` looks for the tree holding `.claude` and `.ci` and forks nothing, which matters on a path every tool call takes."""
    return hookio.repo_root().joinpath(*LEDGER_REL)


def _stem(module):
    return module.__name__.rsplit(".", 1)[-1]


def _session(payload):
    try:
        doc = json.loads(payload)
    except (ValueError, TypeError):
        return None
    got = doc.get("session_id") if isinstance(doc, dict) else None
    return got if isinstance(got, str) and got else None


def append_ledger(path, record):
    """ONE `os.write` of ONE line on an O_APPEND handle, so concurrent sessions interleave whole lines. Raises OSError; the caller decides what a failure means."""
    line = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    path = pathlib.Path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(str(path), flags, 0o644)
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), flags, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def _record(chain, payload, rc, refused_by, timings, crashed, started, ledger, err):
    """Build the chain's ledger line and append it; a failed append becomes one stderr line, never a different rc."""
    if ledger is None:
        return
    record = {
        "chain": chain,
        "refused_by": refused_by,
        "rc": rc,
        "ms": round((time.perf_counter() - started) * 1000, 2),
        "slow": [[stem, ms] for stem, ms in timings if ms > SLOW_MS],
        "crashed": crashed,
        "session": _session(payload),
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        append_ledger(ledger, record)
    except OSError as exc:
        err.append(
            "hook ledger: append to %s failed (%s); the chain's answer is unchanged\n"
            % (ledger, exc)
        )


def run_chain(chain, payload, cwd=None, env=None, ledger=None):
    """A chain in one process, stopping at the first refusal.

    STOPPING IS THE HARNESS'S BEHAVIOUR, NOT A SHORTCUT. Claude Code runs the commands of a block in order and a non-zero exit refuses the tool call; the guards behind it never get to speak, which is why the chain head's whole contract is about being FIRST. Reproducing that here means a chain run and 38 separate runs deny the same events for the same reasons.

    A CRASHING GUARD DOES NOT TAKE THE CHAIN WITH IT, and that is the one place this deliberately does NOT let an exception propagate. Before P7 a guard that died mid-run exited non-zero, the harness showed its stderr and did not block, and the 20-odd guards registered behind it still ran as their own commands. In one process an uncaught exception would end the interpreter, so
    those 20 would silently never run -- a bug in one guard quietly disarming the rest, which is a strictly larger blast radius than the arrangement it replaced. So a crash is caught, named loudly on stderr, and counted; the chain continues, and the process exits 1 rather than 0 so the failure is visible.

    Returns (rc, stdout, stderr). rc is 2 if any guard REFUSED (a refusal always wins, since that is a decision and a crash is not), 1 if any guard crashed and none refused, 0 otherwise.

    `ledger`, when given, receives one line for this run (see the module docstring); None records nothing.

    The guards run inside `_gitmemo.chain_memo()`, so a read-only git question (`rev-parse`, a reading `symbolic-ref`) is asked once per chain run however many guards ask it (68 forks to 8 on an `echo hi` payload, PR-TASK 79b7e92e).
    """
    with _gitmemo.chain_memo():
        return _run_chain(chain, payload, cwd, env, ledger)


def _run_chain(chain, payload, cwd, env, ledger):
    started = time.perf_counter()
    modules = guards.by_chain(chain)
    if not modules:
        err = [EMPTY_CHAIN % (chain, chain)]
        _record(chain, payload, hookio.DENY, None, [], [], started, ledger, err)
        return hookio.DENY, "", "".join(err)
    out = []
    err = []
    crashed = []
    timings = []
    for module in modules:
        event = hookio.Event(payload, cwd=cwd, env=env)
        t0 = time.perf_counter()
        try:
            rc = module.run(event)
        except Exception:
            timings.append((_stem(module), round((time.perf_counter() - t0) * 1000, 2)))
            crashed.append(_stem(module))
            err.append(
                "HOOK GUARD CRASHED: %s (chain %s) raised, so it decided nothing.\n"
                "The rest of the chain still ran. Fix the module; do not delete the\n"
                "guard to make this quiet.\n%s" % (module.__name__, chain, traceback.format_exc())
            )
            continue
        timings.append((_stem(module), round((time.perf_counter() - t0) * 1000, 2)))
        _, one_out, one_err = event.result(rc)
        out.append(one_out)
        err.append(one_err)
        if rc != 0:
            _record(chain, payload, rc, _stem(module), timings, crashed, started, ledger, err)
            return rc, "".join(out), "".join(err)
    rc = 1 if crashed else 0
    _record(chain, payload, rc, None, timings, crashed, started, ledger, err)
    return rc, "".join(out), "".join(err)


def main(argv):
    # Asked-for help goes to stdout like `--list`, so `--help | less` reads it; a bare call is a usage error and says so on stderr.
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 64
    # An unknown stem (or a misspelled flag) used to reach importlib and end in a traceback; name the real stems instead.
    if argv[0] == "--chain" and len(argv) < 2:
        print("dispatch.py: --chain needs a chain name", file=sys.stderr)
        return 64
    if not argv[0].startswith("--") and argv[0] not in guards.stems():
        print(
            "dispatch.py: no guard named %r; `dispatch.py --list` prints every guard" % argv[0],
            file=sys.stderr,
        )
        return 64
    if argv[0].startswith("--") and argv[0] not in ("--list", "--chain"):
        print("dispatch.py: unknown option %r" % argv[0], file=sys.stderr)
        return 64
    if argv[0] == "--list":
        for stem in guards.stems():
            module = guards.load(stem)
            evidence = "own-suite" if guards.has_own_suite(module) else "golden"
            print("%-10s %-40s %s" % (module.CHAIN, stem, evidence))
        return 0
    payload = sys.stdin.read()
    if argv[0] == "--chain":
        rc, out, err = run_chain(argv[1], payload, ledger=ledger_path())
    else:
        rc, out, err = run_one(argv[0], payload)
    sys.stdout.write(out)
    sys.stderr.write(err)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
