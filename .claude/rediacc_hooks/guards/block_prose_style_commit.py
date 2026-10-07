"""Refuse a commit message or a PR body whose prose breaks the house style.

THE OTHER HALF OF `block_prose_style_edit`. That guard sees the bytes going into a FILE; this one sees the bytes going into a COMMIT or a PULL REQUEST, which never touch the working tree and which no file-scoped hook can reach. A style enforced on documents and not on the messages describing them is enforced on the half nobody reads.

OWN_SUITE = True, the same sentinel and for the same reason as its sibling. The
argument is written out once, in `block_prose_style_edit.py`; the short version is that no bash original ever existed, `check_language_policy.py` refuses a new shell file under `.claude`, and the evidence for a guard with no golden to compare against is a dedicated per-guard suite plus the planted DEFECT below.

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
    gh api .../pulls/<n> -X PATCH -F body=@<file>   the SANCTIONED PR-body edit
                                 (`gh pr edit --body-file` is blocked by a
                                 different guard, `gh-pr-edit-body`, for a
                                 GraphQL bug -- this is the redirect it sends
                                 callers to, and it does not look like `gh pr`
                                 at all)

A `git commit -F <file>` that an earlier clause of the same command writes is refused unread (`commit_policy.written_message_refusal`): the guard runs before that clause, so the bytes on disk are an earlier command's.

THE COMMIT SUBJECT IS EXEMPT FROM R11's IMPERATIVE ARM, and that exemption is in the rules file rather than here: R11 lists `ai_output`, `pr` and `markdown` as its scopes and omits `commit` entirely. This repository's subjects are Conventional-Commits-shaped and imperative by house convention -- measured over the last 200 commits, median 71 characters, p90 84, max 98 -- so a guard
that refused `fix(ci): widen the trigger` would refuse the convention itself. The brief's own text carves this out, and compatibility with what is already in the tree wins.

PRE-EXISTING DEBT DOES NOT APPLY HERE, unlike the edit side. A commit message is written fresh every time; there is nothing carried through from a previous version of it, so there is nothing to consult the baseline about and the guard does not. The exception is `--amend`, where the message may be an older one being lightly edited; that is still treated as new, deliberately, because
an amend is the one moment somebody is already looking at the words.

IT FAILS OPEN, LOUDLY, on a missing engine, exactly as its sibling does and for the reason `block_settled_questions.py` gives about a missing jq: the message says the text went UNEXAMINED rather than letting a green read as a pass.
"""

import pathlib
import re
import shlex
import sys

from rediacc_hooks import commit_policy, hookio, shellscan

CHAIN = "pre-bash"
OWN_SUITE = True
# Re-keyed from 40 to 41 on 2026-09-22 by the insertion of block_push_to_protected_branch.py at 39.
ORDER = 40

# THE HEREDOC ARM, which is the one this repository's commits actually travel through: `git commit -F - <<'EOF' ... EOF` puts the whole body somewhere argv parsing cannot see it, so losing this branch means every multi-paragraph message goes UNEXAMINED while the guard still reports as installed.
#
# THE FIRST DECLARATION HERE WAS `if not _is_target(command):` -> `if False:`, and `test_the_differential_can_fail` reported it UNPROVEN on 2026-09-16: examining every command instead of the commit-shaped ones changed no answer, because none of the non-target cases carries a `-m` or a `--body` for the parser to find. The control was right and the declaration moved.
DEFECT = ("        if _reads_stdin(tokens):", "        if False:")

UNEXAMINED = (
    "block-prose-style-commit: the prose-style engine could not be loaded (%s); this "
    "message passed UNEXAMINED (the hook did not run its rules)."
)

# `git commit`, with anything between the two words (`-C dir`, `--no-pager`).
#
# `re.MULTILINE`, so `^` also anchors after a `\n` and not only at the start of the whole payload. Found live by review 2026-09-16: a `git commit` sitting on the SECOND line of a multi-line command (e.g. a `set -e` guard line before it) has a `\n` immediately to its left, which is neither position 0 nor one of `;&|(` -- `_is_target` returned False and the message went unexamined.
# `block_worktree_add.py` does not have this bug because it matches per LINE via `hookio.grep_q`; this guard keeps its single-regex-over-the-whole-command shape and fixes the anchor instead, which is the smaller change for the same result. The `[^;&|\n]*` gap between the verb and `commit`/`pr` already never crosses a line, so `MULTILINE` cannot make the middle of the pattern bleed
# across lines -- only `^` changes meaning.
# `commit` MUST BE A WHOLE TOKEN, not a substring with word boundaries around it, and that cost a round trip before it was fixed. `\bcommit\b` matches inside `block-pathspecless-git-commit.sh`, so `git mv <that path> <dest>` scored as `git commit`: measured 2026-09-21, a `git mv` of exactly that file was refused by `block_unproven_bulk_transform`, which shares this constant,
# with a message about 28 staged files and a commit message that does not exist. `git log -- <any path with commit in it>` and `git add <the same>` were refused the same way. Requiring whitespace before the token and a terminator after it keeps every real spelling (`git commit`, `git -c k=v commit`, `git --no-pager commit -a`) and drops only `git commit-tree`, a plumbing verb
# neither guard was reading a message or a staged set for.
GIT_COMMIT = re.compile(
    r"(?:^|[;&|(])\s*(?:\S*/)?git\b[^;&|\n]*?(?:\s|^)commit(?=$|[\s;&|])", re.MULTILINE
)
GH_PR = re.compile(
    r"(?:^|[;&|(])\s*(?:\S*/)?gh\b[^;&|\n]*\bpr\b[^;&|\n]*\b(?:create|edit|comment|review)\b",
    re.MULTILINE,
)
# The SANCTIONED PR-body edit. `gh pr edit --body-file` is blocked outright by a different guard (`gh-pr-edit-body`) for a real GraphQL bug, which redirects
# every caller to `gh api repos/<owner>/<repo>/pulls/<n> -X PATCH -F body=@<file>`
# instead -- a shape `GH_PR` above cannot see, because it contains no `pr` verb at all, `pr` only ever appearing inside the URL path `pulls/<n>`. Found live 2026-09-17: every PR-body edit in this repository goes through the sanctioned form, so without this the guard's PR half was unreachable in practice. Two independent checks (the endpoint shape, the PATCH method) rather than one
# combined regex, because `gh api`'s flags are order-independent -- `-X PATCH` can precede or follow the endpoint -- and a single sequential pattern would have to duplicate every ordering to stay sound.
GH_API_PR_PATCH = re.compile(r"gh\b[^;&|\n]*\bapi\b[^;&|\n]*\bpulls/\d+")
PATCH_METHOD = re.compile(r"(?:-X|--method)[= ]?['\"]?PATCH\b", re.IGNORECASE)

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

# Which command a flag belongs to, not which command the guard happened to see LAST.
# Found live by review 2026-09-16: `scope` used to be computed ONCE from `GH_PR.search(command)` over the whole command line, so a chained `git commit -m "..." && gh pr create ...` set scope="pr" for the COMMIT message too, and R18 (line length) blocked a long commit body under a rule that, at the time, was scoped to "pr"/"markdown"/"ai_output" and deliberately excluded "commit" -- so the leak surfaced as a false positive on the commit body.
# The flag names are unambiguous per command -- `-m`/`--message`/`-F`/`--file`/a heredoc body are `git commit`'s, `--body`/`--title`/`-b`/`-t`/`--body-file` are `gh pr`'s -- so scope is looked up per LABEL instead of guessed once for the whole command.
# Since 2026-09-22, R18's `scopes` list (`.ci/config/prose-style-rules.json`) also names "commit": with per-label scoping already correct, a commit body genuinely gets the same floor-only line-length check a PR body does, and this mechanism is what keeps that scoped to the right target rather than leaking again.
PR_LABELS = frozenset({"--body", "--title", "-b", "-t", "--body-file"})


def _scope_for(label):
    return "pr" if label in PR_LABELS else "commit"


EDGE_CASES = [
    # The shapes this guard exists for.
    ("a commit subject addressing the reader", 'git commit -m "Did you run the tests?"'),
    ("a commit message saying I", 'git commit -m "fix: the thing" -m "I think this is right."'),
    ("the attached -m form", 'git commit -m"Did you run the tests?"'),
    ("the long --message form", 'git commit --message="Did you run the tests?"'),
    ("an amend", 'git commit --amend -m "Did you run the tests?"'),
    ("a heredoc body", "git commit -F - <<'EOF'\nfix: the thing\n\nI think this is right.\nEOF"),
    ("a gh pr body", 'gh pr create --title "fix: x" --body "Did you run the tests?"'),
    (
        "the sanctioned gh api PATCH form for a PR body",
        'gh api repos/o/r/pulls/589 -X PATCH -F body="Did you run the tests?"',
    ),
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
    (
        "a commit on the second line of a multi-line command is still a target",
        'set -e\ngit commit -m "Did you run the tests?"',
    ),
    (
        "a chained commit+pr scopes each message to its OWN command, not the last one seen",
        'git commit -m "fix: x" -m "%s" && gh pr create --title "fix: x" --body "short body"'
        % ("x" * 400),
    ),
    (
        "a cat heredoc quoting a commit+pr example as prose is not a target",
        "cat > /tmp/note.md <<'EOF'\nExample: git commit -m \"fix: x\" && gh pr create --title x --body y\nEOF",
    ),
    (
        "a python heredoc chained before a commit is not the commit's message",
        "python3 - <<'EOF'\nI think this is right.\nEOF\ngit commit -F /nonexistent/msg -- p",
    ),
    (
        "a heredoc piped into commit -F - is the message",
        "cat <<'EOF' | git commit -F -\nI think this is right.\nEOF",
    ),
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
    """Whether `command` invokes `git commit` or a write-shaped `gh pr` verb.

    RUNS AGAINST `shellscan.scan_target(command)`, NOT the raw string. Found live by review 2026-09-17: a `cat > file <<'EOF' ... EOF` heredoc whose BODY quoted an example (`git commit -m "..." && gh pr create ...`, written as illustrative prose in a reply) tripped this function, because the raw-string regex has no notion of "this text is data being written to a file, not a command
    being executed" -- the literal `&&` immediately before `gh` satisfied the separator class regardless of where it sat. `shellscan.scan_target` already exists to solve exactly this for the `gh`-guard family (`block_admin_merge.py` and siblings): it strips heredoc BODIES (keeping the introducer line, so `git commit -F - <<'EOF'` itself still matches) and quoted spans before a
    command-position anchor ever runs, which is the shared, tested defense this guard should have used from the start instead of scanning the raw command directly. `messages()` below is unaffected: it walks the RAW command with `shellscan`'s lexer and parse, scoped to each target's own segment, to extract the actual bodies to LINT, which is a different question from "is this a target" and still needs the
    real, unstripped text.
    """
    scanned = shellscan._command_substitution(shellscan.scan_target(command))
    if GIT_COMMIT.search(scanned) or GH_PR.search(scanned):
        return True
    if GH_API_PR_PATCH.search(scanned) and PATCH_METHOD.search(scanned):
        return True
    # The walked `gh api` calls, whose method is read the way gh reads it: the regex above sees `-X PATCH` and `-XPATCH` but not `-iXPATCH` (#9de9a8e9).
    return any(_api_pr_patch([r.name, *r.argv]) for r in shellscan.gh_runs(command, ("api",)))


def messages(command, cwd=None):
    """Every message body a target command carries, as `(label, text)`.

    EXPORTED SO THE SUITE CAN DRIVE IT DIRECTLY, without building a payload and running a chain. The parsing is the interesting half of this guard and the half most likely to be wrong, so it is a function rather than an inlined block inside `run`.

    `shlex.split` RATHER THAN A REGEX OVER `-m`. A regex has to decide what a quote means, and the answers differ between `-m "a b"`, `-m'a b'`, `-m"a b"`
    and `--message=a\\ b`. shlex is the shell's own answer to that question. It
    RAISES on an unbalanced quote, which is a command the shell would reject too, and the caller treats that as nothing-to-examine rather than as a finding.
    """
    out: list[tuple[str, str]] = []
    # THE HEREDOC IS SCOPED TO THE COMMAND IT IS ATTACHED TO (#91c4716c): `commit_policy.target_segments` says why, and the commit guards read their `-F -` message through the same walk. The flag arms are scoped the same way: `tail -F log` or `grep -m 5` chained beside a commit is not a message either, so only the target's own source span is shlex-split.
    for segment in commit_policy.target_segments(command, _is_target_stage):
        try:
            tokens = shlex.split(segment.text, comments=False)
        except ValueError:
            tokens = []
        if _reads_stdin(tokens):
            out.extend(("heredoc", body) for body in segment.stdin)
        out.extend(("heredoc", body) for body in segment.inner)
        out.extend(_flag_messages(tokens, command, cwd))
    return [(label, text) for label, text in out if text]


# `-F -` / `--body-file -` read the message from stdin; `/dev/stdin` is the same file spelled as a path.
STDIN_NAMES = commit_policy.STDIN_NAMES


def _reads_stdin(tokens):
    """Whether a target's own tokens take its message from stdin, which is the only way a heredoc on it (or piped into it) becomes the message. Read by the same parsers as `_flag_messages` (#9de9a8e9), so `-qF -` reads stdin as `-F -` does."""
    parsed = _parsed(tokens)
    if parsed is None:
        return False
    if parsed.command == ("commit",):
        return any(v in STDIN_NAMES for v in parsed.values("file"))
    if parsed.command == ("api",):
        return any(v in ("body=@-", "body=@/dev/stdin") for v in parsed.values("field")) or any(
            v in STDIN_NAMES for v in parsed.values("input")
        )
    return any(v in STDIN_NAMES for v in parsed.values("body-file"))


def _is_target_stage(words):
    """Whether one simple command (its words, prefixes already stripped) is `git commit`, a write-shaped `gh pr`, or the sanctioned `gh api` PATCH -- the same three patterns `_is_target` runs, anchored to this command's own start."""
    values = [shellscan._word_value(w) for w in words]
    values[0] = values[0].rsplit("/", 1)[-1]
    line = " ".join(values)
    return bool(GIT_COMMIT.match(line) or GH_PR.match(line) or _api_pr_patch(values))


def _api_pr_patch(values):
    """Whether argv `values` (`gh api ...`) PATCHes a PR, `-X` in every spelling pflag accepts (`-iXPATCH`, `-X=PATCH`, `--method=patch`), read by `shellscan.gh_args` (#9de9a8e9)."""
    if not values or values[0].rsplit("/", 1)[-1] != "gh":
        return False
    parsed = shellscan.gh_args(values[1:])
    return (
        parsed.command == ("api",)
        and bool(re.search(r"(^|/)pulls/[0-9]+$", shellscan.gh_api_endpoint(parsed)))
        and shellscan.gh_api_method(parsed) == "PATCH"
    )


def _flag_messages(tokens, command, cwd):
    """The `-m`/`--body`/`-F <file>`/... values in ONE target command's tokens, as `(label, text)`.

    READ THE WAY EACH TOOL READS ITS ARGV (#9de9a8e9): `git commit` through `shellscan.git_commit_args` (git's parse-options: `-qm x`, `--mess x`, `-qF f`, `-Ff`, `--fil f`), gh through `shellscan.gh_args` (pflag: `-dF f`, `-bx`, `-Fbody=@f`). Until 2026-10-07 this matched the spellings it listed, and each of those carried a message the guard never linted. A value-taking flag's value is never read as a flag, so `gh pr create -t --body` is a PR titled "--body".
    """
    parsed = _parsed(tokens)
    if parsed is None:
        return []
    out: list[tuple[str, str]] = []
    if parsed.command == ("commit",):
        for name, value in parsed.flags:
            if name == "message":
                out.append(("-m", value))
            elif name == "file":
                out.append(("-F", _read_message_file(value, command, cwd)))
        return out
    if parsed.command == ("api",):
        for name, value in parsed.flags:
            if name not in ("field", "raw-field") or not value.startswith("body="):
                continue
            # `-F body=@<file>` reads a file; `-f body=@x` is the literal text "@x".
            body = value[len("body=") :]
            if name == "field" and body.startswith("@"):
                body = _read_message_file(body[1:], command, cwd)
            out.append(("--body", body))
        return out
    for name, value in parsed.flags:
        if name in ("body", "title"):
            out.append(("--" + name, value))
        elif name == "body-file":
            out.append(("--body-file", _read_message_file(value, command, cwd)))
    return out


def _parsed(tokens):
    """`shellscan.ParsedArgs` for one target's tokens (`git [globals] commit ...`, `gh pr <verb> ...`, `gh api ...`), None for anything else."""
    if not tokens:
        return None
    head = tokens[0].rsplit("/", 1)[-1]
    if head == "git":
        _, sub, args = commit_policy.git_split(list(tokens[1:]))
        return shellscan.git_commit_args(args) if sub == "commit" else None
    if head == "gh":
        parsed = shellscan.gh_args(list(tokens[1:]))
        return parsed if parsed.command[:1] in (("pr",), ("api",)) else None
    return None


# `$NAME` / `${NAME}`, the two spellings a same-command assignment is referenced by.
PARAM = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _expand_assigned(word, command):
    """`word` with the command's own earlier `NAME=value` statements expanded, as bash would before reading `-F $S/msg`.

    shlex returns `$S/msg` verbatim, so without this `-F` read a file literally named `$S/msg`, got nothing, and every guard reading `messages()` judged an EMPTY message: a commit carrying its `PR-TASK:` trailer and proof line was refused for lacking them (#09fd19cd, 2026-09-25). Only statements BEFORE the verb count (`shellscan.assignments_before`); a word that still carries `$` or a backtick afterwards is returned unchanged, and reading it fails open as before.
    """
    if "$" not in word:
        return word
    names = {}
    for verb in ("gh pr", "gh api", "git commit"):
        names.update(shellscan.assignments_before(command, verb))
    text = word
    for _ in range(4):
        new = PARAM.sub(lambda m: names.get(m.group(1) or m.group(2), m.group(0)), text)
        if new == text:
            break
        text = new
    return word if ("$" in text or "`" in text) else text


def _expand_assigned_all(command):
    """The command with every `$NAME` its own earlier assignments define expanded, so `> $S/msg` and `-F /tmp/x/msg` compare equal."""
    names = {}
    for verb in ("gh pr", "gh api", "git commit"):
        names.update(shellscan.assignments_before(command, verb))
    return PARAM.sub(lambda m: names.get(m.group(1) or m.group(2), m.group(0)), command)


def _read_message_file(raw, command, cwd):
    """`-F <raw>`: expanded against the command's own assignments, then read, unless the command writes it first."""
    name = _expand_assigned(raw, command)
    # Written by this same command: the bytes on disk are an earlier command's (shellscan.writes_file, #9ec22810).
    if shellscan.writes_file(command, raw, name) or shellscan.writes_file(
        _expand_assigned_all(command), name
    ):
        return ""
    return _read_file(name, cwd)


def _read_file(name, cwd):
    """`-F <path>`, read from disk. `-F -` is stdin and is not readable here.

    A FAILURE TO READ RETURNS "", which the caller drops. That is the right direction: a path this process cannot see is a message this guard cannot examine, and inventing a finding from a missing file would be worse than missing one. The heredoc arm above already covers `-F -`, which is how this repository actually writes a multi-paragraph message.
    """
    # `/dev/stdin` is `-` spelled as a path: opened here it would be the HOOK's stdin, never the command's.
    if name in STDIN_NAMES:
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
    # SCOPE: this policy is about THIS checkout and its submodules. A commit in a repository outside it (a `/tmp` fixture, even one the same command `git init`s) is not its business (finding #5810a9f3).
    if commit_policy.foreign_git_only(ev, command):
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

    # THE PAYLOAD'S OWN `cwd`, not the interpreter's. `-F <relative-path>` has to resolve against where the COMMAND would run. Its sibling guard measured what `os.getcwd()` costs here: run from a foreign directory, every relative path resolved elsewhere and six refusals silently became passes. Falling back to the repository root rather than to the process is the same fix.
    cwd = ev.default(("cwd",), str(root))
    # A `git commit -F <file>` this same command writes first holds an earlier command's bytes (#c56b63bd): `_read_message_file` skips it, so `printf '<violation>' > m && git commit -F m` went unexamined. Refused naming the writer, as the four commit-policy guards do (#9888de00).
    for commit in commit_policy.git_runs(command, "commit"):
        refusal = commit_policy.written_message_refusal(
            command, commit, cwd, "`block_prose_style_commit`"
        )
        if refusal:
            ev.warn_raw(refusal)
            return hookio.DENY
    bodies = messages(command, cwd=cwd)
    if not bodies:
        return hookio.ALLOW

    findings = []
    for label, text in bodies:
        for finding in engine.lint_message(text, rules, globals_, _scope_for(label)):
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
    for finding in errors[:12]:
        rule = by_id.get(finding.rule)
        kind = "pull request body" if _scope_for(finding.path) == "pr" else "commit message"
        lines.append("  [%s] %s  %s  %r\n" % (kind, finding.path, finding.rule, finding.snippet))
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
