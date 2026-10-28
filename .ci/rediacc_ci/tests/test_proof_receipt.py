"""`rediacc_ci.proof.receipt`: the envelope, `identity` over a real fixture checkout, one negative case per `identity_refusal` code with a healthy control beside it, and `row_id`.

The fixture is the console-with-two-submodules `World` of test_proof_surfaces; nothing reads the live tree.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.proof import receipt as R
from rediacc_ci.proof import surfaces as S
from rediacc_ci.tests.test_proof_surfaces import World, _commit, _git, _write

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

PTR_R = "a" * 40
PTR_A = "b" * 40
HEAD = "c" * 40
TREE = "d" * 40
ALL = tuple(S.SURFACES)


@pytest.fixture
def world(tmp_path: pathlib.Path) -> World:
    return World(tmp_path / "console")


def _healthy(**body: Any) -> dict[str, Any]:
    """A VERIFIED live receipt that keeps every identity rule for every surface."""
    ident = {
        "tree": TREE,
        "head": HEAD,
        "dirty": False,
        "inputs": "e" * 64,
        "surfaces": ["account", "renet"],
        "submodules": {
            "private/renet": {"pointer": PTR_R, "checkout": PTR_R, "modified": False},
            "private/account": {"pointer": PTR_A, "checkout": PTR_A, "modified": False},
        },
        "renet": {"built": PTR_R, "modified": False, "sha256": "f" * 64},
    }
    return R.envelope("live", 1, R.VERIFIED, ident, **body)


def _set(path: str, value: object) -> Callable[[dict[str, Any]], None]:
    keys = path.split(".")

    def apply(receipt: dict[str, Any]) -> None:
        node = receipt
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value

    return apply


def _sub(sub: str, key: str, value: object) -> Callable[[dict[str, Any]], None]:
    def apply(receipt: dict[str, Any]) -> None:
        receipt["submodules"][sub][key] = value

    return apply


LIVE_DEPLOY = {"deployed_head": HEAD, "confirmed_live": True}

# (code, surfaces, plant): each plant breaks exactly one identity rule of a healthy receipt.
REFUSAL_CASES: list[tuple[str, tuple[str, ...], Callable[[dict[str, Any]], None]]] = [
    (R.DIRTY_TREE, ("proxy",), _set("dirty", True)),
    (R.DIRTY_TREE, ("proxy",), _set("dirty", None)),
    (R.CHECKOUT_MISMATCH, ("account",), _sub("private/account", "checkout", "9" * 40)),
    (R.CHECKOUT_MISMATCH, ("account",), _sub("private/account", "pointer", "")),
    (R.CHECKOUT_MISMATCH, ("cli-remote",), _sub("private/renet", "checkout", "")),
    (R.MODIFIED_CHECKOUT, ("account",), _sub("private/account", "modified", True)),
    (R.MODIFIED_CHECKOUT, ("renet",), _sub("private/renet", "modified", None)),
    (R.BUILD_MISMATCH, ("renet",), _set("renet.built", "9" * 40)),
    (R.BUILD_MISMATCH, ("cli-remote",), _set("renet.built", "")),
    (R.BUILD_MISMATCH, ("renet",), _set("renet", None)),
    (R.MODIFIED_BUILD, ("renet",), _set("renet.modified", True)),
    (R.MODIFIED_BUILD, ("renet",), _set("renet.modified", None)),
    (R.NOT_LIVE, ("proxy",), _set("deploy", {"deployed_head": "9" * 40, "confirmed_live": True})),
    (R.NOT_LIVE, ("proxy",), _set("deploy", {"deployed_head": HEAD, "confirmed_live": False})),
    (R.NOT_LIVE, ("proxy",), _set("deploy", None)),
]


def test_a_healthy_receipt_is_refused_by_nothing() -> None:
    assert R.identity_refusal(_healthy(), ALL) is None
    assert R.identity_refusal(_healthy(deploy=dict(LIVE_DEPLOY)), ALL) is None


@pytest.mark.parametrize(("code", "surfaces", "plant"), REFUSAL_CASES)
def test_each_refusal_code_fires_on_its_plant(
    code: str, surfaces: tuple[str, ...], plant: Callable[[dict[str, Any]], None]
) -> None:
    receipt = _healthy(deploy=dict(LIVE_DEPLOY))
    assert R.identity_refusal(receipt, surfaces) is None, "the control must pass before the plant"
    planted = copy.deepcopy(receipt)
    plant(planted)
    got = R.identity_refusal(planted, surfaces)
    assert got is not None
    assert not got.ok
    assert got.code == code, got.message
    assert got.receipt is planted


def test_every_refusal_code_has_a_case() -> None:
    """The vocabulary and the cases above cannot drift apart: a new code needs its own plant."""
    assert {case[0] for case in REFUSAL_CASES} == set(R.REFUSAL_CODES)


@pytest.mark.parametrize(
    ("surfaces", "plant"),
    [
        (("account", "proxy", "www", "account-worker"), _set("renet", None)),
        (("account", "proxy", "cli"), _sub("private/renet", "checkout", "9" * 40)),
        (("proxy", "www", "cli"), _sub("private/account", "modified", True)),
    ],
)
def test_a_submodule_or_build_no_given_surface_needs_is_not_judged(
    surfaces: tuple[str, ...], plant: Callable[[dict[str, Any]], None]
) -> None:
    """The judge is scoped by surface: a bench-only account receipt carries no renet build, and a proxy proof does not care about the account checkout."""
    receipt = _healthy()
    plant(receipt)
    assert R.identity_refusal(receipt, surfaces) is None


def test_needed_submodules_follow_the_map() -> None:
    assert R.needed_submodules(("account",)) == ("private/account",)
    assert R.needed_submodules(("cli-remote",)) == ("private/renet",)
    assert R.needed_submodules(("renet", "account")) == ("private/renet", "private/account")
    assert R.needed_submodules(("proxy", "www", "cli")) == ()
    assert R.needs_renet(("cli-remote",))
    assert not R.needs_renet(("cli", "account"))


# ------------------------------------------------------------------ the envelope


@pytest.mark.parametrize(
    ("plant", "needle"),
    [
        (_set("tier", "edge"), "tier"),
        (_set("schema", True), "schema"),
        (_set("status", "OK"), "status"),
        (_set("tree", "abc"), "tree"),
        (_set("head", None), "head"),
        (_set("dirty", "no"), "dirty"),
        (_set("inputs", "x"), "inputs"),
        (_set("surfaces", ["gpu"]), "surfaces"),
        (_set("submodules", {}), "submodules.private/renet"),
        (_sub("private/account", "modified", "no"), "submodules.private/account.modified"),
        (_set("renet", {"built": PTR_R}), "renet"),
    ],
)
def test_a_malformed_envelope_is_refused(
    plant: Callable[[dict[str, Any]], None], needle: str
) -> None:
    receipt = _healthy()
    assert R.envelope_errors(receipt) == []
    plant(receipt)
    errors = R.envelope_errors(receipt)
    assert any(needle in e for e in errors), errors
    with pytest.raises(ValueError, match="invalid receipt envelope"):
        R.envelope(receipt["tier"], receipt["schema"], receipt["status"], receipt)


def test_a_missing_envelope_field_is_named() -> None:
    receipt = _healthy()
    del receipt["inputs"]
    assert "missing field inputs" in R.envelope_errors(receipt)
    assert R.envelope_errors([]) == ["receipt is not an object"]


# ------------------------------------------------------------------ identity on a real checkout


def _fake_renet(built: str, modified: bool | None) -> Callable[[pathlib.Path], dict[str, Any]]:
    return lambda _root: {"built": built, "modified": modified, "sha256": "f" * 64}


def _judge(ident: dict[str, Any], surfaces: tuple[str, ...]) -> R.Verdict | None:
    return R.identity_refusal(R.envelope("live", 1, R.VERIFIED, ident), surfaces)


def test_identity_of_a_clean_checkout_is_refused_by_nothing(world: World) -> None:
    renet_head = _git(world.sub, "rev-parse", "HEAD")
    ident = R.identity(world.root, ("renet", "account"), renet=_fake_renet(renet_head, False))
    receipt = R.envelope("live", 1, R.VERIFIED, ident)
    assert receipt["head"] == _git(world.root, "rev-parse", "HEAD")
    assert receipt["tree"] == _git(world.root, "rev-parse", "HEAD^{tree}")
    assert receipt["dirty"] is False
    assert receipt["surfaces"] == ["account", "renet"]
    assert receipt["submodules"]["private/renet"]["pointer"] == renet_head
    assert receipt["renet"] == {"built": renet_head, "modified": False, "sha256": "f" * 64}
    assert R.identity_refusal(receipt, ("renet", "account")) is None


def test_identity_without_a_renet_surface_carries_no_build(world: World) -> None:
    def boom(_root: pathlib.Path) -> dict[str, Any]:
        msg = "renet_identity must not run for a bench-only surface set"
        raise AssertionError(msg)

    ident = R.identity(world.root, ("account", "proxy"), renet=boom)
    assert ident["renet"] is None


def test_identity_sees_a_dirty_surface_path_and_the_judge_refuses_it(world: World) -> None:
    _write(world.root, "packages/shared/src/new.ts", "export {};\n")
    ident = R.identity(world.root, ("account",))
    assert ident["dirty"] is True
    got = _judge(ident, ("account",))
    assert got is not None
    assert got.code == R.DIRTY_TREE
    # Control: a dirty path outside the given surfaces leaves the identity clean.
    assert R.identity(world.root, ("proxy",))["dirty"] is False


def test_identity_sees_a_moved_submodule_checkout(world: World) -> None:
    world.account_commit({"src/index.ts": "export const moved = 1;\n"})
    got = _judge(R.identity(world.root, ("account",)), ("account",))
    assert got is not None
    assert got.code == R.CHECKOUT_MISMATCH
    world.commit_pointer("bump account")
    assert _judge(R.identity(world.root, ("account",)), ("account",)) is None


def test_identity_sees_a_modified_submodule(world: World) -> None:
    _write(world.acc, "src/index.ts", "export const dirty = 1;\n")
    got = _judge(R.identity(world.root, ("account",)), ("account",))
    assert got is not None
    assert got.code == R.MODIFIED_CHECKOUT


def test_identity_with_a_stale_renet_build_is_refused(world: World) -> None:
    ident = R.identity(world.root, ("renet",), renet=_fake_renet("9" * 40, False))
    got = _judge(ident, ("renet",))
    assert got is not None
    assert got.code == R.BUILD_MISMATCH


def test_identity_inputs_is_the_live_digest_of_its_surfaces(world: World) -> None:
    ident = R.identity(world.root, ("account",))
    assert ident["inputs"] == S.inputs(world.root, ident["tree"], {"account"})
    assert ident["inputs"] != S.inputs(world.root, ident["tree"])
    _write(world.root, "packages/shared/src/x.ts", "export {};\n")
    _commit(world.root, "shared")
    assert R.identity(world.root, ("account",))["inputs"] != ident["inputs"]


def test_identity_refuses_an_unknown_surface(world: World) -> None:
    with pytest.raises(KeyError, match="gpu"):
        R.identity(world.root, ("gpu",))


# ------------------------------------------------------------------ row id and the writer


def test_row_id_round_trips_and_ignores_its_own_id() -> None:
    row: dict[str, Any] = {
        "schema": 1,
        "plan": "agent/plans/PLAN-x.md",
        "box": "LP-bench",
        "check": {"rc": 0},
    }
    rid = R.row_id(row)
    assert rid.startswith("lp-")
    assert len(rid) == len("lp-") + 12
    row["id"] = rid
    assert R.row_id(row) == rid
    assert R.row_id(json.loads(json.dumps(row))) == rid
    body = {k: v for k, v in row.items() if k != "id"}
    expected = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12]
    assert rid == "lp-" + expected


def test_row_id_moves_with_any_field() -> None:
    row = {"schema": 1, "check": {"rc": 0}}
    rid = R.row_id(row)
    assert R.row_id({**row, "check": {"rc": 1}}) != rid
    assert R.row_id({"check": {"rc": 0}, "schema": 1}) == rid


def test_write_atomic_replaces_whole_and_leaves_no_temporary(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "deep" / "receipt.json"
    R.write_atomic(target, "one\n")
    R.write_atomic(target, "two\n")
    assert target.read_text(encoding="utf-8") == "two\n"
    assert sorted(p.name for p in target.parent.iterdir()) == ["receipt.json"]
