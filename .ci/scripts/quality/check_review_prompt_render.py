#!/usr/bin/env python3
"""The review prompt must survive the text it substitutes into itself.

WHY THIS EXISTS, and it is the i18n lesson exactly. On 2026-08-31 the FIRST epic-scoped
Claude Review of PR #583 (run 33445357414, job 99663191041) died before it began:

    sed: -e expression #6, char 77: unterminated `s' command
    ##[error]Matching delimiter not found 'CLAUDE_REVIEW_PROMPT_EOF'

Expression #6 is {{EPIC_SCOPE}}, and `epic_scope` is a SEVEN-LINE paragraph the gate script
authors itself. A `s` command's replacement may not contain a raw newline: the first one
ends the expression and the rest is parsed as more sed script. sed exited non-zero, which
truncated the heredoc being written to $GITHUB_OUTPUT, and the whole review never ran.

THE COST WAS NOT ONE RED RUN. `Review Complete` is a REQUIRED check, and the reviewer is
checked out at a hardcoded `ref: main` (claude-review-reusable.yml:165-169, asserted at
:177). So main's broken copy could not review anything, the required check could never
post, and every PR was unmergeable without an operator bypass -- including the PR carrying
the fix. Breaking that loop cost a one-time protection bypass on 2026-09-02.

WHY NO EXISTING GATE CAUGHT IT, checked before writing this one. `check-rubric-calibration`
hashes the PROMPT TEXT of the judged rubrics against a manifest -- it proves the wording did
not drift and says nothing about whether the substitution RENDERS. Nothing else executes
emit_prompt at all. The defect was invisible by construction, which is this gate's whole
reason to exist.

WHAT IT CHECKS. Not the wording, and not that a particular escape helper exists by name:
those are implementation. It checks the BEHAVIOUR that failed -- that substituting a value
containing a newline, a `|`, an `&` and a backslash still produces a rendered prompt with
no placeholder left behind. A future refactor that drops the escaping fails here even if it
spells the helper differently or drops it entirely.
"""

import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GATE = os.path.join(ROOT, ".ci", "scripts", "review", "claude-review-gate.sh")

# The exact shape that broke it: seven lines, and one of every character that is unsafe in
# a sed replacement. A single-line fixture passes against the BROKEN code and would make
# this gate vacuous, which is why the newline is not optional.
HOSTILE = """SCOPE: this pass reviews ONLY epic 23ac415a. Its commits are
selected with `git log --grep`, and a pipe | is ordinary prose here.
An ampersand & expands to the whole match in a sed replacement.
A backslash \\ starts an escape sequence.
Line five exists because the real scope is seven lines.
Line six likewise.
Line seven ends it."""

PLACEHOLDERS = ("{{REPO}}", "{{PR_NUMBER}}", "{{HEAD_SHA}}", "{{EPIC_SCOPE}}")


def extract(func_name, src):
    """The named shell function's source, or "" when it is absent.

    Absence is not an error here: the gate asserts BEHAVIOUR, and a rewrite that renames or
    inlines the helper should pass on its merits rather than fail on a missing symbol.
    """
    m = re.search(r"^%s\(\)\s*\{\n(.*?)^\}" % re.escape(func_name), src, re.DOTALL | re.MULTILINE)
    return m.group(1) if m else ""


def render(escaper_body, scope):
    """Substitute `scope` into a template the way the gate script does; "" on failure.

    Runs the REAL shell rather than reimplementing sed's quoting rules in Python. A
    reimplementation would be a second thing to drift, and drift is the defect class.
    """
    helper = (
        "sed_replacement() {\n%s\n}\n" % escaper_body
        if escaper_body
        else "sed_replacement() { printf '%s' \"$1\"; }\n"
    )
    script = (
        helper
        + "scope=$1\n"
        + 'printf "EPIC: {{EPIC_SCOPE}}\\nREPO: {{REPO}}\\n" | '
        + 'sed -e "s|{{EPIC_SCOPE}}|$(sed_replacement "$scope")|g" '
        + '-e "s|{{REPO}}|$(sed_replacement "rediacc/console")|g"\n'
    )
    try:
        p = subprocess.run(
            ["bash", "-c", script, "bash", scope],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return p.stdout if p.returncode == 0 else ""


def selftest():
    """Controls, both directions. A gate that cannot fail is worse than none."""
    ok = True

    def check(label, cond):
        nonlocal ok
        if cond:
            print("  PASS  %s" % label)
        else:
            ok = False
            print("  FAIL  %s" % label, file=sys.stderr)

    # THE SANITY CONTROL, and it is the whole gate. With NO escaping -- the code that
    # actually shipped on main -- the hostile scope must produce nothing. If this ever
    # passes, sed stopped caring about raw newlines and this gate is measuring nothing.
    check("SANITY: an unescaped multi-line scope renders NOTHING", render("", HOSTILE) == "")
    check(
        "CONTROL: unescaped is fine on a single-line scope (so the newline is load-bearing)",
        render("", "one harmless line") != "",
    )
    good = "    local s=$1\n    s=${s//\\\\/\\\\\\\\}\n    s=${s//|/\\\\|}\n    s=${s//&/\\\\&}\n    printf '%s' \"${s//$'\\n'/\\\\$'\\n'}\"\n"
    out = render(good, HOSTILE)
    check("SANITY: a correct escaper renders the hostile scope", out != "")
    check("CONTROL: every line of the scope survives", out.count("\n") >= 8)
    check("CONTROL: the pipe survives", "pipe | is ordinary" in out)
    check("CONTROL: the ampersand survives literally", "ampersand & expands" in out)
    check("CONTROL: the backslash survives", "backslash \\ starts" in out)
    # Escaping only the newline is NOT enough, and a partial fix must not read as a pass.
    nl_only = "    printf '%s' \"${1//$'\\n'/\\\\$'\\n'}\"\n"
    partial = render(nl_only, HOSTILE)
    check(
        "SANITY: escaping ONLY newlines still corrupts the & and | cases",
        partial == "" or "ampersand & expands" not in partial,
    )
    return ok


def main():
    if "--selftest" in sys.argv[1:]:
        return 0 if selftest() else 1
    if not selftest():
        print("REFUSING to report on the tree: this gate's own controls failed.", file=sys.stderr)
        return 1

    if not os.path.exists(GATE):
        print("missing %s -- the scan is broken, not the tree." % GATE, file=sys.stderr)
        return 1
    with open(GATE, encoding="utf-8") as fh:
        src = fh.read()

    # The corpus floor: the substitution block must still be here. If someone deletes
    # emit_prompt entirely this gate must go red rather than silently find nothing.
    if "{{EPIC_SCOPE}}" not in src:
        print(
            "no {{EPIC_SCOPE}} substitution in claude-review-gate.sh. Either the prompt\n"
            "template moved (rewire this gate) or the epic scope was dropped.",
            file=sys.stderr,
        )
        return 1

    out = render(extract("sed_replacement", src), HOSTILE)
    problems = []
    if not out:
        problems.append(
            "substituting a 7-line epic scope produced NOTHING -- sed exited non-zero, "
            "exactly as in run 33445357414"
        )
    else:
        left = [p for p in PLACEHOLDERS if p in out]
        if left:
            problems.append("placeholder(s) left unrendered: %s" % ", ".join(left))
        for label, needle in (
            ("pipe", "pipe | is ordinary"),
            ("ampersand", "ampersand & expands"),
            ("backslash", "backslash \\ starts"),
            ("last line", "Line seven ends it."),
        ):
            if needle not in out:
                problems.append("the %s did not survive substitution" % label)

    if problems:
        print("\nthe review prompt cannot render its own epic scope:\n", file=sys.stderr)
        for p in problems:
            print("  - %s" % p, file=sys.stderr)
        print(
            "\n  A value substituted into `s|...|...|` may not carry a raw newline, `|`,\n"
            "  `&` or a backslash unescaped. This exact defect made `Review Complete`\n"
            "  unpostable on EVERY pr at once (the reviewer runs console@main), and cost a\n"
            "  one-time protection bypass to break the loop on 2026-09-02.",
            file=sys.stderr,
        )
        return 1

    print("review prompt render: a 7-line epic scope with | & \\ and newlines substitutes cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
