"""The `npm run vm:check` receipt (the VM tier): how it is written, archived, read and judged.

The latest receipt is `.ci/cache/vm-check/receipt.json`. Every write also archives it as `<tree>.json`, so a later run on another tree does not hide the receipt of an earlier push. `.ci/cache/` is gitignored.

Schema 3 is the shared envelope of `rediacc_ci.proof.receipt` (`tier` is `vm`, then `tree`, `head`, `dirty`, `inputs`, `surfaces`, `submodules` and `renet`) plus the VM body: `reason`, `trigger`, `phases`, `gateway`, `fleet`, `forks`, `steps`, `teardown`, `runId`, `startedAt`, `finishedAt` and `wallMs`. The schema is a clean break. `SCHEMA` is 3, `validate` rejects any other schema, `_load` returns None for such a file, and `admit` reports `no-receipt` when only older receipts exist, so a schema 2 receipt (VERIFIED or NOT_VERIFIED) neither admits a push nor backs an escape. Old files stay on disk, unread.

A run that lost the fleet lock (P0's `fleet-busy`) judged nothing, and a holder may still be running on the same tree, so its record never replaces `receipt.json` or a `<tree>.json` archive: `write_run_record` keeps it at `runs/<runId>/receipt.json` only, which no lookup here reads (VC7(a), 2026-10-20: a busy loser rewrote `receipt.json` while the holder ran, and had it finished last it would have replaced the holder's VERIFIED receipt).

The receipt folder also holds files that are not receipts (A0's `gateway.json` record and `gateway.log`, the per-run evidence under `runs/`); `receipt_files` names only `receipt.json` and the `<tree>.json` archives.

A step row may carry `log` (the path of the kept full output) and `failedAssertions` (a drill's failed assertions, `<number> <description>`); the receipt may carry `runDir`, the directory of that evidence. All three are optional, and checked for shape when present.

A receipt may carry `areas` (agent/plans/PLAN-renet-change-test-triggers.md V1): `{area: {"legs": [{id, kind, status, detail}]}}` for the renet areas the change touched, with `trigger.areas` naming them. A leg that is not `ok` already made the run NOT_VERIFIED (`area-not-verified`), so `admit` needs no rule of its own for them; `areas` is checked for shape only.

A receipt records two phases (`phases.renet`, `phases.account`, each `{required, ran}`) and the sides the trigger found (`trigger.sides`). A VERIFIED receipt needs at least one phase that ran and every required phase ran.

`admit` is the rule the push guard applies. A receipt admits a push when its status is VERIFIED, its `tree` equals the pushed tree or its `inputs` digest equals the digest of the pushed tree, every side the push touches (`sides`) had its phase run, and `receipt.identity_refusal` keeps the identity rules for the surfaces of those sides: a clean console tree, each needed submodule checked out at its pointer and unmodified, and a renet build that is the renet pointer and unmodified when a surface needs one. A later commit outside the trigger paths keeps the `inputs` digest, so it costs no new VM run; any trigger blob or pointer move changes it.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from rediacc_ci.proof import receipt as R
from rediacc_ci.proof import surfaces as S

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Collection

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


def admit(
    root: pathlib.Path, tree: str, inputs_digest: str | None, sides: Collection[str]
) -> Verdict:
    """The guard's verdict for pushing `tree` whose trigger digest is `inputs_digest` and whose trigger hits fall on `sides`.

    Any candidate that admits wins. Otherwise the refusal comes from the first candidate: the tree's own archive, then the latest receipt, then the newest other archives.
    """
    candidates = _candidates(root, tree)
    if not candidates:
        return Verdict(False, "no-receipt", f"no vm:check receipt exists for tree {tree[:12]}")
    verdicts = [_judge(c, tree, inputs_digest, sides) for c in candidates]
    for verdict in verdicts:
        if verdict.ok:
            return verdict
    return verdicts[0]
