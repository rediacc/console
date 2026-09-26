"""Renet functions and the e2e suite must agree in BOTH directions.

Ported from `.ci/scripts/quality/check-e2e-coverage.sh`, retired in W7 P5;
`rediacc_ci.quality.__init__` says how W7 phase 5 retired the twin.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED. Everything below this line up to PORT NOTES is the bash file's own archaeology, transliterated rather than summarised, because the prose is the only copy of why the gate has this shape.
-----------------------------------------------------------------------------

This gate has two halves:

  FORWARD (is every shipped renet function exercised by a suite CI RUNS?):
    delegated to `scripts/gates/check-e2e-coverage.ts`. Bash cannot honestly parse a
    playwright config to learn which files a job selects, so the forward pass is
    TypeScript: it imports each LIVE config, expands its projects into the
    concrete test files, and only counts coverage from those. A verb mentioned
    only in a dark suite or a declared-but-uncalled harness method no longer
    counts; that dead-coverage is the failure mode the rewrite closes. The
    forward allowlist lives in `.ci/policy/.e2e-coverage-allowlist`
    (BLOCKER-gated).

  REVERSE (does a test dispatch a verb renet no longer registers?):
    Phase 3 below, unchanged. It scans ALL e2e sources, dark files included,
    because a dead file calling a deleted verb is still a rot signal, and the
    oracle here is RENET_BRIDGE_FUNCTIONS (the dispatcher's full registry),
    which the forward TypeScript half deliberately does not use.

Usage:
  python3 -m rediacc_ci.quality.e2e_coverage

Exit codes:
  0 - Forward coverage complete AND no dispatched verb is missing from renet
  1 - A function is uncovered (forward), OR a test dispatches a dead verb
      (reverse), OR the live-config registry drifted from the workflows

PHASE 3: THE REVERSE DIRECTION, does e2e dispatch a verb that no longer EXISTS?

The forward half walks live -> e2e: "is every renet function exercised?" That is only half the contract, and the missing half is the one that bites. An e2e test calling a DELETED verb passed the old gate in total silence, which is exactly
how `datastore_init` / `mount` / `unmount`, `datastore_ceph_{init,fork,unfork}`
and `kube_csi_template` outlived their own removal in P1 and only surfaced when the Tests + Infra tier finally ran (it is gated behind the upstream gates, so it had not executed once all campaign).

The oracle is RENET_BRIDGE_FUNCTIONS: every name in the dispatcher's Registry, internal verbs included. RENET_FUNCTIONS (the forward half's subject) is the PUBLIC surface and omits them, and the bridge drives mostly internal verbs (`datastore_*`, `machine_check_*`, `daemon_*`), so it cannot answer this question. A schema-derived list cannot either: a verb may be registered WITHOUT
a schema (`ceph_clone_create` is) and still dispatch fine. This half stays scanning ALL files.

Every `function: 'name'` literal in the harness IS a dispatch. That is how `src/utils/bridge/methods/*.ts` name the verb they send to `functions once`.

THE SECOND WAY THE HARNESS DISPATCHES, and the gate could not see it.

`function: 'name'` is how the METHOD classes name a verb. But a test can also shell the bridge out directly, as a raw command string:

    sudo renet functions once --test-mode --function datastore_init \
        --datastore-path ...

That is the SAME dispatch through a different door, and the first sweep is blind to it, which is exactly how the dual-group migrate suite kept calling the DELETED `datastore_init` and dying with "no command builder registered", while the coverage gate reported that every e2e-dispatched verb existed. A gate that checks one of two call sites is not a gate.

COMMENTS ARE SKIPPED in the raw-dispatch sweep. Both this gate's own explanation and OpsManager's name the dead verb in prose ("the old `functions once --function datastore_init` path fails..."), and a gate that reds on a comment about a bug is a gate people delete.

-----------------------------------------------------------------------------
PORT NOTES. What changed in the translation, and what deliberately did not.
-----------------------------------------------------------------------------

THE FORWARD HALF IS STILL SHELLED OUT, and that is the port, not a shortcut. The twin runs `npx tsx scripts/gates/check-e2e-coverage.ts` from the repository root and keeps only its exit code; its output goes straight to the gate's own two streams. Reimplementing a playwright-config expansion in Python would be a SECOND forward half, and two implementations of one rule is the
failure this whole workstream is trying to remove. So the subprocess inherits stdout and stderr rather than capturing them: the TypeScript half's findings must land on the same streams they land on today, or the differential would score a port that silently swallowed them as equivalent while a human saw nothing.

THE TWO GREP SWEEPS BECOME `os.walk` PLUS `re`, AND FOUR PROPERTIES OF
`grep -rn --include='*.ts'` ARE BEHAVIOUR RATHER THAN INCIDENT:

  * `--include='*.ts'` matches the BASENAME, so `a.ts` is included at any depth
    and a directory called `x.ts` is not a subject.
  * `grep -r` does NOT follow directory symlinks (that is `-R`). The walk goes
    through `paths.walk_tree`, whose `follow_symlinks` defaults to False and is
    passed to `os.walk` explicitly there, because a default that happens to agree
    is one refactor away from not agreeing. That helper additionally prunes
    `.git`, `node_modules` and `.claude/worktrees`; the last is a peer session's
    sibling checkout of this repository, which git hides and `os.walk` did not.
  * A file grep cannot read is SKIPPED, not fatal. One unreadable `.ts` must not
    turn a rot detector into a detector that found nothing.
  * grep prints `<file>:<line>:<match>` with the file spelled exactly as it was
    reached from the command-line argument, which here is ABSOLUTE, because the
    twin passes `$E2E_TESTS_DIR/src` and `$E2E_TESTS_DIR/tests`. The twin then
    strips the repository root with `${file#"$REPO_ROOT"/}` before printing, so
    the finding text is repo-relative. Both steps are reproduced, in that order,
    because the finding text is what the differential compares.

RECURSION ORDER IS NOT PRESERVED, AND IT IS NOT PART OF THE VERDICT. GNU grep walks with fts and does not sort; `os.walk` yields in `os.scandir` order. The differential compares finding MULTISETS precisely so an ordering difference is not scored as a behaviour difference. The walk here sorts its directories and files anyway, so that a human diffing two runs of the PORT sees a
stable list.

THE VERB EXTRACTION IS GREEDY, ON PURPOSE. The twin pipes the matched line through `sed -E "s/.*function:[[:space:]]*'([a-z0-9_]+)'.*/\\1/"`. `sed`'s leading `.*` is greedy, so on a line carrying two `function: '...'` literals the LAST one is the verb extracted, and the first is invisible. That is a defect (reported, not fixed, see the report accompanying this port) and it is
REPRODUCED here rather than corrected: a port that fixes a bug changes the verdict, and the differential would rule MISMATCH_FINDINGS on the very tree that would prove the fix right. Whoever retires the twin owns the fix.

THE COMMENT SKIP IS A PREFIX TEST ON THE CODE COLUMN, not a parse. The twin strips leading whitespace from the third field of the grep hit and matches the shell patterns `'//'*`, `'*'*` and `'/*'*`. A `--function` inside a trailing comment on a live line is therefore NOT skipped by either implementation, which is the same blind spot in both. Named here so the next reader knows it
is inherited rather than introduced.

`is_dispatchable` IS A LINEAR SCAN IN THE TWIN and a set membership here. Same answer, and the twin's shape is the constraint disappearing rather than a simplification anyone chose: bash has no set type, and `check:ci-shell-commands` refuses `mapfile`, which is what pushed the twin to a `while read` accumulation loop in the first place.

EXIT CODES ARE UNCHANGED. 0 and 1 only; the twin has no setup-error code and no
77. `77` is reserved by the W7 contract for cannot-run, and neither half of this
gate can be in that state without the missing-file branches below firing first.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The generated contract. The twin spells this path out in full and so does this module: it is the ORACLE, and a helper that computed it would be one more place
# for the path to be wrong.
FUNCTIONS_REL = "packages/shared/src/renet-contract/data/functions.generated.ts"

# The harness. `src` and `tests` are swept; nothing else under the package is.
E2E_REL = "packages/e2e-tests"
E2E_SUBDIRS = ("src", "tests")

# `--include='*.ts'`, a basename match.
TS_SUFFIX = ".ts"

# The forward half, run from the repository root exactly as the twin runs it.
FORWARD_ARGV = ("npx", "tsx", "scripts/gates/check-e2e-coverage.ts")

# The array the reverse half reads, and the three patterns that bound it. The
# twin uses bash `=~` on each line, which finds the FIRST match in the line, so
# a line carrying two quoted names contributes only the first. Reproduced.
# `[[:space:]]` UNDER `LC_ALL=C` IS EXACTLY THIS SET MINUS THE NEWLINE, and the
# newline cannot occur inside a line either implementation looks at. Spelled out rather than written as `\s`, because Python's `\s` on a `str` pattern also matches U+00A0 and the other Unicode separators, which the C-locale POSIX class does not: a non-breaking space between `function:` and its quoted verb would then be a dispatch to the port and not to the twin.
_HSPACE = r"[ \t\r\f\v]"

ARRAY_OPEN_RE = re.compile(r"RENET_BRIDGE_FUNCTIONS%s*=%s*\[" % (_HSPACE, _HSPACE))
ARRAY_CLOSE_RE = re.compile(r"\]%s*as%s+const" % (_HSPACE, _HSPACE))
ARRAY_ITEM_RE = re.compile(r"'([a-z0-9_]+)'")

# Sweep 1: `function: 'name'`. The grep pattern, and then the greedy sed that extracts from the matched line. Two expressions because the twin uses two, and because they disagree on a line with more than one literal (see PORT NOTES).
METHOD_GREP_RE = re.compile(r"function:%s*'[a-z0-9_]+'" % _HSPACE)
METHOD_VERB_RE = re.compile(r".*function:%s*'([a-z0-9_]+)'" % _HSPACE)

# Sweep 2: a raw `--function <verb>` on a shelled-out command line.
RAW_GREP_RE = re.compile(r"--function%s+[a-z0-9_]+" % _HSPACE)
RAW_VERB_RE = re.compile(r".*--function%s+([a-z0-9_]+)" % _HSPACE)

# The comment prefixes the twin skips in sweep 2, as shell glob prefixes.
COMMENT_PREFIXES = ("//", "*", "/*")

# U+2014 is in the twin's finding text. Written as an escape rather than as the character so this file stays ASCII: the repo's prose rules forbid the literal, and the byte still has to reach the output because the finding text is exactly what the differential compares.
_EM_DASH = "\u2014"


def bridge_functions(text: str) -> list[str]:
    """Every name in the RENET_BRIDGE_FUNCTIONS array literal, in file order.

    THE STATE MACHINE IS THE TWIN'S, LINE FOR LINE. Open on the assignment, close on `] as const`, and take the first quoted lowercase-and-underscore token from every line in between. Anything cleverer (a real TypeScript parse) would answer differently on a file the twin mis-reads, and the whole point of a differential is that the two answer the same.

    A DUPLICATE IS KEPT. The twin appends to a bash array with no de-duplication and then reports its length in `Found N dispatchable verbs`, so a repeated name is counted twice on both sides.
    """
    names: list[str] = []
    in_array = False
    for line in text.split("\n"):
        if not in_array:
            if ARRAY_OPEN_RE.search(line):
                in_array = True
            continue
        if ARRAY_CLOSE_RE.search(line):
            break
        match = ARRAY_ITEM_RE.search(line)
        if match:
            names.append(match.group(1))
    return names


def ts_files(directory: pathlib.Path) -> list[str]:
    """Every `*.ts` under `directory`, absolute, sorted, symlinks not followed.

    A MISSING DIRECTORY IS AN EMPTY LIST, NOT AN ERROR. The twin sends grep's stderr to `/dev/null` and appends `|| true`, so a missing `src` or `tests` contributes nothing and the other one is still swept. That is the right direction for a rot detector, and it is also why the CALLER carries the real anti-vacuity refusal: an empty sweep here is only safe because the oracle itself
    is floored, which is checked before either sweep runs.
    """
    found: list[str] = []
    for dirpath, dirnames, filenames in paths.walk_tree(directory):
        dirnames.sort()
        found.extend(
            str(pathlib.Path(dirpath) / name)
            for name in sorted(filenames)
            if name.endswith(TS_SUFFIX)
        )
    return found


def _hits(path: str, grep_re: re.Pattern) -> list[tuple[int, str]]:
    """`grep -n` over one file: (1-based line number, the line) for each match.

    Unreadable is SKIPPED, matching grep, which prints a diagnostic to the stderr the twin discards and carries on with the next file.
    """
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[tuple[int, str]] = []
    for number, line in enumerate(text.split("\n"), start=1):
        if grep_re.search(line):
            out.append((number, line))
    return out


def method_dispatches(files: list[str]) -> list[tuple[str, str, int]]:
    """Sweep 1. Every `function: 'verb'` literal, as (verb, file, line)."""
    out: list[tuple[str, str, int]] = []
    for path in files:
        for number, line in _hits(path, METHOD_GREP_RE):
            match = METHOD_VERB_RE.match(line)
            if match:
                out.append((match.group(1), path, number))
    return out


def raw_dispatches(files: list[str]) -> list[tuple[str, str, int]]:
    """Sweep 2. Every raw `--function verb`, as (verb, file, line).

    A line whose CODE begins with a comment prefix is skipped. The twin builds
    `code="${rest#*:}"` from the grep hit, which is everything after the line
    number, then strips leading whitespace and tests three shell patterns.
    """
    out: list[tuple[str, str, int]] = []
    for path in files:
        for number, line in _hits(path, RAW_GREP_RE):
            if line.lstrip().startswith(COMMENT_PREFIXES):
                continue
            match = RAW_VERB_RE.match(line)
            if match:
                out.append((match.group(1), path, number))
    return out


def forward_half(root: pathlib.Path) -> int:
    """`(cd "$REPO_ROOT" && npx tsx scripts/gates/check-e2e-coverage.ts)`, exit code only.

    STREAMS ARE INHERITED, NOT CAPTURED. See the PORT NOTES: the TypeScript half's findings are the gate's findings, and a port that buffered them would change which stream carried them and when.

    A MISSING `npx` IS THE SAME 127 THE TWIN REPORTS. `subprocess` raises FileNotFoundError where bash prints `command not found` and yields 127, so the exception is converted rather than allowed to escape as a traceback that a reader would file as flake rather than as a missing toolchain.
    """
    try:
        completed = subprocess.run(
            list(FORWARD_ARGV),
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        print("%s: command not found" % FORWARD_ARGV[0], file=sys.stderr)
        return 127
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 when both halves hold, 1 on any gap."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    functions_file = root / FUNCTIONS_REL
    e2e_dir = root / E2E_REL

    # The twin prints the ABSOLUTE path in both of these, because it interpolates `$FUNCTIONS_FILE` and `$E2E_TESTS_DIR`, which it built from `$REPO_ROOT`.
    if not functions_file.is_file():
        log.error("Functions file not found: %s" % functions_file)
        return 1
    if not e2e_dir.is_dir():
        log.error("e2e-tests directory not found: %s" % e2e_dir)
        return 1

    forward_rc = forward_half(root)

    log.step("Checking e2e-tests dispatch only verbs that still exist...")

    names = bridge_functions(functions_file.read_text(encoding="utf-8", errors="replace"))

    # ZERO INPUTS IS A FAILURE, NEVER A PASS. An empty oracle would make every verb in the tree look dead, which is noisy rather than silent, but the twin still refuses here and names the regeneration command, because a parser that stopped matching is a broken instrument either way.
    if not names:
        log.error(
            "No functions extracted from RENET_BRIDGE_FUNCTIONS %s parsing may be broken,"
            % _EM_DASH
        )
        log.error("or the contract predates it. Regenerate:")
        log.error(
            "  private/renet/bin/renet functions generate-types --output "
            "packages/shared/src/renet-contract/data --version dev"
        )
        return 1

    # THE SHAPE, NOT JUST THE VERDICT. The count is printed on every run so a reader notices the day the oracle collapses from ninety to three.
    log.info("Found %d dispatchable verbs in RENET_BRIDGE_FUNCTIONS" % len(names))

    dispatchable = set(names)
    files: list[str] = []
    for sub in E2E_SUBDIRS:
        files.extend(ts_files(e2e_dir / sub))

    dead: list[str] = []
    for verb, path, number in method_dispatches(files):
        if verb in dispatchable:
            continue
        dead.append("%s  %s %s:%d" % (verb, _EM_DASH, _relative(root, path), number))
    for verb, path, number in raw_dispatches(files):
        if verb in dispatchable:
            continue
        dead.append(
            "%s  %s %s:%d  (raw --function dispatch)"
            % (verb, _EM_DASH, _relative(root, path), number)
        )

    reverse_rc = 0
    if dead:
        reverse_rc = 1
        log.error("e2e-tests dispatch %d verb(s) that renet no longer registers:" % len(dead))
        log.error("")
        for item in dead:
            log.error("  - %s" % item)
        log.error("")
        log.error('These calls fail at RUNTIME with "no command builder registered". A renamed')
        log.error("verb means the test is stale by design: fix it FORWARD against the surviving")
        log.error("surface (see RENET_BRIDGE_FUNCTIONS), never restore the old name.")
    else:
        log.info("All e2e-dispatched verbs exist in the renet registry")

    if forward_rc != 0 or reverse_rc != 0:
        return 1
    return 0


def _relative(root: pathlib.Path, path: str) -> str:
    """`${file#"$REPO_ROOT"/}`: a PREFIX STRIP, not a path computation.

    The distinction matters for a file outside the root, which bash leaves untouched (the prefix does not match) where `os.path.relpath` would invent a `../../..` chain. The sweep cannot reach outside the root today; the twin's behaviour is reproduced anyway, because "cannot happen" is how a difference survives until it can.
    """
    prefix = str(root) + os.sep
    return path.removeprefix(prefix)


_SAMPLE_CONTRACT = """\
export const RENET_FUNCTIONS = [
  'public_only',
] as const;

export const RENET_BRIDGE_FUNCTIONS = [
  'repo_up',
  'datastore_mount',
  'ceph_clone_create',
] as const;

export const RENET_AFTER = ['never_seen'] as const;
"""


def selftest() -> int:
    """Both directions on every extractor, then the gate itself on real trees.

    A GATE WITH ONLY POSITIVE CONTROLS WILL HAPPILY FLAG THE WHOLE TREE, so every plant below is paired with the mirror that must NOT fire: a live verb beside a dead one, a commented dispatch beside a real one, a name outside the array beside the names inside it.
    """
    ctl = Controls("e2e-coverage", floor=19, verbose=True)

    # -- THE ORACLE PARSER, both directions -------------------------------------
    ctl.check(
        "ORACLE: the bridge array is read in file order",
        bridge_functions(_SAMPLE_CONTRACT),
        ["repo_up", "datastore_mount", "ceph_clone_create"],
    )
    ctl.check(
        "ORACLE MIRROR: names before the array and after `as const` are not read",
        [n for n in bridge_functions(_SAMPLE_CONTRACT) if n in {"public_only", "never_seen"}],
        [],
    )
    ctl.check(
        "ORACLE: a file with no array at all yields nothing",
        bridge_functions("export const OTHER = ['x'] as const;\n"),
        [],
    )
    ctl.check(
        "ORACLE: one line contributes at most one name, as bash =~ does",
        bridge_functions("X RENET_BRIDGE_FUNCTIONS = [\n  'a', 'b',\n] as const\n"),
        ["a"],
    )
    ctl.check(
        "ORACLE: a repeated name is counted twice, as the bash array does",
        bridge_functions("RENET_BRIDGE_FUNCTIONS = [\n 'a'\n 'a'\n] as const\n"),
        ["a", "a"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        # -- THE TWO SWEEPS, both directions ------------------------------------
        src = base / "src"
        src.mkdir()
        (src / "live.ts").write_text(
            "const a = { function: 'repo_up' };\nconst b = { function: 'datastore_mount' };\n",
            encoding="utf-8",
        )
        (src / "raw.ts").write_text(
            "// the old functions once --function datastore_init path fails\n"
            "run('sudo renet functions once --function repo_up --tag x');\n"
            "run('sudo renet functions once --function gone_verb');\n",
            encoding="utf-8",
        )
        (src / "notes.md").write_text("function: 'not_a_ts_file'\n", encoding="utf-8")

        listed = ts_files(src)
        ctl.check("SWEEP: only .ts files are subjects", len(listed), 2)
        ctl.check(
            "SWEEP MIRROR: a .md carrying the pattern is not a subject",
            [p for p in listed if p.endswith(".md")],
            [],
        )
        ctl.check(
            "SWEEP: every `function: 'verb'` literal is a dispatch",
            sorted(v for v, _f, _n in method_dispatches(listed)),
            ["datastore_mount", "repo_up"],
        )
        ctl.check(
            "SWEEP: a raw --function on a live line is a dispatch",
            sorted(v for v, _f, _n in raw_dispatches(listed)),
            ["gone_verb", "repo_up"],
        )
        ctl.check(
            "SWEEP MIRROR: a --function named inside a `//` comment is skipped",
            [v for v, _f, _n in raw_dispatches(listed) if v == "datastore_init"],
            [],
        )
        ctl.check(
            "SWEEP: the line number is the grep line number, 1-based",
            [n for v, _f, n in raw_dispatches(listed) if v == "gone_verb"],
            [3],
        )

        # -- THE GATE, on trees built to fire and not to fire --------------------
        def build(name: str, contract: str, sources: dict[str, str]) -> pathlib.Path:
            """A minimal tree the gate can be pointed at with REDIACC_CI_ROOT."""
            tree = base / name
            (tree / pathlib.Path(FUNCTIONS_REL).parent).mkdir(parents=True, exist_ok=True)
            (tree / FUNCTIONS_REL).write_text(contract, encoding="utf-8")
            for rel, body in sources.items():
                target = tree / E2E_REL / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
            # A forward half that always agrees, so the reverse half is what the controls below are measuring. The stub is a real executable on a real PATH rather than a monkeypatch, because the twin resolves `npx` through PATH and a patched function would not prove that.
            binary = tree / "fxbin"
            binary.mkdir(parents=True, exist_ok=True)
            (binary / "npx").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (binary / "npx").chmod(0o755)
            return tree

        def run(tree: pathlib.Path) -> int:
            saved_root = os.environ.get(paths.ROOT_ENV)
            saved_path = os.environ.get("PATH", "")
            os.environ[paths.ROOT_ENV] = str(tree)
            os.environ["PATH"] = "%s%s%s" % (tree / "fxbin", os.pathsep, saved_path)
            try:
                return main([])
            finally:
                os.environ["PATH"] = saved_path
                if saved_root is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved_root

        clean = build(
            "clean",
            _SAMPLE_CONTRACT,
            {"src/a.ts": "const a = { function: 'repo_up' };\n", "tests/b.ts": "// nothing\n"},
        )
        ctl.check("CONTROL: a tree dispatching only live verbs passes", run(clean), 0)

        dead_tree = build(
            "dead",
            _SAMPLE_CONTRACT,
            {"src/a.ts": "const a = { function: 'datastore_init' };\n"},
        )
        ctl.check("PLANT: a dispatch of a deleted verb is caught", run(dead_tree), 1)

        raw_tree = build(
            "raw",
            _SAMPLE_CONTRACT,
            {"tests/c.ts": "run('renet functions once --function kube_csi_template');\n"},
        )
        ctl.check("PLANT: the raw --function door is caught too", run(raw_tree), 1)

        commented = build(
            "commented",
            _SAMPLE_CONTRACT,
            {"tests/c.ts": "// renet functions once --function kube_csi_template\n"},
        )
        ctl.check("PLANT MIRROR: the same verb in a comment is not caught", run(commented), 0)

        # THE VACUITY CONTROL CARRIES A REAL e2e DIRECTORY, and the first cut of it did not. Without `src/a.ts` the tree has no `packages/e2e-tests` at all, so the gate returned 1 from the MISSING-DIRECTORY branch and the control passed while the refusal it names never executed. A control that fires for the wrong reason is worse than one that does not fire, because it reads as
        # evidence. The mirror below is the other half: the same tree with a parseable oracle must PASS, which is what pins the exit code to the oracle rather than to the fixture's shape.
        oracle_sources = {"src/a.ts": "const a = { function: 'repo_up' };\n"}
        empty_oracle = build("empty", "export const NOTHING = [] as const;\n", oracle_sources)
        ctl.check("VACUITY: an unparseable oracle is a refusal, not a pass", run(empty_oracle), 1)
        parseable = build("parseable", _SAMPLE_CONTRACT, oracle_sources)
        ctl.check("VACUITY MIRROR: the same tree with a parseable oracle passes", run(parseable), 0)

        missing_e2e = base / "missing-e2e"
        (missing_e2e / pathlib.Path(FUNCTIONS_REL).parent).mkdir(parents=True, exist_ok=True)
        (missing_e2e / FUNCTIONS_REL).write_text(_SAMPLE_CONTRACT, encoding="utf-8")
        ctl.check("SETUP: an absent e2e-tests directory is a failure", run(missing_e2e), 1)

        missing_contract = base / "missing-contract"
        (missing_contract / E2E_REL / "src").mkdir(parents=True, exist_ok=True)
        ctl.check("SETUP: an absent contract file is a failure", run(missing_contract), 1)

        # THE FORWARD HALF IS LOAD-BEARING, so a stub that FAILS must red a tree whose reverse half is spotless. Without this control the gate could drop the forward exit code entirely and every case above would still pass.
        forward_red = build(
            "forward-red",
            _SAMPLE_CONTRACT,
            {"src/a.ts": "const a = { function: 'repo_up' };\n"},
        )
        (forward_red / "fxbin" / "npx").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (forward_red / "fxbin" / "npx").chmod(0o755)
        ctl.check("PLANT: a failing forward half reds an otherwise clean tree", run(forward_red), 1)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
