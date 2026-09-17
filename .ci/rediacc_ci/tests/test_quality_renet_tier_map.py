"""`rediacc_ci.quality.renet_tier_map` against the shell it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. This gate's verdict is decided by two text transforms and one regular expression, and each of the three has an edge that is not inferable:

  * `go test -list <re> <pkg> | grep '^Test' | sort` -- the `grep` is not
    cosmetic. `go test -list` also prints the package result line
    (`ok  <pkg>  0.002s`), which would otherwise join the comparison and make
    phase 1 fail on every run. And `sort` is the locale's, which is why both
    sides are pinned to `LC_ALL=C`.
  * `grep -q -- "--- PASS: $name"` is a SUBSTRING test, so a subtest's own PASS
    line satisfies its parent. That is the twin's behaviour and the port keeps
    it.
  * `RUN_REGEX` is a Go regexp used by `go test`, and the same string is used by
    the port only for a control. If the two ever disagree, phase 1 verifies a
    different set from the one phase 2 runs.

They are NOT the whole gate: the whole gate is what the committed shadow ledger `.ci/shadow/w7p2-renet-tiermap.observations.jsonl` compares over five distinct trees, against a minimal Go package standing in for `pkg/functions`. This file covers the seams that ledger cannot isolate.
"""

import pathlib
import shutil
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import renet_tier_map as tm
from rediacc_ci.tests import differential as diff

_LIST_PIPELINE = "grep '^Test' listing.txt | sort || true"

LISTING_CASES = [
    ("\n".join(tm.EXPECTED_TESTS) + "\nok  \tm/pkg/functions\t0.002s\n", "the real shape"),
    ("ok  \tm/pkg/functions\t0.002s\n", "ONLY the result line, which selects nothing"),
    ("testing: warning: no tests to run\nPASS\nok  \tm/pkg\t0.001s\n", "the vacuity shape"),
    ("\n".join(reversed(tm.EXPECTED_TESTS)) + "\n", "reverse order, which sort fixes"),
    ("TestB\nTestA\nTestC\n", "plain names"),
    ("BenchmarkX\nTestA\n", "a Benchmark is not a Test"),
    ("  TestIndented\n", "an indented name does not anchor"),
    ("TestA\nTestA\n", "a duplicate is KEPT, because sort has no -u here"),
    ("", "the empty listing"),
]


@pytest.mark.parametrize(("content", "why"), LISTING_CASES)
def test_listed_from_matches_the_shell_pipeline(
    tmp_path: pathlib.Path, content: str, why: str
) -> None:
    (tmp_path / "listing.txt").write_text(content, encoding="utf-8")
    code, out, err = diff.bash_streams(_LIST_PIPELINE, cwd=str(tmp_path))
    assert code == 0, err
    expected = [line for line in out.split("\n") if line != ""]
    assert tm.listed_from(content) == expected, why


def test_the_listing_table_exercises_both_directions() -> None:
    parsed = [tm.listed_from(c) for c, _why in LISTING_CASES]
    assert any(parsed), "no case selects anything"
    assert any(not p for p in parsed), "every case selects something"


def test_wanted_matches_the_shell_sort() -> None:
    """`printf '%s\\n' "${EXPECTED_TESTS[@]}" | sort`, against the real sort.

    Pinned to LC_ALL=C explicitly. The seven names are ASCII, so the two agree,
    and asserting it here is what would catch a name that stopped being ASCII.
    """
    script = "printf '%%s\\n' %s | sort" % " ".join(tm.EXPECTED_TESTS)
    code, out, err = diff.bash_streams(script, env=diff.env_for())
    assert code == 0, err
    assert tm.wanted() == [line for line in out.split("\n") if line != ""]


# NAMED AWAY FROM "PASS" ON PURPOSE. `S105` flags any constant whose name contains PASS as a hardcoded credential, and it is right to be crude about that; the rule is not disabled for one shell snippet. This greps a go-test transcript for the tests that did not report success, so it is named for that.
_TESTS_WITHOUT_SUCCESS_LOOP = (
    """for t in %s; do grep -q -- "--- PASS: $t" run.txt || echo "$t"; done"""
)


PASS_CASES = [
    (tm._PASSING_RUN, "everything passed"),
    (
        tm._PASSING_RUN.replace(
            "--- PASS: TestTierMapGateCanFail", "--- SKIP: TestTierMapGateCanFail"
        ),
        "one SKIPPED",
    ),
    (
        tm._PASSING_RUN.replace(
            "--- PASS: TestTierMapHasNoOrphans", "--- FAIL: TestTierMapHasNoOrphans"
        ),
        "one FAILED",
    ),
    (
        tm._PASSING_RUN.replace(
            "--- PASS: TestTierMapGateCanFail (0.00s)",
            "    --- PASS: TestTierMapGateCanFail/sub (0.00s)",
        ),
        "a SUBTEST's PASS satisfies its parent, because grep is a substring test",
    ),
    ("", "the empty transcript, where every test is missing"),
    ("PASS\nok  \tm/pkg\t0.001s\n", "a green exit with no per-test lines at all"),
]


@pytest.mark.parametrize(("content", "why"), PASS_CASES)
def test_missing_passes_matches_the_grep_loop(
    tmp_path: pathlib.Path, content: str, why: str
) -> None:
    """Phase 3, run for real. The order is EXPECTED's, in both implementations."""
    (tmp_path / "run.txt").write_text(content, encoding="utf-8")
    code, out, err = diff.bash_streams(
        _TESTS_WITHOUT_SUCCESS_LOOP % " ".join(tm.EXPECTED_TESTS), cwd=str(tmp_path)
    )
    assert code == 0, err
    assert tm.missing_passes(content) == [line for line in out.split("\n") if line != ""], why


def test_the_pass_table_exercises_both_directions() -> None:
    results = [tm.missing_passes(c) for c, _why in PASS_CASES]
    assert any(not r for r in results), "no case is fully green"
    assert any(r for r in results), "no case is missing anything"


def test_the_run_regex_selects_exactly_the_expected_set_under_go() -> None:
    """Go's own regexp engine, not Python's, because `go test` is the consumer.

    A `re.match` control lives in the module's selftest and proves the port's understanding. This proves the SHELL's: `go test -list` is what actually applies the pattern, and a Go/Python regexp divergence here would make phase 1 verify a set phase 2 never runs.
    """
    if shutil.which("go") is None:
        pytest.skip("no Go toolchain on this host; the ledger covers this end to end")

    # A throwaway module so the check does not depend on the submodule being present, and so it cannot be satisfied by whatever renet currently holds.
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "go.mod").write_text("module probe\n\ngo 1.21\n", encoding="utf-8")
        pkg = root / "pkg" / "functions"
        pkg.mkdir(parents=True)
        names = (*tm.EXPECTED_TESTS, "TestSomethingElse", "TestTierProbeOther")
        body = ["package functions", "", 'import "testing"']
        body.extend("func %s(t *testing.T) {}" % name for name in names)
        (pkg / "probe_test.go").write_text("\n".join(body) + "\n", encoding="utf-8")

        code, out, err = diff.bash_streams(
            "go test -list '%s' ./pkg/functions/" % tm.RUN_REGEX,
            cwd=str(root),
            env=diff.env_for(GOTOOLCHAIN="auto", GOFLAGS="-mod=mod", GOPATH=None),
            timeout=180,
        )
        assert code == 0, err
        assert tm.listed_from(out) == tm.wanted()


def test_the_expected_list_still_matches_the_bash_twins_array() -> None:
    """Drift between the two copies would make one of them verify nothing.

    Read out of the twin rather than transcribed, so the assertion cannot be satisfied by editing this file.
    """
    twin = paths.repo_root() / ".ci/scripts/quality/check-renet-tier-map.sh"
    text = twin.read_text(encoding="utf-8")
    body = text.split("EXPECTED_TESTS=(", 1)[1].split(")", 1)[0]
    names = [line.strip() for line in body.split("\n") if line.strip().startswith("Test")]
    assert names == list(tm.EXPECTED_TESTS)


def test_the_run_regex_still_matches_the_bash_twins() -> None:
    twin = paths.repo_root() / ".ci/scripts/quality/check-renet-tier-map.sh"
    text = twin.read_text(encoding="utf-8")
    line = next(row for row in text.split("\n") if row.startswith("RUN_REGEX="))
    assert line.split("=", 1)[1].strip("'") == tm.RUN_REGEX


def test_require_submodule_has_all_three_rungs(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CI rung is the one a port loses, so it is asserted directly."""
    marker = tmp_path / "go.mod"
    monkeypatch.delenv("CI", raising=False)
    assert tm._require_submodule(marker, "Renet submodule") is False
    marker.write_text("module x\n", encoding="utf-8")
    assert tm._require_submodule(marker, "Renet submodule") is True
    marker.unlink()
    monkeypatch.setenv("CI", "true")
    with pytest.raises(SystemExit) as excinfo:
        tm._require_submodule(marker, "Renet submodule")
    assert excinfo.value.code == 1


def test_selftest_passes() -> None:
    assert tm.selftest() == 0
