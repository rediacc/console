"""block_commit_on_main refuses every commit-creating git verb from a sub-agent in the main checkout (#60454abe).

Before the fix only `git commit` was judged, so a landing sub-agent ran `git -C private/renet cherry-pick` in the main checkout unrefused on 2026-11-06. The fixture is a real main checkout on a feature branch holding a real submodule at `private/renet`, and a lease tree at `.claude/worktrees/lease-x` with its own linked submodule tree, so `commit_policy.lease_root` answers both the way it answers a real lease. Each verb is driven three ways: a sub-agent in the main checkout (refused, in the plain, `-C` and `cd` spellings and in the submodule), a sub-agent in the lease (admitted) and the lead in the main checkout (admitted).

THE CONTROL is the guard as it stood before the fix: `git show <pre-fix>:.claude/rediacc_hooks/guards/block_commit_on_main.py` loaded in place of the live one admits every non-`commit` row of `test_a_writer_landing_verb_in_the_main_checkout_is_refused`.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from rediacc_hooks import commit_policy, guards, hookio

STEM = "block_commit_on_main"
NEEDLE = "writers never commit"
GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)
for _key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
    GIT_ENV.pop(_key, None)

# (verb as the row names it, the arguments after `git`). Every one writes a commit onto a ref.
LANDING = [
    ("cherry-pick", "cherry-pick -x 0123abc"),
    ("revert", "revert --no-edit HEAD"),
    ("merge", "merge --no-ff other"),
    ("am", "am -3 fix.mbox"),
    ("rebase", "rebase main"),
    ("pull", "pull origin main"),
    ("commit-tree", "commit-tree HEAD^{tree} -m x"),
]
# `commit` was refused before the fix too, so its rows are the unchanged baseline beside the new verbs.
ALL_VERBS = [*LANDING, ("commit", "commit -m 'feat: x' -- a.txt")]


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, env=GIT_ENV)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """(main checkout, lease tree): the checkout on `0923-1` with a submodule at `private/renet`, the lease detached with its own linked submodule tree."""
    base = tmp_path_factory.mktemp("writer-verbs").resolve()
    origin = base / "renet-origin"
    origin.mkdir()
    _git(origin, "init", "-q", "--initial-branch=main")
    _git(origin, "commit", "-q", "--allow-empty", "-m", "seed")
    root = base / "console"
    root.mkdir()
    _git(root, "init", "-q", "--initial-branch=main")
    (root / ".gitignore").write_text(".claude/worktrees/\n", encoding="utf-8")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-q", "-m", "seed")
    _git(root, "checkout", "-q", "-b", "0923-1")
    _git(
        root,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(origin),
        "private/renet",
    )
    _git(root, "commit", "-q", "-m", "add renet")
    # Off `main`, so the lead's `commit` rows in the submodule meet only the writer arm, never the `main` one.
    _git(root / "private" / "renet", "checkout", "-q", "-b", "0923-1")
    lease = root / ".claude" / "worktrees" / "lease-x"
    _git(root, "worktree", "add", "-q", "--detach", str(lease))
    _git(
        root / "private" / "renet",
        "worktree",
        "add",
        "-q",
        "--detach",
        str(lease / "private" / "renet"),
    )
    return root, lease


def _verdict(command, root, agent):
    """(refused, stderr) from the live guard (or the one `guards.load` answers), run in process from `root`."""
    doc = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root)}
    if agent:
        doc.update(agent_id="a0123456789abcdef", agent_type=agent)
    env = dict(GIT_ENV, CLAUDE_PROJECT_DIR=str(root))
    module = guards.load(STEM)
    event = hookio.Event(json.dumps(doc), cwd=str(root), env=env)
    rc = module.run(event)
    _rc, _out, err = event.result(rc)
    return rc != hookio.ALLOW, err


def test_the_fixture_lease_is_a_lease(world):
    """CONTROL on the fixture: the lease and its submodule tree answer `lease_root`, the main checkout and its submodule do not."""
    root, lease = world
    assert commit_policy.lease_root(str(lease)) == str(lease)
    assert commit_policy.lease_root(str(lease / "private" / "renet")) == str(lease)
    assert commit_policy.lease_root(str(root)) == ""
    assert commit_policy.lease_root(str(root / "private" / "renet")) == ""


SPELLINGS = [
    ("plain", "git {args}"),
    ("-C submodule", "git -C private/renet {args}"),
    ("cd submodule", "cd private/renet && git {args}"),
    ("-c option", "git -c core.pager=cat {args}"),
    ("sh -c wrapper", 'sh -c "git {args}"'),
]


@pytest.mark.parametrize(("verb", "args"), ALL_VERBS, ids=[v for v, _ in ALL_VERBS])
@pytest.mark.parametrize(("shape", "template"), SPELLINGS, ids=[s for s, _ in SPELLINGS])
def test_a_writer_landing_verb_in_the_main_checkout_is_refused(world, verb, args, shape, template):
    root, _lease = world
    refused, err = _verdict(template.format(args=args), root, "general-purpose")
    assert refused, "a sub-agent's `git %s` (%s) in the main checkout was admitted" % (verb, shape)
    assert NEEDLE in err
    assert "`git %s`" % verb in err


@pytest.mark.parametrize(("verb", "args"), ALL_VERBS, ids=[v for v, _ in ALL_VERBS])
@pytest.mark.parametrize("where", ["lease", "lease submodule"])
def test_a_writer_landing_verb_in_a_lease_is_admitted(world, verb, args, where):
    root, lease = world
    target = lease if where == "lease" else lease / "private" / "renet"
    refused, err = _verdict("git -C %s %s" % (target, args), root, "general-purpose")
    assert not refused, "a sub-agent's `git %s` in the %s was refused: %s" % (verb, where, err)


@pytest.mark.parametrize(("verb", "args"), ALL_VERBS, ids=[v for v, _ in ALL_VERBS])
@pytest.mark.parametrize(("shape", "template"), SPELLINGS[:3], ids=[s for s, _ in SPELLINGS[:3]])
def test_the_lead_landing_in_the_main_checkout_is_admitted(world, verb, args, shape, template):
    """The lead lands with `git cherry-pick -x` in the main checkout: no `agent_id`, no refusal (the checkout is on `0923-1`, so the `main` arm does not apply)."""
    root, _lease = world
    refused, err = _verdict(template.format(args=args), root, None)
    assert not refused, "the lead's `git %s` (%s) was refused: %s" % (verb, shape, err)


@pytest.mark.parametrize(
    "command",
    [
        "git cherry-pick --abort",
        "git -C private/renet cherry-pick --quit",
        "git merge --abort",
        "git am --show-current-patch",
        "git rebase --abort",
        "git merge-base HEAD main",
        "git log -n 3",
        "git status --porcelain",
    ],
)
def test_a_writer_command_that_creates_no_commit_is_admitted(world, command):
    root, _lease = world
    refused, err = _verdict(command, root, "general-purpose")
    assert not refused, err


def test_a_writer_landing_outside_the_checkout_is_admitted(world, tmp_path):
    root, _lease = world
    outside = tmp_path / "outside"
    outside.mkdir()
    _git(outside, "init", "-q", "--initial-branch=main")
    refused, err = _verdict("git -C %s cherry-pick -x 0123abc" % outside, root, "general-purpose")
    assert not refused, err


def test_the_verb_table_names_every_landing_row():
    """The guard's `WRITER_VERBS` and this file's rows agree, so a verb added to one is tested by the other."""
    module = guards.load(STEM)
    assert set(module.WRITER_VERBS) == {v for v, _ in ALL_VERBS}
