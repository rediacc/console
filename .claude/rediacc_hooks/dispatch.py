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

Positions were preserved rather than renumbered: require-jq.sh and require-python.sh still lead every chain as their own commands, and the one pre-bash guard that is still bash (block-pathspecless-git-commit.sh) sits AFTER the dispatcher entry, so it still runs 40th. `ORDER` in each guard module is that position, and `tests/test_dispatch.py` derives it from settings.json rather
than trusting the number.

WHY `sys.path` IS MANIPULATED HERE AND NOWHERE ELSE. `.claude/settings.json` invokes hooks as plain scripts, so there is no package context and no `pythonpath` from `pyproject.toml` (pytest supplies that, the harness does not). One hop, in the one file that is an entry point, is the alternative to every guard module carrying its own -- which is the arrangement `.claude/hooks/stop`
has and the arrangement `rediacc_hooks/__init__.py` says this package exists to end.
"""

import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from rediacc_hooks import guards, hookio


def run_one(stem, payload, cwd=None, env=None):
    """One guard, as (rc, stdout, stderr). Pure enough for the differential."""
    module = guards.load(stem)
    event = hookio.Event(payload, cwd=cwd, env=env)
    rc = module.run(event)
    return event.result(rc)


# A chain that loads NO guard is the failure this whole cutover risks, so it is refused in code rather than trusted to a reader. Before P7 a broken glob in `guards.stems()` cost nothing: settings.json named 38 bash files and they ran whatever this package thought. Now settings.json names ONE command per chain, so an empty chain is 37 guards silently not running while every Bash
# call still looks clean -- which is exactly what require-jq.sh's header calls "strictly worse than having no hooks at all, because no-hooks is at least visible".
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
    "Refusing every call is the fail-closed answer, the same one require-jq.sh gives\n"
    "for a missing toolchain.\n"
)


def run_chain(chain, payload, cwd=None, env=None):
    """A chain in one process, stopping at the first refusal.

    STOPPING IS THE HARNESS'S BEHAVIOUR, NOT A SHORTCUT. Claude Code runs the commands of a block in order and a non-zero exit refuses the tool call; the guards behind it never get to speak, which is why require-jq.sh's whole contract is about being FIRST. Reproducing that here means a chain run and 38 separate runs deny the same events for the same reasons.

    A CRASHING GUARD DOES NOT TAKE THE CHAIN WITH IT, and that is the one place this deliberately does NOT let an exception propagate. Before P7 a guard that died mid-run exited non-zero, the harness showed its stderr and did not block, and the 20-odd guards registered behind it still ran as their own commands. In one process an uncaught exception would end the interpreter, so
    those 20 would silently never run -- a bug in one guard quietly disarming the rest, which is a strictly larger blast radius than the arrangement it replaced. So a crash is caught, named loudly on stderr, and counted; the chain continues, and the process exits 1 rather than 0 so the failure is visible.

    Returns (rc, stdout, stderr). rc is 2 if any guard REFUSED (a refusal always wins, since that is a decision and a crash is not), 1 if any guard crashed and none refused, 0 otherwise.
    """
    modules = guards.by_chain(chain)
    if not modules:
        return hookio.DENY, "", EMPTY_CHAIN % (chain, chain)
    out = []
    err = []
    crashed = 0
    for module in modules:
        event = hookio.Event(payload, cwd=cwd, env=env)
        try:
            rc = module.run(event)
        except Exception:  # noqa: BLE001 -- see the docstring: never fatal here
            crashed += 1
            err.append(
                "HOOK GUARD CRASHED: %s (chain %s) raised, so it decided nothing.\n"
                "The rest of the chain still ran. Fix the module; do not delete the\n"
                "guard to make this quiet.\n%s" % (module.__name__, chain, traceback.format_exc())
            )
            continue
        _, one_out, one_err = event.result(rc)
        out.append(one_out)
        err.append(one_err)
        if rc != 0:
            return rc, "".join(out), "".join(err)
    return (1 if crashed else 0), "".join(out), "".join(err)


def main(argv):
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 64
    if argv[0] == "--list":
        for stem in guards.stems():
            module = guards.load(stem)
            print("%-10s %-40s %s" % (module.CHAIN, stem, module.TWIN))
        return 0
    payload = sys.stdin.read()
    if argv[0] == "--chain":
        rc, out, err = run_chain(argv[1], payload)
    else:
        rc, out, err = run_one(argv[0], payload)
    sys.stdout.write(out)
    sys.stderr.write(err)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
