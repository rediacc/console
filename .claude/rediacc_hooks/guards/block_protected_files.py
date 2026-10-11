"""Block git restore/checkout/rm of protected hook files.

THE VERB AND THE PATH MUST BE IN THE SAME CLAUSE. The original pattern joined them with `.*`, which spans `&&`, `;` and `|`, so a command that checked out a branch and then merely READ a protected file was refused:

  git checkout main && cat .claude/settings.json

Nothing there restores anything. `[^;&|]*` keeps the match inside one clause, which is the smallest change that tells "restore this file" apart from "restore something, then look at this file".

Verified on 2026-08-27, when this guard blocked the very command that was measuring it -- the probe's line contained the fixture text and never ran. A guard that cannot be measured without tripping over itself is one nobody measures, which is how it sat with a block case and no allow case.

ROUTED THROUGH lib/command-scan.sh 2026-08-27. Matching the raw command meant matching PROSE: `echo '<the banned command>'` was refused, and so was a worklist note or a doc quoting it. hook_scan_target removes heredoc bodies and quoted spans while still extracting `sh -c` / `eval` payloads, so a command hidden in a wrapper is scanned exactly as before -- this narrows what the guard
refuses, never what it catches.

PORT NOTE. `PROTECTED` is interpolated into the ERE by the bash, so the two paths keep their backslash-escaped dots here too. Escaping them a second time through `re.escape` would be a change in what is matched, which is the one thing this port may not make.
"""

import itertools
import posixpath
import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 3

# Widening the gap back to `.*` is the exact over-block the header records: the verb and the path stop having to share a clause, so `git checkout main && cat .claude/settings.json` is refused for reading a file.
DEFECT = (r")[^;&|]*", r").*")

PROTECTED = r"(\.claude/settings\.json|scripts/pre-commit-check\.sh)"
# The same two files as paths, for the walked runs below. Dropping one turns its EDGE_CASES rows allowed (`a quoted path` names the first, `a for list holding the path` the second), which the golden reads as a change.
PROTECTED_PATHS = (".claude/settings.json", "scripts/pre-commit-check.sh")

# COMMAND POSITION ON EVERY ARM. The verb group used to be `(git restore|git checkout|(^|[{S};|&])rm[{S}])`, which anchored only the `rm` arm, and that to any whitespace: `echo the docs say never to run git restore .claude/settings.json in this repo` was refused, and so was `echo never rm .claude/settings.json here` (found by check:ci-guard-mention-anchoring, 2026-10-09).
# Now the whole alternation sits behind one anchor, the line start or a separator, then an optional directory on the program (`/bin/rm`). `git` admits global flags before its verb the way block_worktree_add's GIT_AT_CMD does, so `git -C . restore` and `git  restore` are reached; both were ALLOWED before, because the verb was the literal `git restore`. Prefix commands
# (`sudo`, `xargs`, `time`, an assignment, `if ... then`) reach it through `shellscan.lifted_commands`, and so does `find ... -exec`, a launcher shellscan walks (`shellscan._launched`, #ec63ff8c): every `-exec` lands on a line of its own, so `find . -exec true {} \; -exec rm .claude/settings.json \;`, allowed before, is refused with the single `-exec` spelling.
VERB_AND_PATH = (
    hookio.rx(
        r"(^|[;&|(`{!])[{S}]*([^{S};|&()`]*/)?(git([{S}]+-[A-Za-z-]+([{S}]+[^{S};&|-][^{S};&|]*)?)*[{S}]+(restore|checkout)[{S}]|rm[{S}])[^;&|]*"
    )
    + PROTECTED
)

MESSAGE = "❌ BLOCKED: Cannot delete or restore protected hook files"

EDGE_CASES = [
    ("a restore of the settings file", "git restore .claude/settings.json"),
    ("a checkout of the settings file", "git checkout .claude/settings.json"),
    ("an rm of the pre-commit script", "rm scripts/pre-commit-check.sh"),
    ("rm after a separator", "true; rm .claude/settings.json"),
    # The over-block the clause fix exists for.
    (
        "checking out a branch then READING the file",
        "git checkout main && cat .claude/settings.json",
    ),
    ("reading the file on its own", "cat .claude/settings.json"),
    ("a restore of an unprotected path", "git restore packages/cli/src/x.ts"),
    ("a wrapper payload is still scanned", "sh -c 'git restore .claude/settings.json'"),
    # Command position on every arm: these sentences were refused before 2026-10-09.
    (
        "a sentence naming the restore is not running it",
        "echo the docs say never to run git restore .claude/settings.json in this repo",
    ),
    ("a sentence naming rm is not running it", "echo never rm .claude/settings.json here"),
    ("git global flags before the verb", "git -C . restore .claude/settings.json"),
    ("a prefix command still reaches rm", "sudo rm .claude/settings.json"),
    (
        "find -exec is a launcher shellscan walks",
        r"find . -exec rm .claude/settings.json \;",
    ),
    (
        "every find -exec is walked, not only the first",
        r"find . -name x -exec true {} \; -exec rm .claude/settings.json \;",
    ),
    # The path on the producer side of a pipe into xargs (#ec63ff8c): each was allowed before 2026-10-09.
    ("xargs rm fed the path on stdin", "echo .claude/settings.json | xargs rm"),
    (
        "xargs git restore fed the path on stdin",
        "printf '%s' scripts/pre-commit-check.sh | xargs git restore",
    ),
    ("xargs -I with the path on stdin", "echo .claude/settings.json | xargs -I{} rm -f {}"),
    (
        "an earlier stage of the pipe feeds xargs too",
        "echo .claude/settings.json | sort | xargs git checkout --",
    ),
    # ... and the consumer has to be destructive, and fed by THIS pipe.
    ("piping the path to cat reads it", "echo .claude/settings.json | cat"),
    ("xargs cat reads it", "echo .claude/settings.json | xargs cat"),
    ("xargs rm of an unprotected path", "echo packages/cli/src/x.ts | xargs rm"),
    ("a separator ends the pipe before xargs", "echo .claude/settings.json; ls | xargs rm"),
    ("xargs behind sudo", "echo .claude/settings.json | sudo xargs rm"),
    ("xargs git rm", "git ls-files .claude/settings.json | xargs git rm"),
    ("a tee between the producer and xargs", "echo .claude/settings.json | tee /tmp/l | xargs rm"),
    (
        "git reads its pathspec from stdin",
        "echo .claude/settings.json | git restore --pathspec-from-file=-",
    ),
    ("a heredoc fed to xargs", "cat <<'EOF' | xargs rm\n.claude/settings.json\nEOF"),
    ("inside a wrapper payload", "sh -c 'echo .claude/settings.json | xargs rm'"),
    ("find -exec rm of the path find names", r"find .claude/settings.json -exec rm {} \;"),
    ("xargs echo prints it", "grep -n .claude/settings.json docs/x.md | xargs echo"),
    ("xargs ls lists it", "echo .claude/settings.json | xargs ls -l"),
    ("find -exec cat reads it", r"find .claude/settings.json -exec cat {} \;"),
    (
        "git restore of stdin with no protected path",
        "echo packages/x.ts | git restore --pathspec-from-file=-",
    ),
    # A shell payload xargs or find -exec launches inherits the feed (#32e75fa4): each refusal was allowed before.
    (
        "an xargs-fed sh -c payload removes $0",
        """echo .claude/settings.json | xargs sh -c 'rm "$0"'""",
    ),
    (
        "an xargs-fed bash -c payload removes $@",
        """echo .claude/settings.json | xargs bash -c 'rm "$@"' _""",
    ),
    ("xargs -I into a sh -c payload", "echo .claude/settings.json | xargs -I{} sh -c 'rm {}'"),
    (
        "a nested shell inside the fed payload",
        """echo .claude/settings.json | xargs sh -c 'bash -c "git checkout -- \\"\\$0\\"" "$0"'""",
    ),
    ("find -exec sh -c removes $0", r"""find .claude/settings.json -exec sh -c 'rm "$0"' {} \;"""),
    (
        "an xargs-fed sh -c payload that only reads",
        """echo .claude/settings.json | xargs sh -c 'cat "$0"'""",
    ),
    (
        "an xargs-fed sh -c rm of an unprotected path",
        """echo packages/x.ts | xargs sh -c 'rm "$0"'""",
    ),
    (
        "a piped sh -c payload names no fed command",
        """echo .claude/settings.json | sh -c 'rm -f /tmp/x'""",
    ),
    (
        "a piped sh -c payload's xargs rm reads its stdin",
        "echo .claude/settings.json | sh -c 'xargs rm'",
    ),
    ("through cat inside the payload", "echo .claude/settings.json | bash -c 'cat | xargs rm'"),
    (
        "a piped sh -c payload's xargs only reads",
        "echo .claude/settings.json | bash -c 'xargs cat'",
    ),
    # A group's stdin is every member's, and a read loop turns the feed into a variable (#31ed6c5f): each refusal was allowed before.
    ("a subshell consumer is fed", "echo .claude/settings.json | (xargs rm)"),
    ("a brace-group consumer is fed", "echo .claude/settings.json | { xargs rm; }"),
    ("a here-string on a subshell feeds it", "(xargs rm) <<< .claude/settings.json"),
    (
        "a read loop removes the read variable",
        'echo .claude/settings.json | while read f; do rm "$f"; done',
    ),
    (
        "a read loop restores REPLY",
        'echo .claude/settings.json | while read; do git restore "${REPLY}"; done',
    ),
    (
        "a read loop that only reads",
        'echo .claude/settings.json | while read -r f; do cat "$f"; done',
    ),
    ("a subshell consumer fed an unprotected path", "echo packages/x.ts | (xargs rm)"),
    (
        "a read loop removing another path",
        "echo .claude/settings.json | while read f; do rm /tmp/x; done",
    ),
    # A loop fed through `done` feeds its body (review e085085d.1): each refusal was allowed before, the first pinned as a KNOWN GAP.
    (
        "a read loop fed through done <<<",
        'while read f; do rm "$f"; done <<< .claude/settings.json',
    ),
    (
        "a read loop fed through done < <(...)",
        'while read f; do rm "$f"; done < <(echo .claude/settings.json)',
    ),
    ("a piped loop's body is fed", "echo .claude/settings.json | while true; do xargs rm; done"),
    (
        "a loop fed through done that only reads",
        'while read f; do cat "$f"; done <<< .claude/settings.json',
    ),
    # The path in a shape the prose view drops (e085085d.1 sweep): each refusal was allowed before.
    ("a quoted path", 'rm ".claude/settings.json"'),
    ("a variable holding the path", 'f=.claude/settings.json; rm "$f"'),
    ("a for list holding the path", 'for f in scripts/pre-commit-check.sh; do rm "$f"; done'),
    ("a path relative to a cd", "cd scripts && rm pre-commit-check.sh"),
    ("a recursive rm above the path", "rm -rf .claude"),
    ("a recursive rm beside the path", "rm -rf .claude/tmp-scratch"),
    ("a variable holding the path, read", 'f=.claude/settings.json; cat "$f"'),
    # A wrapper is a command the walk found, not a quoted word that spells one (#31ed6c5f): both were refused before.
    (
        "a quoted sh -c is an echo argument",
        """echo "sh -c 'rm x'" "x .claude/settings.json | y\"""",
    ),
    ("a quoted eval is an echo argument", """echo "eval rm" ".claude/settings.json\""""),
    (
        "a real sh -c after a quoted mention",
        """echo "sh -c 'rm x'"; sh -c 'rm .claude/settings.json'""",
    ),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if cmd == "":
        return hookio.ALLOW

    try:
        cwd = ev.default(("cwd",), str(hookio.repo_root()))
    except RuntimeError:
        cwd = ev.cwd
    if hookio.grep_q(VERB_AND_PATH, scan) or fed_by_stdin(cmd) or names_by_run(cmd, cwd):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW


# THE TEXT VIEW DROPS WHAT BASH STILL HANDS THE COMMAND (review e085085d.1 sweep). VERB_AND_PATH reads `scan_target`, which removes every quoted span so that prose never reads as a command. A quoted path is not prose: `rm ".claude/settings.json"` and `git restore -- ".claude/settings.json"` were both allowed (rc 0, 2026-10-11), and so were the path in a variable (`f=...; rm "$f"`), in a
# `for` list, in a quoted substitution (`rm "$(echo ...)"`), behind a `cd`, and with a doubled slash. So the walked runs are judged too: each operand of an `rm` or a destructive git verb, as bash hands it over (`argv` quote-removed, `xargv` with the walk's variables expanded, a `for` variable as every word of its list), is resolved against the directory the run executes in and normalised. A recursive `rm` of a
# directory holding a protected file deletes it too. A word the walk cannot evaluate is `_unjudgeable` below. `git -C <dir>` resolves against that directory, so another checkout's copy still counts by its name, exactly as the text match always did.
def _resolve(word, base):
    return posixpath.normpath(word if word.startswith("/") else posixpath.join(base, word))


def _is_protected(path):
    return any(path == "/" + p or path.endswith("/" + p) for p in PROTECTED_PATHS)


def _holds_protected(path, root):
    """A directory a recursive rm empties: an ancestor of a protected file in this checkout."""
    return any(posixpath.join(root, p).startswith(path.rstrip("/") + "/") for p in PROTECTED_PATHS)


# A WORD THE WALK CANNOT EVALUATE IS A WILDCARD (review c093f0f3.2). `rm .claude/$(echo settings.json)` and `rm $(echo .claude)/settings.json` delete the file, and the substitution's output is not computed, so neither normalised path names it; both were allowed (rc 0, 2026-10-11). Each `$(...)`, backtick span and `$NAME`/`${...}` the walk left unresolved is read as "any text", and the word is refused when a LITERAL
# segment of it is a whole segment of a protected path (`.claude`, `settings.json`, `scripts`, `pre-commit-check.sh`) and the pattern can still match a protected file, or for a recursive rm a directory holding one. The segment test is what keeps `rm "$(mktemp)"`, `rm -rf "$(mktemp -d)/x"` and `rm "$X".json` allowed: a pattern made only of wildcards, or of text no protected path spells, judges nothing.
_SEGMENTS = frozenset(seg for p in PROTECTED_PATHS for seg in p.split("/"))
_WILD = "\x00"


def _wildcarded(word):
    """`word` with every part bash would compute at run time replaced by `_WILD`, or None when it has none."""
    out: list[str] = []
    wild = False
    k = 0
    while k < len(word):
        if word.startswith("$(", k) or word.startswith("${", k):
            close = ")" if word[k + 1] == "(" else "}"
            depth, j = 0, k + 1
            while j < len(word):
                depth += word[j] == word[k + 1]
                depth -= word[j] == close
                j += 1
                if depth == 0:
                    break
            out.append(_WILD)
            wild, k = True, j
        elif word[k] == "`":
            end = word.find("`", k + 1)
            out.append(_WILD)
            wild, k = True, len(word) if end < 0 else end + 1
        elif name := re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*").match(word, k):
            out.append(_WILD)
            wild, k = True, name.end()
        else:
            out.append(word[k])
            k += 1
    return "".join(out) if wild else None


def _unjudgeable(word, base, root, recursive):
    """True when `word` holds a part the walk cannot evaluate and could still name a protected file (or, for a recursive rm, a directory holding one)."""
    pattern_text = _wildcarded(word)
    if pattern_text is None:
        return False
    literal = {seg for seg in re.split(r"[/%s]" % _WILD, pattern_text) if seg}
    if not literal & _SEGMENTS:
        return False
    absolute = pattern_text.startswith(("/", _WILD))
    body = ".*".join(re.escape(piece) for piece in pattern_text.split(_WILD))
    pattern = re.compile(body if absolute else re.escape(base.rstrip("/") + "/") + body)
    suffix = re.compile("(?:.*/)?" + body)
    targets = [posixpath.join(root, p) for p in PROTECTED_PATHS]
    if any(pattern.fullmatch(t) for t in targets) or any(
        suffix.fullmatch(p) for p in PROTECTED_PATHS
    ):
        return True
    if recursive:
        ancestors = {posixpath.dirname(t) for t in targets}
        return any(
            pattern.fullmatch(a.rstrip("/")) or suffix.fullmatch(posixpath.basename(a))
            for a in ancestors
        )
    return False


def _operand_words(run_):
    """Every word an operand of `run_` could be: the quote-removed argv, the expanded argv where the walk could evaluate it, and each word of a `for` list a `$NAME` in it names."""
    words = list(run_.argv)
    words += [w for w in (run_.xargv or []) if not shellscan.unresolved(w)]
    for name, values in run_.loop_vars.items():
        ref = re.compile(r"\$\{?%s\b" % re.escape(name))
        if any(ref.search(a) for a in run_.argv):
            words += values
    return words


def names_by_run(cmd, cwd):
    """True when a walked `rm` or destructive git verb names a protected file, or recursively removes a directory holding one."""
    here_root = posixpath.normpath(str(cwd) if cwd else "/")
    try:
        root = posixpath.normpath(str(hookio.repo_root()))
    except RuntimeError:
        root = here_root
    for run_ in shellscan.every_run(cmd):
        destructive, git_verb = _destructive(run_)
        if not destructive:
            continue
        here = run_.git_dir if git_verb else run_.cwd
        base = _resolve(here, here_root) if here else here_root
        # `rm -r` and `git rm -r` remove what a directory holds; a restore or checkout of a directory is block_destructive_git_restore's to judge.
        recursive = (not git_verb or run_.git_sub == "rm") and any(
            a == "--recursive" or re.match(r"^-[A-Za-z]*[rR]", a) for a in run_.argv
        )
        for word in _operand_words(run_):
            if word.startswith("-") or word == "":
                continue
            if ("$(" in word or "`" in word) and re.search(PROTECTED, word):
                return True
            if _unjudgeable(word, base, root, recursive):
                return True
            path = _resolve(word, base)
            if _is_protected(path) or (recursive and _holds_protected(path, root)):
                return True
    return False


# THE PATH CAN ARRIVE ON STDIN (#ec63ff8c). `echo .claude/settings.json | xargs rm` deletes the file, and no clause of it holds both the verb and the path, so it was allowed (rc 0, 2026-10-09). `shellscan` records, per command, the literal text arriving on its stdin (`_Run.feed`: the earlier pipeline stages' words, its own here-string or heredoc, and `find`'s words for a `find -exec` command) and the prefixes in front of it
# (`_Run.via`). A protected path in that text counts only when the text BECOMES the destructive command's operands: through `xargs`, through `find -exec ... {}`, or through git's `--pathspec-from-file=-`. `echo .claude/settings.json | cat` and `| xargs cat` read the file and stay allowed. What a producer prints is not computed, so `ls .claude | xargs rm` is outside this reach, and a protected path anywhere in a producer's words counts even
# when it is not what reaches the command, the direction a guard fails safe in. The verbs are the ones VERB_AND_PATH names plus `git rm`, which deletes exactly as `rm` does.
DESTRUCTIVE_GIT = ("restore", "checkout", "rm")
OPERAND_FEEDERS = ("xargs", "find")


def _pathspec_from_stdin(argv):
    return "--pathspec-from-file=-" in argv or any(
        a == "--pathspec-from-file" and b == "-" for a, b in itertools.pairwise(argv)
    )


def _destructive(run_):
    """`(is rm or a destructive git verb, is that git verb)` for one run."""
    base = run_.name.rsplit("/", 1)[-1]
    git_verb = base == "git" and run_.git_sub in DESTRUCTIVE_GIT
    return base == "rm" or git_verb, git_verb


# A SHELL PAYLOAD INHERITS THE FEED (#32e75fa4, review 4aad4597.1), in both of the ways a shell hands it on. `echo .claude/settings.json | xargs sh -c 'rm "$0"'` deletes the file: xargs appends the fed words to `sh -c P` as P's positional parameters (`$0`, `$1`, `$@`; test_bash_semantics W19), and `-I{}` writes them into P itself. The fed run is the `sh`, the `rm` inside P has no feed
# of its own, so it was allowed (rc 0, 2026-10-09). So when xargs or `find -exec` launches a shell's `-c` payload with a protected path in its feed, any rm or destructive git verb in it, at any depth, is refused. Whether the payload really names `$0` is not asked, the direction a guard fails safe in, and asking it would be unsound: `xargs sh -c 'f=$0; rm "$f"'` and `xargs sh -c 'for f; do rm "$f"; done' _` delete the path with an rm that names no positional (review 5aa562c3.1). One that only reads (`cat "$0"`) stays allowed.
# The second way is stdin itself: `echo .claude/settings.json | sh -c 'xargs rm'` gives the payload's `xargs` the shell's own stdin (allowed at rc 0 the same day). So every payload command is judged as if the shell's feed reached it, whatever its own pipeline puts in front of it (`cat | xargs rm` passes it through, and what a stage prints is not computed), the direction a guard fails safe in. A compound consumer (`| (xargs rm)`, `| { xargs rm; }`) is fed too, because shellscan hands a group's stdin to every command in it (#31ed6c5f); a read loop is `_fed_read_loop` below.
def _takes_feed(run_):
    """True when a protected path on this run's stdin can become a destructive command's operands: through xargs, `find -exec` or `--pathspec-from-file=-` on the command itself, or into a fed shell payload holding any destructive command, whether or not that command names `$0` (see the comment above: `f=$0; rm "$f"` and `for f; do rm "$f"; done` read the feed without naming a positional in the rm)."""
    operands_fed = any(v in run_.via for v in OPERAND_FEEDERS)
    if run_.name.rsplit("/", 1)[-1] in shellscan.SHELL_NAMES:
        mode, payload = shellscan._shell_payload(run_.argv)
        if mode == "c" and payload:
            inner_runs = shellscan.every_run(payload)
            if operands_fed and any(_destructive(inner)[0] for inner in inner_runs):
                return True
            if any(_takes_feed(inner) for inner in inner_runs):
                return True
    destructive, git_verb = _destructive(run_)
    return destructive and (operands_fed or (git_verb and _pathspec_from_stdin(run_.argv)))


# A READ LOOP TURNS THE FEED INTO A VARIABLE (#31ed6c5f), and it is in reach: `echo .claude/settings.json | while read f; do rm "$f"; done` deletes the file, and was allowed (rc 0, 2026-10-09). The walk does not model the loop's body as a body (`do` and `done` are words in front of commands), so the rule is the over-reading one: a `read` that is a `while`/`until` condition, with a
# protected path in its feed, makes every LATER destructive command that names one of its variables (`$f`, `${f}`, `$REPLY` when it names none, an `-a` array) a deletion of that path. A loop fed through `done` (`done <<< .claude/settings.json`, `done < <(...)`, a heredoc) is in reach since review e085085d.1: shellscan hands the `done` redirect to every command inside the loop (`_loop_word`).
# `read`'s options that take a value: the rest of the bundle (`-n1`), or the next word when the letter ends it (`-rp prompt`). `-a`'s value is an array it assigns.
_READ_VALUE_LETTERS = frozenset("adinNptu")


def _read_variables(argv):
    """The variables a `read` assigns: its operands, an `-a` array, or REPLY when there are neither."""
    names = []
    k = 0
    while k < len(argv):
        arg = argv[k]
        k += 1
        if arg == "--":
            names.extend(argv[k:])
            break
        if not (arg.startswith("-") and len(arg) > 1):
            names.append(arg)
            continue
        for at, letter in enumerate(arg[1:], 1):
            if letter not in _READ_VALUE_LETTERS:
                continue
            value = arg[at + 1 :]
            if not value and k < len(argv):
                value = argv[k]
                k += 1
            if letter == "a" and value:
                names.append(value)
            break
    return names or ["REPLY"]


def _fed_read_loop(runs):
    for at, run_ in enumerate(runs):
        if run_.name.rsplit("/", 1)[-1] != "read" or "status" not in run_.usage:
            continue
        if run_.feed is None or not re.search(PROTECTED, run_.feed):
            continue
        refs = re.compile(
            r"\$\{?(%s)\b" % "|".join(re.escape(n) for n in _read_variables(run_.argv))
        )
        for later in runs[at + 1 :]:
            if _destructive(later)[0] and any(refs.search(a) for a in later.argv):
                return True
    return False


def fed_by_stdin(cmd):
    runs = shellscan.every_run(cmd)
    return _fed_read_loop(runs) or any(
        run_.feed is not None and re.search(PROTECTED, run_.feed) and _takes_feed(run_)
        for run_ in runs
    )
