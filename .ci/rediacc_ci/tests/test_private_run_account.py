"""`rediacc_ci.private.run_account`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/private/run-account.sh` and the port over one fixture tree apiece and compared four channels: the exit code, stdout, stderr and the recorded argv of every `npm` call. Every case now compares against `goldens/run-account/`, which holds the twin's OWN recorded bytes; each golden's provenance header
carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE LEDGER IS `.ci/shadow/w7p4b-run-account.observations.jsonl`, TEN rows over ten distinct trees, every one EQUIVALENT. The older `w7p6-run-account` file exists with five rows and is deliberately not the citation: the w7p4b rows are the ones whose recorded `old.cmd` names this bash path and whose `new.cmd` names the module spec that replaced it.

NO REAL `npm` IS EVER INVOKED. `npm ci` in `private/account` is a full clean install of that submodule's dependency tree and `npm run test` is its whole vitest suite; a case that shelled out to either would take minutes, would need the network, and would SKIP on a checkout without the submodule, which is the exact failure the CI arm exists to prevent. `npm` is a recording fake on a
scratch PATH: it appends its cwd and full argv to a log, writes canned bytes to BOTH streams, and exits with a status chosen per subcommand.

WHY THE CALL LOG IS ONE OF THE FOUR. It carries each `npm` invocation's CWD because `cd "$ACCOUNT_DIR"` is the only thing that points npm at the right package, and a port that used a `cwd=` argument for one call and not the other would print an identical transcript while installing into the console root.

It carries the ARGV because `ci` and `run test` are different claims about what happened.

THE CALL LOG IS ALSO WHERE THE ORDERING DEFECT STAYS VISIBLE. `deploy` and `bogus` both run `npm ci` BEFORE the stage is validated, so a refusal costs a full dependency install. That is reproduced, not fixed, and `test_an_unknown_stage_still_pays_for_npm_ci` reads it off the recordings.

PATH IS REPLACED, NEVER PREPENDED, and this host HAS a real `npm`. A prepend would leave the "npm is missing" case silently consulting it, and `_binder` asserts the exclusion really took.

WHAT IS MASKED: the fixture root as `<root>`, the scratch directory as `<tmp>`, and the `<$0>: line <n>: ` prefix that bash writes and the port composes from its own frame. `test_the_mask_does_not_hide_the_message` pins that nothing else is collapsed.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
SLUG = "run-account"
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
    twin: bool = False,
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
    if twin:
        # ONLY WHEN THE TWIN IS THE SUBJECT, which is the one-shot recorder and nothing else. The suite drives the port or a throwaway mutant of it, and the twin is no longer in the tree to copy.
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


# name -> the wiring this case is driven with, preserved verbatim from the differential.
CASE_KW = {
    "no-argument-means-stage-quality": ({}, {}, {}),
    "stage-quality": ({}, {}, {"argv": ("quality",)}),
    "stage-test": ({}, {}, {"argv": ("test",)}),
    "empty-stage-becomes-quality": ({}, {}, {"argv": ("",)}),
    "extra-arguments-are-dropped": ({}, {}, {"argv": ("test", "deploy")}),
    "deploy-refuses-with-five-lines": ({}, {}, {"argv": ("deploy",)}),
    "an-unknown-stage-is-named-and-refused": ({}, {}, {"argv": ("bogus",)}),
    "a-flag-is-just-an-unknown-stage": ({}, {}, {"argv": ("--help",)}),
    "the-stage-match-is-case-sensitive": ({}, {}, {"argv": ("TEST",)}),
    "node-modules-present-skips-npm-ci": ({"node_modules": True}, {}, {"argv": ("test",)}),
    "node-modules-present-and-unknown-stage": ({"node_modules": True}, {}, {"argv": ("bogus",)}),
    "npm-ci-failure-is-passed-through": ({}, {"rc_ci": 3}, {"argv": ("test",)}),
    "npm-test-failure-is-passed-through": ({}, {"rc_test": 5}, {"argv": ("test",)}),
    "npm-test-failure-status-one": ({"node_modules": True}, {"rc_test": 1}, {"argv": ("quality",)}),
    "npm-is-not-on-path": ({}, {"npm": "missing"}, {"argv": ("test",)}),
    "npm-is-not-on-path-and-npm-ci-is-skipped": (
        {"node_modules": True},
        {"npm": "missing"},
        {"argv": ("test",)},
    ),
    "submodule-absent-locally": ({"account": "none"}, {}, {"argv": ("test",)}),
    "submodule-absent-in-ci-is-fatal": (
        {"account": "none"},
        {},
        {"argv": ("test",), "env_extra": {"CI": "true"}},
    ),
    "submodule-absent-ci-false": (
        {"account": "none"},
        {},
        {"argv": ("test",), "env_extra": {"CI": "false"}},
    ),
    "ci-is-tested-against-the-literal-true": (
        {"account": "none"},
        {},
        {"argv": ("test",), "env_extra": {"CI": "1"}},
    ),
    "github-actions-alone-takes-the-local-arm": (
        {"account": "none"},
        {},
        {"argv": ("test",), "env_extra": {"GITHUB_ACTIONS": "true"}},
    ),
    "no-account-directory-at-all": ({"account": "absent"}, {}, {"argv": ("test",)}),
    "package-json-is-a-directory-so-it-fails-minus-f": (
        {"account": "dir"},
        {},
        {"argv": ("test",)},
    ),
    "the-guard-runs-before-the-stage-is-looked-at": (
        {"account": "none"},
        {},
        {"argv": ("deploy",), "env_extra": {"CI": "true"}},
    ),
}


CASES = tuple(CASE_KW)

CALLS_MARKER = "--- calls ---\n"


def run(
    tmp_path: pathlib.Path, name: str, *, subject_rel: pathlib.PurePosixPath = PORT_REL
) -> dict[str, object]:
    """One subject, once, over this case's own fixture."""
    fixture_kw, binder_kw, run_kw = CASE_KW[name]
    root = _fixture(tmp_path, **fixture_kw, twin=subject_rel.suffix == ".sh")
    binder = _binder(tmp_path, **binder_kw)
    return _run(subject_rel, root, tmp_path, binder, **run_kw)


def render(out: dict[str, object]) -> str:
    return "%s%s%s\n" % (
        frozen.render(out["exit"], out["stdout"], out["stderr"]),
        CALLS_MARKER,
        json.dumps(out["calls"], indent=2),
    )


def recorded(name: str) -> dict[str, object]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return {
        "exit": int(exit_line.removeprefix("exit: ")),
        "stdout": stdout,
        "stderr": stderr,
        "calls": json.loads(calls),
    }


def compare(tmp_path: pathlib.Path, name: str) -> dict[str, object]:
    want = recorded(name)
    got = run(tmp_path, name)
    for field in ("exit", "stdout", "stderr", "calls"):
        assert got[field] == want[field], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            field,
            want[field],
            got[field],
        )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path, name):
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned():
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_host_path():
    """The scratch tree and the fixture root are masked, so a golden naming either would be one that reds on another machine."""
    for name in CASES:
        out = recorded(name)
        blob = "\n".join([out["stdout"], out["stderr"], json.dumps(out["calls"])])
        assert str(ROOT) not in blob, name
        assert "/tmp/" not in blob, name


def test_the_recording_npm_is_actually_reached():
    """ANTI-VACUITY. Every comparison above is worthless if npm never ran, and a port that printed the same banner while running nothing would satisfy a stdout-only comparison and test no account code at all."""
    out = recorded("stage-test")
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


def test_the_ci_arm_is_the_reason_the_guard_exists():
    """A missing submodule under CI must be FATAL.

    The twin spelled out why: `check:ci-account-server` is a gate in `ci-quality.yml`, and an exit 0 here would report the account suite as passing while it never ran. This is the single assertion in the file whose failure would mean the gate had become vacuous.
    """
    out = recorded("submodule-absent-in-ci-is-fatal")
    assert out["exit"] == 1
    assert "submodule not checked out" in out["stderr"], out["stderr"]
    assert "failing rather than reporting success for tests that never ran" in out["stderr"]
    assert out["calls"] == [], "npm ran anyway"


def test_the_local_arm_is_a_silent_pass_and_that_is_the_hole():
    """THE COMPLEMENT, and a REAL HOLE IN THE LOCAL GATE, pinned rather than fixed. `npm run check:ci-account-server` on a checkout without the submodule prints two warnings and exits 0, so the gate reports success having run nothing. Closing it is a cutover-box decision, not a port's."""
    out = recorded("submodule-absent-locally")
    assert out["exit"] == 0
    assert "skipping." in out["stderr"], out["stderr"]
    assert "in CI it is a hard failure" in out["stderr"]
    assert out["calls"] == [], "npm ran without a submodule"


def test_the_stage_runs_when_the_submodule_is_there():
    """THE NEGATIVE CONTROL on the guard. A gate with only positive controls will happily refuse on a tree where nothing is wrong."""
    out = recorded("node-modules-present-skips-npm-ci")
    assert out["exit"] == 0, "a healthy tree was refused"
    assert len(out["calls"]) == 1, "the tests did not run"
    assert "Running account tests..." in out["stderr"]


def test_an_unknown_stage_still_pays_for_npm_ci():
    """A DEFECT IN THE TWIN, PINNED RATHER THAN FIXED.

    `cd`, then `npm ci`, THEN the `case`. So `bogus` and `deploy` each perform a full clean install of the account server's dependency tree and only then refuse. The day that validation moves above the install, these recordings go red and name the decision.
    """
    for name in ("an-unknown-stage-is-named-and-refused", "deploy-refuses-with-five-lines"):
        out = recorded(name)
        assert out["exit"] == 1, name
        assert [line.split("\t")[2:] for line in out["calls"]] == [["ci"]], (
            "%s ran %r before refusing" % (name, out["calls"])
        )


def test_deploy_refuses_with_all_five_lines_and_names_the_real_script():
    """The refusal is the feature: it exists because this stage once published an orphan worker from `private/account`'s local-dev wrangler.toml. All five lines are contract, and the last one is the route a caller must take instead."""
    out = recorded("deploy-refuses-with-five-lines")
    assert out["exit"] == 1
    assert out["stderr"].count("✗") == 5, out["stderr"]
    assert "wrangler.{eu,us,asia}.toml" in out["stderr"]
    assert (
        ".ci/scripts/deploy/deploy-account.sh --region <eu|us|asia> [--target edge]"
        in (out["stderr"])
    )


def test_the_mask_does_not_hide_the_message():
    """A CONTROL ON THE CONTROL, and half of it is what the deletion cost.

    `_mask` collapses the `<$0>: line <n>: ` prefix; if it were greedier it would hide real divergences and every case above would pass for the wrong reason. The unit half below still drives that directly. What is gone is the half that ran BOTH subjects with no `npm` on PATH and asserted their raw prefixes DIFFER, which was the proof that the mask was necessary rather than
    decorative; the twin's own prefix survives only in the blob every golden header names.
    """
    sample = "/a/b/twin.sh: line 47: npm: command not found\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: npm: command not found\nkept: line noise\n", masked

    out = recorded("npm-is-not-on-path")
    assert out["exit"] == 127
    assert "<shell>: npm: command not found" in out["stderr"], out["stderr"]


def test_a_planted_install_in_the_wrong_directory_is_caught(tmp_path):
    """THE CONTROL ON THE GOLDENS. Install from the console root instead of the account directory.

    `cd "$ACCOUNT_DIR"` is the only thing pointing npm at the right package, and npm is perfectly happy to install a different one: the mutant prints the same two banners, exits 0, and differs only in the CWD the recorded call log carries. That is the whole reason the log records a cwd at all.

    The mutant is a throwaway copy placed at the port's own path inside the fixture tree, which is where the subject resolves its root from; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "        os.chdir(account_dir)\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "        pass\n")

    name = "stage-test"
    want = recorded(name)
    fixture_kw, binder_kw, run_kw = CASE_KW[name]
    root = _fixture(tmp_path / "planted", **fixture_kw)
    (root / PORT_REL).write_text(mutated, encoding="utf-8")
    binder = _binder(tmp_path / "planted", **binder_kw)
    got = _run(PORT_REL, root, tmp_path / "planted", binder, **run_kw)

    assert all(line.split("\t")[1] == "<root>/private/account" for line in want["calls"]), (
        "the recorded corpus moved"
    )
    assert [line.split("\t")[1] for line in got["calls"]] == ["<tmp>/elsewhere"] * 2, (
        "the plant did not move the install: %r" % got["calls"]
    )
    for field in ("exit", "stdout", "stderr"):
        assert got[field] == want[field], "only the recorded cwd may differ: %s" % field

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
