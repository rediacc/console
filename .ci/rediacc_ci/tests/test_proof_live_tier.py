"""`rediacc_ci.proof.live_tier`: the check registry (fixed argv only), expansion, the Accept line, the live row and its judge `validate_row`, the kept-log digest and the ledger read.

Each judge is shown failing on a planted defect beside a healthy control. The git and log checks of `validate_row` run over the console-with-two-submodules `World` of test_proof_surfaces; nothing reads the live tree but the committed registry.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.proof import live_tier as LT
from rediacc_ci.proof import receipt as R
from rediacc_ci.proof import surfaces as S
from rediacc_ci.tests.test_proof_surfaces import World
from rediacc_ci.well_known import BENCH_ORIGIN

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

HEAD = "c" * 40
TREE = "d" * 40
PTR_R = "a" * 40
PTR_A = "b" * 40
UUID = "6b822ba9-1111-4222-8333-444455556666"
CLI_ARGV = [["./rdc.sh", "--config", "eu-bench", "subscription", "status"]]


def _raw_live() -> dict[str, Any]:
    return copy.deepcopy(json.loads(S.MAP_PATH.read_text(encoding="utf-8"))["tiers"]["live"])


def _ident(surfaces: list[str], **over: Any) -> dict[str, Any]:
    ident: dict[str, Any] = {
        "tree": TREE,
        "head": HEAD,
        "dirty": False,
        "inputs": "e" * 64,
        "surfaces": surfaces,
        "submodules": {
            "private/renet": {"pointer": PTR_R, "checkout": PTR_R, "modified": False},
            "private/account": {"pointer": PTR_A, "checkout": PTR_A, "modified": False},
        },
        "renet": None,
    }
    ident.update(over)
    return ident


def _cli_row(**over: Any) -> dict[str, Any]:
    """A healthy VERIFIED cli-bench row: the tree deploy, no VM phase."""
    body: dict[str, Any] = {
        "at": "2026-10-28T10:00:00Z",
        "by": "d778be9d",
        "plan": "agent/plans/PLAN-demo.md",
        "box": "0f30f980",
        "target": "bench",
        "region": None,
        "deploy": {
            "surface": "cli",
            "worker": None,
            "version_id": f"cli:{HEAD}",
            "source": "tree",
            "deployed_head": HEAD,
            "confirmed_live": True,
        },
        "check": {
            "id": "cli-bench",
            "args": [],
            "argv": copy.deepcopy(CLI_ARGV),
            "rc": 0,
            "duration_s": 1.5,
            "log_sha256": "a" * 64,
            "tail": ["subscription: active"],
        },
        "ladder": {"vm": None},
    }
    body.update(over)
    return LT.build_row(_ident(["cli"]), R.VERIFIED, **body)


def _account_row() -> dict[str, Any]:
    """A healthy VERIFIED account-smoke row: the bench cache deploy, the account VM phase."""
    argv = [list(r.argv) for r in LT.expand(LT.registry()["account-smoke"], "bench")]
    return LT.build_row(
        _ident(["account"]),
        R.VERIFIED,
        at="2026-10-28T10:00:00Z",
        by="d778be9d",
        plan="agent/plans/PLAN-demo.md",
        box="114951f1",
        target="bench",
        region="eu",
        deploy={
            "surface": "account",
            "worker": "rediacc-account-bench",
            "version_id": UUID,
            "source": "bench-cache",
            "deployed_head": HEAD,
            "confirmed_live": True,
        },
        check={
            "id": "account-smoke",
            "args": [],
            "argv": argv,
            "rc": 0,
            "duration_s": 2.0,
            "log_sha256": "b" * 64,
            "tail": ['{"status":"ok"}'],
        },
        ladder={"vm": "vmc-10280533-5ddf37"},
    )


# ------------------------------------------------------------------ the registry


def test_the_committed_registry_parses_with_fixed_argv_only() -> None:
    checks = LT.registry()
    assert set(checks) == {"account-smoke", "proxy-ready", "cli-bench", "www-smoke", "renet-live"}
    for check in checks.values():
        for step in check.steps:
            assert step.argv[0] not in LT.REFUSED_PROGRAMS
            assert LT._placeholders(step.argv) <= {"origin", "config", "machine"}
    assert checks["renet-live"].per_machine
    assert checks["renet-live"].deploy == LT.RENET_HASH
    assert checks["account-smoke"].deploy == LT.BENCH_CACHE


def test_the_only_www_check_is_unrecorded() -> None:
    """www has no bench deployment (workers/www carries wrangler.toml and wrangler.edge.toml only), so the one check covering it, www-smoke, is `unrecorded`: it meets LP7's coverage rule and writes no VERIFIED row, so it can never close a box until a bench www deploy is recorded."""
    covering = {cid: c for cid, c in LT.registry().items() if "www" in c.surfaces}
    assert set(covering) == {"www-smoke"}
    www = covering["www-smoke"]
    assert www.deploy == LT.UNRECORDED
    assert www.surfaces == {"www"}
    assert tuple(www.targets) == ("bench",)


BROKEN_REGISTRIES: list[tuple[Callable[[dict[str, Any]], object], str]] = [
    (lambda m: m.__setitem__("checks", {}), "checks is empty"),
    (lambda m: m.__setitem__("targets", {}), "targets is empty"),
    (
        lambda m: m["checks"]["cli-bench"]["steps"][0]["argv"].append("{args}"),
        "the only parameters",
    ),
    (
        lambda m: m["checks"]["cli-bench"]["steps"][0].__setitem__("argv", ["bash", "-c", "x"]),
        "shell or a no-op",
    ),
    (
        lambda m: m["checks"]["cli-bench"]["steps"][0].__setitem__("argv", ["true"]),
        "shell or a no-op",
    ),
    (lambda m: m["checks"]["cli-bench"]["steps"][0].__setitem__("argv", []), "non-empty list"),
    (lambda m: m["checks"]["cli-bench"].__setitem__("targets", ["edge"]), "targets"),
    (lambda m: m["checks"]["cli-bench"].__setitem__("surfaces", ["renet"]), "admits none"),
    (lambda m: m["checks"]["cli-bench"].__setitem__("surfaces", ["gpu"]), "known surfaces"),
    (lambda m: m["checks"]["cli-bench"].__setitem__("deploy", "believed"), "deploy"),
    (lambda m: m["checks"]["cli-bench"].__setitem__("steps", []), "steps is empty"),
    (
        lambda m: m["checks"]["cli-bench"]["steps"][0].__setitem__("expect", "anything"),
        "expect",
    ),
    (
        lambda m: m["checks"]["cli-bench"]["steps"][0].__setitem__("timeout_s", 0),
        "timeout_s",
    ),
    (lambda m: m["checks"]["renet-live"]["steps"].pop(), "no renet-hash step"),
    (lambda m: m["checks"]["renet-live"].__setitem__("per_machine", False), "the only parameters"),
    (lambda m: m["targets"]["hostinger"].__setitem__("machines", []), "names no machines"),
    (lambda m: m["targets"]["hostinger"].pop("config"), "needs ['config']"),
    (lambda m: m["targets"]["bench"].pop("origin_wk"), "needs ['origin']"),
    (
        lambda m: m["targets"]["bench"].__setitem__("origin_wk", "WK_NOT_A_KEY"),
        "is not a key of",
    ),
    (
        lambda m: m["targets"]["bench"].__setitem__("origin", "https://bench.example"),
        "is a literal",
    ),
    (
        lambda m: m["checks"]["cli-bench"]["steps"][0].__setitem__("expect", "renet-hash"),
        "has a renet-hash step",
    ),
]


@pytest.mark.parametrize(("mutate", "needle"), BROKEN_REGISTRIES)
def test_a_broken_registry_is_refused(
    mutate: Callable[[dict[str, Any]], object], needle: str
) -> None:
    raw = _raw_live()
    LT.parse_checks(raw)
    mutate(raw)
    with pytest.raises(LT.RegistryError, match=needle.replace("[", r"\[").replace("]", r"\]")):
        LT.parse_checks(raw)


def test_expand_fills_only_registry_values() -> None:
    checks = LT.registry()
    smoke = LT.expand(checks["account-smoke"], "bench")
    assert [r.argv[-1] for r in smoke] == [
        BENCH_ORIGIN + "/account/api/v1/health",
        BENCH_ORIGIN + "/account/api/v1/.well-known/server-info",
    ]
    renet = LT.expand(checks["renet-live"], "hostinger")
    assert [(r.step.id, r.machine) for r in renet] == [
        ("status", "hostinger"),
        ("hash", "hostinger"),
    ]
    assert renet[0].argv == (
        "./rdc.sh",
        "--config",
        "eu-bench",
        "machine",
        "status",
        "hostinger",
        "-o",
        "json",
    )
    assert LT.rebuild_argv(checks["renet-live"], "hostinger") == ("./rdc.sh", "--version")


def test_a_machine_outside_the_registry_is_refused() -> None:
    renet = LT.registry()["renet-live"]
    assert LT.expand(renet, "hostinger", "hostinger")
    with pytest.raises(LT.RegistryError, match=r"not in tiers\.live\.targets\.hostinger\.machines"):
        LT.expand(renet, "hostinger", "prod-1")


def test_a_machine_for_a_check_that_takes_none_is_refused() -> None:
    with pytest.raises(LT.RegistryError, match="does not run per machine"):
        LT.expand(LT.registry()["cli-bench"], "bench", "hostinger")


def test_a_check_on_a_target_it_does_not_name_is_refused() -> None:
    with pytest.raises(LT.RegistryError, match="not 'hostinger'"):
        LT.expand(LT.registry()["account-smoke"], "hostinger")


@pytest.mark.parametrize("args", [["--force"], ["machine="], ["machine=a", "machine=b"], ["x=y"]])
def test_free_arguments_are_refused(args: list[str]) -> None:
    assert LT.machine_of_args(["machine=hostinger"]) == "hostinger"
    assert LT.machine_of_args([]) is None
    with pytest.raises(LT.RegistryError, match="not a registry parameter"):
        LT.machine_of_args(args)


def test_row_surfaces_keep_what_the_plan_touched_the_check_covers_and_the_target_admits() -> None:
    checks = LT.registry()
    assert LT.row_surfaces({"cli", "renet", "account"}, checks["renet-live"], "hostinger") == [
        "cli",
        "renet",
    ]
    assert LT.row_surfaces({"account"}, checks["renet-live"], "hostinger") == []
    assert LT.judge_surfaces(["cli"], checks["renet-live"]) == {"cli", "renet"}
    assert LT.judge_surfaces(["cli"], checks["cli-bench"]) == {"cli"}


# ------------------------------------------------------------------ the Accept line

PLAN = """# PLAN: demo

## Tasks

- [ ] LP-bench [live] the cli on bench
  - Accept: `live-proof bench cli-bench`
- [ ] LP-hostinger [live] renet on hostinger
  - some note
  - Accept: live-proof hostinger renet-live machine=hostinger
- [ ] LP-bench [live] no accept line
- [ ] next box
  - Accept: live-proof bench account-smoke
"""


def test_accept_of_reads_the_sub_line_of_its_own_box_only() -> None:
    lines = PLAN.splitlines()
    first = lines.index("- [ ] LP-bench [live] the cli on bench")
    second = lines.index("- [ ] LP-hostinger [live] renet on hostinger")
    third = lines.index("- [ ] LP-bench [live] no accept line")
    assert LT.accept_of(PLAN, first) == LT.Accept("bench", "cli-bench", ())
    assert LT.accept_of(PLAN, second) == LT.Accept(
        "hostinger", "renet-live", ("machine=hostinger",)
    )
    assert LT.accept_of(PLAN, third) is None


# ------------------------------------------------------------------ the row and its judge


def test_a_healthy_row_is_valid_and_its_id_round_trips() -> None:
    row = _cli_row()
    assert LT.validate_row(row) == []
    again = json.loads(json.dumps(row, separators=(",", ":")))
    assert again["id"] == R.row_id(again) == row["id"]
    assert row["id"].startswith("lp-")
    assert len(row["id"]) == 15
    assert LT.validate_row(_account_row()) == []


def _reid(row: dict[str, Any]) -> None:
    row.pop("id")
    row["id"] = R.row_id(row)


def _plant(path: str, value: object) -> Callable[[dict[str, Any]], None]:
    keys = path.split(".")

    def apply(row: dict[str, Any]) -> None:
        node = row
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
        _reid(row)

    return apply


def _no_reid(row: dict[str, Any]) -> None:
    row["by"] = "someone-else"


ROW_PLANTS: list[tuple[str, Callable[[dict[str, Any]], None], str]] = [
    ("free argv", _plant("check.argv", [["./rdc.sh", "repo", "delete"]]), "registry's argv"),
    ("argv of another target", _plant("target", "hostinger"), "not 'hostinger'"),
    ("free argument", _plant("check.args", ["--force"]), "not a registry parameter"),
    ("unknown check", _plant("check.id", "true"), "not in the registry"),
    ("failed rc", _plant("check.rc", 1), "check.rc is 1"),
    ("FAILED status", _plant("status", R.FAILED), "VERIFIED rows only"),
    ("dirty tree", _plant("dirty", True), "dirty-tree"),
    ("id mismatch", _no_reid, "id does not hash"),
    ("malformed version", _plant("deploy.version_id", "cli:HEAD"), "malformed"),
    ("deploy of another head", _plant("deploy.deployed_head", "9" * 40), "deployed_head"),
    ("unconfirmed deploy", _plant("deploy.confirmed_live", False), "confirmed_live"),
    ("schema", _plant("schema", 2), "schema 2"),
    ("tier", _plant("tier", "vm"), "tier is 'vm'"),
    ("secret in tail", _plant("check.tail", ["token ghp_" + "A" * 36]), "secret shape"),
    ("long tail", _plant("check.tail", ["x"] * 21), "at most 20"),
    ("log digest shape", _plant("check.log_sha256", "nope"), "log_sha256"),
    ("uncovered surface", _plant("surfaces", ["proxy"]), "does not cover surface proxy"),
    ("missing ladder", _plant("ladder", None), "ladder is not an object"),
    ("region", _plant("region", "mars"), "region"),
]


@pytest.mark.parametrize(("name", "plant", "needle"), ROW_PLANTS, ids=[p[0] for p in ROW_PLANTS])
def test_each_row_defect_is_refused(
    name: str, plant: Callable[[dict[str, Any]], None], needle: str
) -> None:
    row = _cli_row()
    assert LT.validate_row(row) == [], "the control must pass before the plant"
    plant(row)
    problems = LT.validate_row(row)
    assert any(needle in p for p in problems), (name, problems)


def test_a_vm_phase_surface_needs_its_ladder_run() -> None:
    row = _account_row()
    assert LT.validate_row(row) == []
    _plant("ladder", {"vm": None})(row)
    assert any("ladder.vm" in p for p in LT.validate_row(row))


def test_an_account_row_on_a_moved_account_checkout_is_refused() -> None:
    row = _account_row()
    row["submodules"]["private/account"]["checkout"] = "9" * 40
    _reid(row)
    assert any(p.startswith("checkout-mismatch") for p in LT.validate_row(row))


def test_a_renet_hash_row_judges_the_renet_build_even_for_a_cli_only_plan() -> None:
    check = LT.registry()["renet-live"]
    argv = [list(r.argv) for r in LT.expand(check, "hostinger")]
    renet = {"built": PTR_R, "modified": False, "sha256": "f" * 64}
    row = LT.build_row(
        _ident(["cli"], renet=renet),
        R.VERIFIED,
        at="2026-10-28T10:00:00Z",
        by="d778be9d",
        plan="agent/plans/PLAN-demo.md",
        box="2f44fc06",
        target="hostinger",
        region=None,
        deploy={
            "surface": "renet",
            "worker": None,
            "version_id": f"renet:{PTR_R}@sha256:{'f' * 64}",
            "source": "rdc:eu-bench",
            "deployed_head": HEAD,
            "confirmed_live": True,
        },
        check={
            "id": "renet-live",
            "args": [],
            "argv": argv,
            "rc": 0,
            "duration_s": 9.0,
            "log_sha256": "c" * 64,
            "tail": ["f" * 64],
        },
        ladder={"vm": None},
    )
    assert LT.validate_row(row) == []
    _plant("renet.modified", True)(row)
    assert any(p.startswith("modified-build") for p in LT.validate_row(row))


def test_an_unrecorded_deploy_never_validates() -> None:
    row = _cli_row()
    row["check"]["id"] = "proxy-ready"
    row["check"]["argv"] = [list(r.argv) for r in LT.expand(LT.registry()["proxy-ready"], "bench")]
    row["surfaces"] = ["proxy"]
    _reid(row)
    assert any("identifies no deploy" in p for p in LT.validate_row(row))


# ------------------------------------------------------------------ the git checks and the kept log


@pytest.fixture
def world(tmp_path: pathlib.Path) -> World:
    return World(tmp_path / "console")


def _real_row(world: World) -> dict[str, Any]:
    ident = R.identity(world.root, ["cli"])
    head = ident["head"]
    return LT.build_row(
        ident,
        R.VERIFIED,
        at="2026-10-28T10:00:00Z",
        by="d778be9d",
        plan="agent/plans/PLAN-demo.md",
        box="0f30f980",
        target="bench",
        region=None,
        deploy={
            "surface": "cli",
            "worker": None,
            "version_id": f"cli:{head}",
            "source": "tree",
            "deployed_head": head,
            "confirmed_live": True,
        },
        check={
            "id": "cli-bench",
            "args": [],
            "argv": copy.deepcopy(CLI_ARGV),
            "rc": 0,
            "duration_s": 1.0,
            "log_sha256": hashlib.sha256(b"subscription: active\n").hexdigest(),
            "tail": ["subscription: active"],
        },
        ladder={"vm": None},
    )


def test_a_row_whose_kept_log_differs_is_refused(world: World) -> None:
    row = _real_row(world)
    assert LT.validate_row(row, root=world.root) == [], "an absent log is not judged"
    path = LT.log_path(world.root, row["id"])
    path.parent.mkdir(parents=True)
    path.write_text("subscription: active\n", encoding="utf-8")
    assert LT.validate_row(row, root=world.root) == []
    path.write_text("subscription: active (edited)\n", encoding="utf-8")
    problems = LT.validate_row(row, root=world.root)
    assert any("does not match check.log_sha256" in p for p in problems), problems


def test_a_row_whose_inputs_or_head_do_not_resolve_is_refused(world: World) -> None:
    row = _real_row(world)
    assert LT.validate_row(row, root=world.root) == []
    forged = copy.deepcopy(row)
    _plant("inputs", "0" * 64)(forged)
    assert any("inputs is not the digest" in p for p in LT.validate_row(forged, root=world.root))
    unknown = copy.deepcopy(row)
    unknown["head"] = "1" * 40
    unknown["deploy"]["deployed_head"] = "1" * 40
    unknown["deploy"]["version_id"] = "cli:" + "1" * 40
    _reid(unknown)
    assert any("does not resolve" in p for p in LT.validate_row(unknown, root=world.root))


# ------------------------------------------------------------------ the ledger and the match


def test_read_ledger_keeps_unparsable_lines_as_errors(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "live-proof.jsonl"
    assert LT.read_ledger(path) == []
    path.write_text('{"a": 1}\n\nnot json\n[1]\n', encoding="utf-8")
    got = LT.read_ledger(path)
    assert [(g.lineno, g.row is not None) for g in got] == [(1, True), (3, False), (4, False)]
    assert got[1].error.startswith("not JSON")


def test_matches_needs_every_accept_field() -> None:
    row = _cli_row()
    accept = LT.Accept("bench", "cli-bench", ())
    assert LT.matches(row, "agent/plans/PLAN-demo.md", "0f30f980", "bench", accept)
    assert not LT.matches(
        row,
        "agent/plans/PLAN-demo.md",
        "0f30f980",
        "bench",
        LT.Accept("bench", "account-smoke", ()),
    )
    assert not LT.matches(
        row,
        "agent/plans/PLAN-demo.md",
        "0f30f980",
        "bench",
        LT.Accept("bench", "cli-bench", ("machine=x",)),
    )
    assert not LT.matches(row, "agent/plans/PLAN-other.md", "0f30f980", "bench", accept)
    failed = copy.deepcopy(row)
    failed["check"]["rc"] = 2
    assert not LT.matches(failed, "agent/plans/PLAN-demo.md", "0f30f980", "bench", accept)


def test_tail_of_replaces_email_addresses() -> None:
    log = 'ok\n  "author_email": "someone@example.com",\nlast line\n'
    tail = LT.tail_of(log)
    assert not any("@example.com" in ln for ln in tail)
    assert '  "author_email": "<email>",' in tail
