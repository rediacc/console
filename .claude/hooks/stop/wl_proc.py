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

import os
import pathlib
import shutil
import sys
import tempfile

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
    if not _tsx_argv(argv):
        return _run(argv, **kwargs)
    env = dict(kwargs.get("env") or os.environ)
    if len(env.get("TMPDIR") or tempfile.gettempdir()) <= TSX_TMPDIR_MAX:
        return _run(argv, **kwargs)
    # tsx listens on an IPC socket at $TMPDIR/tsx-<uid>/<pid>.pipe, and Linux keeps only the first ~107 bytes of a socket path: under a deep TMPDIR (a hook suite inside a pytest leg) two tsx processes truncate to the SAME socket and the second dies `listen EADDRINUSE` (test-judge-schema control 6o, CI runs on 588e2fb4e and ac1d14ad5, a 140-byte pipe path). A short private TMPDIR for the child keeps the path well inside the limit.
    short = tempfile.mkdtemp(prefix="tsx-", dir="/tmp" if os.path.isdir("/tmp") else None)
    try:
        env["TMPDIR"] = short
        return _run(argv, **{**kwargs, "env": env})
    finally:
        shutil.rmtree(short, ignore_errors=True)


# The longest TMPDIR a tsx child inherits as is: + "/tsx-<uid>/<pid>.pipe" (about 25 bytes) stays under the ~107-byte AF_UNIX path limit.
TSX_TMPDIR_MAX = 72


def _tsx_argv(argv) -> bool:
    return any(os.path.basename(str(a)) == "tsx" for a in list(argv)[:3])


__all__ = ["SPAWN_FAILED_RC", "TIMEOUT_RC", "Result", "run"]
