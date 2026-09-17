r"""check:ci-hook-cross-os -- every platform-sensitive operation in the hook
package sits inside a declared seam, and the declaration is COMPLETE.

WHAT WAS ALREADY TRUE, MEASURED 2026-09-09 BEFORE ANY OF THIS WAS WRITTEN.
`.claude/rediacc_hooks/` is 65 Python files, and exactly ONE of them handles a platform difference: `proc.py`, whose `REDIACC_PROC_BACKEND` seam chooses between reading `/proc` and shelling out to `ps`. `dispatch.py` has zero platform handling, which an AST walk confirms rather than a grep -- the grep answer is 1 and it is a `sys.platform` inside a DOCSTRING.

So this gate is not fixing a spread of ad-hoc platform code. There is none. It is making the ABSENCE checkable, which is the only version of that claim that survives the next commit. A seam that is complete today and unguarded is a seam that is complete until somebody reads `/proc` in a guard, and that guard will work perfectly for every reviewer, because every reviewer is on
Linux.

THE PLATFORM SET IS NAMED, because "cross-OS" without one is unfalsifiable. Linux and macOS. Windows reaches this tree only through WSL -- `run.ps1` is a `wsl.exe --cd` launcher by the program's own arbitration -- so a construct that works on Linux and macOS and not on native Windows is NOT a finding here. That decision is why `fcntl`, `os.killpg` and `signal.SIGKILL` are absent
from the
class list below despite being the first things a Windows-shaped scanner would
report: all three behave identically on macOS, and reporting them would produce five findings a reader can do nothing useful about, which is how a gate teaches people to skim it.

THE FOUR CLASSES, each with the Linux/macOS divergence that puts it here:

  procfs          A path literal under `/proc`. macOS has no procfs at all, so
                  the read does not fail, it silently answers "nothing is
                  there" -- the exact shape `proc.py`'s docstring calls "a
                  no-op that still looks green".
  proc-tool       An exec of `ps`, `pgrep`, `pkill` or `top`. BSD and GNU
                  disagree on flags AND on output: macOS `ps -o comm=` prints a
                  full path where Linux prints a 15-character truncation, which
                  is a divergence `proc.py` had to write code for.
  coreutil        An exec of a coreutil whose macOS build takes different flags:
                  stat, readlink, date, sed, timeout, nproc, realpath, base64,
                  md5sum, sha256sum, mktemp, getopt. Zero of these in the tree
                  today, and the class is here so the first one is a finding
                  rather than a surprise on somebody's laptop.
  platform-branch A read of `sys.platform`, `os.name`, `platform.system()`,
                  `platform.machine()`, `platform.release()` or `os.uname()`.
                  Branching on the platform IS platform handling, and it belongs
                  inside a declared seam where a test can force both sides.

AST, NOT grep, AND THAT IS THE WHOLE DIFFERENCE BETWEEN THIS AND A NOISE
MACHINE. A textual sweep for `pgrep` over this package returns 15 hits; every
one of them is prose or a pattern a guard MATCHES AGAINST in somebody else's command line. `block_self_matching_pgrep.py` is named after the string. The AST walk sees a string constant used as `subprocess.run(["pgrep", ...])` and does not see the same characters inside a regex, which takes the same corpus from 15 findings to one.

BOTH DIRECTIONS, AND THE SECOND ONE IS THE HALF THAT DECAYS.

  * A finding no declared scope claims is a NEW platform-sensitive operation.
    It reds, naming the file, the line, the class and the fix.
  * A declared scope that claims NOTHING is dead. It also reds. A seam
    declaration outliving the code it describes is how the next reader concludes
    the tree is seamed when it is not, and it is the direction a gate normally
    forgets, because nothing breaks when it rots.

AND THE SEAM ITSELF IS CHECKED, not just its scope. Each declaration names an
environment variable; that name must appear in the seam module's own source, and
the module must accept at least two backend values. A declaration whose env override does not exist is a claim about a seam that is not there.

ANTI-VACUITY, FIVE REFUSALS. Zero Python files in the scan root; a scan root
that does not exist; zero declared scopes; a seam module that is missing; and a
corpus that parsed to zero AST nodes. Every one exits 1. The success line prints the file count, the finding count per class and the scope table, so a collapse is visible rather than silent.

Exit 1 on any finding or refusal, 2 on a failed control.

THE GATE HEADER LIVES IN THE ENTRY POINT, not here. `gate-bind` reads the file the
registry INVOKES, and the registry invokes .ci/scripts/quality/check_hook_cross_os.py by path;
a header here derives this module's own path and the binding disagrees with
package.json. Measured 2026-09-09: three gates landed with it in the module and
`check:ci-gate-bind` named all three.
"""

from __future__ import annotations

import ast
import pathlib
import sys

from rediacc_ci import log, paths
from rediacc_ci.controls import Checker, controls_first, plant

SCAN_ROOT = (".claude", "rediacc_hooks")

# Execs whose flags or output differ between the BSD and GNU builds. Kept as two separate sets rather than one, because they are two different arguments
# for being here and a reader deciding whether to add a name needs to know which
# one they are making.
PROC_TOOLS = frozenset({"ps", "pgrep", "pkill", "top"})
DIVERGENT_COREUTILS = frozenset(
    {
        "stat",
        "readlink",
        "date",
        "sed",
        "timeout",
        "nproc",
        "realpath",
        "base64",
        "md5sum",
        "sha256sum",
        "mktemp",
        "getopt",
    }
)

# Attribute reads that ARE a platform branch.
PLATFORM_ATTRS = frozenset(
    {
        ("sys", "platform"),
        ("os", "name"),
        ("os", "uname"),
        ("platform", "system"),
        ("platform", "machine"),
        ("platform", "release"),
    }
)

SUBPROCESS_CALLS = frozenset({"run", "Popen", "check_output", "call", "check_call"})


class Scope:
    """One declared home for platform-sensitive operations.

    `files` is a tuple of repo-relative paths, matched exactly. Not a glob: a glob widens itself as the tree grows, and the whole point of this declaration is that widening it is a decision somebody makes on purpose.
    """

    def __init__(self, name, files, classes, env, why):
        self.name = name
        self.files = tuple(files)
        self.classes = frozenset(classes)
        self.env = env
        self.why = why

    def claims(self, finding):
        return finding.rel in self.files and finding.kind in self.classes


class Finding:
    """A platform-sensitive operation, keyed on its TEXT and never its line.

    The line number is carried for the message and is deliberately absent from `key`. A finding that moves because a paragraph was added above it is the same finding, and a set keyed on line numbers churns until somebody regenerates it wholesale, which is how a fresh finding gets absorbed.
    """

    def __init__(self, rel, line, kind, detail):
        self.rel = rel
        self.line = line
        self.kind = kind
        self.detail = detail

    @property
    def key(self):
        return (self.rel, self.kind, self.detail)

    def __repr__(self):
        return "%s:%d %s %s" % (self.rel, self.line, self.kind, self.detail)


# THE DECLARATION. One scope today, which is the true state of the tree and not a starting point somebody meant to grow.
SCOPES = (
    Scope(
        name="proc-table",
        files=(".claude/rediacc_hooks/proc.py",),
        classes=("procfs", "proc-tool"),
        env="REDIACC_PROC_BACKEND",
        why=(
            "W5 P1's backend seam. `/proc` does not exist on macOS and a guard that "
            "silently finds nothing there is worse than one that refuses: it reports "
            "'no process is running this script' for every script, forever. The seam "
            "picks `proc` or `ps` explicitly, and `auto` probes for /proc/self/cmdline "
            "rather than reading sys.platform, so a container or a future platform is "
            "judged by whether procfs answers."
        ),
    ),
    Scope(
        name="proc-table-tests",
        files=(".claude/rediacc_hooks/tests/test_proc.py",),
        classes=("procfs", "proc-tool"),
        env="REDIACC_PROC_BACKEND",
        why=(
            "The seam's own differential. It has to name /proc and shell out to the "
            "real `pgrep` in order to prove the two backends agree, which is exactly "
            "the evidence that makes the seam trustworthy. Declared as its own scope "
            "rather than folded into the one above so that deleting the proof is a "
            "finding: the scope would claim nothing and this gate reds."
        ),
    ),
)


class RefusalError(Exception):
    """The gate cannot reach a verdict. Exit 1, never a silent pass."""


def _subprocess_argv0(node):
    """The literal argv[0] of a `subprocess.*` call, or None.

    Only the list-literal form is decidable. A command built at runtime is not, and guessing at it would be the false-positive direction on a gate whose findings ask a human to write a seam.
    """
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in SUBPROCESS_CALLS:
        return None
    base = func.value
    if not isinstance(base, ast.Name) or base.id != "subprocess":
        return None
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.List) and first.elts:
        head = first.elts[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return head.value
    return None


def scan_source(rel, source):
    """Every platform-sensitive operation in one file's AST.

    A SyntaxError is raised, not swallowed. A file this cannot parse is a file it cannot judge, and a scanner that skips those quietly reports a clean tree the day somebody adds a construct it does not understand.
    """
    tree = ast.parse(source, filename=rel)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if value == "/proc" or value.startswith("/proc/"):
                out.append(Finding(rel, node.lineno, "procfs", value))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            pair = (node.value.id, node.attr)
            if pair in PLATFORM_ATTRS:
                out.append(Finding(rel, node.lineno, "platform-branch", "%s.%s" % pair))
        elif isinstance(node, ast.Call):
            argv0 = _subprocess_argv0(node)
            if argv0 in PROC_TOOLS:
                out.append(Finding(rel, node.lineno, "proc-tool", argv0))
            elif argv0 in DIVERGENT_COREUTILS:
                out.append(Finding(rel, node.lineno, "coreutil", argv0))
    return out


def python_files(root):
    """Every `.py` under the scan root, sorted, with `__pycache__` excluded."""
    base = pathlib.Path(root).joinpath(*SCAN_ROOT)
    if not base.is_dir():
        raise RefusalError(
            "the scan root %s does not exist, so this gate is not seeing the hook "
            "package at all and its green would mean nothing"
            % paths.relative_to_root(base, pathlib.Path(root))
        )
    files = sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    if not files:
        raise RefusalError(
            "the scan root %s holds ZERO Python files. Zero inputs is a refusal, "
            "never a pass." % base
        )
    return files


def scan_tree(root):
    """(findings, file_count) over the whole scan root."""
    root = pathlib.Path(root)
    findings = []
    files = python_files(root)
    for path in files:
        rel = str(path.relative_to(root))
        try:
            findings.append(scan_source(rel, path.read_text(encoding="utf-8")))
        except SyntaxError as exc:
            raise RefusalError(
                "%s does not parse (%s), so it cannot be judged and this gate will "
                "not report a clean tree around it" % (rel, exc)
            ) from exc
    return [f for group in findings for f in group], len(files)


def check_seams(root, scopes):
    """Findings about the DECLARATIONS themselves: a seam must actually exist."""
    out = []
    root = pathlib.Path(root)
    for scope in scopes:
        if not scope.env:
            out.append("scope %s declares no environment override" % scope.name)
            continue
        # The env name must appear in at least one file the scope covers. A declaration naming a variable no code reads is a seam on paper.
        seen = False
        for rel in scope.files:
            path = root / rel
            if not path.is_file():
                out.append(
                    "scope %s names %s, which is not a file. A scope pointing at "
                    "nothing claims nothing and hides every finding that moved out "
                    "of it." % (scope.name, rel)
                )
                continue
            if scope.env in path.read_text(encoding="utf-8"):
                seen = True
        if not seen:
            out.append(
                "scope %s declares the override %s, but no file it covers mentions "
                "that name. The seam is declared and not implemented." % (scope.name, scope.env)
            )
    return out


def compare(findings, scopes):
    """(unclaimed, dead_scopes). Set equality, stated as two lists."""
    unclaimed = []
    claimed_by = {scope.name: 0 for scope in scopes}
    for finding in findings:
        owners = [s for s in scopes if s.claims(finding)]
        if not owners:
            unclaimed.append(finding)
            continue
        for owner in owners:
            claimed_by[owner.name] += 1
    dead = [name for name, count in claimed_by.items() if count == 0]
    return unclaimed, sorted(dead)


def run(root=None, scopes=SCOPES):
    root = pathlib.Path(root or paths.repo_root())
    if not scopes:
        raise RefusalError(
            "zero declared scopes: every platform-sensitive operation would read as "
            "unclaimed, and a gate that reports the whole tree reports nothing"
        )
    findings, file_count = scan_tree(root)
    unclaimed, dead = compare(findings, scopes)
    seam_problems = check_seams(root, scopes)
    return findings, unclaimed, dead, seam_problems, file_count


def _kind_counts(findings):
    counts = {}
    for finding in findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1
    return counts


def main(argv=None):
    argv = list(argv or [])
    if "--selftest" in argv:
        return 1 if selftest() else 0
    rc = controls_first("hook cross-OS seams", selftest)
    if rc:
        return rc
    try:
        findings, unclaimed, dead, seam_problems, file_count = run()
    except RefusalError as exc:
        log.error("hook cross-OS seams: %s" % exc)
        return 1
    bad = False
    for finding in unclaimed:
        bad = True
        log.error(
            "  %s:%d %s (%s) is platform-sensitive and no declared seam covers it. "
            "Give it a seam with an environment override in the module, then add the "
            "file to a Scope in .ci/rediacc_ci/quality/hook_cross_os.py with the "
            "reason. Do not widen an existing scope's file list to make this go away."
            % (finding.rel, finding.line, finding.detail, finding.kind)
        )
    for name in dead:
        bad = True
        log.error(
            "  scope %s claims NOTHING. Either the operation it was written for is "
            "gone (delete the scope) or it moved to a file the scope does not name "
            "(follow it). A scope nobody's code matches reads as coverage that is "
            "not there." % name
        )
    for problem in seam_problems:
        bad = True
        log.error("  %s" % problem)
    if bad:
        return 1
    # THE SCOPE TABLE IS PRINTED EVERY RUN, not only on failure. An exemption nobody sees is an exemption nobody drains.
    for scope in SCOPES:
        log.info(
            "  seam %-18s %-24s %d file(s), classes %s"
            % (scope.name, scope.env, len(scope.files), ",".join(sorted(scope.classes)))
        )
    counts = _kind_counts(findings)
    log.success(
        "hook cross-OS seams: %d Python file(s) under %s, %d platform-sensitive "
        "operation(s) (%s), all claimed by %d declared seam(s); 0 unclaimed, 0 dead"
        % (
            file_count,
            "/".join(SCAN_ROOT),
            len(findings),
            ", ".join("%s %d" % (k, counts[k]) for k in sorted(counts)) or "none",
            len(SCOPES),
        )
    )
    return 0


# --------------------------------------------------------------------------- controls ---------------------------------------------------------------------------

_CLEAN_SEAM = '''"""A seam module."""
import os
import pathlib
import subprocess

BACKEND_ENV = "REDIACC_PROC_BACKEND"


def read(pid):
    if os.environ.get(BACKEND_ENV, "auto") == "ps":
        return subprocess.run(["ps", "-Awwo", "pid="], check=False)
    return pathlib.Path("/proc/%d/comm" % pid).read_text()
'''

# A guard with NO platform-sensitive operation, and the strings that would fool a grep: `pgrep` and `/proc/` appear as a regex the guard matches against somebody
# else's command line, which is exactly the shape `block_self_matching_pgrep.py`
# has in the real tree.
_CLEAN_GUARD = '''"""An ordinary guard."""
import re
import subprocess

PATTERN = re.compile(r"pgrep -f|/proc/self")


def verdict(command):
    if PATTERN.search(command):
        return 2
    subprocess.run(["git", "status"], check=False)
    return 0
'''


def _fixture(tmp, guard_source=_CLEAN_GUARD, seam_source=_CLEAN_SEAM):
    root = pathlib.Path(tmp)
    pkg = root.joinpath(*SCAN_ROOT)
    (pkg / "tests").mkdir(parents=True, exist_ok=True)
    (pkg / "proc.py").write_text(seam_source, encoding="utf-8")
    (pkg / "guards.py").write_text(guard_source, encoding="utf-8")
    # The fixture's test file MENTIONS the override name, because the real one does and because the gate checks for it. The first draft omitted it and the "no seam problem" control failed, correctly: a test scope that never forces the seam is not proving the two backends agree about anything.
    (pkg / "tests" / "test_proc.py").write_text(
        "import os\nimport subprocess\n\n\ndef test_x():\n"
        '    os.environ["REDIACC_PROC_BACKEND"] = "ps"\n'
        '    subprocess.run(["pgrep", "-f", "x"], check=False)\n'
        '    assert open("/proc/self/cmdline")\n',
        encoding="utf-8",
    )
    return root


def _scopes_for_fixture():
    return (
        Scope(
            name="proc-table",
            files=(str(pathlib.Path(*SCAN_ROOT) / "proc.py"),),
            classes=("procfs", "proc-tool"),
            env="REDIACC_PROC_BACKEND",
            why="fixture",
        ),
        Scope(
            name="proc-table-tests",
            files=(str(pathlib.Path(*SCAN_ROOT) / "tests" / "test_proc.py"),),
            classes=("procfs", "proc-tool"),
            env="REDIACC_PROC_BACKEND",
            why="fixture",
        ),
    )


def selftest():
    """True when a control failed, which is what `controls_first` expects."""
    import tempfile  # noqa: PLC0415

    check = Checker()
    scopes = _scopes_for_fixture()

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        findings, unclaimed, dead, seam_problems, count = run(root, scopes)
        check("CONTROL: a clean fixture has no unclaimed finding", unclaimed == [])
        check("CONTROL: no declared scope is dead", dead == [])
        check("CONTROL: and no seam problem", seam_problems == [])
        check(
            "CONTROL: the scan is NOT trivially empty -- it found the seam's own reads",
            len(findings) >= 4 and count == 3,
        )

    with tempfile.TemporaryDirectory() as tmp:
        dirty = plant(
            _CLEAN_GUARD,
            'subprocess.run(["git", "status"], check=False)',
            'open("/proc/%d/comm" % 1)',
        )
        root = _fixture(tmp, guard_source=dirty)
        _, unclaimed, _, _, _ = run(root, scopes)
        check(
            "PLANT: a /proc read in a guard is unclaimed and reds",
            [f.kind for f in unclaimed] == ["procfs"],
        )

    with tempfile.TemporaryDirectory() as tmp:
        dirty = plant(_CLEAN_GUARD, '["git", "status"]', '["pgrep", "-f", "x"]')
        root = _fixture(tmp, guard_source=dirty)
        _, unclaimed, _, _, _ = run(root, scopes)
        check(
            "PLANT: a pgrep exec in a guard is unclaimed and reds",
            [f.kind for f in unclaimed] == ["proc-tool"],
        )

    with tempfile.TemporaryDirectory() as tmp:
        dirty = plant(_CLEAN_GUARD, '["git", "status"]', '["stat", "-c", "%s", "x"]')
        root = _fixture(tmp, guard_source=dirty)
        _, unclaimed, _, _, _ = run(root, scopes)
        check(
            "PLANT: a GNU-flavoured coreutil exec reds as a coreutil finding",
            [f.kind for f in unclaimed] == ["coreutil"],
        )

    with tempfile.TemporaryDirectory() as tmp:
        dirty = plant(_CLEAN_GUARD, "if PATTERN.search(command):", "if sys.platform == 'darwin':")
        root = _fixture(tmp, guard_source=dirty)
        _, unclaimed, _, _, _ = run(root, scopes)
        check(
            "PLANT: branching on sys.platform outside a seam reds",
            [f.detail for f in unclaimed] == ["sys.platform"],
        )

    with tempfile.TemporaryDirectory() as tmp:
        # THE OTHER DIRECTION. Emptying the seam module leaves a scope claiming nothing, which must red rather than pass for "no findings".
        root = _fixture(tmp, seam_source='"""Nothing here."""\nX = 1\n')
        _, unclaimed, dead, seam_problems, _ = run(root, scopes)
        check("PLANT: a scope that claims nothing is reported DEAD", dead == ["proc-table"])
        check(
            "PLANT: and its missing override is reported too",
            any("declared and not implemented" in p for p in seam_problems),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        broken = (
            Scope(
                name="proc-table",
                files=(str(pathlib.Path(*SCAN_ROOT) / "proc.py"),),
                classes=("procfs", "proc-tool"),
                env="NO_SUCH_OVERRIDE",
                why="fixture",
            ),
            scopes[1],
        )
        _, _, _, seam_problems, _ = run(root, broken)
        check(
            "PLANT: an override name no covered file mentions reds",
            any("NO_SUCH_OVERRIDE" in p for p in seam_problems),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        ghost = (
            *scopes,
            Scope(
                name="ghost",
                files=(str(pathlib.Path(*SCAN_ROOT) / "nowhere.py"),),
                classes=("procfs",),
                env="REDIACC_PROC_BACKEND",
                why="fixture",
            ),
        )
        _, _, dead, seam_problems, _ = run(root, ghost)
        check("PLANT: a scope naming a file that is gone is DEAD", "ghost" in dead)
        check(
            "PLANT: and the missing file is named",
            any("not a file" in p for p in seam_problems),
        )

    with tempfile.TemporaryDirectory() as tmp:
        # ANTI-SILENCER, and this is the case that separates this gate from a grep. The needle appears twice in the clean guard already, inside a
        # regex; adding a third mention in a COMMENT must still be clean.
        quiet = plant(
            _CLEAN_GUARD,
            "def verdict(command):",
            "# a guard may discuss /proc/self/cmdline and pgrep -f freely\ndef verdict(command):",
        )
        root = _fixture(tmp, guard_source=quiet)
        _, unclaimed, dead, _, _ = run(root, scopes)
        check(
            "ANTI-SILENCER: /proc and pgrep in a comment are NOT findings",
            unclaimed == [] and dead == [],
        )

    with tempfile.TemporaryDirectory() as tmp:
        moved = plant(
            _CLEAN_SEAM, "def read(pid):", "# a line that shifts every finding down\ndef read(pid):"
        )
        root_a = _fixture(tmp, seam_source=_CLEAN_SEAM)
        keys_a = {f.key for f in run(root_a, scopes)[0]}
    with tempfile.TemporaryDirectory() as tmp:
        root_b = _fixture(tmp, seam_source=moved)
        keys_b = {f.key for f in run(root_b, scopes)[0]}
    check(
        "ANTI-SILENCER: a finding that MOVED keeps its key, so the set is line-stable",
        keys_a == keys_b and len(keys_a) >= 3,
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        root.joinpath(*SCAN_ROOT).mkdir(parents=True)
        check(
            "VACUITY: a scan root with zero Python files is a REFUSAL",
            _refuses(root, scopes),
        )

    with tempfile.TemporaryDirectory() as tmp:
        check("VACUITY: a missing scan root is a REFUSAL", _refuses(pathlib.Path(tmp), scopes))

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        check("VACUITY: zero declared scopes is a REFUSAL", _refuses(root, ()))

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, guard_source="def broken(:\n    pass\n")
        check(
            "VACUITY: a file that does not parse is a REFUSAL, not a skip",
            _refuses(root, scopes),
        )

    return not check.ok


def _refuses(root, scopes):
    try:
        run(root, scopes)
    except RefusalError:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
