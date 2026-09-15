"""Differential: `rediacc_ci.release.install_sh_config_check` against its twin
`.ci/scripts/test/test-install-sh-config.sh` (gate `check:ci-install-sh-config`).

BOTH SIDES PASS ON THE REAL TREE, which proves only that two programs agree
about an `install.sh` neither is currently catching out. So every case below
runs both against a FIXTURE TREE holding a MUTATED copy of
`packages/www/public/install.sh`, driving the twin's five failure branches --
including the one it was written for, "a preview-cloned backend must not
override the baked channel".

THE ONE BYTE THE TWO SIDES CANNOT SHARE is the mock server's port. Each side
boots its own `python3 -m http.server` on a kernel-assigned port, and case
five's line quotes it. `norm()` masks `127.0.0.1:<port>` on both sides; nothing
else is normalized, so the ANSI-free glyph lines, the blank lines
`write_install_config` prints, the tally and the exit code are all compared as
bytes.

HOW THE TWO SIDES ARE POINTED AT A FIXTURE, and it differs per side. The twin
resolves `REPO_ROOT` from `${BASH_SOURCE[0]}`, so it is COPIED into the fixture
and run from there. The port resolves it through `paths.repo_root()`, whose
documented single override is `$REDIACC_CI_ROOT`. Both then source the same
mutated `install.sh`.

NOTHING ON DISK IS MUTATED: every fixture is a `shutil.copy2` under pytest's
`tmp_path`.

K=5 LEDGER: `.ci/shadow/w7p6-install-sh-config.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.release import install_sh_config_check

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "test" / "test-install-sh-config.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "release" / "install_sh_config_check.py"
INSTALL_SH_REL = "packages/www/public/install.sh"
INSTALL_SH = ROOT / INSTALL_SH_REL

# The VALUES are the twin's literal glyph prefixes; the NAMES avoid "PASS",
# which ruff S105 reads as a hardcoded password.
OK_GLYPH = "  ✓ "
BAD_GLYPH = "  ✗ "

PORT_RE = re.compile(r"127\.0\.0\.1:\d+")

# Mutation anchors, each asserted present before it is used.
SERVER_DEFAULT = 'local account_server="${SERVER_URL:-https://www.rediacc.com}"'
EARLY_RETURN = '    if [[ -z "${SERVER_URL:-}" && "${CHANNEL:-$default_channel}" == "$default_channel" ]]; then'
CHMOD_ABSENT = '        chmod 600 "$config_file"\n    fi'
BAKED_CHANNEL_GUARD = 'if [[ -z "${REDIACC_CHANNEL:-}" && "$CHANNEL" == "$default_channel" ]]; then'
MINIMAL_CONFIG = 'local account_json="{\\"accountServer\\":\\"$account_server\\",\\"updateChannel\\":\\"$CHANNEL\\""'


def norm(text: str) -> str:
    """Mask the kernel-assigned mock port. Nothing else is normalized."""
    return PORT_RE.sub("127.0.0.1:PORT", text)


def build_fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    fixture = tmp_path / "fixture"
    (fixture / ".ci" / "scripts" / "test").mkdir(parents=True, exist_ok=True)
    (fixture / "packages" / "www" / "public").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, fixture / ".ci" / "scripts" / "test" / TWIN.name)
    shutil.copy2(INSTALL_SH, fixture / INSTALL_SH_REL)
    return fixture


def mutate(fixture: pathlib.Path, old: str, new: str) -> None:
    target = fixture / INSTALL_SH_REL
    text = target.read_text(encoding="utf-8")
    assert text.count(old) == 1, "anchor %r appears %d times" % (old, text.count(old))
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def _run(subject: pathlib.Path, fixture: pathlib.Path) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LC_ALL": "C",
    }
    if subject.suffix == ".py":
        runner = ["python3", str(subject)]
        env["PYTHONPATH"] = str(ROOT / ".ci")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["REDIACC_CI_ROOT"] = str(fixture)
    else:
        runner = ["bash", str(fixture / ".ci" / "scripts" / "test" / TWIN.name)]
    return subprocess.run(runner, env=env, capture_output=True, text=True, check=False, timeout=180)


def python_shows_caret_ruler() -> bool:
    """Does the `python3` on PATH draw a caret ruler under a `-c` traceback?

    ASKED, because it is a property of the INTERPRETER and this suite runs on two
    very different ones. Measured 2026-09-15:

        Python 3.14.4 (this tree's hosts)
            File "<string>", line 1, in <module>
              d={"a":1}; d["updateChannel"]
                         ~^^^^^^^^^^^^^^^^^
            KeyError: 'updateChannel'
        Python 3.12.3 (the GitHub runner)
            File "<string>", line 1, in <module>
            KeyError: 'updateChannel'

    CPython only began echoing the SOURCE of a `-c` snippet (and so the PEP 657
    ruler under it) in 3.13; before that there is no source line to underline.
    An unconditional `"^^^" in stderr` therefore passed on every machine here and
    failed in CI run 35009582358 -- the fourth toolchain in this wave whose
    version differs between this tree and the runner, after bash, jq and
    coreutils.

    THE DIFFERENTIAL IS NOT WEAKENED BY THIS. `assert_same` still compares the
    twin's and the port's stderr byte for byte, so a port that forged ANY part of
    the rendering still reds; this predicate only decides which anti-vacuity
    proof is available on the interpreter at hand.
    """
    proc = subprocess.run(
        ["python3", "-c", 'd={"a":1}; d["updateChannel"]'],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return "^^^" in proc.stderr


def run_both(
    fixture: pathlib.Path, *, port: pathlib.Path | None = None
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    return _run(TWIN, fixture), _run(port or PORT, fixture)


def assert_same(
    old: subprocess.CompletedProcess[str], new: subprocess.CompletedProcess[str]
) -> None:
    assert new.returncode == old.returncode, "exit: twin %s, port %s" % (
        old.returncode,
        new.returncode,
    )
    assert norm(new.stdout) == norm(old.stdout)
    assert norm(new.stderr) == norm(old.stderr)


# ---------------------------------------------------------------------------
# The green path
# ---------------------------------------------------------------------------


def test_real_tree_agrees(tmp_path: pathlib.Path) -> None:  # noqa: ARG001 -- symmetry
    old = _run(TWIN, ROOT)
    new = _run(PORT, ROOT)
    assert old.returncode == 0, old.stderr
    assert old.stdout.count(OK_GLYPH) == 5
    assert old.stdout.endswith("\nPassed: 5\nFailed: 0\n")
    assert old.stderr == ""
    assert_same(old, new)


def test_unmutated_fixture_is_the_same_run(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert_same(old, new)
    assert norm(old.stdout) == norm(_run(TWIN, ROOT).stdout)


# ---------------------------------------------------------------------------
# The failure branches, each reached by a real mutation
# ---------------------------------------------------------------------------


def test_a_wrong_default_account_server_is_caught(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    mutate(fixture, SERVER_DEFAULT, 'local account_server="${SERVER_URL:-https://V1.invalid}"')
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stderr == (
        BAD_GLYPH + "worker_channel_only: got channel=edge accountServer=https://V1.invalid; "
        "expected channel=edge accountServer=https://www.rediacc.com\n"
    )
    assert_same(old, new)


def test_a_wrong_config_mode_is_caught_on_every_writing_case(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    mutate(fixture, CHMOD_ABSENT, '        chmod 640 "$config_file"\n    fi')
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stderr.count("expected mode 600, got 640") == 4
    # The mode failure does not suppress the channel PASS lines: the twin's
    # `run_case` keeps going after a mode mismatch (:110-112).
    assert old.stdout.count(OK_GLYPH) == 5
    assert_same(old, new)


def test_a_config_that_is_never_written_is_caught(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    mutate(
        fixture,
        EARLY_RETURN,
        '    if [[ "${CHANNEL:-$default_channel}" == "$default_channel" ]]; then',
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stderr == (
        BAD_GLYPH + "worker_server_only: expected rediacc.json, but none was written\n"
    )
    assert_same(old, new)


def test_the_regression_this_gate_exists_for(tmp_path: pathlib.Path) -> None:
    """A preview-cloned backend must NOT override the baked channel.

    Removing the guard at `install.sh:220` lets server-info's `stable` win over
    the baked `edge`, which is the exact user-visible bug case five was written
    against.
    """
    fixture = build_fixture(tmp_path)
    mutate(fixture, BAKED_CHANNEL_GUARD, "if true; then")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "worker_full_with_server_info: got channel=stable" in old.stderr
    assert "expected channel=edge" in old.stderr
    assert_same(old, new)


def test_a_config_missing_a_key_kills_both_sides_the_same_way(
    tmp_path: pathlib.Path,
) -> None:
    """The `set -e` + un-redirected `python3 -c` path.

    `test-install-sh-config.sh:98` captures only stdout, so a `KeyError` puts
    CPython's own traceback -- caret ruler and tilde underline included -- on
    the gate's stderr and then ends the run. The port runs the identical
    command rather than forging that rendering; this case is what proves it.
    """
    fixture = build_fixture(tmp_path)
    mutate(
        fixture, MINIMAL_CONFIG, 'local account_json="{\\"accountServer\\":\\"$account_server\\""'
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stderr.startswith("Traceback (most recent call last):\n")
    assert old.stderr.rstrip("\n").endswith("KeyError: 'updateChannel'")
    # CPython's own rendering, proved without assuming an interpreter version.
    # The frame line is emitted by every CPython; the caret ruler is not.
    assert 'File "<string>", line 1, in <module>' in old.stderr, (
        "the traceback is not CPython's own: %r" % old.stderr
    )
    if python_shows_caret_ruler():
        assert "^^^" in old.stderr, "the caret ruler is part of what cannot be forged"
    assert "Passed:" not in old.stdout, "set -e ends the run before the tally"
    assert_same(old, new)


def test_a_missing_install_sh_is_the_same_refusal(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    (fixture / INSTALL_SH_REL).unlink()
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stderr == "FAIL: install.sh not found at %s/%s\n" % (fixture, INSTALL_SH_REL)
    assert old.stdout == ""
    assert_same(old, new)


# ---------------------------------------------------------------------------
# The pure helpers
# ---------------------------------------------------------------------------


def test_free_port_hands_back_a_bindable_port() -> None:
    port = install_sh_config_check.free_port()
    assert 1024 < port < 65536
    # The twin's trick is to bind, read the port and close: the port must be
    # re-bindable immediately afterwards or `http.server` would fail.
    sock = socket.socket()
    sock.bind(("127.0.0.1", port))
    sock.close()


def test_config_mode_matches_real_stat(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "cfg.json"
    target.write_text("{}", encoding="utf-8")
    for mode in (0o600, 0o640, 0o400, 0o644):
        target.chmod(mode)
        real = subprocess.run(
            ["stat", "-c", "%a", str(target)], capture_output=True, text=True, check=True
        ).stdout.strip()
        assert install_sh_config_check.config_mode(target) == real


def test_substituted_strips_every_trailing_newline() -> None:
    made = subprocess.CompletedProcess(args=[], returncode=0, stdout="edge\n\n\n", stderr="")
    assert install_sh_config_check.substituted(made) == "edge"
    kept = subprocess.CompletedProcess(args=[], returncode=0, stdout="a\nb\n", stderr="")
    assert install_sh_config_check.substituted(kept) == "a\nb"


# ---------------------------------------------------------------------------
# The control: a planted defect must turn this differential red
# ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_differential(tmp_path: pathlib.Path) -> None:
    """Make a COPY of the port accept any channel/server it is handed.

    That comparison is the gate's whole verdict, and it is invisible on a green
    tree: a port that always reported OK agrees with the twin everywhere except
    against an `install.sh` that really does override the baked channel, which
    is the fixture built here. The real port file is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = """        if got_channel == expect_channel and got_account == expect_account:
"""
    assert source.count(anchor) == 1, "the plant's anchor must still be where it was"
    broken = tmp_path / "install_sh_config_check_broken.py"
    broken.write_text(source.replace(anchor, "        if True:\n", 1), encoding="utf-8")

    fixture = build_fixture(tmp_path)
    mutate(fixture, BAKED_CHANNEL_GUARD, "if true; then")
    old, new = run_both(fixture, port=broken)
    assert old.returncode == 1, "the twin must catch the overridden channel"
    assert new.returncode != old.returncode, "PLANT DID NOT FIRE: the differential is vacuous"

    good_old, good_new = run_both(fixture)
    assert_same(good_old, good_new)
