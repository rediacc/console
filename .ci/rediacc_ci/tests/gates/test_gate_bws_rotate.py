"""Port of `.ci/scripts/test/gates/test-bws-rotate.sh`, retired 2026-09-23 (Ruling 7: scripts/dev is a Python tree).

Tests for `scripts/dev/bws-rotate.py`, which takes a live credential from a terminal and writes it to five places. Its refusals ARE the feature, and a refusal nobody exercises is indistinguishable from a function that always returns true.

NO REAL CREDENTIAL IS USED, READ OR WRITTEN, ANYWHERE IN THIS FILE. `bws` and `gh` are both faked on PATH; the fixture token is the literal string `0.fixture-client.fixture-secret:fixture-key`, which exists in no store.
Every case runs inside a fresh tmp_path and the subject is pointed at it with the five seams the module declares (BWS_BIN, GH_BIN, BWS_ROTATE_ENV_FILE, BWS_ROTATE_GITMODULES, BWS_ROTATE_SECRET_MAP).

WHY A PTY, and it is not an affectation. The module's first refusal is `sys.stdin.isatty()`, which exists to make an AI session physically unable to feed it a credential.
That refusal is tested as a REAL process with stdin from a pipe (`run_lib_process`), and everything downstream of the prompt is tested through a real stdin pty (`run_full`), which `getpass.getpass` needs to turn echo off and actually read the pasted value. Without one, the whole write path would be unreachable and this file would only ever prove that the door is shut.

THE INPUT IS DELAYED ON PURPOSE, same reason the bash twin delayed it: a value written to the pty before `getpass` has had a chance to open it and turn echo off can be echoed back by the terminal driver itself and appear in the captured output, which would make the "nothing is printed" assertion fire on the harness rather than on the subject.

EVERY REFUSAL HAS A MIRROR. A rail that cannot be crossed on purpose is indistinguishable from a verb that never writes anything, which is the exact failure mode a script guarding five credentials must not have.

FUNCTIONS ARE DRIVEN BY IMPORT, not by sourcing: unlike the bash twin, which needed `BWS_ROTATE_LIB=1` to reach its functions without hitting the prompt, importing this module never runs `main()` (the `if __name__ == "__main__"` guard), so no seam is needed for that half at all.
"""

from __future__ import annotations

import importlib.util
import os
import pty as pty_module
import re
import selectors
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

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
    (root / "private" / "account" / ".env").write_text(
        "SOME_OTHER=keep-me\nBWS_ACCESS_TOKEN=%s\nTRAILING=also-keep\n" % INSTALLED_TOKEN,
        encoding="utf-8",
    )


def _seams(root: Path) -> dict[str, str]:
    return {
        "BWS_BIN": str(root / "bin" / "bws"),
        "GH_BIN": str(root / "bin" / "gh"),
        "BWS_ROTATE_ENV_FILE": str(root / "private" / "account" / ".env"),
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
    try:
        # HALF A SECOND ON PURPOSE, same reason the bash twin delayed it: writing before the subject's getpass has opened /dev/tty and turned echo off risks the terminal driver echoing the paste back into the transcript, which would make the "nothing is printed" assertion fire on the harness rather than on the subject.
        time.sleep(0.5)
        os.write(master_fd, (pasted + "\n").encode("utf-8"))
    finally:
        pass
    out = proc.stdout.read() if proc.stdout else b""
    if proc.stdout:
        proc.stdout.close()
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
    env_before = (root / "private" / "account" / ".env").read_text(encoding="utf-8")
    rc, out = run_full(root, FIXTURE_TOKEN)
    assert rc == 1, "a candidate that reads 12 of 40 secrets was installed"
    assert "floor is 40" in out, "the refusal does not name the floor it failed"
    assert "SCOPED-DOWN" in out, "the refusal does not say what a short listing means"
    assert (root / "private" / "account" / ".env").read_text(encoding="utf-8") == env_before, (
        "the .env was written despite the refusal"
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
    time.sleep(0.5)
    os.write(master_fd, (FIXTURE_TOKEN + "\n").encode("utf-8"))
    stdout_bytes = proc.stdout.read() if proc.stdout else b""
    if proc.stdout:
        proc.stdout.close()
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


def test_the_env_file_is_rewritten_in_place_without_losing_its_neighbours(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    rc, out = run_full(root, FIXTURE_TOKEN)
    assert rc == 0, "the rotation failed: %s" % out
    env_body = (root / "private" / "account" / ".env").read_text(encoding="utf-8")
    assert "BWS_ACCESS_TOKEN=%s" % FIXTURE_TOKEN in env_body, "the new value did not land in .env"
    assert "SOME_OTHER=keep-me" in env_body, "a neighbouring key was lost by the rewrite"
    assert "TRAILING=also-keep" in env_body, "the key after the rotated one was lost"
    assert INSTALLED_TOKEN not in env_body, "the OLD value is still in .env beside the new one"
    assert env_body.count("BWS_ACCESS_TOKEN=") == 1, (
        "the rewrite appended a second definition instead of replacing the first"
    )


def test_an_absent_key_is_appended_rather_than_silently_dropped(tmp_path, monkeypatch):
    root = tmp_path / "t"
    root.mkdir()
    seed(root)
    (root / "private" / "account" / ".env").write_text("ONLY_OTHER=x\n", encoding="utf-8")
    mod = module_for(root, monkeypatch)
    mod.env_file_write("appended-value")
    body = (root / "private" / "account" / ".env").read_text(encoding="utf-8")
    assert "BWS_ACCESS_TOKEN=appended-value" in body, (
        "a .env with no existing definition came back with none"
    )
    assert "ONLY_OTHER=x" in body, "the existing line was lost"


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
