"""Differential: `rediacc_ci.build.build_renet` against its twin
`.ci/scripts/build/build-renet.sh`.

ONE REAL RUN EXECUTES `private/renet/build.sh embed_assets` (which compiles CRIU
and rsync from source inside Docker), CREATES A CONTAINER FROM
`rediacc/renet:latest`, AND CROSS-COMPILES SIX GO BINARIES. Every case here runs
against recording fakes on a PATH that REPLACES the caller's rather than
prepending to it, inside a fixture tree, and
`test_the_scratch_path_cannot_reach_a_real_docker_go_or_zstd` asserts the seal
before anything is driven.

NOT THE OTHER `build-renet.sh`. `.ci/scripts/infra/build-renet.sh` shares this
basename, builds one binary for the local machine, and is a different script
with a different differential (`test_infra_build_renet.py`). The ledger names
are `w7p6-build-renet` for that one and `w7p6-build-renet-full` for this one.

FOUR KINDS OF EVIDENCE ARE COMPARED, because no one of them is sufficient:

  * The three streams. `ls -la` and `cat checksums.sha256` put real content on
    STDOUT, and every log line is on stderr.
  * The call log. The six `GOOS`/`GOARCH` pairs, the `-ldflags` value with its
    trailing space, the `docker cp` argv and the `zstd -d` flags are all
    invisible in the streams.
  * The tree, INCLUDING FILE MODE. `chmod +x` on the reconstructed native
    binaries (`:172`) is only visible there.
  * The exit code, which for this script is `go`'s, `zstd`'s, `ls`'s or
    `build.sh`'s own rather than a flattened 1.

`ls -la` TIMESTAMPS ARE MASKED, AND ONLY THEY. The two sides run seconds apart,
so `ls` prints a different mtime for otherwise identical files; the mask
replaces the `<Mon> <day> <HH:MM>` field and leaves mode, link count, owner,
group, size and name alone. `test_the_ls_mask_hides_only_the_timestamp` pins
that in both directions. The only other mask is `$0`.

RECORDING FAKES WRITE TO `$FAKE_CALL_LOG`, NEVER TO STDOUT. This script's stdout
IS an artifact (the `ls` listing and the checksum file), and a fake that logged
to stdout would corrupt the very output under comparison. The `FAKEBIN ` prefix
is also what the K=5 ledger scopes `--finding-re` to, because `shadow-gate.ts`
classifies every line starting `-> ` or `ok ` as CHATTER before any message
regex runs, and this script reports almost entirely through those.

K=5 LEDGER: `.ci/shadow/w7p6-build-renet-full.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.build import build_renet as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/build-renet.sh"
PORT_REL = ".ci/rediacc_ci/build/build_renet.py"
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

# Real and deterministic. `ls`, `sha256sum` and `cat` put their stdout straight
# into the script's own output; `readlink -f` and `chmod +x` are behaviour the
# twin delegates to coreutils and this port delegates to the same binaries.
PATH_MINIMUM = (
    "dirname",
    "uname",
    "jq",
    "mkdir",
    "rm",
    "ls",
    "cat",
    "sha256sum",
    "readlink",
    "chmod",
    "grep",
    "head",
    "sed",
    "sort",
    "tr",
    "basename",
)

# A minimal but REAL-SHAPED lockfile. Three components across both classes, and `zot` covers only amd64, so the per-arch dimension is not uniform: a port that assumed every component had every arch would produce five rows here, not six.
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
      "arches": {"amd64": {}}
    }
  }
}
"""

# `$FAKE_STAGE_SKIP` withholds one asset from the staged tree, which is how the `no staged .zst` warning and the completeness refusal are reached.
FAKE_BUILD_SH = """#!/bin/bash
{
    printf 'FAKEBIN build.sh'
    printf '\\tCWD=%s' "$PWD"
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
if [[ "${1:-}" == "embed_assets" && -z "${FAKE_NO_STAGE:-}" ]]; then
    for pair in amd64/base/criu amd64/base/rsync amd64/cluster/zot \\
        arm64/base/criu arm64/base/rsync; do
        arch="${pair%%/*}"
        rest="${pair#*/}"
        cls="${rest%%/*}"
        base="${rest##*/}"
        if [[ " ${FAKE_STAGE_SKIP:-} " == *" $base-linux-$arch "* ]]; then continue; fi
        mkdir -p "pkg/embed/assets/$arch/$cls"
        printf 'ZSTPAYLOAD %s-linux-%s\\n' "$base" "$arch" \\
            >"pkg/embed/assets/$arch/$cls/$base-linux-$arch.zst"
        if [[ " ${FAKE_STAGE_DUP:-} " == *" $base-linux-$arch "* ]]; then
            other=cluster
            [[ "$cls" == cluster ]] && other=base
            mkdir -p "pkg/embed/assets/$arch/$other"
            printf 'DUPPAYLOAD %s-linux-%s\\n' "$base" "$arch" \\
                >"pkg/embed/assets/$arch/$other/$base-linux-$arch.zst"
        fi
    done
fi
exit "${FAKE_BUILD_SH_RC:-0}"
"""

FAKE_DOCKER = """#!/bin/bash
{
    printf 'FAKEBIN docker'
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
case "$1" in
    image)
        if [[ "${FAKE_DOCKER_HAS_IMAGE:-0}" != 1 ]]; then
            echo "Error: No such image: $3" >&2
            exit 1
        fi
        echo '[{"Id":"sha256:deadbeef"}]'
        ;;
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
            printf 'NATIVE %s\\n' "$leaf" >"$dst$leaf"
        else
            printf 'NATIVE %s\\n' "$leaf" >"$dst"
        fi
        ;;
    rm) : ;;
esac
exit 0
"""

# `zstd -d -f -q <src> -o <dst>`: decompresses to a NEW path and leaves the input alone, which is the opposite of the `--rm` form the sibling script uses.
FAKE_ZSTD = """#!/bin/bash
{
    printf 'FAKEBIN zstd'
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
src=""
out=""
prev=""
for a in "$@"; do
    if [[ "$prev" == "-o" ]]; then
        out="$a"
    elif [[ "$a" != -* ]]; then
        src="$a"
    fi
    prev="$a"
done
if [[ "${FAKE_ZSTD_RC:-0}" != 0 ]]; then
    echo "zstd: $src: unsupported format" >&2
    exit "$FAKE_ZSTD_RC"
fi
printf 'DEC(' >"$out"
cat "$src" >>"$out"
printf ')\\n' >>"$out"
exit 0
"""

FAKE_GO = """#!/bin/bash
{
    printf 'FAKEBIN go'
    printf '\\tGOOS=%s\\tGOARCH=%s\\tCGO_ENABLED=%s\\tCWD=%s' \\
        "${GOOS:-}" "${GOARCH:-}" "${CGO_ENABLED:-}" "$PWD"
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
out=""
prev=""
for a in "$@"; do
    if [[ "$prev" == "-o" ]]; then out="$a"; fi
    prev="$a"
done
if [[ "${FAKE_GO_RC:-0}" != 0 ]]; then
    echo "go: build failed" >&2
    exit "$FAKE_GO_RC"
fi
if [[ -n "$out" ]]; then printf 'GOBIN %s %s\\n' "${GOOS:-}" "${GOARCH:-}" >"$out"; fi
exit 0
"""

# `file(1)`. The description is deliberately longer than 80 bytes so the `head -c 80` truncation on the windows arm is exercised rather than assumed. `$FAKE_FILE_NOTSTRIPPED` names the basenames that should look like debug builds.
FAKE_FILE = """#!/bin/bash
{
    printf 'FAKEBIN file'
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
tgt="${@: -1}"
if [[ ! -e "$tgt" ]]; then
    echo "$tgt: cannot open \\`$tgt' (No such file or directory)"
    exit 1
fi
desc="ELF 64-bit LSB executable, x86-64, statically linked, Go BuildID=deadbeef, stripped"
for n in ${FAKE_FILE_NOTSTRIPPED:-}; do
    if [[ "${tgt##*/}" == "$n" ]]; then
        desc="ELF 64-bit LSB executable, x86-64, statically linked, with debug_info, not stripped"
    fi
done
if [[ "${1:-}" == "-b" ]]; then echo "$desc"; else echo "$tgt: $desc"; fi
exit "${FAKE_FILE_RC:-0}"
"""

FAKES = {
    "docker": FAKE_DOCKER,
    "zstd": FAKE_ZSTD,
    "go": FAKE_GO,
    "file": FAKE_FILE,
}

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))

LS_DATE_RE = re.compile(r"\b[A-Z][a-z]{2} +\d{1,2} +\d{2}:\d{2}\b")


def fixture(
    tmp_path: pathlib.Path,
    *,
    port_source: str | None = None,
    lockfile: str | None = LOCKFILE,
    build_sh: bool = True,
    renet_dir: bool = True,
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

    (root / "private").mkdir(parents=True, exist_ok=True)
    if renet_dir:
        renet = root / "private" / "renet"
        (renet / "pkg" / "embed" / "assets").mkdir(parents=True, exist_ok=True)
        (renet / "cmd" / "renet").mkdir(parents=True, exist_ok=True)
        if lockfile is not None:
            (root / LOCKFILE_REL).write_text(lockfile, encoding="utf-8")
        if build_sh:
            (renet / "build.sh").write_text(FAKE_BUILD_SH, encoding="utf-8")
            (renet / "build.sh").chmod(0o755)
    return root


def scratch_bin(root: pathlib.Path, *, drop: tuple[str, ...] = ()) -> str:
    """The ONLY directory on PATH for either side."""
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for name in (*PATH_MINIMUM, *FAKES):
        link = stub / name
        if name in drop:
            if link.exists() or link.is_symlink():
                link.unlink()
            continue
        if name in FAKES:
            link.write_text(FAKES[name], encoding="utf-8")
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
    args: tuple[str, ...] = ("--version", "1.2.3"),
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


TRACKED_TREES = ("private/bin", "private/elsewhere", "private/renet/pkg/embed/assets")


def _artifacts(root: pathlib.Path) -> dict[str, str]:
    """Every produced file as `<octal mode> <content>`.

    THE MODE IS PART OF THE ARTIFACT. `chmod +x` at `:172` is the only
    difference between a usable native binary and one the runtime image copies
    and cannot execute, and it appears in no stream and in no call log.
    """
    out: dict[str, str] = {}
    for rel in TRACKED_TREES:
        base = root / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                out[str(path.relative_to(root))] = "%o %s" % (
                    path.stat().st_mode & 0o777,
                    path.read_text(encoding="utf-8", errors="replace"),
                )
    return out


def _reset(root: pathlib.Path) -> None:
    for rel in TRACKED_TREES:
        shutil.rmtree(root / rel, ignore_errors=True)
    assets = root / "private" / "renet" / "pkg" / "embed" / "assets"
    if (root / "private" / "renet").is_dir():
        assets.mkdir(parents=True, exist_ok=True)


def run_both(root: pathlib.Path, **kw):
    _reset(root)
    old, old_calls = _run(root, "old", **kw)
    old_files = _artifacts(root)
    _reset(root)
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


def test_the_scratch_path_cannot_reach_a_real_docker_go_or_zstd(tmp_path) -> None:
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    for name in FAKES:
        assert shutil.which(name, path=sealed) == str(root / "fixture-bin" / name)
    dropped = scratch_bin(root, drop=tuple(FAKES))
    for name in (*FAKES, "podman", "gofmt", "docker-compose"):
        assert shutil.which(name, path=dropped) is None, "%s is reachable" % name


def test_the_ls_mask_hides_only_the_timestamp() -> None:
    """The mask is the one place this suite could go blind, so it is asserted
    directly: a differing MTIME is erased, a differing SIZE is not."""
    a = "-rwxr-xr-x 1 dev dev 23 Sep 14 09:27 criu-linux-amd64\n"
    b = "-rwxr-xr-x 1 dev dev 23 Oct  1 11:02 criu-linux-amd64\n"
    c = "-rwxr-xr-x 1 dev dev 99 Sep 14 09:27 criu-linux-amd64\n"
    d = "-rw-r--r-- 1 dev dev 23 Sep 14 09:27 criu-linux-amd64\n"
    assert _mask(a) == _mask(b)
    assert _mask(a) != _mask(c)
    assert _mask(a) != _mask(d), "a mode change must survive the mask"


# --------------------------------------------------------------------------- Argument parsing ---------------------------------------------------------------------------


def test_help_prints_the_usage_on_stdout_and_exits_zero(tmp_path) -> None:
    root = fixture(tmp_path)
    for flag in ("-h", "--help"):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 0
        assert old_t[0].stdout.startswith("Usage: ")
        assert "--skip-embed         Build without embedded assets\n" in old_t[0].stdout
        assert old_t[0].stderr == ""
        assert old_t[1] == "", "nothing should have been executed"
        _agree(old_t, new_t, flag)


def test_no_version_refuses(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=())
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "\u2717 --version is required\n"
    assert old_t[0].stdout == ""
    _agree(old_t, new_t, "no-version")


def test_skip_embed_alone_still_needs_a_version(tmp_path) -> None:
    """The arm that must NOT fire: `--skip-embed` parses fine and is not an
    unknown option, so the refusal that follows is the VERSION one."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--skip-embed",))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "\u2717 --version is required\n"
    _agree(old_t, new_t, "skip-embed-no-version")


def test_an_unknown_option_refuses(tmp_path) -> None:
    root = fixture(tmp_path)
    for flag in ("--bogus", "-x", "1.2.3"):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 1
        assert old_t[0].stderr == "\u2717 Unknown option: %s\n" % flag
        _agree(old_t, new_t, "unknown-%s" % flag)


def test_a_flag_with_no_value_dies_the_way_set_u_does(tmp_path) -> None:
    root = fixture(tmp_path)
    for flag, line in (("--version", 25), ("--output", 29)):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 1
        assert old_t[0].stderr == "%s: line %d: $2: unbound variable\n" % (
            str(root / TWIN_REL),
            line,
        )
        _agree(old_t, new_t, "unbound-%s" % flag)


# --------------------------------------------------------------------------- The success paths ---------------------------------------------------------------------------


def test_skip_embed_builds_six_binaries_and_touches_no_asset(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--version", "1.2.3", "--skip-embed"))
    old = old_t[0]
    assert old.returncode == 0, old.stderr
    assert "\u2713 Skipping asset embedding (--skip-embed)\n" in old.stderr
    assert not _calls(old_t[1], "build.sh"), "embed_assets must not run"
    assert not _calls(old_t[1], "docker")
    produced = sorted(k for k in old_t[2] if k.startswith("private/bin/"))
    assert produced == [
        "private/bin/checksums.sha256",
        "private/bin/renet-darwin-amd64",
        "private/bin/renet-darwin-arm64",
        "private/bin/renet-linux-amd64",
        "private/bin/renet-linux-arm64",
        "private/bin/renet-windows-amd64.exe",
        "private/bin/renet-windows-arm64.exe",
    ]
    # `cat checksums.sha256` is the last thing on stdout, six lines of it.
    assert old.stdout.rstrip().endswith("renet-windows-arm64.exe")
    assert old.stdout.count("renet-") == 12, "the ls listing plus the checksum listing"
    _agree(old_t, new_t, "skip-embed")


def test_the_cache_hit_path_reconstructs_every_asset_with_zstd(tmp_path) -> None:
    """No builder image, so source B: five staged `.zst` decompressed into the
    output directory and made executable."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root)
    old = old_t[0]
    assert old.returncode == 0, old.stderr
    assert (
        "\u2713 Builder image absent (cached staged tree); reconstructing via zstd -d\n"
        in old.stderr
    )
    assert _calls(old_t[1], "docker") == [
        ["FAKEBIN docker", "image", "inspect", "rediacc/renet:latest"]
    ]
    zstd_calls = _calls(old_t[1], "zstd")
    assert len(zstd_calls) == 5, "three components, but zot is amd64-only"
    for call in zstd_calls:
        assert call[1:4] == ["-d", "-f", "-q"]
        assert call[5] == "-o"
    # `chmod +x` is the only reason these are 755 rather than 644.
    assert old_t[2]["private/bin/criu-linux-amd64"].startswith("755 ")
    assert old_t[2]["private/bin/renet-linux-amd64"].startswith("644 ")
    assert old_t[2]["private/bin/criu-linux-amd64"].endswith("DEC(ZSTPAYLOAD criu-linux-amd64\n)\n")
    _agree(old_t, new_t, "cache-hit")


def test_the_builder_image_path_copies_every_asset_out_of_a_container(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, env_overrides={"FAKE_DOCKER_HAS_IMAGE": "1"})
    old = old_t[0]
    assert old.returncode == 0, old.stderr
    assert "Builder image absent" not in old.stderr
    assert not _calls(old_t[1], "zstd"), "source A must not decompress anything"
    docker = _calls(old_t[1], "docker")
    assert [c[1] for c in docker] == ["image", "create", "cp", "cp", "cp", "cp", "cp", "rm"]
    assert docker[2][2].startswith("c0ffee0000deadbeef:/opt/criu/criu-linux-")
    assert docker[-1][2] == "c0ffee0000deadbeef"
    # docker cp preserves the container's mode; nothing chmods here.
    assert old_t[2]["private/bin/criu-linux-amd64"].startswith("644 ")
    _agree(old_t, new_t, "builder-image")


def test_the_six_go_builds_carry_the_right_goos_goarch_cwd_and_ldflags(tmp_path) -> None:
    """Six invocations, in the twin's order, every part invisible in the streams
    -- including the TRAILING SPACE an empty `KEY_LDFLAGS` leaves behind."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--version", "9.9.9", "--skip-embed"))
    go_calls = _calls(old_t[1], "go")
    assert len(go_calls) == 6
    assert [(c[1], c[2]) for c in go_calls] == [
        ("GOOS=linux", "GOARCH=amd64"),
        ("GOOS=linux", "GOARCH=arm64"),
        ("GOOS=darwin", "GOARCH=amd64"),
        ("GOOS=darwin", "GOARCH=arm64"),
        ("GOOS=windows", "GOARCH=amd64"),
        ("GOOS=windows", "GOARCH=arm64"),
    ]
    assert {c[3] for c in go_calls} == {"CGO_ENABLED=0"}
    assert {c[4] for c in go_calls} == {"CWD=%s" % (root / "private" / "renet")}
    for call in go_calls:
        assert call[5] == "build"
        assert call[6] == "-ldflags=-s -w -X main.Version=9.9.9 "
        assert call[7] == "-o"
        assert call[-1] == "./cmd/renet"
    assert go_calls[-1][8].endswith("private/bin/renet-windows-arm64.exe")
    _agree(old_t, new_t, "go-argv")


def test_the_account_public_key_is_injected_into_the_ldflags(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--skip-embed"),
        env_overrides={"ACCOUNT_ED25519_PUBLIC_KEY": "MCowBQYDK2VwAyEAdeadbeef"},
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "\u2713 Account server public key injected from environment\n" in old_t[0].stderr
    assert _calls(old_t[1], "go")[0][6] == (
        "-ldflags=-s -w -X main.Version=1.2.3 "
        "-X github.com/rediacc/renet/pkg/license/keys.ProductionPublicKey="
        "MCowBQYDK2VwAyEAdeadbeef"
    )
    _agree(old_t, new_t, "key-injected")
    # The arm that must NOT fire: an EMPTY value is not an injection.
    old2_t, new2_t = run_both(
        root,
        args=("--version", "1.2.3", "--skip-embed"),
        env_overrides={"ACCOUNT_ED25519_PUBLIC_KEY": ""},
    )
    assert "public key injected" not in old2_t[0].stderr
    assert _calls(old2_t[1], "go")[0][6] == "-ldflags=-s -w -X main.Version=1.2.3 "
    _agree(old2_t, new2_t, "key-empty")


def test_output_selects_where_the_binaries_land_and_is_made_absolute(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--skip-embed", "--output", "private/renet/../elsewhere"),
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    # `readlink -f` normalised the `..` away before it was ever printed.
    assert "\u2713   Output: %s\n" % (root / "private" / "elsewhere") in old_t[0].stderr
    assert "private/elsewhere/checksums.sha256" in old_t[2]
    _agree(old_t, new_t, "output-dir")


def test_the_stripped_verdict_reports_both_ways(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--skip-embed"),
        env_overrides={"FAKE_FILE_NOTSTRIPPED": "renet-darwin-arm64 renet-windows-amd64.exe"},
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "\u2713 renet-linux-amd64: stripped (release build)\n" in old_t[0].stderr
    assert "\u26a0 renet-darwin-arm64: may contain debug symbols\n" in old_t[0].stderr
    # The windows arm never asks the stripped question; it prints the first 80
    # BYTES of `file -b`, which truncates this description mid-word.
    assert (
        "\u2713 renet-windows-amd64.exe: ELF 64-bit LSB executable, x86-64,"
        " statically linked, with debug_info, not strip\n"
    ) in old_t[0].stderr
    _agree(old_t, new_t, "stripped-verdict")


def test_a_file_that_errors_is_trusted_as_stripped_under_pipefail(tmp_path) -> None:
    """`set -o pipefail` makes `file | grep -q` non-zero whenever EITHER side is,
    so a `file` that printed "not stripped" and then exited 3 takes the SAME arm
    as one that found nothing. The twin reports the binary as stripped while the
    only tool that looked at it said the opposite.

    This is the control that a port collapsing the pipeline to "does the text
    contain it" would pass without: it is the only case in this suite where the
    text and the exit status disagree.
    """
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--skip-embed"),
        env_overrides={
            "FAKE_FILE_NOTSTRIPPED": "renet-darwin-arm64",
            "FAKE_FILE_RC": "3",
        },
    )
    assert old_t[0].returncode == 0
    assert "may contain debug symbols" not in old_t[0].stderr
    assert "\u2713 renet-darwin-arm64: stripped (release build)\n" in old_t[0].stderr
    _agree(old_t, new_t, "file-errors")


def test_a_missing_grep_or_head_changes_the_twins_verdict_too(tmp_path) -> None:
    """`file` is only the LEFT half of two pipelines, and under `pipefail` the
    right half's absence is just as load-bearing.

    Without `grep` the pipeline is 127 and every binary is reported stripped,
    INCLUDING the one whose `file` output says otherwise. Without `head` the
    windows description is empty even though `file` answered. A port that read
    `file`'s text directly instead of running the pipeline would disagree on
    both, and this is the control that says so: it was written after a ledger
    fixture with a broken `grep` symlink produced four
    `line 242: grep: command not found` lines on the twin's side and none on
    the port's.
    """
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--skip-embed"),
        drop=("grep",),
        env_overrides={"FAKE_FILE_NOTSTRIPPED": "renet-darwin-arm64"},
    )
    assert old_t[0].returncode == 0
    assert old_t[0].stderr.count("line 242: grep: command not found") == 4
    assert "may contain debug symbols" not in old_t[0].stderr
    _agree(old_t, new_t, "no-grep")

    head_old, head_new = run_both(root, args=("--version", "1.2.3", "--skip-embed"), drop=("head",))
    assert head_old[0].returncode == 0
    assert head_old[0].stderr.count("line 254: head: command not found") == 2
    assert "\u2713 renet-windows-amd64.exe: \n" in head_old[0].stderr
    _agree(head_old, head_new, "no-head")


def test_the_staged_class_search_takes_base_before_cluster(tmp_path) -> None:
    """`:161` searches `base` then `cluster` and BREAKS on the first hit, so an
    asset staged under both classes must come out of `base`. Nothing in the
    lockfile forbids that overlap, and with only one copy per asset the order is
    unobservable, which is why this case stages a deliberate duplicate with
    different content."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, env_overrides={"FAKE_STAGE_DUP": "criu-linux-amd64"})
    assert old_t[0].returncode == 0, old_t[0].stderr
    chosen = [c[4] for c in _calls(old_t[1], "zstd") if "criu-linux-amd64" in c[4]]
    assert chosen == ["%s/private/renet/pkg/embed/assets/amd64/base/criu-linux-amd64.zst" % root], (
        "base must win over cluster"
    )
    assert old_t[2]["private/bin/criu-linux-amd64"].endswith("DEC(ZSTPAYLOAD criu-linux-amd64\n)\n")
    assert "DUPPAYLOAD" not in old_t[2]["private/bin/criu-linux-amd64"]
    _agree(old_t, new_t, "class-order")


# --------------------------------------------------------------------------- Refusals ---------------------------------------------------------------------------


def test_missing_jq_zstd_or_go_refuses_through_require_cmd(tmp_path) -> None:
    root = fixture(tmp_path)
    for tool, args in (
        ("jq", ("--version", "1.2.3")),
        ("zstd", ("--version", "1.2.3")),
        ("go", ("--version", "1.2.3", "--skip-embed")),
    ):
        old_t, new_t = run_both(root, args=args, drop=(tool,))
        assert old_t[0].returncode == 1
        assert ("\u2717 Required command '%s' is not available\n" % tool) in old_t[0].stderr
        _agree(old_t, new_t, "no-%s" % tool)


def test_a_missing_lockfile_refuses(tmp_path) -> None:
    root = fixture(tmp_path, lockfile=None)
    old_t, new_t = run_both(root)
    assert old_t[0].returncode == 1
    assert ("\u2717 embed lockfile not found: %s\n" % (root / LOCKFILE_REL)) in old_t[0].stderr
    _agree(old_t, new_t, "no-lockfile")


def test_an_asset_absent_from_the_builder_image_warns_then_refuses(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        env_overrides={"FAKE_DOCKER_HAS_IMAGE": "1", "FAKE_DOCKER_ABSENT": "zot-linux-amd64"},
    )
    assert old_t[0].returncode == 1
    assert "\u26a0 native binary zot-linux-amd64 not found in builder image\n" in old_t[0].stderr
    assert (
        "\u2717 native binary zot-linux-amd64 missing after export"
        " (builder image or staged tree incomplete)\n"
    ) in old_t[0].stderr
    assert not _calls(old_t[1], "go"), "the refusal must precede the builds"
    _agree(old_t, new_t, "image-missing-asset")


def test_an_asset_with_no_staged_zst_warns_then_refuses(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, env_overrides={"FAKE_STAGE_SKIP": "zot-linux-amd64"})
    assert old_t[0].returncode == 1
    assert "\u26a0 no staged .zst for zot-linux-amd64\n" in old_t[0].stderr
    assert (
        "\u2717 native binary zot-linux-amd64 missing after export"
        " (builder image or staged tree incomplete)\n"
    ) in old_t[0].stderr
    _agree(old_t, new_t, "no-staged-zst")


def test_a_failing_build_sh_stops_the_run_with_its_own_code(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, env_overrides={"FAKE_BUILD_SH_RC": "5"})
    assert old_t[0].returncode == 5, "build.sh's status, not a flattened 1"
    assert len(_calls(old_t[1], "build.sh")) == 1
    _agree(old_t, new_t, "build-sh-fails")


def test_a_missing_build_sh_dies_with_bashs_own_message(tmp_path) -> None:
    root = fixture(tmp_path, build_sh=False)
    old_t, new_t = run_both(root)
    assert old_t[0].returncode == 127
    assert old_t[0].stderr.endswith(
        "%s: line 83: ./build.sh: No such file or directory\n" % (root / TWIN_REL)
    )
    _agree(old_t, new_t, "no-build-sh")


def test_a_missing_renet_directory_dies_at_the_cd(tmp_path) -> None:
    """`--skip-embed` walks past the staging block and reaches `cd "$RENET_DIR"`
    at `:196`, which is where an uninitialised submodule is finally noticed."""
    root = fixture(tmp_path, renet_dir=False)
    old_t, new_t = run_both(root, args=("--version", "1.2.3", "--skip-embed"))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith(
        "%s: line 196: cd: %s: No such file or directory\n"
        % (root / TWIN_REL, root / "private" / "renet")
    )
    _agree(old_t, new_t, "no-renet-dir")


def test_a_failing_go_build_stops_at_the_first_target(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=("--version", "1.2.3", "--skip-embed"), env_overrides={"FAKE_GO_RC": "7"}
    )
    assert old_t[0].returncode == 7
    assert len(_calls(old_t[1], "go")) == 1
    _agree(old_t, new_t, "go-fails")


def test_a_failing_zstd_stops_the_run(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, env_overrides={"FAKE_ZSTD_RC": "9"})
    assert old_t[0].returncode == 9
    assert len(_calls(old_t[1], "zstd")) == 1
    _agree(old_t, new_t, "zstd-fails")


def test_a_failing_docker_create_stops_with_dockers_status(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        env_overrides={"FAKE_DOCKER_HAS_IMAGE": "1", "FAKE_DOCKER_CREATE_RC": "125"},
    )
    assert old_t[0].returncode == 125, "docker's own status, not a flattened 1"
    assert not [k for k in old_t[2] if k.startswith("private/bin/")], (
        "nothing reached the output directory"
    )
    _agree(old_t, new_t, "create-fails")


# --------------------------------------------------------------------------- The defects, each driven rather than asserted from a reading ---------------------------------------------------------------------------


def test_defect_a_missing_file_reports_every_binary_as_stripped(tmp_path) -> None:
    """DEFECT 1. `file` is never `require_cmd`ed, and `! file | grep -q` reads a
    `command not found` as "no debug symbols". The binary that IS a debug build
    is reported clean, and the run exits 0."""
    root = fixture(tmp_path)
    with_tool, _ = run_both(
        root,
        args=("--version", "1.2.3", "--skip-embed"),
        env_overrides={"FAKE_FILE_NOTSTRIPPED": "renet-darwin-arm64"},
    )
    assert "\u26a0 renet-darwin-arm64: may contain debug symbols\n" in with_tool[0].stderr

    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--skip-embed"),
        drop=("file",),
        env_overrides={"FAKE_FILE_NOTSTRIPPED": "renet-darwin-arm64"},
    )
    assert old_t[0].returncode == 0, "the defect is that this is a PASS"
    assert "may contain debug symbols" not in old_t[0].stderr
    assert "\u2713 renet-darwin-arm64: stripped (release build)\n" in old_t[0].stderr
    assert "line 242: file: command not found" in old_t[0].stderr
    # The windows arm loses its description entirely.
    assert "\u2713 renet-windows-amd64.exe: \n" in old_t[0].stderr
    _agree(old_t, new_t, "no-file")


def test_defect_an_output_parent_that_does_not_exist_dies_silently(tmp_path) -> None:
    """DEFECT 2. `readlink -f` needs every component but the last to exist, and
    `set -e` takes its status. Exit 1, both streams EMPTY, and the `mkdir -p` on
    the next line that would have created the directory is never reached."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=("--version", "1.2.3", "--skip-embed", "--output", "private/absent/deep")
    )
    assert old_t[0].returncode == 1
    assert old_t[0].stdout == ""
    assert old_t[0].stderr == "", "no diagnosis at all is the defect"
    assert not (root / "private" / "absent").exists()
    _agree(old_t, new_t, "absent-output-parent")
    # The arm that must NOT fire: a parent that DOES exist is created happily.
    ok_old, ok_new = run_both(
        root, args=("--version", "1.2.3", "--skip-embed", "--output", "private/deep")
    )
    assert ok_old[0].returncode == 0, ok_old[0].stderr
    _agree(ok_old, ok_new, "present-output-parent")


def test_defect_a_malformed_lockfile_makes_the_completeness_check_vacuous(tmp_path) -> None:
    """DEFECT 3. `jq` runs in a PROCESS SUBSTITUTION, so its failure is
    invisible to `set -e`; the asset array stays empty and the "fail fast" loop
    whose comment says a missing asset "must break HERE" runs zero times. The
    build then ships exactly the incomplete artifact that check exists to
    prevent, with exit 0."""
    root = fixture(tmp_path, lockfile="{ this is not json\n")
    old_t, new_t = run_both(root)
    assert old_t[0].returncode == 0, "the defect is that this is a PASS"
    assert "jq: parse error" in old_t[0].stderr
    assert "missing after export" not in old_t[0].stderr
    assert not _calls(old_t[1], "zstd"), "zero assets were reconstructed"
    assert not [k for k in old_t[2] if k.startswith("private/bin/criu")], (
        "no asset reached the output directory, though five were staged"
    )
    assert "private/bin/renet-linux-amd64" in old_t[2], "yet the binaries shipped"
    _agree(old_t, new_t, "malformed-lockfile")


def test_defect_an_empty_component_set_reaches_the_same_vacuous_pass(tmp_path) -> None:
    """The same defect through a door with no error message at all: valid JSON
    declaring no components. `jq` exits 0, the matrix is empty, and nothing in
    the output hints that zero assets were checked."""
    root = fixture(tmp_path, lockfile='{"schemaVersion": 1, "components": {}}\n')
    old_t, new_t = run_both(root)
    assert old_t[0].returncode == 0, "the defect is that this is a PASS"
    assert "jq" not in old_t[0].stderr
    assert "missing after export" not in old_t[0].stderr
    assert not _calls(old_t[1], "zstd")
    _agree(old_t, new_t, "empty-components")


def test_defect_no_staged_assets_at_all_is_a_raw_ls_error(tmp_path) -> None:
    """DEFECT 4. `ls -la .../assets/*/*/` with nothing staged gets the unmatched
    glob LITERALLY, and `ls`'s exit 2 ends the run. The only diagnosis is `ls`
    complaining about a path containing an asterisk."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, env_overrides={"FAKE_NO_STAGE": "1"})
    assert old_t[0].returncode == 2, "ls(1)'s status, and no house refusal"
    assert old_t[0].stderr.endswith(
        "ls: cannot access '%s/private/renet/pkg/embed/assets/*/*/':"
        " No such file or directory\n" % root
    )
    assert "\u2717" not in old_t[0].stderr, "nothing named the real problem"
    _agree(old_t, new_t, "no-staged-assets")


# --------------------------------------------------------------------------- The pure helpers, both directions ---------------------------------------------------------------------------


def test_parse_args_is_exercised_directly_in_both_directions() -> None:
    assert port.parse_args(["--version", "1.2.3"]) == ("1.2.3", "", False, None, "")
    assert port.parse_args(["--version", "1", "--output", "/o", "--skip-embed"]) == (
        "1",
        "/o",
        True,
        None,
        "",
    )
    # Must fire.
    assert port.parse_args(["--help"])[3] == "help"
    assert port.parse_args(["-h"])[3] == "help"
    assert port.parse_args(["--nope"])[3:] == ("unknown", "--nope")
    assert port.parse_args(["--version"])[3:] == ("unbound", "25")
    assert port.parse_args(["--output"])[3:] == ("unbound", "29")
    # Must NOT fire: an empty argv parses cleanly; --version is checked later.
    assert port.parse_args([])[3] is None
    # A later flag wins, exactly as the while-loop's repeated assignment does.
    assert port.parse_args(["--version", "a", "--version", "b"])[0] == "b"


def test_ldflags_keeps_the_trailing_space_and_the_key_symbol() -> None:
    assert port.ldflags("1.2.3", "") == "-ldflags=-s -w -X main.Version=1.2.3 "
    assert port.ldflags("1.2.3", "KEY") == (
        "-ldflags=-s -w -X main.Version=1.2.3 "
        "-X github.com/rediacc/renet/pkg/license/keys.ProductionPublicKey=KEY"
    )


def test_matrix_rows_reproduces_the_read_builtins_field_folding() -> None:
    assert port.matrix_rows("/opt/criu\tcriu\tamd64") == [("/opt/criu", "criu", "amd64")]
    # Blank lines are dropped, exactly as `[ -n "$_line" ] || continue` does.
    assert port.matrix_rows("") == []
    assert port.matrix_rows("\n\n") == []
    # A short row reads the missing fields as empty rather than raising.
    assert port.matrix_rows("/opt/criu") == [("/opt/criu", "", "")]
    # A fourth field folds into the third, as `read -r a b c` does.
    assert port.matrix_rows("a\tb\tc\td") == [("a", "b", "c\td")]


def test_bash_glob_reproduces_both_of_the_shell_behaviours(tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "renet-x").write_text("x", encoding="utf-8")
    (tmp_path / "a" / "renet-a").write_text("a", encoding="utf-8")
    (tmp_path / "a" / "other").write_text("o", encoding="utf-8")
    (tmp_path / "a" / "renet-dir").mkdir()
    # Must fire: sorted, and only the matches.
    assert port.bash_glob("renet-*", tmp_path / "a") == ["renet-a", "renet-dir", "renet-x"]
    # Must NOT fire: with no match the PATTERN is passed through literally, and that is precisely what turns `:86` into DEFECT 4.
    assert port.bash_glob("nothing-*", tmp_path / "a") == ["nothing-*"]
    # A trailing slash matches DIRECTORIES ONLY and keeps the slash.
    assert port.bash_glob("%s/a/renet-*/" % tmp_path) == ["%s/a/renet-dir/" % tmp_path]


# --------------------------------------------------------------------------- The planted defect ---------------------------------------------------------------------------


def test_a_planted_defect_is_caught(tmp_path) -> None:
    """The proof that this differential can fail. Dropping the `chmod +x` is
    invisible in every stream and in the exit code, and it is the difference
    between a runtime image that works and one whose entrypoint cannot execute
    the criu it just copied. Only the artifact MODE sees it."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace(
        '            code = _run(["chmod", "+x", str(output / asset)])\n'
        "            if code != 0:\n"
        "                return code\n",
        "",
    )
    assert planted != source, "the plant did not apply; fix the control first"
    root = fixture(tmp_path, port_source=planted)
    old_t, new_t = run_both(root)
    assert old_t[0].returncode == new_t[0].returncode == 0, new_t[0].stderr
    assert old_t[0].stdout == new_t[0].stdout, "the plant is invisible on stdout"
    assert old_t[2] != new_t[2], "the tree MUST diverge, or this suite proves nothing"
    assert old_t[2]["private/bin/criu-linux-amd64"].startswith("755 ")
    assert new_t[2]["private/bin/criu-linux-amd64"].startswith("644 ")
