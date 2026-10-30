"""The renet areas of `.ci/config/proof-tiers.json` (`tiers.vm.areas`, agent/plans/PLAN-renet-change-test-triggers.md Design item 3), read through `rediacc_ci.proof.surfaces`.

Three kinds of test. The loader refuses each shape of a blind map (planted defects through `parse_map`). The path lookup answers both directions: a path that must land in an area, and paths that must not (a test file, a doc, a renet path in no area). The live map is pinned against the live tree: every glob reaches a tracked renet file, every file an area glob reaches is in the renet surface, every suite, playwright config and `--test` filter a leg names exists, every `vmcheck` step is a step vm:check has, and the area names equal the renet test map's `areaNames`.
"""

from __future__ import annotations

import copy
import json
import pathlib
import re
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.drills import vm_check
from rediacc_ci.proof import surfaces as S

ROOT = paths.repo_root()
AREA_NAMES = ("license", "functions", "migrate", "multi-vm", "ceph", "kube", "backup")
RENET_TEST_MAP = ROOT / ".ci" / "config" / "renet-test-map.json"


def _raw() -> dict:
    return json.loads(S.MAP_PATH.read_text(encoding="utf-8"))


def _renet_files() -> list[str]:
    """Tracked renet files, console-relative. Fewer than 200 means the submodule is not checked out, and a pin over it would pass on nothing."""
    out = subprocess.run(
        ["git", "-C", str(ROOT / S.RENET_SUBMODULE), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
    )
    files = [f"{S.RENET_SUBMODULE}/{f}" for f in out.stdout.split()]
    assert len(files) >= 200, (
        "private/renet is not checked out (%d files): the live pins would judge nothing"
        % len(files)
    )
    return files


# ----------------------------------------------------------------------------- the loader


def test_the_live_map_carries_the_seven_areas_in_order() -> None:
    assert S.AREAS == AREA_NAMES
    for name in AREA_NAMES:
        area = S.MAP.areas[name]
        assert area.globs, name
        assert area.legs, name
        assert area.ci_jobs, name


def _plant(mutate) -> str:
    raw = copy.deepcopy(_raw())
    mutate(raw["tiers"]["vm"])
    with pytest.raises(S.MapError) as exc:
        S.parse_map(raw)
    return str(exc.value)


def test_the_unplanted_map_parses() -> None:
    """The control for every plant below: the same copy, unmutated, parses."""
    parsed = S.parse_map(copy.deepcopy(_raw()))
    assert tuple(parsed.areas) == AREA_NAMES


def test_an_empty_area_table_is_refused() -> None:
    assert "tiers.vm.areas is empty" in _plant(lambda vm: vm.__setitem__("areas", {}))


def test_a_missing_area_table_is_refused() -> None:
    assert "tiers.vm.areas is empty" in _plant(lambda vm: vm.pop("areas"))


def test_an_area_glob_outside_renet_is_refused() -> None:
    def mutate(vm: dict) -> None:
        vm["areas"]["kube"]["globs"].append("packages/cli/src/**")

    assert "leave private/renet/" in _plant(mutate)


def test_an_area_glob_the_renet_surface_cannot_reach_is_refused() -> None:
    def mutate(vm: dict) -> None:
        vm["areas"]["kube"]["globs"] = ["private/renet/docs/**"]

    assert "reach no path of the renet surface" in _plant(mutate)


def test_an_area_with_no_leg_is_refused() -> None:
    def mutate(vm: dict) -> None:
        vm["areas"]["ceph"]["legs"] = []

    assert "nothing would prove the area" in _plant(mutate)


def test_an_area_with_no_ci_job_is_refused() -> None:
    def mutate(vm: dict) -> None:
        vm["areas"]["ceph"]["ci_jobs"] = []

    assert "ci_jobs is empty" in _plant(mutate)


def test_an_external_leg_on_an_unknown_fleet_is_refused() -> None:
    def mutate(vm: dict) -> None:
        vm["areas"]["ceph"]["legs"][0]["fleet"] = "nowhere"

    assert "fleet 'nowhere' is not in tiers.vm.fleets" in _plant(mutate)


def test_an_external_leg_with_no_command_is_refused() -> None:
    def mutate(vm: dict) -> None:
        vm["areas"]["ceph"]["legs"][0]["cmd"] = []

    assert ".cmd is empty" in _plant(mutate)


def test_a_vmcheck_leg_with_no_step_is_refused() -> None:
    def mutate(vm: dict) -> None:
        vm["areas"]["license"]["legs"][0]["steps"] = []

    assert ".steps is empty" in _plant(mutate)


def test_an_unknown_leg_kind_is_refused() -> None:
    def mutate(vm: dict) -> None:
        vm["areas"]["license"]["legs"][0]["kind"] = "maybe"

    assert "kind 'maybe' is not one of" in _plant(mutate)


def test_an_unknown_receipt_is_refused() -> None:
    def mutate(vm: dict) -> None:
        vm["areas"]["backup"]["legs"][0]["receipt"] = "vibes"

    assert "receipt 'vibes'" in _plant(mutate)


def test_two_legs_sharing_an_id_are_refused() -> None:
    def mutate(vm: dict) -> None:
        legs = vm["areas"]["kube"]["legs"]
        legs.append(dict(legs[0]))

    assert "repeat an id" in _plant(mutate)


def test_an_empty_fleet_table_is_refused() -> None:
    assert "tiers.vm.fleets is empty" in _plant(lambda vm: vm.__setitem__("fleets", {}))


# ----------------------------------------------------------------------------- the path lookup, both directions


@pytest.mark.parametrize(
    ("path", "areas"),
    [
        ("private/renet/pkg/license/store.go", {"license"}),
        ("private/renet/cmd/renet/license_renew.go", {"license"}),
        ("private/renet/pkg/kube/distro/k3s.go", {"kube"}),
        ("private/renet/cmd/renet/kube_root.go", {"kube"}),
        ("private/renet/pkg/rbd/rbd.go", {"ceph"}),
        ("private/renet/cmd/renet/ceph_clone.go", {"ceph"}),
        ("private/renet/pkg/chunkstore/store.go", {"backup"}),
        ("private/renet/cmd/renet/backup_push.go", {"backup", "multi-vm"}),
        ("private/renet/cmd/renet/repository_migrate.go", {"migrate"}),
        ("private/renet/pkg/infra/mesh/mesh.go", {"migrate", "multi-vm"}),
        ("private/renet/pkg/functions/executor.go", {"functions"}),
        ("private/renet/pkg/functions/commands/ceph.go", {"ceph", "functions"}),
    ],
)
def test_a_renet_path_lands_in_its_areas(path: str, areas: set[str]) -> None:
    assert set(S.areas_of(path)) == areas


@pytest.mark.parametrize(
    "path",
    [
        # A test file and a doc change no deployed binary: no area, and no VM proof at all.
        "private/renet/pkg/license/store_test.go",
        "private/renet/pkg/kube/README.md",
        "private/renet/tests/unit/test_x.py",
        # A renet runtime path in no area: the base battery alone.
        "private/renet/pkg/hub/hub.go",
        "private/renet/scripts/pull-with-retry.sh",
        # Not renet at all.
        "packages/cli/src/remote/sync.ts",
    ],
)
def test_a_path_outside_every_area_selects_none(path: str) -> None:
    assert S.areas_of(path) == frozenset()


def test_a_change_reports_its_areas_and_its_unmapped_renet_hits() -> None:
    changed = S.changed_from_paths(
        [
            "private/renet/pkg/license/store.go",
            "private/renet/pkg/hub/hub.go",
            "private/renet/pkg/license/store_test.go",
            "docs/x.md",
        ]
    )
    assert changed.areas == frozenset({"license"})
    assert changed.unmapped == ("private/renet/pkg/hub/hub.go",)
    assert changed.sides == frozenset({"renet"})
    assert "private/renet/pkg/license/store_test.go" not in changed.hits


def test_the_build_script_renet_sources_is_a_renet_surface_path() -> None:
    """private/renet/build.sh sources scripts/pull-with-retry.sh, so an edit to it changes the build; it was outside the renet surface until 2026-10-30."""
    assert 'source "$SCRIPT_DIR/scripts/pull-with-retry.sh"' in (
        ROOT / S.RENET_SUBMODULE / "build.sh"
    ).read_text(encoding="utf-8")
    assert S.surfaces_of("private/renet/scripts/pull-with-retry.sh") == frozenset({"renet"})


# ----------------------------------------------------------------------------- the live map against the live tree


def test_every_area_glob_reaches_a_tracked_renet_file() -> None:
    files = _renet_files()
    dead = [
        f"{name}: {glob}"
        for name, area in S.MAP.areas.items()
        for glob in area.globs
        if not any(S.matches(f, [glob]) for f in files)
    ]
    assert dead == [], "area globs that match no tracked renet file: %s" % dead


def test_every_file_an_area_reaches_is_in_the_renet_surface() -> None:
    """An area path outside the renet surface would select legs while the renet phase, and the push guard, never fired."""
    files = _renet_files()
    reached = [f for f in files if S.areas_of(f)]
    assert len(reached) >= 100, "only %d renet files fall in an area: the areas are blind" % len(
        reached
    )
    stray = [f for f in reached if "renet" not in S.surfaces_of(f)]
    assert stray == []


def test_every_vmcheck_leg_names_steps_vm_check_has() -> None:
    known = vm_check.known_step_ids()
    for name, area in S.MAP.areas.items():
        for leg in area.legs:
            if leg.kind == S.LEG_VMCHECK:
                assert set(leg.steps) <= known, (name, leg.id, sorted(set(leg.steps) - known))


def test_the_license_leg_runs_the_license_drill() -> None:
    """A2.3 is the license drill (`drill_argvs`), the leg the license area exists for."""
    leg = S.MAP.areas["license"].legs[0]
    assert leg.steps == ("A0", "A2.3")
    assert vm_check.LICENSE_LEGS in leg.what


def test_every_suite_an_area_names_exists() -> None:
    missing = [s for a in S.MAP.areas.values() for s in a.suites if not (ROOT / s).is_file()]
    assert missing == []


_CONFIG = re.compile(r"--config (\S+)")
_TEST = re.compile(r"--test (\S+)")


def test_every_external_leg_names_a_real_config_and_test_filter() -> None:
    e2e = ROOT / "packages" / "e2e-tests"
    tests = [p.name for p in (e2e / "tests").rglob("*.test.ts")]
    seen = 0
    for name, area in S.MAP.areas.items():
        for leg in area.legs:
            if leg.kind != S.LEG_EXTERNAL:
                continue
            run = leg.cmd[-1]
            assert "--fail-on-skip" in run, (name, leg.id, "a run that may skip proves nothing")
            for cfg in _CONFIG.findall(run):
                seen += 1
                assert (e2e / cfg).is_file(), (name, leg.id, cfg)
            for flt in _TEST.findall(run):
                seen += 1
                assert any(flt in t for t in tests), (name, leg.id, flt)
    assert seen >= 7, "only %d config or filter references were checked" % seen


def test_every_fleet_ip_is_on_an_ops_vm_network() -> None:
    for fleet in S.MAP.fleets.values():
        assert fleet.ips, fleet
        assert all(re.fullmatch(r"192\.168\.11[12]\.\d+", ip) for ip in fleet.ips), fleet


def test_the_area_names_equal_the_renet_test_maps() -> None:
    """One area vocabulary across the two maps: .ci/config/renet-test-map.json (the Go test map) declares `areaNames` and tags its entries with them; proof-tiers.json owns what each area's paths, legs and CI jobs are."""
    if not RENET_TEST_MAP.is_file():
        pytest.skip("%s does not exist yet" % RENET_TEST_MAP.relative_to(ROOT))
    other = json.loads(RENET_TEST_MAP.read_text(encoding="utf-8"))
    assert tuple(other["areaNames"]) == S.AREAS
    used = {a for entry in other.get("entries", []) for a in entry.get("areas", [])}
    assert used <= set(S.AREAS), sorted(used - set(S.AREAS))


def test_the_dry_run_names_its_own_flag_in_the_usage_line() -> None:
    assert "--dry-run" in (vm_check.__doc__ or "").split("\n\n", 2)[1]


def test_the_map_file_is_the_one_surfaces_reads() -> None:
    assert pathlib.Path(S.MAP_PATH) == ROOT / ".ci" / "config" / "proof-tiers.json"
