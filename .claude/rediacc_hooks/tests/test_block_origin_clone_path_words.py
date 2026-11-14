"""block_origin_clone and the word "clone" inside a path (#82053b3b).

`cp scripts/ci-runner/quick-clone.ts /tmp/x.ts`, joined to a run of a script the hook cannot read, was refused as "the command names a clone verb": the old test was a substring match over the whole command, so `quick-clone.ts`, `ci-quick-clones` and `clone_d1.py` each counted as a verb. A verb is now a word (`VERB_WORD`), plus the text of a readable, untracked-or-changed file the command names. These rows read tracked files and a scratch script on disk, so they live here beside the guard's own `test-block_origin_clone.py` harness.
"""

import json
import os
import pathlib
import subprocess
import sys
import typing

import pytest

from rediacc_hooks import wellknown
from rediacc_hooks.guards import block_origin_clone

HOOKS = pathlib.Path(__file__).resolve().parents[1]
DISPATCH = str(HOOKS / "dispatch.py")
ROOT = HOOKS.parents[1]
MARK = "ASKED:2026-11-04T10:15Z"


def _run(cmd, cwd=ROOT):
    payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd)}
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


@pytest.mark.parametrize(
    "extra",
    [
        " %s%s" % (prefix, verb)
        for verb in block_origin_clone.SPELLABLE
        for prefix in ("--", "git-", "/usr/lib/git-core/git-")
    ],
)
def test_every_spellable_verb_counts_in_both_dashed_spellings(tmp_path, extra):
    # Review 97b8666f.1: `--` and `git-` admit every verb in SPELLABLE, not only clone (review 91768330.2: every verb, both spellings).
    _, cmd = _unread(tmp_path)
    rc, err = _run(cmd + extra)
    assert rc == 2
    assert "cannot judge" in err


@pytest.mark.parametrize("extra", [" digit-clone", " legit-pull", " foo--fetch", " x.git-remote"])
def test_a_dashed_verb_inside_a_longer_word_is_a_name(tmp_path, extra):
    # Review 91768330.1: a dashed prefix counts only where it starts a word.
    _, cmd = _unread(tmp_path)
    assert _run(cmd + extra) == (0, "")


# #11ad5926: a stdin heredoc holding a tuple of verb words, run from a directory below the root, was refused as `git clone fetch pull ...` with `fetch` judged a path in this checkout.
SUBDIR = ROOT / "packages" / "cli"
ORIGIN = "%s/%s.git" % (wellknown.GH_ORIGIN, wellknown.GH_REPO)
TUPLE_HEREDOC = (
    "python3 - <<'EOF'\n"
    'SPELLABLE = ("clone", "fetch", "pull", "remote", "submodule")\n'
    "print(SPELLABLE)\n"
    "EOF"
)


def _heredoc(body):
    return "python3 - <<'EOF'\n%s\nEOF" % body


def test_the_subdirectory_exists_and_holds_no_fetch():
    # The rows below stand in this directory; a bare `fetch` there must name nothing.
    assert SUBDIR.is_dir()
    assert not (SUBDIR / "fetch").exists()


@pytest.mark.parametrize("cwd", [ROOT, SUBDIR])
def test_a_tuple_of_verb_words_in_a_heredoc_is_allowed(cwd):
    assert _run(TUPLE_HEREDOC, cwd=cwd) == (0, "")


@pytest.mark.parametrize("cwd", [ROOT, SUBDIR])
def test_a_standalone_list_starting_with_clone_is_data(cwd):
    # `private` exists, so only the argv reading made this a clone.
    assert _run(_heredoc('X = ["clone", "private"]'), cwd=cwd) == (0, "")


@pytest.mark.parametrize("cwd", [ROOT, SUBDIR])
@pytest.mark.parametrize(
    "body",
    [
        'import subprocess\nsubprocess.run(["git", "clone", "%s", "/tmp/x"])' % ORIGIN,
        'X = ("git", "clone", "%s", "/tmp/x")' % ORIGIN,
        'sh("git", ["clone", "%s", "/tmp/x"])' % ORIGIN,
        'run(argv=["clone", "%s", "/tmp/x"])' % ORIGIN,
    ],
)
def test_a_heredoc_that_builds_a_clone_of_the_origin_is_refused(cwd, body):
    rc, err = _run(_heredoc(body), cwd=cwd)
    assert rc == 2
    assert MARK in err
    assert "origin or mirror" in err


def test_a_bare_word_is_not_a_local_path_when_nothing_is_there():
    assert _run("git clone fetch /tmp/oc-y", cwd=SUBDIR) == (0, "")


@pytest.mark.parametrize("source", [".", "..", "../../private/renet", "../../.git"])
def test_an_existing_path_of_this_checkout_is_still_ours_from_below(source):
    rc, err = _run("git clone %s /tmp/oc-y" % source, cwd=SUBDIR)
    assert rc == 2
    assert "is a path in this checkout" in err


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


# Review c804bc45.1: a verb-first list bound to a name and handed to a call later is still a git argv; only a table no call takes stays data.
NAMED_ARGV = 'ARGV = ["clone", "%s", "/tmp/x"]\n' % ORIGIN


@pytest.mark.parametrize("cwd", [ROOT, SUBDIR])
@pytest.mark.parametrize(
    "body",
    [
        NAMED_ARGV + 'sh("git", *ARGV)',
        NAMED_ARGV + "run_git(ARGV)",
        NAMED_ARGV + 'import subprocess\nsubprocess.run(["git", *ARGV])',
        NAMED_ARGV.replace("ARGV =", "ARGV: list =") + "run_git(argv=ARGV)",
        "def main():\n    " + NAMED_ARGV + '    sh("git", *ARGV)',
    ],
)
def test_a_named_clone_argv_handed_to_a_call_is_refused(cwd, body):
    rc, err = _run(_heredoc(body), cwd=cwd)
    assert rc == 2
    assert MARK in err
    assert "origin or mirror" in err


@pytest.mark.parametrize("cwd", [ROOT, SUBDIR])
@pytest.mark.parametrize(
    "body",
    [
        'SPELLABLE = ("clone", "fetch", "pull", "remote", "submodule")\nfor v in SPELLABLE:\n    print(v)',
        'SPELLABLE = ("clone", "fetch", "pull")\nprint("pull" in SPELLABLE)',
    ],
)
def test_a_named_verb_table_no_call_takes_is_data(cwd, body):
    assert _run(_heredoc(body), cwd=cwd) == (0, "")


# Review 21761c0f.1: a table only a pure builtin takes is data, even when its walk as a git argv would be refused (`.` is this checkout from both directories).
PATHY_TABLE = 'SPELLABLE = ("clone", ".", "fetch", "pull")\n'


@pytest.mark.parametrize("cwd", [ROOT, SUBDIR])
@pytest.mark.parametrize(
    "body",
    [
        PATHY_TABLE + "print(SPELLABLE)",
        PATHY_TABLE + "print(len(SPELLABLE))",
        PATHY_TABLE + "n = len(SPELLABLE)",
        PATHY_TABLE + 'print(sorted(SPELLABLE), *SPELLABLE, sep=",")',
        'print(["clone", ".", "/tmp/x"])',
        # Review 2e01f0d2.1: a `**` expansion on a builtin no keyword makes call code, and on `dict`, hands the table nothing.
        PATHY_TABLE + "opts = {}\nn = len(SPELLABLE, **opts)",
        PATHY_TABLE + "opts = {}\nprint(dict(**opts), len(SPELLABLE))",
        # Control for 2a494086.1: a one-argument `type` only reads the table's type.
        PATHY_TABLE + "print(type(SPELLABLE))",
    ],
)
def test_a_verb_table_only_a_pure_builtin_takes_is_data(cwd, body):
    assert _run(_heredoc(body), cwd=cwd) == (0, "")


@pytest.mark.parametrize("cwd", [ROOT, SUBDIR])
def test_a_verb_table_a_pure_builtin_takes_in_a_script_by_path_is_data(cwd, tmp_path):
    script = tmp_path / "t.py"
    script.write_text(PATHY_TABLE + "print(SPELLABLE)\n", encoding="utf-8")
    assert _run("python3 %s" % script, cwd=cwd) == (0, "")


# The pure-builtin exemption must not reopen c804bc45.1: a pure builtin passes its argument through to a call that runs, a rebound builtin is the program's own, and a `key=` or `map` calls what it is handed.
@pytest.mark.parametrize("cwd", [ROOT, SUBDIR])
@pytest.mark.parametrize(
    "body",
    [
        NAMED_ARGV + "run_git(list(ARGV))",
        NAMED_ARGV + "X = list(ARGV)\nrun_git(X)",
        NAMED_ARGV + "X = ARGV\nrun_git(X)",
        NAMED_ARGV + 'import subprocess\nsubprocess.run(["git", *tuple(ARGV)])',
        NAMED_ARGV + "run_git(ARGV[0:])",
        "def print(*a):\n    sh('git', *a)\n" + NAMED_ARGV + "print(*ARGV)",
        "from helpers import run_git as len\n" + NAMED_ARGV + "len(ARGV)",
        NAMED_ARGV + "sorted([ARGV], key=run_git)",
        NAMED_ARGV + 'sorted([ARGV], **{"key": run_git})',
        NAMED_ARGV + "sorted([ARGV], **dict(key=run_git))",
        NAMED_ARGV + "list(map(run_git, [ARGV]))",
        # Review 4c1ac1fc.2: a metaclass `__instancecheck__` and a `file=` writer are program code the table reaches.
        NAMED_ARGV
        + "class C(type):\n    def __instancecheck__(cls, o):\n        run_git(o)\nisinstance(ARGV, C)",
        NAMED_ARGV + "print(ARGV, file=writer)",
        NAMED_ARGV + 'print(ARGV, **{"file": writer})',
        # Review 2a494086.1: a three-argument `type` creates a class, and the bases' `__init_subclass__` takes every keyword.
        NAMED_ARGV + 'type("C", (Base,), {}, **{"k": ARGV})',
        NAMED_ARGV + 'type("C", (Base,), {"argv": ARGV})',
    ],
)
def test_a_named_clone_argv_reaching_a_call_through_a_builtin_is_refused(cwd, body):
    rc, err = _run(_heredoc(body), cwd=cwd)
    assert rc == 2
    assert MARK in err
    assert "origin or mirror" in err


class _Root:
    """The two attributes `is_source_of_ours` reads, over a scratch root with no git directory."""

    def __init__(self, root):
        self.root = str(root)

    def common(self):
        return ""


def test_a_bare_absent_private_is_no_source_of_ours(tmp_path):
    # Review c804bc45.2: `private` alone is a plain superproject directory, never a repository; an absent `private/<name>` and `.git/...` still count.
    world = typing.cast("block_origin_clone.World", _Root(tmp_path))
    judge = block_origin_clone.World.is_source_of_ours
    assert not (tmp_path / "private").exists()
    assert judge(world, str(tmp_path / "private")) is False
    assert judge(world, str(tmp_path / "private" / "renet")) is True
    assert judge(world, str(tmp_path / ".git" / "modules" / "x")) is True
    assert judge(world, str(tmp_path / "fetch")) is False
