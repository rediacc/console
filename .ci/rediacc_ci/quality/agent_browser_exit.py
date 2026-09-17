r"""`agent-browser open`'s exit status must never decide control flow.

Ported from `.ci/scripts/quality/check-agent-browser-exit.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live and for the phase-5 decision that retires the twin.

THE TWIN'S OWN HEADER, carried over because the measurement IS the gate and a paraphrase of it would be a different gate:

  `agent-browser open` has an EXIT CODE THAT DEPENDS ON WHETHER STDOUT IS A TTY.

  Measured 2026-08-28, same binary, same URL, page loads correctly both ways:
      agent-browser open "$URL"                    -> rc=0
      agent-browser open "$URL" >/dev/null 2>&1    -> rc=1

  packages/www/scripts/measure-page-density.sh runs under `set -euo pipefail` and
  redirects that call, so `set -e` killed it at its FIRST page. The symptom was not
  an error: an empty log, and a CSV containing only its header row. It read as "the
  harness produced nothing" rather than "the harness was shot".

  We do not own agent-browser, so the durable invariant is OURS: no script may let
  that exit status decide control flow. The fix is one of `|| true`, `|| :`, an
  `if`, or a `&&`/`||` chain -- anything that states the status is not being
  trusted. This gate exists because the reason lives in a COMMENT above the call,
  and this repo's own trap log records that the next reader deletes a defensive
  line on the comment's authority.

AND THE SECOND HALF, the same defect in JavaScript, also carried verbatim:

  `scan` above reads SHELL scripts under `set -e`. The identical bug lives in Node,
  where `execSync`/`execFileSync` THROW on the same worthless status, and it cost a
  CI red on 2026-08-31 (run 33430885467, job 99616335703): the tutorial-player
  release gate died on its first navigation with `Error: Command failed:
  agent-browser ... open <url>` and nothing else, while the identical command
  passed locally on the same tree.

  THE INVARIANT, deliberately crude so it cannot false-positive on style: a file
  that runs agent-browser through a THROWING exec must reach for the child's
  `.stdout` somewhere. agent-browser prints its verdict as JSON on stdout even when
  it exits 1, so `.stdout` is the only place a caller can learn what actually
  happened. A caller that never mentions it is a caller that has thrown the reason
  away.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE LAST LINE OF A FILE WITH NO TRAILING NEWLINE IS NOT SCANNED, and that is
the twin's behaviour rather than a shortcut taken here. `while IFS= read -r
line; do ... done <"$f"` runs its body only when `read` SUCCEEDS, and `read` returns non-zero at EOF even though it has already assigned the partial line. Measured in this tree:

    printf 'a\nb' > f; n=0
    while IFS= read -r l; do n=$((n+1)); echo "GOT[$n]=$l"; done < f
    -> GOT[1]=a, final n=1

So `b` is invisible to the scanner. `_read_lines` reproduces exactly that by splitting on "\n" and DROPPING the final element unconditionally: for a file ending in a newline that element is the empty string and dropping it is correct, and for a file that does not it is the unscanned last line. Both cases therefore agree with bash. This is reported as a defect in the twin rather
than silently repaired, because repairing it would change the verdict on a real file and the port's job is to keep the verdict.

`set -o errexit` IS NOT SEEN, for the same reason. The eligibility test is `grep -qE '^[[:space:]]*set[[:space:]]+-[a-z]*e'`, which requires the `e` to sit inside the option CLUSTER: `-e`, `-euo` and `-ex` all match because `[a-z]*` can be empty or `u`/`x`-and-friends up to an `e`, while `-o errexit` puts a SPACE between the dash and the `e` and `[a-z]*` cannot cross it. A script
written with the long form dies exactly the same way and this gate never looks at it. Carried unchanged; reported.

`[[:space:]]` IS NOT `\s`. POSIX space is exactly [ \t\n\v\f\r]; Python's `\s` on a str pattern also matches U+00A0 and U+2028, so a line indented with a non-breaking space would be seen by the port and not by grep. The class is written out rather than abbreviated, the same way `rediacc_ci.quality.npmrc` does it and for the same reason.

THE SKIP LIST TESTS THE RAW LINE, NOT THE STRIPPED ONE. Only the comment test
uses the leading-whitespace-stripped form (`${line#"${line%%[![:space:]]*}"}`);
`|| true`, `&&`, `if `, `! agent-browser` and `$(` are all matched against the line as read. That distinction is invisible in practice and is preserved because guessing which one a shell `case` was looking at is exactly the sort of detail a "tidy" rewrite gets wrong.

`*'&&'*` SKIPS ANY LINE CONTAINING `&&` ANYWHERE, which is broader than the header's "a `&&`/`||` chain" promises. `cd "$dir" && agent-browser open "$URL"` is skipped, and under `set -e` that line still kills the script: an AND-list's status is its LAST command's, and a failing last command in a `&&` list is not in a context that suppresses errexit. A real false negative, carried
unchanged and reported.

THE STATUS IS MADE BOOLEAN, THE COUNT IS NOT RETURNED. The twin ends both scanners with `[ "$hits" -eq 0 ]` and says why in as many words: "NOT `return "$hits"`. A shell return is taken mod 256, so exactly 256 findings would return 0 and read as a clean scan." Python has no such wrap, but the shape is kept -- the scanners return their findings and the caller decides -- so the
reason survives next to the code it explains.

SELF-EXCLUSION IS BY EXACT FILENAME AND APPLIES ONLY TO THE SHELL HALF. The twin's `grep -vF 'check-agent-browser-exit.sh'` removes itself from `scan`'s corpus, because it carries the pattern in its own fixtures and in its own error text. `scan_js` needs no equivalent: it only looks at `*.js`, `*.mjs`, `*.cjs` and `*.ts`, and neither the twin nor this module is one of those. THIS
FILE IS LIKEWISE INVISIBLE TO BOTH HALVES, being `.py`, which is worth stating because a reader who notices the literal `execFileSync('agent-browser', ...)` in the selftest below will otherwise wonder whether the gate reads itself.

ORDER MATTERS AND IS PRESERVED: the JS half runs FIRST and exits before the shell half is reached. A tree with both defects reports only the JavaScript one, which is a property of the twin's control flow and would silently change if the two scans were merged into one report.
"""

import os
import pathlib
import re
import shutil
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# POSIX [[:space:]], written out. See the port notes for why `\s` is wrong here.
SPACE = r"[ \t\n\v\f\r]"

# `grep -qE '^[[:space:]]*set[[:space:]]+-[a-z]*e'`: only scripts that would DIE on a non-zero status. See the port notes for the `set -o errexit` blind spot.
SET_E_RE = re.compile(r"^%s*set%s+-[a-z]*e" % (SPACE, SPACE))

# The shell corpus: `--include='*.sh'`, with the twin itself removed by exact
# filename. node_modules and .git USED TO BE LISTED HERE as the path substrings `/node_modules/` and `/.git/`; they now come from `paths.walk_tree`, which prunes them for every gate in this package rather than for the ones that remembered. Empty rather than deleted, because the JS corpus below still has a prune of its own and one parameter is clearer than two code paths.
SH_SUFFIXES = (".sh",)
SH_PRUNE: tuple[str, ...] = ()
SELF_NAME = "check-agent-browser-exit.sh"

# The JS corpus: `--include='*.js' --include='*.mjs' --include='*.cjs'
# --include='*.ts'`, with `dist` pruned. `dist` is on this list and not on the
# shell one, exactly as in the twin. A directory NAME now, not the path substring `/dist/`, because that is what `walk_tree`'s `exclude_dirs` takes; the two agree on every path (the substring only ever matched a whole component) and the name form is pruned before the subtree is entered rather than after it is read.
JS_SUFFIXES = (".js", ".mjs", ".cjs", ".ts")
JS_PRUNE = ("dist",)

# The needle both corpora are built from, and the second half of the shell half's line test. `agent-browser` then, later on the same line, `open`.
NEEDLE = "agent-browser"

# The throwing execs. A file that runs agent-browser through one of these and never mentions `.stdout` has thrown away the only evidence there was.
THROWING_EXECS = ("execSync(", "execFileSync(")

# The recovery marker. Its PRESENCE ANYWHERE IN THE FILE clears the whole file, which is deliberately crude so the rule cannot false-positive on style; the twin's comment says so and the crudeness is the reason it is trusted.
RECOVERY = ".stdout"


def _read_lines(text: str) -> list[str]:
    """The lines bash's `while IFS= read -r line` would actually deliver.

    The final element of the split is dropped ALWAYS: it is the empty string for a file ending in a newline, and the unscanned partial last line for a file that does not end in one. See the port notes for the measurement.
    """
    parts = text.split("\n")
    return parts[:-1]


def _strip_leading(line: str) -> str:
    """`${line#"${line%%[![:space:]]*}"}` -- the line without its indent."""
    return line.lstrip(" \t\n\v\f\r")


def _corpus(root: str, suffixes: tuple[str, ...], prune: tuple[str, ...]) -> list[str]:
    """`grep -rl <needle> --include=... | grep -v ... | sort`, as a path list.

    SORTED BY BYTES, not by locale. The differential harness pins LC_ALL=C
    precisely so `sort` is byte order, and a Python sort over str is the same thing for the ASCII paths this repo has. Encoding the key makes that explicit rather than true by accident.

    A MISSING ROOT IS AN EMPTY CORPUS, not an error, matching the twin's `2>/dev/null` on the grep. That is not a vacuity hole being copied blindly: the twin's controls drive `scan` against a directory that does not exist on purpose, so the behaviour is load-bearing for its own self-test.

    `prune` IS NOW A TUPLE OF DIRECTORY NAMES handed to `paths.walk_tree`, which also prunes `.git`, `node_modules` and `.claude/worktrees` for every caller. The last of those is why this changed: a peer's sibling checkout under `.claude/worktrees/` is invisible to git and was not invisible to `os.walk`, so this corpus was silently scanning a second copy of the repository.
    """
    out: list[str] = []
    for dirpath, dirnames, filenames in paths.walk_tree(root, exclude_dirs=prune):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.endswith(suffixes):
                continue
            full = os.path.join(dirpath, name)
            try:
                text = pathlib.Path(full).read_text(encoding="utf-8", errors="replace")
            except OSError:
                # grep prints an error to the stderr the twin sends to /dev/null and lists nothing. An unreadable file is not a finding.
                continue
            if NEEDLE in text:
                out.append(full)
    return sorted(out, key=lambda p: p.encode("utf-8", "surrogateescape"))


def _report(root: str, path: str, number: int, line: str) -> str:
    """One finding, in the twin's two-line `printf '  %s:%d\\n    %s\\n'` shape.

    The path is made relative with `${f#"$root"/}`, which is a PREFIX strip and
    not a path computation: a file that is not under `root` keeps its full name, which is what the twin does and is the harmless case.
    """
    rel = path.removeprefix(root.rstrip("/") + "/")
    return "  %s:%d\n    %s" % (rel, number, _strip_leading(line))


def scan(root: str) -> list[str]:
    """Shell scripts under `set -e` whose control flow trusts that exit status.

    Returns the findings rather than a boolean, so a test can assert on the decision without capturing a stream. The twin's `[ "$hits" -eq 0 ]` becomes `not scan(root)` at the call site; see the port notes for why the count is never the return value on either side.
    """
    hits: list[str] = []
    for path in _corpus(root, SH_SUFFIXES, SH_PRUNE):
        if SELF_NAME in path:
            # THIS FILE IS EXCLUDED, and that is not a loophole. It carries the pattern in its own fixtures and in its own error text, so a detector that reads itself reports five findings that are prose. This repo's trap log calls the class out by name. The exclusion is by exact path, so no other script can hide behind it.
            continue
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
        # Only scripts that would DIE on a non-zero status. grep sees the whole file, including a final line with no newline, so this test reads the raw text rather than `_read_lines`.
        if not any(SET_E_RE.search(line) for line in text.split("\n")):
            continue
        for number, line in enumerate(_read_lines(text), start=1):
            _before, sep, tail = line.partition(NEEDLE)
            if not sep or "open" not in tail:
                continue
            # A comment is prose, not a call.
            if _strip_leading(line).startswith("#"):
                continue
            # Status already neutralised or consumed by a conditional. Matched against the RAW line, exactly as the shell `case` does.
            if "|| true" in line or "|| :" in line or "||true" in line:
                continue
            # `*'if '*'agent-browser'*` is "an `if ` somewhere BEFORE an occurrence of the needle", so the LAST occurrence is the one that gives the pattern its best chance, not the first.
            if_at = line.find("if ")
            if (if_at >= 0 and line.rfind(NEEDLE) >= if_at + 3) or "&&" in line:
                continue
            if "! agent-browser" in line:
                continue
            if "$(" in line:  # captured, caller decides
                continue
            hits.append(_report(root, path, number, line))
    return hits


def scan_js(root: str) -> list[str]:
    """JS/TS callers that exec agent-browser through a THROWING exec and discard
    the child's stdout.

    See the module docstring for the 2026-08-31 CI red (run 33430885467, job 99616335703) this half was written for.
    """
    hits: list[str] = []
    for path in _corpus(root, JS_SUFFIXES, JS_PRUNE):
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
        # The recovery is present: this file reads the child's stdout on the throw path.
        if RECOVERY in text:
            continue
        for number, line in enumerate(_read_lines(text), start=1):
            if not any(exec_call in line for exec_call in THROWING_EXECS):
                continue
            if NEEDLE not in line:
                continue
            # A comment is prose, not a call.
            stripped = _strip_leading(line)
            if stripped.startswith(("//", "*", "/*")):
                continue
            hits.append(_report(root, path, number, line))
    return hits


# The two blocks of advice, kept as heredocs were: one string each, printed to stderr under the finding they belong to. Reworded advice is allowed by the differential; these are not reworded, because the JS snippet is the fix and a paraphrase of a fix is not a fix.
JS_ADVICE = """
`execSync`/`execFileSync` THROW on a non-zero status, and agent-browser's status is not
evidence (see below). Its verdict is JSON on STDOUT even when it exits 1, so catch the
throw, take `error.stdout`, and let the parsed envelope decide:

    let out;
    try { out = execFileSync('agent-browser', args, { encoding: 'utf8' }); }
    catch (error) { out = String(error.stdout ?? ''); if (!out.trim()) throw error; }
    const parsed = JSON.parse(out);
    if (!parsed.success) throw new Error(`agent-browser failed: ${parsed.error}`);
"""

SH_ADVICE = """
Its exit code is 1 when stdout is REDIRECTED and 0 on a terminal, for a URL that loads
fine either way, so this kills the script at that line with no error text.

Neutralise the status and let a check about the PAGE decide instead:
    agent-browser open "$URL" >/dev/null 2>&1 || true
    # then assert something real: a DOM-node floor, an expected selector, a title.
"""


def _write(path: pathlib.Path, *lines: str) -> None:
    """`printf '%s\\n' ... > path`. One newline per line, including the last."""
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def inline_controls() -> int:
    """The twin's own controls, run BEFORE the real scan. 0 green, 1 red.

    A gate nobody has watched fail is not a gate. These are carried across unchanged, including the two `echo " PASS control: ..."` lines they print on stdout, because a harness reading this gate's output would notice their absence. `--selftest` below is the ADDITION; this is the preserved half.
    """
    ctl = pathlib.Path(tempfile.mkdtemp())
    try:
        _write(
            ctl / "bad.sh",
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            'agent-browser open "$URL" >/dev/null 2>&1',
        )
        _write(
            ctl / "good.sh",
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            'agent-browser open "$URL" >/dev/null 2>&1 || true',
        )
        _write(
            ctl / "no-set-e.sh",
            "#!/usr/bin/env bash",
            'agent-browser open "$URL" >/dev/null 2>&1',
        )

        # A directory that does not exist. The twin drives this and throws the result away (`>/dev/null 2>&1 || true`), so it asserts nothing; it is carried because deleting it would be a change to the twin's behaviour under an unrelated port, and it is reported as dead code instead.
        scan(str(ctl / "bad.sh_dir"))

        one = ctl / "one"
        one.mkdir(parents=True, exist_ok=True)
        shutil.copy(ctl / "bad.sh", one / "bad.sh")
        if not scan(str(one)):
            print(
                "CONTROL FAILED: an unguarded call under set -e was NOT reported.",
                file=sys.stderr,
            )
            return 1
        shutil.rmtree(one)
        one.mkdir(parents=True, exist_ok=True)
        shutil.copy(ctl / "good.sh", one / "good.sh")
        shutil.copy(ctl / "no-set-e.sh", one / "no-set-e.sh")
        if scan(str(one)):
            print(
                "CONTROL FAILED: a guarded call, or one outside set -e, was reported.",
                file=sys.stderr,
            )
            return 1
        print("  PASS  control: an unguarded call under set -e is reported")
        print("  PASS  control: a guarded call, and one outside set -e, are not")

        # The JS half gets its own controls, for the same reason the shell half does.
        js = ctl / "js"
        shutil.rmtree(js, ignore_errors=True)
        js.mkdir(parents=True, exist_ok=True)
        _write(
            js / "bad.js",
            "const out = execFileSync('agent-browser', args, { encoding: 'utf8' });",
        )
        if not scan_js(str(js)):
            print(
                "CONTROL FAILED: a JS exec of agent-browser that never reads .stdout "
                "was NOT reported.",
                file=sys.stderr,
            )
            return 1
        _write(
            js / "bad.js",
            "try { out = execFileSync('agent-browser', args); }",
            "catch (e) { out = String(e.stdout ?? ''); }",
        )
        _write(
            js / "comment.js",
            "// execFileSync('agent-browser', ...) is described here, not called.",
        )
        if scan_js(str(js)):
            print(
                "CONTROL FAILED: a JS caller that recovers .stdout, or a comment, was reported.",
                file=sys.stderr,
            )
            return 1
        print("  PASS  control: a JS exec of agent-browser that discards .stdout is reported")
        print("  PASS  control: one that recovers .stdout, and a comment, are not")
    finally:
        shutil.rmtree(ctl, ignore_errors=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation.

    `--selftest` is intercepted BEFORE the inline controls and before any real scan, matching every other port in this package. The twin takes no arguments at all and would ignore the string entirely, so no caller can be passing it today and the differential never hands it to the old side.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = str(paths.repo_root())

    rc = inline_controls()
    if rc != 0:
        return rc

    # --- the real scan ---------------------------------------------------
    #
    # THE JS HALF RUNS FIRST AND EXITS. A tree carrying both defects reports only the JavaScript one. That is the twin's control flow, preserved.
    js_out = scan_js(root)
    if js_out:
        print(
            "✗ a JS/TS caller execs `agent-browser` and never reads the child's stdout:",
            file=sys.stderr,
        )
        for hit in js_out:
            print(hit, file=sys.stderr)
        print(JS_ADVICE, end="", file=sys.stderr)
        return 1

    out = scan(root)
    if not out:
        # STDOUT, deliberately: the twin's green verdict is a bare `echo`, not a log_info, so it lands on stdout while every finding lands on stderr.
        print(
            "✓ No shell script, and no JS/TS caller, lets `agent-browser`'s "
            "exit status decide control flow."
        )
        return 0

    print(
        "✗ `agent-browser open` exit status is load-bearing in a `set -e` script:",
        file=sys.stderr,
    )
    for hit in out:
        print(hit, file=sys.stderr)
    print(SH_ADVICE, end="", file=sys.stderr)
    return 1


# The three shell fixtures the twin's own controls use, plus the shapes it does NOT have a control for. Each is a property, and a case with no property is a
# case that will be deleted the first time someone tidies this file.
_BAD_SH = '#!/usr/bin/env bash\nset -euo pipefail\nagent-browser open "$URL" >/dev/null 2>&1\n'


def selftest() -> int:
    """Plant each violation, prove it fires; remove it, prove it does not.

    BOTH DIRECTIONS FOR EVERY CONTROL. A scanner with only positive plants will happily flag every call site in the tree, and the mirrors below (`|| true`, a comment, a captured status, a file with no `set -e`, a JS caller that recovers `.stdout`) are the half that proves it does not.
    """
    ctl = Controls("agent-browser-exit", floor=26, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        def sh(name: str, *lines: str) -> list[str]:
            """One shell file in a fresh directory; return `scan`'s findings."""
            box = root / "sh"
            shutil.rmtree(box, ignore_errors=True)
            box.mkdir(parents=True)
            _write(box / name, *lines)
            return scan(str(box))

        def js(name: str, *lines: str) -> list[str]:
            box = root / "js"
            shutil.rmtree(box, ignore_errors=True)
            box.mkdir(parents=True)
            _write(box / name, *lines)
            return scan_js(str(box))

        # -- the shell half, positive plants --------------------------------
        ctl.check(
            "PLANT: an unguarded call under set -euo is reported",
            len(sh("bad.sh", "set -euo pipefail", 'agent-browser open "$URL" >/dev/null 2>&1')),
            1,
        )
        ctl.check(
            "PLANT: bare `set -e` is enough to make the file eligible",
            len(sh("bad.sh", "set -e", 'agent-browser open "$URL" >/dev/null')),
            1,
        )
        ctl.check(
            "PLANT: an indented call is reported, and reported unindented",
            sh("bad.sh", "set -e", '    agent-browser open "$U" >/dev/null'),
            ['  bad.sh:2\n    agent-browser open "$U" >/dev/null'],
        )
        ctl.check(
            "PLANT: two calls in one file are two findings",
            len(
                sh(
                    "bad.sh",
                    "set -e",
                    'agent-browser open "$A" >/dev/null',
                    'agent-browser open "$B" >/dev/null',
                )
            ),
            2,
        )

        # -- the shell half, mirrors that must stay QUIET --------------------
        ctl.check(
            "MIRROR: `|| true` neutralises the status",
            sh("g.sh", "set -e", 'agent-browser open "$U" >/dev/null || true'),
            [],
        )
        ctl.check(
            "MIRROR: `|| :` neutralises the status",
            sh("g.sh", "set -e", 'agent-browser open "$U" >/dev/null || :'),
            [],
        )
        ctl.check(
            "MIRROR: `||true` with no space is also accepted",
            sh("g.sh", "set -e", 'agent-browser open "$U" >/dev/null ||true'),
            [],
        )
        ctl.check(
            "MIRROR: a file with no `set -e` cannot die, so it is not scanned",
            sh("g.sh", "#!/usr/bin/env bash", 'agent-browser open "$U" >/dev/null'),
            [],
        )
        ctl.check(
            "MIRROR: `set -uo pipefail` is NOT errexit and is not scanned",
            sh("g.sh", "set -uo pipefail", 'agent-browser open "$U" >/dev/null'),
            [],
        )
        ctl.check(
            "MIRROR: a commented call is prose, not a call",
            sh("g.sh", "set -e", '  # agent-browser open "$U" >/dev/null'),
            [],
        )
        ctl.check(
            "MIRROR: an `if` consumes the status",
            sh("g.sh", "set -e", 'if agent-browser open "$U"; then :; fi'),
            [],
        )
        ctl.check(
            "MIRROR: `! agent-browser` consumes the status",
            sh("g.sh", "set -e", '! agent-browser open "$U" >/dev/null'),
            [],
        )
        ctl.check(
            "MIRROR: a captured status leaves the decision to the caller",
            sh("g.sh", "set -e", 'out=$(agent-browser open "$U")'),
            [],
        )
        ctl.check(
            "MIRROR: `agent-browser` with no `open` is a different command",
            sh("g.sh", "set -e", 'agent-browser close "$U" >/dev/null'),
            [],
        )
        ctl.check(
            "MIRROR: a file not mentioning agent-browser is not in the corpus",
            sh("g.sh", "set -e", 'curl "$U" >/dev/null'),
            [],
        )
        ctl.check(
            "MIRROR: a non-.sh file is not in the shell corpus",
            sh("bad.bash", "set -e", 'agent-browser open "$U" >/dev/null'),
            [],
        )
        ctl.check(
            "MIRROR: the twin's own filename is excluded by exact name",
            sh(SELF_NAME, "set -e", 'agent-browser open "$U" >/dev/null'),
            [],
        )

        # THE PRESERVED DEFECTS. These two assert the twin's behaviour, not the behaviour anyone would design. They are controls so that a later "cleanup" has to delete an assertion with a name on it rather than quietly widening the gate.
        ctl.check(
            "PRESERVED DEFECT: `cd x && agent-browser open` is SKIPPED though it still dies",
            sh("g.sh", "set -e", 'cd "$d" && agent-browser open "$U" >/dev/null'),
            [],
        )
        ctl.check(
            "PRESERVED DEFECT: `set -o errexit` is not recognised as errexit",
            sh("g.sh", "set -o errexit", 'agent-browser open "$U" >/dev/null'),
            [],
        )

        # THE LAST-LINE DEFECT, asserted directly because it is the one a reader is most likely to call a bug in the port rather than in the twin.
        box = root / "nonl"
        shutil.rmtree(box, ignore_errors=True)
        box.mkdir(parents=True)
        (box / "bad.sh").write_text(
            'set -e\nagent-browser open "$U" >/dev/null',
            encoding="utf-8",
        )
        ctl.check(
            "PRESERVED DEFECT: a final line with no trailing newline is not scanned",
            scan(str(box)),
            [],
        )
        (box / "bad.sh").write_text(
            'set -e\nagent-browser open "$U" >/dev/null\n',
            encoding="utf-8",
        )
        ctl.check(
            "MIRROR: the same line WITH a trailing newline is scanned",
            len(scan(str(box))),
            1,
        )

        # -- the JS half -----------------------------------------------------
        ctl.check(
            "PLANT: an execFileSync that never reads .stdout is reported",
            len(js("bad.js", "const out = execFileSync('agent-browser', args);")),
            1,
        )
        ctl.check(
            "PLANT: execSync counts too",
            len(js("bad.ts", "execSync('agent-browser open ' + url);")),
            1,
        )
        ctl.check(
            "MIRROR: a file mentioning .stdout anywhere is cleared entirely",
            js(
                "ok.js",
                "try { out = execFileSync('agent-browser', args); }",
                "catch (e) { out = String(e.stdout ?? ''); }",
            ),
            [],
        )
        ctl.check(
            "MIRROR: a `//` comment is prose, not a call",
            js("c.js", "// execFileSync('agent-browser', ...) is described here."),
            [],
        )
        ctl.check(
            "MIRROR: a jsdoc `*` continuation is prose too",
            js("c.js", " * execFileSync('agent-browser', ...) in a doc block"),
            [],
        )
        ctl.check(
            "MIRROR: a spawnSync is not a THROWING exec",
            js("s.js", "spawnSync('agent-browser', args);"),
            [],
        )
        ctl.check(
            "MIRROR: an exec of something else is not this gate's business",
            js("s.js", "execSync('curl ' + url);"),
            [],
        )

        # -- VACUITY, in both halves ----------------------------------------
        #
        # An empty corpus produces no findings, and that is CORRECT here rather than a hole: `scan` is a predicate over a directory the caller chose, and the twin drives it against a non-existent one in its own controls. The anti-vacuity property that matters lives in `inline_controls`, which refuses to let the gate proceed unless a planted defect fires.
        empty = root / "empty"
        empty.mkdir(exist_ok=True)
        ctl.check("VACUITY: an empty directory yields nothing", scan(str(empty)), [])
        ctl.check("VACUITY: and nothing from the JS half either", scan_js(str(empty)), [])
        ctl.check(
            "VACUITY: a directory that does not exist yields nothing, as the twin's "
            "own control requires",
            scan(str(root / "nope")),
            [],
        )

        # THE CONTROLS THEMSELVES MUST BE ABLE TO PASS. Driving them here is what proves the block main() runs before every real scan is not itself broken -- a control battery that always returned 1 would make this gate unusable, and one that always returned 0 would make it decorative.
        ctl.check("the twin's inline controls pass", inline_controls(), 0)

        # And the plant they are built from must really be a plant.
        plant = root / "plant"
        plant.mkdir(exist_ok=True)
        (plant / "bad.sh").write_text(_BAD_SH, encoding="utf-8")
        ctl.check("CONTROL: the inline controls' own fixture fires", len(scan(str(plant))), 1)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
