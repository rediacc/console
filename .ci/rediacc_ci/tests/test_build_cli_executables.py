"""Differential: `rediacc_ci.build.build_cli_executables` against its twin
`.ci/scripts/build/build-cli-executables.sh`.

WHAT IS COMPARED. Four things per case, separately, never folded together: stdout, stderr, exit code, and the FAKE-BINARY CALL LOG -- one tab-separated line of argv per invocation of `node`, `uname`, `strip`, `codesign` and `prepare-cli-assets.sh`. Plus, on every build that gets that far, the ARTIFACTS: every file the run left under `dist/` and `packages/cli/dist/`, with its
content and its executable bit.

WHY THE CALL LOG IS NOT OPTIONAL HERE. Almost everything this script says it did is a `log_step` line, and `shadow-gate.ts` classifies any line starting with `→ ` or `✓ ` as CHATTER before a `--finding-re` ever sees it. A port that printed all eighteen log lines correctly and never ran `strip`, or ran `sea-inject/cli.mjs` with the wrong sentinel fuse, would be byte-identical on
both streams. The call log is where those live, and it is why every fake echoes its own argv under a `FAKEBIN ` prefix.

RECORDED TO `$FAKE_CALL_LOG`, NEVER TO STDOUT. The fake `node` is copied by the script under test and then EXECUTED as the built binary, whose stdout is parsed as JSON by `jq`; a fake that logged to stdout would corrupt the artifact it is standing in for. A prior wave lost a day to exactly that.

THE PATH IS REPLACED, NOT PREPENDED, and `test_the_scratch_path_is_sealed` asserts it before anything is driven. A prepended PATH let a real system binary reach into the live checkout in an earlier wave.

WHAT IS REAL AND WHAT IS FAKE. `dirname`, `mkdir`, `cp`, `chmod`, `sed`, `cat`, `wc`, `sha256sum` and `jq` are REAL: they are deterministic and several of them produce the bytes under comparison. `node`, `uname`, `strip`, `codesign` and `prepare-cli-assets.sh` are FAKE, because they are respectively not installed as a SEA toolchain here, the thing whose branches must be steered,
destructive to the fixture, absent on Linux, and a 200-line sibling script with its own port and its own differential.

ONE FAKE, TWO PERSONALITIES. The fake `node` inspects `${0##*/}` and behaves as
the built CLI when it has been copied to `rdc-*`. That is not a trick: it is what a SEA binary IS -- the host `node` with a blob glued on -- and it is the only way the `--version` and `doctor` smoke tests can be driven at all.

`$0` IS MASKED TO `<SELF>` and, in the two cases where bash names a line number of its own, `line <n>: ` is masked too (the twin's line and the port's line are necessarily different numbers in different files). Nothing else is masked.

K=5 LEDGER: `.ci/shadow/w7p6-build-cli-executables.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.build import build_cli_executables as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/build-cli-executables.sh"
PORT_REL = ".ci/rediacc_ci/build/build_cli_executables.py"
COMMON_REL = ".ci/scripts/lib/common.sh"
INJECT_REL = ".ci/scripts/version/inject-env.sh"
ASSETS_REL = ".ci/scripts/build/prepare-cli-assets.sh"

VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/build/__init__.py",
    ".ci/rediacc_ci/version/__init__.py",
    ".ci/rediacc_ci/version/inject_env.py",
)

BASH = shutil.which("bash") or "/bin/bash"

# Real, deterministic, and genuinely reached. Anything absent from this tuple is ABSENT from the scratch PATH -- including `shasum`, whose absence is what makes the `sha256sum` arm the one taken, and `node`, which is supplied as a fake.
PATH_MINIMUM = ("dirname", "mkdir", "cp", "chmod", "sed", "cat", "wc", "sha256sum", "jq")

RECORD = """{
    printf 'FAKEBIN %s' "$__self"
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
"""

# `node`, and -- once `cp`'d to `rdc-*` -- the SEA binary it becomes. `${0##*/}`
# rather than `basename`, so the fake needs nothing on PATH of its own.
FAKE_NODE = (
    """#!/bin/bash
__self="${0##*/}"
"""
    + RECORD
    + """
case "$__self" in
    rdc-*)
        case "${1:-}" in
            --version)
                printf '%s\\n' "${FAKE_RDC_VERSION:-0.0.0-dev}"
                exit "${FAKE_RDC_VERSION_RC:-0}"
                ;;
            doctor)
                [[ -n "${FAKE_DOCTOR_JSON:-}" ]] && printf '%s\\n' "$FAKE_DOCTOR_JSON"
                printf 'doctor noise\\n' >&2
                exit "${FAKE_DOCTOR_RC:-0}"
                ;;
        esac
        exit 0
        ;;
esac

case "${1:-}" in
    --version)
        printf 'v22.14.0\\n'
        exit 0
        ;;
    bundle.mjs)
        if [[ "${FAKE_NODE_BUNDLE_WRITES:-1}" == "1" ]]; then
            mkdir -p dist
            printf 'CJS BUNDLE BYTES\\n' >dist/cli-bundle.cjs
        fi
        exit "${FAKE_NODE_BUNDLE_RC:-0}"
        ;;
    --experimental-sea-config)
        if [[ "${FAKE_NODE_SEA_WRITES:-1}" == "1" ]]; then
            mkdir -p dist
            printf 'SEA PREP BLOB BYTES\\n' >dist/sea-prep.blob
        fi
        exit "${FAKE_NODE_SEA_RC:-0}"
        ;;
esac
exit "${FAKE_NODE_RC:-0}"
"""
)

FAKE_UNAME = (
    """#!/bin/bash
__self=uname
"""
    + RECORD
    + """
case "${1:-}" in
    -s) printf '%s\\n' "${FAKE_UNAME_S:-Linux}" ;;
    -m) printf '%s\\n' "${FAKE_UNAME_M:-x86_64}" ;;
esac
"""
)

FAKE_STRIP = (
    """#!/bin/bash
__self=strip
"""
    + RECORD
    + """
exit "${FAKE_STRIP_RC:-0}"
"""
)

FAKE_CODESIGN = (
    """#!/bin/bash
__self=codesign
"""
    + RECORD
    + """
exit "${FAKE_CODESIGN_RC:-0}"
"""
)

FAKE_ASSETS = (
    """#!/bin/bash
__self=prepare-cli-assets.sh
"""
    + RECORD
    + """
exit "${FAKE_ASSETS_RC:-0}"
"""
)

FAKES = {
    "node": FAKE_NODE,
    "uname": FAKE_UNAME,
    "strip": FAKE_STRIP,
    "codesign": FAKE_CODESIGN,
}

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))
LINE_RE = re.compile(r"line \d+: ")


def doctor_json(
    *,
    install_method: str = "SEA binary",
    cli_version: str = "0.0.0-dev",
    node_status: str = "ok",
    renet: list[dict[str, str]] | None = None,
) -> str:
    """The shape `:269-318` reads: three `.Environment` rows and a `.Renet` list."""
    return json.dumps(
        {
            "Environment": [
                {"name": "Install method", "value": install_method},
                {"name": "CLI version", "value": cli_version},
                {"name": "Node.js", "value": "v22.14.0", "status": node_status},
            ],
            "Renet": renet if renet is not None else [{"name": "linux-amd64", "value": "ok"}],
        }
    )


def fixture(tmp_path: pathlib.Path, *, port_source: str | None = None) -> pathlib.Path:
    root = tmp_path / "repo"
    for rel in (TWIN_REL, PORT_REL, COMMON_REL, INJECT_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in (TWIN_REL, COMMON_REL, INJECT_REL, *VENDORED):
        shutil.copy2(ROOT / rel, root / rel)
    if port_source is None:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")

    # The sibling the twin shells out to, replaced by a recorder. Its real 200-line self has its own port and its own differential; running it here would be testing that file through this one.
    assets = root / ASSETS_REL
    assets.write_text(FAKE_ASSETS, encoding="utf-8")
    assets.chmod(0o755)

    (root / "packages" / "cli").mkdir(parents=True, exist_ok=True)
    return root


def scratch_bin(root: pathlib.Path, *, drop: tuple[str, ...] = ()) -> str:
    """The ONLY directory on PATH for either side. Replaced, never prepended."""
    stub = root / "fixture-bin"
    if stub.exists():
        shutil.rmtree(stub)
    stub.mkdir(parents=True)
    for name in PATH_MINIMUM:
        if name in drop:
            continue
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        (stub / name).symlink_to(real)
    for name, body in FAKES.items():
        if name in drop:
            continue
        (stub / name).write_text(body, encoding="utf-8")
        (stub / name).chmod(0o755)
    return str(stub)


def _run(
    root: pathlib.Path,
    side: str,
    *,
    args: tuple[str, ...] = (),
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
        "FAKE_DOCTOR_JSON": doctor_json(),
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
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def _artifacts(root: pathlib.Path) -> dict[str, tuple[str, bool]]:
    """Everything the run wrote, with content and the executable bit."""
    out: dict[str, tuple[str, bool]] = {}
    for base in (root / "dist", root / "packages" / "cli" / "dist", root / "out"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            mode = path.stat().st_mode
            out[str(path.relative_to(root))] = (
                path.read_text(encoding="utf-8", errors="replace"),
                bool(mode & stat.S_IXUSR),
            )
    return out


def _reset(root: pathlib.Path) -> None:
    for rel in ("dist", "out", "packages/cli/dist"):
        shutil.rmtree(root / rel, ignore_errors=True)


def run_both(root: pathlib.Path, **kw):
    _reset(root)
    old, old_calls = _run(root, "old", **kw)
    old_files = _artifacts(root)
    _reset(root)
    new, new_calls = _run(root, "new", **kw)
    new_files = _artifacts(root)
    return (old, old_calls, old_files), (new, new_calls, new_files)


def _mask(text: str, *, lines: bool = False) -> str:
    masked = SELF_RE.sub("<SELF>", text)
    return LINE_RE.sub("line <N>: ", masked) if lines else masked


def _agree(old_t, new_t, label: str, *, lines: bool = False) -> None:
    old, old_calls, old_files = old_t
    new, new_calls, new_files = new_t
    assert new.returncode == old.returncode, (
        "%s: exit diverged: %r vs %r\nold stderr: %r\nnew stderr: %r"
        % (label, old.returncode, new.returncode, old.stderr, new.stderr)
    )
    assert _mask(new.stdout, lines=lines) == _mask(old.stdout, lines=lines), (
        "%s: stdout diverged:\n%r\n%r" % (label, old.stdout, new.stdout)
    )
    assert _mask(new.stderr, lines=lines) == _mask(old.stderr, lines=lines), (
        "%s: stderr diverged:\n%r\n%r" % (label, old.stderr, new.stderr)
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


NATIVE = ("--platform", "linux", "--arch", "x64")


# --------------------------------------------------------------------------- The control on the control ---------------------------------------------------------------------------


def test_the_scratch_path_is_sealed(tmp_path) -> None:
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    assert shutil.which("node", path=sealed) == str(root / "fixture-bin" / "node")
    assert shutil.which("uname", path=sealed) == str(root / "fixture-bin" / "uname")
    assert shutil.which("strip", path=sealed) == str(root / "fixture-bin" / "strip")
    assert shutil.which("shasum", path=sealed) is None, "the shasum fallback must stay unreachable"
    assert shutil.which("npx", path=sealed) is None
    assert shutil.which("git", path=sealed) is None
    dropped = scratch_bin(root, drop=("node",))
    assert shutil.which("node", path=dropped) is None


def test_the_fakes_really_record_and_never_touch_stdout(tmp_path) -> None:
    """If a fake logged to stdout it would land inside the JSON `jq` parses, and
    every doctor case below would be comparing corruption to corruption."""
    root = fixture(tmp_path)
    old_t, _ = run_both(root, args=NATIVE)
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "FAKEBIN" not in old_t[0].stdout
    assert "FAKEBIN" not in old_t[0].stderr
    assert old_t[1].count("FAKEBIN node") == 5, old_t[1]
    assert old_t[1].count("FAKEBIN uname") == 4, old_t[1]
    assert "FAKEBIN prepare-cli-assets.sh" in old_t[1]


# --------------------------------------------------------------------------- Argument parsing ---------------------------------------------------------------------------


def test_help_prints_usage_on_stdout_and_exits_zero(tmp_path) -> None:
    root = fixture(tmp_path)
    for flag in ("-h", "--help"):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 0
        assert old_t[0].stderr == ""
        assert old_t[0].stdout.endswith(
            " [--platform PLATFORM] [--arch ARCH] [--output DIR] [--dry-run]\n"
        )
        assert old_t[1] == "FAKEBIN uname\t-s\nFAKEBIN uname\t-m\n", (
            "common.sh:509-511 runs two unames at SOURCE time, before parsing"
        )
        _agree(old_t, new_t, flag)


def test_an_unknown_option_refuses_and_names_it(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--nope",))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "\u2717 Unknown option: --nope\n"
    _agree(old_t, new_t, "unknown-option")


def test_a_flag_with_no_value_dies_the_way_set_u_does(tmp_path) -> None:
    """`"$2"` under `set -u`. The shell refuses, so there is no `✗` glyph."""
    root = fixture(tmp_path)
    for flag, line in (("--platform", 33), ("--arch", 37), ("--output", 41)):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 1
        assert old_t[0].stderr == "%s: line %d: $2: unbound variable\n" % (
            str(root / TWIN_REL),
            line,
        )
        assert not old_t[0].stderr.startswith("\u2717")
        _agree(old_t, new_t, flag)


def test_help_wins_wherever_it_appears(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--dry-run", "--help"))
    assert old_t[0].returncode == 0
    _agree(old_t, new_t, "late-help")


# --------------------------------------------------------------------------- Auto-detection: four uname answers, two of them refusals ---------------------------------------------------------------------------


def test_auto_detects_linux_x64(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--dry-run",))
    assert old_t[0].returncode == 0
    assert "\u2713 Auto-detected platform: linux\n" in old_t[0].stderr
    assert "\u2713 Auto-detected arch: x64\n" in old_t[0].stderr
    assert old_t[1].count("FAKEBIN uname") == 4, (
        "two from common.sh at source time, two from the auto-detect cases"
    )
    _agree(old_t, new_t, "auto-linux")


def test_auto_detects_darwin_as_mac_and_arm64(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--dry-run",),
        env_overrides={"FAKE_UNAME_S": "Darwin", "FAKE_UNAME_M": "arm64"},
    )
    assert "\u2713 Auto-detected platform: mac\n" in old_t[0].stderr
    assert "rdc-mac-arm64" in old_t[0].stderr
    _agree(old_t, new_t, "auto-darwin")


def test_auto_detects_mingw_as_win_and_appends_exe(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=("--dry-run",), env_overrides={"FAKE_UNAME_S": "MINGW64_NT-10.0"}
    )
    assert "rdc-win-x64.exe" in old_t[0].stderr
    _agree(old_t, new_t, "auto-mingw")


def test_an_unnameable_platform_refuses_and_calls_uname_twice(tmp_path) -> None:
    """The error arm re-runs `uname -s` to build its own message; the count is
    observable in the call log and a port that cached the value would diverge."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--dry-run",), env_overrides={"FAKE_UNAME_S": "Plan9"})
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "\u2717 Cannot detect platform from: Plan9\n"
    assert old_t[1].count("FAKEBIN uname\t-s") == 3, "one sourcing, two in the refusal arm"
    assert old_t[1].count("FAKEBIN uname\t-m") == 1, "only common.sh's own"
    _agree(old_t, new_t, "unnameable-platform")


def test_the_arch_case_has_no_globs_so_x86_64h_refuses(tmp_path) -> None:
    """`Linux*` is a pattern but `x86_64|amd64` is not, so a Haswell Darwin
    `x86_64h` is refused where a `Linux-anything` would have been accepted."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--dry-run",), env_overrides={"FAKE_UNAME_M": "x86_64h"})
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith("\u2717 Cannot detect architecture from: x86_64h\n")
    assert old_t[1].count("FAKEBIN uname\t-m") == 3, "one sourcing, two in the refusal arm"
    _agree(old_t, new_t, "x86_64h")


def test_explicit_flags_skip_uname_entirely_until_the_smoke_guard(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*NATIVE, "--dry-run"))
    assert old_t[0].returncode == 0
    assert old_t[1] == ("FAKEBIN uname\t-s\nFAKEBIN uname\t-m\nFAKEBIN node\t--version\n"), (
        "common.sh's source-time pair, plus the `node --version` the log line interpolates"
    )
    _agree(old_t, new_t, "explicit-dry-run")


# --------------------------------------------------------------------------- DEFECT 1: a missing `node` is a silent exit 1 ---------------------------------------------------------------------------


def test_a_missing_node_is_a_silent_exit_one(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, drop=("node",))
    assert old_t[0].returncode == 1
    assert old_t[0].stdout == "", "DEFECT 1: nothing on stdout"
    assert old_t[0].stderr == "", "DEFECT 1: nothing on stderr either"
    _agree(old_t, new_t, "no-node")


def test_the_dry_run_still_needs_node_because_the_lookup_is_above_it(tmp_path) -> None:
    """`:99` runs before `:107`, so `--dry-run` inherits DEFECT 1 wholesale: a
    preview that cannot preview anything without a toolchain it never names."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*NATIVE, "--dry-run"), drop=("node",))
    assert old_t[0].returncode == 1
    assert (old_t[0].stdout, old_t[0].stderr) == ("", "")
    _agree(old_t, new_t, "dry-run-no-node")


# --------------------------------------------------------------------------- The happy path ---------------------------------------------------------------------------


def test_a_native_linux_build_runs_every_step_in_order(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE)
    old = old_t[0]
    assert old.returncode == 0, old.stderr
    calls = [line.split("\t") for line in old_t[1].splitlines()]
    assert [c[0] for c in calls] == [
        "FAKEBIN uname",  # common.sh:509, CI_OS
        "FAKEBIN uname",  # common.sh:510, CI_ARCH
        "FAKEBIN node",  # --version, for the log line
        "FAKEBIN node",  # bundle.mjs
        "FAKEBIN prepare-cli-assets.sh",
        "FAKEBIN node",  # --experimental-sea-config
        "FAKEBIN strip",
        "FAKEBIN node",  # sea-inject/cli.mjs
        "FAKEBIN node",  # sea-inject/verify.mjs
        "FAKEBIN uname",  # detect_os
        "FAKEBIN uname",  # detect_arch
        "FAKEBIN rdc-linux-x64",  # --version smoke test
        "FAKEBIN rdc-linux-x64",  # doctor
    ], old_t[1]
    assert "\u2713 CLI SEA build complete: " in old.stderr
    assert "\u2713 Smoke test (doctor) passed\n" in old.stderr
    assert set(old_t[2]) == {
        "dist/cli/rdc-linux-x64",
        "dist/cli/rdc-linux-x64.sha256",
        "packages/cli/dist/cli-bundle.cjs",
        "packages/cli/dist/sea-prep.blob",
    }
    assert old_t[2]["dist/cli/rdc-linux-x64"][1] is True, "chmod +x must have happened"
    _agree(old_t, new_t, "native-linux")


def test_the_injector_argv_carries_the_sentinel_fuse_and_no_macho_flag_on_linux(
    tmp_path,
) -> None:
    """The fuse is the one argument whose corruption is invisible in the log."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE)
    inject = [line for line in old_t[1].splitlines() if "sea-inject/cli.mjs" in line]
    assert len(inject) == 1
    fields = inject[0].split("\t")
    assert fields[1] == str(root / ".ci/scripts/build/sea-inject/cli.mjs")
    assert fields[2] == str(root / "dist/cli/rdc-linux-x64")
    assert fields[3] == "NODE_SEA_BLOB"
    assert fields[4] == str(root / "packages/cli/dist/sea-prep.blob")
    assert fields[5:] == [
        "--sentinel-fuse",
        "NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2",
    ]
    verify = [line for line in old_t[1].splitlines() if "sea-inject/verify.mjs" in line]
    assert len(verify) == 1
    assert verify[0].endswith("\t--sentinel-fuse\tNODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2")
    assert "--macho-segment-name" not in old_t[1]
    _agree(old_t, new_t, "inject-argv")


def test_mac_signs_twice_never_strips_and_names_the_macho_segment(tmp_path) -> None:
    """Order matters and is asserted: the signature is REMOVED before the strip
    would have run and re-applied after the injection, never the other way."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--platform", "mac", "--arch", "arm64"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    kinds = [line.split("\t")[0] for line in old_t[1].splitlines()]
    assert kinds.count("FAKEBIN codesign") == 2
    assert "FAKEBIN strip" not in kinds, "macOS strip corrupts __LINKEDIT; it must not run"
    codesign_calls = [line for line in old_t[1].splitlines() if line.startswith("FAKEBIN codesign")]
    assert codesign_calls[0].split("\t")[1] == "--remove-signature"
    assert codesign_calls[1].split("\t")[1:3] == ["-s", "-"]
    assert "\t--macho-segment-name\tNODE_SEA" in old_t[1]
    assert "\u2713 Skipping smoke tests (cross-platform build)\n" in old_t[0].stderr
    _agree(old_t, new_t, "mac")


def test_win_appends_exe_and_neither_strips_nor_signs(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--platform", "win", "--arch", "x64"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "dist/cli/rdc-win-x64.exe" in old_t[2]
    kinds = [line.split("\t")[0] for line in old_t[1].splitlines()]
    assert "FAKEBIN strip" not in kinds
    assert "FAKEBIN codesign" not in kinds
    _agree(old_t, new_t, "win")


def test_a_relative_output_resolves_against_packages_cli_not_the_cwd(tmp_path) -> None:
    """`:143` chdirs, and `--output` is used AFTER it. A port that resolved the
    flag against the invocation directory would write to a different tree and
    still print the same log lines."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=(*NATIVE, "--output", "out"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert (root / "packages" / "cli" / "out" / "rdc-linux-x64").is_file()
    assert not (root / "out").exists()
    assert "\u2713   Output: out/rdc-linux-x64\n" in old_t[0].stderr
    _agree(old_t, new_t, "relative-output")


def test_the_size_lines_report_real_byte_counts(tmp_path) -> None:
    """Four `wc -c` sites are `stat().st_size` in the port. If either side were
    reading a different file the digits would disagree here."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE)
    assert "\u2713 Bundle created: 17 bytes\n" in old_t[0].stderr
    assert "\u2713 SEA blob created: 20 bytes\n" in old_t[0].stderr
    size = (root / "dist" / "cli" / "rdc-linux-x64").stat().st_size
    assert "\u2713 Binary size: %dMB (%d bytes)\n" % (size // 1024 // 1024, size) in old_t[0].stderr
    _agree(old_t, new_t, "sizes")


def test_the_checksum_is_written_beside_the_binary_with_a_bare_name(tmp_path) -> None:
    """`(cd "$OUTPUT_DIR" && sha256sum "$BINARY_NAME")`: the subshell is what
    keeps a PATH out of the `.sha256`, and `sha256sum -c` later depends on it."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE)
    body = old_t[2]["dist/cli/rdc-linux-x64.sha256"][0]
    assert body.endswith("  rdc-linux-x64\n")
    assert "/" not in body
    assert "\u2713 Checksum: %s\n" % body.rstrip("\n") in old_t[0].stderr
    _agree(old_t, new_t, "checksum")


# --------------------------------------------------------------------------- DEFECT 2 and DEFECT 3: two undeclared tools, two different endings ---------------------------------------------------------------------------


def test_a_missing_strip_dies_with_bashs_own_message_and_127(tmp_path) -> None:
    """DEFECT 2. No `require_cmd strip` anywhere, so the diagnosis comes from the
    shell, one line after a `→ Stripping debug symbols...` that already claimed
    the step had started."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, drop=("strip",))
    assert old_t[0].returncode == 127
    assert "\u2192 Stripping debug symbols...\n" in old_t[0].stderr
    assert old_t[0].stderr.endswith("strip: command not found\n")
    assert "Required command" not in old_t[0].stderr
    _agree(old_t, new_t, "no-strip", lines=True)


def test_no_checksum_tool_is_a_warning_and_the_build_still_passes(tmp_path) -> None:
    """DEFECT 3. The artifact ships with nothing to verify it against and the
    step is green."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, drop=("sha256sum",))
    assert old_t[0].returncode == 0
    assert "\u26a0 No sha256sum or shasum available - skipping checksum\n" in old_t[0].stderr
    assert "Checksum:" not in old_t[0].stderr
    assert "dist/cli/rdc-linux-x64.sha256" not in old_t[2]
    assert "\u2713 CLI SEA build complete: " in old_t[0].stderr
    _agree(old_t, new_t, "no-checksum-tool")


# --------------------------------------------------------------------------- The version seam ---------------------------------------------------------------------------


def test_a_release_build_without_a_version_refuses(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=NATIVE, env_overrides={"RELEASE_BUILD": "true", "CLI_VERSION": ""}
    )
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith(
        "\u2717 RELEASE_BUILD=true but CLI_VERSION is empty; "
        "refusing to build a publishable artifact without a version\n"
    )
    _agree(old_t, new_t, "release-no-version")


def test_a_release_build_refuses_the_placeholder_with_both_messages(tmp_path) -> None:
    """inject-env's own refusal reaches stderr FIRST, then this script's. Two
    lines, two authors, and the order is the observable."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=NATIVE,
        env_overrides={"RELEASE_BUILD": "true", "CLI_VERSION": "0.0.0-dev"},
    )
    assert old_t[0].returncode == 1
    tail = old_t[0].stderr.splitlines()[-2:]
    assert tail == [
        (
            "inject-env.sh: version resolved to 0.0.0-dev under --strict "
            "(did the checkout include tags?)"
        ),
        "\u2717 Release build refused: CLI_VERSION='0.0.0-dev' is not a publishable version",
    ]
    _agree(old_t, new_t, "release-placeholder")


def test_a_release_build_refuses_a_non_numeric_version(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=NATIVE, env_overrides={"RELEASE_BUILD": "true", "CLI_VERSION": "latest"}
    )
    assert old_t[0].returncode == 1
    assert "is not a dotted numeric version, refusing under --strict" in old_t[0].stderr
    _agree(old_t, new_t, "release-latest")


def test_a_release_build_with_a_real_version_builds_and_compares_it(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=NATIVE,
        env_overrides={
            "RELEASE_BUILD": "true",
            "CLI_VERSION": "1.2.3",
            "FAKE_RDC_VERSION": "1.2.3",
            "FAKE_DOCTOR_JSON": doctor_json(cli_version="1.2.3"),
        },
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "\u2713 CLI version: 1.2.3\n" in old_t[0].stderr
    assert "\u2713 CLI version: 1.2.3 (matches build version)\n" in old_t[0].stderr
    _agree(old_t, new_t, "release-good")


def test_release_build_is_a_string_test_so_one_is_not_true(tmp_path) -> None:
    """`[[ "${RELEASE_BUILD:-}" == "true" ]]`. `RELEASE_BUILD=1` takes the DEV
    branch and quietly builds a 0.0.0-dev artifact on what the caller believed
    was a release path."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=NATIVE,
        env_overrides={
            "RELEASE_BUILD": "1",
            "CLI_VERSION": "",
            "FAKE_DOCTOR_JSON": doctor_json(cli_version="0.0.0-dev"),
            "FAKE_RDC_VERSION": "0.0.0-dev",
        },
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "\u2713 CLI version: 0.0.0-dev\n" in old_t[0].stderr
    _agree(old_t, new_t, "release-build-is-one")


def test_the_injected_version_reaches_the_bundler_environment(tmp_path) -> None:
    """The whole reason inject-env is SOURCED rather than run: `node bundle.mjs`
    must inherit `CLI_VERSION`. Proved by making the fake node write it out."""
    root = fixture(tmp_path)
    probe = root / "fixture-bin" / "node"
    for side, argv in (
        ("old", [BASH, str(root / TWIN_REL)]),
        ("new", [sys.executable, str(root / PORT_REL)]),
    ):
        _reset(root)
        env = {
            "PATH": scratch_bin(root),
            "HOME": os.environ.get("HOME", "/tmp"),
            "NO_COLOR": "1",
            "PYTHONPATH": str(root / ".ci"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "FAKE_CALL_LOG": str(root / ("%s-calls.log" % side)),
            "FAKE_DOCTOR_JSON": doctor_json(cli_version="4.5.6"),
            "RELEASE_BUILD": "true",
            "CLI_VERSION": "4.5.6",
            "FAKE_RDC_VERSION": "4.5.6",
        }
        probe.write_text(
            FAKE_NODE.replace(
                "    bundle.mjs)",
                "    bundle.mjs)\n        printf '%s %s %s\\n' \"$CLI_VERSION\" "
                '"$APP_VERSION" "$TAG" >"$FAKE_CALL_LOG.env"',
            ),
            encoding="utf-8",
        )
        probe.chmod(0o755)
        proc = subprocess.run(
            [*argv, *NATIVE], cwd=str(root), capture_output=True, text=True, env=env, check=False
        )
        assert proc.returncode == 0, proc.stderr
        seen = (root / ("%s-calls.log.env" % side)).read_text(encoding="utf-8")
        assert seen == "4.5.6 4.5.6 4.5.6\n", "%s: %r" % (side, seen)


# --------------------------------------------------------------------------- The required-file gates and status propagation ---------------------------------------------------------------------------


def test_a_bundler_that_writes_nothing_is_caught_by_require_file(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_NODE_BUNDLE_WRITES": "0"})
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith(
        "\u2717 Required file '%s' does not exist\n" % (root / "packages/cli/dist/cli-bundle.cjs")
    )
    _agree(old_t, new_t, "no-bundle")


def test_a_sea_config_that_writes_no_blob_is_caught_too(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_NODE_SEA_WRITES": "0"})
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith(
        "\u2717 Required file '%s' does not exist\n" % (root / "packages/cli/dist/sea-prep.blob")
    )
    _agree(old_t, new_t, "no-blob")


def test_a_failing_bundler_propagates_its_own_status_not_a_flattened_one(tmp_path) -> None:
    """A real exit code flattened to 1 is a defect class this campaign keeps
    finding. This script does not have it, and neither may the port."""
    root = fixture(tmp_path)
    for code in ("3", "42"):
        old_t, new_t = run_both(
            root,
            args=NATIVE,
            env_overrides={"FAKE_NODE_BUNDLE_RC": code, "FAKE_NODE_BUNDLE_WRITES": "0"},
        )
        assert old_t[0].returncode == int(code)
        _agree(old_t, new_t, "bundle-rc-%s" % code)


def test_a_failing_asset_step_propagates_its_status(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_ASSETS_RC": "7"})
    assert old_t[0].returncode == 7
    _agree(old_t, new_t, "assets-rc")


def test_a_failing_injector_propagates_its_status(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_NODE_RC": "9"})
    assert old_t[0].returncode == 9
    assert "\u2192 Injecting SEA blob into binary...\n" in old_t[0].stderr
    _agree(old_t, new_t, "inject-rc")


# --------------------------------------------------------------------------- The smoke tests ---------------------------------------------------------------------------


def test_a_failing_version_smoke_test_reports_its_code(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_RDC_VERSION_RC": "4"})
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith("\u2717 Smoke test (--version) failed (exit code: 4)\n")
    _agree(old_t, new_t, "version-smoke-fail")


def test_defect_4_the_version_test_cannot_tell_a_signal_from_a_verdict(tmp_path) -> None:
    """137 is SIGKILL. `doctor` decodes that; `--version`, twelve lines earlier,
    reports it as an exit code and says nothing about the kill."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_RDC_VERSION_RC": "137"})
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith("\u2717 Smoke test (--version) failed (exit code: 137)\n")
    assert "KILLED by signal" not in old_t[0].stderr
    _agree(old_t, new_t, "version-smoke-137")


def test_doctor_killed_by_a_signal_is_decoded(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_DOCTOR_RC": "137"})
    assert old_t[0].returncode == 1
    assert (
        "\u2717 Doctor was KILLED by signal 9 (raw 137), so it reported no verdict\n"
        in old_t[0].stderr
    )
    _agree(old_t, new_t, "doctor-137")


def test_doctor_exit_three_is_an_unexpected_failure(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_DOCTOR_RC": "3"})
    assert old_t[0].returncode == 1
    assert "\u2717 Doctor command failed unexpectedly (exit code: 3)\n" in old_t[0].stderr
    assert old_t[0].stdout.endswith('"value": "ok"}]}\n'), old_t[0].stdout
    assert '{"Environment"' in old_t[0].stdout
    _agree(old_t, new_t, "doctor-3")


def test_doctor_exit_two_is_accepted(tmp_path) -> None:
    """`-le 2`: CI has no auth and no renet, so "some checks failed" is expected."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_DOCTOR_RC": "2"})
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert (
        "\u2713 Doctor exited with code 2 (expected in CI without auth/renet)\n" in old_t[0].stderr
    )
    _agree(old_t, new_t, "doctor-2")


def test_a_silent_doctor_falls_into_the_failure_arm_even_at_exit_zero(tmp_path) -> None:
    """`-le 2` AND `-n "$DOCTOR_OUTPUT"`; an empty verdict is not a verdict."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_DOCTOR_JSON": ""})
    assert old_t[0].returncode == 1
    assert "\u2717 Doctor command failed unexpectedly (exit code: 0)\n" in old_t[0].stderr
    _agree(old_t, new_t, "doctor-empty")


def test_doctor_output_that_is_not_json_is_dumped_and_refused(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=NATIVE, env_overrides={"FAKE_DOCTOR_JSON": "not json at all"}
    )
    assert old_t[0].returncode == 1
    assert "\u2717 Doctor output is not valid JSON\n" in old_t[0].stderr
    assert old_t[0].stdout.endswith("not json at all\n")
    _agree(old_t, new_t, "doctor-not-json")


def test_a_non_sea_install_method_refuses(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=NATIVE, env_overrides={"FAKE_DOCTOR_JSON": doctor_json(install_method="npm")}
    )
    assert old_t[0].returncode == 1
    assert "\u2717 SEA mode check failed: 'npm'\n" in old_t[0].stderr
    _agree(old_t, new_t, "install-method")


def test_a_version_mismatch_refuses_and_names_both_versions(tmp_path) -> None:
    """The check release 31154305287 needed: binaries built as 1.2.16 shipped
    under the label 1.2.17 and the step said nothing."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=NATIVE,
        env_overrides={
            "RELEASE_BUILD": "true",
            "CLI_VERSION": "1.2.17",
            "FAKE_DOCTOR_JSON": doctor_json(cli_version="1.2.16"),
        },
    )
    assert old_t[0].returncode == 1
    assert (
        "\u2717 CLI version mismatch: built for '1.2.17' but the binary reports '1.2.16'\n"
        in old_t[0].stderr
    )
    _agree(old_t, new_t, "version-mismatch")


def test_a_null_reported_version_refuses_before_the_comparison(tmp_path) -> None:
    root = fixture(tmp_path)
    body = json.loads(doctor_json())
    body["Environment"][1]["value"] = None
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_DOCTOR_JSON": json.dumps(body)})
    assert old_t[0].returncode == 1
    assert "\u2717 CLI version check failed: doctor reported 'null'\n" in old_t[0].stderr
    _agree(old_t, new_t, "version-null")


def test_a_missing_cli_version_row_reports_an_empty_string(tmp_path) -> None:
    root = fixture(tmp_path)
    body = json.loads(doctor_json())
    body["Environment"] = [row for row in body["Environment"] if row["name"] != "CLI version"]
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_DOCTOR_JSON": json.dumps(body)})
    assert old_t[0].returncode == 1
    assert "\u2717 CLI version check failed: doctor reported ''\n" in old_t[0].stderr
    _agree(old_t, new_t, "version-missing-row")


def test_a_bad_node_status_refuses(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=NATIVE, env_overrides={"FAKE_DOCTOR_JSON": doctor_json(node_status="warn")}
    )
    assert old_t[0].returncode == 1
    assert "\u2717 Node.js check failed: status='warn'\n" in old_t[0].stderr
    _agree(old_t, new_t, "node-status")


def test_a_corrupt_embedded_asset_refuses_and_prints_every_offender(tmp_path) -> None:
    """The one RUNTIME check a shredded blob cannot pass. Its detail line goes to
    STDOUT, not stderr, which is itself worth pinning."""
    root = fixture(tmp_path)
    corrupt = [
        {"name": "linux-amd64", "value": "corrupt \u2014 sha256 mismatch"},
        {"name": "linux-arm64", "value": "ok"},
        {"name": "darwin-arm64", "value": "corrupt \u2014 unreadable"},
    ]
    old_t, new_t = run_both(
        root, args=NATIVE, env_overrides={"FAKE_DOCTOR_JSON": doctor_json(renet=corrupt)}
    )
    assert old_t[0].returncode == 1
    assert (
        "\u2717 Embedded renet asset integrity check FAILED (corrupt/unreachable blob)\n"
        in old_t[0].stderr
    )
    assert old_t[0].stdout.endswith(
        "  linux-amd64: corrupt \u2014 sha256 mismatch\n  darwin-arm64: corrupt \u2014 unreadable\n"
    ), old_t[0].stdout
    _agree(old_t, new_t, "embed-corrupt")


def test_an_absent_renet_list_is_not_a_corruption(tmp_path) -> None:
    """`.Renet[]?` -- the `?` is why a doctor with no Renet section reports 0
    rather than dying. A port that dropped it would fail the build on a shape
    that is merely different."""
    root = fixture(tmp_path)
    body = json.loads(doctor_json())
    del body["Renet"]
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_DOCTOR_JSON": json.dumps(body)})
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "\u2713 Embedded renet asset read back and sha256-verified\n" in old_t[0].stderr
    _agree(old_t, new_t, "no-renet-section")


# --------------------------------------------------------------------------- DEFECT 5, and the cross-build guard that hides it ---------------------------------------------------------------------------


def test_an_unvalidated_platform_builds_a_nonsense_name(tmp_path) -> None:
    """DEFECT 5. `--platform banana` is never checked; the build succeeds, names
    the artifact `rdc-banana-x64`, and the smoke tests -- the one thing that
    would have noticed -- are skipped BECAUSE the platform does not match."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--platform", "banana", "--arch", "x64"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "dist/cli/rdc-banana-x64" in old_t[2]
    assert "\u2713 Skipping smoke tests (cross-platform build)\n" in old_t[0].stderr
    assert "FAKEBIN strip" not in old_t[1]
    _agree(old_t, new_t, "banana")


def test_an_arch_mismatch_skips_the_smoke_tests_without_calling_detect_arch(
    tmp_path,
) -> None:
    """`&&` SHORT-CIRCUITS. When the platform already disagrees, `detect_arch`
    never runs, so there is exactly ONE `uname` in the log instead of two."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--platform", "win", "--arch", "x64"))
    tail = [line for line in old_t[1].splitlines() if line.startswith("FAKEBIN uname")]
    assert tail == ["FAKEBIN uname\t-s", "FAKEBIN uname\t-m", "FAKEBIN uname\t-s"], tail
    _agree(old_t, new_t, "short-circuit")


def test_a_matching_platform_with_a_different_arch_calls_both_unames(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--platform", "linux", "--arch", "arm64"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    tail = [line for line in old_t[1].splitlines() if line.startswith("FAKEBIN uname")]
    assert tail == [
        "FAKEBIN uname\t-s",
        "FAKEBIN uname\t-m",
        "FAKEBIN uname\t-s",
        "FAKEBIN uname\t-m",
    ], tail
    assert "\u2713 Skipping smoke tests (cross-platform build)\n" in old_t[0].stderr
    _agree(old_t, new_t, "arch-mismatch")


def test_an_unknown_detect_os_never_matches_and_smoke_tests_are_skipped(tmp_path) -> None:
    """`detect_os`'s fail-open `unknown` arm. It reads like an answer and it is
    compared against `linux` as though it were one."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=NATIVE, env_overrides={"FAKE_UNAME_S": "Plan9"})
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "\u2713 Skipping smoke tests (cross-platform build)\n" in old_t[0].stderr
    _agree(old_t, new_t, "detect-os-unknown")


# --------------------------------------------------------------------------- The proof the differential can fail ---------------------------------------------------------------------------


def test_a_planted_defect_is_caught(tmp_path) -> None:
    """Four separate plants, each caught by a DIFFERENT assertion, so a green
    suite cannot be green because one comparison does all the work."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")

    # 1. Wrong sentinel fuse: invisible on both streams, visible only in argv.
    root = fixture(
        tmp_path / "a",
        port_source=source.replace(
            'SENTINEL_FUSE = "NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2"',
            'SENTINEL_FUSE = "NODE_SEA_FUSE_0000000000000000000000000000000"',
        ),
    )
    old_t, new_t = run_both(root, args=NATIVE)
    assert old_t[0].returncode == new_t[0].returncode == 0
    assert old_t[0].stderr == new_t[0].stderr, "the plant must be invisible on stderr"
    assert new_t[1] != old_t[1], "the call log must catch it"

    # 2. Strip skipped: an artifact and a call-log difference, no stream change other than the one log line.
    root = fixture(
        tmp_path / "b",
        port_source=source.replace('if platform_name == "linux":', "if False:"),
    )
    old_t, new_t = run_both(root, args=NATIVE)
    assert "FAKEBIN strip" in old_t[1]
    assert "FAKEBIN strip" not in new_t[1]

    # 3. The version comparison downgraded to the non-empty test it used to be.
    root = fixture(
        tmp_path / "c",
        port_source=source.replace("    if reported_version != expected_version:", "    if False:"),
    )
    old_t, new_t = run_both(
        root,
        args=NATIVE,
        env_overrides={
            "RELEASE_BUILD": "true",
            "CLI_VERSION": "1.2.17",
            "FAKE_DOCTOR_JSON": doctor_json(cli_version="1.2.16"),
        },
    )
    assert old_t[0].returncode == 1
    assert new_t[0].returncode == 0, "the plant must actually change the verdict"

    # 4. The `&&` short-circuit turned into eager evaluation: same verdict, same streams, one extra `uname` in the log.
    root = fixture(
        tmp_path / "d",
        port_source=source.replace(
            "    if platform_name == native_platform_name() and arch == detect_arch():",
            "    _eager = (native_platform_name(), detect_arch())\n"
            "    if platform_name == _eager[0] and arch == _eager[1]:",
        ),
    )
    old_t, new_t = run_both(root, args=("--platform", "win", "--arch", "x64"))
    assert old_t[0].returncode == new_t[0].returncode == 0
    assert old_t[0].stderr == new_t[0].stderr
    assert old_t[1].count("FAKEBIN uname") == 3
    assert new_t[1].count("FAKEBIN uname") == 4


# --------------------------------------------------------------------------- Unit-level: the helpers, exercised directly ---------------------------------------------------------------------------


def test_binary_name_appends_exe_only_for_win() -> None:
    assert port.binary_name("linux", "x64") == "rdc-linux-x64"
    assert port.binary_name("mac", "arm64") == "rdc-mac-arm64"
    assert port.binary_name("win", "x64") == "rdc-win-x64.exe"
    assert port.binary_name("banana", "x64") == "rdc-banana-x64", "DEFECT 5, at the helper level"


def test_platform_and_arch_cases_carry_the_twins_asymmetry() -> None:
    assert port.platform_from_uname("Linux") == "linux"
    assert port.platform_from_uname("Linux-6.18") == "linux", "`Linux*` is a glob"
    assert port.platform_from_uname("Darwin24.0") == "mac"
    for name in ("MINGW64_NT-10.0", "MSYS_NT-10.0", "CYGWIN_NT-10.0"):
        assert port.platform_from_uname(name) == "win"
    assert port.platform_from_uname("Plan9") is None
    assert port.arch_from_uname("x86_64") == "x64"
    assert port.arch_from_uname("amd64") == "x64"
    assert port.arch_from_uname("aarch64") == "arm64"
    assert port.arch_from_uname("arm64") == "arm64"
    assert port.arch_from_uname("x86_64h") is None, "the arch case has NO glob"


def test_the_exec_failure_shapes_are_the_two_bash_uses() -> None:
    message, code = port._exec_failure("strip", 175)
    assert message.endswith("line 175: strip: command not found")
    assert code == 127
    message, code = port._exec_failure("/no/such/thing", 150)
    assert message.endswith("line 150: /no/such/thing: No such file or directory")
    assert code == 127


def test_console_root_is_this_checkout() -> None:
    assert port.console_root() == ROOT
    assert port.script_dir(ROOT) == ROOT / ".ci" / "scripts" / "build"


def test_the_module_reads_env_at_the_call_site() -> None:
    """The env-registry alias trap, confirmed in waves 15, 18, 45 and 46: a name
    read through a dict alias is invisible to the manifest scanner."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    assert 'os.environ.get("RELEASE_BUILD", "")' in source
    assert 'os.environ.get("CLI_VERSION", "")' in source
    assert "dict(os.environ)" not in source
    assert "environ.copy()" not in source
