"""Differential: `rediacc_ci.deploy.deploy_proxy` against its twin
`.ci/scripts/deploy/deploy-proxy.sh`.

RECORDING FAKE `npm` AND `npx` ON A SCRATCH PATH, AND A FIXTURE REPO ROOT.
NOTHING IS BUILT HERE. The twin's first real act is two `npm run build
--workspace` runs from the repo root (:33-34), and the fake `npm` is what stops
them: a differential that let those run would compile `@rediacc/shared` and
`@rediacc/cli` for real, twice per case. The root is made to agree across the
two implementations exactly as in the two sibling differentials -- a COPY of
`common.sh` inside `tmp_path` for the bash side, `$REDIACC_CI_ROOT` for the
port -- and `test_the_copied_twin_is_the_real_twin` keeps the copy honest.

`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one
real run" clause and says in as many words that the mocked parity ledger is a
separate, achievable piece of work. This is that piece. The twin is additionally
MANUAL ONLY by its own header: no workflow invokes it, and CI drives only the
`--dry-run` path.

WHAT THE STREAMS CANNOT SHOW, and therefore what the call log is compared for:
which region reached wrangler (none: the region is printed and never passed),
whether the dry run really passed `--outdir`, and whether the two builds ran
BEFORE the worker directory was looked at. All three are recorded rather than
inferred.

TWO DEFECTS IN THE TWIN ARE PINNED, NOT FIXED:
`test_the_build_runs_before_the_directory_is_checked` shows both builds
completing and only then a failed `cd`, and
`test_the_account_id_is_documented_and_never_checked` shows a run succeeding
with `CLOUDFLARE_ACCOUNT_ID` entirely absent, against a header that lists it as
required.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_proxy as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "deploy-proxy.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "deploy_proxy.py"
COMMON_SH = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
BASH = shutil.which("bash") or "/bin/bash"

# `uname` and `dirname` are what `common.sh` needs at source time; `tr` is
# `to_upper` (common.sh:302), which every `parse_args` key goes through.
PATH_MINIMUM = ("tr", "uname", "dirname")

FAKE_NPX = """#!/usr/bin/python3
import os
import sys

log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("npx\\t" + "\\t".join(sys.argv[1:]) + "\\n")
    fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")

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
    sys.stderr.write("npm ERR! build failed\\n")
    sys.exit(rc)
sys.stdout.write("> build done\\n")
"""

BASE_ENV = {"CLOUDFLARE_API_TOKEN": "tok"}

# The whole stderr of a successful real deploy, in order. Quoted once here because four tests need to say "and not this".
DEPLOY_STDERR = (
    "→ Building the CLI bundle the container image ships...\n"
    "→ Deploying the proxy worker and container image (region: eu)...\n"
    "✓ Deployed. The executor still needs its own account token:\n"
    "✓   npx wrangler secret put EXECUTOR_TOKEN --config workers/proxy/wrangler.toml\n"
    "✓ That token must carry the proxy:exec scope and belong to the Rediacc org.\n"
)


def _fixture_root(tmp_path: pathlib.Path, *, worker: str = "dir") -> pathlib.Path:
    """A repo root holding a COPY of the twin, its library, and `workers/proxy`.

    `worker` is `dir` for the normal case, `file` for the "Not a directory" one,
    and `absent` for the missing-directory defect.
    """
    root = tmp_path / "root"
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / "workers").mkdir(parents=True, exist_ok=True)
    shutil.copy2(COMMON_SH, root / ".ci" / "scripts" / "lib" / COMMON_SH.name)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    target = root / "workers" / "proxy"
    if worker == "dir":
        target.mkdir(exist_ok=True)
        (target / "wrangler.toml").write_text('name = "rediacc-proxy"\n', encoding="utf-8")
    elif worker == "file":
        target.write_text("not a directory\n", encoding="utf-8")
    return root


def _bin(tmp_path: pathlib.Path, name: str) -> str:
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
    return str(stub)


def _run(
    subject: pathlib.Path,
    tmp_path: pathlib.Path,
    root: pathlib.Path,
    args: tuple[str, ...],
    *,
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    side = "old" if subject.suffix == ".sh" else "new"
    call_log = tmp_path / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin"),
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


def test_the_copied_twin_is_the_real_twin(tmp_path: pathlib.Path) -> None:
    """THE COPY IS THE SUBJECT, so a stale copy would silently pass everything."""
    root = _fixture_root(tmp_path)
    copied = root / ".ci" / "scripts" / "deploy" / TWIN.name
    assert copied.read_bytes() == TWIN.read_bytes()
    assert (root / ".ci" / "scripts" / "lib" / "common.sh").read_bytes() == COMMON_SH.read_bytes()


# --------------------------------------------------------------------------- The real deploy ---------------------------------------------------------------------------


def test_the_default_run_is_a_real_deploy_and_is_pinned_in_full(tmp_path: pathlib.Path) -> None:
    """TWO BUILDS FROM THE ROOT, THEN ONE BARE `wrangler deploy` FROM THE WORKER
    DIRECTORY. Note the deploy carries no `--config`, unlike both siblings, and
    that `--dry-run` defaults to false so the DEFAULT is the deploying path."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == 0, old.stderr
    assert old_calls == (
        "npm\trun\tbuild\t--workspace\t@rediacc/shared\n"
        "  cwd=root\n"
        "npm\trun\tbuild\t--workspace\t@rediacc/cli\n"
        "  cwd=root\n"
        "npx\twrangler\tdeploy\n"
        "  cwd=proxy\n"
    )
    assert old.stderr == DEPLOY_STDERR
    assert old.stdout == "> build done\n> build done\nTotal Upload: 1.00 KiB\n"
    _assert_agree(old, new, "default-deploy", old_calls, new_calls)


def test_the_three_closing_lines_all_carry_the_check_glyph(tmp_path: pathlib.Path) -> None:
    """THEY GO THROUGH `log_info`, INCLUDING THE ONE THAT IS A COMMAND TO COPY
    (:49). A reader pasting that line pastes a `✓ ` and two spaces with it, so
    the port must not "clean up" the middle line into a plain print."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    for line in port.CLOSING_LINES:
        assert "✓ %s\n" % line in old.stderr
    assert "✓   npx wrangler secret put" in old.stderr
    _assert_agree(old, new, "closing-lines", old_calls, new_calls)


def test_the_region_is_printed_and_never_passed_to_wrangler(tmp_path: pathlib.Path) -> None:
    """`REGION` REACHES ONE LOG LINE AND NO ARGV (:26, :45). Two regions produce
    two different messages and byte-identical calls, which is the whole point of
    comparing the call log rather than the streams alone."""
    root = _fixture_root(tmp_path)
    eu_old, eu_new, eu_old_calls, eu_new_calls = run_both(tmp_path, root)
    as_old, as_new, as_old_calls, as_new_calls = run_both(tmp_path, root, "--region", "asia")
    assert as_old.returncode == 0, as_old.stderr
    assert "(region: asia)" in as_old.stderr
    assert as_old_calls == eu_old_calls
    assert _twin_source().count("$REGION") == 1
    _assert_agree(eu_old, eu_new, "region-eu", eu_old_calls, eu_new_calls)
    _assert_agree(as_old, as_new, "region-asia", as_old_calls, as_new_calls)


def test_an_absent_region_defaults_to_eu(tmp_path: pathlib.Path) -> None:
    """`${ARG_REGION:-eu}` (:26), and `--region=` is EMPTY, which the `:-` form
    also replaces. A port using `args.get("ARG_REGION", "eu")` would print an
    empty region for the second case."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region=")
    assert "(region: %s)" % port.DEFAULT_REGION in old.stderr
    _assert_agree(old, new, "empty-region", old_calls, new_calls)


# --------------------------------------------------------------------------- The dry run ---------------------------------------------------------------------------


def test_a_bare_dry_run_flag_takes_the_dry_run_path(tmp_path: pathlib.Path) -> None:
    """`parse_args` stores the string `true` for a flag with no value, which is
    exactly what `[[ "$DRY_RUN" == "true" ]]` (:38) wants. The run exits 0 at
    :42, so none of the three closing lines print."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--dry-run")
    assert old.returncode == 0, old.stderr
    assert old_calls.endswith(
        "npx\twrangler\tdeploy\t--dry-run\t--outdir\t/tmp/rediacc-proxy-dry-run\n  cwd=proxy\n"
    )
    assert old.stderr == (
        "→ Building the CLI bundle the container image ships...\n"
        "→ Dry run: type-checking and compiling the worker without deploying...\n"
        "✓ Dry run passed. Nothing was deployed.\n"
    )
    assert "EXECUTOR_TOKEN" not in old.stderr
    _assert_agree(old, new, "dry-run-bare", old_calls, new_calls)


def test_the_dry_run_still_builds_first(tmp_path: pathlib.Path) -> None:
    """THE BUILD IS NOT SKIPPED ON A DRY RUN (:31-34 run before the branch at
    :38), which is what makes the dry run a real check of the CLI bundle."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--dry-run")
    assert old_calls.count("npm\trun\tbuild") == 2
    _assert_agree(old, new, "dry-run-builds", old_calls, new_calls)


def test_only_the_literal_true_is_a_dry_run(tmp_path: pathlib.Path) -> None:
    """`--dry-run yes` IS A REAL DEPLOY. The comparison at :38 is against the
    string `true` and nothing else, so a plausible-looking value deploys the
    executor. Driven in both directions rather than argued."""
    root = _fixture_root(tmp_path)
    for value, deploying in (("true", False), ("false", True), ("yes", True), ("1", True)):
        old, new, old_calls, new_calls = run_both(tmp_path, root, "--dry-run", value)
        assert old.returncode == 0, old.stderr
        assert ("--dry-run" not in old_calls) is deploying, value
        assert ("EXECUTOR_TOKEN" in old.stderr) is deploying, value
        _assert_agree(old, new, "dry-run-%s" % value, old_calls, new_calls)


def test_the_dry_run_outdir_is_a_fixed_tmp_path(tmp_path: pathlib.Path) -> None:
    """NOT A `mktemp` (:40). Two concurrent dry runs write the same directory,
    and so does anything else that picks the name. Reproduced as the literal."""
    del tmp_path
    assert port.DRY_RUN_OUTDIR in _twin_source()
    assert "mktemp" not in _twin_source()


# --------------------------------------------------------------------------- Refusals and failures ---------------------------------------------------------------------------


def test_a_missing_token_refuses_before_the_build(tmp_path: pathlib.Path) -> None:
    """THE ONE DIVERGENCE ON THIS PATH, asserted from both sides: bash prefixes
    its `${VAR:?}` diagnostic with the script path as invoked and a line number.
    The doubled variable name is the twin's own message, not a mistake here.

    THE ORDER IS THE POINT: nothing is built, so the refusal is cheap."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, drop_env=("CLOUDFLARE_API_TOKEN",))
    assert old.returncode == 1
    assert new.returncode == 1
    assert old.stderr.endswith(port.MISSING_TOKEN + "\n")
    assert ": line 29: " in old.stderr
    assert new.stderr == port.MISSING_TOKEN + "\n"
    assert old.stdout == new.stdout == ""
    assert old_calls == new_calls == "", "nothing may be built before the token is checked"


def test_an_empty_token_refuses_exactly_as_an_absent_one_does(tmp_path: pathlib.Path) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST."""
    root = _fixture_root(tmp_path)
    old, new, _, _ = run_both(tmp_path, root, CLOUDFLARE_API_TOKEN="")
    assert old.returncode == new.returncode == 1
    assert old.stderr.endswith(port.MISSING_TOKEN + "\n")
    assert new.stderr == port.MISSING_TOKEN + "\n"


def test_the_account_id_is_documented_and_never_checked(tmp_path: pathlib.Path) -> None:
    """DEFECT, REPRODUCED NOT FIXED. The header (:16) lists
    `CLOUDFLARE_ACCOUNT_ID` under "Requires:" and no line reads it, so a run
    without it builds the CLI and calls wrangler anyway."""
    source = _twin_source()
    assert source.count("CLOUDFLARE_ACCOUNT_ID") == 1, "the header mention, and nothing else"
    assert "require_var" not in source
    assert port.THE_ACCOUNT_ID_IS_DOCUMENTED_AND_UNCHECKED
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == 0, old.stderr
    assert "npx\twrangler\tdeploy\n" in old_calls
    _assert_agree(old, new, "no-account-id", old_calls, new_calls)


def test_the_build_runs_before_the_directory_is_checked(tmp_path: pathlib.Path) -> None:
    """DEFECT, REPRODUCED NOT FIXED. There is no guard on `workers/proxy` (:36),
    unlike the `-f` checks both siblings do FIRST, so a missing worker directory
    costs a full CLI build before bash's own `cd` diagnostic ends the run.

    The divergence in that diagnostic is the usual one: bash prefixes it with
    the script path and a line number."""
    root = _fixture_root(tmp_path, worker="absent")
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == 1
    assert new.returncode == 1
    assert old_calls.count("npm\trun\tbuild") == 2, "both builds ran anyway"
    assert new_calls == old_calls
    tail = port.cd_failed(root / "workers" / "proxy", "No such file or directory")
    assert old.stderr.endswith(tail + "\n")
    assert ": line 36: " in old.stderr
    assert new.stderr.endswith(tail + "\n")
    assert port.THE_BUILD_RUNS_BEFORE_THE_DIRECTORY_IS_CHECKED


def test_a_worker_path_that_is_a_file_says_not_a_directory(tmp_path: pathlib.Path) -> None:
    """THE REASON COMES FROM THE OPERATING SYSTEM, NOT FROM A LITERAL. A port
    that hard-coded "No such file or directory" would be wrong here, and the
    only way to notice is to drive the case."""
    root = _fixture_root(tmp_path, worker="file")
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == new.returncode == 1
    tail = port.cd_failed(root / "workers" / "proxy", "Not a directory")
    assert old.stderr.endswith(tail + "\n")
    assert new.stderr.endswith(tail + "\n")
    assert new_calls == old_calls


def test_a_failed_first_build_stops_before_the_second(tmp_path: pathlib.Path) -> None:
    """`set -e` on :33. `@rediacc/cli` must NOT be built, and the status is
    npm's own."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, FAKE_NPM_RC="2")
    assert old.returncode == 2
    assert old_calls.count("npm\trun\tbuild") == 1
    assert "@rediacc/cli" not in old_calls
    _assert_agree(old, new, "build-failed", old_calls, new_calls)


def test_a_failed_dry_run_propagates_wranglers_status(tmp_path: pathlib.Path) -> None:
    """`set -e` on :40: the "Dry run passed" line must NOT print."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--dry-run", FAKE_NPX_RC="5")
    assert old.returncode == 5
    assert "Dry run passed" not in old.stderr
    _assert_agree(old, new, "dry-run-failed", old_calls, new_calls)


def test_a_failed_deploy_prints_none_of_the_closing_lines(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, FAKE_NPX_RC="6")
    assert old.returncode == 6
    for line in port.CLOSING_LINES:
        assert line not in old.stderr
    _assert_agree(old, new, "deploy-failed", old_calls, new_calls)


def test_a_flag_that_is_not_a_shell_identifier_exits_two(tmp_path: pathlib.Path) -> None:
    """`parse_args` IS CALLED HERE (:22), unlike in `deploy-edge.sh`, so a flag
    bash cannot turn into a variable name kills the run with `printf`'s status
    before the token is even looked at."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--foo.bar", "x")
    assert old.returncode == 2
    assert new.returncode == 2
    assert old.stderr.endswith("printf: `ARG_FOO.BAR': not a valid identifier\n")
    assert new.stderr == "deploy-proxy.sh: printf: `ARG_FOO.BAR': not a valid identifier\n"
    assert old_calls == new_calls == ""


# --------------------------------------------------------------------------- Staleness alarms: the port copies six things out of the twin ---------------------------------------------------------------------------


def test_the_literals_are_still_the_twins(tmp_path: pathlib.Path) -> None:
    del tmp_path
    source = _twin_source()
    assert "workers/%s" % port.WORKER_SUBDIR[1] in source
    assert 'REGION="${ARG_REGION:-%s}"' % port.DEFAULT_REGION in source
    assert 'DRY_RUN="${ARG_DRY_RUN:-%s}"' % port.DEFAULT_DRY_RUN in source
    assert '"$DRY_RUN" == "%s"' % port.TRUE in source
    for workspace in port.WORKSPACES:
        assert "npm run build --workspace %s" % workspace in source
    for line in port.CLOSING_LINES:
        assert 'log_info "%s"' % line in source


def test_the_deploy_call_still_carries_no_config_flag(tmp_path: pathlib.Path) -> None:
    """THE DIFFERENCE FROM BOTH SIBLINGS, re-derived rather than remembered.

    The twin names `--config` exactly ONCE, and it is inside the closing
    `log_info` that tells a human what to paste next -- never on a line this
    script runs. If a `--config` ever appears on the deploy itself, this fails
    instead of the port silently deploying a different Worker."""
    del tmp_path
    source = _twin_source()
    assert "npx wrangler deploy\n" in source
    config_lines = [line for line in source.splitlines() if "--config" in line]
    assert config_lines == [
        'log_info "  npx wrangler secret put EXECUTOR_TOKEN --config workers/proxy/wrangler.toml"'
    ]
    assert port.deploy_argv() == ["npx", "wrangler", "deploy"]
