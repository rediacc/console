"""Differential: `rediacc_ci.build.prepare_cli_assets` against its twin
`.ci/scripts/build/prepare-cli-assets.sh`.

THE ARTIFACTS ARE THE SUBJECT, NOT THE LOG. This script's whole output is three
files -- `dist/assets/renet-metadata.json`, `dist/assets/THIRD_PARTY_LICENSES`
and `packages/cli/sea-config.generated.json`, plus the copied binaries -- and
its stderr says almost nothing about them. Every case therefore compares the
FULL byte content of everything the run wrote under `packages/cli/`, not just
the three streams. A port that logged the right sentences and emitted different
JSON would pass on stdout, stderr and exit code alone;
`test_a_planted_defect_is_caught_only_by_the_artifacts` plants exactly that.

`date` IS FAKED, AND IT HAS TO BE. `:171` stamps `generatedAt` with
`date -u +%Y-%m-%dT%H:%M:%SZ`. That is the only non-deterministic byte in the
metadata, and two sides run seconds apart, so without a frozen `date` the two
files differ for a reason that has nothing to do with the port. The port shells
out to the same `date` for that reason; a `datetime.now()` implementation could
not be pinned on both sides at once.

`npx` IS FAKED because `:190` runs a real `tsx` program that walks the whole
dependency tree and reaches the network. `jq`, `sha256sum`, `cp` and `stat` are
REAL: they are deterministic, and the point of the comparison is the bytes they
produce.

A PATH THAT REPLACES, NEVER PREPENDS.
`test_the_scratch_path_cannot_reach_a_real_npx` asserts the seal before anything
is driven.

FAKES RECORD TO `$FAKE_CALL_LOG`, NEVER TO STDOUT, and never to the stdout of
anything whose stdout is an artifact. A prior wave's fake `jq` logged to stdout
and corrupted the very JSON the twin was writing.

`$0` IS MASKED TO `<SELF>`; nothing else is. Streams are compared separately.

K=5 LEDGER: `.ci/shadow/w7p6-prepare-cli-assets.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.build import prepare_cli_assets as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/prepare-cli-assets.sh"
PORT_REL = ".ci/rediacc_ci/build/prepare_cli_assets.py"
COMMON_REL = ".ci/scripts/lib/common.sh"

VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/build/__init__.py",
)

BASH = shutil.which("bash") or "/bin/bash"

# Real, deterministic, and genuinely used by the twin. Anything not listed is
# ABSENT from the scratch PATH, including `npx`, `shasum` and `node`.
PATH_MINIMUM = ("dirname", "uname", "jq", "cp", "mkdir", "stat", "sha256sum", "cut", "wc")

# `:171`, frozen. Recorded to the call log on STDERR-adjacent storage only; its
# STDOUT is the timestamp itself and must stay clean.
FROZEN_STAMP = "2026-01-02T03:04:05Z"
FAKE_DATE = """#!/bin/bash
{
    printf 'FAKEBIN date'
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
printf '%s\\n' '__STAMP__'
"""

# `:190-192`. Records its argv and, unless told otherwise, writes nothing --
# which is DEFECT 4's input.
FAKE_NPX = """#!/bin/bash
{
    printf 'FAKEBIN npx'
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
if [[ -n "${FAKE_NPX_WRITES:-}" ]]; then
    out=""
    prev=""
    for a in "$@"; do
        if [[ "$prev" == "--output" ]]; then out="$a"; fi
        prev="$a"
    done
    [[ -n "$out" ]] && printf 'LICENSE TEXT\\n' >"$out"
fi
exit "${FAKE_NPX_RC:-0}"
"""

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))

RENET_BINARIES = (
    "renet-linux-amd64",
    "renet-linux-arm64",
    "renet-darwin-amd64",
    "renet-darwin-arm64",
    "renet-windows-amd64.exe",
    "renet-windows-arm64.exe",
)


def fixture(
    tmp_path: pathlib.Path,
    *,
    port_source: str | None = None,
    binaries: tuple[str, ...] = RENET_BINARIES,
    package_json: str = '{"name": "@rediacc/cli", "version": "9.9.9"}\n',
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

    bin_dir = root / "private" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in binaries:
        target = bin_dir / name
        target.write_text("%s payload\n" % name, encoding="utf-8")
        target.chmod(0o755)

    cli = root / "packages" / "cli"
    (cli / "src" / "data").mkdir(parents=True, exist_ok=True)
    (cli / "package.json").write_text(package_json, encoding="utf-8")
    (cli / "src" / "data" / "third-party-credits.json").write_text(
        '{"components": []}\n', encoding="utf-8"
    )
    (root / "scripts" / "gen").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "gen" / "generate-third-party-licenses.ts").write_text(
        "// placeholder\n", encoding="utf-8"
    )
    return root


def scratch_bin(root: pathlib.Path, *, drop_hash_tools: bool = False) -> str:
    """The ONLY directory on PATH for either side."""
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
        link = stub / name
        if drop_hash_tools and name == "sha256sum":
            if link.exists() or link.is_symlink():
                link.unlink()
            continue
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        if not link.exists():
            link.symlink_to(real)
    (stub / "date").write_text(FAKE_DATE.replace("__STAMP__", FROZEN_STAMP), encoding="utf-8")
    (stub / "date").chmod(0o755)
    (stub / "npx").write_text(FAKE_NPX, encoding="utf-8")
    (stub / "npx").chmod(0o755)
    return str(stub)


def _run(
    root: pathlib.Path,
    side: str,
    *,
    args: tuple[str, ...] = (),
    drop_hash_tools: bool = False,
    env_overrides: dict[str, str | None] | None = None,
):
    call_log = root / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        # REPLACED, never prepended.
        "PATH": scratch_bin(root, drop_hash_tools=drop_hash_tools),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_NPX_WRITES": "1",
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


def _artifacts(root: pathlib.Path) -> dict[str, str]:
    """Everything the run wrote under `packages/cli/`, by relative path."""
    out: dict[str, str] = {}
    cli = root / "packages" / "cli"
    for path in sorted(cli.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        if rel.endswith(("src/data/third-party-credits.json", "package.json")):
            continue
        out[rel] = path.read_text(encoding="utf-8", errors="replace")
    return out


def _reset(root: pathlib.Path) -> None:
    shutil.rmtree(root / "packages" / "cli" / "dist", ignore_errors=True)
    generated = root / "packages" / "cli" / "sea-config.generated.json"
    if generated.exists():
        generated.unlink()


def run_both(root: pathlib.Path, **kw):
    _reset(root)
    old, old_calls = _run(root, "old", **kw)
    old_files = _artifacts(root)
    _reset(root)
    new, new_calls = _run(root, "new", **kw)
    new_files = _artifacts(root)
    return (old, old_calls, old_files), (new, new_calls, new_files)


def _mask(text: str) -> str:
    return SELF_RE.sub("<SELF>", text)


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


# ---------------------------------------------------------------------------
# The control on the control
# ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_npx(tmp_path) -> None:
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    assert shutil.which("npx", path=sealed) == str(root / "fixture-bin" / "npx")
    assert shutil.which("date", path=sealed) == str(root / "fixture-bin" / "date")
    assert shutil.which("node", path=sealed) is None, "a real node is reachable"
    assert shutil.which("tsx", path=sealed) is None
    assert shutil.which("shasum", path=sealed) is None


def test_the_frozen_date_really_is_what_lands_in_the_metadata(tmp_path) -> None:
    """If the fake `date` were bypassed on either side, every metadata comparison
    below would be comparing timestamps rather than the port. Pinned once here so
    a silent bypass fails LOUDLY instead of turning the suite vacuous."""
    root = fixture(tmp_path)
    old_t, _ = run_both(root, args=("--platform", "linux", "--arch", "x64"))
    meta = json.loads(old_t[2]["packages/cli/dist/assets/renet-metadata.json"])
    assert meta["generatedAt"] == FROZEN_STAMP


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def test_no_arguments_refuses_with_the_usage(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root)
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.startswith("\u2717 Usage: ")
    assert old_t[0].stderr.endswith(" --platform <linux|mac|win> --arch <x64|arm64>\n")
    assert old_t[2] == {}, "nothing should have been written"
    _agree(old_t, new_t, "no-args")


def test_one_flag_without_the_other_refuses(tmp_path) -> None:
    root = fixture(tmp_path)
    for args in (("--platform", "linux"), ("--arch", "x64")):
        old_t, new_t = run_both(root, args=args)
        assert old_t[0].returncode == 1
        assert "Usage: " in old_t[0].stderr
        _agree(old_t, new_t, "half-%s" % args[0])


def test_help_prints_usage_on_stdout_and_exits_zero(tmp_path) -> None:
    root = fixture(tmp_path)
    for flag in ("-h", "--help"):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 0
        assert old_t[0].stderr == ""
        assert old_t[0].stdout.endswith(" --platform <linux|mac|win> --arch <x64|arm64>\n")
        _agree(old_t, new_t, flag)


def test_an_unknown_option_refuses_and_names_it(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--nope",))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "\u2717 Unknown option: --nope\n"
    _agree(old_t, new_t, "unknown-option")


def test_a_flag_with_no_value_dies_the_way_set_u_does(tmp_path) -> None:
    root = fixture(tmp_path)
    for flag, line in (("--platform", 32), ("--arch", 36)):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 1
        assert old_t[0].stderr == "%s: line %d: $2: unbound variable\n" % (
            str(root / TWIN_REL),
            line,
        )
        _agree(old_t, new_t, flag)


# ---------------------------------------------------------------------------
# The three real platforms
# ---------------------------------------------------------------------------


def test_linux_embeds_both_linux_binaries_and_nothing_else(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--platform", "linux", "--arch", "x64"))
    old = old_t[0]
    assert old.returncode == 0, old.stderr
    assert old.stdout == ""
    assert set(old_t[2]) == {
        "packages/cli/dist/assets/renet-linux-amd64",
        "packages/cli/dist/assets/renet-linux-arm64",
        "packages/cli/dist/assets/renet-metadata.json",
        "packages/cli/dist/assets/third-party-credits.json",
        "packages/cli/dist/assets/THIRD_PARTY_LICENSES",
        "packages/cli/sea-config.generated.json",
    }
    meta = json.loads(old_t[2]["packages/cli/dist/assets/renet-metadata.json"])
    assert sorted(meta["binaries"]) == ["amd64", "arm64"], "linux-* keys lose their prefix"
    assert meta["version"] == "9.9.9"
    _agree(old_t, new_t, "linux-x64")


def test_mac_adds_its_own_darwin_binary(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--platform", "mac", "--arch", "arm64"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    meta = json.loads(old_t[2]["packages/cli/dist/assets/renet-metadata.json"])
    assert sorted(meta["binaries"]) == ["amd64", "arm64", "darwin-arm64"]
    assert "packages/cli/dist/assets/renet-darwin-arm64" in old_t[2]
    _agree(old_t, new_t, "mac-arm64")


def test_win_copies_the_exe_but_drops_the_extension_from_the_asset_key(tmp_path) -> None:
    """`:118-126`: the source path carries `.exe` and the SEA asset key never
    does, so the copy renames. Both the destination name and the metadata key
    are asserted, because getting only one right is the plausible mistake."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--platform", "win", "--arch", "x64"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "packages/cli/dist/assets/renet-windows-amd64" in old_t[2]
    assert "packages/cli/dist/assets/renet-windows-amd64.exe" not in old_t[2]
    meta = json.loads(old_t[2]["packages/cli/dist/assets/renet-metadata.json"])
    assert "windows-amd64" in meta["binaries"]
    config = json.loads(old_t[2]["packages/cli/sea-config.generated.json"])
    assert config["assets"]["renet-windows-amd64"] == "dist/assets/renet-windows-amd64"
    _agree(old_t, new_t, "win-x64")


def test_a_missing_renet_binary_refuses_naming_the_path(tmp_path) -> None:
    root = fixture(tmp_path, binaries=("renet-linux-amd64",))
    old_t, new_t = run_both(root, args=("--platform", "linux", "--arch", "x64"))
    assert old_t[0].returncode == 1
    assert "\u2717 Missing renet binary: " in old_t[0].stderr
    assert old_t[0].stderr.rstrip().endswith("private/bin/renet-linux-arm64")
    _agree(old_t, new_t, "missing-binary")


def test_renet_version_overrides_the_package_json(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--platform", "linux", "--arch", "x64"),
        env_overrides={"RENET_VERSION": "7.7.7-rc1"},
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    meta = json.loads(old_t[2]["packages/cli/dist/assets/renet-metadata.json"])
    assert meta["version"] == "7.7.7-rc1"
    assert "FAKEBIN date" in old_t[1]
    _agree(old_t, new_t, "renet-version")


def test_an_empty_renet_version_falls_through_to_jq(tmp_path) -> None:
    """`${RENET_VERSION:-...}` fires on SET-BUT-EMPTY as well as unset."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--platform", "linux", "--arch", "x64"),
        env_overrides={"RENET_VERSION": ""},
    )
    meta = json.loads(old_t[2]["packages/cli/dist/assets/renet-metadata.json"])
    assert meta["version"] == "9.9.9"
    _agree(old_t, new_t, "empty-renet-version")


def test_a_package_json_with_no_version_yields_the_string_null(tmp_path) -> None:
    """jq's `-r` prints `null` for an absent key and the twin embeds it as-is."""
    root = fixture(tmp_path, package_json='{"name": "@rediacc/cli"}\n')
    old_t, new_t = run_both(root, args=("--platform", "linux", "--arch", "x64"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    meta = json.loads(old_t[2]["packages/cli/dist/assets/renet-metadata.json"])
    assert meta["version"] == "null"
    _agree(old_t, new_t, "null-version")


def test_with_no_hashing_tool_the_run_refuses(tmp_path) -> None:
    """`file_sha256`'s `exit 1` is reached from a TOP-LEVEL `$( )`, where errexit
    DOES fire, so unlike `map_arch` this refusal really stops the script. The
    contrast with DEFECT 1 is the reason this case exists."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=("--platform", "linux", "--arch", "x64"), drop_hash_tools=True
    )
    assert old_t[0].returncode == 1
    assert "\u2717 No sha256sum or shasum available\n" in old_t[0].stderr
    _agree(old_t, new_t, "no-hash-tool")


# ---------------------------------------------------------------------------
# THIRD_PARTY_LICENSES
# ---------------------------------------------------------------------------


def test_a_failing_generator_writes_the_placeholder_and_does_not_fail_the_build(
    tmp_path,
) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--platform", "linux", "--arch", "x64"),
        env_overrides={"FAKE_NPX_RC": "1", "FAKE_NPX_WRITES": None},
    )
    assert old_t[0].returncode == 0, "generation is best-effort and non-fatal"
    assert "\u26a0 THIRD_PARTY_LICENSES generation failed; writing placeholder" in old_t[0].stderr
    assert old_t[2]["packages/cli/dist/assets/THIRD_PARTY_LICENSES"].startswith(
        "THIRD_PARTY_LICENSES generation failed at build time."
    )
    _agree(old_t, new_t, "licenses-placeholder")


def test_defect_a_generator_that_writes_nothing_is_still_reported_as_generated(
    tmp_path,
) -> None:
    """DEFECT 4. `:190` branches on the STATUS alone. A generator that exits 0
    without writing leaves the sea-config pointing at a file that is not there,
    and the log claims success."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--platform", "linux", "--arch", "x64"),
        env_overrides={"FAKE_NPX_WRITES": None},
    )
    assert old_t[0].returncode == 0, "the defect is that this is a PASS"
    assert "\u2713 Generated THIRD_PARTY_LICENSES\n" in old_t[0].stderr
    assert "packages/cli/dist/assets/THIRD_PARTY_LICENSES" not in old_t[2], (
        "the file the log claims was generated"
    )
    config = json.loads(old_t[2]["packages/cli/sea-config.generated.json"])
    assert config["assets"]["THIRD_PARTY_LICENSES"] == "dist/assets/THIRD_PARTY_LICENSES"
    _agree(old_t, new_t, "licenses-phantom")


# ---------------------------------------------------------------------------
# The defects in the validation
# ---------------------------------------------------------------------------


def test_defect_an_unknown_arch_is_reported_and_then_ignored(tmp_path) -> None:
    """DEFECT 1. `map_arch`'s `exit 1` runs two command substitutions deep, and
    bash does not inherit errexit into `$( )`, so the refusal is printed and
    discarded. On `--platform linux` the value is never used and the run
    completes with exit 0 and a fully valid artifact set."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--platform", "linux", "--arch", "bogus"))
    assert old_t[0].returncode == 0, "the defect is that this is a PASS"
    assert "\u2717 Unknown arch: bogus\n" in old_t[0].stderr
    assert "\u2713 CLI assets prepared successfully\n" in old_t[0].stderr
    assert "packages/cli/dist/assets/renet-metadata.json" in old_t[2]
    _agree(old_t, new_t, "bogus-arch-linux")


def test_defect_an_unknown_arch_on_mac_dies_with_the_wrong_diagnostic(tmp_path) -> None:
    """The other half of DEFECT 1: on `--platform mac` the empty `renet_arch`
    becomes the asset name `renet-darwin-`, which does not exist, so the run
    fails at `:128` complaining about a MISSING BINARY rather than about the
    argument it already rejected two lines earlier."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--platform", "mac", "--arch", "bogus"))
    assert old_t[0].returncode == 1
    assert "\u2717 Unknown arch: bogus\n" in old_t[0].stderr
    assert old_t[0].stderr.rstrip().endswith("private/bin/renet-darwin-")
    _agree(old_t, new_t, "bogus-arch-mac")


def test_defect_the_platform_is_never_validated(tmp_path) -> None:
    """DEFECT 2. The usage says `linux|mac|win`; the code tests only for `mac`
    and `win`, so anything else silently means "linux"."""
    root = fixture(tmp_path)
    banana_t, banana_new_t = run_both(root, args=("--platform", "banana", "--arch", "x64"))
    assert banana_t[0].returncode == 0, "the defect is that this is a PASS"
    assert "Preparing CLI embedded assets for banana-x64..." in banana_t[0].stderr
    _agree(banana_t, banana_new_t, "banana-platform")

    linux_t, _ = run_both(root, args=("--platform", "linux", "--arch", "x64"))
    assert banana_t[2] == linux_t[2], "identical output to --platform linux"


def test_defect_the_reported_asset_count_is_one_short(tmp_path) -> None:
    """DEFECT 3. `:211` uses `printf '%b'` with no trailing newline and counts
    with `wc -l`, so it reports SEPARATORS. `:213`, which feeds the same string
    to jq, uses `printf '%b\\n'` -- so the FILE is right and only the report is
    wrong. Both halves are asserted, on both platforms, because a fix to one
    without the other is the plausible half-repair."""
    root = fixture(tmp_path)
    for args, real_count in (
        (("--platform", "linux", "--arch", "x64"), 5),
        (("--platform", "mac", "--arch", "arm64"), 6),
    ):
        old_t, new_t = run_both(root, args=args)
        assert old_t[0].returncode == 0, old_t[0].stderr
        config = json.loads(old_t[2]["packages/cli/sea-config.generated.json"])
        assert len(config["assets"]) == real_count
        assert ("\u2713 Generated sea-config with %d assets\n" % (real_count - 1)) in old_t[
            0
        ].stderr
        _agree(old_t, new_t, "asset-count-%s" % args[1])


# ---------------------------------------------------------------------------
# The pure helpers, and the planted defect
# ---------------------------------------------------------------------------


def test_the_helpers_are_exercised_directly_in_both_directions() -> None:
    # Must NOT fire.
    assert port.map_arch("x64") == ("amd64", None)
    assert port.map_arch("arm64") == ("arm64", None)
    # Must fire, and must still hand back a usable (empty) value: that IS the
    # defect, and a helper that raised would be a fix, not a port.
    assert port.map_arch("bogus") == ("", "Unknown arch: bogus")

    assert port.required_binaries("linux", "x64") == (["linux-amd64", "linux-arm64"], None)
    assert port.required_binaries("mac", "x64")[0][-1] == "darwin-amd64"
    assert port.required_binaries("win", "arm64")[0][-1] == "windows-arm64"
    assert port.required_binaries("banana", "x64") == (["linux-amd64", "linux-arm64"], None)

    assert port.binary_to_meta_key("linux-amd64") == "amd64"
    assert port.binary_to_meta_key("darwin-arm64") == "darwin-arm64"
    assert port.disk_name("windows-amd64") == "renet-windows-amd64.exe"
    assert port.disk_name("linux-amd64") == "renet-linux-amd64"

    assert port.asset_count([("a", "b")] * 5) == 4
    assert port.asset_count([]) == 0


def test_the_generated_json_matches_what_jq_would_have_written(tmp_path) -> None:
    """The port builds both JSON files in Python instead of shelling out to
    `jq -Rn`. That is only safe if the bytes agree, so this drives the REAL jq
    with the twin's own filter and compares."""
    root = fixture(tmp_path)
    pairs = [
        ("renet-metadata.json", "dist/assets/renet-metadata.json"),
        ("third-party-credits.json", "dist/assets/third-party-credits.json"),
        ("THIRD_PARTY_LICENSES", "dist/assets/THIRD_PARTY_LICENSES"),
        ("renet-linux-amd64", "dist/assets/renet-linux-amd64"),
    ]
    jq_filter = (
        '[inputs | select(length > 0) | split("\t") | {key: .[0], value: .[1]}] | '
        "from_entries as $assets |\n"
        "     {\n"
        "       main: $main,\n"
        "       output: $output,\n"
        "       disableExperimentalSEAWarning: true,\n"
        "       useSnapshot: false,\n"
        "       useCodeCache: false,\n"
        "       assets: $assets\n"
        "     }"
    )
    proc = subprocess.run(
        [
            "jq",
            "-Rn",
            "--arg",
            "main",
            "dist/cli-bundle.cjs",
            "--arg",
            "output",
            "dist/sea-prep.blob",
            jq_filter,
        ],
        input="".join("%s\t%s\n" % pair for pair in pairs),
        capture_output=True,
        text=True,
        check=True,
        cwd=str(root),
    )
    assert port.sea_config(pairs) == proc.stdout


def test_a_planted_defect_is_caught_only_by_the_artifacts(tmp_path) -> None:
    """The proof that this differential can fail. Dropping the `linux-` prefix
    strip from the metadata key changes the FILE and nothing else: the exit code,
    both streams and the call log are identical on both sides."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace(
        '    if name.startswith("linux-"):\n        return name[len("linux-") :]\n',
        '    if name.startswith("linux-"):\n        return name\n',
    )
    assert planted != source, "the plant did not apply; fix the control first"
    root = fixture(tmp_path, port_source=planted)
    old_t, new_t = run_both(root, args=("--platform", "linux", "--arch", "x64"))
    assert old_t[0].returncode == new_t[0].returncode == 0, new_t[0].stderr
    assert old_t[0].stderr == new_t[0].stderr, "the streams agree, which is the point"
    assert old_t[1] == new_t[1], "the call log agrees too"
    assert old_t[2] != new_t[2], "the artifacts MUST diverge, or this suite proves nothing"
    old_meta = json.loads(old_t[2]["packages/cli/dist/assets/renet-metadata.json"])
    new_meta = json.loads(new_t[2]["packages/cli/dist/assets/renet-metadata.json"])
    assert sorted(old_meta["binaries"]) == ["amd64", "arm64"]
    assert sorted(new_meta["binaries"]) == ["linux-amd64", "linux-arm64"]
