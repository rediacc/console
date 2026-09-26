"""`rediacc_ci.proxies.ensure_nfpm` against its bash twin `.ci/scripts/test/proxies/proxy-ensure-nfpm.sh` (gate `check:ci-proxy-ensure-nfpm`).

Sibling of `test_proxies_docker_prepull.py`; see that file for why the two invocations are compared byte for byte rather than as a finding set. This one needs a reachable `https://github.com`, because BOTH sides declare it as a requirement and would otherwise exit 77 (cannot-run, not a verdict) -- the test
would then assert 77 == 77 and prove nothing, so it is skipped instead, exactly
as a developer's offline run would be.

MOST CASES DOWNLOAD NOTHING. Only `test_real_tree_agrees_byte_for_byte` fetches the pinned tarball. The rest run against a fixture root whose SUBJECT is a stub that prints a directory holding a fake `nfpm`, which is what lets the version-comparison branch be driven at all: the real subject can only be made to report a wrong version by shipping a wrong binary.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-ensure-nfpm.observations.jsonl` (5 rows, 5
distinct trees, 5 distinct finding sets).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.proxies import ensure_nfpm
from rediacc_ci.tests import differential as diff

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/test/proxies/proxy-ensure-nfpm.sh"
PORT_MODULE = "rediacc_ci.proxies.ensure_nfpm"
TWIN = ROOT / TWIN_REL

# Every file either side needs inside a fixture root, all copied verbatim.
FIXTURE_FILES = (
    TWIN_REL,
    ".ci/scripts/test/proxies/proxy-lib.sh",
    ".devcontainer/toolchain.env",
    ".ci/config/constants.sh",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/proxyx.py",
    ".ci/rediacc_ci/proxies/__init__.py",
    ".ci/rediacc_ci/proxies/ensure_nfpm.py",
)

# A stub SUBJECT: prints a directory holding a fake nfpm, with no network. `%s` is what that fake nfpm answers to `--version`.
STUB_SUBJECT = """#!/usr/bin/env bash
# The real subject's SHAPE, minus the network: the early-exit on a warm cache,
# the arch refusal (which the proxy drives with a `uname` shim, so the stub has
# to honour it or that check cannot pass), the `fetching` line on stderr, and
# the cache directory on stdout.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
d="$root/.ci/cache/bin"
if [ -x "$d/nfpm" ]; then printf '%%s\\n' "$d"; exit 0; fi
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64 | amd64) ;;
    *)
        echo "ensure-nfpm: no pinned checksum for $ARCH in .ci/config/constants.sh -- add one rather than downloading unverified bytes" >&2
        exit 1
        ;;
esac
mkdir -p "$d"
printf '%%s\\n' '#!/bin/bash' "echo '%s'" >"$d/nfpm"
chmod +x "$d/nfpm"
echo "ensure-nfpm: fetching nfpm 2.45.0 for x86_64" >&2
printf '%%s\\n' "$d"
"""


def _github_reachable() -> bool:
    if shutil.which("curl") is None:
        return False
    return (
        subprocess.run(
            ["curl", "-sS", "-m", "10", "-o", "/dev/null", "https://github.com"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


pytestmark = pytest.mark.skipif(
    not _github_reachable(),
    reason="github unreachable; both sides would report 77, proving nothing",
)


def build_fixture(
    tmp_path: pathlib.Path, *, stub_version: str | None = None, port_source: str | None = None
) -> pathlib.Path:
    fixture = tmp_path / "fixture"
    for rel in FIXTURE_FILES:
        dst = fixture / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((ROOT / rel).read_bytes())
    (fixture / TWIN_REL).chmod(0o755)
    if port_source is not None:
        (fixture / ".ci/rediacc_ci/proxies/ensure_nfpm.py").write_text(
            port_source, encoding="utf-8"
        )
    shutil.copytree(ROOT / ".ci" / "scripts" / "lib", fixture / ".ci" / "scripts" / "lib")
    subject = fixture / ".ci" / "scripts" / "build" / "ensure-nfpm.sh"
    subject.parent.mkdir(parents=True, exist_ok=True)
    if stub_version is None:
        subject.write_bytes((ROOT / ".ci" / "scripts" / "build" / "ensure-nfpm.sh").read_bytes())
    else:
        subject.write_text(STUB_SUBJECT % stub_version, encoding="utf-8")
    subject.chmod(0o755)
    return fixture


def _env(fixture: pathlib.Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        # The per-run child TMPDIR, so the twin's leftover `mktemp` files land in a directory removed at exit (see differential._child_tmpdir).
        "TMPDIR": diff.BASE_ENV["TMPDIR"],
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(fixture / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_both(
    fixture: pathlib.Path, *args: str
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    env = _env(fixture)
    kwargs = {"env": env, "cwd": str(fixture), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(fixture / TWIN_REL), *args], timeout=300, check=False, **kwargs
    )
    # The subject caches into the FIXTURE root, so a second run would take the warm branch. Both sides must start from the same cold state.
    shutil.rmtree(fixture / ".ci" / "cache", ignore_errors=True)
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, *args], timeout=300, check=False, **kwargs
    )
    return old, new


def assert_same(
    old: subprocess.CompletedProcess[str], new: subprocess.CompletedProcess[str]
) -> None:
    assert new.returncode == old.returncode, "exit: twin %s, port %s (%r)" % (
        old.returncode,
        new.returncode,
        old.stderr,
    )
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr


# --------------------------------------------------------------------------- The real tree ---------------------------------------------------------------------------


def test_selftest_is_byte_identical() -> None:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        # The per-run child TMPDIR, so the twin's leftover `mktemp` files land in a directory removed at exit (see differential._child_tmpdir).
        "TMPDIR": diff.BASE_ENV["TMPDIR"],
        "LC_ALL": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    kwargs = {"env": env, "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN), "--selftest"], timeout=180, check=False, **kwargs
    )
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, "--selftest"], timeout=180, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "proxy-lib selftest: 4 case(s) passed" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


def test_real_tree_agrees_byte_for_byte() -> None:
    """The only case that fetches the pinned tarball, and it fetches it twice.

    Both sides build their own throwaway fixture root with a COLD cache, so neither can be satisfied by this checkout's warm `.ci/cache/bin/nfpm`.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        # The per-run child TMPDIR, so the twin's leftover `mktemp` files land in a directory removed at exit (see differential._child_tmpdir).
        "TMPDIR": diff.BASE_ENV["TMPDIR"],
        "LC_ALL": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    kwargs = {"env": env, "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN)], timeout=300, check=False, **kwargs
    )
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE], timeout=300, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "9 check(s) passed, 7 requirement(s) present" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


# --------------------------------------------------------------------------- The fixture cases, none of which touch the network ---------------------------------------------------------------------------


def test_a_stubbed_subject_at_the_pin_passes_every_check(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, stub_version="nfpm version 2.45.0")
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert "the installed nfpm reports 2.45.0, exactly the pin" in old.stdout
    assert_same(old, new)


def test_a_stubbed_subject_at_the_wrong_version_is_caught(tmp_path: pathlib.Path) -> None:
    """The drift check this whole gate exists for, driven for real."""
    fixture = build_fixture(tmp_path, stub_version="nfpm version 1.2.3")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "the installed nfpm reports '1.2.3' but the pin is '2.45.0'" in old.stderr
    assert_same(old, new)


def test_a_constants_sh_with_no_pin_refuses_before_comparing(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, stub_version="nfpm version 2.45.0")
    constants = fixture / ".ci" / "config" / "constants.sh"
    text, n = re.subn(r'readonly NFPM_VERSION="[^"]*"\n', "", constants.read_text(encoding="utf-8"))
    assert n == 1, "the NFPM_VERSION pin line moved in constants.sh"
    constants.write_text(text, encoding="utf-8")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "could not read NFPM_VERSION out of .ci/config/constants.sh" in old.stderr
    assert "or worse a false pass" in old.stderr
    assert_same(old, new)


# --------------------------------------------------------------------------- THE DEFECT: an errexit the twin never asked for, reproduced rather than fixed ---------------------------------------------------------------------------


def test_the_set_e_toggle_really_enables_errexit() -> None:
    """MEASURED, in this test, not asserted from reading.

    `proxy-ensure-nfpm.sh:33` is `set -uo pipefail` with no `-e`, and `:92-95` wraps the first subject run in `set +e` / `set -e`. `set -e` TURNS ERREXIT ON; it does not restore the previous state.
    """
    flags = subprocess.run(
        ["bash", "-c", 'set -uo pipefail; printf "%s|" "$-"; set +e; :; set -e; printf "%s" "$-"'],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    ).stdout
    before, after = flags.split("|")
    assert "e" not in before, before
    assert "e" in after, after

    # And the consequence, on the exact pipeline shape `:113` uses.
    with_toggle = subprocess.run(
        [
            "bash",
            "-c",
            (
                "set -uo pipefail; set +e; :; set -e; "
                'X="$(echo hi | grep -oE "[0-9]+" | head -1)"; echo REACHED'
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert with_toggle.returncode == 1
    assert with_toggle.stdout == "", "the script died at the assignment, printing nothing"

    without = subprocess.run(
        [
            "bash",
            "-c",
            'set -uo pipefail; X="$(echo hi | grep -oE "[0-9]+" | head -1)"; echo REACHED',
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert without.returncode == 0
    assert without.stdout == "REACHED\n"


def test_the_twin_still_carries_the_toggle_and_the_ungated_pipeline() -> None:
    text = TWIN.read_text(encoding="utf-8")
    assert "\nset -uo pipefail\n" in text
    assert "\nset -e\n" not in text.split("set -uo pipefail")[0]
    assert text.count("\nset +e\n") == 3
    assert text.count("\nset -e\n") == 3
    assert 'GOT_VERSION="$("$PRINTED_DIR/nfpm" --version 2>&1 | grep -oE' in text


def test_a_version_with_no_semver_token_kills_both_sides(tmp_path: pathlib.Path) -> None:
    """`:113` under the acquired errexit: exit 1, four PASS lines, no FAIL line.

    That is indistinguishable from the gate crashing, which is why it is a defect and not a quirk. Fixing it changes what a registered gate prints, so both sides reproduce it and this test pins the shape.
    """
    fixture = build_fixture(tmp_path, stub_version="nfpm banana")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stdout.count("PASS:") == 4
    assert "FAIL:" not in old.stdout
    assert "FAIL:" not in old.stderr
    assert "check(s) FAILED" not in old.stderr, "no verdict line at all"
    assert_same(old, new)


def test_a_planted_soft_version_read_is_caught(tmp_path: pathlib.Path) -> None:
    """Plant the obvious "fix": return "" instead of aborting.

    It is the RIGHT behaviour and the WRONG port. If this ever passes, the case above has stopped comparing anything.

    The real file is compared before and after; the mutation lives in the fixture copy only.
    """
    port = ROOT / ".ci" / "rediacc_ci" / "proxies" / "ensure_nfpm.py"
    before = port.read_bytes()
    source = port.read_text(encoding="utf-8")
    anchor = "    if not version:\n        raise SystemExit(1)\n"
    assert source.count(anchor) == 1
    planted = source.replace(anchor, "", 1)
    fixture = build_fixture(tmp_path, stub_version="nfpm banana", port_source=planted)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stdout.count("PASS:") == 4, "the twin still aborts at the fourth check"
    # The plant survives past `:113` and keeps going, so it reaches checks the twin never gets to. Named precisely rather than "something differs".
    assert new.stdout.count("PASS:") > 4, "the plant did not fire; this control proves nothing"
    assert "the installed nfpm reports ''" in new.stderr
    assert "the installed nfpm reports ''" not in old.stderr
    assert port.read_bytes() == before, "the real port file moved"


# --------------------------------------------------------------------------- Pure helpers ---------------------------------------------------------------------------


def test_clean_path_drops_every_entry_holding_nfpm(tmp_path: pathlib.Path) -> None:
    home = tmp_path / "hasnfpm"
    home.mkdir()
    (home / "nfpm").write_text("#!/bin/bash\n", encoding="utf-8")
    (home / "nfpm").chmod(0o755)
    other = tmp_path / "plain"
    other.mkdir()
    path = "%s:%s:%s" % (home, other, home)
    assert ensure_nfpm.clean_path(path) == str(other)
    assert ensure_nfpm.clean_path(str(other)) == str(other)


def test_semver_of_takes_the_first_match_like_grep_o_head_1() -> None:
    assert ensure_nfpm.semver_of("nfpm version 2.45.0 (built 1.2.3)") == "2.45.0"
    assert ensure_nfpm.semver_of("nfpm banana") == ""
    assert ensure_nfpm.semver_of("") == ""
    assert ensure_nfpm.semver_of("v10.20.30") == "10.20.30"


def test_read_pin_returns_the_real_pin_and_swallows_the_sources_streams() -> None:
    pin = ensure_nfpm.read_pin(ROOT / ".ci" / "config" / "constants.sh")
    assert re.fullmatch(r"\d+\.\d+\.\d+", pin), pin
    assert 'readonly NFPM_VERSION="%s"' % pin in (
        ROOT / ".ci" / "config" / "constants.sh"
    ).read_text(encoding="utf-8")
    assert ensure_nfpm.read_pin(ROOT / "does" / "not" / "exist.sh") == ""
