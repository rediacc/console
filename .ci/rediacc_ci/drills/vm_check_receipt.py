"""The `npm run vm:check` receipt: how it is written, archived, read and judged.

The latest receipt is `.ci/cache/vm-check/receipt.json`. Every write also archives it as `<tree>.json`, so a later run on another tree does not hide the receipt of an earlier push. `.ci/cache/` is gitignored.

`admit` is the rule the push guard applies. A receipt admits a push when its status is VERIFIED, its `tree` equals the pushed tree or its `inputs` digest equals the digest of the pushed tree, the renet it deployed (`renet.built`) is the renet the tree points at (`renet.pointer`), and that build was not modified. A later commit outside the trigger paths keeps the `inputs` digest, so it costs no new VM run; any trigger blob or pointer move changes it.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import tempfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pathlib

SCHEMA = 1
VERIFIED = "VERIFIED"
FAILED = "FAILED"
NOT_VERIFIED = "NOT_VERIFIED"
STATUSES = (VERIFIED, FAILED, NOT_VERIFIED)
CACHE_DIR = ".ci/cache/vm-check"
LATEST = "receipt.json"
EVIDENCE_MAX = 200
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
    "trigger",
    "fleet",
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


def clip_evidence(text: str) -> str:
    """At most EVIDENCE_MAX bytes of UTF-8, cut on a character boundary."""
    raw = text.encode()
    if len(raw) <= EVIDENCE_MAX:
        return text
    return raw[:EVIDENCE_MAX].decode(errors="ignore")


def validate(receipt: object) -> list[str]:
    """Every way `receipt` departs from the schema, empty when it is well formed."""
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
    # admit reads these with .get, so a truthy non-object would raise instead of refusing.
    errors.extend(
        f"{key} is not an object"
        for key in ("renet", "trigger", "fleet", "teardown")
        if key in receipt and not isinstance(receipt[key], dict)
    )
    if "forks" in receipt and not isinstance(receipt["forks"], list):
        errors.append("forks is not a list")
    steps = receipt.get("steps")
    if not isinstance(steps, list):
        errors.append("steps is not a list")
    else:
        for step in steps:
            ev = step.get("evidence", "") if isinstance(step, dict) else ""
            if isinstance(ev, str) and len(ev.encode()) > EVIDENCE_MAX:
                errors.append(f"step {step.get('id')} evidence exceeds {EVIDENCE_MAX} bytes")
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
    """Write the latest receipt and its `<tree>.json` archive. Raises ValueError on a receipt that fails `validate`, so a run never records a shape the guard cannot read."""
    errors = validate(receipt)
    if errors:
        raise ValueError("invalid vm-check receipt: " + "; ".join(errors))
    data = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    out = receipt_dir(root)
    _atomic(out / f"{receipt['tree']}.json", data)
    _atomic(out / LATEST, data)
    return out / LATEST


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


@dataclasses.dataclass(frozen=True)
class Verdict:
    """`ok` admits the push. `code` is one of ok, no-receipt, not-verified, failed, other-inputs, build-mismatch, modified-build. `message` is the sentence the guard shows."""

    ok: bool
    code: str
    message: str
    receipt: dict[str, Any] | None = None


def _failed_step(receipt: dict[str, Any]) -> str:
    for step in receipt.get("steps", []):
        if isinstance(step, dict) and str(step.get("verdict", "")).upper().startswith("FAIL"):
            return f"{step.get('id')}: {step.get('desc', '')} ({step.get('evidence', '')})"
    reason = receipt.get("reason") or {}
    return f"{reason.get('class')}: {reason.get('detail', '')}"


def _judge(receipt: dict[str, Any], tree: str, inputs_digest: str | None) -> Verdict:
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
    renet = receipt.get("renet") or {}
    if renet.get("built") != renet.get("pointer") or not renet.get("built"):
        return Verdict(
            False,
            "build-mismatch",
            f"the deployed renet {str(renet.get('built'))[:12]} is not the pointer {str(renet.get('pointer'))[:12]}",
            receipt,
        )
    if renet.get("modified") is not False:
        return Verdict(
            False, "modified-build", "the receipt's renet build had uncommitted changes", receipt
        )
    return Verdict(
        True, "ok", f"VERIFIED receipt {receipt['runId']} covers tree {tree[:12]}", receipt
    )


def admit(root: pathlib.Path, tree: str, inputs_digest: str | None) -> Verdict:
    """The guard's verdict for pushing `tree` whose trigger digest is `inputs_digest`.

    Any candidate that admits wins. Otherwise the refusal comes from the first candidate: the tree's own archive, then the latest receipt, then the newest other archives.
    """
    candidates = _candidates(root, tree)
    if not candidates:
        return Verdict(False, "no-receipt", f"no vm:check receipt exists for tree {tree[:12]}")
    verdicts = [_judge(c, tree, inputs_digest) for c in candidates]
    for verdict in verdicts:
        if verdict.ok:
            return verdict
    return verdicts[0]
