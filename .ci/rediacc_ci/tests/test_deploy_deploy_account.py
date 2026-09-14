"""Differential: `rediacc_ci.deploy.deploy_account` against its twin
`.ci/scripts/deploy/deploy-account.sh`.

RECORDING FAKE `npx` AND `npm` ON A SCRATCH PATH, AND A FIXTURE REPO ROOT.
Nothing here reaches Cloudflare and nothing installs anything: the fakes log
their exact argv, their cwd, and the value of `CLOUDFLARE_API_TOKEN` they were
handed. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the
"one real run" clause and says in as many words that the mocked parity ledger is
a separate, achievable piece of work. This is that piece.

HOW THE TWO SIDES ARE MADE TO AGREE ABOUT THE REPO ROOT, since they answer the
question differently and a differential that let them answer it differently
would be comparing two trees. The twin's `get_repo_root` is
`${BASH_SOURCE[0]}/../../..` from `common.sh`, so a COPY of `common.sh` and a
COPY of the script inside `tmp_path` resolve to the fixture. The port's
`common.repo_root()` delegates to `paths.repo_root()`, which honours
`$REDIACC_CI_ROOT`, so the port is the REAL file under test and the variable
points it at the same fixture. `test_the_copied_twin_is_the_real_twin` asserts
the copy is byte-identical, so the differential cannot drift onto a stale twin,
and `test_the_twin_ignores_the_root_override` asserts the variable is not
secretly steering the bash side as well.

THE HAPPY PATH SAYS PLENTY, so the streams carry real evidence here, unlike the
`set-www-worker-secrets` sibling. What the streams CANNOT show is which database
got migrated with which config and which token reached the child, so every case
that gets that far compares the recorded call log too.

TWO DEFECTS IN THE TWIN ARE PINNED, NOT FIXED. A `database_name` that is the
first match but not in the expected shape (a comment, or a line with a trailing
quoted comment) is passed through by `sed` UNCHANGED and becomes the database
name, and the "Could not read database_name" guard at :51-54 never fires. Both
are driven here in both directions: the port must produce the same wrong answer,
because a `tomllib` port would produce a different one and that is not a port.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_account as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "deploy-account.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "deploy_account.py"
COMMON_SH = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
BASH = shutil.which("bash") or "/bin/bash"

# The canonical shape of the line the twin reads, copied from
# `workers/account/wrangler.eu.toml:40-43`.
FIXTURE_TOML = (
    '[[d1_databases]]\nbinding = "DB"\ndatabase_name = "account-db-eu"\ndatabase_id = "x"\n'
)

# What the real binaries on the scratch PATH must be. `grep`, `head` and `sed`
# are the database-name pipeline on BOTH sides (the port shells out to the same
# three); `uname` and `dirname` are what `common.sh` needs at source time.
PATH_MINIMUM = ("grep", "head", "sed", "tr", "uname", "dirname")

FAKE_NPX = """#!/usr/bin/python3
import os
import sys

log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("npx\\t" + "\\t".join(sys.argv[1:]) + "\\n")
    fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")
    fh.write("  token=" + repr(os.environ.get("CLOUDFLARE_API_TOKEN")) + "\\n")

rc = int(os.environ.get("FAKE_NPX_RC", "0"))
if rc:
    sys.stderr.write("wrangler: deploy failed\\n")
    sys.exit(rc)
sys.stdout.write("Total Upload: 1.00 KiB\\n")
"""

FAKE_NPM = """#!/usr/bin/python3
import os
import sys

log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("npm\\t" + "\\t".join(sys.argv[1:]) + "\\n")
    fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")

rc = int(os.environ.get("FAKE_NPM_RC", "0"))
if rc:
    sys.stderr.write("npm ERR! install failed\\n")
    sys.exit(rc)
sys.stdout.write("added 1 package\\n")
"""

# A `wrangler` that is never invoked. Its only job is to be FOUND by
# `command -v` / `shutil.which`, which is half of the npm-install condition.
FAKE_WRANGLER = "#!/usr/bin/python3\nraise SystemExit('the fake wrangler must never run')\n"

BASE_ENV = {
    "CLOUDFLARE_API_TOKEN": "tok",
    "CLOUDFLARE_ACCOUNT_ID": "acct",
}


def _fixture_root(tmp_path: pathlib.Path, *, configs: dict[str, str] | None = None) -> pathlib.Path:
    """A repo root holding a COPY of the twin, its library, and `workers/account`."""
    root = tmp_path / "root"
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    worker = root / "workers" / "account"
    worker.mkdir(parents=True, exist_ok=True)
    shutil.copy2(COMMON_SH, root / ".ci" / "scripts" / "lib" / COMMON_SH.name)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    for name, body in (configs or {"wrangler.eu.toml": FIXTURE_TOML}).items():
        (worker / name).write_text(body, encoding="utf-8")
    return root


def _bin(tmp_path: pathlib.Path, name: str, *, with_wrangler: bool = False) -> str:
    stub = tmp_path / name
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    for fake_name, body in (("npx", FAKE_NPX), ("npm", FAKE_NPM)):
        fake = stub / fake_name
        fake.write_text(body, encoding="utf-8")
        fake.chmod(0o755)
    wrangler = stub / "wrangler"
    if with_wrangler:
        wrangler.write_text(FAKE_WRANGLER, encoding="utf-8")
        wrangler.chmod(0o755)
    elif wrangler.exists():
        wrangler.unlink()
    assert (shutil.which("wrangler", path=str(stub)) is not None) == with_wrangler
    return str(stub)


def _run(
    subject: pathlib.Path,
    tmp_path: pathlib.Path,
    root: pathlib.Path,
    args: tuple[str, ...],
    *,
    with_wrangler: bool = False,
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    side = "old" if subject.suffix == ".sh" else "new"
    call_log = tmp_path / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin", with_wrangler=with_wrangler),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(root),
        "FAKE_CALL_LOG": str(call_log),
        **BASE_ENV,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *args],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, root: pathlib.Path, *args: str, **kw):
    twin_copy = root / ".ci" / "scripts" / "deploy" / TWIN.name
    old, old_calls = _run(twin_copy, tmp_path, root, args, **kw)
    new, new_calls = _run(PORT, tmp_path, root, args, **kw)
    return old, new, old_calls, new_calls


def _assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )
    if old_calls is not None:
        assert new_calls == old_calls, (
            f"{label}: the recorded calls diverged:\nold: {old_calls!r}\nnew: {new_calls!r}"
        )


def _twin_source() -> str:
    return TWIN.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The harness itself, which is a claim before it is a tool
# ---------------------------------------------------------------------------


def test_the_copied_twin_is_the_real_twin(tmp_path: pathlib.Path) -> None:
    """THE COPY IS THE SUBJECT, so a stale copy would silently pass everything."""
    root = _fixture_root(tmp_path)
    copied = (root / ".ci" / "scripts" / "deploy" / TWIN.name).read_bytes()
    assert copied == TWIN.read_bytes()
    assert (root / ".ci" / "scripts" / "lib" / "common.sh").read_bytes() == COMMON_SH.read_bytes()


def test_the_twin_ignores_the_root_override(tmp_path: pathlib.Path) -> None:
    """$REDIACC_CI_ROOT STEERS ONLY THE PORT, and the two must still land on the
    same tree. Pointed at a decoy, the bash side keeps resolving from its own
    location, so a differential that relied on the variable for both would be
    comparing nothing."""
    root = _fixture_root(tmp_path)
    decoy = tmp_path / "decoy"
    (decoy / "workers" / "account").mkdir(parents=True)
    old, _ = _run(
        root / ".ci" / "scripts" / "deploy" / TWIN.name,
        tmp_path,
        root,
        ("--region", "eu"),
        REDIACC_CI_ROOT=str(decoy),
    )
    assert old.returncode == 0, old.stderr
    assert "REDIACC_CI_ROOT" not in _twin_source()


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_the_two_wrangler_calls_are_pinned_in_full(tmp_path: pathlib.Path) -> None:
    """MIGRATIONS FIRST, THEN DEPLOY, both with the SAME `--config`, both from
    inside the worker directory, both carrying the token."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu")
    assert old.returncode == 0, old.stderr
    assert old_calls == (
        "npm\tinstall\n"
        "  cwd=account\n"
        "npx\twrangler\td1\tmigrations\tapply\taccount-db-eu\t--remote\t--config\twrangler.eu.toml\n"
        "  cwd=account\n"
        "  token='tok'\n"
        "npx\twrangler\tdeploy\t--config\twrangler.eu.toml\n"
        "  cwd=account\n"
        "  token='tok'\n"
    )
    assert old.stderr == (
        "→ Deploying account worker: production eu (wrangler.eu.toml)\n"
        "→ Applying migrations to account-db-eu...\n"
        "✓ Migrations applied to account-db-eu\n"
        "✓ Account worker deployed: production eu\n"
    )
    assert old.stdout == "added 1 package\nTotal Upload: 1.00 KiB\nTotal Upload: 1.00 KiB\n"
    _assert_agree(old, new, "happy-path", old_calls, new_calls)


def test_the_edge_target_selects_the_edge_config(tmp_path: pathlib.Path) -> None:
    """`--target edge` composes `wrangler.edge-<region>.toml` (:25-26), and the
    target string is echoed into the two log lines."""
    root = _fixture_root(tmp_path, configs={"wrangler.edge-eu.toml": FIXTURE_TOML})
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu", "--target", "edge")
    assert old.returncode == 0, old.stderr
    assert "--config\twrangler.edge-eu.toml" in old_calls
    assert "Deploying account worker: edge eu (wrangler.edge-eu.toml)" in old.stderr
    _assert_agree(old, new, "edge-target", old_calls, new_calls)


def test_an_unknown_target_is_silently_production(tmp_path: pathlib.Path) -> None:
    """THE COMPARISON IS AGAINST THE LITERAL `edge` AND NOTHING ELSE (:25), so a
    typo deploys the production config while printing the typo."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu", "--target", "Edge")
    assert old.returncode == 0, old.stderr
    assert "--config\twrangler.eu.toml" in old_calls
    assert "Deploying account worker: Edge eu (wrangler.eu.toml)" in old.stderr
    assert port.config_name("eu", "Edge") == "wrangler.eu.toml"
    _assert_agree(old, new, "unknown-target", old_calls, new_calls)


def test_the_token_is_stripped_of_carriage_returns_before_the_child_sees_it(
    tmp_path: pathlib.Path,
) -> None:
    """`tr -d '\\r\\n'` (:41). A token pasted out of a secret store carries a
    trailing newline, and wrangler sends the header verbatim."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        root,
        "--region",
        "eu",
        CLOUDFLARE_API_TOKEN="to\rk\n",  # noqa: S106 -- a fixture value that authenticates nowhere
    )
    assert old.returncode == 0, old.stderr
    assert "  token='tok'\n" in old_calls
    assert port.strip_newlines("to\rk\n") == "tok"
    _assert_agree(old, new, "token-strip", old_calls, new_calls)


def test_the_account_id_is_not_stripped(tmp_path: pathlib.Path) -> None:
    """THE ASYMMETRY IS THE TWIN'S: only the token is cleaned (:41), so a
    carriage return in the account id survives into wrangler's environment."""
    assert _twin_source().count("tr -d '\\r\\n'") == 1
    assert 'CLOUDFLARE_ACCOUNT_ID="$(printf' not in _twin_source()
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(
        tmp_path, root, "--region", "eu", CLOUDFLARE_ACCOUNT_ID="acct\r"
    )
    assert old.returncode == 0, old.stderr
    _assert_agree(old, new, "account-id-unstripped", old_calls, new_calls)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_missing_region_refuses_and_the_divergence_is_bash_only(tmp_path: pathlib.Path) -> None:
    """THE ONE DIVERGENCE ON THIS PATH, asserted from both sides so nobody
    "fixes" it into agreement: bash prefixes its `${VAR:?}` diagnostic with the
    script path as invoked and a line number, the port does not."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == 1
    assert new.returncode == 1
    assert old.stderr.endswith(port.MISSING_REGION + "\n")
    assert old.stderr != new.stderr
    assert ": line 21: " in old.stderr
    assert new.stderr == port.MISSING_REGION + "\n"
    assert old.stdout == new.stdout == ""
    assert old_calls == new_calls == ""


def test_an_empty_region_refuses_exactly_as_an_absent_one_does(tmp_path: pathlib.Path) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST. A port checking only for presence would
    resolve `wrangler..toml` and report it missing instead, which is a different
    message and a different reason."""
    root = _fixture_root(tmp_path)
    old, new, _, _ = run_both(tmp_path, root, "--region=")
    assert old.returncode == new.returncode == 1
    assert old.stderr.endswith(port.MISSING_REGION + "\n")
    assert new.stderr == port.MISSING_REGION + "\n"


def test_a_bare_region_flag_becomes_the_literal_true(tmp_path: pathlib.Path) -> None:
    """`parse_args` QUIRK: `--region` as the last token stores the string
    `true`, so the run refuses on a config file named after it rather than on a
    missing region."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region")
    assert old.returncode == 1
    assert (
        old.stderr == "✗ Wrangler config not found: %s/workers/account/wrangler.true.toml\n" % root
    )
    _assert_agree(old, new, "bare-region", old_calls, new_calls)


def test_a_missing_config_names_the_absolute_path(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "zz")
    assert old.returncode == 1
    assert old.stderr == "✗ Wrangler config not found: %s/workers/account/wrangler.zz.toml\n" % root
    assert old_calls == "", "nothing may be invoked before the config is found"
    _assert_agree(old, new, "missing-config", old_calls, new_calls)


def test_the_two_credential_guards_fire_in_order(tmp_path: pathlib.Path) -> None:
    """`require_var CLOUDFLARE_API_TOKEN` runs first (:38-39), so a run missing
    BOTH names the token. The order is observable and therefore pinned."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(
        tmp_path, root, "--region", "eu", drop_env=("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")
    )
    assert old.returncode == 1
    assert old.stderr == "✗ Required environment variable 'CLOUDFLARE_API_TOKEN' is not set\n"
    _assert_agree(old, new, "both-missing", old_calls, new_calls)

    old, new, old_calls, new_calls = run_both(
        tmp_path, root, "--region", "eu", drop_env=("CLOUDFLARE_ACCOUNT_ID",)
    )
    assert old.returncode == 1
    assert old.stderr == "✗ Required environment variable 'CLOUDFLARE_ACCOUNT_ID' is not set\n"
    _assert_agree(old, new, "account-id-missing", old_calls, new_calls)


def test_an_empty_credential_is_refused_like_an_absent_one(tmp_path: pathlib.Path) -> None:
    """`require_var` tests EMPTINESS through indirect expansion, so
    `CLOUDFLARE_API_TOKEN=` is "not set"."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(
        tmp_path, root, "--region", "eu", CLOUDFLARE_API_TOKEN=""
    )
    assert old.returncode == 1
    assert old.stderr == "✗ Required environment variable 'CLOUDFLARE_API_TOKEN' is not set\n"
    _assert_agree(old, new, "empty-token", old_calls, new_calls)


def test_a_flag_that_is_not_a_shell_identifier_exits_two(tmp_path: pathlib.Path) -> None:
    """`printf -v ARG_FOO.BAR` is `printf`'s own failure inside `common.sh:341`,
    status 2, and under `set -e` it takes the whole script down before anything
    else runs. The port reports the same status with its own prefix."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--foo.bar", "x", "--region", "eu")
    assert old.returncode == 2
    assert new.returncode == 2
    assert old.stderr.endswith("printf: `ARG_FOO.BAR': not a valid identifier\n")
    assert new.stderr == "deploy-account.sh: printf: `ARG_FOO.BAR': not a valid identifier\n"
    assert old_calls == new_calls == ""


# ---------------------------------------------------------------------------
# The database-name pipeline, including the two defects it has
# ---------------------------------------------------------------------------


def test_a_config_with_no_database_name_refuses(tmp_path: pathlib.Path) -> None:
    """THE GUARD THAT DOES WORK (:51-54): grep matching nothing yields an empty
    pipeline output. Note the message names the config RELATIVELY, unlike the
    "config not found" one above, because the run has already `cd`'d."""
    root = _fixture_root(tmp_path, configs={"wrangler.eu.toml": 'name = "account"\n'})
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu")
    assert old.returncode == 1
    assert old.stderr == "✗ Could not read database_name from wrangler.eu.toml\n"
    assert old_calls == "npm\tinstall\n  cwd=account\n", "the install still ran first"
    _assert_agree(old, new, "no-database-name", old_calls, new_calls)


def test_a_comment_becomes_the_database_name(tmp_path: pathlib.Path) -> None:
    """DEFECT, REPRODUCED NOT FIXED. `sed` is a substitution: a first match that
    does not fit the pattern is passed through UNCHANGED, so the guard sees a
    non-empty string and `wrangler d1 migrations apply` is handed a sentence.

    A `tomllib` port would refuse here, or find `real-db`. Either would be a
    different program, which is why this is asserted rather than repaired."""
    root = _fixture_root(
        tmp_path,
        configs={
            "wrangler.eu.toml": (
                "# database_name is chosen per environment\n"
                "[[d1_databases]]\n"
                'database_name = "real-db"\n'
            )
        },
    )
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu")
    assert old.returncode == 0, old.stderr
    assert "apply\t# database_name is chosen per environment\t--remote" in old_calls
    assert "real-db" not in old_calls
    assert port.A_COMMENT_BECOMES_THE_DATABASE_NAME
    _assert_agree(old, new, "comment-as-db-name", old_calls, new_calls)


def test_the_last_quote_on_the_line_wins(tmp_path: pathlib.Path) -> None:
    """DEFECT, REPRODUCED NOT FIXED. Both `.*` in the sed program are greedy, so
    a trailing quoted comment is swallowed into the database name."""
    root = _fixture_root(
        tmp_path,
        configs={"wrangler.eu.toml": 'database_name = "account-db-eu" # was "old-db"\n'},
    )
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu")
    assert old.returncode == 0, old.stderr
    assert 'apply\taccount-db-eu" # was "old-db\t--remote' in old_calls
    assert port.THE_LAST_QUOTE_WINS
    _assert_agree(old, new, "greedy-sed", old_calls, new_calls)


def test_the_first_of_two_database_blocks_wins(tmp_path: pathlib.Path) -> None:
    """`head -1` (:50). A config with two D1 bindings migrates the first and
    never mentions the second."""
    root = _fixture_root(
        tmp_path,
        configs={"wrangler.eu.toml": 'database_name = "first-db"\ndatabase_name = "second-db"\n'},
    )
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu")
    assert old.returncode == 0, old.stderr
    assert "apply\tfirst-db\t--remote" in old_calls
    assert "second-db" not in old_calls
    _assert_agree(old, new, "two-blocks", old_calls, new_calls)


def test_a_tab_indented_unspaced_assignment_still_parses(tmp_path: pathlib.Path) -> None:
    """THE NEGATIVE CONTROL FOR THE TWO DEFECTS ABOVE: the pipeline is not
    simply broken, it reads a legitimately-formatted line correctly."""
    root = _fixture_root(tmp_path, configs={"wrangler.eu.toml": '\tdatabase_name="tabbed"\n'})
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu")
    assert old.returncode == 0, old.stderr
    assert "apply\ttabbed\t--remote" in old_calls
    _assert_agree(old, new, "tabbed", old_calls, new_calls)


# ---------------------------------------------------------------------------
# The install branch and the two child failures
# ---------------------------------------------------------------------------


def test_a_wrangler_on_path_skips_the_install(tmp_path: pathlib.Path) -> None:
    """`! command -v wrangler && [[ ! -d node_modules ]]` (:45): BOTH halves are
    required, so a global wrangler is enough on its own."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu", with_wrangler=True)
    assert old.returncode == 0, old.stderr
    assert "npm\tinstall" not in old_calls
    assert not port.needs_npm_install(
        root / "workers" / "account", {"PATH": str(tmp_path / "old-bin")}
    )
    _assert_agree(old, new, "global-wrangler", old_calls, new_calls)


def test_an_existing_node_modules_skips_the_install(tmp_path: pathlib.Path) -> None:
    """The other half, and it is RELATIVE to the worker directory, not to cwd."""
    root = _fixture_root(tmp_path)
    (root / "workers" / "account" / "node_modules").mkdir()
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu")
    assert old.returncode == 0, old.stderr
    assert "npm\tinstall" not in old_calls
    _assert_agree(old, new, "node-modules-present", old_calls, new_calls)


def test_a_failed_install_ends_the_run_with_npms_status(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu", FAKE_NPM_RC="4")
    assert old.returncode == 4
    assert old.stderr == "npm ERR! install failed\n", "no message of the script's own"
    assert "npx" not in old_calls
    _assert_agree(old, new, "install-failed", old_calls, new_calls)


def test_a_failed_migration_stops_before_the_deploy(tmp_path: pathlib.Path) -> None:
    """`set -e` on :60. The deploy must NOT run, and the exit status is
    wrangler's own, not 1."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu", FAKE_NPX_RC="7")
    assert old.returncode == 7
    assert old_calls.count("npx\t") == 1
    assert "Migrations applied" not in old.stderr
    _assert_agree(old, new, "migration-failed", old_calls, new_calls)


# ---------------------------------------------------------------------------
# Staleness alarms: the port copies three things out of the twin
# ---------------------------------------------------------------------------


def test_the_sed_program_and_the_needle_are_still_the_twins(tmp_path: pathlib.Path) -> None:
    """THE PIPELINE IS A COPY, so the day someone rewrites it in the twin this
    fails instead of the port quietly reading a different key."""
    del tmp_path
    source = _twin_source()
    assert port.SED_PROGRAM in source
    assert "grep '%s'" % port.DB_NAME_NEEDLE in source
    assert "head -1" in source


def test_the_worker_directory_and_config_family_are_still_the_twins(
    tmp_path: pathlib.Path,
) -> None:
    del tmp_path
    source = _twin_source()
    assert "workers/%s" % port.WORKER_SUBDIR[1] in source
    assert 'CONFIG="wrangler.edge-${REGION}.toml"' in source
    assert 'CONFIG="wrangler.${REGION}.toml"' in source
    assert 'TARGET="${ARG_TARGET:-%s}"' % port.DEFAULT_TARGET in source
    assert '"$TARGET" == "%s"' % port.EDGE_TARGET in source
