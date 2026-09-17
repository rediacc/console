"""Differential: `rediacc_ci.deploy.deploy_edge` against its twin
`.ci/scripts/deploy/deploy-edge.sh`.

RECORDING FAKE `npx` AND `npm` ON A SCRATCH PATH, AND A FIXTURE REPO ROOT. Nothing here reaches Cloudflare and nothing installs anything. The root is made to agree across the two implementations the same way the `deploy_account` differential does it, and for the same reason: the twin's `get_repo_root` resolves from a COPY of `common.sh` inside `tmp_path`, and the port's
`common.repo_root()` is pointed at the same directory with `$REDIACC_CI_ROOT`. `test_the_copied_twin_is_the_real_twin` keeps the copy honest.

THIS SCRIPT IS NOT ITS SIBLING WITH THE MIGRATIONS REMOVED, and three tests exist only to hold that line, because "the account file, shorter" is the assumption that would port it wrong:

  * `test_every_argument_is_ignored` drives `--foo.bar x`, which exits 2 in the
    account sibling and exits 0 here, because there is no `parse_args` call.
  * `test_a_global_wrangler_does_not_skip_the_install` drives the case where the
    two conditions genuinely disagree.
  * `test_the_install_condition_is_still_the_one_condition_form` re-derives the
    condition from the twin's own source, so the day the two files are
    harmonised this fails rather than the port quietly keeping the old shape.

`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_edge as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "deploy-edge.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "deploy_edge.py"
ACCOUNT_TWIN = ROOT / ".ci" / "scripts" / "deploy" / "deploy-account.sh"
COMMON_SH = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
BASH = shutil.which("bash") or "/bin/bash"

# `uname` and `dirname` are what `common.sh` needs at source time; `tr` is the
# token strip at :27 on the bash side. Nothing else is on the scratch PATH.
PATH_MINIMUM = ("tr", "uname", "dirname")

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

# Found by `command -v`, never executed. It exists so the ONE case where this script and its account sibling disagree can be driven.
FAKE_WRANGLER = "#!/usr/bin/python3\nraise SystemExit('the fake wrangler must never run')\n"

BASE_ENV = {
    "CLOUDFLARE_API_TOKEN": "tok",
    "CLOUDFLARE_ACCOUNT_ID": "acct",
}


def _fixture_root(tmp_path: pathlib.Path, *, config: bool = True) -> pathlib.Path:
    """A repo root holding a COPY of the twin, its library, and `workers/www`."""
    root = tmp_path / "root"
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    worker = root / "workers" / "www"
    worker.mkdir(parents=True, exist_ok=True)
    shutil.copy2(COMMON_SH, root / ".ci" / "scripts" / "lib" / COMMON_SH.name)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    if config:
        (worker / port.CONFIG).write_text('name = "rediacc-www-edge"\n', encoding="utf-8")
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


def test_the_copied_twin_is_the_real_twin(tmp_path: pathlib.Path) -> None:
    """THE COPY IS THE SUBJECT, so a stale copy would silently pass everything."""
    root = _fixture_root(tmp_path)
    copied = root / ".ci" / "scripts" / "deploy" / TWIN.name
    assert copied.read_bytes() == TWIN.read_bytes()
    assert (root / ".ci" / "scripts" / "lib" / "common.sh").read_bytes() == COMMON_SH.read_bytes()


def test_the_one_wrangler_call_is_pinned_in_full(tmp_path: pathlib.Path) -> None:
    """ONE DEPLOY, no migrations, from inside `workers/www`, carrying the token."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == 0, old.stderr
    assert old_calls == (
        "npm\tinstall\n"
        "  cwd=www\n"
        "npx\twrangler\tdeploy\t--config\twrangler.edge.toml\n"
        "  cwd=www\n"
        "  token='tok'\n"
    )
    assert old.stderr == ("→ Deploying edge worker (edge.rediacc.com)...\n✓ Edge worker deployed\n")
    assert old.stdout == "added 1 package\nTotal Upload: 1.00 KiB\n"
    assert "d1" not in old_calls, "there is no database here"
    _assert_agree(old, new, "happy-path", old_calls, new_calls)


def test_every_argument_is_ignored(tmp_path: pathlib.Path) -> None:
    """NO `parse_args` CALL AT ALL (contrast `deploy-account.sh:17`). `--foo.bar`
    exits 2 in the account sibling and is invisible here, and `--region eu` does
    not mean anything either. Both sides must agree that they mean nothing."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region", "eu", "--foo.bar", "x")
    assert old.returncode == 0, old.stderr
    assert port.ARGUMENTS_ARE_IGNORED
    assert "parse_args" not in _twin_source()
    _assert_agree(old, new, "arguments-ignored", old_calls, new_calls)


def test_a_missing_config_names_the_absolute_path(tmp_path: pathlib.Path) -> None:
    """:17-20. Note the wording differs from the account sibling's ("not found
    at" versus "not found:"), so the two messages are not interchangeable."""
    root = _fixture_root(tmp_path, config=False)
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == 1
    assert old.stderr == (
        "✗ Edge worker config not found at %s/workers/www/wrangler.edge.toml\n" % root
    )
    assert old_calls == "", "nothing may be invoked before the config is found"
    _assert_agree(old, new, "missing-config", old_calls, new_calls)


def test_the_two_credential_guards_fire_in_order(tmp_path: pathlib.Path) -> None:
    """`require_var CLOUDFLARE_API_TOKEN` first (:24-25), so a run missing BOTH
    names the token."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(
        tmp_path, root, drop_env=("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")
    )
    assert old.returncode == 1
    assert old.stderr == "✗ Required environment variable 'CLOUDFLARE_API_TOKEN' is not set\n"
    _assert_agree(old, new, "both-missing", old_calls, new_calls)

    old, new, old_calls, new_calls = run_both(tmp_path, root, drop_env=("CLOUDFLARE_ACCOUNT_ID",))
    assert old.returncode == 1
    assert old.stderr == "✗ Required environment variable 'CLOUDFLARE_ACCOUNT_ID' is not set\n"
    _assert_agree(old, new, "account-id-missing", old_calls, new_calls)


def test_an_empty_credential_is_refused_like_an_absent_one(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, CLOUDFLARE_ACCOUNT_ID="")
    assert old.returncode == 1
    assert old.stderr == "✗ Required environment variable 'CLOUDFLARE_ACCOUNT_ID' is not set\n"
    _assert_agree(old, new, "empty-account-id", old_calls, new_calls)


def test_the_account_id_is_demanded_and_then_never_used(tmp_path: pathlib.Path) -> None:
    """THE VACUITY CLASS, NAMED: `CLOUDFLARE_ACCOUNT_ID` is required at :25 and
    read by nothing in the file. A WRONG one passes every check here."""
    source = _twin_source()
    assert source.count("CLOUDFLARE_ACCOUNT_ID") == 2, "one header mention, one require_var"
    assert "$CLOUDFLARE_ACCOUNT_ID" not in source
    assert port.THE_ACCOUNT_ID_IS_CHECKED_AND_UNUSED
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, CLOUDFLARE_ACCOUNT_ID="wrong-account")
    assert old.returncode == 0, old.stderr
    _assert_agree(old, new, "wrong-account-id", old_calls, new_calls)


def test_the_token_is_stripped_of_carriage_returns_before_the_child_sees_it(
    tmp_path: pathlib.Path,
) -> None:
    """`tr -d '\\r\\n'` (:27)."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        root,
        CLOUDFLARE_API_TOKEN="\nto\rk\n",  # noqa: S106 -- a fixture value that authenticates nowhere
    )
    assert old.returncode == 0, old.stderr
    assert "  token='tok'\n" in old_calls
    assert port.strip_newlines("\nto\rk\n") == "tok"
    _assert_agree(old, new, "token-strip", old_calls, new_calls)


def test_the_two_strip_lines_still_agree_across_the_siblings(tmp_path: pathlib.Path) -> None:
    """WHY THE PORT DOES NOT SHARE ONE HELPER. The line is duplicated in both
    twins today; this asserts that, so the duplication in the ports is a checked
    fact rather than an assumption, and so a change to one twin shows up here."""
    del tmp_path
    line = "CLOUDFLARE_API_TOKEN=\"$(printf '%s' \"$CLOUDFLARE_API_TOKEN\" | tr -d '\\r\\n')\""
    assert line in _twin_source()
    assert line in ACCOUNT_TWIN.read_text(encoding="utf-8")


def test_an_existing_node_modules_skips_the_install(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "workers" / "www" / "node_modules").mkdir()
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == 0, old.stderr
    assert "npm\tinstall" not in old_calls
    assert not port.needs_npm_install(root / "workers" / "www")
    _assert_agree(old, new, "node-modules-present", old_calls, new_calls)


def test_a_global_wrangler_does_not_skip_the_install(tmp_path: pathlib.Path) -> None:
    """THE CASE WHERE THE TWO SIBLINGS DISAGREE. `deploy-account.sh:45` also
    tests `command -v wrangler`; this one does not, so the install runs anyway."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, with_wrangler=True)
    assert old.returncode == 0, old.stderr
    assert old_calls.startswith("npm\tinstall\n")
    _assert_agree(old, new, "global-wrangler", old_calls, new_calls)


def test_the_install_condition_is_still_the_one_condition_form(tmp_path: pathlib.Path) -> None:
    """STALENESS ALARM for the test above: the day someone harmonises the two
    scripts, this fails instead of the port keeping a condition nobody has."""
    del tmp_path
    source = _twin_source()
    assert 'if [[ ! -d "node_modules" ]]; then' in source
    assert "command -v wrangler" not in source
    assert "command -v wrangler" in ACCOUNT_TWIN.read_text(encoding="utf-8")


def test_a_failed_install_ends_the_run_with_npms_status(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, FAKE_NPM_RC="9")
    assert old.returncode == 9
    assert old.stderr == "npm ERR! install failed\n", "no message of the script's own"
    assert "npx" not in old_calls
    _assert_agree(old, new, "install-failed", old_calls, new_calls)


def test_a_failed_deploy_propagates_wranglers_status(tmp_path: pathlib.Path) -> None:
    """`set -e` on :36: the closing `log_info` must NOT print, and the status is
    wrangler's own rather than 1."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, FAKE_NPX_RC="3")
    assert old.returncode == 3
    assert "Edge worker deployed" not in old.stderr
    _assert_agree(old, new, "deploy-failed", old_calls, new_calls)


def test_the_config_name_and_worker_directory_are_still_the_twins(tmp_path: pathlib.Path) -> None:
    """STALENESS ALARM: the port holds three literals copied out of the twin."""
    del tmp_path
    source = _twin_source()
    assert source.count(port.CONFIG) == 3, "the test at :17, its message at :18, the deploy at :36"
    assert "workers/%s" % port.WORKER_SUBDIR[1] in source
    assert "npx wrangler deploy --config %s" % port.CONFIG in source
    for name in port.REQUIRED_VARS:
        assert "require_var %s" % name in source
