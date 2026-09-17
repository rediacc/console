"""Under `pipefail`, a locally-defined function piped into `grep -q` is a RACE.

Ported from `.ci/scripts/quality/check-pipefail-grep-q.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live until a differential ledger row exists over K distinct trees. Its gate header registers it as step "No racing pipefail/grep -q detectors", lane quality-code, emit false, and it carries this BLOCKER, which is about WIRING rather than about the defect class, so it stays with the bash file: "runs before this lane's `- id:
setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails."

The twin's `why:` line, which is the one-sentence version: "A detector built as `producer | grep -q` under pipefail cannot reliably fail: grep -q exits at its first match, SIGPIPEs the producer, and pipefail makes that 141 the verdict. check-ci-watch-recipe.sh shipped exactly that in both detectors and certified 124 files clean over a real offender for as long as it existed."

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED WHOLE. Every paragraph below is evidence that cannot be recovered from the code, and a port that summarised it would destroy the only copy.
-----------------------------------------------------------------------------

THE MECHANISM. `grep -q` exits the instant it matches. That closes the pipe, the producer gets SIGPIPE, and its status becomes 141. `set -o pipefail` makes the RIGHTMOST NON-ZERO status the pipeline's status -- so a pipeline that MATCHED reports 141, i.e. false. Whether it happens depends on whether the producer has already written everything into the 64 KB pipe buffer and exited,
which is a
function of output size and machine load. The same code returns different answers
on different days.

WHAT IT COST. `.ci/scripts/quality/check-ci-watch-recipe.sh` had exactly this in both of its detectors:

    hands_out_banned() { advice_only "$1" | grep -qE '<banned>'; }

Measured 2026-08-27 against .claude/hooks/test-hooks.sh, 1,644 lines then (hit at line 692 of the filtered stream): 8/8 trips WITHOUT pipefail, 0/8 WITH it. The gate had been printing "no hand-rolled watch in 124 scanned file(s)" over a real offender, and went red exactly once -- under `npm run ci`'s parallel load, where the timing flipped. Its own four controls could not have
caught it: all of them ran on 2-line fixtures, where the producer finishes long before `grep -q` exits, so the mechanism does not exist at that size.

THE SUBJECT IS THE SIZE, NOT THAT FILE. It was 1,644 lines the day this was measured, 2,774 by 2026-09-09, and it is being ported out of bash into .claude/rediacc_hooks/tests/ -- so the citation is dated on purpose and the large-file control below is what keeps the measurement reproducible after the file it names is gone.

WHY A LOCALLY-DEFINED FUNCTION IS THE TEST, and not "any pipe into grep -q". There are 115 `| grep -q` sites under pipefail in this repo. What makes the shape MOST dangerous is a producer whose output SCALES WITH ITS INPUT -- a function that reads a file, filters a corpus, enumerates a tree. Judging "is the producer a
function this file defines" is a property this gate owns, independent of what the
code claims, which is the trap gates.md warns about: an assertion that re-asks a question the code already answered cannot fire.

THE EXEMPTION BELOW USED TO BE STATED AS SAFETY, AND THAT WAS WRONG. This block previously read "almost all are harmless: `printf '%s' "$x" | grep -q` has a bounded producer that finishes before anything can race". Falsified on 2026-08-31 by CI run 33432878128, job 99628247967:

    .ci/scripts/test/gates/test-run-sh.sh:67
    if printf '%s' "$QA" | grep -q 'return 1'; then

`$QA` is 1129 bytes, far inside the 64 KB pipe buffer, and the match sits on line 23 of ~30. It still raced: the log carries `printf: write error: Broken pipe` and the branch took the else, reporting "quality_all has no failure path" against code whose `return 1` grep had just FOUND. EPIPE does not depend on the buffer filling. It depends on whether `grep -q` has already exited and
CLOSED the read end when the write syscall lands, and that is pure scheduling. A bounded producer is less likely to lose the race, never immune to it.

THE BOUNDED PRODUCERS STOPPED BEING EXEMPT ON 2026-09-16, and the deferral that used to sit here -- "a separate, larger, still-untriaged class" -- was closed by measuring it rather than by arguing about it. The measurement:
`set -uo pipefail; if printf '%s' "$s" | grep -q NEEDLE; ...` with the NEEDLE on
line 1, 40 trials per size, this host::

      payload   printf MISSED   echo MISSED
      1,219 B       0/40           0/40
      8,289 B       0/40           0/40
     16,470 B       0/40            --
     32,832 B       0/40            --
     49,194 B      32/40            --
     61,516 B      40/40            --
     65,556 B      39/40          40/40
    300,078 B      40/40            --

So the shell BUILTINS reproduce the class outright, and the knee sits between 32 KB and 48 KB -- BELOW the nominal 64 KB pipe buffer, because `grep -q` exits after its FIRST READ rather than after the buffer fills. This also re-confirms the 2026-08-31 datum above from the other side: a 1129-byte printf is 0/80 here and still lost the race once in CI under load, so sub-knee is RARE,
not SAFE.

The mechanism differs and the effect does not: a BUILTIN takes EPIPE and returns non-zero, an EXTERNAL producer is SIGPIPE'd to 141, and under `pipefail` both make a pipeline that MATCHED report false. `printf` and `echo` are therefore in SCALING_PRODUCERS, and the eleven sites that widening found across eight files were converted in the same change.

`.claude/oracles/**` IS EXCLUDED FROM THE CORPUS ON PURPOSE and holds eight of the shape. Those files are the FROZEN bash originals for `.claude/rediacc_hooks/guards/block_compacted_plan_edit.py` and
`block_unlinked_commit_author.py`; `.claude/oracles/README.md:49-54` says "They
are FROZEN. Do not fix a bug here; fix it in the port." Nothing registers them,
the live code is Python and has no pipe, so the eight are not defects and must not be converted. Recorded here so the next sweep does not re-derive 47 files and 104 sites and have to work out again why they do not count.

THE PIPEFAIL TEST IS PER-FILE, AND IT IS WRONG IN BOTH DIRECTIONS. It greps the whole file for `set -o pipefail` and cannot see an inner shell's options:

  FALSE POSITIVE -- `.ci/scripts/test/test-install-methods.sh:1129`. The file
  sets `set -euo pipefail` at line 29, but the flagged line lives inside a
  `docker run ... bash -c "..."` whose INNER shell sets `set -e` only (line 1057,
  and the same at 800, 886, 925, 965, 1010, 1097). Without pipefail the pipeline
  reports grep's status and the match stands, so there is no bug at that line.
  Converted regardless: an allowlist entry would be a suppression, which this
  repo forbids, and the conversion is defensively correct the day anyone adds
  `-o pipefail` to those container scripts.

  FALSE NEGATIVE -- `.ci/lib/devbox.sh:1082`, which is the strongest finding the
  2026-09-16 sweep produced. The file sets no pipefail of its own and INHERITS it
  from every sourcer: `scripts/dev/worktree.sh:12`, and `.ci/lib/local-common.sh`
  at 937 and 983, itself sourced by `rdc.sh:11`. It is a live, user-facing
  detector -- `devbox_identity_ok` hunting "dubious ownership" -- and losing the
  race makes it return SUCCESS. INHERITS_PIPEFAIL_PREFIXES below is the narrow
  answer. A general source-graph analyser is not proportionate: measured over
  every tracked shell file that lacks its own pipefail and is sourced by one that
  has it, this is the ONLY such site in the repository.

THE FIX IS ALWAYS THE SAME and is a drop-in: command substitution reads the producer to completion, so there is no signal to race.

    [ -n "$(producer | grep -E '<pattern>')" ]

THREE CAVEATS ON THAT DROP-IN, each paid for by a site in the 2026-09-16 sweep:

  1. KEEP EVERY GREP FLAG EXCEPT `-q`. The spelling above is an EXAMPLE, not the
     rule. `proxy-go-unit.sh:124` was `grep -qx` and became `grep -Fx`;
     `renet .ci/scripts/quality/i18n.sh:229` is `grep -q --` and the `--` is
     load-bearing, because its pattern starts `--- PASS:`.

  2. `[ -n "$(...)" ]` IS NOT EQUIVALENT WHEN THE PATTERN CAN MATCH AN EMPTY
     LINE. Command substitution strips trailing newlines, so a matched empty line
     reads back as no match. Checked against all eleven patterns in that sweep --
     none can match empty -- and recorded here because the next sweep must check
     it again rather than inherit the conclusion.

  3. `set -e` BEHAVIOUR IS UNCHANGED as long as the converted test keeps its
     position in the same `&&`/`||` list. Verify by RUNNING the file, not by
     reading it.

NO BASELINE, deliberately. The class was 13 sites and every one was converted, so this gate stands at zero with an anti-vacuity floor. A baseline here would have recorded ten provably-safe sites as debt and left three real risks sitting in a list that says "known, fine" -- and a stale baseline entry is a slot where the next regression hides.

THE MECHANISM CONTROL ASKS THE OPERATING SYSTEM, not this gate's regex. Everything else here is pattern matching, and pattern matching cannot tell you the mechanism is real on the machine the gate runs on. If SIGPIPE-under-pipefail ever stops flipping the verdict, this gate is guarding a myth and should say so rather than keep passing. THE PRODUCER MUST BE ONE THAT DIES ON SIGPIPE,
and not every command does. Measured on this host (uutils coreutils 0.8.0, ugrep 7.8.4):
`grep -v`, `sed` and `awk` all exhibit the race; `cat` does NOT -- uutils cat
reports success on a 300 KB producer that was killed mid-write. The first draft of this control used `cat` and therefore could not reproduce the very mechanism
the gate exists for; the control refused to pass, which is what caught it.
`grep -v` is used because that is literally what the defect's producer was: `advice_only()` in check-ci-watch-recipe.sh is a `grep -vE`.

THE FIXTURE IS ASSEMBLED AT RUNTIME so this file's own TEXT never carries the racing shape contiguously. Written out literally, the gate flagged its own control fixture -- correctly, by its rule, since the fixture IS the bad shape on purpose. Self-exemption was the wrong answer: a gate that skips its own file stops policing the one script most likely to grow this bug next. The same
runtime-concatenation convention test-hooks.sh uses for banned tokens.

COMMENTS AND STRING LITERALS ARE BOTH STRIPPED FIRST, and the second one was learned the hard way: this gate flagged ITSELF the moment it became a tracked file, because its own message text says "no racing <function> | grep -q ..." and `pass` is a function it defines. Four findings, every one of them prose describing the very bug the gate exists for. That is the
mention-as-execution class, this time inside the gate written to catch a different class -- and its own fixture heredoc (`if producer "$2" | grep -q ...`) is real code that must stay quoted-out too, since it is a CONTROL, not a defect. `sed` blanks quoted spans rather than deleting the line, so line numbers stay honest in the report.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE CORPUS IS `git ls-files`, INVOKED, NOT REIMPLEMENTED. The twin's pathspecs (`.ci/scripts/**/*.sh`, `scripts/**/*.sh`, `.claude/hooks/**/*.sh`) are matched by git's wildmatch, which by default lets `*` cross a `/`. A `pathlib.rglob` rewrite would be a SECOND definition of the corpus and would drift from the twin's the first time a directory moved -- and a corpus that quietly
narrows is precisely the vacuity this gate's own floor exists to catch. It is a subprocess.

THE COLOUR CONDITION IS THE TWIN'S BUG, CARRIED. `[ -t 1 ]` tests STDOUT and `fail()` writes its coloured line to STDERR, which is the 11-file variant `rediacc_ci.log` was written to replace. `rediacc_ci.log` is deliberately NOT used here: it would decide colour from stderr and disable it under CI, so the two implementations would emit different bytes in exactly the environment CI
runs in. Reported as a twin finding instead of repaired.

THE MECHANISM CONTROL IS RUN FOR REAL, in a bash child, with a 300 KB producer. It is the one control that would be worthless as a pure-Python assertion: the whole claim is about what the OPERATING SYSTEM does to a writer whose reader has gone, and Python cannot answer that on bash's behalf. Both implementations therefore spawn the same fixture, and if the host ever stops
reproducing the race BOTH go red together, which is the correct joint behaviour.

THERE ARE TWO OF THEM SINCE 2026-09-16, AND THE SECOND IS NOT A DUPLICATE. The original kills an EXTERNAL producer with SIGPIPE. A BUILTIN reaches the same verdict down a different kernel path: bash traps SIGPIPE for its own builtins, so `printf` does not die -- it takes EPIPE from write(2) and returns non-zero, which `pipefail` promotes to the pipeline's status. Adding
`printf`/`echo` to SCALING_PRODUCERS without `mechanism_builtin_output()` would have left the two builtin controls guarding a claim nothing on the host had confirmed.

THE SED IS THREE SUBSTITUTIONS IN ORDER, per line: strip from the first `#` to end of line, then blank single-quoted spans, then blank double-quoted spans. Order matters -- a `#` inside a string is removed before the string is blanked, which is the twin's behaviour and not obviously right, but changing it would change which lines are findings.

`\\b` AND `[[:space:]]` are written out rather than abbreviated. `\\b` means the
same thing in both engines for ASCII identifiers; `[[:space:]]` does not equal
Python's `\\s`, which additionally matches U+00A0 and U+2028, so the class is spelled literally.

SORT ORDER IS BYTEWISE IN BOTH. The twin pipes function names through `sort -u`
with no locale pinned, and the differential harness exports LC_ALL=C; Python's
`sorted()` on ASCII identifiers is the same order. Named because a locale-aware sort would reorder findings, and while the comparator treats findings as an unordered multiset, a human diffing the two streams would see churn.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The corpus, as git pathspecs. Handed to `git ls-files` verbatim; see the port
# notes for why this is not rewritten as a glob walk. `:(glob)` IS LOAD-BEARING: without it git reads `**` as demanding a slash, so these matched nothing at depth 1 and the corpus silently skipped six tracked shell files. Measured 2026-09-08: 471 before, 477 after. Kept BYTE-EQUAL to the twin's spelling at `check-pipefail-grep-q.sh`, since the shadow ledger compares the two
# verdicts and a corpus difference would read as a behavioural divergence.
#
# THE LAST THREE ROOTS WERE ADDED 2026-09-16 and cost 26 files for two findings, both real: `.ci/lib/devbox.sh:1082` (a silent-miss detector, and the reason `.ci/lib/` is also in INHERITS_PIPEFAIL_PREFIXES) and `.devcontainer/start-kvm.sh:216`, which offended the rule as it stood and was invisible only because nothing looked there. `.ci/media/**` came in with them and
# is clean; it is listed so the next shell script written there is covered rather
# than discovered by the sweep after next.
PATHSPECS = (
    ":(glob).ci/scripts/**/*.sh",
    ":(glob)scripts/**/*.sh",
    ":(glob).claude/hooks/**/*.sh",
    ":(glob).ci/lib/**/*.sh",
    ":(glob).devcontainer/**/*.sh",
    ":(glob).ci/media/**/*.sh",
)

# A SOURCED LIBRARY INHERITS ITS SOURCER'S OPTIONS, and the per-file pipefail test cannot see that. These repo-relative prefixes are treated as pipefail-bearing
# whatever the file itself sets; see the FALSE NEGATIVE note in the docstring. One
# prefix, because one site in the whole repository needs it: building a source-graph analyser for `.ci/lib/devbox.sh:1082` would be the wrong size of answer.
INHERITS_PIPEFAIL_PREFIXES = (".ci/lib/",)

# `grep -qE 'set -[a-z]*o pipefail|set -o pipefail'`. Only a script that actually
# sets pipefail can have the bug; without it the pipeline reports grep's status
# and the match stands.
PIPEFAIL_RE = re.compile(r"set -[a-z]*o pipefail|set -o pipefail")

# A stripped line that ends in `|` is a pipeline continued on the next line.
CONTINUES_RE = re.compile(r"\|[ \t]*$")

# `grep -oE '^[A-Za-z_][A-Za-z0-9_]*\(\)'` -- a function DEFINITION at column one,
# with no space before the parentheses.
FUNCDEF_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)")

# The three sed expressions, in the twin's order. See the port notes.
_STRIP_COMMENT = (re.compile(r"#.*$"), "")
_BLANK_SQUOTE = (re.compile(r"'[^']*'"), "''")
_BLANK_DQUOTE = (re.compile(r'"[^"]*"'), '""')

# POSIX [[:space:]], written out.
_SPACE = r"[ \t\n\v\f\r]"

# The 200-byte pad and 1500 lines of the mechanism fixture: ~300 KB, well past the 64 KB pipe buffer, so the producer BLOCKS and grep -q's early exit kills it. Under the buffer nothing races and the control would silently prove nothing -- which is exactly how the first attempt at a large-file control in check-ci-watch-recipe.sh came out vacuous.
MECH_PAD_WIDTH = 200
MECH_LINES = 1500

# ASSEMBLED AT RUNTIME so this file's own text never carries the racing shape contiguously. See the twin's note, carried in the module docstring.
_GQ = "grep -q"


# PRODUCERS WHOSE OUTPUT SCALES WITH THEIR INPUT, which is the criterion this gate has stated since it was written -- "a function that reads a file, filters a corpus, enumerates a tree". Until 2026-09-16 only the FUNCTION half of that sentence was implemented, so a scaling producer that happened to be a command rather than a local function was invisible.
#
# THAT HOLE WAS LIVE, not theoretical. `check-control-vacuity.sh:81-83` is
#
# grep -vE '<comments>' "$1" | grep -vE '<prefix-sed>' | grep -qE '<subst>'
#
# and it lost the race in 2 of 20 measured runs under suite load, returning 141
# for a file that MATCHED. The effect was not a flaky test: the gate moved that
# file from `checked` to `exempt` and silently stopped checking one of its own controls while still printing a tick. The twin/port differential is the only reason it ever surfaced.
#
# `printf`/`echo` JOINED THIS LIST ON 2026-09-16, when the deferral the docstring used to carry was closed by measurement: both builtins report MISSED 40/40 at 300 KB and the knee is between 32 KB and 48 KB. They are here for the same reason as the commands -- their output scales with what is interpolated into them, which is routinely a captured command's whole stdout -- not
# because "printf" is dangerous.
#
# `tee`/`docker` JOINED ON 2026-09-16 TOO, and they came from the SUBMODULE. The work that gave private/renet its own copy of this detector had to measure which producers renet needed, and the same two names turned out to be missing HERE:
#
# tee -- a PURE PASS-THROUGH. Its output scales exactly with its input, and
#             it is the stage `grep -q` SIGPIPEs. Zero sites in console today; it
# is in the list because the next `cmd | tee log | grep -q` written here should be caught rather than measured afterwards, and because renet's copy must stay a superset of this one. Its renet site (`.ci/scripts/quality/i18n.sh`) lost the race 5/5 at 300 KB AND truncated the tee'd log to 32 bytes -- the very log its failure branch cats.
#
# docker -- `docker ps --format ...` / `docker version -f ...` output scales
#             with the daemon's state, not with a constant. THREE live console
# sites, all of the same shape and all under `.ci/lib/`'s INHERITED pipefail (neither file sets it itself), so all three were invisible twice over -- once for the missing producer name and once for the per-file test: .ci/lib/account.sh:796 teardown of `account-server` .ci/lib/service.sh:156 teardown of four rediacc-service-* containers .ci/lib/service.sh:183 `service status`
# reporting running/not Losing the race SKIPS a container teardown, or reports a running container as absent. A fourth site, `.ci/scripts/private/concurrent-fork-isolation-test.sh:266`, is the known FALSE-POSITIVE direction -- it lives inside an `_ssh "sudo bash -c '...'"` body whose remote shell sets no pipefail (its neighbour at :278 says exactly that in a comment) -- and was
# converted anyway, for the same reason test-install-methods.sh:1129 was: an allowlist entry would be a suppression, and the conversion is defensively correct the day that remote body gains `-o pipefail`. TWO MORE SITES CARRY THE IDENTICAL SHAPE AND ARE NOT THE CLASS: `.ci/scripts/infra/ci-stop.sh:44` and `.ci/scripts/infra/ci-stop-elite.sh:35` are byte-for-byte the same
#             `docker ps -a --format ... | grep -q "^${container}$"`, but both set
# `set -e` ONLY (line 8 of each) and both are EXECUTED as subprocesses, never sourced -- so no sourcer's pipefail reaches them and the pipeline reports grep's status. Checked 2026-09-16 and left alone
#             deliberately; the gate is silent on them by its own rule, and this
# note exists so the next sweep does not re-derive the answer.
#
# ORDER IS THE TWIN'S ORDER (plain ASCII sort), because the twin interpolates this list into a `sort -u` and the two implementations are compared byte for byte.
SCALING_PRODUCERS = (
    "awk",
    "cat",
    "comm",
    "cut",
    "diff",
    "docker",
    "echo",
    "find",
    "git",
    "grep",
    "jq",
    "ls",
    "printf",
    "sed",
    "sort",
    "tail",
    "tee",
    "tr",
    "uniq",
    "xargs",
)


def inherits_pipefail(rel: str | None) -> bool:
    """The twin's `inherits_pipefail`. An EMPTY path is false.

    Fixture controls have no repo-relative identity, so they keep testing the ordinary per-file rule.
    """
    return bool(rel) and str(rel).startswith(INHERITS_PIPEFAIL_PREFIXES)


def strip_code(line: str) -> str:
    """The twin's `sed -e 's/#.*$//' -e "s/'[^']*'/''/g" -e 's/"[^"]*"/""/g'`.

    Blanks rather than deletes, so line numbers in the report stay honest. Exported so `--selftest` can drive the mention-as-execution direction without writing a file.
    """
    for pattern, replacement in (_STRIP_COMMENT, _BLANK_SQUOTE, _BLANK_DQUOTE):
        line = pattern.sub(replacement, line)
    return line


def local_functions(text: str) -> list[str]:
    """`grep -oE '^[A-Za-z_][A-Za-z0-9_]*\\(\\)' | tr -d '()' | sort -u`."""
    names = {match.group(1) for line in text.split("\n") if (match := FUNCDEF_RE.match(line))}
    return sorted(names)


def logical_lines(text: str) -> list[tuple[int, str]]:
    """Stripped lines, with a pipeline that CONTINUES onto the next line joined.

    A pipeline written across several lines was invisible to a per-line regex, and that is precisely how the `check-control-vacuity.sh` offender survived every run of this gate: its three `grep` stages sit on three separate lines, so no single line ever contained both a producer and `grep -q`.

    A line whose stripped text ends in `|` is continued, so it is joined to the one after it with NO separator inserted -- the next line's own leading whitespace is what keeps the tokens apart, and inserting anything here would make the twin and this port disagree byte for byte. The tuple carries the number of the line the pipeline STARTED on, so the report still points at the top
    of the construct rather than at its tail.
    """
    out: list[tuple[int, str]] = []
    start = 0
    buf = ""
    for number, line in enumerate(text.split("\n"), start=1):
        stripped = strip_code(line)
        if not buf:
            start = number
            buf = stripped
        else:
            buf += stripped
        if CONTINUES_RE.search(buf):
            continue
        out.append((start, buf))
        buf = ""
    if buf:
        out.append((start, buf))
    return out


def producer_names(text: str) -> list[str]:
    """The producers worth searching for: this file's own functions, plus commands.

    Both halves are "a producer whose output scales with its input"; the gate has
    always said so and, until 2026-09-16, only implemented the first half.
    """
    return sorted(set(local_functions(text)) | set(SCALING_PRODUCERS))


def offenders_in(text: str, rel: str | None = None) -> list[str]:
    """`offenders <file> [<rel>]` -- one `<line>:<text>` per racing pipeline.

    Empty is clean. `rel` is the REPO-RELATIVE path, used only to ask
    `inherits_pipefail()`; it is None for a fixture, which then takes the ordinary
    per-file test.

    The order is the twin's: producer names in sorted order, and within each name the file's own line order, because the twin runs one `grep -n` per name. A line naming two different producers is therefore reported TWICE, which is real and is preserved.
    """
    if not inherits_pipefail(rel) and not PIPEFAIL_RE.search(text):
        return []
    names = producer_names(text)
    if not names:
        return []
    hits: list[str] = []
    joined = logical_lines(text)
    for name in names:
        # `grep -nE "\b${fn}\b[^|]*\|[[:space:]]*grep -q"` -- the producer, then
        # a pipe, then grep -q, in CODE. `[^|]*` keeps the producer in the stage IMMEDIATELY before the pipe, so `printf x | grep -q` is not dragged in by a `grep` that appears earlier in the same line.
        pattern = re.compile(r"\b%s\b[^|]*\|%s*%s" % (re.escape(name), _SPACE, re.escape(_GQ)))
        for number, line in joined:
            if pattern.search(line):
                hits.append("%d:%s" % (number, line))
    return hits


def offenders(path: pathlib.Path, rel: str | None = None) -> list[str]:
    """`offenders` over a file on disk. An unreadable file is silent, as `2>/dev/null` is."""
    try:
        return offenders_in(path.read_text(encoding="utf-8", errors="replace"), rel)
    except OSError:
        return []


def scan_files(root: pathlib.Path) -> list[str]:
    """`git -C "$ROOT" ls-files <pathspecs> 2>/dev/null`, as repo-relative strings."""
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", *PATHSPECS],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
        check=False,
    )
    return (completed.stdout or "").split("\n")


def _write_big(big: pathlib.Path) -> None:
    """The twin's `{ echo NEEDLE; ...1500 x 200-byte lines... } >"$TMP/big.txt"`.

    ~300 KB, well past the 64 KB pipe buffer, with the NEEDLE on line 1 so the reader exits after its first read while the writer is still going.
    """
    pad = "x" * MECH_PAD_WIDTH
    with big.open("w", encoding="utf-8") as handle:
        handle.write("NEEDLE\n")
        for _ in range(MECH_LINES):
            handle.write(pad + "\n")


def mechanism_output(tmp: pathlib.Path) -> str:
    """Run the SIGPIPE fixture in a real bash child. "MISSED" means the race is live.

    THE ONE CONTROL THAT ASKS THE OPERATING SYSTEM. See the module docstring: a pure-Python assertion here would prove something about Python, and the claim is about what bash and the kernel do to a writer whose reader has exited.
    """
    mech = tmp / "mech.sh"
    mech.write_text(
        "set -uo pipefail\n"
        'producer() { grep -v ZZZ_NEVER_MATCHES "$1"; }\n'
        "if producer \"$2\" | %s 'NEEDLE'; then echo MATCHED; else echo MISSED; fi\n" % _GQ,
        encoding="utf-8",
    )
    big = tmp / "big.txt"
    _write_big(big)
    completed = subprocess.run(
        ["bash", str(mech), "x", str(big)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
        check=False,
    )
    # `mech_out="$(...)"` strips trailing newlines, and the comparison is `=`.
    return (completed.stdout or "").rstrip("\n")


def mechanism_builtin_output(tmp: pathlib.Path) -> str:
    """The BUILTIN half of the mechanism, in a real bash child. "MISSED" means live.

    Not a duplicate of `mechanism_output`: that one proves SIGPIPE kills an EXTERNAL producer, and bash traps SIGPIPE for its own builtins, so `printf` reaches the same verdict by taking EPIPE from write(2) instead. Adding `printf`/`echo` to SCALING_PRODUCERS without this control would leave the two builtin controls guarding a claim nothing on the host had confirmed.

    Re-uses the same ~300 KB `big.txt` the external fixture writes, so the two controls are measured against the identical payload.
    """
    mech = tmp / "mech-builtin.sh"
    mech.write_text(
        "set -uo pipefail\n"
        'payload="$(cat "$1")"\n'
        "if printf '%%s\\n' \"$payload\" | %s 'NEEDLE'; then echo MATCHED; else echo MISSED; fi\n"
        % _GQ,
        encoding="utf-8",
    )
    big = tmp / "big.txt"
    if not big.exists():
        # `main()` always runs the external fixture first, so the twin can simply reuse `$TMP/big.txt`. A caller that drives this function ALONE (pytest does) would otherwise measure an empty payload and report MATCHED -- a vacuous green for the one control that must not have one.
        _write_big(big)
    completed = subprocess.run(
        ["bash", str(mech), str(big)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
        check=False,
    )
    return (completed.stdout or "").rstrip("\n")


class _Report:
    """The twin's `fail` / `pass` pair, colours and streams included.

    THE COLOUR CONDITION IS THE TWIN'S: `[ -t 1 ]` tests STDOUT while `fail`
    writes to STDERR. `rediacc_ci.log` is deliberately not used; see the port
    notes.
    """

    def __init__(self, *, colour: bool | None = None) -> None:
        if colour is None:
            colour = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.red = "\033[0;31m" if colour else ""
        self.green = "\033[0;32m" if colour else ""
        self.nc = "\033[0m" if colour else ""
        self.fails = 0

    def fail(self, message: str) -> None:
        print("%s✗%s %s" % (self.red, self.nc, message), file=sys.stderr)
        self.fails += 1

    def ok(self, message: str) -> None:
        print("%sok%s   %s" % (self.green, self.nc, message))


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean, 1 on any failed control or any racing pipeline.

    `--selftest` is intercepted BEFORE any real scan, which is the addition the twin does not have. The twin takes no arguments, so no caller passes it.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    report = _Report()

    with tempfile.TemporaryDirectory() as tmpname:
        tmp = pathlib.Path(tmpname)

        mech_out = mechanism_output(tmp)
        if mech_out == "MISSED":
            report.ok(
                "control: SIGPIPE under pipefail really does flip a matching pipeline to false"
            )
        else:
            report.fail(
                "CONTROL DID NOT FIRE: a matching `producer | grep -q` reported '%s' on a 300 KB "
                "producer. The mechanism this gate exists for did not reproduce, so its green "
                "means nothing here." % mech_out
            )

        # THE SECOND MECHANISM CONTROL, AND IT IS NOT A DUPLICATE OF THE FIRST. See the docstring: a builtin does not die of SIGPIPE, it takes EPIPE.
        mech_builtin_out = mechanism_builtin_output(tmp)
        if mech_builtin_out == "MISSED":
            report.ok(
                "control: a BUILTIN producer takes EPIPE under pipefail and flips a matching "
                "pipeline to false"
            )
        else:
            report.fail(
                "CONTROL DID NOT FIRE: a matching `printf | grep -q` reported '%s' on a 300 KB "
                "payload. The builtin EPIPE path did not reproduce, so the printf/echo half of "
                "this gate is guarding a myth here." % mech_builtin_out
            )

        bad = 'set -o pipefail\nbody() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % _GQ
        if offenders_in(bad):
            report.ok("control: a local function piped into grep -q is detected")
        else:
            report.fail("CONTROL DID NOT FIRE: the racing shape went undetected")

        fixed = (
            'set -o pipefail\nbody() { cat "$1"; }\nif [ -n "$(body "$1" | grep x)" ]; then :; fi\n'
        )
        if not offenders_in(fixed):
            report.ok("control: the command-substitution form is NOT flagged")
        else:
            report.fail("GATE IS OVER-BROAD: the sanctioned fix was flagged")

        # THE BUILTIN HALF, ADDED 2026-09-16. These four controls used to be ONE control asserting the OPPOSITE -- "a bounded producer (printf, not a local function) is not flagged" -- which is why they are spelled out rather than folded into the command-producer pair below: the inversion is the change, and a reader diffing this file should see it stated.
        builtin_printf = 'set -o pipefail\nif printf "%%s" "$x" | %s y; then :; fi\n' % _GQ
        if offenders_in(builtin_printf):
            report.ok("control: a BUILTIN producer (printf) piped into grep -q is detected")
        else:
            report.fail("CONTROL DID NOT FIRE: a builtin printf producer raced and went undetected")

        printf_fixed = 'set -o pipefail\nif [ -n "$(printf "%s" "$x" | grep y)" ]; then :; fi\n'
        if not offenders_in(printf_fixed):
            report.ok("control: the command-substitution form of printf is NOT flagged")
        else:
            report.fail("GATE IS OVER-BROAD: the sanctioned fix for a printf producer was flagged")

        builtin_echo = 'set -o pipefail\nif echo "$x" | %s y; then :; fi\n' % _GQ
        if offenders_in(builtin_echo):
            report.ok("control: a BUILTIN producer (echo) piped into grep -q is detected")
        else:
            report.fail("CONTROL DID NOT FIRE: a builtin echo producer raced and went undetected")

        echo_fixed = 'set -o pipefail\nif [ -n "$(echo "$x" | grep y)" ]; then :; fi\n'
        if not offenders_in(echo_fixed):
            report.ok("control: the command-substitution form of echo is NOT flagged")
        else:
            report.fail("GATE IS OVER-BROAD: the sanctioned fix for an echo producer was flagged")

        # INHERITED PIPEFAIL, both directions. The SAME bytes are classified twice, once under a repo-relative path inside INHERITS_PIPEFAIL_PREFIXES and once outside it, so the control cannot pass by accident of the file's own content: the content is identical and only the path differs.
        inherited = (
            'lib_detect() { git -C "$1" status --porcelain; }\n'
            'if printf "%%s" "$out" | %s dubious; then :; fi\n' % _GQ
        )
        if offenders_in(inherited, ".ci/lib/inherited.sh"):
            report.ok("control: a file under .ci/lib/ with no pipefail of its OWN is still scanned")
        else:
            report.fail(
                "CONTROL DID NOT FIRE: .ci/lib/devbox.sh:1082 is exactly this shape and would be "
                "invisible again"
            )
        if not offenders_in(inherited, "scripts/dev/inherited.sh"):
            report.ok("control: the same bytes OUTSIDE the inheriting prefixes are not flagged")
        else:
            report.fail(
                "GATE IS OVER-BROAD: a file that never sets pipefail was flagged on its path alone"
            )

        # THE TWO CASES THE 2026-09-16 WIDENING ADDED. Each had a live offender in this repo and neither could be seen before, so each gets a control that fails if the widening is ever reverted or regressed.
        cmdprod = 'set -o pipefail\nif grep -vE "^x" "$1" | %s needle; then :; fi\n' % _GQ
        if offenders_in(cmdprod):
            report.ok("control: a scaling COMMAND producer piped into grep -q is detected")
        else:
            report.fail("CONTROL DID NOT FIRE: a command producer raced and went undetected")

        # check-control-vacuity.sh:81-83 in miniature: no single LINE holds both the producer and grep -q, which is why a per-line regex never saw it.
        multiline = 'set -o pipefail\ngrep -vE "^x" "$1" |\n    %sE needle\n' % _GQ
        if offenders_in(multiline):
            report.ok("control: a pipeline SPANNING LINES is detected")
        else:
            report.fail("CONTROL DID NOT FIRE: a multi-line racing pipeline went undetected")

        # THE `tee` AND `docker` CASES, FROM THE SAME 2026-09-16 WIDENING, and here
        # for the same reason as the pair above: a widening whose revert is silent
        # is a widening that will be reverted. `docker` had THREE live offenders in
        # this repo, all under `.ci/lib/`'s inherited pipefail; `tee` had none here
        # and one in private/renet, whose copy of this gate must stay a SUPERSET of this list, so losing `tee` here would also un-pin it there.
        teeprod = 'set -o pipefail\nif cmd 2>&1 | tee "$LOG" | %s ok; then :; fi\n' % _GQ
        if offenders_in(teeprod):
            report.ok("control: a `tee` pass-through piped into grep -q is detected")
        else:
            report.fail(
                "CONTROL DID NOT FIRE: `tee` has fallen out of SCALING_PRODUCERS, and a pure "
                "pass-through producer is invisible again"
            )

        dockerprod = (
            'set -o pipefail\nif docker ps -a --format "{{.Names}}" | %s "^x$"; then :; fi\n' % _GQ
        )
        if offenders_in(dockerprod):
            report.ok("control: a `docker` producer piped into grep -q is detected")
        else:
            report.fail(
                "CONTROL DID NOT FIRE: `docker` has fallen out of SCALING_PRODUCERS, and "
                ".ci/lib/account.sh:796 plus both .ci/lib/service.sh sites are invisible again"
            )

        nopipefail = 'body() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % _GQ
        if not offenders_in(nopipefail):
            report.ok("control: without pipefail the same shape is harmless and not flagged")
        else:
            report.fail("GATE IS OVER-BROAD: flagged a file that never sets pipefail")

        comment = 'set -o pipefail\nbody() { cat "$1"; }\n# never write: body "$1" | %s x\n' % _GQ
        if not offenders_in(comment):
            report.ok("control: prose describing the shape is not committing it")
        else:
            report.fail(
                "GATE IS OVER-BROAD: a COMMENT naming the shape was read as code -- the "
                "mention-as-execution class"
            )

        # ---- the real tree ----------------------------------------------------
        scanned = 0
        found: list[str] = []
        for rel in scan_files(root):
            if not rel:
                continue
            target = root / rel
            if not target.is_file():
                continue
            scanned += 1
            found.extend("%s:%s" % (rel, hit) for hit in offenders(target, rel))

        # ANTI-VACUITY: scanning nothing must FAIL, never pass quietly.
        if scanned == 0:
            report.fail(
                "scanned ZERO files -- the pathspec matched nothing, so a green here would "
                "mean nothing"
            )
        elif not found:
            report.ok(
                "no racing `producer | grep -q` under pipefail in %d scanned file(s)" % scanned
            )
        else:
            report.fail(
                "%d racing pipeline(s): a producer piped into grep -q under pipefail" % len(found)
            )
            # `printf '    %s\n' "${found[@]}"` -- an ARRAY, so the format is
            # reused per element and every line carries the four-space indent.
            for hit in found:
                print("    %s" % hit, file=sys.stderr)
            print(file=sys.stderr)
            print(
                "  grep -q exits at its first match and SIGPIPEs the producer; pipefail then",
                file=sys.stderr,
            )
            print(
                "  makes that 141 the pipeline's status, so a pipeline that MATCHED reports",
                file=sys.stderr,
            )
            print(
                "  false. It only bites once the producer outruns the 64 KB pipe buffer, so",
                file=sys.stderr,
            )
            print("  it passes on small inputs and flips under load.", file=sys.stderr)
            print(file=sys.stderr)
            print(
                """  Fix, a drop-in:  [ -n "$(producer | grep -E '<pattern>')" ]""", file=sys.stderr
            )

        print()
        if report.fails == 0:
            print("%s✓%s pipefail/grep -q: %d file(s) clean." % (report.green, report.nc, scanned))
            print("  Blind spot, stated so the green is not read as more than it is: this sees")
            print("  producers that SCALE with their input -- this file's own functions, and")
            print("  the commands and builtins in SCALING_PRODUCERS, which since 2026-09-16")
            print("  includes printf, echo, tee and docker. What it still cannot see is an INNER")
            print("  shell's options: the pipefail test is per-FILE, so a docker/ssh heredoc that")
            print("  sets only 'set -e' reads as pipefail-bearing, and a sourced library reads as")
            print("  clean unless its prefix is in INHERITS_PIPEFAIL_PREFIXES.")
            return 0
        print("%s✗%s pipefail/grep -q: %d failure(s)." % (report.red, report.nc, report.fails))
        return 1


def selftest() -> int:
    """Plant each violation, prove it fires; remove it, prove it does not.

    BOTH DIRECTIONS FOR EVERY CONTROL. The twin's own five fixture controls are re-asserted here against `offenders_in` directly, plus the shapes the twin does not cover: two functions on one line, a line number that survives quoting, and the empty corpus.
    """
    # FLOOR 26, raised from 18 when the 2026-09-16 builtin widening added five controls (a printf pair, an echo pair, and the inherited-pipefail pair, less the one inverted mirror it replaced). The floor is the only thing that catches controls that stopped EXECUTING, so it tracks the real count rather than sitting comfortably below it.
    ctl = Controls("pipefail-grep-q", floor=26, verbose=True)

    bad = 'set -o pipefail\nbody() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % _GQ
    ctl.check("CONTROL: the racing shape is detected", len(offenders_in(bad)), 1)
    ctl.check("...and it is reported at the RIGHT line", offenders_in(bad)[0].split(":")[0], "3")

    ctl.check(
        "MIRROR: the command-substitution fix is not flagged",
        offenders_in(
            'set -o pipefail\nbody() { cat "$1"; }\nif [ -n "$(body "$1" | grep x)" ]; then :; fi\n'
        ),
        [],
    )
    # INVERTED 2026-09-16. This used to read "MIRROR: a bounded builtin producer is not flagged" and assert []. The builtins are in SCALING_PRODUCERS now, so the
    # old assertion is the exact opposite of the shipped rule; keeping it would have
    # made the port and the twin disagree at the first run.
    ctl.check(
        "CONTROL: a builtin producer (printf) is detected",
        len(offenders_in('set -o pipefail\nif printf "%%s" "$x" | %s y; then :; fi\n' % _GQ)),
        1,
    )
    ctl.check(
        "MIRROR: the command-substitution form of printf is not flagged",
        offenders_in('set -o pipefail\nif [ -n "$(printf "%s" "$x" | grep y)" ]; then :; fi\n'),
        [],
    )
    ctl.check(
        "CONTROL: a builtin producer (echo) is detected",
        len(offenders_in('set -o pipefail\nif echo "$x" | %s y; then :; fi\n' % _GQ)),
        1,
    )
    ctl.check(
        "MIRROR: the command-substitution form of echo is not flagged",
        offenders_in('set -o pipefail\nif [ -n "$(echo "$x" | grep y)" ]; then :; fi\n'),
        [],
    )

    # INHERITED PIPEFAIL: identical bytes, classified by PATH alone. `.ci/lib/` files set no pipefail of their own and get it from every sourcer, which is how `.ci/lib/devbox.sh:1082` stayed invisible.
    _inherited = (
        'lib_detect() { git -C "$1" status --porcelain; }\n'
        'if printf "%%s" "$out" | %s dubious; then :; fi\n' % _GQ
    )
    ctl.check(
        "CONTROL: a .ci/lib/ file with no pipefail of its own IS scanned",
        len(offenders_in(_inherited, ".ci/lib/inherited.sh")),
        1,
    )
    ctl.check(
        "MIRROR: the same bytes elsewhere, with no pipefail, are not",
        offenders_in(_inherited, "scripts/dev/inherited.sh"),
        [],
    )
    # THE 2026-09-16 `tee`/`docker` WIDENING, driven here as well as in main() so a revert reds the selftest too rather than only the live run.
    ctl.check(
        "CONTROL: a `tee` pass-through producer is detected",
        len(offenders_in('set -o pipefail\nif cmd 2>&1 | tee "$LOG" | %s ok; then :; fi\n' % _GQ)),
        1,
    )
    ctl.check(
        "CONTROL: a `docker` producer is detected",
        len(
            offenders_in(
                'set -o pipefail\nif docker ps -a --format "{{.Names}}" | %s "^x$"; then :; fi\n'
                % _GQ
            )
        ),
        1,
    )
    ctl.check(
        "MIRROR: without pipefail the same shape is harmless",
        offenders_in('body() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % _GQ),
        [],
    )
    ctl.check(
        "MIRROR: a COMMENT naming the shape is not committing it",
        offenders_in(
            'set -o pipefail\nbody() { cat "$1"; }\n# never write: body "$1" | %s x\n' % _GQ
        ),
        [],
    )
    # THE ONE THAT COST THIS GATE ITS FIRST GREEN: its own message text names a
    # function it defines, inside a string literal.
    ctl.check(
        "MIRROR: the shape inside a STRING LITERAL is prose, not code",
        offenders_in(
            'set -o pipefail\npass() { echo "$*"; }\necho "no racing pass | %s here"\n' % _GQ
        ),
        [],
    )

    ctl.check(
        "VACUITY: a file defining no function cannot offend",
        offenders_in("set -o pipefail\nif x | %s y; then :; fi\n" % _GQ),
        [],
    )
    ctl.check("VACUITY: an empty file is clean", offenders_in(""), [])

    # `pipefail` spellings the twin's alternation accepts.
    for spelling in ("set -o pipefail", "set -euo pipefail", "set -uo pipefail"):
        ctl.check(
            "CONTROL: `%s` counts as setting pipefail" % spelling,
            len(
                offenders_in(
                    '%s\nbody() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % (spelling, _GQ)
                )
            ),
            1,
        )

    # The stripper, in both directions.
    ctl.check("strip: a comment is removed", strip_code("code # body | %s x" % _GQ), "code ")
    ctl.check("strip: a single-quoted span is blanked", strip_code("a 'b c' d"), "a '' d")
    ctl.check("strip: a double-quoted span is blanked", strip_code('a "b c" d'), 'a "" d')
    ctl.check(
        "strip: unquoted code survives untouched", strip_code("body | grep x"), "body | grep x"
    )

    # Function-name extraction, both directions.
    ctl.check("funcs: a definition at column one is found", local_functions("body() {\n"), ["body"])
    ctl.check("funcs: an INDENTED definition is not", local_functions("  body() {\n"), [])
    ctl.check(
        "funcs: a space before the parens is not the shape", local_functions("body () {\n"), []
    )
    ctl.check(
        "funcs: names come back sorted and unique",
        local_functions("zed() {\nabe() {\nzed() {\n"),
        ["abe", "zed"],
    )

    # A line naming two local functions is reported twice, once per name. Pinned because it looks like a duplicate-suppression bug and is the twin's shape.
    two = "set -o pipefail\nabe() { :; }\nzed() { :; }\nif abe zed | %s x; then :; fi\n" % _GQ
    ctl.check("a line naming TWO local functions is reported twice", len(offenders_in(two)), 2)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
