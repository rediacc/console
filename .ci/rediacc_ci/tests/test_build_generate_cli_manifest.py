"""Differential: `rediacc_ci.build.generate_cli_manifest` against its twin `.ci/scripts/build/generate-cli-manifest.sh`.

THE FIXTURE SHAPE follows `test_build_build_pages.py`: both sides are copied into a throwaway root, PATH is REPLACED rather than prepended, `rediacc_ci` is vendored so no absolute path outside the fixture reaches a command string, and `$0` is masked to `<SELF>` and nothing else is.

FOUR TOOLS ARE RECORDED. `jq`, `awk` and `mkdir` are wrappers that append their own argv to a log and then `exec` the real binary, so the work really happens AND the argv each side built is comparable. `date` is different: it is recorded and FROZEN, printing a fixed timestamp instead of `exec`-ing, because `releaseDate` is the one field in the manifest that two processes started a
second apart disagree about. Freezing it lets every case compare the manifest BYTE FOR BYTE rather than field by field with one field excused.

`dirname` is a plain symlink and deliberately NOT recorded. The twin spawns it three times (`:16` for `SCRIPT_DIR`, `common.sh:207` for `get_repo_root`, and `:136` for the output directory) where the port spawns it once, because Python resolves its own path in-process; recording it would manufacture a divergence out of that. `test_a_failing_dirname_does_not_stop_either_side` and
`test_the_twin_cannot_start_without_dirname_and_the_port_can` cover the `:136` call and that plumbing divergence on their own.

THE MANIFEST IS PART OF THE COMPARISON, not just the log. `_state` hashes every file either side produced, so a port that printed the same nine lines while writing a different manifest fails.

K=5 LEDGER: `.ci/shadow/w7p6-generate-cli-manifest.observations.jsonl`.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.build import generate_cli_manifest as port
from rediacc_ci.core import bash_dialect

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/generate-cli-manifest.sh"
PORT_REL = ".ci/rediacc_ci/build/generate_cli_manifest.py"
COMMON_REL = ".ci/scripts/lib/common.sh"

VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
)

BASH = shutil.which("bash") or "/bin/bash"

# `dirname` for `SCRIPT_DIR` and `get_repo_root`, `uname` because sourcing common.sh runs `detect_os`/`detect_arch`. Anything not listed is ABSENT.
PLAIN = ("dirname", "uname")

# Recorded wrappers around the real binaries. These ARE the ported logic.
RECORDED = ("jq", "awk", "mkdir")

# `:82`'s answer, frozen. Chosen to be a real instant so nothing downstream can object to it, and fixed so the two manifests are byte-identical.
FROZEN_DATE = "2026-09-14T00:00:00Z"

RECORDER = """#!/bin/bash
printf 'CALL {name}' >>"$FAKE_CALL_LOG"
for a in "$@"; do printf '\\t%s' "$a" >>"$FAKE_CALL_LOG"; done
printf '\\n' >>"$FAKE_CALL_LOG"
exec {real} "$@"
"""

# A `dirname` that answers CORRECTLY and then exits 1. It is the only way to reach the `set -e` question at `:136` -- see `test_a_failing_dirname_does_not_stop_either_side`.
FAILING_DIRNAME = """#!/bin/bash
{real} "$@"
exit 1
"""

FROZEN_DATE_FAKE = """#!/bin/bash
printf 'CALL date' >>"$FAKE_CALL_LOG"
for a in "$@"; do printf '\\t%s' "$a" >>"$FAKE_CALL_LOG"; done
printf '\\n' >>"$FAKE_CALL_LOG"
echo '{frozen}'
"""

# Top-level entries the fixture owns and never resets.
KEEP = frozenset({".ci", "fixture-bin", ".pristine", "old-calls.log", "new-calls.log"})

VALID_SHA = "a" * 64
OTHER_SHA = "b" * 64

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))


# --------------------------------------------------------------------------- Fixture ---------------------------------------------------------------------------


def fixture(
    tmp_path: pathlib.Path,
    *,
    port_source: str | None = None,
    checksums: dict[str, str] | None = None,
    input_subdir: str = "in",
) -> pathlib.Path:
    """A throwaway repo root holding both sides and a directory of checksums."""
    root = tmp_path / "repo"
    for rel in (TWIN_REL, PORT_REL, COMMON_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in (TWIN_REL, COMMON_REL, *VENDORED):
        shutil.copy2(ROOT / rel, root / rel)
    (root / ".ci" / "rediacc_ci" / "build").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / ".ci" / "rediacc_ci" / "build" / "__init__.py",
        root / ".ci" / "rediacc_ci" / "build" / "__init__.py",
    )
    if port_source is None:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")

    indir = root / input_subdir
    indir.mkdir(parents=True, exist_ok=True)
    for name, body in (checksums or {}).items():
        (indir / name).write_text(body, encoding="utf-8")

    _pristine(root)
    return root


def default_fixture(tmp_path: pathlib.Path, **kw) -> pathlib.Path:
    """One valid linux-x64 checksum and nothing else."""
    kw.setdefault("checksums", {"rdc-linux-x64.sha256": "%s  rdc-linux-x64\n" % VALID_SHA})
    return fixture(tmp_path, **kw)


def _mutable(root: pathlib.Path) -> list[str]:
    return [p.name for p in root.iterdir() if p.name not in KEEP]


def _pristine(root: pathlib.Path) -> None:
    keep = root / ".pristine"
    if keep.exists():
        shutil.rmtree(keep)
    keep.mkdir()
    for name in _mutable(root):
        src = root / name
        if src.is_dir():
            shutil.copytree(src, keep / name, symlinks=True)
        else:
            shutil.copy2(src, keep / name)


def _restore(root: pathlib.Path) -> None:
    keep = root / ".pristine"
    for name in _mutable(root):
        target = root / name
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    for entry in keep.iterdir():
        if entry.is_dir():
            shutil.copytree(entry, root / entry.name, symlinks=True)
        else:
            shutil.copy2(entry, root / entry.name)


def scratch_bin(
    root: pathlib.Path, *, drop: tuple[str, ...] = (), dirname_fails: bool = False
) -> str:
    """The ONLY directory on PATH for either side."""
    stub = root / "fixture-bin"
    if stub.exists():
        shutil.rmtree(stub)
    stub.mkdir(parents=True)
    for name in PLAIN:
        if name in drop:
            continue
        if name == "dirname" and dirname_fails:
            fake = stub / "dirname"
            fake.write_text(FAILING_DIRNAME.format(real=shutil.which("dirname")), encoding="utf-8")
            fake.chmod(0o755)
            continue
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        (stub / name).symlink_to(real)
    for name in RECORDED:
        if name in drop:
            continue
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        wrapper = stub / name
        wrapper.write_text(RECORDER.format(name=name, real=real), encoding="utf-8")
        wrapper.chmod(0o755)
    if "date" not in drop:
        fake = stub / "date"
        fake.write_text(FROZEN_DATE_FAKE.format(frozen=FROZEN_DATE), encoding="utf-8")
        fake.chmod(0o755)
    return str(stub)


# --------------------------------------------------------------------------- Driving ---------------------------------------------------------------------------


def _state(root: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in sorted(_mutable(root)):
        base = root / name
        if base.is_file():
            out[name] = "file:" + hashlib.sha256(base.read_bytes()).hexdigest()[:16]
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            here = os.path.relpath(dirpath, root)
            for d in sorted(dirnames):
                out[os.path.join(here, d)] = "dir"
            for f in sorted(filenames):
                full = pathlib.Path(dirpath) / f
                digest = hashlib.sha256(full.read_bytes()).hexdigest()[:16]
                out[os.path.relpath(full, root)] = "file:" + digest
    return out


def _run(
    root: pathlib.Path,
    side: str,
    *,
    args: tuple[str, ...] = (),
    drop: tuple[str, ...] = (),
    dirname_fails: bool = False,
    cwd: str | None = None,
    **extra,
):
    call_log = root / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        # REPLACED, never prepended.
        "PATH": scratch_bin(root, drop=drop, dirname_fails=dirname_fails),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(extra)
    if side == "old":
        argv = [BASH, str(root / TWIN_REL), *args]
    else:
        argv = [sys.executable, str(root / PORT_REL), *args]
    proc = subprocess.run(
        argv,
        cwd=cwd or str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8"), _state(root)


def run_both(root: pathlib.Path, **kw):
    old, old_calls, old_state = _run(root, "old", **kw)
    _restore(root)
    new, new_calls, new_state = _run(root, "new", **kw)
    return (old, old_calls, old_state), (new, new_calls, new_state)


def _mask(text: str) -> str:
    return SELF_RE.sub("<SELF>", text)


def _agree(old_t, new_t, label: str) -> None:
    old, old_calls, old_state = old_t
    new, new_calls, new_state = new_t
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
    assert new_state == old_state, "%s: the produced files diverged:\n%s" % (
        label,
        sorted(set(old_state.items()) ^ set(new_state.items())),
    )


def manifest_of(root: pathlib.Path, rel: str = "out/manifest.json") -> dict:
    return json.loads((root / rel).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- The control on the control ---------------------------------------------------------------------------


def test_the_scratch_path_holds_only_the_six_named_tools(tmp_path) -> None:
    root = default_fixture(tmp_path)
    sealed = scratch_bin(root)
    for name in (*PLAIN, *RECORDED, "date"):
        assert shutil.which(name, path=sealed) == str(root / "fixture-bin" / name)
    for absent in ("npm", "node", "git", "bash", "python3", "curl"):
        assert shutil.which(absent, path=sealed) is None, "%s is reachable" % absent
    assert shutil.which("jq", path=scratch_bin(root, drop=("jq",))) is None


def test_the_frozen_date_really_answers_and_is_recorded(tmp_path) -> None:
    """A `date` fake that printed nothing would make `releaseDate` empty on both sides and the comparison would still pass, so the fake is checked first.
    """
    root = default_fixture(tmp_path)
    log = root / "probe.log"
    log.write_text("", encoding="utf-8")
    proc = subprocess.run(
        ["date", "-u", port.DATE_FORMAT],
        env={"PATH": scratch_bin(root), "FAKE_CALL_LOG": str(log)},
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert proc.stdout == FROZEN_DATE + "\n"
    assert log.read_text(encoding="utf-8") == "CALL date\t-u\t%s\n" % port.DATE_FORMAT


# --------------------------------------------------------------------------- The success path ---------------------------------------------------------------------------


def test_one_valid_checksum_produces_one_binary_and_nine_lines(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json"),
        GITHUB_SHA="deadbeef",
    )
    old, old_calls, _tree = old_t
    assert old.returncode == 0, old.stderr
    assert old.stdout == ""
    assert old.stderr == (
        "→ Generating CLI manifest v1.2.3\n"
        "✓   Input: in\n"
        "✓   Output: out/manifest.json\n"
        "✓   Added linux-x64: aaaaaaaaaaaaaaaa...\n"
        "✓   Skipping linux-arm64 (no checksum file)\n"
        "✓   Skipping mac-x64 (no checksum file)\n"
        "✓   Skipping mac-arm64 (no checksum file)\n"
        "✓   Skipping win-x64 (no checksum file)\n"
        "✓   Skipping win-arm64 (no checksum file)\n"
        "✓ Manifest generated: out/manifest.json\n"
    ), old.stderr
    assert manifest_of(root) == {
        "version": "1.2.3",
        "releaseDate": FROZEN_DATE,
        "releaseNotesUrl": "https://github.com/rediacc/console/releases/tag/v1.2.3",
        "commit": "deadbeef",
        "binaries": {
            "linux-x64": {
                "url": "https://releases.rediacc.com/cli/v1.2.3/rdc-linux-x64",
                "sha256": VALID_SHA,
            }
        },
    }
    assert old_calls.startswith("CALL date\t-u\t%s\nCALL jq\t-n\t" % port.DATE_FORMAT)
    assert "CALL awk\t{print $1}\tin/rdc-linux-x64.sha256\n" in old_calls
    _agree(old_t, new_t, "one-binary")


def test_all_six_binaries_are_added_in_the_twins_iteration_order(tmp_path) -> None:
    names = [port.binary_name(p, a) for p in port.PLATFORMS for a in port.ARCHES]
    root = fixture(
        tmp_path,
        checksums={"%s.sha256" % n: "%s  %s\n" % (VALID_SHA, n) for n in names},
    )
    old_t, new_t = run_both(
        root, args=("--version", "2.0.0", "--input", "in", "--output", "out/manifest.json")
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert list(manifest_of(root)["binaries"]) == [
        "linux-x64",
        "linux-arm64",
        "mac-x64",
        "mac-arm64",
        "win-x64",
        "win-arm64",
    ]
    assert (
        manifest_of(root)["binaries"]["win-arm64"]["url"]
        == "https://releases.rediacc.com/cli/v2.0.0/rdc-win-arm64.exe"
    )
    _agree(old_t, new_t, "all-six")


def test_the_default_output_is_the_input_directorys_manifest_json(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--version", "1.0.0", "--input", "in"))
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "✓   Output: in/manifest.json\n" in old_t[0].stderr
    assert (root / "in" / "manifest.json").is_file()
    _agree(old_t, new_t, "default-output")


def test_the_default_input_is_the_repo_roots_dist_cli_and_is_absolute(tmp_path) -> None:
    """Half of defect 3: with no `--input` the directory is ABSOLUTE, resolved
    from the script's own location and not from the caller's cwd.
    """
    root = default_fixture(tmp_path)
    (root / "dist" / "cli").mkdir(parents=True)
    (root / "dist" / "cli" / "rdc-mac-arm64.sha256").write_text(
        "%s  rdc-mac-arm64\n" % OTHER_SHA, encoding="utf-8"
    )
    # The snapshot was taken before `dist/` existed; retake it or the second side starts from a tree the first side never saw.
    _pristine(root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    old_t, new_t = run_both(root, args=("--version", "3.0.0"), cwd=str(elsewhere))
    old = old_t[0]
    assert old.returncode == 0, old.stderr
    assert "✓   Input: %s/dist/cli\n" % root in old.stderr
    assert manifest_of(root, "dist/cli/manifest.json")["binaries"]["mac-arm64"]["sha256"] == (
        OTHER_SHA
    )
    _agree(old_t, new_t, "default-input")


def test_defect_3_an_explicit_relative_input_follows_the_caller_not_the_root(
    tmp_path,
) -> None:
    """The other half of defect 3. There is no `cd "$(get_repo_root)"` here, unlike every sibling in `.ci/scripts/build/`, so `--input in` means `$PWD/in`. Driven from a cwd holding a DIFFERENT `in/`, both sides read the caller's and neither reads the repo's.
    """
    root = default_fixture(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "in").mkdir(parents=True)
    (elsewhere / "in" / "rdc-win-x64.exe.sha256").write_text(
        "%s  rdc-win-x64.exe\n" % OTHER_SHA, encoding="utf-8"
    )
    old, _calls, _st = _run(
        root,
        "old",
        args=("--version", "4.0.0", "--input", "in", "--output", "m.json"),
        cwd=str(elsewhere),
    )
    assert old.returncode == 0, old.stderr
    produced = json.loads((elsewhere / "m.json").read_text(encoding="utf-8"))
    assert list(produced["binaries"]) == ["win-x64"], produced
    assert not (root / "m.json").exists(), "the output landed in the repo, not the cwd"


# --------------------------------------------------------------------------- The channel and the environment ---------------------------------------------------------------------------


def test_stable_edge_and_an_empty_channel_all_get_the_versioned_url(tmp_path) -> None:
    for channel in ("stable", "edge", ""):
        root = default_fixture(tmp_path / ("ch-%s" % (channel or "none")))
        old_t, new_t = run_both(
            root,
            args=(
                "--version",
                "1.2.3",
                "--channel",
                channel,
                "--input",
                "in",
                "--output",
                "out/manifest.json",
            ),
        )
        assert old_t[0].returncode == 0, old_t[0].stderr
        assert manifest_of(root)["binaries"]["linux-x64"]["url"] == (
            "https://releases.rediacc.com/cli/v1.2.3/rdc-linux-x64"
        )
        _agree(old_t, new_t, "channel " + (channel or "<empty>"))


def test_any_other_channel_gets_its_own_path(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=(
            "--version",
            "1.2.3",
            "--channel",
            "pr-42",
            "--input",
            "in",
            "--output",
            "out/manifest.json",
        ),
    )
    assert manifest_of(root)["binaries"]["linux-x64"]["url"] == (
        "https://releases.rediacc.com/cli/pr-42/rdc-linux-x64"
    )
    _agree(old_t, new_t, "channel pr-42")


def test_releases_base_url_overrides_the_host_and_an_empty_value_does_not(tmp_path) -> None:
    """`${RELEASES_BASE_URL:-...}` falls back on UNSET *and* on empty."""
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json"),
        RELEASES_BASE_URL="https://staging.example",
    )
    assert manifest_of(root)["binaries"]["linux-x64"]["url"].startswith("https://staging.example/")
    _agree(old_t, new_t, "releases-base")

    root2 = default_fixture(tmp_path / "empty-base")
    old2, new2 = run_both(
        root2,
        args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json"),
        RELEASES_BASE_URL="",
    )
    assert manifest_of(root2)["binaries"]["linux-x64"]["url"].startswith(port.DEFAULT_RELEASES_BASE)
    _agree(old2, new2, "releases-base-empty")


def test_an_absent_github_sha_becomes_the_literal_unknown(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(
        root, args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json")
    )
    assert manifest_of(root)["commit"] == port.DEFAULT_COMMIT
    _agree(old_t, new_t, "no-github-sha")


def test_the_repo_flag_only_moves_the_release_notes_url(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=(
            "--version",
            "1.2.3",
            "--repo",
            "someone/fork",
            "--input",
            "in",
            "--output",
            "out/manifest.json",
        ),
    )
    got = manifest_of(root)
    assert got["releaseNotesUrl"] == "https://github.com/someone/fork/releases/tag/v1.2.3"
    assert got["binaries"]["linux-x64"]["url"].startswith(port.DEFAULT_RELEASES_BASE)
    _agree(old_t, new_t, "repo-flag")


# --------------------------------------------------------------------------- The argument parser ---------------------------------------------------------------------------


def test_help_goes_to_stdout_and_exits_zero(tmp_path) -> None:
    for flag in ("-h", "--help"):
        root = default_fixture(tmp_path / ("help" + flag))
        old_t, new_t = run_both(root, args=(flag,))
        old = old_t[0]
        assert old.returncode == 0
        assert old.stderr == ""
        assert _mask(old.stdout) == (
            "Usage: <SELF> --version VERSION [--input DIR] [--output PATH] "
            "[--repo REPO] [--channel CHANNEL]\n"
        ), old.stdout
        _agree(old_t, new_t, "help " + flag)


def test_an_unknown_option_is_refused_unlike_its_build_pages_sibling(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--bogus", "x"))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "✗ Unknown option: --bogus\n"
    _agree(old_t, new_t, "unknown-option")


def test_a_positional_argument_is_also_an_unknown_option(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(root, args=("1.2.3",))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "✗ Unknown option: 1.2.3\n"
    _agree(old_t, new_t, "positional")


def test_a_missing_version_is_refused(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--input", "in"))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "✗ %s\n" % port.NO_VERSION_MESSAGE
    _agree(old_t, new_t, "no-version")


def test_an_empty_version_string_is_also_refused(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--version", ""))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "✗ %s\n" % port.NO_VERSION_MESSAGE
    _agree(old_t, new_t, "empty-version")


def test_defect_4_every_dangling_flag_is_bashs_own_unbound_variable(tmp_path) -> None:
    """`$2` under `set -u`, with the ARM's line number rather than the flag's name. Each of the five value-taking arms has its own line, so each is driven.
    """
    for flag, line in port.FLAG_LINES.items():
        root = default_fixture(tmp_path / ("dangling" + flag))
        old_t, new_t = run_both(root, args=(flag,))
        old = old_t[0]
        assert old.returncode == 1, old.stderr
        assert _mask(old.stderr) == "<SELF>: line %d: $2: unbound variable\n" % line, old.stderr
        assert old_t[1] == "", "something ran before the parser gave up"
        _agree(old_t, new_t, "dangling " + flag)


# --------------------------------------------------------------------------- The defects ---------------------------------------------------------------------------


def test_defect_1_an_input_with_no_checksums_is_an_empty_manifest_and_exit_zero(
    tmp_path,
) -> None:
    """The known hazard `proxy-cli-manifest.sh:160-166` reports and does not enforce: a release published from this manifest offers no downloads at all.
    """
    root = fixture(tmp_path, checksums={})
    old_t, new_t = run_both(
        root, args=("--version", "9.9.9", "--input", "in", "--output", "out/manifest.json")
    )
    old = old_t[0]
    assert old.returncode == 0, "a manifest with no binaries was refused; defect 1 is gone"
    assert manifest_of(root)["binaries"] == {}
    assert old.stderr.endswith("✓ Manifest generated: out/manifest.json\n")
    assert old.stderr.count("Skipping") == 6
    _agree(old_t, new_t, "zero-binaries")


def test_defect_2_three_different_bad_checksums_all_become_one_warning(tmp_path) -> None:
    """An empty file, a truncated hash and a multi-line file are distinct situations; `:117-120` folds all three into `⚠ Invalid checksum` and a `continue`, and none of them changes the exit code.
    """
    cases = {
        "empty": "",
        "truncated": "abc123  rdc-linux-x64\n",
        "two-lines": "%s  a\n%s  b\n" % (VALID_SHA, OTHER_SHA),
        "sixty-five": "%s  rdc-linux-x64\n" % ("a" * 65),
    }
    for label, body in cases.items():
        root = fixture(
            tmp_path / label,
            checksums={"rdc-linux-x64.sha256": body},
        )
        old_t, new_t = run_both(
            root,
            args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json"),
        )
        old = old_t[0]
        assert old.returncode == 0, "%s: %s" % (label, old.stderr)
        assert "⚠   Invalid checksum for rdc-linux-x64, skipping\n" in old.stderr, label
        assert manifest_of(root)["binaries"] == {}, label
        _agree(old_t, new_t, "bad-checksum " + label)


def test_a_checksum_file_with_leading_whitespace_still_yields_the_first_field(
    tmp_path,
) -> None:
    """`awk '{print $1}'` skips leading blanks, so this one IS accepted. The
    port must not tighten it: a NEGATIVE control on defect 2's warning.
    """
    root = fixture(
        tmp_path,
        checksums={"rdc-linux-x64.sha256": "   %s   rdc-linux-x64\n" % VALID_SHA},
    )
    old_t, new_t = run_both(
        root, args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json")
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert manifest_of(root)["binaries"]["linux-x64"]["sha256"] == VALID_SHA
    assert "Invalid checksum" not in old_t[0].stderr
    _agree(old_t, new_t, "leading-whitespace")


def test_defect_5_the_file_header_never_mentions_the_channel_flag() -> None:
    """`:5-12` documents four flags; `--channel` decides the download URL and is what `cd-stage.yml:171` passes. Asserted against the twin on disk so the docstring's defect 5 goes red the day someone fixes the header.
    """
    header = (ROOT / TWIN_REL).read_text(encoding="utf-8").split("set -euo pipefail")[0]
    assert "--version VERSION" in header
    assert "--repo REPO" in header
    assert "--channel" not in header, "the header now documents --channel; defect 5 is fixed"


# --------------------------------------------------------------------------- Missing tools ---------------------------------------------------------------------------


def test_a_missing_jq_is_a_named_refusal_after_three_log_lines(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json"),
        drop=("jq",),
    )
    old = old_t[0]
    assert old.returncode == 1
    assert old.stderr.endswith("✗ %s\n" % port.NO_JQ_MESSAGE), old.stderr
    assert not (root / "out").exists()
    _agree(old_t, new_t, "no-jq")


def test_a_missing_awk_stops_at_127_rather_than_skipping_the_binary(tmp_path) -> None:
    """The reason `awk` is spawned rather than reimplemented. `SHA256="$(awk ...)"`
    is an assignment, so `set -e` takes the substitution's status: the run STOPS at 127 instead of quietly recording a manifest with no binaries.
    """
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json"),
        drop=("awk",),
    )
    old = old_t[0]
    assert old.returncode == 127, old.stderr
    assert _mask(old.stderr).endswith(
        "<SELF>: line %d: awk: command not found\n" % port.AWK_LINE
    ), old.stderr
    assert not (root / "out").exists(), "a manifest was written despite the stop"
    _agree(old_t, new_t, "no-awk")


def test_a_missing_date_stops_before_a_single_log_line(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json"),
        drop=("date",),
    )
    old = old_t[0]
    assert old.returncode == 127, old.stderr
    assert _mask(old.stderr) == ("<SELF>: line %d: date: command not found\n" % port.DATE_LINE), (
        old.stderr
    )
    assert "Generating CLI manifest" not in old.stderr
    _agree(old_t, new_t, "no-date")


def test_a_missing_mkdir_stops_after_every_binary_is_added(tmp_path) -> None:
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json"),
        drop=("mkdir",),
    )
    old = old_t[0]
    assert old.returncode == 127, old.stderr
    assert "✓   Added linux-x64" in old.stderr
    assert _mask(old.stderr).endswith(
        "<SELF>: line %d: mkdir: command not found\n" % port.MKDIR_LINE
    ), old.stderr
    _agree(old_t, new_t, "no-mkdir")


def test_a_failing_dirname_does_not_stop_either_side(tmp_path) -> None:
    """THE CONTROL FOR `capture_lax`, and the reason it exists.

    `mkdir -p "$(dirname "$OUTPUT_PATH")"` at `:136` is a substitution used as an ARGUMENT, not as the command, so `set -e` does NOT take its status: the only status that counts is `mkdir`'s. A port that used the strict helper here would stop where the twin carries on.

    Reaching that question needs a `dirname` that ANSWERS and then exits 1;
    removing `dirname` outright cannot reach it (see the next test). Both sides are driven with exactly that fake and must complete normally.
    """
    root = default_fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json"),
        dirname_fails=True,
    )
    old = old_t[0]
    assert old.returncode == 0, old.stderr
    assert (root / "out" / "manifest.json").is_file()
    assert manifest_of(root)["binaries"]["linux-x64"]["sha256"] == VALID_SHA
    _agree(old_t, new_t, "dirname-fails")


def test_the_twin_cannot_start_without_dirname_and_the_port_can(tmp_path) -> None:
    """A DOCUMENTED DIVERGENCE, driven rather than assumed.

    The twin resolves its own `SCRIPT_DIR` at `:16` with
    `cd "$(dirname "${BASH_SOURCE[0]}")"`, so a PATH without `dirname` kills it
    before line 17 and exit 1. The port resolves its own path in-process and gets all the way to `:136`, where its one real `dirname` call is missing and `mkdir -p ''` then fails -- exit 1 as well, but for a different reason and after doing all the work.

    This is shell plumbing, not ported logic, which is why `dirname` is a plain unrecorded symlink in the fixture. Recorded here so nobody discovers it as a surprise.

    HOW FAR THE TWIN GETS IS BASH-VERSION-DEPENDENT, and this case used to hard-code the 5.3 answer (`ends with "line 16: cd: null directory"`). The difference is BEHAVIOURAL, not just wording, and it was worth measuring rather than guessing:

        bash 5.3  `cd ""` FAILS and says `cd: null directory`, so `set -e` kills
                  the script AT line 16 and line 17 never runs.
        bash 5.2  `cd ""` SUCCEEDS, silently, leaving the shell where it was --
                  so the script survives line 16 and dies one line later, unable
                  to source `../lib/common.sh` from the wrong directory.

    Both versions still die in the twin's own plumbing before any manifest work happens, which is the property this case actually exists to pin, so that is asserted unconditionally and only the tail is asked of the running bash. Hard-coding the 5.3 tail made this pass on every machine in this tree and fail in CI run 34970782616.
    """
    root = default_fixture(tmp_path)
    args = ("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json")
    old, _calls, _st = _run(root, "old", args=args, drop=("dirname",))
    _restore(root)
    new, _c2, _s2 = _run(root, "new", args=args, drop=("dirname",))
    assert old.returncode == 1, old.stderr
    # Version-independent, and the real point of the case: the missing `dirname` is reported from inside the command substitution, and no manifest work happens on either bash.
    assert "line 16: dirname: command not found" in old.stderr, old.stderr
    cd_null = bash_dialect.cd_null_directory()
    if cd_null:
        assert old.stderr.endswith("line 16: %s\n" % cd_null), old.stderr
    else:
        assert old.stderr.rstrip().endswith("lib/common.sh: No such file or directory"), old.stderr
    assert "Generating CLI manifest" not in old.stderr
    assert new.returncode == 1, new.stderr
    assert "✓   Added linux-x64" in new.stderr
    assert "mkdir: cannot create directory" in new.stderr, new.stderr


def test_the_port_and_the_twin_agree_about_the_repo_root_in_this_checkout() -> None:
    proc = subprocess.run(
        [BASH, "-c", 'source "$1" && get_repo_root', "bash", str(ROOT / COMMON_REL)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert proc.stdout.strip() == str(port.repo_root())
    assert proc.stdout.strip() == str(ROOT)


# --------------------------------------------------------------------------- The control: this differential can actually fail ---------------------------------------------------------------------------


def test_a_planted_defect_is_caught(tmp_path) -> None:
    """A gate that has never been seen to fail is not a gate.

    The plant relaxes the length check from `!= 64` to `< 8`, which is what a
    reader "being lenient about hash formats" would write. It is invisible on every valid checksum and visible on exactly one case: the truncated hash, which the twin discards with a warning and the plant enshrines in the manifest.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace(
        "if not sha256 or len(sha256) != SHA256_LENGTH:",
        "if not sha256 or len(sha256) < 8:",
    )
    assert planted != source, "the plant site moved; this control is not planting anything"
    root = fixture(
        tmp_path,
        port_source=planted,
        checksums={"rdc-linux-x64.sha256": "abc123def  rdc-linux-x64\n"},
    )
    old_t, new_t = run_both(
        root, args=("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json")
    )
    assert "⚠   Invalid checksum for rdc-linux-x64, skipping\n" in old_t[0].stderr
    assert "Invalid checksum" not in new_t[0].stderr, "the plant did not diverge"
    assert new_t[2] != old_t[2], "the plant produced the same manifest"
