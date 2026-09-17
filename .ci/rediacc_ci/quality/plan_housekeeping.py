"""A plan file nobody has touched for delete_days must be dealt with.

Ported from `.ci/scripts/quality/check-plan-housekeeping.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live until W7
phase 5.

-----------------------------------------------------------------------------
THE TWIN'S ARCHAEOLOGY, CARRIED. This is the half of a port that cannot be
recovered from the code, so it is transliterated rather than summarised.
-----------------------------------------------------------------------------

`check:ci-plan-housekeeping` -- a plan file nobody has touched for delete_days
must be dealt with, and the gate says the exact date each one goes red.

The operator: "let's also add another quality check for housekeeping of old plan
files! If a plan file is older than 33 days, then CI should complain until
someone deletes them from the branch."

WHY THE INSTRUMENT IS `git log`, AND WHY THAT ALMOST MADE THIS VACUOUS. mtime is
wrong: a clone or a checkout rewrites it, so the gate would answer differently on
every machine. But the obvious replacement is wrong HERE in a way that fails
GREEN, which is worse. Measured on this checkout:

    $ git rev-parse --is-shallow-repository
    true
    $ git log -1 --format=%cI -- agent/PLAN-cold-path.md
    2026-09-01T14:25:23+02:00     # the GRAFT commit, not the file's

Every one of the 70 tracked plans reports one day old, because `git log` on a
shallow clone attributes each file to the graft boundary. A gate built on that is
not merely inaccurate, it is a gate that CANNOT FAIL, and it would report a
confident "none over 33 days" forever. `check_git_history_depth.py:6` already
documents the class. So a shallow checkout is REFUSED here, not answered.

WHY LAST-COMMIT AND NOT ADDED-DATE. The operator's words are "old plan files ...
until someone deletes them", which describes a file that has been SITTING there.
A plan edited yesterday is being worked on. And the property that dissolves the
hard case: a plan genuinely being executed is being EDITED, an edit is a COMMIT,
and a commit resets the clock. So the instrument auto-exempts every actually
active plan against an oracle nobody can forge by typing a word in a Status
header, which is why `Status: executing` buys nothing here.

%cI AND NOT %aI, measured: author and committer dates diverge on 735 of 4001
commits in this repo with a maximum skew of 21.5 days, which is 65% of the
window. %cI answers "when did this file, in its current form, enter the branch".
It errs lenient (a rebase makes a file look fresher, never staler), which is the
safe direction for a gate whose false positive deletes a document somebody needs.

THE NUMBERS LIVE IN `.ci/config/plan-lifecycle.json` and are NOT inlined here,
because `check_plan_boxes.py`'s A5 refuses a deletion this gate demands unless
the same threshold is crossed. Two copies of `33` is a deadlock.

W12: THE REMEDY IS NO LONGER "DELETE IT", AND THAT WORD IS GONE ON PURPOSE. The
operator's standing rule is that nothing is deleted, so this gate spent its whole
life demanding an act nobody was allowed to perform, and the only escape was the
allowlist, which is a suppression rather than an answer. The third door is
COMPACTION: `worklist.py --plan-compact` replaces a finished plan with an
attested record that KEEPS ITS OWN PATH, so every citation still resolves, while
the full text moves into a git blob (content-addressed, so `gh pr merge --rebase`
cannot break the pointer; measured 2026-09-06, 37 of 71 commit-shaped tokens
already cited in plans no longer resolve).

A `Status: compacted` plan whose `Full-Text-Blob:` RESOLVES is exempt here and
counted separately. The resolution test is the whole exemption: a record whose
blob is missing is worse than the deleted plan it replaced, because it advertises
a recovery command that silently returns nothing, so it is reported as an OFFENDER
rather than waved through on the strength of its own header word.
`Status: parked` -- a plan whose text is compacted while its work is NOT finished
-- stays on the clock. Parking buys a smaller file, never an exemption.

The pointer itself is checked in depth by `check:ci-plan-record`, which needs
fetch-depth 0 and the PR head ref. This gate only asks "does the blob exist",
which is the cheap half and the half that decides the exemption.

Exit 1 on any offender or on a refusal, 2 on setup error.

CONTROL FIRST. The age arithmetic is the whole gate, so it is proven on synthetic
input in BOTH directions before the real tree is judged: an over-age date must be
reported and an under-age one must not. Without the second, a function returning
"too old" for everything would look identical to a real finding.

THE COMPACTION CONTROLS RUN BOTH DIRECTIONS TOO. The exemption is the only thing
in this gate that can turn a red into a green, so a broken extractor would
silently exempt nothing (noisy, survivable) or, far worse, a broken
`blob_is_real` would exempt every plan carrying the word `compacted`.

THE CONTROL IS HERMETIC, and two rejected alternatives are why. `git hash-object`
without `-w` computes an id and writes nothing, so `cat-file -t` misses and the
control fails for the wrong reason. Reading a blob out of HEAD's tree works in
this repository and FAILS IN AN EMPTY FIXTURE -- measured: it turned the
gate-test's "an empty tree must fail" case from exit 1 into exit 2, which is the
case that proves `PLAN_HK_ROOT` is not an escape hatch. So the control mints its
own blob in a scratch repository it throws away. Nothing is written to the
repository being judged, and the control holds whatever state that repository is
in, which is the property a control needs most.

`record_blob` IS ANCHORED AT END OF LINE, matching `wl_planrec.FULLTEXT_BLOB_RE`.
A trailing `.*` accepted `Full-Text-Blob: <41 hex>` by reading the first 40
characters of it, so a value the strict gate REJECTS would have been exempted
here; two readers of one header disagreeing is how a plan ends up exempt in one
place and red in the other.

`record_status` READS THE SAME 10-LINE WINDOW every status regex in this repo
reads (`wl_checks.PLAN_HEADER_LINES`). The general status extractor below
deliberately scans the whole file -- it is for DISPLAY and some plans put their
header low -- but this one decides an EXEMPTION, so it must agree with
`wl_planrec.parse` exactly. Otherwise a plan whose prose quotes
`Status: compacted` routes into the compacted branch and is reported as an
offender regardless of its age.

THE SHALLOW REFUSAL. This is the one that stops the gate being a comment. HARD in
CI because the answer would be wrong there; locally a LOUD skip of the age verdict
only, so the floor and the allowlist checks still run and a partial run stays
distinguishable from a clean one.

`git rev-parse --is-shallow-repository` IS NOT THE TEST, and believing it cost a
CI round. It answers on the EXISTENCE of `.git/shallow`, and `git fetch
--unshallow` against a partial clone (`--filter=blob:none`, which every
fetch-depth: 0 checkout in this repo uses) leaves that file behind EMPTY. So on
2026-09-03 job 100500447167 unshallowed successfully at 02:28:52 -- the log shows
every branch and tag arriving -- and this gate still refused at 02:33:39, in the
very lane its own error message names as the correct one. A gate that cannot pass
in the job it tells you to use is indistinguishable from a broken gate.

THE SHALLOW REFUSAL IS MEASURED AGAINST THE PLANS, not against the repository.
Third iteration, because the first two asked the wrong question:

  1. `git rev-parse --is-shallow-repository` alone. It answers on the EXISTENCE
     of `.git/shallow`, which `git fetch --unshallow` can leave behind empty.
  2. "any graft at all". Correct but far too wide: CI job 100507628220 measured
     90 commits reachable and 1 graft, and refused -- in the lane its own error
     message recommends -- while every plan file's history was entirely present.
     `agent/` has only been a tracked directory since 2026-08-18, so nothing in
     this corpus is older than the boundary.

A graft only corrupts THIS gate when a plan's last commit IS the boundary,
because that is the case where `git log -1` reports the graft's date instead of
the file's. So it asks exactly that, per plan. A deepened clone that contains
every plan's history answers correctly and is allowed to.

THE CORPUS is tracked-only and non-recursive, which is exactly the Stop hook's
own glob (`wl_store.agent_plan_dir` -> `agent_root`, `d.glob("PLAN-*.md")`). If
the gate and the hook disagreed about what a plan file IS, one of them would be
enforcing a rule about a set the other cannot see. Non-recursive also excludes
the archive, which is the SUCCESSFUL outcome of housekeeping.

THE FLOOR was measured 2026-09-03: 70 tracked plans, and 30 is well under it on
purpose. It guards against the glob losing the corpus, not against ordinary
housekeeping.

THE ALLOWLIST'S THREE LIVENESS RULES. Every entry must NAME something, must
actually be suppressing something, and dies on its own stated date. Rule three
alone is what stops this becoming a dumping ground: an entry cannot outlive the
argument for it without being re-argued.

A BROKEN RECORD IS STILL ALLOWLISTABLE. The first cut reported it and skipped
past the allowlist branch, so remedy step 3 did not work for the one case where a
session might genuinely need it (a blob this checkout does not have yet, e.g.
mid-rebase or a partial clone), and that plan's allowlist entry was never
liveness-checked either. An unexpired entry suppresses it; an expired one does
not.

THE COMPACTION EXEMPTION IS CHECKED BEFORE THE ALLOWLIST and before the age
thresholds, because a compacted record is not being suppressed and is not waiting
for a date: it has already been dealt with, and the age of a record is not a
defect. `parked` deliberately does NOT appear there; its work is unfinished, so it
falls through to the ordinary clock. The allowlist's third liveness rule reaches a
compacted plan only from that branch, because compaction is a BETTER exemption
than a dated suppression, so an entry that survives it is dead weight with an
expiry date, and dead weight in a suppression file is how that file becomes a
dumping ground.

ONE PYTHON START FOR THE WHOLE CORPUS, not two per plan. The twin's first cut
spawned `age_days` and a red-on date per file; on a 70-plan tree that is 140
interpreter starts, and `check:ci-gate-manifest` caught the selftest at 33.5s
because of it. The dates come out of a single `git log` per file (unavoidable)
and one batch conversion, which took the gate-test from 33.5s to under a second.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE BATCH-CONVERSION OPTIMISATION IS THE ONE PIECE OF THE TWIN THAT DISAPPEARS
ENTIRELY, and it is written down above precisely because it disappears. The twin
shells out to `python3` for every date; this module IS Python, so there is no
interpreter to start and the shape that cost 33.5 seconds cannot recur. A reader
who deletes the paragraph will not know why the twin looked the way it did.

`is_shallow()` IS NOT PORTED, BECAUSE IT IS DEAD IN THE TWIN. It is defined at
`check-plan-housekeeping.sh:275` and called nowhere: the live logic reads
`GRAFTS_FILE` directly, per plan, which is the third iteration described above.
Porting it would import dead code into a new language; deleting it silently would
lose the reasoning, which is why the reasoning is above and the function is not.
Reported as a finding against the twin.

THE CONTROLS RUN INLINE ON EVERY INVOCATION, exactly as the twin's do, and they
print their two `✓ control:` lines to STDOUT on success. `--selftest` is an
ADDITION on top.

`[[ -z "${line// /}" ]]` STRIPS SPACES ONLY, not tabs, so a tab-only line in the
allowlist is NOT blank to the twin and falls through to the entry branch, where
`read -r expiry path` gives an empty path and it is reported as a malformed
entry. Reproduced with `line.replace(" ", "")` rather than `line.strip()`,
because the two differ on exactly that line and a fixture full of spaces would
never show it.

`read -r expiry path <<<"$line"` USES THE DEFAULT IFS, so it splits on spaces AND
tabs, and `path` takes the remainder with leading whitespace removed. A path
containing a space therefore keeps it. `split(maxsplit=1)` is the same rule.

THE DATE COMPARISON IS A STRING COMPARISON in the twin (`[[ "$TODAY" > "$exp" ]]`)
and it is a string comparison here. Both are correct for ISO-8601 and both are
wrong in the same way for anything else, which is the property that matters:
an allowlist carrying `2026-1-5` sorts as later than `2026-12-01` on BOTH sides.

EXIT CODES ARE UNCHANGED: 0 clean, 1 offender or refusal, 2 setup error.
"""

import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import gitx, paths
from rediacc_ci.controls import Controls
from rediacc_ci.policy_paths import policy_rel

# The environment seams, all of which the gate-test drives.
ROOT_ENV = "PLAN_HK_ROOT"
CONFIG_ENV = "PLAN_HK_CONFIG"
ALLOWLIST_ENV = "PLAN_HK_ALLOWLIST"
MIN_FILES_ENV = "PLAN_HK_MIN_FILES"

DEFAULT_CONFIG_REL = ".ci/config/plan-lifecycle.json"
# THROUGH THE SEAM (W4 P4a). `.ci/config/` above is configuration and joins
# normally; the allowlist is POLICY, and every reader of a policy file goes
# through `rediacc_ci.policy_paths` so that the directory is written down once.
DEFAULT_ALLOWLIST_REL = policy_rel(".plan-housekeeping-allowlist")

# Floor. Measured 2026-09-03: 70 tracked plans. Well under it on purpose.
DEFAULT_MIN_PLANS = 30

# The header window every status regex in this repo reads (`wl_checks.PLAN_HEADER_LINES`).
HEADER_LINES = 10

# A BLOCKER reason shorter than this is not substantive. The twin's own number, and note it is NOT the 30 that `blocker-validator.sh` uses: this gate parses its allowlist itself, with a stricter bar, because an entry here suppresses a clock rather than a finding.
MIN_REASON_LENGTH = 40

# The escapes, and the CI test that empties them. `common.sh` is not sourced by
# this gate; it sets its own, so the condition is the twin's own `CI == "true"`
# rather than the tty test the rest of the tree uses.
_RED = "\033[0;31m"
_GREEN = "\033[0;32m"
_YEL = "\033[0;33m"
_NC = "\033[0m"

# The sentinel `age_days` prints for a date it cannot read. Callers must not treat it as an age.
UNPARSEABLE = -1


def _colours() -> tuple[str, str, str, str]:
    if os.environ.get("CI", "") == "true":
        return "", "", "", ""
    return _RED, _GREEN, _YEL, _NC


# --------------------------------------------------------------------------- The three extractors the controls drive ---------------------------------------------------------------------------


def age_days(value: str, now: dt.datetime | None = None) -> int:
    """Whole days since `value`, or UNPARSEABLE for a date that will not read.

    A naive timestamp is read as UTC, which is what the twin's
    `then.replace(tzinfo=dt.UTC)` does.
    """
    try:
        then = dt.datetime.fromisoformat(value)
    except ValueError:
        return UNPARSEABLE
    if then.tzinfo is None:
        then = then.replace(tzinfo=dt.UTC)
    moment = dt.datetime.now(dt.UTC) if now is None else now
    return (moment - then).days


_BLOB_RE = re.compile(r"^Full-Text-Blob:[ \t]*([0-9a-f]{40})[ \t]*$")

# W12 P3.3. THE RECORD-STATUS VOCABULARY IS CONFIG, NOT A LITERAL HERE.
#
# It used to be `re.compile(r"^Status:[ \t]*(compacted|parked)[ \t]*$")`, and the bash twin carried the same alternation in a sed program, and the twin test carried a third copy of that sed verbatim. Three copies of one vocabulary: adding a state means finding all three, and missing one makes a plan a RECORD in one reader and an OFFENDER in the other, which is precisely the
# disagreement `record_status`'s own docstring warns about one screen below.
#
# THE CONFIG IS A MIRROR, NOT THE ORIGIN. `wl_planrec.RECORD_STATES` (`.claude/hooks/stop/wl_planrec.py:155`) is canonical, and `.ci/scripts/quality/check_plan_record.py` imports it by name. This gate cannot: it must stay runnable in a checkout with no `.claude/`, which is the whole reason it reads a config file. So the mirror is compared against the origin in
# BOTH directions by `test_quality_plan_housekeeping.py`; a mirror nobody
# compares is just a fourth copy.
DEFAULT_RECORD_STATES = ("compacted", "parked")
_STATUS_RE_CACHE: dict[tuple[str, ...], re.Pattern[str]] = {}


def record_states(config: pathlib.Path | None = None) -> tuple[str, ...]:
    """The `Status:` words that mark a compaction record, from the config.

    Returns () when the config cannot be read or the key is missing. THAT IS THE
    SAFE DIRECTION and it is deliberate: with no vocabulary nothing is a record,
    so nothing is exempt and every aged plan stays ON the clock. The opposite
    default would exempt plans because a file failed to parse, which is a green
    that means nothing. `main()` refuses up front rather than relying on it.
    """
    path = config or pathlib.Path(
        os.environ.get(CONFIG_ENV) or (pathlib.Path(os.getcwd()) / DEFAULT_CONFIG_REL)
    )
    try:
        got = json.loads(path.read_text(encoding="utf-8")).get("record_states")
    except (OSError, ValueError):
        return ()
    if not isinstance(got, list):
        return ()
    return tuple(str(w) for w in got if isinstance(w, str) and w)


def _status_re(states: tuple[str, ...]) -> re.Pattern[str]:
    """`^Status: <one of them>$`, cached per vocabulary.

    An EMPTY vocabulary gets a pattern that cannot match, rather than the empty
    alternation `()` a naive join produces: that one matches `Status:` with
    nothing after it and would report a record whose status is the empty string.
    """
    if states not in _STATUS_RE_CACHE:
        body = "|".join(re.escape(w) for w in states) if states else r"(?!)"
        _STATUS_RE_CACHE[states] = re.compile(r"^Status:[ \t]*(%s)[ \t]*$" % body)
    return _STATUS_RE_CACHE[states]


# The DISPLAY status, scanned over the WHOLE file on purpose: some plans put their header low, and this value is only ever printed.
_DISPLAY_STATUS_RE = re.compile(
    r"^[ \t]*(?:\*\*)?Status[ \t]*[:=][ \t]*(?:\*\*)?([A-Za-z][A-Za-z-]*)"
)


def record_blob(path: pathlib.Path) -> str:
    """The `Full-Text-Blob:` of a record, or "" when it carries none.

    ANCHORED AT END OF LINE, and only in the first ten lines. See the header:
    both anchors were paid for.
    """
    for line in _head(path):
        match = _BLOB_RE.match(line)
        if match:
            return match.group(1)
    return ""


def record_status(path: pathlib.Path, states: tuple[str, ...] | None = None) -> str:
    """A record status from the header window, or "".

    The word in PROSE must not exempt anything, and neither must a real header
    below line 10: a pointer no consumer can see is a pointer that exempts
    nothing.

    `states` defaults to reading the config, which keeps every existing one-arg
    call site working. The hot loop in `main()` passes the vocabulary it already
    read, so judging 86 plans does not re-open the config 86 times.
    """
    vocab = record_states() if states is None else states
    rx = _status_re(vocab)
    for line in _head(path):
        match = rx.match(line)
        if match:
            return match.group(1)
    return ""


def display_status(path: pathlib.Path) -> str:
    """The first `Status:` anywhere in the file, for the report line only."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.split("\n"):
        match = _DISPLAY_STATUS_RE.match(line)
        if match:
            return match.group(1)
    return ""


def _head(path: pathlib.Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.split("\n")[:HEADER_LINES]


def blob_is_real(blob: str, root: os.PathLike[str] | str | None = None) -> bool:
    """True when git has `blob` AS A BLOB, in the repository we are standing in."""
    if not blob:
        return False
    result = gitx.git(["cat-file", "-t", blob], root=root)
    return result.stdout.strip() == "blob"


# --------------------------------------------------------------------------- The allowlist, which has its OWN parser in this gate ---------------------------------------------------------------------------


def parse_allowlist(text: str) -> tuple[dict[str, str], list[str]]:
    """(path -> expiry, problems). The twin's loop, rule for rule.

    A `# BLOCKER:` line arms the NEXT entry and is consumed by it, so one reason
    covers exactly one path. A plain comment does NOT reset the armed reason and
    neither does a blank line, which is the opposite of `blocker-validator.sh`
    and is deliberate on the twin's part.
    """
    exempt: dict[str, str] = {}
    problems: list[str] = []
    reason = ""
    for raw in _allowlist_lines(text):
        if re.match(r"^[ \t]*#[ \t]*BLOCKER:", raw):
            # `${line#*BLOCKER:}` keeps the leading space, and that space counts
            # toward the length test below.
            reason = raw.split("BLOCKER:", 1)[1]
            continue
        if re.match(r"^[ \t]*#", raw):
            continue
        if raw.replace(" ", "") == "":
            continue
        fields = raw.split(None, 1)
        expiry = fields[0] if fields else ""
        path = fields[1].strip() if len(fields) > 1 else ""
        if not path:
            problems.append("malformed entry '%s' (want: YYYY-MM-DD  path)" % raw)
            continue
        if reason.replace(" ", "") == "" or len(reason) < MIN_REASON_LENGTH:
            problems.append("%s carries no substantive '# BLOCKER:' line above it" % path)
            reason = ""
            continue
        exempt[path] = expiry
        reason = ""
    return exempt, problems


def _allowlist_lines(text: str) -> list[str]:
    """`while IFS= read -r line || [[ -n "$line" ]]`.

    That `||` is why a file whose last line carries no newline is still read.
    `split("\\n")` yields the same records once the single trailing empty element
    a terminating newline produces is dropped.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


# --------------------------------------------------------------------------- The inline controls ---------------------------------------------------------------------------


def inline_controls(delete_days: int) -> list[str]:
    """The twin's control block. Returns the failure lines, empty when it holds.

    Every one of these is a plant with its mirror: an over-age date and an
    under-age one, a real blob and an all-zero one, a real header and the same
    word in prose, a 40-hex pointer and a 41-hex one, a header inside the window
    and one below it.
    """
    failures: list[str] = []
    old = age_days((dt.datetime.now(dt.UTC) - dt.timedelta(days=40)).isoformat())
    new = age_days((dt.datetime.now(dt.UTC) - dt.timedelta(days=2)).isoformat())
    if old < delete_days:
        failures.append(
            "control: a 40-day date did not read as over %d (got %d)" % (delete_days, old)
        )
    if new >= delete_days:
        failures.append("control: a 2-day date read as over %d (got %d)" % (delete_days, new))
    if age_days("not-a-date") != UNPARSEABLE:
        failures.append("control: an unparseable date did not report -1")

    with tempfile.TemporaryDirectory() as ctldir, tempfile.TemporaryDirectory() as scratch:
        ctl = pathlib.Path(scratch) / "record.md"
        gitx.git(["init", "-q", ctldir])
        minted = subprocess.run(
            ["git", "-C", ctldir, "hash-object", "-w", "--stdin"],
            input="a control blob\n",
            capture_output=True,
            text=True,
            check=False,
        )
        self_blob = minted.stdout.strip() if minted.returncode == 0 else ""
        if not self_blob:
            failures.append(
                "control: could not mint a scratch blob, so the exemption cannot be proven"
            )

        ctl.write_text(
            "# t\nStatus: compacted\nFull-Text-Blob: %s\nRecord-Sig: 00000000\n" % self_blob,
            encoding="utf-8",
        )
        if record_blob(ctl) != self_blob:
            failures.append("control: record_blob did not read the blob out of a record header")
        # blob_is_real reads the repository it is POINTED AT, so both directions are driven inside the scratch one. The twin uses subshells rather than a cd/cd-back pair, because an early exit between them would otherwise
        # leave the whole gate judging the wrong tree; passing the root as an
        # argument removes the hazard rather than working around it.
        if not blob_is_real(self_blob, root=ctldir):
            failures.append("control: blob_is_real refused a blob git demonstrably has")
        if blob_is_real("0" * 40, root=ctldir):
            failures.append(
                "control: blob_is_real accepted an all-zero blob, so the exemption is unconditional"
            )
        if record_status(ctl) != "compacted":
            failures.append("control: record_status did not read a compacted header")

        ctl.write_text("# t\nStatus: compacted\nno pointer here\n", encoding="utf-8")
        if record_blob(ctl):
            failures.append("control: record_blob invented a blob for a record that carries none")

        # A 41-hex value must be REFUSED, not silently truncated to 40. The strict gate rejects it, and a reader that accepted it would exempt a plan CI reds.
        ctl.write_text(
            "# t\nStatus: compacted\nFull-Text-Blob: %sf\n" % self_blob, encoding="utf-8"
        )
        if record_blob(ctl):
            failures.append("control: record_blob accepted a 41-hex pointer by truncating it")

        ctl.write_text(
            "# t\nStatus: draft\n\nWe should set Status: compacted here one day.\n",
            encoding="utf-8",
        )
        if record_status(ctl):
            failures.append("control: record_status read a status out of prose")

        filler = "".join("filler %d\n" % i for i in range(1, 11))
        ctl.write_text("# t\n%sStatus: compacted\n" % filler, encoding="utf-8")
        if record_status(ctl):
            failures.append("control: record_status read a status from below the 10-line window")

        ctl.write_text(
            "# t\nStatus: compacted\n%sFull-Text-Blob: %s\n" % (filler, self_blob),
            encoding="utf-8",
        )
        if record_blob(ctl):
            failures.append(
                "control: record_blob read a pointer from below the 10-line header window"
            )

    return failures


CONTROL_LINE_AGE = (
    "✓ control: the age arithmetic reports over and under the threshold, and refuses a bad date"
)
CONTROL_LINE_COMPACTION = (
    "✓ control: the compaction exemption reads a real pointer and a real header, refuses a fake "
    "blob, a 41-hex blob, a status in prose, and anything below line 10"
)


# --------------------------------------------------------------------------- The gate ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean, 1 offender or refusal, 2 setup error."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    override = os.environ.get(ROOT_ENV)
    root = pathlib.Path(override) if override else paths.CI_DIR.parent
    try:
        os.chdir(str(root))
    except OSError:
        return 2
    root = pathlib.Path(os.getcwd())

    red, green, yel, nc = _colours()

    config = pathlib.Path(os.environ.get(CONFIG_ENV) or (root / DEFAULT_CONFIG_REL))
    allowlist_path = pathlib.Path(os.environ.get(ALLOWLIST_ENV) or (root / DEFAULT_ALLOWLIST_REL))
    min_plans = int(os.environ.get(MIN_FILES_ENV) or DEFAULT_MIN_PLANS)

    if not config.is_file():
        print("VACUOUS INPUT: %s is missing, so no threshold can be read" % config, file=sys.stderr)
        return 1
    try:
        settings = json.loads(config.read_text(encoding="utf-8"))
        warn_days = int(settings["warn_days"])
        delete_days = int(settings["delete_days"])
        plan_glob = str(settings["plan_glob"])
    except (OSError, ValueError, KeyError, TypeError):
        # The twin runs three separate `python3 -c` calls and `|| exit 2` on each, so a config missing any one key is a SETUP error rather than a verdict. One read here, same exit code.
        return 2

    # W12 P3.3. A MISSING OR EMPTY VOCABULARY IS A SETUP ERROR, not a quiet "nothing is a record". Without it no plan is a compaction record, every one of the 31 records loses its exemption at once, and the gate reds on a tree defect that is really a config that lost a key. Same exit code and same sentence as the twin, which refuses at `[[ -n "$RECORD_STATES_ALT" ]]`.
    states = record_states(config)
    if not states:
        print(
            "VACUOUS INPUT: %s carries no record_states, so no plan could ever be read as a"
            % config,
            file=sys.stderr,
        )
        print(
            "  compaction record and every compacted plan would lose its exemption at once.",
            file=sys.stderr,
        )
        return 2

    failures = inline_controls(delete_days)
    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print(
            "%s✗%s instrument control failed; every verdict below would be meaningless" % (red, nc),
            file=sys.stderr,
        )
        return 2
    print(CONTROL_LINE_AGE)
    print(CONTROL_LINE_COMPACTION)

    plans = gitx.ls_files(plan_glob, root=root)
    if len(plans) < min_plans:
        print(
            "VACUOUS INPUT: found %d tracked plan file(s) matching %s, floor is %d."
            % (len(plans), plan_glob, min_plans),
            file=sys.stderr,
        )
        print(
            "  The glob lost the corpus; refusing a verdict rather than reporting a clean tree.",
            file=sys.stderr,
        )
        return 1

    grafts_file = _grafts_file(root)
    skip_ages = False
    grafted: list[str] = []
    if grafts_file is not None:
        graft_shas = set(grafts_file.read_text(encoding="utf-8", errors="replace").split())
        for plan in plans:
            last = gitx.git(["log", "-1", "--format=%H", "--", plan], root=root).stdout.strip()
            # A plan whose last commit is a graft boundary reports the boundary's date. A plan with NO commit at all is the same failure, louder.
            if not last or last in graft_shas:
                grafted.append(plan)

    if grafted:
        if os.environ.get("CI", "") == "true":
            print(
                "%s✗%s plan housekeeping: this checkout is SHALLOW at a boundary that %d plan(s)"
                % (red, nc, len(grafted)),
                file=sys.stderr,
            )
            print(
                "  sit on, so they report the GRAFT commit's date and the age verdict would be",
                file=sys.stderr,
            )
            print("  fiction. Refusing rather than answering.", file=sys.stderr)
            for plan in grafted:
                print("    %s" % plan, file=sys.stderr)
            print(
                "  Fix: the step must run in a job whose actions/checkout carries", file=sys.stderr
            )
            print("    fetch-depth: 0", file=sys.stderr)
            print("    filter: blob:none", file=sys.stderr)
            print("  Measured: %s commit(s) reachable, and" % _commit_count(root), file=sys.stderr)
            print(
                "  %s holds %d graft(s)." % (grafts_file, _line_count(grafts_file)),
                file=sys.stderr,
            )
            return 1
        print(
            "%s⚠%s plan housekeeping: %d plan(s) sit on a shallow boundary"
            % (yel, nc, len(grafted))
        )
        print("  (%s commit(s) reachable); their AGE verdict is DEFERRED." % _commit_count(root))
        print("  To run it here: git fetch --unshallow --filter=blob:none")
        skip_ages = True
    elif grafts_file is not None:
        print(
            "  note: the clone is shallow (%d graft(s), %s commit(s)),"
            % (_line_count(grafts_file), _commit_count(root))
        )
        print("  but every plan's last commit is present, so the age verdict below is real.")

    exempt_until: dict[str, str] = {}
    allow_problems: list[str] = []
    if allowlist_path.is_file():
        exempt_until, allow_problems = parse_allowlist(
            allowlist_path.read_text(encoding="utf-8", errors="replace")
        )

    offenders: list[tuple[str, int, str, str, str]] = []
    warnings: list[tuple[str, int, str, str]] = []
    n_exempt = 0
    n_compacted = 0
    today = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")

    rows: list[tuple[str, int, str]] = []
    if not skip_ages:
        for plan in plans:
            when = gitx.git(["log", "-1", "--format=%cI", "--", plan], root=root).stdout.strip()
            if not when:
                continue
            try:
                then = dt.datetime.fromisoformat(when)
            except ValueError:
                continue
            if then.tzinfo is None:
                then = then.replace(tzinfo=dt.UTC)
            days = (dt.datetime.now(dt.UTC) - then).days
            red_on = (then + dt.timedelta(days=delete_days)).date().isoformat()
            rows.append((plan, days, red_on))

    for plan, days, red_on in rows:
        path = pathlib.Path(plan)
        status = display_status(path)
        if record_status(path, states) == "compacted":
            blob = record_blob(path)
            if blob_is_real(blob, root=root):
                if exempt_until.get(plan):
                    allow_problems.append(
                        "%s is COMPACTED, so the allowlist entry (expires %s) suppresses "
                        "nothing. Delete the line; the record's blob is what exempts it now."
                        % (plan, exempt_until[plan])
                    )
                n_compacted += 1
                continue
            if exempt_until.get(plan) and not today > exempt_until[plan]:
                n_exempt += 1
                continue
            offenders.append(
                (
                    plan,
                    days,
                    red_on,
                    "compacted",
                    "its Full-Text-Blob %s does not resolve, so its full text is UNRECOVERABLE"
                    % (blob or "is missing and"),
                )
            )
            continue
        if exempt_until.get(plan):
            expiry = exempt_until[plan]
            if today > expiry:
                offenders.append(
                    (
                        plan,
                        days,
                        red_on,
                        status or "UNKNOWN",
                        "the allowlist entry EXPIRED on %s" % expiry,
                    )
                )
            elif days < delete_days:
                allow_problems.append(
                    "%s is exempted until %s but is only %d day(s) old -- the entry "
                    "suppresses nothing. Delete it." % (plan, expiry, days)
                )
            else:
                n_exempt += 1
            continue
        if days >= delete_days:
            offenders.append((plan, days, red_on, status or "UNKNOWN", ""))
        elif days >= warn_days:
            warnings.append((plan, days, red_on, status or "UNKNOWN"))

    for plan in exempt_until:
        if gitx.git(["ls-files", "--error-unmatch", plan], root=root).returncode != 0:
            allow_problems.append(
                "%s is allowlisted but is not a tracked plan file. Delete the line; the "
                "plan is gone." % plan
            )

    rc = 0
    if allow_problems:
        print(
            "%s✗%s plan housekeeping: %d allowlist problem(s):" % (red, nc, len(allow_problems)),
            file=sys.stderr,
        )
        for message in allow_problems:
            print("    %s" % message, file=sys.stderr)
        rc = 1

    if offenders:
        print(
            "%s✗%s plan housekeeping: %d plan file(s) unchanged for more than %d days"
            % (red, nc, len(offenders), delete_days),
            file=sys.stderr,
        )
        for plan, days, _red_on, status, extra in offenders:
            print(
                "    %-52s %3s days  Status: %s %s" % (plan, days, status, extra), file=sys.stderr
            )
        print(_REMEDY % (delete_days, allowlist_path.name, delete_days), file=sys.stderr)
        rc = 1

    if warnings:
        print("%s⚠%s %d plan(s) will cross %d days soon:" % (yel, nc, len(warnings), delete_days))
        for plan, days, red_on, status in warnings:
            print("    %-52s %3s days  Status: %-12s red on %s" % (plan, days, status, red_on))

    if rc == 0:
        if skip_ages:
            print(
                "%s✓%s plan housekeeping: %d tracked plan file(s) (floor %d), %d exempt, "
                "%d compacted." % (green, nc, len(plans), min_plans, n_exempt, n_compacted)
            )
            print("  PARTIAL RUN: the age verdict was skipped (shallow clone), not passed.")
        else:
            print(
                "%s✓%s plan housekeeping: %d tracked plan file(s) (floor %d), none over %d days, "
                "%d within %d days, %d exempt, %d compacted (their full text is in a blob; "
                "check:ci-plan-record verifies the pointer)."
                % (
                    green,
                    nc,
                    len(plans),
                    min_plans,
                    delete_days,
                    len(warnings),
                    delete_days - warn_days,
                    n_exempt,
                    n_compacted,
                )
            )
    return rc


# NO EM DASH REACHES THIS FILE'S OUTPUT, and the first cut of the port assumed one did. The twin writes `-- the entry suppresses nothing` with two ASCII hyphens, not U+2014, and a `_EM_DASH` constant carried over from the sibling ports turned that one message into a MISMATCH_FINDINGS the differential caught on its third recorded tree. Named here rather than silently corrected: the
# two characters are indistinguishable in a code review and identical in meaning to a reader, which is exactly why only a byte comparison finds them.

# The remedy block, a heredoc in the twin. NOTHING HERE ASKS FOR A DELETION, and that is the W12 change: the operator's standing rule is that nothing is deleted, and a gate demanding an act nobody may perform is a gate whose only exit is a suppression.
_REMEDY = """
  Fix, in order of preference. NOTHING HERE ASKS YOU TO DELETE A PLAN: the
  operator's standing rule is that nothing is deleted, and a gate demanding an
  act nobody may perform is a gate whose only exit is a suppression.

  1. WORK ON IT. A commit touching the file resets the clock. There is no
     "mark it fresh" edit -- an empty touch is a lie the log records.

  2. COMPACT IT, if the plan is finished. The file KEEPS ITS PATH, so every
     citation of it still resolves, and its full text moves into a git blob
     that a plain `git show` recovers for as long as the repository exists:
       .claude/hooks/stop/worklist.py --plan-compact <me> <path> --why auto
       .claude/hooks/stop/worklist.py --plan-compact <me> <path> --write
     The first run prints the record without writing it; read it, then write.
     A plan with open boxes is refused unless you pass --park, which records
     it as `parked` and deliberately KEEPS it on this clock -- parking buys a
     smaller file, never an exemption.
     Land it with its ledger and its index in the SAME commit, or two gates
     will disagree with each other:
       npm run check:ci-plan-boxes  -- --update
       npm run check:ci-plan-record -- --update

  3. EXEMPT IT, only if it must outlive %d days on purpose. Add to
     %s:
       # BLOCKER: <why this plan must stay, and what makes that true>
       2026-12-01  agent/PLAN-example.md
     The date is a HARD expiry: it goes red again on that date whether or not
     anyone looked. An entry whose plan is under %d days, or whose
     path no longer exists, is REFUSED -- an exemption must suppress something."""


def _grafts_file(root: pathlib.Path) -> pathlib.Path | None:
    """`git rev-parse --git-path shallow`, when it exists and is NON-EMPTY.

    Non-emptiness is the whole test; see the header on why
    `--is-shallow-repository` is the wrong question.
    """
    result = gitx.git(["rev-parse", "--git-path", "shallow"], root=root)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    path = pathlib.Path(result.stdout.strip())
    if not path.is_absolute():
        path = root / path
    try:
        if path.stat().st_size == 0:
            return None
    except OSError:
        return None
    return path


def _commit_count(root: pathlib.Path) -> str:
    """`git rev-list --count HEAD`, or "" when git cannot say.

    The empty string is what a failed command substitution interpolates in the
    twin, so an unanswerable count prints as a gap in the sentence rather than
    as a zero that reads like a measurement.
    """
    result = gitx.git(["rev-list", "--count", "HEAD"], root=root)
    return result.stdout.strip() if result.returncode == 0 else ""


def _line_count(path: pathlib.Path) -> int:
    """`wc -l`, which counts NEWLINES, not records."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").count("\n")
    except OSError:
        return 0


# --------------------------------------------------------------------------- The selftest, an ADDITION on top of the inline controls ---------------------------------------------------------------------------

_GOOD_REASON = (
    "this plan is the standing reference for the release rotation and must outlive the window"
)


def selftest() -> int:
    """Both directions on every extractor, then the gate on real git trees."""
    ctl = Controls("plan-housekeeping", floor=26, verbose=True)

    now = dt.datetime.now(dt.UTC)
    ctl.truthy(
        "AGE: a 40-day date reads as 40 days",
        age_days((now - dt.timedelta(days=40)).isoformat()) == 40,
    )
    ctl.check(
        "AGE: a 2-day date reads as 2 days", age_days((now - dt.timedelta(days=2)).isoformat()), 2
    )
    ctl.check(
        "AGE MIRROR: an unparseable date reports -1, never an age",
        age_days("not-a-date"),
        UNPARSEABLE,
    )
    ctl.check(
        "AGE: a naive timestamp is read as UTC",
        age_days((now - dt.timedelta(days=5)).replace(tzinfo=None).isoformat()),
        5,
    )

    # `ignore_cleanup_errors` BECAUSE THE FAILURE IS JANITORIAL, NOT A VERDICT. This block runs `git init` and real commits inside the temp tree, and on a loaded runner the directory can still be gaining files when `TemporaryDirectory.__exit__` walks it, so `shutil.rmtree` raises `OSError: [Errno 39] Directory not empty` and the selftest reports a FAILURE that says nothing about
    # any control. Observed once in CI, job 104604932125.
    #
    # SAFE HERE IN A WAY IT WOULD NOT BE ELSEWHERE, which is the reason this is fixed on a single observation while the control-vacuity flake next door is not: every `ctl.check` in this block has already RUN and been recorded by the time `__exit__` is reached. Tolerating undeleted scratch cannot hide a failing assertion -- it can only stop leftover bytes in /tmp from being
    # reported as one. Nothing is suppressed; the verdict is unchanged.
    #
    # The writer was NOT identified (no process is leaked -- every call here is a synchronous `subprocess.run`), so this tolerates the debris rather than claiming to have removed its cause.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = pathlib.Path(tmp)
        record = base / "r.md"

        record.write_text(
            "# t\nStatus: compacted\nFull-Text-Blob: %s\n" % ("a" * 40), encoding="utf-8"
        )
        ctl.check("RECORD: a 40-hex pointer in the window is read", record_blob(record), "a" * 40)
        ctl.check("RECORD: the compacted header is read", record_status(record), "compacted")

        record.write_text(
            "# t\nStatus: compacted\nFull-Text-Blob: %s\n" % ("a" * 41), encoding="utf-8"
        )
        ctl.check(
            "RECORD MIRROR: a 41-hex pointer is REFUSED, not truncated", record_blob(record), ""
        )

        record.write_text(
            "# t\nStatus: draft\n\nWe should set Status: compacted here.\n", encoding="utf-8"
        )
        ctl.check("RECORD MIRROR: the word in prose is not a status", record_status(record), "")

        filler = "".join("filler %d\n" % i for i in range(1, 11))
        record.write_text("# t\n%sStatus: compacted\n" % filler, encoding="utf-8")
        ctl.check("RECORD MIRROR: a header below line 10 is not read", record_status(record), "")

        record.write_text("# t\nStatus: parked\n", encoding="utf-8")
        ctl.check("RECORD: parked is read, and is NOT compacted", record_status(record), "parked")

        # -- The allowlist parser, both directions ---------------------------
        exempt, problems = parse_allowlist(
            "# BLOCKER: %s\n2026-12-01  agent/PLAN-x.md\n" % _GOOD_REASON
        )
        ctl.check("ALLOW: a well-formed entry is taken", exempt, {"agent/PLAN-x.md": "2026-12-01"})
        ctl.check("ALLOW: a well-formed entry raises no problem", problems, [])

        exempt, problems = parse_allowlist("# BLOCKER: short\n2026-12-01  agent/PLAN-x.md\n")
        ctl.check("ALLOW MIRROR: a thin BLOCKER is refused", exempt, {})
        ctl.truthy("ALLOW MIRROR: and it says so", problems)

        exempt, problems = parse_allowlist("2026-12-01  agent/PLAN-x.md\n")
        ctl.check("ALLOW MIRROR: no BLOCKER at all is refused", exempt, {})

        _exempt, problems = parse_allowlist("# BLOCKER: %s\njustonefield\n" % _GOOD_REASON)
        ctl.truthy("ALLOW: a one-field line is malformed", any("malformed" in p for p in problems))

        # A TAB-ONLY LINE IS NOT BLANK to the twin, because `${line// /}` strips
        # spaces and not tabs. It therefore reaches the entry branch and is reported as malformed. Reproduced rather than tidied.
        _exempt, problems = parse_allowlist("# BLOCKER: %s\n\t\n" % _GOOD_REASON)
        ctl.truthy(
            "ALLOW: a TAB-only line is malformed, not blank",
            any("malformed" in p for p in problems),
        )

        ctl.check("CONTROLS: the gate's own inline controls hold", inline_controls(33), [])

        # -- The gate, on real committed git trees ---------------------------
        saved_cwd = os.getcwd()

        def build(
            name: str, plans: dict[str, tuple[str, str]], allow: str | None = None
        ) -> pathlib.Path:
            """A git repo with `plans` as {relpath: (body, committer-date)}."""
            tree = base / name
            (tree / "agent").mkdir(parents=True, exist_ok=True)
            (tree / ".ci" / "config").mkdir(parents=True, exist_ok=True)
            (tree / ".ci" / "config" / "plan-lifecycle.json").write_text(
                # `record_states` IS NOT OPTIONAL HERE. main() refuses a config without it (return 2), which is the right refusal and is why this fixture must carry it: a fixture missing the key does not test the gate, it tests the refusal, and every case below then reports 2 where it wanted 0 or 1.
                '{"plan_glob": "agent/PLAN-*.md", "warn_days": 26, "delete_days": 33,'
                ' "record_states": ["compacted", "parked"]}\n',
                encoding="utf-8",
            )
            if allow is not None:
                (tree / "allow").write_text(allow, encoding="utf-8")
            env = dict(os.environ)
            env.update(
                {
                    "GIT_AUTHOR_NAME": "pi",
                    "GIT_AUTHOR_EMAIL": "pi@example.invalid",
                    "GIT_COMMITTER_NAME": "pi",
                    "GIT_COMMITTER_EMAIL": "pi@example.invalid",
                }
            )
            subprocess.run(["git", "init", "-q", str(tree)], check=False, capture_output=True)
            for rel, (body, when) in plans.items():
                (tree / rel).parent.mkdir(parents=True, exist_ok=True)
                (tree / rel).write_text(body, encoding="utf-8")
                subprocess.run(
                    ["git", "-C", str(tree), "add", "-A"], check=False, capture_output=True
                )
                stamp = dict(env)
                stamp["GIT_COMMITTER_DATE"] = when
                stamp["GIT_AUTHOR_DATE"] = when
                subprocess.run(
                    ["git", "-C", str(tree), "commit", "-q", "--no-gpg-sign", "-m", rel],
                    check=False,
                    capture_output=True,
                    env=stamp,
                )
            return tree

        def run(tree: pathlib.Path, **over: str) -> int:
            names = {
                ROOT_ENV: str(tree),
                CONFIG_ENV: str(tree / ".ci" / "config" / "plan-lifecycle.json"),
                ALLOWLIST_ENV: str(tree / "allow"),
                MIN_FILES_ENV: "3",
            }
            names.update(over)
            saved = {k: os.environ.get(k) for k in names}
            os.environ.update(names)
            try:
                return main([])
            finally:
                os.chdir(saved_cwd)
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

        fresh = "2026-09-05T12:00:00+00:00"
        stale = "2020-01-01T12:00:00+00:00"

        clean = build(
            "clean",
            {
                "agent/PLAN-a.md": ("# a\nStatus: draft\n", fresh),
                "agent/PLAN-b.md": ("# b\nStatus: draft\n", fresh),
                "agent/PLAN-c.md": ("# c\nStatus: draft\n", fresh),
            },
        )
        ctl.check("CONTROL: three fresh plans pass", run(clean), 0)

        aged = build(
            "aged",
            {
                "agent/PLAN-a.md": ("# a\nStatus: draft\n", stale),
                "agent/PLAN-b.md": ("# b\nStatus: draft\n", fresh),
                "agent/PLAN-c.md": ("# c\nStatus: draft\n", fresh),
            },
        )
        ctl.check("PLANT: one over-age plan reds the gate", run(aged), 1)

        ctl.check(
            "VACUITY: a corpus under the floor is a REFUSAL, not a clean tree",
            run(clean, **{MIN_FILES_ENV: "99"}),
            1,
        )
        ctl.check(
            "VACUITY: a missing config is a refusal",
            run(clean, **{CONFIG_ENV: str(base / "nosuch.json")}),
            1,
        )

        exempted = build(
            "exempted",
            {
                "agent/PLAN-a.md": ("# a\nStatus: draft\n", stale),
                "agent/PLAN-b.md": ("# b\nStatus: draft\n", fresh),
                "agent/PLAN-c.md": ("# c\nStatus: draft\n", fresh),
            },
            "# BLOCKER: %s\n2099-12-01  agent/PLAN-a.md\n" % _GOOD_REASON,
        )
        ctl.check("SUPPRESSION: an unexpired allowlist entry silences it", run(exempted), 0)

        expired = build(
            "expired",
            {
                "agent/PLAN-a.md": ("# a\nStatus: draft\n", stale),
                "agent/PLAN-b.md": ("# b\nStatus: draft\n", fresh),
                "agent/PLAN-c.md": ("# c\nStatus: draft\n", fresh),
            },
            "# BLOCKER: %s\n2000-01-01  agent/PLAN-a.md\n" % _GOOD_REASON,
        )
        ctl.check("LIVENESS: an EXPIRED allowlist entry reds again", run(expired), 1)

        pointless = build(
            "pointless",
            {
                "agent/PLAN-a.md": ("# a\nStatus: draft\n", fresh),
                "agent/PLAN-b.md": ("# b\nStatus: draft\n", fresh),
                "agent/PLAN-c.md": ("# c\nStatus: draft\n", fresh),
            },
            "# BLOCKER: %s\n2099-12-01  agent/PLAN-a.md\n" % _GOOD_REASON,
        )
        ctl.check("LIVENESS: an entry that suppresses nothing is a problem", run(pointless), 1)

        dangling = build(
            "dangling",
            {
                "agent/PLAN-a.md": ("# a\nStatus: draft\n", fresh),
                "agent/PLAN-b.md": ("# b\nStatus: draft\n", fresh),
                "agent/PLAN-c.md": ("# c\nStatus: draft\n", fresh),
            },
            "# BLOCKER: %s\n2099-12-01  agent/PLAN-gone.md\n" % _GOOD_REASON,
        )
        ctl.check("LIVENESS: an entry naming no tracked plan is a problem", run(dangling), 1)

        broken_record = build(
            "broken-record",
            {
                "agent/PLAN-a.md": (
                    "# a\nStatus: compacted\nFull-Text-Blob: %s\n" % ("0" * 40),
                    stale,
                ),
                "agent/PLAN-b.md": ("# b\nStatus: draft\n", fresh),
                "agent/PLAN-c.md": ("# c\nStatus: draft\n", fresh),
            },
        )
        ctl.check(
            "PLANT: a compacted record whose blob does not resolve is an OFFENDER",
            run(broken_record),
            1,
        )

        parked = build(
            "parked",
            {
                "agent/PLAN-a.md": (
                    "# a\nStatus: parked\nFull-Text-Blob: %s\n" % ("0" * 40),
                    stale,
                ),
                "agent/PLAN-b.md": ("# b\nStatus: draft\n", fresh),
                "agent/PLAN-c.md": ("# c\nStatus: draft\n", fresh),
            },
        )
        ctl.check("PARKED: parking buys a smaller file, never an exemption", run(parked), 1)

        # THE EXEMPTION THAT ACTUALLY WORKS, driven with a REAL blob minted in the fixture's own repository. Without this the compaction branch could be dead code that only ever produced offenders.
        compacted = build(
            "compacted",
            {
                "agent/PLAN-b.md": ("# b\nStatus: draft\n", fresh),
                "agent/PLAN-c.md": ("# c\nStatus: draft\n", fresh),
            },
        )
        minted = subprocess.run(
            ["git", "-C", str(compacted), "hash-object", "-w", "--stdin"],
            input="the full text\n",
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        (compacted / "agent" / "PLAN-a.md").write_text(
            "# a\nStatus: compacted\nFull-Text-Blob: %s\n" % minted, encoding="utf-8"
        )
        env = dict(os.environ)
        env.update(
            {
                "GIT_AUTHOR_NAME": "pi",
                "GIT_AUTHOR_EMAIL": "pi@example.invalid",
                "GIT_COMMITTER_NAME": "pi",
                "GIT_COMMITTER_EMAIL": "pi@example.invalid",
                "GIT_COMMITTER_DATE": stale,
                "GIT_AUTHOR_DATE": stale,
            }
        )
        subprocess.run(["git", "-C", str(compacted), "add", "-A"], check=False, capture_output=True)
        subprocess.run(
            ["git", "-C", str(compacted), "commit", "-q", "--no-gpg-sign", "-m", "compacted"],
            check=False,
            capture_output=True,
            env=env,
        )
        ctl.truthy("COMPACTED: the fixture minted a real blob", bool(minted))
        ctl.check("COMPACTED: a resolving pointer EXEMPTS an over-age plan", run(compacted), 0)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
