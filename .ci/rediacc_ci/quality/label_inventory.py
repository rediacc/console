r"""`.github/labels.yml` and the labels that exist on the repo must agree, both ways.

Ported from `.ci/scripts/quality/check-label-inventory.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

WHY, in the twin's own words, because the failure was a silent fail-open:

    The sibling gate check-label-references.sh closes the first link of the
    chain: code that names a label -> that label declared in .github/labels.yml.
    It stops there on purpose, because DECLARING is not CREATING. The link that
    was still open is the one that bit: `rollback` was declared and referenced and
    did not exist on the repo, and promote-stable.yml:58 searches for that label.
    A GitHub search for a label that does not exist returns zero PRs -- not an
    error -- so the promotion block never fired and nothing said so. That is
    SILENT FAIL-OPEN, and it is invisible to every check that reads only the tree.

    The other direction matters too, for a quieter reason: a label that exists on
    the repo but is declared nowhere is recorded nowhere in the tree, and cannot
    reach the PR label guide (.ci/scripts/ci/label-guide-comment.cjs renders that
    guide from labels.yml), so it is a label people can apply and nobody can look
    up. Note that declaring is not the same as listing: an entry may carry
    `guide: false`, which keeps it out of the PR comment while still satisfying
    THIS gate. That is the intended home for GitHub's stock defaults and
    bot-applied labels -- declared and reconciled, just not advertised.

    BLINDNESS IS NOT CLEANLINESS. If the live list cannot be read -- no token, an
    API error, an empty response -- this refuses. An empty label list would
    otherwise make direction (b) vacuously clean and direction (a) fire on
    everything, so "empty" is treated as a failed read, never as a tree state.

    CREATE-ON-DEMAND. Exactly one label is legitimately absent until first use:
    report-nightly-status.cjs creates `nightly-red` right before it opens the
    rolling issue, because createIssue with an unknown label fails the whole call.
    It is still declared in labels.yml (the guide must be able to explain it), so
    it would otherwise trip direction (a) forever. The allowlist below forgives
    ABSENCE only; the entry names its creator so a future reader can check the
    claim, and the gate verifies both halves of the entry still exist.

    Test seams (so the test never touches the network):
      LABEL_INVENTORY_LABELS_FILE - the declaration file
      LABEL_INVENTORY_LIVE_FILE   - newline-separated live label names; when set,
                                    no `gh` call is made at all
      LABEL_INVENTORY_PROBE_FILE  - newline-separated names the single-label
                                    re-read (see VERIFY-AT-READ below) should
                                    report as existing. A SEPARATE seam from the
                                    list, because the whole point of the re-read
                                    is that it can disagree with the list.

THE THREE ALLOWLIST ENTRIES CARRY THEIR OWN BLOCKER REASONS, verbatim:

    nightly-red: report-nightly-status.cjs calls issues.createLabel for
    nightly-red immediately before opening the rolling issue, because
    issues.create with an unknown label fails the entire call; the label
    therefore does not exist until the first red night, and demanding it up front
    would fail this gate on a repo whose nightly has never gone red.

    ci: claude-review-gate.sh --apply-labels creates `ci` immediately before its
    first use, the same pattern and for the same reason: the label is brand new,
    and declaring it here without creating it would fail direction (a) until some
    human ran `gh label create`. Creating it up front instead is the ordering trap
    in reverse -- the applier only reaches main after this file does, so the label
    would sit live and undeclared for the length of one PR and fail direction (b).
    Create-on-demand dissolves both halves.

    bump-none: bump-none is in exactly the position `ci` was. The same applier
    creates it immediately before its first use, and the same ordering trap
    applies in both directions.

THE ARCHAEOLOGY THAT GETS TIDIED OUT, AND MUST NOT BE. The twin was FIXED at
commit 96355d3b5 on 2026-09-06, and the fix is one `|| true`:

    `|| true` IS LOAD-BEARING, and its absence disarmed the floor below. grep
    exits 1 when the file declares no labels, `set -e` killed the script HERE, and
    the MIN_DECLARED control -- whose own message reads "this reader is broken, not
    the file" -- could never fire in the one case it was written for. Reproduced
    2026-09-06 with LABEL_INVENTORY_LABELS_FILE pointed at an empty file: exit 1,
    zero bytes on both streams.

Zero bytes on both streams is the shape worth remembering: it looks exactly like a
gate failing for a real reason. The Python port cannot reproduce the defect, which
is why the note has to survive as prose.

THE DESCRIPTION CAP IS A CREATE-TIME RULE, so it fails late and elsewhere:

    GitHub caps label descriptions at 100 characters, and rejects longer ones at
    CREATE time only -- a declaration here can sit over the cap indefinitely and
    then fail whatever finally tries to create/sync it (bump-none did exactly this
    on 2026-08-09: the applier's create call failed live, mid-merge-flow).
    Validate proactively, control-first: a checker that cannot fire is not a
    checker, so prove it fires on a planted 101-char description before reading
    the real file.

THE ALLOWLIST IS SELF-EXPIRING, and the scoping of that is deliberate:

    a stale entry is a permanent hole, so both halves of every entry are
    re-verified. This is what makes the exemption self-expiring: delete
    report-nightly-status.cjs and the allowlist fails rather than quietly
    forgiving a label nothing creates any more.

    The "still declared" half is scoped to the REAL declaration file: a fixture
    tree legitimately does not carry nightly-red, and the entry must not fail every
    test that drives this gate against a fixture. Same shape as
    check-workflow-gates.sh's SLIM_TIMEOUT_REQUIRE_COVERAGE, and the test drives
    the flag on explicitly so the scoping itself stays covered.

VERIFY-AT-READ EXISTS BECAUSE THE GATE CRIED WOLF ONCE:

    The list read is a snapshot, and the repo's labels change under it. Observed
    live: a full CI run accused `no-auto-retry` of not existing while it existed
    and watchdog-monitor.cjs:1105 was reading it -- someone was mid-way through
    delete-and-recreate to fix its empty description, and the paginated list came
    back one short. The EMPTY-list guard above does not catch that: a list that is
    merely wrong-by-one passes every guard and then produces this gate's loudest
    possible message, the one about rollback and silent fail-open.

    That is worse than a missed finding. A gate that cries wolf that hard on a race
    gets ignored, and then it is worth nothing on the day it is right. So a label
    that LOOKS absent is re-read on its own before it is accused: a 404 confirms
    the finding, a 200 means the list was stale and the finding is dropped with a
    note.

    Only this direction needs it. An EXTRA name in the list cannot be a
    partial-read artifact -- a stale read loses entries, it does not invent them.

    Only a 404 CONFIRMS absence. A 403, a 500 or a network error says nothing about
    the label, and must not be read as agreement with the stale list.

SECTION (c) EXISTS BECAUSE NAMES WERE NEVER THE WHOLE CONTRACT:

    This gate reconciled existence in both directions and stopped there, so a label
    could exist, be declared, and still tell every human the opposite of the truth.

    Measured 2026-08-26: TEN fields had drifted, silently, for an unknown period.
    The one that cost real time: `release` still read "Opt-in: triggers CD pipeline
    on merge to main", while labels.yml says "Historical only: CD reads no label,
    it is dispatched unconditionally". An operator read the live text, reasonably
    concluded that a label controlled releases, and scoped a whole task around it.
    Others: `translation` carried the typo "Missing on wrong translation,";
    `no-auto-retry` had an EMPTY description and the wrong colour; `no-cancel-push`
    described behaviour it does not have.

    The description is documentation that ships to every human who opens the label
    picker, and it was the one part of the label nothing checked.

AND THE SWALLOWED-FAILURE NOTE ON THAT COMPARISON, which is the reason it has an
exit code of its own:

    `|| true` here would make a CRASHED comparator indistinguishable from "the
    labels agree" -- empty output either way, and the gate would report a clean tree
    over a probe that never ran. check-swallowed-failures.sh caught exactly that.
    The exit code is captured separately and a non-zero one is a hard failure,
    because a comparison that could not run is not a match.

    NEVER exit 0 here. The outer bash captures this process's exit code as drift_rc
    and treats 0 as "the comparison ran and found nothing" -- the exact
    swallowed-failure class check-swallowed-failures.sh already caught once at the
    shell level (1eac336b: a no-op fallback around $DRIFT made a crashed comparator
    indistinguishable from a clean tree). This is the same defect one level down:
    LIVE_JSON can be malformed (a paginated gh api call that fails mid-stream leaves
    partial stdout, and the caller's own empty-string fallback does not un-truncate
    it), and a bare sys.exit success here reported that as "names, descriptions and
    colours all agree" with the comparison never having run.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE EMBEDDED PYTHON HEREDOC BECOMES ORDINARY FUNCTIONS, and its exit-code contract
becomes an exception. The twin runs a `python3 - <<'PY'` child and captures
`drift_rc` separately so that a crash cannot read as agreement; here the same
distinction is `DriftUnreadableError`, raised where that child exits 1, and the caller
turns it into the identical message and exit. The shape of the guarantee is what
matters: an unreadable comparison is never a clean tree.

`length()` IN awk IS BYTES UNDER `LC_ALL=C`, which `scripts/lib/shadow-gate.ts`
pins for both sides, while Python's `len()` counts CHARACTERS. Every description in
this repo is ASCII, so the two agree today; a description with a non-ASCII
character would be measured differently, and the port would under-report rather
than over-report. Stated rather than silently normalised, because normalising it
would make the port disagree with the twin on a real file.

THE UNQUOTING ORDER IS OBSERVABLE AND IS PRESERVED. The twin strips the `- name:`
prefix, then a surrounding pair of double quotes, then a surrounding pair of single
quotes, and only THEN trailing whitespace. So `- name: "x"  ` keeps its quotes: the
`^"(.*)"$` anchor fails while the trailing spaces are still there. That is a bug in
the twin and it is carried, because "fixing" it changes which names reconcile.

`gh` IS SHELLED OUT TO, once for the name list and once for the JSON, exactly as
the twin does it, and the single-label re-read is a third call. A failed call is
never folded into "fine": the name read refuses outright, and the re-read reports
"could not probe" (2), which REPORTS the finding rather than dropping it.

THE ALLOWLIST IS PRINTED, NOT SILENT. `log_info` names every allowlisted label that
is legitimately absent on every run, so the debt stays visible. That is the
house rule about quiet exemptions, and the twin already follows it.
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

LABELS_FILE_ENV = "LABEL_INVENTORY_LABELS_FILE"
LIVE_FILE_ENV = "LABEL_INVENTORY_LIVE_FILE"
LIVE_JSON_FILE_ENV = "LABEL_INVENTORY_LIVE_JSON_FILE"
PROBE_FILE_ENV = "LABEL_INVENTORY_PROBE_FILE"
MIN_DECLARED_ENV = "LABEL_INVENTORY_MIN_DECLARED"
VERIFY_ALLOWLIST_ENV = "LABEL_INVENTORY_VERIFY_ALLOWLIST"

DEFAULT_LABELS_FILE = ".github/labels.yml"

# "Anti-vacuity on the declaration side. A parse that yields almost nothing is a
# broken parse (reindent, quoting change, wrong path), and treating it as a
# nearly-empty declaration set would make direction (b) scream about every live
# label while direction (a) stayed silent. Refuse instead."
DEFAULT_MIN_DECLARED = 5

# GitHub's create-time cap.
DESC_CAP = 100

# "<label>|<script that creates it>". Absence is forgiven for these and ONLY
# these. Keep it this short. Each entry's BLOCKER reason is in the module
# docstring, where a reviewer reads it.
CREATE_ON_DEMAND = (
    "nightly-red|.ci/scripts/ci/report-nightly-status.cjs",
    "ci|.ci/scripts/review/claude-review-gate.sh",
    "bump-none|.ci/scripts/review/claude-review-gate.sh",
)

# The declaration reader, as four sequential `sed`s. The ORDER is observable; see
# the port notes.
NAME_PREFIX = re.compile(r"^- name:[ \t]*")
DQUOTED = re.compile(r'^"(.*)"$')
SQUOTED = re.compile(r"^'(.*)'$")
TRAILING_SPACE = re.compile(r"[ \t]+$")

# The awk description scanner.
AWK_NAME = re.compile(r"^- name:")
AWK_NAME_PREFIX = re.compile(r"^- name:[ \t]*")
AWK_DESC = re.compile(r"^[ \t]+description:")
AWK_DESC_PREFIX = re.compile(r"^[ \t]+description:[ \t]*")
AWK_EDGE_QUOTE = re.compile(r'^"|"$')

# Section (c)'s parser, the twin's embedded python verbatim in shape.
DRIFT_NAME = re.compile(r"^\s*-\s*name:\s*(.+?)\s*$")
DRIFT_FIELD = re.compile(r"^\s*(description|color):\s*(.*)$")


class DriftUnreadableError(RuntimeError):
    """The drift comparison could not run.

    A DISTINCT TYPE, not a returned empty list, because those are exactly the two
    things the twin's `drift_rc` exists to keep apart: "the comparison ran and
    found nothing" and "the comparison never ran". Collapsing them is the
    swallowed-failure class check-swallowed-failures.sh already caught twice.
    """


def declared_labels(text: str) -> list[str]:
    """`grep -E '^- name:' | sed | sed | sed | sed`, one label per line.

    RETURNS AN EMPTY LIST FOR AN EMPTY FILE, never raising. That is the behaviour
    the twin only acquired at 96355d3b5; see the module docstring for what its
    absence disarmed.
    """
    out: list[str] = []
    for line in text.split("\n"):
        if not AWK_NAME.match(line):
            continue
        value = NAME_PREFIX.sub("", line, count=1)
        value = DQUOTED.sub(r"\1", value, count=1)
        value = SQUOTED.sub(r"\1", value, count=1)
        out.append(TRAILING_SPACE.sub("", value))
    return out


def desc_over_cap(text: str, cap: int = DESC_CAP) -> list[tuple[str, int]]:
    """Every declared description longer than `cap`, as (name, length).

    THE NAME IS WHATEVER `- name:` WAS SEEN LAST, exactly as the awk program
    carries it in a variable across records. A description line with no preceding
    name is therefore attributed to the empty string rather than skipped, which is
    the twin's behaviour on a malformed file.
    """
    out: list[tuple[str, int]] = []
    name = ""
    for line in text.split("\n"):
        if AWK_NAME.match(line):
            name = AWK_NAME_PREFIX.sub("", line, count=1)
            name = AWK_EDGE_QUOTE.sub("", name)
            continue
        if AWK_DESC.match(line):
            desc = AWK_DESC_PREFIX.sub("", line, count=1)
            desc = AWK_EDGE_QUOTE.sub("", desc)
            if len(desc) > cap:
                out.append((name, len(desc)))
    return out


def drift(live_json: str, labels_text: str) -> list[tuple[str, str, str]]:
    """Declared labels whose live description or colour disagrees.

    Raises `DriftUnreadableError` where the twin's child exits 1. Absence is section
    (a)'s job, not this one's, so a declared label missing from the live list is
    skipped here rather than reported twice.
    """
    try:
        parsed = json.loads(live_json)
        live = {entry["name"]: entry for entry in parsed}
    except Exception as exc:
        raise DriftUnreadableError("LIVE_JSON is not valid JSON: %s" % exc) from exc

    want: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in labels_text.split("\n"):
        match = DRIFT_NAME.match(line)
        if match:
            current = match.group(1).strip("\"'")
            want[current] = {}
            continue
        if current:
            field = DRIFT_FIELD.match(line)
            if field:
                want[current][field.group(1)] = field.group(2).strip().strip("\"'")

    out: list[tuple[str, str, str]] = []
    for name in sorted(want):
        declared = want[name]
        entry = live.get(name)
        if not entry:
            continue
        if (
            "description" in declared
            and (entry.get("description") or "") != declared["description"]
        ):
            out.append((name, "description", (entry.get("description") or "<empty>")[:70]))
        if "color" in declared and (entry.get("color") or "").lower() != declared[
            "color"
        ].lower().lstrip("#"):
            out.append((name, "color", str(entry.get("color"))))
    return out


def url_encode(name: str) -> str:
    """`jq -sRr @uri` when jq is present, else the space-only fallback.

    "Space is the only character in this repo's label names that needs it
    ('good first issue'); a name with anything more exotic would fail the probe
    loudly rather than silently, which is the safe direction."
    """
    try:
        proc = subprocess.run(
            ["jq", "-sRr", "@uri"],
            input=name,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.rstrip("\n")
    except (OSError, subprocess.SubprocessError):
        pass
    return name.replace(" ", "%20")


def probe_label(name: str, env: dict[str, str] | None = None) -> int:
    """0 exists, 1 confirmed absent, 2 could not probe.

    THREE OUTCOMES, NOT TWO, and that is the whole design. "Could not probe" is
    not "absent": a 403, a 500 or a network error says nothing about the label. In
    injected mode there is no API to re-read, so the injected list stands as its
    own authority and the probe reports "could not" (which REPORTS the finding,
    preserving the offline test seam).
    """
    environ = os.environ if env is None else env
    probe_file = environ.get(PROBE_FILE_ENV)
    if probe_file:
        path = pathlib.Path(probe_file)
        if not path.is_file():
            return 2
        names = path.read_text(encoding="utf-8", errors="replace").split("\n")
        return 0 if name in names else 1
    if environ.get(LIVE_FILE_ENV):
        return 2
    if _which("gh") is None:
        return 2
    proc = subprocess.run(
        ["gh", "api", "repos/{owner}/{repo}/labels/%s" % url_encode(name)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return 0
    combined = proc.stdout + proc.stderr
    if "HTTP 404" in combined or "Not Found" in combined:
        return 1
    return 2


def _which(name: str) -> str | None:
    """`command -v`, without importing shutil for one call."""
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 when the inventory reconciles, 1 otherwise.

    NEVER 0 ON A FAILED READ. Every path that cannot see the live list refuses,
    because "empty" would make direction (b) vacuously clean.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    os.chdir(root)
    labels_file = os.environ.get(LABELS_FILE_ENV) or DEFAULT_LABELS_FILE
    min_declared = int(os.environ.get(MIN_DECLARED_ENV) or DEFAULT_MIN_DECLARED)

    labels_path = pathlib.Path(labels_file)
    if not labels_path.is_file():
        log.error("labels file not found: %s" % labels_file)
        return 1

    labels_text = labels_path.read_text(encoding="utf-8", errors="replace")
    declared = declared_labels(labels_text)
    declared_count = len([name for name in declared if name != ""])

    if declared_count < min_declared:
        log.error(
            "only %d label(s) parsed from %s (floor: %d). The file carries more than that, "
            "so this reader is broken, not the file." % (declared_count, labels_file, min_declared)
        )
        return 1

    # ---- the description cap, control-first --------------------------------
    control = desc_over_cap('- name: control-label\n  description: "%s"\n' % ("x" * 101))
    if not control:
        log.error(
            "description-cap control did not fire on a planted 101-char description; the "
            "checker is broken, refusing to certify anything"
        )
        return 1
    over = desc_over_cap(labels_text)
    if over:
        for name, length in over:
            log.error(
                "label '%s' declares a %d-char description; GitHub rejects anything over %d at "
                "create time, so this fails exactly when something finally tries to create or "
                "sync it. Shorten it in %s." % (name, length, DESC_CAP, labels_file)
            )
        return 1

    # ---- the live list -----------------------------------------------------
    live_file = os.environ.get(LIVE_FILE_ENV)
    if live_file:
        live_path = pathlib.Path(live_file)
        if not live_path.is_file():
            log.error(
                "%s is set to '%s' but no such file exists; this gate cannot read the live "
                "label list and refuses to pass blind" % (LIVE_FILE_ENV, live_file)
            )
            return 1
        live = [
            TRAILING_SPACE.sub("", line)
            for line in live_path.read_text(encoding="utf-8", errors="replace").split("\n")
        ]
        live = [name for name in live if name != ""]
        live_source = "%s (injected)" % live_file
    else:
        if _which("gh") is None:
            log.error(
                "gh is not installed, so the live label list cannot be read. This gate "
                "reconciles the tree against the REAL repo; without that read it asserts "
                "nothing and refuses to pass blind."
            )
            return 1
        proc = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}/labels", "--paginate", "--jq", ".[].name"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            # `2>&1` in the twin: the error text becomes the value.
            log.error(
                "could not read the live label list from GitHub: %s"
                % (proc.stdout + proc.stderr).rstrip("\n")
            )
            log.error(
                "This gate refuses to pass blind. Authenticate (gh auth login / GH_TOKEN) "
                "and re-run."
            )
            return 1
        live = [TRAILING_SPACE.sub("", line) for line in proc.stdout.split("\n")]
        live = [name for name in live if name != ""]
        live_source = "GitHub API"

    live_count = len(live)
    if live_count == 0:
        log.error(
            "the live label list read from %s is EMPTY. A repo with zero labels is not a "
            "state this repo can be in, so this is a failed read, not a clean tree -- and an "
            "empty list would make half this gate vacuously green." % live_source
        )
        return 1

    # ---- allowlist hygiene -------------------------------------------------
    verify = os.environ.get(VERIFY_ALLOWLIST_ENV)
    if not verify:
        verify = "true" if labels_file == DEFAULT_LABELS_FILE else "false"

    allowed: list[str] = []
    for entry in CREATE_ON_DEMAND:
        name, _, creator = entry.partition("|")
        if verify == "true" and name not in declared:
            log.error(
                "create-on-demand allowlist names '%s', which is not declared in %s. Remove "
                "the allowlist entry or declare the label." % (name, labels_file)
            )
            return 1
        creator_path = pathlib.Path(creator)
        if not creator_path.is_file():
            log.error(
                "create-on-demand allowlist says '%s' creates '%s', but that file does not "
                "exist. The exemption is stale: nothing creates the label any more."
                % (creator, name)
            )
            return 1
        if name not in creator_path.read_text(encoding="utf-8", errors="replace"):
            log.error(
                "create-on-demand allowlist says '%s' creates '%s', but that file does not "
                "mention it. The exemption is stale." % (creator, name)
            )
            return 1
        allowed.append(name)

    problems = 0

    # ---- (a) declared but absent live --------------------------------------
    for label in declared:
        if not label:
            continue
        if label in live:
            continue
        if label in allowed:
            log.info(
                "'%s' is declared and absent, which is expected: it is created on demand "
                "(see the allowlist in this script)." % label
            )
            continue
        if probe_label(label) == 0:
            log.warn(
                "'%s' was missing from the label list but a direct re-read found it. The list "
                "read was stale (the repo's labels were being edited mid-run); dropping the "
                "finding rather than accusing a live label of deletion." % label
            )
            continue
        log.error(
            "label '%s' is declared in %s but does NOT exist on the repo. Any workflow that "
            "searches or filters on it FAILS OPEN -- a search for a nonexistent label returns "
            "zero results rather than an error, which is exactly how 'rollback' let stable "
            "promotion proceed past a rolled-back PR. Create it: gh label create '%s'"
            % (label, labels_file, label)
        )
        problems += 1

    # ---- (b) live but undeclared -------------------------------------------
    for label in live:
        if not label:
            continue
        if label in declared:
            continue
        log.error(
            "label '%s' exists on the repo but is declared nowhere in %s. Nothing in the tree "
            "records that it exists, and it cannot reach the PR label guide, so it is a label "
            "people can apply and nobody can look up. Declare it (name/color/description, plus "
            "'guide: false' if it should stay off the PR guide) or delete it: gh label delete "
            "'%s'" % (label, labels_file, label)
        )
        problems += 1

    # ---- (c) present in both, but a field has drifted ----------------------
    live_json = ""
    live_json_file = os.environ.get(LIVE_JSON_FILE_ENV)
    if live_json_file:
        try:
            live_json = pathlib.Path(live_json_file).read_text(encoding="utf-8", errors="replace")
        except OSError:
            live_json = ""
    elif live_source == "GitHub API":
        proc = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}/labels", "--paginate"],
            capture_output=True,
            text=True,
            check=False,
        )
        live_json = proc.stdout if proc.returncode == 0 else ""

    if live_json and labels_file == DEFAULT_LABELS_FILE:
        try:
            drifted = drift(live_json, labels_text)
        except DriftUnreadableError as exc:
            print("%s" % exc, file=sys.stderr)
            log.error(
                "regions/labels drift comparison FAILED to run (exit 1). An unreadable "
                "comparison is never a clean tree."
            )
            return 1
        for name, field, value in drifted:
            log.error(
                "label '%s' has a drifted %s: the repo says '%s', %s says something else. The "
                "description is what every human reads in the label picker, so a drifted one "
                "is documentation that lies. Push the declared values: gh api --method PATCH "
                "repos/{owner}/{repo}/labels/%s -f %s='<value from %s>'"
                % (name, field, value, labels_file, name, field, labels_file)
            )
            problems += 1

    if problems > 0:
        log.error(
            "%d label inventory mismatch(es) between %s and the live repo."
            % (problems, labels_file)
        )
        return 1

    log.info(
        "label inventory reconciled: %d declared, %d live (source: %s); names, descriptions "
        "and colours all agree" % (declared_count, live_count, live_source)
    )
    return 0


def selftest() -> int:
    """Both directions on every reader, and on the three-outcome probe.

    THE FLOOR IS DERIVED from the case corpus, so a case that stops running turns
    the suite red rather than quietly shortening it.
    """
    declared_cases = [
        ("a plain declaration", "- name: alpha\n  color: fff\n", ["alpha"]),
        ("two declarations", "- name: alpha\n- name: beta\n", ["alpha", "beta"]),
        ("double quotes are stripped", '- name: "alpha"\n', ["alpha"]),
        ("single quotes are stripped", "- name: 'alpha'\n", ["alpha"]),
        ("trailing whitespace is stripped", "- name: alpha   \n", ["alpha"]),
        # THE UNQUOTING ORDER BUG, CARRIED. The trailing-space strip runs AFTER
        # the unquote, so the anchors fail and the quotes survive.
        ("quotes plus trailing space keep the quotes", '- name: "alpha"  \n', ['"alpha"']),
        # NEGATIVES: an indented name is not a declaration, and neither is prose.
        ("an indented name is not a declaration", "  - name: alpha\n", []),
        ("a comment is not a declaration", "# - name: alpha\n", []),
        # THE 96355d3b5 CASE.
        ("an empty file yields no declarations, and does not raise", "", []),
    ]
    cap_cases = [
        (
            "a 101-char description is over the cap",
            '- name: a\n  description: "%s"\n' % ("x" * 101),
            1,
        ),
        # THE BOUNDARY, both sides of it. 100 is allowed; 101 is not.
        ("a 100-char description is not", '- name: a\n  description: "%s"\n' % ("x" * 100), 0),
        (
            "an unquoted long description is measured too",
            "- name: a\n  description: %s\n" % ("x" * 101),
            1,
        ),
        ("a short description is silent", "- name: a\n  description: short\n", 0),
    ]
    drift_cases = [
        (
            "a drifted description is reported",
            '[{"name":"a","description":"live text","color":"fff"}]',
            "- name: a\n  description: declared text\n",
            [("a", "description", "live text")],
        ),
        (
            "an agreeing description is silent",
            '[{"name":"a","description":"same","color":"fff"}]',
            "- name: a\n  description: same\n",
            [],
        ),
        (
            "a drifted colour is reported, case-insensitively and hash-insensitively",
            '[{"name":"a","color":"ABCDEF"}]',
            "- name: a\n  color: '#123456'\n",
            [("a", "color", "ABCDEF")],
        ),
        (
            "the same colour in a different case is silent",
            '[{"name":"a","color":"ABCDEF"}]',
            "- name: a\n  color: '#abcdef'\n",
            [],
        ),
        (
            # ABSENCE IS SECTION (a)'S JOB. Reporting it here too would double every
            # finding on a label that does not exist.
            "a declared label absent from the live list is not a drift",
            "[]",
            "- name: a\n  description: x\n",
            [],
        ),
    ]

    floor = len(declared_cases) + len(cap_cases) + len(drift_cases) + 7
    ctl = Controls("label-inventory", floor=floor)

    for label, text, want in declared_cases:
        ctl.check("declared: %s" % label, declared_labels(text), want)
    for label, text, want in cap_cases:
        ctl.check("cap: %s" % label, len(desc_over_cap(text)), want)
    for label, live_json, labels_text, want in drift_cases:
        ctl.check("drift: %s" % label, drift(live_json, labels_text), want)

    # AN UNREADABLE COMPARISON IS NEVER A CLEAN TREE. This is the assertion the
    # twin's separate `drift_rc` capture exists to make possible.
    ctl.raises(
        "drift: malformed JSON raises rather than returning []",
        DriftUnreadableError,
        drift,
        "{",
        "",
    )
    ctl.raises("drift: a truncated array raises", DriftUnreadableError, drift, '[{"name":"a"', "")

    # THE PROBE HAS THREE OUTCOMES AND THEY ARE NOT INTERCHANGEABLE.
    with tempfile.TemporaryDirectory() as tmp:
        present = pathlib.Path(tmp) / "probe.txt"
        present.write_text("alpha\nbeta\n", encoding="utf-8")
        env = {PROBE_FILE_ENV: str(present)}
        ctl.check("probe: a listed label exists", probe_label("alpha", env), 0)
        ctl.check("probe: an unlisted label is CONFIRMED absent", probe_label("gamma", env), 1)
        missing = {PROBE_FILE_ENV: str(pathlib.Path(tmp) / "nope.txt")}
        ctl.check(
            "probe: an unreadable probe file is 'could not', not 'absent'",
            probe_label("alpha", missing),
            2,
        )
        ctl.check(
            "probe: injected-list mode cannot re-read, so it is 'could not'",
            probe_label("alpha", {LIVE_FILE_ENV: "x"}),
            2,
        )

    # THE ALLOWLIST STAYS SHORT AND EVERY ENTRY NAMES ITS CREATOR.
    ctl.check("the allowlist has three entries", len(CREATE_ON_DEMAND), 3)
    ctl.truthy(
        "every allowlist entry names a creator",
        all("|" in entry and entry.split("|", 1)[1] for entry in CREATE_ON_DEMAND),
    )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
