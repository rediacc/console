"""block_origin_clone and the word "clone" inside a path (#82053b3b).

`cp scripts/ci-runner/quick-clone.ts /tmp/x.ts`, joined to a run of a script the hook cannot read, was refused as "the command names a clone verb": the old test was a substring match over the whole command, so `quick-clone.ts`, `ci-quick-clones` and `clone_d1.py` each counted as a verb. A verb is now a word (`VERB_WORD`), plus the text of a readable, untracked-or-changed file the command names. These rows read tracked files and a scratch script on disk, so they live here beside the guard's own `test-block_origin_clone.py` harness.
"""

import json
import os
import pathlib
import subprocess
import sys

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1]
DISPATCH = str(HOOKS / "dispatch.py")
ROOT = HOOKS.parents[1]
MARK = "ASKED:2026-11-04T10:15Z"


def _run(cmd):
    payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(ROOT)}
    proc = subprocess.run(
        [sys.executable, DISPATCH, "block_origin_clone"],
        input=json.dumps(payload),
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT)),
        timeout=60,
    )
    assert proc.returncode in (0, 2), proc.stderr
    return proc.returncode, proc.stderr


def _unread(tmp_path, name="y.py"):
    """A script whose text the walk cannot know: an in-place `sed` leaves it unknown, so running it is "unjudgeable"."""
    script = tmp_path / name
    return script, "sed -i s/a/b/ %s && python3 %s" % (script, script)


def test_the_named_files_exist():
    # The rows below are about these real paths; a rename must not leave them testing nothing.
    assert (ROOT / "scripts/ci-runner/quick-clone.ts").is_file()
    assert (ROOT / ".ci/rediacc_ci/deploy/clone_d1.py").is_file()


@pytest.mark.parametrize(
    "cmd",
    [
        "cp scripts/ci-runner/quick-clone.ts /tmp/x.ts",
        "cat .ci/rediacc_ci/deploy/clone_d1.py",
        "ls ~/.cache/rediacc/ci-quick-clones",
    ],
)
def test_a_path_holding_clone_alone_is_allowed(cmd):
    assert _run(cmd) == (0, "")


def test_a_copy_of_a_clone_named_file_then_an_unread_run_is_allowed(tmp_path):
    dest = tmp_path / "x.ts"
    cmd = "cp scripts/ci-runner/quick-clone.ts %s && sed -i s/a/b/ %s && npx tsx %s" % (
        dest,
        dest,
        dest,
    )
    assert _run(cmd) == (0, "")


def test_a_cat_of_a_clone_named_file_then_an_unread_run_is_allowed(tmp_path):
    dest = tmp_path / "q.py"
    cmd = "cat .ci/rediacc_ci/deploy/clone_d1.py > %s; sed -i s/a/b/ %s; python3 %s" % (
        dest,
        dest,
        dest,
    )
    assert _run(cmd) == (0, "")


def test_a_clone_named_directory_beside_an_unread_run_is_allowed(tmp_path):
    _, cmd = _unread(tmp_path)
    assert _run(cmd + " ~/.cache/rediacc/ci-quick-clones") == (0, "")


@pytest.mark.parametrize(
    "extra",
    [
        # The bare verb as a word.
        " clone",
        # `gh repo fork --clone`.
        " --clone",
        # git's own executable.
        " /usr/lib/git-core/git-clone",
        # The verb pair in an argument.
        " 'git clone'",
    ],
)
def test_a_verb_word_beside_an_unread_run_is_refused(tmp_path, extra):
    _, cmd = _unread(tmp_path)
    rc, err = _run(cmd + extra)
    assert rc == 2
    assert MARK in err
    assert "cannot judge" in err


def test_a_verb_written_by_sed_into_the_unread_script_is_refused(tmp_path):
    script = tmp_path / "y.py"
    rc, err = _run("sed -i 's/X/git clone/' %s && python3 %s" % (script, script))
    assert rc == 2
    assert MARK in err


def test_a_copied_source_holding_a_verb_is_refused_under_any_name(tmp_path):
    source = tmp_path / "helper.sh"
    source.write_text("git clone https://example.invalid/a.git /y\n", encoding="utf-8")
    script = tmp_path / "y.py"
    cmd = "cp %s %s && sed -i s/a/b/ %s && python3 %s" % (source, script, script, script)
    rc, err = _run(cmd)
    assert rc == 2
    assert MARK in err


def test_a_copied_source_with_no_verb_is_allowed(tmp_path):
    source = tmp_path / "helper.sh"
    source.write_text("echo quick-clone.ts\n", encoding="utf-8")
    script = tmp_path / "y.py"
    cmd = "cp %s %s && sed -i s/a/b/ %s && python3 %s" % (source, script, script, script)
    assert _run(cmd) == (0, "")


@pytest.mark.parametrize("extra", [" --remote", " git-fetch", " /usr/lib/git-core/git-pull"])
def test_every_spellable_verb_counts_in_both_dashed_spellings(tmp_path, extra):
    # Review 97b8666f.1: `--` and `git-` admit every verb in SPELLABLE, not only clone.
    _, cmd = _unread(tmp_path)
    rc, err = _run(cmd + extra)
    assert rc == 2
    assert "cannot judge" in err


def _tracked_helper(tmp_path):
    """A committed file holding the verb pair, in a scratch repository of its own."""
    repo = tmp_path / "repo"
    repo.mkdir()
    helper = repo / "helper.sh"
    helper.write_text("git clone https://example.invalid/a.git /y\n", encoding="utf-8")
    git = [
        "git",
        "-C",
        str(repo),
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
    ]
    for args in (["init", "-q"], ["add", "helper.sh"], ["commit", "-q", "-m", "a"]):
        subprocess.run([*git, *args], check=True, capture_output=True)
    return helper


def test_a_modified_tracked_file_holding_a_verb_beside_an_unread_run_is_refused(tmp_path):
    # Review 97b8666f.2: a tracked file changed from HEAD is read like an untracked one.
    helper = _tracked_helper(tmp_path)
    helper.write_text(helper.read_text(encoding="utf-8") + "echo more\n", encoding="utf-8")
    _, cmd = _unread(tmp_path)
    rc, err = _run("%s %s" % (cmd, helper))
    assert rc == 2
    assert MARK in err
    assert "cannot judge" in err


def test_an_unchanged_tracked_file_holding_a_verb_beside_an_unread_run_is_allowed(tmp_path):
    # The control: the same file, tracked and unchanged from HEAD, is exempt.
    helper = _tracked_helper(tmp_path)
    _, cmd = _unread(tmp_path)
    assert _run("%s %s" % (cmd, helper)) == (0, "")
