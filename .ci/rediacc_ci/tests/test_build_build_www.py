"""`rediacc_ci.build.build_www`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/build/build-www.sh` and the port inside one throwaway fixture root and compared exit code, stdout, stderr and the recording fake's call log. The ledger `.ci/shadow/w7p6-build-www.observations.jsonl` holds 5 rows of that comparison.

Every fixture case now compares against `goldens/build-www/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

IT WAS SAFE TO RETIRE, and that was established before anything was deleted. The one live invocation is already the port, `.github/workflows/ci-build-docker.yml:123`, as `PYTHONPATH=.ci python3 -m rediacc_ci.build.build_www`.

The only other reference was a CLOSURE PATH LIST that is hashed to decide whether a docker build can be skipped, and that list exists twice, at `rediacc_ci/ci/generate_tag.py:122` and `.ci/scripts/ci/generate-tag.sh:217`.

Both were flipped to the port's path and the generate-tag differential was re-run with both of ITS copies still present, which is the live evidence that the two lists still agree and the closure hash still resolves.

`npm` IS NEVER REAL, and the PATH is REPLACED rather than prepended. That is not a formality: `npm run build:www` in this checkout is an Astro build of the marketing site, several minutes and several gigabytes, and a scratch PATH with the caller's own appended still resolves the real binary. `test_the_scratch_path_cannot_reach_a_real_npm` asserts it cannot, in both directions.

`rediacc_ci` IS VENDORED INTO THE FIXTURE rather than reached through an absolute `PYTHONPATH`, which proves the port needs only the six modules listed in `VENDORED`. A seventh entry appearing there means the port grew a dependency, which is worth noticing.

WHICH CASES ARE RECORDED AND WHICH ARE NOT. Every case driving the fixture has a golden. `test_the_port_agrees_with_common_sh_about_the_repo_root_in_this_checkout` does NOT: it reads the LIVE `common.sh` and the live checkout, and freezing it would freeze a tracked file's content into a golden. The two PATH-seal assertions are controls over the fixture rather than recordings of the
subject, so they stay live too.

WHAT IS MASKED, and it is three things. `<SELF>` is the subject's own path, which bash names in its `command not found` line and which `sys.argv[0]` spells with a `.py`; `<root>` is the throwaway fixture root, rebuilt under a different temporary name every run; `<repo>` is the checkout root. Nothing else is touched, and both streams are compared SEPARATELY, never merged.

THE THREE DEFECTS EACH HAVE THEIR OWN RECORDING, and each is preserved rather than repaired: npm's exit code is flattened to 1 so the workflow cannot tell an OOM kill from a compilation failure; the green tick is printed on npm's status alone, before anything is verified, so a run that produced an empty dist prints a success line and THEN refuses; and both `require_*` labels are
dropped by `common.sh`, so the operator is never told WHICH build produced nothing. Each assertion is written so that it fires the day the subject is repaired rather than quietly agreeing with a fixed one.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.build import build_www as bw
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()

PORT_REL = ".ci/rediacc_ci/build/build_www.py"
TWIN_REL = ".ci/scripts/build/build-www.sh"
COMMON_REL = ".ci/scripts/lib/common.sh"

SLUG = "build-www"
CALLS_MARKER = "--- calls ---\n"

# Everything the port imports, transitively, and nothing else.
VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/build/__init__.py",
)

BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

# `dirname` for `get_repo_root` (common.sh:207), `uname` because SOURCING common.sh runs `CI_OS="$(detect_os)"` and `CI_ARCH="$(detect_arch)"` at :509-510, two forks on every source whether or not the caller wants them, and `mkdir` for the fake npm's own bookkeeping. Anything not listed is ABSENT.
#
# THE `uname` FORKS WERE A NAMED DIVERGENCE, not a reproduced one: the port imports a module rather than sourcing a library, so it never runs them. It is invisible in output on any machine that HAS uname, and on one that does not the twin printed two `common.sh: line 64: uname: command not found` lines the port has no reason to forge. The fixture therefore supplies uname.
PATH_MINIMUM = ("dirname", "uname", "mkdir")

# The recording fake. It writes its own argv to the call log with a distinct prefix, the same prefix the K=5 ledger scoped `--finding-re` to, because `shadow-gate.ts` classifies every `→ `/`✓ ` line as CHATTER before any message-text regex is consulted and this subject reports ONLY through those two glyphs on its success path.
FAKE_NPM = """#!/bin/bash
printf 'CALL npm' >>"$FAKE_CALL_LOG"
for a in "$@"; do printf '\\t%s' "$a" >>"$FAKE_CALL_LOG"; done
printf '\\n' >>"$FAKE_CALL_LOG"
if [[ -n "${FAKE_NPM_STDOUT:-}" ]]; then echo "$FAKE_NPM_STDOUT"; fi
if [[ -n "${FAKE_NPM_STDERR:-}" ]]; then echo "$FAKE_NPM_STDERR" >&2; fi
if [[ -n "${FAKE_NPM_MAKE_DIST:-}" ]]; then mkdir -p "$FAKE_NPM_MAKE_DIST"; fi
if [[ -n "${FAKE_NPM_MAKE_INDEX:-}" ]]; then
    mkdir -p "$(dirname "$FAKE_NPM_MAKE_INDEX")"
    echo '<html></html>' >"$FAKE_NPM_MAKE_INDEX"
fi
exit "${FAKE_NPM_RC:-0}"
"""

# `$0` as bash printed it: the ABSOLUTE path the script was invoked with, whose fixture-root prefix is also per-run.
SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))

# name -> the environment the fake npm reads its behaviour from, plus the two fixture switches. `@ROOT@` is resolved to the fixture root, which is the only way a case can ask the fake to create a path inside it.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "a-complete-build": {"env": {"FAKE_NPM_MAKE_INDEX": "@ROOT@/%s" % bw.INDEX_HTML}},
    "a-missing-dist-directory": {},
    "a-dist-without-an-index": {"env": {"FAKE_NPM_MAKE_DIST": "@ROOT@/%s" % bw.DIST_DIR}},
    "a-failing-npm": {"env": {"FAKE_NPM_RC": "1"}},
    "npm-exiting-three": {"env": {"FAKE_NPM_RC": "3"}},
    "npm-exiting-one-three-seven": {"env": {"FAKE_NPM_RC": "137"}},
    "no-npm-on-the-path": {"drop_npm": True},
    "a-caller-elsewhere-with-a-decoy": {"decoy": True},
    "npms-own-two-streams": {
        "env": {
            "FAKE_NPM_STDOUT": "astro: building 42 pages",
            "FAKE_NPM_STDERR": "astro: warning: unused import",
            "FAKE_NPM_MAKE_INDEX": "@ROOT@/%s" % bw.INDEX_HTML,
        }
    },
}

CASES = tuple(CASE_KW)


def fixture(where: pathlib.Path, subject: pathlib.Path) -> pathlib.Path:
    """A throwaway tree holding the subject and the libraries it needs."""
    root = where / "repo"
    for rel in (PORT_REL, COMMON_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / COMMON_REL, root / COMMON_REL)
    for rel in VENDORED:
        shutil.copy2(ROOT / rel, root / rel)
    if subject.suffix == ".sh":
        (root / TWIN_REL).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / TWIN_REL, root / TWIN_REL)
    else:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    return root


def scratch_bin(root: pathlib.Path, *, drop_npm: bool = False) -> str:
    """The ONLY directory on PATH for the subject."""
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    npm = stub / "npm"
    if drop_npm:
        if npm.exists():
            npm.unlink()
    else:
        npm.write_text(FAKE_NPM, encoding="utf-8")
        npm.chmod(0o755)
    return str(stub)


def run(subject: pathlib.Path, where: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    """One subject, once, inside its own throwaway root."""
    kw = CASE_KW[name]
    where.mkdir(parents=True, exist_ok=True)
    root = fixture(where, subject)
    call_log = root / "calls.log"
    call_log.write_text("", encoding="utf-8")
    cwd = str(root)
    if kw.get("decoy"):
        # A directory that is NOT the fixture root and that holds a decoy index.html: a subject reading paths relative to the CALLER would find it and exit 0.
        decoy = where / "elsewhere"
        (decoy / bw.DIST_DIR).mkdir(parents=True, exist_ok=True)
        (decoy / bw.INDEX_HTML).write_text("decoy", encoding="utf-8")
        cwd = str(decoy)
    env = {
        # REPLACED, never prepended. See the module docstring.
        "PATH": scratch_bin(root, drop_npm=kw.get("drop_npm", False)),
        "HOME": str(where),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    for key, value in (kw.get("env") or {}).items():
        env[key] = value.replace("@ROOT@", str(root))
    target = root / (TWIN_REL if subject.suffix == ".sh" else PORT_REL)
    proc = subprocess.run(
        [BASH if subject.suffix == ".sh" else PYTHON, str(target)],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )

    def mask(text: str) -> str:
        folded = SELF_RE.sub("<SELF>", text)
        return folded.replace(str(root), "<root>").replace(str(ROOT), "<repo>")

    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(call_log.read_text(encoding="utf-8")),
    )


def render(code: int, stdout: str, stderr: str, calls: str) -> str:
    return "%s%s%s" % (frozen.render(code, stdout, stderr), CALLS_MARKER, calls)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    return run(pathlib.Path(PORT_REL), tmp_path / name, name)


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = run(pathlib.Path(PORT_REL), tmp_path / name, name)
    labels = ("exit code", "stdout", "stderr", "the npm CALL LOG")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The control on the control: the scratch PATH really is sealed ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_npm(tmp_path: pathlib.Path) -> None:
    """A PREPENDED PATH would still resolve the real npm, and the real `npm run build:www` is a multi-minute Astro build of this repository. So the fixture REPLACES PATH, and this asserts the replacement holds in both directions: the fake is reachable, and dropping it leaves nothing behind it."""
    root = fixture(tmp_path, pathlib.Path(PORT_REL))
    sealed = scratch_bin(root)
    assert shutil.which("npm", path=sealed) == str(root / "fixture-bin" / "npm")
    dropped = scratch_bin(root, drop_npm=True)
    assert shutil.which("npm", path=dropped) is None, "a real npm is reachable from the fixture"
    assert shutil.which("node", path=dropped) is None
    assert shutil.which("docker", path=dropped) is None


# --------------------------------------------------------------------------- What the recordings say: the four exit paths ---------------------------------------------------------------------------


def test_a_complete_build_prints_three_lines_and_exits_zero() -> None:
    code, stdout, stderr, calls = recorded("a-complete-build")
    assert code == 0, stderr
    assert stdout == ""
    assert stderr == (
        "→ Building www (Astro)...\n"
        "✓ www build completed\n"
        "✓ www build complete: packages/www/dist/\n"
    )
    assert calls == "CALL npm\trun\tbuild:www\n"


def test_a_missing_dist_directory_refuses_with_the_generic_sentence() -> None:
    """DEFECT 1, recorded. `require_dir "packages/www/dist" "www build output"` passes a label that `common.sh:161-167` never reads, so the operator is told nothing about WHICH build produced nothing. The assertion is on the label's ABSENCE, so it fires the day the subject is repaired rather than quietly agreeing with a fixed one."""
    code, stdout, stderr, _ = recorded("a-missing-dist-directory")
    assert code == 1
    assert stderr.endswith("✗ Required directory 'packages/www/dist' does not exist\n"), stderr
    assert bw.DIST_DIR_LABEL not in stderr
    assert bw.DIST_DIR_LABEL not in stdout


def test_a_dist_without_an_index_refuses_on_the_file() -> None:
    """The second `require_*`, and its label is dropped the same way."""
    code, _, stderr, _ = recorded("a-dist-without-an-index")
    assert code == 1
    assert stderr.endswith("✗ Required file 'packages/www/dist/index.html' does not exist\n"), (
        stderr
    )
    assert bw.INDEX_HTML_LABEL not in stderr


def test_a_failing_npm_is_reported_as_a_failed_build() -> None:
    code, _, stderr, _ = recorded("a-failing-npm")
    assert code == 1
    assert stderr == "→ Building www (Astro)...\n✗ www build failed\n", stderr


# --------------------------------------------------------------------------- The defects, each with its own recording ---------------------------------------------------------------------------


def test_defect_npms_exit_code_is_flattened_to_one() -> None:
    """DEFECT 2. npm exiting 3, or 137 for an OOM kill, makes this subject exit 1, so the workflow step cannot tell an infrastructure failure from a compilation failure. `buildx-push-web.sh` one file over did the opposite and let docker's status through, which is what makes this a defect rather than a house rule."""
    for name, npm_rc in (("npm-exiting-three", "3"), ("npm-exiting-one-three-seven", "137")):
        code, _, _, _ = recorded(name)
        assert code == 1, "npm rc %s leaked through as %s" % (npm_rc, code)


def test_defect_the_green_tick_precedes_every_verification() -> None:
    """DEFECT 3. `✓ www build completed` is printed on npm's exit code alone, so a run that produced an empty dist prints a success line and THEN refuses. Pinned by ORDER, which is the only way it is visible."""
    lines = recorded("a-missing-dist-directory")[2].splitlines()
    assert lines[1] == "✓ www build completed"
    assert lines[2].startswith("✗ ")


def test_a_missing_npm_reads_as_a_failed_build_with_bashs_line_above_it() -> None:
    """The shell's own diagnostic is the ONLY evidence the tool was absent, so the port forges it rather than tracebacking. `$0` is masked; the line number, the binary name and the reason are recorded exactly."""
    code, _, stderr, calls = recorded("no-npm-on-the-path")
    assert code == 1
    assert stderr == (
        "→ Building www (Astro)...\n"
        "<SELF>: line %d: npm: command not found\n"
        "✗ www build failed\n" % bw.NPM_LINE
    ), stderr
    assert calls == ""


# --------------------------------------------------------------------------- The `cd` and the stream discipline ---------------------------------------------------------------------------


def test_the_subject_cds_to_the_repo_root_whatever_the_caller_did() -> None:
    """The `cd` is observable: every later path is relative, so a run that skipped it would refuse with the same sentence for a completely different reason. Driven from a directory that is NOT the fixture root and that holds a decoy `packages/www/dist/index.html`, which a subject reading paths relative to the CALLER would find and exit 0 on."""
    code, _, stderr, _ = recorded("a-caller-elsewhere-with-a-decoy")
    assert code == 1, "the decoy was picked up: the subject did not cd"
    assert "Required directory 'packages/www/dist' does not exist" in stderr


def test_npms_own_two_streams_are_inherited_unmerged() -> None:
    """A build log is the caller's, not this subject's. The stream a line arrives on is part of the contract, the 2026-09-06 emit-advisory incident was a stream SWAP, so the fake writes to both and each is recorded separately."""
    code, stdout, stderr, _ = recorded("npms-own-two-streams")
    assert code == 0, stderr
    assert stdout == "astro: building 42 pages\n"
    assert "astro: warning: unused import\n" in stderr


# --------------------------------------------------------------------------- The live tree, deliberately NOT recorded ---------------------------------------------------------------------------


def test_the_port_agrees_with_common_sh_about_the_repo_root_in_this_checkout() -> None:
    """NOT RECORDED: it reads the LIVE `common.sh` and the live checkout.

    Both answers come from a file's own location three levels up, but from DIFFERENT files, so a directory move that touched one and not the other would go unnoticed until a build ran in the wrong place.
    """
    proc = subprocess.run(
        [BASH, "-c", 'source "$1" && get_repo_root', "bash", str(ROOT / COMMON_REL)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert proc.stdout.strip() == str(bw.repo_root())
    assert proc.stdout.strip() == str(ROOT)


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_swap_of_the_two_output_checks_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, and it is the smallest realistic plant.

    The two output checks are swapped, so the subject asks for the FILE before the DIRECTORY. Both orders exit 1 with an identical, empty call log on a tree with neither, and only the message text tells them apart, which is exactly what a comparison of exit codes alone would miss.

    THE PLANT IS A COPY WRITTEN AT THE SUBJECT'S OWN PATH INSIDE THE FIXTURE, which is where the module already runs from in every case here, so nothing about its own location changes. The tracked file is never written.
    """
    original = (ROOT / PORT_REL).read_text(encoding="utf-8")
    anchor = "        common.require_dir(DIST_DIR)\n        common.require_file(INDEX_HTML)\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"

    name = "a-missing-dist-directory"
    want = recorded(name)
    assert "Required directory" in want[2], "the recorded corpus moved"

    where = tmp_path / "planted"
    where.mkdir(parents=True)
    root = fixture(where, pathlib.Path(PORT_REL))
    (root / PORT_REL).write_text(
        original.replace(
            anchor,
            "        common.require_file(INDEX_HTML)\n        common.require_dir(DIST_DIR)\n",
        ),
        encoding="utf-8",
    )
    call_log = root / "calls.log"
    call_log.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [PYTHON, str(root / PORT_REL)],
        cwd=str(root),
        capture_output=True,
        text=True,
        env={
            "PATH": scratch_bin(root),
            "HOME": str(where),
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "PYTHONPATH": str(root / ".ci"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "FAKE_CALL_LOG": str(call_log),
        },
        check=False,
        timeout=120,
        input="",
    )
    assert proc.returncode == want[0] == 1, "the plant changed the exit code"
    assert "Required file" in proc.stderr, "the plant did not swap the checks"
    assert "Required directory" not in proc.stderr
    assert call_log.read_text(encoding="utf-8") == want[3], "the plant moved the call log"

    compare(tmp_path / "good", name)
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == original
