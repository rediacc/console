"""Refuse a commit message or a PR body whose prose breaks the house style.

THE OTHER HALF OF `block_prose_style_edit`. That guard sees the bytes going into
a FILE; this one sees the bytes going into a COMMIT or a PULL REQUEST, which
never touch the working tree and which no file-scoped hook can reach. A style
enforced on documents and not on the messages describing them is enforced on the
half nobody reads.

TWIN = None, the same sentinel and for the same reason as its sibling. The
argument is written out once, in `block_prose_style_edit.py`; the short version
is that no bash original exists, `check_language_policy.py` refuses a new shell
file under `.claude`, and the evidence that replaces the oracle is a dedicated
per-guard suite plus the planted DEFECT below.

=============================================================================
WHAT IT READS OUT OF A COMMAND LINE
=============================================================================

    git commit -m "..."          the subject, and any further -m as the body
    git commit -m"..."           the attached form, which `-m "..."` parsing misses
    git commit --message=...     the long form
    git commit -F <file>         READ FROM DISK, because the body is not on the
    git commit --file=<file>     command line at all and a guard that only
                                 scanned argv would pass every heredoc-written
                                 message in this repository unexamined
    git commit --amend           same, and amend is where a message is REWRITTEN
    heredoc                      `git commit -F - <<'EOF' ... EOF`, the shape
                                 this repository actually uses
    gh pr create/edit            --title, --body, --body-file
    gh pr comment / pr review    --body, --body-file

THE COMMIT SUBJECT IS EXEMPT FROM R11's IMPERATIVE ARM, and that exemption is in
the rules file rather than here: R11 lists `ai_output`, `pr` and `markdown` as
its scopes and omits `commit` entirely. This repository's subjects are
Conventional-Commits-shaped and imperative by house convention -- measured over
the last 200 commits, median 71 characters, p90 84, max 98 -- so a guard that
refused `fix(ci): widen the trigger` would refuse the convention itself. The
brief's own text carves this out, and compatibility with what is already in the
tree wins.

PRE-EXISTING DEBT DOES NOT APPLY HERE, unlike the edit side. A commit message is
written fresh every time; there is nothing carried through from a previous
version of it, so there is nothing to consult the baseline about and the guard
does not. The exception is `--amend`, where the message may be an older one being
lightly edited; that is still treated as new, deliberately, because an amend is
the one moment somebody is already looking at the words.

IT FAILS OPEN, LOUDLY, on a missing engine, exactly as its sibling does and for
the reason `block_settled_questions.py` gives about a missing jq: the message
says the text went UNEXAMINED rather than letting a green read as a pass.
"""

import pathlib
import re
import shlex
import sys

from rediacc_hooks import hookio

CHAIN = "pre-bash"
TWIN = None
ORDER = 40

# THE HEREDOC ARM, which is the one this repository's commits actually travel
# through: `git commit -F - <<'EOF' ... EOF` puts the whole body somewhere argv
# parsing cannot see it, so losing this loop means every multi-paragraph message
# goes UNEXAMINED while the guard still reports as installed.
#
# THE FIRST DECLARATION HERE WAS `if not _is_target(command):` -> `if False:`, and
# `test_the_differential_can_fail` reported it UNPROVEN on 2026-09-16: examining
# every command instead of the commit-shaped ones changed no answer, because none
# of the non-target cases carries a `-m` or a `--body` for the parser to find. The
# control was right and the declaration moved.
DEFECT = ("for _, body in HEREDOC.findall(command):", "for _, body in []:")

UNEXAMINED = (
    "block-prose-style-commit: the prose-style engine could not be loaded (%s); this "
    "message passed UNEXAMINED (the hook did not run its rules)."
)

# `git commit`, with anything between the two words (`-C dir`, `--no-pager`).
GIT_COMMIT = re.compile(r"(?:^|[;&|(])\s*(?:\S*/)?git\b[^;&|\n]*\bcommit\b")
GH_PR = re.compile(
    r"(?:^|[;&|(])\s*(?:\S*/)?gh\b[^;&|\n]*\bpr\b[^;&|\n]*\b(?:create|edit|comment|review)\b"
)
# A heredoc body: `<<'EOF' ... EOF` or `<<EOF ... EOF`, quoted or not.
HEREDOC = re.compile(
    r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\s*\n(.*?)\n\s*\1\s*(?:\n|$)", re.DOTALL
)

HEADER = """BLOCKED: this message breaks the house writing style -- make the WORK the subject,
or use the shared "we". Never "you", never "I".

"""

FOOTER = """
The rules, their examples and the reasons for each are in
.ci/config/prose-style-rules.json.

A line that genuinely has to carry the violation -- quoting somebody, or showing
the sentence being fixed -- takes an explicit marker on that line:
<!-- style-ok -->. Use it for a line that IS the example, never to get past
this hook.
"""

EDGE_CASES = [
    # The shapes this guard exists for.
    ("a commit subject addressing the reader", 'git commit -m "Did you run the tests?"'),
    ("a commit message saying I", 'git commit -m "fix: the thing" -m "I think this is right."'),
    ("the attached -m form", 'git commit -m"Did you run the tests?"'),
    ("the long --message form", 'git commit --message="Did you run the tests?"'),
    ("an amend", 'git commit --amend -m "Did you run the tests?"'),
    ("a heredoc body", "git commit -F - <<'EOF'\nfix: the thing\n\nI think this is right.\nEOF"),
    ("a gh pr body", 'gh pr create --title "fix: x" --body "Did you run the tests?"'),
    ("a gh pr comment", 'gh pr comment 1 --body "I already told you!"'),
    # CONTROLS. Every one of these must pass untouched.
    (
        "a house-convention imperative subject is EXEMPT",
        'git commit -m "fix(ci): widen the trigger"',
    ),
    (
        "the rewritten message passes",
        'git commit -m "fix: the thing" -m "Have the tests been run?"',
    ),
    (
        "the ownership exception is allowed",
        'git commit -m "fix: the thing" -m "My mistake; a fix is on the way."',
    ),
    ("a backticked pronoun is code", 'git commit -m "docs: rename the `you` placeholder"'),
    ("a commit with no message flag at all", "git commit"),
    ("git log is not git commit", 'git log --grep "Did you run it?"'),
    ("a plain command is not a target", "ls -la"),
    ("an echo mentioning commit is not a commit", 'echo "git commit -m \\"Did you run it?\\""'),
    ("a gh pr view is not a write", "gh pr view 1"),
    ("a warning-only absolute does not block", 'git commit -m "fix: x" -m "That will never work."'),
]


def _engine(root):
    """Import the engine with a SCOPED `sys.path` insert. See the sibling guard."""
    cipath = str(pathlib.Path(root) / ".ci")
    inserted = cipath not in sys.path
    if inserted:
        sys.path.insert(0, cipath)
    try:
        from rediacc_ci.quality import prose_style  # noqa: PLC0415 - deliberately late
    finally:
        if inserted and cipath in sys.path:
            sys.path.remove(cipath)
    return prose_style


def _is_target(command):
    return bool(GIT_COMMIT.search(command) or GH_PR.search(command))


def messages(command, cwd=None):
    """Every message body a target command carries, as `(label, text)`.

    EXPORTED SO THE SUITE CAN DRIVE IT DIRECTLY, without building a payload and
    running a chain. The parsing is the interesting half of this guard and the
    half most likely to be wrong, so it is a function rather than an inlined
    block inside `run`.

    `shlex.split` RATHER THAN A REGEX OVER `-m`. A regex has to decide what a
    quote means, and the answers differ between `-m "a b"`, `-m'a b'`, `-m"a b"`
    and `--message=a\\ b`. shlex is the shell's own answer to that question. It
    RAISES on an unbalanced quote, which is a command the shell would reject too,
    and the caller treats that as nothing-to-examine rather than as a finding.
    """
    out = []
    for _, body in HEREDOC.findall(command):
        out.append(("heredoc", body))
    try:
        tokens = shlex.split(command, comments=False)
    except ValueError:
        return out

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in ("-m", "--message", "--body", "--title", "-b", "-t"):
            if index + 1 < len(tokens):
                out.append((token, tokens[index + 1]))
            index += 2
            continue
        if token.startswith(("--message=", "--body=", "--title=")):
            out.append((token.split("=", 1)[0], token.split("=", 1)[1]))
            index += 1
            continue
        if token.startswith("-m") and len(token) > 2:
            out.append(("-m", token[2:]))
            index += 1
            continue
        if token in ("-F", "--file", "--body-file"):
            if index + 1 < len(tokens):
                out.append((token, _read_file(tokens[index + 1], cwd)))
            index += 2
            continue
        if token.startswith(("--file=", "--body-file=")):
            out.append((token.split("=", 1)[0], _read_file(token.split("=", 1)[1], cwd)))
            index += 1
            continue
        index += 1
    return [(label, text) for label, text in out if text]


def _read_file(name, cwd):
    """`-F <path>`, read from disk. `-F -` is stdin and is not readable here.

    A FAILURE TO READ RETURNS "", which the caller drops. That is the right
    direction: a path this process cannot see is a message this guard cannot
    examine, and inventing a finding from a missing file would be worse than
    missing one. The heredoc arm above already covers `-F -`, which is how this
    repository actually writes a multi-paragraph message.
    """
    if name == "-":
        return ""
    try:
        path = pathlib.Path(name)
        if not path.is_absolute() and cwd:
            path = pathlib.Path(cwd) / path
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return ""


def run(ev):
    command = ev.raw("tool_input", "command")
    if command in ("", "null"):
        return hookio.ALLOW
    if not _is_target(command):
        return hookio.ALLOW

    try:
        root = hookio.repo_root()
        engine = _engine(root)
        globals_, rules = engine.load_rules_file(root)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        ev.warn(UNEXAMINED % exc)
        return hookio.ALLOW

    off = globals_.get("env_off", "PROSE_STYLE")
    if ev.env(off, "").lower() in ("off", "0", "false"):
        ev.warn(
            "%s=%s: block-prose-style-commit did NOT run. That is an UNEXAMINED message, "
            "not a clean one." % (off, ev.env(off))
        )
        return hookio.ALLOW

    scope = "pr" if GH_PR.search(command) else "commit"
    # THE PAYLOAD'S OWN `cwd`, not the interpreter's. `-F <relative-path>` has to
    # resolve against where the COMMAND would run. Its sibling guard measured what
    # `os.getcwd()` costs here: run from a foreign directory, every relative path
    # resolved elsewhere and six refusals silently became passes. Falling back to
    # the repository root rather than to the process is the same fix.
    bodies = messages(command, cwd=ev.default(("cwd",), str(root)))
    if not bodies:
        return hookio.ALLOW

    findings = []
    for label, text in bodies:
        for finding in engine.lint_message(text, rules, globals_, scope):
            finding.path = label
            findings.append(finding)

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    if warnings:
        ev.warn(
            "block-prose-style-commit: %d style warning(s) in this message (not blocking):"
            % len(warnings)
        )
        for finding in warnings[:10]:
            ev.warn("  ~ %s %s: %s" % (finding.rule, finding.snippet, finding.text[:120]))

    if not errors:
        return hookio.ALLOW

    by_id = {rule.id: rule for rule in rules}
    lines = [HEADER]
    lines.append("%s\n" % ("pull request body" if scope == "pr" else "commit message"))
    for finding in errors[:12]:
        rule = by_id.get(finding.rule)
        lines.append("  %s  %s  %r\n" % (finding.path, finding.rule, finding.snippet))
        lines.append("    %s\n" % (rule.description if rule else ""))
        for example in rule.examples if rule else ():
            if example.get("kind") == "good":
                lines.append("    instead: %s\n" % example["text"])
                break
        lines.append("    in: %s\n" % finding.text[:200])
    if len(errors) > 12:
        lines.append("  ... and %d more\n" % (len(errors) - 12))
    lines.append(FOOTER)
    ev.warn_raw("".join(lines))
    return hookio.DENY
