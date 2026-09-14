r"""Case-arm globs that assert on a field name nothing emits.

Ported from `.ci/scripts/quality/check-dead-case-arms.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

WHY THIS EXISTS, in the twin's own words, because the incident is the design:

    A test assertion must be able to FAIL. This gate catches one mechanically
    detectable way it cannot: a `case` arm that globs for a `field=` token which
    exists nowhere in the code the test exercises.

    THE DEFECT THIS COMES FROM, 2026-08-05, written by the session lead while
    auditing other agents for exactly this class. A test proving the CI profiler
    reads a container's ceiling rather than the host's asserted the second half
    like this:

        case "$out" in
            *"cores=20"* | *"cores=1[0-9]"* | *"cores=[3-9]"*)
                log_fail "the sampler sized itself from the HOST" ;;
        esac

    The sampler's #META record is TSV. It contains no `cores=` anywhere. All
    three arms were dead, so the "not the host's" half of that test passed
    permanently while proving nothing, and its green was reported as evidence.

    WHY THIS SHAPE AND NOT SOMETHING BROADER. "Detect assertions that cannot
    fail" is not decidable in general, and a fuzzy version of it would be noisy
    enough to get suppressed -- which is the failure mode this repo keeps
    finding. So the scope is deliberately narrow and mechanical: a case-arm glob
    is an ASSERTION (unlike a `FOO=` assignment, of which there are ~20 in the
    suite and none are assertions), and a `key=` token in one is a claim about
    the SHAPE of data some other script produced. If that key appears in no
    non-test script, the arm is dead by construction.

    It reports zero findings today. That is the point of the control below: a
    gate whose green has never been contrasted with a red is a gate nobody has
    checked, so this one plants its own defect and refuses to pass unless that
    planted defect is caught.

THE COMMENT-STRIPPING RULE IS THE WHOLE GATE, and the twin says why:

    WITHOUT IT THIS GATE IS BLIND TO ITS OWN FOUNDING DEFECT, verified
    2026-08-05 with a two-fixture pair: an arm globbing `cores=20` was MISSED
    (exit 0) while an identical arm globbing `zzznosuchkeyq=20` FIRED (exit 1).
    The only two occurrences of `cores=` anywhere in CODE_DIRS were the comment
    lines in this file's own header describing the defect -- one of which is the
    sentence asserting that `cores=` appears nowhere. The gate had immunised
    itself against the bug it exists to catch, by describing it.

    The general form is worse than the instance: ANY script that documents a bad
    pattern in prose would vaccinate the whole tree against detecting that
    pattern, so the gate would grow quieter the better anything was commented.

THE MEDIA ROOT IS A SCAN ROOT AND NOT A CODE ROOT, and the asymmetry is
deliberate: "a directory that vouches for its own keys cannot be scanned. That
is this gate's founding lesson in a second costume: `cores=` survived because
the only occurrences were in the file describing it. A media module globbing for
`frames=` while being the only emitter of `frames=` would rule itself live by
exactly the same mechanism."

THE COUNT LEAVES THE SCANNER AS A VALUE, NOT AS AN EXIT STATUS, and the twin
records the reason: "It used to come back as the exit status, which a shell
takes mod 256: exactly 256 dead arms would have returned 0 and read as a clean
tree, and the control that proves this gate works compares that same status
against zero." The port returns a LIST, which cannot wrap at all.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`grep` ON THIS HOST IS ugrep 7.8.4, AND IT SKIPS BINARY FILES SILENTLY. Measured
2026-09-06: a shell file carrying a NUL byte, whose line 2 matches the case-arm
pattern, produces NO output and exit 1 from `grep -rnE`. GNU grep would print
`Binary file X matches` instead. The port reproduces ugrep by skipping any file
containing a NUL byte, which is the behaviour the differential compares against;
under GNU grep the twin would emit a mangled `Binary file ...` line that the
scanner would then try to split on colons. Reported as a portability defect in
the twin rather than repaired.

THE SCANNER READS THE WHOLE grep LINE, PREFIX INCLUDED. `printf '%s' "$line" |
grep -oE '"[^"]*"'` runs over `path:lineno:content`, so a quoted segment in the
PATH would contribute keys. No such path exists; the behaviour is carried
because narrowing it to the content would change which keys a future path could
produce.

FINDING ORDER IS TRAVERSAL ORDER AND IS NOT SORTED. `grep -r` emits in the order
its directory walk produces, which is readdir order and therefore filesystem
state rather than repository content. The port uses `os.walk`, which is also
readdir order, and the two need not agree. That is fine and deliberate:
`scripts/lib/shadow-gate.ts` compares findings as an unordered MULTISET, so a
different order is the same verdict, and imposing a sort here would hide a real
change in enumeration that the twin would show.

SYMLINKS ARE NOT FOLLOWED, on both sides. `grep -r` (as opposed to `-R`) does
not descend through a directory symlink, and `os.walk` agrees by default. A
symlinked FILE inside a scanned tree is skipped too, which matches `-r`.

EVERY LOOP VARIABLE THAT WAS AN OUT-PARAMETER IS NOW A RETURN VALUE. `scan()`
returns its findings as a list of message strings rather than logging them and
setting a global, so the two control scans no longer need `2>/dev/null` to stay
quiet and cannot accidentally print into a caller's output.
"""

import os
import pathlib
import re
import sys
import tempfile
import time

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The three roots and their environment overrides, exactly as the twin names
# them. Space-separated strings rather than lists, because the twin word-splits
# them and the SPLIT STRING is what appears in the finding text.
TEST_DIRS_ENV = "DEAD_CASE_TEST_DIRS"
MEDIA_DIRS_ENV = "DEAD_CASE_MEDIA_DIRS"
CODE_DIRS_ENV = "DEAD_CASE_CODE_DIRS"

DEFAULT_TEST_DIRS = ".ci/scripts/test"
DEFAULT_MEDIA_DIRS = ".ci/media"
DEFAULT_CODE_DIRS = ".ci/scripts scripts packages/www/scripts"

# POSIX [[:space:]], written out rather than abbreviated to `\s`, which is wider
# in Python and would match a non-breaking space grep never sees.
SPACE = r"[ \t\n\v\f\r]"

# A case-arm line: starts with an optional `*`, carries at least one
# double-quoted glob segment, and ENDS in `)` (optionally followed by a
# command on the same line). The earlier attempt anchored on `)$`, which
# missed the common `... ) ;;` and `... )` -with-trailing-code shapes and
# made this gate's own control fail -- which is exactly what the control
# is for.
CASE_ARM = re.compile(r'^%s*\*[^)]*"[^"]*"[^)]*\)' % SPACE)

# The second grep of `extract_case_keys`, dropping a matched line whose CONTENT
# is a comment. Applied to the whole `path:lineno:content` string, so the
# `[^:]+:[0-9]+:` prefix is part of the pattern and not stripped first.
COMMENT_HIT = re.compile(r"^[^:]+:[0-9]+:%s*#" % SPACE)

# Every quoted segment on a matched line, and every `ident=` token inside one.
# The identifier needs at least THREE characters before the `=`, which is what
# `{2,}` after the first character means and what keeps `a=` out.
QUOTED = re.compile(r'"[^"]*"')
KEY_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}=")

# A line that does not count as a live reference: a comment in shell, C or a
# block-comment continuation. `grep -qvE` over the hits, so ONE non-comment line
# anywhere makes the key live.
CODE_COMMENT = re.compile(r"^%s*(#|//|\*)" % SPACE)

# The directory name `--exclude-dir=test` removes, at any depth.
EXCLUDED_DIR = "test"


def split_dirs(value: str) -> list[str]:
    """Bash word-splitting on unquoted `$CODE_DIRS`. Whitespace, no globbing."""
    return value.split()


def _walk_files(root: pathlib.Path, exclude_dir: str | None = None):
    """Every regular, non-symlinked, non-binary file under `root`.

    THREE EXCLUSIONS, EACH MATCHING A grep FLAG OR BEHAVIOUR:
      * directory symlinks are not descended, because `-r` does not follow them
        (`-R` would), and `paths.walk_tree` passes `followlinks=False` explicitly
      * file symlinks are skipped, matching `-r` on a symlink found in the tree
      * a file containing a NUL byte is skipped, because ugrep treats it as
        binary and reports nothing at all; see the port notes

    A FOURTH EXCLUSION IS NOT grep's, and is named separately so it is not read as
    one: `paths.walk_tree` also prunes `.git`, `node_modules` and
    `.claude/worktrees`. The last is a peer session's sibling checkout of this
    repository, git-excluded and therefore invisible to CI, which a raw `os.walk`
    happily descended into and scanned as if it were source.
    """
    if root.is_file():
        candidates = [root]
    elif root.is_dir():
        candidates = []
        extra = () if exclude_dir is None else (exclude_dir,)
        for dirpath, _dirnames, filenames in paths.walk_tree(root, exclude_dirs=extra):
            for name in filenames:
                candidates.append(pathlib.Path(dirpath) / name)
    else:
        # A root that does not exist. `grep`'s complaint goes to /dev/null in
        # the twin and the walk simply yields nothing here.
        return
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        yield path, data.decode("utf-8", "replace")


def extract_case_keys(dirs: list[str], base: pathlib.Path) -> list[str]:
    """`grep -rnE '<case arm>' <dirs> | grep -vE '<comment hit>'`.

    Returns `path:lineno:content` strings with the path spelled exactly as the
    argument was, because that spelling is what lands in the finding text: a
    relative root gives relative paths and an absolute root gives absolute ones,
    on both sides.
    """
    out: list[str] = []
    for spec in dirs:
        root = pathlib.Path(spec)
        absolute = root if root.is_absolute() else base / root
        for path, text in _walk_files(absolute):
            # Re-spell the path the way grep would have printed it: the argument
            # as given, plus the part below it.
            try:
                suffix = path.relative_to(absolute)
                shown = spec if str(suffix) == "." else os.path.join(spec, str(suffix))
            except ValueError:  # pragma: no cover - defensive
                shown = str(path)
            for number, line in enumerate(text.split("\n"), start=1):
                if not CASE_ARM.search(line):
                    continue
                hit = "%s:%d:%s" % (shown, number, line)
                if COMMENT_HIT.search(hit):
                    continue
                out.append(hit)
    return out


def key_is_live(key: str, code_dirs: list[str], base: pathlib.Path) -> bool:
    r"""Does `key=` occur AS CODE in any non-test file under `code_dirs`?

        grep -rhE --exclude-dir=test "${key}=" $CODE_DIRS | grep -qvE '^\s*(#|//|\*)'

    ONE non-comment hit anywhere is enough, which is deliberately generous: this
    gate deletes nothing, but a false POSITIVE tells an author their assertion is
    dead when it is not, and that costs more than a missed dead arm. Over-count
    life on purpose.
    """
    needle = re.compile(re.escape(key) + "=")
    for spec in code_dirs:
        root = pathlib.Path(spec)
        absolute = root if root.is_absolute() else base / root
        for _path, text in _walk_files(absolute, exclude_dir=EXCLUDED_DIR):
            for line in text.split("\n"):
                if needle.search(line) and not CODE_COMMENT.search(line):
                    return True
    return False


def keys_in(hit: str) -> list[str]:
    """Every `ident=` key inside a quoted segment of one grep hit, sorted unique.

    Two chained `grep -o`s in the twin: quoted segments first, then identifier
    tokens inside them. Run over the WHOLE line including the `path:lineno:`
    prefix; see the port notes.
    """
    keys: set[str] = set()
    for segment in QUOTED.findall(hit):
        for token in KEY_TOKEN.findall(segment):
            keys.add(token[:-1])
    return sorted(keys)


def scan(
    dirs: list[str], code_dirs: list[str], base: pathlib.Path, code_dirs_text: str
) -> list[str]:
    """Every dead-arm finding, as the message the twin logs. Empty means clean.

    RETURNS A LIST, NEVER A COUNT AND NEVER AN EXIT STATUS. See the module
    docstring: the twin's earlier shape returned the count as the status, which
    a shell takes mod 256, so exactly 256 dead arms read as a clean tree.
    """
    findings: list[str] = []
    for hit in extract_case_keys(dirs, base):
        if hit == "":
            continue
        # `${line%%:*}` and `cut -d: -f2`: the path is everything before the
        # FIRST colon and the line number is the second colon-separated field.
        # A path containing a colon breaks both, identically on both sides.
        parts = hit.split(":")
        path = parts[0]
        lineno = parts[1] if len(parts) > 1 else ""
        for key in keys_in(hit):
            if key_is_live(key, code_dirs, base):
                continue
            findings.append(
                "%s:%s: case arm globs for '%s=' but no non-test script under %s emits "
                "that field, so this arm is DEAD and the assertion around it cannot fail"
                % (path, lineno, key, code_dirs_text)
            )
    return findings


def media_shell_files(media_dirs: list[str], base: pathlib.Path) -> int:
    """`for _f in "$_d"/*.sh` -- TOP LEVEL ONLY, not a recursive count.

    COUNTED WITHOUT A PIPELINE in the twin, and the reason is carried:
    "`find ... | wc -l` is what check:ci-silent-failures forbids here: under
    `set -eo pipefail` a find that exits non-zero takes the whole script down
    mid-count, and the number it was computing is the one thing standing between
    a collapsed glob and a green report."
    """
    total = 0
    for spec in media_dirs:
        root = pathlib.Path(spec)
        absolute = root if root.is_absolute() else base / root
        if not absolute.is_dir():
            continue
        for entry in absolute.glob("*.sh"):
            if entry.is_file():
                total += 1
    return total


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 on a control failure, a vacuous root, or a
    dead arm.

    `--selftest` is intercepted BEFORE any real scan. The twin documents itself
    as taking no arguments ("Usage: check-dead-case-arms.sh") and ignores any it
    is given.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    test_dirs_text = os.environ.get(TEST_DIRS_ENV) or DEFAULT_TEST_DIRS
    media_dirs_text = os.environ.get(MEDIA_DIRS_ENV) or DEFAULT_MEDIA_DIRS
    code_dirs_text = os.environ.get(CODE_DIRS_ENV) or DEFAULT_CODE_DIRS
    code_dirs = split_dirs(code_dirs_text)

    with tempfile.TemporaryDirectory() as control_dir:
        control = pathlib.Path(control_dir)

        # -------------------------------------------------------------------
        # CONTROL FIRST. Plant the exact defect this gate exists for and require
        # the scanner to catch it. A gate that has never been seen to fire is
        # indisputably worthless, and this one would otherwise report a clean
        # tree forever.
        # -------------------------------------------------------------------
        (control / "test").mkdir(parents=True)
        # The planted key is GENERATED, never a literal. A literal placed here
        # would live in this very file, which sits inside CODE_DIRS, so
        # key_is_live would find it and call the planted arm "live" -- the
        # control would then pass by accident and this gate would report a clean
        # tree without ever having caught anything. Found by the control failing
        # on its first run, which is the whole argument for putting the control
        # before the scan.
        planted_key = "deadarmprobe%d%d" % (os.getpid(), int(time.time()))
        (control / "test" / "planted.sh").write_text(
            'case "$out" in\n    *"%s=20"* | *"%s=1"*)\n        log_fail "planted dead arm" ;;\n'
            "esac\n" % (planted_key, planted_key),
            encoding="utf-8",
        )
        if not scan([str(control / "test")], code_dirs, root, code_dirs_text):
            log.error(
                "CONTROL FAILED: the scanner did not catch a planted dead case arm, so "
                "its verdict on the real tree means nothing"
            )
            return 1

        # -------------------------------------------------------------------
        # THE MEDIA SCAN ROOT, CONTROLLED IN BOTH DIRECTIONS.
        #
        # Adding a directory to a scan is the easiest change in this file to get
        # wrong in a way that reports success: name the variable, forget to pass
        # it, and the gate goes on scanning what it always scanned while its
        # output claims a wider corpus. One control cannot catch that on its own
        # -- a scanner that flagged EVERYTHING would also fire on a planted arm
        # -- so both directions are required here:
        #
        #   FIRES on a dead arm placed in a media-shaped root, and
        #   STAYS SILENT on a live one whose key a real emitter does produce.
        #
        # The live half points CODE_DIRS at a generated emitter rather than
        # hoping some existing key is still live, for the same reason the
        # planted key is generated: a literal written here would live in this
        # file, inside CODE_DIRS, and vouch for itself.
        # -------------------------------------------------------------------
        for name in ("media", "media-live", "media-code"):
            (control / name).mkdir(parents=True)
        media_planted_key = "mediadeadprobe%d%d" % (os.getpid(), int(time.time()))
        (control / "media" / "planted.sh").write_text(
            'case "$1" in\n    *"%s=1"*) exit 1 ;;\nesac\n' % media_planted_key,
            encoding="utf-8",
        )
        if not scan([str(control / "media")], code_dirs, root, code_dirs_text):
            log.error(
                "CONTROL FAILED: a dead case arm planted in a media scan root was not "
                "caught, so scanning %s asserts nothing" % media_dirs_text
            )
            return 1

        media_live_key = "medialiveprobe%d%d" % (os.getpid(), int(time.time()))
        (control / "media-code" / "emit.sh").write_text(
            'printf "%s=%%s\\n" "$x"\n' % media_live_key, encoding="utf-8"
        )
        (control / "media-live" / "live.sh").write_text(
            'case "$1" in\n    *"%s=1"*) exit 1 ;;\nesac\n' % media_live_key, encoding="utf-8"
        )
        if scan([str(control / "media-live")], [str(control / "media-code")], root, code_dirs_text):
            log.error(
                "CONTROL FAILED: an arm whose key a real emitter DOES produce was reported "
                "dead, so the media scan is a blanket refusal rather than a check"
            )
            return 1

    # VACUITY FLOOR for the new root. A scan root that has stopped matching
    # files reports clean forever, which is the same green as a clean tree and
    # tells them apart never.
    media_files = media_shell_files(split_dirs(media_dirs_text), root)
    if media_files == 0:
        log.error(
            "VACUOUS: the media scan root (%s) holds no shell files, so scanning it "
            "proves nothing" % media_dirs_text
        )
        return 1

    # -----------------------------------------------------------------------
    # The real scan.
    # -----------------------------------------------------------------------
    real = scan(
        split_dirs(test_dirs_text) + split_dirs(media_dirs_text), code_dirs, root, code_dirs_text
    )
    for finding in real:
        log.error(finding)
    if real:
        log.error(
            "%d dead case arm(s). Parse the data and assert on the PARSED value instead "
            "of globbing for a field name that may not exist." % len(real)
        )
        return 1

    log.info(
        "no dead case arms across %s %s (%d media shell file(s); the planted-arm control "
        "fired and the live-arm control stayed silent, so this verdict is real)"
        % (test_dirs_text, media_dirs_text, media_files)
    )
    return 0


def selftest() -> int:
    """Plant a dead arm, prove it fires; make it live, prove it stops.

    BOTH DIRECTIONS FOR EVERY RULE. This gate is a LIVENESS question, and a
    liveness check has exactly two ways to be useless: it can call everything
    dead (a blanket refusal, which the twin's media-live control exists to
    forbid) or everything live (which is what a missing comment-stripping rule
    produces, and is the 2026-08-05 self-vaccination).
    """
    ctl = Controls("dead-case-arms", floor=24, verbose=True)

    # -- the case-arm recogniser ------------------------------------------
    ctl.check(
        "ARM: the founding shape is recognised",
        bool(CASE_ARM.search('    *"cores=20"* | *"cores=1[0-9]"*)')),
        True,
    )
    ctl.check(
        "ARM: an arm with a trailing command on the same line is recognised",
        bool(CASE_ARM.search('    *"a=1"*) exit 1 ;;')),
        True,
    )
    ctl.check(
        "MIRROR: an assignment is not an arm",
        bool(CASE_ARM.search('FOO="bar=1"')),
        False,
    )
    ctl.check(
        "MIRROR: an arm with no quoted segment is not matched",
        bool(CASE_ARM.search("    *foo*)")),
        False,
    )

    # -- key extraction ----------------------------------------------------
    ctl.check(
        "KEYS: both keys of a two-glob arm are extracted, sorted and unique",
        keys_in('f.sh:3:    *"cores=20"* | *"mem_kb=1"* | *"cores=9"*)'),
        ["cores", "mem_kb"],
    )
    ctl.check(
        "KEYS: an identifier shorter than three characters is not a key",
        keys_in('f.sh:3:    *"ab=1"*)'),
        [],
    )
    ctl.check(
        "KEYS: exactly three characters IS a key",
        keys_in('f.sh:3:    *"abc=1"*)'),
        ["abc"],
    )
    ctl.check(
        "MIRROR: an unquoted key= contributes nothing",
        keys_in("f.sh:3:    *cores=20*)"),
        [],
    )

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        tests = base / "t"
        code = base / "c"
        tests.mkdir()
        code.mkdir()

        # A generated key, for the same reason the gate generates its own: a
        # literal here would live in this file, inside the repository's real
        # CODE_DIRS, and vouch for itself the next time the gate ran.
        dead_key = "selftestdeadprobe%d" % os.getpid()
        live_key = "selftestliveprobe%d" % os.getpid()

        (tests / "arm.sh").write_text(
            'case "$out" in\n    *"%s=1"*) log_fail "x" ;;\nesac\n' % dead_key, encoding="utf-8"
        )
        (code / "emit.sh").write_text('printf "%s=%%s\\n" "$x"\n' % live_key, encoding="utf-8")

        ctl.check(
            "PLANT: an arm whose key nothing emits is DEAD",
            len(scan([str(tests)], [str(code)], base, "c")),
            1,
        )
        (tests / "arm.sh").write_text(
            'case "$out" in\n    *"%s=1"*) log_fail "x" ;;\nesac\n' % live_key, encoding="utf-8"
        )
        ctl.check(
            "MIRROR: an arm whose key a real emitter produces is LIVE",
            scan([str(tests)], [str(code)], base, "c"),
            [],
        )

        # THE FOUNDING DEFECT, as a control. A key that appears ONLY in a
        # comment must not count as live, or the gate immunises itself against
        # every pattern anyone documents.
        (tests / "arm.sh").write_text(
            'case "$out" in\n    *"%s=1"*) log_fail "x" ;;\nesac\n' % dead_key, encoding="utf-8"
        )
        (code / "doc.sh").write_text(
            "# the sampler never emits %s=20\n" % dead_key, encoding="utf-8"
        )
        ctl.check(
            "PLANT: a key mentioned only in a COMMENT does not make an arm live",
            len(scan([str(tests)], [str(code)], base, "c")),
            1,
        )
        ctl.check(
            "MIRROR: a key that is live is not resurrected into deadness by the comment",
            key_is_live(live_key, [str(code)], base),
            True,
        )
        ctl.check(
            "MIRROR: the comment-only key is not live",
            key_is_live(dead_key, [str(code)], base),
            False,
        )
        # All three comment markers, and a mirror for each: the same text as
        # code IS live.
        for marker in ("#", "//", "*"):
            (code / "doc.sh").write_text("%s %s=20\n" % (marker, dead_key), encoding="utf-8")
            ctl.check(
                "COMMENT: a %r line is not a live reference" % marker,
                key_is_live(dead_key, [str(code)], base),
                False,
            )
        (code / "doc.sh").write_text("x=%s=20\n" % dead_key, encoding="utf-8")
        ctl.check(
            "MIRROR: the same token as CODE is a live reference",
            key_is_live(dead_key, [str(code)], base),
            True,
        )

        # `--exclude-dir=test`: a directory named exactly `test` cannot vouch
        # for a key. Its mirror is a directory whose name merely CONTAINS test.
        (code / "doc.sh").unlink()
        (code / "test").mkdir()
        (code / "test" / "e.sh").write_text("%s=20\n" % dead_key, encoding="utf-8")
        ctl.check(
            "EXCLUDE: a file under a directory named 'test' does not make a key live",
            key_is_live(dead_key, [str(code)], base),
            False,
        )
        (code / "testdata").mkdir()
        (code / "testdata" / "e.sh").write_text("%s=20\n" % dead_key, encoding="utf-8")
        ctl.check(
            "MIRROR: 'testdata' is not 'test' and DOES make a key live",
            key_is_live(dead_key, [str(code)], base),
            True,
        )

        # A binary file is invisible to the scanner, matching ugrep.
        (tests / "bin.sh").write_bytes(
            b'case "$1" in\n    *"zzzbinprobe=1"*) exit 1 ;;\nesac\n\x00\n'
        )
        ctl.check(
            "BINARY: a file carrying a NUL byte is skipped entirely",
            [h for h in extract_case_keys([str(tests)], base) if "bin.sh" in h],
            [],
        )

        ctl.check(
            "MEDIA COUNT: top-level .sh files only, not a recursive walk",
            media_shell_files([str(tests)], base),
            2,
        )
        ctl.check(
            "MEDIA COUNT: an absent root contributes zero",
            media_shell_files([str(base / "nope")], base),
            0,
        )

    # -- the whole gate, driven through its environment overrides ----------
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        for name in ("t", "m", "c"):
            (base / name).mkdir()
        (base / "m" / "keep.sh").write_text("echo media\n", encoding="utf-8")

        def run() -> int:
            saved = {
                key: os.environ.get(key)
                for key in (paths.ROOT_ENV, TEST_DIRS_ENV, MEDIA_DIRS_ENV, CODE_DIRS_ENV)
            }
            os.environ[paths.ROOT_ENV] = str(base)
            os.environ[TEST_DIRS_ENV] = "t"
            os.environ[MEDIA_DIRS_ENV] = "m"
            os.environ[CODE_DIRS_ENV] = "c"
            try:
                return main([])
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        ctl.check("CONTROL: an empty scan root with a populated media root passes", run(), 0)

        probe = "gateprobe%d" % os.getpid()
        (base / "t" / "arm.sh").write_text(
            'case "$out" in\n    *"%s=1"*) log_fail "x" ;;\nesac\n' % probe, encoding="utf-8"
        )
        ctl.check("PLANT: a dead arm in the real scan reds", run(), 1)

        (base / "c" / "emit.sh").write_text('printf "%s=%%s\\n" "$x"\n' % probe, encoding="utf-8")
        ctl.check("MIRROR: adding a real emitter turns the same arm green", run(), 0)

        # THE VACUITY FLOOR. An empty media root must refuse, never pass.
        (base / "m" / "keep.sh").unlink()
        ctl.check("VACUITY: an empty media scan root reds", run(), 1)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
