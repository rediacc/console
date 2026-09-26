"""`rediacc_ci.quality.go_tool_path` against the shell pipeline it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. The interesting half of this gate is three greps whose behaviour on the awkward inputs is decided by POSIX character classes and by the ORDER of the pipe stages, not by anything a reader could infer. In particular the numbering grep runs AFTER a comment filter, so its numbers do not count file lines -- a table of expected
strings would be a table of what the port does, asserted against itself. Running the real pipeline under bash and comparing is the only form of this test that can fail for the right reason.

The bash fragments below were lifted verbatim from the three greps of `.ci/scripts/quality/check-go-tool-path.sh`, with `$GO_TOOLS` substituted and nothing else changed. They outlive that file: W7 P5 batch B6 retired it once `.ci/shadow/w7p2-gotoolpath.observations.jsonl` asserted equivalence over five distinct trees, and these fragments are the pipeline itself rather than a
call into the script, so every case below still runs the real bash against the port. They are NOT the whole gate -- the ledger is what compared the whole gate over five trees, and this file covers the seams the ledger cannot isolate.
"""

import pathlib
import subprocess

import pytest

from rediacc_ci.quality import go_tool_path as gtp
from rediacc_ci.tests import differential as diff

TOOLS = gtp.GO_TOOLS

# Every shape the three greps have to survive. The comment on each line is the property it is there for; a case with no property is a case that will be deleted the first time someone tidies this file.
BODIES = [
    "go install x@latest\n",  # the ordinary one
    "cd d; go install x@latest\n",  # after a separator
    "cargo install x\n",  # must NOT match: a different installer
    "django install x\n",  # must NOT match: a word ending in `go`
    "go installer x\n",  # must NOT match: `install` is a prefix, not the word
    "  go install x\n",  # leading indent
    "#go install x\n",  # a comment still matches the INSTALL grep
    'GOBIN="$d" go install x\n',  # install AND the fix on one line
    'PATH="$(go env GOPATH)/bin:$PATH"\ngo install x\n',  # the PATH fix
    "GOPATH_BIN=/x\ngo install y\n",  # the third fix spelling
    "_go_bin=/x\ngo install y\n",  # the fourth
    "go install x\ngoimports -l .\n",  # the defect
    "go install x\nunformatted=$(goimports -l .)\n",  # the defect inside $( )
    'go install x\n"$c/goimports" -l .\n',  # path-qualified: cleared
    "go install x\n./goimports -l .\n",  # path-qualified: cleared
    "go install x\ngoimports\n",  # no trailing space: not a hit
    "go install x\n# goimports -l .\n",  # a comment: filtered out first
    "go install x\n  goimports -l .\n",  # indented invocation
    "go install x\nfoo && gotestsum ./...\n",  # after &&
    "go install x\nfoo | shfmt -l .\n",  # after a pipe
]


def _bash_install(body: str, tmp_path: pathlib.Path) -> bool:
    (tmp_path / "f").write_text(body, encoding="utf-8")
    script = "grep -qE '(^|[[:space:];&|])go[[:space:]]+install[[:space:]]' f"
    code, _out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    return code == 0


def _bash_fix(body: str, tmp_path: pathlib.Path) -> bool:
    (tmp_path / "f").write_text(body, encoding="utf-8")
    script = "grep -qE 'GOBIN=|go env GOPATH.*bin|GOPATH_BIN|_go_bin' f"
    code, _out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    return code == 0


def _bash_hits(body: str, tmp_path: pathlib.Path) -> list[str]:
    """The retired twin's `hits` pipeline, verbatim, including `printf '%s'`."""
    (tmp_path / "f").write_text(body, encoding="utf-8")
    script = (
        'body="$(cat f)"; printf \'%%s\' "$body" | '
        "grep -vE '^[[:space:]]*#' | "
        'grep -nE "(^|[[:space:];&|(]|\\$\\()[[:space:]]*(%s)[[:space:]]" | '
        'grep -vE "[/\\"\'\\$](%s)" || true'
    ) % (TOOLS, TOOLS)
    code, out, err = diff.bash_streams(script, cwd=str(tmp_path))
    assert code == 0, err
    return [line for line in out.split("\n") if line]


@pytest.mark.parametrize("body", BODIES)
def test_install_detection_matches_bash(body: str, tmp_path: pathlib.Path) -> None:
    assert gtp.installs_go_tool(body) == _bash_install(body, tmp_path)


@pytest.mark.parametrize("body", BODIES)
def test_fix_detection_matches_bash(body: str, tmp_path: pathlib.Path) -> None:
    assert gtp.has_path_fix(body) == _bash_fix(body, tmp_path)


@pytest.mark.parametrize("body", BODIES)
def test_bare_invocation_pipeline_matches_bash(body: str, tmp_path: pathlib.Path) -> None:
    """Numbers AND text. The numbers are the half that would silently drift."""
    assert gtp.bare_invocations(body) == _bash_hits(body, tmp_path)


def test_the_numbering_counts_the_filtered_stream_not_the_file(tmp_path: pathlib.Path) -> None:
    """A DEFECT IN THE TWIN, PINNED SO A "FIX" IS A VISIBLE DECISION.

    The comment filter runs BEFORE the numbering grep, so a shebang and a header comment are removed and every reported number is short by that many lines. Measured while recording the shadow ledger: a plant whose bad line sat on file line 5 was reported as `4:`.
    """
    body = "#!/usr/bin/env bash\ngo install x\na=$(goimports -l .)\nb=$(gotestsum ./...)\n"
    hits = gtp.bare_invocations(body)
    assert hits == _bash_hits(body, tmp_path)
    # File line 3 and 4; reported as 2 and 3, because the shebang was filtered.
    assert hits == ["2:a=$(goimports -l .)", "3:b=$(gotestsum ./...)"]


def test_scan_file_head_3_truncates_and_still_prints_the_fix(tmp_path: pathlib.Path) -> None:
    """`head -3` shows three hits and NEVER says how many were hidden."""
    body = "go install x\n" + "".join("a%d=$(goimports -l .)\n" % i for i in range(9))
    target = tmp_path / "many.sh"
    target.write_text(body, encoding="utf-8")
    lines = gtp.scan_file(target, "many.sh")
    assert len(lines) == 5  # header + 3 hits + FIX
    assert lines[0].startswith("many.sh installs a go tool")
    assert lines[-1].lstrip().startswith("FIX: GOBIN=")
    # The count is absent, which is the twin's behaviour and worth seeing.
    assert "9" not in lines[0]


def test_an_unreadable_file_is_not_a_finding(tmp_path: pathlib.Path) -> None:
    """`cat "$f" 2>/dev/null || return 0`. Both directions matter here.

    A path in the index but deleted from disk is an ordinary state in this repo, and turning it into a finding would red the gate for a reason that has nothing to do with go tools.
    """
    assert gtp.scan_file(tmp_path / "absent.sh", "absent.sh") == []


def test_the_floor_is_computed_from_git_not_from_disk(tmp_path: pathlib.Path) -> None:
    """UNTRACKED FILES MUST NOT PROP THE COUNT UP.

    The twin's own comment: "Verified against the tracked list, not the filesystem, so a stray untracked file cannot prop the number up." A port that walked the directory instead would pass the floor on a tree CI would refuse.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / ".ci").mkdir()
    for i in range(60):
        (tmp_path / ".ci" / ("f%02d.sh" % i)).write_text("#!/bin/bash\n", encoding="utf-8")
    assert gtp.tracked_shell_files(tmp_path) == []
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
    assert len(gtp.tracked_shell_files(tmp_path)) == 60


def test_the_pathspec_reaches_files_directly_under_dot_ci(tmp_path: pathlib.Path) -> None:
    """`.ci/*.sh` MUST match `.ci/bootstrap.sh`, and `.ci/**/*.sh` must not.

    Measured 2026-09-06 in the twin's header: the two spellings return the same 453 tracked files and only the second drops bootstrap.sh. This asserts the fact rather than the prose, because the prose is what a tidy-up ignores.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / ".ci").mkdir()
    (tmp_path / ".ci" / "bootstrap.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
    assert gtp.tracked_shell_files(tmp_path) == [".ci/bootstrap.sh"]
    wide = subprocess.run(
        ["git", "-C", str(tmp_path), "ls-files", ".ci/**/*.sh"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert wide.stdout.strip() == "", "the ** spelling has stopped dropping the flat file"


def test_selftest_is_green() -> None:
    """The gate's own controls, driven in-process. Exit 0 or the port is broken."""
    assert gtp.selftest() == 0
