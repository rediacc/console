"""Differential: `rediacc_ci.deploy.deploy_www` against its twin `.ci/scripts/deploy/deploy-www.sh`.

A RECORDING FAKE FOR `npx`/`npm` ON A SCRATCH PATH, INSIDE A FIXTURE REPO. Nothing here reaches Cloudflare; every case pins a fixture token, account and D1 state file, and the fake `npx` is a MODEL of `wrangler d1` rather than wrangler. the ledger (deleted in commit:936280cd35) records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity
ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG AND THE GENERATED CONFIG ARE THE EVIDENCE. Everything the script prints goes through `log_step`/`log_info`, which any classifier reads as progress; the observable effect of a run is the ordered list of `npx wrangler` subcommands and the exact bytes of the `wrangler.preview.toml` the preview lane generates. The fake records both: every invocation as a `call: ` line in
`$FAKE_CALL_LOG`, and the bytes of any `--config` file the deploy step is handed into `$FAKE_CONFIG_DUMP`.

BOTH SIDES GET THEIR OWN D1 STATE FILE, because a run MUTATES it (a preview deploy deletes and recreates a database). Sharing one would make the second side read what the first side wrote, which is a different scenario rather than the same one.

`$REDIACC_CI_ROOT` STEERS ONLY THE PORT: the twin resolved its root from the COPIED `common.sh`'s own location. The bash side of every case is answered from its frozen golden (`goldens/twins/deploy.deploy-www.jsonl`), so the twin file is not needed to run this module; `test_the_root_variable_steers_the_port` pins the variable's effect on the port.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_www as port
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests.twin_names import as_twin

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "deploy-www.sh"
TWIN_REL = ".ci/scripts/deploy/deploy-www.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "deploy_www.py"
BASH = shutil.which("bash") or "/bin/bash"

# The production lane refuses a www dist without this key (`www_sitekey_refusal`); the fixture builds one that carries it, so the twin's goldens, recorded before the refusal existed, still describe every keyed run.
SITE_KEY = "0x4AAAAAAAwwwfixturekey"

CREDENTIALS = {
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
    "CLOUDFLARE_ACCOUNT_ID": "acct-fixture",
}
BASE_ENV = {**CREDENTIALS, "TURNSTILE_SITE_KEY": SITE_KEY}

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

if argv[:2] != ["--no-install", "wrangler"]:
    sys.stderr.write("fake npx: unmodelled tool %r\n" % (argv[:1],))
    sys.exit(127)

rest = argv[2:]
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

if rest[:2] == ["secret", "put"]:
    emit("secret-put-name: %s\n" % rest[2])
    emit("secret-put-stdin: %s\n" % sys.stdin.read())
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
    www_bundle: str | None = "const k='%s';" % SITE_KEY,
) -> pathlib.Path:
    """A throwaway repository holding the twin, common.sh and a workers/www whose `dist/assets` holds one bundle (`www_bundle`, none when None)."""
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    if TWIN.exists():  # the bash side is recorded only while the twin is on disk
        shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / ".ci" / "config" / "well-known.env", root / ".ci" / "config" / "well-known.env"
    )
    shutil.copy2(
        ROOT / ".ci" / "config" / "well-known.generated.sh",
        root / ".ci" / "config" / "well-known.generated.sh",
    )

    worker = root / "workers" / "www"
    worker.mkdir(parents=True, exist_ok=True)
    for name in worker_files:
        (worker / name).write_text('name = "rediacc-www"\n', encoding="utf-8")
    if node_modules:
        (worker / "node_modules").mkdir(exist_ok=True)
    if www_bundle is not None:
        (worker / "dist" / "assets").mkdir(parents=True, exist_ok=True)
        (worker / "dist" / "assets" / "index.js").write_text(www_bundle, encoding="utf-8")

    for side in ("old", "new"):
        # The twin's golden names its databases `account-db-pr-<n>`; the port's are `account-pr-<n>` (PLAN-product-domain-rename), so the port's side starts from the same state under its own names.
        named = {} if databases is None else databases
        if side == "new":
            named = {_new_name(k): v for k, v in named.items()}
        (root / f"{side}-d1.json").write_text(json.dumps(named), encoding="utf-8")
    return root


def _run(
    root: pathlib.Path,
    side: str,
    *args: str,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    """The port runs live; the bash side is answered from its frozen golden."""
    if side != "old":
        return _run_live(root, side, *args, drop=drop, drop_env=drop_env, **extra)
    worker = root / "workers" / "www"
    parts = [
        *args,
        "--",
        "drop=%s" % drop,
        "drop_env=%s" % ",".join(drop_env),
        # `dist` is the port's keyed build, which the twin never read, so it stays out of the golden key.
        "worker_files=%s" % ",".join(sorted(p.name for p in worker.iterdir() if p.name != "dist")),
        "d1=%s" % (root / "old-d1.json").read_text(encoding="utf-8"),
        *("%s=%s" % kv for kv in sorted(extra.items())),
    ]
    return diff.twin_result(
        TWIN_REL,
        parts,
        lambda: _run_live(root, side, *args, drop=drop, drop_env=drop_env, **extra),
        port=lambda: _port_as_golden(root, *args, drop=drop, drop_env=drop_env, **extra),
        work=(root,),
    )


def _port_as_golden(
    root: pathlib.Path,
    *args: str,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    """The re-record seam of a Rule-T change (`regolden --source port`): the port's answer in the golden's spelling, exactly the mapping `_agree` applies to the live port side. The port's fake D1 state is restored afterwards, so the live port run that follows starts from the fixture's state."""
    state = root / "new-d1.json"
    saved = state.read_text(encoding="utf-8")
    try:
        proc, calls, config = _run_live(root, "new", *args, drop=drop, drop_env=drop_env, **extra)
    finally:
        state.write_text(saved, encoding="utf-8")
    proc = subprocess.CompletedProcess(
        proc.args, proc.returncode, as_twin(_golden(proc.stdout)), as_twin(_golden(proc.stderr))
    )
    return proc, _mask_preview_pepper(_golden(calls)), _golden(config)


def _run_live(
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


def _new_name(text: str) -> str:
    """The twin's database name in the port's spelling."""
    return text.replace("account-db-pr-", "account-pr-")


def _golden(text: str) -> str:
    """The port's database name written back in the twin's spelling, so every OTHER byte is still compared."""
    return text.replace("account-pr-", "account-db-pr-")


PREVIEW_PEPPER_STDIN = re.compile(r"^secret-put-stdin: [0-9a-f]{64}$", re.MULTILINE)


def _mask_preview_pepper(calls: str) -> str:
    """A preview's pepper is random per deploy (`secrets.token_hex(32)`), so the call log carries it as `<preview-pepper>` before it is compared with the golden; the tests below pin its shape and that it is never the production value."""
    return PREVIEW_PEPPER_STDIN.sub("secret-put-stdin: <preview-pepper>", calls)


def _agree(old, new, label: str) -> None:
    """THE THREE STREAMS SEPARATELY, plus the call log and the generated config."""
    old_proc, old_calls, old_config = old
    new_proc, new_calls, new_config = new
    # `_golden` maps the port's spelling onto the twin's, which would hide a port that still used the retired name, so the port's raw streams are refused for it first.
    for stream, text in (
        ("stdout", new_proc.stdout),
        ("stderr", new_proc.stderr),
        ("calls", new_calls),
        ("config", new_config),
    ):
        assert "account-db-pr-" not in text, f"{label}: the port's {stream} names account-db-pr-"
    new_proc = subprocess.CompletedProcess(
        new_proc.args, new_proc.returncode, _golden(new_proc.stdout), _golden(new_proc.stderr)
    )
    new_calls, new_config = _mask_preview_pepper(_golden(new_calls)), _golden(new_config)
    assert new_proc.returncode == old_proc.returncode, (
        f"{label}: exit diverged: {old_proc.returncode!r} vs {new_proc.returncode!r}\n"
        f"old stderr: {old_proc.stderr!r}\nnew stderr: {as_twin(new_proc.stderr)!r}"
    )
    assert as_twin(new_proc.stdout) == old_proc.stdout, (
        f"{label}: stdout diverged:\n{old_proc.stdout!r}\n{as_twin(new_proc.stdout)!r}"
    )
    assert as_twin(new_proc.stderr) == old_proc.stderr, (
        f"{label}: stderr diverged:\n{old_proc.stderr!r}\n{as_twin(new_proc.stderr)!r}"
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
    assert _calls(calls) == ["npx --no-install wrangler deploy"], calls
    assert config == "", "the production lane generated a config file"
    assert proc.stdout == "Deployed worker\n", repr(proc.stdout)
    assert "Deploying www production worker..." in proc.stderr


def test_the_pepper_is_pushed_as_a_worker_secret_on_stdin_after_the_deploy(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, calls, _config = _run_live(root, "new", ENTERPRISE_LOOKUP_PEPPER="pepper-fixture-value")
    assert proc.returncode == 0, proc.stderr
    assert _calls(calls) == [
        "npx --no-install wrangler deploy",
        "npx --no-install wrangler secret put ENTERPRISE_LOOKUP_PEPPER",
    ], calls
    assert "secret-put-stdin: pepper-fixture-value\n" in calls
    assert "pepper-fixture-value" not in " ".join(_calls(calls)), "the value rode argv"
    assert "pepper-fixture-value" not in proc.stdout + proc.stderr


def test_a_failed_deploy_pushes_no_pepper(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, calls, _config = _run_live(
        root, "new", ENTERPRISE_LOOKUP_PEPPER="x", FAKE_NPX_FAIL_ON_CALL="1"
    )
    assert proc.returncode != 0
    assert not any("secret put" in c for c in _calls(calls)), calls


def test_a_failed_pepper_push_fails_the_run(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, _calls_log, _config = _run_live(
        root, "new", ENTERPRISE_LOOKUP_PEPPER="x", FAKE_NPX_FAIL_ON_CALL="2"
    )
    assert proc.returncode != 0


# --------------------------------------------------------------------------- the keyless-dist refusal (2026-11-12)


@pytest.mark.parametrize(
    ("label", "fixture_kw", "env", "needle"),
    [
        ("unbound key", {}, {"TURNSTILE_SITE_KEY": ""}, "TURNSTILE_SITE_KEY is not bound"),
        ("malformed key", {}, {"TURNSTILE_SITE_KEY": "not-a-key"}, "does not look like"),
        ("no built pages", {"www_bundle": None}, {}, "no built www pages at"),
        (
            "the 2026-11-12 keyless build",
            {"www_bundle": "const k='';"},
            {},
            "carry no Turnstile site key",
        ),
    ],
)
def test_production_refuses_a_keyless_www_dist_before_any_deploy(
    tmp_path, label, fixture_kw, env, needle
) -> None:
    root = fixture(tmp_path, **fixture_kw)
    proc, calls, _config = _run_live(root, "new", **env)
    assert proc.returncode == 1, (label, proc.stderr)
    assert needle in proc.stderr, (label, proc.stderr)
    assert "wrangler" not in " ".join(_calls(calls)), (label, calls)
    assert "Deploying www production worker" not in proc.stderr, label


def test_the_refusal_reads_only_the_pages_bundles_not_the_portals(tmp_path) -> None:
    """A key that sits only in `dist/account/assets` (the portal) does not vouch for the www pages."""
    root = fixture(tmp_path, www_bundle="const k='';")
    portal = root / "workers" / "www" / "dist" / "account" / "assets"
    portal.mkdir(parents=True)
    (portal / "portal.js").write_text("const k='%s';" % SITE_KEY, encoding="utf-8")
    proc, calls, _config = _run_live(root, "new")
    assert proc.returncode == 1, proc.stderr
    assert "carry no Turnstile site key" in proc.stderr
    assert _calls(calls) == []


def test_a_keyed_www_dist_deploys_and_the_preview_lane_needs_no_key(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, calls, _config = _run_live(root, "new")
    assert proc.returncode == 0, proc.stderr
    assert _calls(calls) == ["npx --no-install wrangler deploy"]
    preview_root = fixture(tmp_path / "p", www_bundle=None)
    proc, calls, _config = _run_live(preview_root, "new", "--name", "pr-7", TURNSTILE_SITE_KEY="")
    assert proc.returncode == 0, proc.stderr
    assert "npx --no-install wrangler deploy --config wrangler.preview.toml" in _calls(calls)


def test_preview_mints_a_database_and_the_generated_toml_is_byte_identical(tmp_path) -> None:
    _root, old, new = run_both(tmp_path, "--name", "pr-379")
    _agree(old, new, "preview-fresh")

    proc, calls, config = old
    assert proc.returncode == 0, proc.stderr
    # THE SHAPE: one info that finds nothing, a create, a second info, the migrations, the deploy. NO delete, because the database did not exist.
    assert _calls(calls) == [
        "npx --no-install wrangler d1 info account-db-pr-379 --json",
        "npx --no-install wrangler d1 create account-db-pr-379 --location eeur",
        "npx --no-install wrangler d1 info account-db-pr-379 --json",
        (
            "npx --no-install wrangler d1 migrations apply account-db-pr-379 --remote "
            "--config wrangler.preview.toml"
        ),
        "npx --no-install wrangler deploy --config wrangler.preview.toml",
        PREVIEW_PEPPER_PUT,
        PREVIEW_TURNSTILE_PUT,
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
    """THE PORT SPELLS U+2014 AS AN ESCAPE, so this proves the emitted BYTES are the twin's rather than trusting the module docstring's claim.

    Both halves matter. The backticks around `trailingSlash: 'never'` are `\\`` in the twin's UNQUOTED heredoc; a port that left the backslashes in would emit a different file that no test comparing only the two ports would catch, because both sides would be equally wrong. Here the twin IS one of the two sides, so the comparison is against bash's own expansion.
    """
    _root, old, new = run_both(tmp_path, "--name", "pr-1")
    _agree(old, new, "preview-toml-bytes")

    _proc, _calls_text, config = old
    assert "\u2014 infinite loop." in config, "the twin's em dash is not in the emitted TOML"
    assert "`trailingSlash: 'never'`" in config
    assert "\\`" not in config, "the heredoc's backslash-backtick leaked into the output"
    # AND THE PORT'S OWN SOURCE CARRIES NO LITERAL EM DASH, which is the reason the escape is there at all.
    assert "\u2014" not in PORT_FILE.read_text(encoding="utf-8")


PREVIEW_PEPPER_PUT = (
    "npx --no-install wrangler secret put ENTERPRISE_LOOKUP_PEPPER --config wrangler.preview.toml"
)
PREVIEW_TURNSTILE_PUT = "npx --no-install wrangler secret put CLOUDFLARE_TURNSTILE_SECRET_KEY --config wrangler.preview.toml"


def test_an_existing_database_is_deleted_first(tmp_path) -> None:
    """THE CLEAN-SLATE PATH. The delete only happens when the first `d1 info` answered with a uuid, so this is the case the first lookup exists for."""
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
        "npx --no-install wrangler d1 info account-db-pr-42 --json",
        "npx --no-install wrangler d1 delete account-db-pr-42 --skip-confirmation",
        "npx --no-install wrangler d1 create account-db-pr-42 --location eeur",
        "npx --no-install wrangler d1 info account-db-pr-42 --json",
        (
            "npx --no-install wrangler d1 migrations apply account-db-pr-42 --remote "
            "--config wrangler.preview.toml"
        ),
        "npx --no-install wrangler deploy --config wrangler.preview.toml",
        PREVIEW_PEPPER_PUT,
        PREVIEW_TURNSTILE_PUT,
    ], calls
    assert "Deleting existing D1 database: account-db-pr-42 (clean slate)" in proc.stderr
    assert "Deleted account-db-pr-42" in proc.stderr


def test_the_generated_config_is_removed_on_success_and_kept_on_failure(tmp_path) -> None:
    """`rm -f wrangler.preview.toml` IS ONLY ON THE SUCCESS PATH (twin :141), so a failed deploy leaves the generated file in the worker directory. Both halves are driven, because "it is cleaned up" is the plausible reading."""
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

    Nothing validates the shape, so the run mints `account-db-pr-true` and deploys a worker literally named `true`. Reproduced, not repaired.
    """
    assert port.A_VALUELESS_NAME_DEPLOYS_A_WORKER_CALLED_TRUE is True

    _root, old, new = run_both(tmp_path, "--name")
    _agree(old, new, "valueless-name")

    proc, calls, config = old
    assert proc.returncode == 0, proc.stderr
    assert "npx --no-install wrangler d1 create account-db-pr-true --location eeur" in _calls(calls)
    assert 'name = "true"' in config
    assert "Deploying preview worker: true" in proc.stderr


def test_fact_a_non_pr_name_is_accepted_verbatim(tmp_path) -> None:
    """`${ARG_NAME#pr-}` STRIPS ONLY WHEN THE PREFIX IS THERE."""
    assert port.A_NON_PR_NAME_IS_ACCEPTED_VERBATIM is True

    _root, old, new = run_both(tmp_path, "--name", "staging")
    _agree(old, new, "non-pr-name")

    proc, calls, config = old
    assert proc.returncode == 0, proc.stderr
    assert "npx --no-install wrangler d1 create account-db-pr-staging --location eeur" in _calls(
        calls
    )
    assert 'name = "staging"' in config


def test_fact_the_production_database_guard_cannot_fire() -> None:
    """THE REFUSAL AT twin :69-72 IS UNREACHABLE, and both halves are asserted.

    The guard itself works (`is_protected` says yes to every shared database); no output `db_name_for` can produce ever reaches it, because the template carries a literal `-pr-` for every input including the empty string.
    """
    assert port.PRODUCTION_GUARD_IS_UNREACHABLE is True
    shared = (
        "account-eu",
        "account-us",
        "account-asia",
        "account-bench",
        "account-eu-j",
        "account-bench-j",
    )
    for name in shared:
        assert port.is_protected(name) is True, name
    assert not port.is_protected("account-db"), "the retired bare name guards nothing"
    for name in ("", "pr-", "pr-1", "account-eu", "pr-account-eu", "account-bench"):
        assert not port.is_protected(port.db_name_for(name)), name
    assert port.db_name_for("") == "account-pr-"
    assert port.db_name_for("pr-account-eu") == "account-pr-account-eu"


# --------------------------------------------------------------------------- Refusals ---------------------------------------------------------------------------


def test_a_missing_wrangler_toml_refuses_before_anything_else(tmp_path) -> None:
    """AND IT REFUSES BEFORE `require_var`, so a run with no credentials at all still reports the missing worker rather than the missing token."""
    root = fixture(tmp_path, worker_files=())
    old = _run(root, "old", drop_env=tuple(CREDENTIALS))
    new = _run(root, "new", drop_env=tuple(CREDENTIALS))
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
    """ORDER MATTERS: `require_cmd jq` is AFTER both `require_var`s (twin :26-28), so a run with neither jq nor a token names the token."""
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

    `FAKE_D1_CREATE_IS_INVISIBLE` makes `d1 create` report success without registering the database, which is what a create that silently did not take would look like. The second `get_d1_uuid` then answers empty and the run stops before writing any config.
    """
    _root, old, new = run_both(tmp_path, "--name", "pr-5", FAKE_D1_CREATE_IS_INVISIBLE="1")
    _agree(old, new, "invisible-create")

    proc, calls, config = old
    assert proc.returncode == 1
    assert "✗ Failed to retrieve UUID for newly created D1 database: account-db-pr-5" in proc.stderr
    assert config == "", "a refused run still generated a config"
    assert _calls(calls)[-1] == "npx --no-install wrangler d1 info account-db-pr-5 --json"


def test_an_npx_failure_mid_run_stops_with_npxs_status(tmp_path) -> None:
    """UNGUARDED UNDER `set -e`. Call 2 is the create, so the run stops with the first `d1 info` done and nothing generated."""
    _root, old, new = run_both(tmp_path, "--name", "pr-8", FAKE_NPX_FAIL_ON_CALL="2")
    _agree(old, new, "npx-fails")

    proc, calls, config = old
    assert proc.returncode == 1
    assert proc.stderr.endswith("wrangler: a fixture failure was injected on call 2\n")
    assert len(_calls(calls)) == 2
    assert config == ""


def test_npm_install_runs_only_when_node_modules_is_absent(tmp_path) -> None:
    """BOTH DIRECTIONS. The twin's condition is `[[ ! -d "node_modules" ]]` and nothing else, so unlike `deploy-account.sh` a globally installed wrangler does NOT skip the install."""
    _root, old, new = run_both(tmp_path, fixture_kw={"node_modules": False})
    _agree(old, new, "npm-install")
    assert _calls(old[1])[0] == "npm install", old[1]

    _root2, old2, new2 = run_both(tmp_path / "b", fixture_kw={"node_modules": True})
    _agree(old2, new2, "npm-skip")
    assert "npm install" not in old2[1]


def test_a_flag_that_is_not_an_identifier_exits_two_on_both_sides(tmp_path) -> None:
    """THE ONE NAMED DIVERGENCE, and it is in text nobody parses.

    `printf -v` refuses `ARG_FOO.BAR`, returns 2, and `set -e` takes the whole script down. bash's message names `common.sh` and a line number; the port prefixes the twin's own name. The EXIT CODE and the STREAM agree, which is the part a caller can observe.
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
    assert (
        new_proc.stderr
        == "rediacc_ci.deploy.deploy_www: printf: `ARG_FOO.BAR': not a valid identifier\n"
    ), repr(new_proc.stderr)


def test_the_root_variable_steers_the_port(tmp_path) -> None:
    """$REDIACC_CI_ROOT STEERS ONLY THE PORT.

    The twin resolved the root from the copied `common.sh`'s own location and read no such variable (frozen in the golden), so both sides landing on the same fixture was a real agreement. Pinned by pointing the variable at a DECOY and watching the port follow it.
    """
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

    The plant drops `--location eeur` from the create, which is invisible in every printed byte: the twin and the port would both log `Creating D1 database ...` and both exit 0. Only the call log sees it, and a preview database minted in the wrong region is exactly the class of defect this ledger exists to rule out.
    """
    root = fixture(tmp_path)
    old_proc, old_calls, _ = _run(root, "old", "--name", "pr-3")

    # The port runs out of process, so the plant is applied to a COPY of the source that the new side is pointed at.
    planted_file = root / "planted_deploy_www.py"
    source = PORT_FILE.read_text(encoding="utf-8")
    mutant = source.replace(
        'return [*wrangler.ARGV, "d1", "create", db_name, "--location", D1_LOCATION]',
        'return [*wrangler.ARGV, "d1", "create", db_name]',
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
    assert _golden(new_proc.stdout) == old_proc.stdout, "the plant changed stdout; wrong plant"
    assert _golden(new_proc.stderr) == old_proc.stderr, "the plant changed stderr; wrong plant"
    assert _golden(new_calls) != old_calls, "THE CALL LOG DID NOT SEE IT: this gate cannot fail"
    assert "npx --no-install wrangler d1 create account-pr-3\n" in new_calls


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_the_argv_builders_match_the_twins_words() -> None:
    assert port.info_argv("d") == ["npx", "--no-install", "wrangler", "d1", "info", "d", "--json"]
    assert port.delete_argv("d") == [
        "npx",
        "--no-install",
        "wrangler",
        "d1",
        "delete",
        "d",
        "--skip-confirmation",
    ]
    assert port.create_argv("d") == [
        "npx",
        "--no-install",
        "wrangler",
        "d1",
        "create",
        "d",
        "--location",
        "eeur",
    ]
    assert port.migrations_argv("d")[-2:] == ["--config", "wrangler.preview.toml"]
    assert port.preview_deploy_argv() == [
        "npx",
        "--no-install",
        "wrangler",
        "deploy",
        "--config",
        "wrangler.preview.toml",
    ]
    assert port.production_deploy_argv() == ["npx", "--no-install", "wrangler", "deploy"]


def test_strip_newlines_removes_both_bytes_anywhere_in_the_token() -> None:
    assert port.strip_newlines("tok\n") == "tok"
    assert port.strip_newlines("\r\ntok\r\n") == "tok"
    assert port.strip_newlines("to\rk") == "tok"
    assert port.strip_newlines("tok") == "tok"


def test_the_generated_toml_ends_with_exactly_one_newline() -> None:
    body = port.preview_toml("pr-1", "db", "u")
    assert body.endswith('[[kv_namespaces]]\nbinding = "ENTERPRISE_LOOKUP"\n')
    assert not body.endswith("\n\n")


def test_a_preview_binds_no_signer_and_declares_itself_signerless() -> None:
    """PLAN-preview-signer Context 11: PR-written preview code must never reach a signer holding the production key, so the preview binds no LICENSE_SIGNER and holds no key. SIGNERLESS_PREVIEW = "true" next to ENVIRONMENT = "preview" is what lets the account Worker serve without one (private/account src/types/env.ts)."""
    body = port.preview_toml("pr-1", "db", "u")
    # The comments name the binding to say why it is absent; the settings must not.
    settings = "\n".join(line for line in body.splitlines() if not line.startswith("#"))
    assert "LICENSE_SIGNER" not in settings
    assert "signer-bench" not in settings
    assert "LicenseSigner" not in settings
    assert "ED25519_PRIVATE_KEY" not in body
    vars_table = body.split("[vars]\n", 1)[1].split("\n[", 1)[0]
    assert 'ENVIRONMENT = "preview"\n' in vars_table
    assert 'SIGNERLESS_PREVIEW = "true"\n' in vars_table


def test_bench_still_binds_the_signer_and_sets_no_signerless_flag() -> None:
    """The control for the test above: the bench account Worker keeps its LICENSE_SIGNER binding, and no checked-in Worker config carries the signerless flag, so only the generated preview does."""
    workers = ROOT / "workers"
    bench = (workers / "account" / "wrangler.bench-eu.toml").read_text(encoding="utf-8")
    assert 'binding = "LICENSE_SIGNER"' in bench
    configs = sorted(workers.glob("*/wrangler*.toml"))
    assert configs, "no Worker configs found: wrong root"
    for config in configs:
        assert "SIGNERLESS_PREVIEW" not in config.read_text(encoding="utf-8"), config


def test_a_preview_worker_persists_no_logs_or_traces() -> None:
    """PLAN-telemetry-export T15: Cloudflare persists a Worker's logs and traces unless told not to, and a preview has no OTLP destination, so every observability table is off and both signals carry `persist = false`."""
    body = port.preview_toml("pr-1", "db", "u")
    tables: dict[str, list[str]] = {}
    current = None
    for line in body.splitlines():
        if line.startswith("["):
            current = line
            tables[current] = []
        elif current is not None and line and not line.startswith("#"):
            tables[current].append(line)
    assert tables["[observability]"] == ["enabled = false"]
    assert tables["[observability.logs]"] == [
        "enabled = false",
        "invocation_logs = false",
        "persist = false",
    ]
    assert tables["[observability.traces]"] == ["enabled = false", "persist = false"]
    assert "head_sampling_rate" not in body


def test_both_credentials_are_read_with_literal_keys() -> None:
    """THE ENV-REGISTRY SCANNER MUST BE ABLE TO SEE BOTH INPUTS.

    `common.require_var` does the refusing, and the read that makes the refusal happen lives inside `core.common`, where an AST walk of THIS module cannot see it. So `main` reads both names with literal keys as well. A future edit that folds those two reads away leaves `CLOUDFLARE_ACCOUNT_ID` an undeclared input, and this is what says so.

    THE ORDER IS ASSERTED TOO, because a dict literal is what preserves it and `test_a_missing_jq_refuses_after_the_variables` depends on the token being named first.
    """
    source = inspect.getsource(port.main)
    for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        assert 'os.environ.get("%s"' % name in source, name
    assert source.index("CLOUDFLARE_API_TOKEN") < source.index("CLOUDFLARE_ACCOUNT_ID")


def test_diagnostics_are_prefixed_with_the_module_name() -> None:
    """The twin's `.sh` is deleted, so the prefix names the module a reader can run and find."""
    assert port.SELF == "rediacc_ci.deploy.deploy_www"
    assert port.__name__ == port.SELF


# --- a preview answers /api/enterprise-lookup (found in the 2026-11-16 live run: 503 unavailable) ---


def test_a_preview_binds_the_lookup_namespace_and_the_account_worker() -> None:
    """The route answers 503 `unavailable` without the ENTERPRISE_LOOKUP namespace; the preview binds its own (no id, so wrangler provisions one) and never the production namespace id."""
    body = port.preview_toml("pr-1", "db", "u")
    assert '[[kv_namespaces]]\nbinding = "ENTERPRISE_LOOKUP"\n' in body
    assert '[[services]]\nbinding = "ACCOUNT"\nservice = "account-bench"\n' in body
    assert "7bbf3025c29349f5b4f833c1d47d8eb5" not in body


def test_a_preview_pushes_the_turnstile_dummy_secret_after_the_deploy(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, calls, _config = _run_live(root, "new", "--name", "pr-9")
    assert proc.returncode == 0, proc.stderr
    names = _calls(calls)
    assert names[-3] == "npx --no-install wrangler deploy --config wrangler.preview.toml"
    assert names[-2] == PREVIEW_PEPPER_PUT
    assert names[-1] == PREVIEW_TURNSTILE_PUT
    assert "secret-put-stdin: 1x0000000000000000000000000000000AA\n" in calls
    assert "secret put ENTERPRISE_LOOKUP_PEPPER" in calls, (
        "a preview's own pepper is pushed with no production one in the run"
    )


def test_a_preview_never_receives_the_production_pepper(tmp_path) -> None:
    """Code from a PR branch served at the public pr-N URL must not hold the production pepper: the preview gets its own random pepper, which keys its own empty namespace."""
    root = fixture(tmp_path)
    proc, calls, _config = _run_live(
        root, "new", "--name", "pr-9", ENTERPRISE_LOOKUP_PEPPER="pepper-fixture-value"
    )
    assert proc.returncode == 0, proc.stderr
    assert "pepper-fixture-value" not in calls, "the production pepper reached the preview"
    puts = [c for c in _calls(calls) if "secret put" in c]
    assert [c.split()[5] for c in puts] == [
        "ENTERPRISE_LOOKUP_PEPPER",
        "CLOUDFLARE_TURNSTILE_SECRET_KEY",
    ]
    values = re.findall(r"^secret-put-stdin: (.*)$", calls, re.MULTILINE)
    assert len(values) == 2
    assert values[1] == port.TURNSTILE_ALWAYS_PASSES
    assert re.fullmatch(r"[0-9a-f]{64}", values[0]), values[0]


def test_each_preview_deploy_gets_a_fresh_pepper(tmp_path) -> None:
    peppers = []
    for n in ("a", "b"):
        root = fixture(tmp_path / n)
        proc, calls, _config = _run_live(root, "new", "--name", "pr-9")
        assert proc.returncode == 0, proc.stderr
        peppers.append(re.findall(r"^secret-put-stdin: (.*)$", calls, re.MULTILINE)[0])
    assert peppers[0] != peppers[1]
    assert all(re.fullmatch(r"[0-9a-f]{64}", p) for p in peppers), peppers


def test_a_failed_preview_deploy_pushes_no_secret(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, calls, _config = _run_live(root, "new", "--name", "pr-9", FAKE_NPX_FAIL_ON_CALL="5")
    assert proc.returncode != 0
    assert not any("secret put" in c for c in _calls(calls)), calls


# ---- word-named previews (PLAN-preview-signer D5). Port only: the twin predates the names. ----


WORD = "pv-able-baker-charlie"
SHA_A = "a" * 64
SHA_B = "b" * 64
MANIFEST = {
    "version": "1.4.0-preview.abc1234",
    "releaseDate": "2026-11-23T00:00:00Z",
    "releaseNotesUrl": "",
    "commit": "abc1234",
    "binaries": {
        "linux-x64": {"url": "https://releases.example/cli/x/rdc-linux-x64", "sha256": SHA_A},
        "mac-arm64": {"url": "https://releases.example/cli/x/rdc-mac-arm64", "sha256": SHA_B},
    },
}
FORMAT_DIFF = """diff --git a/pkg/chunkstore/manifest.go b/pkg/chunkstore/manifest.go
--- a/pkg/chunkstore/manifest.go
+++ b/pkg/chunkstore/manifest.go
@@ -17,7 +17,7 @@
-const ManifestVersion = 1
+const ManifestVersion = 2
"""


def _word_inputs(
    root: pathlib.Path, *, diff: str = "", manifest: dict | None = None
) -> tuple[str, ...]:
    m = root / "manifest.json"
    m.write_text(json.dumps(MANIFEST if manifest is None else manifest), encoding="utf-8")
    d = root / "renet.diff"
    d.write_text(diff, encoding="utf-8")
    return ("--name", WORD, "--manifest", str(m), "--renet-diff", str(d))


def test_a_word_named_preview_keeps_its_pr_numbered_database(tmp_path) -> None:
    """The D1 is account-pr-<n> and is created and migrated before the preview's own signer is deployed; the fixture holds no signer template (box S2), so the run stops there, before the Worker deploy, naming the box."""
    root = fixture(tmp_path)
    proc, calls, _config = _run_live(root, "new", *_word_inputs(root), PR_NUMBER="42")
    assert proc.returncode == 1, proc.stderr
    names = _calls(calls)
    assert "npx --no-install wrangler d1 create account-pr-42 --location eeur" in names
    assert any(
        n.startswith("npx --no-install wrangler d1 migrations apply account-pr-42") for n in names
    )
    assert not any(n.startswith("npx --no-install wrangler deploy") for n in names)
    assert "box S2" in proc.stderr
    assert "account-pv-" not in calls, "the database never takes the word name"


def test_a_word_named_preview_without_a_pr_number_is_refused_before_any_call(tmp_path) -> None:
    for label, pr in (("unset", None), ("letters", "4x")):
        root = fixture(tmp_path / label)
        if pr is None:
            proc, calls, _config = _run_live(root, "new", *_word_inputs(root))
        else:
            proc, calls, _config = _run_live(root, "new", *_word_inputs(root), PR_NUMBER=pr)
        assert proc.returncode == 1, label
        assert "needs PR_NUMBER (digits)" in proc.stderr, label
        assert _calls(calls) == [], label


def test_a_signer_name_is_never_deployed_as_the_www_preview(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, calls, _config = _run_live(
        root, "new", "--name", "pv-able-baker-charlie-signer", PR_NUMBER="42"
    )
    assert proc.returncode == 1
    assert "-signer name" in proc.stderr
    assert _calls(calls) == []


def test_the_old_pr_name_still_derives_its_database_from_the_name() -> None:
    """The control: a pr-<n> name is the twin's lane and ignores PR_NUMBER."""
    assert port.preview_db_name("pr-7", "") == ("account-pr-7", "")
    assert port.preview_db_name("pr-7", "99") == ("account-pr-7", "")


def _build(**over) -> dict:
    marker = over.pop("marker", None)
    return port.preview_build(WORD, json.dumps({**MANIFEST, **over}), marker)


def test_preview_build_carries_one_sha256_per_platform_and_no_marker_means_no_format_change() -> (
    None
):
    build = _build()
    assert build == {
        "name": WORD,
        "version": "1.4.0-preview.abc1234",
        "sha256": {"linux-x64": SHA_A, "mac-arm64": SHA_B},
        "formatChange": None,
    }


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"binaries": {}}, "lists no binary"),
        ({"binaries": {"linux-x64": {"sha256": "abc"}}}, "no valid sha256"),
        ({"version": ""}, "names no version"),
    ],
)
def test_a_manifest_that_proves_nothing_is_refused(over, reason) -> None:
    with pytest.raises(port.PreviewBuildError, match=reason):
        _build(**over)


def test_a_marker_file_reaches_format_change_and_a_malformed_one_is_refused() -> None:
    marker = json.dumps({"formats": ["chunkstore manifest v2"], "reason": "new chunk index"})
    assert _build(marker=marker)["formatChange"] == {
        "formats": ["chunkstore manifest v2"],
        "reason": "new chunk index",
    }
    with pytest.raises(port.PreviewBuildError, match="must be"):
        _build(marker=json.dumps({"formats": [], "reason": "x"}))


def test_the_format_backstop_sees_a_changed_constant_and_ignores_other_lines() -> None:
    assert port.format_constant_changes(FORMAT_DIFF) == [
        "pkg/chunkstore/manifest.go: ManifestVersion"
    ]
    unrelated = FORMAT_DIFF.replace("const ManifestVersion = 2", "// ManifestVersion is documented")
    unrelated = unrelated.replace("-const ManifestVersion = 1", "-// old comment")
    assert port.format_constant_changes(unrelated) == []
    other_file = FORMAT_DIFF.replace("pkg/chunkstore/manifest.go", "pkg/other/thing.go")
    assert port.format_constant_changes(other_file) == []


def test_a_format_constant_change_without_a_marker_refuses_before_any_call(tmp_path) -> None:
    root = fixture(tmp_path)
    proc, calls, _config = _run_live(
        root, "new", *_word_inputs(root, diff=FORMAT_DIFF), PR_NUMBER="42"
    )
    assert proc.returncode == 1
    assert "on-disk format constant (pkg/chunkstore/manifest.go: ManifestVersion)" in proc.stderr
    assert _calls(calls) == []
    marker = root.joinpath(*port.FORMAT_MARKER)
    marker.write_text(
        json.dumps({"formats": ["chunkstore manifest v2"], "reason": "r"}), encoding="utf-8"
    )
    proc, calls, _config = _run_live(
        root, "new", *_word_inputs(root, diff=FORMAT_DIFF), PR_NUMBER="42"
    )
    assert "on-disk format constant" not in proc.stderr
    assert _calls(calls), "with the marker the deploy proceeds"


def test_a_word_named_preview_without_its_manifest_or_diff_is_refused_before_any_call(
    tmp_path,
) -> None:
    root = fixture(tmp_path)
    proc, calls, _config = _run_live(root, "new", "--name", WORD, PR_NUMBER="42")
    assert proc.returncode == 1
    assert "needs --manifest" in proc.stderr
    assert _calls(calls) == []


def test_the_word_preview_config_binds_its_own_signer_and_carries_its_build() -> None:
    build = _build()
    body = port.word_preview_toml(WORD, "account-pr-42", "u", build)
    doc = tomllib.loads(body)
    assert "SIGNERLESS_PREVIEW" not in body
    assert "ED25519_PRIVATE_KEY" not in body
    assert "signer-bench" not in "\n".join(x for x in body.splitlines() if not x.startswith("#"))
    assert doc["vars"]["ENVIRONMENT"] == "preview"
    assert json.loads(doc["vars"]["PREVIEW_BUILD"]) == build
    signer = [svc for svc in doc["services"] if svc["binding"] == "LICENSE_SIGNER"]
    assert signer == [
        {
            "binding": "LICENSE_SIGNER",
            "service": WORD + "-signer",
            "entrypoint": "LicenseSigner",
            "props": {"tier": "shared", "region": "eu"},
        }
    ]
    assert "route" not in doc
    # The control: every other line is the twin's config.
    service = port.SIGNER_SERVICE % (WORD + "-signer")
    assert body.endswith(service)
    kept = [
        line
        for line in body[: -len(service)].splitlines(keepends=True)
        if not line.startswith(("PREVIEW_BUILD = ", "# The build this preview serves"))
    ]
    twin = port.preview_toml(WORD, "account-pr-42", "u")
    assert "".join(kept) == twin.replace(port.SIGNERLESS_BLOCK, "")
