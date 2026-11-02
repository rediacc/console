"""`rediacc_ci.release.cd_preflight`: the pre-merge prediction of CD failures (PLAN-cd-errors-in-ci W3).

THE ORACLE IS THE GATE'S. Checks (a) and (b) judge through `release_state.assert_bijection`, the function that went red on main after the 2026-10-07 housekeeping run deleted tag v1.3.1 while `cli/v1.3.1/.released` stayed. So the controls here are states, not restatements:

  * the 10-07 replay (a sentinel with no tag after the keep-20-with-production prune) must go RED;
  * the 10-08 CD state (v2.2.0 sealed, its tag not yet created, v2.2.0 under release) must go GREEN, and the same state with any OTHER version under release must go red, so the exclusion is of that version only;
  * a healthy state must go green;
  * an unreachable reader must be UNCHECKED with a non-zero exit, never a pass;
  * with check (a) planted out, the 10-07 replay goes GREEN, which proves the replay's red is (a)'s and the test bites.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.quality import release_state
from rediacc_ci.release import cd_preflight as cp
from rediacc_ci.release import retention_contract
from rediacc_ci.well_known import RELEASES_ORIGIN, SITE_ORIGIN

if TYPE_CHECKING:
    import pathlib

# The formula as private/homebrew-tap carries it (2026-10-08), so the rewrite is driven without the submodule.
FORMULA = """class RediaccCli < Formula
  desc "Rediacc CLI - automation and scripting tool"
  homepage "@SITE@"
  version "2.1.0"
  license "MIT"

  on_macos do
    if Hardware::CPU.arm?
      url "@REL@/cli/v#{version}/rdc-mac-arm64"
      sha256 "948dab8a0d5d9694695fef1142337660fa940bbea6333566555fba6c0d4fb69e"

      def install
        bin.install "rdc-mac-arm64" => "rdc"
      end
    else
      url "@REL@/cli/v#{version}/rdc-mac-x64"
      sha256 "9abf481829b52777e99cb0946a5667aca6c92277ba67ca1b1452cbbaba725450"

      def install
        bin.install "rdc-mac-x64" => "rdc"
      end
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "@REL@/cli/v#{version}/rdc-linux-arm64"
      sha256 "e2367ed94fd44629fd7003521179d40b4d375f3d9323e62d77a1d27ac504c490"

      def install
        bin.install "rdc-linux-arm64" => "rdc"
      end
    else
      url "@REL@/cli/v#{version}/rdc-linux-x64"
      sha256 "712673e49c0c8f2dce489d2a559a60e5a549572981afdc424c18f251e789de42"

      def install
        bin.install "rdc-linux-x64" => "rdc"
      end
    end
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/rdc --version")
  end
end
""".replace("@SITE@", SITE_ORIGIN).replace("@REL@", RELEASES_ORIGIN)


@pytest.fixture(autouse=True)
def _gate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The floor comes from the state's ratchet alone: no override, no floor-file redirect leaking in from the caller."""
    monkeypatch.delenv("RSV_FLOOR_FILE", raising=False)
    monkeypatch.delenv("RSV_GRANDFATHER_BEFORE", raising=False)


@pytest.fixture
def root(tmp_path: pathlib.Path) -> pathlib.Path:
    formula = cp.formula_path(tmp_path)
    formula.parent.mkdir(parents=True)
    formula.write_text(FORMULA, encoding="utf-8")
    return tmp_path


def ok_dry_run(version: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["update_homebrew_tap", version], 0, "", "")


def series(major_minor: str, first: int, last: int) -> list[str]:
    """`X.Y.first` .. `X.Y.last`, oldest first, without the `v`."""
    return ["%s.%d" % (major_minor, i) for i in range(first, last + 1)]


def snapshot(
    sealed: list[str],
    tagged: list[str],
    *,
    edge: str,
    stable: str,
    ratchet: str,
    tracker: list[str] | None = None,
    objects: int = 600,
    extra_tags: tuple[str, ...] = ("production",),
) -> dict[str, Any]:
    """A `--state` snapshot. `sealed` and `tagged` are versions without the `v`; the tracker defaults to the sealed list newest first."""
    tags = {"v" + v: "%040x" % i for i, v in enumerate(tagged, 1)}
    tags.update(dict.fromkeys(extra_tags, "f" * 40))
    return {
        "sentinels": ["v" + v for v in sealed],
        "tags": tags,
        "tracker": list(reversed(sealed)) if tracker is None else tracker,
        "pointers": {
            "edge/latest.json": "v" + edge,
            "edge/manifest.json": "v" + edge,
            "stable/latest.json": "v" + stable,
            "stable/manifest.json": "v" + stable,
        },
        "channel_objects": {"edge": objects},
        "ratchet": "v" + ratchet if ratchet else "",
    }


def run(
    state: dict[str, Any],
    version: str,
    phase: str = "pr",
    *,
    root: pathlib.Path,
    checks: tuple[str, ...] = cp.CHECK_IDS,
    release_sha: str = "",
) -> tuple[int, dict[str, cp.Result]]:
    results = cp.run_checks(
        cp.State(cp.replay_readers(state)),
        version=version,
        phase=phase,
        selected=checks,
        release_sha=release_sha,
        root=root,
        dry_run=ok_dry_run,
    )
    return cp.exit_code(results), {r.check: r for r in results}


def replay_10_07() -> dict[str, Any]:
    """R2 kept twenty sealed releases; the pre-fix housekeeping kept the newest twenty TAGS, `production` among them, so v1.3.1 lost its tag and kept its sentinel."""
    sealed = series("1.3", 1, 20)
    return snapshot(sealed, sealed[1:], edge="1.3.20", stable="1.3.18", ratchet="1.3.1")


def cd_10_08() -> dict[str, Any]:
    """CD for v2.2.0 at its first step: ci.yml sealed `cli/v2.2.0/.released`, init has not yet created the tag, and the upload has not yet touched the tracker or the edge pointer."""
    released = series("2.1", 1, 19)
    return snapshot(
        [*released, "2.2.0"],
        released,
        edge="2.1.19",
        stable="2.1.15",
        ratchet="2.1.1",
        tracker=list(reversed(released)),
    )


def healthy() -> dict[str, Any]:
    sealed = series("1.4", 1, 20)
    return snapshot(sealed, sealed, edge="1.4.20", stable="1.4.17", ratchet="1.4.1")


# --------------------------------------------------------------------------- the controls ---------------------------------------------------------------------------


def test_the_10_07_replay_is_red_on_check_a(root: pathlib.Path) -> None:
    """No release follows: housekeeping's own call (`--release-version 0.0.0 --checks a,c`)."""
    rc, results = run(replay_10_07(), "0.0.0", root=root, checks=("a", "c"))
    assert rc == 1
    assert results["a"].status == cp.DRIFT
    assert "DRIFT v1.3.1: cli sentinel present, git tag missing" in results["a"].lines
    assert results["c"].status == cp.OK, results["c"].lines


def test_the_10_07_replay_with_a_release_that_prunes_v1_3_1_is_a_warning(
    root: pathlib.Path,
) -> None:
    """The release of v1.3.21 prunes v1.3.1 itself, so the drift heals in the very run (a) would otherwise refuse (2026-10-08: v1.3.2 and the release of v2.2.1)."""
    rc, results = run(replay_10_07(), "1.3.21", root=root)
    assert rc == 0, {k: (r.status, r.lines) for k, r in results.items()}
    assert results["a"].status == cp.WARN
    assert "DRIFT v1.3.1: cli sentinel present, git tag missing" in results["a"].lines
    assert results["a"].lines[-1] == (
        "the release of v1.3.21 prunes v1.3.1 itself, so this drift heals in that release"
    )
    for other in ("c", "d", "homebrew", "promotion"):
        assert results[other].status == cp.OK, (other, results[other].lines)


def test_mirror_drift_on_a_version_the_release_keeps_stays_red(root: pathlib.Path) -> None:
    """The heal is of the pruned version only: v1.3.10 untagged survives the release of v1.3.21, so (a) still refuses it."""
    sealed = series("1.3", 1, 20)
    state = snapshot(
        sealed,
        [v for v in sealed if v != "1.3.10"],
        edge="1.3.20",
        stable="1.3.18",
        ratchet="1.3.1",
    )
    rc, results = run(state, "1.3.21", root=root)
    assert rc == 1
    assert results["a"].status == cp.DRIFT
    assert "DRIFT v1.3.10: cli sentinel present, git tag missing" in results["a"].lines
    assert not any("heals" in line for line in results["a"].lines)


def test_mirror_an_unreadable_tracker_keeps_the_drift_blocking(root: pathlib.Path) -> None:
    """The heal needs the tracker to say what the release prunes; when it cannot be read, (a) fails closed."""
    state = replay_10_07()
    state["tracker"] = {"unchecked": "aws exited 255: Could not connect to the endpoint URL"}
    rc, results = run(state, "1.3.21", root=root, checks=("a",))
    assert rc == 1
    assert results["a"].status == cp.DRIFT


def test_the_10_08_cd_state_is_green_with_the_version_under_release_excluded(
    root: pathlib.Path,
) -> None:
    rc, results = run(cd_10_08(), "2.2.0", "cd", root=root)
    assert rc == 0, {k: (r.status, r.lines) for k, r in results.items()}
    assert all(r.status == cp.OK for r in results.values())
    assert "excluding v2.2.0" in results["a"].lines[0]
    assert "init's Create version tag creates v2.2.0" in results["d"].lines


def test_mirror_the_10_08_state_with_another_version_under_release_is_red(
    root: pathlib.Path,
) -> None:
    """The exclusion names ONE version: judged as if v2.2.1 were under release, v2.2.0's sealed-but-untagged state is the drift it is."""
    rc, results = run(cd_10_08(), "2.2.1", "pr", root=root)
    assert rc == 1
    assert "DRIFT v2.2.0: cli sentinel present, git tag missing" in results["a"].lines


def test_mirror_the_10_08_state_in_phase_pr_is_red_on_check_d(root: pathlib.Path) -> None:
    """Before a merge, a predicted version that is already sealed is a collision, not an in-flight release."""
    rc, results = run(cd_10_08(), "2.2.0", "pr", root=root)
    assert rc == 1
    assert results["a"].status == cp.OK
    assert results["d"].status == cp.DRIFT
    assert any("already RELEASED" in line for line in results["d"].lines)


def test_a_healthy_state_is_green_and_says_what_it_saw(root: pathlib.Path) -> None:
    rc, results = run(healthy(), "1.4.21", root=root)
    assert rc == 0, {k: (r.status, r.lines) for k, r in results.items()}
    assert all(r.status == cp.OK for r in results.values())
    assert results["a"].lines[0].startswith("20 sentinels, 20 release tags, ratchet v1.4.1")
    assert results["b"].lines[0].startswith("projected from 20 sentinels, 20 release tags")


def test_an_unreachable_reader_is_unchecked_and_fails(root: pathlib.Path) -> None:
    state = healthy()
    state["sentinels"] = {"unchecked": "aws exited 255: Could not connect to the endpoint URL"}
    rc, results = run(state, "1.4.21", root=root)
    assert rc == 1
    for check in ("a", "b", "c", "d"):
        assert results[check].status == cp.UNCHECKED
        assert "Could not connect" in results[check].lines[0]
    assert results["promotion"].status == cp.OK


def test_planted_with_check_a_disabled_the_10_07_replay_goes_green(
    root: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE TEST BITES. First the control fires; then (a) is replaced by a check that always passes, and the same replay exits 0. If this went red, the replay's red was coming from somewhere other than (a)."""
    assert run(replay_10_07(), "0.0.0", root=root, checks=("a", "c"))[0] == 1

    def always_ok(*_: object) -> cp.Result:
        return cp.Result("a", cp.OK, ("off",))

    monkeypatch.setitem(cp.STATE_CHECKS, "a", always_ok)
    rc, results = run(replay_10_07(), "0.0.0", root=root, checks=("a", "c"))
    assert rc == 0, {k: (r.status, r.lines) for k, r in results.items()}


# --------------------------------------------------------------------------- (b) the projection ---------------------------------------------------------------------------


def _prefix_rule(
    tags, *, stable, sentinels=(), keep=retention_contract.KEEP_RELEASES, contract=True
):
    """Housekeeping before 2026-10-08: the newest `keep` tags of ANY kind survive, no sentinel hold."""
    del stable, sentinels, contract
    return retention_contract.TagPlan(
        tuple(
            retention_contract.Verdict(
                name, retention_contract.KEEP if i < keep else retention_contract.DELETE, "prefix"
            )
            for i, name in enumerate(tags)
        )
    )


def test_b_projects_the_pre_fix_keep_rule_into_drift(
    root: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checkout whose keep rule is the 10-07 one: healthy today, so (a) is green, and (b) is what sees the next run deleting v1.4.1's tag. It WARNS (plan tunables) and does not fail the run."""
    assert run(healthy(), "1.4.21", root=root, checks=("b",))[1]["b"].status == cp.OK
    monkeypatch.setattr(retention_contract, "tag_retention_plan", _prefix_rule)
    rc, results = run(healthy(), "1.4.21", root=root)
    assert results["a"].status == cp.OK
    assert results["b"].status == cp.WARN
    assert "  DRIFT v1.4.1: cli sentinel present, git tag missing" in results["b"].lines
    assert rc == 0


def test_b_in_phase_cd_keeps_the_sealed_version_in_flight_until_it_is_tagged() -> None:
    steps = cp.project(
        [f"v{v}" for v in series("2.1", 1, 19)] + ["v2.2.0"],
        [f"v{v}" for v in series("2.1", 1, 19)],
        list(reversed(series("2.1", 1, 19))),
        "2.1.15",
        "2.2.0",
    )
    assert [s[3] for s in steps] == ["v2.2.0", "", ""]
    assert "v2.2.0" in steps[1][2], "the release step did not tag the version"


def test_b_the_release_prunes_r2_beyond_the_window() -> None:
    sealed = ["v" + v for v in series("1.4", 1, 20)]
    steps = cp.project(sealed, sealed, list(reversed(series("1.4", 1, 20))), "1.4.17", "1.4.21")
    after_release = steps[1][1]
    assert "v1.4.1" not in after_release
    assert "v1.4.21" in after_release
    assert len(after_release) == retention_contract.KEEP_RELEASES


def test_b_an_unreadable_stable_manifest_is_unchecked_not_hold_everything(
    root: pathlib.Path,
) -> None:
    state = healthy()
    state["pointers"]["stable/manifest.json"] = {"unchecked": "aws exited 1: NoSuchKey"}
    rc, results = run(state, "1.4.21", root=root)
    assert results["b"].status == cp.UNCHECKED
    assert rc == 1


# --------------------------------------------------------------------------- (c) floor and pointers ---------------------------------------------------------------------------


def test_c_a_ratchet_above_every_sentinel_is_drift(root: pathlib.Path) -> None:
    state = healthy()
    state["ratchet"] = "v9.0.0"
    results = run(state, "1.4.21", root=root)[1]
    assert results["c"].status == cp.DRIFT
    assert "compares NOTHING" in results["c"].lines[0]


def test_c_a_ratchet_above_the_oldest_sentinel_warns(root: pathlib.Path) -> None:
    state = healthy()
    state["ratchet"] = "v1.4.3"
    results = run(state, "1.4.21", root=root)[1]
    assert results["c"].status == cp.WARN
    assert "v1.4.1, v1.4.2" in results["c"].lines[0]


def test_c_a_ratchet_lagging_the_oldest_sentinel_warns_and_does_not_fail(
    root: pathlib.Path,
) -> None:
    state = healthy()
    state["ratchet"] = "v1.3.0"
    code, results = run(state, "1.4.21", root=root)
    assert results["c"].status == cp.WARN
    assert "lags the oldest sentinel v1.4.1" in results["c"].lines[0]
    assert "next PR" in results["c"].lines[0]
    assert results["c"].status != cp.DRIFT
    assert code == 0, "a lagging floor must not fail the preflight"


def test_c_an_untagged_pointer_is_drift(root: pathlib.Path) -> None:
    state = healthy()
    state["pointers"]["edge/latest.json"] = state["pointers"]["edge/manifest.json"] = "v1.4.99"
    results = run(state, "1.4.21", root=root)[1]
    assert results["c"].status == cp.DRIFT
    assert any("names 'v1.4.99', which has NO git tag" in line for line in results["c"].lines)


def test_c_an_edge_pointer_without_a_sentinel_is_drift(root: pathlib.Path) -> None:
    sealed = series("1.4", 1, 20)
    state = snapshot(sealed[:-1], sealed, edge="1.4.20", stable="1.4.17", ratchet="1.4.1")
    results = run(state, "1.4.21", root=root)[1]
    assert any("has NO sentinel on R2" in line for line in results["c"].lines)


def test_c_stable_newer_than_edge_is_drift(root: pathlib.Path) -> None:
    sealed = series("1.4", 1, 20)
    state = snapshot(sealed, sealed, edge="1.4.17", stable="1.4.20", ratchet="1.4.1")
    results = run(state, "1.4.21", root=root)[1]
    assert results["c"].status == cp.DRIFT
    assert any("NEWER than edge" in line for line in results["c"].lines)


def test_c_mirror_the_edge_pointer_may_name_the_version_under_release(root: pathlib.Path) -> None:
    state = cd_10_08()
    state["pointers"]["edge/latest.json"] = state["pointers"]["edge/manifest.json"] = "v2.2.0"
    results = run(state, "2.2.0", "cd", root=root)[1]
    assert results["c"].status == cp.OK, results["c"].lines


# --------------------------------------------------------------------------- (d) the release version ---------------------------------------------------------------------------


def test_d_pr_an_already_tagged_version_is_drift(root: pathlib.Path) -> None:
    state = healthy()
    state["tags"]["v1.4.21"] = "a" * 40
    results = run(state, "1.4.21", root=root)[1]
    assert results["d"].status == cp.DRIFT
    assert any("already TAGGED" in line for line in results["d"].lines)


def test_d_pr_a_prediction_behind_the_newest_release_is_drift(root: pathlib.Path) -> None:
    results = run(healthy(), "1.4.5", root=root)[1]
    assert results["d"].status == cp.DRIFT
    assert any("older than v1.4.20" in line for line in results["d"].lines)


def test_d_cd_an_unsealed_version_is_drift(root: pathlib.Path) -> None:
    results = run(healthy(), "1.4.21", "cd", root=root)[1]
    assert results["d"].status == cp.DRIFT
    assert any("is not sealed" in line for line in results["d"].lines)


def test_d_cd_a_short_or_upper_case_release_sha_matches_the_full_tag_sha(
    root: pathlib.Path,
) -> None:
    state = cd_10_08()
    state["tags"]["v2.2.0"] = "abcdef0123" + "0" * 30
    assert run(state, "2.2.0", "cd", root=root, release_sha="ABCDEF0")[1]["d"].status == cp.OK
    assert run(state, "2.2.0", "cd", root=root, release_sha="abcdef1")[1]["d"].status == cp.DRIFT


def test_d_cd_a_stub_release_sha_is_unchecked_not_ok(root: pathlib.Path) -> None:
    state = cd_10_08()
    state["tags"]["v2.2.0"] = "abcdef0123" + "0" * 30
    for stub in ("a", "abcdef", "zzzzzzzz"):
        got = run(state, "2.2.0", "cd", root=root, release_sha=stub)[1]
        assert got["d"].status == cp.UNCHECKED, stub


def test_seen_sorts_an_unsorted_state_snapshot() -> None:
    state = healthy()
    state["sentinels"] = ["v1.4.21", "v1.4.3", "v1.4.20"]
    got = cp._seen(cp.State(cp.replay_readers(state)))[0]
    assert got == ["v1.4.3", "v1.4.20", "v1.4.21"]


def test_d_cd_a_tag_at_another_commit_is_drift_and_at_the_release_commit_is_fine(
    root: pathlib.Path,
) -> None:
    state = cd_10_08()
    state["tags"]["v2.2.0"] = "b" * 40
    assert run(state, "2.2.0", "cd", root=root, release_sha="b" * 40)[1]["d"].status == cp.OK
    moved = run(state, "2.2.0", "cd", root=root, release_sha="c" * 40)[1]["d"]
    assert moved.status == cp.DRIFT
    assert any("not at the release commit" in line for line in moved.lines)


# --------------------------------------------------------------------------- homebrew and promotion ---------------------------------------------------------------------------


def test_homebrew_without_the_tap_is_unchecked(tmp_path: pathlib.Path) -> None:
    rc, results = run(healthy(), "1.4.21", root=tmp_path)
    assert results["homebrew"].status == cp.UNCHECKED
    assert "is not checked out" in results["homebrew"].lines[0]
    assert rc == 1


def test_homebrew_a_failing_dry_run_is_drift(root: pathlib.Path) -> None:
    def failing(version: str) -> subprocess.CompletedProcess:
        del version
        return subprocess.CompletedProcess([], 1, "", "Refusing to reset: uncommitted changes\n")

    result = cp.check_homebrew(root, "1.4.21", "", failing)
    assert result.status == cp.DRIFT
    assert "uncommitted changes" in result.lines[0]


def test_homebrew_a_tap_without_origin_main_is_unchecked(root: pathlib.Path) -> None:
    def offline(version: str) -> subprocess.CompletedProcess:
        del version
        err = "fatal: ambiguous argument 'origin/main': unknown revision or path not in the tree\n"
        return subprocess.CompletedProcess([], 128, "", err)

    with pytest.raises(cp.UnreadableError, match="origin/main"):
        cp.check_homebrew(root, "1.4.21", "", offline)


def test_homebrew_dry_run_pins_the_git_locale(
    root: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller matches git's English text, so the subprocess env must carry the C locale."""
    seen: dict[str, str] = {}

    def fake(argv: list[str], env: dict[str, str] | None) -> subprocess.CompletedProcess:
        seen.update(env or {})
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    monkeypatch.setenv("LANGUAGE", "de")
    monkeypatch.setattr(cp, "run_process", fake)
    cp.homebrew_dry_run(root)("1.4.21")
    assert seen["LC_ALL"] == "C"
    assert seen["LANG"] == "C"
    assert "LANGUAGE" not in seen


def test_homebrew_a_formula_the_awk_misplaces_is_drift(root: pathlib.Path) -> None:
    """Without the linux `if Hardware::CPU.arm?` line the real awk writes the linux checksums into the wrong slots. The oracle is url-then-sha256 adjacency, not the awk's own state machine, so it sees that."""
    broken = FORMULA.replace(
        "  on_linux do\n    if Hardware::CPU.arm?\n", "  on_linux do\n    if true\n", 1
    )
    assert broken != FORMULA
    cp.formula_path(root).write_text(broken, encoding="utf-8")
    result = cp.check_homebrew(root, "1.4.21", "", ok_dry_run)
    assert result.status == cp.DRIFT, result.lines
    assert any("rdc-linux-arm64" in line for line in result.lines)


def test_homebrew_the_real_rewrite_places_each_checksum() -> None:
    sums = cp.synthetic_checksums()
    rc, rewritten = cp.rewrite_formula(FORMULA, "1.4.21", sums)
    assert rc == 0
    assert cp.formula_findings(FORMULA, rewritten, "1.4.21", sums) == []
    swapped = dict(
        sums, **{"rdc-mac-arm64": sums["rdc-mac-x64"], "rdc-mac-x64": sums["rdc-mac-arm64"]}
    )
    assert cp.formula_findings(FORMULA, rewritten, "1.4.21", swapped), "the oracle missed a swap"


def test_homebrew_checksums_from_a_directory(root: pathlib.Path, tmp_path: pathlib.Path) -> None:
    sums = tmp_path / "sums"
    sums.mkdir()
    for i, name in enumerate(cp.update_homebrew_tap.BINARY_NAMES):
        (sums / ("%s.sha256" % name)).write_text("%064x  %s\n" % (i + 1, name), encoding="utf-8")
    assert cp.check_homebrew(root, "1.4.21", str(sums), ok_dry_run).status == cp.OK
    (sums / "rdc-linux-x64.sha256").unlink()
    with pytest.raises(cp.UnreadableError, match="rdc-linux-x64"):
        cp.read_checksums(sums)


@pytest.mark.parametrize(
    ("objects", "status"),
    [(1000, cp.OK), (1199, cp.OK), (1200, cp.WARN), (1499, cp.WARN), (1500, cp.DRIFT)],
)
def test_promotion_thresholds(root: pathlib.Path, objects: int, status: str) -> None:
    state = healthy()
    state["channel_objects"]["edge"] = objects
    assert run(state, "1.4.21", root=root, checks=("promotion",))[1]["promotion"].status == status


def test_promotion_an_empty_channel_is_unchecked(root: pathlib.Path) -> None:
    state = healthy()
    state["channel_objects"]["edge"] = 0
    result = run(state, "1.4.21", root=root, checks=("promotion",))[1]["promotion"]
    assert result.status == cp.UNCHECKED
    assert "ZERO objects" in result.lines[0]


# --------------------------------------------------------------------------- live readers ---------------------------------------------------------------------------

CREDS = {
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "id",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "secret",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example",
}


class FakeRunner:
    def __init__(self, answers: dict[str, subprocess.CompletedProcess]) -> None:
        self.answers = answers
        self.calls: list[tuple[list[str], dict[str, str] | None]] = []

    def __call__(self, argv: list[str], env: dict[str, str] | None) -> subprocess.CompletedProcess:
        self.calls.append((argv, env))
        for needle, answer in self.answers.items():
            if needle in " ".join(argv):
                return answer
        raise AssertionError("unexpected call %r" % argv)


def done(rc: int, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, out, err)


def test_live_sentinels_parse_the_gates_argv_and_map_the_credentials(
    tmp_path: pathlib.Path,
) -> None:
    runner = FakeRunner(
        {
            "list-objects-v2": done(
                0, "cli/v1.0.0/.released\tcli/v1.0.1/.released\tcli/v1.0.2-rc.1/.released\n"
            )
        }
    )
    live = cp.LiveReaders(tmp_path, "origin", dict(CREDS), runner)
    assert live.sentinels() == ["v1.0.0", "v1.0.1"]
    argv, env = runner.calls[0]
    assert argv[-2:] == ["--endpoint-url", "https://r2.example"]
    assert env is not None
    assert env["AWS_ACCESS_KEY_ID"] == "id"
    assert env["AWS_DEFAULT_REGION"] == "auto"


def test_live_a_failed_aws_is_unreadable_never_an_empty_list(tmp_path: pathlib.Path) -> None:
    """The difference from `release_state.list_sentinels`, which answers [] here."""
    runner = FakeRunner(
        {"list-objects-v2": done(255, "", "Could not connect to the endpoint URL\n")}
    )
    with pytest.raises(cp.UnreadableError, match="aws exited 255: Could not connect"):
        cp.LiveReaders(tmp_path, "origin", dict(CREDS), runner).sentinels()


def test_live_missing_aws_and_missing_credentials_are_named(tmp_path: pathlib.Path) -> None:
    runner = FakeRunner({"aws": done(127, "", "aws: command not found\n")})
    with pytest.raises(cp.UnreadableError, match="aws CLI is not installed"):
        cp.LiveReaders(tmp_path, "origin", dict(CREDS), runner).tracker()
    with pytest.raises(cp.UnreadableError, match=r"CLOUDFLARE_R2_ENDPOINT not set.*bws_env"):
        cp.LiveReaders(
            tmp_path,
            "origin",
            {"CLOUDFLARE_R2_ACCESS_KEY_ID": "id", "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "s"},
            runner,
        ).pointer("edge", "latest.json")


def test_live_tags_peel_annotated_tags_and_fail_closed(tmp_path: pathlib.Path) -> None:
    listing = "aaa\trefs/tags/v1.0.0\nbbb\trefs/tags/v1.0.0^{}\nccc\trefs/tags/production\n"
    runner = FakeRunner({"ls-remote": done(0, listing)})
    assert cp.LiveReaders(tmp_path, "origin", {}, runner).tags() == {
        "v1.0.0": "bbb",
        "production": "ccc",
    }
    failing = FakeRunner({"ls-remote": done(128, "", "fatal: could not read Username\n")})
    with pytest.raises(cp.UnreadableError, match="could not read Username"):
        cp.LiveReaders(tmp_path, "origin", {}, failing).tags()


def test_live_tracker_and_pointer_refuse_what_they_cannot_read(tmp_path: pathlib.Path) -> None:
    live = cp.LiveReaders(
        tmp_path, "origin", dict(CREDS), FakeRunner({"versions.json": done(0, "not json")})
    )
    with pytest.raises(cp.UnreadableError, match="not JSON"):
        live.tracker()
    live = cp.LiveReaders(
        tmp_path,
        "origin",
        dict(CREDS),
        FakeRunner({"versions.json": done(0, '["v1.0.1","1.0.0"]')}),
    )
    assert live.tracker() == ["1.0.1", "1.0.0"]
    live = cp.LiveReaders(
        tmp_path, "origin", dict(CREDS), FakeRunner({"latest.json": done(0, "{}")})
    )
    with pytest.raises(cp.UnreadableError, match="names no version"):
        live.pointer("edge", "latest.json")


def test_live_channel_objects_counts_every_directory_and_reads_an_empty_prefix(
    tmp_path: pathlib.Path,
) -> None:
    listing = "2026-10-01 00:00:00  12 apt/edge/a\n2026-10-01 00:00:00  12 apt/edge/b\n"
    runner = FakeRunner(
        {
            "apt/edge": done(0, listing),
            "rpm/edge": done(1),
            "apk/edge": done(0, listing),
            "archlinux/edge": done(0, listing),
        }
    )
    assert cp.LiveReaders(tmp_path, "origin", dict(CREDS), runner).channel_objects("edge") == 6
    broken = FakeRunner({"apt/edge": done(0, listing), "rpm/edge": done(1, "", "AccessDenied\n")})
    with pytest.raises(cp.UnreadableError, match="AccessDenied"):
        cp.LiveReaders(tmp_path, "origin", dict(CREDS), broken).channel_objects("edge")


def test_live_ratchet_reads_the_floor_file_and_refuses_a_missing_one(
    tmp_path: pathlib.Path,
) -> None:
    live = cp.LiveReaders(tmp_path, "origin", {}, FakeRunner({}))
    with pytest.raises(cp.UnreadableError, match="unreadable"):
        live.ratchet()
    floor = tmp_path / release_state.FLOOR_FILE_REL
    floor.parent.mkdir(parents=True)
    floor.write_text("# comment\nv1.3.1\n", encoding="utf-8")
    assert live.ratchet() == "v1.3.1"


def test_a_zero_sentinel_answer_is_unchecked_not_contract_not_in_effect(root: pathlib.Path) -> None:
    state = healthy()
    state["sentinels"] = []
    results = run(state, "1.4.21", root=root)[1]
    assert results["a"].status == cp.UNCHECKED
    assert "ZERO cli sentinels" in results["a"].lines[0]


# --------------------------------------------------------------------------- the CLI ---------------------------------------------------------------------------


def test_cli_replays_the_10_07_state_from_a_json_snapshot(
    root: pathlib.Path,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"state": replay_10_07()}), encoding="utf-8")
    argv = ["--phase", "pr", "--release-version", "0.0.0", "--checks", "a,c"]
    argv += ["--state", str(state_file)]
    assert cp.main(argv, dry_run=ok_dry_run) == 1
    out = capsys.readouterr().out
    assert "[a] DRIFT: bijection now" in out
    assert (
        "::error title=cd-preflight (a)::DRIFT v1.3.1: cli sentinel present, git tag missing\n"
        in out
    )
    assert out.rstrip().endswith("1 DRIFT, 0 UNCHECKED, 4 SKIPPED -> FAIL")


def test_cli_json_round_trips_into_a_replay(
    root: pathlib.Path,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What a live run prints under --json is exactly what --state replays, unchecked answers included."""
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    state = healthy()
    state["tracker"] = {"unchecked": "aws exited 1"}
    argv = ["--phase", "pr", "--release-version", "1.4.21", "--json"]
    assert cp.main(argv, readers=cp.replay_readers(state), dry_run=ok_dry_run) == 1
    first = json.loads(capsys.readouterr().out)
    assert first["state"]["tracker"] == {"unchecked": "aws exited 1"}
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(first), encoding="utf-8")
    assert cp.main([*argv, "--state", str(state_file)], dry_run=ok_dry_run) == 1
    second = json.loads(capsys.readouterr().out)
    assert second["results"] == first["results"]


def test_cli_dry_run_is_not_a_verdict(capsys: pytest.CaptureFixture[str]) -> None:
    assert cp.main(["--phase", "cd", "--release-version", "2.2.0", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "git ls-remote --tags origin" in out
    assert out.rstrip().endswith("this is NOT a verdict.")


def test_cli_a_narrowed_run_prints_what_it_skipped(
    root: pathlib.Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    argv = ["--phase", "pr", "--release-version", "1.4.21", "--checks", "a,d"]
    assert cp.main(argv, readers=cp.replay_readers(healthy())) == 0
    out = capsys.readouterr().out
    assert "[homebrew] SKIPPED: homebrew formula" in out
    assert "2 OK, 0 WARN, 0 DRIFT, 0 UNCHECKED, 4 SKIPPED -> PASS" in out


@pytest.mark.parametrize(
    "argv",
    [
        ["--phase", "pr", "--release-version", "2.2"],
        ["--phase", "pr", "--release-version", "2.2.0", "--checks", "a,z"],
        ["--phase", "pr", "--release-version", "2.2.0", "--checks", ","],
    ],
)
def test_cli_refuses_a_bad_argument(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert cp.main(argv) == 2
    assert capsys.readouterr().err.startswith("cd-preflight: ")


def test_a_warning_annotation_quotes_the_drift_not_the_passing_steps() -> None:
    """The live run of 2026-10-08 printed (b)'s warning as its last two lines, both "holds"."""
    result = cp.Result(
        "b",
        cp.WARN,
        (
            "projected from 20 sentinels",
            "after housekeeping before the release:",
            "  DRIFT v1.3.2: cli sentinel present, git tag missing",
            "    remediation: re-run CD",
            "after the release of v2.2.1: holds (20 sentinels, 21 tags)",
        ),
    )
    rendered = cp.render([result], "2.2.1", "pr")
    assert (
        "::warning title=cd-preflight (b)::DRIFT v1.3.2: cli sentinel present, git tag missing"
        in rendered
    )
