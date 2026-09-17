r"""Every GitHub label the code names must be declared in `.github/labels.yml`.

Ported from `.ci/scripts/quality/check-label-references.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live.

WHY THIS EXISTS, in the twin's own words, because the failure was silent:

    Labels are the repo's kill switches and routing flags, and nothing used to
    connect the code that reads them to the labels that exist: `full-ci` (the
    scope engine's documented kill switch), `autopilot`, `autopilot-blocked` and
    `rollback` were all referenced by merged code for weeks while not existing on
    the repo at all. The worst failure mode is SILENT fail-open:
    promote-stable.yml searched on the `rollback` label, and a search for a
    nonexistent label returns zero PRs, so the promotion block simply never
    fired. (The twin writes that search term in its own consumption shape; this
    file writes it in prose, because this file is not excluded from the sweep and
    the shape would match itself.)

    Declaring in labels.yml is the tracked, reviewable half; creating the label
    live is one `gh label create`. This gate enforces the tracked half, in the
    code -> labels.yml direction only (a declared label nothing references is
    inventory, not an error).

    HOW LABELS ARE FOUND. A curated pattern set, one per consumption shape that
    exists in the tree. Each pattern is SELF-TESTED against a planted sample line
    before the sweep, so a regex that silently stops matching turns the gate red
    instead of quietly under-reporting (the check-silent-failure gate scanned zero
    files for weeks; that class of death is the one to design out). A floor on the
    total distinct labels found catches a broken sweep the self-tests cannot (for
    example a bad SCAN_DIRS path).

THE SELF-EXCLUSION IS NOT A CONVENIENCE, and the twin explains the one thing that makes it safe: "This script and its test carry PLANTED sample lines (the self-test below and the test's fixtures): instrument fixtures, not label references. Both are excluded by basename, which cannot affect the self-test because its sample files are named sample.txt."

THE ARCHAEOLOGY THAT GETS TIDIED OUT, AND MUST NOT BE. The twin was FIXED at commit 96355d3b5 on 2026-09-06, and the fix is one `|| true` that looks like noise:

    `|| true` IS LOAD-BEARING: grep exits 1 on a file that declares no labels and
    `set -e` then killed this script silently, before anything could say so.
    Reproduced 2026-09-06 with LABEL_REFS_LABELS_FILE pointed at an empty file.

That is the whole shape of the class: a bare `grep` in a command substitution under `set -e` kills the program AT THE ASSIGNMENT, so the handler written for the empty case never runs. The Python port cannot reproduce the defect (an empty `findall` is an empty list, not a fatal status), which is exactly why the note has to survive as prose: a reader who deletes it from the twin
deletes the reason the twin can report anything about an empty labels file.

A SECOND `|| true`, in the site listing, for the same reason and a different consequence, also carried:

    `|| true` because this runs under `set -o pipefail` and grep exits 1 on
    no-match: without it, a label whose site list came up empty would KILL the
    sweep mid-report instead of naming the finding it just made. Display-only
    value, so an empty result is legitimate here.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE PATTERNS ARE PARALLEL LISTS, NOT A DICT, and the twin says why: "They are kept as parallel arrays because bash 4 associative arrays lose ordering and the self-test error should name the pattern that died." Python dicts preserve insertion order, so one ordered mapping expresses both halves; the ORDER is still the observable part, because the self-test reports the FIRST pattern
that fails and stops.

THE grep THAT RUNS THIS GATE IS GNU grep 3.12 AT `/usr/bin/grep`, which is what a SCRIPT resolves `grep` to on this host. Measured 2026-09-06 with a two-file specimen: `-r` does not descend a directory symlink, and a file containing a NUL byte contributes NOTHING TO STDOUT -- with `-o` GNU grep prints no matching text
for it, only `grep: <path>: binary file matches` on STDERR, which every extractor
here sends to /dev/null. Both are reproduced, so the corpus the port sweeps is the corpus the twin sweeps.

AN INTERACTIVE CLAUDE CODE SHELL DEFINES `grep` AS A FUNCTION wrapping a bundled
ugrep 7.8.4 with `-G --ignore-files --hidden -I --exclude-dir=.git ...`. A probe
run at the prompt therefore measures a DIFFERENT PROGRAM than the gate runs, and the two disagree on `\x27`, on binary reporting and on which files are searched. Probe with `/usr/bin/grep`, or from inside a script file.

`-h` MEANS THE FILENAME IS NOT PART OF THE MATCH, which matters for the `js-labels-array` pattern: that one greps whole LINES and then pulls quoted tokens out of them, so a filename containing a quoted segment would contribute labels if `-h` were dropped. The port reproduces `-h` by matching against line text only.

THE FILTERS RUN IN THE TWIN'S ORDER: blank lines first, then anything containing
`$`, `{` or `}`. Reordering them would not change the result today and would
change it the day a pattern starts emitting a value that is blank AND templated.

SITES ARE A DISPLAY-ONLY GREP AND ARE MATCHED AS A BASIC REGULAR EXPRESSION, not as a literal. A label containing `.` therefore matches any character in that position, which over-reports sites and under-reports nothing. Carried, because the value is only ever printed. The site grep also carries NO `--exclude`, unlike the ten extraction greps, so an instrument file can be listed as
a site for a label it does not contribute; that asymmetry is the twin's and is reproduced.

SITE ORDER IS FILESYSTEM STATE, NOT REPOSITORY CONTENT, AND THE TWO SIDES NEED NOT
AGREE ON IT. `grep -rl` emits in the order its directory walk produces and `os.walk` does the same, and the two orders are NOT the same walk: measured 2026-09-06 over one directory of four files, ugrep 7.8.4 returned bravo, mike, zeta, alpha and `os.walk` returned bravo, mike, alpha, zeta. So a finding naming TWO OR MORE sites can differ between the implementations in the order of
that one bracketed list, while naming the same set. This is not fixable by sorting: sorting would guarantee a difference wherever the twin's readdir order is not sorted, which is most of the time. It is stated here because it is the one place this port is not byte-deterministic against its twin, and because the differential specimens are therefore built with exactly one site per
finding.
"""

import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The environment seams, spelled as the twin spells them. The test drives all three; the defaults are the real surfaces.
LABELS_FILE_ENV = "LABEL_REFS_LABELS_FILE"
SCAN_DIRS_ENV = "LABEL_REFS_SCAN_DIRS"
MIN_DISTINCT_ENV = "LABEL_REFS_MIN_DISTINCT"

DEFAULT_LABELS_FILE = ".github/labels.yml"
# Space-separated for the test seam; defaults to the real surfaces.
DEFAULT_SCAN_DIRS = ".github .ci"
# "The tree carries well over this many distinct referenced labels; finding fewer means the sweep itself broke (wrong root, bad glob), not a clean tree."
DEFAULT_MIN_DISTINCT = 8

# Excluded by BASENAME, because both files carry planted sample lines that are instrument fixtures rather than label references.
GREP_EXCLUDES = ("check-label-references.sh", "test-label-references.sh")

# The token every planted sample must yield, ASSEMBLED rather than written.
#
# THIS FILE WOULD OTHERWISE POISON THE GATE IT IMPLEMENTS, and it did: the first draft carried the ten sample lines as literals, so the real sweep over `.ci` found `selftest-label` in this very file and reported it as an undeclared label reference. The twin dodges that by excluding its OWN basename, and its comment says why: "This script and its test carry PLANTED sample lines ...
# instrument fixtures, not label references." A second basename exclusion would work too, and would be worse: it would make the port scan a corpus the twin does not, so the two would disagree on the real tree for a reason that has nothing to do with labels. Assembling the shapes at runtime removes the reason instead of hiding it, which is the same treatment `dead_case_arms.py` and
# `pipefail_grep_q.py` already give to a gate that must not match its own text.
SELFTEST_LABEL = "selftest" + "-label"

# One entry per consumption shape that exists in the tree, in the twin's order. `extract` is (line-matcher, capture) and `sample` is the planted line that must yield SELFTEST_LABEL. Keeping the sample beside the pattern is the whole design: a pattern that silently stops matching turns the gate red instead of quietly under-reporting.
PATTERNS: dict[str, dict[str, object]] = {
    "workflow-contains": {
        "find": re.compile(r"labels\.\*\.name, '[A-Za-z0-9._:-]+'"),
        "capture": re.compile(r".*'([^']+)'.*"),
        "sample": "if: contains(github.event.pull_request.labels.*.name, '%s')" % SELFTEST_LABEL,
    },
    "gh-api-labels-array": {
        "find": re.compile(r"labels\[\]=[A-Za-z0-9._:-]+"),
        "capture": re.compile(r".*labels\[\]="),
        "strip": True,
        "sample": "gh api -f 'labels[]=%s'" % SELFTEST_LABEL,
    },
    "search-filter": {
        "find": re.compile(r"label:[A-Za-z0-9._-]+"),
        "capture": re.compile(r"^label:"),
        "strip": True,
        "sample": '--search "merged:>=X label:%s"' % SELFTEST_LABEL,
    },
    "js-includes": {
        "find": re.compile(r"labels\.includes\('[A-Za-z0-9._:-]+'\)"),
        "capture": re.compile(r".*'([^']+)'.*"),
        "sample": "if (labels.includes('%s')) {" % SELFTEST_LABEL,
    },
    "js-label-const": {
        "find": re.compile(r"ISSUE_LABEL = '[A-Za-z0-9._:-]+'"),
        "capture": re.compile(r".*'([^']+)'.*"),
        "sample": "const ISSUE_LABEL = '%s';" % SELFTEST_LABEL,
    },
    "js-labels-array": {
        # Quoted strings on a line declaring a *_LABELS array literal. The only pattern that matches a whole LINE and then extracts from it.
        "line": re.compile(r"_LABELS = \["),
        "find": re.compile(r"'[A-Za-z0-9._:-]+'"),
        "unquote": True,
        "sample": "const ISSUE_LABELS = ['%s', OTHER];" % SELFTEST_LABEL,
    },
    "jq-arg-label": {
        # autopilot-gate.sh passes the label under test as a jq argument named `l`. The twin's comment spells that shape out inline; this one does not, because the twin is excluded by basename and this file is not, and the spelled-out form matched itself and reported `...` as a label.
        "find": re.compile(r'--arg l "[A-Za-z0-9._:-]+"'),
        "capture": re.compile(r'.*"([^"]+)".*'),
        "sample": 'jq -e --arg l "%s" query' % SELFTEST_LABEL,
    },
    "var-default-yml": {
        "find": re.compile(r"AUTOPILOT_LABEL \|\| '[A-Za-z0-9._:-]+'"),
        "capture": re.compile(r".*'([^']+)'.*"),
        "sample": "LABEL: ${{ vars.AUTOPILOT_LABEL || '%s' }}" % SELFTEST_LABEL,
    },
    "var-default-sh": {
        "find": re.compile(r"AUTOPILOT_LABEL:-[A-Za-z0-9._:-]+"),
        "capture": re.compile(r".*AUTOPILOT_LABEL:-"),
        "strip": True,
        "sample": 'LABEL="${AUTOPILOT_LABEL:-%s}"' % SELFTEST_LABEL,
    },
    "grep-exact-label": {
        # detect-bump-type.sh matches PR labels with `grep -qx "<label>"`;
        # verified the only -qx uses in the surfaces are label matches.
        "find": re.compile(r'grep -qx "[A-Za-z0-9._:-]+"'),
        "capture": re.compile(r'.*"([^"]+)".*'),
        "sample": 'echo "$labels" | grep -qx "%s"' % SELFTEST_LABEL,
    },
}

# `grep -E '^- name:'` then two `sed`s. The trailing-space strip is separate in the twin and is kept separate here.
DECLARED_RE = re.compile(r"^- name:[ \t]*")
TRAILING_SPACE = re.compile(r"[ \t]+$")

# The two post-filters, in the twin's order.
BLANK_RE = re.compile(r"^\s*$")
TEMPLATE_RE = re.compile(r"[${}]")


def split_dirs(value: str) -> list[str]:
    """Bash word-splitting on unquoted `$SCAN_DIRS`. Whitespace, no globbing."""
    return value.split()


def walk_text(root: pathlib.Path, *, apply_excludes: bool = True):
    """Every file `grep -r` would read under `root`, as (path, text).

    THREE BEHAVIOURS REPRODUCED, each measured against ugrep 7.8.4 on 2026-09-06: a directory symlink is not descended, a file symlink is skipped, and a file containing a NUL byte produces NOTHING AT ALL (ugrep does not even print `Binary file X matches`). The last one is the surprising half, and a port that decoded binary files anyway would find labels the twin cannot see.
    """
    if root.is_file() and not root.is_symlink():
        candidates = [root]
    elif root.is_dir():
        candidates = []
        for dirpath, _dirnames, filenames in paths.walk_tree(root):
            candidates.extend(pathlib.Path(dirpath) / name for name in filenames)
    else:
        return
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            continue
        if apply_excludes and path.name in GREP_EXCLUDES:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        yield path, data.decode("utf-8", "replace")


def extract(name: str, targets: list[pathlib.Path]) -> list[str]:
    """One pattern's labels, in first-seen order, WITH duplicates.

    The twin's `extract` prints one label per line and the caller sorts and deduplicates afterwards, so duplicates are the honest intermediate value; a
    port that deduplicated here would make the self-test's `!= "selftest-label"`
    comparison pass for a pattern that matched twice.
    """
    spec = PATTERNS.get(name)
    if spec is None:
        log.error("unknown pattern: %s" % name)
        raise SystemExit(1)
    out: list[str] = []
    line_re = spec.get("line")
    find_re = spec["find"]
    for target in targets:
        for _path, text in walk_text(target):
            for raw in text.split("\n"):
                if line_re is not None and not line_re.search(raw):
                    continue
                out.extend(_capture(spec, hit) for hit in find_re.findall(raw))
    return out


def _capture(spec: dict, hit: str) -> str:
    """The `sed` stage of one pattern: a substitution, not a match.

    THREE SHAPES, and they are not interchangeable. A capture group replaces the whole matched text with group 1; a `strip` pattern deletes a prefix; and `unquote` removes every quote character (`s/'//g`), which is what the `js-labels-array` pattern does after pulling quoted tokens off a line.
    """
    if spec.get("unquote"):
        return hit.replace("'", "")
    capture = spec.get("capture")
    if capture is None:
        return hit
    if spec.get("strip"):
        return capture.sub("", hit, count=1)
    return capture.sub(r"\1", hit, count=1)


def declared_labels(text: str) -> list[str]:
    """`grep -E '^- name:' | sed ...`, one label per line.

    RETURNS AN EMPTY LIST FOR AN EMPTY FILE rather than raising, which is the behaviour the twin only acquired at 96355d3b5. See the module docstring: the missing `|| true` killed the script at the assignment and the floor below it could never fire.
    """
    out: list[str] = []
    for line in text.split("\n"):
        if not DECLARED_RE.match(line):
            continue
        out.append(TRAILING_SPACE.sub("", DECLARED_RE.sub("", line, count=1)))
    return out


def sites_for(label: str, scan_dirs: list[str], base: pathlib.Path) -> str:
    """`grep -rln "$label" $SCAN_DIRS | head -5 | tr '\\n' ' '`.

    DISPLAY ONLY. The label is used as a BASIC regular expression by the twin, so a `.` in it matches any character; that over-reports sites and is carried rather than corrected, because narrowing it would change printed text for no gain in what the gate rules on.
    """
    needle = re.compile(label)
    found: list[str] = []
    for spec in scan_dirs:
        root = pathlib.Path(spec)
        absolute = root if root.is_absolute() else base / root
        # NO EXCLUSIONS HERE, and that asymmetry is the twin's. The extraction
        # greps carry `--exclude=check-label-references.sh --exclude=test-label-
        # references.sh`; this one does not, so a label whose only mention is inside an excluded instrument file is still LISTED as a site while not counting as a reference. Reproduced, because the first draft applied the exclusions here too and dropped a site the twin prints.
        for path, text in walk_text(absolute, apply_excludes=False):
            if needle.search(text):
                try:
                    suffix = path.relative_to(absolute)
                    found.append(os.path.join(spec, str(suffix)))
                except ValueError:  # pragma: no cover - defensive
                    found.append(str(path))
            if len(found) >= 5:
                break
        if len(found) >= 5:
            break
    return "".join("%s " % name for name in found[:5])


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 when every referenced label is declared, 1 otherwise.

    `--selftest` is intercepted BEFORE any file is read. The twin runs its pattern self-test inline on every invocation and takes no arguments; this flag drives the same controls plus their mirrors.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    os.chdir(root)
    labels_file = os.environ.get(LABELS_FILE_ENV) or DEFAULT_LABELS_FILE
    scan_dirs_text = os.environ.get(SCAN_DIRS_ENV) or DEFAULT_SCAN_DIRS
    min_distinct = int(os.environ.get(MIN_DISTINCT_ENV) or DEFAULT_MIN_DISTINCT)
    scan_dirs = split_dirs(scan_dirs_text)

    labels_path = pathlib.Path(labels_file)
    if not labels_path.is_file():
        log.error("labels file not found: %s" % labels_file)
        return 1

    # ---- the self-test, before the sweep --------------------------------- "A pattern that cannot fire is a pattern that silently stopped protecting its consumption shape." The sample files are named sample.txt, which is why the basename exclusions above cannot mask this.
    with tempfile.TemporaryDirectory() as selftest_dir:
        sample = pathlib.Path(selftest_dir) / "sample.txt"
        for name, spec in PATTERNS.items():
            sample.write_text("%s\n" % spec["sample"], encoding="utf-8")
            got = "\n".join(extract(name, [sample]))
            if got != SELFTEST_LABEL:
                log.error(
                    "SELF-TEST FAILED: pattern '%s' extracted '%s' from its planted sample; "
                    "the extractor is broken and the sweep would silently under-report"
                    % (name, got or "<nothing>")
                )
                return 1

    # ---- the sweep --------------------------------------------------------
    targets = [pathlib.Path(spec) for spec in scan_dirs]
    swept: set[str] = set()
    for name in PATTERNS:
        swept.update(extract(name, targets))
    found = sorted(swept)

    # "'ubuntu-slim' etc. cannot appear: patterns anchor on label-consuming shapes, not on generic strings. Still, drop anything that is obviously a template placeholder rather than a literal."
    found = [
        label for label in found if not BLANK_RE.match(label) and not TEMPLATE_RE.search(label)
    ]

    distinct = len([label for label in found if label != ""])
    if distinct < min_distinct:
        log.error(
            "sweep found only %d distinct label reference(s) (floor: %d). The tree carries "
            "more than that, so the sweep itself is broken (wrong root or dead glob), not "
            "clean." % (distinct, min_distinct)
        )
        return 1

    declared = declared_labels(labels_path.read_text(encoding="utf-8", errors="replace"))

    missing = 0
    for label in found:
        if not label:
            continue
        if label in declared:
            continue
        # Name every referencing site so the fix needs no re-discovery.
        sites = sites_for(label, scan_dirs, root)
        log.error(
            "label '%s' is referenced by code but not declared in %s (sites: %s)"
            % (label, labels_file, sites)
        )
        missing += 1

    if missing > 0:
        log.error(
            "%d undeclared label reference(s). Declare them in %s and create them live with "
            "'gh label create' if absent." % (missing, labels_file)
        )
        return 1

    log.info("all %d code-referenced labels are declared in %s" % (distinct, labels_file))
    return 0


def selftest() -> int:
    """Every pattern fires on its own sample AND stays silent on a decoy.

    THE TWIN HAS ONLY THE POSITIVE HALF. Its inline self-test proves each pattern can match its planted sample; nothing proves a pattern does not match everything. A pattern degraded to `[A-Za-z0-9._:-]+` would pass all ten of the twin's checks and then report every identifier in the tree as an undeclared label. So each pattern here is also run against a decoy line that names
    `selftest-label` in a shape it does not consume.

    THE FLOOR IS DERIVED from the pattern registry, so adding a consumption shape without a sample turns this red rather than quietly shrinking the suite.
    """
    decoy = "a bare mention of %s in prose, and nothing that consumes it" % SELFTEST_LABEL
    floor = 2 * len(PATTERNS) + 6
    ctl = Controls("label-references", floor=floor)

    with tempfile.TemporaryDirectory() as tmp:
        sample = pathlib.Path(tmp) / "sample.txt"
        for name, spec in PATTERNS.items():
            sample.write_text("%s\n" % spec["sample"], encoding="utf-8")
            ctl.check(
                "%s fires on its own sample" % name, extract(name, [sample]), [SELFTEST_LABEL]
            )
            sample.write_text("%s\n" % decoy, encoding="utf-8")
            ctl.check("%s stays silent on a decoy line" % name, extract(name, [sample]), [])

        # THE EXCLUSION IS BY BASENAME AND MUST NOT SWALLOW THE SAMPLES.
        excluded = pathlib.Path(tmp) / "check-label-references.sh"
        excluded.write_text("%s\n" % PATTERNS["search-filter"]["sample"], encoding="utf-8")
        ctl.check(
            "an excluded basename contributes nothing",
            extract("search-filter", [pathlib.Path(tmp) / "check-label-references.sh"]),
            [],
        )

        # BINARY FILES ARE INVISIBLE TO ugrep, so they must be invisible here.
        binary = pathlib.Path(tmp) / "b.bin"
        # ASSEMBLED, like every other sample in this file: written as a literal it is a search-filter reference, and the real sweep reads this file.
        binary.write_bytes(("label:%s\x00\n" % SELFTEST_LABEL).encode())
        ctl.check(
            "a file with a NUL byte contributes nothing", extract("search-filter", [binary]), []
        )

    # -- the declaration reader, both directions ----------------------------
    ctl.check(
        "declared labels parse, trailing space stripped",
        declared_labels("- name: alpha  \n  color: red\n- name: beta\n"),
        ["alpha", "beta"],
    )
    # THE 96355d3b5 CASE. An empty file yields an EMPTY LIST, never a fatal exit, so the floor below it can actually fire.
    ctl.check("an empty labels file yields no declarations", declared_labels(""), [])
    ctl.check("an indented name: is not a declaration", declared_labels("  - name: x\n"), [])

    # -- the two post-filters -----------------------------------------------
    ctl.check("a templated value is dropped", bool(TEMPLATE_RE.search("${{ vars.X }}")), True)
    ctl.check("a real label is not dropped", bool(TEMPLATE_RE.search("full-ci")), False)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
