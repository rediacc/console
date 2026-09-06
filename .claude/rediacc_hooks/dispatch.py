#!/usr/bin/env python3
"""Run one ported guard, or a whole chain, over a hook event on stdin.

    python3 .claude/rediacc_hooks/dispatch.py block_git_amend      one guard
    python3 .claude/rediacc_hooks/dispatch.py --chain pre-bash     the chain
    python3 .claude/rediacc_hooks/dispatch.py --list               what exists

WHAT IT IS FOR TODAY. The differential in `tests/` drives the port through this
entry point rather than through an import, because the bash twin it is compared
against is a PROCESS: it has an exit code, a stdout and a stderr, and comparing
a Python return value against those three would be comparing something else.
One process per case is also what `.claude/settings.json` does today, so the
measurement is of the thing that will actually run.

WHAT IT IS FOR AT P6, stated because the shape only makes sense with it in
view. `--chain` runs every guard of one chain IN ONE PROCESS, in the order
settings.json declares them, stopping at the first refusal. That is the whole
fork saving this workstream is measured by: 38 command entries plus roughly 50
in-guard jq forks collapse to one interpreter that parses the payload once.
It is implemented and tested here and deliberately NOT registered: the cutover
is P6 and `.claude/settings.json` is a single-writer file.

WHY `sys.path` IS MANIPULATED HERE AND NOWHERE ELSE. `.claude/settings.json`
invokes hooks as plain scripts, so there is no package context and no
`pythonpath` from `pyproject.toml` (pytest supplies that, the harness does
not). One hop, in the one file that is an entry point, is the alternative to
every guard module carrying its own -- which is the arrangement
`.claude/hooks/stop` has and the arrangement `rediacc_hooks/__init__.py` says
this package exists to end.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from rediacc_hooks import guards, hookio


def run_one(stem, payload, cwd=None, env=None):
    """One guard, as (rc, stdout, stderr). Pure enough for the differential."""
    module = guards.load(stem)
    event = hookio.Event(payload, cwd=cwd, env=env)
    rc = module.run(event)
    return event.result(rc)


def run_chain(chain, payload, cwd=None, env=None):
    """A chain in one process, stopping at the first refusal.

    STOPPING IS THE HARNESS'S BEHAVIOUR, NOT A SHORTCUT. Claude Code runs the
    commands of a block in order and a non-zero exit refuses the tool call; the
    guards behind it never get to speak, which is why require-jq.sh's whole
    contract is about being FIRST. Reproducing that here means a chain run and
    38 separate runs deny the same events for the same reasons.
    """
    out = []
    err = []
    for module in guards.by_chain(chain):
        event = hookio.Event(payload, cwd=cwd, env=env)
        rc = module.run(event)
        _, one_out, one_err = event.result(rc)
        out.append(one_out)
        err.append(one_err)
        if rc != 0:
            return rc, "".join(out), "".join(err)
    return 0, "".join(out), "".join(err)


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
