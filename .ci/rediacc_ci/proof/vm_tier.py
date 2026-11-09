"""The `npm run vm:check` receipt (the VM tier): how it is written, archived, read and judged.

The latest receipt is `.ci/cache/vm-check/receipt.json`. Every write also archives it as `<tree>.json`, so a later run on another tree does not hide the receipt of an earlier push. `.ci/cache/` is gitignored.

Schema 3 is the shared envelope of `rediacc_ci.proof.receipt` (`tier` is `vm`, then `tree`, `head`, `dirty`, `inputs`, `surfaces`, `submodules` and `renet`) plus the VM body: `reason`, `trigger`, `phases`, `gateway`, `fleet`, `forks`, `steps`, `teardown`, `runId`, `startedAt`, `finishedAt` and `wallMs`. The schema is a clean break. `SCHEMA` is 3, `validate` rejects any other schema, `_load` returns None for such a file, and `admit` reports `no-receipt` when only older receipts exist, so a schema 2 receipt (VERIFIED or NOT_VERIFIED) neither admits a push nor backs an escape. Old files stay on disk, unread.

A run that lost the fleet lock (P0's `fleet-busy`) judged nothing, and a holder may still be running on the same tree, so its record never replaces `receipt.json` or a `<tree>.json` archive: `write_run_record` keeps it at `runs/<runId>/receipt.json` only, which no lookup here reads (VC7(a), 2026-10-20: a busy loser rewrote `receipt.json` while the holder ran, and had it finished last it would have replaced the holder's VERIFIED receipt).

The receipt folder also holds files that are not receipts (A0's `gateway.json` record and `gateway.log`, the per-run evidence under `runs/`); `receipt_files` names only `receipt.json` and the `<tree>.json` archives.

A step row may carry `log` (the path of the kept full output) and `failedAssertions` (a drill's failed assertions, `<number> <description>`); the receipt may carry `runDir`, the directory of that evidence. All three are optional, and checked for shape when present.

A receipt may carry `areas` (agent/plans/PLAN-renet-change-test-triggers.md V1): `{area: {"legs": [{id, kind, status, detail}]}}` for the renet areas the change touched, with `trigger.areas` naming them. A leg that is not `ok` already made the run NOT_VERIFIED (`area-not-verified`), so `admit` needs no rule of its own for them; `areas` is checked for shape only.

A receipt records two phases (`phases.renet`, `phases.account`, each `{required, ran}`) and the sides the trigger found (`trigger.sides`). A VERIFIED receipt needs at least one phase that ran and every required phase ran.

`admit` is the rule the push guard applies. A receipt admits a push when its status is VERIFIED, its `tree` equals the pushed tree or its `inputs` digest equals the digest of the pushed tree, every side the push touches (`sides`) had its phase run, and `receipt.identity_refusal` keeps the identity rules for the surfaces of those sides: a clean console tree, each needed submodule checked out at its pointer and unmodified, and a renet build that is the renet pointer and unmodified when a surface needs one. A later commit outside the trigger paths keeps the `inputs` digest, so it costs no new VM run; any trigger blob or pointer move changes it.

THE `--only` MERGE (agent/plans/PLAN-vmcheck-incremental.md V1). A FAILED receipt can be repaired step by step: a `--only` run of steps that receipt FAILED merges its rows into the receipt of the same tree, and vm_check re-judges the merged ledger with the verdict a full run uses, so the receipt becomes VERIFIED only when no failed step remains AND every required phase and area leg is proven. `merge_refusal` is the admission rule of that merge, and every rule is a refusal:

  the base       is FAILED (`step-failed`), has no stop row (`--`), a clean teardown, and failed only phase steps: a failure in P0-P4 (`MANDATORY_STEPS`) or T is never merged, since those rows decide what every later step ran against
  the run        carries `only` (the steps it named), each a step the base FAILED, at least one row per named step and every such row ok, no failed row anywhere, no stop row, a clean teardown, and a reason that only says it was narrowed (`phase-not-run`, `only-partial`)
  the identity   the run's `tree`, `inputs` and `submodules` equal the base's, its `dirty` is false, and its renet build (`built`, `modified`, `sha256`) equals the base's. The CLI runs from the console tree on every `rdc` call, so the tree is the CLI build identity.

A merged receipt records each merge in `merged` (`runId`, `tree`, `inputs`, `steps`, `renet`, `submodules`), and `validate` holds every entry to the receipt it sits in: the same tree, inputs, submodules and renet build, no mandatory step, and on a VERIFIED receipt an ok row for every merged step. A merge that would leave the receipt NOT_VERIFIED is not written: the FAILED receipt stays, and the run says why.

THE VERIFIED CHAIN (V2). `vm:check --changed` diffs against the newest commit on the branch whose own receipt the guard admits (`verified_base_admits`), and records it as `trigger.verifiedBase` (`head`, `tree`). Such a receipt ran only the sides changed since that base, so `admit` takes a `Chain` (the pushed commit, a `touched(old, new)` that names the sides changed between two commits, and the digest of a tree): a VERIFIED receipt for the pushed tree that did not run a side the push touches admits only when its `verifiedBase` names a commit since which that side is untouched up to the pushed commit, and `admit` itself admits that base tree for the missing sides, recursively up to `CHAIN_MAX` links. Nothing of the recorded base is believed but its commit: the guard recomputes what changed since it and judges the base receipt afresh.
"""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
from typing import TYPE_CHECKING, Any

from rediacc_ci.proof import receipt as R
from rediacc_ci.proof import surfaces as S

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Collection, Sequence

SCHEMA = 3
TIER = "vm"
VERIFIED = R.VERIFIED
FAILED = R.FAILED
NOT_VERIFIED = R.NOT_VERIFIED
STATUSES = R.STATUSES
SIDES = S.SIDES
Verdict = R.Verdict
CACHE_DIR = ".ci/cache/vm-check"
LATEST = "receipt.json"
RUNS_DIR = "runs"
EVIDENCE_MAX = 200
ARCHIVE_SCAN_MAX = 50
_TREE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
# The steps every run takes before any phase step (vm_check.INFRA_STEPS, which a test holds equal to this): the lock, the build identity, the account token, the fleet and the keys. A `--only` run always re-runs them and never names one.
MANDATORY_STEPS = ("P0", "P1", "P2", "P3", "P4")
# Rows a merge never takes or repairs: the mandatory chain, the teardown and the stop row a run records when it could not go on.
UNMERGEABLE_ROWS = (*MANDATORY_STEPS, "T", "--")
# The reasons an `--only` run's own verdict may carry and still feed a merge: both say only that the run was narrowed, never that something could not be judged.
MERGEABLE_RUN_REASONS = ("phase-not-run", "only-partial")
# The renet build fields a merged step must share with the receipt it lands in.
BUILD_KEYS = ("built", "modified", "sha256")
# The longest VERIFIED chain `admit` follows: every link is one VERIFIED run, and a chain longer than this is a loop or a history nobody should lean on.
CHAIN_MAX = 8
_RUN_ID = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*")
_BODY = (
    "reason",
    "trigger",
    "fleet",
    "phases",
    "gateway",
    "forks",
    "steps",
    "teardown",
    "runId",
    "startedAt",
    "finishedAt",
    "wallMs",
)


def receipt_dir(root: pathlib.Path) -> pathlib.Path:
    return root / CACHE_DIR


def receipt_files(root: pathlib.Path) -> list[pathlib.Path]:
    """`receipt.json` and every `<tree>.json` archive in the receipt folder, nothing else (review 2fa7d53d.1: `gateway.json` was counted as a receipt of an earlier schema)."""
    folder = receipt_dir(root)
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.glob("*.json") if p.name == LATEST or _TREE.match(p.name[: -len(".json")])
    )


def clip_evidence(text: str) -> str:
    """At most EVIDENCE_MAX bytes of UTF-8, cut on a character boundary."""
    raw = text.encode()
    if len(raw) <= EVIDENCE_MAX:
        return text
    return raw[:EVIDENCE_MAX].decode(errors="ignore")


def _phase_errors(receipt: dict[str, Any], status: object) -> list[str]:
    phases = receipt.get("phases")
    if not isinstance(phases, dict):
        return []
    errors: list[str] = []
    flags: dict[str, tuple[bool, bool]] = {}
    for side in SIDES:
        entry = phases.get(side)
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(k), bool) for k in ("required", "ran")
        ):
            errors.append(f"phases.{side} needs boolean required and ran")
        else:
            flags[side] = (entry["required"], entry["ran"])
    if status == VERIFIED and len(flags) == len(SIDES):
        if not any(ran for _, ran in flags.values()):
            errors.append("a VERIFIED receipt needs at least one phase that ran")
        errors.extend(
            f"a VERIFIED receipt needs the required phase {side} to have run"
            for side, (required, ran) in flags.items()
            if required and not ran
        )
    return errors


def _sides_errors(trigger: object) -> list[str]:
    if not isinstance(trigger, dict):
        return []
    sides = trigger.get("sides")
    if not isinstance(sides, list) or not all(s in SIDES for s in sides):
        return [f"trigger.sides is not a list of {', '.join(SIDES)}"]
    return []


def validate(receipt: object) -> list[str]:
    """Every way `receipt` departs from schema 3, empty when it is well formed."""
    errors = R.envelope_errors(receipt)
    if not isinstance(receipt, dict):
        return errors
    errors.extend(f"missing field {k}" for k in _BODY if k not in receipt)
    if receipt.get("tier") != TIER:
        errors.append(f"tier is {receipt.get('tier')!r}, not {TIER!r}")
    if receipt.get("schema") != SCHEMA:
        errors.append(f"schema is {receipt.get('schema')!r}, not {SCHEMA}")
    status = receipt.get("status")
    reason = receipt.get("reason")
    if status == VERIFIED and reason is not None:
        errors.append("a VERIFIED receipt carries no reason")
    if status in (FAILED, NOT_VERIFIED) and not (isinstance(reason, dict) and reason.get("class")):
        errors.append(f"a {status} receipt needs reason.class")
    # admit reads these with .get, so a truthy non-object would raise instead of refusing.
    errors.extend(
        f"{key} is not an object"
        for key in ("trigger", "fleet", "teardown", "phases", "gateway", "areas")
        if key in receipt and not isinstance(receipt[key], dict)
    )
    errors.extend(_phase_errors(receipt, status))
    errors.extend(_sides_errors(receipt.get("trigger")))
    if "forks" in receipt and not isinstance(receipt["forks"], list):
        errors.append("forks is not a list")
    if "runDir" in receipt and not (
        receipt["runDir"] is None or isinstance(receipt["runDir"], str)
    ):
        errors.append("runDir is not a string or null")
    steps = receipt.get("steps")
    if not isinstance(steps, list):
        errors.append("steps is not a list")
    else:
        for step in steps:
            errors.extend(_step_errors(step))
    if "only" in receipt and not (
        isinstance(receipt["only"], list)
        and receipt["only"]
        and all(isinstance(s, str) and s for s in receipt["only"])
    ):
        errors.append("only is not a non-empty list of step ids")
    errors.extend(_verified_base_errors(receipt.get("trigger")))
    errors.extend(_merged_errors(receipt))
    return errors


def _verified_base_errors(trigger: object) -> list[str]:
    if not isinstance(trigger, dict) or "verifiedBase" not in trigger:
        return []
    base = trigger["verifiedBase"]
    if not (
        isinstance(base, dict)
        and all(isinstance(base.get(k), str) and _TREE.match(base[k]) for k in ("head", "tree"))
    ):
        return ["trigger.verifiedBase needs a head and a tree, each a git object id"]
    return []


def build_of(receipt: dict[str, Any]) -> dict[str, Any] | None:
    """The renet build identity of `receipt` (`BUILD_KEYS`), or None when it records no renet object."""
    renet = receipt.get("renet")
    if not isinstance(renet, dict):
        return None
    return {k: renet.get(k) for k in BUILD_KEYS}


def _merged_errors(receipt: dict[str, Any]) -> list[str]:
    """Each `merged` entry held to the receipt it sits in (module docstring, THE `--only` MERGE)."""
    if "merged" not in receipt:
        return []
    merged = receipt["merged"]
    if not isinstance(merged, list) or not merged:
        return ["merged is not a non-empty list"]
    errors: list[str] = []
    status = receipt.get("status")
    if status not in (VERIFIED, FAILED):
        errors.append(f"a {status} receipt carries no merged steps")
    rows = receipt.get("steps") if isinstance(receipt.get("steps"), list) else []
    for n, entry in enumerate(merged):
        where = f"merged[{n}]"
        if not isinstance(entry, dict):
            errors.append(f"{where} is not an object")
            continue
        if not isinstance(entry.get("runId"), str) or not entry["runId"]:
            errors.append(f"{where} names no runId")
        errors.extend(
            f"{where}.{key} is not the receipt's {key}"
            for key in ("tree", "inputs", "submodules")
            if entry.get(key) != receipt.get(key)
        )
        if entry.get("renet") != build_of(receipt):
            errors.append(f"{where}.renet is not the receipt's renet build")
        steps = entry.get("steps")
        if not (isinstance(steps, list) and steps and all(isinstance(s, str) for s in steps)):
            errors.append(f"{where}.steps is not a non-empty list of step ids")
            continue
        errors.extend(
            f"{where} merges {s}, which no merge may take" for s in steps if s in UNMERGEABLE_ROWS
        )
        if status == VERIFIED:
            for s in steps:
                mine = [r for r in rows if isinstance(r, dict) and r.get("id") == s]
                if not mine or any(r.get("verdict") != "ok" for r in mine):
                    errors.append(f"{where} merges {s}, which has no ok row in a VERIFIED receipt")
    return errors


def _step_errors(step: object) -> list[str]:
    if not isinstance(step, dict):
        return []
    errors: list[str] = []
    ev = step.get("evidence", "")
    if isinstance(ev, str) and len(ev.encode()) > EVIDENCE_MAX:
        errors.append(f"step {step.get('id')} evidence exceeds {EVIDENCE_MAX} bytes")
    if "log" in step and not isinstance(step["log"], str):
        errors.append(f"step {step.get('id')} log is not a string")
    failed = step.get("failedAssertions")
    if "failedAssertions" in step and not (
        isinstance(failed, list) and all(isinstance(f, str) for f in failed)
    ):
        errors.append(f"step {step.get('id')} failedAssertions is not a list of strings")
    return errors


def write(root: pathlib.Path, receipt: dict[str, Any]) -> pathlib.Path:
    """Write the latest receipt and its `<tree>.json` archive. Raises ValueError on a receipt that fails `validate`, so a run never records a shape the guard cannot read."""
    errors = validate(receipt)
    if errors:
        raise ValueError("invalid vm-check receipt: " + "; ".join(errors))
    data = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    out = receipt_dir(root)
    R.write_atomic(out / f"{receipt['tree']}.json", data)
    R.write_atomic(out / LATEST, data)
    return out / LATEST


def run_record_path(root: pathlib.Path, run_id: str) -> pathlib.Path:
    return receipt_dir(root) / RUNS_DIR / run_id / LATEST


def write_run_record(root: pathlib.Path, receipt: dict[str, Any]) -> pathlib.Path:
    """Keep the record of a run that never held the fleet lock at `runs/<runId>/receipt.json`, and nothing else: `receipt.json` and every `<tree>.json` archive stay byte-identical, so a busy loser finishing after the holder cannot replace the holder's receipt. Raises ValueError on a receipt that fails `validate` or a `runId` that is not a plain directory name."""
    errors = validate(receipt)
    run_id = receipt.get("runId")
    if not (isinstance(run_id, str) and _RUN_ID.fullmatch(run_id)):
        errors.append(f"runId {run_id!r} is not a plain directory name")
    if errors or not isinstance(run_id, str):
        raise ValueError("invalid vm-check run record: " + "; ".join(errors))
    path = run_record_path(root, run_id)
    R.write_atomic(path, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return path


def _load(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parsed if not validate(parsed) else None


def read_archive(root: pathlib.Path, tree: str) -> dict[str, Any] | None:
    """The archived receipt of `tree`, or None when absent, unreadable or malformed."""
    if not _TREE.match(tree):
        return None
    return _load(receipt_dir(root) / f"{tree}.json")


def read_latest(root: pathlib.Path) -> dict[str, Any] | None:
    return _load(receipt_dir(root) / LATEST)


# --------------------------------------------------------------------------- the --only merge (V1)


def failed_step_ids(receipt: dict[str, Any]) -> list[str]:
    """The ids of the rows `receipt` FAILED, in ledger order, each once."""
    out: list[str] = []
    for row in receipt.get("steps") or []:
        if isinstance(row, dict) and str(row.get("verdict", "")).upper().startswith("FAIL"):
            sid = str(row.get("id"))
            if sid not in out:
                out.append(sid)
    return out


def _rows_of(receipt: dict[str, Any], step: str) -> list[dict[str, Any]]:
    return [r for r in receipt.get("steps") or [] if isinstance(r, dict) and r.get("id") == step]


def _base_refusal(base: dict[str, Any]) -> str | None:
    if base.get("status") != FAILED:
        return "the receipt of tree %s is %s, and only a FAILED receipt takes a --only merge" % (
            str(base.get("tree"))[:12],
            base.get("status"),
        )
    if (base.get("reason") or {}).get("class") != "step-failed":
        return "the FAILED receipt is not step-failed, so it names no failed step to repair"
    if _rows_of(base, "--"):
        return "the FAILED receipt stopped part-way (a `--` row), so later steps never ran; run the whole check"
    if (base.get("teardown") or {}).get("ok") is not True:
        return "the FAILED receipt's teardown left resources behind; run the whole check"
    failed = failed_step_ids(base)
    if not failed:
        return "the FAILED receipt records no failed row"
    mandatory = [s for s in failed if s in UNMERGEABLE_ROWS]
    if mandatory:
        return (
            "the FAILED receipt failed at %s, a step every run takes and every later step ran against; run the whole check"
            % ", ".join(mandatory)
        )
    return None


def _run_refusal(run: dict[str, Any], named: Sequence[str], failed: Sequence[str]) -> str | None:
    extra = [s for s in named if s not in failed]
    if extra:
        return "the --only run names %s, which the FAILED receipt did not fail (it failed %s)" % (
            ", ".join(extra),
            ", ".join(failed),
        )
    if run.get("status") == FAILED or failed_step_ids(run):
        return "the --only run has a failed row (%s)" % ", ".join(failed_step_ids(run) or ["?"])
    if _rows_of(run, "--"):
        return "the --only run stopped part-way (a `--` row)"
    if (run.get("teardown") or {}).get("ok") is not True:
        return "the --only run's teardown left resources behind"
    cls = (run.get("reason") or {}).get("class")
    if run.get("status") != NOT_VERIFIED or cls not in MERGEABLE_RUN_REASONS:
        return "the --only run ended %s (%s), not as a narrowed pass" % (run.get("status"), cls)
    for step in named:
        rows = _rows_of(run, step)
        if not rows:
            return "the --only run recorded no %s row" % step
        if any(r.get("verdict") != "ok" for r in rows):
            return "the --only run's %s rows are not all ok" % step
    return None


def _identity_mismatch(base: dict[str, Any], run: dict[str, Any]) -> str | None:
    if run.get("tree") != base.get("tree"):
        return "the --only run judged tree %s, not the FAILED receipt's tree %s" % (
            str(run.get("tree"))[:12],
            str(base.get("tree"))[:12],
        )
    if run.get("inputs") != base.get("inputs"):
        return "the --only run's inputs digest is not the FAILED receipt's"
    if run.get("dirty") is not False:
        return "the --only run's console tree was not clean (dirty=%s)" % run.get("dirty")
    if run.get("submodules") != base.get("submodules"):
        return "the --only run's submodule pointers, checkouts or modified flags are not the FAILED receipt's"
    built = build_of(run)
    if built is None or built != build_of(base):
        return (
            "the --only run's renet build %s is not the one the FAILED receipt was judged with (%s)"
            % (
                json.dumps(built, sort_keys=True),
                json.dumps(build_of(base), sort_keys=True),
            )
        )
    return None


def merge_refusal(base: dict[str, Any], run: dict[str, Any]) -> str | None:
    """Why the `--only` run record `run` may not merge into the receipt `base`, or None when it may (module docstring, THE `--only` MERGE). PURE."""
    refused = _base_refusal(base)
    if refused is not None:
        return refused
    named = run.get("only")
    if not (isinstance(named, list) and named and all(isinstance(s, str) for s in named)):
        return "the run record names no --only steps, so it is not a --only run"
    if run.get("runId") == base.get("runId") or any(
        isinstance(e, dict) and e.get("runId") == run.get("runId") for e in base.get("merged") or []
    ):
        return "run %s is already part of this receipt" % run.get("runId")
    return _run_refusal(run, named, failed_step_ids(base)) or _identity_mismatch(base, run)


def merge_steps(
    base_steps: Sequence[dict[str, Any]],
    run_steps: Sequence[dict[str, Any]],
    named: Collection[str],
) -> list[dict[str, Any]]:
    """`base_steps` with every row of a `named` step replaced by the run's rows of that step, in place of the first base row of it."""
    out: list[dict[str, Any]] = []
    placed: set[str] = set()
    for row in base_steps:
        sid = str(row.get("id"))
        if sid not in named:
            out.append(dict(row))
            continue
        if sid not in placed:
            placed.add(sid)
            out.extend(dict(r) for r in run_steps if r.get("id") == sid)
    return out


def merge_entry(run: dict[str, Any]) -> dict[str, Any]:
    """The `merged` record of the `--only` run `run`."""
    return {
        "runId": run["runId"],
        "tree": run["tree"],
        "inputs": run["inputs"],
        "steps": sorted(run["only"]),
        "renet": build_of(run),
        "submodules": run["submodules"],
        "finishedAt": run.get("finishedAt"),
    }


# --------------------------------------------------------------------------- the VERIFIED chain (V2)


@dataclasses.dataclass(frozen=True)
class Chain:
    """What `admit` needs to follow a receipt's `trigger.verifiedBase`: the commit being judged, the sides changed between two commits, and the inputs digest of a tree."""

    tip: str
    touched: Callable[[str, str], Collection[str]]
    digest: Callable[[str], str | None]
    # The tree a commit names, so a receipt's claimed `verifiedBase.tree` is checked against its `head` rather than believed (review 3dd946ff.1). `chain_for`, the one production constructor, always sets it; only hand-built test chains leave it None.
    tree_of: Callable[[str], str | None] | None = None
    # Every tree the chain has already followed, so a cycle of any length reads as `chain-loop` (review 3dd946ff.3).
    seen: frozenset[str] = frozenset()


def chain_for(root: pathlib.Path, tip: str) -> Chain:
    """The `Chain` of commit `tip` in the checkout at `root`, from the one trigger definition (`surfaces.changed_paths`, push mode, which charges every side an unknown range or a failed diff could reach)."""
    return Chain(
        tip,
        lambda old, new: frozenset(S.changed_paths(root, old, "push", new).sides),
        lambda tree: S.inputs(root, tree),
        lambda head: _tree_of(root, head),
    )


def _tree_of(root: pathlib.Path, head: str) -> str | None:
    """`head^{tree}` in the checkout at `root`, or None when git cannot resolve it."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", head + "^{tree}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def verified_base_admits(root: pathlib.Path, merge_base: str) -> Callable[[str, str], bool]:
    """The predicate `surfaces.newest_verified_base` asks of each commit on the branch: True when `commit` (tree `tree`) has its own VERIFIED archive and `admit` admits it for the sides changed since `merge_base`, which is the push guard's own judgment of that tree."""

    def admitted(commit: str, tree: str) -> bool:
        own = read_archive(root, tree)
        if own is None or own.get("status") != VERIFIED:
            return False
        sides = frozenset(S.changed_paths(root, merge_base, "push", commit).sides)
        return admit(root, tree, S.inputs(root, tree), sides, chain_for(root, commit)).ok

    return admitted


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


def _failed_step(receipt: dict[str, Any]) -> str:
    for step in receipt.get("steps", []):
        if isinstance(step, dict) and str(step.get("verdict", "")).upper().startswith("FAIL"):
            return f"{step.get('id')}: {step.get('desc', '')} ({step.get('evidence', '')})"
    reason = receipt.get("reason") or {}
    return f"{reason.get('class')}: {reason.get('detail', '')}"


def _phase_missing(receipt: dict[str, Any], sides: Collection[str]) -> Verdict | None:
    phases = receipt.get("phases") or {}
    for side in SIDES:
        if side in sides and not (phases.get(side) or {}).get("ran"):
            return Verdict(
                False,
                "phase-missing",
                f"the VERIFIED receipt did not run the {side} phase this push touches; run `npm run vm:check -- --changed`",
                receipt,
            )
    return None


def sides_surfaces(sides: Collection[str]) -> frozenset[str]:
    """The surfaces the VM phases `sides` cover."""
    return frozenset().union(*(S.MAP.phases[side] for side in sides if side in S.MAP.phases))


def _judge(
    receipt: dict[str, Any], tree: str, inputs_digest: str | None, sides: Collection[str]
) -> Verdict:
    status = receipt["status"]
    reason = receipt.get("reason") or {}
    if status == NOT_VERIFIED:
        return Verdict(
            False,
            "not-verified",
            f"the last vm:check was NOT_VERIFIED ({reason.get('class')}): {reason.get('detail', '')}",
            receipt,
        )
    if status == FAILED:
        return Verdict(
            False, "failed", f"the last vm:check FAILED at {_failed_step(receipt)}", receipt
        )
    same_tree = receipt["tree"] == tree
    same_inputs = bool(inputs_digest) and receipt["inputs"] == inputs_digest
    if not (same_tree or same_inputs):
        return Verdict(
            False,
            "other-inputs",
            f"the VERIFIED receipt (tree {receipt['tree'][:12]}) was taken with other trigger inputs than tree {tree[:12]}",
            receipt,
        )
    missing = _phase_missing(receipt, sides)
    if missing is not None:
        return missing
    refused = R.identity_refusal(receipt, sides_surfaces(sides))
    if refused is not None:
        return refused
    return Verdict(
        True, "ok", f"VERIFIED receipt {receipt['runId']} covers tree {tree[:12]}", receipt
    )


def _ran_sides(receipt: dict[str, Any]) -> frozenset[str]:
    phases = receipt.get("phases") or {}
    return frozenset(s for s in SIDES if (phases.get(s) or {}).get("ran"))


def _chained(
    root: pathlib.Path,
    receipt: dict[str, Any],
    tree: str,
    sides: Collection[str],
    chain: Chain,
    depth: int,
) -> Verdict | None:
    """The verdict of a VERIFIED `receipt` for `tree` that did not run every side in `sides`, read through its `trigger.verifiedBase`; None when it names no base, so its `phase-missing` stands."""
    base = (receipt.get("trigger") or {}).get("verifiedBase")
    if not isinstance(base, dict):
        return None
    run_id = receipt.get("runId")
    missing = frozenset(s for s in sides if s not in _ran_sides(receipt))
    head, base_tree = str(base.get("head")), str(base.get("tree"))
    if depth >= CHAIN_MAX:
        return Verdict(
            False,
            "chain-too-long",
            "the VERIFIED chain from tree %s is longer than %d links; run `npm run vm:check -- --changed`"
            % (tree[:12], CHAIN_MAX),
            receipt,
        )
    if base_tree in (tree, receipt.get("tree")) or base_tree in chain.seen:
        return Verdict(
            False,
            "chain-loop",
            "receipt %s names a tree already in its VERIFIED chain as its base" % run_id,
            receipt,
        )
    if chain.tree_of is not None and chain.tree_of(head) != base_tree:
        return Verdict(
            False,
            "chain-broken",
            "receipt %s names VERIFIED base %s with tree %s, but that commit's tree is %s"
            % (run_id, head[:12], base_tree[:12], (chain.tree_of(head) or "unresolvable")[:12]),
            receipt,
        )
    moved = sorted(missing & frozenset(chain.touched(head, chain.tip)))
    if moved:
        return Verdict(
            False,
            "chain-touched",
            "the %s side changed since the VERIFIED base %s and receipt %s did not run its phase; run `npm run vm:check -- --changed`"
            % (" and ".join(moved), head[:12], run_id),
            receipt,
        )
    refused = R.identity_refusal(receipt, sides_surfaces(frozenset(sides) - missing))
    if refused is not None:
        return refused
    under = admit(
        root,
        base_tree,
        chain.digest(base_tree),
        missing,
        Chain(head, chain.touched, chain.digest, chain.tree_of, chain.seen | {tree}),
        depth + 1,
    )
    if not under.ok:
        return Verdict(
            False,
            "chain-broken",
            "receipt %s leaves the %s phase to its VERIFIED base %s, which does not cover it: [%s] %s"
            % (run_id, " and ".join(sorted(missing)), base_tree[:12], under.code, under.message),
            receipt,
        )
    return Verdict(
        True,
        "ok",
        "VERIFIED receipt %s covers tree %s, and the %s phase rides its base: %s"
        % (run_id, tree[:12], " and ".join(sorted(missing)), under.message),
        receipt,
    )


def admit(
    root: pathlib.Path,
    tree: str,
    inputs_digest: str | None,
    sides: Collection[str],
    chain: Chain | None = None,
    _depth: int = 0,
) -> Verdict:
    """The guard's verdict for pushing `tree` whose trigger digest is `inputs_digest` and whose trigger hits fall on `sides`.

    Any candidate that admits wins. With a `chain`, a VERIFIED candidate that is `phase-missing` is judged again through its `trigger.verifiedBase` (module docstring, THE VERIFIED CHAIN), and that verdict replaces its own. Otherwise the refusal comes from the first candidate: the tree's own archive, then the latest receipt, then the newest other archives.
    """
    candidates = _candidates(root, tree)
    if not candidates:
        return Verdict(False, "no-receipt", f"no vm:check receipt exists for tree {tree[:12]}")
    verdicts = [_judge(c, tree, inputs_digest, sides) for c in candidates]
    for verdict in verdicts:
        if verdict.ok:
            return verdict
    if chain is not None:
        for n, (receipt, verdict) in enumerate(zip(candidates, verdicts, strict=True)):
            if verdict.code != "phase-missing":
                continue
            chained = _chained(root, receipt, tree, sides, chain, _depth)
            if chained is None:
                continue
            if chained.ok:
                return chained
            verdicts[n] = chained
    return verdicts[0]
