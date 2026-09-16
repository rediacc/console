"""AI-slop patterns in markdown content, at two severities.

Ported from `.ci/scripts/quality/check-content-quality.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live side by side until a
committed differential ledger says otherwise.

WHAT THE TWIN ENFORCES, carried over from its own header because the list is the
gate and a paraphrase of it would be a different gate:

    Scans markdown documentation and blog posts against the banned phrase list
    defined in .ci/config/content-quality-patterns.conf

    Two severity levels:
      ERROR - Blocks CI (exit 1)
      WARN  - Informational only (logged but does not block)

    Suppression:
      1. Inline: append <!-- slop-ok --> to any line
      2. File-level: add path to .ci/config/content-quality-allowlist.txt
      3. Code blocks: lines inside ``` fenced blocks are skipped automatically
      4. Frontmatter: YAML frontmatter (between --- markers) is skipped

The patterns file carries its own fix guidance, and it is the reason this gate
exists rather than a spell-checker: "Restructure the sentence using periods,
commas, colons, or parentheses. Do NOT replace em dashes or double dashes with
spaced hyphens ( - ). A spaced hyphen is the same AI tell in different clothing."

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TWIN'S OWN CLOSING COMMENT IS CARRIED, because it records a REMOVED check
and the reason a future reader must not re-add it:

    NOTE: Double-dash ( -- ) detection was removed because ` -- ` is a
    legitimate CLI argument separator (e.g., `renet compose -- up -d`,
    `npm run dev -- --host`). Detecting it requires understanding whether
    the context is prose or a command, which grep cannot distinguish
    reliably. The em dash pattern (U+2014) in the patterns file catches
    the actual AI tell.

BLANK IS "ONLY SPACES", NOT "ONLY WHITESPACE". The twin tests
`[[ -z "${line// /}" ]]`, which deletes SPACE characters and nothing else, so a
line holding a single TAB is not blank and becomes a pattern. `str.strip()`
would silently widen that and change which patterns load, so the port deletes
exactly the space character.

THE PATTERN LIST IS ORDERED AND THE ORDER IS OBSERVABLE. `identify_pattern`
returns the FIRST pattern that matches, and the two loops inside it do not scan
the list once: every short pattern is tried before any long one. So the reported
"Pattern:" for a line matching both a short and a long pattern is the short one
regardless of file order. Reproduced loop for loop rather than folded into a
single pass.

"SHORT" IS MEASURED IN BYTES, WHICH IS THE TWIN'S BEHAVIOUR UNDER LC_ALL=C AND
NOT UNDER A UTF-8 LOCALE. `${#p}` counts characters when the locale is UTF-8 and
BYTES when it is C, so the em dash pattern (U+2014, one character, three bytes)
is length 1 or length 3 depending on an environment variable. Both are <= 3, so
the live pattern set classifies identically either way and nothing observable
turns on it today. A future two-character non-ASCII pattern would be 2 under
UTF-8 and 4 or 6 under C, and the twin would take a different branch on two
machines. That is a defect in the twin, reported rather than repaired; the port
follows the C-locale reading because `scripts/lib/shadow-gate.ts` pins LC_ALL=C
and that is the behaviour the differential compares against.

THE FAST PATH IS CASE SENSITIVE AND THE SLOW PATH IS NOT. `[[ "$line" == *"$p"* ]]`
is a literal substring test; `grep -iqE "$p"` is case insensitive. So a line that
grep matched case-insensitively against a SHORT pattern can fall through the fast
path, be re-tested by the slow path (which skips short patterns), and be reported
as "(unknown)". That is real twin behaviour and it is preserved: a port that
"fixed" it would print a different Pattern: line for the same finding.

TRUNCATION IS BYTE TRUNCATION. `${line_text:0:117}` slices bytes under LC_ALL=C
and can cut a UTF-8 sequence in half. The port encodes, slices, and decodes with
`surrogateescape`, so the same bytes come out and a half-character stays half a
character rather than becoming a replacement glyph the twin never printed.

MESSAGES ON STDERR, DATA ON STDOUT, exactly as the twin splits them: `log_error`
and `log_warn` write to stderr while the two indented `Pattern:` / `Line:` lines
are bare `echo` and land on stdout. `rediacc_ci.log` refuses to put messages on
stdout, which is right for messages; these two are the copy-paste payload, so
they go through `print()` and the split survives.

WHAT THIS GATE STILL CANNOT SEE, unchanged by the port: it reads only the two
content directories, so a slop phrase in `README.md`, in a component's JSX, or
in a translation JSON is invisible to it. The allowlist is also a FILE-level
opt-out with no expiry and no liveness check, so an allowlisted path stays
unscanned forever. Both are limits of the twin, preserved rather than widened,
because widening either would change the verdict.
"""

import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls


def _joined(*rows: str) -> str:
    """`"\n".join(rows)` behind a call. The rows stay one per line.

    A helper rather than a literal join because ruff's FLY002 rewrites a join
    over a LITERAL list into an f-string, and a ten-line shell fixture written
    as one f-string is unreadable. Passing the rows as arguments keeps the
    fixture legible and gives the linter nothing static to fold.
    """
    return "\n".join(rows)


# The two configuration files, repo-relative. The twin `cd`s to the root and
# names them bare; this is the same fact with the cd removed.
PATTERNS_FILE = ".ci/config/content-quality-patterns.conf"
ALLOWLIST_FILE = ".ci/config/content-quality-allowlist.txt"

# The scanned roots, in the twin's order. A directory that does not exist is
# skipped silently, which is how the twin behaves and is also how this gate can
# go quiet; see the anti-vacuity note on `main`.
CONTENT_DIRS = (
    "packages/www/src/content/docs",
    "packages/www/src/content/blog",
)

# The severity switches, matched EXACTLY as whole lines. `# [ERROR]` with a
# trailing space is not a switch, it is a comment, and the twin agrees because
# it uses `==` on the whole line rather than a prefix test.
ERROR_MARKER = "# [ERROR]"
WARN_MARKER = "# [WARN]"

# The inline suppression token and the fence opener, both matched the way awk
# matches them: the token anywhere in the line, the fence anchored at column 1.
SLOP_OK = "<!-- slop-ok -->"

# How long a reported line may be before it is cut, and where the cut lands.
# Two numbers, not one, because the twin's are 120 and 117 and the three-byte
# difference is the "..." it appends.
MAX_LINE_BYTES = 120
CUT_LINE_BYTES = 117


def read_text(path) -> str:
    """A file's bytes as text, round-trippable.

    `surrogateescape` rather than `replace`: every byte survives and can be
    written back out unchanged, which is what keeps a truncation that cuts a
    UTF-8 sequence in half byte-identical to the twin's. `replace` would turn
    those bytes into a glyph bash never printed.
    """
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8", "surrogateescape")


def read_lines(text: str) -> list[str]:
    """The lines a `while IFS= read -r line || [[ -n "$line" ]]` loop would see.

    The `||` half is the interesting one: it is what makes bash process a final
    line that has no terminating newline. Splitting on "\\n" produces a trailing
    empty string for a file that DOES end in a newline, and that empty string is
    not a line, so it is dropped. Nothing else is stripped: `IFS=` means the
    loop does no whitespace trimming at all.
    """
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def load_patterns(text: str) -> tuple[list[str], list[str]]:
    """(error patterns, warn patterns) from the .conf, in file order.

    THE SEVERITY STARTS AT ERROR. A patterns file with no `# [ERROR]` marker at
    all loads every pattern as blocking, which is the twin's `local severity="ERROR"`
    initialiser and the safe direction: a mis-edited header downgrades nothing.
    """
    severity = "ERROR"
    errors: list[str] = []
    warns: list[str] = []
    for line in read_lines(text):
        # `${line// /}` deletes SPACE, not whitespace. A tab-only line is a
        # pattern. See the port notes.
        if line.replace(" ", "") == "":
            continue
        if line == ERROR_MARKER:
            severity = "ERROR"
            continue
        if line == WARN_MARKER:
            severity = "WARN"
            continue
        if line.startswith("#"):
            continue
        if severity == "ERROR":
            errors.append(line)
        else:
            warns.append(line)
    return errors, warns


def load_allowlist(text: str) -> set[str]:
    """The file-level opt-outs, as repo-relative path strings.

    Same blank and comment rules as the patterns file, and the same absence of
    trimming: a trailing space in an allowlist entry makes it match nothing,
    silently, in both implementations.
    """
    out: set[str] = set()
    for line in read_lines(text):
        if line.replace(" ", "") == "":
            continue
        if line.startswith("#"):
            continue
        out.add(line)
    return out


def build_regex(patterns: list[str]) -> str:
    """`local IFS='|'; echo "$*"` -- the alternation the twin hands to grep.

    Not `re.escape`d and not parenthesised, on purpose: the entries ARE extended
    regular expressions (`game[ -]changer`, `^in conclusion,`,
    `plays? a (significant|crucial) role`), and wrapping them would change which
    lines match. An unanchored alternation is exactly what grep receives.
    """
    return "|".join(patterns)


def grep_in_file(text: str, regex: str) -> list[tuple[int, str]]:
    """`grep -inE <regex> <file>`: (1-based line number, line) for every match.

    Case insensitive, extended, per line. `^` and `$` are line anchors in grep;
    matching each line separately as its own string gives them the same meaning
    without needing re.MULTILINE, and avoids `$` also matching before the final
    newline of the whole buffer.
    """
    if regex == "":
        return []
    compiled = re.compile(regex, re.IGNORECASE)
    out: list[tuple[int, str]] = []
    for index, line in enumerate(read_lines(text), start=1):
        if compiled.search(line):
            out.append((index, line))
    return out


def exempt_lines(text: str) -> set[int]:
    """The line numbers awk marks exempt, rule for rule.

    The twin's program, verbatim, because the ORDER of these five rules is the
    whole semantics and a reordered "equivalent" would exempt different lines:

        BEGIN { fm=0; cb=0 }
        /^---$/ && cb==0 { fm++; if (fm<=2) { print NR; next } }
        fm==1 { print NR; next }
        /^```/ { cb=1-cb; print NR; next }
        cb==1 { print NR; next }
        /<!-- slop-ok -->/ { print NR; next }

    THE THIRD `---` IS NOT FRONTMATTER, and the twin says so by construction:
    `fm` keeps counting past 2 but only the first two get the `next`, so a
    horizontal rule later in the document falls through to the fence and
    slop-ok rules like any other line. `fm==1` is what exempts the BODY of the
    frontmatter, so the block is only skipped while exactly one `---` has been
    seen.

    A FENCE LINE IS ITSELF EXEMPT, opener and closer both, because the toggle
    happens in the same rule that prints NR. So a banned phrase written into
    the ```` ```language ```` opener is not reported.
    """
    fm = 0
    cb = 0
    out: set[int] = set()
    for number, line in enumerate(read_lines(text), start=1):
        if line == "---" and cb == 0:
            fm += 1
            if fm <= 2:
                out.add(number)
                continue
        if fm == 1:
            out.add(number)
            continue
        if line.startswith("```"):
            cb = 1 - cb
            out.add(number)
            continue
        if cb == 1:
            out.add(number)
            continue
        if SLOP_OK in line:
            out.add(number)
            continue
    return out


def identify_pattern(line: str, patterns: list[str]) -> str:
    """Which pattern to name in the report. First short match, then first long.

    TWO FULL PASSES, NOT ONE. A single loop testing "short substring or long
    regex" per pattern would report a different pattern for any line matching
    both, and the reported pattern is the only thing telling an author what to
    rewrite. See the port notes for the byte-length and case-sensitivity rules
    that make this function's answer differ from "what grep matched".
    """
    for pattern in patterns:
        if len(pattern.encode("utf-8", "surrogateescape")) <= 3 and pattern in line:
            return pattern
    for pattern in patterns:
        if len(pattern.encode("utf-8", "surrogateescape")) <= 3:
            continue  # already checked above
        if re.search(pattern, line, re.IGNORECASE):
            return pattern
    return "(unknown)"


def truncate(line_text: str) -> str:
    """The twin's `${line_text:0:117}...` when longer than 120, in BYTES.

    Sliced on the encoded form so the cut lands on the same byte bash cuts at,
    then decoded with `surrogateescape` so a severed multi-byte sequence comes
    back out as the same bytes rather than as a replacement character.
    """
    raw = line_text.encode("utf-8", "surrogateescape")
    if len(raw) > MAX_LINE_BYTES:
        return raw[:CUT_LINE_BYTES].decode("utf-8", "surrogateescape") + "..."
    return line_text


class Report:
    """The two counters and the printing, in one object.

    An object rather than two module globals because `selftest` drives several
    scans in one process and globals would carry a previous case's count into
    the next one, which is the shape of bug that makes a suite pass in isolation
    and fail in a run.
    """

    def __init__(self) -> None:
        self.errors = 0
        self.warnings = 0

    def violation(self, severity: str, rel_file: str, lineno: int, pattern: str, text: str) -> None:
        """One finding: a marked header on stderr, two data lines on stdout."""
        body = truncate(text)
        if severity == "ERROR":
            log.error("%s:%d" % (rel_file, lineno))
            self.errors += 1
        else:
            log.warn("%s:%d" % (rel_file, lineno))
            self.warnings += 1
        # NINE SPACES, matching the twin's `echo "         Pattern: ..."`. The
        # indent is not decoration: `scripts/lib/shadow-gate.ts` attaches an
        # INDENTED unmarked line to the finding above it, so a port that
        # un-indented these would emit two lines of chatter and one finding
        # where the twin emits three findings.
        print('         Pattern: "%s"' % pattern)
        print("         Line:    %s" % body)


def scan_file(
    path: pathlib.Path,
    rel_file: str,
    allowlisted: set[str],
    error_patterns: list[str],
    warn_patterns: list[str],
    report: Report,
) -> None:
    """Scan one content file and report every non-exempt match.

    THE EXEMPT SET IS COMPUTED ONLY WHEN SOMETHING MATCHED, matching the twin's
    early return. That is a performance decision in the original and it is
    preserved because it is also a BEHAVIOUR one: a file whose awk pass would
    crash or hang is never awk'd unless grep found something in it first.
    """
    if rel_file in allowlisted:
        return

    text = read_text(path)
    error_regex = build_regex(error_patterns)
    warn_regex = build_regex(warn_patterns)

    error_raw = grep_in_file(text, error_regex)
    warn_raw = grep_in_file(text, warn_regex)
    if not error_raw and not warn_raw:
        return

    exempt = exempt_lines(text)

    for lineno, line in error_raw:
        if lineno in exempt:
            continue
        report.violation("ERROR", rel_file, lineno, identify_pattern(line, error_patterns), line)
    for lineno, line in warn_raw:
        if lineno in exempt:
            continue
        report.violation("WARN", rel_file, lineno, identify_pattern(line, warn_patterns), line)

    # NOTE: Double-dash ( -- ) detection was removed because ` -- ` is a
    # legitimate CLI argument separator (e.g., `renet compose -- up -d`,
    # `npm run dev -- --host`). Detecting it requires understanding whether
    # the context is prose or a command, which grep cannot distinguish
    # reliably. The em dash pattern (U+2014) in the patterns file catches
    # the actual AI tell.


def discover(root: pathlib.Path) -> list[pathlib.Path]:
    """Every `*.md` / `*.mdx` under the two content roots.

    `find <dir> \\( -name '*.md' -o -name '*.mdx' \\) -type f`, which follows no
    symlinks (find's default is -P) and descends without limit. SORTED here and
    not by the twin: `find` emits in readdir order, which is filesystem state
    rather than repository content, and two runs on one tree can differ. The
    findings are compared as an unordered multiset by the differential, so the
    sort changes the printed order and nothing else, and it makes the port's own
    output reproducible.
    """
    out: list[pathlib.Path] = []
    for name in CONTENT_DIRS:
        base = root / name
        if not base.is_dir():
            continue
        for dirpath, _dirnames, filenames in paths.walk_tree(base):
            for filename in filenames:
                if filename.endswith((".md", ".mdx")):
                    candidate = pathlib.Path(dirpath) / filename
                    if candidate.is_file():
                        out.append(candidate)
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 on an ERROR-severity finding.

    WARNINGS DO NOT BLOCK, and that is deliberate in the twin: the WARN section
    of the patterns file holds structural tells ("^(First|Second|Third|Finally),")
    that are frequently correct prose. They are counted, printed, and ignored by
    the exit code.

    `--selftest` is intercepted BEFORE any real scan. The twin takes FILE
    ARGUMENTS, so a twin invoked with this string would try to scan a file named
    `--selftest`; no caller does that, and the differential never passes it.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    # Byte-exact output. The gate prints content it read from disk, so its own
    # streams must be able to carry every byte back out; without this a
    # surrogate from `surrogateescape` raises UnicodeEncodeError in the middle
    # of a failure report, which is the worst place for a traceback.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="surrogateescape")

    root = paths.repo_root()

    log.step("Checking content quality (anti-slop patterns)...")

    patterns_path = root / PATTERNS_FILE
    if not patterns_path.is_file():
        log.error("Pattern file not found: %s" % PATTERNS_FILE)
        return 1

    error_patterns, warn_patterns = load_patterns(read_text(patterns_path))

    allowlist_path = root / ALLOWLIST_FILE
    allowlisted = load_allowlist(read_text(allowlist_path)) if allowlist_path.is_file() else set()

    log.info(
        "Loaded %d error patterns, %d warn patterns" % (len(error_patterns), len(warn_patterns))
    )

    # ARGUMENTS OVERRIDE THE DISCOVERY, exactly as the twin's
    # `if [[ $# -gt 0 ]]` does: a caller naming files scans those and only
    # those, and the two content roots are not consulted at all.
    files = [pathlib.Path(a) for a in args] if args else discover(root)

    log.info("Scanning %d content files..." % len(files))

    report = Report()
    for path in files:
        # `${file#"$REPO_ROOT/"}` is a PREFIX strip, not a relative-path
        # computation: a path that is not under the root keeps its full text and
        # is compared against the allowlist in that form. Reproduced literally,
        # because `os.path.relpath` would invent `../..` segments the twin never
        # produces and would then fail to match an allowlist entry.
        text = str(path)
        prefix = str(root) + os.sep
        rel_file = text.removeprefix(prefix)
        scan_file(path, rel_file, allowlisted, error_patterns, warn_patterns, report)

    print()
    if report.errors > 0 or report.warnings > 0:
        if report.warnings > 0:
            log.warn("%d warning(s) (review recommended)" % report.warnings)
        if report.errors > 0:
            log.error("%d content quality violation(s) found" % report.errors)
            log.info(
                "Fix violations by restructuring: use periods, commas, colons, or parentheses."
            )
            log.info("Do NOT replace em dashes with hyphens. Restructure the sentence instead.")
            log.info("Suppress specific lines with <!-- slop-ok --> (use sparingly).")
            log.info("Pattern definitions: %s" % PATTERNS_FILE)
            return 1
    else:
        log.info("All content files pass quality checks")
    return 0


# A patterns file with one pattern per severity, short enough to reason about
# and shaped like the real one (a header comment, the two markers, blanks).
_PATTERNS = _joined(
    "# Content quality patterns",
    "",
    "# [ERROR]",
    "in the world of",
    "\u2014",
    "",
    "# [WARN]",
    "^(First|Second|Third|Finally),",
    "",
)


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. The suppression rules are the half most
    likely to rot into "exempts everything", so each of the four has a MIRROR
    proving an identical line one row outside the exemption still fires.
    """
    ctl = Controls("content-quality", floor=20, verbose=True)

    ctl.check(
        "helper: the severity switch splits the list",
        load_patterns(_PATTERNS),
        (["in the world of", "\u2014"], ["^(First|Second|Third|Finally),"]),
    )
    ctl.check(
        "helper: a tab-only line is NOT blank and loads as a pattern",
        load_patterns("# [ERROR]\n\t\n")[0],
        ["\t"],
    )
    ctl.check(
        "helper: a space-only line IS blank",
        load_patterns("# [ERROR]\n   \n")[0],
        [],
    )
    ctl.check(
        "helper: patterns before any marker default to ERROR",
        load_patterns("first\n")[0],
        ["first"],
    )
    ctl.check(
        "helper: a file with no trailing newline still yields its last line",
        load_patterns("# [ERROR]\nlast"),
        (["last"], []),
    )
    ctl.check("helper: the alternation is joined with a pipe", build_regex(["a", "b"]), "a|b")

    # The exemption map, every rule and its mirror. Line numbers are 1-based and
    # written out so a reader can count them in the fixture text.
    doc = _joined(
        "---",  # 1 frontmatter open
        "title: in the world of x",  # 2 frontmatter body
        "---",  # 3 frontmatter close
        "prose in the world of a",  # 4 REPORTED
        "```bash",  # 5 fence open
        "in the world of b",  # 6 fenced
        "```",  # 7 fence close
        "in the world of c <!-- slop-ok -->",  # 8 suppressed inline
        "in the world of d",  # 9 REPORTED
        "---",  # 10 a horizontal rule, NOT frontmatter
        "in the world of e",  # 11 REPORTED
        "",
    )
    exempt = exempt_lines(doc)
    ctl.check("EXEMPT: the frontmatter open, body and close", sorted(exempt & {1, 2, 3}), [1, 2, 3])
    ctl.check("EXEMPT: the fence open, body and close", sorted(exempt & {5, 6, 7}), [5, 6, 7])
    ctl.check("EXEMPT: an inline slop-ok line", 8 in exempt, True)
    ctl.check("MIRROR: plain prose is NOT exempt", 4 in exempt, False)
    ctl.check("MIRROR: a line after the fence closes is NOT exempt", 9 in exempt, False)
    ctl.check(
        "MIRROR: a THIRD --- is a horizontal rule, and neither it nor what follows is exempt",
        (10 in exempt, 11 in exempt),
        (False, False),
    )

    ctl.check(
        "helper: grep finds the match case-INsensitively",
        grep_in_file("IN THE WORLD OF x\n", "in the world of"),
        [(1, "IN THE WORLD OF x")],
    )
    ctl.check(
        "helper: an anchored pattern anchors per LINE",
        grep_in_file("a\nFirst, b\n", "^(First|Second|Third|Finally),"),
        [(2, "First, b")],
    )
    ctl.check(
        "helper: identify_pattern takes the SHORT pattern first",
        identify_pattern("a \u2014 in the world of x", ["in the world of", "\u2014"]),
        "\u2014",
    )
    ctl.check(
        "helper: identify_pattern's fast path is case SENSITIVE, so this is unknown",
        identify_pattern("A B", ["ab"]),
        "(unknown)",
    )
    ctl.check("helper: a short line is not truncated", truncate("x" * 120), "x" * 120)
    ctl.check(
        "helper: a long line is cut at 117 bytes plus an ellipsis",
        truncate("x" * 121),
        "x" * 117 + "...",
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / ".ci" / "config").mkdir(parents=True)
        (root / ".ci" / "config" / "content-quality-patterns.conf").write_text(
            _PATTERNS, encoding="utf-8"
        )
        docs = root / "packages" / "www" / "src" / "content" / "docs"
        docs.mkdir(parents=True)

        def run(body: str, allowlist: str | None = None) -> int:
            (docs / "page.md").write_text(body, encoding="utf-8")
            allow = root / ".ci" / "config" / "content-quality-allowlist.txt"
            if allowlist is None:
                if allow.exists():
                    allow.unlink()
            else:
                allow.write_text(allowlist, encoding="utf-8")
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        ctl.check("CONTROL: clean prose passes", run("nothing to see here\n"), 0)
        ctl.check("PLANT: an ERROR pattern reds", run("in the world of x\n"), 1)
        ctl.check("PLANT: an em dash reds", run("a \u2014 b\n"), 1)
        ctl.check(
            "MIRROR: the same phrase inside a fence passes", run("```\nin the world of x\n```\n"), 0
        )
        ctl.check(
            "MIRROR: the same phrase with slop-ok passes",
            run("in the world of x <!-- slop-ok -->\n"),
            0,
        )
        ctl.check(
            "MIRROR: an allowlisted file passes",
            run("in the world of x\n", "packages/www/src/content/docs/page.md\n"),
            0,
        )
        ctl.check(
            "PLANT: a WARN pattern is counted but does NOT block",
            run("First, a thing.\n"),
            0,
        )

        # THE VACUITY CASE, and it is a REPORTED TWIN DEFECT rather than a
        # behaviour to be proud of: with the content directories absent the gate
        # scans zero files and exits 0. Asserted here so the port's agreement
        # with the twin is deliberate and visible, not accidental.
        empty = root / "empty"
        (empty / ".ci" / "config").mkdir(parents=True)
        (empty / ".ci" / "config" / "content-quality-patterns.conf").write_text(
            _PATTERNS, encoding="utf-8"
        )
        saved = os.environ.get(paths.ROOT_ENV)
        os.environ[paths.ROOT_ENV] = str(empty)
        try:
            ctl.check("TWIN DEFECT: zero content files still exits 0", main([]), 0)
            # A missing patterns file IS a refusal, which is the one input the
            # twin does treat as a failure.
            (empty / ".ci" / "config" / "content-quality-patterns.conf").unlink()
            ctl.check("REFUSAL: an absent patterns file exits 1", main([]), 1)
        finally:
            if saved is None:
                del os.environ[paths.ROOT_ENV]
            else:
                os.environ[paths.ROOT_ENV] = saved

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
