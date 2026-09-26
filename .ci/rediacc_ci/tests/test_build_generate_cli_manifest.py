"""`rediacc_ci.build.generate_cli_manifest`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/build/generate-cli-manifest.sh` and the port inside one throwaway repo root and compared exit code, stdout, stderr, the recorded CALL LOG of the four tools either side spawns, and the hash of every file the run produced. The ledger `.ci/shadow/w7p6-generate-cli-manifest.observations.jsonl` holds 5 rows
of that comparison.

Every case now compares against `goldens/generate-cli-manifest/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

WHY THE MANIFEST IS WORTH THIS MUCH APPARATUS. What this subject writes is what `rdc update` fetches to decide which binary to download and what sha256 to verify it against, so a wrong URL or a wrong hash here is a broken updater for every installed CLI.

ONE MORE PIECE OF EVIDENCE EXISTS THAN FOR MOST PORTS, and it was taken before the twin went: `.ci/scripts/test/proxies/proxy-cli-manifest.sh` drives the subject over a six-binary dist directory with real `sha256sum` output, and its own differential compares the bash proxy with the ported proxy byte for byte. Pointing only the ported proxy at this port, while the bash twin still
drove the bash subject, left that comparison byte-identical across all eleven of its checks, including every emitted hash and both channel URL branches.

THREE SECTIONS BEYOND THE TWO STREAMS, because the streams are the smallest part of what this subject does.

  `--- calls ---`  `jq`, `awk` and `mkdir` are wrappers that append their own
                   argv to a log and then `exec` the real binary, so the work
                   really happens AND the argv each side built is comparable.
  `--- files ---`  every file the run produced, hashed. A port that printed the
                   same nine lines while writing a different manifest fails
                   here and nowhere else.
  `--- exit ---`   carried in the first line of the recorded shape, as always.

`date` IS RECORDED AND FROZEN rather than wrapped, because `releaseDate` is the one field two processes started a second apart disagree about. Freezing it is what lets every case compare the manifest byte for byte rather than field by field with one field excused, and `test_the_frozen_date_really_answers_and_is_recorded` checks the fake first, since a `date` that printed nothing
would make the field empty everywhere and the comparison would still pass.

`dirname` IS A PLAIN SYMLINK AND DELIBERATELY NOT RECORDED. The twin spawned it three times where the port spawns it once, because Python resolves its own path in-process; recording it would have manufactured a divergence out of that. Two cases cover the plumbing on their own.

THE SEALED PATH IS THE CONTROL THE REST RESTS ON. PATH is REPLACED, never prepended, and holds exactly six entries; `test_the_sealed_path_holds_only_the_six_named_tools` asserts both halves, that each of the six resolves into the fixture and that `node`, `git`, `bash`, `python3` and `curl` resolve nowhere.

WHAT IS MASKED, and it is two things. The throwaway repo root is rebuilt under a different temporary name every run, so it becomes `<root>`; and the subject's own path becomes `<SELF>`, because bash reported its refusals against the `.sh` and the port reports them against the `.py`, which is the one difference no port can honestly remove. Nothing else is touched.

ONE CASE IS COMPARED BY SHAPE, and it is a documented divergence rather than a wart: with no `dirname` on PATH the twin died resolving its own `SCRIPT_DIR` before it did any work, while the port resolves its path in-process, does all the work and fails later at `mkdir`. The recorded half is also BASH-VERSION-DEPENDENT (bash 5.3 fails `cd ""`, bash 5.2 succeeds silently and dies one
line later), which is exactly why it is evidence rather than an expectation: only the port's half is compared, and the recording is kept for what it says about the twin.

ONE CASE IS NOT RECORDED AT ALL, and it says so where it stands: `test_the_port_agrees_with_common_sh_about_the_repo_root_in_this_checkout` reads the LIVE `common.sh` and the live checkout, and freezing it would freeze a tracked file's content into a golden.

DEFECT 5 DIED WITH THE TWIN'S HEADER, and it is recorded here rather than silently dropped. The old differential asserted that the twin's file header documented four flags and never `--channel`, the flag that decides the download URL, so that the day someone fixed the header the assertion would go red. That header is gone with the file. The port's own docstring names `--channel` at
its call sites and its `--help` line always listed it, so there is no surviving text for the assertion to watch and the case is not carried over.
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
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.build import generate_cli_manifest as gcm
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()

PORT_REL = ".ci/rediacc_ci/build/generate_cli_manifest.py"
TWIN_REL = ".ci/scripts/build/generate-cli-manifest.sh"
COMMON_REL = ".ci/scripts/lib/common.sh"

SLUG = "generate-cli-manifest"
CALLS_MARKER = "--- calls ---\n"
FILES_MARKER = "--- files ---\n"

VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
)

BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

# `dirname` for `SCRIPT_DIR` and `get_repo_root`, `uname` because sourcing common.sh runs `detect_os`/`detect_arch`. Anything not listed is ABSENT.
PLAIN = ("dirname", "uname")

# Recorded wrappers around the real binaries. These ARE the ported logic.
RECORDED = ("jq", "awk", "mkdir")

# `:82`'s answer, frozen. Chosen to be a real instant so nothing downstream can object to it, and fixed so every manifest is byte-identical.
FROZEN_DATE = "2026-09-14T00:00:00Z"

RECORDER = """#!/bin/bash
printf 'CALL {name}' >>"$FAKE_CALL_LOG"
for a in "$@"; do printf '\\t%s' "$a" >>"$FAKE_CALL_LOG"; done
printf '\\n' >>"$FAKE_CALL_LOG"
exec {real} "$@"
"""

# A `dirname` that answers CORRECTLY and then exits 1. It is the only way to reach the `set -e` question at `:136`.
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

# Top-level entries the fixture owns and never reports as produced.
KEEP = frozenset({".ci", "fixture-bin", "calls.log"})

VALID_SHA = "a" * 64
OTHER_SHA = "b" * 64

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))

ALL_SIX = {
    "%s.sha256" % gcm.binary_name(p, a): "%s  %s\n" % (VALID_SHA, gcm.binary_name(p, a))
    for p in gcm.PLATFORMS
    for a in gcm.ARCHES
}

ONE_BINARY = {"rdc-linux-x64.sha256": "%s  rdc-linux-x64\n" % VALID_SHA}

STANDARD = ("--version", "1.2.3", "--input", "in", "--output", "out/manifest.json")


def dangling(flag: str) -> dict[str, typing.Any]:
    return {"args": (flag,)}


# name -> the arguments, the checksum files the input directory holds, the environment, the tools to withhold, and the two fixture shapes that need more than that
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "one-binary": {"args": STANDARD, "env": {"GITHUB_SHA": "deadbeef"}},
    "all-six-binaries": {
        "args": ("--version", "2.0.0", "--input", "in", "--output", "out/manifest.json"),
        "checksums": ALL_SIX,
    },
    "the-default-output": {"args": ("--version", "1.0.0", "--input", "in")},
    "the-default-input": {"args": ("--version", "3.0.0"), "dist_cli": True, "cwd": "elsewhere"},
    "a-relative-input-follows-the-caller": {
        "args": ("--version", "4.0.0", "--input", "in", "--output", "m.json"),
        "cwd": "elsewhere",
        "elsewhere_checksums": {"rdc-win-x64.exe.sha256": "%s  rdc-win-x64.exe\n" % OTHER_SHA},
    },
    "the-stable-channel": {
        "args": ("--version", "1.2.3", "--channel", "stable", "--input", "in", "--output", "o.json")
    },
    "the-edge-channel": {
        "args": ("--version", "1.2.3", "--channel", "edge", "--input", "in", "--output", "o.json")
    },
    "an-empty-channel": {
        "args": ("--version", "1.2.3", "--channel", "", "--input", "in", "--output", "o.json")
    },
    "a-pull-request-channel": {
        "args": ("--version", "1.2.3", "--channel", "pr-42", "--input", "in", "--output", "o.json")
    },
    "a-releases-base-url": {
        "args": STANDARD,
        "env": {"RELEASES_BASE_URL": "https://staging.example"},
    },
    "an-empty-releases-base-url": {"args": STANDARD, "env": {"RELEASES_BASE_URL": ""}},
    "an-absent-github-sha": {"args": STANDARD},
    "a-repo-flag": {
        "args": (
            "--version",
            "1.2.3",
            "--repo",
            "someone/fork",
            "--input",
            "in",
            "--output",
            "out/manifest.json",
        )
    },
    "the-short-help-flag": {"args": ("-h",)},
    "the-long-help-flag": {"args": ("--help",)},
    "an-unknown-option": {"args": ("--bogus", "x")},
    "a-positional-argument": {"args": ("1.2.3",)},
    "a-missing-version": {"args": ("--input", "in")},
    "an-empty-version": {"args": ("--version", "")},
    "no-checksums-at-all": {
        "args": ("--version", "9.9.9", "--input", "in", "--output", "out/manifest.json"),
        "checksums": {},
    },
    "an-empty-checksum-file": {"args": STANDARD, "checksums": {"rdc-linux-x64.sha256": ""}},
    "a-truncated-checksum": {
        "args": STANDARD,
        "checksums": {"rdc-linux-x64.sha256": "abc123  rdc-linux-x64\n"},
    },
    "a-two-line-checksum-file": {
        "args": STANDARD,
        "checksums": {
            "rdc-linux-x64.sha256": "%s  a\n%s  b\n" % (VALID_SHA, OTHER_SHA),
        },
    },
    "a-sixty-five-character-hash": {
        "args": STANDARD,
        "checksums": {"rdc-linux-x64.sha256": "%s  rdc-linux-x64\n" % ("a" * 65)},
    },
    "leading-whitespace-in-the-checksum": {
        "args": STANDARD,
        "checksums": {"rdc-linux-x64.sha256": "   %s   rdc-linux-x64\n" % VALID_SHA},
    },
    "no-jq-on-the-path": {"args": STANDARD, "drop": ("jq",)},
    "no-awk-on-the-path": {"args": STANDARD, "drop": ("awk",)},
    "no-date-on-the-path": {"args": STANDARD, "drop": ("date",)},
    "no-mkdir-on-the-path": {"args": STANDARD, "drop": ("mkdir",)},
    "a-failing-dirname": {"args": STANDARD, "dirname_fails": True},
    "no-dirname-on-the-path": {"args": STANDARD, "drop": ("dirname",)},
}
CASE_KW.update({"a-dangling-%s" % flag.lstrip("-"): dangling(flag) for flag in gcm.FLAG_LINES})

CASES = tuple(CASE_KW)

# The one case whose recorded half is the twin's own bash plumbing, and bash-version-dependent at that. Compared by shape, in its own test.
DIVERGENT = ("no-dirname-on-the-path",)


def build(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    """A throwaway repo root holding the subject and a directory of checksums.

    `common.sh` and the three vendored `rediacc_ci` files are copied from the LIVE tree. That is deliberate and it is not a frozen copy of anything: the twin sourced `common.sh`, and the port imports `rediacc_ci.log`, so the fixture has to hold whatever the checkout holds. What is frozen is the OUTPUT, and the output would change if those files changed, which is a regression a
    golden should catch rather than hide.
    """
    kw = CASE_KW[name]
    root = tmp_path / "repo"
    for rel in (PORT_REL, COMMON_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    if (ROOT / TWIN_REL).is_file():
        (root / TWIN_REL).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / TWIN_REL, root / TWIN_REL)
    for rel in (COMMON_REL, PORT_REL, *VENDORED):
        shutil.copy2(ROOT / rel, root / rel)
    (root / ".ci" / "rediacc_ci" / "build").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / ".ci" / "rediacc_ci" / "build" / "__init__.py",
        root / ".ci" / "rediacc_ci" / "build" / "__init__.py",
    )

    indir = root / "in"
    indir.mkdir(parents=True, exist_ok=True)
    checksums = kw.get("checksums", ONE_BINARY)
    for filename, body in checksums.items():
        (indir / filename).write_text(body, encoding="utf-8")

    if kw.get("dist_cli"):
        (root / "dist" / "cli").mkdir(parents=True)
        (root / "dist" / "cli" / "rdc-mac-arm64.sha256").write_text(
            "%s  rdc-mac-arm64\n" % OTHER_SHA, encoding="utf-8"
        )
    if kw.get("cwd"):
        where = root / kw["cwd"]
        where.mkdir(parents=True, exist_ok=True)
        elsewhere_checksums = kw.get("elsewhere_checksums")
        if elsewhere_checksums:
            (where / "in").mkdir(parents=True, exist_ok=True)
            for filename, body in elsewhere_checksums.items():
                (where / "in" / filename).write_text(body, encoding="utf-8")
    return root


def sealed_path(
    root: pathlib.Path, *, drop: tuple[str, ...] = (), dirname_fails: bool = False
) -> str:
    """The ONLY directory on PATH for the subject."""
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


def produced(root: pathlib.Path) -> dict[str, str]:
    """Every file the run left behind, hashed, keyed by its path inside the root."""
    out: dict[str, str] = {}
    for entry in sorted(p.name for p in root.iterdir() if p.name not in KEEP):
        base = root / entry
        if base.is_file():
            out[entry] = "file:" + hashlib.sha256(base.read_bytes()).hexdigest()[:16]
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


def run(subject: pathlib.Path, tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    """One subject, once, inside its own freshly built repo root."""
    kw = CASE_KW[name]
    root = build(tmp_path, name)
    call_log = root / "calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        # REPLACED, never prepended.
        "PATH": sealed_path(
            root, drop=kw.get("drop", ()), dirname_fails=kw.get("dirname_fails", False)
        ),
        "HOME": str(root),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(kw.get("env") or {})
    runner = BASH if subject.suffix == ".sh" else PYTHON
    proc = subprocess.run(
        [runner, str(root / (TWIN_REL if subject.suffix == ".sh" else PORT_REL)), *kw["args"]],
        cwd=str(root / kw["cwd"]) if kw.get("cwd") else str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )

    def mask(text: str) -> str:
        return SELF_RE.sub("<SELF>", text.replace(str(root), "<root>"))

    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(call_log.read_text(encoding="utf-8")),
        mask(json.dumps(produced(root), indent=2, sort_keys=True)),
    )


def render(code: int, stdout: str, stderr: str, calls: str, files: str) -> str:
    return "%s%s%s%s%s\n" % (
        frozen.render(code, stdout, stderr),
        CALLS_MARKER,
        calls,
        FILES_MARKER,
        files,
    )


def recorded(name: str) -> tuple[int, str, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, rest = rest.split(CALLS_MARKER, 1)
    calls, files = rest.split(FILES_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        calls,
        files.removesuffix("\n"),
    )


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    return run(pathlib.Path(PORT_REL), tmp_path / name, name)


def files_of(state: str) -> dict[str, str]:
    return json.loads(state)


def manifest_in(tmp_path: pathlib.Path, name: str, rel: str = "out/manifest.json") -> dict:
    """The manifest the PORT writes, read back from the case's own root.

    The recorded `--- files ---` section carries a HASH of every produced file, which catches any change to the bytes but cannot say what changed. A case that wants to name a URL or a hash re-runs the port and reads the JSON, and the comparison above is what guarantees those are the same bytes the twin wrote.
    """
    compare(tmp_path, name)
    return json.loads((tmp_path / name / "repo" / rel).read_text(encoding="utf-8"))


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    want = recorded(name)
    got = run(pathlib.Path(PORT_REL), tmp_path / name, name)
    labels = ("exit code", "stdout", "stderr", "the CALL LOG", "the files produced")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The controls the rest rests on ---------------------------------------------------------------------------


def test_the_sealed_path_holds_only_the_six_named_tools(tmp_path: pathlib.Path) -> None:
    root = build(tmp_path, "one-binary")
    sealed = sealed_path(root)
    for name in (*PLAIN, *RECORDED, "date"):
        assert shutil.which(name, path=sealed) == str(root / "fixture-bin" / name)
    for absent in ("npm", "node", "git", "bash", "python3", "curl"):
        assert shutil.which(absent, path=sealed) is None, "%s is reachable" % absent
    assert shutil.which("jq", path=sealed_path(root, drop=("jq",))) is None


def test_the_frozen_date_really_answers_and_is_recorded(tmp_path: pathlib.Path) -> None:
    """A `date` fake that printed nothing would make `releaseDate` empty in every recording and every replay alike, and the comparison would still pass, so the fake is checked before anything leans on it."""
    root = build(tmp_path, "one-binary")
    log = root / "probe.log"
    log.write_text("", encoding="utf-8")
    proc = subprocess.run(
        ["date", "-u", gcm.DATE_FORMAT],
        env={"PATH": sealed_path(root), "FAKE_CALL_LOG": str(log)},
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert proc.stdout == FROZEN_DATE + "\n"
    assert log.read_text(encoding="utf-8") == "CALL date\t-u\t%s\n" % gcm.DATE_FORMAT


# --------------------------------------------------------------------------- What the recordings say: the success path ---------------------------------------------------------------------------


def test_one_valid_checksum_produces_one_binary_and_nine_lines(tmp_path: pathlib.Path) -> None:
    code, stdout, stderr, calls, _ = recorded("one-binary")
    assert code == 0
    assert stdout == ""
    assert stderr == (
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
    ), stderr
    assert calls.startswith("CALL date\t-u\t%s\nCALL jq\t-n\t" % gcm.DATE_FORMAT)
    assert "CALL awk\t{print $1}\tin/rdc-linux-x64.sha256\n" in calls
    assert manifest_in(tmp_path, "one-binary") == {
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


def test_all_six_binaries_are_added_in_the_twins_iteration_order(tmp_path: pathlib.Path) -> None:
    got = manifest_in(tmp_path, "all-six-binaries")
    assert list(got["binaries"]) == [
        "linux-x64",
        "linux-arm64",
        "mac-x64",
        "mac-arm64",
        "win-x64",
        "win-arm64",
    ]
    assert got["binaries"]["win-arm64"]["url"] == (
        "https://releases.rediacc.com/cli/v2.0.0/rdc-win-arm64.exe"
    )


def test_the_default_output_is_the_input_directorys_manifest_json() -> None:
    code, _, stderr, _, files = recorded("the-default-output")
    assert code == 0
    assert "✓   Output: in/manifest.json\n" in stderr
    assert "in/manifest.json" in files_of(files)


def test_the_default_input_is_the_repo_roots_dist_cli_and_is_absolute(
    tmp_path: pathlib.Path,
) -> None:
    """Half of defect 3: with no `--input` the directory is ABSOLUTE, resolved from the script's own location and not from the caller's cwd, which is why this case is driven from a different working directory."""
    code, _, stderr, _, files = recorded("the-default-input")
    assert code == 0
    assert "✓   Input: <root>/dist/cli\n" in stderr
    assert "dist/cli/manifest.json" in files_of(files)
    assert (
        manifest_in(tmp_path, "the-default-input", "dist/cli/manifest.json")["binaries"][
            "mac-arm64"
        ]["sha256"]
        == OTHER_SHA
    )


def test_defect_3_an_explicit_relative_input_follows_the_caller_not_the_root(
    tmp_path: pathlib.Path,
) -> None:
    """The other half of defect 3. There is no `cd "$(get_repo_root)"` here, unlike every sibling in `.ci/scripts/build/`, so `--input in` means `$PWD/in`. Driven from a directory holding a DIFFERENT `in/`, and the recorded file map is what shows which one was read and where the output landed."""
    code, _, _, _, files = recorded("a-relative-input-follows-the-caller")
    assert code == 0
    produced_files = files_of(files)
    assert "elsewhere/m.json" in produced_files, produced_files
    assert "m.json" not in produced_files, "the output landed in the repo, not the caller's cwd"
    got = manifest_in(tmp_path, "a-relative-input-follows-the-caller", "elsewhere/m.json")
    assert list(got["binaries"]) == ["win-x64"], got
    assert got["binaries"]["win-x64"]["sha256"] == OTHER_SHA


# --------------------------------------------------------------------------- The channel and the environment ---------------------------------------------------------------------------


def test_stable_edge_and_an_empty_channel_all_get_the_versioned_url(
    tmp_path: pathlib.Path,
) -> None:
    """A release channel bakes the immutable `/cli/v<version>/` path so homebrew and the long cache can pin it."""
    for name in ("the-stable-channel", "the-edge-channel", "an-empty-channel"):
        got = manifest_in(tmp_path, name, "o.json")
        assert got["binaries"]["linux-x64"]["url"] == (
            "https://releases.rediacc.com/cli/v1.2.3/rdc-linux-x64"
        ), name


def test_any_other_channel_gets_its_own_path(tmp_path: pathlib.Path) -> None:
    """Every other channel points at `/cli/<channel>/` so `rdc update` fetches the bits that were actually uploaded for that pull request. Asserting only one side of the branch would let it invert unnoticed."""
    got = manifest_in(tmp_path, "a-pull-request-channel", "o.json")
    assert got["binaries"]["linux-x64"]["url"] == (
        "https://releases.rediacc.com/cli/pr-42/rdc-linux-x64"
    )


def test_releases_base_url_overrides_the_host_and_an_empty_value_does_not(
    tmp_path: pathlib.Path,
) -> None:
    """`${RELEASES_BASE_URL:-...}` falls back on UNSET and on empty alike."""
    assert manifest_in(tmp_path, "a-releases-base-url")["binaries"]["linux-x64"]["url"].startswith(
        "https://staging.example/"
    )
    assert manifest_in(tmp_path, "an-empty-releases-base-url")["binaries"]["linux-x64"][
        "url"
    ].startswith(gcm.DEFAULT_RELEASES_BASE)


def test_an_absent_github_sha_becomes_the_literal_unknown(tmp_path: pathlib.Path) -> None:
    assert manifest_in(tmp_path, "an-absent-github-sha")["commit"] == gcm.DEFAULT_COMMIT


def test_the_repo_flag_only_moves_the_release_notes_url(tmp_path: pathlib.Path) -> None:
    got = manifest_in(tmp_path, "a-repo-flag")
    assert got["releaseNotesUrl"] == "https://github.com/someone/fork/releases/tag/v1.2.3"
    assert got["binaries"]["linux-x64"]["url"].startswith(gcm.DEFAULT_RELEASES_BASE)


# --------------------------------------------------------------------------- The argument parser ---------------------------------------------------------------------------


def test_help_goes_to_stdout_and_exits_zero() -> None:
    for name in ("the-short-help-flag", "the-long-help-flag"):
        code, stdout, stderr, _, _ = recorded(name)
        assert code == 0, name
        assert stderr == "", name
        assert stdout == (
            "Usage: <SELF> --version VERSION [--input DIR] [--output PATH] "
            "[--repo REPO] [--channel CHANNEL]\n"
        ), stdout


def test_an_unknown_option_and_a_positional_are_the_same_refusal() -> None:
    code, _, stderr, _, _ = recorded("an-unknown-option")
    assert code == 1
    assert stderr == "✗ Unknown option: --bogus\n"
    code, _, stderr, _, _ = recorded("a-positional-argument")
    assert code == 1
    assert stderr == "✗ Unknown option: 1.2.3\n"


def test_a_missing_or_empty_version_is_refused() -> None:
    for name in ("a-missing-version", "an-empty-version"):
        code, _, stderr, _, _ = recorded(name)
        assert code == 1, name
        assert stderr == "✗ %s\n" % gcm.NO_VERSION_MESSAGE, name


def test_defect_4_every_dangling_flag_is_bashs_own_unbound_variable() -> None:
    """`$2` under `set -u`, reported with the ARM's line number rather than the flag's name. Each of the five value-taking arms has its own line, so each has its own recording."""
    for flag, line in gcm.FLAG_LINES.items():
        code, _, stderr, calls, _ = recorded("a-dangling-%s" % flag.lstrip("-"))
        assert code == 1, flag
        assert stderr == "<SELF>: line %d: $2: unbound variable\n" % line, flag
        assert calls == "", "something ran before the parser gave up on %s" % flag


# --------------------------------------------------------------------------- The defects ---------------------------------------------------------------------------


def test_defect_1_an_input_with_no_checksums_is_an_empty_manifest_and_exit_zero(
    tmp_path: pathlib.Path,
) -> None:
    """The known hazard the cli-manifest proxy reports and does not enforce: a release published from this manifest offers no downloads at all."""
    code, _, stderr, _, _ = recorded("no-checksums-at-all")
    assert code == 0, "a manifest with no binaries was refused; defect 1 is gone"
    assert stderr.endswith("✓ Manifest generated: out/manifest.json\n")
    assert stderr.count("Skipping") == 6
    assert manifest_in(tmp_path, "no-checksums-at-all")["binaries"] == {}


def test_defect_2_four_different_bad_checksums_all_become_one_warning(
    tmp_path: pathlib.Path,
) -> None:
    """An empty file, a truncated hash, a multi-line file and an over-long hash are distinct situations; `:117-120` folds all of them into `⚠ Invalid checksum` and a `continue`, and none of them changes the exit code."""
    for name in (
        "an-empty-checksum-file",
        "a-truncated-checksum",
        "a-two-line-checksum-file",
        "a-sixty-five-character-hash",
    ):
        code, _, stderr, _, _ = recorded(name)
        assert code == 0, name
        assert "⚠   Invalid checksum for rdc-linux-x64, skipping\n" in stderr, name
        assert manifest_in(tmp_path, name)["binaries"] == {}, name


def test_a_checksum_file_with_leading_whitespace_still_yields_the_first_field(
    tmp_path: pathlib.Path,
) -> None:
    """`awk '{print $1}'` skips leading blanks, so this one IS accepted. A NEGATIVE control on defect 2's warning: the port must not tighten it."""
    code, _, stderr, _, _ = recorded("leading-whitespace-in-the-checksum")
    assert code == 0
    assert "Invalid checksum" not in stderr
    assert (
        manifest_in(tmp_path, "leading-whitespace-in-the-checksum")["binaries"]["linux-x64"][
            "sha256"
        ]
        == VALID_SHA
    )


# --------------------------------------------------------------------------- Missing tools ---------------------------------------------------------------------------


def test_a_missing_jq_is_a_named_refusal_after_three_log_lines() -> None:
    code, _, stderr, _, files = recorded("no-jq-on-the-path")
    assert code == 1
    assert stderr.endswith("✗ %s\n" % gcm.NO_JQ_MESSAGE), stderr
    assert "out" not in files_of(files)


def test_a_missing_awk_stops_at_127_rather_than_skipping_the_binary() -> None:
    """The reason `awk` is spawned rather than reimplemented. `SHA256="$(awk ...)"` is an assignment, so `set -e` takes the substitution's status: the run STOPS at 127 instead of quietly recording a manifest with no binaries."""
    code, _, stderr, _, files = recorded("no-awk-on-the-path")
    assert code == 127, stderr
    assert stderr.endswith("<SELF>: line %d: awk: command not found\n" % gcm.AWK_LINE), stderr
    assert "out" not in files_of(files), "a manifest was written despite the stop"


def test_a_missing_date_stops_before_a_single_log_line() -> None:
    code, _, stderr, _, _ = recorded("no-date-on-the-path")
    assert code == 127, stderr
    assert stderr == "<SELF>: line %d: date: command not found\n" % gcm.DATE_LINE, stderr
    assert "Generating CLI manifest" not in stderr


def test_a_missing_mkdir_stops_after_every_binary_is_added() -> None:
    code, _, stderr, _, _ = recorded("no-mkdir-on-the-path")
    assert code == 127, stderr
    assert "✓   Added linux-x64" in stderr
    assert stderr.endswith("<SELF>: line %d: mkdir: command not found\n" % gcm.MKDIR_LINE), stderr


def test_a_failing_dirname_does_not_stop_the_run(tmp_path: pathlib.Path) -> None:
    """THE CONTROL FOR `capture_lax`, and the reason it exists.

    `mkdir -p "$(dirname "$OUTPUT_PATH")"` at `:136` is a substitution used as an ARGUMENT, not as the command, so `set -e` does NOT take its status: the only status that counts is `mkdir`'s. A port that used the strict helper here would stop where the twin carried on. Reaching that question needs a `dirname` that ANSWERS and then exits 1; removing `dirname` outright cannot reach
    it, which is the next case.
    """
    code, _, _, _, files = recorded("a-failing-dirname")
    assert code == 0
    assert "out/manifest.json" in files_of(files)
    assert manifest_in(tmp_path, "a-failing-dirname")["binaries"]["linux-x64"]["sha256"] == (
        VALID_SHA
    )


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_the_twin_could_not_start_without_dirname_and_the_port_can(
    tmp_path: pathlib.Path,
) -> None:
    """A DOCUMENTED DIVERGENCE, recorded rather than assumed.

    The twin resolved its own `SCRIPT_DIR` at `:16` with `cd "$(dirname "${BASH_SOURCE[0]}")"`, so a PATH without `dirname` killed it before line 17. The port resolves its own path in-process and gets all the way to `:136`, where its one real `dirname` call is missing and `mkdir -p ''` then fails: exit 1 as well, but for a different reason and after doing all the work.

    THE RECORDED HALF IS BASH-VERSION-DEPENDENT, which is exactly why it is evidence and not an expectation. On bash 5.3 `cd ""` FAILS and the script dies at line 16; on bash 5.2 it succeeds silently and the script dies one line later, unable to source `../lib/common.sh`. Hard-coding the 5.3 tail once made this pass on every machine in this tree and fail in CI run 34970782616. Only
    the port's half is compared here; the recording is kept for what it says about the twin, and only its version-independent part is read.
    """
    name = "no-dirname-on-the-path"
    want = recorded(name)
    got = run(pathlib.Path(PORT_REL), tmp_path / name, name)
    assert want[0] == got[0] == 1
    assert want[1] == got[1] == ""
    # Version-independent, and the real point of the recording: the missing `dirname` was reported from inside the command substitution, and no manifest work happened on any bash.
    assert "line 16: dirname: command not found" in want[2], want[2]
    assert "Generating CLI manifest" not in want[2]
    assert "✓   Added linux-x64" in got[2]
    assert "mkdir: cannot create directory" in got[2], got[2]


# --------------------------------------------------------------------------- The live tree, deliberately NOT recorded ---------------------------------------------------------------------------


def test_the_port_agrees_with_common_sh_about_the_repo_root_in_this_checkout() -> None:
    """NOT RECORDED: it reads the LIVE `common.sh` and the live checkout, and a golden would freeze both."""
    proc = subprocess.run(
        [BASH, "-c", 'source "$1" && get_repo_root', "bash", str(ROOT / COMMON_REL)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert proc.stdout.strip() == str(gcm.repo_root())
    assert proc.stdout.strip() == str(ROOT)


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_lenient_hash_length_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, and it plants what a reader "being lenient about hash formats" would write.

    A hash that is not 64 characters is discarded with a warning;

    Accepting a shorter one puts a checksum in the manifest that no download can ever match, and `rdc update` then refuses every binary it fetches. the plant drops the length test altogether and accepts any non-empty hash, which is invisible on every valid checksum and visible on exactly one recording, the six-character truncated hash, which turns from a warning
    and an empty `binaries` object into an entry the manifest enshrines. Both streams and the file map move together, which is what the recording is for.

    THE PLANT IS A COPY, AND IT IS WRITTEN AT THE PORT'S OWN PATH INSIDE THE FIXTURE, which is the only place a copy of this module can run: it resolves its repository root from its own location, so a copy under a temporary directory would answer a different root and read a different input directory. The tracked file is never written.
    """
    original = (ROOT / PORT_REL).read_text(encoding="utf-8")
    anchor = "if not sha256 or len(sha256) != SHA256_LENGTH:"
    assert original.count(anchor) == 1, "the plant's anchor moved"

    name = "a-truncated-checksum"
    want = recorded(name)
    assert "\u26a0   Invalid checksum for rdc-linux-x64, skipping\n" in want[2], "the corpus moved"

    root = build(tmp_path / "planted", name)
    (root / PORT_REL).write_text(original.replace(anchor, "if not sha256:"), encoding="utf-8")
    call_log = root / "calls.log"
    call_log.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [PYTHON, str(root / PORT_REL), *CASE_KW[name]["args"]],
        cwd=str(root),
        capture_output=True,
        text=True,
        env={
            "PATH": sealed_path(root),
            "HOME": str(root),
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "PYTHONPATH": str(root / ".ci"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "FAKE_CALL_LOG": str(call_log),
        },
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Invalid checksum" not in proc.stderr, "the plant did not change the verdict"
    planted = json.loads((root / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert planted["binaries"]["linux-x64"]["sha256"] == "abc123", planted

    compare(tmp_path / "good", name)
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == original
