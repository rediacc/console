"""`rediacc_ci.deploy.test_d1_migrations`: the migration test against a clone of every region's database.

PORT ONLY. The bash twin tested the edge databases first and then the stable ones, created every clone `--location eeur`, and named them `migration-test-<edge|stable>-<region>-...`. One shared database per region replaced both lists, and the clone is created where the region's own `d1.location` in regions.json says, so the frozen twin golden (`goldens/twins/deploy.test-d1-migrations.jsonl`) no longer describes this module and this file pins the port's own behaviour. The golden file is orphaned by this change; pruning it is `regolden`'s job (named in the box report).

A RECORDING FAKE FOR `npx` ON A SCRATCH PATH, INSIDE A FIXTURE REPO. Nothing here reaches Cloudflare; every case pins a fixture token, account and D1 state file. THE CLONE IS NOT STUBBED: the port runs the real `clone_d1`, which reaches `npx --no-install wrangler d1 export` and `d1 execute` (modelled below), so the call log covers the callers and the clone together.

THE CALL LOG AND THE GENERATED CONFIG ARE THE EVIDENCE, because what a run PRINTS is `::group::` directives and one summary line, while the observable effect is the ordered `npx --no-install wrangler d1` invocations.
"""

from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import test_d1_migrations as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "test_d1_migrations.py"

BASE_ENV = {
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
    "CLOUDFLARE_ACCOUNT_ID": "acct-fixture",
    "GITHUB_RUN_ID": "777",
    "GITHUB_RUN_ATTEMPT": "2",
}

# Two regions with DIFFERENT locations, so a port that hard-coded one location (the retired `eeur`) is visible rather than coincidentally right.
DEFAULT_REGIONS = {
    "regions": [
        {"id": "eu", "d1": {"name": "account-eu", "location": "eeur"}},
        {"id": "us", "d1": {"name": "account-us", "location": "enam"}},
    ]
}

# A MODEL of `wrangler d1`, not wrangler. It has to serve `clone_d1` as well as the script under test, so `d1 export` and `d1 execute` are modelled too.
FAKE_NPX = r'''#!/usr/bin/python3
"""Recording fake for `npx`. See the test module docstring."""
import json
import os
import sys

argv = sys.argv[1:]
log = os.environ["FAKE_CALL_LOG"]
state_file = os.environ["FAKE_D1_STATE"]


def emit(text):
    with open(log, "a") as fh:
        fh.write(text)


emit("call: npx %s\n" % " ".join(argv))

with open(log) as fh:
    call_index = len([line for line in fh if line.startswith("call: ")])
fail_on = os.environ.get("FAKE_NPX_FAIL_ON_CALL", "")
if fail_on and str(call_index) == fail_on:
    sys.stderr.write("wrangler: a fixture failure was injected on call %d\n" % call_index)
    sys.exit(1)


def load():
    try:
        with open(state_file) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def save(state):
    with open(state_file, "w") as fh:
        json.dump(state, fh)


rest = argv[2:] if argv[:2] == ["--no-install", "wrangler"] else None
if rest is None:
    sys.stderr.write("fake npx: unmodelled tool %r\n" % (argv[:1],))
    sys.exit(127)

state = load()

if rest[:2] == ["d1", "create"]:
    name = rest[2]
    state[name] = "uuid-for-%s" % name
    save(state)
    sys.stdout.write("Created database %s\n" % name)
    sys.exit(0)

if rest[:2] == ["d1", "info"]:
    name = rest[2]
    if os.environ.get("FAKE_D1_INFO_HAS_NO_UUID") == "1":
        sys.stdout.write(" wrangler 4.0.0 (fixture)\n")
        sys.stdout.write(json.dumps({"name": name}, indent=2) + "\n")
        sys.exit(0)
    if name not in state:
        sys.stderr.write("wrangler: no D1 database named %s\n" % name)
        sys.exit(1)
    sys.stdout.write(" wrangler 4.0.0 (fixture)\n")
    sys.stdout.write("-------------------\n")
    sys.stdout.write(json.dumps({"uuid": state[name], "name": name}, indent=2) + "\n")
    sys.exit(0)

if rest[:2] == ["d1", "delete"]:
    name = rest[2]
    if os.environ.get("FAKE_D1_DELETE_FAILS") == "1":
        sys.stderr.write("wrangler: could not delete %s\n" % name)
        sys.exit(1)
    state.pop(name, None)
    save(state)
    sys.stdout.write("Deleted database %s\n" % name)
    sys.exit(0)

if rest[:2] == ["d1", "export"]:
    out = ""
    for i, a in enumerate(rest):
        if a.startswith("--output="):
            out = a.split("=", 1)[1]
    if out:
        with open(out, "w") as fh:
            fh.write('CREATE TABLE "users" (id INTEGER PRIMARY KEY);\n')
            fh.write("INSERT INTO users VALUES (1);\n")
    sys.stdout.write("Exported to a presigned URL, valid for one hour\n")
    sys.exit(0)

if rest[:2] == ["d1", "execute"]:
    if "--json" in rest:
        sys.stdout.write(json.dumps([{"results": []}]) + "\n")
    else:
        sys.stdout.write("Executed against the target database\n")
    sys.exit(0)

if rest[:3] == ["d1", "migrations", "apply"]:
    sys.stdout.write("No migrations to apply!\n")
    sys.exit(0)

sys.stderr.write("fake wrangler: unmodelled subcommand %r\n" % (rest,))
sys.exit(127)
'''

# `clone-d1.sh` reaches for all of these, plus the ones the script under test needs. `du`, `wc` and `cut` are the export size report; `grep` is the R2 URL redaction; `mktemp` is its scratch directory.
PATH_MINIMUM = (
    "cat",
    "jq",
    "sed",
    "grep",
    "tr",
    "rm",
    "wc",
    "du",
    "cut",
    "mktemp",
    "uname",
    "dirname",
    "basename",
    "env",
)


def _bin(root: pathlib.Path, *, drop: str = "") -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        link = stub / real_name
        if real_name == drop:
            if link.is_symlink() or link.exists():
                link.unlink()
            continue
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        if not link.exists():
            link.symlink_to(real)
    npx = stub / "npx"
    if drop == "npx":
        if npx.exists():
            npx.unlink()
    else:
        npx.write_text(FAKE_NPX, encoding="utf-8")
        npx.chmod(0o755)
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def fixture(
    tmp_path: pathlib.Path,
    *,
    regions: dict | None = DEFAULT_REGIONS,
    worker_dir: bool = True,
) -> pathlib.Path:
    """A throwaway repository holding common.sh and regions.json.

    `regions=None` REMOVES regions.json entirely, which is the input for fact 1.
    """
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / ".ci" / "config" / "well-known.env", root / ".ci" / "config" / "well-known.env"
    )
    shutil.copy2(
        ROOT / ".ci" / "config" / "well-known.generated.sh",
        root / ".ci" / "config" / "well-known.generated.sh",
    )

    if worker_dir:
        (root / "workers" / "www").mkdir(parents=True, exist_ok=True)
    if regions is not None:
        (root / "regions.json").write_text(json.dumps(regions, indent=2), encoding="utf-8")

    for side in ("old", "new"):
        (root / f"{side}-d1.json").write_text(
            json.dumps({"account-eu": "u1", "account-us": "u2"}), encoding="utf-8"
        )
    return root


def _run(
    root: pathlib.Path,
    *,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    """`(CompletedProcess, call log)` of one live run of the port."""
    call_log = root / "new-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(root, drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(root),
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_D1_STATE": str(root / "new-d1.json"),
        **BASE_ENV,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    proc = subprocess.run(
        [sys.executable, str(PORT_FILE)],
        # cwd IS DELIBERATELY NOT THE FIXTURE ROOT: the port derives the root from $REDIACC_CI_ROOT and then `cd`s to it.
        cwd=str(root.parent),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def _calls(log: str) -> list[str]:
    return [line[len("call: ") :] for line in log.splitlines() if line.startswith("call: ")]


def _wrangler_verbs(log: str) -> list[str]:
    """The `d1 <verb>` pairs, which is the shape of the whole run."""
    out = []
    for line in _calls(log):
        fields = line.split()
        if fields[:3] == ["npx", "--no-install", "wrangler"] and fields[3:4] == ["d1"]:
            out.append(" ".join(fields[3:5]))
    return out


# --------------------------------------------------------------------------- The happy path ---------------------------------------------------------------------------


def test_happy_path_runs_every_region_then_the_cleanup(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, calls = _run(root)
    assert proc.returncode == 0, proc.stderr
    # Two regions, each: create, info, the clone's export plus two executes, one migrations apply. Then two deletes from the trap.
    assert _wrangler_verbs(calls) == (
        ["d1 create", "d1 info", "d1 export", "d1 execute", "d1 execute", "d1 migrations"] * 2
        + ["d1 delete"] * 2
    ), _wrangler_verbs(calls)
    assert "All 2 regional migration tests passed" in proc.stderr
    assert "edge" not in proc.stderr
    assert "stable" not in proc.stderr


def test_the_clone_is_named_by_region_and_the_group_names_the_source(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, calls = _run(root)
    created = [
        line.split()[5]
        for line in _calls(calls)
        if line.startswith("npx --no-install wrangler d1 create ")
    ]
    assert created == ["migration-test-eu-777-2", "migration-test-us-777-2"], created
    groups = [line for line in proc.stdout.splitlines() if line.startswith("::group::Test")]
    assert groups == [
        "::group::Test migrations against account-eu (eu)",
        "::group::Test migrations against account-us (us)",
    ], groups


def test_each_clone_is_created_in_its_regions_own_location(tmp_path) -> None:
    """The retired hard-coded `--location eeur` would put the us clone in eeur too."""
    root = fixture(tmp_path)
    _proc, calls = _run(root)
    creates = [c for c in _calls(calls) if c.startswith("npx --no-install wrangler d1 create ")]
    assert [c.split()[-2:] for c in creates] == [["--location", "eeur"], ["--location", "enam"]]
    assert port.create_argv("d", "apac")[-2:] == ["--location", "apac"]


def test_a_region_without_a_location_is_refused_before_anything_is_created(tmp_path) -> None:
    regions = {"regions": [{"id": "eu", "d1": {"name": "account-eu"}}]}
    root = fixture(tmp_path, regions=regions)
    proc, calls = _run(root)
    assert proc.returncode == 1
    assert "regions.json names no d1.location for account-eu" in proc.stderr
    assert "d1 create" not in calls, "a guessed location must never create a database"


def test_the_generated_config_is_written_and_removed_after_each_region(tmp_path) -> None:
    """The file is written, used and removed inside one iteration, so nothing survives a successful run."""
    root = fixture(tmp_path)
    proc, _calls_text = _run(root)
    assert proc.returncode == 0, proc.stderr
    assert not (root / "workers" / "www" / port.TMPCONFIG_BASENAME).exists()
    assert port.migration_test_toml("d", "u") == (
        'name = "migration-test"\n'
        'main = "src/index.ts"\n'
        'compatibility_date = "2026-01-20"\n'
        "\n"
        "[[d1_databases]]\n"
        'binding = "DB"\n'
        'database_name = "d"\n'
        'database_id = "u"\n'
        'migrations_dir = "../../private/account/drizzle"\n'
    )


def test_the_cleanup_trap_deletes_every_clone_and_says_so(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, _calls_text = _run(root)
    assert proc.stdout.splitlines()[-4:] == [
        "::group::Cleanup: deleting test databases",
        "  Deleted migration-test-eu-777-2",
        "  Deleted migration-test-us-777-2",
        "::endgroup::",
    ], proc.stdout


def test_a_delete_that_fails_is_reported_as_failed_not_as_deleted(tmp_path) -> None:
    """The old form swallowed stderr, ignored the status and printed `Deleted $db` unconditionally, so a clone left behind announced itself as cleaned up. The warning's WORDING is part of it."""
    root = fixture(tmp_path)
    proc, _calls_text = _run(root, FAKE_D1_DELETE_FAILS="1")
    assert (port.CLEANUP_WARNING % "migration-test-eu-777-2") in proc.stdout
    assert "  Deleted migration-test-eu-777-2" not in proc.stdout


def test_fact_an_unreadable_regions_json_is_a_green_run_that_tested_nothing(tmp_path) -> None:
    """THE VACUITY DEFECT, reproduced rather than repaired: `< <(jq ...)` is a process substitution, so with `regions.json` gone the list is empty, the loop runs zero times, and the run reports success."""
    assert port.AN_EMPTY_REGION_LIST_IS_A_GREEN_RUN is True
    root = fixture(tmp_path, regions=None)
    proc, calls = _run(root)
    assert proc.returncode == 0, proc.stderr
    assert "All 0 regional migration tests passed" in proc.stderr
    assert calls == "", "a run that tested nothing still called wrangler"
    assert proc.stdout.splitlines() == [
        "::group::Cleanup: deleting test databases",
        "::endgroup::",
    ], proc.stdout
    assert "regions.json" in proc.stderr


def test_fact_the_workspace_takes_over_after_the_first_region(tmp_path) -> None:
    """ITERATION 1 RESOLVES AGAINST THE REPO ROOT AND 2..N AGAINST `$GITHUB_WORKSPACE`: the loop `cd workers/www` relatively and then `cd "$WORKSPACE"`."""
    assert port.THE_WORKSPACE_TAKES_OVER_AFTER_THE_FIRST_REGION is True
    root = fixture(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "workers" / "www").mkdir(parents=True)
    proc, calls = _run(root, GITHUB_WORKSPACE=str(elsewhere))
    assert proc.returncode == 0, proc.stderr
    assert len([c for c in _calls(calls) if "migrations apply" in c]) == 2
    assert not (elsewhere / "workers" / "www" / port.TMPCONFIG_BASENAME).exists()
    assert not (root / "workers" / "www" / port.TMPCONFIG_BASENAME).exists()


def test_fact_the_uuid_guard_only_fires_for_valid_json_without_a_uuid(tmp_path) -> None:
    """With `FAKE_D1_INFO_HAS_NO_UUID` the JSON parses and has no `uuid`, so `Failed to get UUID` is printed. With a `d1 info` that EXITS NON-ZERO the pipeline fails under `pipefail`, the assignment fails, and `set -e` ends the run with no message from this script."""
    assert port.THE_UUID_GUARD_IS_ONLY_FOR_VALID_JSON_WITHOUT_A_UUID is True
    root = fixture(tmp_path / "a")
    proc, calls = _run(root, FAKE_D1_INFO_HAS_NO_UUID="1")
    assert proc.returncode == 1
    assert "✗ Failed to get UUID for migration-test-eu-777-2" in proc.stderr
    assert _wrangler_verbs(calls) == ["d1 create", "d1 info", "d1 delete"], _wrangler_verbs(calls)

    root2 = fixture(tmp_path / "b")
    proc2, _calls2 = _run(root2, FAKE_NPX_FAIL_ON_CALL="2")
    assert proc2.returncode == 1
    assert "Failed to get UUID" not in proc2.stderr, proc2.stderr
    assert "::group::Cleanup: deleting test databases" in proc2.stdout


def test_fact_the_generated_config_survives_a_failed_apply(tmp_path) -> None:
    """`rm -f` IS AFTER THE APPLY, so a failed apply leaves the file behind."""
    assert port.THE_GENERATED_CONFIG_SURVIVES_A_FAILED_APPLY is True
    # Call 6 is the first region's `migrations apply`: create, info, export, execute, execute, apply.
    root = fixture(tmp_path)
    proc, _calls_text = _run(root, FAKE_NPX_FAIL_ON_CALL="6")
    assert proc.returncode == 1
    assert (root / "workers" / "www" / port.TMPCONFIG_BASENAME).is_file()


# --------------------------------------------------------------------------- Refusals, and the trap that is not installed yet ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"])
def test_each_required_variable_refuses_before_the_trap_is_installed(tmp_path, missing) -> None:
    """The cleanup block does not print, because `trap cleanup EXIT` is installed after these guards."""
    root = fixture(tmp_path)
    proc, calls = _run(root, drop_env=(missing,))
    assert proc.returncode == 1, proc.stderr
    assert proc.stdout == ""
    assert calls == ""
    assert proc.stderr == "%s: %s is required\n" % (missing, missing), repr(proc.stderr)


def test_an_empty_variable_refuses_exactly_as_an_absent_one_does(tmp_path) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST."""
    root = fixture(tmp_path)
    proc, _calls_text = _run(root, CLOUDFLARE_ACCOUNT_ID="")
    assert proc.returncode == 1
    assert proc.stderr == "CLOUDFLARE_ACCOUNT_ID: CLOUDFLARE_ACCOUNT_ID is required\n"


@pytest.mark.parametrize("tool", ["jq", "npx"])
def test_a_missing_tool_refuses_before_the_variables(tmp_path, tool) -> None:
    """ORDER: `require_cmd jq` then `require_cmd npx`, both BEFORE the two variables, so a run with neither jq nor a token names the tool."""
    root = fixture(tmp_path)
    proc, _calls_text = _run(root, drop=tool, drop_env=tuple(BASE_ENV))
    assert proc.returncode == 1
    assert proc.stderr == "✗ Required command '%s' is not available\n" % tool, repr(proc.stderr)


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_region_id_strips_the_account_prefix_only_when_it_is_there() -> None:
    assert port.region_id("account-eu") == "eu"
    assert port.region_id("account-asia") == "asia"
    # A NAME WITHOUT THE PREFIX IS PASSED THROUGH WHOLE, which is what a regions.json naming its databases anything else would produce.
    assert port.region_id("eu-db") == "eu-db"


def test_test_db_name_has_no_channel_tag() -> None:
    assert port.test_db_name("account-eu", "777", "2") == "migration-test-eu-777-2"
    assert port.test_db_name("account-asia", "local", "1") == "migration-test-asia-local-1"


def test_d1_location_reads_the_regions_own_entry(tmp_path) -> None:
    (tmp_path / "regions.json").write_text(json.dumps(DEFAULT_REGIONS), encoding="utf-8")
    assert port.d1_location(str(tmp_path), "account-eu") == "eeur"
    assert port.d1_location(str(tmp_path), "account-us") == "enam"
    with pytest.raises(port.BashExitError):
        port.d1_location(str(tmp_path), "account-asia")


def test_the_retired_edge_surface_is_gone() -> None:
    for name in ("EDGE_JQ", "STABLE_JQ", "EDGE_PREFIX", "STABLE_PREFIX", "EDGE_TAG", "channel_tag"):
        assert not hasattr(port, name), name
    assert not hasattr(port, "D1_LOCATION"), "the fixed location is read per region now"


def test_read_names_follows_bash_rather_than_python() -> None:
    # A FINAL LINE WITH NO NEWLINE IS DROPPED and an empty line is skipped.
    assert port.read_names("a\nb\n") == ["a", "b"]
    assert port.read_names("a\nb") == ["a"]
    assert port.read_names("a\n\nb\n") == ["a", "b"]
    assert port.read_names("") == []


def test_the_argv_builders_match_the_twins_words() -> None:
    assert port.info_argv("d")[-3:] == ["info", "d", "--json"]
    assert port.delete_argv("d")[-3:] == ["delete", "d", "--skip-confirmation"]
    assert port.migrations_argv("d")[-6:] == [
        "migrations",
        "apply",
        "d",
        "--remote",
        "--config",
        port.TMPCONFIG_BASENAME,
    ]
    assert port.clone_args("s", "t") == ["--source", "s", "--target", "t"]


def test_the_guard_table_and_the_literal_reads_cannot_drift() -> None:
    """`require_env` READS `os.environ` WITH LITERAL KEYS so the env-registry scanner can see them, and `REQUIRED_ENV` is the table it must agree with."""
    assert [name for name, _ in port.REQUIRED_ENV] == [
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
    ]
    source = inspect.getsource(port.require_env)
    for name, _message in port.REQUIRED_ENV:
        assert 'os.environ.get("%s"' % name in source, name


def test_diagnostics_are_prefixed_with_the_module_name() -> None:
    assert port.SELF == "rediacc_ci.deploy.test_d1_migrations"
    assert port.__name__ == port.SELF
