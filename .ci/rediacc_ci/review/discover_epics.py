#!/usr/bin/env python3
"""Port of `.ci/scripts/review/discover-epics.sh`.

Emits the epic ids a branch declares as a JSON array on `epics=`, for the
review workflow's job matrix. The twin's own header explains why it is a script at all rather than an inline workflow block, and the reason is exactly the reason this port must not carry its own parser: the inline version "re-implemented the snapshot parse that `review_epic_ids` in .ci/scripts/lib/common.sh already does, so there were two copies of one rule -- and two copies
drift."

SO THE PARSE IS NOT RE-IMPLEMENTED HERE EITHER. `review_epic_ids` (common.sh:603-617) already has its Python equivalent in `rediacc_ci.core.review_budget.epic_ids`, ported with the twin's own three quirks driven (the `/` -> `-` branch mapping, the grep anchored at BOTH ends, lowercase hex only). This module calls that function. Adding a fourth copy of the rule -- bash helper,
Python helper, `check_review_report_replies`'s deliberate re-implementation, and one more here -- is the failure the twin's header is about.

ONE THING IS RESOLVED HERE RATHER THAN DELEGATED, AND IT IS A REAL DIVERGENCE
BETWEEN THE TWO HELPERS. The bash `review_epic_ids` resolves its root as
`${WORKLIST_PUBLISH_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}`
(common.sh:610-611): the CHECKOUT the caller is standing in. `review_budget.epic_ids` falls back to `paths.repo_root()`, which is derived from the package file's own location and is deliberately immune to cwd (see `paths.py`'s docstring on why cwd is never a rung). Those two answers agree whenever the process is standing in the checkout the package was copied into, and disagree the
moment it is not -- a fixture repo under a tmpdir being the case that matters. So this module computes the twin's root itself and passes it down through the shared parser's own `WORKLIST_PUBLISH_ROOT` override, which keeps ONE parser and still gives the twin's root semantics byte for byte.

`jq` IS STILL REQUIRED THOUGH NOTHING HERE SHELLS OUT TO IT. `require_cmd jq` is the twin's first statement, so a machine without jq gets a refusal and exit
1 from bash; a port that quietly dropped the check would exit 0 with a correct
answer in exactly the environment the check exists for, and the two would disagree there and nowhere else. The requirement is preserved deliberately and named here so the cutover step -- which is where dropping it becomes correct, because `json.dumps` needs no binary -- can drop it on purpose rather than by accident.

THE EMPTY CASE IS THE ONE TO GET RIGHT, quoting the twin: a matrix over an empty array does not run the job AT ALL, so `[""]` (one flat pass) is emitted rather than `[]`. That is the single most load-bearing line in either file and `test_review_discover_epics.py` drives it on both sides.

JSON SHAPE: the twin's `jq -R . | jq -sc .` produces a compact array with no
spaces, which is `json.dumps(ids, separators=(",", ":"))`. Every element is
`[0-9a-f]{6,32}` by construction of the parse, so the two encoders cannot
disagree about escaping or non-ASCII -- there is nothing to escape.

ONE DEFECT FOUND BY THIS PORT AND FIXED IN THE TWIN IN LOCKSTEP (2026-09-10).
Both call sites used to write `>>"${GITHUB_OUTPUT:-/dev/stdout}"`. Opening
`/dev/stdout` fails with ENXIO ("No such device or address") when fd 1 is a UNIX SOCKET, and a socket is exactly what Node's `child_process.spawnSync` hands its child -- which is how `scripts/lib/shadow-gate.ts` runs both sides
while recording this file's own ledger. Measured before the fix, with
GITHUB_OUTPUT unset and a socketpair on fd 1:

    twin  rc=1  stdout="no epics declared for 0906-1; one flat review pass
                        will run\n"
                stderr="discover-epics.sh: line 36: /dev/stdout: No such
                        device or address\n"
    port  rc=0  stdout="no epics declared ...\nepics=[\"\"]\n"

So the twin printed the human line, LOST the `epics=` line -- the only thing
the workflow reads -- and then exited 1, reporting failure for a run that had already done its work. GITHUB_OUTPUT is always set in Actions, so the live
matrix never hit it; every local run and every Node-harness run did. The twin
now has an `emit()` helper that branches on `GITHUB_OUTPUT` rather than redirecting to a path, which is what this port always did, and `test_review_discover_epics.py` pins both sides against a real socketpair.

K=5 LEDGER: `.ci/shadow/w7p6-discover-epics.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common, review_budget

SELF = "discover-epics"


def publish_root(env: dict[str, str] | None = None) -> str:
    """common.sh:610-611's root, verbatim, including its two fallbacks.

    `git rev-parse --show-toplevel 2>/dev/null || echo .` means a cwd that is not inside any repository yields the literal `.`, so the snapshot is looked
    for at `./agent/pr/<branch>.md`. That is a relative path and it is the
    twin's behaviour, not a bug being ported around.
    """
    environ = os.environ if env is None else env
    override = environ.get("WORKLIST_PUBLISH_ROOT", "")
    if override:
        return override
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    top = proc.stdout.strip() if proc.returncode == 0 else ""
    return top or "."


def epic_ids(branch: str, env: dict[str, str] | None = None) -> list[str]:
    """The shared parser, pinned to the twin's root.

    The `if line` filter mirrors the twin's `[[ -n "$id" ]]` guard. It is unreachable today -- `grep -o` never emits an empty match -- and is kept because dropping it would make the two disagree if the parse ever did.
    """
    environ = dict(os.environ) if env is None else dict(env)
    environ[review_budget.PUBLISH_ROOT_ENV] = publish_root(environ)
    return [i for i in review_budget.epic_ids(branch, env=environ) if i]


def _emit(line: str, env: dict[str, str]) -> None:
    """`>>"${GITHUB_OUTPUT:-/dev/stdout}"`. Empty reads as unset, as in bash."""
    target = env.get("GITHUB_OUTPUT", "")
    if not target:
        sys.stdout.write(line)
        sys.stdout.flush()
        return
    # Flushed FIRST: the twin's `echo` reaches the fd before its `>>` append does, and a caller that points GITHUB_OUTPUT at /dev/stdout would otherwise see the two lines swap places behind Python's own buffer.
    sys.stdout.flush()
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(line)


def main(argv: list[str]) -> int:
    del argv
    env = dict(os.environ)
    try:
        common.require_cmd("jq", env=env)
    except common.RefusalError as exc:
        log.error(str(exc))
        return 1

    branch = env.get("PR_HEAD_REF", "")
    if not branch:
        log.error("PR_HEAD_REF is unset; refusing to guess a branch and silently report no epics")
        return 1

    ids = epic_ids(branch, env=env)

    if not ids:
        print("no epics declared for %s; one flat review pass will run" % branch)
        _emit('epics=[""]\n', env)
        return 0

    print("epics for %s: %s" % (branch, " ".join(ids)))
    _emit("epics=%s\n" % json.dumps(ids, separators=(",", ":")), env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
