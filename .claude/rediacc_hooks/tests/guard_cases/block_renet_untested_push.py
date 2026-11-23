"""The test tables of `block_renet_untested_push`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import json
import pathlib

from rediacc_hooks.guards import block_vm_unverified_push as VM
from rediacc_hooks.guards.block_renet_untested_push import REASON_ENV, RENET

CONSOLE_READ = "packages/shared/src/subscription/schema.generated.json"


FIXTURE_MAP = {
    "schema": 1,
    "module": "github.com/rediacc/renet",
    "whole": [{"glob": "go.mod", "why": "the module graph reaches every package"}],
    "always": [],
    "entries": [
        {"glob": "cmd/renet/**", "packages": ["cmd/renet"], "dependents": []},
        {
            "glob": "pkg/license/**",
            "packages": ["pkg/license"],
            "dependents": ["cmd/renet"],
        },
        {
            "glob": "pkg/sandbox/**",
            "packages": ["pkg/sandbox"],
            "dependents": ["cmd/renet"],
        },
    ],
    "console": [
        {"glob": CONSOLE_READ, "packages": ["pkg/license"], "why": "a renet test reads it"}
    ],
}


LICENSE_FILE = "pkg/license/store.go"


UNMAPPED_FILE = "pkg/brandnew/x.go"


RECEIPTS_REL = ".ci/cache/renet-receipts"


def world(path, renet_files=(), missing_old=False):
    """`block_vm_unverified_push.world` (a console checkout on `1008-1`, renet commit A at origin/main's gitlink and B on the branch when `renet_files` are named) plus this guard's map and a renet `origin/main` at A, so the renet push form has a base. Returns the console path."""
    root = VM.world(path, renet_files=renet_files, missing_old=missing_old)
    renet = root / RENET
    VM._put(root, ".ci/config/renet-test-map.json", json.dumps(FIXTURE_MAP, indent=2) + "\n")
    VM._git(root, "add", ".ci/config/renet-test-map.json")
    VM._git(root, "commit", "-q", "-m", "map")
    VM._git(renet, "remote", "add", "origin", "https://github.com/fixture/renet.git")
    first = VM._git(renet, "rev-list", "--max-parents=0", "HEAD")
    VM._git(renet, "update-ref", "refs/remotes/origin/main", first)
    return root


def plant_receipt(root, packages, every=False, commit="HEAD"):
    """A passing receipt for the renet tree of `commit` (in private/renet) under `<root>/RECEIPTS_REL`, the shape the gate writes."""
    renet = pathlib.Path(root) / RENET
    tree = VM._git(renet, "rev-parse", "%s^{tree}" % commit)
    if not tree:
        raise RuntimeError("plant_receipt: rev-parse %s^{tree} printed nothing" % commit)
    receipts = pathlib.Path(root) / RECEIPTS_REL
    receipts.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": 1,
        "renetTree": tree,
        "renetHead": VM._git(renet, "rev-parse", commit),
        "dirty": False,
        "all": every,
        "packages": sorted(packages),
        "consoleTrees": [],
        "base": "",
        "passed": 3,
        "finishedAt": "2026-01-01T00:00:00Z",
    }
    (receipts / ("%s.json" % tree)).write_text(json.dumps(doc) + "\n", encoding="utf-8")
    return root


def _new_missing(path):
    """The branch moves the renet gitlink to a commit this checkout does not hold, so no local run can have tested it."""
    root = world(path)
    VM._git(root, "update-index", "--cacheinfo", "160000,%s,%s" % (MISSING_NEW, RENET))
    VM._git(root, "commit", "-q", "-m", "gitlink to a commit not fetched")
    return root


def _console_read(path, receipt=False):
    """The renet pointer does not move, but the branch changes a console file a renet test reads, so the renet packages that read it need a receipt."""
    root = world(path)
    VM._put(root, CONSOLE_READ, "{}\n")
    VM._git(root, "add", CONSOLE_READ)
    VM._git(root, "commit", "-q", "-m", "console read")
    return plant_receipt(root, ["pkg/license"]) if receipt else root


MISSING_NEW = "fedcba9876543210fedcba9876543210fedcba98"


FIXTURES = {
    "rnt-docs": world,
    "rnt-new-missing": _new_missing,
    "rnt-renet-docs": lambda p: world(p, renet_files=("README.md",)),
    "rnt-license": lambda p: world(p, renet_files=(LICENSE_FILE,)),
    "rnt-license-receipt": lambda p: plant_receipt(
        world(p, renet_files=(LICENSE_FILE,)), ["cmd/renet", "pkg/license"]
    ),
    "rnt-license-partial": lambda p: plant_receipt(
        world(p, renet_files=(LICENSE_FILE,)), ["pkg/license"]
    ),
    "rnt-license-seed-receipt": lambda p: plant_receipt(
        world(p, renet_files=(LICENSE_FILE,)), ["cmd/renet", "pkg/license"], commit="HEAD~1"
    ),
    "rnt-unmapped-partial": lambda p: plant_receipt(
        world(p, renet_files=(UNMAPPED_FILE,)), ["cmd/renet", "pkg/license", "pkg/sandbox"]
    ),
    "rnt-unmapped-all": lambda p: plant_receipt(
        world(p, renet_files=(UNMAPPED_FILE,)), [], every=True
    ),
    "rnt-missing-old": lambda p: world(p, renet_files=(LICENSE_FILE,), missing_old=True),
    "rnt-console-read": _console_read,
    "rnt-console-read-receipt": lambda p: _console_read(p, receipt=True),
}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (
        name[len("rnt-") :],
        {
            "CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name,
            "RENET_TEST_RECEIPT_DIR": "{FIXTURE:%s}/%s" % (name, RECEIPTS_REL),
        },
        {},
    )
    for name in FIXTURES
]


_ASK = " ASKED:2026-01-01T00:00Z"


_ENVIRONMENT = "pkg/daemon netns tests need root here; CI test-renet-go runs them under sudo"


_DEADLINE = "the 03:00Z CD promote carries the broken stable licence check otherwise"


EDGE_CASES = [
    ("a console push", "git push origin 1008-1"),
    ("an implicit console push", "git push"),
    ("a renet push by -C", "git -C private/renet push origin main"),
    ("a renet push after cd", "cd private/renet && git push origin main"),
    (
        "environment",
        "%s='environment: %s%s' git push origin 1008-1" % (REASON_ENV, _ENVIRONMENT, _ASK),
    ),
    ("deadline", "%s='deadline: %s%s' git push origin 1008-1" % (REASON_ENV, _DEADLINE, _ASK)),
    (
        "an unknown kind",
        "%s='because: %s%s' git push origin 1008-1" % (REASON_ENV, _DEADLINE, _ASK),
    ),
    ("no ASKED", "%s='deadline: %s' git push origin 1008-1" % (REASON_ENV, _DEADLINE)),
    ("a dry run", "git push --dry-run origin 1008-1"),
    ("a renet dry run", "git -C private/renet push --dry-run origin main"),
    ("a delete push", "git push origin --delete 1007-1"),
    ("prose naming a push", "echo 'git -C private/renet push origin main'"),
    ("a mirror push", "git push --mirror origin"),
]
