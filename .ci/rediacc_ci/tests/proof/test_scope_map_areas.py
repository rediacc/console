"""`.ci/scripts/ci/scope-map.cjs` selecting CI VM jobs from the renet areas of `.ci/config/proof-tiers.json` (agent/plans/PLAN-renet-change-test-triggers.md box V2).

Every assertion shells out to node and reads the real module, since the subject is the JavaScript. Both directions are pinned: a one-area renet path selects only that area's VM jobs, and the bare gitlink, a renet path in no area, or a renet path beside any other VM-surface module selects all nine. The parity test reads the area globs through the JavaScript and through `rediacc_ci.proof.surfaces` over every tracked renet file and requires the same answer, so the two readers of one map cannot drift.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.proof import surfaces as S

ROOT = paths.repo_root()
SCOPE_MAP = ROOT / ".ci" / "scripts" / "ci" / "scope-map.cjs"
ALL_VM = {
    "e2e_workers",
    "e2e_ceph",
    "e2e_ceph_workers",
    "e2e_k8s",
    "e2e_k8s_ceph",
    "e2e_k8s_multinode",
    "e2e_migrate",
    "e2e_backup_browse_at",
    "fork_isolation",
}
# The non-VM keys that consume `renet`; an area never narrows them.
RENET_NON_VM = {
    "renet",
    "license_enforcement",
    "drills",
    "ops",
    "elite_run",
    "update_flow",
    "package_tests",
    "install_methods",
}


def node(script: str, stdin: str = "") -> str:
    proc = subprocess.run(
        ["node", "-e", script, str(SCOPE_MAP)],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def plan(*paths_: str) -> dict:
    out = node(
        "const m = require(process.argv[1]);"
        'const paths = JSON.parse(require("fs").readFileSync(0, "utf8"));'
        "process.stdout.write(JSON.stringify(m.buildPlan(m.classify(paths))));",
        json.dumps(list(paths_)),
    )
    return json.loads(out)


def running(p: dict) -> set[str]:
    return {k for k, j in p["jobs"].items() if j["run"] is True}


@pytest.mark.parametrize(
    ("path", "vm"),
    [
        ("private/renet/pkg/license/store.go", {"e2e_workers", "fork_isolation"}),
        ("private/renet/pkg/kube/distro/k3s.go", {"e2e_k8s", "e2e_k8s_ceph", "e2e_k8s_multinode"}),
        ("private/renet/pkg/rbd/rbd.go", {"e2e_ceph", "e2e_ceph_workers", "e2e_k8s_ceph"}),
        ("private/renet/cmd/renet/repository_migrate.go", {"e2e_migrate", "e2e_workers"}),
        ("private/renet/pkg/chunkstore/store.go", {"e2e_workers", "e2e_backup_browse_at"}),
    ],
)
def test_a_one_area_renet_path_selects_only_its_vm_jobs(path: str, vm: set[str]) -> None:
    p = plan(path)
    assert p["mode"] == "reduced"
    assert running(p) & ALL_VM == vm
    assert running(p) >= RENET_NON_VM, "the renet Go tests and the other renet keys still run"
    for job in ALL_VM - vm:
        assert p["jobs"][job] == {"run": False, "reason": "out-of-scope"}, job


def test_a_kube_path_skips_the_ceph_and_worker_jobs() -> None:
    p = plan("private/renet/pkg/kube/distro/k3s.go")
    assert p["jobs"]["e2e_k8s"]["reason"] == "modules:renet;areas:kube"
    assert p["jobs"]["e2e_ceph"]["run"] is False
    assert p["jobs"]["e2e_workers"]["run"] is False


@pytest.mark.parametrize(
    "paths_",
    [
        # The bare gitlink, the only renet form the CI diff carries today.
        ["private/renet"],
        # A renet runtime path in no area.
        ["private/renet/pkg/hub/hub.go"],
        # A renet path outside the renet surface (the Dockerfile builds the image).
        ["private/renet/Dockerfile"],
        # One area beside the gitlink.
        ["private/renet/pkg/kube/distro/k3s.go", "private/renet"],
        # One area beside another VM-surface module: cli reaches every VM job.
        ["private/renet/pkg/kube/distro/k3s.go", "packages/cli/src/commands/repo.ts"],
    ],
)
def test_a_renet_change_the_areas_cannot_bound_selects_every_vm_job(paths_: list[str]) -> None:
    p = plan(*paths_)
    assert p["mode"] == "reduced"
    assert running(p) >= ALL_VM, sorted(ALL_VM - running(p))


def test_two_areas_select_the_union_of_their_jobs() -> None:
    p = plan("private/renet/pkg/kube/distro/k3s.go", "private/renet/pkg/license/store.go")
    assert running(p) & ALL_VM == {
        "e2e_k8s",
        "e2e_k8s_ceph",
        "e2e_k8s_multinode",
        "e2e_workers",
        "fork_isolation",
    }


def test_a_test_only_renet_change_selects_no_vm_job_but_the_renet_tests() -> None:
    p = plan("private/renet/pkg/license/store_test.go")
    assert running(p) & ALL_VM == set()
    assert "renet" in running(p)
    assert p["reasons"] == ["private/renet/pkg/license/store_test.go -> renet [excluded]"]


def test_the_proof_tiers_map_itself_still_forces_full_ci() -> None:
    p = plan(".ci/config/proof-tiers.json")
    assert p["mode"] == "full"


def test_every_area_names_only_vm_job_keys() -> None:
    keys = set(
        json.loads(
            node("process.stdout.write(JSON.stringify(require(process.argv[1]).VM_E2E_JOB_KEYS))")
        )
    )
    assert keys == ALL_VM
    for name, area in S.MAP.areas.items():
        assert set(area.ci_jobs) <= keys, (name, area.ci_jobs)


def test_an_area_naming_an_unknown_job_throws_at_load() -> None:
    out = node(
        "const m = require(process.argv[1]);"
        'const raw = JSON.parse(require("fs").readFileSync(0, "utf8"));'
        'raw.tiers.vm.areas.kube.ci_jobs = ["e2e_kube_typo"];'
        'try { m.loadRenetAreas(raw, m.VM_E2E_JOB_KEYS); process.stdout.write("LOADED"); }'
        'catch (e) { process.stdout.write("THREW " + e.message); }',
        S.MAP_PATH.read_text(encoding="utf-8"),
    )
    assert out.startswith("THREW"), out
    assert "e2e_kube_typo" in out


def test_an_empty_area_table_throws_at_load() -> None:
    out = node(
        "const m = require(process.argv[1]);"
        'try { m.loadRenetAreas({tiers: {vm: {areas: {}}}, exclude: ["**/*.md"]}, m.VM_E2E_JOB_KEYS); process.stdout.write("LOADED"); }'
        'catch (e) { process.stdout.write("THREW " + e.message); }'
    )
    assert out.startswith("THREW"), out


def test_a_character_class_is_refused_not_half_read() -> None:
    out = node(
        "const m = require(process.argv[1]);"
        'try { m.globRegex("private/renet/pkg/[ab]/**"); process.stdout.write("ACCEPTED"); }'
        'catch (e) { process.stdout.write("THREW"); }'
    )
    assert out == "THREW"


def _tracked_renet() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT / S.RENET_SUBMODULE), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    files = [f"{S.RENET_SUBMODULE}/{f}" for f in out]
    assert len(files) >= 200, "private/renet is not checked out (%d files)" % len(files)
    return files


def test_the_javascript_reads_the_area_globs_as_python_does() -> None:
    """Every tracked renet file, plus planted shapes the tree may not hold, classified by both readers of the one map."""
    files = [
        *_tracked_renet(),
        "private/renet/pkg/license/deep/nested/x.go",
        "private/renet/cmd/renet/kube_new_thing.go",
        "private/renet/pkg/functions/commands/kube_new.go",
        "private/renet/pkg/kube/README.md",
        "private/renet/pkg/kube/x_test.go",
    ]
    out = node(
        "const m = require(process.argv[1]);"
        'const files = JSON.parse(require("fs").readFileSync(0, "utf8"));'
        "const res = {};"
        'for (const f of files) { const r = m.renetAreasOf(f); res[f] = r.kind === "excluded" ? null : r.areas.sort(); }'
        "process.stdout.write(JSON.stringify(res));",
        json.dumps(files),
    )
    js = json.loads(out)
    mismatched = []
    mapped = 0
    for f in files:
        py = None if S.excluded(f) else sorted(S.areas_of(f))
        mapped += bool(py)
        if js[f] != py:
            mismatched.append((f, js[f], py))
    assert mismatched == [], mismatched[:10]
    assert mapped >= 100, "only %d files fall in an area: the parity judged almost nothing" % mapped


def test_the_real_tree_reads_the_area_map() -> None:
    out = node(
        "const m = require(process.argv[1]);"
        "process.stdout.write(JSON.stringify([m.AREA_MAP_ERROR, Object.keys(m.RENET_AREAS.areas)]));"
    )
    err, names = json.loads(out)
    assert err is None
    assert tuple(names) == S.AREAS


def test_a_copy_without_the_map_selects_every_vm_job_and_says_so(tmp_path: pathlib.Path) -> None:
    """Two gate fixtures copy .ci/scripts/ci alone. An absent map is the ambiguous case, so it resolves to every VM job, and the reason line names why; a present map naming a bad job still throws (test_an_area_naming_an_unknown_job_throws_at_load)."""
    lone = tmp_path / "ci" / "scope-map.cjs"
    lone.parent.mkdir(parents=True)
    lone.write_text(SCOPE_MAP.read_text(encoding="utf-8"), encoding="utf-8")
    proc = subprocess.run(
        [
            "node",
            "-e",
            (
                "const m = require(process.argv[1]);"
                'const p = m.buildPlan(m.classify(["private/renet/pkg/kube/distro/k3s.go"]));'
                "process.stdout.write(JSON.stringify({err: m.AREA_MAP_ERROR, plan: p}));"
            ),
            str(lone),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    assert "not found" in got["err"]
    assert running(got["plan"]) >= ALL_VM
    assert got["plan"]["reasons"] == [
        "private/renet/pkg/kube/distro/k3s.go -> renet [areas-unavailable]"
    ]


def test_classify_reads_the_map_from_the_one_file() -> None:
    src = SCOPE_MAP.read_text(encoding="utf-8")
    assert "const PROOF_TIERS_REL = '../../config/proof-tiers.json';" in src
    assert (
        pathlib.Path(SCOPE_MAP.parent / "../../config/proof-tiers.json").resolve()
        == S.MAP_PATH.resolve()
    )
