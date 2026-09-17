"""`.claude/hooks/stop/wl_proc.py` is the Stop hook's one door to the bounded runner.

WHY THE HOOKS NEEDED ONE AT ALL. Eight call sites across four `wl_*` modules launch a command that FORKS -- `npm run <gate>`, `npx tsx`, and six `claude -p` invocations --
and every one used `subprocess.run(capture_output=True, timeout=N)`. That combination
bounds nothing when the child has children: on timeout `run` kills the direct child and then blocks in `communicate()` on pipe write ends a GRANDCHILD still holds.

AND IT MATTERS MORE IN A HOOK THAN IN A GATE. These run inside the Stop hook, so a block there is not a slow gate -- it is a worktree in which no session can stop, including sessions with nothing to do with the command that hung.

WHAT THIS FILE PROVES, and it is the property rather than the plumbing: a child that spawns a grandchild holding the capture pipes is killed WITH its grandchild, in bounded time, and what the child managed to say still comes back. The last part is not a detail: partial output is usually the only evidence of why something hung, and the naive fix (kill the child, give up on the
pipes) throws it away.

NOT A GATE-TEST PORT. There is no bash twin for `wl_proc.py`; it is new. This is a plain
unit test in the plain test tree, which is also why it can be added without putting `test_twin_parity.py` into disagreement.
"""

import importlib.util
import os
import sys
import time

from rediacc_ci import paths

_HOOK_DIR = paths.from_root(".claude", "hooks", "stop")

# A child that backgrounds a grandchild and then exits on its own. The grandchild inherits stdout, so the pipe stays open long after the child is gone -- which is the whole hazard. The child speaks first so there is partial output to preserve.
_FORKING_CHILD = "echo i-said-something; sleep 120 & exec sleep 120"


def _load():
    """Import `wl_proc.py` by path; it is not on `sys.path` as a package."""
    root = os.fspath(_HOOK_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    spec = importlib.util.spec_from_file_location("wl_proc_under_test", _HOOK_DIR / "wl_proc.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_hook_can_reach_the_shared_runner():
    """The coupling itself, asserted. `wl_proc` exists to be the ONE place `.ci` is put
    on `sys.path` from under `.claude/hooks/`, so its failure mode should be this test
    going red rather than four modules each raising a bare ImportError at hook time."""
    mod = _load()
    assert callable(mod.run)
    assert mod.TIMEOUT_RC == 124
    assert mod.SPAWN_FAILED_RC == 127


def test_a_child_holding_the_pipe_through_a_grandchild_is_bounded():
    """THE REGRESSION. Without the process-group kill this call does not return."""
    mod = _load()
    started = time.monotonic()
    result = mod.run(["bash", "-c", _FORKING_CHILD], timeout=3)
    elapsed = time.monotonic() - started

    assert result.timed_out is True, "the child outlives the deadline, so this IS a timeout"
    assert result.returncode == mod.TIMEOUT_RC
    # Generous against a loaded machine, and still far below the 120s the grandchild would otherwise hold the pipe for. The point is bounded, not fast.
    assert elapsed < 30, "the runner took %.1fs; the grandchild kept the pipe open" % elapsed


def test_the_kill_preserves_what_the_child_already_said():
    """The half a naive kill throws away. A timeout with empty streams tells the reader
    nothing about WHY, which is exactly when they need it most."""
    mod = _load()
    result = mod.run(["bash", "-c", _FORKING_CHILD], timeout=3)
    assert "i-said-something" in result.stdout, "the partial output was lost: %r" % result.stdout


def test_a_command_that_does_not_exist_is_a_result_not_an_exception():
    """The four routed call sites dropped their `except OSError` arms, so a failed spawn
    has to arrive as a value. If this ever raised again, those sites would crash the
    Stop hook instead of reporting."""
    mod = _load()
    result = mod.run(["definitely-no-such-binary-xyz"], timeout=5)
    assert result.returncode == mod.SPAWN_FAILED_RC
    assert result.timed_out is False
    assert result.stderr, "a failed spawn must say what went wrong"


def test_an_ordinary_command_is_unaffected():
    """The quiet direction, so the three cases above are not satisfied by a runner that
    simply fails everything."""
    mod = _load()
    result = mod.run(["bash", "-c", "echo fine; echo bad >&2; exit 0"], timeout=10)
    assert result.returncode == 0
    assert result.timed_out is False
    assert result.stdout.strip() == "fine"
    # NEVER MERGED: several callers parse stdout as JSON, and a log line folded in from stderr would break the parse rather than the logging.
    assert result.stderr.strip() == "bad"
