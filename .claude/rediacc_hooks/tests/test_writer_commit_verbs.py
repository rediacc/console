"""block_commit_on_main refuses every commit-creating git verb from a sub-agent in the main checkout (#60454abe).

Before the fix only `git commit` was judged, so a landing sub-agent ran `git -C private/renet cherry-pick` in the main checkout unrefused on 2026-11-06. The fixture is a real main checkout on a feature branch holding a real submodule at `private/renet`, and a lease tree at `.claude/worktrees/lease-x` with its own linked submodule tree, so `commit_policy.lease_root` answers both the way it answers a real lease. Each verb is driven three ways: a sub-agent in the main checkout (refused, in the plain, `-C` and `cd` spellings and in the submodule), a sub-agent in the lease (admitted) and the lead in the main checkout (admitted).

THE CONTROL is the guard as it stood before the fix: `git show <pre-fix>:.claude/rediacc_hooks/guards/block_commit_on_main.py` loaded in place of the live one admits every non-`commit` row of `test_a_writer_landing_verb_in_the_main_checkout_is_refused`.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import types

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

# THE ALIASES (#6bb5e37a): git runs the verb an alias names, so the typed one decides nothing. Configured in the fixture's repositories (`world`).
CONFIGURED = [
    ("cp", "cherry-pick"),
    ("pick", "cp"),
    ("loudpick", "-c commit.verbose=true pick"),
    ("shpick", "!git cherry-pick"),
    ("lg", "log --oneline"),
    ("cpa", "cherry-pick --abort"),
]
# (row id, the arguments after `git`, the verb the refusal names, or None for a refusal that cannot read the alias).
ALIASED = [
    ("inline -c alias", "-c alias.zz=cherry-pick zz -x 0123abc", "cherry-pick"),
    ("inline chained alias", "-c alias.za=zb -c alias.zb=revert za --no-edit HEAD", "revert"),
    ("inline shell alias", "-c 'alias.zs=!git commit -m x' zs", None),
    ("configured alias", "cp -x 0123abc", "cherry-pick"),
    ("configured alias, other case", "CP -x 0123abc", "cherry-pick"),
    ("chained configured alias", "pick -x 0123abc", "cherry-pick"),
    ("chained alias carrying -c", "loudpick -x 0123abc", "cherry-pick"),
    ("configured shell alias", "shpick 0123abc", None),
    ("inline alias to an inline-only name", "-c alias.zc=ci -c alias.ci=commit zc -m x", "commit"),
    ("neither a command nor an alias", "nosuchverb -x 0123abc", None),
]


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
    # The configured aliases, in the console's config (which the lease shares) and the submodule's (which its lease tree shares).
    for repo in (root, root / "private" / "renet"):
        for name, value in CONFIGURED:
            _git(repo, "config", "alias.%s" % name, value)
    return root, lease


def _verdict(command, root, agent, module=None):
    """(refused, stderr) from the live guard (or the one `guards.load` answers, or `module`), run in process from `root`."""
    doc = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root)}
    if agent:
        doc.update(agent_id="a0123456789abcdef", agent_type=agent)
    env = dict(GIT_ENV, CLAUDE_PROJECT_DIR=str(root))
    module = module or guards.load(STEM)
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


ALIAS_SPELLINGS = [s for s in SPELLINGS if s[0] != "-c option"]
ALIASED_ARGS = [(row, args) for row, args, _ in ALIASED]
# Each spelled through the environment or an earlier step of the same command, so none fits the `git {args}` templates.
ALIAS_COMMANDS = [
    (
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ze GIT_CONFIG_VALUE_0=merge git ze other",
    ),
    ("--config-env", "ZV=am git --config-env=alias.zv=ZV zv fix.mbox"),
    ("alias defined earlier", "git config alias.zq cherry-pick && git zq -x 0123abc"),
    ("alias redefined earlier", "git config alias.lg cherry-pick; git lg -x 0123abc"),
]


@pytest.mark.parametrize(("row", "args", "verb"), ALIASED, ids=[r for r, _, _ in ALIASED])
@pytest.mark.parametrize(
    ("shape", "template"), ALIAS_SPELLINGS, ids=[s for s, _ in ALIAS_SPELLINGS]
)
def test_a_writer_alias_in_the_main_checkout_is_refused(world, row, args, verb, shape, template):
    """#6bb5e37a: the verb is the one git runs after every alias, so an alias of a writer verb is refused, and one this guard cannot read is refused too."""
    root, _lease = world
    refused, err = _verdict(template.format(args=args), root, "general-purpose")
    assert refused, "a sub-agent's aliased `git %s` (%s, %s) was admitted" % (args, row, shape)
    assert NEEDLE in err
    if verb:
        assert "`git %s`" % verb in err, err
        assert "resolves through" in err, err
    else:
        assert "cannot resolve" in err, err


@pytest.mark.parametrize(("row", "args"), ALIASED_ARGS, ids=[r for r, _ in ALIASED_ARGS])
@pytest.mark.parametrize("where", ["lease", "lease submodule"])
def test_a_writer_alias_in_a_lease_is_admitted(world, row, args, where):
    root, lease = world
    target = lease if where == "lease" else lease / "private" / "renet"
    refused, err = _verdict("git -C %s %s" % (target, args), root, "general-purpose")
    assert not refused, "a sub-agent's `git %s` (%s) in the %s was refused: %s" % (
        args,
        row,
        where,
        err,
    )


@pytest.mark.parametrize(("row", "args"), ALIASED_ARGS, ids=[r for r, _ in ALIASED_ARGS])
@pytest.mark.parametrize(("shape", "template"), SPELLINGS[:3], ids=[s for s, _ in SPELLINGS[:3]])
def test_the_lead_alias_in_the_main_checkout_is_admitted(world, row, args, shape, template):
    root, _lease = world
    refused, err = _verdict(template.format(args=args), root, None)
    assert not refused, "the lead's `git %s` (%s, %s) was refused: %s" % (args, row, shape, err)


@pytest.mark.parametrize(("row", "command"), ALIAS_COMMANDS, ids=[r for r, _ in ALIAS_COMMANDS])
def test_a_writer_alias_from_the_environment_or_an_earlier_step_is_refused(world, row, command):
    root, lease = world
    refused, err = _verdict(command, root, "general-purpose")
    assert refused, "a sub-agent's `%s` (%s) in the main checkout was admitted" % (command, row)
    assert NEEDLE in err
    leased, err = _verdict("cd %s && %s" % (lease, command), root, "general-purpose")
    assert not leased, "the same `%s` (%s) in the lease was refused: %s" % (command, row, err)


@pytest.mark.parametrize(
    "command",
    [
        "git lg -n 3",
        "git cpa",
        "git -c alias.zl=log zl -n 1",
        "git gc --auto",
        "git -c alias.status=commit status",
    ],
)
def test_a_writer_alias_that_creates_no_commit_is_admitted(world, command):
    """CONTROL: an alias of a read, a sequencer's `--abort` behind an alias, a builtin outside `PLAIN_VERBS`, and an alias hiding a builtin (which git ignores) are all admitted."""
    root, _lease = world
    refused, err = _verdict(command, root, "general-purpose")
    assert not refused, err


def _typed_verb_guard():
    """The guard with alias resolution planted out: the verb as typed decides, the guard as it stood before #6bb5e37a."""
    path = pathlib.Path(guards.load(STEM).__file__)
    src = path.read_text(encoding="utf-8")
    plants = [
        (
            "    if not verb or verb in WRITER_VERBS or verb in PLAIN_VERBS or not os.path.isdir(directory):\n",
            "    if True:\n",
        ),
        ("        if defining and not write.refusal", "        if False and not write.refusal"),
    ]
    for old, new in plants:
        assert src.count(old) == 1, "the plant %r no longer applies" % old
        src = src.replace(old, new)
    namespace = {"__name__": "typed_verb_guard", "__file__": str(path)}
    exec(compile(src, "typed_verb_guard", "exec"), namespace)
    return types.SimpleNamespace(run=namespace["run"])


def test_every_alias_row_needs_the_resolution(world):
    """CONTROL: with resolution planted out every refused alias row is admitted while the typed `cherry-pick` row is still refused, so each row tests the resolution and nothing else."""
    root, _lease = world
    typed = _typed_verb_guard()
    rows = ["git %s" % args for _, args, _ in ALIASED] + [c for _, c in ALIAS_COMMANDS]
    still = [c for c in rows if _verdict(c, root, "general-purpose", module=typed)[0]]
    assert not still, "rows refused without alias resolution: %r" % still
    assert _verdict("git cherry-pick -x 0123abc", root, "general-purpose", module=typed)[0]
