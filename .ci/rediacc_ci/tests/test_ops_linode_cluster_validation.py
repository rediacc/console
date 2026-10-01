"""`rediacc_ci.ops.linode_cluster_validation` against its bash twin `scripts/ops/linode-cluster-validation.sh`, with fake `curl` (the Linode API), `terraform`, `npx` and `rdc.sh` on the sealed PATH of `ops_cf_harness`. Nothing billable is reachable.

Differentials compare stdout, stderr (ANSI stripped) and the exit code. A `test_delta_*` case pins one Rule T difference, asserting the bash behaviour first as the control.
"""

from __future__ import annotations

import json
import shutil
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import ops_cf_harness as h

if typing.TYPE_CHECKING:
    import pathlib

SUBJECT = "scripts/ops/linode-cluster-validation.sh"
MODULE = "rediacc_ci.ops.linode_cluster_validation"

FAKE_TERRAFORM = """#!{py}
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({{"tool": "terraform", "argv": sys.argv[1:]}}) + "\\n")
if sys.argv[1:3] == ["state", "list"]:
    sys.stdout.write(os.environ.get("FAKE_TF_STATE", ""))
sys.exit(0)
"""

FAKE_RDC = """#!{py}
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({{"tool": "rdc", "argv": sys.argv[1:]}}) + "\\n")
if sys.argv[1:4] == ["config", "cluster", "add"]:
    sys.stderr.write(os.environ.get("FAKE_ADD_ERR", ""))
    sys.exit(int(os.environ.get("FAKE_ADD_RC", "0")))
sys.exit(0)
"""


def listing(label_prefix: str | None = None, pages: int = 1) -> dict:
    data = (
        [{"id": 1, "label": label_prefix + "-1", "status": "running", "region": "de", "type": "g6"}]
        if label_prefix
        else []
    )
    return {"data": data, "pages": pages}


def routes(instances: dict | None = None, extra: tuple[dict, ...] = ()) -> list[dict]:
    return [
        *extra,
        {"method": "GET", "match": "/linode/instances", "body": instances or listing()},
        {"method": "GET", "match": "/volumes", "body": {"data": [], "pages": 1}},
        {"method": "GET", "match": "/networking/vlans", "body": {"data": [], "pages": 1}},
    ]


@pytest.fixture
def world(tmp_path: pathlib.Path) -> h.World:
    w = h.World(tmp_path)
    py = sys.executable
    h.World._write_exec(w.bin / "terraform", FAKE_TERRAFORM.format(py=py))
    for tool in ("mktemp", "rm", "wc", "tr", "ls", "sort"):
        real = shutil.which(tool)
        if real and not (w.bin / tool).exists():
            (w.bin / tool).symlink_to(real)
    src = paths.repo_root()
    dest = w.root / SUBJECT
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / SUBJECT, dest)
    h.World._write_exec(w.root / "rdc.sh", FAKE_RDC.format(py=py))
    cfg = w.root / ".config/rediacc"
    cfg.mkdir(parents=True)
    (cfg / "rediacc.json").write_text(
        json.dumps({"resources": {"cloudProviders": {"my-linode": {"apiToken": "linode-token"}}}})
    )
    (w.root / ".ssh").mkdir()
    (w.root / ".ssh/id_ed25519.pub").write_text("ssh-ed25519 AAAA test\n")
    (w.root / "tmp").mkdir()
    w.set_routes(routes())
    return w


def _both(world: h.World, args: list[str], **env: str):
    e = world.env(TMPDIR=str(world.root / "tmp"), **env)
    b = world.bash(SUBJECT, args, e)
    calls_b = [c for c in world.calls() if c["tool"] != "curl" or True]
    world.reset_log()
    p = world.port(MODULE, args, e)
    return b, p, calls_b, world.calls()


def _same(b: tuple, p: tuple) -> None:
    assert b[0] == p[0]
    assert h.strip(b[1]) == h.strip(p[1])
    assert h.strip(b[2]) == h.strip(p[2])


def _urls(calls: list[dict]) -> list[str]:
    return [c["url"] for c in calls if c["tool"] == "curl"]


def test_preflight_clean_matches_bash(world: h.World) -> None:
    b, p, calls_b, calls_p = _both(world, ["preflight"])
    _same(b, p)
    assert p[0] == 0
    assert "Preflight CLEAN" in p[1]
    assert _urls(calls_b) == _urls(calls_p)
    assert all(
        c["headers"] == ["Authorization: Bearer linode-token"]
        for c in calls_p
        if c["tool"] == "curl"
    )


def test_preflight_with_live_instances_exits_2_in_both(world: h.World) -> None:
    world.set_routes(routes(listing("lval")))
    b, p, _, _ = _both(world, ["preflight"])
    _same(b, p)
    assert p[0] == 2
    assert "LIVE billable resources exist" in p[2]
    assert "INSTANCE 1 lval-1" in p[2]


def test_verify_survivors_exit_4_and_clean_exit_0_match_bash(world: h.World) -> None:
    world.set_routes(routes(listing("lval")))
    b, p, _, _ = _both(world, ["verify"])
    _same(b, p)
    assert p[0] == 4
    assert "ZERO-SURVIVOR CHECK FAILED" in p[2]
    world.set_routes(routes())
    b, p, _, _ = _both(world, ["verify"])
    _same(b, p)
    assert p[0] == 0


def test_verify_counts_tofu_state_like_bash(world: h.World) -> None:
    state = world.root / ".config/rediacc/tofu/clusters/lval"
    state.mkdir(parents=True)
    (state / "terraform.tfstate").write_text("{}")
    b, p, _, _ = _both(world, ["verify"], FAKE_TF_STATE="linode_instance.a\nlinode_instance.b\n")
    _same(b, p)
    assert p[0] == 4
    assert "tofu state still lists 2 resource(s)" in p[2]


def test_billable_phases_need_yes_in_both(world: h.World) -> None:
    for phase in ("provision", "destroy", "idempotency"):
        b, p, _, calls_p = _both(world, [phase])
        _same(b, p)
        assert p[0] == 3
        assert "needs --yes" in p[2]
        assert not [c for c in calls_p if c["tool"] == "rdc"]


def test_provision_calls_match_bash(world: h.World) -> None:
    b, p, calls_b, calls_p = _both(world, ["provision", "--yes"], CLUSTER_POOLS="a:b:1:c,d:e:2")
    _same(b, p)
    rdc_b = [c["argv"] for c in calls_b if c["tool"] == "rdc"]
    rdc_p = [c["argv"] for c in calls_p if c["tool"] == "rdc"]
    assert rdc_b == rdc_p
    assert rdc_p[0][:6] == ["config", "cluster", "add", "--name", "lval", "--provider"]
    assert rdc_p[0].count("--pool") == 2
    assert rdc_p[1] == ["cluster", "create", "--name", "lval"]


def test_destroy_removes_the_workdir_in_both(world: h.World) -> None:
    state = world.root / ".config/rediacc/tofu/clusters/lval"
    state.mkdir(parents=True)
    b, p, calls_b, calls_p = _both(world, ["destroy", "--yes"])
    assert b[0] == p[0] == 0
    assert [c["argv"] for c in calls_b if c["tool"] == "rdc"] == [
        c["argv"] for c in calls_p if c["tool"] == "rdc"
    ]
    assert not state.exists()


def test_arguments_default_phases_and_missing_token_match_bash(world: h.World) -> None:
    b, p, _, _ = _both(world, ["--bogus"])
    _same(b, p)
    assert p[0] == 1
    b, p, _, _ = _both(world, ["preflight"], PROVIDER="nope")
    _same(b, p)
    assert p[0] == 1
    assert "No apiToken for provider 'nope'" in p[2]


def test_delta_a_quote_in_the_provider_is_data_not_code(world: h.World) -> None:
    b, p, _, _ = _both(world, ["preflight"], PROVIDER="a'b")
    assert b[0] != 0
    assert "SyntaxError" in b[2]
    assert p[0] == 1
    assert "No apiToken for provider 'a'b'" in p[2]


def test_delta_a_second_page_of_survivors_is_read(world: h.World) -> None:
    page1 = listing(None, pages=2)
    page2 = listing("lval", pages=2)
    extra = ({"method": "GET", "match": "/linode/instances?page=2", "body": page2},)
    world.set_routes(routes(page1, extra))
    b, p, _, calls_p = _both(world, ["verify"])
    assert b[0] == 0  # the control: the survivor on page 2 is invisible to the bash
    assert p[0] == 4
    assert "instances=1" in p[2]
    assert any(u.endswith("/linode/instances?page=2") for u in _urls(calls_p))


def test_delta_a_failed_listing_is_named(world: h.World) -> None:
    world.set_routes(routes(None, ({"method": "GET", "match": "/volumes", "rc": 22},)))
    b, p, _, _ = _both(world, ["verify"])
    assert b[0] != 0
    assert "the Linode API listing" not in h.strip(b[2])
    assert p[0] == 1
    assert "the Linode API listing /volumes failed (curl exit 22)" in p[2]


def test_delta_cluster_add_is_not_swallowed_unless_the_cluster_exists(world: h.World) -> None:
    _b, p, calls_b, calls_p = _both(
        world, ["provision", "--yes"], FAKE_ADD_RC="1", FAKE_ADD_ERR="unknown provider"
    )
    assert ["cluster", "create", "--name", "lval"] in [
        c["argv"] for c in calls_b if c["tool"] == "rdc"
    ]  # the control
    assert p[0] == 1
    assert "rdc config cluster add failed" in p[2]
    assert not any(c["argv"][:1] == ["cluster"] for c in calls_p if c["tool"] == "rdc")
    _b, p, _, calls_p = _both(
        world, ["provision", "--yes"], FAKE_ADD_RC="1", FAKE_ADD_ERR="cluster lval already exists"
    )
    assert p[0] == 0
    assert any(c["argv"][:1] == ["cluster"] for c in calls_p if c["tool"] == "rdc")


def test_delta_the_plan_tempdir_is_removed_on_failure(world: h.World) -> None:
    (world.bin / "terraform").unlink()
    b, p, _, _ = _both(world, ["plan"])
    left_b = list((world.root / "tmp").iterdir())
    assert b[0] == 127
    assert left_b
    for entry in left_b:
        shutil.rmtree(entry)
    world.reset_log()
    p = world.port(MODULE, ["plan"], world.env(TMPDIR=str(world.root / "tmp")))
    assert p[0] == 127
    assert "terraform: command not found" in p[2]
    assert list((world.root / "tmp").iterdir()) == []


def test_plan_generates_with_a_json_spec_and_runs_terraform(world: h.World) -> None:
    p = world.port(MODULE, ["plan"], world.env(TMPDIR=str(world.root / "tmp"), CLUSTER_NAME="it's"))
    assert p[0] == 0, p[2]
    calls = world.calls()
    npx = next(c for c in calls if c["tool"] == "npx")
    assert npx["argv"][0] == "tsx"
    assert npx["argv"][1].endswith("gen.mts")
    assert [c["argv"][:1] for c in calls if c["tool"] == "terraform"] == [["init"], ["plan"]]
