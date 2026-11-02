"""vm:check over the renet areas: the `--dry-run` plan, the per-leg judge, and a whole run on the fake host.

The dry run is driven twice: through `--paths` (no git), and through `--changed` against a real fixture repository whose `private/renet` is a nested repository with its gitlink recorded by hand, so the change is read by the same `changed_paths` the real run uses. The whole runs reuse the fake host of test_drills_vm_check.py and set the touched areas directly, because that host's root is no git repository (`_evaluate_areas` says so and reads none), which keeps every existing scenario there unchanged.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.drills import vm_check
from rediacc_ci.proof import surfaces as S
from rediacc_ci.proof import vm_tier as receipt_mod
from rediacc_ci.tests import test_drills_vm_check as base

if TYPE_CHECKING:
    import pathlib

ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
    "HOME": "/nonexistent",
}


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=ENV
    ).stdout.strip()


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _tmp_workdirs(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The drill work directory of a whole run lands under `tmp_path`, as in test_drills_vm_check.py, never in the shared /tmp."""
    work = tmp_path / "tmp"
    work.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(work))
    monkeypatch.delenv("DRILL_KEEP_WORK", raising=False)


def dry(argv: list[str], root: pathlib.Path | None = None) -> tuple[int, str]:
    out = io.StringIO()
    rc = vm_check.main([*argv, "--dry-run"], root=root, out=out, environ={})
    return rc, out.getvalue()


# ----------------------------------------------------------------------------- --dry-run --paths


def test_a_license_path_plans_the_license_leg_and_no_ceph_leg() -> None:
    rc, out = dry(["--paths", "private/renet/pkg/license/store.go"])
    assert rc == 0, out
    assert "leg license-drill RUNS steps A0, A2.3" in out
    assert "area steps run beyond the required phases: A0, A2.3" in out
    assert "phase renet required" in out
    assert "phase account not required" in out
    assert "area ceph" not in out
    assert "ceph-08-09-12c" not in out
    assert "best verdict: VERIFIED" in out


def test_a_kube_path_plans_the_kube_suites_and_runs_their_legs() -> None:
    rc, out = dry(["--paths", "private/renet/pkg/kube/distro/k3s.go"])
    assert rc == 0, out
    for suite in (
        "packages/e2e-tests/tests/kube/15-k8s-repo.test.ts",
        "packages/e2e-tests/tests/kube/16-datastore-cluster.test.ts",
        "packages/e2e-tests/tests/kube/17-multinode-cluster.test.ts",
    ):
        assert "suite %s" % suite in out
    assert "--config playwright.k8s.config.ts --fail-on-skip" in out
    assert "leg k8s-15 RUNS after the base battery on its own fleet" in out
    assert "leg k8s-multinode-17-24 RUNS after the base battery on its own fleet" in out
    assert "best verdict: VERIFIED" in out
    assert "area license" not in out
    assert "ci jobs: e2e_k8s, e2e_k8s_ceph, e2e_k8s_multinode" in out


def test_a_renet_path_in_no_area_plans_the_base_battery_alone() -> None:
    rc, out = dry(["--paths", "private/renet/pkg/hub/hub.go"])
    assert rc == 0, out
    assert "1 renet path(s) in no area (base battery alone): private/renet/pkg/hub/hub.go" in out
    assert "areas: none; best verdict: VERIFIED" in out


def test_a_test_only_renet_path_plans_nothing() -> None:
    rc, out = dry(["--paths", "private/renet/pkg/license/store_test.go"])
    assert rc == 0, out
    assert "a real run would verify nothing and write no receipt" in out
    assert "area " not in out


def test_the_backup_leg_is_judged_by_its_receipt_and_says_how_to_produce_it() -> None:
    rc, out = dry(["--paths", "private/renet/pkg/chunkstore/store.go"])
    assert rc == 0, out
    assert "leg backup-drills JUDGES the backup-check receipt" in out
    assert "./run.sh drill backup && ./run.sh drill backup-onprem" in out


def test_a_dry_run_touches_nothing(tmp_path: pathlib.Path) -> None:
    """No receipt folder, no lock, no work dir: the plan is printed and the process returns."""
    root = tmp_path / "console"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    rc, out = dry(["--paths", "private/renet/pkg/license/store.go"], root=root)
    assert rc == 0, out
    assert not (root / receipt_mod.CACHE_DIR).exists()
    assert sorted(p.name for p in root.iterdir()) == [".git"]


def test_a_dry_run_on_a_root_that_is_no_repository_refuses(tmp_path: pathlib.Path) -> None:
    rc, out = dry(["--changed"], root=tmp_path)
    assert rc == 2
    assert "is not a git repository root" in out


@pytest.mark.parametrize(
    "argv",
    [
        ["--paths", "x"],
        ["--dry-run", "--only", "V1.2"],
        ["--dry-run", "--paths", ","],
        ["--changed", "--dry-run", "--paths", "x", "--base", "v1"],
    ],
)
def test_the_dry_run_flags_refuse_their_misuses(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        vm_check.parse_args(argv, {})


def test_paths_split_on_commas_and_repeat() -> None:
    opts = vm_check.parse_args(["--dry-run", "--paths", "a, b", "--paths", "c"], {})
    assert opts.paths == ("a", "b", "c")
    assert opts.dry_run


# ----------------------------------------------------------------------------- --changed --dry-run against a real repository


class Console:
    """A console repository whose private/renet is a nested repository, its gitlink recorded by hand, with origin/main at the first commit."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        root.mkdir()
        _git(root, "init", "-q", "-b", "main")
        _write(root, "README.md", "x\n")
        self.sub = root / "private" / "renet"
        self.sub.mkdir(parents=True)
        _git(self.sub, "init", "-q", "-b", "main")
        for rel in ("pkg/license/store.go", "pkg/rbd/rbd.go", "pkg/kube/k.go", "pkg/hub/hub.go"):
            _write(self.sub, rel, "package x\n")
        _git(self.sub, "add", "-A")
        _git(self.sub, "commit", "-q", "-m", "r0")
        sha = _git(self.sub, "rev-parse", "HEAD")
        _git(root, "update-index", "--add", "--cacheinfo", f"160000,{sha},private/renet")
        _git(root, "add", "README.md")
        _git(root, "commit", "-q", "-m", "c0")
        _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")

    def edit(self, rel: str) -> None:
        _write(self.sub, rel, "package x\n// changed\n")


@pytest.fixture
def console(tmp_path: pathlib.Path) -> Console:
    return Console(tmp_path / "console")


def test_changed_dry_run_on_a_license_diff_lists_the_license_leg_not_the_ceph_leg(
    console: Console,
) -> None:
    console.edit("pkg/license/store.go")
    rc, out = dry(["--changed"], root=console.root)
    assert rc == 0, out
    assert "private/renet/pkg/license/store.go" in out
    assert "leg license-drill RUNS steps A0, A2.3" in out
    assert "ceph" not in out


def test_changed_dry_run_on_a_kube_diff_lists_the_kube_suites(console: Console) -> None:
    console.edit("pkg/kube/k.go")
    rc, out = dry(["--changed"], root=console.root)
    assert rc == 0, out
    assert "suite packages/e2e-tests/tests/kube/15-k8s-repo.test.ts" in out
    assert "leg k8s-multinode-17-24 RUNS after the base battery" in out
    assert "area license" not in out


def test_changed_dry_run_with_no_renet_diff_is_the_no_op(console: Console) -> None:
    _write(console.root, "docs/x.md", "x\n")
    rc, out = dry(["--changed"], root=console.root)
    assert rc == 0, out
    assert "a real run would verify nothing" in out


# ----------------------------------------------------------------------------- the per-leg judge


def _rows(**verdicts: str) -> list[dict[str, Any]]:
    return [{"id": step.replace("_", "."), "verdict": v} for step, v in verdicts.items()]


LICENSE = S.MAP.areas["license"].legs[0]
K8S = S.MAP.areas["kube"].legs[0]
BACKUP = S.MAP.areas["backup"].legs[0]


def _no_receipt(_name: str) -> tuple[bool, str]:
    return False, "no receipt"


def test_a_vmcheck_leg_is_ok_only_when_every_step_ran_ok() -> None:
    assert vm_check.judge_leg(LICENSE, _rows(A0="ok", A2_3="ok"), _no_receipt, None)[0] == "ok"


def test_a_vmcheck_leg_missing_a_step_did_not_run() -> None:
    status, detail = vm_check.judge_leg(LICENSE, _rows(A0="ok"), _no_receipt, None)
    assert status == "not-run"
    assert "A2.3" in detail


def test_a_vmcheck_leg_with_a_failed_step_failed() -> None:
    assert (
        vm_check.judge_leg(LICENSE, _rows(A0="ok", A2_3="FAIL"), _no_receipt, None)[0] == "failed"
    )


def test_a_receipt_leg_follows_its_receipt() -> None:
    assert vm_check.judge_leg(BACKUP, [], lambda _n: (True, "admitted"), None) == ("ok", "admitted")
    status, detail = vm_check.judge_leg(BACKUP, [], _no_receipt, None)
    assert status == "not-verified"
    assert "./run.sh drill backup" in detail


def test_an_external_leg_with_no_row_did_not_run_and_names_its_fleet() -> None:
    status, detail = vm_check.judge_leg(K8S, [], lambda _n: (True, "x"), None)
    assert status == "not-run"
    assert "no X.k8s-15 row" in detail
    assert "fleet worker (192.168.111.1 192.168.111.11) unknown;" in detail
    assert "playwright.k8s.config.ts" in detail


@pytest.mark.parametrize(
    ("row", "status"),
    [
        ({"id": "X.k8s-15", "verdict": "ok", "desc": "3 passed"}, "ok"),
        ({"id": "X.k8s-15", "verdict": "FAIL", "desc": "1 failed"}, "failed"),
        (
            {"id": "X.k8s-15", "verdict": "FAIL", "desc": "fleet", "outcome": "not-verified"},
            "not-verified",
        ),
    ],
)
def test_an_external_leg_follows_its_row(row: dict[str, Any], status: str) -> None:
    got, detail = vm_check.judge_leg(K8S, [row], _no_receipt, None)
    assert got == status
    assert row["desc"] in detail
    # A leg that is not ok still names the commands that reproduce it.
    assert ("playwright.k8s.config.ts" in detail) == (status != "ok")


# ----------------------------------------------------------------------------- whole runs on the fake host


def run_with_areas(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    areas: set[str],
    *,
    account_required: bool,
    receipt: tuple[bool, str] = (False, "no backup receipt exists"),
) -> tuple[int, str, dict[str, Any], base.World]:
    """A run whose trigger is set by hand: the renet side required, the account side as given, and `areas` touched."""

    def trigger(self: vm_check.VmCheck) -> bool:
        self.areas = frozenset(areas)
        self.phases[vm_check.SIDE_ACCOUNT]["required"] = account_required
        self.trigger_info = {
            "base": "origin/main",
            "via": "test",
            "hits": ["private/renet/x.go"],
            "sides": ["renet", "account"] if account_required else ["renet"],
            "areas": [a for a in S.AREAS if a in areas],
        }
        return True

    monkeypatch.setattr(vm_check.VmCheck, "_evaluate_trigger", trigger)
    world = base.make_world(tmp_path)
    out = io.StringIO()
    rc = vm_check.main(
        ["--changed", "--keep-work", "--wait", "0"],
        root=world.root,
        host=world,
        account=base.FakeAccount(),
        lock=vm_check.Lock(tmp_path / "vm-check.lock"),
        out=out,
        environ={
            "HOME": str(tmp_path / "home"),
            "PATH": os.environ.get("PATH", ""),
            "VM_NET_BASE": base.NET,
        },
        inputs_fn=lambda _root: base.DIGEST,
        account_modified_fn=lambda _root: False,
        dirty_fn=lambda _root, _surfaces: False,
        renet_modified_fn=lambda _root: False,
        account_digest_fn=lambda _root: base.ADIGEST,
        u1_fn=base.stub_u1,
        extra_fns=base.STUB_EXTRA,
        receipt_fn=lambda _root, _tree: receipt,
    )
    latest = world.root / receipt_mod.CACHE_DIR / receipt_mod.LATEST
    doc = json.loads(latest.read_text()) if latest.exists() else {}
    if doc:
        assert receipt_mod.validate(doc) == [], receipt_mod.validate(doc)
    return rc, out.getvalue(), doc, world


def _step_ids(doc: dict[str, Any]) -> set[str]:
    return {s["id"] for s in doc["steps"]}


def test_a_license_change_runs_the_license_drill_without_the_account_phase(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rc, out, doc, _world = run_with_areas(
        tmp_path, monkeypatch, {"license"}, account_required=False
    )
    assert rc == vm_check.EXIT_VERIFIED, out
    ids = _step_ids(doc)
    assert {"A0", "A2.3", "P5", "V1.1"} <= ids
    assert not ids & {"A1.1", "A1.2", "A1.3", "A1.4", "A2.1", "A2.2"}, ids
    assert doc["trigger"]["areas"] == ["license"]
    assert doc["areas"]["license"]["legs"][0]["status"] == "ok"
    assert "area license/license-drill ok" in out


def test_a_kube_change_runs_its_legs_on_their_fleets(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The kube legs run after the base battery: k8s-15 on the worker fleet already up, the two k3s-ceph legs after one `ops up` with the recipe's topology, which leaves the VMs it added running for the next leg."""
    rc, out, doc, world = run_with_areas(tmp_path, monkeypatch, {"kube"}, account_required=False)
    assert rc == vm_check.EXIT_VERIFIED, out
    legs = {leg["id"]: leg for leg in doc["areas"]["kube"]["legs"]}
    assert {leg["status"] for leg in legs.values()} == {"ok"}, legs
    ups = [(c, e) for c, e in zip(world.calls, world.envs, strict=True) if c[1:3] == ["ops", "up"]]
    assert len(ups) == 1, ups
    assert ups[0][1]["VM_CEPH_NODES"] == "21 22 23"
    assert "--config playwright.k8s.config.ts" in world.bash_cmds[1]
    assert any("CLUSTER_LICENSING_SUITE=1" in c for c in world.bash_cmds)
    assert doc["phases"]["renet"]["ran"] is True
    assert "A2.3" not in _step_ids(doc)


def test_a_backup_change_follows_the_backup_receipt(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rc, out, doc, _world = run_with_areas(tmp_path, monkeypatch, {"backup"}, account_required=False)
    assert rc == vm_check.EXIT_NOT_VERIFIED, out
    assert "backup/backup-drills" in doc["reason"]["detail"]


def test_a_backup_change_with_an_admitting_receipt_is_verified(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rc, out, doc, _world = run_with_areas(
        tmp_path, monkeypatch, {"backup"}, account_required=False, receipt=(True, "covered")
    )
    assert rc == vm_check.EXIT_VERIFIED, out
    assert doc["areas"]["backup"]["legs"][0] == {
        "id": "backup-drills",
        "kind": "receipt",
        "status": "ok",
        "detail": "covered",
    }


def test_no_area_keeps_the_base_battery_verdict(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rc, out, doc, _world = run_with_areas(tmp_path, monkeypatch, set(), account_required=False)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert doc["areas"] == {}
    assert "A2.3" not in _step_ids(doc)


def test_a_full_run_outside_a_repository_reads_no_area(tmp_path: pathlib.Path) -> None:
    """The fake host's root is no git repository: the run says so and its verdict is the base battery's, which is what keeps every scenario of test_drills_vm_check.py unchanged."""
    world = base.make_world(tmp_path)
    rc, out, doc = base.run_check(tmp_path, world)
    assert rc == vm_check.EXIT_VERIFIED, out
    assert "is not a git repository root, so no area is read" in out
    assert doc["trigger"]["areas"] == []


def test_a_full_run_in_a_repository_reads_its_areas(console: Console) -> None:
    """Without --changed the areas still come from the diff, so a full run is no way past an area's NOT_VERIFIED."""
    console.edit("pkg/rbd/rbd.go")
    check = vm_check.VmCheck(
        root=console.root,
        opts=vm_check.Options(),
        host=vm_check.Host(),
        account=base.FakeAccount(),
        work=console.root,
        lock=vm_check.Lock(console.root / "lock"),
        out=io.StringIO(),
        environ={},
    )
    check._evaluate_areas()
    assert check.areas == frozenset({"ceph"})
    assert check.trigger_info["areas"] == ["ceph"]


def test_a_receipt_whose_areas_is_not_an_object_is_refused(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _rc, _out, doc, _world = run_with_areas(
        tmp_path, monkeypatch, {"license"}, account_required=False
    )
    assert receipt_mod.validate(doc) == []
    doc["areas"] = ["license"]
    assert "areas is not an object" in receipt_mod.validate(doc)
