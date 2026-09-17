"""`worklist.py --state` must not block on a stdin nobody writes to.

WHAT HAPPENED. On 2026-09-08 a `--state` call sat for EIGHTY-ONE MINUTES with its OS process alive and its output stream empty, and was killed by hand. Its stdin was inherited from a backgrounded tool invocation: a pipe whose write end stays open and is never written to. The verb guarded only `sys.stdin.isatty()`, which catches an interactive terminal and nothing else, and then
called a plain `sys.stdin.read()`.

WHY IT MATTERS MORE THAN A SLOW COMMAND. `--state` writes the compaction-recovery document. A session that cannot write it has no way to hand itself over, and the stop machinery reports the hung worker as VERIFIED ALIVE -- correctly, because it is -- so nothing anywhere says the command will never finish.

THE LESSON WAS ALREADY IN THE FILE. `_read_event`, twenty lines above the verb, carries a docstring saying a process that hangs is worse than one that fails, because it stalls the session instead of failing it, and it takes a deadline for exactly that reason. This is the same property for the document reader.

NOT A GATE-TEST PORT, deliberately. The two harnesses that would otherwise host this (`test_gate_stop_hook_stdin.py`, `test_gate_worklist_hooks.py`) are ports
with bash twins under twin parity, so a case added to one side only would put the
differential in disagreement. This is a unit property of a CLI reader and belongs in the plain test tree.
"""

import importlib.util
import os
import sys
import threading
import time

from rediacc_ci import paths

_SUBJECT = paths.from_root(".claude", "hooks", "stop", "worklist.py")


def _load():
    """Import worklist.py by path. It is a hyphen-free module but not on sys.path."""
    root = os.fspath(paths.from_root(".claude", "hooks", "stop"))
    if root not in sys.path:
        sys.path.insert(0, root)
    spec = importlib.util.spec_from_file_location("worklist_under_test", _SUBJECT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _StdinFromFd:
    """Swap `sys.stdin` for a real file object on `fd`, and put it back."""

    def __init__(self, fd):
        self._fd = fd
        self._saved = None
        self._fh = None

    def __enter__(self):
        self._saved = sys.stdin
        self._fh = os.fdopen(self._fd, "r", encoding="utf-8")
        sys.stdin = self._fh
        return self

    def __exit__(self, *_exc):
        sys.stdin = self._saved
        self._fh.close()
        return False


def test_a_silent_stdin_is_refused_in_bounded_time():
    """THE REGRESSION. An open pipe nobody writes to must come back, not hang."""
    mod = _load()
    r, w = os.pipe()  # w is deliberately left open: that is the whole fixture
    try:
        with _StdinFromFd(r):
            started = time.monotonic()
            body, arrived = mod._read_document(seconds=1.0)
            elapsed = time.monotonic() - started
        assert arrived is False, "a stdin that produced nothing must not report a body"
        assert body == ""
        # Generous upper bound: the assertion is "bounded", not "exactly 1.0s".
        assert elapsed < 10.0, "the read took %.1fs; the deadline did not apply" % elapsed
    finally:
        os.close(w)


def test_a_plain_read_on_that_same_pipe_really_does_hang():
    """THE CONTROL, and without it the case above proves nothing. If this pipe shape did not actually block a naive read, the regression test would pass against the very code that shipped the defect."""
    mod = _load()
    r, w = os.pipe()
    finished = threading.Event()

    def _naive():
        with os.fdopen(r, "r", encoding="utf-8") as fh:
            fh.read()  # what the verb used to call
        finished.set()

    t = threading.Thread(target=_naive, daemon=True)
    t.start()
    try:
        assert not finished.wait(timeout=2.0), (
            "a plain read returned on a pipe whose write end is still open, so this "
            "fixture does not reproduce the hang and the test above is vacuous"
        )
    finally:
        os.close(w)  # release the reader thread
        t.join(timeout=5.0)
    assert mod is not None


def test_a_document_that_does_arrive_is_read_whole():
    """THE QUIET DIRECTION. The deadline is on the FIRST byte, so a writer that starts must still be read to EOF rather than truncated at the bound."""
    mod = _load()
    r, w = os.pipe()
    payload = "## Where it is\n\n%s\n" % ("x" * 4000)

    def _write_slowly():
        with os.fdopen(w, "w", encoding="utf-8") as fh:
            fh.write(payload[:100])
            fh.flush()
            time.sleep(0.3)
            fh.write(payload[100:])

    t = threading.Thread(target=_write_slowly, daemon=True)
    t.start()
    with _StdinFromFd(r):
        body, arrived = mod._read_document(seconds=5.0)
    t.join(timeout=5.0)
    assert arrived is True
    assert body == payload, "the document was truncated: got %d of %d chars" % (
        len(body),
        len(payload),
    )


def test_the_default_budget_is_a_real_bound():
    """A deadline nobody would wait out is a deadline in name only, and one of a few seconds would refuse a legitimate slow writer."""
    mod = _load()
    assert 5.0 <= mod.STATE_STDIN_WAIT_SECONDS <= 120.0
    assert mod.STATE_STDIN_WAIT_SECONDS > mod.STDIN_WAIT_SECONDS, (
        "the document budget must exceed the Stop-payload budget: a person or a "
        "generator producing 4 KB is not a hook pipe handing over a small JSON event"
    )
