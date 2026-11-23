"""The test tables of `block_pr_freeze_commit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import json
import os
import pathlib
import subprocess

from rediacc_hooks import commit_policy, hookio, syspath
from rediacc_hooks.tests.fixtures.guards.loader import load_table

# ---- the differential's world: a main checkout on 1120-2 and a linked landing tree on 1120-1, bound by a landing record, with a `gh` stub answering PR 605 open ----
# The guard reads the tree role of CLAUDE_PROJECT_DIR (commit_policy.tree_binding, through pr_freeze.check) and the landing branch's open PR (`gh pr list`), so under the harness's default CLAUDE_PROJECT_DIR (the live checkout) and the real gh its answer was whatever the live trees and GitHub said. CLAUDE_PROJECT_DIR is the one variable this guard reads itself (the repository it judges); PATH reaches the gh stub, and WORKLIST_STORE_DIR and TMPDIR are read by pr_freeze or wl_store / wl_core, never by this guard; the token builds the world.
_FREEZE_BRANCH = "1120-1"


_DEV_BRANCH = "1120-2"


_GH_STUB = "#!/bin/sh\necho '[{\"number\": 605}]'\n"


def _freeze_world(target):
    """`target`/main on `_DEV_BRANCH` with one commit holding a record-paths policy, `target`/landing a linked tree of it on `_FREEZE_BRANCH` bound by the landing record, `target`/bin/gh a stub answering PR 605 open, and an empty `target`/store and `target`/tmp."""
    root = pathlib.Path(os.path.realpath(target))
    main = root / "main"
    ident = ["-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid"]
    subprocess.run(["git", "init", "-q", "-b", _DEV_BRANCH, str(main)], check=True)
    policy = syspath.import_from_ci("rediacc_ci.policy_paths").policy_path(
        "record-paths.json", main
    )
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        json.dumps({"version": 1, "records": [{"glob": "agent/reviews/**", "except": []}]}) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(main), "add", "."], check=True)
    subprocess.run(["git", "-C", str(main), *ident, "commit", "-q", "-m", "base"], check=True)
    landing = root / "landing"
    worktree_add = ["git", "-C", str(main), "worktree", "add", "-q", "-b", _FREEZE_BRANCH]
    subprocess.run([*worktree_add, str(landing)], check=True)
    commit_policy.write_landing_record(str(main), str(landing), _FREEZE_BRANCH)
    (root / "bin").mkdir(parents=True, exist_ok=True)
    hookio.write_world_file(root / "bin" / "gh", _GH_STUB)
    (root / "bin" / "gh").chmod(0o755)
    (root / "store").mkdir(parents=True, exist_ok=True)
    (root / "tmp").mkdir(parents=True, exist_ok=True)
    return root


FIXTURES = {"pr-freeze-world": _freeze_world}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (
        "frozen",
        {
            "CLAUDE_PROJECT_DIR": "{FIXTURE:pr-freeze-world}/landing",
            "PATH": "{FIXTURE:pr-freeze-world}/bin:/usr/bin:/bin:/usr/local/bin",
            "WORKLIST_STORE_DIR": "{FIXTURE:pr-freeze-world}/store",
            "TMPDIR": "{FIXTURE:pr-freeze-world}/tmp",
        },
        {},
    )
]


def _bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


EDGE_CASES = load_table("block_pr_freeze_commit", "EDGE_CASES")
