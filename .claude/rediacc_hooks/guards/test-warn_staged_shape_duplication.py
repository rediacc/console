#!/usr/bin/env python3
"""warn_staged_shape_duplication: both directions, against real scratch repositories.

HERMETIC BY CONSTRUCTION, the same shape as `test-block_unproven_bulk_transform.py`: every case runs against a generated repository with its own corpus, its own index and its own cache, so nothing here reads or writes the real checkout's index. The guard is driven as a PROCESS through `dispatch.py`, because a hook's whole contract is its exit code, its stdout and its stderr,
and an in-process call would compare something else.

WHY THE SCRATCH CORPUS IS THIS BIG. The gate refuses to write an index it does not trust: each family carries a FLOOR (100, 50, 100 and 1 tracked files) and the whole scan carries two more (200 files, 5000 windows), because a scan that shrank silently would cache a confident green. A three-file fixture would be refused, correctly, so the fixture generates a corpus that clears
every floor. Each generated file is unique except for ONE deliberately shared block, which keeps the near index small and makes the third copy the only finding there is to find.

TWIN = None ON THE GUARD ITSELF, so this file is the whole differential, exactly as `test-block_unproven_bulk_transform.py` is for its sibling. `check-hook-integrity.sh` reads this file's existence as crediting both directions.
"""

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve()
DISPATCH = str(HERE.parents[1] / "dispatch.py")
REPO = HERE.parents[3]
GATE = REPO / "scripts" / "gates" / "check-shape-duplication.ts"

# ONE PID-STAMPED RUN DIRECTORY holds the corpus repo and the foreign repo, and the next run sweeps it when this one was killed before `atexit` could fire. See `rediacc_ci.runtmp`, loaded BY FILE rather than through a `sys.path` hop, which test_canonical_sys_path_hop.py freezes; it is stdlib-only for exactly this reason.
_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", REPO / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)

RUN_TMP = runtmp.run_dir("shapeprobe-")

# The shared block: eight lines of plain code, carried by two generated files. Plain assignments on purpose -- an import preamble, a report line or a call to a shared helper is excluded by the gate's own predicates, so a fixture built from any of those would be silent for a reason that has nothing to do with this guard.
TWIN_BLOCK = "\n".join("const shared_%02d = %d;" % (i, i) for i in range(8))


def sh(argv, cwd=None, env=None, stdin=None):
    return subprocess.run(
        argv, cwd=cwd, env=env, input=stdin, capture_output=True, text=True, check=False
    )


def git(cwd, *args, check=True):
    proc = sh(["git", "-C", str(cwd), *args])
    if check and proc.returncode != 0:
        msg = "git %s failed in %s: %s" % (" ".join(args), cwd, proc.stderr)
        raise AssertionError(msg)
    return proc


def body(tag, index, lines=30, twin=False):
    """A generated corpus file: unique code, optionally carrying the shared block."""
    rows = ["const %s_%03d_%02d = %d;" % (tag, index, i, i) for i in range(lines)]
    if twin:
        rows.insert(5, TWIN_BLOCK)
    return "\n".join(rows) + "\n"


def build_repo():
    """A tracked corpus that clears every floor the gate enforces, plus the gate itself."""
    # Inside RUN_TMP rather than only removed by the rmtree at the bottom: that line runs only when the suite reaches it, and this repo holds a few hundred generated corpus files.
    root = pathlib.Path(tempfile.mkdtemp(prefix="corpus-", dir=RUN_TMP))
    families = [
        ("scripts/gates", "check-gen%03d.ts", 110, "ts"),
        (".ci/scripts/quality", "check-gen%03d.sh", 60, "qa"),
        (".ci/scripts/test/gates", "test-gen%03d.sh", 110, "tg"),
        (".claude/hooks/pre-bash", "block-gen%03d.sh", 2, "bg"),
    ]
    for directory, pattern, count, tag in families:
        (root / directory).mkdir(parents=True, exist_ok=True)
        for i in range(count):
            twin = tag == "ts" and i < 2
            (root / directory / (pattern % i)).write_text(body(tag, i, twin=twin), encoding="utf-8")
    # The gate and every module it imports, at the same relative paths, because the index records the sha256 of each one and the guard checks them against THIS root.
    (root / "scripts" / "gates").mkdir(parents=True, exist_ok=True)
    shutil.copy2(GATE, root / "scripts" / "gates" / GATE.name)
    (root / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    for src in sorted((REPO / "scripts" / "lib").glob("*.ts")):
        shutil.copy2(src, root / "scripts" / "lib" / src.name)
    (root / "scripts" / "data").mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Fixture")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "corpus")
    return root


def emit_index(root):
    """The real gate, pointed at the scratch tree. `--no-seed` because a generated corpus has no seed and needs none."""
    proc = sh(
        ["npx", "tsx", str(GATE), "--root", str(root), "--emit-index", "--no-seed", "--json"],
        cwd=str(REPO),
    )
    index = root / ".ci" / "cache" / "shape-index" / "index.json"
    if not index.is_file():
        msg = "the gate wrote no index for the fixture (rc=%d):\n%s" % (
            proc.returncode,
            proc.stderr,
        )
        raise AssertionError(msg)
    return index


class Tally:
    fails = 0
    spoke = 0
    cases = 0


def run_guard(command, root, env_extra=None, path=None):
    """(rc, stdout, stderr, elapsed) for one command, through the dispatcher."""
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(root)
    if path is not None:
        env["PATH"] = path
    env.update(env_extra or {})
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, DISPATCH, "warn_staged_shape_duplication"],
        input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root)}
        ),
        capture_output=True,
        text=True,
        check=False,
        cwd=str(root),
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr, time.monotonic() - started


def case(name, command, root, want, **kwargs):
    """`want` is (speaks_on_stderr, speaks_on_stdout, needle) -- the needle may be "".

    THE STREAMS ARE ASSERTED SEPARATELY, and that is the half a needle test would miss: this guard's whole loudness design is that a warning reaches stderr AND stdout, because whether a PreToolUse exit-0 JSON body reaches the operator is unverified. A case that only grepped the combined output would pass with either channel silent.
    """
    rc, out, err, elapsed = run_guard(command, root, **kwargs)
    want_err, want_out, needle = want
    problems = []
    if rc != 0:
        problems.append("exit %d, and this guard may never refuse" % rc)
    if bool(err.strip()) != want_err:
        problems.append("stderr %s" % ("spoke" if err.strip() else "was silent"))
    if bool(out.strip()) != want_out:
        problems.append("stdout %s" % ("spoke" if out.strip() else "was silent"))
    if want_out and out.strip():
        try:
            doc = json.loads(out)
        except ValueError as exc:
            problems.append("stdout was not JSON: %s" % exc)
        else:
            if not doc.get("systemMessage"):
                problems.append("stdout JSON carries no systemMessage")
            if not (doc.get("hookSpecificOutput") or {}).get("additionalContext"):
                problems.append("stdout JSON carries no additionalContext")
    if needle and needle not in (err + out):
        problems.append("the message never says %r" % needle)
    Tally.cases += 1
    Tally.spoke += bool(err.strip())
    Tally.fails += bool(problems)
    print(
        "%-62s %-7s %s"
        % (name, "%.2fs" % elapsed, "ok" if not problems else "*** FAIL *** " + "; ".join(problems))
    )
    if problems:
        print("    stderr: %s" % err.strip()[:400])
        print("    stdout: %s" % out.strip()[:200])
    return elapsed


SILENT = (False, False, "")
NOTICE = (True, False, "")


def loud(needle):
    return (True, True, needle)


# --------------------------------------------------------------------------- The fixture, built once ---------------------------------------------------------------------------

ROOT = build_repo()
INDEX = emit_index(ROOT)
CACHE = INDEX.parent
STUBS = ROOT / ".stubs"
STUBS.mkdir()
(STUBS / "node").write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
(STUBS / "node").chmod(0o755)
GIT_ONLY = ROOT / ".gitonly"
GIT_ONLY.mkdir()
os.symlink(shutil.which("git"), GIT_ONLY / "git")

near = json.loads(INDEX.read_text(encoding="utf-8"))["near"]
if not near:
    msg = "the fixture index holds no near shapes, so no case below could ever find a third copy"
    raise AssertionError(msg)

# ---- the commands that are not this guard's business -----------------------

case("a plain command is not a target", "ls -la", ROOT, SILENT)
case("a different git verb", "git status", ROOT, SILENT)
case("quoted prose is not a command", "echo 'do not run git commit here'", ROOT, SILENT)
case("a commit with nothing staged", 'git commit -m "empty"', ROOT, SILENT)
case(
    "-a takes the working tree, so it is skipped with a notice", "git commit -a -m x", ROOT, NOTICE
)

# ---- an unrelated file, and then the genuine third copy --------------------

(ROOT / "README.md").write_text("prose\n", encoding="utf-8")
git(ROOT, "add", "README.md")
case("a staged file outside the corpus", 'git commit -m "docs"', ROOT, SILENT)
git(ROOT, "reset", "-q")

COPY = "scripts/gates/check-gencopy.ts"


def stage_copy(n=0):
    """A FRESH staged copy per case, and the freshness is load-bearing.

    A case that committed anything committed the whole index with it, so a single staged fixture file silently disappeared partway through the run and every case after it exercised the empty-index branch instead of the one it names. The fixture commits below now carry pathspecs for the same reason this repository demands them of every commit.
    """
    path = COPY if n == 0 else COPY.replace(".ts", "%02d.ts" % n)
    (ROOT / path).write_text(body("cp", 900 + n, twin=True), encoding="utf-8")
    git(ROOT, "add", path)
    return path


stage_copy()
case(
    "a staged THIRD copy of a shared block is reported",
    'git commit -m "feat: another gate"',
    ROOT,
    loud("check-gen000.ts"),
)
case(
    "the same file through the sanctioned pathspec form",
    "git commit -F /tmp/msg -- %s" % COPY,
    ROOT,
    loud("check-gen001.ts"),
)

# ---- the cases where the probe cannot answer, each loud and each allowed ----

case(
    "a probe that cannot be started, because node is absent",
    'git commit -m "feat: another gate"',
    ROOT,
    loud("probe could not be started"),
    path=str(GIT_ONLY),
)
slow = case(
    "a probe that never answers is killed at the deadline",
    'git commit -m "feat: another gate"',
    ROOT,
    loud("did not answer"),
    path="%s:%s" % (STUBS, os.environ.get("PATH", "")),
)
if slow > 2.0:
    print(
        "*** FAIL *** the deadline case took %.2fs; the 0.3s budget is not being enforced" % slow,
        file=sys.stderr,
    )
    Tally.fails += 1
    Tally.cases += 1

# The bundle, altered under the index that recorded its sha.
probe = CACHE / "probe.mjs"
kept = probe.read_text(encoding="utf-8")
probe.write_text(kept + "\n// tampered\n", encoding="utf-8")
case(
    "a bundle that does not match the index that named it",
    'git commit -m "feat: another gate"',
    ROOT,
    loud("does not match the index"),
)
probe.write_text(kept, encoding="utf-8")

# An INPUT the bundle was built from, altered: every hash in the index may have moved with it.
lib = ROOT / "scripts" / "lib" / "console.ts"
kept_lib = lib.read_text(encoding="utf-8")
lib.write_text(kept_lib + "\n// tampered\n", encoding="utf-8")
case(
    "a source the bundle was built from, changed since",
    'git commit -m "feat: another gate"',
    ROOT,
    loud("scripts/lib/console.ts"),
)
lib.write_text(kept_lib, encoding="utf-8")

# A corpus path committed since the index was written: the cached neighbour counts are about a tree that no longer exists.
DRIFT = "scripts/gates/check-gendrift.ts"
(ROOT / DRIFT).write_text(body("dr", 500), encoding="utf-8")
git(ROOT, "add", DRIFT)
git(ROOT, "commit", "-qm", "drift", "--", DRIFT)
stage_copy(1)
case(
    "a corpus that has drifted from the index",
    'git commit -m "feat: another gate"',
    ROOT,
    loud("drifted from the index"),
)
git(ROOT, "rm", "-q", "-f", DRIFT)
git(ROOT, "commit", "-qm", "undrift", "--", DRIFT)

# More corpus files than the cap: skipped, and the skip is visible.
for i in range(13):
    path = "scripts/gates/check-genbulk%02d.ts" % i
    (ROOT / path).write_text(body("bk", 700 + i), encoding="utf-8")
    git(ROOT, "add", path)
case("more corpus files than the cap", 'git commit -m "feat: many"', ROOT, NOTICE)

# Reproduces the 2026-09-23 class fix (shellscan.target_root), and this state IS the discriminator: ROOT has 13 corpus files staged RIGHT NOW, which the case just above proved fires NOTICE when the guard reads ROOT.
# A `-C <foreign>` targeting an unrelated, cleanly-committed repo must stay SILENT -- if the guard mistakenly resolved back to CLAUDE_PROJECT_DIR (ROOT) instead of the command's own target, it would see these same 13 staged files and speak NOTICE instead.
FOREIGN = pathlib.Path(tempfile.mkdtemp(prefix="foreign-", dir=RUN_TMP))
git(FOREIGN, "init", "-q", "-b", "main")
git(FOREIGN, "config", "user.email", "fixture@example.invalid")
git(FOREIGN, "config", "user.name", "Fixture")
(FOREIGN / "unrelated.txt").write_text("nothing shape-duplicated here\n", encoding="utf-8")
git(FOREIGN, "add", "-A")
case(
    "a `-C <foreign>` commit is scanned against the FOREIGN repo, not CLAUDE_PROJECT_DIR's 13 staged corpus files",
    'git -C %s commit -m "chore: unrelated"' % FOREIGN,
    ROOT,
    SILENT,
)

git(ROOT, "reset", "-q")
for i in range(13):
    (ROOT / ("scripts/gates/check-genbulk%02d.ts" % i)).unlink()

# The cache itself: corrupt, then absent. Both are "cannot run", never silence.
stage_copy(2)
INDEX.write_text("{not json", encoding="utf-8")
case(
    "an index that does not parse",
    'git commit -m "feat: another gate"',
    ROOT,
    loud("unreadable"),
)
INDEX.unlink()
case(
    "no cached index at all",
    'git commit -m "feat: another gate"',
    ROOT,
    loud("no cached index"),
)

print()
if Tally.spoke in (0, Tally.cases):
    print(
        "*** FAIL *** %d of %d cases spoke: the guard answered the same way on every input, "
        "so this suite compared it against a constant." % (Tally.spoke, Tally.cases),
        file=sys.stderr,
    )
    Tally.fails += 1
print("%d case(s), %d spoke, %d silent" % (Tally.cases, Tally.spoke, Tally.cases - Tally.spoke))
print("FAILURES: %d" % Tally.fails)
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if Tally.fails else 0)
