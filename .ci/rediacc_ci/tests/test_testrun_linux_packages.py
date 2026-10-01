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
from rediacc_ci.tests import testrun_support as ts
from rediacc_ci.well_known import RELEASES_ORIGIN

TWIN_REL = ".ci/scripts/test/test-linux-packages.sh"
TWIN = ts.ROOT / TWIN_REL
MODULE = "rediacc_ci.testrun.linux_packages"
TWIN_TEXT = TWIN.read_text()


def bash_function(name: str) -> str:
    start = TWIN_TEXT.index(f"{name}() {{")
    return TWIN_TEXT[start : TWIN_TEXT.index("\n}\n", start) + 3]


def bash(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [ts.BASH, "-c", script, "x", *args],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )


@pytest.mark.parametrize("version", ["99.0.0", "v1.2.3", "10.20.30", "1.2.3-rc.1"])
def test_version_token_re_matches_the_twin(version: str) -> None:
    done = bash(f'{bash_function("version_token_re")}\nversion_token_re "$1"', version)
    assert port.version_token_re(version) == done.stdout


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Package: x\nVersion: 99.0.0\n", "Version"),
        (" Version : 99.0.0\n", "Version"),
        ("Version: 99.0.01\n", "Version"),
        ("Version: 199.0.0\n", "Version"),
        ("Name: x\n", "Version"),
        ("Version: 99.0.0\nVersion: 1\n", "Version"),
    ],
)
def test_assert_version_field_matches_the_twin(text: str, label: str) -> None:
    script = f'source "{ts.ROOT}/.ci/scripts/lib/common.sh"\nTEST_VERSION=99.0.0\n{bash_function("assert_version_field")}\nassert_version_field "$1" "$2"'
    assert port.assert_version_field(text, label) == (bash(script, text, label).returncode == 0)


ARMOR = "-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nAAAA\nBBBB\nCCCC\nDDDD\nEEEE\nFFFF\nGGGG\n=chk\n-----END PGP PRIVATE KEY BLOCK-----"


def test_weld_armor_matches_the_twins_awk_program() -> None:
    awk = re.search(r"awk '\n(.*?)'\)", TWIN_TEXT, re.DOTALL)
    assert awk
    done = subprocess.run(
        ["awk", awk.group(1)], input=ARMOR + "\n", capture_output=True, text=True, check=False
    )
    assert port.weld_armor(ARMOR) == done.stdout
    assert "DDDDEEEE" in done.stdout


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
    old = subprocess.run(
        [ts.BASH, str(TWIN), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
        stdin=subprocess.DEVNULL,
    )
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
    assert (new.returncode, mask_paths(new.stdout), mask_paths(new.stderr)) == (
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
    # The twin reads exactly one thing, the first argument, and has no refusal arm: `--dry-runn` or `x --dry-run` silently run the full Docker suite.
    assert '[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true' in TWIN_TEXT
    assert "Unknown" not in TWIN_TEXT


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
    # The twin's cleanup line sits after every early `return 1` of the signing block, so those paths skipped it.
    block = TWIN_TEXT[TWIN_TEXT.index("phase4_validate_apt_metadata() {") :]
    first_return = block.index("return 1", block.index("CONTROL FAILED"))
    cleanup = block.index('rm -rf "$gnupg_tmp"')
    assert first_return < cleanup


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
    # In the twin the same call ends in `2>/dev/null` with no `||`, inside a function that `run_test` calls as an `if` condition, where `set -e` is off.
    assert re.search(r"--quick-generate-key[^\n]*2>/dev/null\n", TWIN_TEXT)


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
