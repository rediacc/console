"""Differential: `rediacc_ci.build.ensure_nfpm` against its twin
`.ci/scripts/build/ensure-nfpm.sh`.

HOW THE TWO SIDES ARE POINTED AT A FIXTURE. Neither side takes a root override:
the twin resolves `REPO_ROOT` from `${BASH_SOURCE[0]}` and the port from
`__file__` (deliberately NOT `paths.repo_root()`, see the port's docstring), so BOTH are copied into the fixture root and run from there. That is also what the registered gate `.ci/scripts/test/proxies/proxy-ensure-nfpm.sh:13-21` does, and
for the same reason it states: run in this checkout and the warm
`.ci/cache/bin/nfpm` takes the early-exit branch, so the download and the checksum are never reached and the green proves only that a file existed.

NOTHING IS NORMALIZED. Neither side emits a timestamp, a pid or a tempdir path: `curl -sfL` is silent, `sha256sum`'s `<file>: FAILED` line goes to the stdout the twin redirects to /dev/null, and the fixture's own absolute path appears identically on both sides. Byte comparison, both streams, separately.

THE NETWORK IS NEVER TOUCHED, including by the real-tree case. `curl` is shimmed on PATH in every case here; the shim serves a locally built tarball or refuses. A test that downloads 4 MB from github is a test that fails on a plane.

K=5 LEDGER: `.ci/shadow/w7p6-ensure-nfpm.observations.jsonl` (5 rows, 5 distinct
trees, 5 distinct finding sets).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import typing

from rediacc_ci import paths
from rediacc_ci.build import ensure_nfpm

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "build" / "ensure-nfpm.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "build" / "ensure_nfpm.py"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
TOOLCHAIN_ENV = ROOT / ".devcontainer" / "toolchain.env"

TWIN_REL = ".ci/scripts/build/ensure-nfpm.sh"
PORT_REL = ".ci/rediacc_ci/build/ensure_nfpm.py"

SHA_LINE_RE = re.compile(r'readonly NFPM_SHA256_LINUX_X86_64="[0-9a-f]+"')

# A curl shim that refuses, for the cases that must never reach the network.
CURL_REFUSE = "#!/bin/bash\nexit 22\n"

# A curl shim that serves a local file into whatever `-o` names.
CURL_SERVE = """#!/bin/bash
dest=""
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-o" ]]; then dest="$2"; shift 2; continue; fi
    shift
done
cp "$FIXTURE_PAYLOAD" "$dest"
"""

# A uname shim answering a fixed machine for `-m` and delegating otherwise. The delegation matters: `bash` itself never calls uname here, but a shim that answered every question would be a different program.
UNAME_SHIM = """#!/bin/bash
for a in "$@"; do [[ "$a" == "-m" ]] && { echo %s; exit 0; }; done
exec /usr/bin/uname "$@"
"""


def _make_payload(dest: pathlib.Path, version_text: str) -> str:
    """A real gzip tarball holding one executable `nfpm`. Returns its sha256."""
    stage = dest.parent / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    binary = stage / "nfpm"
    binary.write_text("#!/bin/bash\necho 'nfpm version %s'\n" % version_text, encoding="utf-8")
    binary.chmod(0o755)
    with tarfile.open(dest, "w:gz") as tf:
        tf.add(str(binary), arcname="nfpm")
    shutil.rmtree(stage)
    return hashlib.sha256(dest.read_bytes()).hexdigest()


def build_fixture(
    tmp_path: pathlib.Path,
    *,
    pinned_sha: str | None = None,
    warm_version: str | None = None,
    on_path_version: str | None = None,
    arch: str | None = None,
    curl: str = CURL_REFUSE,
    drop_toolchain_env: bool = False,
    drop_version_pin: bool = False,
    port_source: str | None = None,
) -> pathlib.Path:
    fixture = tmp_path / "fixture"
    (fixture / ".ci" / "scripts" / "build").mkdir(parents=True, exist_ok=True)
    (fixture / ".ci" / "rediacc_ci" / "build").mkdir(parents=True, exist_ok=True)
    (fixture / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (fixture / ".devcontainer").mkdir(parents=True, exist_ok=True)
    (fixture / "bin").mkdir(parents=True, exist_ok=True)

    shutil.copy2(TWIN, fixture / TWIN_REL)
    if port_source is None:
        shutil.copy2(PORT, fixture / PORT_REL)
    else:
        (fixture / PORT_REL).write_text(port_source, encoding="utf-8")
    if not drop_toolchain_env:
        shutil.copy2(TOOLCHAIN_ENV, fixture / ".devcontainer" / "toolchain.env")

    constants = CONSTANTS.read_text(encoding="utf-8")
    if pinned_sha is not None:
        constants, n = SHA_LINE_RE.subn(
            'readonly NFPM_SHA256_LINUX_X86_64="%s"' % pinned_sha, constants
        )
        assert n == 1, "the sha pin line moved in constants.sh; this fixture is stale"
    if drop_version_pin:
        before = constants
        constants = re.sub(r'readonly NFPM_VERSION="[^"]*"\n', "", constants)
        assert constants != before, "the NFPM_VERSION pin line moved in constants.sh"
    (fixture / ".ci" / "config" / "constants.sh").write_text(constants, encoding="utf-8")

    (fixture / "bin" / "curl").write_text(curl, encoding="utf-8")
    (fixture / "bin" / "curl").chmod(0o755)
    if arch is not None:
        (fixture / "bin" / "uname").write_text(UNAME_SHIM % arch, encoding="utf-8")
        (fixture / "bin" / "uname").chmod(0o755)
    if on_path_version is not None:
        elsewhere = fixture / "elsewhere"
        elsewhere.mkdir(parents=True, exist_ok=True)
        (elsewhere / "nfpm").write_text(
            "#!/bin/bash\necho 'nfpm version %s'\n" % on_path_version, encoding="utf-8"
        )
        (elsewhere / "nfpm").chmod(0o755)
    if warm_version is not None:
        cache = fixture / ".ci" / "cache" / "bin"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "nfpm").write_text(
            "#!/bin/bash\necho 'nfpm version %s'\n" % warm_version, encoding="utf-8"
        )
        (cache / "nfpm").chmod(0o755)
    return fixture


def _env(fixture: pathlib.Path) -> dict[str, str]:
    path = [str(fixture / "bin")]
    if (fixture / "elsewhere").is_dir():
        path.append(str(fixture / "elsewhere"))
    path.append(os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"))
    return {
        "PATH": os.pathsep.join(path),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "FIXTURE_PAYLOAD": str(fixture / "payload.tar.gz"),
    }


def _run(argv: list[str], fixture: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        env=_env(fixture),
        cwd=str(fixture),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def run_both(
    fixture: pathlib.Path,
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    """The two sides, each from the SAME starting state.

    The cache is snapshotted and restored between them, and that is not housekeeping: the twin runs first and a successful cold-cache run LEAVES a binary behind, so without the reset the port would take the warm-cache branch and "agree" by printing the same directory for a completely different reason. Caught by this file's own first run, which reported an empty stderr against the
    twin's `fetching` line.
    """
    cache = fixture / ".ci" / "cache"
    snapshot = fixture / ".cache-snapshot"
    if snapshot.exists():
        shutil.rmtree(snapshot)
    if cache.exists():
        shutil.copytree(cache, snapshot, symlinks=True)
    old = _run(["bash", str(fixture / TWIN_REL)], fixture)
    if cache.exists():
        shutil.rmtree(cache)
    if snapshot.exists():
        shutil.copytree(snapshot, cache, symlinks=True)
    new = _run(["python3", str(fixture / PORT_REL)], fixture)
    return old, new


def assert_same(
    old: subprocess.CompletedProcess[str], new: subprocess.CompletedProcess[str]
) -> None:
    assert new.returncode == old.returncode, "exit: twin %s, port %s (twin stderr %r)" % (
        old.returncode,
        new.returncode,
        old.stderr,
    )
    assert new.stdout == old.stdout, (old.stdout, new.stdout)
    assert new.stderr == old.stderr, (old.stderr, new.stderr)


# --------------------------------------------------------------------------- The real tree ---------------------------------------------------------------------------


def test_real_tree_agrees_byte_for_byte(tmp_path: pathlib.Path) -> None:
    """Both sides in THIS checkout, with a refusing `curl` so nothing downloads.

    Whether the cache here is warm (both print the cache directory, exit 0) or cold (both print the `fetching` line and exit 22 out of the shim), the two sides must agree, and this is the only case that runs against the real `.ci/config/constants.sh` in its real location.
    """
    shim = tmp_path / "bin"
    shim.mkdir(parents=True, exist_ok=True)
    (shim / "curl").write_text(CURL_REFUSE, encoding="utf-8")
    (shim / "curl").chmod(0o755)
    env = {
        "PATH": os.pathsep.join([str(shim), os.environ.get("PATH", "")]),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    kwargs = {"env": env, "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN)], timeout=120, check=False, **kwargs
    )
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", str(PORT)], timeout=120, check=False, **kwargs
    )
    assert new.returncode == old.returncode
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr
    assert old.returncode in (0, 22)


# --------------------------------------------------------------------------- The three cold-cache paths ---------------------------------------------------------------------------


def test_cold_cache_downloads_verifies_and_prints_the_cache_dir(
    tmp_path: pathlib.Path,
) -> None:
    fixture = build_fixture(tmp_path, curl=CURL_SERVE)
    sha = _make_payload(fixture / "payload.tar.gz", "9.9.9")
    fixture_constants = fixture / ".ci" / "config" / "constants.sh"
    fixture_constants.write_text(
        SHA_LINE_RE.sub(
            'readonly NFPM_SHA256_LINUX_X86_64="%s"' % sha,
            fixture_constants.read_text(encoding="utf-8"),
        ),
        encoding="utf-8",
    )
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert old.stdout == "%s\n" % (fixture / ".ci" / "cache" / "bin")
    assert old.stderr == "ensure-nfpm: fetching nfpm 2.45.0 for x86_64\n"
    assert_same(old, new)
    # The port really extracted, not merely reported.
    assert os.access(str(fixture / ".ci" / "cache" / "bin" / "nfpm"), os.X_OK)


def test_a_failing_curl_exits_with_curls_own_status(tmp_path: pathlib.Path) -> None:
    """`set -e` on `curl -sfL` (:67): the script's exit status is curl's 22, and
    the only output is the `fetching` line already on stderr. A port that
    normalised this to 1 would be indistinguishable from a checksum failure."""
    fixture = build_fixture(tmp_path, curl=CURL_REFUSE)
    old, new = run_both(fixture)
    assert old.returncode == 22
    assert old.stdout == ""
    assert old.stderr == "ensure-nfpm: fetching nfpm 2.45.0 for x86_64\n"
    assert_same(old, new)
    assert not (fixture / ".ci" / "cache").exists(), "the cache dir is created only after the sum"


def test_a_checksum_mismatch_aborts_before_extracting(tmp_path: pathlib.Path) -> None:
    """The verification is `sha256sum -c`, and its stderr is the whole diagnostic.

    `<file>: FAILED` goes to the stdout the twin sends to /dev/null (:70), so the only visible line is coreutils' own WARNING. That is why the port calls `sha256sum` rather than `hashlib`: the sentence is not this repo's to write.
    """
    fixture = build_fixture(tmp_path, curl=CURL_SERVE, pinned_sha="0" * 64)
    _make_payload(fixture / "payload.tar.gz", "9.9.9")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stdout == ""
    assert "sha256sum: WARNING: 1 computed checksum did NOT match" in old.stderr
    assert_same(old, new)
    assert not (fixture / ".ci" / "cache").exists()


# --------------------------------------------------------------------------- The refusal, driven through a PATH shim exactly as the registered gate does ---------------------------------------------------------------------------


def test_an_unpinned_architecture_is_refused_through_a_path_shim(
    tmp_path: pathlib.Path,
) -> None:
    """This is the case that forces `uname -m` over `os.uname()` in the port.

    `proxy-ensure-nfpm.sh:149-158` drives the refusal with a `uname` shim on PATH. A port reading the raw syscall would ignore the shim, take the x86_64 arm, and try to download under the gate's own refusal case.
    """
    fixture = build_fixture(tmp_path, arch="riscv64")
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stdout == ""
    assert old.stderr == (
        "ensure-nfpm: no pinned checksum for riscv64 in .ci/config/constants.sh -- "
        "add one rather than downloading unverified bytes\n"
    )
    assert_same(old, new)


def test_the_port_reads_uname_through_path_not_the_syscall() -> None:
    """The claim above, made against the two real files rather than a fixture."""
    assert '"$(uname -m)"' in TWIN.read_text(encoding="utf-8")
    source = PORT.read_text(encoding="utf-8")
    assert '["uname", "-m"]' in source
    assert "os.uname()" not in source.split('"""')[2], "the code, not the docstring"


# --------------------------------------------------------------------------- The two defects, pinned rather than fixed ---------------------------------------------------------------------------


def test_defect_1_a_warm_cache_is_never_checked_against_the_pin(
    tmp_path: pathlib.Path,
) -> None:
    """`ensure-nfpm.sh:42-45` asks the cached binary only whether it ANSWERS.

    So a `.ci/cache/bin/nfpm` left from an older pin survives a bump in `constants.sh` forever, and this measures it: the pin says 2.45.0, the cache says 1.0.0-stale, and both sides exit 0 handing out the stale directory without a single network call. Fixing this is outside the port's ownership (it would change what two workflows and a registered gate do), so it is reproduced and
    pinned here.
    """
    fixture = build_fixture(tmp_path, warm_version="1.0.0-stale", curl=CURL_REFUSE)
    old, new = run_both(fixture)
    assert old.returncode == 0
    assert old.stdout == "%s\n" % (fixture / ".ci" / "cache" / "bin")
    assert old.stderr == ""
    assert_same(old, new)
    stale = subprocess.run(
        [str(fixture / ".ci" / "cache" / "bin" / "nfpm"), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "1.0.0-stale" in stale.stdout
    assert 'readonly NFPM_VERSION="2.45.0"' in CONSTANTS.read_text(encoding="utf-8")


def test_defect_2_any_nfpm_on_path_wins_over_the_pin(tmp_path: pathlib.Path) -> None:
    """`ensure-nfpm.sh:38-41`, one rung earlier and with a wider door.

    The registered gate strips nfpm from PATH before its own run (`proxy-ensure-nfpm.sh:81-87`), which acknowledges the branch rather than checking it.
    """
    fixture = build_fixture(tmp_path, on_path_version="0.1.0-wrong", curl=CURL_REFUSE)
    old, new = run_both(fixture)
    assert old.returncode == 0
    assert old.stdout == "%s\n" % (fixture / "elsewhere")
    assert old.stderr == ""
    assert_same(old, new)


# --------------------------------------------------------------------------- The two ways the pin read itself can fail ---------------------------------------------------------------------------


def test_a_missing_toolchain_env_is_constants_shs_own_refusal(tmp_path: pathlib.Path) -> None:
    """`constants.sh:30-31` prints and `return 1`s; the twin's `set -e` carries it.

    The port reproduces it by SOURCING the same file in a bash child with both streams inherited, which is why the message arrives on stderr identically rather than being re-worded in Python.
    """
    fixture = build_fixture(tmp_path, drop_toolchain_env=True)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stdout == ""
    assert "constants.sh: gate toolchain pins missing:" in old.stderr
    assert_same(old, new)


def test_unpinned_version_exits_1_without_forging_bash_text(tmp_path: pathlib.Path) -> None:
    """THE ONE NAMED DIVERGENCE, and both halves of it are asserted here.

    With `NFPM_VERSION` gone, the twin dies at `:54` under `set -u` with bash's own `line NN: NFPM_VERSION: unbound variable` -- an interpreter diagnostic carrying a path and a line number, which a second language cannot produce and `scripts/lib/shadow-gate.ts` files as CHATTER on both sides. The port matches the exit code and the empty stdout and does NOT forge the sentence.
    """
    fixture = build_fixture(tmp_path, drop_version_pin=True)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert new.returncode == 1
    assert old.stdout == ""
    assert new.stdout == ""
    assert "NFPM_VERSION: unbound variable" in old.stderr
    assert new.stderr == ""


# --------------------------------------------------------------------------- A PLANTED DEFECT, on a throwaway copy, never on the file on disk ---------------------------------------------------------------------------


def test_a_planted_fix_of_defect_1_is_caught_by_the_differential(
    tmp_path: pathlib.Path,
) -> None:
    """Plant the "obvious improvement" and watch the differential go red.

    The plant makes the warm-cache branch compare the cached binary's version against the pin -- which is the RIGHT behaviour and the WRONG port, because the twin does not do it. If this ever passes, the differential above has stopped comparing anything.

    The real file is hashed before and after: the mutation lives in the fixture copy only.
    """
    before = hashlib.sha256(PORT.read_bytes()).hexdigest()
    source = PORT.read_text(encoding="utf-8")
    anchor = "    if os.access(str(cached), os.X_OK) and _binary_answers(cached):\n"
    assert source.count(anchor) == 1
    planted = source.replace(
        anchor,
        anchor + "        probe = subprocess.run([str(cached), '--version'], "
        "capture_output=True, text=True, check=False)\n"
        "        if version not in probe.stdout:\n"
        "            raise SystemExit(1)\n",
        1,
    )
    fixture = build_fixture(
        tmp_path, warm_version="1.0.0-stale", curl=CURL_REFUSE, port_source=planted
    )
    old, new = run_both(fixture)
    assert old.returncode == 0, "the twin must still take the stale-cache branch"
    assert new.returncode == 1, "the plant did not fire; this control proves nothing"
    assert new.stdout == ""
    assert old.stdout != new.stdout
    assert hashlib.sha256(PORT.read_bytes()).hexdigest() == before, "the real port file moved"


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_pure_helpers_match_the_twins_literals() -> None:
    twin = TWIN.read_text(encoding="utf-8")
    assert ensure_nfpm.tarball_name("2.45.0") == "nfpm_2.45.0_Linux_x86_64.tar.gz"
    assert 'TARBALL="nfpm_${NFPM_VERSION}_Linux_x86_64.tar.gz"' in twin
    assert ensure_nfpm.download_url("2.45.0", "t.tar.gz") == (
        "https://github.com/goreleaser/nfpm/releases/download/v2.45.0/t.tar.gz"
    )
    assert (
        'URL="https://github.com/goreleaser/nfpm/releases/download/v${NFPM_VERSION}/${TARBALL}"'
        in twin
    )
    assert ensure_nfpm.is_pinned_arch("x86_64")
    assert ensure_nfpm.is_pinned_arch("amd64")
    assert not ensure_nfpm.is_pinned_arch("aarch64")
    assert "x86_64 | amd64)" in twin
    assert ensure_nfpm.unpinned_arch_message("riscv64") in twin.replace("$ARCH", "riscv64")
    assert ensure_nfpm.fetching_message("2.45.0", "x86_64") in twin.replace(
        "${NFPM_VERSION}", "2.45.0"
    ).replace("${ARCH}", "x86_64")


def test_the_pin_names_are_the_ones_constants_sh_defines() -> None:
    constants = CONSTANTS.read_text(encoding="utf-8")
    assert "readonly %s=" % ensure_nfpm.VERSION_KEY in constants
    assert "readonly %s=" % ensure_nfpm.SHA_KEY in constants
    rc, version, sha = ensure_nfpm.read_pins(CONSTANTS)
    assert rc == 0
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
    assert re.fullmatch(r"[0-9a-f]{64}", sha), sha


def test_bin_dir_is_the_twins_cache_path() -> None:
    assert ensure_nfpm.bin_dir(ROOT) == ROOT / ".ci" / "cache" / "bin"
    assert 'BIN_DIR="$REPO_ROOT/.ci/cache/bin"' in TWIN.read_text(encoding="utf-8")
    assert ensure_nfpm.repo_root() == ROOT
