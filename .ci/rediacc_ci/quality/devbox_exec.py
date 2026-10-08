"""`devbox_docker` CAN ANSWER TWO WORDS, and every consumer must treat it that way.

The subject is `.ci/rediacc_ci/core/devbox.py`, the Python port of the retired `.ci/lib/devbox.sh`.

WHAT WENT WRONG, measured 2026-08-26 in the bash original: `sudo docker: command not found`. `devbox_docker` answers plain `docker` when the caller's shell already has the docker group and the TWO-WORD string `sudo docker` when it does not. One call site, `devbox_exec` (the lane every gate routes through), passed that answer as ONE command name, so every routed gate died on any host where docker needs sudo, which is the default on a fresh Linux machine.

THE SAME SHAPE EXISTS IN THE PORT. `Devbox.docker_words()` returns the answer already split into a list, and a call site that writes `[d, "exec", ...]` instead of `[*d, "exec", ...]` hands subprocess one argv element holding two words. That is B1, and it is invisible wherever CI runs, because runners already grant docker without sudo and the failing branch is never taken. The defect is fully visible in the SOURCE, so the gate is static.

B2: the exec into the devbox names the user BY NAME (`-u vscode`), never by numeric id. The devbox runs a local layer whose `vscode` carries the host identity, so the name is correct on Linux, macOS (501:20) and WSL2, while a numeric id is correct only where the host's numbering means something inside the container. The wrong identity makes git refuse the worktree ("dubious ownership"), `git ls-files` return empty, and a gate report green over zero files.

THE ANTI-VACUITY FLOOR counts the `*d` / `*words` splat sites: a count below MIN_SITES means the enumeration broke, not that the code is clean.

THE SCANS READ WHOLE-LINE-COMMENT-BLANKED TEXT, with line numbers preserved: the wrong shapes are explained in docstrings and comments throughout, and a scan that read them would fail on its own documentation. Docstring text is not blanked, so a docstring must not spell the wrong shape as code.

WHAT THIS GATE CANNOT SEE: it reasons about core/devbox.py's own call sites. A new file elsewhere that builds a docker argv from `docker_words()` on its own is out of scope.
"""

import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The subject, repo-relative. This gate reasons about ONE file's call sites.
DEVBOX_REL = ".ci/rediacc_ci/core/devbox.py"

# B1: a list literal whose first element is the bare variable `d`/`words` (a single argv element) instead of its splat. Spans lines.
BUG_RE = re.compile(r"\[\s*(?:d|words)\s*[,\]]")

# The anti-vacuity denominator: every splat of the split docker answer into an argv.
SITE_RE = re.compile(r"\*(?:d|words)\b")

# B2: a `-u` argv element whose value is anything but the literal "vscode", or a `-u <value>` inside one string.
NUMERIC_RE = re.compile(r"\"-u\",\s*(?!\s|\"vscode\")|[\"']-u[ =]")

# The floor under B1's enumeration: core/devbox.py carries 34 splat sites (measured), so a count below this means the enumeration broke.
MIN_SITES = 10


def code_of(text: str) -> str:
    """Whole-line `#` comments blanked, line numbers preserved.

    Every explanation of the WRONG shape in this repo lives in a comment, so a scan for that shape must read code only or it fails on its own documentation.
    """
    return "\n".join("" if re.match(r"^[ \t]*#", line) else line for line in text.split("\n"))


def find(pattern: re.Pattern, text: str) -> list[str]:
    """`<line>:<matched line>` for every match, numbered from ONE in `text` (the true file line, since `code_of` keeps blanks)."""
    lines = text.split("\n")
    return [
        "%d:%s" % (text.count("\n", 0, m.start()) + 1, lines[text.count("\n", 0, m.start())])
        for m in pattern.finditer(text)
    ]


def count(pattern: re.Pattern, text: str) -> int:
    """How many LINES carry a match."""
    return len([line for line in text.split("\n") if pattern.search(line)])


# --------------------------------------------------------------------------- The controls, built by CONCATENATION.
#
# Never by substituting into a copy of the real file: a substitution silently yields an identical copy when the targeted line is later reworded, and the control then passes against unmutated source. ---------------------------------------------------------------------------

CONTROL_BAD = 'd = self.sub(self.docker)[1]\nself.run([d, "exec", "-u", "vscode", cid])\n'

CONTROL_BAD_MULTILINE = 'self.run(\n    [\n        d,\n        "exec",\n    ]\n)\n'

CONTROL_GOOD = (
    "d = self.docker_words()\n"
    'self.run([*d, "exec", "-u", "vscode", cid])\n'
    'self.run([*words, *flags, cid, "bash"])\n'
)

CONTROL_NUMERIC = 'self.run([*d, "exec", "-u", "%d:%d" % (uid, gid), cid])\n'

CONTROL_COMMENT = '# [d, "exec", "-u", "0"] -- the wrong shape, explained in a comment\n'


def main(argv: list[str] | None = None) -> int:
    """Run B1, B2, their anti-vacuity floor and the controls. 0 clean, 1 otherwise."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    devbox = root / DEVBOX_REL

    fails = 0

    def fail(message: str) -> None:
        nonlocal fails
        print("  FAIL %s" % message)
        fails += 1

    def ok(message: str) -> None:
        print("  ok   %s" % message)

    if not devbox.is_file():
        print("✗ subject under test is missing: %s" % devbox)
        return 1

    code = code_of(devbox.read_text(encoding="utf-8", errors="replace"))

    # --- B1. devbox_docker's answer is never passed as one argv element -----
    hits = find(BUG_RE, code)
    if not hits:
        ok("B1. no call site passes devbox_docker's two-word answer as one argv element")
    else:
        fail("B1. these pass a possibly-two-word docker as a single argv element:")
        for line in hits:
            print("         %s" % line)

    # Anti-vacuity: B1 is a scan, and a scan over nothing passes.
    sites = count(SITE_RE, code)
    if sites >= MIN_SITES:
        ok("B1 anti-vacuity: %d docker invocation(s) actually scanned" % sites)
    else:
        fail("B1 SCANNED ALMOST NOTHING (%d sites) -- the enumeration broke, not the code" % sites)

    # --- B2. nothing execs into the devbox under a numeric identity ---------
    numeric = find(NUMERIC_RE, code)
    if not numeric:
        ok("B2. container exec uses -u vscode by name, never a numeric id")
    else:
        fail("B2. numeric -u would break on macOS/WSL2 and can yield a vacuous green:")
        for line in numeric:
            print("         %s" % line)

    # --- controls, by CONSTRUCTION -----------------------------------------
    if find(BUG_RE, code_of(CONTROL_BAD)):
        ok("B1 control: a one-element docker argv is detected")
    else:
        fail("B1 CONTROL DID NOT FIRE: the planted defect went undetected")

    if find(BUG_RE, code_of(CONTROL_GOOD)):
        fail("B1 IS OVER-BROAD: splatted forms were flagged")
    else:
        ok("B1 control: splatted forms are not flagged")

    if find(NUMERIC_RE, code_of(CONTROL_NUMERIC)):
        ok("B2 control: a numeric container identity is detected")
    else:
        fail("B2 CONTROL DID NOT FIRE: a numeric -u went undetected")

    if find(NUMERIC_RE, code_of(CONTROL_COMMENT)) or find(BUG_RE, code_of(CONTROL_COMMENT)):
        fail("B1/B2 ARE OVER-BROAD: prose describing the wrong shape was flagged as code")
    else:
        ok("B1/B2 control: a comment describing the bad shape is not flagged")

    print()
    if fails == 0:
        print("✓ devbox exec: %d docker invocation(s), none mis-passed." % sites)
        print("  Blind spot: scoped to core/devbox.py's own call sites; a new file")
        print("  that builds a docker argv independently is not covered.")
        return 0
    print("✗ devbox exec: %d failure(s)." % fails)
    return 1


# --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------


def selftest() -> int:
    """Both directions for both detectors, plus the floor and the comment filter."""
    ctl = Controls("devbox-exec", floor=21, verbose=True)

    ctl.truthy("PLANT: a one-element docker argv is detected", find(BUG_RE, code_of(CONTROL_BAD)))
    ctl.truthy(
        "PLANT: the same defect spread over several lines is detected",
        find(BUG_RE, code_of(CONTROL_BAD_MULTILINE)),
    )
    ctl.check("MIRROR: splatted forms are not flagged", find(BUG_RE, code_of(CONTROL_GOOD)), [])
    ctl.truthy("PLANT: `[words]` alone is the same defect", find(BUG_RE, "x = [words]\n"))
    ctl.check(
        "MIRROR: `d` as a later element is not flagged",
        find(BUG_RE, 'self.run(["echo", d])\n'),
        [],
    )
    ctl.check(
        "MIRROR: a comment carrying the defect shape is blanked before the scan",
        find(BUG_RE, code_of('# [d, "exec"] -- the wrong shape\n')),
        [],
    )
    ctl.check(
        "the reported line is the TRUE file line",
        find(BUG_RE, code_of('# a\n# b\nself.run([d, "x"])\n')),
        ['3:self.run([d, "x"])'],
    )

    ctl.truthy("PLANT: a numeric container identity is detected", find(NUMERIC_RE, CONTROL_NUMERIC))
    ctl.truthy(
        "PLANT: a `-u` value on the next line is detected",
        find(NUMERIC_RE, '"-u",\n    uid,\n'),
    )
    ctl.truthy("PLANT: `-u 0` inside one string is detected", find(NUMERIC_RE, '"-u 0"\n'))
    ctl.check(
        "MIRROR: a comment describing the bad shape is not flagged",
        find(NUMERIC_RE, code_of(CONTROL_COMMENT)),
        [],
    )
    ctl.check(
        "MIRROR: `-u vscode` by NAME is not flagged",
        find(NUMERIC_RE, '["exec", "-u", "vscode", cid]\n'),
        [],
    )
    ctl.check(
        "MIRROR: `-u vscode` split over lines is not flagged",
        find(NUMERIC_RE, '"-u",\n    "vscode",\n'),
        [],
    )

    ctl.check(
        "a whole-line comment is BLANKED, keeping the numbering",
        code_of("# gone\nkept\n"),
        "\nkept\n",
    )
    ctl.check("an INLINE comment survives", code_of("kept # tail\n"), "kept # tail\n")
    ctl.check("count counts LINES, not matches", count(SITE_RE, "*d a *d b\n*d c\n"), 2)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        def run(body: str | None) -> int:
            target = root / DEVBOX_REL
            target.parent.mkdir(parents=True, exist_ok=True)
            if body is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_text(body, encoding="utf-8")
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    os.environ.pop(paths.ROOT_ENV, None)
                else:
                    os.environ[paths.ROOT_ENV] = saved

        clean = "".join('self.run([*d, "exec", "-u", "vscode", "c%d"])\n' % i for i in range(12))
        ctl.check("MIRROR: a clean devbox.py with 12 sites passes", run(clean), 0)
        ctl.check("PLANT: one single-element call site reds", run(clean + 'x([d, "exec"])\n'), 1)
        ctl.check(
            "PLANT: a numeric identity reds",
            run(clean + 'x([*d, "exec", "-u", ids])\n'),
            1,
        )
        ctl.check(
            "PLANT: a devbox.py with too FEW sites trips the anti-vacuity floor",
            run('self.run([*d, "exec"])\n'),
            1,
        )
        ctl.check("PLANT: a missing subject reds rather than skipping", run(None), 1)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
