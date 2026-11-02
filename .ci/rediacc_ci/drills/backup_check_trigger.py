"""The paths whose change needs a backup receipt, the receipt itself, and the rule that judges it (box J4 of agent/plans/PLAN-backup-program.md).

THE CLONE. This is the backup twin of the `vm:check` pair: `rediacc_ci.proof.surfaces` (what is touched) and `rediacc_ci.proof.vm_tier` (what proves it) folded into one module, because the backup receipt has no phases or sides to keep apart. The git arithmetic is NOT cloned: `make_git`, `push_base`, the submodule range and the worktree blob hashing are imported from `rediacc_ci.proof.surfaces`, so the two guards cannot disagree about what a push range or a worktree blob is. Only the path tables, the digest and the receipt are this module's own.

WHAT IS TOUCHED. Three path tables, one per repository, each entry either a directory prefix (ending in `/`) or an `fnmatch` pattern (`*` crosses `/`):

  CONSOLE_PATHS   the CLI backup commands and services, and the drill that writes the receipt
  RENET_PATHS     relative to private/renet: the backup, datastore and prune commands, the chunk store, delta, datastore, coldbackup, backupstate and prune packages, go.mod and go.sum
  ACCOUNT_PATHS   relative to private/account: the backup routes, services and DTO, their migrations, and `src/entry/on-premise.ts` (the I7 boot)

Test files and documents are excluded through `rediacc_ci.proof.surfaces.excluded`, the same rule the vm-check trigger applies. A submodule whose gitlink moved is diffed inside the submodule; a range that cannot be computed is UNKNOWN, named in `Changed.unknown`, and counts as touched.

THE KEY. A receipt admits a push when its tree IS the pushed tree, or when BOTH of these hold: its `inputs` digest equals the pushed tree's (version `backup-v1`: the sorted `ls-tree` lines of the console trigger files), and its two gitlinks equal the pushed tree's (`stale-gitlink` otherwise). The gitlinks are kept OUT of the digest on purpose: inside it a stale gitlink would read as `other-inputs`, and the gitlink rule would be a line no test could tell apart from the digest. A later commit outside the trigger keeps the key, so it costs no new drill run.

THE RECEIPT is `.ci/cache/backup-check/receipt.json`, archived as `<tree>.json` on every write (`.ci/cache/` is gitignored). Schema 1. A VERIFIED receipt names every leg of `REQUIRED_LEGS` in `legs` and carries `onprem: true` (the I7 variant: entry/on-premise.ts booted against RustFS with the S3 conformance probe passing); `validate` refuses a VERIFIED receipt short of either, so a partial run is recorded NOT_VERIFIED (class `legs-partial`) and never admits. `renet` and `account` each record `pointer` (the tree's gitlink), `checkout` (the submodule HEAD the drill ran against) and `modified` (uncommitted trigger-path edits in that checkout); a checkout that is not the pointer is `checkout-mismatch`, a modified one `modified-checkout`.

WHO WRITES IT. `record_drill()`, called once by each drill runner at the end of a run: `rediacc_ci.drills.backup.main` records the legs half (the legs that passed), `rediacc_ci.drills.backup_onprem.main` the on-premise half. `record_half()` carries the other half from the receipt on file for the same tree, digest and checkouts, so the two runs together write one VERIFIED receipt; `record()` builds and writes it. Nothing else writes one, and there is deliberately no command line for writing.

WHO READS IT. The pre-bash guard `.claude/rediacc_hooks/guards/block_backup_unverified_push.py` (box J4) imports this module; the git-level half (box J10, `.claude/rediacc_hooks/git/githooks.py` pre_push) cannot import this package without a `sys.path` hop and so runs THE COMMAND LINE as a process:

    PYTHONPATH=.ci python3 -m rediacc_ci.drills.backup_check_trigger check --root <repo> --tip <sha> [--base <sha>]

exit 0 when the range touches no trigger path or a receipt admits it, 1 with the refusal on stderr otherwise, 2 when the range cannot be judged (a refusal too, never a pass). With no `--base`, the base is the merge-base of the tip and `refs/remotes/origin/main`.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
import time
from typing import TYPE_CHECKING, Any

from rediacc_ci.proof import surfaces as vmt

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

RENET_SUBMODULE = vmt.RENET_SUBMODULE
ACCOUNT_SUBMODULE = vmt.ACCOUNT_SUBMODULE
SUBMODULES = (RENET_SUBMODULE, ACCOUNT_SUBMODULE)

CONSOLE_PATHS = (
    "packages/cli/src/commands/backup*",
    "packages/cli/src/commands/repo-backup*",
    "packages/cli/src/services/backup/",
    ".ci/rediacc_ci/drills/backup.py",
    ".ci/rediacc_ci/drills/lib.py",
    ".ci/rediacc_ci/drills/wire.py",
)
RENET_PATHS = (
    "cmd/renet/backup*",
    "cmd/renet/datastore*",
    "cmd/renet/repository_prune*",
    "cmd/renet/prune_commands*",
    "pkg/chunkstore/",
    "pkg/delta/",
    "pkg/datastore/",
    "pkg/coldbackup/",
    "pkg/backupstate/",
    "pkg/prune/",
    "go.mod",
    "go.sum",
)
ACCOUNT_PATHS = (
    "src/routes/backups.ts",
    "src/services/backup*",
    "src/dto/backup.dto.ts",
    "src/entry/on-premise.ts",
    "drizzle/*backup*",
)
DIGEST_VERSION = "backup-v1"

SCHEMA = 1
VERIFIED = "VERIFIED"
FAILED = "FAILED"
NOT_VERIFIED = "NOT_VERIFIED"
STATUSES = (VERIFIED, FAILED, NOT_VERIFIED)
# The RustFS drill legs a-l without the opt-in machine leg i (box J4: "legs a-l"); leg l is box J8. Legs n and o are the S5 and S12 isolation legs; leg m is not required.
REQUIRED_LEGS = ("a", "b", "c", "d", "e", "f", "g", "h", "j", "k", "l", "n", "o", "p", "q", "r", "s")
CACHE_DIR = ".ci/cache/backup-check"
LATEST = "receipt.json"
ARCHIVE_SCAN_MAX = 50
_TREE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_REQUIRED = (
    "schema",
    "status",
    "reason",
    "tree",
    "head",
    "inputs",
    "renet",
    "account",
    "legs",
    "onprem",
    "runId",
    "startedAt",
    "finishedAt",
)

# The git arithmetic, shared with the vm-check trigger rather than copied.
make_git = vmt.make_git
push_base = vmt.push_base
excluded = vmt.excluded


# ----------------------------------------------------------------------------- the trigger


def watched(path: str, patterns: Iterable[str]) -> bool:
    """True when `path` matches an entry: a directory prefix (ending in `/`) or an fnmatch pattern."""
    for pattern in patterns:
        if pattern.endswith("/"):
            if path.startswith(pattern):
                return True
        elif fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def console_hit(path: str) -> bool:
    return watched(path, CONSOLE_PATHS) and not excluded(path)


def renet_hit(path: str) -> bool:
    """`path` is relative to private/renet."""
    return watched(path, RENET_PATHS) and not excluded(path)


def account_hit(path: str) -> bool:
    """`path` is relative to private/account."""
    return watched(path, ACCOUNT_PATHS) and not excluded(path)


_SUBMODULE_HIT: dict[str, Callable[[str], bool]] = {
    RENET_SUBMODULE: renet_hit,
    ACCOUNT_SUBMODULE: account_hit,
}


@dataclasses.dataclass(frozen=True)
class Changed:
    """`hits` are console-relative (submodule files carry the `private/renet/` or `private/account/` prefix); `unknown` names each range that could not be computed as `<submodule> <sha>: <why>`, and a caller counts it as touched."""

    hits: tuple[str, ...]
    unknown: tuple[str, ...] = ()

    @property
    def touched(self) -> bool:
        return bool(self.hits or self.unknown)


def changed_paths(
    root: pathlib.Path, base: str, mode: vmt.Mode = "push", tip: str = "HEAD"
) -> Changed:
    """The backup trigger paths changed between `base` and `tip` (`push`), or between `base` and the worktree plus untracked files (`worktree`). A submodule range that cannot be computed is reported in `unknown`, never dropped."""
    git = make_git(root)
    if mode == "push":
        names = git(["diff", "--no-renames", "--name-only", "-z", base, tip])
    else:
        names = git(["diff", "--no-renames", "--name-only", "-z", base])
    if names is None:
        return Changed(hits=(), unknown=(f"{base}: git diff failed",))
    changed = vmt._lines(names)
    if mode == "worktree":
        changed += vmt._lines(git(["ls-files", "-z", "--others", "--exclude-standard"]))
    hits = sorted({p for p in changed if console_hit(p)})
    unknown: list[str] = []
    for sub in SUBMODULES:
        old = vmt._gitlink(git, base, sub)
        new = vmt._gitlink(git, tip, sub) if mode == "push" else ""
        if mode == "push":
            moved = old != new
        else:
            moved = vmt._submodule_worktree_moved(root, sub, old, changed)
        if not moved:
            continue
        paths, why = vmt._submodule_range(root, sub, old, new, mode)
        if why is not None:
            unknown.append(f"{sub} {old or new or 'none'}: {why}")
        hits += sorted({f"{sub}/{p}" for p in paths if _SUBMODULE_HIT[sub](p)})
    return Changed(hits=tuple(hits), unknown=tuple(unknown))


# ----------------------------------------------------------------------------- the key


def _scopes() -> list[str]:
    """The literal directory or file each console pattern lives under, for `ls-tree` and `ls-files` (neither expands an fnmatch `*`)."""
    out: set[str] = set()
    for pattern in CONSOLE_PATHS:
        cut = min((pattern.find(ch) for ch in "*?[" if ch in pattern), default=-1)
        literal = pattern if cut < 0 else pattern[:cut].rsplit("/", 1)[0]
        out.add(literal.rstrip("/"))
    return sorted(out)


def _digest(lines: Iterable[str]) -> str:
    body = f"{DIGEST_VERSION}\n" + "".join(f"{ln}\n" for ln in sorted(lines))
    return hashlib.sha256(body.encode()).hexdigest()


def inputs_of_tree(root: pathlib.Path, tree: str) -> str | None:
    """sha256 (`backup-v1`) over the sorted `git ls-tree -r <tree>` lines of the console trigger files. None when git cannot read the tree."""
    out = make_git(root)(["ls-tree", "-r", "-z", tree, "--", *_scopes()])
    if out is None:
        return None
    lines = [ln for ln in vmt._lines(out) if console_hit(vmt._tree_entry_path(ln))]
    return _digest(lines)


def inputs_of_worktree(root: pathlib.Path) -> str | None:
    """The same digest over worktree blobs (`git hash-object` per file), so what ran and what is pushed compare on equal terms."""
    listed = make_git(root)(
        ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *_scopes()]
    )
    if listed is None:
        return None
    lines: list[str] = []
    for rel in sorted(set(vmt._lines(listed))):
        if not console_hit(rel):
            continue
        entry = vmt._worktree_entry(root, rel)
        if entry is not None:
            lines.append(entry)
    return _digest(lines)


def inputs(root: pathlib.Path, tree: str | None = None) -> str | None:
    """The receipt key's digest: of `tree`, or of the worktree when `tree` is None."""
    return inputs_of_worktree(root) if tree is None else inputs_of_tree(root, tree)


def pointers_of_tree(root: pathlib.Path, tree: str) -> dict[str, str]:
    """The `private/renet` and `private/account` gitlinks of `tree`, "" for one it does not have."""
    git = make_git(root)
    return {sub: vmt._gitlink(git, tree, sub) for sub in SUBMODULES}


# ----------------------------------------------------------------------------- the receipt


def receipt_dir(root: pathlib.Path) -> pathlib.Path:
    return root / CACHE_DIR


def _checkout_errors(name: str, entry: object) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{name} is not an object"]
    errors = [
        f"{name} is missing {k}" for k in ("pointer", "checkout", "modified") if k not in entry
    ]
    if (
        "modified" in entry
        and entry["modified"] is not None
        and not isinstance(entry["modified"], bool)
    ):
        errors.append(f"{name}.modified is not a boolean or null")
    return errors


def validate(receipt: object) -> list[str]:
    """Every way `receipt` departs from schema 1, empty when it is well formed."""
    if not isinstance(receipt, dict):
        return ["receipt is not an object"]
    errors = [f"missing field {k}" for k in _REQUIRED if k not in receipt]
    if receipt.get("schema") != SCHEMA:
        errors.append(f"schema is {receipt.get('schema')!r}, not {SCHEMA}")
    status = receipt.get("status")
    if status not in STATUSES:
        errors.append(f"status {status!r} is not one of {', '.join(STATUSES)}")
    reason = receipt.get("reason")
    if status == VERIFIED and reason is not None:
        errors.append("a VERIFIED receipt carries no reason")
    if status in (FAILED, NOT_VERIFIED) and not (isinstance(reason, dict) and reason.get("class")):
        errors.append(f"a {status} receipt needs reason.class")
    tree = receipt.get("tree")
    if not isinstance(tree, str) or not _TREE.match(tree):
        errors.append("tree is not a git object id")
    for name in ("renet", "account"):
        if name in receipt:
            errors.extend(_checkout_errors(name, receipt[name]))
    legs = receipt.get("legs")
    if not isinstance(legs, list) or not all(isinstance(leg, str) for leg in legs):
        errors.append("legs is not a list of leg ids")
    elif status == VERIFIED:
        missing = [leg for leg in REQUIRED_LEGS if leg not in legs]
        if missing:
            errors.append(
                f"a VERIFIED receipt needs every required leg; missing {','.join(missing)}"
            )
    if not isinstance(receipt.get("onprem"), bool):
        errors.append("onprem is not a boolean")
    elif status == VERIFIED and receipt.get("onprem") is not True:
        errors.append("a VERIFIED receipt needs the on-premise variant (I7) to have passed")
    return errors


def _atomic(path: pathlib.Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write(root: pathlib.Path, receipt: dict[str, Any]) -> pathlib.Path:
    """Write the latest receipt and its `<tree>.json` archive. Raises ValueError on a receipt that fails `validate`."""
    errors = validate(receipt)
    if errors:
        raise ValueError("invalid backup receipt: " + "; ".join(errors))
    data = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    out = receipt_dir(root)
    _atomic(out / f"{receipt['tree']}.json", data)
    _atomic(out / LATEST, data)
    return out / LATEST


def _checkout_state(root: pathlib.Path, sub: str, pointer: str) -> dict[str, Any]:
    subgit = vmt._submodule_git(root, sub)
    head = (subgit(["rev-parse", "HEAD"]) if subgit else None) or ""
    modified: bool | None = None
    if subgit is not None:
        out = subgit(["status", "--porcelain", "-z", "--no-renames", "--untracked-files=all"])
        if out is not None:
            modified = any(_SUBMODULE_HIT[sub](entry[3:]) for entry in vmt._lines(out))
    return {"pointer": pointer, "checkout": head, "modified": modified}


def record(
    root: pathlib.Path,
    *,
    status: str,
    legs: Sequence[str],
    onprem: bool,
    run_id: str,
    started_at: str,
    finished_at: str,
    reason: dict[str, str] | None = None,
) -> pathlib.Path:
    """The drill runner's one call: build the receipt for the checkout at `root` (HEAD's tree, the worktree digest, each submodule's pointer, checkout and modified state) and write it. `legs` are the legs that PASSED. A VERIFIED status short of `REQUIRED_LEGS` or the on-premise variant is written NOT_VERIFIED with class `legs-partial` rather than raising, so a partial run is still on record."""
    git = make_git(root)
    tree = git(["rev-parse", "HEAD^{tree}"]) or ""
    head = git(["rev-parse", "HEAD"]) or ""
    pointers = pointers_of_tree(root, tree) if tree else dict.fromkeys(SUBMODULES, "")
    ran = sorted(set(legs))
    missing = [leg for leg in REQUIRED_LEGS if leg not in ran]
    if status == VERIFIED and (missing or not onprem):
        gaps = [*missing, *([] if onprem else ["onprem"])]
        status = NOT_VERIFIED
        reason = {"class": "legs-partial", "detail": "not run or not passed: " + ",".join(gaps)}
    worktree_inputs = inputs(root)
    # The receipt is keyed by HEAD's tree, so a drill that ran uncommitted trigger-path edits tested code that tree does not hold: it may not vouch for it.
    if status == VERIFIED and tree and worktree_inputs != inputs(root, tree):
        status = NOT_VERIFIED
        reason = {
            "class": "dirty-inputs",
            "detail": "the drill ran uncommitted backup trigger files; commit them and run it again",
        }
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "reason": None if status == VERIFIED else reason,
        "tree": tree,
        "head": head,
        "inputs": worktree_inputs,
        "renet": _checkout_state(root, RENET_SUBMODULE, pointers[RENET_SUBMODULE]),
        "account": _checkout_state(root, ACCOUNT_SUBMODULE, pointers[ACCOUNT_SUBMODULE]),
        "legs": ran,
        "onprem": bool(onprem),
        "runId": run_id,
        "startedAt": started_at,
        "finishedAt": finished_at,
    }
    return write(root, receipt)


LEGS_HALF = "legs"
ONPREM_HALF = "onprem"
HALVES = (LEGS_HALF, ONPREM_HALF)


def _carried(root: pathlib.Path, tree: str) -> dict[str, Any] | None:
    """The receipt already on file for exactly the checkout at `root`: the same tree, the same worktree digest, and each submodule at the same checkout with the same modified state. Only such a receipt may lend its other half to this run."""
    prior = read_archive(root, tree) if tree else None
    if prior is None or prior.get("inputs") != inputs(root):
        return None
    for sub in SUBMODULES:
        name = sub.rsplit("/", 1)[-1]
        now = _checkout_state(root, sub, (prior.get(name) or {}).get("pointer", ""))
        if prior.get(name) != now:
            return None
    return prior


def record_half(
    root: pathlib.Path,
    *,
    half: str,
    status: str,
    legs: Sequence[str] = (),
    run_id: str,
    started_at: str,
    finished_at: str,
    reason: dict[str, str] | None = None,
) -> pathlib.Path:
    """Record one drill's half of the receipt and carry the other half from the receipt already on file for this exact checkout (`_carried`).

    The RustFS drill (`half="legs"`, `legs` = the legs that passed) and the on-premise variant (`half="onprem"`) are separate runs, and the receipt is VERIFIED only once both halves passed for one tree, one digest and one pair of checkouts. A half that did not pass contributes nothing (no legs, `onprem` false), so a failed re-run withdraws what that half had vouched for, and the other half survives it."""
    if half not in HALVES:
        raise ValueError(f"half {half!r} is not one of {', '.join(HALVES)}")
    tree = make_git(root)(["rev-parse", "HEAD^{tree}"]) or ""
    prior = _carried(root, tree) or {}
    passed = status == VERIFIED
    if half == LEGS_HALF:
        ran = list(legs) if passed else []
        onprem = prior.get("onprem") is True
    else:
        ran = list(prior.get("legs") or [])
        onprem = passed
    return record(
        root,
        status=status,
        legs=ran,
        onprem=onprem,
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        reason=reason,
    )


def _iso(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def drill_outcome(*, rc: int, count: int, failures: int) -> tuple[str, dict[str, str] | None]:
    """(status, reason) for a finished drill run. Only exit 0 with at least one assertion and no failure is VERIFIED: a run that asserted nothing is a skip (`lib.Drill.summary` exits 0 on it) and proves nothing; a run that failed an assertion is FAILED; a run that stopped before asserting anything (a preflight refusal, a store that would not start) is NOT_VERIFIED, the attempt the `drill-unavailable` escape names."""
    if rc == 0 and count > 0 and failures == 0:
        return VERIFIED, None
    if failures > 0:
        return FAILED, {
            "class": "assertions-failed",
            "detail": f"{failures} of {count} assertions failed (exit {rc})",
        }
    if rc == 0:
        return NOT_VERIFIED, {
            "class": "skipped",
            "detail": "0 assertions ran, so nothing was proven",
        }
    return NOT_VERIFIED, {
        "class": "drill-unavailable",
        "detail": f"the drill exited {rc} after {count} assertions and no failure",
    }


def record_drill(drill: Any, half: str, rc: int, legs: Sequence[str] = ()) -> pathlib.Path | None:
    """The drill runner's one call at the end of a run: map the `lib.Drill` outcome to a status and record `half`. A `--selftest` run records nothing (its exit is non-zero on purpose). A receipt that cannot be written is said loudly on stderr and never changes the drill's exit code."""
    if drill.selftest:
        return None
    status, reason = drill_outcome(rc=rc, count=drill.count, failures=drill.failures)
    started = drill.started_at or time.time()
    try:
        path = record_half(
            pathlib.Path(drill.root),
            half=half,
            status=status,
            legs=legs,
            run_id=f"{drill.name}-{int(started)}",
            started_at=_iso(started),
            finished_at=_iso(time.time()),
            reason=reason,
        )
    except (OSError, ValueError) as exc:
        print(f"backup-check: the receipt was NOT written ({exc})", file=sys.stderr)
        return None
    written = read_latest(pathlib.Path(drill.root)) or {}
    print(
        f"backup-check: receipt {written.get('status', '?')} for tree "
        f"{str(written.get('tree', ''))[:12]} (legs {','.join(written.get('legs') or []) or 'none'}, "
        f"onprem {written.get('onprem')}) at {path}",
        file=sys.stderr,
    )
    return path


def _load(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parsed if not validate(parsed) else None


def read_archive(root: pathlib.Path, tree: str) -> dict[str, Any] | None:
    if not _TREE.match(tree):
        return None
    return _load(receipt_dir(root) / f"{tree}.json")


def read_latest(root: pathlib.Path) -> dict[str, Any] | None:
    return _load(receipt_dir(root) / LATEST)


def _candidates(root: pathlib.Path, tree: str) -> list[dict[str, Any]]:
    """The pushed tree's archive, then the latest receipt, then the newest other archives."""
    found: list[dict[str, Any]] = []
    for receipt in (read_archive(root, tree), read_latest(root)):
        if receipt is not None and receipt not in found:
            found.append(receipt)
    folder = receipt_dir(root)
    if folder.is_dir():
        others = sorted(
            (p for p in folder.glob("*.json") if p.name not in (LATEST, f"{tree}.json")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in others[:ARCHIVE_SCAN_MAX]:
            receipt = _load(path)
            if receipt is not None and receipt not in found:
                found.append(receipt)
    return found


@dataclasses.dataclass(frozen=True)
class Verdict:
    """`ok` admits the push. `code` is one of ok, no-receipt, not-verified, failed, stale-gitlink, other-inputs, checkout-mismatch, modified-checkout."""

    ok: bool
    code: str
    message: str
    receipt: dict[str, Any] | None = None


def _judge(
    receipt: dict[str, Any], tree: str, digest: str | None, pointers: dict[str, str]
) -> Verdict:
    status = receipt["status"]
    reason = receipt.get("reason") or {}
    if status == NOT_VERIFIED:
        return Verdict(
            False,
            "not-verified",
            f"the last backup drill was NOT_VERIFIED ({reason.get('class')}): {reason.get('detail', '')}",
            receipt,
        )
    if status == FAILED:
        return Verdict(
            False,
            "failed",
            f"the last backup drill FAILED ({reason.get('class')}): {reason.get('detail', '')}",
            receipt,
        )
    for sub, want in pointers.items():
        name = sub.rsplit("/", 1)[-1]
        have = (receipt.get(name) or {}).get("pointer")
        if have != want:
            return Verdict(
                False,
                "stale-gitlink",
                f"the VERIFIED receipt ran {sub} {str(have)[:12]}, and tree {tree[:12]} points at {want[:12] or 'none'}",
                receipt,
            )
    if receipt["tree"] != tree and not (bool(digest) and receipt["inputs"] == digest):
        return Verdict(
            False,
            "other-inputs",
            f"the VERIFIED receipt (tree {receipt['tree'][:12]}) was taken with other backup inputs than tree {tree[:12]}",
            receipt,
        )
    for sub in pointers:
        name = sub.rsplit("/", 1)[-1]
        entry = receipt.get(name) or {}
        if entry.get("checkout") != entry.get("pointer"):
            return Verdict(
                False,
                "checkout-mismatch",
                f"the drill ran {sub} at {str(entry.get('checkout'))[:12]}, not the pointer {str(entry.get('pointer'))[:12]}",
                receipt,
            )
        if entry.get("modified") is not False:
            return Verdict(
                False,
                "modified-checkout",
                f"the drill's {sub} checkout had uncommitted backup-path changes",
                receipt,
            )
    return Verdict(
        True, "ok", f"VERIFIED receipt {receipt['runId']} covers tree {tree[:12]}", receipt
    )


def admit(root: pathlib.Path, tree: str, digest: str | None, pointers: dict[str, str]) -> Verdict:
    """The verdict for pushing `tree`, whose console trigger digest is `digest` and whose gitlinks `pointers` the receipt must match. Any candidate that admits wins; otherwise the first candidate's refusal is returned."""
    candidates = _candidates(root, tree)
    if not candidates:
        return Verdict(False, "no-receipt", f"no backup receipt exists for tree {tree[:12]}")
    verdicts = [_judge(c, tree, digest, pointers) for c in candidates]
    for verdict in verdicts:
        if verdict.ok:
            return verdict
    return verdicts[0]


# ----------------------------------------------------------------------------- the git-level check


RECEIPT_FIX = (
    "the two backup drills write it together: `./run.sh drill backup` (legs a-l and n-s) and "
    "`./run.sh drill backup-onprem` (the on-premise variant), on the committed tree"
)


def check(root: pathlib.Path, tip: str, base: str = "") -> tuple[int, str]:
    """(exit code, message) for pushing `tip`: 0 untouched or admitted, 1 refused, 2 cannot be judged."""
    git = make_git(root)
    if not base:
        base = git(["merge-base", tip, "refs/remotes/origin/main"]) or ""
        if not base:
            return (
                2,
                f"backup-check: no merge base of {tip[:12]} and refs/remotes/origin/main, so the range cannot be judged",
            )
    tree = git(["rev-parse", f"{tip}^{{tree}}"])
    if not tree:
        return 2, f"backup-check: git cannot name the tree of {tip[:12]}"
    changed = changed_paths(root, base, "push", tip)
    if not changed.touched:
        return 0, f"backup-check: {tip[:12]} touches no backup path"
    verdict = admit(root, tree, inputs_of_tree(root, tree), pointers_of_tree(root, tree))
    if verdict.ok:
        return 0, f"backup-check: {verdict.message}"
    shown = [*changed.hits[:10], *(f"(unknown) {u}" for u in changed.unknown)]
    if len(changed.hits) > 10:
        shown.append(f"... and {len(changed.hits) - 10} more")
    return 1, (
        f"backup-check: {tip[:12]} touches the backup paths and no VERIFIED backup receipt covers tree {tree[:12]}.\n"
        f"  receipt: [{verdict.code}] {verdict.message}\n"
        + "".join(f"  {h}\n" for h in shown)
        + f"  {RECEIPT_FIX}"
    )


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="backup_check_trigger")
    sub = parser.add_subparsers(dest="cmd", required=True)
    chk = sub.add_parser("check", help="judge one pushed commit against the backup receipt")
    chk.add_argument("--root", default=".")
    chk.add_argument("--tip", required=True)
    chk.add_argument("--base", default="")
    args = parser.parse_args(list(argv))
    code, message = check(pathlib.Path(args.root).resolve(), args.tip, args.base)
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
