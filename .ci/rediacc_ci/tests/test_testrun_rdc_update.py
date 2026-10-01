"""`rediacc_ci.testrun.rdc_update` against its bash twin `.ci/scripts/test/test-rdc-update.sh`.

The subject under test of the twin is a real SEA `rdc` binary, which the live run in the porting report uses. Here `RDC_BINARY` is a small FAKE `rdc` (a shell script that fetches the fixture manifest with curl, verifies the sha256, swaps `rdc` with `rdc.old`, rolls back and records the channel), so both runners drive the REAL `install.sh` against their fixture server and the comparison covers every scenario's assertions without a 500 MB binary. Compared: exit code, the PASS/FAIL lines on stdout and the FAIL lines on stderr (temporary paths masked).

INTENTIONAL DELTAS (Rule T), each a `test_delta_*` that fails on the bash behaviour: a failing prerequisite leaks the fixture server and temporary tree; `sha256-mismatch` and `rollback-empty` accept a failure for the wrong reason; an unknown scenario name only exits 2 after earlier scenarios ran.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import signal
import subprocess

import pytest

from rediacc_ci.testrun import rdc_update
from rediacc_ci.tests import testrun_support as ts

TWIN = ".ci/scripts/test/test-rdc-update.sh"
MODULE = "rediacc_ci.testrun.rdc_update"

FAKE_RDC = r"""#!/bin/bash
# A fake rdc: just enough of `update` for test-rdc-update's seven scenarios.
bindir="$HOME/.local/share/rediacc/bin"
case "$1" in
  --version) echo "1.0.3"; exit 0 ;;
esac
[[ "$1" == "update" ]] || exit 0
shift
channel=edge
force=0; rollback=0; check=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) force=1 ;;
    --rollback) rollback=1 ;;
    --check-only) check=1 ;;
    --channel) channel="$2"; shift ;;
  esac
  shift
done
if (( rollback )); then
  if [[ ! -f "$bindir/rdc.old" ]]; then
    echo "No previous version found. Rollback is only available after an update." >&2
    exit 1
  fi
  mv "$bindir/rdc.old" "$bindir/rdc"
  exit 0
fi
if [[ "${FAKE_UPDATE_MODE:-}" == unreachable ]]; then echo "connect ECONNREFUSED" >&2; exit 1; fi
if (( check )); then
  mkdir -p "$HOME/.config/rediacc"
  printf '{"account":{"updateChannel":"%s"}}\n' "$channel" > "$HOME/.config/rediacc/rediacc.json"
  exit 0
fi
manifest="$(curl -fsS "$REDIACC_RELEASES_URL/cli/edge/manifest.json")" || { echo "manifest fetch failed" >&2; exit 1; }
url="$(sed -n 's/.*"url": "\(.*\)",/\1/p' <<<"$manifest" | head -1)"
want="$(sed -n 's/.*"sha256": "\(.*\)",/\1/p' <<<"$manifest" | head -1)"
tmp="$(mktemp)"
curl -fsS "$url" -o "$tmp" || { echo "download failed" >&2; exit 1; }
have="$(sha256sum "$tmp" | awk '{print $1}')"
if [[ "$have" != "$want" ]]; then
  echo "Downloaded binary failed checksum verification." >&2
  rm -f "$tmp"
  exit 1
fi
cp "$bindir/rdc" "$bindir/rdc.old"
cp "$tmp" "$bindir/rdc"
chmod +x "$bindir/rdc"
rm -f "$tmp"
echo "Updated"
"""


@pytest.fixture(scope="module")
def fake_rdc(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    path = tmp_path_factory.mktemp("fakerdc") / "rdc"
    path.write_text(FAKE_RDC)
    path.chmod(0o755)
    return path


def drive(
    tmp_path: pathlib.Path,
    name: str,
    args: list[str],
    rdc: pathlib.Path | str,
    extra: dict[str, str] | None = None,
) -> ts.Outcome:
    directory = tmp_path / name
    directory.mkdir()
    env = {"RDC_BINARY": str(rdc), "CI": "", "GITHUB_ACTIONS": "", **(extra or {})}
    runner = ts.bash_cmd(TWIN, *args) if name.startswith("bash") else ts.py_cmd(MODULE, *args)
    if not name.startswith("bash"):
        env = ts.py_env(env)
    return ts.run_side(runner, directory, (), env, timeout=240)


def norm(text: str, directory: pathlib.Path) -> str:
    text = ts.mask(text, directory)
    text = re.sub(r"/tmp/[A-Za-z0-9._-]+", "<TMP>", text)
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def pass_fail_lines(outcome: ts.Outcome) -> list[str]:
    plain = ANSI.sub("", outcome.out)
    return [ln for ln in plain.splitlines() if ln.startswith(("PASS:", "ALL SCENARIOS", "FAILED:"))]


def same(old: ts.Outcome, new: ts.Outcome) -> None:
    assert (new.code, pass_fail_lines(new)) == (old.code, pass_fail_lines(old))


def test_all_scenarios_pass_with_the_fake_rdc(
    tmp_path: pathlib.Path, fake_rdc: pathlib.Path
) -> None:
    old = drive(tmp_path, "bash", ["all"], fake_rdc)
    new = drive(tmp_path, "py", ["all"], fake_rdc)
    assert old.code == 0, old.err
    assert len(pass_fail_lines(old)) == 8
    same(old, new)


@pytest.mark.parametrize(
    "scenario",
    [
        "happy",
        "check-only",
        "sha256-mismatch",
        "rollback",
        "rollback-empty",
        "channel-switch",
        "reinstall",
    ],
)
def test_each_scenario_matches_the_twin(
    tmp_path: pathlib.Path, fake_rdc: pathlib.Path, scenario: str
) -> None:
    old = drive(tmp_path, "bash", [scenario], fake_rdc)
    new = drive(tmp_path, "py", [scenario], fake_rdc)
    assert old.code == 0, old.err
    same(old, new)


def test_a_broken_updater_fails_the_same_scenarios(tmp_path: pathlib.Path) -> None:
    """A rdc that does nothing: the swap scenarios fail on both sides, and the same ones."""
    inert = tmp_path / "inert"
    inert.write_text('#!/bin/bash\n[[ "$1" == --version ]] && echo 1.0.3\nexit 0\n')
    inert.chmod(0o755)
    old = drive(tmp_path, "bash", ["happy", "rollback", "check-only"], inert)
    new = drive(tmp_path, "py", ["happy", "rollback", "check-only"], inert)
    assert old.code == 1
    assert old.err.count("FAIL:") >= 2
    assert (new.code, ANSI.sub("", new.out).count("PASS:")) == (
        old.code,
        ANSI.sub("", old.out).count("PASS:"),
    )
    old_failed = FAILED_LINE.search(ANSI.sub("", old.err))
    new_failed = FAILED_LINE.search(ANSI.sub("", new.err))
    assert old_failed
    assert new_failed
    assert old_failed.group(0) == new_failed.group(0)


FAILED_LINE = re.compile(r"FAILED: .*")


def test_usage_errors_match_the_twin(tmp_path: pathlib.Path) -> None:
    old = drive(tmp_path, "bash", [], "")
    new = drive(tmp_path, "py", [], "")
    assert (old.code, new.code) == (2, 2)
    assert "RDC_BINARY env var must point to an rdc executable" in old.err
    assert "RDC_BINARY env var must point to an rdc executable" in new.err
    old = drive(tmp_path, "bash2", ["happy"], "/nonexistent/rdc")
    new = drive(tmp_path, "py2", ["happy"], "/nonexistent/rdc")
    assert (old.code, new.code) == (2, 2)
    assert "is not executable" in old.err
    assert "is not executable" in new.err


# ---- intentional deltas ----------------------------------------------------------------------------------------------------


def http_servers_under(directory: pathlib.Path) -> list[int]:
    found = []
    for entry in pathlib.Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmd = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode()
            cwd = os.readlink(entry / "cwd")
        except OSError:
            continue
        if "http.server" in cmd and str(directory) in cwd:
            found.append(int(entry.name))
    return found


def test_delta_a_failing_prerequisite_leaks_nothing(
    tmp_path: pathlib.Path, fake_rdc: pathlib.Path
) -> None:
    """No curl on PATH: the twin's readiness poll fails, `set -e` ends it past `stop_fixture`, and the fixture server and temp tree stay behind."""
    leaked: list[int] = []
    try:
        directory = tmp_path / "bash"
        directory.mkdir()
        bindir = ts.make_fakes(directory, ())
        for tool in (
            "bash",
            "python3",
            "mktemp",
            "rm",
            "mkdir",
            "cp",
            "sha256sum",
            "awk",
            "stat",
            "uname",
            "ldd",
            "dirname",
            "basename",
            "env",
            "sed",
            "grep",
            "cat",
            "chmod",
            "ln",
            "mv",
            "head",
            "tr",
            "id",
            "sleep",
            "kill",
            "wait",
        ):
            found = ts.shutil.which(tool)
            if found and not (bindir / tool).exists():
                (bindir / tool).symlink_to(found)
        tmp_old = directory / "tmp"
        tmp_old.mkdir()
        env = {
            "PATH": str(bindir),
            "HOME": str(directory),
            "TMPDIR": str(tmp_old),
            "RDC_BINARY": str(fake_rdc),
            "LC_ALL": "C",
        }
        old = subprocess.run(
            [ts.BASH, str(ts.ROOT / TWIN), "happy"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=str(directory),
        )
        assert old.returncode != 0
        leaked = http_servers_under(tmp_old)
        assert leaked, "the twin left its fixture server running"
        assert any(tmp_old.iterdir()), "the twin left its temporary tree"

        directory2 = tmp_path / "py"
        directory2.mkdir()
        tmp_new = directory2 / "tmp"
        tmp_new.mkdir()
        env2 = {
            **env,
            "HOME": str(directory2),
            "TMPDIR": str(tmp_new),
            "PYTHONPATH": str(ts.ROOT / ".ci"),
            "PATH": str(bindir),
        }
        new = subprocess.run(
            [ts.sys.executable, "-m", MODULE, "happy"],
            env=env2,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=str(directory2),
        )
        assert new.returncode == 1
        assert "FAIL:" in new.stderr
        assert "install.sh exited" in new.stderr
        assert not http_servers_under(tmp_new)
        assert not any(tmp_new.iterdir()), "the port removed its temporary tree"
    finally:
        for pid in leaked:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)


def test_delta_sha_mismatch_must_fail_for_the_checksum(tmp_path: pathlib.Path) -> None:
    """An updater that fails for ANY other reason (server unreachable) passed the twin's scenario."""
    unreachable = tmp_path / "rdc-unreachable"
    unreachable.write_text(
        FAKE_RDC.replace('if [[ "${FAKE_UPDATE_MODE:-}" == unreachable ]]', "if true")
    )
    unreachable.chmod(0o755)
    old = drive(tmp_path, "bash", ["sha256-mismatch"], unreachable)
    new = drive(tmp_path, "py", ["sha256-mismatch"], unreachable)
    assert old.code == 0, "bash accepted a connection error as 'sha mismatch aborts update'"
    assert new.code == 1
    assert "update failed, but not for the checksum" in new.err


def test_delta_rollback_empty_must_fail_for_the_missing_backup(tmp_path: pathlib.Path) -> None:
    other = tmp_path / "rdc-other"
    other.write_text(
        '#!/bin/bash\n[[ "$1" == --version ]] && { echo 1.0.3; exit 0; }\necho "boom" >&2\nexit 1\n'
    )
    other.chmod(0o755)
    old = drive(tmp_path, "bash", ["rollback-empty"], other)
    new = drive(tmp_path, "py", ["rollback-empty"], other)
    assert old.code == 0, "bash accepted any failure as a refused rollback"
    assert new.code == 1
    assert "rollback failed, but not for a missing backup" in new.err


def test_delta_unknown_scenario_is_refused_before_any_runs(
    tmp_path: pathlib.Path, fake_rdc: pathlib.Path
) -> None:
    old = drive(tmp_path, "bash", ["check-only", "bogus"], fake_rdc)
    new = drive(tmp_path, "py", ["check-only", "bogus"], fake_rdc)
    assert (old.code, new.code) == (2, 2)
    assert "PASS:" in ANSI.sub("", old.out), "bash ran check-only before it noticed the bad name"
    assert "PASS:" not in new.out
    assert "unknown scenario: bogus" in new.err


def test_the_fixture_serves_the_tree_shape_install_sh_expects(
    tmp_path: pathlib.Path, fake_rdc: pathlib.Path
) -> None:
    fixture = rdc_update.Fixture(tmp_path / "fx")
    try:
        fixture.prep("stable", "1.0.3", "linux-x64", "rdc-linux-x64", fake_rdc)
        assert (tmp_path / "fx/cli/stable/manifest.json").is_file()
        assert (tmp_path / "fx/cli/v1.0.3/rdc-linux-x64.sha256").is_file()
        manifest = json.loads((tmp_path / "fx/cli/stable/manifest.json").read_text())
        assert manifest["binaries"]["linux-x64"]["url"] == f"{fixture.url}/cli/v1.0.3/rdc-linux-x64"
        assert manifest["binaries"]["linux-x64"]["size"] == fake_rdc.stat().st_size
        fixture.prep("pr-9", "1.0.3", "linux-x64", "rdc-linux-x64", fake_rdc, override_sha="f" * 64)
        manifest = json.loads((tmp_path / "fx/cli/pr-9/manifest.json").read_text())
        assert manifest["binaries"]["linux-x64"]["url"] == f"{fixture.url}/cli/pr-9/rdc-linux-x64"
        assert manifest["binaries"]["linux-x64"]["sha256"] == "f" * 64
    finally:
        fixture.stop()
