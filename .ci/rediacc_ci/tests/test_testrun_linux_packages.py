"""`rediacc_ci.testrun.linux_packages` against its bash twin `.ci/scripts/test/test-linux-packages.sh`.

Two layers. The pure helpers (the version token regex, the metadata field check, the welded-armor transform) are driven against the twin's OWN functions and awk program, extracted from its text. The `--dry-run` path (real nfpm, real package builders, no Docker) is run on both sides and compared with temporary paths masked. The full path (Docker images, signing, nginx) is exercised by the live run in the porting report.

INTENTIONAL DELTAS (Rule T), each pinned by a `test_delta_*`: an unknown argument is refused; the throwaway GPG home is removed on every path; the nginx container and network are removed on every path; failing `gpg` is reported where it happens. The twin's behaviour is shown from its own text where running it would start containers.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import typing

import pytest

from rediacc_ci.testrun import linux_packages as port
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import testrun_support as ts
from rediacc_ci.tests.twin_names import as_twin, usage_command
from rediacc_ci.well_known import RELEASES_ORIGIN

TWIN_REL = ".ci/scripts/test/test-linux-packages.sh"
TWIN = ts.ROOT / TWIN_REL
MODULE = "rediacc_ci.testrun.linux_packages"


# The retired twin's answers, measured while `test-linux-packages.sh` still existed (its `version_token_re` and `assert_version_field` functions and its welding awk program were run on these exact inputs, PLAN-retire-bash-oracles B3).
@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("99.0.0", "(^|[^0-9.])v?99\\.0\\.0([^0-9.]|$)"),
        ("v1.2.3", "(^|[^0-9.])v?1\\.2\\.3([^0-9.]|$)"),
        ("10.20.30", "(^|[^0-9.])v?10\\.20\\.30([^0-9.]|$)"),
        ("1.2.3-rc.1", "(^|[^0-9.])v?1\\.2\\.3-rc\\.1([^0-9.]|$)"),
    ],
)
def test_version_token_re_matches_the_twin(version: str, expected: str) -> None:
    assert port.version_token_re(version) == expected


@pytest.mark.parametrize(
    ("text", "label", "accepted"),
    [
        ("Package: x\nVersion: 99.0.0\n", "Version", True),
        (" Version : 99.0.0\n", "Version", True),
        ("Version: 99.0.01\n", "Version", False),
        ("Version: 199.0.0\n", "Version", False),
        ("Name: x\n", "Version", False),
        ("Version: 99.0.0\nVersion: 1\n", "Version", True),
    ],
)
def test_assert_version_field_matches_the_twin(text: str, label: str, accepted: bool) -> None:
    assert port.assert_version_field(text, label) is accepted


ARMOR = "-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nAAAA\nBBBB\nCCCC\nDDDD\nEEEE\nFFFF\nGGGG\n=chk\n-----END PGP PRIVATE KEY BLOCK-----"
# What the twin's awk program printed for ARMOR: the fourth body line and the fifth welded into one, then a trailing newline.
WELDED = "-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nAAAA\nBBBB\nCCCC\nDDDDEEEE\nFFFF\nGGGG\n=chk\n-----END PGP PRIVATE KEY BLOCK-----\n"


def test_weld_armor_matches_the_twins_awk_program() -> None:
    assert port.weld_armor(ARMOR) == WELDED
    assert "DDDDEEEE" in WELDED


# ---- dry run, both sides -----------------------------------------------------------------------------------------------------


def nfpm_available() -> bool:
    if shutil.which("nfpm"):
        return True
    fetched = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.build.ensure_nfpm"],
        env={"PYTHONPATH": str(ts.ROOT / ".ci"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    return fetched.returncode == 0


def mask_paths(text: str) -> str:
    return re.sub(r"/tmp/[A-Za-z0-9._-]+|/[A-Za-z0-9._/-]*/tmp[A-Za-z0-9._-]+", "<TMP>", text)


def test_dry_run_matches_the_twin() -> None:
    if not nfpm_available():
        pytest.skip("nfpm cannot be fetched on this host (offline)")

    def twin_streams() -> tuple[int, str, str]:
        proc = subprocess.run(
            [ts.BASH, str(TWIN), "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
            stdin=subprocess.DEVNULL,
        )
        return proc.returncode, proc.stdout, proc.stderr

    # The bash twin is retired: its answer comes from the golden (PLAN-retire-bash-oracles B3).
    old = subprocess.CompletedProcess([], *diff.twin_call(TWIN_REL, ["dry-run"], twin_streams))
    new = subprocess.run(
        [sys.executable, "-m", MODULE, "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "PYTHONPATH": str(ts.ROOT / ".ci")},
    )
    assert old.returncode == 0, old.stderr
    assert (new.returncode, mask_paths(as_twin(new.stdout)), mask_paths(as_twin(new.stderr))) == (
        old.returncode,
        mask_paths(old.stdout),
        mask_paths(old.stderr),
    )
    assert "21 passed, 0 failed" in new.stderr


# ---- intentional deltas ------------------------------------------------------------------------------------------------------


def test_delta_unknown_arguments_are_refused() -> None:
    new = subprocess.run(
        [sys.executable, "-m", MODULE, "--dry-runn"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ts.ROOT / ".ci")},
    )
    assert new.returncode == 2
    assert "Unknown option: --dry-runn" in new.stderr
    # The retired twin read exactly one thing, the first argument, and had no refusal arm: `--dry-runn` or `x --dry-run` silently ran the full Docker suite.


class StubSuite(port.Suite):
    """A Suite whose process calls are scripted, so the cleanup behaviour can be observed without gpg, nfpm or Docker."""

    def __init__(
        self,
        root: pathlib.Path,
        script: typing.Callable[
            [list[str], dict[str, str] | None], subprocess.CompletedProcess[str]
        ],
    ) -> None:
        super().__init__(False, root, root / "t", RELEASES_ORIGIN)
        self.test_dir.mkdir(exist_ok=True)
        self.script = script
        self.seen: list[tuple[list[str], dict[str, str] | None]] = []

    def sh(
        self, argv: list[str], env: dict[str, str] | None = None, quiet: bool = True
    ) -> subprocess.CompletedProcess[str]:
        del quiet
        self.seen.append((argv, env))
        return self.script(argv, env)


def done(code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, out, err)


def test_delta_the_throwaway_gpg_home_is_removed_when_a_control_returns_early(
    tmp_path: pathlib.Path,
) -> None:
    homes: list[str] = []

    def script(argv: list[str], env: dict[str, str] | None) -> subprocess.CompletedProcess[str]:
        if env and "GNUPGHOME" in env and env["GNUPGHOME"] not in homes:
            homes.append(env["GNUPGHOME"])
        if argv[:2] == ["gpg", "--list-keys"]:
            return done(out="pub:u:2048:1:KEYID1234:1::::::\n")
        if argv[0] == "gpg" and "--armor" in argv:
            return done(out="ARMOR\n")
        if (
            "build_pkg_repo" in " ".join(argv)
            and "--output" in argv
            and argv[argv.index("--output") + 1].endswith("repo-control")
        ):
            return done(0)  # the refused-key control FAILS: the repo build accepted the wrong key
        return done(0)

    suite = StubSuite(tmp_path, script)
    assert suite.p4_apt_metadata() is False
    assert homes, "a GNUPGHOME was handed to gpg"
    assert not pathlib.Path(homes[0]).exists(), "the key material is gone"
    # The retired twin's cleanup line sat after every early `return 1` of the signing block, so those paths skipped it.


def test_delta_gpg_failure_is_reported_where_it_happens(tmp_path: pathlib.Path) -> None:
    def script(argv: list[str], _env: dict[str, str] | None) -> subprocess.CompletedProcess[str]:
        if argv[:1] == ["gpg"] and "--quick-generate-key" in argv:
            return done(2, err="gpg: agent_genkey failed")
        return done(0)

    suite = StubSuite(tmp_path, script)
    assert suite.p4_apt_metadata() is False
    assert not any("build_pkg_repo" in " ".join(a) for a, _ in suite.seen), (
        "no repo build was attempted with no key"
    )
    # In the retired twin the same call ended in `2>/dev/null` with no `||`, inside a function that `run_test` called as an `if` condition, where `set -e` is off.


def test_delta_nginx_and_network_are_removed_when_the_flow_fails(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "t" / "repo-real" / "apt").mkdir(parents=True)
    calls: list[list[str]] = []

    def script(argv: list[str], _env: dict[str, str] | None) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[:3] == ["docker", "exec", argv[2]]:
            return done(1)  # nginx never answers
        return done(0)

    suite = StubSuite(tmp_path, script)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    assert suite.p5_apt_flow() is False
    verbs = [c[1] for c in calls if c[0] == "docker"]
    assert "stop" in verbs
    assert verbs[-1] == "network"
    assert calls[-1][2] == "rm"


def test_the_package_names_match_constants_sh() -> None:
    constants = (ts.ROOT / ".ci/config/constants.sh").read_text()
    assert f'readonly PKG_NAME="{port.PKG_NAME}"' in constants
    assert f'readonly PKG_BINARY_NAME="{port.PKG_BINARY_NAME}"' in constants


def test_a_missing_docker_is_a_clean_refusal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(port.shutil, "which", lambda name, **_kw: f"/x/{name}")

    def refuse(cmd: str, **_kw: object) -> str:
        raise port.common.RefusalError(f"Required command '{cmd}' is not available")

    monkeypatch.setattr(port.common, "require_cmd", refuse)
    assert port.main([]) == 1
    assert "Required command 'docker' is not available" in capsys.readouterr().err


def test_the_usage_line_runs_as_printed_from_the_repository_root() -> None:
    """Review finding 08928e86.2's sibling: the usage line is a command a reader runs from the repository root, so it must import there. Control first: the same command without its `PYTHONPATH=.ci` cannot find `rediacc_ci`."""
    root = pathlib.Path(__file__).resolve().parents[3]
    assigned, argv = usage_command(port.USAGE)
    assert assigned == {"PYTHONPATH": ".ci"}, port.USAGE
    argv = [sys.executable, *argv[1:], "--not-an-option"]
    bare = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    control = subprocess.run(argv, cwd=root, env=bare, capture_output=True, text=True, check=False)
    assert "No module named 'rediacc_ci'" in control.stderr, control.stderr
    proc = subprocess.run(
        argv, cwd=root, env={**bare, **assigned}, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 2, proc.stderr
    assert port.USAGE in proc.stderr.splitlines(), proc.stderr
