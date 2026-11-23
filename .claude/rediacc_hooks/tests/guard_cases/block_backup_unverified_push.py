"""The test tables of `block_backup_unverified_push`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import pathlib

from rediacc_hooks import syspath
from rediacc_hooks.guards import block_vm_unverified_push as VM
from rediacc_hooks.guards.block_backup_unverified_push import (
    ACCOUNT,
    REASON_ENV,
    RENET,
    TRIGGER_MOD,
)

CONSOLE_FILE = "packages/cli/src/services/backup/backup-schedule.ts"


RENET_FILE = "pkg/chunkstore/store.go"


RENET_TEST = "pkg/chunkstore/store_test.go"


RENET_OTHER = "pkg/license/x.go"


ACCOUNT_FILE = "src/services/backup-gc.service.ts"


def world(path, console=False, renet_files=(), account_files=(), missing_old=False):
    """`block_vm_unverified_push.world` (a console-shaped checkout on `1008-1` with real `private/renet` and `private/account` gitlinks, one unpushed commit), plus a second commit editing `CONSOLE_FILE` when `console`. Returns the console path."""
    root = VM.world(
        path, renet_files=renet_files, account_files=account_files, missing_old=missing_old
    )
    if console:
        VM._put(root, CONSOLE_FILE, "export const schedule = 2;\n")
        VM._commit(root, "backup schedule")
    return root


def plant_receipt(
    root,
    status="VERIFIED",
    tree=None,
    legs=None,
    onprem=True,
    reason_class=None,
    checkout=None,
    modified=False,
):
    """Write a schema 1 backup receipt into `root`'s cache through the trigger module's own `write`, keyed on `tree` (HEAD's by default) with that tree's digest and gitlinks. `checkout` overrides the renet checkout, `modified` both modified flags."""
    trigger = syspath.import_from_ci(TRIGGER_MOD)
    root = pathlib.Path(root)
    tree = tree or VM._git(root, "rev-parse", "HEAD^{tree}")
    pointers = trigger.pointers_of_tree(root, tree)
    reason = None
    if status != "VERIFIED":
        reason = {"class": reason_class or "store-unavailable", "detail": "RustFS :9100 refused"}
    receipt = {
        "schema": trigger.SCHEMA,
        "status": status,
        "reason": reason,
        "tree": tree,
        "head": VM._git(root, "rev-parse", "HEAD"),
        "inputs": trigger.inputs_of_tree(root, tree),
        "renet": {
            "pointer": pointers[RENET],
            "checkout": pointers[RENET] if checkout is None else checkout,
            "modified": modified,
        },
        "account": {
            "pointer": pointers[ACCOUNT],
            "checkout": pointers[ACCOUNT],
            "modified": modified,
        },
        "legs": list(trigger.REQUIRED_LEGS if legs is None else legs),
        "onprem": onprem,
        "runId": "fixture-backup-run",
        "startedAt": "2026-01-01T00:00:00Z",
        "finishedAt": "2026-01-01T00:05:00Z",
    }
    trigger.write(root, receipt)
    return root


def _seed_tree(root):
    tree = VM._git(root, "rev-parse", "origin/main^{tree}")
    if not tree:
        raise RuntimeError("fixture has no origin/main tree to seed the receipt from")
    return tree


def _stale_gitlink(path):
    """A renet chunk-store range; the only VERIFIED receipt was taken at the seed, whose console inputs match but whose renet gitlink is the old one."""
    root = world(path, renet_files=(RENET_FILE,))
    return plant_receipt(root, tree=_seed_tree(root))


def _stale_not_verified(path):
    """The console backup file touched; the only NOT_VERIFIED receipt is for the seed's tree, whose console inputs differ."""
    root = world(path, console=True)
    return plant_receipt(root, "NOT_VERIFIED", tree=_seed_tree(root))


FIXTURES = {
    "bck-docs-only": world,
    "bck-console-none": lambda p: world(p, console=True),
    "bck-console-verified": lambda p: plant_receipt(world(p, console=True)),
    "bck-console-not-verified": lambda p: plant_receipt(world(p, console=True), "NOT_VERIFIED"),
    "bck-console-failed": lambda p: plant_receipt(world(p, console=True), "FAILED"),
    "bck-renet-chunkstore": lambda p: world(p, renet_files=(RENET_FILE,)),
    "bck-renet-tests-only": lambda p: world(p, renet_files=(RENET_TEST,)),
    "bck-renet-other": lambda p: world(p, renet_files=(RENET_OTHER,)),
    "bck-renet-verified": lambda p: plant_receipt(world(p, renet_files=(RENET_FILE,))),
    "bck-stale-gitlink": _stale_gitlink,
    "bck-account-src": lambda p: world(p, account_files=(ACCOUNT_FILE,)),
    "bck-missing-old": lambda p: world(p, missing_old=True),
    "bck-stale-not-verified": _stale_not_verified,
}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (name[len("bck-") :], {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in FIXTURES
]


_ASK = " ASKED:2026-01-01T00:00Z"


_FILES = "only comments in packages/cli/src/services/backup changed, no runtime code"


_DEADLINE = "the 03:00Z CD promote carries the broken stable backup restore otherwise"


_UNAVAIL = "RustFS on :9100 refuses connections and run.sh account dev cannot start it"


_PUSH = "git push origin 1008-1"


EDGE_CASES = [
    ("a bare push", "git push -u origin 1008-1"),
    ("an implicit push", "git push"),
    ("a -C push", "git -C . push origin 1008-1"),
    (
        "drill-unavailable",
        "%s='drill-unavailable: %s%s' %s" % (REASON_ENV, _UNAVAIL, _ASK, _PUSH),
    ),
    ("not-runtime", "%s='not-runtime: %s%s' %s" % (REASON_ENV, _FILES, _ASK, _PUSH)),
    ("deadline", "%s='deadline: %s%s' %s" % (REASON_ENV, _DEADLINE, _ASK, _PUSH)),
    ("an unknown kind", "%s='because: %s%s' %s" % (REASON_ENV, _FILES, _ASK, _PUSH)),
    ("a short why", "%s='deadline: soon%s' %s" % (REASON_ENV, _ASK, _PUSH)),
    ("no ASKED", "%s='not-runtime: %s' %s" % (REASON_ENV, _FILES, _PUSH)),
    ("a dry run", "git push --dry-run origin 1008-1"),
    ("a delete push", "git push origin --delete 1007-1"),
    ("the mirror push of main", "git push gitlab origin/main:refs/heads/main --follow-tags"),
    ("a submodule push", "git -C private/renet push origin 1008-1"),
    ("prose naming a push", "echo 'git push origin 1008-1'"),
    ("a mirror push", "git push --mirror origin"),
]
