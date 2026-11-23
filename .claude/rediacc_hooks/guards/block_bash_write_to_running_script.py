"""The Bash half of block-edit-of-running-script.

WHY A SECOND FILE. The pre-EDIT guard only sees the Edit/Write tools. Within an hour of shipping it I walked into the same trap through Bash instead -- a `python3 - <<PY ... p.write_text(...) PY` rewriting test-hooks.sh while FOUR copies of it were executing. The guard did not fire because it never saw the call. A guard that covers one of two doors is a guard you will walk around
without noticing, which is exactly what happened.

THE MECHANISM, since the error never points at it: bash reads a script LAZILY, by byte offset. Rewrite it mid-run and the interpreter resumes at its old offset inside the new bytes and starts parsing mid-token. It dies naming an INNOCENT line while `bash -n` on that same file stays clean. Documented at docs/agent-reference/TRAPS.md, and hit three times on 2026-08-26/27.

HOOK-CHAIN SIBLINGS ARE NOT A RUNNING JOB, and excluding them is not a loophole -- it is the difference between this guard working and this guard making a whole directory uneditable. Every pre-bash guard executes on EVERY Bash call, including the one carrying your edit. So while you edit block-binary-deploy.sh, that guard is running, as a sibling in the chain evaluating that very
edit. This fired on exactly that on 2026-08-27, and the block is PERMANENT: there is no moment when a pre-bash guard is not running during a Bash call, so no amount of waiting clears it. It cost four blocked commands before the cause was visible, one of them the fix itself.

The exclusion costs close to nothing. A chain evaluator lives for milliseconds and is re-read from scratch on the next call, so the lazy-read corruption below needs a window that does not exist here. What this guard is actually for -- a suite, a build, a background job running for minutes -- is untouched, test-hooks.sh included: that runs from the hooks ROOT, not a chain directory,
so it still matches and still blocks.

WRITE INTENT IS REQUIRED, not merely the filename. Every second command in this repo mentions a .sh path -- running it, grepping it, checking its processes. Blocking on the name alone would be the over-matching that gets a guard switched off, so this needs a write operator AND a live process.

A WRITE IS SOMETHING THAT RUNS, NOT TEXT THAT SPELLS ONE (worklist #0c331972). The write patterns below were matched over the RAW command, so `echo 'echo x > <running>.sh'` -- a sentence quoting a redirect -- was refused as a write. The guard now asks the shell's own walk: the redirects bash performs (`shellscan.write_targets`), the write verbs it runs (`tee`, `sed -i`, `cp`/`mv` onto a destination, `shfmt -w`, `truncate`, `dd of=`, each read off its argv by `_verb_targets`, behind `sudo`, `xargs`, `sh -c` or `find -exec`), and the program texts it hands an interpreter (`block_worktree_add.interpreter_programs`: `python3 -c`, `python3 - <<PY`, `node -e`, `perl -e`, a here-string or a piped `cat`). Only a program text is still read with the patterns, because a python write names its target in ways no shell walk sees. An `echo` or a commit message quoting any of it is data and passes.

`pattern_for` AND THE PGREP LOOP NOW LIVE IN `rediacc_hooks.runningscript`, shared with the Edit-tool sibling (PLAN-retire-bash-oracles A3: "unifying is a P6 change, once there is no twin left to diverge from" -- this is that change). Until then each guard carried its own copy of the same twenty lines, because the two BASH originals duplicated them too and a port whose job was fidelity
did not get to unify what its twin kept apart; that duplication is exactly what produced the sibling drift their comments recorded (the path anchor reached the Edit-side guard on 2026-08-30, three days after this one got it on 2026-08-27).

PORT NOTE ON `for cand in $TARGETS`. That is an UNQUOTED expansion, so bash splits on IFS -- dropping empty fields, which is why an empty first line from `printf '%s\\n%s'` costs nothing -- and then GLOBS each word against the filesystem. The globbing has never mattered here (a `.sh` path holding a `*` or a `?` would already have been skipped by the `$` test or failed to match a
process) and is not reproduced; the splitting is, because the empty-field case happens on every command that reaches the fallback with no redirect targets.

PORT NOTE ON `sort -u`. Under `LC_ALL=C` sort orders by BYTE, so the key below
is the UTF-8 encoding rather than Python's default codepoint comparison. The two agree on every ASCII path and can differ on anything else, and the order is observable: it decides which of several targets is reported first.
"""

from rediacc_hooks import hookio, runningscript, shellscan
from rediacc_hooks.guards import block_worktree_add as WT
from rediacc_hooks.guards import tables

__getattr__ = tables(
    "block_bash_write_to_running_script",
    "EDGE_CASES",
    "ENVS",
    "FIXTURES",
    "IDLE_SCRIPT",
    "LIVE_SCRIPT",
    "SIBLING_SCRIPT",
    "WORLD",
    "_BODY",
    "_CHILDREN",
    "_LOCK_FDS",
    "_PY",
    "_await_visible",
    "_bashwrite_world",
    "_hold_world_lock",
    "_kill_stale",
    "_reap",
    "_spawn",
)

CHAIN = "pre-bash"
ORDER = 15

# AN ASCII ARROW IS NOT A REDIRECT, and this is the FIFTH round of the same
# class. Since #0c331972 the patterns read only interpreter program texts, so the witness is a python program printing an arrow (EDGE_CASES); a quoted shell sentence never reaches them at all. Measured 2026-09-01: writing a plain markdown file was refused because
# its PROSE contained `check:ci-hook-worklist-suite -> .claude/hooks/stop/test-worklist-v5.sh`. The `->` scored as a redirect and the path after it as the target, so a document describing a script was treated as a command overwriting it. Widening the class back to "any character" restores that block exactly.
DEFECT = ('NOT_ARROW = r"(^|[^->])"', 'NOT_ARROW = r"(^|[^ZZ])"')

# A real redirect's `>` is preceded by whitespace, start-of-string, or a digit (`2>`). Never by `-`. Requiring that keeps every true positive and drops the arrow. One constant, used by BOTH the intent test and the target harvest, because the two disagreeing about what a redirect is was how the class kept coming back.
#
# RULE T DECISION (PLAN-retire-bash-oracles A4, A0 L14), 2026-09-24: THE ARROW RULE STAYS FOR THE RAW-TEXT PATTERNS, AND IS NO LONGER THE WHOLE ANSWER. The premise above is false for bash: an UNQUOTED `x->f.sh` is the word `x-` followed by a real `>` opening `f.sh` (`echo x->/dev/null` prints nothing). What made the arrow worth excluding was prose, and prose that names an arrow is QUOTED, which a regex over the raw command cannot tell from a real redirect. The lexer can, so `shellscan.write_targets` now supplies the redirects bash actually performs (quote-aware, so the 2026-09-01 arrow inside `echo '... -> x.sh'` is still no target) and `run` unions them with the regex harvest. `NOT_ARROW` keeps doing the one job it is still right for: stopping a quoted or heredoc'd arrow from scoring in the raw-text patterns. The same union closes `>|`, which truncates even under noclobber and which `_NOT_SEP`'s `|` exclusion made invisible to every pattern here.
NOT_ARROW = r"(^|[^->])"

_S = hookio.SPACE
_NOT_SEP = r"[^|&;" + _S + r"]"

# A write indicator: a redirect, an in-place edit, a copy/move onto it, or a python/perl write. Reading, running and grepping are none of these. The write-detector. It recognised `write_text` -- the exact idiom in the header comment above -- but NOT `open(path, "w").write(...)`, which is the commoner one, so the door this guard exists to close was open for that spelling. Verified
# 2026-08-27: the header's own example was caught and its sibling was not.
WRITE_INTENT = (
    NOT_ARROW
    + r">>?["
    + _S
    + r"]*"
    + _NOT_SEP
    + r"*\.sh|sed["
    + _S
    + r"]+-i|tee["
    + _S
    + r"]|write_text|write_bytes|writelines|\.write\(|open\([^)]*[\"']]?[wa]"
    r"|shutil\.(copy|move)|truncate|\bcp[" + _S + r"]|\bmv[" + _S + r"]|\bshfmt[" + _S + r"]+-w"
)

# Only .sh paths that are actually the TARGET of a write. Collecting every .sh token anywhere in the command blocked a heredoc that merely MENTIONED a running script while writing a different file -- and a false block on a safety guard is how a guard gets worked around, which costs more than the block saved.
TARGET_SPAN = (
    NOT_ARROW
    + r">>?["
    + _S
    + r"]*"
    + _NOT_SEP
    + r"+\.sh|tee["
    + _S
    + r"]+(-[a-z]+["
    + _S
    + r"]+)*"
    + _NOT_SEP
    + r"+\.sh|sed["
    + _S
    + r"]+-i[^|&;]*["
    + _S
    + r"]"
    + _NOT_SEP
    + r"+\.sh|shfmt["
    + _S
    + r"]+-w[^|&;]*["
    + _S
    + r"]"
    + _NOT_SEP
    + r"+\.sh|\b(cp|mv)["
    + _S
    + r"]+[^|&;]*["
    + _S
    + r"]"
    + _NOT_SEP
    + r"+\.sh"
)

# `$` IS IN THE CHARACTER CLASS so a variable expansion is RECOGNISED and then skipped. Without it, `"$SP/mp-$ver.sh"` yielded the candidate `ver.sh` -- the tail of a variable name plus the suffix, a filename that appears nowhere. The guard cannot know what `$ver` expands to, so it must not guess.
SH_PATH = r"[A-Za-z0-9_.$/-]+\.sh"

# A python/perl heredoc can name its target in ways no redirect grep will see, so fall back to the old broad scan whenever the command opens one. Broad and noisy beats silent here: this is the door the pre-edit guard cannot cover.
PY_HEREDOC = r"write_text|open\(|<<[" + _S + r"]*.?(PY|EOPY|PYTHON)"

# A copy or move inside a program names its destination as a call ARGUMENT, which `ASSIGN_TARGET` does not see, so such a program takes the precise-then-broad branch too.
PY_COPY = r"shutil\.(copy|move)"

# A python write target appears in a target POSITION: assigned to a name, or passed to open()/Path(). A mention inside prose does not.
#
# THE `=` BRANCH NEEDS A SPACE BEFORE IT, and this is the third round of the
# same class. Measured 2026-08-28: a python heredoc's REPLACEMENT STRING held
# `ROUTE="./run.sh devbox exec -- $CMD"` -- valid bash SOURCE TEXT the script
# was writing INTO a hook file, never executed by the outer command -- and the
# bare `=` alternative scored it as a real python assignment because it looks
# identical in shape to one.
#
# The two are not identical in FORM, only in shape: this repo's own python is
# ruff-formatted (PEP8), so a real target assignment reads `p = 'x.sh'` with a
# space on both sides of `=`; a bash env-assignment payload being written out
# as DATA is valid bash, which forbids the space (`VAR=value`, no spaces,
# or it is a syntax error). Requiring a preceding space keeps every documented
# true positive (all authored `NAME = value` in this repo) while dropping the
# embedded-bash-as-data shape. `open(`/`Path(` are untouched -- neither of those idioms exists as bash syntax, so they carry no equivalent ambiguity.
# NO WHITESPACE INSIDE THE QUOTED TARGET (2026-09-24, #a655c5f5): `grep -n "source\\|PATS=" a.sh; ls lib/b.sh` read the CLOSING quote after `PATS=` as an opening one, and `[^"']+` then ran across `; ls` to the next `.sh`, refusing a command that only listed a running script. A real target literal holds no whitespace.
# THE QUOTE MUST CLOSE RIGHT AFTER THE EXTENSION (2026-09-24, found by PLAN-retire-bash-oracles A4's full hook-suite run): with the whitespace ban alone, `ROUTE=".<live>.sh devbox exec"` still scored `<live>.sh` as a target, because nothing required the quoted span to END there, and the round-3 control in test_hooks_procs.py ("a bash-shaped assignment MENTION inside replacement text") went red at 0868e3a53. A real target literal is the WHOLE quoted string, so a lookahead now demands its closing quote.
# `p = "x.txt"` AND `p="x.txt"`: the spaced form alone missed the compact assignment every short heredoc uses, so its target read as unidentifiable and the broad scan blocked a payload that only MENTIONED a running script (./rdc.sh, 2026-09-24). The leading `[^=!<>]` keeps `==`, `!=`, `<=`, `>=` out, and it stays plain ERE so the bash oracle can carry the identical pattern.
ASSIGN_TARGET = (
    r"([^=!<>"
    + _S
    + r"]["
    + _S
    + r"]*=["
    + _S
    + r"]*|open\(|Path\()["
    + _S
    + r"]*[\"'][^\"'"
    + _S
    + r"]+\.[A-Za-z0-9]+(?=[\"'])"
)

# Targets come from TWO places, and looking in only one of them was the bug.
# A `cat > notes.txt <<'PY'`-shaped command names its target in the REDIRECT;
# the earlier cut only harvested redirect targets ending in .sh, so a redirect to any other extension contributed nothing and the command read as "target unidentifiable" while its target sat in plain sight. Measured 2026-08-27: writing two commit-message files was refused because their TEXT discussed write_text and named a running script.
REDIR_TARGET = NOT_ARROW + r">>?[" + _S + r']*"?[^|&;<' + _S + r'"]+\.[A-Za-z0-9]+'

ANY_TAIL = r"[A-Za-z0-9_.$/-]+\.[A-Za-z0-9]+$"

MESSAGE = """BLOCKED: '%(base)s' is being executed right now, and this command writes to it.

  %(running)s

Bash reads a script LAZILY, by byte offset. Editing it now makes the running
interpreter resume at its old offset inside your new bytes, so it parses
mid-token and dies at an INNOCENT line -- while `bash -n` on the file stays
clean, which is what makes the failure so expensive to chase.

This is TRAPS.md, "Editing a shell script while a background job is RUNNING it".
Hit three times on 2026-08-26/27, twice on this very file. Its Edit-tool sibling
(block-edit-of-running-script.sh) covers the other door; this one exists because
covering only that door meant walking through this one within the hour.

Pick one:
  1. Let it finish. The run you would corrupt is usually the one you are
     waiting on, so editing now costs you the result twice.
  2. Write a COPY and move it into place once the run exits.
  3. If the process is stale rather than working, stop it first.
"""


def _sort_u(lines):
    """`sort -u` under LC_ALL=C: unique, ordered by byte."""
    return sorted(set(lines), key=lambda s: s.encode("utf-8", "surrogateescape"))


def _pipe(pattern, text):
    """One `grep -oE` stage, feeding the next one grep's own output shape."""
    return hookio._grep_out(hookio.grep_o(pattern, text))


def _targets(cmd):
    """Every .sh path an interpreter program text writes to, `sort -u` order. Called only with a program `interpreter_programs` found, never with the command line itself."""
    # Which .sh files does this program name at all?
    targets = "\n".join(_sort_u(hookio.grep_o(SH_PATH, _pipe(TARGET_SPAN, cmd))))

    if not hookio.grep_q(PY_HEREDOC, cmd) and not hookio.grep_q(PY_COPY, cmd):
        return targets

    # PRECISE FIRST, BROAD ONLY IF THAT FINDS NOTHING.
    #
    # The old line took EVERY .sh token in the command. That is correct for a python heredoc naming its target, and badly wrong for one whose payload merely MENTIONS a script -- which is what documentation, a hook message, or a commit body routinely does. Measured 2026-08-27: patching this very guard's sibling was refused twice because the replacement TEXT contained `./run.sh
    # devbox remove` while a peer ran that script. No interpreter was executing the file being written, and the same false-positive class is already recorded twice in this file's own comments.
    #
    # ASK "COULD I IDENTIFY THE TARGET AT ALL", not "did I find a .sh". The first cut of this asked the second question and fell back to the broad scan whenever no .sh sat in a target position -- which is precisely the shape of the false positive (real target a .py, payload mentioning a script), so the narrowing changed nothing. Control 1 caught it.
    anytarget = "\n".join(
        _sort_u(
            hookio.grep_o(ANY_TAIL, _pipe(ASSIGN_TARGET, cmd))
            + hookio.grep_o(ANY_TAIL, _pipe(REDIR_TARGET, cmd))
        )
    )
    precise = "\n".join(_sort_u(hookio.grep_lines(r"\.sh$", hookio._printf_line(anytarget))))
    if anytarget != "":
        # Targets were identifiable. If none is a shell script, this command writes none, however many it happens to NAME in its payload.
        if precise != "":
            targets = "\n".join(_sort_u(("%s\n%s" % (targets, precise)).split("\n")))
    else:
        # Nothing looked like a target, so keep the old broad-and-noisy scan rather than going silent: a missed corruption costs more than a false positive, which is why the broad form was chosen originally.
        broad = hookio._command_substitution(_pipe(SH_PATH, cmd))
        targets = "\n".join(_sort_u(("%s\n%s" % (targets, broad)).split("\n")))
    return targets


def _operands(run_):
    """A write verb's operands: its own non-option words, then what xargs appends from its feed (`echo a.sh | xargs sed -i s/x/y/` edits `a.sh`). What a producer prints is not computed, so every fed word counts, the direction this guard fails safe in (review 0bbd6471.4)."""
    words = [a for a in run_.argv if not (a.startswith("-") and len(a) > 1)]
    if run_.feed and "xargs" in run_.via:
        words += run_.feed.split()
    return words


def _verb_targets(run_, cwd):
    """The `.sh` files one run's write verb writes: `tee`, `truncate`, `shfmt -w` and `sed -i` write their operands, `cp`/`mv` where `shellscan.copy_landings` puts the copy, `dd` its `of=`. Every arm reads the xargs feed as `_operands` does. Anything else writes nothing here."""
    base = shellscan._base(run_.name)
    args = list(run_.argv)
    if base in ("tee", "truncate"):
        found = _operands(run_)
    elif base == "shfmt":
        found = _operands(run_) if any(a in ("-w", "--write") for a in args) else []
    elif shellscan.in_place_edit(run_) is not None:
        # EVERY IN-PLACE EDITOR, by its own option parse (#6378e10e): sed, gsed and `perl -i`/`-pi` rewrite the files they name, and `perl -pi -e ... <running>.sh` was allowed while only sed was asked. The files are `in_place_edit`'s (an attached `-e` script is not a file, review 3f53e99e.2), plus what xargs appends.
        edit = shellscan.in_place_edit(run_)
        fed = run_.feed.split() if run_.feed and "xargs" in run_.via else []
        found = [*edit[1], *fed]
    elif base in ("cp", "mv"):
        found = [path for path, _into in shellscan.copy_landings(run_, cwd, ("cp", "mv"))]
    elif base == "dd":
        found = [a[3:] for a in args if a.startswith("of=")]
    else:
        found = []
    return [t for t in found if t.endswith(".sh")]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    # The redirects bash really performs onto a `.sh` (see the Rule T note at NOT_ARROW), then the write verbs it runs, then what each interpreter program writes.
    cands = [t for t in shellscan.write_targets(cmd) if t.endswith(".sh")]
    cwd = ev.field("cwd") or str(hookio.repo_root())
    for run_ in shellscan.every_run(cmd):
        cands += _verb_targets(run_, cwd)
    for _family, code in WT.interpreter_programs(cmd):
        if hookio.grep_q(WRITE_INTENT, code):
            cands += _targets(code).split()
    for cand in dict.fromkeys(cands):
        if hookio.case_glob(cand, "*$*"):
            continue
        base = cand.rsplit("/", 1)[-1]
        running = runningscript.live_shells(runningscript.pattern_for(base), 2, cand, cwd)
        if running == "":
            continue
        body = hookio._command_substitution(
            hookio.sed_sub(r"^", "    ", hookio._printf_line(running))
        )
        ev.warn_raw(MESSAGE % {"base": base, "running": body})
        return hookio.DENY
    return hookio.ALLOW
