"""Run the bash original and the Python port, and compare the bytes.

WHY THIS FILE EXISTS. Every module in `rediacc_ci` replaces something that is
already running in this tree, and "the port looks right" is not evidence. The
acceptance rule for the whole workstream is that a port is proven EQUIVALENT to
the thing it replaces, in the shape `.ci/scripts/quality/check-python-lint.sh`
already uses for its own control: build a specimen, run both implementations
over it, and compare. This module is the plumbing that makes that cheap enough
to do for every case rather than for one.

THREE THINGS IT GETS RIGHT THAT AN INLINE `subprocess.run` DOES NOT.

  1. STDOUT AND STDERR ARE NEVER MERGED. `2>&1` is the default reflex and it
     destroys exactly the defect these tests exist to catch. The 2026-09-06
     emit-advisory incident was a STREAM SWAP -- log_info moved from stderr to
     stdout -- and `.ci/scripts/test/gates/test-emit-advisory.sh:100-102` says
     so in as many words: "The cases below capture stdout and stderr into
     SEPARATE files on purpose. The defect is a stream swap; the `2>&1` used by
     every case above merges the two streams back together and would hide it
     completely." Every function here returns the two separately, and there is
     no option to combine them.

  2. A REAL TTY IS AVAILABLE. Colour is decided by `isatty`, so a differential
     that only ever runs off a tty proves the boring half. `bash_streams(...,
     tty="stderr")` puts a pseudo-terminal on the stream under test, which is
     the only way to exercise the branch a developer actually sees.

  3. THE ENVIRONMENT IS EXPLICIT. `env=` REPLACES rather than extends, with a
     small documented base, because a differential that inherits the caller's
     environment passes or fails depending on whether the developer running it
     happens to export CI or NO_COLOR. Inheriting is how a test becomes green
     on one machine and red on another for reasons nobody can see.

WHAT A PTY DOES TO THE BYTES, since it is the part that surprises people. A tty
in its default mode has ONLCR set, so every `\\n` the child writes arrives at the
master as `\\r\\n`. That is the terminal discipline, not the program's output, so
`read_pty` strips the carriage returns. Without that every tty-mode comparison
fails on invisible bytes and the natural "fix" is to compare stripped strings,
which would also stop the comparison seeing a real trailing-whitespace change.
"""

import os
import pty
import re
import selectors
import subprocess

from rediacc_ci import paths

# The environment every differential starts from. Deliberately tiny.
#
# PATH is needed (bash resolves `git`, `timeout`, `sleep` through it). HOME is
# needed because git refuses some operations without one. LC_ALL=C pins message
# text and, more importantly, sort order: `git ls-files` output compared against a Python sort diverges under a locale with different collation, which is a difference in the TEST rather than in the thing under test.
BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
}

# How long any single differential child may run. A hung bash in a test suite is indistinguishable from a slow one until CI's own job timeout fires 15 minutes later, having reported nothing.
DEFAULT_TIMEOUT = 60


def repo() -> str:
    """The repository root as a string, for `cwd=`."""
    return str(paths.repo_root())


def env_for(**overrides: str) -> dict[str, str]:
    """BASE_ENV plus overrides. A value of None REMOVES the key.

    The removal case is the interesting one: several conditions in this repo are
    `[ -z "${NO_COLOR:-}" ]` or `[ "${CI:-}" != "true" ]`, which distinguish
    unset from empty-string in ways `env["X"] = ""` cannot express.
    """
    out = dict(BASE_ENV)
    for key, value in overrides.items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def read_pty(master_fd: int, proc: subprocess.Popen, timeout: float) -> bytes:
    """Drain a pty master until the child exits and the buffer is empty.

    THE EIO IS NORMAL, NOT AN ERROR. When the last slave descriptor closes, Linux
    reports EIO to a reader of the master rather than a clean EOF. Treating that
    as a failure is the classic pty bug; treating it as end-of-stream is correct.

    A selector rather than a blocking read because the child may exit having
    written nothing, and a blocking read on a master whose slave this process
    still holds open would never return.
    """
    chunks: list[bytes] = []
    sel = selectors.DefaultSelector()
    sel.register(master_fd, selectors.EVENT_READ)
    deadline_hits = 0
    try:
        while True:
            events = sel.select(timeout=0.25)
            if events:
                try:
                    data = os.read(master_fd, 65536)
                except OSError:
                    break  # EIO: every slave is closed, so this is the end
                if not data:
                    break
                chunks.append(data)
                continue
            if proc.poll() is not None:
                # The child is gone and nothing is pending. One more short pass catches bytes written between the poll and the select.
                deadline_hits += 1
                if deadline_hits >= 2:
                    break
            else:
                deadline_hits += 1
                if deadline_hits * 0.25 > timeout:
                    break
    finally:
        sel.close()
    # ONLCR: the line discipline turns every \n into \r\n on the way out. That is the terminal's doing, not the program's, so it is undone here rather than by every caller comparing stripped strings.
    return b"".join(chunks).replace(b"\r\n", b"\n")


def bash_streams(
    script: str,
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    tty: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, str, str]:
    """Run `script` under bash. Returns (returncode, stdout, stderr), separately.

    `tty` is None, "stdout" or "stderr": the named stream gets a pseudo-terminal
    and the other gets a pipe. Only one at a time, on purpose -- the whole point
    of most of these cases is that one stream is a terminal and the other is not,
    which is precisely the asymmetry the 11-file `[ -t 1 ]`-then-write-to-stderr
    variant gets wrong.

    `bash`, not `sh`: every script here is `#!/bin/bash` and uses `[[`.
    """
    environ = BASE_ENV if env is None else env
    workdir = repo() if cwd is None else cwd

    if tty is None:
        proc = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
            cwd=workdir,
            env=environ,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr

    if tty not in ("stdout", "stderr"):
        raise ValueError("tty must be None, 'stdout' or 'stderr' (got %r)" % tty)

    master_fd, slave_fd = pty.openpty()
    other = subprocess.PIPE
    kwargs = (
        {"stdout": slave_fd, "stderr": other}
        if tty == "stdout"
        else {
            "stdout": other,
            "stderr": slave_fd,
        }
    )
    proc = subprocess.Popen(
        ["bash", "-c", script],
        cwd=workdir,
        env=environ,
        text=False,
        **kwargs,
    )
    # CLOSED IN THE PARENT IMMEDIATELY. While this process holds the slave open, the master never sees EOF and read_pty would spin until its timeout on every single case -- turning a fast suite into a slow one for a reason that looks like flakiness.
    os.close(slave_fd)
    try:
        tty_text = read_pty(master_fd, proc, timeout).decode("utf-8", "replace")
        pipe_bytes = b""
        pipe = proc.stdout if tty == "stderr" else proc.stderr
        if pipe is not None:
            pipe_bytes = pipe.read()
            pipe.close()
        proc.wait(timeout=timeout)
    finally:
        os.close(master_fd)
    pipe_text = pipe_bytes.decode("utf-8", "replace")
    if tty == "stdout":
        return proc.returncode, tty_text, pipe_text
    return proc.returncode, pipe_text, tty_text


def escape_bytes(text: str) -> int:
    """How many ESC bytes are in `text`.

    The single number that answers "did colour leak into this stream", which is
    the assertion `test-emit-advisory.sh:172` makes with `tr -cd '\\033' | wc -c`.
    Counted rather than pattern-matched so a NEW escape sequence nobody
    anticipated still trips it.
    """
    return text.count("\033")


# `<cache>/shfmt-3.13.1/shfmt.1R2NkECK` -> `.../shfmt.<tmp>`, and the same for shellcheck's `sc.XXXXXXXX` and actionlint's `al.XXXXXXXX` staging directories.
#
# BOTH toolchain download helpers give every process its OWN temp name, because the single fixed path they shared before was a data-corruption race between concurrent acquirers (the reasoning is at `.ci/scripts/lib/toolchain.sh`, in `_toolchain_download_shfmt`). The randomness IS the fix, so it is the one token a twin/port differential must not demand equality of -- `mktemp` and
# `tempfile` draw from different alphabets and always will. Masking it leaves every observable claim intact: the flags, the URL, the order, and the fact that a temp path is used at all.
#
# Shared rather than copied into each differential, because the first version of this lived in the shfmt module alone and the shellcheck module failed the same way twenty minutes later.
_TOOLCHAIN_TMP_RE = re.compile(r"(/(?:shfmt|sc|al))\.[A-Za-z0-9_]{8}\b")


def mask_toolchain_tmp(text: str) -> str:
    """Replace per-process toolchain temp names with a stable `<tmp>`."""
    return _TOOLCHAIN_TMP_RE.sub(r"\1.<tmp>", text)
