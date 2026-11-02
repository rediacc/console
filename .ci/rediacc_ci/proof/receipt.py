"""The receipt envelope both proof tiers share, its identity capture and the one identity judge (agent/plans/PLAN-tested-on-bench.md Design item 6).

THE ENVELOPE. Every receipt, VM or live, carries `tier` (`vm` or `live`), `schema`, `status` (VERIFIED, FAILED or NOT_VERIFIED), `tree`, `head`, `dirty`, `inputs`, `surfaces`, `submodules` (`{"private/renet": {pointer, checkout, modified}, "private/account": {...}}`) and `renet` (`{built, modified, sha256}`, null when no given surface needs a renet build). The tier body adds its own fields; storage stays per tier.

`identity(root, surfaces)` captures every envelope field but `tier`, `schema` and `status` from the live checkout. `envelope(...)` adds those three and validates. `identity_refusal(receipt, surfaces)` is the judge every tier applies to the build and checkout rules, and reports through the shared `Verdict` codes:

  dirty-tree         a console path of a given surface was modified, staged or untracked
  checkout-mismatch  a submodule a given surface lives in is not checked out at its pointer
  modified-checkout  that submodule has a modified or untracked surface path (or could not tell)
  build-mismatch     `bin/renet` is not built from the renet pointer
  modified-build     `bin/renet` was built from a modified tree (or the build could not tell)
  not-live           a live body's deploy is not the head (`deploy.deployed_head`) or was not confirmed live

`row_id` is the id of a live ledger row: `lp-` and 12 hex of the sha256 of the canonical row without its `id`. `write_atomic` is the tmp-then-rename writer both tiers use.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import tempfile
from typing import TYPE_CHECKING, Any

from rediacc_ci.proof import surfaces as S

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Collection

TIERS = ("vm", "live")
VERIFIED = "VERIFIED"
FAILED = "FAILED"
NOT_VERIFIED = "NOT_VERIFIED"
STATUSES = (VERIFIED, FAILED, NOT_VERIFIED)
ENVELOPE_KEYS = (
    "tier",
    "schema",
    "status",
    "tree",
    "head",
    "dirty",
    "inputs",
    "surfaces",
    "submodules",
    "renet",
)
DIRTY_TREE = "dirty-tree"
CHECKOUT_MISMATCH = "checkout-mismatch"
MODIFIED_CHECKOUT = "modified-checkout"
BUILD_MISMATCH = "build-mismatch"
MODIFIED_BUILD = "modified-build"
NOT_LIVE = "not-live"
REFUSAL_CODES = (
    DIRTY_TREE,
    CHECKOUT_MISMATCH,
    MODIFIED_CHECKOUT,
    BUILD_MISMATCH,
    MODIFIED_BUILD,
    NOT_LIVE,
)
ROW_ID_PREFIX = "lp-"
_OID = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclasses.dataclass(frozen=True)
class Verdict:
    """`ok` admits. `code` is `ok` or a refusal code (`REFUSAL_CODES` here; a tier adds its own, such as the VM tier's `no-receipt`). `message` is the sentence a judge shows."""

    ok: bool
    code: str
    message: str
    receipt: dict[str, Any] | None = None


def needs_renet(surfaces: Collection[str]) -> bool:
    """True when a given surface needs the renet build identity (`renet_build` in the map)."""
    return any(S.MAP.surfaces[name].renet_build for name in surfaces)


def needed_submodules(surfaces: Collection[str]) -> tuple[str, ...]:
    """The submodules the given surfaces live in, plus private/renet when one needs a renet build."""
    subs: set[str] = set()
    for name in surfaces:
        subs |= S.MAP.surfaces[name].submodules
    if needs_renet(surfaces):
        subs.add(S.RENET_SUBMODULE)
    return tuple(s for s in S.SUBMODULES if s in subs)


def identity(
    root: pathlib.Path,
    surfaces: Collection[str],
    *,
    renet: Callable[[pathlib.Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The envelope fields of the checkout at `root` for `surfaces`: head, tree, dirty, the inputs digest of those surfaces at that tree, both submodules' pointer, checkout and modified state, and the renet build when a surface needs one. `renet` replaces `surfaces.renet_identity` (a caller passes one with its rebuild hook). KeyError on an unknown surface."""
    unknown = sorted(set(surfaces) - set(S.SURFACES))
    if unknown:
        msg = f"unknown surfaces {unknown}"
        raise KeyError(msg)
    git = S.make_git(root)
    head = git(["rev-parse", "HEAD"]) or ""
    tree = git(["rev-parse", "HEAD^{tree}"]) or ""
    build = None
    if needs_renet(surfaces):
        got = (renet or S.renet_identity)(root)
        build = {k: got.get(k) for k in ("built", "modified", "sha256")}
    return {
        "tree": tree,
        "head": head,
        "dirty": S.console_dirty(root, surfaces),
        "inputs": S.inputs(root, tree, surfaces) if tree else None,
        "surfaces": sorted(surfaces),
        "submodules": {sub: S.submodule_state(root, sub) for sub in S.SUBMODULES},
        "renet": build,
    }


def _submodule_errors(subs: object) -> list[str]:
    if not isinstance(subs, dict):
        return ["submodules is not an object"]
    errors: list[str] = []
    for sub in S.SUBMODULES:
        entry = subs.get(sub)
        if not (isinstance(entry, dict) and all(k in entry for k in ("pointer", "checkout"))):
            errors.append(f"submodules.{sub} needs pointer and checkout")
        elif not isinstance(entry.get("modified"), bool | None):
            errors.append(f"submodules.{sub}.modified is not a boolean or null")
    return errors


def envelope_errors(receipt: object) -> list[str]:
    """Every way `receipt` departs from the envelope, empty when it is well formed. The tier body is not judged here."""
    if not isinstance(receipt, dict):
        return ["receipt is not an object"]
    errors = [f"missing field {k}" for k in ENVELOPE_KEYS if k not in receipt]
    if receipt.get("tier") not in TIERS:
        errors.append(f"tier {receipt.get('tier')!r} is not one of {', '.join(TIERS)}")
    schema = receipt.get("schema")
    if not isinstance(schema, int) or isinstance(schema, bool):
        errors.append("schema is not an integer")
    if receipt.get("status") not in STATUSES:
        errors.append(f"status {receipt.get('status')!r} is not one of {', '.join(STATUSES)}")
    errors.extend(
        f"{key} is not a git object id"
        for key in ("tree", "head")
        if not (isinstance(receipt.get(key), str) and _OID.match(receipt[key]))
    )
    if "dirty" in receipt and not isinstance(receipt["dirty"], bool | None):
        errors.append("dirty is not a boolean or null")
    if not (isinstance(receipt.get("inputs"), str) and _SHA256.match(receipt["inputs"])):
        errors.append("inputs is not a sha256 digest")
    names = receipt.get("surfaces")
    if not (isinstance(names, list) and all(n in S.SURFACES for n in names)):
        errors.append(f"surfaces is not a list of {', '.join(S.SURFACES)}")
    errors.extend(_submodule_errors(receipt.get("submodules")))
    renet = receipt.get("renet")
    if renet is not None and not (
        isinstance(renet, dict) and all(k in renet for k in ("built", "modified", "sha256"))
    ):
        errors.append("renet is not null or an object with built, modified and sha256")
    return errors


def envelope(
    tier: str, schema: int, status: str, ident: dict[str, Any], **body: Any
) -> dict[str, Any]:
    """`ident` (from `identity`) with `tier`, `schema`, `status` and the tier `body`. ValueError when the result is not a well-formed envelope."""
    receipt = {**ident, **body, "tier": tier, "schema": schema, "status": status}
    errors = envelope_errors(receipt)
    if errors:
        raise ValueError("invalid receipt envelope: " + "; ".join(errors))
    return receipt


def _short(value: object) -> str:
    return str(value)[:12] if value else "<none>"


def _submodule_refusal(receipt: dict[str, Any], sub: str) -> Verdict | None:
    entry = (receipt.get("submodules") or {}).get(sub) or {}
    pointer, checkout = entry.get("pointer"), entry.get("checkout")
    if not pointer or checkout != pointer:
        return Verdict(
            False,
            CHECKOUT_MISMATCH,
            f"the {sub} checkout {_short(checkout)} is not its pointer {_short(pointer)}",
            receipt,
        )
    if entry.get("modified") is not False:
        return Verdict(
            False,
            MODIFIED_CHECKOUT,
            f"the {sub} checkout has uncommitted surface changes (modified={entry.get('modified')})",
            receipt,
        )
    return None


def _renet_refusal(receipt: dict[str, Any]) -> Verdict | None:
    renet = receipt.get("renet") or {}
    pointer = ((receipt.get("submodules") or {}).get(S.RENET_SUBMODULE) or {}).get("pointer")
    built = renet.get("built")
    if not built or built != pointer:
        return Verdict(
            False,
            BUILD_MISMATCH,
            f"bin/renet carries vcs.revision={_short(built)}, the renet pointer is {_short(pointer)}",
            receipt,
        )
    if renet.get("modified") is not False:
        return Verdict(
            False,
            MODIFIED_BUILD,
            f"bin/renet was built with vcs.modified={renet.get('modified')}",
            receipt,
        )
    return None


def _deploy_refusal(receipt: dict[str, Any]) -> Verdict | None:
    if "deploy" not in receipt:
        return None
    deploy = receipt.get("deploy") or {}
    if deploy.get("deployed_head") != receipt.get("head"):
        return Verdict(
            False,
            NOT_LIVE,
            f"the deploy was cut from {_short(deploy.get('deployed_head'))}, not the head {_short(receipt.get('head'))}",
            receipt,
        )
    if deploy.get("confirmed_live") is not True:
        return Verdict(
            False, NOT_LIVE, "the deployed version was not confirmed serving at check time", receipt
        )
    return None


def identity_refusal(receipt: dict[str, Any], surfaces: Collection[str]) -> Verdict | None:
    """The first identity rule `receipt` breaks for `surfaces`, or None when it keeps them all. Order: the console tree, each needed submodule's checkout, the renet build, then a live body's deploy."""
    if receipt.get("dirty") is not False:
        return Verdict(
            False,
            DIRTY_TREE,
            f"the console tree had uncommitted surface changes (dirty={receipt.get('dirty')})",
            receipt,
        )
    for sub in needed_submodules(surfaces):
        refused = _submodule_refusal(receipt, sub)
        if refused is not None:
            return refused
    if needs_renet(surfaces):
        refused = _renet_refusal(receipt)
        if refused is not None:
            return refused
    return _deploy_refusal(receipt)


def canonical(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def row_id(row: dict[str, Any]) -> str:
    """`lp-` and 12 hex of the sha256 of `row` without its `id`, canonically serialised."""
    body = {k: v for k, v in row.items() if k != "id"}
    return ROW_ID_PREFIX + hashlib.sha256(canonical(body).encode()).hexdigest()[:12]


def write_atomic(path: pathlib.Path, data: str) -> None:
    """Write `data` to `path` through a temporary sibling and a rename, so a reader never sees half a file."""
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
