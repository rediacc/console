"""`rediacc_ci.release.install_script_check` against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. `.ci/scripts/test/test-install-script.sh` was the registered gate until this module took the registration; the K=5 ledger `.ci/shadow/w7p6-install-script.observations.jsonl` holds five rows of equivalence over five distinct trees, and `goldens/install-script/` holds the twin's OWN recorded bytes, captured on its last day in the tree. Each golden's
provenance header carries two blob shas, the twin's and the `install.sh` it ran against, so `git cat-file -p <sha>` still yields both programs.

WHICH CASES ARE RECORDED AND WHICH ARE NOT. Every case driving a FIXTURE has a golden. The two cases that run against the LIVE checkout do not: freezing them would freeze a tracked file's content into a golden, and the tracked file is the SUBJECT, so the recording would go stale the first time somebody edited `install.sh` and would red the port for a change it did not make.

THE TWIN STOPPED AT THE FIRST FAILURE -- its `log_fail` was an immediate `exit 1` -- so a green run says nothing about the thirteen assertions behind whichever one fired. Every case below therefore mutates a COPY of `packages/www/public/install.sh` so that exactly one chosen assertion is the one reached, and compares the port against the recording byte for byte from there.

THE COLOUR QUIRK IS PINNED HERE, IN BOTH DIRECTIONS, because it is the part of this pair a reader is most likely to "fix". `test-install-script.sh:26-33` sets `RED`/`GREEN`/`NC` and then every `log_pass` runs AFTER a `source "$INSTALL_SH"`, which reassigns those same three names -- to escapes on a tty and to EMPTY STRINGS otherwise (`install.sh:62-72`). So the twin's own constants
were dead, and the observable rule is install.sh's. The port is run twice: through a pipe, where it may emit no escape, and under a pty, where it must, and each is compared against a separate recording.

HOW THE TWO SIDES WERE POINTED AT A FIXTURE: the twin resolved `ROOT_DIR` from
`${BASH_SOURCE[0]}` and was COPIED into the fixture; the port resolves it through
`paths.repo_root()` and takes `$REDIACC_CI_ROOT`. The fixture no longer holds a copy of the twin, and that changes nothing the port can see: it reads `packages/www/public/install.sh` under `$REDIACC_CI_ROOT` and nothing else under that root.

WHAT IS NORMALIZED, AND IT IS ONLY THIS: `mktemp` paths. Two of the twin's messages embed `$HOME`, which is a fresh `mktemp -d` per case, so the two sides cannot agree on those bytes. Nothing else is masked.

K=5 LEDGER: `.ci/shadow/w7p6-install-script.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import typing

from rediacc_ci import paths
from rediacc_ci.release import install_script_check
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "release" / "install_script_check.py"
SLUG = "install-script"
INSTALL_SH_REL = "packages/www/public/install.sh"
INSTALL_SH = ROOT / INSTALL_SH_REL

# The VALUE is the twin's literal verdict prefix as a NON-tty run emits it. The NAME avoids "PASS", which ruff S105 reads as a hardcoded password.
OK_LINE = "PASS: "
BAD_LINE = "FAIL: "

TMP_RE = re.compile(re.escape(tempfile.gettempdir()) + r"/[^\s\"']*")

# Mutation anchors, each asserted present before use.
PLATFORM = '        Linux) echo "linux" ;;'
ARCH = '        x86_64 | amd64) echo "x64" ;;'
CHMOD_ABSENT = '        chmod 600 "$config_file"\n    fi'
RM_LEGACY = '        rm -rf "$LEGACY_VERSIONS_DIR"'
CHANNEL_GREP = '\'"updateChannel"[[:space:]]*:[[:space:]]*"[^"]+"\''
FOLLOW_UP = 'echo "    rdc update --channel $CHANNEL"'
LEGACY_DECL = 'LEGACY_VERSIONS_DIR="${INSTALL_PREFIX}/versions"'
WRONG_MODE = '        chmod 640 "$config_file"\n    fi'

# Every case with a golden. The two live-checkout cases are deliberately absent; the docstring says why.
RECORDED_CASES = {
    "unmutated",
    "unmutated-on-a-pty",
    "a-wrong-detect-platform",
    "a-wrong-detect-arch",
    "a-wrong-config-mode",
    "a-no-jq-path-with-the-wrong-command",
    "a-cleanup-that-leaves-the-legacy-dir",
    "a-reintroduced-versions-constant",
    "a-broken-channel-inheritance",
}


def norm(text: str) -> str:
    """Mask `mktemp` paths. Nothing else."""
    return TMP_RE.sub("<tmp>", text)


def build_fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    fixture = tmp_path / "fixture"
    (fixture / "packages" / "www" / "public").mkdir(parents=True, exist_ok=True)
    shutil.copy2(INSTALL_SH, fixture / INSTALL_SH_REL)
    return fixture


def mutate(fixture: pathlib.Path, old: str, new: str) -> None:
    target = fixture / INSTALL_SH_REL
    text = target.read_text(encoding="utf-8")
    assert text.count(old) == 1, "anchor %r appears %d times" % (old, text.count(old))
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def _argv(subject: pathlib.Path, fixture: pathlib.Path) -> tuple[list[str], dict[str, str]]:
    """The licensed invocation, verbatim: the ledger's `new` command in both its halves."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LC_ALL": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(fixture),
    }
    return ["python3", str(subject)], env


def _run(subject: pathlib.Path, fixture: pathlib.Path) -> subprocess.CompletedProcess[str]:
    argv, env = _argv(subject, fixture)
    return subprocess.run(argv, env=env, capture_output=True, text=True, check=False, timeout=180)


def _run_on_a_pty(subject: pathlib.Path, fixture: pathlib.Path) -> str:
    """Both streams, through a real pty, so `[ -t 1 ]` is true in the child.

    `pty.spawn` copies the child's output onto ITS OWN stdout, so the spawn runs in a helper process whose stdout this call captures.
    """
    argv, env = _argv(subject, fixture)
    helper = "import pty,sys; sys.exit(pty.spawn(%r))" % (argv,)
    return subprocess.run(
        ["python3", "-c", helper],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    ).stdout


def recorded(case: str) -> tuple[int, str, str]:
    """One golden, split back into exit code, stdout and stderr."""
    body = frozen.read(SLUG, case)
    head, rest = body.split("\n--- stdout ---\n", 1)
    out, err = rest.split("--- stderr ---\n", 1)
    return int(head[len("exit: ") :]), out, err


def assert_same(old: tuple[int, str, str], new: subprocess.CompletedProcess[str]) -> None:
    assert new.returncode == old[0], "exit: recorded %s, port %s" % (old[0], new.returncode)
    assert norm(new.stdout) == old[1]
    assert norm(new.stderr) == old[2]


def drive(case: str, tmp_path: pathlib.Path, mutation: tuple[str, str] | None = None):
    """Build the case's fixture, apply its mutation, run the port, return both sides."""
    fixture = build_fixture(tmp_path)
    if mutation is not None:
        mutate(fixture, *mutation)
    return recorded(case), _run(PORT, fixture), fixture


# --------------------------------------------------------------------------- The live checkout, deliberately NOT recorded ---------------------------------------------------------------------------


def test_the_live_tree_still_runs_every_case_green() -> None:
    """NOT RECORDED: it reads the LIVE `install.sh` and the live checkout.

    Freezing this would freeze a tracked file's content into a golden, and that tracked file is the SUBJECT. The assertion is therefore on the SHAPE the gate has to keep -- fifteen passes, the closing line, and a silent stderr -- which is what a caller of `test:install-script` depends on and what no recording could hold without going stale.
    """
    new = _run(PORT, ROOT)
    assert new.returncode == 0, new.stderr
    assert new.stdout.count(OK_LINE) == 15
    assert new.stdout.endswith("\nPASS: all install.sh unit cases\n")
    assert new.stderr == ""


def test_a_piped_run_carries_no_ansi_escape() -> None:
    """install.sh blanks the colours when stdout is not a tty, and the twin's own constants were already gone by then. A port that emitted its own escapes would look right in a terminal and wrong in every CI log."""
    new = _run(PORT, ROOT)
    assert "\033[" not in new.stdout
    assert new.stdout.startswith("PASS: detect_platform matches uname\n")


# --------------------------------------------------------------------------- The fixture cases, each against the twin's recording ---------------------------------------------------------------------------


def test_a_pty_run_carries_the_recorded_escapes(tmp_path: pathlib.Path) -> None:
    """A pty merges the two streams, so this case is recorded as stdout alone."""
    fixture = build_fixture(tmp_path)
    old = recorded("unmutated-on-a-pty")
    new = norm(_run_on_a_pty(PORT, fixture))
    assert "\033[0;32mPASS:\033[0m detect_platform matches uname" in old[1], repr(old[1][:120])
    assert new == old[1]


def test_unmutated_fixture_is_the_recorded_run(tmp_path: pathlib.Path) -> None:
    old, new, _ = drive("unmutated", tmp_path)
    assert new.returncode == 0, new.stderr
    assert_same(old, new)
    assert old[1].count(OK_LINE) == 15, "the recorded green run lost its passes"


# --------------------------------------------------------------------------- Seven of the fourteen cases, each reached by a real mutation ---------------------------------------------------------------------------


def test_a_wrong_detect_platform_is_caught_first(tmp_path: pathlib.Path) -> None:
    old, new, _ = drive(
        "a-wrong-detect-platform", tmp_path, (PLATFORM, '        Linux) echo "linuxx" ;;')
    )
    assert old[0] == 1
    assert old[2] == BAD_LINE + "detect_platform: expected linux, got linuxx\n"
    assert old[1] == "", "case one fails, so no PASS line is printed at all"
    assert_same(old, new)


def test_a_wrong_detect_arch_is_caught_second(tmp_path: pathlib.Path) -> None:
    old, new, _ = drive(
        "a-wrong-detect-arch", tmp_path, (ARCH, '        x86_64 | amd64) echo "x64x" ;;')
    )
    assert old[0] == 1
    assert old[2] == BAD_LINE + "detect_arch: expected x64, got x64x\n"
    assert old[1].count(OK_LINE) == 1
    assert_same(old, new)


def test_a_wrong_config_mode_is_caught(tmp_path: pathlib.Path) -> None:
    old, new, _ = drive("a-wrong-config-mode", tmp_path, (CHMOD_ABSENT, WRONG_MODE))
    assert old[0] == 1
    assert old[2] == BAD_LINE + "rediacc.json mode must be 600 (got 640)\n"
    assert old[1].count(OK_LINE) == 3
    assert_same(old, new)


def test_a_no_jq_path_that_prints_the_wrong_command_is_caught(tmp_path: pathlib.Path) -> None:
    """The branch that must NOT rewrite a live config, only advise about it."""
    old, new, _ = drive(
        "a-no-jq-path-with-the-wrong-command",
        tmp_path,
        (FOLLOW_UP, 'echo "    rdc upgrade --channel $CHANNEL"'),
    )
    assert old[0] == 1
    assert old[2].startswith(BAD_LINE + "no-jq path must print the follow-up command:")
    assert "rdc upgrade --channel edge" in old[2]
    assert old[1].count(OK_LINE) == 5
    assert_same(old, new)


def test_a_cleanup_that_leaves_the_legacy_dir_is_caught(tmp_path: pathlib.Path) -> None:
    """The one message that embeds a `mktemp` path, hence `norm()`."""
    old, new, _ = drive(
        "a-cleanup-that-leaves-the-legacy-dir",
        tmp_path,
        (RM_LEGACY, "        : # defect: the legacy dir is left behind"),
    )
    assert old[0] == 1
    assert old[2] == BAD_LINE + "cleanup_legacy_state must remove <tmp>\n"
    assert old[1].count(OK_LINE) == 6
    assert_same(old, new)


def test_a_reintroduced_versions_constant_is_caught(tmp_path: pathlib.Path) -> None:
    old, new, _ = drive(
        "a-reintroduced-versions-constant",
        tmp_path,
        (LEGACY_DECL, LEGACY_DECL + '\nVERSIONS_DIR="${INSTALL_PREFIX}/versions"'),
    )
    assert old[0] == 1
    assert old[2] == (
        BAD_LINE + "VERSIONS_DIR / MAX_VERSIONS must not be defined under the new layout\n"
    )
    assert old[1].count(OK_LINE) == 8
    assert_same(old, new)


def test_a_broken_channel_inheritance_is_caught(tmp_path: pathlib.Path) -> None:
    """The asymmetry that caused a real user-visible bug: a stable install followed by an immediate `rdc update` jumping to edge."""
    old, new, _ = drive(
        "a-broken-channel-inheritance",
        tmp_path,
        (CHANNEL_GREP, '\'"noSuchKey"[[:space:]]*:[[:space:]]*"[^"]+"\''),
    )
    assert old[0] == 1
    assert old[2] == (
        BAD_LINE + "config account.updateChannel=edge must be inherited, got: stable\n"
    )
    assert old[1].count(OK_LINE) == 10
    assert_same(old, new)


def test_the_corpus_and_the_goldens_are_the_same_set() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, RECORDED_CASES)


def test_the_recording_holds_both_verdicts() -> None:
    """A corpus of refusals only would agree with a port that never passes anything."""
    codes = {recorded(case)[0] for case in RECORDED_CASES}
    assert codes == {0, 1}, "the recording must hold a green and a red"


# --------------------------------------------------------------------------- The pure helpers ---------------------------------------------------------------------------


def test_the_nojq_shim_hides_jq_and_keeps_the_rest(tmp_path: pathlib.Path) -> None:
    shim = install_script_check.build_nojq_shim(tmp_path)
    assert not (shim / "jq").exists(), "hiding jq is the entire point of the shim"
    linked = sorted(p.name for p in shim.iterdir())
    assert linked, "the shim collapsed to nothing; the case would prove nothing"
    for name in linked:
        assert name in install_script_check.NOJQ_TOOLS
        assert (shim / name).is_symlink()
    # Every tool the host actually has must be there: a silently short shim would make the case measure the shim rather than install.sh.
    for tool in install_script_check.NOJQ_TOOLS:
        assert ((shim / tool).exists()) == (shutil.which(tool) is not None), tool


def test_colours_are_install_shs_own_palette() -> None:
    """`colours()` is `install.sh:62-72`, and the ESCAPES are read from it.

    Comparing `colours()` against `os.isatty(1)` alone would be circular -- that is its implementation. The non-circular half is the palette: the three literals are lifted out of `install.sh` itself, so a change there reds this rather than silently re-colouring the gate.
    """
    text = INSTALL_SH.read_text(encoding="utf-8")
    for literal in ("RED='\\033[0;31m'", "GREEN='\\033[0;32m'", "NC='\\033[0m'"):
        assert literal in text, "install.sh's palette moved: %s" % literal
    for blank in ("RED=''", "GREEN=''", "NC=''"):
        assert blank in text, "install.sh no longer blanks its palette off a tty"

    red, green, nc = install_script_check.colours()
    if os.isatty(1):
        assert (red, green, nc) == ("\033[0;31m", "\033[0;32m", "\033[0m")
    else:
        assert (red, green, nc) == ("", "", "")


def test_mode_matches_real_stat(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "cfg.json"
    target.write_text("{}", encoding="utf-8")
    for mode in (0o600, 0o640, 0o400, 0o644):
        target.chmod(mode)
        real = subprocess.run(
            ["stat", "-c", "%a", str(target)], capture_output=True, text=True, check=True
        ).stdout.strip()
        assert install_script_check._mode(target) == real


# --------------------------------------------------------------------------- The control: a planted defect must turn this differential red ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_comparison(tmp_path: pathlib.Path) -> None:
    """Delete the 0600 assertion from a COPY of the port.

    The config holds an account server and an update channel and is written by a `curl | bash` installer, so its mode is a real security property. A port that dropped the check agrees with the recording on every tree where install.sh still chmods correctly -- which is every tree except the fixture built here. The real port file is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = """    perms = _mode(config)
    if perms != "600":
        log_fail("rediacc.json mode must be 600 (got %s)" % perms)
"""
    assert source.count(anchor) == 1, "the plant's anchor must still be where it was"
    broken = tmp_path / "install_script_check_broken.py"
    broken.write_text(source.replace(anchor, "", 1), encoding="utf-8")

    fixture = build_fixture(tmp_path)
    mutate(fixture, CHMOD_ABSENT, WRONG_MODE)
    old = recorded("a-wrong-config-mode")
    assert old[0] == 1, "the recording must hold the twin catching the wrong mode"
    assert _run(broken, fixture).returncode != old[0], (
        "PLANT DID NOT FIRE: the comparison is vacuous"
    )
    assert_same(old, _run(PORT, fixture))
