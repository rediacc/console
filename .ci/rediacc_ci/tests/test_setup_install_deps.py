"""Differential: `rediacc_ci.setup.install_deps` against its twin
`.ci/scripts/setup/install-deps.sh`.

NOTHING HERE RUNS A REAL `npm ci`. A recording fake `npm` sits on a scratch PATH, logs its exact argv AND the directory it was called in, echoes the same under a `call: ` prefix, and exits with whatever the environment tells it to. The one thing this script does is decide which `npm` runs where and with which flags, so the CALL LOG is the primary evidence and the two streams are
the secondary.

WHY THE DIRECTORY IS PART OF EVERY LOGGED CALL. The root install and the three account installs are the same two words -- `npm ci` -- and differ only in the working directory. A log that recorded argv alone could not tell a run that installed the root four times from a correct one, which is precisely the regression a port could introduce by dropping the subshell `cd`.

`sleep` AND `uname` ARE FAKED ON BOTH SIDES, SYMMETRICALLY, and that needs saying because the two mechanisms look different:

  * bash resolves `sleep` and `uname` through PATH, so the fakes are executables
    in the stub directory.
  * Python calls `time.sleep` and `platform.system()`, which no PATH entry can
    reach, so `harness/sitecustomize.py` patches those two functions at
    interpreter startup -- before `rediacc_ci` is imported, which matters
    because `proc.retry_with_backoff` binds `time.sleep` as a default argument
    at import time.

Both fakes write the SAME `sleep\\t<seconds>` line into the same call log, so the backoff schedule is compared rather than waited for. Without them each failing
case would cost 30 real seconds per side; with them the schedule itself is an
assertion (`10` then `20`, never a third).

THE LEDGER LINE. `shadow-gate.ts` classifies any line starting with `→ ` or `✓ ` as CHATTER before `--finding-re` is ever consulted, and this script reports almost entirely through `log_step`/`log_info`. The fake's `call: npm [...] ...`
line on stdout is what gives the shadow ledger something to compare; see
`.ci/shadow/w7p6-install-deps.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.setup import install_deps as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/setup/install-deps.sh"
PORT_REL = ".ci/rediacc_ci/setup/install_deps.py"
BASH = shutil.which("bash") or "/bin/bash"

# The files a fixture tree needs: the twin, the bash library it sources, and the Python modules the port imports transitively. Listed explicitly rather than copied with a wildcard, so a new dependency appears here as an edit instead of being dragged in silently.
TREE_FILES = (
    TWIN_REL,
    ".ci/scripts/lib/common.sh",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/proc.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/setup/__init__.py",
    PORT_REL,
)

# `common.sh` needs `dirname` at source time and `uname`/`tr` inside the detection helpers it runs there. `sleep` and `uname` are the two fakes.
PATH_MINIMUM = ("dirname", "tr")

FAKE_NPM = """#!{python}
import os
import shlex
import sys

argv = sys.argv[1:]
root = os.environ.get("FAKE_TREE_ROOT") or os.getcwd()
where = os.path.relpath(os.getcwd(), root)

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("npm\\t" + where + "\\t" + "\\t".join(argv) + "\\n")

# THE LEDGER LINE, on stdout under a prefix no CHATTER rule matches. See the
# module docstring: a `→ `/`✓ ` line can never become a shadow-gate finding.
sys.stdout.write(
    "call: npm [" + where + "] " + " ".join(shlex.quote(a) for a in argv) + "\\n"
)

rc = int(os.environ.get("FAKE_NPM_RC") or 0)
if os.environ.get("FAKE_NPM_FAIL_IN") == where:
    rc = int(os.environ.get("FAKE_NPM_FAIL_RC") or 1)
sys.exit(rc)
"""

# Records the delay and returns instantly. `$1` is bash's integer, printed unchanged so it can be compared against the port's `%g`-formatted float.
FAKE_SLEEP = """#!/bin/sh
printf 'sleep\\t%s\\n' "$1" >> "$FAKE_CALL_LOG"
"""

# `-s` is the only question `detect_os` asks; everything else is handed to the
# real binary so `detect_arch`'s `uname -m` still answers truthfully on both sides. NOT logged: OS detection is a query, not an effect, and logging it would need a matching hook on the Python side for no gain.
FAKE_UNAME = """#!/bin/sh
if [ "$1" = "-s" ]; then
    printf '%s\\n' "${{FAKE_UNAME_S:-Linux}}"
    exit 0
fi
exec {real} "$@"
"""

# The Python half of the sleep and uname fakes. Imported by `site` at interpreter startup, which is EARLIER than any `rediacc_ci` import -- required, because `proc.retry_with_backoff` captures `time.sleep` as a default argument when `proc` is imported.
SITECUSTOMIZE = '''"""Test harness only. Fakes the two primitives bash reaches through PATH."""

import os

_LOG = os.environ.get("FAKE_CALL_LOG")
if _LOG:
    import time as _time

    def _sleep(seconds):
        with open(_LOG, "a") as fh:
            fh.write("sleep\\t%g\\n" % float(seconds))

    _time.sleep = _sleep

_UNAME_S = os.environ.get("FAKE_UNAME_S")
if _UNAME_S:
    import platform as _platform

    _platform.system = lambda: _UNAME_S
'''


def _bin(tree: pathlib.Path, *, drop: str = "") -> str:
    stub = tree / "stub-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    real_uname = shutil.which("uname")
    assert real_uname is not None, "uname is missing from this machine"
    (stub / "uname").write_text(FAKE_UNAME.format(real=real_uname), encoding="utf-8")
    (stub / "uname").chmod(0o755)
    (stub / "sleep").write_text(FAKE_SLEEP, encoding="utf-8")
    (stub / "sleep").chmod(0o755)
    if drop != "npm":
        (stub / "npm").write_text(FAKE_NPM.format(python=sys.executable), encoding="utf-8")
        (stub / "npm").chmod(0o755)
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def _tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """A miniature checkout whose root is `tmp_path/tree`.

    Both implementations derive the repo root from their OWN location -- the twin
    from `common.sh` three directories up, the port from `paths.py` two up -- so
    placing the copies at their real relative paths makes `tmp_path/tree` the root for both, with no environment variable involved.
    """
    tree = tmp_path / "tree"
    if tree.exists():
        return tree
    for rel in TREE_FILES:
        dest = tree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    harness = tree / "harness"
    harness.mkdir(parents=True, exist_ok=True)
    (harness / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    return tree


def _layout(
    tree: pathlib.Path,
    *,
    node_modules: bool = True,
    accounts: tuple[str, ...] = (),
) -> None:
    """Rebuild the mutable parts, so each side starts from the same state."""
    shutil.rmtree(tree / "node_modules", ignore_errors=True)
    shutil.rmtree(tree / "private", ignore_errors=True)
    if node_modules:
        (tree / "node_modules").mkdir(parents=True, exist_ok=True)
    for rel in accounts:
        directory = tree / rel
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "package.json").write_text("{}\n", encoding="utf-8")


def _run(subject: str, tree: pathlib.Path, args: list[str], *, drop: str = "", **extra: str):
    side = "old" if subject.endswith(".sh") else "new"
    call_log = tree / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tree, drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": os.pathsep.join([str(tree / ".ci"), str(tree / "harness")]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_TREE_ROOT": str(tree),
    }
    env.update(extra)
    runner = [BASH] if subject.endswith(".sh") else [sys.executable]
    proc = subprocess.run(
        [*runner, subject, *args],
        cwd=tree,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


def run_both(tmp_path: pathlib.Path, args: list[str], **kw):
    layout_kw = {k: kw.pop(k) for k in ("node_modules", "accounts") if k in kw}
    tree = _tree(tmp_path)
    _layout(tree, **layout_kw)
    old, old_calls = _run(TWIN_REL, tree, args, **kw)
    _layout(tree, **layout_kw)
    new, new_calls = _run(PORT_REL, tree, args, **kw)
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
            f"{label}: call sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


ACCOUNT_ALL = ("private/account", "private/account/web", "private/account/e2e")


# --------------------------------------------------------------------------- The default path ---------------------------------------------------------------------------


def test_the_bare_run_is_one_npm_ci_at_the_root(tmp_path: pathlib.Path) -> None:
    """PINNED AGAINST LITERAL BYTES rather than against the port's own constants,
    so a change made in BOTH implementations is still caught."""
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    assert old.returncode == 0
    assert old_calls == ["npm\t.\tci"]
    assert old.stdout == "call: npm [.] ci\n"
    assert old.stderr == (
        "→ Installing npm dependencies...\n"
        "✓ Dependencies installed successfully\n"
        "✓ npm install complete\n"
    )
    _assert_agree(old, new, "default", old_calls, new_calls)


def test_ignore_scripts_adds_the_flag_and_announces_it(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--ignore-scripts"])
    assert old_calls == ["npm\t.\tci\t--ignore-scripts"]
    assert old.stderr.splitlines()[1] == "✓ Using --ignore-scripts flag"
    _assert_agree(old, new, "--ignore-scripts", old_calls, new_calls)


def test_windows_adds_the_flag_with_no_argument_at_all(tmp_path: pathlib.Path) -> None:
    """`CI_OS == "windows"` is the other half of the `||` at install-deps.sh:50.
    The twin reads it from `uname -s` at source time; the port from
    `platform.system()`. Both are faked to `MINGW64_NT-10.0`, which is one of the
    three prefixes `detect_os` maps to `windows`."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_UNAME_S="MINGW64_NT-10.0-19045")
    assert old_calls == ["npm\t.\tci\t--ignore-scripts"]
    assert "✓ Using --ignore-scripts flag\n" in old.stderr
    _assert_agree(old, new, "windows", old_calls, new_calls)


def test_darwin_does_not_add_the_flag(tmp_path: pathlib.Path) -> None:
    """THE NEGATIVE CONTROL for the platform branch. A gate with only positive
    controls will happily flag the whole tree, and a port that answered
    `windows` for everything would pass every test above."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_UNAME_S="Darwin")
    assert old_calls == ["npm\t.\tci"]
    assert "--ignore-scripts" not in old.stderr
    _assert_agree(old, new, "darwin", old_calls, new_calls)


def test_an_unrecognised_flag_is_ignored_in_silence(tmp_path: pathlib.Path) -> None:
    """Fact 4. The `case` has no `*)` arm, so `--ignore-script` (singular, a
    plausible typo) neither warns nor adds the flag it looks like."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--ignore-script", "extra"])
    assert old.returncode == 0
    assert old_calls == ["npm\t.\tci"]
    _assert_agree(old, new, "typo", old_calls, new_calls)


# --------------------------------------------------------------------------- Failure paths ---------------------------------------------------------------------------


def test_a_failing_npm_retries_three_times_on_the_10_20_schedule(
    tmp_path: pathlib.Path,
) -> None:
    """THREE ATTEMPTS AND TWO SLEEPS, never three: `common.sh:225` sleeps only
    when another attempt is coming. Both error lines are asserted, in order -- the helper's `Command failed after 3 attempts` and then the caller's `Failed to install dependencies after retries`. A port that printed only the
    caller's would lose the attempt count."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_NPM_RC="1")
    assert old.returncode == 1
    assert old_calls == [
        "npm\t.\tci",
        "sleep\t10",
        "npm\t.\tci",
        "sleep\t20",
        "npm\t.\tci",
    ]
    assert old.stderr == (
        "→ Installing npm dependencies...\n"
        "⚠ Attempt 1/3 failed, retrying in 10s...\n"
        "⚠ Attempt 2/3 failed, retrying in 20s...\n"
        "✗ Command failed after 3 attempts\n"
        "✗ Failed to install dependencies after retries\n"
    )
    _assert_agree(old, new, "npm-fails", old_calls, new_calls)


def test_a_127_from_a_missing_npm_is_retried_like_any_other_failure(
    tmp_path: pathlib.Path,
) -> None:
    """Fact 5: there is no `require_cmd npm`, so an absent binary spends 30
    seconds of backoff and then reports a registry-shaped message. Driven by dropping `npm` from the stub PATH entirely.

    THE ONE DIVERGENCE IN THE WHOLE PAIR IS PINNED HERE, AS A PREFIX. Bash writes
    `<script>: line 60: npm: command not found`; the port writes
    `npm: command not found`. The prefix names a bash file and a line number that do not exist on the Python side, so it is stripped from the twin's bytes and the REMAINDER is required to match exactly -- three occurrences, in the same positions, interleaved with the same warn lines. Asserting equality of the stripped text rather than a substring is what stops this test from
    passing if
    the port ever went silent on the missing-binary path."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], drop="npm")
    assert old.returncode == 1
    assert [c for c in old_calls if c.startswith("sleep")] == ["sleep\t10", "sleep\t20"]
    assert "✗ Failed to install dependencies after retries\n" in old.stderr
    assert "not available" not in old.stderr
    assert old.stderr.count("npm: command not found\n") == 3
    stripped = re.sub(r"^\S+: line \d+: ", "", old.stderr, flags=re.MULTILINE)
    assert new.stderr == stripped, (
        f"npm-absent: the divergence is more than the prefix:\n"
        f"old(stripped): {stripped!r}\nnew: {new.stderr!r}"
    )
    assert new.returncode == old.returncode
    assert new.stdout == old.stdout
    assert new_calls == old_calls


def test_npm_succeeding_without_node_modules_is_refused(tmp_path: pathlib.Path) -> None:
    """The ONE anti-vacuity check in the script (install-deps.sh:68-72), and the
    only place it refuses a green. `npm ci` exits 0, the directory is absent, the
    script stops with exit 1."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], node_modules=False)
    assert old.returncode == 1
    assert old.stderr.endswith("✗ node_modules directory not created\n")
    assert "npm install complete" not in old.stderr
    _assert_agree(old, new, "no-node-modules", old_calls, new_calls)


# --------------------------------------------------------------------------- The account trees ---------------------------------------------------------------------------


def test_all_three_account_trees_are_installed_in_order(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [], accounts=ACCOUNT_ALL)
    assert old.returncode == 0
    assert old_calls == [
        "npm\t.\tci",
        "npm\tprivate/account\tci",
        "npm\tprivate/account/web\tci",
        "npm\tprivate/account/e2e\tci",
    ]
    assert "→ Installing account dependencies...\n" in old.stderr
    _assert_agree(old, new, "accounts", old_calls, new_calls)


def test_the_account_trees_never_receive_ignore_scripts(tmp_path: pathlib.Path) -> None:
    """FACT 1, THE ONE THAT MATTERS. The flag exists, per the twin's own header,
    to avoid native-module rebuilds on Windows -- and `run_account_ci` is a bare `npm ci`, so the three account trees run their lifecycle scripts on exactly the platform the flag was added for. Asserted under BOTH triggers at once: an
    explicit `--ignore-scripts` and a Windows `uname`."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--ignore-scripts"],
        accounts=ACCOUNT_ALL,
        FAKE_UNAME_S="MINGW64_NT-10.0-19045",
    )
    assert old_calls[0] == "npm\t.\tci\t--ignore-scripts"
    assert old_calls[1:] == [
        "npm\tprivate/account\tci",
        "npm\tprivate/account/web\tci",
        "npm\tprivate/account/e2e\tci",
    ]
    _assert_agree(old, new, "accounts+ignore-scripts", old_calls, new_calls)


def test_a_missing_web_tree_is_skipped_not_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, [], accounts=("private/account", "private/account/e2e")
    )
    assert old.returncode == 0
    assert old_calls == [
        "npm\t.\tci",
        "npm\tprivate/account\tci",
        "npm\tprivate/account/e2e\tci",
    ]
    _assert_agree(old, new, "no-web", old_calls, new_calls)


def test_no_account_submodule_means_no_account_banner(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [], accounts=())
    assert "Installing account dependencies" not in old.stderr
    assert old_calls == ["npm\t.\tci"]
    _assert_agree(old, new, "no-account", old_calls, new_calls)


def test_skip_account_leaves_a_present_submodule_alone(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--skip-account"], accounts=ACCOUNT_ALL)
    assert old_calls == ["npm\t.\tci"]
    assert "Installing account dependencies" not in old.stderr
    _assert_agree(old, new, "--skip-account", old_calls, new_calls)


def test_account_only_skips_the_root_and_its_node_modules_check(
    tmp_path: pathlib.Path,
) -> None:
    """`node_modules` is deliberately ABSENT here. The check at
    install-deps.sh:68 lives inside the `WANT_ROOT` guard, so `--account-only` never asks -- which is right, and is also the reason nothing verifies the
    account trees produced anything either."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--account-only"], accounts=ACCOUNT_ALL, node_modules=False
    )
    assert old.returncode == 0
    assert old_calls == [
        "npm\tprivate/account\tci",
        "npm\tprivate/account/web\tci",
        "npm\tprivate/account/e2e\tci",
    ]
    assert not old.stderr.startswith("→ Installing npm dependencies")
    _assert_agree(old, new, "--account-only", old_calls, new_calls)


def test_account_only_still_announces_the_ignore_scripts_flag(
    tmp_path: pathlib.Path,
) -> None:
    """Fact 2. The `log_info` sits OUTSIDE the `WANT_ROOT` guard, so a run that
    executes no root install still says it is using a flag it will not pass to
    anything."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--account-only", "--ignore-scripts"], accounts=("private/account",)
    )
    assert old.stderr.startswith("✓ Using --ignore-scripts flag\n")
    assert old_calls == ["npm\tprivate/account\tci"]
    _assert_agree(old, new, "--account-only --ignore-scripts", old_calls, new_calls)


def test_a_failing_account_install_names_the_directory(tmp_path: pathlib.Path) -> None:
    """The loop stops at the FIRST failure, so `e2e` is never attempted and the
    message names `private/account/web`."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        accounts=ACCOUNT_ALL,
        FAKE_NPM_FAIL_IN="private/account/web",
    )
    assert old.returncode == 1
    assert old_calls == [
        "npm\t.\tci",
        "npm\tprivate/account\tci",
        "npm\tprivate/account/web\tci",
        "sleep\t10",
        "npm\tprivate/account/web\tci",
        "sleep\t20",
        "npm\tprivate/account/web\tci",
    ]
    assert old.stderr.endswith(
        "✗ Command failed after 3 attempts\n"
        "✗ Failed to install dependencies in private/account/web\n"
    )
    _assert_agree(old, new, "account-fails", old_calls, new_calls)


# --------------------------------------------------------------------------- The vacuity case ---------------------------------------------------------------------------


def test_both_halves_switched_off_still_reports_npm_install_complete(
    tmp_path: pathlib.Path,
) -> None:
    """FACT 3, THE VACUITY. `--account-only --skip-account` disables the root half
    by flag and the account half by flag; no file test is involved and no
    subprocess runs. The script prints `npm install complete` and exits 0.

    THE CALL LOG BEING EMPTY IS THE ASSERTION. Nothing in the script counts installs, so there is no number in the output a reader could notice
    collapsing -- which is why the emptiness has to be asserted from outside."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--account-only", "--skip-account"],
        accounts=ACCOUNT_ALL,
        node_modules=False,
    )
    assert old.returncode == 0
    assert old_calls == []
    assert old.stdout == ""
    assert old.stderr == "✓ npm install complete\n"
    _assert_agree(old, new, "nothing-at-all", old_calls, new_calls)


def test_account_only_with_no_submodule_also_installs_nothing(
    tmp_path: pathlib.Path,
) -> None:
    """The same vacuity reached by a FILE TEST rather than by a second flag, which
    is the shape a real CI job hits on a checkout without the private submodule."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--account-only"], accounts=(), node_modules=False
    )
    assert old.returncode == 0
    assert old_calls == []
    assert old.stderr == "✓ npm install complete\n"
    _assert_agree(old, new, "account-only-no-submodule", old_calls, new_calls)


# --------------------------------------------------------------------------- The pure helpers, exercised directly ---------------------------------------------------------------------------


def test_parse_args_honours_every_occurrence_and_ignores_the_rest() -> None:
    opts = port.parse_args(["--skip-account", "positional", "--skip-account", "--nope"])
    assert opts.want_account is False
    assert opts.want_root is True
    assert opts.ignore_scripts is False


def test_npm_argv_appends_the_flag_last() -> None:
    assert port.npm_argv(ignore_scripts=False) == ["npm", "ci"]
    assert port.npm_argv(ignore_scripts=True) == ["npm", "ci", "--ignore-scripts"]


def test_wants_ignore_scripts_is_an_or_not_an_and() -> None:
    assert port.wants_ignore_scripts(requested=False, os_name="windows") is True
    assert port.wants_ignore_scripts(requested=True, os_name="linux") is True
    assert port.wants_ignore_scripts(requested=False, os_name="linux") is False
    assert port.wants_ignore_scripts(requested=False, os_name="unknown") is False


def test_secs_prints_bash_integers_not_python_floats() -> None:
    """`${delay}s` in bash is `10s`; `"%s" % 10.0` is `10.0s`. One character of
    divergence in a line the differential compares byte for byte."""
    assert port.secs(10.0) == "10"
    assert port.secs(20.0) == "20"
    assert port.secs(2.5) == "2.5"
