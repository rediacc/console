"""Differential: `rediacc_ci.build.extract_renet_from_image` against its twin `.ci/scripts/build/extract-renet-from-image.sh`.

ONE REAL RUN CREATES A CONTAINER FROM `ghcr.io/rediacc/renet:<tag>`, COPIES BINARIES OUT OF IT, DELETES AND REWRITES `private/renet/pkg/embed/assets/`, AND CROSS-COMPILES FOUR GO BINARIES. Every case here runs against recording fakes on a PATH that REPLACES the caller's rather than prepending to it, inside a fixture tree, and `test_the_scratch_path_cannot_reach_a_real_docker_or_go`
asserts the seal before anything is driven.

THREE KINDS OF EVIDENCE ARE COMPARED, because no one of them is sufficient:

  * The three streams. `ls -la` and `cat checksums.sha256` put real content on
    STDOUT here, unlike the other two scripts in this wave.
  * The call log. `docker cp` argv, the `zstd` flags and the four
    `GOOS`/`GOARCH` pairs are invisible in the streams.
  * The tree. `pkg/embed/assets/<arch>/<class>/*.zst` and `private/bin/*` are
    what the script exists to produce.

`ls -la` TIMESTAMPS ARE MASKED, AND ONLY THEY. The two sides run seconds apart, so `ls` prints a different mtime for files that are otherwise identical; the mask replaces the `<Mon> <day> <HH:MM>` field and leaves mode, link count, owner, group, size and name alone. Nothing else in the output is masked except `$0`.

RECORDING FAKES WRITE TO `$FAKE_CALL_LOG`, NEVER TO STDOUT. This script's stdout IS an artifact (the checksum listing), and a prior wave's fake that logged to stdout corrupted the very file its twin was writing. The `FAKEBIN ` prefix is
also what the K=5 ledger scopes `--finding-re` to, because `shadow-gate.ts`
classifies every `-> `/`ok ` line as CHATTER before any message regex runs.

K=5 LEDGER: `.ci/shadow/w7p6-extract-renet-from-image.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.build import extract_renet_from_image as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/extract-renet-from-image.sh"
PORT_REL = ".ci/rediacc_ci/build/extract_renet_from_image.py"
COMMON_REL = ".ci/scripts/lib/common.sh"
LOCKFILE_REL = "private/renet/embed-assets.lock.json"

VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/build/__init__.py",
)

BASH = shutil.which("bash") or "/bin/bash"

# Real and deterministic: the twin genuinely calls each, and `ls`/`sha256sum` put their stdout straight into the script's own output. `grep`/`sed`/`sort` are here for the twin's version-check pipeline; the port uses `re` instead, which is the one named divergence, and supplying the real binaries is what makes the two sides comparable at all.
PATH_MINIMUM = (
    "dirname",
    "uname",
    "jq",
    "mkdir",
    "rm",
    "ls",
    "cat",
    "sha256sum",
    "grep",
    "sed",
    "sort",
    "tr",
    "basename",
)

# A minimal but REAL-SHAPED lockfile: two arches, both classes, and one component (`criu`) whose version is checkable plus one (`rsync`) whose version is declared and deliberately not checkable, so the "return success rather than pretend" branch is exercised too.
LOCKFILE = """{
  "schemaVersion": 1,
  "components": {
    "criu": {
      "version": "4.2.1",
      "class": "base",
      "assetBase": "criu",
      "imageDir": "/opt/criu",
      "arches": {"amd64": {}, "arm64": {}}
    },
    "rsync": {
      "version": "3.4.1",
      "class": "base",
      "assetBase": "rsync",
      "imageDir": "/opt/rsync",
      "arches": {"amd64": {}, "arm64": {}}
    },
    "zot": {
      "version": "2.1.9",
      "class": "cluster",
      "assetBase": "zot",
      "imageDir": "/opt/zot",
      "arches": {"amd64": {}, "arm64": {}}
    }
  }
}
"""

FAKE_DOCKER = """#!/bin/bash
{
    printf 'FAKEBIN docker'
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
case "$1" in
    create)
        if [[ "${FAKE_DOCKER_CREATE_RC:-0}" != 0 ]]; then
            echo "Unable to find image '$2' locally" >&2
            exit "$FAKE_DOCKER_CREATE_RC"
        fi
        echo 'c0ffee0000deadbeef'
        ;;
    cp)
        src="$2"
        dst="$3"
        leaf="${src##*/}"
        for skip in ${FAKE_DOCKER_ABSENT:-}; do
            if [[ "$leaf" == "$skip" ]]; then
                echo "Error response from daemon: no such file: $src" >&2
                exit 1
            fi
        done
        if [[ "$dst" == */ ]]; then
            printf 'PAYLOAD %s\\n' "$leaf" >"$dst$leaf"
        else
            printf 'PAYLOAD %s\\n' "$leaf" >"$dst"
        fi
        ;;
    rm) : ;;
esac
exit 0
"""

# `zstd -19 -T0 -q --rm -f <file>`: compresses in place and REMOVES the input. The fake keeps that contract (the `.zst` appears, the input goes away) without actually compressing, so the staged tree can be compared byte for byte.
FAKE_ZSTD = """#!/bin/bash
{
    printf 'FAKEBIN zstd'
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
f="${@: -1}"
printf 'ZSTD(' >"$f.zst"
cat "$f" >>"$f.zst"
printf ')\\n' >>"$f.zst"
rm -f "$f"
exit 0
"""

# `strings -a <file>`. `$FAKE_CRIU_VERSION` decides which version the "binary" appears to carry; leaving it unset makes it match the lockfile.
FAKE_STRINGS = """#!/bin/bash
{
    printf 'FAKEBIN strings'
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
v="${FAKE_CRIU_VERSION:-4.2.1}"
if [[ -n "${FAKE_STRINGS_SILENT:-}" ]]; then exit 0; fi
printf 'GCC: (Alpine 13.2.1)\\n'
printf '/build/criu-%s\\n' "$v"
printf '%s\\n' "$v"
printf 'not-a-version-line\\n'
exit 0
"""

FAKE_GO = """#!/bin/bash
{
    printf 'FAKEBIN go'
    printf '\\tGOOS=%s\\tGOARCH=%s\\tCGO_ENABLED=%s' \\
        "${GOOS:-}" "${GOARCH:-}" "${CGO_ENABLED:-}"
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
out=""
prev=""
for a in "$@"; do
    if [[ "$prev" == "-o" ]]; then out="$a"; fi
    prev="$a"
done
if [[ -n "$out" ]]; then printf 'GOBIN %s %s\\n' "${GOOS:-}" "${GOARCH:-}" >"$out"; fi
exit "${FAKE_GO_RC:-0}"
"""

FAKE_BUILD_SH = """#!/bin/bash
{
    printf 'FAKEBIN build.sh'
    printf '\\tCWD=%s' "$PWD"
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
exit "${FAKE_BUILD_SH_RC:-0}"
"""

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))

# `ls -la` prints an mtime, and the two sides run seconds apart. Only the date field is masked; mode, links, owner, group, size and name are compared.
LS_DATE_RE = re.compile(r"\b[A-Z][a-z]{2} +\d{1,2} +\d{2}:\d{2}\b")


def fixture(
    tmp_path: pathlib.Path,
    *,
    port_source: str | None = None,
    lockfile: str | None = LOCKFILE,
    stale_zst: bool = False,
) -> pathlib.Path:
    root = tmp_path / "repo"
    for rel in (TWIN_REL, PORT_REL, COMMON_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in (TWIN_REL, COMMON_REL, *VENDORED):
        shutil.copy2(ROOT / rel, root / rel)
    if port_source is None:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")

    renet = root / "private" / "renet"
    (renet / "pkg" / "embed" / "assets").mkdir(parents=True, exist_ok=True)
    (renet / "cmd" / "renet").mkdir(parents=True, exist_ok=True)
    if lockfile is not None:
        (root / LOCKFILE_REL).write_text(lockfile, encoding="utf-8")
    (renet / "build.sh").write_text(FAKE_BUILD_SH, encoding="utf-8")
    (renet / "build.sh").chmod(0o755)
    if stale_zst:
        # `:106` exists to remove exactly this: a payload a PREVIOUS extraction left behind, at the depth the glob is written for.
        stale = renet / "pkg" / "embed" / "assets" / "amd64" / "base"
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "criu-linux-amd64.zst").write_text("STALE PAYLOAD\n", encoding="utf-8")
    return root


def scratch_bin(
    root: pathlib.Path,
    *,
    drop: tuple[str, ...] = (),
) -> str:
    """The ONLY directory on PATH for either side."""
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    fakes = {
        "docker": FAKE_DOCKER,
        "zstd": FAKE_ZSTD,
        "strings": FAKE_STRINGS,
        "go": FAKE_GO,
    }
    for name in (*PATH_MINIMUM, *fakes):
        link = stub / name
        if name in drop:
            if link.exists() or link.is_symlink():
                link.unlink()
            continue
        if name in fakes:
            link.write_text(fakes[name], encoding="utf-8")
            link.chmod(0o755)
            continue
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        if not link.exists():
            link.symlink_to(real)
    return str(stub)


def _run(
    root: pathlib.Path,
    side: str,
    *,
    args: tuple[str, ...] = ("--tag", "abc1234"),
    drop: tuple[str, ...] = (),
    env_overrides: dict[str, str | None] | None = None,
):
    call_log = root / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        # REPLACED, never prepended.
        "PATH": scratch_bin(root, drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    for key, value in (env_overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    argv = [BASH, str(root / TWIN_REL)] if side == "old" else [sys.executable, str(root / PORT_REL)]
    proc = subprocess.run(
        [*argv, *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


TRACKED_TREES = ("private/bin", "private/renet/pkg/embed/assets")


def _artifacts(root: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in TRACKED_TREES:
        base = root / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                out[str(path.relative_to(root))] = path.read_text(
                    encoding="utf-8", errors="replace"
                )
    return out


def _reset(root: pathlib.Path, *, stale_zst: bool = False) -> None:
    shutil.rmtree(root / "private" / "bin", ignore_errors=True)
    assets = root / "private" / "renet" / "pkg" / "embed" / "assets"
    shutil.rmtree(assets, ignore_errors=True)
    assets.mkdir(parents=True, exist_ok=True)
    if stale_zst:
        stale = assets / "amd64" / "base"
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "criu-linux-amd64.zst").write_text("STALE PAYLOAD\n", encoding="utf-8")


def run_both(root: pathlib.Path, *, stale_zst: bool = False, **kw):
    _reset(root, stale_zst=stale_zst)
    old, old_calls = _run(root, "old", **kw)
    old_files = _artifacts(root)
    _reset(root, stale_zst=stale_zst)
    new, new_calls = _run(root, "new", **kw)
    new_files = _artifacts(root)
    return (old, old_calls, old_files), (new, new_calls, new_files)


def _mask(text: str) -> str:
    return LS_DATE_RE.sub("<MTIME>", SELF_RE.sub("<SELF>", text))


def _agree(old_t, new_t, label: str) -> None:
    old, old_calls, old_files = old_t
    new, new_calls, new_files = new_t
    assert new.returncode == old.returncode, (
        "%s: exit diverged: %r vs %r\nold stderr: %r\nnew stderr: %r"
        % (label, old.returncode, new.returncode, old.stderr, new.stderr)
    )
    assert _mask(new.stdout) == _mask(old.stdout), "%s: stdout diverged:\n%r\n%r" % (
        label,
        old.stdout,
        new.stdout,
    )
    assert _mask(new.stderr) == _mask(old.stderr), "%s: stderr diverged:\n%r\n%r" % (
        label,
        old.stderr,
        new.stderr,
    )
    assert new_calls == old_calls, "%s: call log diverged:\n%s---\n%s" % (
        label,
        old_calls,
        new_calls,
    )
    assert new_files == old_files, "%s: artifacts diverged:\n%s" % (
        label,
        "\n".join(
            "%s:\n  old=%r\n  new=%r" % (k, old_files.get(k), new_files.get(k))
            for k in sorted(set(old_files) | set(new_files))
            if old_files.get(k) != new_files.get(k)
        ),
    )


def _calls(log: str, tool: str) -> list[list[str]]:
    prefix = "FAKEBIN %s" % tool
    return [ln.split("\t") for ln in log.splitlines() if ln.startswith(prefix)]


# --------------------------------------------------------------------------- The control on the control ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_docker_or_go(tmp_path) -> None:
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    for name in ("docker", "zstd", "strings", "go"):
        assert shutil.which(name, path=sealed) == str(root / "fixture-bin" / name)
    dropped = scratch_bin(root, drop=("docker", "go", "zstd", "strings"))
    for name in ("docker", "go", "zstd", "strings", "podman", "gofmt"):
        assert shutil.which(name, path=dropped) is None, "%s is reachable" % name


def test_the_ls_mask_hides_only_the_timestamp(tmp_path) -> None:
    """The mask is the one place this suite could go blind, so it is asserted directly: a differing MTIME is erased, a differing SIZE is not."""
    del tmp_path
    a = "-rw-r--r-- 1 dev dev 23 Sep 14 09:27 criu-linux-amd64.zst\n"
    b = "-rw-r--r-- 1 dev dev 23 Oct  1 11:02 criu-linux-amd64.zst\n"
    c = "-rw-r--r-- 1 dev dev 99 Sep 14 09:27 criu-linux-amd64.zst\n"
    assert _mask(a) == _mask(b)
    assert _mask(a) != _mask(c)


# --------------------------------------------------------------------------- Argument parsing ---------------------------------------------------------------------------


def test_no_tag_refuses(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=())
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "\u2717 --tag is required\n"
    assert old_t[1] == "", "nothing should have been executed"
    _agree(old_t, new_t, "no-tag")


def test_defect_help_is_an_error_here(tmp_path) -> None:
    """DEFECT 2. There is no `-h`/`--help` arm, so the flag both sibling build scripts answer with a usage and exit 0 is an ERROR in this one."""
    root = fixture(tmp_path)
    for flag in ("-h", "--help"):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 1
        assert old_t[0].stderr == "\u2717 Unknown option: %s\n" % flag
        _agree(old_t, new_t, flag)


def test_a_flag_with_no_value_dies_the_way_set_u_does(tmp_path) -> None:
    root = fixture(tmp_path)
    for flag, line in (("--tag", 23), ("--output", 27), ("--registry", 31)):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 1
        assert old_t[0].stderr == "%s: line %d: $2: unbound variable\n" % (
            str(root / TWIN_REL),
            line,
        )
        _agree(old_t, new_t, flag)


def test_the_registry_defaults_and_can_be_overridden(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root)
    assert "Extracting renet binaries from ghcr.io/rediacc/renet:abc1234" in old_t[0].stderr
    assert _calls(old_t[1], "docker")[0][1:] == ["create", "ghcr.io/rediacc/renet:abc1234"]
    _agree(old_t, new_t, "default-registry")

    old2_t, new2_t = run_both(root, args=("--tag", "v9", "--registry", "registry.example/team"))
    assert _calls(old2_t[1], "docker")[0][1:] == ["create", "registry.example/team/renet:v9"]
    _agree(old2_t, new2_t, "custom-registry")


# --------------------------------------------------------------------------- The success path ---------------------------------------------------------------------------


def test_the_full_success_path(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root)
    old = old_t[0]
    assert old.returncode == 0, old.stderr

    # The two renet binaries land in the default output directory.
    assert old_t[2]["private/bin/renet-linux-amd64"] == "PAYLOAD renet-linux-amd64\n"
    # Six assets: three components x two arches, each zstd-ed in place.
    staged = sorted(k for k in old_t[2] if k.endswith(".zst"))
    assert staged == [
        "private/renet/pkg/embed/assets/amd64/base/criu-linux-amd64.zst",
        "private/renet/pkg/embed/assets/amd64/base/rsync-linux-amd64.zst",
        "private/renet/pkg/embed/assets/amd64/cluster/zot-linux-amd64.zst",
        "private/renet/pkg/embed/assets/arm64/base/criu-linux-arm64.zst",
        "private/renet/pkg/embed/assets/arm64/base/rsync-linux-arm64.zst",
        "private/renet/pkg/embed/assets/arm64/cluster/zot-linux-arm64.zst",
    ]
    # The uncompressed inputs are gone: `zstd --rm`.
    assert not [k for k in old_t[2] if k.endswith("criu-linux-amd64")]
    # Four cross-compiled binaries, windows carrying `.exe`.
    for name in (
        "renet-darwin-amd64",
        "renet-darwin-arm64",
        "renet-windows-amd64.exe",
        "renet-windows-arm64.exe",
    ):
        assert "private/bin/%s" % name in old_t[2]
    # `cat checksums.sha256` is the last thing on stdout.
    assert old.stdout.rstrip().endswith("renet-windows-arm64.exe")
    assert old.stdout.count("renet-") >= 12, "the ls listing plus the checksum listing"
    _agree(old_t, new_t, "success")


def test_the_go_builds_carry_the_right_goos_goarch_and_output(tmp_path) -> None:
    """Four invocations, in the twin's order, each invisible in the streams."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root)
    go_calls = _calls(old_t[1], "go")
    assert len(go_calls) == 4
    assert [c[1] for c in go_calls] == [
        "GOOS=darwin",
        "GOOS=darwin",
        "GOOS=windows",
        "GOOS=windows",
    ]
    assert [c[2] for c in go_calls] == [
        "GOARCH=amd64",
        "GOARCH=arm64",
        "GOARCH=amd64",
        "GOARCH=arm64",
    ]
    assert {c[3] for c in go_calls} == {"CGO_ENABLED=0"}
    for call in go_calls:
        assert call[4:7] == ["build", "-ldflags=-s -w", "-o"]
        assert call[-1] == "./cmd/renet"
    assert go_calls[-1][7].endswith("private/bin/renet-windows-arm64.exe")
    _agree(old_t, new_t, "go-argv")


def test_zstd_is_invoked_with_the_twins_exact_flags(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root)
    zstd_calls = _calls(old_t[1], "zstd")
    assert len(zstd_calls) == 6
    for call in zstd_calls:
        assert call[1:6] == ["-19", "-T0", "-q", "--rm", "-f"]
        assert call[6].endswith(("-linux-amd64", "-linux-arm64"))
        assert len(call) == 7
    _agree(old_t, new_t, "zstd-argv")


def test_the_proxy_compose_is_staged_through_build_sh_from_the_renet_directory(
    tmp_path,
) -> None:
    """`:211` is `(cd "$REPO_ROOT/private/renet" && ./build.sh embed_proxy)`, and the fake records its own `$PWD` so the directory is asserted rather than assumed. Only the PROXY step is delegated; the asset staging deliberately is not."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root)
    calls = _calls(old_t[1], "build.sh")
    assert len(calls) == 1
    assert calls[0][1] == "CWD=%s" % (root / "private" / "renet")
    assert calls[0][2] == "embed_proxy"
    _agree(old_t, new_t, "embed-proxy")


def test_a_stale_zst_from_a_previous_run_is_removed_first(tmp_path) -> None:
    """`:106`. The stale payload has DIFFERENT content from what this run produces, so an implementation that skipped the cleanup would leave it in place and the comparison would see it."""
    root = fixture(tmp_path, stale_zst=True)
    old_t, new_t = run_both(root, stale_zst=True)
    assert old_t[0].returncode == 0, old_t[0].stderr
    staged = old_t[2]["private/renet/pkg/embed/assets/amd64/base/criu-linux-amd64.zst"]
    assert staged == "ZSTD(PAYLOAD criu-linux-amd64\n)\n"
    assert "STALE" not in staged
    _agree(old_t, new_t, "stale-cleanup")


def test_output_selects_where_the_binaries_land(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--tag", "abc1234", "--output", "private/elsewhere"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert (root / "private" / "elsewhere" / "checksums.sha256").is_file()
    assert (root / "private" / "elsewhere" / "renet-darwin-arm64").is_file()
    _agree(old_t, new_t, "output-dir")


# --------------------------------------------------------------------------- Refusals ---------------------------------------------------------------------------


def test_a_missing_lockfile_refuses(tmp_path) -> None:
    root = fixture(tmp_path, lockfile=None)
    old_t, new_t = run_both(root)
    assert old_t[0].returncode == 1
    assert "\u2717 embed lockfile not found: " in old_t[0].stderr
    # The container was created and must still be removed by the EXIT trap.
    assert _calls(old_t[1], "docker")[-1][1] == "rm"
    _agree(old_t, new_t, "no-lockfile")


def test_missing_jq_or_zstd_refuses_through_require_cmd(tmp_path) -> None:
    root = fixture(tmp_path)
    for tool in ("jq", "zstd"):
        old_t, new_t = run_both(root, drop=(tool,))
        assert old_t[0].returncode == 1
        assert ("\u2717 Required command '%s' is not available\n" % tool) in old_t[0].stderr
        _agree(old_t, new_t, "no-%s" % tool)


def test_an_asset_absent_from_the_image_refuses_and_names_every_one(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, env_overrides={"FAKE_DOCKER_ABSENT": "zot-linux-amd64 zot-linux-arm64"}
    )
    assert old_t[0].returncode == 1
    assert (
        "\u2717 Cached renet image is missing assets the lockfile declares:"
        " zot-linux-amd64 zot-linux-arm64\n"
    ) in old_t[0].stderr
    assert "./build.sh docker_image)" in old_t[0].stderr
    _agree(old_t, new_t, "missing-asset")


def test_a_version_the_lockfile_forbids_refuses(tmp_path) -> None:
    """The whole point of the lockfile check: the CACHED image carries criu 3.17.1 while the lockfile declares 4.2.1."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, env_overrides={"FAKE_CRIU_VERSION": "3.17.1"})
    assert old_t[0].returncode == 1
    assert (
        "\u2717 criu-linux-amd64 declares version(s) [3.17.1] but the lockfile requires 4.2.1\n"
    ) in old_t[0].stderr
    assert (
        "\u2717 Cached renet image carries assets at versions the lockfile does not declare:"
        " criu-linux-amd64 criu-linux-arm64\n"
    ) in old_t[0].stderr
    assert "docker_image --force)" in old_t[0].stderr
    _agree(old_t, new_t, "version-mismatch")


def test_defect_a_silent_strings_turns_the_version_check_into_a_warning(tmp_path) -> None:
    """DEFECT 1. `strings` is never `require_cmd`ed and its stderr is discarded, so when it produces nothing the check that exists to catch a stale criu reports `cannot verify` and the run EXITS 0 -- with the very same stale 3.17.1 that the previous test refuses."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        env_overrides={"FAKE_CRIU_VERSION": "3.17.1", "FAKE_STRINGS_SILENT": "1"},
    )
    assert old_t[0].returncode == 0, "the defect is that this is a PASS"
    assert (
        "\u26a0 criu-linux-amd64: no version string found; cannot verify against lockfile (4.2.1)\n"
    ) in old_t[0].stderr
    assert "declares version(s)" not in old_t[0].stderr
    _agree(old_t, new_t, "strings-silent")


def test_defect_a_missing_strings_binary_reaches_the_same_pass(tmp_path) -> None:
    """The same defect through the door an operator is far more likely to walk through: `strings` (binutils) simply not installed. `2>/dev/null` swallows bash's own `command not found`, so nothing at all says the tool is absent."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, drop=("strings",), env_overrides={"FAKE_CRIU_VERSION": "3.17.1"})
    assert old_t[0].returncode == 0, "the defect is that this is a PASS"
    assert "no version string found; cannot verify" in old_t[0].stderr
    assert "command not found" not in old_t[0].stderr
    _agree(old_t, new_t, "strings-absent")


def test_a_failing_docker_create_stops_before_anything_is_touched(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, env_overrides={"FAKE_DOCKER_CREATE_RC": "125"})
    assert old_t[0].returncode == 125, "docker's own status, not a flattened 1"
    assert old_t[2] == {}
    _agree(old_t, new_t, "create-fails")


def test_a_failing_go_build_stops_the_run(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, env_overrides={"FAKE_GO_RC": "2"})
    assert old_t[0].returncode == 2
    _agree(old_t, new_t, "go-fails")


def test_a_failing_build_sh_stops_the_run(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, env_overrides={"FAKE_BUILD_SH_RC": "3"})
    assert old_t[0].returncode == 3
    assert not _calls(old_t[1], "go"), "the cross-compiles must not have started"
    _agree(old_t, new_t, "build-sh-fails")


# --------------------------------------------------------------------------- The pure helpers, and the planted defect ---------------------------------------------------------------------------


def test_bash_glob_reproduces_both_of_the_shell_behaviours(tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "renet-x").write_text("x", encoding="utf-8")
    (tmp_path / "a" / "renet-a").write_text("a", encoding="utf-8")
    (tmp_path / "a" / "other").write_text("o", encoding="utf-8")
    # Must fire: sorted, and only the matches.
    assert port.bash_glob("renet-*", tmp_path / "a") == ["renet-a", "renet-x"]
    # Must NOT fire: with no match the PATTERN is passed through literally.
    assert port.bash_glob("nothing-*", tmp_path / "a") == ["nothing-*"]
    # An absolute pattern yields absolute paths regardless of the cwd.
    absolute = port.bash_glob("%s/a/renet-*" % tmp_path, tmp_path)
    assert absolute == [str(tmp_path / "a" / "renet-a"), str(tmp_path / "a" / "renet-x")]


def test_criu_versions_reads_both_shapes_and_neither_when_there_is_nothing(
    tmp_path,
) -> None:
    del tmp_path
    # Exercised through the real `strings` fake in the driven cases above; here the regexes themselves are pinned in both directions.
    assert port.CRIU_BUILD_PATH_RE.findall("junk /build/criu-4.2.1 junk") == ["/build/criu-4.2.1"]
    assert port.CRIU_BUILD_PATH_RE.findall("/build/criu-x") == []
    assert port.CRIU_BARE_VERSION_RE.match("4.2.1") is not None
    assert port.CRIU_BARE_VERSION_RE.match("4.2") is not None
    # Must NOT fire: `grep -x` is a WHOLE-LINE match.
    assert port.CRIU_BARE_VERSION_RE.match("v4.2.1") is None
    assert port.CRIU_BARE_VERSION_RE.match("4.2.1-rc") is None


def test_parse_args_is_exercised_directly_in_both_directions() -> None:
    assert port.parse_args(["--tag", "v1"]) == ("v1", "", port.DEFAULT_REGISTRY, None, "")
    assert port.parse_args(["--tag", "v1", "--output", "/o", "--registry", "r"]) == (
        "v1",
        "/o",
        "r",
        None,
        "",
    )
    # Must fire.
    assert port.parse_args(["--help"])[3] == 1
    assert port.parse_args(["--tag"])[3] == 1
    assert port.parse_args([])[3] is None, "an empty argv parses; --tag is checked later"


def test_a_planted_defect_is_caught_only_by_the_staged_tree(tmp_path) -> None:
    """The proof that this differential can fail. Flattening the per-arch layout is the exact regression the twin's comment says once shipped assetless darwin/windows binaries, and it changes neither the exit code, nor stderr, nor the call log's `docker cp` count -- only where the files land."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace(
        "        target_dir = embed_dir / arch / klass\n",
        "        target_dir = embed_dir\n",
    )
    assert planted != source, "the plant did not apply; fix the control first"
    root = fixture(tmp_path, port_source=planted)
    old_t, new_t = run_both(root)
    assert old_t[0].returncode == new_t[0].returncode == 0, new_t[0].stderr
    assert old_t[2] != new_t[2], "the tree MUST diverge, or this suite proves nothing"
    assert "private/renet/pkg/embed/assets/amd64/base/criu-linux-amd64.zst" in old_t[2]
    assert "private/renet/pkg/embed/assets/criu-linux-amd64.zst" in new_t[2]
