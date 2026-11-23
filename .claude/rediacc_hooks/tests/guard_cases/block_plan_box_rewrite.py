"""The test tables of `block_plan_box_rewrite`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os
import subprocess

from rediacc_hooks.guards.block_plan_box_rewrite import QUEUE_REL

EDGE_CASES = [
    # The incident's first shape: the evidence appended to the box text.
    ("a tick that rewrites the box text", "git commit -F m -- agent/plans/PLAN-rewrite.md"),
    ("the correct tick, evidence indented below", "git commit -F m -- agent/plans/PLAN-ticked.md"),
    (
        "a move into _done with bracket flips only",
        "git commit -F m -- agent/plans/PLAN-moved.md agent/plans/_done/PLAN-moved.md",
    ),
    (
        "a move into _done whose copy rewrites a box",
        "git commit -F m -- agent/plans/PLAN-movedbad.md agent/plans/_done/PLAN-movedbad.md",
    ),
    ("a plan deleted with an open box", "git commit -F m -- agent/plans/PLAN-deleted.md"),
    # The incident's second shape: the sliced QUEUE.md.
    ("a QUEUE.md with its sections duplicated", "git commit -F m -- agent/plans/QUEUE.md"),
    ("a commit touching no plan", "git commit -F m -- docs/x.md"),
    ("a directory pathspec reaches the rewritten plan", "git commit -F m -- agent/plans/"),
    ("prose naming a plan commit", "echo 'git commit -- agent/plans/PLAN-rewrite.md'"),
    ("git log is not a commit", "git log -- agent/plans/PLAN-rewrite.md"),
]


def _fixture(path):
    """A checkout whose working tree holds one instance of each shape, uncommitted. Each EDGE_CASE commits a different pathspec of it."""
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )

    def git(*args):
        subprocess.run(["git", *args], cwd=str(path), check=True, capture_output=True, env=env)

    def put(rel, text):
        p = path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    path.mkdir(parents=True)
    git("init", "--initial-branch=1008-1", "-q")
    for slug, body in FIXTURE_HEAD.items():
        put("agent/plans/PLAN-%s.md" % slug, body)
    put(QUEUE_REL, FIXTURE_QUEUE)
    put("docs/x.md", "seed\n")
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    for rel, text in FIXTURE_WORKTREE.items():
        if text is None:
            (path / rel).unlink()
        else:
            put(rel, text)
    put("m", "docs(plans): fixture\n")
    return path


def _plan(slug, boxes):
    return (
        "# PLAN: %s\n\nStatus: in-progress\nOwner: cafe0000\nDepends-On: no-dep -- a fixture\n\n"
        "## Tasks\n\n%s" % (slug, "".join("- [ ] %s\n" % b for b in boxes))
    )


def _stub(slug):
    return (
        "# PLAN: %s (moved)\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-%s.md\n\n"
        "This plan moved.\n" % (slug, slug)
    )


FIXTURE_HEAD = {
    "rewrite": _plan("rewrite", ["T16 Retarget writers:", "T17 Delete the rewrite env files"]),
    "ticked": _plan("ticked", ["T16 Retarget the ticked writers:", "T17 Delete ticked env files"]),
    "moved": _plan("moved", ["T1 Move the moved token file", "T2 Bind the moved devbox"]),
    "movedbad": _plan("movedbad", ["T1 Seed the movedbad store", "T2 Wire the movedbad fetcher"]),
    "deleted": _plan("deleted", ["T1 Keep the deleted plan's box"]),
}


FIXTURE_QUEUE = (
    "# Plan queue\n\nThe list below `## Generated` is rendered; the Promoted list is by hand.\n\n"
    "## Settings\n\n```stop-hook\nturbo: off\n```\n\n"
    "## In flight\n\n<!-- queue:inflight:begin -->\n- Mode: x\n<!-- queue:inflight:end -->\n\n"
    "## Promoted\n\n1. agent/plans/PLAN-rewrite.md\n\n"
    "## Generated\n\n<!-- queue:generated:begin -->\n1. agent/plans/PLAN-ticked.md\n"
    "<!-- queue:generated:end -->\n"
)


def _sliced_queue(text):
    """The incident's splice: a new `## Promoted` body written between that heading and the FIRST `## Generated`, which sits in prose above it, so the tail `text[end:]` starts before the head ends and `## Settings` / `## In flight` are written twice."""
    start = text.index("\n## Promoted") + 1
    end = text.index("## Generated")
    return text[:start] + "## Promoted\n\n1. agent/plans/PLAN-ticked.md\n\n" + text[end:]


FIXTURE_WORKTREE = {
    "agent/plans/PLAN-rewrite.md": FIXTURE_HEAD["rewrite"].replace(
        "- [ ] T16 Retarget writers:",
        "- [x] T16 Retarget writers: (done 2026-10-08: c2ca68dfe with private/account 65b2332)",
    ),
    "agent/plans/PLAN-ticked.md": FIXTURE_HEAD["ticked"].replace(
        "- [ ] T16 Retarget the ticked writers:\n",
        "- [x] T16 Retarget the ticked writers:\n"
        "    (ticked) 2026-10-08 by d778be9d: c2ca68dfe with private/account 65b2332\n",
    ),
    "agent/plans/PLAN-moved.md": _stub("moved"),
    "agent/plans/_done/PLAN-moved.md": FIXTURE_HEAD["moved"].replace("[ ]", "[x]"),
    "agent/plans/PLAN-movedbad.md": _stub("movedbad"),
    "agent/plans/_done/PLAN-movedbad.md": FIXTURE_HEAD["movedbad"]
    .replace("[ ]", "[x]")
    .replace("store", "store (done 2026-10-08: c2ca68dfe)"),
    "agent/plans/PLAN-deleted.md": None,
    QUEUE_REL: _sliced_queue(FIXTURE_QUEUE),
}


FIXTURES = {"plan-box-commits": _fixture}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("plan-box-commits", {"CLAUDE_PROJECT_DIR": "{FIXTURE:plan-box-commits}"}, {})
]
