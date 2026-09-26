"""Differential: `rediacc_ci.deploy.test_d1_migrations` against its twin `.ci/scripts/deploy/test-d1-migrations.sh`.

A RECORDING FAKE FOR `npx` ON A SCRATCH PATH, INSIDE A FIXTURE REPO. Nothing here reaches Cloudflare; every case pins a fixture token, account and D1 state file. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece.

`clone-d1.sh` IS THE REAL SCRIPT, COPIED INTO THE FIXTURE AND RUN BY BOTH SIDES. It is not stubbed, because the twin invokes it and so does the port, and running the same bytes on both sides is what makes the comparison about the two callers rather than about a stub. It reaches `npx wrangler d1 export` and `d1 execute`, which the same fake `npx` models: an export writes a small SQL
file, an execute reports success, and `PRAGMA foreign_key_check` answers with an
empty result set. Its own output is therefore part of what the two sides are compared on.

THE CALL LOG AND THE GENERATED CONFIG ARE THE EVIDENCE, for the reason the module under test spells out: what the run PRINTS is `::group::` directives and one summary line, while the observable effect is the ordered `npx wrangler d1` invocations, one clone per region, and the bytes of the generated `wrangler-migration-test.toml`.

BOTH SIDES GET THEIR OWN D1 STATE FILE, because a run creates and deletes databases in it.
"""

from __future__ import annotations

import inspect
import json
import os
import re
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
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "test-d1-migrations.sh"
CLONE = ROOT / ".ci" / "scripts" / "deploy" / "clone-d1.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "test_d1_migrations.py"
BASH = shutil.which("bash") or "/bin/bash"

BASE_ENV = {
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
    "CLOUDFLARE_ACCOUNT_ID": "acct-fixture",
    "GITHUB_RUN_ID": "777",
    "GITHUB_RUN_ATTEMPT": "2",
}

# Two regions rather than the tree's three, so the "edge first, then stable" ordering is four entries long and a port that interleaved them would be visible rather than merely differently sorted.
DEFAULT_REGIONS = {
    "regions": [
        {"id": "eu", "d1": {"name": "account-db-eu"}, "edgeD1": {"name": "edge-account-db-eu"}},
        {"id": "us", "d1": {"name": "account-db-us"}, "edgeD1": {"name": "edge-account-db-us"}},
    ]
}

# A MODEL of `wrangler d1`, not wrangler. It has to serve `clone-d1.sh` as well as the script under test, so `d1 export` and `d1 execute` are modelled too.
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


rest = argv[1:] if argv[:1] == ["wrangler"] else None
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
    """A throwaway repository holding the twin, clone-d1.sh, common.sh and regions.json.

    `regions=None` REMOVES regions.json entirely, which is the input for fact 1.
    """
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    shutil.copy2(CLONE, root / ".ci" / "scripts" / "deploy" / CLONE.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)

    if worker_dir:
        (root / "workers" / "www").mkdir(parents=True, exist_ok=True)
    if regions is not None:
        (root / "regions.json").write_text(json.dumps(regions, indent=2), encoding="utf-8")

    for side in ("old", "new"):
        (root / f"{side}-d1.json").write_text(
            json.dumps({"account-db-eu": "u1", "account-db-us": "u2"}), encoding="utf-8"
        )
    return root


def _run(
    root: pathlib.Path,
    side: str,
    *,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    call_log = root / f"{side}-calls.log"
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
        "FAKE_D1_STATE": str(root / f"{side}-d1.json"),
        **BASE_ENV,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)

    if side == "old":
        argv = [BASH, str(root / ".ci" / "scripts" / "deploy" / TWIN.name)]
    else:
        argv = [sys.executable, str(PORT_FILE)]
    proc = subprocess.run(
        argv,
        # cwd IS DELIBERATELY NOT THE FIXTURE ROOT. Both sides derive the root
        # from their own location (bash) or from $REDIACC_CI_ROOT (the port) and
        # then `cd` to it; starting elsewhere proves they actually do.
        cwd=str(root.parent),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, *, fixture_kw: dict | None = None, **kw):
    root = fixture(tmp_path, **(fixture_kw or {}))
    old = _run(root, "old", **kw)
    new = _run(root, "new", **kw)
    return root, old, new


# `clone-d1.sh` RUNS `mktemp -d`, so its scratch directory has a fresh random suffix on every invocation and appears in both the call log (as
# `--output=/tmp/tmp.XXXXXXXXXX/export.sql`) and in nothing else. That is the
# ONE thing in this comparison that cannot be equal between two runs of the SAME implementation, so it is masked rather than compared.
#
# THE MASK IS DELIBERATELY NARROW: it matches `mktemp -d`'s own shape, ten alphanumerics after `/tmp/tmp.`, and stops at the word boundary. So the `/export.sql` and `/import.sql` tails, and every other `/tmp/...` path a different implementation might invent, are still compared verbatim. `test_the_mktemp_mask_hides_only_the_random_suffix` asserts both halves rather than leaving the
# claim as a comment.
MKTEMP_DIR = re.compile(r"/tmp/tmp\.[A-Za-z0-9]{10}\b")


def _mask(text: str) -> str:
    return MKTEMP_DIR.sub("/tmp/tmp.<MKTEMP>", text)


def _agree(old, new, label: str) -> None:
    """THE THREE STREAMS SEPARATELY, plus the call log, all mktemp-masked."""
    old_proc, old_calls = old
    new_proc, new_calls = new
    assert new_proc.returncode == old_proc.returncode, (
        f"{label}: exit diverged: {old_proc.returncode!r} vs {new_proc.returncode!r}\n"
        f"old stderr: {old_proc.stderr!r}\nnew stderr: {new_proc.stderr!r}"
    )
    assert _mask(new_proc.stdout) == _mask(old_proc.stdout), (
        f"{label}: stdout diverged:\n{old_proc.stdout!r}\n{new_proc.stdout!r}"
    )
    assert _mask(new_proc.stderr) == _mask(old_proc.stderr), (
        f"{label}: stderr diverged:\n{old_proc.stderr!r}\n{new_proc.stderr!r}"
    )
    assert _mask(new_calls) == _mask(old_calls), (
        f"{label}: call log diverged:\n{old_calls}\n---\n{new_calls}"
    )


def _calls(log: str) -> list[str]:
    return [line[len("call: ") :] for line in log.splitlines() if line.startswith("call: ")]


def _wrangler_verbs(log: str) -> list[str]:
    """The `d1 <verb> <name>` triples, which is the shape of the whole run."""
    out = []
    for line in _calls(log):
        fields = line.split()
        if fields[:2] == ["npx", "wrangler"] and fields[2:3] == ["d1"]:
            out.append(" ".join(fields[2:4]))
    return out


# --------------------------------------------------------------------------- The happy path and the ORDER, which is this script's whole design ---------------------------------------------------------------------------


def test_happy_path_agrees_on_both_streams_and_every_call(tmp_path) -> None:
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "happy")

    proc, calls = old
    assert proc.returncode == 0, proc.stderr

    # PRINT THE SHAPE: four regions, each contributing create, info, the clone's export plus two executes, and one migrations apply. Then four deletes from the trap. A collapse in any of those numbers is what a "both printed the same groups" comparison would miss.
    assert _wrangler_verbs(calls) == (
        ["d1 create", "d1 info", "d1 export", "d1 execute", "d1 execute", "d1 migrations"] * 4
        + ["d1 delete"] * 4
    ), _wrangler_verbs(calls)
    assert "All 4 regional migration tests passed (2 edge + 2 stable)" in proc.stderr


def test_edge_databases_are_tested_before_stable_ones(tmp_path) -> None:
    """THE ORDERING IS THE TWIN'S HEADER'S WHOLE POINT: edge is the soak environment, so a regression must surface there before it can propagate to stable on the next promotion. A port that concatenated the two lists the other way round would print the same four groups and exit 0."""
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "edge-first")

    proc, calls = old
    created = [
        line.split()[4] for line in _calls(calls) if line.startswith("npx wrangler d1 create ")
    ]
    assert created == [
        "migration-test-edge-eu-777-2",
        "migration-test-edge-us-777-2",
        "migration-test-stable-eu-777-2",
        "migration-test-stable-us-777-2",
    ], created
    # AND THE GROUP HEADERS NAME THE SOURCE, so a reader of the log can see it.
    groups = [line for line in proc.stdout.splitlines() if line.startswith("::group::Test")]
    assert groups == [
        "::group::Test migrations against edge-account-db-eu (edge/eu)",
        "::group::Test migrations against edge-account-db-us (edge/us)",
        "::group::Test migrations against account-db-eu (stable/eu)",
        "::group::Test migrations against account-db-us (stable/us)",
    ], groups


def test_the_generated_config_is_byte_identical_and_removed_after_each_region(
    tmp_path,
) -> None:
    """The file is written, used and removed inside one iteration, so nothing survives a successful run. `clone-d1.sh` is what makes this checkable: it runs BETWEEN the write and the apply, and a port that wrote the file later would change the order of the calls around it."""
    root, old, new = run_both(tmp_path)
    _agree(old, new, "generated-config")
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
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "cleanup")

    proc, _calls_text = old
    tail = proc.stdout.splitlines()[-6:]
    assert tail == [
        "::group::Cleanup: deleting test databases",
        "  Deleted migration-test-edge-eu-777-2",
        "  Deleted migration-test-edge-us-777-2",
        "  Deleted migration-test-stable-eu-777-2",
        "  Deleted migration-test-stable-us-777-2",
        "::endgroup::",
    ], tail


def test_a_delete_that_fails_is_reported_as_failed_not_as_deleted(tmp_path) -> None:
    """THE TWIN'S OWN COMMENT CALLS THIS A REPAIR: the old form swallowed stderr, ignored the status and printed `Deleted $db` unconditionally, so a clone left behind announced itself as cleaned up. The warning's WORDING is part of it, and is asserted whole."""
    _root, old, new = run_both(tmp_path, FAKE_D1_DELETE_FAILS="1")
    _agree(old, new, "delete-fails")

    proc, _calls_text = old
    assert proc.returncode == 0, "a failed cleanup must not change the run's status"
    assert (port.CLEANUP_WARNING % "migration-test-edge-eu-777-2") in proc.stdout
    assert "  Deleted migration-test-edge-eu-777-2" not in proc.stdout
    assert "needs manual removal" not in proc.stdout


# --------------------------------------------------------------------------- The four named facts ---------------------------------------------------------------------------


def test_fact_an_unreadable_regions_json_is_a_green_run_that_tested_nothing(
    tmp_path,
) -> None:
    """THE VACUITY DEFECT, and it is the reason this port carries a named constant for it.

    `< <(jq ...)` is a PROCESS SUBSTITUTION, so neither `set -e` nor `pipefail` can see jq's failure. With `regions.json` gone both lists are empty, the loop runs zero times, and the run reports success. Reproduced, not repaired: adding a floor changes what the release pipeline accepts, which is a cutover-box decision.
    """
    assert port.AN_EMPTY_REGION_LIST_IS_A_GREEN_RUN is True

    _root, old, new = run_both(tmp_path, fixture_kw={"regions": None})
    _agree(old, new, "no-regions")

    proc, calls = old
    assert proc.returncode == 0, proc.stderr
    assert "All 0 regional migration tests passed (0 edge + 0 stable)" in proc.stderr
    assert calls == "", "a run that tested nothing still called wrangler"
    assert proc.stdout.splitlines() == [
        "::group::Cleanup: deleting test databases",
        "::endgroup::",
    ], proc.stdout
    # jq's own complaint is the only trace, and it IS on stderr on both sides.
    assert "regions.json" in proc.stderr


def test_fact_the_workspace_takes_over_after_the_first_region(tmp_path) -> None:
    """ITERATION 1 RESOLVES AGAINST THE REPO ROOT AND 2..N AGAINST
    `$GITHUB_WORKSPACE`.

    The loop `cd workers/www` relatively and then `cd "$WORKSPACE"`, so a workspace that is NOT the repository root splits the run in two. Driven with a second tree that has its own `workers/www`: the first region's config lands under the repo root and every later one under the workspace.
    """
    assert port.THE_WORKSPACE_TAKES_OVER_AFTER_THE_FIRST_REGION is True

    root = fixture(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "workers" / "www").mkdir(parents=True)

    old = _run(root, "old", GITHUB_WORKSPACE=str(elsewhere))
    new = _run(root, "new", GITHUB_WORKSPACE=str(elsewhere))
    _agree(old, new, "workspace-split")

    proc, calls = old
    # THE RUN STILL SUCCEEDS, which is what makes this quiet: four regions, four applies, and nothing says the later three used a different tree.
    assert proc.returncode == 0, proc.stderr
    assert len([c for c in _calls(calls) if "migrations apply" in c]) == 4
    # And the workspace tree really was used: its worker directory is where the last three configs were written and removed, so it exists and is empty of the generated file on both sides.
    assert not (elsewhere / "workers" / "www" / port.TMPCONFIG_BASENAME).exists()
    assert not (root / "workers" / "www" / port.TMPCONFIG_BASENAME).exists()


def test_fact_the_uuid_guard_only_fires_for_valid_json_without_a_uuid(tmp_path) -> None:
    """TWO INPUTS, TWO DIFFERENT ENDINGS, and only one of them reaches the guard's own sentence.

    With `FAKE_D1_INFO_HAS_NO_UUID` the JSON parses and has no `uuid`, so jq prints nothing, all three stages exit 0, and `Failed to get UUID` is printed. With a `d1 info` that EXITS NON-ZERO the pipeline fails under `pipefail`, the assignment fails, and `set -e` ends the run with wrangler's status and no message from this script at all.
    """
    assert port.THE_UUID_GUARD_IS_ONLY_FOR_VALID_JSON_WITHOUT_A_UUID is True

    _root, old, new = run_both(tmp_path / "a", FAKE_D1_INFO_HAS_NO_UUID="1")
    _agree(old, new, "no-uuid-key")
    proc, calls = old
    assert proc.returncode == 1
    assert "✗ Failed to get UUID for migration-test-edge-eu-777-2" in proc.stderr
    assert _wrangler_verbs(calls) == ["d1 create", "d1 info", "d1 delete"], _wrangler_verbs(calls)

    # Call 2 is the first `d1 info`. The guard's sentence never appears.
    _root2, old2, new2 = run_both(tmp_path / "b", FAKE_NPX_FAIL_ON_CALL="2")
    _agree(old2, new2, "info-exits-nonzero")
    proc2, _calls2 = old2
    assert proc2.returncode == 1
    assert "Failed to get UUID" not in proc2.stderr, proc2.stderr
    # AND THE TRAP STILL RAN, which is the half a `set -e` exit could have lost.
    assert "::group::Cleanup: deleting test databases" in proc2.stdout


def test_fact_the_generated_config_survives_a_failed_apply(tmp_path) -> None:
    """`rm -f` IS AFTER THE APPLY, so a failed apply leaves the file behind."""
    assert port.THE_GENERATED_CONFIG_SURVIVES_A_FAILED_APPLY is True

    # Call 6 is the first region's `migrations apply`: create, info, export, execute, execute, apply.
    root, old, new = run_both(tmp_path, FAKE_NPX_FAIL_ON_CALL="6")
    _agree(old, new, "apply-fails")
    assert old[0].returncode == 1
    assert (root / "workers" / "www" / port.TMPCONFIG_BASENAME).is_file()


# --------------------------------------------------------------------------- Refusals, and the trap that is not installed yet ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"])
def test_each_required_variable_refuses_before_the_trap_is_installed(tmp_path, missing) -> None:
    """THE ONE NAMED DIVERGENCE, and the half that is NOT a divergence: the cleanup block does not print, because `trap cleanup EXIT` is installed after these guards."""
    root = fixture(tmp_path)
    old_proc, old_calls = _run(root, "old", drop_env=(missing,))
    new_proc, new_calls = _run(root, "new", drop_env=(missing,))

    assert old_proc.returncode == 1, old_proc.stderr
    assert new_proc.returncode == 1, new_proc.stderr
    assert old_proc.stdout == ""
    assert new_proc.stdout == ""
    assert old_calls == ""
    assert new_calls == ""
    tail = "%s: %s is required\n" % (missing, missing)
    assert old_proc.stderr.endswith(tail), repr(old_proc.stderr)
    assert new_proc.stderr == tail, repr(new_proc.stderr)


def test_an_empty_variable_refuses_exactly_as_an_absent_one_does(tmp_path) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST."""
    root = fixture(tmp_path)
    old_proc, _ = _run(root, "old", CLOUDFLARE_ACCOUNT_ID="")
    new_proc, _ = _run(root, "new", CLOUDFLARE_ACCOUNT_ID="")
    assert old_proc.returncode == 1
    assert new_proc.returncode == 1
    tail = "CLOUDFLARE_ACCOUNT_ID: CLOUDFLARE_ACCOUNT_ID is required\n"
    assert old_proc.stderr.endswith(tail)
    assert new_proc.stderr == tail


@pytest.mark.parametrize("tool", ["jq", "npx"])
def test_a_missing_tool_refuses_with_the_same_bytes(tmp_path, tool) -> None:
    """ORDER: `require_cmd jq` then `require_cmd npx`, both BEFORE the two variables, so a run with neither jq nor a token names jq."""
    _root, old, new = run_both(tmp_path, drop=tool, drop_env=tuple(BASE_ENV))
    _agree(old, new, "no-" + tool)
    assert old[0].returncode == 1
    assert old[0].stderr == "✗ Required command '%s' is not available\n" % tool, repr(old[0].stderr)


# --------------------------------------------------------------------------- The planted defect ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_the_call_log(tmp_path) -> None:
    """PROVE THE DIFFERENTIAL CAN FIRE, and prove WHICH assertion fires.

    The plant reverses the concatenation so stable clones are tested before edge ones. That is the ONE ordering the twin's header argues for, and it changes NOTHING about the exit code: the same four regions are tested, the same four databases are cleaned up, and the summary line is identical. Only the call log and the group headers see it.
    """
    root = fixture(tmp_path)
    old_proc, old_calls = _run(root, "old")

    planted_file = root / "planted_test_d1_migrations.py"
    source = PORT_FILE.read_text(encoding="utf-8")
    mutant = source.replace(
        "    all_dbs = edge_dbs + stable_dbs",
        "    all_dbs = stable_dbs + edge_dbs",
    )
    assert mutant != source, "the plant did not apply; the control is broken, not the gate"
    planted_file.write_text(mutant, encoding="utf-8")

    call_log = root / "planted-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(root),
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
    new_proc = subprocess.run(
        [sys.executable, str(planted_file)],
        cwd=str(root.parent),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
        input="",
    )
    new_calls = call_log.read_text(encoding="utf-8")

    assert new_proc.returncode == old_proc.returncode, "the plant changed the exit code"
    # THE SUMMARY LINE IS UNCHANGED, which is the part that makes this quiet: the run still reports four regions, two edge and two stable. Only the ORDER moved, and only the call log and the group headers carry it.
    assert "All 4 regional migration tests passed (2 edge + 2 stable)" in new_proc.stderr
    assert _mask(new_calls) != _mask(old_calls), (
        "THE CALL LOG DID NOT SEE IT: this gate cannot fail"
    )
    assert new_proc.stdout != old_proc.stdout, "the group headers did not see it either"
    first_created = next(
        line.split()[4] for line in _calls(new_calls) if line.startswith("npx wrangler d1 create ")
    )
    assert first_created == "migration-test-stable-eu-777-2"


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_region_id_strips_the_right_prefix_in_the_right_order() -> None:
    """BOTH SPELLINGS WORK BECAUSE OF THE ORDER, not in spite of it."""
    assert port.region_id("account-db-eu") == "eu"
    assert port.region_id("edge-account-db-eu") == "eu"
    assert port.region_id("account-db-") == ""
    # A NAME MATCHING NEITHER PREFIX IS PASSED THROUGH WHOLE, which is what a regions.json naming its databases anything else would produce.
    assert port.region_id("weird-db") == "weird-db"


def test_channel_tag_is_a_glob_on_the_edge_prefix() -> None:
    assert port.channel_tag("edge-account-db-eu") == "edge"
    assert port.channel_tag("account-db-eu") == "stable"
    assert port.channel_tag("edge-account-db-") == "edge"
    assert port.channel_tag("weird-db") == "stable"


def test_test_db_name_matches_the_twins_template() -> None:
    assert port.test_db_name("edge-account-db-eu", "777", "2") == "migration-test-edge-eu-777-2"
    assert port.test_db_name("account-db-us", "local", "1") == "migration-test-stable-us-local-1"


def test_read_names_follows_bash_rather_than_python() -> None:
    assert port.read_names("a\nb\n") == ["a", "b"]
    assert port.read_names("a\nb") == ["a"], "a final line without a newline is dropped"
    assert port.read_names("a\n\nb\n") == ["a", "b"], "an empty line is skipped, not fatal"
    assert port.read_names("") == []


def test_the_argv_builders_match_the_twins_words() -> None:
    assert port.create_argv("d")[-2:] == ["--location", "eeur"]
    assert port.info_argv("d") == ["npx", "wrangler", "d1", "info", "d", "--json"]
    assert port.delete_argv("d")[-1] == "--skip-confirmation"
    assert port.migrations_argv("d")[-2:] == ["--config", "wrangler-migration-test.toml"]
    assert port.clone_argv("/r", "src", "dst")[-4:] == ["--source", "src", "--target", "dst"]
    assert port.clone_argv("/r", "s", "d")[0] == "/r/.ci/scripts/deploy/clone-d1.sh"


def test_the_mktemp_mask_hides_only_the_random_suffix() -> None:
    """A MASK THAT SWALLOWED MORE THAN THE SUFFIX WOULD MAKE `_agree` VACUOUS.

    Both halves, because either alone is satisfiable by a broken pattern: the mask DOES collapse two different `mktemp -d` directories to one string, and it does NOT touch the filename after it, a `/tmp` path of any other shape, or
    the `--output=` flag that carries it.
    """
    a = "call: npx wrangler d1 export db --remote --output=/tmp/tmp.KSwRwsYJRr/export.sql"
    b = "call: npx wrangler d1 export db --remote --output=/tmp/tmp.JTIJi7lgUF/export.sql"
    assert _mask(a) == _mask(b)
    assert _mask(a).endswith("--output=/tmp/tmp.<MKTEMP>/export.sql")

    # A DIFFERENT FILENAME UNDER THE SAME MASK IS STILL A DIFFERENCE.
    c = "call: npx wrangler d1 export db --remote --output=/tmp/tmp.KSwRwsYJRr/dump.sql"
    assert _mask(a) != _mask(c)
    # AND A TEMPORARY PATH OF ANY OTHER SHAPE IS NOT MASKED AT ALL.
    assert _mask("/tmp/somewhere/else") == "/tmp/somewhere/else"
    assert _mask("/tmp/tmp.short") == "/tmp/tmp.short"


def test_the_guard_table_and_the_literal_reads_cannot_drift() -> None:
    """`require_env` READS `os.environ` WITH LITERAL KEYS so the env-registry scanner can see them, and `REQUIRED_ENV` is the table it must agree with.

    Two claims, because either one alone is satisfiable by a broken file: the table names exactly the two variables the twin guards, IN ORDER, and the
    function's SOURCE contains a literal `os.environ.get("<name>"` for each of
    them. A future edit that folds the reads back into a loop over the table passes the first assertion and fails the second, which is the whole point.
    """
    assert [name for name, _ in port.REQUIRED_ENV] == [
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
    ]
    source = inspect.getsource(port.require_env)
    for name, _message in port.REQUIRED_ENV:
        assert 'os.environ.get("%s"' % name in source, name


def test_the_twin_still_says_what_this_port_says_it_says() -> None:
    """A STALENESS GUARD, quoting the twin."""
    text = TWIN.read_text(encoding="utf-8")
    assert "jq -r '.regions[].edgeD1.name' regions.json" in text
    assert "jq -r '.regions[].d1.name' regions.json" in text
    assert 'DB_NAME="migration-test-${CHANNEL_TAG}-${REGION_ID}-${RUN_ID}-${RUN_ATTEMPT}"' in text
    assert 'ALL_DBS=("${EDGE_DBS[@]}" "${STABLE_DBS[@]}")' in text
    assert "trap cleanup EXIT" in text
    assert "$SCRIPT_DIR/clone-d1.sh" in text
