"""The Stop hook's one door to `rediacc_ci.proc`, and the only place `.ci` is added to `sys.path` from under `.claude/hooks/`.

WHY THE HOOKS NEEDED ONE. Eight call sites across four `wl_*` modules launch a command that FORKS -- `npm run <gate>`, `npx tsx`, and six `claude -p` invocations -- and every
one used `subprocess.run(capture_output=True, timeout=N)`. That combination bounds
nothing when the child has children: on timeout `run` kills the direct child and then blocks in `communicate()` waiting for pipe write ends a GRANDCHILD still holds. `.ci/rediacc_ci/proc.py` fixes that by putting the child in its own session and signalling the whole group, and it is already the tree's single implementation of that fix; a second copy inside the hooks is the drift
`rediacc_ci/controls.py` argues against.

AND IT MATTERS MORE HERE THAN IN A GATE. These eight run inside the STOP HOOK. A gate that hangs fails one job; a hook that hangs means no session in this worktree can ever stop, including sessions with nothing to do with the command that hung.

THE FAILURE IS DEFERRED TO THE CALL, NOT RAISED AT IMPORT, and that is not politeness -- it is a measured requirement. `test-worklist-v5.sh` case 222j copies the hook directory somewhere WITHOUT `.ci` beside it and asserts the hook still reports exactly the one module it planted a crash in. An import-time raise made three more modules unimportable there, `worklist.py` refused with
"3 sibling module(s) unusable", and the case went red. That red is the real behaviour in miniature: a tree without `.ci` would have lost the WHOLE Stop hook, every check, over a runner that most stops never reach.

So the import always succeeds, and `run()` refuses -- loudly, naming what is missing -- only if something actually tries to launch a forking child without the runner present. Everything else the hook does keeps working.
"""

import pathlib
import sys

_CI = pathlib.Path(__file__).resolve().parents[3] / ".ci"
if _CI.is_dir() and str(_CI) not in sys.path:
    sys.path.insert(0, str(_CI))

# The two codes, given values here as well as re-exported, so a caller can branch on them even in a tree where the runner itself did not load. They are the codes the call sites were already synthesising by hand in their `except` arms.
TIMEOUT_RC = 124
SPAWN_FAILED_RC = 127

_IMPORT_ERROR = None
try:
    from rediacc_ci.proc import SPAWN_FAILED_RC, TIMEOUT_RC, Result
    from rediacc_ci.proc import run as _run
except ImportError as exc:  # pragma: no cover - a checkout without .ci
    _IMPORT_ERROR = exc
    Result = None
    _run = None


def run(argv, **kwargs):
    """`rediacc_ci.proc.run`, or a refusal that says exactly what is missing.

    A refusal rather than a silent fall back to `subprocess.run`: falling back would reinstate the unbounded call this module exists to remove, in the one situation nobody is watching, and it would do it invisibly.
    """
    if _run is None:
        raise RuntimeError(
            "the Stop hook needs .ci/rediacc_ci/proc.py to launch %r, because that "
            "command forks and a plain subprocess timeout cannot bound it. It is not "
            "importable from %s (%s). This is the ONLY dependency the hooks have on the "
            "CI package; if the tree genuinely has no .ci, that is the thing to fix "
            "rather than re-implementing a process-group kill inside .claude/hooks."
            % (argv[:1], _CI, _IMPORT_ERROR)
        )
    return _run(argv, **kwargs)


__all__ = ["SPAWN_FAILED_RC", "TIMEOUT_RC", "Result", "run"]
