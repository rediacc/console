"""Every spelling gh and git accept for a flag gets the verdict its long form gets (#8ed364fe, the class sweep after 28801da09).

Measured 2026-10-07 through `dispatch.py` in a scratch repository whose origin is rediacc/console, before the fix. Each guard below read a flag by regex over the quote-stripped command text, so only the spellings the regex named were seen:

  block_nondraft_pr_create  `-R=rediacc/renet -t x` rc=2 (read as console) against `--repo=rediacc/renet` rc=0; `-R=rediacc/renet --draft` rc=0 against the long form's rc=2; `-dt x` rc=2 against `-d -t x` rc=0; `-t --draft` (a PR titled "--draft") rc=0; `--repo github.com/rediacc/console` rc=0 (read as a foreign repo); `-XPOST` and `--method=POST` past the REST ban.
  block_admin_merge         `-R=someone/other` rc=2 (merge judged against rediacc/console); `--repo rediacc/renet 66` asked gh about PR "rediacc/renet"; `-XPUT` past the REST ban.
  block_premature_ready     `-R=rediacc/renet` rc=2 (flip judged as console); `--repo rediacc/console 42` asked about PR "rediacc/console".
  block_second_open_pr      `-R=rediacc/renet` listed console's open PRs, not renet's.
  block_merge_with_unpushed `-R rediacc/renet` rc=2 against `--repo rediacc/renet` rc=0; `gh pr view 1 --repo rediacc/renet && gh pr merge 42` rc=0 (a sibling's flag).
  block_raw_pr_body_edit    `-R=rediacc/renet --body prose` rc=2 against rc=0; `-XPATCH`, `--method=PATCH`, `-Fbody=@f`, `--field=body=@f`, `-fbody=x` past the PATCH arm.
  block_commit_meta         `git commit -F<file>`, `-qF <file>`, `git tag -F<file>`, `gh pr create -F<file>`/`-dF <file>`, `gh api -Fbody=@<file>` never read the file.

The cure is one reader, `shellscan.gh_args`, which parses a walked gh argv the way pflag does. Every case states the long-form verdict first (the control that proves the guard fires at all), then asks the same of each other spelling.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from rediacc_hooks import dispatch
from rediacc_hooks.wellknown import GH_REPO, RENET_REPO

FOOTER = "\U0001f916 " + "Generated " + "with [Claude Code](u)"

# gh, stubbed: every call is logged, `pr list` answers one open PR for renet and none elsewhere, everything else answers nothing (so a merge or a ready flip a guard judges is refused as unresolvable, and the log says which repo and PR it asked about).
GH_STUB = (
    """#!/bin/sh
echo "$*" >> "$GH_LOG"
case "$*" in
  "pr list --repo %s "*) echo '[{"number":7,"title":"t","headRefName":"0101-1","isDraft":false}]';;
  "pr list "*) echo '[]';;
esac
exit 0
"""
    % RENET_REPO
)


def _git(cwd, *args):
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A console-looking checkout on `0101-1`, one commit ahead of its origin, with `gh` stubbed on PATH."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "--initial-branch=0101-1")
    _git(root, "remote", "add", "origin", "https://github.com/%s.git" % GH_REPO)
    _git(root, "commit", "-q", "--allow-empty", "-m", "a")
    _git(root, "update-ref", "refs/remotes/origin/0101-1", "HEAD")
    _git(root, "commit", "-q", "--allow-empty", "-m", "b")
    (root / "foot.md").write_text("prose\n\n%s\n" % FOOTER, encoding="utf-8")
    (root / "prose.md").write_text("prose only\n", encoding="utf-8")
    # block_raw_pr_body_edit names the blockless (submodule) repos from this file.
    (root / ".gitmodules").write_text(
        '[submodule "private/renet"]\n\tpath = private/renet\n\turl = https://github.com/%s.git\n'
        % RENET_REPO,
        encoding="utf-8",
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "gh"
    stub.write_text(GH_STUB, encoding="utf-8")
    stub.chmod(0o755)
    log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", "%s%s%s" % (bindir, os.pathsep, os.environ["PATH"]))
    monkeypatch.setenv("GH_LOG", str(log))
    return root, log


def judge(world, stem, command):
    """(rc, the gh calls the guard made) for `command`, payload cwd and project dir at the fixture."""
    root, log = world
    log.write_text("", encoding="utf-8")
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root)}
    )
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    rc, _out, _err = dispatch.run_one(stem, payload, cwd=str(root), env=env)
    return rc, log.read_text(encoding="utf-8").splitlines()


# (stem, control command, its rc, [other spellings that must get the same rc]).
SAME_VERDICT = [
    # --- block_nondraft_pr_create: which repo, and is it a draft ---
    (
        "block_nondraft_pr_create",
        "gh pr create --repo %s -t x" % RENET_REPO,
        0,
        [
            "gh pr create -R %s -t x" % RENET_REPO,
            "gh pr create -R=%s -t x" % RENET_REPO,
            "gh pr create -R%s -t x" % RENET_REPO,
            "gh pr create --repo=%s -t x" % RENET_REPO,
            "gh pr create --repo '%s' -t x" % RENET_REPO,
            "gh pr create --repo github.com/%s -t x" % RENET_REPO,
        ],
    ),
    (
        "block_nondraft_pr_create",
        "gh pr create --repo %s -t x" % GH_REPO,
        2,
        [
            "gh pr create -R=%s -t x" % GH_REPO,
            "gh pr create --repo github.com/%s -t x" % GH_REPO,
            "gh pr create --repo https://github.com/%s -t x" % GH_REPO,
        ],
    ),
    (
        "block_nondraft_pr_create",
        "gh pr create --repo %s --draft -t x" % RENET_REPO,
        2,
        ["gh pr create -R=%s --draft -t x" % RENET_REPO, "gh pr create -dR %s -t x" % RENET_REPO],
    ),
    (
        "block_nondraft_pr_create",
        "gh pr create --draft --title x",
        0,
        ["gh pr create -d -t x", "gh pr create -dt x", "gh pr create --draft=true -t x"],
    ),
    (
        "block_nondraft_pr_create",
        "gh pr create --title x",
        2,
        ["gh pr create -t --draft", "gh pr create --draft=false -t x", "gh pr create -t -d"],
    ),
    (
        "block_nondraft_pr_create",
        "gh api repos/o/r/pulls -X POST -f title=x -f head=b",
        2,
        [
            "gh api repos/o/r/pulls -XPOST -f title=x -f head=b",
            "gh api repos/o/r/pulls --method=POST -f title=x",
            "gh api repos/o/r/pulls -X=POST -f title=x",
            "gh api repos/o/r/pulls -f title=x -f head=b",
        ],
    ),
    ("block_nondraft_pr_create", "gh pr view 5", 0, ["gh pr create --help"]),
    # --- block_admin_merge: which repo (a foreign one is not policed) ---
    (
        "block_admin_merge",
        "gh pr merge 5 --repo someone/other --rebase",
        0,
        [
            "gh pr merge 5 -R someone/other --rebase",
            "gh pr merge 5 -R=someone/other --rebase",
            "gh pr merge 5 -Rsomeone/other --rebase",
            "gh pr merge 5 -rR someone/other",
        ],
    ),
    (
        "block_admin_merge",
        "gh api repos/o/r/pulls/5/merge -X PUT",
        2,
        ["gh api repos/o/r/pulls/5/merge -XPUT", "gh api repos/o/r/pulls/5/merge --method=PUT"],
    ),
    # --- block_premature_ready: which repo (only console flips are gated) ---
    (
        "block_premature_ready",
        "gh pr ready 42 --repo %s" % RENET_REPO,
        0,
        ["gh pr ready 42 -R=%s" % RENET_REPO, "gh pr ready 42 -R%s" % RENET_REPO],
    ),
    # --- block_second_open_pr: which repo's open PRs are counted (the stub has one on renet) ---
    (
        "block_second_open_pr",
        "gh pr create --repo %s -t x" % RENET_REPO,
        2,
        [
            "gh pr create -R %s -t x" % RENET_REPO,
            "gh pr create -R=%s -t x" % RENET_REPO,
            "gh pr create -R%s -t x" % RENET_REPO,
        ],
    ),
    # --- block_merge_with_unpushed: a merge for another repository strands nothing here ---
    (
        "block_merge_with_unpushed",
        "gh pr merge 42 --repo %s" % RENET_REPO,
        0,
        [
            "gh pr merge 42 -R %s" % RENET_REPO,
            "gh pr merge 42 -R=%s" % RENET_REPO,
            "gh pr merge 42 -R%s" % RENET_REPO,
            "gh pr merge 42 --repo=%s" % RENET_REPO,
        ],
    ),
    (
        "block_merge_with_unpushed",
        "gh pr merge 42",
        2,
        ["gh pr view 1 --repo %s && gh pr merge 42" % RENET_REPO],
    ),
    # --- block_raw_pr_body_edit: a submodule edit carries no block; the sanctioned PATCH is judged in every spelling ---
    (
        "block_raw_pr_body_edit",
        "gh pr edit 113 --repo %s --body 'prose only'" % RENET_REPO,
        0,
        [
            "gh pr edit 113 -R=%s --body 'prose only'" % RENET_REPO,
            "gh pr edit 113 -R%s -b 'prose only'" % RENET_REPO,
        ],
    ),
    (
        "block_raw_pr_body_edit",
        "gh api repos/%s/pulls/5 -X PATCH -F body=@prose.md" % GH_REPO,
        2,
        [
            "gh api repos/%s/pulls/5 -XPATCH -F body=@prose.md" % GH_REPO,
            "gh api repos/%s/pulls/5 --method=PATCH -F body=@prose.md" % GH_REPO,
            "gh api repos/%s/pulls/5 -X PATCH -Fbody=@prose.md" % GH_REPO,
            "gh api repos/%s/pulls/5 -X PATCH --field=body=@prose.md" % GH_REPO,
            "gh api repos/%s/pulls/5 -X PATCH --input=prose.md" % GH_REPO,
        ],
    ),
    (
        "block_raw_pr_body_edit",
        "gh api repos/%s/pulls/5 -X PATCH -f body='prose'" % GH_REPO,
        2,
        [
            "gh api repos/%s/pulls/5 -X PATCH -fbody='prose'" % GH_REPO,
            "gh api repos/%s/pulls/5 -X PATCH --raw-field=body='prose'" % GH_REPO,
        ],
    ),
    # --- block_commit_meta: the attribution footer in a message FILE, in every spelling that names one ---
    (
        "block_commit_meta",
        "git commit --file foot.md -- a",
        2,
        [
            "git commit -F foot.md -- a",
            "git commit -Ffoot.md -- a",
            "git commit -qF foot.md -- a",
            "git commit --file=foot.md -- a",
        ],
    ),
    ("block_commit_meta", "git tag -a v1 --file=foot.md", 2, ["git tag -a v1 -Ffoot.md"]),
    (
        "block_commit_meta",
        "gh pr create --draft -t x --body-file foot.md",
        2,
        [
            "gh pr create --draft -t x -F foot.md",
            "gh pr create --draft -t x -Ffoot.md",
            "gh pr create -dF foot.md -t x",
            "gh pr create --draft -t x --body-file=foot.md",
        ],
    ),
    (
        "block_commit_meta",
        "gh api repos/o/r/pulls/5 -X PATCH -F body=@foot.md",
        2,
        [
            "gh api repos/o/r/pulls/5 -X PATCH -Fbody=@foot.md",
            "gh api repos/o/r/pulls/5 --method=PATCH --field=body=@foot.md",
        ],
    ),
    (
        "block_commit_meta",
        "gh pr create --draft -t x --body-file prose.md",
        0,
        ["gh pr create -dFprose.md -t x"],
    ),
]


def _cases():
    for stem, control, want, others in SAME_VERDICT:
        for other in others:
            yield pytest.param(stem, control, want, other, id="%s: %s" % (stem, other))


@pytest.mark.parametrize(("stem", "control", "want", "other"), list(_cases()))
def test_every_spelling_gets_the_long_form_verdict(world, stem, control, want, other):
    rc, _calls = judge(world, stem, control)
    assert rc == want, (
        "control %r answered rc=%d, not %d: the guard is not judging this shape at all"
        % (control, rc, want)
    )
    rc, calls = judge(world, stem, other)
    assert rc == want, "%r answered rc=%d where %r answers rc=%d (gh calls: %r)" % (
        other,
        rc,
        control,
        want,
        calls,
    )


# The PR a merge or ready flip is judged on is the first OPERAND, wherever the flags sit: `--repo <r> 66` asked gh about PR "<r>".
SAME_GH_CALLS = [
    (
        "block_admin_merge",
        "gh pr merge 66 --repo %s" % RENET_REPO,
        "gh pr merge --repo %s 66" % RENET_REPO,
    ),
    (
        "block_admin_merge",
        "gh pr merge 66 --repo %s" % RENET_REPO,
        "gh pr merge -R=%s 66" % RENET_REPO,
    ),
    (
        "block_premature_ready",
        "gh pr ready 42 --repo %s" % GH_REPO,
        "gh pr ready --repo %s 42" % GH_REPO,
    ),
    (
        "block_premature_ready",
        "gh pr ready 42 --repo %s" % GH_REPO,
        "gh pr ready -R%s 42" % GH_REPO,
    ),
]


@pytest.mark.parametrize(
    ("stem", "control", "other"), SAME_GH_CALLS, ids=[c[2] for c in SAME_GH_CALLS]
)
def test_the_judged_pr_is_the_operand_whatever_the_flag_order(world, stem, control, other):
    rc_c, want = judge(world, stem, control)
    assert want, "control %r made no gh call: the guard never reached the PR lookup" % control
    rc_o, got = judge(world, stem, other)
    assert (rc_o, got) == (rc_c, want)


# `--head` is read by `commit_policy._gh_creations` through `commit_policy._flag_value`, outside this sweep's file set: a bundle (`-dH x`) is never seen and `-H=<live>` names a branch `=<live>`. Strict, so the day it is fixed the XPASS says to drop the mark.
@pytest.mark.xfail(
    strict=True,
    reason="commit_policy._flag_value reads --head without pflag bundles; see the report for #8ed364fe",
)
@pytest.mark.parametrize(
    ("control", "want", "other"),
    [
        ("gh pr create --draft --head 0229-7", 2, "gh pr create -dH 0229-7"),
        ("gh pr create --draft --head=0101-1", 0, "gh pr create --draft -H=0101-1"),
    ],
)
def test_second_branch_reads_head_in_every_spelling(world, control, want, other):
    rc, _ = judge(world, "block_second_branch", control)
    assert rc == want
    rc, _ = judge(world, "block_second_branch", other)
    assert rc == want
