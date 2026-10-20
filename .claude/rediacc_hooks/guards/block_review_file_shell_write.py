"""Refuse a Bash command that writes a per-commit review record under `agent/reviews/` by hand.

WHY. The pre-bash half of `block_review_file_edit` (agent/plans/PLAN-per-commit-review.md section 6): the Edit/Write tools are refused there, so the same hand edit through the shell is refused here. The shapes are the ones a session reaches for: an output redirection (`>`, `>>`, `>|`), `tee`, `sed -i`/`perl -i`, `cp`/`mv`/`install`/`rsync`/`ln` onto the directory, `truncate`, `dd of=`, and an
interpreter one-liner or heredoc (`python3 -c`, `python3 - <<EOF`, `node -e`) whose code names the directory and opens something for writing. A tool's own output option is a write too (`sort -o`, `git diff --output=`, `find -fprint`), and so is any word of a command `shellscan.output_landings` does not list as a reader (`curl -o`, `tar -cf`, `touch`): that reading is a table of non-writers, so a tool
nobody listed is refused when it names a review path rather than allowed.

READ BY THE LEXER, NOT BY A REGEX OVER THE TEXT. `shellscan` already knows where bash really redirects and which words are a command's operands, so `echo "agent/reviews"`, `cat agent/reviews/b/x.md`, `grep -rn x agent/reviews/` and a commit message naming the path all pass. The two sanctioned writers are named and pass too: the reviewer (`wl_review.py`) and the worklist verbs that
call it (`worklist.py --review-mark`, `--review-commit`, `--review-run`).

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_review_file_shell_write.py` beside it and against its own DEFECT, never against a golden.
"""

import ast
import fnmatch
import functools
import itertools
import os
import re
import shlex

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 53

# The path test every shell shape goes through. With it answering no, every redirect, tee, sed -i and copy onto a review file passes.
DEFECT = ("    if not word:\n        return False", "    if True:\n        return False")

REVIEW_TEXT = "agent/reviews/"
# A string literal that IS a review path (relative or absolute), as opposed to prose that mentions one: the quote is followed by path characters only. A URL (`https://.../agent/reviews/...`) names a web page, not a file on disk, so a literal opening with a scheme is not one.
REVIEW_LITERAL = re.compile(r"['\"](?![A-Za-z][A-Za-z0-9+.-]*://)(?:[^'\"\s]*/)?agent/reviews/")
REVIEW_WORD = re.compile(r"(\A|/)agent/reviews(/|\Z)")
SANCTIONED = ("wl_review.py", "worklist.py")
# Every interpreter `shellscan.interpreter_program` reads (#a2599946): this guard listed python, node, perl and ruby alone, so `deno eval`, `bun -e`, `tsx -e` and `deno run - <<EOF` wrote a review file unread (rc 0, 2026-10-15 at bd4ead963).
INTERPRETERS = shellscan.INTERPRETER_NAMES
# Code that opens a file for writing, replaces or removes one. `.open('w')` is pathlib's spelling, whose mode is the FIRST argument (e30f1ad1.1).
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|\.open\(\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|O_WRONLY|O_RDWR|O_APPEND|O_CREAT|O_TRUNC|write_text|write_bytes|os\.replace|os\.rename|shutil\.(copy|move)|unlink|writeFileSync|appendFileSync"
)
# Code that hands a string to a shell or starts a program (e30f1ad1.2): its string literals are commands, judged by this guard's own shell reading rather than by the line-scoped write test, which a redirect inside `os.system('echo x > ...')` never meets.
SHELL_CALL = re.compile(
    r"\b(system|popen|exec(Sync|File|FileSync)?|spawn(Sync)?|subprocess|check_output|check_call|getoutput|getstatusoutput|qx|Popen3?|Open3)\b|`"
)
_LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`([^`\n]*)`")
# How deep a command handed to a shell from inside a program is followed; a program that runs a program that runs a shell is two.
MAX_DEPTH = 4

MESSAGE = (
    "BLOCKED: this command writes a per-commit review record by hand (%s).\n"
    "\n"
    "Review files are written by the reviewer and closed only through the verb, which checks\n"
    "the fix before it records it. A hand edit is how a high finding disappears without a fix.\n"
    "\n"
    "  close a finding:  .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> fixed <sha>\n"
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> not-a-bug <evidence path:line>\n"
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> waived #<item> ASKED:<YYYY-MM-DDTHH:MM>Z\n"
    "  re-review:        python3 .claude/hooks/stop/wl_review.py --run <sha> --branch <branch>\n"
    "  record them:      .claude/hooks/stop/worklist.py --review-commit <me>\n"
)

R = "agent/reviews/1231-9/" + "a" * 40 + ".md"

EDGE_CASES = [
    ("a redirect", "printf 'Resolution: fixed' > %s" % R),
    ("an append", "echo x >> %s" % R),
    ("an append to the clean ledger", "echo '{}' >> agent/reviews/1231-9/clean.jsonl"),
    ("a cat heredoc", "cat > %s <<'EOF'\n# Review\nEOF" % R),
    ("tee", "echo x | tee %s" % R),
    ("tee -a", "echo x | tee -a %s >/dev/null" % R),
    ("sed -i", "sed -i 's/\\[high\\]/[low]/' %s" % R),
    ("cp onto the directory", "cp /tmp/x.md agent/reviews/1231-9/"),
    ("mv onto a review file", "mv /tmp/x.md %s" % R),
    ("cp -t names the directory", "cp -t agent/reviews/1231-9 /tmp/x.md"),
    # #5077391c: xargs appends its feed, so under `-t` a fed word is a source and without it the last one is the destination.
    # The fed word as the file an in-place editor, tee or truncate writes. Each was allowed before: the editor's own words named no review file.
    ("xargs feeds a review file to sed -i", "echo %s | xargs sed -i s/a/b/" % R),
    ("xargs -I feeds a review file to sed -i", "echo %s | xargs -I{} sed -i s/a/b/ {}" % R),
    ("xargs feeds a review file to tee", "echo %s | xargs tee" % R),
    ("xargs feeds a review file to truncate", "echo %s | xargs truncate -s 0" % R),
    (
        "xargs -I feeds a review directory to truncate",
        "echo agent/reviews/1231-9 | xargs -I{} truncate -s 0 {}/x.md",
    ),
    ("xargs feeds a review file to a reader", "echo %s | xargs cat" % R),
    ("xargs feeds another file to sed -i", "echo /tmp/x.md | xargs sed -i s/a/b/"),
    ("xargs feeds a review file to cp -t elsewhere", "echo %s | xargs cp -t /tmp" % R),
    (
        "xargs feeds cp -t the review directory a source",
        "echo /tmp/x.md | xargs cp -t agent/reviews/1231-9",
    ),
    ("xargs feeds cp a review file as its destination", "echo %s | xargs cp /tmp/x.md" % R),
    (
        "xargs feeds a review file then a destination elsewhere",
        "echo %s /tmp/out.md | xargs cp" % R,
    ),
    ("a copy OUT through cp -t", "cp -t /tmp %s" % R),
    ("truncate", "truncate -s 0 %s" % R),
    ("python -c open for write", "python3 -c \"open('%s','w').write('x')\"" % R),
    (
        "python heredoc write_text",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('%s').write_text('x')\nEOF" % R,
    ),
    ("after cd", "cd agent/reviews/1231-9 && echo x > a.md"),
    ("inside sh -c", "sh -c 'echo x > %s'" % R),
    # allowed
    ("reading one", "cat %s" % R),
    ("grep over the directory", "grep -rn high agent/reviews/"),
    ("echo naming the path", "echo 'see agent/reviews/1231-9/'"),
    ("a commit that carries them", "git commit -F /tmp/m.txt -- agent/reviews/1231-9/"),
    ("git add", "git add -- agent/reviews/1231-9/%s.md" % ("a" * 40)),
    (
        "the mark verb",
        ".claude/hooks/stop/worklist.py --review-mark abcd1234 aaaaaaaa.1 fixed %s" % ("b" * 40),
    ),
    ("the reviewer", "python3 .claude/hooks/stop/wl_review.py --run abc --branch 1231-9"),
    ("a copy OUT of the directory", "cp %s /tmp/x.md" % R),
    ("a python read", "python3 -c \"print(open('%s').read())\"" % R),
    (
        "python heredoc rewriting a URL that names the directory",
        (
            "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('t.py')\n"
            "p.write_text(p.read_text().replace('\"https://github.com/o/r/blob/h/agent/reviews/b/x.md\"', 'U'))\nEOF"
        ),
    ),
    ("an unrelated redirect", "echo x > /tmp/out.txt"),
    ("a sibling directory", "echo x > agent/reviews-old/x.md"),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    (
        "sed -i launched by find under the directory",
        "find agent/reviews -name '*.md' -exec sed -i s/high/low/ {} +",
    ),
    (
        "a launched cp onto what find names",
        r"find agent/reviews -name '*.md' -exec cp /tmp/x.md {} \;",
    ),
    (
        "a launched copy OUT of the directory",
        r"find agent/reviews -name '*.md' -exec cp {} /tmp/ \;",
    ),
    # A Python program is judged by its write TARGETS: a review path in written content is data.
    (
        "a review path only in written content",
        "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('/tmp/s/f.py')\ns = p.read_text().replace('X', 'agent/reviews/feat/%02d.md')\np.write_text(s)\nEOF",
    ),
    (
        "a target built from a review path",
        "python3 - <<'EOF'\nimport pathlib\nT = 'agent/reviews/feat/%02d.md'\npathlib.Path(T % 1).write_text('x')\nEOF",
    ),
    # e30f1ad1.1: pathlib's `.open` takes its mode first, `os.open` takes flags.
    ("Path.open for write", "python3 -c \"import pathlib; pathlib.Path('%s').open('w')\"" % R),
    ("Path.open for read", "python3 -c \"import pathlib; pathlib.Path('%s').open().read()\"" % R),
    ("os.open for write", "python3 -c \"import os; os.open('%s', os.O_WRONLY)\"" % R),
    # e30f1ad1.2: a command a program hands to a shell is judged as the shell line it is.
    ("os.system redirect", "python3 -c \"import os; os.system('echo x > %s')\"" % R),
    ("subprocess argv tee", "python3 -c \"import subprocess; subprocess.run(['tee', '%s'])\"" % R),
    ("node execSync redirect", "node -e \"require('child_process').execSync('echo x > %s')\"" % R),
    (
        "os.system reading the directory",
        "python3 -c \"import os; os.system('cat %s > /tmp/x')\"" % R,
    ),
]


def _is_review(word, cwd=None, base=None):
    if not word:
        return False
    # The directory is read with the word, so a glob in it counts as one in the word does: `cd agen? && tee revi*s/x.md` writes a review file, and joining the typed `agen?` onto the word's forms read `agen?/reviews/x.md` (rc 0).
    joined = [word, str(cwd).rstrip("/") + "/" + word] if cwd else [word]
    return any(REVIEW_WORD.search(form) for w in joined for form in _review_forms(w)) or (
        _lands_in_reviews(word, base)
    )


# A WORD IS ALSO READ WHERE THE DISK PUTS IT (#816a7c93). With `lnk` a link to `agent/reviews/sub`, `cd lnk && tee x.md`, `echo x > lnk/x.md` and `cp /tmp/a lnk/` write review files while no word, and no directory text the walk keeps, spells the review directory: the lexical reading allowed all three (rc 0), logical `cd` or physical. `base` is the absolute directory the run executes in, and the word is resolved against it on disk.
# Read only for a word short enough to be a path: a heredoc body or a commit message is not one, and resolving it would only spend system calls.
_PATH_MAX = 4096


def _base(where, cwd):
    """The absolute directory a run in `where` (`shellscan.write_directory`'s answer) executes in, or None when the hook's own directory is not an absolute path."""
    if not cwd or not os.path.isabs(str(cwd)):
        return None
    return os.path.join(str(cwd), str(where)) if where else str(cwd)


def _lands_in_reviews(word, base):
    """True when `word`, resolved on disk from the absolute directory `base`, is inside the review directory: a symlink anywhere on the way is followed, and so is one the walk's text cannot see (the hook's own directory, a `..` after a link)."""
    if not base or not word or len(word) > _PATH_MAX or "\n" in word or "\0" in word:
        return False
    try:
        landed = os.path.realpath(os.path.join(base, word))
    except (OSError, ValueError):
        return False
    return REVIEW_WORD.search(landed.replace("\\", "/")) is not None


def _reaches_reviews(cmd, cwd):
    """The pre-filter's second question, for a command whose text names no review directory: does any directory it runs in, or any word or redirect target it names, resolve on disk into one (#816a7c93)? Each run's words, redirects, fed words and launch starts are read against the directory the run executes in, so a link reached by `cd`, `pushd`, `env -C` or inside a path word sends the command to the full check, and a command that touches no such link stays on the cheap path.

    SOUND FOR THE FULL CHECK'S DISK READING: every word `_offending` resolves on disk is one of a run's words, redirects or fed words joined to that run's directory, so a command answered no here holds nothing `_lands_in_reviews` would refuse.
    """
    if not cwd or not os.path.isabs(str(cwd)):
        return False
    if any(_lands_in_reviews(t, str(cwd)) for t in shellscan.write_targets(cmd)):
        return True
    for run in shellscan.every_run(cmd):
        base = _base(shellscan.write_directory(run.cwd, cwd), cwd)
        words = [".", *run.argv, *shellscan.redirect_targets(run), *(run.xargv or ())]
        words.extend(run.feed_words or ())
        if run.feed:
            words.extend(run.feed.split())
        if run.launch is not None:
            words.extend(run.launch.starts)
        # Each value a `for` loop gives a word (#b53f586d): `for D in lnk; do echo x > $D/y.md; done` writes through the link.
        words.extend(
            form
            for w in [*run.argv, *shellscan.redirect_targets(run)]
            for form, definite in _readings(w, run, cmd)
            if definite
        )
        # A program's code is one argv word, so a link it names (`python3 -c "open('lnk/x.md','w')"`) is read as each string literal it holds (review 84fdeff8.1).
        words.extend(lit for w in run.argv for lit in _literals(w))
        if any(_lands_in_reviews(w, base) for w in words):
            return True
    return False


# A WORD THE WALK CANNOT EXPAND IS READ BY WHERE ITS VALUE CAN COME FROM (#b53f586d). `for D in agent/reviews/x; do echo hi > $D/y.md; done` and `read D <<< agent/reviews/x; echo hi > $D/y.md` write the review file (bash 5.3), while the walk keeps `$D/y.md` as typed, since one value cannot stand for every
# iteration of a loop and a `read` takes what its input holds: both were allowed (rc 0). Each expansion in such a word is read as one of four things. A `for`/`select` variable is each word of the list it walks (`shellscan._Run.loop_vars`), so the word is read once per value, and a value that names a review path is a write to it. A variable the walk knows is its value, and `$#`,
# `$?`, `$$`, `$!` and `$((...))` are numbers. A value made ON THE LINE that the walk cannot know is read from the text it is made from: the value word of `NAME=$(...)`, the input of a `read`, `mapfile` or `readarray`, the words of a `printf -v`, of a `set` or of a call to a function the line defines for a positional parameter, the text of a substitution in the word itself (`_value_source`, `_positional_source`). When that text spells `reviews` as a path segment, or when no such text is readable (a `read` from a file, `getopts`, `${D:=x}`, every variable after `source`) and the line itself spells it, the value is read as a path into the review directory, and a write there is refused as unjudgeable.
# A value from OUTSIDE the line (a variable the session's environment holds, a substitution whose text does not name `reviews`) is one unknown path segment: it may complete a directory the literal text half spells (`agent/$X`, `$X/reviews/y.md`, `$X/y.md` under `cd agent`), but two of them never spell `agent/reviews` alone, so `echo > "$OUT/$NAME"` stays allowed.
_WORST = "agent/reviews/_"
# Text that spells `reviews` as a path segment could: `agent/reviews/x`, `reviews` alone under `cd agent`; never inside a longer name (`push_with_unrecorded_reviews`, `reviews-only`, `reviews.txt`), which no value turns into the directory.
_SPELLS_REVIEWS = re.compile(r"(?<![\w.-])reviews(?![\w.-])")
_OUTSIDE = "\x01"
_READINGS_CAP = 64


def _expansions(word):
    """`(start, end, kind, name)` for each outermost expansion in a quote-removed word: kind "var" (`$NAME`, `${NAME}`), "op" (`${NAME...}` with an operator), "positional" (`$1`, `$@`, `$*`), "number" (`$#`, `$?`, `$$`, `$!`, `$-`, `$0`, `$((...))`), "indirect" (`${!NAME}`, and with an empty name any other `${!...}` form) or "subst" (`$(...)`, a backquoted span)."""
    out = []
    i = 0
    while i < len(word):
        ch = word[i]
        if ch == "`":
            end = word.find("`", i + 1)
            end = len(word) if end < 0 else end + 1
            out.append((i, end, "subst", ""))
            i = end
            continue
        if ch != "$" or i + 1 >= len(word):
            i += 1
            continue
        nxt = word[i + 1]
        if nxt in "({":
            close = ")" if nxt == "(" else "}"
            depth, j = 0, i + 1
            while j < len(word):
                depth += word[j] == nxt
                depth -= word[j] == close
                j += 1
                if depth == 0:
                    break
            body = word[i + 2 : j - 1]
            if nxt == "(":
                out.append((i, j, "number" if body.startswith("(") else "subst", ""))
            elif body.startswith("!") and len(body) > 1:
                # `${!NAME}` is the value of the variable NAME names (8ef78586.1), not `$!`: `P=D; D=agent/reviews/x; echo hi > ${!P}/y.md` writes the review file (bash 5.3). Any other `${!...}` form (`${!P:-x}`, `${!pre*}`, `${!a[@]}`) keeps an empty name and is read as unknowable.
                m = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", body[1:])
                out.append((i, j, "indirect", m.group(0) if m else ""))
            else:
                m = re.match(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[@*#?$!-]", body)
                name = m.group(0) if m else ""
                if not name or name in "#?$!-" or name == "0":
                    kind = "number"
                elif name[0].isdigit() or name in "@*":
                    kind = "positional"
                else:
                    kind = "var" if body == name else "op"
                out.append((i, j, kind, name))
            i = j
            continue
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", word[i + 1 :])
        if m:
            out.append((i, i + 1 + m.end(), "var", m.group(0)))
            i += 1 + m.end()
        elif nxt.isdigit() or nxt in "@*":
            out.append((i, i + 2, "number" if nxt == "0" else "positional", nxt))
            i += 2
        elif nxt in "#?$!-":
            out.append((i, i + 2, "number", nxt))
            i += 2
        else:
            i += 1
    return out


def _span_choices(span, word, run, cmd):
    """`(values, definite)` for one expansion of `word`: the texts it may stand for, and whether they are every value bash can give it."""
    start, end, kind, name = span
    text = word[start:end]
    on_line = _WORST if _SPELLS_REVIEWS.search(cmd) else _OUTSIDE
    loop = getattr(run, "loop_vars", None) or {}
    state = getattr(run, "vars", None) or {}
    if kind == "number":
        return ["0"], True
    if kind == "positional":
        source = _positional_source(cmd)
        if source is None:
            return [on_line], False
        return [_WORST if _SPELLS_REVIEWS.search(source) else _OUTSIDE], False
    if kind == "subst":
        return [_WORST if _SPELLS_REVIEWS.search(text) else _OUTSIDE], False
    if kind == "indirect":
        # Read through both names when the walk knows both (`P=D; D=x` gives `x`); a name it cannot know, or a value that is not a variable name, leaves the line's unknown.
        if name:
            targets, definite = _span_choices((start, end, "var", name), word, run, cmd)
            if definite and all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t) for t in targets):
                values = []
                for target in targets:
                    got, known = _span_choices((start, end, "var", target), word, run, cmd)
                    if not known:
                        break
                    values.extend(got)
                else:
                    return values, True
        return [on_line], False
    if kind == "op":
        # `${D:?msg}` is D's value; `${D:-x}` and `${D:=x}` are D's or `x`; `${D:+x}` is `x` or nothing; `${f#p}`, `${f##p}`, `${f%p}` and `${f%%p}` trim a known value. Any other operator (`${D/a/b}`, `${D:1}`) derives a value this reading does not compute.
        trim = re.match(r"[A-Za-z_][A-Za-z0-9_]*(##?|%%?)(.*)\Z", text[2:-1], re.DOTALL)
        if trim is not None and "$" not in trim.group(2) and "`" not in trim.group(2):
            own = _span_choices((start, end, "var", name), word, run, cmd)
            if own[1]:
                return [_trimmed(v, trim.group(1), trim.group(2)) for v in own[0]], True
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*(:?[-=?+])(.*)\Z", text[2:-1], re.DOTALL)
        if m is None:
            return [on_line], False
        op, alt = m.group(1).lstrip(":"), m.group(2)
        alt_choice = (
            ([alt], True)
            if "$" not in alt and "`" not in alt
            else (
                [_WORST if _SPELLS_REVIEWS.search(alt) else _OUTSIDE],
                False,
            )
        )
        if op == "+":
            return [*alt_choice[0], ""], alt_choice[1]
        own = _span_choices((start, end, "var", name), word, run, cmd)
        if op == "?":
            return own
        return own[0] + alt_choice[0], own[1] and alt_choice[1]
    if kind == "var" and name in loop:
        return list(loop[name]), True
    if name in state:
        value = state[name][0]
        if isinstance(value, str) and shellscan._UNRESOLVED not in value and kind == "var":
            return [value], True
        source = _value_source(name, cmd, shellscan._CLOBBERED in str(value))
        if source is None:
            return [on_line], False
        return [_WORST if _SPELLS_REVIEWS.search(source) else _OUTSIDE], False
    if shellscan._OPAQUE_KEY in state:
        return [on_line], False
    return [_OUTSIDE], False


@functools.lru_cache(maxsize=64)
def _positional_source(cmd):
    """The text the positional parameters take their values from: the words of every `set` and of every call to a function the command defines (`shellscan._FN_KEY`), or None after `source`, which may set them from anywhere. The hook's own shell runs the command with none, so a command that sets none gives the empty text."""
    texts = []
    try:
        runs = list(shellscan.every_run(cmd))
    except Exception:
        return None
    for run in runs:
        base = run.name.rsplit("/", 1)[-1]
        if base in ("source", "."):
            return None
        state = getattr(run, "vars", None) or {}
        if base == "set" or shellscan._FN_KEY + run.name in state:
            texts.append(" ".join(run.argv))
    return "\n".join(texts)


def _assignment_values(name, cmd):
    """The text of every `NAME=value` (and `NAME+=`, `NAME:=`) the command spells, each value read to the first unquoted blank or control operator outside a substitution, as bash ends an assignment word."""
    out = []
    for m in re.finditer(r"(?<![\w$])%s:?\+?=" % re.escape(name), cmd):
        i, depth, quote = m.end(), 0, ""
        while i < len(cmd):
            ch = cmd[i]
            if quote:
                if ch == quote:
                    quote = ""
                elif ch == "\\" and quote == '"':
                    i += 1
            elif ch in "'\"`":
                quote = ch
            elif ch == "\\":
                i += 1
            elif ch in "({":
                depth += 1
            elif ch in ")}":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0 and (ch.isspace() or ch in ";&|<>"):
                break
            i += 1
        out.append(cmd[m.end() : i])
    return out


@functools.lru_cache(maxsize=64)
def _value_source(name, cmd, by_builtin):
    """The text a variable the walk could not evaluate takes its value from, as near as the command spells it, or None where that is not readable: each `NAME=value` it spells, the input a `read`, `mapfile` or `readarray` of NAME reads (its here-string, heredoc or piped words) and the words of a `printf -v NAME`.

    None, read as any text the line holds, for an assignment no spelling here reaches: a `read` from a file, `getopts`, a function call, an arithmetic or `${NAME:=x}` assignment with no `NAME=` word, and every variable after `source`. Without this, `T=$(mktemp); cat agent/reviews/a.md > $T` read `$T` as the review directory.
    """
    if not by_builtin:
        # The walk keeps a builtin's assignment apart (`shellscan._CLOBBERED`), so a value it calls unresolved was last given by a `NAME=value` word.
        texts = _assignment_values(name, cmd)
        return "\n".join(texts) if texts else None
    texts = []
    try:
        runs = list(shellscan.every_run(cmd))
    except Exception:
        return None
    for run in runs:
        base = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        if base in ("read", "mapfile", "readarray") and name in argv:
            if run.feed is None:
                return None
            texts.append(run.feed)
        elif base == "printf" and name in argv and "-v" in argv:
            texts.append(" ".join(argv))
    return "\n".join(texts) if texts else None


def _trimmed(value, op, pattern):
    """`${NAME#pattern}` and its siblings on a known `value`: `#` drops the shortest matching prefix, `##` the longest, `%` the shortest matching suffix, `%%` the longest, each matched as bash matches a pattern (`fnmatch`)."""
    cuts = range(len(value) + 1)
    if op.startswith("#"):
        hits = [i for i in cuts if fnmatch.fnmatchcase(value[:i], pattern)]
        if not hits:
            return value
        return value[max(hits) if op == "##" else min(hits) :]
    hits = [i for i in cuts if fnmatch.fnmatchcase(value[i:], pattern)]
    if not hits:
        return value
    return value[: min(hits) if op == "%%" else max(hits)]


def _outside_forms(form):
    """`form` with each value from outside the line read as an unknown segment (`*`), a whole-segment one only one at a time, so two such segments never stand for `agent` and `reviews` together."""
    segments = form.split("/")
    whole = [i for i, seg in enumerate(segments) if seg == _OUTSIDE]
    if not whole:
        return [form.replace(_OUTSIDE, "*")]
    return [
        "/".join(
            ("*" if i == keep else "_") if i in whole else seg.replace(_OUTSIDE, "*")
            for i, seg in enumerate(segments)
        )
        for keep in whole
    ]


def _readings(word, run, cmd, depth=0):
    """`(form, definite)` for every path `word` may expand to that the walk did not expand (#b53f586d), [] for a word with no expansion. A definite form is one bash really produces (a loop value, a known variable); any other stands for a value this hook cannot know."""
    if not word or ("$" not in word and "`" not in word):
        return []
    spans = _expansions(word)
    if not spans:
        return []
    state = getattr(run, "vars", None) or {}
    loop = getattr(run, "loop_vars", None) or {}
    if all(
        kind == "number"
        or (
            kind in ("var", "op")
            and name not in loop
            and name in state
            and shellscan._UNRESOLVED not in str(state[name][0])
        )
        for _s, _e, kind, name in spans
    ):
        # Every value is one the walk knows, so a word it still left as typed is one bash splits, globs or drops (`D="a b"; echo > $D` is an ambiguous redirect), which the walk already judged.
        return []
    choices = [_span_choices(span, word, run, cmd) for span in spans]
    combos = 1
    for values, _definite in choices:
        combos *= max(1, len(values))
    if combos > _READINGS_CAP:
        # Past the cap every expansion is read as the line's unknown, which names the review directory exactly when the line does.
        worst = _WORST if _SPELLS_REVIEWS.search(cmd) else _OUTSIDE
        choices = [(["0"], True) if s[2] == "number" else ([worst], False) for s in spans]
    out: list[tuple[str, bool]] = []
    for pick in itertools.product(*[values or [""] for values, _d in choices]):
        form, last = [], 0
        for (start, end, _k, _n), value in zip(spans, pick, strict=True):
            form.append(word[last:start])
            form.append(value)
            last = end
        form.append(word[last:])
        text = "".join(form)
        definite = all(d for _v, d in choices)
        if depth == 0 and ("$" in text or "`" in text) and _OUTSIDE not in text:
            # A loop word may itself hold an expansion (`for D in $X`): read it once more.
            nested = _readings(text, run, cmd, depth + 1)
            if nested:
                out.extend((f, definite and d) for f, d in nested)
                continue
        out.extend((f, definite) for f in _outside_forms(text))
    return out


def _argv_readings(run, argv, cmd):
    """`(argv, definite)` with one word at a time replaced by each of its `_readings`, the others as typed: every operand reading checks one word, so a product across words adds nothing."""
    for at, word in enumerate(argv):
        for form, definite in _readings(word, run, cmd):
            yield [*argv[:at], form, *argv[at + 1 :]], definite


_UNKNOWN_NOTE = ", through a word this hook cannot expand (read as %s); spell the path literally"


_GLOB_OR_BRACE = frozenset("*?[{")


def _globs_reviews(cmd, cwd):
    """The pre-filter's glob question: does any word the full check reads hold a glob or brace that `_review_forms` reads as the review directory, alone or under the directory its run executes in? Each run's words as typed and as bash expands them, its redirects, what xargs feeds it (alone and in a marker's place) and what a `find -exec` walks, so `cp x agent/revi*s/` and `echo revi*s/x | xargs cp a` under `cd agent` reach the full check.

    A GLOB INSIDE PROGRAM TEXT IS NOT A PATH (#a1852a9e). Testing for any `*?[{` in the command sent `sed -i 's/a.*b/c/' x.py && python3 x.py` to the full check, whose unreadable-script refusal then fired on a command that names no review path at all (rc 2). `a.*b` is one segment no fnmatch reads as `agent` or `reviews`, so it stays on the cheap path; a sed or perl expression that does spell the directory through a glob (`s|x|agent/revi*s|`) still goes to the full check, which judges it as before.
    """

    def spells(word, where):
        return any(ch in word for ch in _GLOB_OR_BRACE) and _is_review(word, where)

    if any(spells(t, None) for t in shellscan.write_targets(cmd)):
        return True
    for run in shellscan.every_run(cmd):
        where = shellscan.write_directory(run.cwd, cwd)
        if where and spells(str(where), None):
            return True
        words = [*run.argv, *(run.xargv or ()), *shellscan.redirect_targets(run)]
        words.extend(run.feed_words or ())
        words = shellscan.xargs_fed_operands(run, words)
        if run.launch is not None:
            words.extend(run.launch.starts)
        if any(spells(w, where) for w in words):
            return True
        # A word the walk could not expand, read as the full check reads it (#b53f586d): a loop value, or an unknown segment that completes `agent/$X` or `$X/y.md` under `cd agent`.
        if any(
            _is_review(form, where)
            for w in [*run.argv, *shellscan.redirect_targets(run)]
            for form, _definite in _readings(w, run, cmd)
        ):
            return True
    return False


def _literals(text):
    """Every quoted string literal in `text` (single, double or backquoted), unescaped no further."""
    for m in _LITERAL.finditer(text):
        yield next(g for g in m.groups() if g is not None)


def _code_writes_through_disk(code, base, program=None):
    """Interpreter code that writes, through a link, to a path inside the review directory that its text never spells: `open('lnk/x.md','w')` with `lnk` a link into it (review 84fdeff8.1).

    A literal that spells the directory is the precise readings' to judge (a read-only `os.open`, a URL); this reading is for a path that reaches it only on disk. A Python `program` that parses is judged by its write TARGETS through `shellscan.python_writes_to`, so a literal bound to a name on one line and written on another is followed, and a link that is only read is not a write (review f25b1360.1, .3). Other code is read line by line, with a name assigned from such a literal standing for it on a later line.
    """

    def through_link(value):
        return (
            isinstance(value, str)
            and not REVIEW_WORD.search(value)
            and _lands_in_reviews(value, base)
        )

    if program is not None:
        verdict = shellscan.python_writes_to(program, through_link)
        if verdict is not None:
            return verdict
    names = {
        m.group(1)
        for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*=\s*([^\n=]*)", code)
        if any(through_link(lit) for lit in _literals(m.group(2)))
    }
    for line in code.splitlines():
        if not WRITE_CODE.search(line):
            continue
        if any(through_link(lit) for lit in _literals(line)):
            return True
        if any(re.search(r"(?<![\w$])%s(?![\w$])" % re.escape(n), line) for n in names):
            return True
    return False


_GLOB = frozenset("*?[")


def _review_forms(word):
    """The word, and what bash may make of it on the way to a review path (#7094b75e): each brace alternative (`agent/{reviews,x}/`), with every globbed segment that could match `agent` or `reviews` read as that name (`agent/revi*s/`, `revie[w]s` under `cd agent`). Read by shape, never against the disk, so a glob that does not match yet still counts."""
    forms = [word]
    for alt in shellscan._brace_alternatives(word) if "{" in word else [word]:
        segments = alt.split("/")
        forms.append(alt)
        # LINEAR IN THE SEGMENTS, never a product of them: the review directory is one segment read as `reviews`, or two neighbours read as `agent` and `reviews`, and every other segment stays as typed. A capped product dropped the reading of `agent/revi*s/*/*/*/*/*/f.md` that sits past its 64th combination (review c6dc18ec.1).
        reads = [
            [
                n
                for n in ("agent", "reviews")
                if any(ch in seg for ch in _GLOB) and fnmatch.fnmatchcase(n, seg)
            ]
            for seg in segments
        ]
        for i, names in enumerate(reads):
            forms.extend("/".join([*segments[:i], name, *segments[i + 1 :]]) for name in names)
            if "agent" in names and i + 1 < len(reads) and "reviews" in reads[i + 1]:
                forms.append("/".join([*segments[:i], "agent", "reviews", *segments[i + 2 :]]))
    return forms


# Git verbs whose positional words are refs, refspecs, patterns or names, never a file the verb writes: a glob refspec such as `refs/heads/*/*:refs/heads/q/*/*` is two adjacent `*` segments, which `_review_forms` reads as `agent/reviews`. The first operand of the remote verbs stays judged (a remote may be a path); an option stays judged whatever it carries. The word after a separate-form value option (`--receive-pack X`, `-o X`) is judged for the REMOTE verbs only, because there it is a program or path the verb runs or writes, wherever it sits; for a ref verb that word is a message, a format or a ref (`update-ref -m X ref`, `tag -m X v1`) and is dropped with the other positionals.
_GIT_REF_VERBS = frozenset(
    (
        "branch",
        "tag",
        "for-each-ref",
        "show-ref",
        "update-ref",
        "symbolic-ref",
        "remote",
        "merge",
        "rebase",
        "cherry-pick",
        "revert",
        "describe",
        "name-rev",
        "rev-parse",
        "reflog",
    )
)
_GIT_REMOTE_VERBS = frozenset(("push", "fetch", "pull", "ls-remote"))
# Options of the remote verbs that take their value as the NEXT word; that word is a program or path the verb may run or write, so it is read like the option.
_GIT_VALUE_OPTIONS = frozenset(
    (
        "--receive-pack",
        "--exec",
        "--upload-pack",
        "--repo",
        "--push-option",
        "--server-option",
        "-o",
    )
)


_GIT_ARCHIVE_VALUE_OPTIONS = frozenset(("-o", "--output", "--remote", "--exec"))


def _archive_takes_value(word):
    """Does this `git archive` option word take the NEXT word as its value?

    git's parse-options accepts a unique prefix of a long option (`--outp` is `--output`) and a bundle of short flags whose last one takes a value (`-vo X` is `-v -o X`), so exact membership let `git archive --outp agent/reviews/... HEAD` through (review 58be8bbc.1). A `--name=value` word carries its value and takes nothing more, and so does `-oPATH`: the first `o` ends the bundle and the rest of the word is its value, so only a word whose ONLY `o` is its last letter (`-o`, `-vo`, `-9o`) takes the next word (`-oo` writes a file named `o`).
    """
    if word.startswith("--"):
        if "=" in word or len(word) < 3:
            return False
        return any(
            full.startswith(word) for full in _GIT_ARCHIVE_VALUE_OPTIONS if full.startswith("--")
        )
    return re.fullmatch(r"-[A-Za-np-z0-9]*o", word) is not None


def _without_ref_operands(run, argv):
    """`argv` with the positional words of a git ref verb dropped, so only its options and its remote are read as possible file writes; any other command comes back unchanged."""
    if run.name.rsplit("/", 1)[-1] != "git":
        return argv
    at, _ = shellscan._git_verb_at(argv)
    if at is None:
        return argv
    verb = argv[at]
    if verb == "archive":
        # `git archive <rev> -- <path>` streams a tar to stdout and writes no file it names; only `-o`/`--output` (and the `--remote`/`--exec` words, a repository and a program) take a path the verb can write or run. The positionals are a tree-ish and pathspecs: reading `git archive HEAD -- agent/reviews/b/x.md | tar -x -C /tmp/x` as a write to that pathspec refused a pure read (2026-10-20). `-o X` / `--output X` in the separate form keeps X.
        out = list(argv[: at + 1])
        takes_value = False
        for word in argv[at + 1 :]:
            value_of_option, takes_value = takes_value, False
            if word.startswith("-") and len(word) > 1:
                out.append(word)
                takes_value = _archive_takes_value(word)
            elif value_of_option:
                out.append(word)
        return out
    if verb not in _GIT_REF_VERBS and verb not in _GIT_REMOTE_VERBS:
        return argv
    keep = 1 if verb in _GIT_REMOTE_VERBS else 0
    out = list(argv[: at + 1])
    takes_value = False
    for word in argv[at + 1 :]:
        value_of_option, takes_value = takes_value, False
        if word.startswith("-") and len(word) > 1:
            out.append(word)
            takes_value = verb in _GIT_REMOTE_VERBS and word in _GIT_VALUE_OPTIONS
        elif value_of_option:
            out.append(word)
        elif keep:
            out.append(word)
            keep -= 1
    return out


def _operands(argv):
    return [a for a in argv if not (a.startswith("-") and len(a) > 1)]


def _run_operands(run, argv):
    """`_operands`, with a `find -exec` run's `{}` read as what the find walks (#503f0ba8): `find agent/reviews -exec sed -i ... {} +` edits files under `agent/reviews`, so the find's starting points (`shellscan.Launch.starts`) stand in for `{}`, in place. A `{}` that is a copy's SOURCE is still not its last operand, so `-exec cp {} /tmp/ ';'` stays a copy out."""
    ops = _operands(argv)
    # What xargs reads becomes this command's words, appended or put where its marker stands, whatever the marker is (`shellscan.xargs_fed_operands`). It over-reads the operands and never under-reads them; a file named only inside an option's value (`sort --output=X/kept.md`) is not an operand, fed or typed, and is read by the `shellscan.output_landings` arm of `_offending` instead (worklist item ff3ab826): `echo <review file> | xargs sed -i ...` named no review file among sed's own words and was allowed.
    ops = shellscan.xargs_fed_operands(run, ops)
    if run.launch is None or run.launch.launcher != "find":
        return ops
    out: list[str] = []
    for a in ops:
        out.extend(run.launch.starts if "{}" in a else [a])
    return out


def _operand_write(run, name, argv, where, base, cwd):
    """A description of the review file `run` writes through one of its operands read from `argv` (tee, an in-place sed or perl, a copy's destination, truncate, `dd of=`), or ""."""
    operands = _run_operands(run, argv)
    if name == "tee" and any(_is_review(a, where, base) for a in operands):
        return "tee into the review directory"
    # In place is sed's or perl's own option parse (review 3f53e99e.2 sweep): `sed -Ei` and `perl -pi -e` are in place.
    in_place = shellscan.in_place_edit(run) is not None
    if in_place and any(_is_review(a, where, base) for a in operands):
        return "%s -i on a review file" % name
    # Where a copy lands is `shellscan.run_copies`' getopt reading, not the last operand (review cac47d16.1 sweep): `cp -t agent/reviews/x /tmp/a.md` left the source last.
    # `cwd` places a relative fed glob in the run's own directory (#e5b0540a). Two kinds of run get the shape reading instead: a command a PROGRAM hands down (the recursion in `_offending` passes no `cwd`, since it runs wherever that program does), and one a launcher starts (`find -exec`, `npx`: `shellscan._feed_directories`, review 9ed30a8a.1).
    copies = shellscan.run_copies(run, argv, cwd)
    if copies is not None and any(_is_review(d, where, base) for d in copies[1]):
        return "%s onto the review directory" % name
    if name == "truncate" and any(_is_review(a, where, base) for a in operands):
        return "truncate of a review file"
    if name == "dd" and any(a.startswith("of=") and _is_review(a[3:], where, base) for a in argv):
        return "dd of= a review file"
    return ""


def _offending(cmd, depth=0, cwd=None):
    """A short description of the first hand write to a review file in `cmd`, or "". `depth` counts the programs a shell command was handed down through (`os.system`, `subprocess.run`, `execSync`), so a command quoting itself cannot recurse forever.

    PAST THE CAP IT REFUSES. A command is only handed down when it names the review directory, so one nested deeper than MAX_DEPTH is a review path this guard stopped reading, and allowing it would let depth alone carry a write past the guard.
    """
    if depth > MAX_DEPTH:
        return (
            "a command nested more than %d programs deep that names the review directory"
            % MAX_DEPTH
        )
    hits = [t for t in shellscan.write_targets(cmd) if _is_review(t, cwd, _base(None, cwd))]
    if hits:
        return "redirect into %s" % hits[0]
    # THE LAUNCHED COMMANDS TOO (#503f0ba8): a `sed -i`, `cp` or interpreter that `find -exec` or `npx -c` starts writes the same review file, so the runs are `shellscan.every_run`.
    for run in shellscan.every_run(cmd):
        name = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        # A kept `<name>/..` pair is read where the disk resolves it (review 2925782e.1): `cd lnk && env -C .. tee x.md` writes into the parent of the directory `lnk` points to.
        where = shellscan.write_directory(run.cwd, cwd)
        # The absolute directory the run executes in, so each word is also read where the disk resolves it (#816a7c93).
        base = _base(where, cwd)
        if any(a.rsplit("/", 1)[-1] in SANCTIONED for a in [run.name, *argv[:2]]):
            continue
        # Each redirect target as typed and as bash expands it (#4deea064): under `cd agent`, `D=reviews/x; echo hi > $D/y.md` writes a review file that only the run's own directory joined to the expanded target names.
        for target in shellscan.redirect_targets(run):
            if _is_review(target, where, base):
                return "redirect into %s" % target
        # A target the walk could not expand (its expanded form is still the typed text) is read by where its value can come from (#b53f586d, `_readings`). One it expanded is already judged: a group's redirect is expanded before the body assigns (`D=plain; { D=x; } > $D/y.md`).
        typed = list(getattr(run, "writes", ()))
        expanded = list(getattr(run, "xwrites", ())) or typed
        for target, value in zip(typed, expanded, strict=False):
            if value != target:
                continue
            for form, definite in _readings(target, run, cmd):
                if _is_review(form, where, base):
                    return (
                        "redirect into %s" % form
                        if definite
                        else ("redirect into %s" % target + _UNKNOWN_NOTE % form)
                    )
        # THE WORDS ARE READ TWICE, as typed and as bash expands them (#f6334e52): `D=agent/reviews/x; tee $D/y.md`, `sudo tee $D/y.md` and `timeout 5 tee $D/y.md` write the review file while the typed operand reads `$D/y.md`, and each was allowed (rc 0). A word the walk cannot know stays unknown in the expanded form, so the typed form is still read beside it.
        variants = [(argv, "")]
        if run.xargv is not None and run.xargv != argv:
            variants.append((list(run.xargv), ""))
        # Each word the walk could not expand, read by where its value can come from (#b53f586d): `for D in agent/reviews/x; do tee $D/y.md; done` tees the review file.
        variants += [
            (words, "" if definite else _UNKNOWN_NOTE % shlex.join(words))
            for words, definite in _argv_readings(run, argv, cmd)
        ]
        for words, note in variants:
            what = _operand_write(run, name, list(words), where, base, cwd)
            if what:
                return what + note
        # EVERY OTHER COMMAND IS READ BY `shellscan.output_landings` (worklist item ff3ab826): a command its table lists writes only through its own output spellings (`sort -o`, `git diff --output=`, `find -fprint`, `sed 'w ...'`, `uniq IN OUT`), and one it does not list is read as writing any word it names, since `curl -o`, `tar -cf`, `pandoc -o`, `touch` and `prettier --write` each spell
        # the write their own way. Each was allowed before (rc 0). The words are read twice, as typed and as bash expands them (`F=<review file>; sort -o $F`).
        for words, note in variants:
            for word, how in shellscan.output_landings(run, _without_ref_operands(run, words), cwd):
                if not _is_review(word, where, base):
                    continue
                if how == "option":
                    return "%s writing %s through its own output option%s" % (name, word, note)
                return (
                    "%s naming %s, and %s is not a command this guard reads as a reader; "
                    "read a review file with cat, grep, head, sed -n, jq or git show, and call "
                    "a command itself rather than through a shell function%s"
                ) % (name, word, name, note)
        # A script run DIRECTLY by its shebang is the interpreter it names (review 05c4df4d.2): no interpreter word stands in the command.
        shebang = shellscan.shebang_interpreter(run, cwd)
        if shebang and shebang.startswith(INTERPRETERS) and not name.startswith(INTERPRETERS):
            name = shebang
        if name.startswith(INTERPRETERS):
            # The program is `shellscan.interpreter_program`'s reading (#c4542b69): the `-c` value, the heredocs only when it reads its program from stdin (a `cat > x.py <<EOF` earlier in the line is a file being written, not code being run), or a script passed BY PATH, which was not read at all before (rc 0 against rc 2 for the same program as a heredoc).
            text, kind = shellscan.interpreter_program(run, cmd, cwd)
            # A program this hook cannot read (review b922f15c.1, .4) is refused rather than run unread; the pre-filter already matched.
            if kind == "unjudgeable":
                return "%s code this hook cannot read (%s)" % (name, shellscan.UNJUDGEABLE_REASON)
            code = " ".join(argv)
            if kind in ("stdin", "file"):
                code += "\n" + text
            # A PROGRAM RUN INSIDE THE REVIEW DIRECTORY writes there by any relative path (#816a7c93, as block_user_only_command_shell_write reads a command directory): `cd agent/reviews/b && python3 -c "open('a.md','w')"` named no review path in its code and was allowed (rc 0), through a link or not. Any write in its code is refused there.
            if _lands_in_reviews(".", base) and WRITE_CODE.search(code):
                return "%s code that writes inside the review directory" % name
            program = text if kind is not None and re.match(r"^python[0-9.]*$", name) else None
            if _code_writes_through_disk(code, base, program):
                return "%s code that writes through a link into the review directory" % name
            verdict = _python_writes_review(program, depth) if program is not None else None
            if verdict is None:
                verdict = _code_writes_review(code, depth)
            if verdict:
                return "%s code that writes into the review directory" % name
    return ""


def _code_writes_review(code, depth=0):
    """Interpreter code that writes a review path: a write on a line naming the directory, or through a name bound to such a path, or a shell command on a line that hands one to a shell.

    LINE-SCOPED, measured on its first live run: a python heredoc that patched an unrelated module, whose replacement text merely MENTIONED the directory in a comment, was refused when any write anywhere plus any mention anywhere was enough. A write and a path LITERAL (a quote followed by path characters, not prose) have to meet on one line, or through a variable assigned from such a literal.
    A SHELL CALL IS A THIRD WAY (e30f1ad1.2): on a line that hands a string to a shell (`system(...)`, `execSync(...)`, backticks), each string literal is read as a command by `_offending`, so `system("echo x > agent/reviews/a.md")` is the redirect it spells, while a literal that only names the directory is a command that writes nothing.
    """
    if REVIEW_TEXT not in code:
        return False
    for line in code.splitlines():
        if REVIEW_TEXT in line and SHELL_CALL.search(line):
            for m in _LITERAL.finditer(line):
                text = next(g for g in m.groups() if g is not None)
                if REVIEW_TEXT in text and _offending(text, depth + 1):
                    return True
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


# PYTHON IS JUDGED BY ITS WRITE TARGETS (2026-10-09). The line-scoped reading below refused a heredoc that wrote only a scratchpad file, because a review path TEMPLATE flowed into the written content (`s = s.replace(..., 'agent/reviews/feat/%02d.md')` then `p.write_text(s)`): the name `s` was bound to a review literal, and a write named it. The content of a write is not where it lands.
# So a Python program that parses is read with `ast`: each write call's TARGET expression (the path `open` opens for writing, the receiver of `write_text`/`write_bytes`/`unlink`/`touch`, the destination of `os.replace`/`os.rename`/`shutil.copy*`/`shutil.move`, the path `os.remove` deletes) is refused when it holds a review path string or a name bound to one, transitively. Strings anywhere else are data. Node, perl, ruby and Python that does not parse keep the line-scoped regex.
_URL = re.compile(r"\A[A-Za-z][A-Za-z0-9+.-]*://")


def _is_review_string(value):
    return (
        isinstance(value, str) and not _URL.match(value) and REVIEW_WORD.search(value) is not None
    )


# Calls that hand a command to a shell or start a program (e30f1ad1.2), by qualified name: the first argument (or `args=`/`cmd=`) is the command, a string for a shell and a list for an argv.
_SHELL_CALLS = frozenset(
    (
        "os.system",
        "os.popen",
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.getoutput",
        "subprocess.getstatusoutput",
    )
)
# Text standing in for a piece of a command the ast cannot spell: a name bound to a review path renders as one, anything else as an unknown path segment.
# The unknown ends in `/` so text glued after it still starts a segment: `f"{root}agent/reviews/a.md"` renders `_/agent/reviews/a.md`, which REVIEW_WORD matches. A bare `_` made it `_agent/reviews/a.md`, which it did not (review 071b7987.1).
_UNKNOWN = "_/"
_UNKNOWN_REVIEW = "agent/reviews/_"
# A printf-style conversion in a `%` template: `%s`, `%-10r`, `%(name)s`, `%%` (a literal percent).
_PERCENT_SPEC = re.compile(r"%(\([^)]*\))?[-#0 +]*(\*|\d+)?(\.(\*|\d+))?[a-zA-Z%]")
# A replacement field in a `str.format` template: `{}`, `{0}`, `{name!r:>10}`; `{{`/`}}` are literal braces.
_FORMAT_FIELD = re.compile(r"\{\{|\}\}|\{[^{}]*\}")
_PATH_CTORS = frozenset(("Path", "PurePath", "PosixPath", "PurePosixPath"))


def _is_path_join(func):
    """`os.path.join` or `posixpath.join`, spelled as the call names it."""
    if not (isinstance(func, ast.Attribute) and func.attr == "join"):
        return False
    owner = func.value
    if isinstance(owner, ast.Name):
        return owner.id == "posixpath"
    return (
        isinstance(owner, ast.Attribute)
        and owner.attr == "path"
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "os"
    )


def _is_path_ctor(func):
    """`Path(...)` and its siblings, bare or as `pathlib.Path`."""
    if isinstance(func, ast.Name):
        return func.id in _PATH_CTORS
    return isinstance(func, ast.Attribute) and func.attr in _PATH_CTORS


def _str_dict(node, sub):
    """`{key: rendered value}` for a dict literal's constant string keys; {} for anything else."""
    if not isinstance(node, ast.Dict):
        return {}
    return {
        k.value: sub(v)
        for k, v in zip(node.keys, node.values, strict=True)
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }


def _render(expr, bound, review_names, seen=frozenset()):
    """The text a string expression evaluates to, as near as the ast spells it: constants, f-strings, `+`, `%` and `str.format`, `os.path.join`, `Path(...)` and `/`, and names bound once to such an expression."""

    def sub(node):
        return _render(node, bound, review_names, seen)

    if isinstance(expr, ast.Constant):
        return expr.value if isinstance(expr.value, str) else str(expr.value)
    if isinstance(expr, ast.JoinedStr):
        return "".join(sub(v) for v in expr.values)
    if isinstance(expr, ast.FormattedValue):
        return sub(expr.value)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        return sub(expr.left) + sub(expr.right)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        return sub(expr.left).rstrip("/") + "/" + sub(expr.right)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Mod):
        # Each conversion takes the next argument, after one more for each `*` width or precision; `%(key)s` takes the mapping's value; `%%` stays a percent (review 071b7987.1 sibling, 6dcf79c7.2).
        mapping = _str_dict(expr.right, sub)
        args = iter(
            [sub(e) for e in expr.right.elts]
            if isinstance(expr.right, ast.Tuple)
            else [sub(expr.right)]
        )

        def conversion(m):
            if m.group(0) == "%%":
                return "%"
            if m.group(1):
                return mapping.get(m.group(1)[1:-1], _UNKNOWN)
            for _star in range(m.group(0).count("*")):
                next(args, None)
            return next(args, _UNKNOWN)

        return _PERCENT_SPEC.sub(conversion, sub(expr.left))
    if isinstance(expr, ast.Call):
        func = expr.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("format", "format_map")
            and isinstance(func.value, ast.Constant)
            and isinstance(func.value.value, str)
        ):
            # A field names a positional by number or by order, or a keyword; `format_map` reads a dict (review 6dcf79c7.1). Attribute, index, conversion and spec (`{p.x}`, `{p[0]}`, `{p!r}`, `{p:>9}`) render the named value itself.
            if func.attr == "format":
                positional = [sub(a) for a in expr.args]
                named = {k.arg: sub(k.value) for k in expr.keywords if k.arg is not None}
            else:
                positional = []
                named = _str_dict(expr.args[0], sub) if expr.args else {}
            # Unbounded: a template may hold more auto-numbered fields than the call spells positionals (`'{} {} {}'.format(*row)`), and each extra one is an unknown value, never a StopIteration out of `re.sub` (review c093f0f3.1).
            order = itertools.count()

            def field(m):
                if m.group(0) in ("{{", "}}"):
                    return m.group(0)[0]
                key = re.split(r"[.\[!:]", m.group(0)[1:-1], maxsplit=1)[0]
                if key == "" or key.isdigit():
                    at = next(order) if key == "" else int(key)
                    return positional[at] if at < len(positional) else _UNKNOWN
                return named.get(key, _UNKNOWN)

            return _FORMAT_FIELD.sub(field, func.value.value)
        if _is_path_join(func) or _is_path_ctor(func):
            return "/".join(sub(a).rstrip("/") for a in expr.args) if expr.args else _UNKNOWN
        if isinstance(func, ast.Name) and func.id in ("str", "fspath") and len(expr.args) == 1:
            return sub(expr.args[0])
        if isinstance(func, ast.Attribute) and func.attr == "fspath" and len(expr.args) == 1:
            return sub(expr.args[0])
    if isinstance(expr, ast.Name):
        values = bound.get(expr.id, [])
        if len(values) == 1 and expr.id not in seen:
            return _render(values[0], bound, review_names, seen | {expr.id})
        return _UNKNOWN_REVIEW if expr.id in review_names else _UNKNOWN
    return _UNKNOWN


def _shell_commands(tree, imports, bound, review_names):
    """Every command a Python tree hands to a shell or starts, rendered as one shell line."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if shellscan.python_qualified(node.func, imports) not in _SHELL_CALLS:
            continue
        arg = (
            node.args[0]
            if node.args
            else shellscan.python_keyword(node, "args") or shellscan.python_keyword(node, "cmd")
        )
        if arg is None:
            continue
        if isinstance(arg, (ast.List, ast.Tuple)):
            yield shlex.join(_render(e, bound, review_names) for e in arg.elts)
        else:
            yield _render(arg, bound, review_names)


def _python_writes_review(program, depth=0):
    """True or False for a Python program that parses, by its write targets and the shell commands it runs; None when it does not parse, so the regex reading answers instead.

    THE SHELL COMMANDS ARE ADDITIVE (e30f1ad1.2): a program whose only write is `os.system('echo x > agent/reviews/a.md')` names no write target, so each command it hands to a shell is rendered and judged by `_offending` as the shell line it is. A review path in written CONTENT is still data: only a string that reaches a shell is read as a command.
    """
    if REVIEW_TEXT.rstrip("/") not in program:
        return False
    try:
        tree = ast.parse(program)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    bound = shellscan.python_bindings(tree)
    review_names = shellscan.python_matching_names(bound, _is_review_string)

    def holds_review(expr):
        return shellscan.python_holds(expr, _is_review_string, review_names)

    imports = shellscan.python_imports(tree)
    if any(holds_review(t) for t in shellscan.python_write_targets(tree, imports)):
        return True
    return any(
        REVIEW_TEXT.rstrip("/") in c and _offending(c, depth + 1)
        for c in _shell_commands(tree, imports, bound, review_names)
    )


def _programs_name_reviews(cmd, cwd):
    """The pre-filter's program question: does a script `cmd` runs by path name `reviews` in its text (#c4542b69), or does a program it runs have text this hook cannot read whose sources may (#b53f586d)?

    AN UNJUDGEABLE PROGRAM IS JUDGED BY WHAT IT CAN BE MADE FROM. `mkdir -p "$(echo n)" && cp rv.py n && python3 n/rv.py` runs `rv.py`, which writes a review file, while the walk cannot say where the copy landed: the line names no review word, so the pre-filter allowed it (rc 0), and the same line with one was refused. Refusing every such program instead turns the planting loop this repository runs (`sed -i ... x.py && python3 x.py`: 522 of 158,263 distinct Bash commands in this repository's session transcripts on 2026-10-15 run an unjudgeable program, 518 of them naming no review word) into review-record refusals.
    So the program is read through its possible sources: every file a word of the line names (each run's words, as typed and as expanded, joined to the run's directory), and the command goes to the full check, which refuses the program as unjudgeable, when one of those files is larger than a script read or holds code the full check reads as a write into the review directory (`_source_writes_review`), or when `curl`/`wget` fetches a URL or an archive is extracted, whose content no file on disk holds as code.
    Testing a source for the bare word `reviews` instead sent 55 of those 518 to the refusal, on scripts that only mention the directory; the code reading sends 1, and changes the verdict on none of the 158,263. A program generated by a command whose own files never write there (`python3 gen.py > n.py` where `gen.py` imports what does), and one downloaded by a tool other than curl or wget, are the residue this reading cannot see.
    """
    if not shellscan.PROGRAM_PREFILTER.search(cmd):
        return False
    runs = list(shellscan.every_run(cmd))
    unjudgeable = False
    for run in runs:
        text, kind = shellscan.interpreter_program(run, cmd, cwd)
        if kind == "file" and "reviews" in (text or ""):
            return True
        unjudgeable = unjudgeable or kind == "unjudgeable"
    if not unjudgeable:
        return False
    for run in runs:
        words = {*run.argv, *(run.xargv or ())}
        if run.name.rsplit("/", 1)[-1] in _FETCHERS and any("://" in w for w in words):
            return True
        # An archive extraction writes files whose text no file on disk holds as code either (#63109cf2): `tar -xf x.tar && python3 a.py`.
        if shellscan._tool_outputs(run)[1]:
            return True
        base = _base(shellscan.write_directory(run.cwd, cwd), cwd)
        for word in words:
            if base is None or not word or len(word) > _PATH_MAX or "\0" in word or "\n" in word:
                continue
            if _source_writes_review(os.path.join(base, word)):
                return True
    return False


# Commands whose output is a download: a program written from one has no source on disk to read.
_FETCHERS = frozenset(("curl", "wget"))


def _source_writes_review(path):
    """True when the file at `path` is larger than a script read, or holds code the full check reads as a write into the review directory (`_python_writes_review`, else the line-scoped `_code_writes_review`): a source an unjudgeable program may be made from."""
    try:
        if not os.path.isfile(path):
            return False
        if os.path.getsize(path) > shellscan._SCRIPT_MAX:
            return True
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except (OSError, ValueError):
        return False
    if REVIEW_TEXT.rstrip("/") not in text:
        return False
    verdict = _python_writes_review(text)
    return bool(_code_writes_review(text) if verdict is None else verdict)


def run(ev):
    cmd = ev.field("tool_input", "command")
    try:
        cwd = ev.default(("cwd",), str(hookio.repo_root()))
    except RuntimeError:
        cwd = ev.cwd
    # A script run by path names the directory in its own text, not the command's (#c4542b69), so the pre-filter reads those scripts too; the lexer starts only when an interpreter is named. A glob or brace can spell the directory without the word (`echo revi*s/... | xargs cp ...` under `cd agent`, #7094b75e), so a command with a word the full check would read as one is read too (`_globs_reviews`).
    # A LINK SPELLS THE DIRECTORY WITHOUT THE WORD (#816a7c93): with `lnk` a link into `agent/reviews`, `cd lnk && tee x.md` names neither, so a command the text test passes is read once more against the disk, and only one whose directories and words stay outside the review directory takes the cheap path.
    if (
        "reviews" not in cmd
        and not _globs_reviews(cmd, cwd)
        and not _programs_name_reviews(cmd, cwd)
        and not _reaches_reviews(cmd, cwd)
    ):
        return hookio.ALLOW
    what = _offending(cmd, cwd=cwd)
    if not what:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % what)
    return hookio.DENY
