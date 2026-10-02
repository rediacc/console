"""Refuse a Bash command that writes a per-commit review record under `agent/reviews/` by hand.

WHY. The pre-bash half of `block_review_file_edit` (agent/plans/PLAN-per-commit-review.md section 6): the Edit/Write tools are refused there, so the same hand edit through the shell is refused here. The shapes are the ones a session reaches for: an output redirection (`>`, `>>`, `>|`), `tee`, `sed -i`/`perl -i`, `cp`/`mv`/`install`/`rsync`/`ln` onto the directory, `truncate`, `dd of=`, and an
interpreter one-liner or heredoc (`python3 -c`, `python3 - <<EOF`, `node -e`) whose code names the directory and opens something for writing.

READ BY THE LEXER, NOT BY A REGEX OVER THE TEXT. `shellscan` already knows where bash really redirects and which words are a command's operands, so `echo "agent/reviews"`, `cat agent/reviews/b/x.md`, `grep -rn x agent/reviews/` and a commit message naming the path all pass. The two sanctioned writers are named and pass too: the reviewer (`wl_review.py`) and the worklist verbs that
call it (`worklist.py --review-mark`, `--review-commit`, `--review-run`).

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_review_file_shell_write.py` beside it and against its own DEFECT, never against a golden.
"""

import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 53

# The path test every shell shape goes through. With it answering no, every redirect, tee, sed -i and copy onto a review file passes.
DEFECT = ("    if not word:\n        return False", "    if True:\n        return False")

REVIEW_TEXT = "agent/reviews/"
# A string literal that IS a review path (relative or absolute), as opposed to prose that mentions one: the quote is followed by path characters only.
REVIEW_LITERAL = re.compile(r"['\"](?:[^'\"\s]*/)?agent/reviews/")
REVIEW_WORD = re.compile(r"(\A|/)agent/reviews(/|\Z)")
SANCTIONED = ("wl_review.py", "worklist.py")
COPIERS = ("cp", "mv", "install", "rsync", "ln")
INPLACE = ("sed", "perl", "gsed")
INTERPRETERS = ("python", "python3", "node", "perl", "ruby")
# Code that opens a file for writing, replaces or removes one.
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|write_text|write_bytes|os\.replace|os\.rename|shutil\.(copy|move)|unlink|writeFileSync|appendFileSync"
)

MESSAGE = (
    "BLOCKED: this command writes a per-commit review record by hand (%s).\n"
    "\n"
    "Review files are written by the reviewer and closed only through the verb, which checks\n"
    "the fix before it records it. A hand edit is how a high finding disappears without a fix.\n"
    "\n"
    "  close a finding:  .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> fixed <sha>\n"
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> not-a-bug <evidence path:line>\n"
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> deferred #<item>\n"
    "  re-review:        python3 .claude/hooks/stop/wl_review.py --run <sha> --branch <branch>\n"
    "  record them:      .claude/hooks/stop/worklist.py --review-commit <me>\n"
)

R = "agent/reviews/0930-1/" + "a" * 40 + ".md"

EDGE_CASES = [
    ("a redirect", "printf 'Resolution: fixed' > %s" % R),
    ("an append", "echo x >> %s" % R),
    ("a cat heredoc", "cat > %s <<'EOF'\n# Review\nEOF" % R),
    ("tee", "echo x | tee %s" % R),
    ("tee -a", "echo x | tee -a %s >/dev/null" % R),
    ("sed -i", "sed -i 's/\\[high\\]/[low]/' %s" % R),
    ("cp onto the directory", "cp /tmp/x.md agent/reviews/0930-1/"),
    ("mv onto a review file", "mv /tmp/x.md %s" % R),
    ("truncate", "truncate -s 0 %s" % R),
    ("python -c open for write", "python3 -c \"open('%s','w').write('x')\"" % R),
    (
        "python heredoc write_text",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('%s').write_text('x')\nEOF" % R,
    ),
    ("after cd", "cd agent/reviews/0930-1 && echo x > a.md"),
    ("inside sh -c", "sh -c 'echo x > %s'" % R),
    # allowed
    ("reading one", "cat %s" % R),
    ("grep over the directory", "grep -rn high agent/reviews/"),
    ("echo naming the path", "echo 'see agent/reviews/0930-1/'"),
    ("a commit that carries them", "git commit -F /tmp/m.txt -- agent/reviews/0930-1/"),
    ("git add", "git add -- agent/reviews/0930-1/%s.md" % ("a" * 40)),
    (
        "the mark verb",
        ".claude/hooks/stop/worklist.py --review-mark abcd1234 aaaaaaaa.1 fixed %s" % ("b" * 40),
    ),
    ("the reviewer", "python3 .claude/hooks/stop/wl_review.py --run abc --branch 0930-1"),
    ("a copy OUT of the directory", "cp %s /tmp/x.md" % R),
    ("a python read", "python3 -c \"print(open('%s').read())\"" % R),
    ("an unrelated redirect", "echo x > /tmp/out.txt"),
    ("a sibling directory", "echo x > agent/reviews-old/x.md"),
]


def _is_review(word, cwd=None):
    if not word:
        return False
    if REVIEW_WORD.search(word):
        return True
    return bool(cwd and REVIEW_WORD.search(str(cwd).rstrip("/") + "/" + word))


def _operands(argv):
    return [a for a in argv if not (a.startswith("-") and len(a) > 1)]


def _offending(cmd):
    """A short description of the first hand write to a review file in `cmd`, or ""."""
    hits = [t for t in shellscan.write_targets(cmd) if _is_review(t)]
    if hits:
        return "redirect into %s" % hits[0]
    analysis = shellscan._analyse(cmd)
    for run in analysis.runs:
        name = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        if any(a.rsplit("/", 1)[-1] in SANCTIONED for a in [run.name, *argv[:2]]):
            continue
        for target in run.writes:
            if _is_review(target, run.cwd):
                return "redirect into %s" % target
        operands = _operands(argv)
        if name == "tee" and any(_is_review(a, run.cwd) for a in operands):
            return "tee into the review directory"
        in_place = any(a == "-i" or a.startswith(("-i", "--in-place")) for a in argv)
        if name in INPLACE and in_place and any(_is_review(a, run.cwd) for a in operands):
            return "%s -i on a review file" % name
        if name in COPIERS and operands and _is_review(operands[-1], run.cwd):
            return "%s onto the review directory" % name
        if name == "truncate" and any(_is_review(a, run.cwd) for a in operands):
            return "truncate of a review file"
        if name == "dd" and any(a.startswith("of=") and _is_review(a[3:], run.cwd) for a in argv):
            return "dd of= a review file"
        if name.startswith(INTERPRETERS):
            # A heredoc is this interpreter's code only when it reads its program from stdin (`python3 -`, a bare `python3`); a `cat > x.py <<EOF` earlier in the line is a file being written, not code being run.
            reads_stdin = not operands or operands[0] == "-"
            code = " ".join(argv)
            if reads_stdin:
                code += "\n" + "\n".join(_heredoc_bodies(cmd, analysis))
            if _code_writes_review(code):
                return "%s code that writes into the review directory" % name
    return ""


def _code_writes_review(code):
    """Interpreter code that writes a review path: a write on a line naming the directory, or through a name bound to such a path.

    LINE-SCOPED, measured on its first live run: a python heredoc that patched an unrelated module, whose replacement text merely MENTIONED the directory in a comment, was refused when any write anywhere plus any mention anywhere was enough. A write and a path LITERAL (a quote followed by path characters, not prose) have to meet on one line, or through a variable assigned from such a literal.
    """
    if REVIEW_TEXT not in code:
        return False
    names = {
        m.group(1)
        for m in re.finditer(r"\b([A-Za-z_]\w*)\s*=\s*([^\n=]*)", code)
        if REVIEW_LITERAL.search(m.group(2))
    }
    for line in code.splitlines():
        if REVIEW_LITERAL.search(line) and WRITE_CODE.search(line):
            return True
        for name in names:
            if re.search(r"\b%s\b" % re.escape(name), line) and WRITE_CODE.search(line):
                return True
    return False


def _heredoc_bodies(cmd, analysis):
    """The text of every heredoc the lexer read; a body fed to an interpreter is code."""
    return [
        cmd[doc.body_start : doc.body_end]
        for doc in analysis.heredocs
        if doc.body_start is not None and doc.body_end is not None
    ]


def run(ev):
    cmd = ev.field("tool_input", "command")
    if "reviews" not in cmd:
        return hookio.ALLOW
    what = _offending(cmd)
    if not what:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % what)
    return hookio.DENY
