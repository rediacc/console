#!/usr/bin/env python3
"""Controls for `wl_review.mark(..., "fixed", [<sha>])`, the path `worklist.py --review-mark <me> <id> fixed <sha>` runs.

    python3 .claude/hooks/stop/test-review-mark.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/).

THE DEFECT. On 2026-11-12 seven `--review-mark ... fixed commit:edd459ffbc` runs were refused with "does not resolve to a commit in console" although the commit existed: `commit:<sha>` is the `--tick` evidence form and mark() handed it to rev-parse whole. The prefix is now stripped. Each control runs the real mark() against a throwaway git repository holding a reviewed commit, a fix commit touching the anchored file, and one review record, so a mark() that stops stripping the prefix, or starts admitting what it must refuse, turns a control red.

THE ADVANCE (agent/plans/PLAN-push-decoupling.md R3). Sections 5 and 6 drive `commit_reviews`, the path `worklist.py --review-commit <me>` runs. After a green whole ci:quick in a fixture carrying a copy of the real runner, the verb's commit leaves a receipt the push guard (`block_unverified_push.receipt_refusal`) admits at the new tree with no second whole run; with no green receipt, a red one or a narrowed one, the verb commits and starts nothing.
"""

import atexit
import importlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import wl_review as R

_SCRATCH = pathlib.Path(tempfile.mkdtemp(prefix="review-mark-"))
atexit.register(shutil.rmtree, _SCRATCH, True)
# ONE PRIVATE TMPDIR: wl_review's locks live under `$TMPDIR/claude-worklist`, read at call time, and test_hooks_delegates fails a standalone suite that leaves an entry in the shared one.
os.environ["TMPDIR"] = str(_SCRATCH)
tempfile.tempdir = str(_SCRATCH)


class Tally:
    count = 0
    fails = 0


def control(label, got, want):
    Tally.count += 1
    if got != want:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted %r" % (label, got, want), file=sys.stderr)


BRANCH = "0101-1"
CLAIM = "the fixture line is wrong and a later commit corrects it."
ME = "testmark"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def fixture(name, prepared=False):
    """(repo, reviewed sha, fix sha): the fix touches the file the finding anchors on. `prepared`: the directory already holds files (runner_fixture's), and the base commit carries them."""
    repo = _SCRATCH / name
    repo.mkdir(exist_ok=prepared)
    git(repo, "init", "-q", "-b", BRANCH)
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "fixture")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "reviewed")
    reviewed = git(repo, "rev-parse", "HEAD")
    record = repo / "agent" / "reviews" / BRANCH / ("%s.md" % reviewed)
    record.parent.mkdir(parents=True)
    record.write_text(
        "# Review %s: reviewed\n\n"
        "Commit: %s\nRepo: console\nBranch: %s\nParent: %s\nPatch-Id: %s\n"
        "Reviewed-At: 2026-11-12T00:00:00Z\nModel: fixture\nCost: (none)\n"
        "Diff: 1 bytes, 1 files, truncated: no\nUnreviewed: (none)\nVerdict: findings\n"
        "Attempt: 1\nLabels: bump=none kind=ci why=fixture.\nDropped: 0\nBody-Sig: %s\n\n## Findings\n\n"
        "### %s.1 [medium] a.txt:1\nAnchor: in-diff\n"
        "Claim: %s\n"
        "Class: other\nResolution: open\n"
        % (
            reviewed[:8],
            reviewed,
            BRANCH,
            git(repo, "rev-parse", "HEAD~1"),
            git(repo, "rev-parse", "HEAD").replace(reviewed, "0" * 40),
            R.body_sig([R.Finding("%s.1" % reviewed[:8], "medium", "a.txt", 1, "in-diff", CLAIM)]),
            reviewed[:8],
            CLAIM,
        ),
        encoding="utf-8",
    )
    (repo / "a.txt").write_text("three\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "fix")
    return repo, reviewed, git(repo, "rev-parse", "HEAD")


def mark(repo, reviewed, arg):
    """None on success, else the refusal text."""
    try:
        R.mark(str(repo), BRANCH, "%s.1" % reviewed[:8], "fixed", [arg], ME)
    except ValueError as err:
        return str(err)
    return None


def resolution(repo, reviewed):
    text = (repo / "agent" / "reviews" / BRANCH / ("%s.md" % reviewed)).read_text(encoding="utf-8")
    return next(line for line in text.splitlines() if line.startswith("Resolution:"))


# ---- 1. CONTROL: a bare sha marks the finding fixed ---------------------------------------------------
repo, reviewed, fix = fixture("bare")
control("bare sha: accepted", mark(repo, reviewed, fix), None)
control("bare sha: resolution is fixed", resolution(repo, reviewed).split()[1], "fixed")

# ---- 2. THE DEFECT: commit:<sha>, the --tick form, names the same commit ------------------------------
repo, reviewed, fix = fixture("prefixed")
control("commit:<sha>: accepted", mark(repo, reviewed, "commit:" + fix[:10]), None)
control("commit:<sha>: resolution is fixed", resolution(repo, reviewed).split()[1], "fixed")

# ---- 3. THE REFUSALS stay refusals, with or without the prefix ----------------------------------------
repo, reviewed, fix = fixture("refused")
unknown = mark(repo, reviewed, "commit:" + "f" * 40)
control("an unknown sha: refused", unknown is not None and "does not resolve" in unknown, True)
itself = mark(repo, reviewed, "commit:" + reviewed)
control(
    "the reviewed commit itself: refused",
    itself is not None and "cannot be the reviewed" in itself,
    True,
)
control("nothing was marked by a refusal", resolution(repo, reviewed), "Resolution: open")

# ---- 4. related_test reads the repo's test naming: a private module's leading `_`, a stop-hook `wl_` --
control(
    "a private module's test: test_sample_push_predicate.py tests _sample_push.py",
    R.related_test(
        "fixture/tests/test_sample_push_predicate.py",
        "fixture/guards/_sample_push.py",
    ),
    True,
)
control(
    "a stop-hook module's test: test-samplerec.py tests wl_samplerec.py",
    R.related_test("fixture/stop/test-samplerec.py", "fixture/stop/wl_samplerec.py"),
    True,
)
control(
    "CONTROL: the stem stays a whole token (test_radio.py does not test io.py)",
    R.related_test("tests/test_radio.py", "src/io.py"),
    False,
)
control(
    "CONTROL: a short stripped stem is not read loosely (test_io_x.py does not test wl_io.py)",
    R.related_test("tests/test_io_x.py", "hooks/wl_io.py"),
    False,
)
control(
    "CONTROL: another module's test still does not close it",
    R.related_test("fixture/stop/test-samplerec.py", "fixture/stop/wl_sampleroster.py"),
    False,
)

# ---- 4b. --test: a test whose content names the anchored file closes the finding whatever its file is called (#7b73e110) --


def test_fixture(name, test_body):
    """(repo, reviewed sha, test fix sha, test path): the finding anchors on a.txt and the fix commit touches only a test whose file name carries no `a`."""
    repo, reviewed, _fix = fixture(name)
    rel = "tests/check_zzz_floor.py"
    (repo / "tests").mkdir()
    (repo / rel).write_text(test_body, encoding="utf-8")
    git(repo, "add", "--", rel)
    git(repo, "commit", "-q", "-m", "test only")
    return repo, reviewed, git(repo, "rev-parse", "HEAD"), rel


def mark_with_test(repo, reviewed, fix, rel):
    try:
        R.mark(str(repo), BRANCH, "%s.1" % reviewed[:8], "fixed", [fix, "--test", rel], ME)
    except ValueError as err:
        return str(err)
    return None


repo, reviewed, fix, rel = test_fixture("ref-test", "assert read('A.txt') == 'three'\n")
control(
    "a test naming the anchored basename: accepted",
    mark_with_test(repo, reviewed, fix, rel),
    None,
)
control(
    "a test naming the anchored basename: resolution is fixed",
    resolution(repo, reviewed).split()[1],
    "fixed",
)
repo, reviewed, fix, rel = test_fixture("ref-none", "assert read('b.txt') == 'three'\n")
refused = mark_with_test(repo, reviewed, fix, rel)
control(
    "CONTROL: a test naming nothing of the anchored file: refused",
    refused is not None and "does not touch a.txt" in refused,
    True,
)
control("CONTROL: the refusal marks nothing", resolution(repo, reviewed), "Resolution: open")
repo, reviewed, fix, rel = test_fixture("ref-untouched", "assert read('a.txt')\n")
untouched = mark_with_test(repo, reviewed, fix, "tests/other_floor.py") or ""
control(
    "CONTROL: a --test the fix does not touch is refused",
    "does not touch the named test" in untouched,
    True,
)
# A submodule fix lists submodule-relative paths, so --test named from the superproject root is read without the submodule's prefix (#32aa9f91).
_super = _SCRATCH / "ref-super"
_super.mkdir()
git(_super, "init", "-q", "-b", BRANCH)
git(_super, "config", "user.email", "fixture@example.invalid")
git(_super, "config", "user.name", "fixture")
repo, reviewed, fix, rel = test_fixture("ref-super/sub", "assert read('a.txt') == 'three'\n")
git(_super, "-c", "protocol.file.allow=always", "submodule", "add", "-q", "./sub", "sub")
control(
    "a --test named from the superproject root (sub/tests/...): accepted",
    mark_with_test(repo, reviewed, fix, "sub/" + rel),
    None,
)
control(
    "the superproject-relative --test marks it fixed",
    resolution(repo, reviewed).split()[1],
    "fixed",
)
repo, reviewed, fix, rel = test_fixture("ref-super-control", "assert read('a.txt') == 'three'\n")
control(
    "CONTROL: the same prefix on a repo that is no submodule: refused",
    "does not touch the named test" in (mark_with_test(repo, reviewed, fix, "sub/" + rel) or ""),
    True,
)


# A file whose own --selftest mode is its suite, run by a tracked test, counts as a --test path (scripts/pins/pins.ts and test_gate_pin_cli.py); both are judged at the reviewed commit, so a fix cannot make its own file a host.
def selftest_host_fixture(name, host_before, runner_line):
    """(repo, reviewed, fix): the host and its runner are in the base when `host_before` (else the host has no --selftest yet), and the fix commit edits the host to read the anchored a.txt."""
    repo = _SCRATCH / name
    (repo / "tool").mkdir(parents=True)
    (repo / "tests").mkdir()
    host = repo / "tool" / "host.ts"
    host.write_text(
        ("if (argv.includes('--selftest')) {}\n" if host_before else "main()\n"), encoding="utf-8"
    )
    (repo / "tests" / "test_host_runs.py").write_text(runner_line + "\n", encoding="utf-8")
    repo, reviewed, _fix = fixture(name, prepared=True)
    host.write_text(
        "if (argv.includes('--selftest')) { control(read('a.txt')); }\n", encoding="utf-8"
    )
    git(repo, "commit", "-q", "-am", "fix in the host's selftest")
    return repo, reviewed, git(repo, "rev-parse", "HEAD")


repo, reviewed, fix = selftest_host_fixture(
    "ref-host", True, "SUBJECT = from_root('tool', 'host.ts')  # its --selftest"
)
control(
    "a selftest host a tracked test runs: --test accepted",
    mark_with_test(repo, reviewed, fix, "tool/host.ts"),
    None,
)
control("the selftest host marks it fixed", resolution(repo, reviewed).split()[1], "fixed")
repo, reviewed, fix = selftest_host_fixture("ref-host-none", True, "SUBJECT = 'other'  # selftest")
control(
    "CONTROL: the same host with no test naming it: refused as a non-test path",
    "is not a test path" in (mark_with_test(repo, reviewed, fix, "tool/host.ts") or ""),
    True,
)
repo, reviewed, fix = selftest_host_fixture(
    "ref-host-added", False, "SUBJECT = 'host.ts'  # selftest"
)
control(
    "CONTROL: a host whose --selftest the fix itself adds: refused",
    "is not a test path" in (mark_with_test(repo, reviewed, fix, "tool/host.ts") or ""),
    True,
)
repo, reviewed, fix = selftest_host_fixture(
    "ref-host-substr", True, "SUBJECT = 'myhost.ts'  # selftest"
)
control(
    "CONTROL: a test naming only a longer name containing the basename: refused",
    "is not a test path" in (mark_with_test(repo, reviewed, fix, "tool/host.ts") or ""),
    True,
)
repo, reviewed, fix = selftest_host_fixture(
    "ref-host-bak", True, "SUBJECT = 'tool/host.ts.bak'  # selftest"
)
control(
    "CONTROL: a test naming the full path with a suffix (tool/host.ts.bak): refused",
    "is not a test path" in (mark_with_test(repo, reviewed, fix, "tool/host.ts") or ""),
    True,
)
repo, reviewed, fix = selftest_host_fixture(
    "ref-host-full", True, "SUBJECT = 'tool/host.ts'  # selftest"
)
control(
    "a test naming the full path: --test accepted",
    mark_with_test(repo, reviewed, fix, "tool/host.ts"),
    None,
)
control(
    "normalised stem: numeric prefix and dashes",
    R.related_test("tests/partner-customer-org.test.ts", "db/0090_partner_customer_org.sql"),
    True,
)
control(
    "CONTROL: a numeric prefix alone names nothing",
    R.related_test("tests/db-0090.test.ts", "db/0090_partner_customer_org.sql"),
    False,
)

# ---- 5. --review-commit carries a green receipt forward with the records-only advance (PLAN-push-decoupling R3) --
ROOT = pathlib.Path(__file__).resolve().parents[3]
TSX = ROOT / "node_modules" / ".bin" / "tsx"
RUNNER_DIR = ROOT / "scripts" / "ci-runner"
_PATHS_SPEC = importlib.util.spec_from_file_location(
    "paths", ROOT / ".ci" / "rediacc_ci" / "paths.py"
)
if _PATHS_SPEC is None or _PATHS_SPEC.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/paths.py is missing" % __file__)
_PATHS = importlib.util.module_from_spec(_PATHS_SPEC)
_PATHS_SPEC.loader.exec_module(_PATHS)
_PATHS.on_sys_path(ROOT / ".claude")
GUARD = importlib.import_module("rediacc_hooks.guards.block_unverified_push")

READER_POLICY = json.dumps(
    {
        "version": 1,
        "records": [
            {"glob": "agent/reviews/**", "readers": [{"id": "fast:reader", "evidence": "fixture"}]}
        ],
    }
)
GATES: list[dict[str, Any]] = [
    {
        "id": gid,
        "run": "true",
        "gate": True,
        "leaves": [],
        "ci": {"kind": "local-only", "blocker": "BLOCKER: synthetic fixture"},
    }
    for gid in ("fast:reader", "fast:other")
]
DEP_LOCK = json.dumps({"packages": {"node_modules/dep": {"version": "1.0.0"}}}) + "\n"
RUNNER_STUB = (
    "import { spawnSync } from 'node:child_process';\n"
    "import path from 'node:path';\n"
    "const args = process.argv.slice(2);\n"
    "if (args[0] === '--selftest') process.exit(0);\n"
    "const real = path.join(import.meta.dirname, 'run-real.ts');\n"
    "const tsx = path.join(process.cwd(), 'node_modules', '.bin', 'tsx');\n"
    "const r = spawnSync(tsx, [real, ...args], { stdio: 'inherit' });\n"
    "process.exit(r.status ?? 1);\n"
)


def runner_fixture(name):
    """A fixture() repository that also carries a copy of the real runner and quick-clone.ts, a two-gate manifest whose `fast:reader` reads agent/reviews/**, and an install the kept clone can copy. The runner's own selftest is a stub, as in test_gate_ci_runner's clone fixture: `check:ci-runner-selftest` runs the real one."""
    repo = _SCRATCH / name
    runner = repo / "scripts" / "ci-runner"
    runner.mkdir(parents=True)
    for src in RUNNER_DIR.glob("*.ts"):
        shutil.copy(src, runner / src.name)
    os.rename(runner / "run.ts", runner / "run-real.ts")
    (runner / "run.ts").write_text(RUNNER_STUB, encoding="utf-8")
    (runner / "manifest.ts").write_text(
        "export type { CiCoverage, GateSpec } from './gate-spec.js';\nexport const GATES = %s;\n"
        % json.dumps(GATES, indent=2),
        encoding="utf-8",
    )
    (runner / "gates.lock.json").write_text(json.dumps(GATES), encoding="utf-8")
    (repo / "scripts" / "lib").mkdir()
    for lib_name in ("policy-paths.ts", "entry-point.ts"):
        shutil.copy(ROOT / "scripts" / "lib" / lib_name, repo / "scripts" / "lib" / lib_name)
    for rel in ("__init__.py", "core/__init__.py", "core/tmp_capacity.py"):
        dest = repo / ".ci" / "rediacc_ci" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / ".ci" / "rediacc_ci" / rel, dest)
    (repo / ".ci" / "policy").mkdir(parents=True)
    (repo / ".ci" / "policy" / "record-paths.json").write_text(READER_POLICY, encoding="utf-8")
    (repo / "package.json").write_text('{"scripts": {}}\n', encoding="utf-8")
    (repo / "package-lock.json").write_text(DEP_LOCK, encoding="utf-8")
    (repo / ".gitignore").write_text("node_modules/\n.ci/cache/\n", encoding="utf-8")
    (repo / "node_modules" / ".bin").mkdir(parents=True)
    os.symlink(TSX, repo / "node_modules" / ".bin" / "tsx")
    (repo / "node_modules" / ".package-lock.json").write_text(DEP_LOCK, encoding="utf-8")
    (repo / "node_modules" / "dep").mkdir()
    (repo / "node_modules" / "dep" / "package.json").write_text(
        json.dumps({"name": "dep", "version": "1.0.0"}) + "\n", encoding="utf-8"
    )
    return fixture(name, prepared=True)


def quick_env(name):
    """The environment the verb hands quick-clone.ts: no CI marker (CI routes in place), a private clone and duration cache.

    A SHORT TMPDIR: tsx opens its IPC socket at `$TMPDIR/tsx-<uid>/<pid>.pipe`, and under a nested suite TMPDIR that path passed the 108-byte unix socket limit (`listen EINVAL`, seen under test_hooks_delegates). The directory is private and removed at exit, so wl_review's locks written there during the verb leave nothing behind.
    """
    short = tempfile.mkdtemp(prefix="rvm-", dir="/tmp")
    atexit.register(shutil.rmtree, short, True)
    # CI_QUICK_IN_CLONE too: a suite run inside a whole ci:quick inherits the outer run's in-clone marker, and quick-clone.ts then refuses --advance-only ("runs only in the kept clone, and this run would use the shared checkout"), so the advance controls failed in the kept clone and passed in a plain shell.
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CI", "GITHUB_ACTIONS", "CI_QUICK_IN_CLONE", "CI_QUICK_NO_CARRY")
    }
    env.update(
        {
            "TMPDIR": short,
            "CI_QUICK_CLONE_DIR": str(_SCRATCH / ("%s-clone" % name)),
            "CI_PROFILE": "off",
            "CI_RUNNER_CACHE": str(_SCRATCH / ("%s-durations.json" % name)),
            "CI_RUNNER_CORES": "",
            "CI_CORE_LEASE_HELD": "",
            "REDIACC_CORE_LEASE_DIR": str(_SCRATCH / ("%s-lease" % name)),
        }
    )
    return env


def receipt_of(repo):
    path = repo / ".ci" / "cache" / "prepush-receipt.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


repo, reviewed, fix = runner_fixture("advance")
saved_env = dict(os.environ)
advance_env = quick_env("advance")
os.environ.clear()
os.environ.update(advance_env)
try:
    whole = subprocess.run(
        [str(TSX), str(repo / "scripts" / "ci-runner" / "quick-clone.ts")],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    control("a whole ci:quick at the fix commit passes", whole.returncode, 0)
    if whole.returncode != 0:
        print(whole.stdout[-2000:] + whole.stderr[-2000:], file=sys.stderr)
    parent_tree = git(repo, "rev-parse", "HEAD^{tree}")
    before = receipt_of(repo) or {}
    control(
        "the whole receipt vouches for the fix commit's tree", before.get("headTree"), parent_tree
    )
    rc, text = R.commit_reviews(str(repo), BRANCH)
finally:
    os.environ.clear()
    os.environ.update(saved_env)
control("the verb commits", rc, 0)
control(
    "the verb's commit is the review record",
    git(repo, "log", "-1", "--format=%s").startswith("chore(reviews)"),
    True,
)
head_tree = git(repo, "rev-parse", "HEAD^{tree}")
control("the verb says it advanced", "ADVANCED" in text, True)
after = receipt_of(repo) or {}
control("no second whole run: headTree is still the parent's", after.get("headTree"), parent_tree)
control(
    "one advances step, ending at the new tree",
    [s.get("to") for s in after.get("advances") or []],
    [head_tree],
)
control(
    "the step ran the record's reader",
    (after.get("advances") or [{}])[-1].get("gates"),
    {"fast:reader": 0},
)
control(
    "the push guard admits the new tree on the advanced receipt",
    GUARD.receipt_refusal(str(repo), head_tree, GUARD.read_receipt(str(repo), head_tree)),
    None,
)
control(
    "CONTROL: the receipt before the verb is refused at the new tree",
    GUARD.receipt_refusal(str(repo), head_tree, before) is not None,
    True,
)


# ---- 6. No green receipt: the verb commits and starts nothing -----------------------------------------
class Spawn:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw.get("cwd")))
        return subprocess.CompletedProcess(cmd, 0, "", "")


def verb_with(name, receipt, carried=None, dirty_carried=None, spawn=None):
    """commit_reviews in a fixture() repo whose latest receipt is `receipt` (None: no file), whose COMMITTED carried-reds.json is `carried` and whose uncommitted working-tree copy is `dirty_carried` (None: none), with the advance's spawn recorded."""
    repo, _reviewed, _fix = fixture(name)
    cpath = repo / ".ci" / "config" / "carried-reds.json"
    if carried is not None:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps(carried), encoding="utf-8")
        git(repo, "add", "-f", "--", ".ci/config/carried-reds.json")
        git(repo, "commit", "-q", "-m", "carried reds")
    if dirty_carried is not None:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps(dirty_carried), encoding="utf-8")
    if receipt is not None:
        path = repo / ".ci" / "cache" / "prepush-receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tree = git(repo, "rev-parse", "HEAD^{tree}")
        path.write_text(json.dumps(dict(receipt, headTree=tree)), encoding="utf-8")
        (repo / ".git" / "info" / "exclude").write_text(".ci/\n", encoding="utf-8")
    spawn = Spawn() if spawn is None else spawn
    rc, text = R.commit_reviews(
        str(repo), BRANCH, advance=lambda root: R.advance_after_commit(root, spawn=spawn)
    )
    committed = git(repo, "log", "-1", "--format=%s").startswith("chore(reviews)")
    return rc, text, committed, spawn.calls


GREEN = {"schema": 2, "whole": True, "exitCode": 0, "failed": [], "advances": []}
for label, receipt in (
    ("no receipt", None),
    ("a red receipt", dict(GREEN, exitCode=1, failed=["fast:red"])),
    ("a narrowed receipt", dict(GREEN, whole=False)),
):
    rc, text, committed, calls = verb_with("none-%s" % label.split()[-2], receipt)
    control("%s: the verb commits" % label, (rc, committed), (0, True))
    control("%s: nothing is started" % label, calls, [])
    control("%s: the verb says so" % label, "nothing was advanced" in text, True)
rc, text, committed, calls = verb_with("green-seam", GREEN)
control("CONTROL: a green receipt for the parent tree commits", (rc, committed), (0, True))
control(
    "CONTROL: and starts quick-clone.ts --advance-only once",
    [(c[-2].endswith("quick-clone.ts"), c[-1], bool(cwd)) for c, cwd in calls],
    [(True, "--advance-only", True)],
)

# A receipt red only on carried gates is carried forward the way the push guard admits it (#68452957).
LONG = "carried because the live state it reads is off-box and cannot be fixed in code; " * 3
STAR_ENTRIES = [{"gate": "fast:red", "findings": "*", "reason": LONG}]
CARRY_STAR = {"version": 2, "carried": STAR_ENTRIES}
RED_CARRIED = dict(GREEN, exitCode=1, failed=["fast:red"])
rc, text, committed, calls = verb_with("carried-only", RED_CARRIED, CARRY_STAR)
control("a receipt red only on a carried gate: the verb commits", (rc, committed), (0, True))
control(
    "a receipt red only on a carried gate: --advance-only starts once",
    [(c[-2].endswith("quick-clone.ts"), c[-1]) for c, _cwd in calls],
    [(True, "--advance-only")],
)
rc, text, committed, calls = verb_with(
    "carried-other",
    RED_CARRIED,
    {"version": 2, "carried": [{"gate": "fast:other", "findings": "*", "reason": LONG}]},
)
control("CONTROL: a red the carried-reds file does not cover starts nothing", calls, [])

rc, text, committed, calls = verb_with("carried-dirty", RED_CARRIED, None, dirty_carried=CARRY_STAR)
control(
    "CONTROL: an UNCOMMITTED carried-reds.json covering the red starts nothing (HEAD's copy decides)",
    calls,
    [],
)


class SpawnAdvancing(Spawn):
    """--advance-only as the runner does it for a carried-only receipt: the receipt gains an advance to HEAD's tree and the exit is 1 (the run is red, honestly)."""

    def __init__(self, advance=True):
        super().__init__()
        self.advance = advance

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw.get("cwd")))
        root = pathlib.Path(kw.get("cwd") or ".")
        if self.advance:
            path = root / ".ci" / "cache" / "prepush-receipt.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["advances"] = [{"to": git(root, "rev-parse", "HEAD^{tree}"), "gates": {}}]
            path.write_text(json.dumps(doc), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 1, "", "")


rc, text, committed, calls = verb_with(
    "carried-exit1", RED_CARRIED, CARRY_STAR, spawn=SpawnAdvancing()
)
control(
    "a carried-only advance that exits 1 and moves the receipt to HEAD reports ADVANCED",
    "ADVANCED" in text,
    True,
)
rc, text, committed, calls = verb_with(
    "carried-exit1-stuck", RED_CARRIED, CARRY_STAR, spawn=SpawnAdvancing(advance=False)
)
control(
    "CONTROL: exit 1 with the receipt left behind is a FAILED advance",
    "ADVANCE FAILED" in text,
    True,
)

# carried_only agrees with the push guard's carried_verdict (no stale entries in these fixtures).
KEYED_ENTRIES = [{"gate": "g", "findings": ["k1", "k2"], "reason": LONG}]
KEYED = {"version": 2, "carried": KEYED_ENTRIES}
SHORT = {"version": 2, "carried": [{"gate": "fast:red", "findings": "*", "reason": "too short"}]}
for label, carried_receipt, doc, want in (
    ("keyed exact", {"failed": ["g"], "findings": {"g": ["k1", "k2"]}}, KEYED, True),
    ("keyed with a stale carried key", {"failed": ["g"], "findings": {"g": ["k1"]}}, KEYED, False),
    (
        "a stale carried gate",
        {"failed": ["fast:red"], "findings": {}},
        {"version": 2, "carried": STAR_ENTRIES + KEYED_ENTRIES},
        False,
    ),
    ("keyed extra key", {"failed": ["g"], "findings": {"g": ["k1", "k9"]}}, KEYED, False),
    ("keyed, no keys recorded", {"failed": ["g"], "findings": {}}, KEYED, False),
    ("uncarried gate", {"failed": ["g", "h"], "findings": {"g": ["k1"]}}, KEYED, False),
    ("star", {"failed": ["fast:red"], "findings": {}}, CARRY_STAR, True),
    (
        "star, with a gate that could not run",
        {"failed": ["fast:red"], "findings": {}, "blocked": ["fast:cannot-run"]},
        CARRY_STAR,
        True,
    ),
    ("star under the reason bar", {"failed": ["fast:red"], "findings": {}}, SHORT, False),
):
    full = dict(GREEN, exitCode=1, **carried_receipt)
    refusal, _notes = GUARD.carried_verdict(full, doc)
    control(
        "carried_only matches the push guard: %s" % label,
        (R.carried_only(full, doc), refusal is None),
        (want, want),
    )

print("%d control(s), %d failed" % (Tally.count, Tally.fails))
sys.exit(1 if Tally.fails else 0)
