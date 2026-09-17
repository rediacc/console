"""Differential: `rediacc_ci.deploy.deploy_www` against its twin
`.ci/scripts/deploy/deploy-www.sh`.

A RECORDING FAKE FOR `npx`/`npm` ON A SCRATCH PATH, INSIDE A FIXTURE REPO.
Nothing here reaches Cloudflare; every case pins a fixture token, account and
D1 state file, and the fake `npx` is a MODEL of `wrangler d1` rather than
wrangler. `.ci/shadow/w7p5a-status.json` records this path as blocked only for
the "one real run" clause and says in as many words that the mocked parity
ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG AND THE GENERATED CONFIG ARE THE EVIDENCE. Everything the script
prints goes through `log_step`/`log_info`, which any classifier reads as
progress; the observable effect of a run is the ordered list of `npx wrangler`
subcommands and the exact bytes of the `wrangler.preview.toml` the preview lane
generates. The fake records both: every invocation as a `call: ` line in
`$FAKE_CALL_LOG`, and the bytes of any `--config` file the deploy step is
handed into `$FAKE_CONFIG_DUMP`.

BOTH SIDES GET THEIR OWN D1 STATE FILE, because a run MUTATES it (a preview
deploy deletes and recreates a database). Sharing one would make the second side
read what the first side wrote, which is a different scenario rather than the
same one.

`$REDIACC_CI_ROOT` STEERS ONLY THE PORT, and the twin resolves its root from the
COPIED `common.sh`'s own location, so the two arrive at the same fixture from
opposite directions. `test_the_two_root_resolutions_agree` pins that, including
the half that matters: the twin does not read the variable at all.
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
from rediacc_ci.deploy import deploy_www as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "deploy-www.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "deploy_www.py"
BASH = shutil.which("bash") or "/bin/bash"

BASE_ENV = {
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
    "CLOUDFLARE_ACCOUNT_ID": "acct-fixture",
}

# A MODEL of `wrangler d1`, not wrangler. Serves and mutates a JSON state file mapping database name to uuid, so "does this database exist" is a real question with a real answer that a delete and a create both change.
#
# `d1 info` PRINTS A BANNER BEFORE THE JSON, which is the whole reason the twin
# runs `sed -n '/^[[:space:]]*[{[]/,$p'` at all. A fake that printed bare JSON
# would leave that stage unexercised and a port that dropped it would still pass.
FAKE_NPX = r'''#!/usr/bin/python3
"""Recording fake for `npx` and `npm`. See the test module docstring."""
import json
import os
import sys

argv = sys.argv[1:]
tool = os.path.basename(sys.argv[0])
log = os.environ["FAKE_CALL_LOG"]
state_file = os.environ["FAKE_D1_STATE"]


def emit(text):
    with open(log, "a") as fh:
        fh.write(text)


emit("call: %s %s\n" % (tool, " ".join(argv)))

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


def uuid_for(name):
    """Deterministic, so both sides mint the same uuid for the same name."""
    if os.environ.get("FAKE_D1_CREATE_IS_INVISIBLE") == "1":
        return None
    return "uuid-for-%s" % name


if tool == "npm":
    sys.stdout.write("added 0 packages in 0s\n")
    sys.exit(0)

if argv[:1] != ["wrangler"]:
    sys.stderr.write("fake npx: unmodelled tool %r\n" % (argv[:1],))
    sys.exit(127)

rest = argv[1:]
state = load()

if rest[:2] == ["d1", "info"]:
    name = rest[2]
    if name not in state:
        sys.stderr.write("wrangler: no D1 database named %s\n" % name)
        sys.exit(1)
    sys.stdout.write(" wrangler 4.0.0 (fixture)\n")
    sys.stdout.write("-------------------\n")
    sys.stdout.write(json.dumps({"uuid": state[name], "name": name}, indent=2) + "\n")
    sys.exit(0)

if rest[:2] == ["d1", "delete"]:
    name = rest[2]
    state.pop(name, None)
    save(state)
    sys.stdout.write("Deleted database %s\n" % name)
    sys.exit(0)

if rest[:2] == ["d1", "create"]:
    name = rest[2]
    minted = uuid_for(name)
    if minted is not None:
        state[name] = minted
        save(state)
    sys.stdout.write("Created database %s\n" % name)
    sys.exit(0)

if rest[:3] == ["d1", "migrations", "apply"]:
    sys.stdout.write("No migrations to apply!\n")
    sys.exit(0)

if rest[:1] == ["deploy"]:
    dump = os.environ.get("FAKE_CONFIG_DUMP", "")
    if dump and "--config" in rest:
        path = rest[rest.index("--config") + 1]
        with open(dump, "a") as out:
            with open(path) as fh:
                out.write("CONFIG %s<<<%s>>>\n" % (path, fh.read()))
    sys.stdout.write("Deployed worker\n")
    sys.exit(0)

sys.stderr.write("fake wrangler: unmodelled subcommand %r\n" % (rest,))
sys.exit(127)
'''

# Everything bash and the port both resolve through PATH. `cat` is here because the twin's heredoc is `cat >wrangler.preview.toml`, `jq` and `sed` because `get_d1_uuid` is those two programs, and `uname` because `common.sh` calls `detect_os`/`detect_arch` at source time.
PATH_MINIMUM = ("cat", "jq", "sed", "tr", "rm", "uname", "dirname", "basename", "env")


def _bin(root: pathlib.Path, *, drop: str = "") -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        if real_name == drop:
            link = stub / real_name
            if link.is_symlink() or link.exists():
                link.unlink()
            continue
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    for name in ("npx", "npm"):
        script = stub / name
        script.write_text(FAKE_NPX, encoding="utf-8")
        script.chmod(0o755)
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def fixture(
    tmp_path: pathlib.Path,
    *,
    worker_files: tuple[str, ...] = ("wrangler.toml",),
    node_modules: bool = True,
    databases: dict[str, str] | None = None,
) -> pathlib.Path:
    """A throwaway repository holding the twin, common.sh and a workers/www."""
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)

    worker = root / "workers" / "www"
    worker.mkdir(parents=True, exist_ok=True)
    for name in worker_files:
        (worker / name).write_text('name = "rediacc-www"\n', encoding="utf-8")
    if node_modules:
        (worker / "node_modules").mkdir(exist_ok=True)

    for side in ("old", "new"):
        (root / f"{side}-d1.json").write_text(
            json.dumps({} if databases is None else databases), encoding="utf-8"
        )
    return root


def _run(
    root: pathlib.Path,
    side: str,
    *args: str,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    call_log = root / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    config_dump = root / f"{side}-configs.log"
    config_dump.write_text("", encoding="utf-8")

    env = {
        "PATH": _bin(root, drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "REDIACC_CI_ROOT": str(root),
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_CONFIG_DUMP": str(config_dump),
        "FAKE_D1_STATE": str(root / f"{side}-d1.json"),
        **BASE_ENV,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)

    if side == "old":
        argv = [BASH, str(root / ".ci" / "scripts" / "deploy" / TWIN.name), *args]
    else:
        argv = [sys.executable, str(PORT_FILE), *args]
    proc = subprocess.run(
        argv,
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8"), config_dump.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, *args: str, fixture_kw: dict | None = None, **kw):
    root = fixture(tmp_path, **(fixture_kw or {}))
    old = _run(root, "old", *args, **kw)
    new = _run(root, "new", *args, **kw)
    return root, old, new


def _agree(old, new, label: str) -> None:
    """THE THREE STREAMS SEPARATELY, plus the call log and the generated config."""
    old_proc, old_calls, old_config = old
    new_proc, new_calls, new_config = new
    assert new_proc.returncode == old_proc.returncode, (
        f"{label}: exit diverged: {old_proc.returncode!r} vs {new_proc.returncode!r}\n"
        f"old stderr: {old_proc.stderr!r}\nnew stderr: {new_proc.stderr!r}"
    )
    assert new_proc.stdout == old_proc.stdout, (
        f"{label}: stdout diverged:\n{old_proc.stdout!r}\n{new_proc.stdout!r}"
    )
    assert new_proc.stderr == old_proc.stderr, (
        f"{label}: stderr diverged:\n{old_proc.stderr!r}\n{new_proc.stderr!r}"
    )
    assert new_calls == old_calls, f"{label}: call log diverged:\n{old_calls}\n---\n{new_calls}"
    assert new_config == old_config, (
        f"{label}: generated config diverged:\n{old_config}\n---\n{new_config}"
    )


def _calls(log: str) -> list[str]:
    return [line[len("call: ") :] for line in log.splitlines() if line.startswith("call: ")]


# --------------------------------------------------------------------------- The two lanes ---------------------------------------------------------------------------


def test_production_deploys_with_no_config_flag_and_never_touches_d1(tmp_path) -> None:
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "production")

    proc, calls, config = old
    assert proc.returncode == 0, proc.stderr
    assert _calls(calls) == ["npx wrangler deploy"], calls
    assert config == "", "the production lane generated a config file"
    assert proc.stdout == "Deployed worker\n", repr(proc.stdout)
    assert "Deploying www production worker..." in proc.stderr


def test_preview_mints_a_database_and_the_generated_toml_is_byte_identical(tmp_path) -> None:
    _root, old, new = run_both(tmp_path, "--name", "pr-379")
    _agree(old, new, "preview-fresh")

    proc, calls, config = old
    assert proc.returncode == 0, proc.stderr
    # THE SHAPE: one info that finds nothing, a create, a second info, the migrations, the deploy. NO delete, because the database did not exist.
    assert _calls(calls) == [
        "npx wrangler d1 info account-db-pr-379 --json",
        "npx wrangler d1 create account-db-pr-379 --location eeur",
        "npx wrangler d1 info account-db-pr-379 --json",
        (
            "npx wrangler d1 migrations apply account-db-pr-379 --remote "
            "--config wrangler.preview.toml"
        ),
        "npx wrangler deploy --config wrangler.preview.toml",
    ], calls

    # The generated config, byte for byte, is what the deploy was handed.
    assert config.startswith("CONFIG wrangler.preview.toml<<<")
    body = config[len("CONFIG wrangler.preview.toml<<<") : -len(">>>\n")]
    assert body == port.preview_toml("pr-379", "account-db-pr-379", "uuid-for-account-db-pr-379"), (
        repr(body)
    )
    assert 'name = "pr-379"' in body
    assert 'database_id = "uuid-for-account-db-pr-379"' in body


def test_the_generated_toml_carries_the_twins_em_dash_and_backticks(tmp_path) -> None:
    """THE PORT SPELLS U+2014 AS AN ESCAPE, so this proves the emitted BYTES are
    the twin's rather than trusting the module docstring's claim.

    Both halves matter. The backticks around `trailingSlash: 'never'` are `\\``
    in the twin's UNQUOTED heredoc; a port that left the backslashes in would
    emit a different file that no test comparing only the two ports would catch,
    because both sides would be equally wrong. Here the twin IS one of the two
    sides, so the comparison is against bash's own expansion.
    """
    _root, old, new = run_both(tmp_path, "--name", "pr-1")
    _agree(old, new, "preview-toml-bytes")

    _proc, _calls_text, config = old
    assert "\u2014 infinite loop." in config, "the twin's em dash is not in the emitted TOML"
    assert "`trailingSlash: 'never'`" in config
    assert "\\`" not in config, "the heredoc's backslash-backtick leaked into the output"
    # AND THE PORT'S OWN SOURCE CARRIES NO LITERAL EM DASH, which is the reason the escape is there at all.
    assert "\u2014" not in PORT_FILE.read_text(encoding="utf-8")


def test_an_existing_database_is_deleted_first(tmp_path) -> None:
    """THE CLEAN-SLATE PATH. The delete only happens when the first `d1 info`
    answered with a uuid, so this is the case the first lookup exists for."""
    _root, old, new = run_both(
        tmp_path,
        "--name",
        "pr-42",
        fixture_kw={"databases": {"account-db-pr-42": "uuid-stale"}},
    )
    _agree(old, new, "preview-existing")

    proc, calls, _config = old
    assert proc.returncode == 0, proc.stderr
    assert _calls(calls) == [
        "npx wrangler d1 info account-db-pr-42 --json",
        "npx wrangler d1 delete account-db-pr-42 --skip-confirmation",
        "npx wrangler d1 create account-db-pr-42 --location eeur",
        "npx wrangler d1 info account-db-pr-42 --json",
        (
            "npx wrangler d1 migrations apply account-db-pr-42 --remote "
            "--config wrangler.preview.toml"
        ),
        "npx wrangler deploy --config wrangler.preview.toml",
    ], calls
    assert "Deleting existing D1 database: account-db-pr-42 (clean slate)" in proc.stderr
    assert "Deleted account-db-pr-42" in proc.stderr


def test_the_generated_config_is_removed_on_success_and_kept_on_failure(tmp_path) -> None:
    """`rm -f wrangler.preview.toml` IS ONLY ON THE SUCCESS PATH (twin :141), so
    a failed deploy leaves the generated file in the worker directory. Both
    halves are driven, because "it is cleaned up" is the plausible reading."""
    root, old, new = run_both(tmp_path, "--name", "pr-7")
    _agree(old, new, "cleanup-success")
    assert not (root / "workers" / "www" / port.PREVIEW_CONFIG).exists()

    root2, old2, new2 = run_both(tmp_path / "b", "--name", "pr-7", FAKE_NPX_FAIL_ON_CALL="5")
    _agree(old2, new2, "cleanup-failure")
    assert old2[0].returncode == 1
    left = root2 / "workers" / "www" / port.PREVIEW_CONFIG
    assert left.is_file(), "the generated config was cleaned up on a failed deploy"


# --------------------------------------------------------------------------- The three named facts ---------------------------------------------------------------------------


def test_fact_a_valueless_name_deploys_a_worker_called_true(tmp_path) -> None:
    """`parse_args` STORES THE STRING `true` FOR A FLAG WITH NO VALUE.

    Nothing validates the shape, so the run mints `account-db-pr-true` and
    deploys a worker literally named `true`. Reproduced, not repaired.
    """
    assert port.A_VALUELESS_NAME_DEPLOYS_A_WORKER_CALLED_TRUE is True

    _root, old, new = run_both(tmp_path, "--name")
    _agree(old, new, "valueless-name")

    proc, calls, config = old
    assert proc.returncode == 0, proc.stderr
    assert "npx wrangler d1 create account-db-pr-true --location eeur" in _calls(calls)
    assert 'name = "true"' in config
    assert "Deploying preview worker: true" in proc.stderr


def test_fact_a_non_pr_name_is_accepted_verbatim(tmp_path) -> None:
    """`${ARG_NAME#pr-}` STRIPS ONLY WHEN THE PREFIX IS THERE."""
    assert port.A_NON_PR_NAME_IS_ACCEPTED_VERBATIM is True

    _root, old, new = run_both(tmp_path, "--name", "staging")
    _agree(old, new, "non-pr-name")

    proc, calls, config = old
    assert proc.returncode == 0, proc.stderr
    assert "npx wrangler d1 create account-db-pr-staging --location eeur" in _calls(calls)
    assert 'name = "staging"' in config


def test_fact_the_production_database_guard_cannot_fire() -> None:
    """THE REFUSAL AT twin :69-72 IS UNREACHABLE, and both halves are asserted.

    The guard itself works (`is_protected` says yes to both names); no output
    `db_name_for` can produce ever reaches it, because the template carries a
    literal `-pr-` for every input including the empty string.
    """
    assert port.PRODUCTION_GUARD_IS_UNREACHABLE is True
    assert port.is_protected("account-db") is True
    assert port.is_protected("edge-account-db") is True
    for name in ("", "pr-", "pr-1", "account-db", "edge-account-db", "pr-account-db"):
        assert not port.is_protected(port.db_name_for(name)), name
    assert port.db_name_for("") == "account-db-pr-"
    assert port.db_name_for("pr-account-db") == "account-db-pr-account-db"


# --------------------------------------------------------------------------- Refusals ---------------------------------------------------------------------------


def test_a_missing_wrangler_toml_refuses_before_anything_else(tmp_path) -> None:
    """AND IT REFUSES BEFORE `require_var`, so a run with no credentials at all
    still reports the missing worker rather than the missing token."""
    root = fixture(tmp_path, worker_files=())
    old = _run(root, "old", drop_env=tuple(BASE_ENV))
    new = _run(root, "new", drop_env=tuple(BASE_ENV))
    _agree(old, new, "no-worker")

    proc, calls, _config = old
    assert proc.returncode == 1
    assert proc.stderr == "✗ www worker not found at %s/workers/www\n" % root, repr(proc.stderr)
    assert calls == "", "a refused run still called npx"


@pytest.mark.parametrize("missing", ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"])
def test_each_required_variable_refuses_with_the_same_bytes(tmp_path, missing) -> None:
    _root, old, new = run_both(tmp_path, drop_env=(missing,))
    _agree(old, new, "missing-" + missing)

    proc, calls, _config = old
    assert proc.returncode == 1
    assert proc.stderr == "✗ Required environment variable '%s' is not set\n" % missing
    assert calls == ""


def test_an_empty_variable_refuses_exactly_as_an_absent_one_does(tmp_path) -> None:
    """`[[ -z "${!var:-}" ]]` IS AN EMPTINESS TEST, not a presence test."""
    _root, old, new = run_both(tmp_path, CLOUDFLARE_ACCOUNT_ID="")
    _agree(old, new, "empty-account-id")
    assert old[0].returncode == 1
    assert "Required environment variable 'CLOUDFLARE_ACCOUNT_ID' is not set" in old[0].stderr


def test_a_missing_jq_refuses_after_the_variables(tmp_path) -> None:
    """ORDER MATTERS: `require_cmd jq` is AFTER both `require_var`s (twin :26-28),
    so a run with neither jq nor a token names the token."""
    _root, old, new = run_both(tmp_path, drop="jq")
    _agree(old, new, "no-jq")
    assert old[0].returncode == 1
    assert old[0].stderr == "✗ Required command 'jq' is not available\n", repr(old[0].stderr)

    _root2, old2, new2 = run_both(tmp_path / "b", drop="jq", drop_env=("CLOUDFLARE_API_TOKEN",))
    _agree(old2, new2, "no-jq-no-token")
    assert "CLOUDFLARE_API_TOKEN" in old2[0].stderr
    assert "jq" not in old2[0].stderr


def test_a_failed_uuid_lookup_after_create_is_the_one_self_refusal(tmp_path) -> None:
    """THE ONLY PLACE THIS SCRIPT REFUSES ON ITS OWN ACCOUNT.

    `FAKE_D1_CREATE_IS_INVISIBLE` makes `d1 create` report success without
    registering the database, which is what a create that silently did not take
    would look like. The second `get_d1_uuid` then answers empty and the run
    stops before writing any config.
    """
    _root, old, new = run_both(tmp_path, "--name", "pr-5", FAKE_D1_CREATE_IS_INVISIBLE="1")
    _agree(old, new, "invisible-create")

    proc, calls, config = old
    assert proc.returncode == 1
    assert "✗ Failed to retrieve UUID for newly created D1 database: account-db-pr-5" in proc.stderr
    assert config == "", "a refused run still generated a config"
    assert _calls(calls)[-1] == "npx wrangler d1 info account-db-pr-5 --json"


def test_an_npx_failure_mid_run_stops_with_npxs_status(tmp_path) -> None:
    """UNGUARDED UNDER `set -e`. Call 2 is the create, so the run stops with the
    first `d1 info` done and nothing generated."""
    _root, old, new = run_both(tmp_path, "--name", "pr-8", FAKE_NPX_FAIL_ON_CALL="2")
    _agree(old, new, "npx-fails")

    proc, calls, config = old
    assert proc.returncode == 1
    assert proc.stderr.endswith("wrangler: a fixture failure was injected on call 2\n")
    assert len(_calls(calls)) == 2
    assert config == ""


def test_npm_install_runs_only_when_node_modules_is_absent(tmp_path) -> None:
    """BOTH DIRECTIONS. The twin's condition is `[[ ! -d "node_modules" ]]` and
    nothing else, so unlike `deploy-account.sh` a globally installed wrangler
    does NOT skip the install."""
    _root, old, new = run_both(tmp_path, fixture_kw={"node_modules": False})
    _agree(old, new, "npm-install")
    assert _calls(old[1])[0] == "npm install", old[1]

    _root2, old2, new2 = run_both(tmp_path / "b", fixture_kw={"node_modules": True})
    _agree(old2, new2, "npm-skip")
    assert "npm install" not in old2[1]


def test_a_flag_that_is_not_an_identifier_exits_two_on_both_sides(tmp_path) -> None:
    """THE ONE NAMED DIVERGENCE, and it is in text nobody parses.

    `printf -v` refuses `ARG_FOO.BAR`, returns 2, and `set -e` takes the whole
    script down. bash's message names `common.sh` and a line number; the port
    prefixes the twin's own name. The EXIT CODE and the STREAM agree, which is
    the part a caller can observe.
    """
    root = fixture(tmp_path)
    old_proc, old_calls, _ = _run(root, "old", "--foo.bar=x")
    new_proc, new_calls, _ = _run(root, "new", "--foo.bar=x")

    assert old_proc.returncode == 2, old_proc.stderr
    assert new_proc.returncode == 2, new_proc.stderr
    assert old_proc.stdout == ""
    assert new_proc.stdout == ""
    assert old_calls == ""
    assert new_calls == ""
    assert "not a valid identifier" in old_proc.stderr
    assert new_proc.stderr == "deploy-www.sh: printf: `ARG_FOO.BAR': not a valid identifier\n", (
        repr(new_proc.stderr)
    )


def test_the_two_root_resolutions_agree(tmp_path) -> None:
    """$REDIACC_CI_ROOT STEERS ONLY THE PORT.

    The twin resolves the root from the copied `common.sh`'s own location and
    reads no such variable, so the fact that both sides land on the same fixture
    is a real agreement rather than a shared configuration. Pinned by pointing
    the variable at a DECOY and watching the port follow it while the twin does
    not.
    """
    assert "REDIACC_CI_ROOT" not in TWIN.read_text(encoding="utf-8")
    assert "REDIACC_CI_ROOT" not in COMMON.read_text(encoding="utf-8")

    root = fixture(tmp_path)
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    proc, calls, _ = _run(root, "new", REDIACC_CI_ROOT=str(decoy))
    assert proc.returncode == 1
    assert str(decoy) in proc.stderr, proc.stderr
    assert calls == ""


# --------------------------------------------------------------------------- The planted defect ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_the_call_log(tmp_path) -> None:
    """PROVE THE DIFFERENTIAL CAN FIRE, and prove WHICH assertion fires.

    The plant drops `--location eeur` from the create, which is invisible in
    every printed byte: the twin and the port would both log
    `Creating D1 database ...` and both exit 0. Only the call log sees it, and a
    preview database minted in the wrong region is exactly the class of defect
    this ledger exists to rule out.
    """
    root = fixture(tmp_path)
    old_proc, old_calls, _ = _run(root, "old", "--name", "pr-3")

    # The port runs out of process, so the plant is applied to a COPY of the source that the new side is pointed at.
    planted_file = root / "planted_deploy_www.py"
    source = PORT_FILE.read_text(encoding="utf-8")
    mutant = source.replace(
        'return ["npx", "wrangler", "d1", "create", db_name, "--location", D1_LOCATION]',
        'return ["npx", "wrangler", "d1", "create", db_name]',
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
        "FAKE_CONFIG_DUMP": str(root / "planted-configs.log"),
        "FAKE_D1_STATE": str(root / "new-d1.json"),
        **BASE_ENV,
    }
    new_proc = subprocess.run(
        [sys.executable, str(planted_file), "--name", "pr-3"],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    new_calls = call_log.read_text(encoding="utf-8")

    assert new_proc.returncode == old_proc.returncode, "the plant changed the exit code"
    assert new_proc.stdout == old_proc.stdout, "the plant changed stdout; wrong plant"
    assert new_proc.stderr == old_proc.stderr, "the plant changed stderr; wrong plant"
    assert new_calls != old_calls, "THE CALL LOG DID NOT SEE IT: this gate cannot fail"
    assert "npx wrangler d1 create account-db-pr-3\n" in new_calls


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_the_argv_builders_match_the_twins_words() -> None:
    assert port.info_argv("d") == ["npx", "wrangler", "d1", "info", "d", "--json"]
    assert port.delete_argv("d") == [
        "npx",
        "wrangler",
        "d1",
        "delete",
        "d",
        "--skip-confirmation",
    ]
    assert port.create_argv("d") == ["npx", "wrangler", "d1", "create", "d", "--location", "eeur"]
    assert port.migrations_argv("d")[-2:] == ["--config", "wrangler.preview.toml"]
    assert port.preview_deploy_argv() == [
        "npx",
        "wrangler",
        "deploy",
        "--config",
        "wrangler.preview.toml",
    ]
    assert port.production_deploy_argv() == ["npx", "wrangler", "deploy"]


def test_strip_newlines_removes_both_bytes_anywhere_in_the_token() -> None:
    assert port.strip_newlines("tok\n") == "tok"
    assert port.strip_newlines("\r\ntok\r\n") == "tok"
    assert port.strip_newlines("to\rk") == "tok"
    assert port.strip_newlines("tok") == "tok"


def test_the_generated_toml_ends_with_exactly_one_newline() -> None:
    body = port.preview_toml("pr-1", "db", "u")
    assert body.endswith('migrations_dir = "../../private/account/drizzle"\n')
    assert not body.endswith("\n\n")


def test_both_credentials_are_read_with_literal_keys() -> None:
    """THE ENV-REGISTRY SCANNER MUST BE ABLE TO SEE BOTH INPUTS.

    `common.require_var` does the refusing, and the read that makes the refusal
    happen lives inside `core.common`, where an AST walk of THIS module cannot
    see it. So `main` reads both names with literal keys as well. A future edit
    that folds those two reads away leaves `CLOUDFLARE_ACCOUNT_ID` an undeclared
    input, and this is what says so.

    THE ORDER IS ASSERTED TOO, because a dict literal is what preserves it and
    `test_a_missing_jq_refuses_after_the_variables` depends on the token being
    named first.
    """
    source = inspect.getsource(port.main)
    for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        assert 'os.environ.get("%s"' % name in source, name
    assert source.index("CLOUDFLARE_API_TOKEN") < source.index("CLOUDFLARE_ACCOUNT_ID")


def test_the_twin_still_says_what_this_port_says_it_says() -> None:
    """A STALENESS GUARD. Every literal below is quoted from the twin; if the
    twin is edited, this fails here rather than silently in a ledger nobody
    re-records."""
    text = TWIN.read_text(encoding="utf-8")
    assert 'DB_NAME="account-db-pr-${PR_NUM}"' in text
    assert "--location eeur" in text
    assert "jq -r '.uuid // empty'" in text
    assert "sed -n '/^[[:space:]]*[{[]/,$p'" in text
    assert "rm -f wrangler.preview.toml" in text
