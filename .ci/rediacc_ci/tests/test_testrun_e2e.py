"""`rediacc_ci.testrun.e2e` against its bash twin `.ci/scripts/test/run-e2e.sh`.

Driven with a FAKE `npx` (see `testrun_support`), so what is compared is the exact playwright command line each side builds, its working directory, the zero-skip verdict and the exit code. A real Playwright run needs the KVM fleet and is NOT exercised here.

INTENTIONAL DELTAS (Rule T), each pinned by a test that fails on the bash behaviour, named `test_delta_*`:
  unknown flag, valueless flag, a flag swallowed as a value, options dropped in shard mode, `--also` without a manifest.
"""

from __future__ import annotations

import json
import typing

import pytest

from rediacc_ci.testrun import e2e, shard
from rediacc_ci.tests import testrun_support as ts

if typing.TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/test/run-e2e.sh"
MODULE = "rediacc_ci.testrun.e2e"
TOOLS = ("npx",)


def both(
    tmp_path: pathlib.Path, args: list[str], env: dict[str, str] | None = None
) -> tuple[ts.Outcome, ts.Outcome]:
    base = {"CI": "", "GITHUB_ACTIONS": "", "GITLAB_CI": "", **(env or {})}
    old = ts.run_side(ts.bash_cmd(TWIN, *args), tmp_path / "bash", TOOLS, base)
    new = ts.run_side(ts.py_cmd(MODULE, *args), tmp_path / "py", TOOLS, ts.py_env(base))
    return old, new


def same(old: ts.Outcome, new: ts.Outcome) -> None:
    assert new.calls == old.calls
    assert (new.code, new.out, new.err) == (old.code, old.out, old.err)


def write_manifest(path: pathlib.Path, ids: list[str], of: int = 8, index: int = 1) -> str:
    path.write_text(json.dumps({"of": of, "legs": [{"index": index, "ids": ids}]}))
    return str(path)


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--workers", "2"],
        ["--config", "playwright.ceph.config.ts", "--workers", "1"],
        ["--filter", "system-checks"],
        ["--grep", "@ceph", "--grep-invert", "@slow"],
        ["--test", "tests/a.test.ts", "--test", "tests/b.test.ts"],
        ["--headed", "--debug", "--ui"],
    ],
)
def test_plain_command_matches_the_twin(tmp_path: pathlib.Path, args: list[str]) -> None:
    old, new = both(tmp_path, args)
    assert old.calls, "the fake npx was never reached, so nothing was compared"
    same(old, new)


def test_ci_adds_max_failures_and_one_worker(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, ["--config", "x.ts"], {"CI": "true"})
    assert "--max-failures=3" in old.calls[0]["argv"]
    assert "--workers=1" in old.calls[0]["argv"]
    same(old, new)


def test_playwright_failure_is_exit_one(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, [], {"FAKE_RC_NPX": "7"})
    assert old.code == 1
    same(old, new)


@pytest.mark.parametrize(
    ("out", "verdict"),
    [
        ("ran\nE2E_SKIPPED=0", 0),
        ("ran\nE2E_SKIPPED=3\nx (0.0s, skipped)", 1),
        ("ran without any reporter line", 1),
        ("E2E_SKIPPED=1\nE2E_SKIPPED=2\nfoo (1.0s, skipped)", 1),
    ],
)
def test_zero_skip_gate_matches_the_twin(tmp_path: pathlib.Path, out: str, verdict: int) -> None:
    old, new = both(tmp_path, ["--fail-on-skip"], {"FAKE_OUT_NPX": out})
    assert old.code == verdict
    same(old, new)


def test_zero_skip_gate_off_ignores_skips(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, [], {"FAKE_OUT_NPX": "E2E_SKIPPED=9"})
    assert old.code == 0
    same(old, new)


IDS = [
    "e2e-workers:tests/01-a.test.ts",
    "e2e-workers:tests/13-postgres-fork-isolation.test.ts#part2",
    "e2e-workers:tests/02.b+c.test.ts",
]


def test_shard_leg_matches_the_twin_including_the_regex_escape(tmp_path: pathlib.Path) -> None:
    manifest = write_manifest(tmp_path / "m.json", IDS)
    old, new = both(
        tmp_path,
        ["--shard-manifest", manifest, "--shard", "1/8", "--fail-on-skip"],
        {"CI": "true", "FAKE_OUT_NPX": "E2E_SKIPPED=0"},
    )
    assert old.code == 0
    assert (
        "tests/02\\.b\\+c\\.test\\.ts"
        in old.calls[0]["argv"][old.calls[0]["argv"].index("--grep") + 1]
    )
    same(old, new)


def test_shard_also_and_dedupe_match_the_twin(tmp_path: pathlib.Path) -> None:
    manifest = write_manifest(
        tmp_path / "m.json",
        ["e2e-workers:tests/a.ts", "e2e-workers:tests/a.ts#part1", "e2e-workers:tests/a.ts"],
    )
    old, new = both(
        tmp_path,
        ["--shard-manifest", manifest, "--shard", "1/8", "--also", "tests/x.ts,tests/y.ts"],
    )
    same(old, new)


@pytest.mark.parametrize(
    ("ids", "of", "spec", "needle"),
    [
        (["notours:tests/a.ts"], 8, "1/8", "is not an e2e-workers unit"),
        (
            ["e2e-workers:tests/a.ts#nope"],
            8,
            "1/8",
            "has no entry in E2E_SKIPPED_BUCKETS".replace(
                "E2E_SKIPPED_BUCKETS", "E2E_SHARD_GREP_BUCKETS"
            ),
        ),
        (["e2e-workers:tests/a.ts"], 4, "1/8", "has 4 leg(s); asked for 1/8"),
        ([], 8, "1/8", "no non-empty leg 1"),
        (["e2e-workers:tests/a.ts"], 8, "2/8", "no non-empty leg 2"),
    ],
)
def test_shard_refusals_match_the_twin(
    tmp_path: pathlib.Path, ids: list[str], of: int, spec: str, needle: str
) -> None:
    manifest = write_manifest(tmp_path / "m.json", ids, of=of)
    old, new = both(tmp_path, ["--shard-manifest", manifest, "--shard", spec])
    assert old.code == 1
    assert needle in old.err
    assert not old.calls
    same(old, new)


def test_shard_without_manifest_pair_matches_the_twin(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, ["--shard", "1/8"])
    assert old.code == 1
    same(old, new)


# ---- intentional deltas: each fails on the bash behaviour --------------------------------------------------------------


def test_delta_unknown_flag_is_refused(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, ["--fail-on-skp"], {"FAKE_OUT_NPX": "E2E_SKIPPED=5"})
    assert (old.code, len(old.calls)) == (0, 1), (
        "bash ran the suite with the zero-skip gate silently off"
    )
    assert new.code == 2
    assert not new.calls
    assert "unknown argument: --fail-on-skp" in new.err


def test_delta_valueless_flag_is_refused(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, ["--workers"])
    assert old.code == 0, "bash ignored the flag"
    assert new.code == 2
    assert "--workers needs a value" in new.err


def test_delta_a_flag_is_never_swallowed_as_a_value(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, ["--workers", "--headed", "3"])
    assert "--workers=3" in old.calls[0]["argv"], (
        "bash took the later bare word as the worker count"
    )
    assert new.code == 2
    assert not new.calls


def test_delta_shard_mode_refuses_the_options_it_would_drop(tmp_path: pathlib.Path) -> None:
    manifest = write_manifest(tmp_path / "m.json", ["e2e-workers:tests/a.ts"])
    args = ["--shard-manifest", manifest, "--shard", "1/8", "--config", "other.ts"]
    old, new = both(tmp_path, args)
    assert old.code == 0
    assert "other.ts" not in " ".join(old.calls[0]["argv"]), "bash silently dropped --config"
    assert new.code == 2
    assert "--config cannot be combined with --shard-manifest" in new.err


def test_delta_also_needs_a_manifest(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, ["--also", "tests/x.ts"])
    assert old.code == 0
    assert new.code == 2
    assert "--also needs --shard-manifest" in new.err


# ---- units ---------------------------------------------------------------------------------------------------------------


def test_js_escape_matches_node(tmp_path: pathlib.Path) -> None:
    sample = "a.b*c+d?e^f$g{h}i(j)k|l[m]n\\o-p/q r"
    expr = r'process.stdout.write(process.argv[1].replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))'
    done = ts.run_side(["node", "-e", expr, sample], tmp_path, ())
    assert done.out == e2e.js_escape(sample)


def test_shard_spec_must_be_index_over_of() -> None:
    with pytest.raises(shard.ShardError):
        shard.parse_spec("1/x")
    assert shard.parse_spec("3/8") == (3, 8)
