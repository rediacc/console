"""The test tables of `block_vm_unverified_push`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import json
import pathlib

from rediacc_hooks import syspath
from rediacc_hooks.guards.block_vm_unverified_push import (
    ACCOUNT,
    ACCOUNT_SRC,
    ACCOUNT_TEST,
    CLI_FILE,
    REASON_ENV,
    RECEIPT_MOD,
    RENET,
    TRIGGER_MOD,
    _commit,
    _git,
    _put,
    world,
)


def plant_receipt(
    root,
    status="VERIFIED",
    tree=None,
    inputs=None,
    pointer=None,
    built=None,
    ran=("renet",),
    reason_class=None,
    account_checkout=None,
    account_modified=False,
    verified_base=None,
):
    """Write a schema 3 receipt into `root`'s cache through the receipt module's own `write`, keyed on `tree` (HEAD's by default) with the trigger digest the guard will compute for it unless `inputs` overrides it.

    `ran` names the phases a VERIFIED receipt ran (each also required); a FAILED or NOT_VERIFIED one ran none and required both. `reason_class` overrides the NOT_VERIFIED or FAILED class, `account_checkout` the account checkout (the pointer by default) and `account_modified` its modified flag. `verified_base`, a (commit, tree) pair, is recorded as `trigger.verifiedBase`, the base a `--changed` run diffed against.
    """
    trigger = syspath.import_from_ci(TRIGGER_MOD)
    receipt_mod = syspath.import_from_ci(RECEIPT_MOD)
    root = pathlib.Path(root)
    tree = tree or _git(root, "rev-parse", "HEAD^{tree}")
    head = _git(root, "rev-parse", "HEAD")
    if not head:
        raise RuntimeError("fixture has no HEAD commit to key the receipt on")
    if pointer is None:
        pointer = _git(root, "rev-parse", "%s:%s" % (tree, RENET))
    account_pointer = _git(root, "rev-parse", "%s:%s" % (tree, ACCOUNT))
    if not account_pointer:
        raise RuntimeError("fixture has no account pointer to key the receipt on")
    reason = None
    steps = [{"id": "V1.1", "desc": "deploy renet", "rc": 0, "verdict": "PASS", "ms": 1}]
    if status == "NOT_VERIFIED":
        reason = {
            "class": reason_class or "fleet-unavailable",
            "detail": "ops up --basic exited 1",
        }
        steps = []
    elif status == "FAILED":
        reason = {"class": reason_class or "step-failed", "detail": "V1.3 sftp put"}
        steps.append(
            {
                "id": "V1.3",
                "desc": "sftp put into the repo",
                "rc": 1,
                "verdict": "FAIL",
                "ms": 1,
                "evidence": "permission denied",
            }
        )
    verified = status == "VERIFIED"
    phases = {
        side: {"required": side in ran if verified else True, "ran": verified and side in ran}
        for side in receipt_mod.SIDES
    }
    surfaces = sorted(
        set().union(*(trigger.MAP.phases[side] for side, ph in phases.items() if ph["required"]))
    )
    receipt = {
        "tier": "vm",
        "schema": receipt_mod.SCHEMA,
        "status": status,
        "reason": reason,
        "tree": tree,
        "head": head,
        "dirty": False,
        "inputs": inputs if inputs is not None else trigger.inputs(root, tree),
        "surfaces": surfaces,
        "submodules": {
            RENET: {"pointer": pointer, "checkout": pointer, "modified": False},
            ACCOUNT: {
                "pointer": account_pointer,
                "checkout": account_pointer if account_checkout is None else account_checkout,
                "modified": account_modified,
            },
        },
        "renet": {
            "built": pointer if built is None else built,
            "modified": False,
            "sha256": "0" * 64,
            "deployed": True,
        },
        "trigger": {
            "base": "origin/main",
            "via": "origin/main",
            "hits": [],
            "sides": sorted(side for side, phase in phases.items() if phase["required"]),
        },
        "fleet": {"mode": "reused", "os": "ubuntu-24.04", "ips": [], "landlock": {}},
        "phases": phases,
        "gateway": {"mode": "reused", "port": 8787, "started": 1767225600},
        "forks": [],
        "steps": steps,
        "teardown": {"ok": True, "leftovers": []},
        "runId": "fixture-run",
        "startedAt": "2026-01-01T00:00:00Z",
        "finishedAt": "2026-01-01T00:01:00Z",
        "wallMs": 60000,
    }
    if verified_base is not None:
        receipt["trigger"]["verifiedBase"] = {"head": verified_base[0], "tree": verified_base[1]}
        receipt["runId"] = "fixture-run-chained"
    receipt_mod.write(root, receipt)
    return root


def plant_retired(root, schema):
    """A VERIFIED receipt in a retired schema shape (1 or 2) for HEAD's tree, written raw (the receipt module's `write` refuses it): the guard must read it as no receipt at all."""
    trigger = syspath.import_from_ci(TRIGGER_MOD)
    receipt_mod = syspath.import_from_ci(RECEIPT_MOD)
    root = pathlib.Path(root)
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    pointer = _git(root, "rev-parse", "%s:%s" % (tree, RENET))
    receipt = {
        "schema": schema,
        "status": "VERIFIED",
        "reason": None,
        "tree": tree,
        "head": _git(root, "rev-parse", "HEAD"),
        "inputs": trigger.inputs(root, tree),
        "renet": {
            "pointer": pointer,
            "checkout": pointer,
            "built": pointer,
            "modified": False,
            "deployed": True,
        },
        "trigger": {"base": "origin/main", "via": "origin/main", "hits": []},
        "fleet": {"mode": "reused", "os": "ubuntu-24.04", "ips": [], "landlock": {}},
        "forks": [],
        "steps": [{"id": "V1.1", "desc": "deploy renet", "rc": 0, "verdict": "PASS", "ms": 1}],
        "teardown": {"ok": True, "leftovers": []},
        "runId": "fixture-run-schema-%d" % schema,
        "startedAt": "2026-01-01T00:00:00Z",
        "finishedAt": "2026-01-01T00:01:00Z",
        "wallMs": 60000,
    }
    if schema == 2:
        receipt["trigger"]["sides"] = ["renet"]
        receipt["phases"] = {
            "renet": {"required": True, "ran": True},
            "account": {"required": False, "ran": False},
        }
        receipt["account"] = {
            "pointer": _git(root, "rev-parse", "%s:%s" % (tree, ACCOUNT)),
            "checkout": _git(root, "rev-parse", "%s:%s" % (tree, ACCOUNT)),
            "modified": False,
            "gateway": {},
        }
    folder = receipt_mod.receipt_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    data = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    for name in ("%s.json" % tree, receipt_mod.LATEST):
        (folder / name).write_text(data, encoding="utf-8")
    return root


def _with_receipt(path, status, **kw):
    root = world(path, cli=True)
    return plant_receipt(root, status, **kw)


def _advanced(path):
    """VERIFIED at the CLI commit, then one more docs-only commit: the digest carries over."""
    root = world(path, cli=True)
    plant_receipt(root)
    _put(root, "docs/later.md", "later\n")
    _commit(root, "docs after the run")
    return root


def _other_pointer(path):
    """A VERIFIED receipt taken at renet A, while the pushed tree points at renet B."""
    root = world(path, renet_files=("cmd/renet/sandbox_exec.go",))
    seed_tree = _git(root, "rev-parse", "origin/main^{tree}")
    if not seed_tree:
        raise RuntimeError("fixture has no origin/main tree to seed the receipt from")
    return plant_receipt(root, tree=seed_tree)


def _stale_not_verified(path):
    """The CLI touched; the only NOT_VERIFIED receipt is for the seed's tree and inputs."""
    root = world(path, cli=True)
    seed_tree = _git(root, "rev-parse", "origin/main^{tree}")
    if not seed_tree:
        raise RuntimeError("fixture has no origin/main tree to seed the receipt from")
    return plant_receipt(root, "NOT_VERIFIED", tree=seed_tree)


def _chained(path, base="VERIFIED", account_after=False):
    """The V2 chain: an account commit with a both-phase receipt of status `base` (none when `base` is None), then a CLI commit whose renet-only VERIFIED receipt names the account commit as its `verifiedBase`. `account_after` also moves the account gitlink in the CLI commit, so the account side changed after the base and the chained receipt did not run it."""
    root = world(path, account_files=(ACCOUNT_SRC,))
    base_head = _git(root, "rev-parse", "HEAD")
    base_tree = _git(root, "rev-parse", "HEAD^{tree}")
    if not base_head or not base_tree:
        raise RuntimeError("fixture has no HEAD commit or tree to chain the receipt from")
    if base is not None:
        plant_receipt(root, base, ran=("renet", "account"))
    if account_after:
        _put(root / ACCOUNT, ACCOUNT_SRC, "export const licenses = 3;\n")
        _commit(root / ACCOUNT, "account C")
    _put(root, CLI_FILE, "export const sftp = 3;\n")
    _commit(root, "the CLI after the VERIFIED run")
    return plant_receipt(root, ran=("renet",), verified_base=(base_head, base_tree))


TIP_BRANCH = "vm-tip"


def _reverted(path):
    """`TIP_BRANCH` holds the CLI commit; HEAD reverts the CLI file on top, so HEAD's range touches nothing while the branch's does."""
    root = world(path, cli=True)
    _git(root, "branch", TIP_BRANCH)
    _put(root, CLI_FILE, "export const sftp = 1;\n")
    _commit(root, "revert the CLI change")
    return root


FIXTURES = {
    "vmc-docs-only": world,
    "vmc-cli-none": lambda p: world(p, cli=True),
    "vmc-cli-verified": lambda p: _with_receipt(p, "VERIFIED"),
    "vmc-cli-not-verified": lambda p: _with_receipt(p, "NOT_VERIFIED"),
    "vmc-cli-failed": lambda p: _with_receipt(p, "FAILED"),
    "vmc-renet-sandbox": lambda p: world(p, renet_files=("cmd/renet/sandbox_exec.go",)),
    "vmc-renet-tests-only": lambda p: world(p, renet_files=("pkg/sandbox/sandbox_test.go",)),
    "vmc-other-pointer": _other_pointer,
    "vmc-advanced": _advanced,
    "vmc-missing-old": lambda p: world(p, missing_old=True),
    "vmc-stale-not-verified": _stale_not_verified,
    "vmc-reverted": _reverted,
    "vmc-account-src": lambda p: world(p, account_files=(ACCOUNT_SRC,)),
    "vmc-account-tests-only": lambda p: world(p, account_files=(ACCOUNT_TEST,)),
    "vmc-account-renet-receipt": lambda p: plant_receipt(world(p, account_files=(ACCOUNT_SRC,))),
    "vmc-account-verified": lambda p: plant_receipt(
        world(p, account_files=(ACCOUNT_SRC,)), ran=("account",)
    ),
    "vmc-account-missing-old": lambda p: world(p, account_missing_old=True),
    "vmc-renet-wide": lambda p: world(p, renet_files=("pkg/license/x.go",)),
    "vmc-renet-gomod": lambda p: world(p, renet_files=("go.mod",)),
    "vmc-chain-ok": _chained,
    "vmc-chain-account-after": lambda p: _chained(p, account_after=True),
    "vmc-chain-no-base": lambda p: _chained(p, base=None),
    "vmc-chain-base-not-verified": lambda p: _chained(p, base="NOT_VERIFIED"),
    "vmc-schema-1": lambda p: plant_retired(world(p, cli=True), 1),
    "vmc-schema-2": lambda p: plant_retired(world(p, cli=True), 2),
}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (name[len("vmc-") :], {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in FIXTURES
]


_ASK = " ASKED:2026-01-01T00:00Z"


_FILES = "only packages/cli/src/remote/sftp.ts comments changed, no runtime code"


_DEADLINE = "the 03:00Z CD promote carries the broken stable SFTP path otherwise"


_UNAVAIL = "the ops fleet is down, ops up --basic exits 1 on vm11 and vm12"


_PUSH = "git push origin 1008-1"


EDGE_CASES = [
    ("a bare push", "git push -u origin 1008-1"),
    ("an implicit push", "git push"),
    ("a -C push", "git -C . push origin 1008-1"),
    ("vm-unavailable", "%s='vm-unavailable: %s%s' %s" % (REASON_ENV, _UNAVAIL, _ASK, _PUSH)),
    ("not-runtime", "%s='not-runtime: %s%s' %s" % (REASON_ENV, _FILES, _ASK, _PUSH)),
    ("deadline", "%s='deadline: %s%s' %s" % (REASON_ENV, _DEADLINE, _ASK, _PUSH)),
    (
        "an exported reason",
        "export %s='not-runtime: %s%s'; %s" % (REASON_ENV, _FILES, _ASK, _PUSH),
    ),
    ("an unknown kind", "%s='because: %s%s' %s" % (REASON_ENV, _FILES, _ASK, _PUSH)),
    ("a short why", "%s='deadline: soon%s' %s" % (REASON_ENV, _ASK, _PUSH)),
    ("no ASKED", "%s='not-runtime: %s' %s" % (REASON_ENV, _FILES, _PUSH)),
    ("a malformed ASKED", "%s='not-runtime: %s ASKED:today' %s" % (REASON_ENV, _FILES, _PUSH)),
    ("a dry run", "git push --dry-run origin 1008-1"),
    ("a delete push", "git push origin --delete 1007-1"),
    ("the mirror push of main", "git push gitlab origin/main:refs/heads/main --follow-tags"),
    ("a submodule push", "git -C private/renet push origin 1008-1"),
    ("prose naming a push", "echo 'git push origin 1008-1'"),
    ("a scratch repo", "git -C /tmp push origin x"),
    ("two pushes of two commits", "git push origin %s:refs/heads/x && %s" % (TIP_BRANCH, _PUSH)),
    ("two refspecs in one push", "git push origin 1008-1:1008-1 %s:refs/heads/x" % TIP_BRANCH),
    ("every branch", "git push --all origin"),
    ("a glob refspec", "git push origin 'refs/heads/*:refs/heads/*'"),
    ("a mirror push", "git push --mirror origin"),
    (
        "a mirror push, escaped",
        "%s='deadline: %s%s' git push --mirror origin" % (REASON_ENV, _DEADLINE, _ASK),
    ),
]
