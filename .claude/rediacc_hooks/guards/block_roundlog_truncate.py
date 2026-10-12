"""Deny TRUNCATING Bash writes to a pr-babysit round log. Appends and reads pass.

WHY A SECOND GUARD. block-roundlog-write.sh (pre-edit) stops the Write tool, which is what an agent reaches for first. It cannot see Bash. Its neighbour block-agent-state-shape.sh names that residual honestly and leaves it open: "a Bash heredoc straight onto the path, which no PreToolUse hook can see".

For STATE.md that residual is theoretical. For the round log it is the ACTUAL incident: on 2026-08-19 the appendix was destroyed by

    python3 - <<'PY' ... p.write_text(s[:i] + new) ... PY

run through Bash, by a session that had a perfectly good reason to be editing the file and no idea it was about to truncate it. A pre-edit-only guard would have watched that go past.

WHAT IS DENIED, AND WHY NOT EVERYTHING. The failure is silent truncation, so the guard targets operations that can REPLACE the file wholesale:

    >  redirection      sed -i      tee (without -a)      truncate
    cp/mv onto it       dd of=      python write_text / open(...,'w')

Appends are deliberately allowed: `>>` and `tee -a` cannot delete a history appendix, and appending to it is a normal, sanctioned thing to do. Reads are untouched. So is `worklist.py --roundlog` itself, which is the whole point of having somewhere to send people.

JUDGED ON WHAT RUNS, NOT ON THE TEXT (worklist #0c331972). Every verb arm used to be a regex over the raw command, anchored to `(^|[;|&])`, so a separator or a `|` INSIDE a quoted sentence was a command position: `echo 'echo x | tee --output-error=warn agent/pr-babysit-0831-1.md'` was refused as a truncation. The arms now read the shell's own walk: the redirects bash performs with their operator (`>` truncates, `>>` appends), the verbs it runs (`tee`, `cp`, `mv`, `truncate`, `dd`, `sed -i`, each read off its argv, behind `sudo`, `xargs`, `sh -c` or `find -exec`), and the program texts it hands an interpreter (`block_worktree_add.interpreter_programs`). The `--roundlog` carve-out is gone with the text matching: the verb is a `worklist.py` run that writes nothing the walk can see, so it passes on its own, and the whole-line glob that exempted it also exempted `worklist.py --roundlog x; mv <log> /tmp/` (rc 0 at HEAD 306285231), a truncation riding on the verb's name.

FAILS OPEN. This matches on a path shape plus a write verb; anything it does not recognise runs. A guard that blocked on suspicion would be routed around, and being routed around is worse than a named residual.

NAMED RESIDUAL, not pretended away: a write whose path is ASSEMBLED at runtime is partly invisible here. A verb's operand set by an earlier statement of the same command (`F=<log>; mv $F /tmp/`) is read as bash expands it; a REDIRECT onto such a variable (`> $F`), a value from the environment, and a shell glob that expands to the log are not, because the walk keeps a redirect target unexpanded. The verb's own success line is the backstop for that case: it reports the bytes kept above and below STATUS, so a session that used the verb can SEE
the appendix survived, and a session that bypassed it has no such line to point at.

=============================================================================
PORT NOTES, and the bash's own two are worth keeping because they are about what a naive reader would write instead.
=============================================================================

`grep -q ... | grep -qv ...` IS NOT THE CHECK IT READS AS, and the tee arm used to be written that way: `-q` suppresses stdout, so the downstream grep always sees empty input and its exit status says nothing whatever about the first pattern. Measured in the bash: the pipeline returns 0 on a match AND on a miss. It happened not to set the flag in practice, which is worse than
failing loudly, because it made the line look tested when the controls were passing for an unrelated reason. In Python the two tests are simply two calls, so the trap cannot recur; the record of it is here because the NEXT person to "simplify" this arm is the reader this paragraph is for.

`${RL}` BRACED, NOT `$RL`, in the bash: a `[` directly after a bare name reads
as an array subscript to shellcheck (SC1087, an error not a warning), and here the bracket opens a character class in the regex rather than an index. Python has no such ambiguity, which is why the braces are gone and the reason is not.
"""

import os
import re
import types

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import block_worktree_add as WT

CHAIN = "pre-bash"
ORDER = 31

# THE APPEND EXEMPTION. `>>` cannot truncate, and appending to the history is the sanctioned way to add to it; planting `>>` among the truncating operators refuses every append, which is the over-block the module docstring says gets a guard routed around.
DEFECT = (
    'TRUNCATING_OPS = frozenset((">", ">|", "&>", ">&"))',
    'TRUNCATING_OPS = frozenset((">", ">|", "&>", ">&", ">>"))',
)

# The redirect operators that open their target from byte zero. `>>`, `&>>` and `<>` keep what is there.
TRUNCATING_OPS = frozenset((">", ">|", "&>", ">&"))

# A round-log path. A target is a round log when its BASENAME is one and not a briefing (`_is_log`), which is the 2026-08 anchoring finding this file records twice carried to the walk: the verb and the path are one run, never two words on a line.
RL = r"pr-babysit-[A-Za-z0-9._-]+\.md"
BRIEFING = r"pr-babysit-[A-Za-z0-9._-]+-briefing\.md"

MESSAGE = (
    "❌ BLOCKED: this Bash command can replace a pr-babysit round log wholesale. That is "
    "how the round history was destroyed on 2026-08-19: a python heredoc doing "
    "p.write_text(s[:i] + new), which replaces from the STATUS heading to END OF FILE and "
    "takes the entire appendix with it, silently, on a file with no backup. To refresh "
    "STATUS use the verb, which replaces ONLY that block and prints the bytes it kept "
    "above and below:  .claude/hooks/stop/worklist.py --roundlog <branch> <<'EOF' ... EOF   "
    "To add to the history appendix, append instead ('>>' and 'tee -a' are deliberately "
    "allowed, since they cannot truncate). To amend the wave header, use the Edit tool -- "
    "targeted edits are allowed for the same reason."
)

EDGE_CASES = [
    ("the sanctioned verb", ".claude/hooks/stop/worklist.py --roundlog 0831-1"),
    # THE CASE THAT FOUND THE BYPASS, kept with its verdict inverted. It used to be labelled "the carve-out is a substring match, so this truncation passes" and it DID pass, on both sides, because `*--roundlog*` matched the string anywhere on the line rather than the verb at a command position. The twin was narrowed on 2026-09-06 and this port followed it a day later; the case
    # stays because it is the only one in this corpus that can tell the narrow carve-out from the wide one.
    (
        "a refresh and an archive on one line",
        ".claude/hooks/stop/worklist.py --roundlog 0831-1; mv agent/pr-babysit-0831-1.md /tmp/bak.md",
    ),
    (
        "merely NAMING the flag in a payload no longer buys the exemption",
        'echo "see --roundlog" > agent/pr-babysit-0831-1.md',
    ),
    ("a briefing has its own contract", "cat > agent/pr-babysit-0831-1-briefing.md"),
    # #0c331972: text no shell runs is a sentence, and every write that runs is still one.
    (
        "an echo quoting a truncating tee",
        "echo 'echo x | tee --output-error=warn agent/pr-babysit-0831-1.md'",
    ),
    (
        "a commit message quoting a mv",
        "git commit -m 'never mv agent/pr-babysit-0831-1.md' -- a.md",
    ),
    (
        "the verb's own heredoc may name the log and a redirect",
        ".claude/hooks/stop/worklist.py --roundlog 0831-1 <<'EOF'\nsee > agent/pr-babysit-0831-1.md\nEOF",
    ),
    ("a truncating redirect inside sh -c", "sh -c 'echo x > agent/pr-babysit-0831-1.md'"),
    ("sudo tee truncates", "echo x | sudo tee agent/pr-babysit-0831-1.md"),
    ("xargs truncate", "echo agent/pr-babysit-0831-1.md | xargs truncate -s 0"),
    (
        "a briefing beside a log write is no exemption",
        "cat agent/pr-babysit-0831-1-briefing.md > agent/pr-babysit-0831-1.md",
    ),
    ("a verb operand set by an earlier statement", "F=agent/pr-babysit-0831-1.md; mv $F /tmp/"),
    ("cp -t a backup directory is a read", "cp -t /backup agent/pr-babysit-0831-1.md"),
    # Review 0bbd6471.3: xargs appends the log as cp's destination.
    (
        "xargs feeds the log to cp as its destination",
        "echo agent/pr-babysit-0831-1.md | xargs cp /tmp/bak.md",
    ),
    ("xargs feeds the log to sed -i", "echo agent/pr-babysit-0831-1.md | xargs sed -i s/a/b/"),
    ("xargs feeds the log to tee", "echo agent/pr-babysit-0831-1.md | xargs tee"),
    ("a cp destination set by an earlier statement", "F=agent/pr-babysit-0831-1.md; cp /tmp/x $F"),
    # Review 126f2a9f.1: bash brace-expands the fed word before xargs reads it.
    (
        "a brace-expanded fed destination",
        "echo {/tmp/x,agent/pr-babysit-0831-1.md} | xargs cp /tmp/y.md",
    ),
    # #e5b0540a: a glob or brace that could spell a log reaches the walk, and every arm reads it expanded.
    (
        "a fed log glob in an unknown directory",
        'cd "$D" && echo pr-babysit-*.md | xargs cp /tmp/x.md',
    ),
    ("a fed glob that cannot spell a log", 'cd "$D" && echo notes-*.md | xargs cp /tmp/x.md'),
    ("mv a brace that spells the log", "mv agent/pr-babysit-{0831-1,x}.md /tmp/"),
    ("truncate a log glob", "truncate -s 0 agent/pr-babysit-*.md"),
    ("a redirect onto a log glob", "echo x > agent/pr-babysit-*.md"),
    ("cp onto a log glob", "cp /tmp/x agent/pr-babysit-*.md"),
    ("listing a log glob is a read", "ls agent/pr-babysit-*.md"),
    ("a log glob piped with no blank", 'cd "$D" && echo pr-babysit-*.md|xargs cp /tmp/x.md'),
    # Review 9ed30a8a.3: a glob that meets the round-log pattern in an unknown directory, whatever sample names it would miss.
    ("a bare md glob in an unknown directory", 'cd "$D" && truncate -s 0 *.md'),
    (
        "a glob that meets the log by a class",
        'cd "$D" && echo [p]r-babysit-1?08*.md | xargs cp /tmp/x.md',
    ),
    ("a txt glob in an unknown directory cannot be a log", 'cd "$D" && truncate -s 0 *.txt'),
    # #e5b0540a, live false positive (w2): a `*` in Python code is not a glob, and a program that cannot spell a log writes some other file.
    (
        "a heredoc that multiplies and writes through a variable",
        "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('notes.txt')\nn = 3 * 4\np.write_text(str(n))\nEOF",
    ),
    (
        "python -c repeating a string into a file",
        "python3 -c \"import pathlib,sys; t=pathlib.Path(sys.argv[1]); t.write_text('x' * 3)\" out.txt",
    ),
    (
        "a star import that writes",
        "python3 - <<'EOF'\nfrom os import *\nf = open(name, 'w')\nf.write('x')\nEOF",
    ),
    # ...and a program whose literals could spell a log still fails closed.
    (
        "a program globbing md files writes through a variable",
        "python3 - <<'PY'\nimport glob\nfor p in glob.glob('agent/*.md'):\n    open(p, 'w').write('')\nPY",
    ),
    (
        "a program building the log name in an f-string",
        "python3 - <<'PY'\nb = '0831-1'\nopen(f'agent/pr-babysit-{b}.md', 'w').write('')\nPY",
    ),
    (
        "a program globbing txt files cannot write a log",
        "python3 - <<'PY'\nimport glob\nfor p in glob.glob('docs/*.txt'):\n    open(p, 'w').write('')\nPY",
    ),
    ("appending to a log glob", "echo x >> agent/pr-babysit-*.md"),
    ("a copy back into agent/ lands on the log", "cp /tmp/pr-babysit-0831-1.md agent/"),
    (
        "xargs feeds the log to cp -t a backup directory",
        "echo agent/pr-babysit-0831-1.md | xargs cp -t /backup",
    ),
    ("a here-string python write", "python3 <<< \"open('agent/pr-babysit-0831-1.md', 'w')\""),
    # Appends cannot truncate, so they pass.
    ("append redirection", "echo x >> agent/pr-babysit-0831-1.md"),
    ("tee -a", "echo x | tee -a agent/pr-babysit-0831-1.md"),
    ("tee --append", "echo x | tee --append agent/pr-babysit-0831-1.md"),
    # The two shapes the tee arm was fixed for, both reproduced in review.
    (
        "tee --output-error=warn TRUNCATES",
        "echo x | tee --output-error=warn agent/pr-babysit-0831-1.md",
    ),
    (
        "a decoy append to another file",
        "echo x | tee -a other.txt | tee agent/pr-babysit-0831-1.md",
    ),
    # Truncating shell verbs.
    ("truncating redirection", "echo x > agent/pr-babysit-0831-1.md"),
    ("sed -i", "sed -i 's/a/b/' agent/pr-babysit-0831-1.md"),
    # #6378e10e: perl edits in place too, and a script naming the log is not the file edited.
    ("perl -pi", "perl -pi -e 's/a/b/' agent/pr-babysit-0831-1.md"),
    ("perl -i -pe", "perl -i -pe 's/a/b/' agent/pr-babysit-0831-1.md"),
    ("perl -pe only prints", "perl -pe 's/a/b/' agent/pr-babysit-0831-1.md"),
    ("gsed -i", "gsed -i 's/a/b/' agent/pr-babysit-0831-1.md"),
    (
        "a sed script naming the log edits another file",
        "sed -i 's/pr-babysit-0831-1.md/x/' notes.md",
    ),
    ("dd of=", "dd if=/dev/null of=agent/pr-babysit-0831-1.md"),
    ("mv the log away", "mv agent/pr-babysit-0831-1.md /tmp/"),
    ("cp ONTO the log", "cp /tmp/x agent/pr-babysit-0831-1.md"),
    # The cp finding: the log as a SOURCE is a pure read, and backing it up is the single most useful thing a session can do with it.
    ("cp the log AWAY is a read", "cp agent/pr-babysit-0831-1.md /backup/"),
    ("reading the log", "cat agent/pr-babysit-0831-1.md"),
    # The unanchored-verb defect, reproduced twice against this very hook.
    (
        "listing this guard's own filename",
        "ls .claude/hooks/pre-bash/block-roundlog-trunc*.sh; cat agent/pr-babysit-0831-1.md",
    ),
    # The python arm.
    (
        "the 2026-08-19 shape: an unresolvable write target",
        "python3 - <<'PY'\np = open('agent/pr-babysit-0831-1.md')\np.write_text(s[:i] + new)\nPY",
    ),
    (
        "a resolvable write to another file",
        "python3 -c \"open('other.md','w').write(x)  # see agent/pr-babysit-0831-1.md\"",
    ),
    ("shutil.copy onto the log", "python3 -c \"shutil.copy('a.md','agent/pr-babysit-0831-1.md')\""),
    ("os.replace onto the log", "python3 -c \"os.replace('a.md','agent/pr-babysit-0831-1.md')\""),
]


def _is_log(path):
    """A round-log path, by its basename; a briefing has its own contract."""
    base = path.rsplit("/", 1)[-1]
    return re.fullmatch(RL, base) is not None and re.fullmatch(BRIEFING, base) is None


# The characters with which bash makes one word into other names: globs, braces, a leading tilde.
_EXPANDING = frozenset("*?[{~")
_GLOB = frozenset("*?[")
# Round-log names a glob is tried against by the prefilter: any pattern that matches one of these could spell a log.
_PRINTABLE = frozenset(chr(c) for c in range(32, 127))


def _char_class(body: str) -> frozenset[str]:
    """The characters a bracket body names (`A-Za-z0-9._-`), ranges expanded; a leading or trailing `-` is itself."""
    out: set[str] = set()
    k = 0
    while k < len(body):
        if k + 2 < len(body) and body[k + 1] == "-":
            out.update(chr(c) for c in range(ord(body[k]), ord(body[k + 2]) + 1))
            k += 3
        else:
            out.add(body[k])
            k += 1
    return frozenset(out)


def _log_automaton():
    """The round-log name as an automaton, read out of `RL` itself (review 9ed30a8a.3): `<prefix>[<class>]+<suffix>`. A change to RL that leaves that shape raises here, at import, rather than leaving the prefilter testing an old pattern."""
    m = re.fullmatch(r"([^\[\\]+)\[([^\]]+)\]\+((?:\\.|[^\\])+)", RL)
    if m is None:
        raise RuntimeError("RL no longer reads as <prefix>[<class>]+<suffix>: %r" % RL)
    prefix, body, suffix = m.group(1), _char_class(m.group(2)), re.sub(r"\\(.)", r"\1", m.group(3))
    # States 0..len(prefix) spell the prefix; "B" is one or more body characters; ("S", i) has matched i characters of the suffix after the body.
    edges: dict[object, list[tuple[frozenset[str], object]]] = {
        i: [(frozenset(prefix[i]), i + 1)] for i in range(len(prefix))
    }
    edges[len(prefix)] = [(body, "B")]
    edges["B"] = [(body, "B")]
    for i in range(len(suffix)):
        edges[("S", i)] = [(frozenset(suffix[i]), ("S", i + 1))]
    return edges, ("S", len(suffix))


_LOG_EDGES, _LOG_ACCEPT = _log_automaton()


def _closure(states):
    """`B` reaches the suffix's start without reading a character."""
    out = set(states)
    if "B" in out:
        out.add(("S", 0))
    return out


def _glob_elements(pattern: str) -> list[frozenset[str] | None]:
    """A glob as a list of character sets, `None` for `*`."""
    out: list[frozenset[str] | None] = []
    k = 0
    while k < len(pattern):
        ch = pattern[k]
        if ch == "*":
            out.append(None)
        elif ch == "?":
            out.append(_PRINTABLE)
        elif ch == "\\" and k + 1 < len(pattern):
            k += 1
            out.append(frozenset(pattern[k]))
        elif ch == "[" and "]" in pattern[k + 2 :]:
            close = pattern.index("]", k + 2)
            inner = pattern[k + 1 : close]
            negated = inner[:1] in ("!", "^")
            named = _char_class(inner[1:] if negated else inner)
            out.append(_PRINTABLE - named if negated else named)
            k = close
        else:
            out.append(frozenset(ch))
        k += 1
    return out


def _glob_meets_log(pattern):
    """Can the glob `pattern` (a basename) and the round-log name both match some one name? Read as the intersection of the two languages, so no sample name is involved: `*.md`, `pr-*`, `p?-babysit-*` and `[p]r-babysit-x.md` do, `notes-*.md` and `*.txt` do not."""
    states = _closure({0})
    for element in _glob_elements(pattern):
        if element is None:
            reached = set(states)
            frontier = list(states)
            while frontier:
                state = frontier.pop()
                for _chars, nxt in _LOG_EDGES.get(state, ()):
                    for n in _closure({nxt}):
                        if n not in reached:
                            reached.add(n)
                            frontier.append(n)
            states = reached
            continue
        states = _closure(
            {nxt for s in states for chars, nxt in _LOG_EDGES.get(s, ()) if chars & element}
        )
        if not states:
            return False
    return _LOG_ACCEPT in states


def _names_log(word, directory=None):
    """Could `word` name a round log once bash expands it? A literal name is read as it stands; a word bash brace-, tilde- or glob-expands is read through `shellscan._fed_candidates` (its matches on disk in `directory`, the run's own, when known) and, for a glob, through one name of its shape too (`shellscan._glob_shape`), so `pr-babysit-*.md` in a directory this walk cannot read still counts (#e5b0540a)."""
    if _is_log(word):
        return True
    if not any(ch in word for ch in _EXPANDING):
        return False
    forms = shellscan._fed_candidates([word], directory)
    forms += [
        shellscan._glob_shape(f) for f in forms if any(ch in f.rsplit("/", 1)[-1] for ch in _GLOB)
    ]
    if any(_is_log(f) for f in forms):
        return True
    # A RELATIVE glob in a directory this walk cannot read fails safe: any glob that could match a round-log name counts as one (`cd "$D" && truncate -s0 *.md`), since which names it meets is the disk's answer, not ours.
    if directory is None:
        return any(
            _glob_meets_log(alt.rsplit("/", 1)[-1])
            for alt in shellscan._brace_alternatives(word)
            if not alt.startswith("/") and any(ch in alt.rsplit("/", 1)[-1] for ch in _GLOB)
        )
    return False


# The verbs whose operands `_verb_truncates` judges; the prefilter reads their words, and nothing else of the command.
_TRUNCATING_VERBS = frozenset(("mv", "truncate", "cp", "dd", "tee"))


def _log_stem():
    """The fixed part every round-log name carries (`pr-babysit`), read from RL's own prefix; raises at import if RL stops starting with one."""
    m = re.match(r"[A-Za-z]+-[A-Za-z]+", RL)
    if m is None:
        raise RuntimeError("RL no longer starts with a <word>-<word> stem: %r" % RL)
    return m.group(0)


_LOG_STEM = _log_stem()


def _word_could_name_log(word):
    """Could one word, as bash or a program's glob call expands it, name a round log? Its brace alternatives spell one (`RL`), or a glob in its basename meets the round-log pattern (`_glob_meets_log`)."""
    if not any(ch in word for ch in "*?[{"):
        return False
    for alt in shellscan._brace_alternatives(word):
        if re.search(RL, alt):
            return True
        base = alt.rsplit("/", 1)[-1]
        if any(ch in base for ch in _GLOB) and _glob_meets_log(base):
            return True
    return False


def _program_could_name_log(code):
    """Could an interpreter program's own text spell a round-log path? It names the round-log stem (`pr-babysit`, in a literal or an f-string alike), or one of its STRING LITERALS is a glob or brace that can meet the round-log pattern (`glob.glob('agent/*.md')`). Code outside a literal is never read for globs: `3 * 4`, `from os import *` and `r']*'` are Python, not paths (#e5b0540a's false positive, reported live by w2)."""
    if _LOG_STEM in code:
        return True
    # Every single- or double-quoted string literal, escapes kept (Python, shell and JS alike): an EXTRACTOR over program text the walk already chose, so it is local here rather than a module pattern a sentence could be probed against.
    literals = re.findall(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"", code)
    return any(_word_could_name_log(lit[1:-1]) for lit in literals)


def _shell_words(cmd):
    """The shell words a truncating arm judges: every redirect target, and the words (with what xargs appends) of each `mv`, `truncate`, `cp`, `dd`, `tee` and in-place editor bash runs. Interpreter program text is not among them."""
    words = [target for _op, target in shellscan._analyse(cmd).writes]
    for run_ in shellscan.every_run(cmd):
        base = run_.name.rsplit("/", 1)[-1]
        if base in _TRUNCATING_VERBS or shellscan.in_place_edit(run_) is not None:
            words.extend(run_.argv)
            if run_.feed and "xargs" in run_.via:
                words.extend(run_.feed.split())
    return words


def _could_name_log(cmd):
    """The prefilter. A command passes when it names the round-log stem at all (`pr-babysit`), when one of its SHELL WORDS that a truncating arm judges holds a glob or brace that could spell a log (`_shell_words`, `_word_could_name_log`), or when an interpreter program's text could spell one (`_program_could_name_log`). A glob is put to the round-log pattern's automaton, never to the disk.

    SHELL WORDS, NEVER PROGRAM TEXT (#e5b0540a, live false positive reported by w2). The first version tokenised the whole command, so a lone `*` anywhere (`3 * 4` in a Python heredoc) met the pattern, the program's write through a variable then failed closed, and every Python heredoc that wrote a file and multiplied was refused.
    """
    if _LOG_STEM in cmd:
        return True
    if not any(ch in cmd for ch in "*?[{"):
        return False
    if any(_word_could_name_log(w) for w in _shell_words(cmd)):
        return True
    return any(_program_could_name_log(code) for _family, code in WT.interpreter_programs(cmd))


def _copy_writes_log(run_, cwd):
    """Does this `cp` put a file at a round-log path? Where the copy lands is `shellscan.copy_landings`' reading, over the words as bash expands them, the xargs feed included (review 0bbd6471.3: `echo <log> | xargs cp /tmp/bak.md` copies onto the log).

    A copy INTO a directory lands under the source's own name, so `cp <log> /backup/` writes `/backup/<log name>`: a backup, which this guard has always read as a read. Such a landing counts only where a round log lives (a directory named `agent`) or where one already exists, which is the restore-over-the-log shape (`cp /tmp/<log name> agent/`).
    """
    for path, into in shellscan.copy_landings(run_, cwd, ("cp",)):
        # A landing is absolute, so a glob in it is matched on disk; its shape counts too (`_names_log`).
        if not _names_log(path):
            continue
        if not into or os.path.exists(path) or os.path.basename(os.path.dirname(path)) == "agent":
            return True
    return False


def _appends(args):
    """`tee -a`, `--append`, or a bundle holding `a` (`-ia`). `--output-error=warn` is not one: the arm was once fooled by the `a` in `warn`."""
    return any(
        a == "--append" or re.fullmatch(r"-[A-Za-z]*a[A-Za-z]*", a) is not None for a in args
    )


def _verb_truncates(run_, cwd):
    """Does this run's verb replace a round log wholesale? `mv` and `truncate` on any operand, `cp` onto where `_copy_writes_log` lands it, `dd of=`, `sed -i`, and `tee` without an append flag. xargs appends its input as operands, so the fed words count as operands in every arm."""
    base = run_.name.rsplit("/", 1)[-1]
    # The words as bash hands them over (`_Run.xargv`): `F=<log>; mv $F /tmp/` names the log through a variable an earlier statement set.
    args = list(run_.argv if run_.xargv is None else run_.xargv)
    operands = [a for a in args if not (a.startswith("-") and len(a) > 1)]
    if "xargs" in run_.via and run_.feed:
        operands += run_.feed.split()
    if base in ("mv", "truncate"):
        hits = operands
    elif base == "cp":
        return _copy_writes_log(run_, cwd)
    elif base == "dd":
        hits = [a[3:] for a in args if a.startswith("of=")]
    elif shellscan.in_place_edit(run_) is not None:
        # EVERY IN-PLACE EDITOR, by its own option parse (#6378e10e): sed, gsed and `perl -i`/`-pi` rewrite the files they name, and `perl -pi -e ... <log>` was allowed while only sed was asked. The files are `in_place_edit`'s, read over the words as bash expands them (an attached `-e` script is not a file, review 3f53e99e.2), plus what xargs appends.
        expanded = types.SimpleNamespace(name=run_.name, argv=args)
        edit = shellscan.in_place_edit(expanded) or shellscan.in_place_edit(run_)
        fed = run_.feed.split() if "xargs" in run_.via and run_.feed else []
        hits = [*edit[1], *fed]
    elif base == "tee":
        hits = [] if _appends(args) else operands
    else:
        hits = []
    # Each operand as bash expands it in the run's own directory: `mv agent/pr-babysit-{0831-1,x}.md /tmp/` and `truncate -s0 agent/pr-babysit-*.md` name the log (#e5b0540a).
    directory = shellscan._run_directory(run_, cwd)
    return any(_names_log(h, directory) for h in hits)


def _program_truncates(code):
    """Does an interpreter program write a round log, or write a target it never names?

    THE PYTHON ARM MUST TEST THE TARGET, NOT JUST THE IDIOM. A heredoc editing an unrelated file whose CONTENT quotes a round-log path matched every time when this was an unconditional idiom test (measured 2026-08-27, refusing an edit to a scratchpad state-body file). So the write target is resolved the way python spells one -- assigned to a name, or handed to open()/Path() -- and every quoted path inside a copy/move call counts too, since only the destination truncates and telling the two apart by position across copy/copyfile/copy2/move/replace/rename is fragile. FAIL CLOSED when no target resolves: that unidentifiable shape is `p.write_text(s[:i] + new)`, which destroyed the round history on 2026-08-19.

    shutil/os MOVE AND COPY COUNT AS WRITES. Measured 2026-08-27: shutil.copy and os.replace onto a round log both returned 0 from this guard, because the arm triggered only on write_text and open(...,"w"). Each of them overwrites the file completely.
    """
    if not hookio.grep_q_line(
        r"write_text|open\([^)]*[\"']w|shutil\.(copy|copyfile|copy2|move)|os\.(replace|rename)",
        code,
    ):
        return False
    candidates = []
    for match in hookio.grep_o(
        r"(=|open\(|Path\()[" + hookio.BLANK + r"]*[\"'][^\"']+\.md", hookio._here_string(code)
    ):
        candidates.extend(hookio.grep_o(r"[A-Za-z0-9_./-]+\.md", match))
    for match in hookio.grep_o(
        r"(shutil\.(copy|copyfile|copy2|move)|os\.(replace|rename))\([^)]*",
        hookio._here_string(code),
    ):
        candidates.extend(hookio.grep_o(r"[A-Za-z0-9_./-]+\.md", match))
    if candidates:
        return any(_is_log(c) for c in candidates)
    # FAIL CLOSED ONLY WHERE THE PROGRAM COULD SPELL A LOG (#e5b0540a). An unresolvable target is `p.write_text(s[:i] + new)`, the 2026-08-19 shape, and stays refused when the program's text could name a round log (`_program_could_name_log`); a program that names nothing of the kind writes some other file, however it writes it.
    return _program_could_name_log(code)


def run(ev):
    cmd = ev.field("tool_input", "command")

    # A round-log path must appear at all, literally or as a glob or brace that could spell one (#e5b0540a: `echo pr-babysit-*.md | xargs cp /tmp/x.md` was allowed here before the walk ran), which is also what keeps the walk below off every command that cannot touch one.
    if not _could_name_log(cmd):
        return hookio.ALLOW

    # The redirects bash performs, with their operator: `>` truncates, `>>` appends (`2>&1`-style descriptor plumbing names no file).
    # A redirect target is expanded by bash too (`> agent/pr-babysit-*.md` truncates the one log it matches), and its run's directory is not on the write record, so a glob there is read by its shape.
    truncating = any(
        op in TRUNCATING_OPS and _names_log(target) and not re.fullmatch(r"\d+|-", target)
        for op, target in shellscan._analyse(cmd).writes
    )
    # The verbs it runs, behind any prefix, xargs, sh -c or find -exec.
    cwd = ev.field("cwd") or str(hookio.repo_root())
    truncating = truncating or any(_verb_truncates(r, cwd) for r in shellscan.every_run(cmd))
    # An in-process write from python, node, perl or ruby. NOT anchorable the way the shell verbs are: the 2026-08-19 incident was a heredoc where the path sat on a DIFFERENT LINE from the write call. A program that writes an UNNAMED target is refused when its OWN text could spell a round-log path (`_program_could_name_log`: the `pr-babysit` stem, or a string literal glob that meets the pattern), because that is the exact shape that destroyed the appendix; one whose text cannot spell a log writes some other file and passes, whatever else the command mentions (#e5b0540a).
    truncating = truncating or any(
        _program_truncates(code) for _family, code in WT.interpreter_programs(cmd)
    )

    if not truncating:
        return hookio.ALLOW

    ev.warn(MESSAGE)
    return hookio.DENY
