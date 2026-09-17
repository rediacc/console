"""Differential: `.ci/rediacc_ci/private/run_account.py` against its twin
`.ci/scripts/private/run-account.sh`, the registered gate `check:ci-account-server`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new code is correct", it is "the new code says what the old code said". Only running BOTH, on the same fixture, in the same run, can support that.

NO REAL `npm` IS EVER INVOKED. `npm ci` in `private/account` is a full clean install of that submodule's dependency tree, and `npm run test` is its whole vitest suite. A test that shelled out to either would take minutes, would need the network, and would SKIP on a checkout without the submodule -- which is the exact failure the twin's CI arm exists to prevent. `npm` is a recording
fake on a scratch PATH: it appends its cwd and full argv to a log, writes canned bytes to BOTH streams, and exits with a status chosen per subcommand.

WHAT IS COMPARED, AND WHY THE CALL LOG IS ONE OF THE FOUR. Every case compares the exit code, stdout, stderr, and the CALL LOG. The log carries each `npm` invocation's CWD because `cd "$ACCOUNT_DIR"` is the only thing that points npm
at the right package, and a port that used a `cwd=` argument for one call and
not the other would print an identical transcript while installing into the console root. It carries the ARGV because `ci` and `run test` are different claims about what happened.

THE CALL LOG IS ALSO WHERE THE TWIN'S ORDERING DEFECT STAYS VISIBLE.
`run-account.sh deploy` and `run-account.sh bogus` both run `npm ci` BEFORE the stage is validated, so a refusal costs a full dependency install. `test_an_unknown_stage_still_pays_for_npm_ci` asserts that on BOTH sides: it is reproduced, not fixed, and moving the validation earlier in the port would show up here as a missing call rather than as a silent improvement.

PATH IS REPLACED, NEVER PREPENDED, and this host HAS a real `npm`. A prepend would leave the "npm is missing" case silently consulting it, and `_binder` asserts the exclusion really took.

THE ONE MASK. Bash prefixes its own diagnostics with `<$0>: line <n>: `, naming the file it is running; the port composes the same prefix from `sys.argv[0]` and its own live frame. Those can never be equal, so `_mask` collapses exactly that prefix on both sides. `test_the_mask_does_not_hide_the_message` pins it.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "private" / "run-account.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "private" / "run_account.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/private/run-account.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/private/run_account.py")

# The recording `npm`. Its status is chosen per SUBCOMMAND so a case can make the install fail without also failing the tests, which is the difference between "exit with npm ci's code" and "exit with npm run test's code".
FAKE_NPM = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
RC_CI = %(rc_ci)d
RC_TEST = %(rc_test)d
args = sys.argv[1:]
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join(["npm", os.getcwd(), *args]) + "\\n")
sys.stdout.write("npm %%s stdout\\n" %% " ".join(args))
sys.stdout.flush()
sys.stderr.write("npm %%s stderr\\n" %% " ".join(args))
sys.stderr.flush()
sys.exit(RC_CI if args[:1] == ["ci"] else RC_TEST)
"""

# Everything both subjects need once PATH is rebuilt from scratch, MINUS `npm`, which is supplied per case. Named rather than derived: a PATH built by copying "everything except npm" is a PATH nobody can state, and the first tool it forgot would look like a divergence in the subject rather than a hole in the harness.
NEEDED = (
    "bash",
    "sh",
    "python3",
    "uname",
    "dirname",
    "cat",
    "grep",
    "sed",
    "rm",
    "mkdir",
    "env",
    "ls",
)

SHELL_PREFIX = re.compile(r"^[^\n]*?: line \d+: ", re.MULTILINE)


def _mask(text: str, root: pathlib.Path, tmp: pathlib.Path) -> str:
    text = SHELL_PREFIX.sub("<shell>: ", text)
    return text.replace(str(root), "<root>").replace(str(tmp), "<tmp>")


def _fixture(
    tmp_path: pathlib.Path,
    *,
    account: str = "package",
    node_modules: bool = False,
) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because each subject derives the console root from its own location (`BASH_SOURCE` / `__file__`, then three directories up). Driving the tracked files with a `cwd` would point both at the REAL repository and the npm fake would run in the real `private/account`.

    `account` takes the four shapes the `-f "$ACCOUNT_DIR/package.json"` guard can meet:

      "package"  a real package.json
      "none"     the directory exists and is empty (an uninitialised submodule)
      "absent"   no `private/account` at all
      "dir"      a DIRECTORY named package.json, which FAILS `-f` and therefore
                 takes the same arm as "none". This is the case that shows the
                 guard is a file test, not an existence test.
    """
    root = tmp_path.resolve() / "tree"
    (root / ".ci" / "scripts" / "private").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "private").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)

    account_dir = root / "private" / "account"
    if account != "absent":
        account_dir.mkdir(parents=True)
    if account == "package":
        (account_dir / "package.json").write_text('{"name": "@rediacc/account"}\n', encoding="utf8")
    elif account == "dir":
        (account_dir / "package.json").mkdir()
    if node_modules:
        (account_dir / "node_modules").mkdir(parents=True, exist_ok=True)
    return root


def _binder(
    tmp_path: pathlib.Path,
    *,
    npm: str = "ok",
    rc_ci: int = 0,
    rc_test: int = 0,
) -> str:
    """The COMPLETE PATH for one case: named real tools, plus the fake `npm`.

    `npm` is one of "ok" (a recording fake) and "missing" (absent from PATH entirely), which is the arm where bash writes its own `command not found`.
    """
    binder = tmp_path.resolve() / "bin"
    if binder.exists():
        shutil.rmtree(binder)
    binder.mkdir(parents=True)
    for tool in NEEDED:
        target = shutil.which(tool)
        if target is None:
            continue
        (binder / tool).symlink_to(target)
    if npm == "ok":
        fake = binder / "npm"
        fake.write_text(
            FAKE_NPM
            % {
                "log": str(tmp_path.resolve() / "calls.log"),
                "rc_ci": rc_ci,
                "rc_test": rc_test,
            },
            encoding="utf-8",
        )
        fake.chmod(0o755)
    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
    if npm == "missing":
        assert shutil.which("npm", path=str(binder)) is None, (
            "the probe cannot fire: npm is still reachable on the scratch PATH"
        )
    return str(binder)


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    tmp_path: pathlib.Path,
    binder: str,
    argv: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
) -> dict[str, object]:
    """Drive one subject from a NEUTRAL cwd and collect all four observables.

    Neutral, because both subjects `cd` into the account directory and the recorded cwd is what proves it. Starting inside the fixture would make the `cd` unobservable.
    """
    cwd = tmp_path.resolve() / "elsewhere"
    cwd.mkdir(exist_ok=True)
    env = {
        "PATH": binder,
        "HOME": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
        # The port imports `rediacc_ci.log`; the COPY under the fixture is what runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    env.update(env_extra or {})
    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject), *argv],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        check=False,
        timeout=120,
    )
    log = tmp_path.resolve() / "calls.log"
    calls: list[str] = []
    if log.exists():
        calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        log.unlink()
    return {
        "exit": proc.returncode,
        "stdout": _mask(proc.stdout, root, tmp_path.resolve()),
        "stderr": _mask(proc.stderr, root, tmp_path.resolve()),
        "calls": [_mask(line, root, tmp_path.resolve()) for line in calls],
    }


CASES = [
    pytest.param({}, {}, {}, id="no-argument-means-stage-quality"),
    pytest.param({}, {}, {"argv": ("quality",)}, id="stage-quality"),
    pytest.param({}, {}, {"argv": ("test",)}, id="stage-test"),
    pytest.param({}, {}, {"argv": ("",)}, id="empty-stage-becomes-quality"),
    pytest.param({}, {}, {"argv": ("test", "deploy")}, id="extra-arguments-are-dropped"),
    pytest.param({}, {}, {"argv": ("deploy",)}, id="deploy-refuses-with-five-lines"),
    pytest.param({}, {}, {"argv": ("bogus",)}, id="an-unknown-stage-is-named-and-refused"),
    pytest.param({}, {}, {"argv": ("--help",)}, id="a-flag-is-just-an-unknown-stage"),
    pytest.param({}, {}, {"argv": ("TEST",)}, id="the-stage-match-is-case-sensitive"),
    pytest.param(
        {"node_modules": True},
        {},
        {"argv": ("test",)},
        id="node-modules-present-skips-npm-ci",
    ),
    pytest.param(
        {"node_modules": True},
        {},
        {"argv": ("bogus",)},
        id="node-modules-present-and-unknown-stage",
    ),
    pytest.param({}, {"rc_ci": 3}, {"argv": ("test",)}, id="npm-ci-failure-is-passed-through"),
    pytest.param({}, {"rc_test": 5}, {"argv": ("test",)}, id="npm-test-failure-is-passed-through"),
    pytest.param(
        {"node_modules": True},
        {"rc_test": 1},
        {"argv": ("quality",)},
        id="npm-test-failure-status-one",
    ),
    pytest.param({}, {"npm": "missing"}, {"argv": ("test",)}, id="npm-is-not-on-path"),
    pytest.param(
        {"node_modules": True},
        {"npm": "missing"},
        {"argv": ("test",)},
        id="npm-is-not-on-path-and-npm-ci-is-skipped",
    ),
    pytest.param({"account": "none"}, {}, {"argv": ("test",)}, id="submodule-absent-locally"),
    pytest.param(
        {"account": "none"},
        {},
        {"argv": ("test",), "env_extra": {"CI": "true"}},
        id="submodule-absent-in-ci-is-fatal",
    ),
    pytest.param(
        {"account": "none"},
        {},
        {"argv": ("test",), "env_extra": {"CI": "false"}},
        id="submodule-absent-ci-false",
    ),
    pytest.param(
        {"account": "none"},
        {},
        {"argv": ("test",), "env_extra": {"CI": "1"}},
        id="ci-is-tested-against-the-literal-true",
    ),
    pytest.param(
        {"account": "none"},
        {},
        {"argv": ("test",), "env_extra": {"GITHUB_ACTIONS": "true"}},
        id="github-actions-alone-takes-the-local-arm",
    ),
    pytest.param({"account": "absent"}, {}, {"argv": ("test",)}, id="no-account-directory-at-all"),
    pytest.param(
        {"account": "dir"},
        {},
        {"argv": ("test",)},
        id="package-json-is-a-directory-so-it-fails-minus-f",
    ),
    pytest.param(
        {"account": "none"},
        {},
        {"argv": ("deploy",), "env_extra": {"CI": "true"}},
        id="the-guard-runs-before-the-stage-is-looked-at",
    ),
]


@pytest.mark.parametrize(("fixture_kw", "binder_kw", "run_kw"), CASES)
def test_port_and_twin_agree(tmp_path, fixture_kw, binder_kw, run_kw):
    root = _fixture(tmp_path, **fixture_kw)
    binder = _binder(tmp_path, **binder_kw)

    old = _run(TWIN_REL, root, tmp_path, binder, **run_kw)
    new = _run(PORT_REL, root, tmp_path, binder, **run_kw)

    for field in ("exit", "stdout", "stderr", "calls"):
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_the_recording_npm_is_actually_reached(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if npm never ran, and a
    port that printed the same banner while running nothing would satisfy a
    stdout-only comparison and test no account code at all."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    out = _run(PORT_REL, root, tmp_path, binder, argv=("test",))
    assert out["calls"], "the recording npm was never invoked; this file proves nothing"
    assert len(out["calls"]) == 2, "npm ran %d times, not twice" % len(out["calls"])
    install, tests = (line.split("\t") for line in out["calls"])
    assert install[0] == "npm"
    assert install[1] == "<root>/private/account", (
        "npm ci ran in %r, not in the account directory" % install[1]
    )
    assert install[2:] == ["ci"], install
    assert tests[1] == "<root>/private/account", (
        "npm run test ran in %r, not in the account directory" % tests[1]
    )
    assert tests[2:] == ["run", "test"], tests
    assert out["exit"] == 0


def test_the_ci_arm_is_the_reason_the_guard_exists(tmp_path):
    """A missing submodule under CI must be FATAL on both sides.

    The twin spells out why: `check:ci-account-server` is a gate in `ci-quality.yml`, and an exit 0 here would report the account suite as passing while it never ran. This is the single assertion in the file whose failure would mean the gate had become vacuous.
    """
    root = _fixture(tmp_path, account="none")
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, argv=("test",), env_extra={"CI": "true"})
        assert out["exit"] == 1, "%s exited %r under CI with no submodule" % (
            subject.name,
            out["exit"],
        )
        assert "submodule not checked out" in out["stderr"], out["stderr"]
        assert "failing rather than reporting success for tests that never ran" in out["stderr"]
        assert out["calls"] == [], "%s ran npm anyway" % subject.name


def test_the_local_arm_is_a_silent_pass_and_that_is_the_hole(tmp_path):
    """THE COMPLEMENT, and a REAL HOLE IN THE LOCAL GATE, pinned rather than
    fixed. `npm run check:ci-account-server` on a checkout without the submodule prints two warnings and exits 0, so the gate reports success having run nothing. The twin says why in its own comment, and closing it is a
    cutover-box decision, not a port's."""
    root = _fixture(tmp_path, account="none")
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, argv=("test",))
        assert out["exit"] == 0, "%s exited %r locally" % (subject.name, out["exit"])
        assert "skipping." in out["stderr"], out["stderr"]
        assert "in CI it is a hard failure" in out["stderr"]
        assert out["calls"] == [], "%s ran npm without a submodule" % subject.name


def test_the_stage_runs_when_the_submodule_is_there(tmp_path):
    """THE NEGATIVE CONTROL on the guard. A gate with only positive controls
    will happily refuse on a tree where nothing is wrong."""
    root = _fixture(tmp_path, node_modules=True)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, argv=("test",))
        assert out["exit"] == 0, "%s refused a healthy tree" % subject.name
        assert len(out["calls"]) == 1, "%s did not run the tests" % subject.name
        assert "Running account tests..." in out["stderr"]


def test_an_unknown_stage_still_pays_for_npm_ci(tmp_path):
    """A DEFECT IN THE TWIN, PINNED RATHER THAN FIXED.

    `cd`, then `npm ci`, THEN the `case`. So `run-account.sh bogus` and `run-account.sh deploy` each perform a full clean install of the account server's dependency tree and only then refuse. Both subjects are asserted, because the port must not quietly improve on it; the day the twin's validation moves above the install, this goes red and names the decision.
    """
    binder = _binder(tmp_path)
    for stage in ("bogus", "deploy"):
        root = _fixture(tmp_path)
        for subject in (TWIN_REL, PORT_REL):
            out = _run(subject, root, tmp_path, binder, argv=(stage,))
            assert out["exit"] == 1, "%s exited %r for %s" % (subject.name, out["exit"], stage)
            assert [line.split("\t")[2:] for line in out["calls"]] == [["ci"]], (
                "%s ran %r before refusing stage %s" % (subject.name, out["calls"], stage)
            )
        shutil.rmtree(root)


def test_deploy_refuses_with_all_five_lines_and_names_the_real_script(tmp_path):
    """The refusal is the feature: it exists because this stage once published
    an orphan worker from `private/account`'s local-dev wrangler.toml. All five lines are contract, and the last one is the route a caller must take
    instead."""
    root = _fixture(tmp_path, node_modules=True)
    binder = _binder(tmp_path)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder, argv=("deploy",))
        assert out["exit"] == 1
        assert out["stderr"].count("✗") == 5, out["stderr"]
        assert "wrangler.{eu,us,asia}.toml" in out["stderr"]
        assert (
            ".ci/scripts/deploy/deploy-account.sh --region <eu|us|asia> [--target edge]"
            in (out["stderr"])
        )
        assert out["calls"] == [], "%s ran npm for a stage that refuses" % subject.name


def test_the_mask_does_not_hide_the_message(tmp_path):
    """A CONTROL ON THE CONTROL. `_mask` collapses the `<$0>: line <n>: ` prefix
    on both sides; if it were greedier it would hide real divergences and every
    case above would pass for the wrong reason."""
    sample = "/a/b/twin.sh: line 47: npm: command not found\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: npm: command not found\nkept: line noise\n", masked

    root = _fixture(tmp_path)
    binder = _binder(tmp_path, npm="missing")
    raw = {}
    for subject in (TWIN_REL, PORT_REL):
        proc = subprocess.run(
            ["bash" if subject.suffix == ".sh" else "python3", str(root / subject), "test"],
            capture_output=True,
            text=True,
            env={
                "PATH": binder,
                "HOME": str(tmp_path),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(ROOT / ".ci"),
            },
            cwd=str(tmp_path),
            check=False,
            timeout=120,
        )
        raw[subject.name] = proc.stderr
    assert raw[TWIN_REL.name] != raw[PORT_REL.name], (
        "the two prefixes are identical, so the mask is unnecessary and should be deleted"
    )
    for name, text in raw.items():
        assert "npm: command not found" in text, "%s said %r" % (name, text)
