"""A gate test that WRITES INTO THE REAL TREE must be registered as a WRITER.

Ported from `.ci/scripts/quality/check-pool-writer-safety.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live until a
differential ledger row exists over K distinct trees. Its gate header registers it as step "Pool-registered tests do not write the real tree", needs none, selftest true.

-----------------------------------------------------------------------------
RETARGETED 2026-09-09 (W7P3-BAT): THE REGISTRATION IS THE LOCK, NOT THE RUNNER.
-----------------------------------------------------------------------------

The registration used to live in `.ci/scripts/test/run-all.sh`, as the hand-maintained `WRITER_TESTS` / `WRITER_TESTS_FALLBACK` arrays, and this gate parsed them out of that file's TEXT. `battery.py` replaces run-all.sh and has no such array on purpose -- it classifies from `scripts/ci-runner/gates.lock.json`'s `mutex: ["tree:..."]` declarations, which is the same contract
`scripts/ci-runner/pool.ts` schedules by, and a third hand list would be the duplication the whole port exists to remove.

So the subject moved with the runner. Left parsing run-all.sh this gate would have gone one of two ways once that file was deleted, and both are worse than a red: it would REFUSE ("runner not found", exit 1) and read as a bug in the deletion, or -- had anyone "fixed" that by treating an absent runner as clean -- it would pass forever while policing nothing.

THE RETARGET IS NOT A WEAKENING, MEASURED RATHER THAN ASSERTED. On this tree, 2026-09-09: the old parse over run-all.sh returned 4 names (`test-docs-gen.sh`, `test-gate-anti-vacuity.sh`, `test-gate-paths-exist.sh`, `test-generate-tag-inputs.sh`) and the lock's `mutex` set returns those 4 plus `test-shrink-only-composition.sh`. `old - new` is EMPTY, so nothing that was
being demanded stopped being demanded; the one addition is a test the lock
already serialises and the hand list had never been updated to carry, which is itself the argument against hand lists.

`reads` IS DELIBERATELY NOT ACCEPTED as a registration. A scanner is released to
run beside other scanners; only `mutex` puts a test in the serial W chain, so a
writer declared `reads` is exactly the flake this gate exists to catch.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED WHOLE. These paragraphs are measurements and dated
incidents; none of them can be recovered from the code.
-----------------------------------------------------------------------------

THE DEFECT THIS COMES FROM, 2026-08-17. run-all.sh fans the gate battery out over the runner cores in three sets: W (writers, one serial chain, exclusive), S (scanners, read the real tree, released after W), and T (everything else, isolated by construction). test-generate-tag-inputs.sh swaps the REAL .ci/scripts/version/resolve-version.sh for a stub and restores it a second later,
and it was classified T -- in the pool -- on the strength of its own comment, which claimed it "cannot disturb a shared tree". That was true of the tag namespace it carefully avoids writing and false of the working tree it overwrites.

WHY THIS CLASS IS WORTH A GATE RATHER THAN A CODE REVIEW. The symptom is not a clean failure. A concurrent gate read resolve-version.sh mid-restore and reddened gate-test:claude-hooks with a bash syntax error in a file that parses clean and passes 884/0 serially. That is a CONCURRENCY ARTIFACT: it does not reproduce on the serial re-run, so the re-run "clears" it and the next
session pays for the diagnosis again. docs/agent-reference/TRAPS.md carries the entry. The misclassification is invisible to every other gate in the repo, and it is cheap to
make -- the run-all.sh comment says it outright: "Adding to this list is cheap;
leaving something off it is a flake."

WHY THIS SIGNAL AND NOT A BROADER ONE. "Detect a write to shared state" is not decidable in general, and a fuzzy version gets skimmed and then suppressed, which is the failure mode this repo keeps finding. So the rule is ONE mechanical shape, chosen because it is what all three real writers actually look like: a write whose TARGET PATH is rooted at a variable that derives from the
repo root, and not at one that derives from mktemp.

Two candidate signals were measured against the real battery and DROPPED for precision, both on evidence:
  - `git tag` / `git commit` / `git add`: zero true positives (the one real
    tag-namespace risk, test-generate-tag-inputs.sh, deliberately drives the
    resolver instead of cutting a tag) and one guaranteed false positive at
    test-age-check.sh:26-30, which runs git against a `git init` fixture in a temp
    dir. Deciding that apart needs cwd tracking through a subshell.
  - a literal repo-relative redirect (`>.ci/...`): zero true positives, and its
    only match in the battery is a docs path inside a JS string literal at
    test-scope-engine.sh:523. Matching inside strings is exactly the cry-wolf
    shape.
The surviving signal alone flags all three registered writers and nothing else across all 93 gate tests: measured false-positive rate zero.

THE RULE IS ONE-DIRECTIONAL, deliberately. A file that writes must be declared; a
file declared W that no longer writes is NOT reported. Over-declaring costs a little wall time, under-declaring manufactures a flake, and the gate should not push anybody toward the expensive side of that asymmetry.

Exit codes:
  0 - every real-tree writer declares a `mutex` `tree:` resource in the lock
  1 - an unregistered writer, or the gate could not prove itself (see CONTROL)

THE SCANNER, in the twin's own words. Two passes over each file. Pass 1 classifies every variable as REPO-ROOTED or TEMP-ROOTED and propagates that
through assignment; pass 2 reports writes aimed at a repo-rooted target. Two
passes rather than one because a function body can textually precede the assignment of a global it uses.

The taint SEED is the idiom, never the name: any variable assigned from `$(cd ... && pwd)`, `get_repo_root`, or `git rev-parse --show-toplevel`. That is what makes it self-maintaining -- 79 of the 93 gate tests spell it REPO_ROOT and 4 use get_repo_root, but a new file picking a different name is still caught. It also, correctly, taints SCRIPT_DIR: the gates directory is itself
inside the real tree, so a write aimed there is a real-tree write.

TEMP beats REPO in propagation. `ROOT="$FIXTURE/repo"` where
`FIXTURE="$(mktemp -d)"` is a temp path even though the name looks like a root,
and that exact pair is 15 of the 21 lines an earlier draft of this scanner got wrong before propagation was ordered this way.

Heredoc bodies are stripped in both passes: 40 of the 93 gate tests carry a heredoc, and a redirect quoted inside one is text, not a write.

THE WRITE TARGET IS THE LAST ARGUMENT, not the whole line. Taking the whole line instead reads the source path and, for sed, the expression -- which is how an earlier draft flagged test-installmethods-args.sh:141, where a real-tree dir appears in the REPLACEMENT TEXT while the file being edited is a temp copy. That is a false positive of exactly the kind that trains a reader to
skim this gate. `rm`, `mkdir`, `chmod`, `touch` and `truncate` take a LIST of targets rather than a source/target pair, so for those every non-flag argument is a write target.

`&` AND `<` RULE OUT fd duplication and input redirection, and `-` rules out the ASCII arrow: test-generate-tag-inputs.sh:309 logs "($before -> $after -> $restored)", and $restored is repo-rooted, so without this the gate reports a log line as a write.

CONTROL FIRST. A gate whose green has never been contrasted with a red is a gate nobody has checked. This one plants both directions and refuses to report on the real tree unless BOTH land. The NEGATIVE half is not decoration. A scanner that flagged every file would satisfy the positive control perfectly while being worthless, and "it fired" is the reassuring half of the evidence.
The planted temp-writer uses the exact mktemp-into-a-root-shaped-name pair that broke the first draft.

-----------------------------------------------------------------------------
THE ARCHAEOLOGY OF THE THREE STACKED DEFECTS, 2026-09-06. This is why the twin is the shape it is, and it is carried verbatim because a port that dropped it would leave the next reader free to make all three again.
-----------------------------------------------------------------------------

1. log_fail: log_error plus exit 1, in one call. common.sh defines log_info,
   log_warn, log_error, log_step and log_debug, and NOT this one, so every
   `log_fail` was `command not found` and this gate exited 127 instead of
   refusing. That mattered more than a missing helper usually does, because ALL
   THREE call sites are the anti-vacuity refusals: the runner being absent,
   WRITER_TESTS parsing empty, and the gates directory being empty. A guard that
   crashes is a guard that never fired, and 127 is not a verdict. Found
   2026-09-06 when the shape change below finally drove one of them.

2. RE-KEYED 2026-09-06, invariant 2. The registered-writer read was
   `WRITER_TESTS=(` ... `)`, and W2.4b changed run-all.sh so that array is no
   longer a literal: it is DERIVED from the `tree:` isolation declarations in
   scripts/ci-runner/gates.lock.json, with the hand-maintained literal list
   surviving only as WRITER_TESTS_FALLBACK. The old pattern therefore matched the
   computed assignment `WRITER_TESTS=($RUN_ALL_WRITERS)`, whose body holds no test
   names, and parsed EMPTY -- which is exactly the state the refusal exists to
   catch, and it could not report it because log_fail did not exist. Both arrays
   are read and unioned rather than picking one, because which of them run-all.sh
   actually uses is decided at RUN time by whether the lock declares any
   isolation. A gate that read only one of the two would go quiet the moment that
   branch flipped, which is the same silent narrowing this re-key is repairing.
   Comment lines inside the array name test files while describing them (the
   test-generate-tag-inputs.sh entry cites two line numbers), so they are dropped
   before the names are read.

3. With both fixed, the gate named a real unregistered tree writer. The finding
   was genuine; the two defects above are what had been hiding it.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE AWK IS TRANSLITERATED, NOT REWRITTEN, and the awk-isms are kept because they are behaviour. `split(line, a, /[ \t]+/)` with a REGEX field separator produces a leading EMPTY field for an indented line, so `nonflagargs`, which starts at index 2, skips that empty field and then treats the COMMAND NAME as an argument on an indented line while skipping it on a flush-left one. That
asymmetry is harmless (a command name carries no `$VAR`, so `reftype` ignores it) and it is preserved rather than tidied, because tidying it is a change to the corpus of things the gate looks at.

POSIX ERE IS LEFTMOST-LONGEST AND PYTHON IS LEFTMOST-FIRST. Every pattern here was checked for a case where the two differ and none does: the assignment pattern
backtracks to the same answer for `local=1` and `exportFOO=1`, the redirect
pattern's `>>?` is greedy in both, and `test-[A-Za-z0-9._-]+\\.sh` lands on the same token in both engines. Stated because "the regex is the same text" is not the same claim as "the regex matches the same thing".

THE MULTI-LINE `printf ' %s\\n' "$hits"` IS A TWIN DEFECT, CARRIED. `$hits` is ONE argument holding several newline-separated lines, so printf applies the format ONCE and only the FIRST line gets its two-space indent. A port that indented every line would print different bytes and, worse, would change the finding set: `scripts/lib/shadow-gate.ts` promotes an unindented
`<file>.sh:<line>:` to a finding by its path-line rule and an indented one by its continuation rule, so both are compared either way, but the TEXT differs. Reported, not repaired.

THE ONE-DIRECTIONAL RULE MEANS THIS GATE HAS NO SHRINK-ONLY BASELINE and needs none: it reports only NEW unregistered writers, and a registration that outlived its write is deliberately not a finding.

`grep -qxF "$base" <<<"$REGISTERED"` IS AN EXACT WHOLE-LINE FIXED MATCH, so membership is a set lookup here and not a substring test. A substring test would
let `test-foo.sh` be satisfied by a registration of `test-foo.sh.bak`. The
retarget kept that property: the lock parser emits basenames and membership is still an exact set lookup.

THE THREE ANTI-VACUITY REFUSALS SURVIVED THE RETARGET ONE FOR ONE, because they are what make the verdict mean anything: the LOCK being absent (was: the runner), the parse returning ZERO writers (was: an empty WRITER_TESTS), and the gates directory being empty. Each one exits 1 and says which.
"""

import json
import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The twin's seams, kept by name so one harness drives either implementation. `POOL_SAFETY_RUNNER` BECAME `POOL_SAFETY_LOCK` IN THE 2026-09-09 RETARGET, and the rename is deliberate rather than cosmetic: the seam now points at the declaration file, and a seam still called RUNNER would invite a caller to hand this gate a runner it no longer reads, which is the quietest way to make a
# fixture-driven control test nothing.
GATES_DIR_ENV = "POOL_SAFETY_GATES_DIR"
LOCK_ENV = "POOL_SAFETY_LOCK"
GATES_DIR_REL = (".ci", "scripts", "test", "gates")
LOCK_REL = ("scripts", "ci-runner", "gates.lock.json")

# A lock entry is a gate test when its `run` names a script under this prefix. `run` is a command line in the general case, so the WORD that starts with the prefix is taken rather than the whole string.
GATES_RUN_PREFIX = ".ci/scripts/test/gates/"

# The claim strength that means "serialised writer". `reads` is NOT accepted: a scanner is released to run beside other scanners, so a writer hiding in that set is exactly the flake this gate exists for.
WRITER_CLAIM = "mutex"
TREE_RESOURCE_PREFIX = "tree:"

# --------------------------------------------------------------------------- The awk scanner's patterns, one Python name per awk construct so a reader can put the two files side by side. ---------------------------------------------------------------------------

# `split(line, a, /[ \t]+/)`.
_FIELD_SEP_RE = re.compile(r"[ \t]+")

# `\$\{?[A-Za-z_][A-Za-z0-9_]*\}?` -- a $VAR or ${VAR} reference.
_VARREF_RE = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")

# `^[ \t]*(local|declare|readonly|export|typeset)?[ \t]*[A-Za-z_][A-Za-z0-9_]*=`
_ASSIGN_RE = re.compile(
    r"^[ \t]*(?:local|declare|readonly|export|typeset)?[ \t]*[A-Za-z_][A-Za-z0-9_]*="
)
_ASSIGN_HEAD_RE = re.compile(r"^[ \t]*(?:local|declare|readonly|export|typeset)?[ \t]*")

# The TEMP seed and the REPO seed. TEMP beats REPO; see the twin's header.
_TEMP_VAL_RE = re.compile(r"mktemp|TMPDIR|get_temp_dir|/tmp/")
_REPO_VAL_RE = re.compile(r"\$\(cd .*pwd\)|rev-parse --show-toplevel|get_repo_root")

# The write commands, split by how they name their target.
_PAIR_CMD_RE = re.compile(r"^[ \t]*(?:cp|mv|install|ln)[ \t]")
_SED_RE = re.compile(r"sed_in_place|sed -i")
_LIST_CMD_RE = re.compile(r"^[ \t]*(?:rm|mkdir|chmod|touch|truncate)[ \t]")

# `>>?[ \t]*"?\$\{?[A-Za-z_][A-Za-z0-9_]*\}?` -- a redirect at a $VAR target.
_REDIRECT_RE = re.compile(r">>?[ \t]*\"?\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")
# `pre !~ /[-&<]$/` -- fd duplication, input redirection, and the ASCII arrow.
_NOT_A_REDIRECT_RE = re.compile(r"[-&<]$")

# `^[ \t]*#` -- a whole-line comment, skipped in both passes.
_COMMENT_RE = re.compile(r"^[ \t]*#")

# `<<-?[ \t]*[\047"]?[A-Za-z_][A-Za-z0-9_]*` guarded by `line !~ /<<</`.
_HEREDOC_RE = re.compile(r"<<-?[ \t]*['\"]?[A-Za-z_][A-Za-z0-9_]*")
_HEREDOC_LEAD_RE = re.compile(r"^<<-?[ \t]*")
_HERESTRING_RE = re.compile(r"<<<")

# THE TWO ARRAY PATTERNS ARE GONE WITH THE 2026-09-09 RETARGET. They read
# `WRITER_TESTS(_FALLBACK)?=(` out of run-all.sh, and battery.py has no such
# array: it classifies from the lock and carries no hand list at all, on purpose (three copies of one definition is the defect the whole port removes). The registered set is now read from the lock by `registered_writers` below.


def _fields(line: str) -> list[str]:
    """`split(line, a, /[ \\t]+/)`, leading empty field and all. See the port notes."""
    return _FIELD_SEP_RE.split(line)


def _lastarg(line: str) -> str:
    """`lastarg`: the final field. Empty when the line ends in whitespace, as awk's is."""
    fields = _fields(line)
    return fields[-1] if fields else ""


def _nonflagargs(line: str) -> str:
    """`nonflagargs`: every field from index 2 on that does not start with `-`.

    Index 2 in awk is index 1 here. The awk quirk that this skips the leading empty field on an indented line, and therefore includes the command name, is
    preserved; see the port notes.
    """
    out = ""
    for field in _fields(line)[1:]:
        if field.startswith("-"):
            continue
        out = out + " " + field
    return out


def _reftype(text: str, safe: set[str], taint: set[str]) -> str:
    """`reftype`: "safe" if ANY referenced name is temp-rooted, else "taint", else "none".

    SAFE WINS over taint, which is the propagation order that took an earlier draft's 21 wrong lines down to 6. A path built from a temp root is a temp path however repo-shaped the variable's NAME is.
    """
    has_safe = False
    has_taint = False
    for match in _VARREF_RE.finditer(text):
        name = re.sub(r"[${}]", "", match.group(0))
        if name in safe:
            has_safe = True
        elif name in taint:
            has_taint = True
    if has_safe:
        return "safe"
    if has_taint:
        return "taint"
    return "none"


class _Heredoc:
    """The `inhd`/`hd` state machine, reset at FNR==1 of each pass.

    A heredoc BODY is skipped in both passes: 40 of the 93 gate tests carry one, and a redirect quoted inside it is text rather than a write.
    """

    def __init__(self) -> None:
        self.inside = False
        self.token = ""

    def swallow(self, line: str) -> bool:
        """True when this line is inside a heredoc body (or is its terminator)."""
        if not self.inside:
            return False
        if re.search("^[ \t]*%s[ \t]*$" % re.escape(self.token), line):
            self.inside = False
        return True

    def opens(self, line: str) -> bool:
        """Does this line OPEN a heredoc? `<<<` is a herestring and does not."""
        if _HERESTRING_RE.search(line):
            return False
        match = _HEREDOC_RE.search(line)
        if not match:
            return False
        token = _HEREDOC_LEAD_RE.sub("", match.group(0))
        self.token = re.sub(r"['\"]", "", token)
        return True


def scan_text(text: str, fname: str) -> list[str]:
    """The two-pass awk scanner over one file's text.

    Returns one `<fname>:<line>: <body>` per repo-rooted write site, in file order. Empty means clean. Exported so `--selftest` and a pytest case can plant both directions without touching the disk.
    """
    lines = text.split("\n")
    # awk reads records, and a trailing newline does not make a final empty one.
    if lines and lines[-1] == "":
        lines = lines[:-1]

    safe: set[str] = set()
    taint: set[str] = set()

    # --- pass 1: classify assignments ---------------------------------------
    heredoc = _Heredoc()
    for line in lines:
        if heredoc.swallow(line):
            continue
        if _COMMENT_RE.match(line):
            continue
        opened = heredoc.opens(line)
        match = _ASSIGN_RE.match(line)
        if match:
            head = match.group(0)
            val = line[match.end() :]
            head = re.sub(r"=$", "", head, count=1)
            head = _ASSIGN_HEAD_RE.sub("", head, count=1)
            if _TEMP_VAL_RE.search(val):
                safe.add(head)
                taint.discard(head)
            elif _REPO_VAL_RE.search(val):
                taint.add(head)
            else:
                kind = _reftype(val, safe, taint)
                if kind == "safe":
                    safe.add(head)
                    taint.discard(head)
                elif kind == "taint":
                    taint.add(head)
        if opened:
            heredoc.inside = True

    # --- pass 2: report repo-rooted write targets ---------------------------
    hits: list[str] = []
    heredoc = _Heredoc()
    for number, line in enumerate(lines, start=1):
        if heredoc.swallow(line):
            continue
        if _COMMENT_RE.match(line):
            continue
        opened = heredoc.opens(line)

        tgt = ""
        if _PAIR_CMD_RE.match(line):
            tgt = tgt + " " + _lastarg(line)
        if _SED_RE.search(line):
            tgt = tgt + " " + _lastarg(line)
        if _LIST_CMD_RE.match(line):
            tgt = tgt + " " + _nonflagargs(line)
        rest = line
        while True:
            match = _REDIRECT_RE.search(rest)
            if not match:
                break
            pre = rest[: match.start()]
            if not _NOT_A_REDIRECT_RE.search(pre):
                tgt = tgt + " " + match.group(0)
            rest = rest[match.end() :]

        if tgt != "" and _reftype(tgt, safe, taint) == "taint":
            body = re.sub(r"^[ \t]+", "", line, count=1)
            hits.append("%s:%d: %s" % (fname, number, body))

        if opened:
            heredoc.inside = True

    return hits


def scan_file(path: pathlib.Path) -> str:
    """`scan_file <path>` -- one line per repo-rooted write site, empty when clean.

    Returns the joined text rather than a list because the twin's callers test it
    with `[[ -z ... ]]` and print it with a single `printf`, and the multi-line
    printf's behaviour is part of the output contract; see the port notes.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return "\n".join(scan_text(text, path.name))


def registered_writers(lock_text: str) -> list[str]:
    """Gate-test basenames declared `mutex: ["tree:..."]` in gates.lock.json.

    RETARGETED 2026-09-09. This used to parse `WRITER_TESTS(_FALLBACK)?=(` out of
    run-all.sh. battery.py has no such array by design, so the registration it schedules by is the lock, and this is `battery.classify_from_lock(lock, "mutex")` transliterated -- the same algorithm run-all.sh itself carried as an inline python3 heredoc at run-all.sh:292. Reading the same declaration the runner schedules by is the point: a gate that read a SECOND list would be the
    third copy of one definition, and copies disagree.

    MEASURED AT THE RETARGET, and it is the reason this is not a weakening: the old parse returned 4 names and this one returns those same 4 plus test-shrink-only-composition.sh, which run-all.sh's hand list had never been updated to carry. Set difference in the other direction is empty.

    An unparseable or non-list lock contributes NOTHING rather than raising,
    which is `battery.classify_from_lock`'s documented behaviour; the CALLER
    turns that into the anti-vacuity refusal, because "nothing is declared" and "the lock is broken" must not silently become "nothing needs isolating".
    """
    try:
        entries = json.loads(lock_text)
    except ValueError:
        return []
    if not isinstance(entries, list):
        return []
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        run = entry.get("run")
        if not isinstance(run, str) or GATES_RUN_PREFIX not in run:
            continue
        claimed = entry.get(WRITER_CLAIM)
        if not isinstance(claimed, list):
            continue
        if not any(isinstance(r, str) and r.startswith(TREE_RESOURCE_PREFIX) for r in claimed):
            continue
        for word in run.split():
            if word.startswith(GATES_RUN_PREFIX):
                names.add(os.path.basename(word))
                break
    return sorted(names)


# The two planted control fixtures, byte for byte from the twin's heredocs. The temp-safe one uses the exact mktemp-into-a-root-shaped-name pair that broke the first draft of the scanner, and its INNER heredoc is a redirect that is text.
PLANTED_WRITER = """#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
run_it() {
    local real="$REPO_ROOT/.ci/scripts/version/resolve-version.sh"
    printf 'stub\\n' >"$real"
}
"""

PLANTED_TEMPSAFE = """#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
FIXTURE="$(mktemp -d)"
ROOT="$FIXTURE/repo"
run_it() {
    mkdir -p "$ROOT/.ci/scripts/ci"
    cp "$REPO_ROOT/.ci/scripts/lib/common.sh" "$ROOT/.ci/scripts/lib/"
    printf 'seed\\n' >"$ROOT/seed.txt"
    cat >"$ROOT/here.txt" <<'INNER'
printf 'not a real write\\n' >"$REPO_ROOT/decoy.txt"
INNER
}
"""


def _log_fail(message: str) -> int:
    """`log_fail`: log_error plus exit 1, in one call.

    THE HELPER THAT DID NOT EXIST. See archaeology item 1: all three call sites are anti-vacuity refusals, every one of them was `command not found`, and the gate exited 127 instead of refusing. 127 is not a verdict.
    """
    log.error(message)
    return 1


def get_repo_root() -> pathlib.Path:
    """`get_repo_root` from common.sh: three directories up from `.ci/scripts/lib`.

    Reproduced from the LIBRARY's location rather than the gate's, which is what the bash function does, and which is the same answer as `rediacc_ci.paths.repo_root()` in every tree either can see. `paths` is used so a harness pointing the package at a fixture with $REDIACC_CI_ROOT moves both implementations together.
    """
    return paths.repo_root()


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean, 1 on an unregistered writer or a failed control.

    `--selftest` is intercepted BEFORE any real scan, which is the addition the twin does not have. The twin takes no arguments, so no caller passes it.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    repo_root = get_repo_root()
    gates_dir = pathlib.Path(os.environ.get(GATES_DIR_ENV) or repo_root.joinpath(*GATES_DIR_REL))
    lock = pathlib.Path(os.environ.get(LOCK_ENV) or repo_root.joinpath(*LOCK_REL))

    with tempfile.TemporaryDirectory() as control_name:
        control_dir = pathlib.Path(control_name)
        writer_fixture = control_dir / "test-planted-writer.sh"
        tempsafe_fixture = control_dir / "test-planted-tempsafe.sh"
        writer_fixture.write_text(PLANTED_WRITER, encoding="utf-8")
        tempsafe_fixture.write_text(PLANTED_TEMPSAFE, encoding="utf-8")

        if not scan_file(writer_fixture):
            log.error(
                "CONTROL FAILED: the scanner did not catch a planted real-tree write, so its "
                "verdict on the real battery means nothing"
            )
            return 1
        control_noise = scan_file(tempsafe_fixture)
        if control_noise:
            log.error(
                "CONTROL FAILED: the scanner flagged a planted temp-only writer, so it is not "
                "discriminating and its findings would be noise:"
            )
            print("  %s" % control_noise, file=sys.stderr)
            return 1

    if not lock.is_file():
        return _log_fail(
            "check-pool-writer-safety: gate lock not found at %s; refusing to pass while "
            "measuring nothing" % lock
        )

    registered = registered_writers(lock.read_text(encoding="utf-8", errors="replace"))
    if not registered:
        return _log_fail(
            "check-pool-writer-safety: parsed ZERO mutex tree: writers out of %s; the declaration "
            "shape changed and this gate would pass everything" % lock
        )

    # `shopt -s nullglob; GATE_FILES=("$GATES_DIR"/test-*.sh)`. Sorted, because a
    # bash glob is, and LC_ALL=C makes that bytewise, which Python's sort is too.
    gate_files = sorted(gates_dir.glob("test-*.sh")) if gates_dir.is_dir() else []
    if not gate_files:
        return _log_fail(
            "check-pool-writer-safety: no gate tests found under %s; refusing to report a clean "
            "battery over an empty set" % gates_dir
        )

    registered_set = set(registered)
    lock_rel = _strip_root(str(lock), str(repo_root))

    violations = 0
    for gate_file in gate_files:
        hits = scan_file(gate_file)
        if not hits:
            continue
        if gate_file.name in registered_set:
            continue
        log.error(
            "%s writes into the real tree but declares no mutex tree: resource in %s, so "
            "battery.py schedules it in the pool alongside tests that read the same paths:"
            % (gate_file.name, lock_rel)
        )
        # THE TWIN'S `printf ' %s\n' "$hits"` WITH ONE MULTI-LINE ARGUMENT: only
        # the FIRST line is indented. Carried; see the port notes.
        print("  %s" % hits, file=sys.stderr)
        violations += 1

    if violations > 0:
        log.error(
            "%d unregistered real-tree writer(s). Declare mutex: ['tree:repo'] on each one's "
            "entry in scripts/ci-runner/manifest.ts and regenerate %s, so it runs in the serial "
            "W chain. A write left in the pool does not fail cleanly: it corrupts a concurrent "
            "reader and presents as an unrelated gate going red in a file that parses fine on "
            "the serial re-run." % (violations, lock_rel)
        )
        return 1

    log.info(
        "every real-tree writer among %d gate tests declares a mutex tree: resource (%d declared, "
        "controls fired in both directions, so this verdict is real)"
        % (len(gate_files), len(registered))
    )
    return 0


def _strip_root(path: str, root: str) -> str:
    """`${LOCK#"$REPO_ROOT"/}` -- drop the root prefix, or leave the path alone."""
    prefix = root + "/"
    return path.removeprefix(prefix)


def selftest() -> int:
    """Plant each violation, prove it fires; remove it, prove it does not.

    BOTH DIRECTIONS FOR EVERY RULE the scanner has, because a scanner that flagged everything would satisfy the positive controls perfectly while being useless, and that is the failure the twin's own negative control exists to catch.
    """
    ctl = Controls("pool-writer-safety", floor=24, verbose=True)

    ctl.check(
        "CONTROL: the planted real-tree writer is caught",
        len(scan_text(PLANTED_WRITER, "test-planted-writer.sh")),
        1,
    )
    ctl.check(
        "MIRROR: the planted temp-only writer is NOT caught",
        scan_text(PLANTED_TEMPSAFE, "test-planted-tempsafe.sh"),
        [],
    )

    seed = 'REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"\n'
    tempseed = 'TMP="$(mktemp -d)"\n'

    # -- the taint seeds, all three idioms, and their mirror -----------------
    for label, assign in (
        ("$(cd ... pwd)", 'R="$(cd "$X/.." && pwd)"\n'),
        ("git rev-parse --show-toplevel", 'R="$(git rev-parse --show-toplevel)"\n'),
        ("get_repo_root", 'R="$(get_repo_root)"\n'),
    ):
        ctl.check(
            "SEED: %s taints a variable whatever it is named" % label,
            len(scan_text(assign + 'printf x >"$R/f"\n', "t.sh")),
            1,
        )
    ctl.check(
        "MIRROR: a variable seeded from nothing in particular is not tainted",
        scan_text('R="/some/literal"\nprintf x >"$R/f"\n', "t.sh"),
        [],
    )

    # -- TEMP BEATS REPO, the pair that broke the first draft -----------------
    ctl.check(
        "PROPAGATION: a repo-shaped name built from mktemp is SAFE",
        scan_text(tempseed + 'ROOT="$TMP/repo"\nprintf x >"$ROOT/f"\n', "t.sh"),
        [],
    )
    ctl.check(
        "PROPAGATION: a temp-shaped name built from the repo root is TAINTED",
        len(scan_text(seed + 'TMPISH="$REPO_ROOT/x"\nprintf x >"$TMPISH/f"\n', "t.sh")),
        1,
    )
    ctl.check(
        "PROPAGATION: reassignment to a temp value CLEARS an earlier taint",
        scan_text(seed + 'REPO_ROOT="$(mktemp -d)"\nprintf x >"$REPO_ROOT/f"\n', "t.sh"),
        [],
    )
    # THE ORDER ITSELF, WHICH NEEDS A TARGET NAMING BOTH KINDS OF VARIABLE. Every control above happens to reference exactly one, and `if has_safe` before `if has_taint` versus the reverse gives the SAME answer for those, so none of them pins the rule. Measured 2026-09-06 by planting the swap: all 32 controls and all five recorded shadow rows stayed green. A control that cannot
    # fail is not a control, so this pair is the one that pins it.
    both = tempseed + seed + 'cp "$SRC" "$TMP/${REPO_ROOT}.log"\n'
    ctl.check("ORDER: SAFE beats TAINT when one target names both", scan_text(both, "t.sh"), [])
    ctl.check(
        "MIRROR: the same target with only the TAINTED half IS flagged",
        len(scan_text(seed + 'cp "$SRC" "$X/${REPO_ROOT}.log"\n', "t.sh")),
        1,
    )

    # -- pass 2's write shapes, each with a mirror ---------------------------
    ctl.check(
        "WRITE: a redirect at a tainted target fires",
        len(scan_text(seed + 'echo x >"$REPO_ROOT/f"\n', "t.sh")),
        1,
    )
    ctl.check(
        "WRITE: an APPEND redirect fires too",
        len(scan_text(seed + 'echo x >>"$REPO_ROOT/f"\n', "t.sh")),
        1,
    )
    ctl.check(
        "MIRROR: fd duplication is not a write",
        scan_text(seed + 'echo x 2>&1 >"$T"\n', "t.sh"),
        [],
    )
    ctl.check(
        "MIRROR: an ASCII arrow in a LOG LINE is not a redirect",
        scan_text(seed + 'echo "($before -> $REPO_ROOT)"\n', "t.sh"),
        [],
    )
    ctl.check(
        "MIRROR: input redirection is not a write",
        scan_text(seed + 'read -r x <"$REPO_ROOT/f"\n', "t.sh"),
        [],
    )
    ctl.check(
        "WRITE: cp reports its LAST argument, not its source",
        len(scan_text(seed + 'cp "$SRC" "$REPO_ROOT/f"\n', "t.sh")),
        1,
    )
    ctl.check(
        "MIRROR: cp FROM the repo INTO a temp dir is not a real-tree write",
        scan_text(tempseed + 'cp "$REPO_ROOT/f" "$TMP/f"\n', "t.sh"),
        [],
    )
    ctl.check(
        "WRITE: sed -i reports its last argument",
        len(scan_text(seed + 'sed -i "s/a/b/" "$REPO_ROOT/f"\n', "t.sh")),
        1,
    )
    # The test-installmethods-args.sh:141 shape: a real-tree dir in the REPLACEMENT TEXT while the edited file is a temp copy.
    ctl.check(
        "MIRROR: a repo path in sed's REPLACEMENT is not the file being edited",
        scan_text(tempseed + seed + 'sed -i "s|X|$REPO_ROOT|" "$TMP/f"\n', "t.sh"),
        [],
    )
    ctl.check(
        "WRITE: rm reports EVERY non-flag argument",
        len(scan_text(seed + 'rm -rf "$TMP" "$REPO_ROOT/f"\n', "t.sh")),
        1,
    )
    ctl.check(
        "MIRROR: rm with only temp targets is silent",
        scan_text(tempseed + 'rm -rf "$TMP"\n', "t.sh"),
        [],
    )

    # -- what is NOT code -----------------------------------------------------
    ctl.check(
        "MIRROR: a COMMENT describing a write is not a write",
        scan_text(seed + '# printf x >"$REPO_ROOT/f"\n', "t.sh"),
        [],
    )
    ctl.check(
        "MIRROR: a heredoc BODY is text, not a write",
        scan_text(seed + "cat <<'EOF'\nprintf x >\"$REPO_ROOT/f\"\nEOF\n", "t.sh"),
        [],
    )
    ctl.check(
        "MIRROR: a herestring is not a heredoc, so the line after it is still scanned",
        len(scan_text(seed + 'grep x <<<"$Y"\nprintf x >"$REPO_ROOT/f"\n', "t.sh")),
        1,
    )
    # PASS 1 EXISTS FOR THIS: a function body can textually precede the assignment of the global it uses.
    ctl.check(
        "TWO PASSES: a write above the assignment that taints it is still caught",
        len(scan_text('run() { printf x >"$REPO_ROOT/f"; }\n' + seed, "t.sh")),
        1,
    )

    # -- the registered-writer parser, and its refusals -----------------------
    #
    # RETARGETED 2026-09-09: these cases were bash arrays until battery.py replaced run-all.sh. The subject is now the lock, so the fixtures are JSON, and the two directions that matter are unchanged: a real declaration is read, and every near-miss parses EMPTY so the caller refuses.
    lock_text = json.dumps(
        [
            {
                "id": "gate-test:generate-tag-inputs",
                "run": "bash .ci/scripts/test/gates/test-generate-tag-inputs.sh",
                "mutex": ["tree:repo"],
            },
            {
                "id": "gate-test:age-check",
                "run": ".ci/scripts/test/gates/test-age-check.sh",
                "mutex": ["tree:repo", "npm:install"],
            },
            {
                "id": "gate-test:quiet",
                "run": ".ci/scripts/test/gates/test-quiet.sh",
                "reads": ["tree:repo"],
            },
            {
                "id": "gate-test:free",
                "run": ".ci/scripts/test/gates/test-free.sh",
            },
            {
                "id": "check:elsewhere",
                "run": "npx tsx scripts/gates/check-elsewhere.ts",
                "mutex": ["tree:repo"],
            },
        ]
    )
    ctl.check(
        "PARSE: a mutex tree: declaration registers the gate test",
        registered_writers(lock_text),
        ["test-age-check.sh", "test-generate-tag-inputs.sh"],
    )
    ctl.check(
        "PARSE: the SCRIPT word is taken out of a `run` that is a command line",
        registered_writers(
            '[{"run": "bash -x .ci/scripts/test/gates/test-x.sh --flag", "mutex": ["tree:repo"]}]'
        ),
        ["test-x.sh"],
    )
    # THE ONE-DIRECTIONAL CLAIM STRENGTH. A scanner is released beside other
    # scanners, so `reads` is NOT a writer registration; accepting it would
    # silence exactly the flake this gate exists for.
    ctl.check(
        "PARSE: a `reads` declaration is NOT a writer registration",
        registered_writers('[{"run": ".ci/scripts/test/gates/test-r.sh", "reads": ["tree:repo"]}]'),
        [],
    )
    ctl.check(
        "PARSE: a mutex resource that is not a tree: does not register",
        registered_writers(
            '[{"run": ".ci/scripts/test/gates/test-n.sh", "mutex": ["npm:install"]}]'
        ),
        [],
    )
    ctl.check(
        "PARSE: a NON-gate-test entry with mutex tree: is not a gate test",
        registered_writers('[{"run": "npx tsx scripts/gates/check-x.ts", "mutex": ["tree:repo"]}]'),
        [],
    )
    ctl.check("VACUITY: an empty lock parses empty", registered_writers(""), [])
    ctl.check("VACUITY: unparseable JSON parses empty", registered_writers("{not json"), [])
    ctl.check(
        "VACUITY: a JSON OBJECT rather than a list parses empty", registered_writers("{}"), []
    )
    # THE REAL LOCK IS NOT EMPTY, and this is the case that would have caught the retarget landing against a lock whose shape had moved: every fixture above is synthetic, and a parser that agreed with all of them while reading the live file as empty would look perfect here.
    ctl.check(
        "REAL: the live lock declares at least the four historical writers",
        set(
            registered_writers(
                (paths.repo_root() / "scripts" / "ci-runner" / "gates.lock.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        >= {
            "test-docs-gen.sh",
            "test-gate-anti-vacuity.sh",
            "test-gate-paths-exist.sh",
            "test-generate-tag-inputs.sh",
        },
        True,
    )

    ctl.check("VACUITY: an empty file yields no hits", scan_text("", "t.sh"), [])
    ctl.check(
        "the report names the file and the LINE",
        scan_text(seed + 'echo x >"$REPO_ROOT/f"\n', "t.sh")[0],
        't.sh:2: echo x >"$REPO_ROOT/f"',
    )
    ctl.check("_strip_root drops the prefix", _strip_root("/r/a/b.sh", "/r"), "a/b.sh")
    ctl.check("_strip_root leaves a foreign path alone", _strip_root("/x/b.sh", "/r"), "/x/b.sh")

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
