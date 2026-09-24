"""Port of `.ci/scripts/test/gates/test-bws-rotate.sh`, retired 2026-09-23 (Ruling 7: scripts/dev is a Python tree).

Tests for `scripts/dev/bws-rotate.py`, which takes a live credential from a terminal and writes it to five places. Its refusals ARE the feature, and a refusal nobody exercises is indistinguishable from a function that always returns true.

NO REAL CREDENTIAL IS USED, READ OR WRITTEN, ANYWHERE IN THIS FILE. `bws` and `gh` are both faked on PATH; the fixture token is the literal string `0.fixture-client.fixture-secret:fixture-key`, which exists in no store.
Every case runs inside a fresh tmp_path and the subject is pointed at it with the five seams the module declares (BWS_BIN, GH_BIN, BWS_ROTATE_TARGET_FILE, BWS_ROTATE_GITMODULES, BWS_ROTATE_SECRET_MAP).

WHY A PTY, and it is not an affectation. The module's first refusal is `sys.stdin.isatty()`, which exists to make an AI session physically unable to feed it a credential.
That refusal is tested as a REAL process with stdin from a pipe (`run_lib_process`), and everything downstream of the prompt is tested through a real stdin pty (`run_full`), which `getpass.getpass` needs to turn echo off and actually read the pasted value. Without one, the whole write path would be unreachable and this file would only ever prove that the door is shut.

THE INPUT WAITS FOR ECHO-OFF, not a fixed sleep. A value written to the pty before `getpass` has turned echo off can be echoed back by the terminal driver and appear in the captured output (the "nothing is printed" assertion would then fire on the harness rather than on the subject); worse, `getpass` turns echo off with `termios.TCSAFLUSH`, which discards unread input at the moment it runs, so a write that lands a hair too early is silently dropped rather than merely echoed -- the exact shape of the pty hang `_bounded_stdout` guards against. `_wait_for_echo_off` polls the pty's ECHO bit through the master fd (which mirrors the slave's termios state, see pty(7)) until `getpass`'s own `tcsetattr` has run, which is deterministic where a fixed sleep before it was a bet against machine load. This assumes `getpass` turns echo off on THIS pty rather than on some other terminal: verified for this harness, `getpass.getpass` tries `/dev/tty` first and only falls back to `sys.stdin` when that open fails, and neither pytest nor a child spawned the way `run_full` spawns one has a controlling terminal at all here (`os.open('/dev/tty', ...)` raises ENXIO for both), so the `sys.stdin` fallback -- this test's own pty -- is the path that always runs.

EVERY REFUSAL HAS A MIRROR. A rail that cannot be crossed on purpose is indistinguishable from a verb that never writes anything, which is the exact failure mode a script guarding five credentials must not have.

FUNCTIONS ARE DRIVEN BY IMPORT, not by sourcing: unlike the bash twin, which needed `BWS_ROTATE_LIB=1` to reach its functions without hitting the prompt, importing this module never runs `main()` (the `if __name__ == "__main__"` guard), so no seam is needed for that half at all.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import pty as pty_module
import re
import selectors
import stat
import subprocess
import sys
import termios
import time
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci import paths

if TYPE_CHECKING:
    from pathlib import Path

MODULE_PATH = paths.from_root("scripts", "dev", "bws-rotate.py")
NOTICE = paths.from_root(".ci", "config", "bws-rotation-notice.txt")

FIXTURE_CLIENT = "fixture-client-one"
FIXTURE_TOKEN = "0.%s.fixture-secret:fixture-key" % FIXTURE_CLIENT
# The token "already installed", so check 3 has two different things to compare.
INSTALLED_TOKEN = "0.fixture-client-zero.old-secret:old-key"  # noqa: S105 -- fixture, exists in no store


def _load_module():
    """A fresh import of the subject, so each test's monkeypatched globals never leak into another."""
    spec = importlib.util.spec_from_file_location("bws_rotate_under_test", MODULE_PATH)
    assert spec is not None, "could not build a spec for %s" % MODULE_PATH
    assert spec.loader is not None, "the spec for %s has no loader" % MODULE_PATH
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def seed(root: Path, rows: int = 44) -> None:
    """Everything the subject reads, none of it real.

    THE FAKE bws ANSWERS FROM THE TOKEN IT IS GIVEN, which is what makes the live probe testable at all: a store cannot be made to return 3 secrets on demand. It also REFUSES without `--color no`, exactly as the bws-env fixtures do, so a subject that dropped the flag fails here rather than in production against a bws that wraps its JSON in truecolor escapes.
    """
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (root / "private" / "account").mkdir(parents=True, exist_ok=True)

    fake_bws = root / "bin" / "bws"
    fake_bws.write_text(
        "#!/bin/bash\n"
        'for a in "$@"; do [ "$a" = "--color" ] && seen=1; done\n'
        '[ -n "${seen:-}" ] || { echo "fake bws: caller did not pass --color" >&2; exit 3; }\n'
        'case "${BWS_ACCESS_TOKEN:-}" in\n'
        '  "%s") n=%d ;;\n'
        '  "%s") n=44 ;;\n'
        '  "0.short-client.s:k")     n=3 ;;\n'
        '  "")  echo "Missing access token" >&2; exit 1 ;;\n'
        '  *)   echo \'[400 Bad Request] {"error":"invalid_client"}\' >&2; exit 1 ;;\n'
        "esac\n"
        'python3 -c "\n'
        "import json,sys\n"
        "n=int(sys.argv[1])\n"
        "print(json.dumps([{'id':'i%%d'%%i,'key':'K%%d'%%i,'value':'v%%d'%%i} for i in range(n)]))\n"
        '" "$n"\n' % (FIXTURE_TOKEN, rows, INSTALLED_TOKEN),
        encoding="utf-8",
    )
    fake_bws.chmod(0o755)

    # The fake gh RECORDS rather than acts: argv on one line, stdin on the next, so a case can assert that the value arrived on stdin and never on argv.
    fake_gh = root / "bin" / "gh"
    fake_gh.write_text(
        "#!/bin/bash\n"
        'log="%s/gh.log"\n'
        'case "$1 ${2:-}" in\n'
        '  "auth status") exit 0 ;;\n'
        '  "secret list")\n'
        '    repo="$4"\n'
        '    printf \'LIST %%s\\n\' "$repo" >>"$log"\n'
        '    grep -qx "$repo" "%s/holders" 2>/dev/null || exit 0\n'
        "    printf 'BWS_ACCESS_TOKEN\\t2026-09-02T13:43:11Z\\n'\n"
        "    ;;\n"
        '  "secret set")\n'
        '    body="$(cat)"\n'
        '    printf \'SET argv=%%s stdin=%%s\\n\' "$*" "$body" >>"$log"\n'
        "    ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n" % (root, root),
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    # FIVE repositories, four of them derived from .gitmodules at run time. The URL spellings are deliberately mixed (https and ssh, with and without .git) because both forms appear in real submodule files.
    (root / ".gitmodules").write_text(
        '[submodule "private/renet"]\n'
        "\tpath = private/renet\n"
        "\turl = https://github.com/rediacc/renet.git\n"
        "\tbranch = main\n"
        '[submodule "private/homebrew-tap"]\n'
        "\tpath = private/homebrew-tap\n"
        "\turl = https://github.com/rediacc/homebrew-tap.git\n"
        "\tbranch = main\n"
        '[submodule "private/elite"]\n'
        "\tpath = private/elite\n"
        "\turl = git@github.com:rediacc/elite\n"
        "\tbranch = main\n"
        '[submodule "private/account"]\n'
        "\tpath = private/account\n"
        "\turl = https://github.com/rediacc/account.git\n"
        "\tbranch = main\n",
        encoding="utf-8",
    )

    # The live state D1 requires the target set to be DERIVED from: three of the five hold the secret, two do not.
    (root / "holders").write_text(
        "rediacc/console\nrediacc/account\nrediacc/renet\n", encoding="utf-8"
    )

    real_map = paths.from_root(".ci", "config", "bws-secret-map.json")
    (root / ".ci" / "config" / "bws-secret-map.json").write_text(
        real_map.read_text(encoding="utf-8"), encoding="utf-8"
    )
    token_dir = root / "xdg" / "rediacc"
    token_dir.mkdir(parents=True, mode=0o700)
    (token_dir / "bws-access-token").write_text(INSTALLED_TOKEN + "\n", encoding="utf-8")
    (token_dir / "bws-access-token").chmod(0o600)


def token_path(root: Path) -> Path:
    """The fixture's token-only file (PLAN-account-env-to-bws T3), never the operator's real one."""
    return root / "xdg" / "rediacc" / "bws-access-token"


def _seams(root: Path) -> dict[str, str]:
    return {
        "BWS_BIN": str(root / "bin" / "bws"),
        "GH_BIN": str(root / "bin" / "gh"),
        "BWS_ROTATE_TARGET_FILE": str(token_path(root)),
        "BWS_ROTATE_GITMODULES": str(root / ".gitmodules"),
        "BWS_ROTATE_SECRET_MAP": str(root / ".ci" / "config" / "bws-secret-map.json"),
    }


def module_for(root: Path, monkeypatch) -> Any:
    """A subject module whose globals point at the fixture root, matching the bash twin's env-var seams.

    Typed `Any`, deliberately: this is a hyphenated-filename module loaded by path, so no static type carries its real attributes, and a dozen per-call-site `# type: ignore[attr-defined]` comments would say the same thing eleven times over.
    """
    for key, value in _seams(root).items():
        monkeypatch.setenv(key, value)
    return _load_module()


def _read_pty(master_fd: int, proc: subprocess.Popen, timeout: float) -> bytes:
    """Drain a pty master until the child exits and the buffer is empty. Shared shape with `rediacc_ci.tests.differential.read_pty`; not imported directly because this one drains a STDIN-side pty rather than a stdout/stderr one."""
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
                    break
                if not data:
                    break
                chunks.append(data)
                continue
            if proc.poll() is not None:
                deadline_hits += 1
                if deadline_hits >= 2:
                    break
            else:
                deadline_hits += 1
                if deadline_hits * 0.25 > timeout:
                    break
    finally:
        sel.close()
    return b"".join(chunks)


def _bounded_stdout(proc: subprocess.Popen, timeout: float) -> bytes:
    """The child's stdout to EOF, but never longer than `timeout`.

    WHY. This used to be `proc.stdout.read()`, which returns only when the child closes stdout, that is when it exits, and it ran BEFORE the bounded `_read_pty`. A child still waiting on its pty (the input, written after a fixed sleep rather than a readiness wait, could lose that race on a loaded machine and never arrive at all) therefore held the test forever: on 2026-09-24 three xdist workers sat in exactly that read for 51 minutes and the run never finished. Now the wait is bounded, the child is killed, and the case FAILS with what it printed. `_wait_for_echo_off` has since closed the race itself; this bound stays as the control for the hang shape, proven by `test_a_child_stuck_on_its_pty_fails_the_case_instead_of_hanging` below.
    """
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        raise AssertionError(
            "bws-rotate did not exit within %ss; it is probably still waiting on its pty. Output so far: %r"
            % (timeout, (out or b"")[-800:])
        ) from None
    return out or b""


# Bound for _wait_for_echo_off, not an expected wait: getpass reaches its tcsetattr well
# under a second even on the loaded box this was written for (control passes in 1.44s per
# _bounded_stdout's own docstring). This only needs to be longer than that.
_ECHO_WAIT_TIMEOUT = 10.0


def _wait_for_echo_off(master_fd: int, proc: subprocess.Popen, deadline: float) -> None:
    """Block until the pty's ECHO bit goes low or the child exits, or raise once `deadline` seconds have passed with neither.

    REPLACES A FIXED time.sleep(0.5). On a loaded box that sleep can expire before `getpass` has reached its own `termios.tcsetattr` call, and writing before that call does not just risk an echoed value: `tcsetattr` runs with TCSAFLUSH, which discards any input already sitting unread in the pty at that instant, so an early write can vanish outright and leave the subject waiting on a pty nothing will ever fill again -- the hang `_bounded_stdout` exists to bound rather than actually prevent.

    Polling removes the guess. A write to the pty's master is reliably reflected in the slave's termios state as read back through the master fd (pty(7)), so observing ECHO go low here IS observing that `getpass`'s `tcsetattr` has already completed -- which happens before it starts reading, so a write issued right after this returns lands after any flush, never before it.

    THE CHILD-EXIT CHECK IS NOT AN AFTERTHOUGHT. `test_an_unreachable_fingerprint_tool_...` dies in `require_fingerprint_tool` before `read_candidate` ever runs `getpass`, so ECHO never moves at all; without this check every run of that case would burn the whole deadline and then fail on a subject that had already produced its own correct verdict. A refusal that fires before the prompt is not the race this function exists to close.
    """
    deadline_at = time.monotonic() + deadline
    while True:
        attrs = termios.tcgetattr(master_fd)
        if not attrs[3] & termios.ECHO:
            return
        if proc.poll() is not None:
            return
        if time.monotonic() >= deadline_at:
            raise AssertionError(
                "the pty's ECHO bit never went low within %ss and the child is still running; "
                "getpass never reached its tcsetattr, so bws-rotate is probably still blocked "
                "before the prompt" % deadline
            )
        time.sleep(0.01)


def run_full(
    root: Path, pasted: str, extra_env: dict[str, str] | None = None, timeout: float = 20
) -> tuple[int, str]:
    """The whole subject, through a real pty on STDIN, exactly like the bash twin's `run_full`.

    `getpass.getpass` opens `/dev/tty` for its prompt and echo-off read when stdin is a real terminal, so stdout/stderr are plain pipes here -- only stdin needs the pty.
    """
    master_fd, slave_fd = pty_module.openpty()
    env = {
        **os.environ,
        **_seams(root),
        "BWS_ACCESS_TOKEN": INSTALLED_TOKEN,
        "PATH": "%s:%s" % (root / "bin", os.environ.get("PATH", "")),
    }
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, str(MODULE_PATH)],
        stdin=slave_fd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(paths.repo_root()),
        text=False,
    )
    os.close(slave_fd)
    _wait_for_echo_off(master_fd, proc, _ECHO_WAIT_TIMEOUT)
    # The child exited before the prompt (an earlier refusal fired); the paste is moot.
    with contextlib.suppress(OSError):
        os.write(master_fd, (pasted + "\n").encode("utf-8"))
    out = _bounded_stdout(proc, timeout)
    tty_leak = _read_pty(master_fd, proc, timeout)
    proc.wait(timeout=timeout)
    os.close(master_fd)
    combined = out.decode("utf-8", "replace") + tty_leak.decode("utf-8", "replace")
    return proc.returncode, combined


# --------------------------------------------------------------------------- Preconditions.


def test_the_subject_and_its_tools_are_present():
    assert MODULE_PATH.is_file(), "subject under test is missing: %s" % MODULE_PATH
    assert os.access(MODULE_PATH, os.X_OK), (
        "%s is not executable, so the operator cannot run the one command the whole notice names"
        % MODULE_PATH
    )
    assert NOTICE.is_file(), "%s is missing; the subject's first action is to point at it" % NOTICE
    assert NOTICE.stat().st_size > 0, (
        "%s is empty; the subject's first action is to point at it" % NOTICE
    )


# --------------------------------------------------------------------------- B1: the input path. The refusal with no seam.


def test_a_non_tty_stdin_is_refused_with_exit_2(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    proc = subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=FIXTURE_TOKEN + "\n",
        capture_output=True,
        text=True,
        env={**os.environ, **_seams(root)},
        cwd=str(paths.repo_root()),
        timeout=20,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 2, (
        "a credential piped into the script was ACCEPTED; the one mechanism that keeps a "
        "tool call from feeding this script is gone: rc=%d out=%r" % (proc.returncode, combined)
    )
    assert "refuses a non-TTY stdin" in combined, "the refusal does not say what was refused"
    assert "bws-rotation-notice.txt" in combined, "the refusal does not point at the procedure"
    assert FIXTURE_TOKEN not in combined, "the refused value was echoed back in the refusal"


def test_the_subject_offers_no_flag_or_variable_that_supplies_the_value():
    # COMMENTS AND DOCSTRINGS ARE STRIPPED FIRST, and that is not a convenience: the subject's own module docstring says "There is no --token flag" as part of explaining why, so a grep over the raw bytes fires on the documentation of the absence, the exact inversion of what this check should do.
    body = MODULE_PATH.read_text(encoding="utf-8")
    body = re.sub(r'"""(?:[^"]|"(?!""))*"""', "", body, flags=re.DOTALL)
    lines = [ln for ln in body.splitlines() if not ln.strip().startswith("#")]
    stripped = "\n".join(lines)
    assert "--token" not in stripped, "the subject grew a --token flag; argv is visible in ps"
    assert "BWS_ROTATE_TOKEN" not in stripped, (
        "the subject grew an environment door around the TTY refusal"
    )
    assert "getpass" in stripped, "the prompt no longer reads with echo off"


# --------------------------------------------------------------------------- B2: the four checks, each driven directly and each mirrored.


def test_the_shape_check_accepts_a_token_and_refuses_five_near_misses(tmp_path, monkeypatch):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    mod = module_for(root, monkeypatch)
    assert mod.token_shape_ok(FIXTURE_TOKEN), "a correctly shaped token was refused"
    for bad in ["", "not-a-token", "0.onlyclient", "abc.def:ghi", "0.a.b c:d"]:
        assert not mod.token_shape_ok(bad), "the shape check accepted %r" % bad


def test_the_live_probe_counts_what_the_candidate_can_actually_read(tmp_path, monkeypatch):
    root = tmp_path / "t"
    root.mkdir()
    seed(root, 44)
    mod = module_for(root, monkeypatch)
    assert mod.probe_count(FIXTURE_TOKEN) == "44", (
        "the probe did not count the rows the store returned"
    )
    # A token that reads only three: exit 0, real output, most of the store invisible. This is the silent-404 shape the floor exists for.
    assert mod.probe_count("0.short-client.s:k") == "3", (
        "a scoped-down token did not report its short count"
    )
    assert mod.probe_count("0.wrong-client.s:k") is None, (
        "a candidate bws rejected outright still produced a count"
    )


def test_a_short_listing_is_refused_before_anything_is_written(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root, 12)
    env_before = token_path(root).read_text(encoding="utf-8")
    rc, out = run_full(root, FIXTURE_TOKEN)
    assert rc == 1, "a candidate that reads 12 of 40 secrets was installed"
    assert "floor is 40" in out, "the refusal does not name the floor it failed"
    assert "SCOPED-DOWN" in out, "the refusal does not say what a short listing means"
    assert token_path(root).read_text(encoding="utf-8") == env_before, (
        "the token file was written despite the refusal"
    )
    gh_log = root / "gh.log"
    n_set = gh_log.read_text(encoding="utf-8").count("\nSET") if gh_log.exists() else 0
    assert n_set == 0, "a repository secret was written despite the refusal"


def test_the_same_credential_pasted_back_is_refused(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    rc, out = run_full(root, INSTALLED_TOKEN)
    assert rc == 1, "the credential already installed was accepted as its own replacement"
    assert "SAME machine account" in out, "the refusal does not say the two are one account"
    gh_log = root / "gh.log"
    n_set = gh_log.read_text(encoding="utf-8").count("\nSET") if gh_log.exists() else 0
    assert n_set == 0, "a rotation that changed nothing still wrote to five repositories"


def test_an_unreachable_fingerprint_tool_refuses_instead_of_blaming_the_candidate(tmp_path):
    """THIS CASE EXISTS BECAUSE A PLANT FOUND THE BUG in the bash original. `fingerprint_of` answers "" both for a token with no client id and for a module that could not be imported, and check 3 read the second as the first: a copy of the script run from outside the repository refused a good token with "the candidate has no client id".
    A missing tool must never wear a verdict's clothes.

    The copy sits under the fixture root, so its own `parents[2]` puts ROOT somewhere with no `.ci/` in it. That is the real shape of the bug rather than a simulation of it.
    """
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    copy_path = root / "copy.py"
    copy_path.write_text(MODULE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    copy_path.chmod(0o755)
    # run_full targets MODULE_PATH directly; drive the COPY instead for this one case.
    master_fd, slave_fd = pty_module.openpty()
    env = {
        **os.environ,
        **_seams(root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": "%s:%s" % (root / "bin", os.environ.get("PATH", "")),
    }
    proc = subprocess.Popen(
        [sys.executable, str(copy_path)],
        stdin=slave_fd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(root),
        text=False,
    )
    os.close(slave_fd)
    _wait_for_echo_off(master_fd, proc, _ECHO_WAIT_TIMEOUT)
    # The child exited before the prompt (the expected refusal fired); the paste is moot.
    with contextlib.suppress(OSError):
        os.write(master_fd, (FIXTURE_TOKEN + "\n").encode("utf-8"))
    stdout_bytes = _bounded_stdout(proc, 20)
    out_bytes = stdout_bytes + _read_pty(master_fd, proc, 20)
    proc.wait(timeout=20)
    os.close(master_fd)
    out = out_bytes.decode("utf-8", "replace")
    assert proc.returncode == 1, (
        "a script that cannot reach its own fingerprint tool reported success"
    )
    assert "fingerprint tool could not be reached" in out, (
        "the refusal blames the candidate rather than naming the tool that did not run"
    )
    assert "python3 -m rediacc_ci.core.bws_env fingerprint" in out, (
        "the refusal does not carry the command that would reproduce it"
    )
    assert "no client id to fingerprint" not in out, (
        "the refusal still reads as a verdict about the candidate"
    )


def test_the_fingerprint_ignores_the_secret_half_and_separates_the_client_half(
    tmp_path, monkeypatch
):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    mod = module_for(root, monkeypatch)
    a = mod.fingerprint_of("0.%s.secret-one:key-one" % FIXTURE_CLIENT)
    b = mod.fingerprint_of("0.%s.secret-two:key-two" % FIXTURE_CLIENT)
    c = mod.fingerprint_of("0.other-client.secret-one:key-one")
    d = mod.fingerprint_of("not-a-token")
    assert a, "the fingerprint did not behave as a client-id digest"
    assert a == b, "the fingerprint did not behave as a client-id digest"
    assert a != c, "the fingerprint moved with the SECRET half instead of the CLIENT half"
    assert d == "", "a shapeless value produced a fingerprint"
    assert len(a) <= 32, "the fingerprint output is longer than a digest"


# --------------------------------------------------------------------------- B3 and D1: propagation derived from live state.


def test_the_target_set_is_derived_from_gitmodules_and_not_listed(tmp_path, monkeypatch):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    mod = module_for(root, monkeypatch)
    assert mod.target_repos() == [
        "rediacc/account",
        "rediacc/console",
        "rediacc/elite",
        "rediacc/homebrew-tap",
        "rediacc/renet",
    ], "the derived target set is not the parent plus the four submodules"
    # A FIFTH submodule, added to the fixture only. If the set were hardcoded this would not move, which is the whole claim.
    with (root / ".gitmodules").open("a", encoding="utf-8") as fh:
        fh.write(
            '[submodule "private/fifth"]\n\tpath = private/fifth\n'
            "\turl = https://github.com/rediacc/fifth.git\n"
        )
    mod2 = module_for(root, monkeypatch)
    assert "rediacc/fifth" in mod2.target_repos(), (
        "a fifth submodule did not appear in the target set, so the list is hardcoded somewhere"
    )


def test_exactly_the_repositories_that_hold_a_secret_are_written(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    rc, out = run_full(root, FIXTURE_TOKEN)
    assert rc == 0, "a valid rotation failed: %s" % out
    gh_log = (root / "gh.log").read_text(encoding="utf-8")
    set_lines = "\n".join(ln for ln in gh_log.splitlines() if ln.startswith("SET"))
    wrote = sorted(set(re.findall(r"rediacc/[a-z-]+", set_lines)))
    assert wrote == ["rediacc/account", "rediacc/console", "rediacc/renet"], (
        "the written set is not the three repositories that already held the secret"
    )
    assert "SKIP     rediacc/elite" in out, "a repository without the secret was not named"
    assert "SKIP     rediacc/homebrew-tap" in out, "the second such repository was not named"


def test_a_repository_that_gains_a_secret_is_written_on_the_next_run(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    # D1's real claim: the rule is derived from LIVE state, not from a list. The same fixture, one repository flipped into holding a secret, must be written.
    with (root / "holders").open("a", encoding="utf-8") as fh:
        fh.write("rediacc/elite\n")
    rc, out = run_full(root, FIXTURE_TOKEN)
    assert rc == 0, "the rotation failed: %s" % out
    gh_log = (root / "gh.log").read_text(encoding="utf-8")
    assert "rediacc/elite" in "\n".join(ln for ln in gh_log.splitlines() if ln.startswith("SET")), (
        "a repository that now HOLDS the secret was skipped, so the refresh set is hardcoded"
    )
    assert "SKIP     rediacc/elite" not in out, (
        "the same repository was both written and reported as absent"
    )


def test_the_value_reaches_gh_on_stdin_and_never_on_argv(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    rc, out = run_full(root, FIXTURE_TOKEN)
    assert rc == 0, "the rotation failed: %s" % out
    gh_log = (root / "gh.log").read_text(encoding="utf-8")
    set_lines = [ln for ln in gh_log.splitlines() if ln.startswith("SET")]
    argvs = "\n".join(ln.split(" stdin=")[0] for ln in set_lines)
    assert FIXTURE_TOKEN not in argvs, (
        "the token appeared in gh's ARGV, which is visible in ps and in process accounting"
    )
    assert "stdin=%s" % FIXTURE_TOKEN in set_lines[0], (
        "the token did not arrive on gh's stdin, so it came from somewhere this test cannot see"
    )


# --------------------------------------------------------------------------- B4: the local write, all-or-nothing, and the honest verdict.


def test_the_token_file_is_replaced_whole_at_mode_0600(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    rc, out = run_full(root, FIXTURE_TOKEN)
    assert rc == 0, "the rotation failed: %s" % out
    body = token_path(root).read_text(encoding="utf-8")
    assert body == FIXTURE_TOKEN + "\n", "the token file does not hold exactly the new value"
    assert INSTALLED_TOKEN not in body, "the OLD value survived beside the new one"
    assert stat.S_IMODE(token_path(root).stat().st_mode) == 0o600, "the token file is not 0600"
    assert stat.S_IMODE(token_path(root).parent.stat().st_mode) == 0o700, (
        "its directory is not 0700"
    )
    assert not list(token_path(root).parent.glob("*.rotate.*")), "a temporary was left behind"


def test_an_absent_token_file_is_created_0600_in_a_0700_directory(tmp_path, monkeypatch):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    token_path(root).unlink()
    token_path(root).parent.rmdir()
    mod = module_for(root, monkeypatch)
    mod.token_file_write("created-value")
    assert token_path(root).read_text(encoding="utf-8") == "created-value\n"
    assert stat.S_IMODE(token_path(root).stat().st_mode) == 0o600
    assert stat.S_IMODE(token_path(root).parent.stat().st_mode) == 0o700


def test_a_failed_repository_write_is_reported_and_exits_non_zero(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    # One repository that cannot be written: `gh secret set` fails for it only.
    gh_path = root / "bin" / "gh"
    body = gh_path.read_text(encoding="utf-8")
    body = body.replace(
        '  "secret set")\n',
        '  "secret set")\n    case "$*" in *rediacc/renet*) exit 1 ;; esac\n',
    )
    gh_path.write_text(body, encoding="utf-8")
    rc, out = run_full(root, FIXTURE_TOKEN)
    assert rc == 1, "a rotation that could not write one of its targets reported success"
    assert "were NOT written" in out, "the partial failure is not named as one"
    assert "split across two credentials" in out, (
        "the report does not say what state the fleet is now in"
    )


def test_the_verdict_states_what_it_cannot_prove(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    rc, out = run_full(root, FIXTURE_TOKEN)
    assert rc == 0, "the rotation failed: %s" % out
    assert "cannot be read" in out, "the verdict does not state the limit of what it proved"
    assert "next CI run is the only end-to-end proof" in out, (
        "the verdict does not name the only thing that actually proves the write"
    )
    assert "OLD token is still live" in out, (
        "the verdict does not say the old credential has not been revoked"
    )
    # D2: the two repositories that hold this secret with no consumer are a DECISION, and the decision is stated at the one moment anybody is thinking about these credentials rather than left in a plan nobody opens during a rotation.
    assert "OPEN DECISION" in out, "the dormant-secret decision is not surfaced"
    assert "private/account and private/renet" in out, (
        "the decision does not name which repositories it is about"
    )


# --------------------------------------------------------------------------- The constraint the whole script exists to keep.


def test_no_part_of_the_value_reaches_any_stream(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    rc, out = run_full(root, FIXTURE_TOKEN)
    assert rc == 0, "the rotation failed: %s" % out
    assert "fixture-secret" not in out, "the SECRET half of the token appeared in the output"
    assert "fixture-key" not in out, "the encryption-key half of the token appeared in the output"
    assert FIXTURE_TOKEN not in out, "the whole token appeared in the output"
    # The CONTROL for this assertion: the run genuinely produced output, and it genuinely carried the one derived value that IS publishable. Without this, a script that printed nothing at all would pass every line above.
    assert "4/4" in out, "the run did not reach the end, so the three checks above proved nothing"
    assert "client id " in out, "the publishable fingerprint was not printed either, so nothing was"


def test_a_child_stuck_on_its_pty_fails_the_case_instead_of_hanging():
    """CONTROL for `_bounded_stdout`: a child blocked reading a pty nobody writes to is the shape that held three workers for 51 minutes. It must become a failed case within the bound."""
    master_fd, slave_fd = pty_module.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"],
        stdin=slave_fd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    os.close(slave_fd)
    started = time.monotonic()
    try:
        with pytest.raises(AssertionError, match="did not exit within"):
            _bounded_stdout(proc, 1)
        assert time.monotonic() - started < 15, "the bound did not bound anything"
        assert proc.poll() is not None, "the stuck child was left running"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        os.close(master_fd)
