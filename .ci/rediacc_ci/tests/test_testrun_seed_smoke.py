"""`rediacc_ci.testrun.seed_smoke` against its bash twin `.ci/scripts/test/seed-smoke-test.sh`, with a FAKE `npx`.

The two `wrangler` invocations, the config the second one is handed (read by the fake while the file still exists), the token on `$GITHUB_OUTPUT` and the exit code are compared. Timestamps and the scratch directory are masked. The live Cloudflare D1 write is NOT exercised.

INTENTIONAL DELTAS (Rule T), each a `test_delta_*` that fails on the bash behaviour: an unset `ACCOUNT_JWT_SECRET` no longer falls back to `default`; a non-numeric `PR_NUMBER` is refused; the temporary config is not left behind at a fixed /tmp path; a missing `$GITHUB_OUTPUT` no longer fails after seeding; the token is masked.
"""

from __future__ import annotations

import json
import pathlib
import typing

from rediacc_ci.testrun import seed_smoke
from rediacc_ci.tests import testrun_support as ts

# THE BASH TWIN WRITES AND DELETES THE MACHINE-WIDE /tmp/wrangler-seed.toml, so two twin runs on two xdist workers delete each other's file. One worker runs this whole module.
XDIST_GROUP = "seed-smoke-fixed-tmp"

TWIN = ".ci/scripts/test/seed-smoke-test.sh"
MODULE = "rediacc_ci.testrun.seed_smoke"
LISTING = json.dumps(
    [{"name": "other", "uuid": "x"}, {"name": "account-db-pr-12", "uuid": "uuid-12"}]
)


def env_for(tmp_path: pathlib.Path, **extra: str) -> dict[str, str]:
    return {
        "PR_NUMBER": "12",
        "ACCOUNT_JWT_SECRET": "s3cret",
        "GITHUB_OUTPUT": str(tmp_path / "gh_output"),
        "FAKE_OUT_NPX": LISTING,
        "FAKE_CAT_NPX": "--config",
        **extra,
    }


def both(tmp_path: pathlib.Path, **extra: str) -> tuple[ts.Outcome, ts.Outcome, str, str]:
    outs = []
    for side, runner in (("bash", ts.bash_cmd(TWIN)), ("py", ts.py_cmd(MODULE))):
        directory = tmp_path / side
        directory.mkdir()
        env = env_for(directory, **extra)
        if side == "py":
            env = ts.py_env(env)
        gh = directory / "gh_output"
        if side == "bash":
            outcome = ts.twin_run(TWIN, runner, directory, ("npx",), env, files=(gh,))
        else:
            outcome = ts.run_side(runner, directory, ("npx",), env)
        outs.append((outcome, gh.read_text() if gh.exists() else ""))
    return outs[0][0], outs[1][0], outs[0][1], outs[1][1]


def normalised(outcome: ts.Outcome, directory: pathlib.Path) -> list[dict[str, typing.Any]]:
    calls = []
    for original in outcome.calls:
        call = dict(original)
        masked = [ts.mask(a, directory) for a in original["argv"]]
        call["argv"] = ["<CONFIG>" if a.endswith("wrangler-seed.toml") else a for a in masked]
        calls.append(call)
    return calls


def test_both_sides_seed_the_same_rows_and_token(tmp_path: pathlib.Path) -> None:
    old, new, old_gh, new_gh = both(tmp_path)
    assert old.code == 0
    assert len(old.calls) == 2
    assert normalised(old, tmp_path / "bash") == normalised(new, tmp_path / "py")
    assert old_gh == new_gh
    assert old_gh.startswith("SMOKE_TEST_TOKEN=rdt_smoke_12_")
    assert old.calls[1]["config"] == new.calls[1]["config"]
    assert 'database_id = "uuid-12"' in new.calls[1]["config"]
    assert ts.mask(old.out, tmp_path / "bash") == ts.mask(new.out, tmp_path / "py").replace(
        "::add-mask::" + old_gh.split("=", 1)[1].strip() + "\n", ""
    )


def test_missing_database_fails_the_same_way(tmp_path: pathlib.Path) -> None:
    old, new, _, _ = both(tmp_path, FAKE_OUT_NPX="[]")
    assert (old.code, new.code) == (1, 1)
    assert "Database account-db-pr-12 not found" in old.err
    assert "Database account-db-pr-12 not found" in new.err
    assert len(old.calls) == len(new.calls) == 1


def test_execute_failure_exit_code_is_wranglers(tmp_path: pathlib.Path) -> None:
    old, new, _, _ = both(tmp_path, FAKE_RC_NPX="4", FAKE_RCWHEN_NPX="execute")
    assert (old.code, new.code) == (4, 4)
    assert len(old.calls) == len(new.calls) == 2


def test_missing_pr_number_matches(tmp_path: pathlib.Path) -> None:
    old, new, _, _ = both(tmp_path, PR_NUMBER="")
    assert old.code == new.code == 1
    assert "PR_NUMBER is required" in old.err
    assert "PR_NUMBER is required" in new.err


def test_derive_is_the_twins_token_shape() -> None:
    d = seed_smoke.derive("7", "k", "NOW")
    assert d["token"] == "rdt_smoke_7_" + seed_smoke.sha256_hex("k")[:32]
    assert d["token_hash"] == seed_smoke.sha256_hex(d["token"])
    assert d["email_hash"] == seed_smoke.sha256_hex("smoketest-pr7@rediacc.io")


# ---- intentional deltas --------------------------------------------------------------------------------------------------


def test_delta_unset_jwt_secret_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_gh, _ = both(tmp_path, ACCOUNT_JWT_SECRET="")
    assert old.code == 0
    assert (
        old_gh.strip() == "SMOKE_TEST_TOKEN=rdt_smoke_12_" + seed_smoke.sha256_hex("default")[:32]
    ), "bash seeded a token derived from the word default"
    assert new.code == 1
    assert len(new.calls) == 0
    assert "ACCOUNT_JWT_SECRET is required" in new.err


def test_delta_non_numeric_pr_number_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, _, _ = both(tmp_path, PR_NUMBER="1'; DROP TABLE users; --")
    assert old.calls, "bash interpolated the text into SQL and into a config"
    assert new.code == 1
    assert not new.calls


def test_delta_no_fixed_tmp_config_is_left_behind(tmp_path: pathlib.Path) -> None:
    leftover = pathlib.Path("/tmp/wrangler-seed.toml")
    old, new, _, _ = both(tmp_path, FAKE_RC_NPX="")
    # Bash writes and removes the fixed path on success; on a failed execute it stays. The port's config lives in its own private temp directory. The fixed path's EXISTENCE is not asserted: every twin run in this module writes and deletes it, so its state at any instant belongs to whichever twin ran last (a 2-in-5 flake under -n 8, 2026-10-01).
    new_cfg = new.calls[1]["argv"][new.calls[1]["argv"].index("--config") + 1]
    old_cfg = old.calls[1]["argv"][old.calls[1]["argv"].index("--config") + 1]
    assert pathlib.Path(new_cfg).name == "wrangler-seed.toml"
    assert new_cfg != str(leftover)
    assert pathlib.Path(new_cfg).parent != pathlib.Path("/tmp")
    assert old_cfg == str(leftover)


def test_delta_missing_github_output_prints_the_token(tmp_path: pathlib.Path) -> None:
    old, new, _, _ = both(tmp_path, GITHUB_OUTPUT="")
    assert old.code != 0, "bash failed after it had already seeded"
    assert new.code == 0
    assert "SMOKE_TEST_TOKEN=rdt_smoke_12_" in new.out


def test_delta_token_is_masked(tmp_path: pathlib.Path) -> None:
    old, new, _, _ = both(tmp_path)
    assert "::add-mask::" not in old.out
    assert "::add-mask::rdt_smoke_12_" in new.out
