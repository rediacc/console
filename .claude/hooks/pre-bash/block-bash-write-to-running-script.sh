#!/usr/bin/env bash
# The Bash half of block-edit-of-running-script.
#
# WHY A SECOND FILE. The pre-EDIT guard only sees the Edit/Write tools. Within
# an hour of shipping it I walked into the same trap through Bash instead --
# a `python3 - <<PY ... p.write_text(...) PY` rewriting test-hooks.sh while FOUR
# copies of it were executing. The guard did not fire because it never saw the
# call. A guard that covers one of two doors is a guard you will walk around
# without noticing, which is exactly what happened.
#
# THE MECHANISM, since the error never points at it: bash reads a script LAZILY,
# by byte offset. Rewrite it mid-run and the interpreter resumes at its old
# offset inside the new bytes and starts parsing mid-token. It dies naming an
# INNOCENT line while `bash -n` on that same file stays clean. Documented at
# docs/agent-reference/TRAPS.md, and hit three times on 2026-08-26/27.
#
#
# HOOK-CHAIN SIBLINGS ARE NOT A RUNNING JOB, and excluding them is not a
# loophole -- it is the difference between this guard working and this guard
# making a whole directory uneditable. Every pre-bash guard executes on EVERY
# Bash call, including the one carrying your edit. So while you edit
# block-binary-deploy.sh, that guard is running, as a sibling in the chain
# evaluating that very edit. This fired on exactly that on 2026-08-27, and the
# block is PERMANENT: there is no moment when a pre-bash guard is not running
# during a Bash call, so no amount of waiting clears it. It cost four blocked
# commands before the cause was visible, one of them the fix itself.
#
# The exclusion costs close to nothing. A chain evaluator lives for
# milliseconds and is re-read from scratch on the next call, so the lazy-read
# corruption below needs a window that does not exist here. What this guard is
# actually for -- a suite, a build, a background job running for minutes -- is
# untouched, test-hooks.sh included: that runs from the hooks ROOT, not a chain
# directory, so it still matches and still blocks.
#
# WRITE INTENT IS REQUIRED, not merely the filename. Every second command in
# this repo mentions a .sh path -- running it, grepping it, checking its
# processes. Blocking on the name alone would be the over-matching that gets a
# guard switched off, so this needs a write operator AND a live process.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# A write indicator: a redirect, an in-place edit, a copy/move onto it, or a
# python/perl write. Reading, running and grepping are none of these.
# The write-detector. It recognised `write_text` -- the exact idiom in the header
# comment above -- but NOT `open(path, "w").write(...)`, which is the commoner one,
# so the door this guard exists to close was open for that spelling. Verified
# 2026-08-27: the header's own example was caught and its sibling was not.
printf '%s' "$CMD" | grep -qE '>[[:space:]]*[^|&;[:space:]]*\.sh|sed[[:space:]]+-i|tee[[:space:]]|write_text|write_bytes|writelines|\.write\(|open\([^)]*["'"'"']]?[wa]|shutil\.(copy|move)|truncate|\bcp[[:space:]]|\bmv[[:space:]]|\bshfmt[[:space:]]+-w|>>[[:space:]]*[^|&;[:space:]]*\.sh' || exit 0

# Which .sh files does this command name at all?
#
# `$` IS IN THE CHARACTER CLASS so a variable expansion is RECOGNISED and then
# skipped. Without it, `"$SP/mp-$ver.sh"` yielded the candidate `ver.sh` -- the
# tail of a variable name plus the suffix, a filename that appears nowhere. The
# guard cannot know what `$ver` expands to, so it must not guess.
# Only .sh paths that are actually the TARGET of a write. Collecting every .sh
# token anywhere in the command blocked a heredoc that merely MENTIONED a running
# script while writing a different file -- and a false block on a safety guard is
# how a guard gets worked around, which costs more than the block saved.
TARGETS=$(printf '%s' "$CMD" |
    grep -oE '>>?[[:space:]]*[^|&;[:space:]]+\.sh|tee[[:space:]]+(-[a-z]+[[:space:]]+)*[^|&;[:space:]]+\.sh|sed[[:space:]]+-i[^|&;]*[[:space:]][^|&;[:space:]]+\.sh|shfmt[[:space:]]+-w[^|&;]*[[:space:]][^|&;[:space:]]+\.sh|\b(cp|mv)[[:space:]]+[^|&;]*[[:space:]][^|&;[:space:]]+\.sh' |
    grep -oE '[A-Za-z0-9_.$/-]+\.sh' | sort -u)
# A python/perl heredoc can name its target in ways no redirect grep will see, so
# fall back to the old broad scan whenever the command opens one. Broad and noisy
# beats silent here: this is the door the pre-edit guard cannot cover.
if printf '%s' "$CMD" | grep -qE 'write_text|open\(|<<[[:space:]]*.?(PY|EOPY|PYTHON)'; then
    # PRECISE FIRST, BROAD ONLY IF THAT FINDS NOTHING.
    #
    # The old line took EVERY .sh token in the command. That is correct for a
    # python heredoc naming its target, and badly wrong for one whose payload
    # merely MENTIONS a script -- which is what documentation, a hook message,
    # or a commit body routinely does. Measured 2026-08-27: patching this very
    # guard's sibling was refused twice because the replacement TEXT contained
    # `./run.sh devbox remove` while a peer ran that script. No interpreter was
    # executing the file being written, and the same false-positive class is
    # already recorded twice in this file's own comments.
    #
    # A python write target appears in a target POSITION: assigned to a name, or
    # passed to open()/Path(). A mention inside prose does not.
    #
    # ASK "COULD I IDENTIFY THE TARGET AT ALL", not "did I find a .sh".
    # The first cut of this asked the second question and fell back to the broad
    # scan whenever no .sh sat in a target position -- which is precisely the
    # shape of the false positive (real target a .py, payload mentioning a
    # script), so the narrowing changed nothing. Control 1 caught it.
    # Targets come from TWO places, and looking in only one of them was the bug.
    # A `cat > notes.txt <<'PY'`-shaped command names its target in the REDIRECT;
    # the earlier cut only harvested redirect targets ending in .sh, so a
    # redirect to any other extension contributed nothing and the command read as
    # "target unidentifiable" while its target sat in plain sight. Measured
    # 2026-08-27: writing two commit-message files was refused because their TEXT
    # discussed write_text and named a running script.
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
    # embedded-bash-as-data shape. `open(`/`Path(` are untouched -- neither of
    # those idioms exists as bash syntax, so they carry no equivalent ambiguity.
    ANYTARGET=$(
        {
            printf '%s' "$CMD" |
                grep -oE '([[:space:]]=[[:space:]]|open\(|Path\()[[:space:]]*["'"'"'][^"'"'"']+\.[A-Za-z0-9]+' |
                grep -oE '[A-Za-z0-9_.$/-]+\.[A-Za-z0-9]+$'
            printf '%s' "$CMD" |
                grep -oE '>>?[[:space:]]*"?[^|&;<[:space:]"]+\.[A-Za-z0-9]+' |
                grep -oE '[A-Za-z0-9_.$/-]+\.[A-Za-z0-9]+$'
        } | sort -u
    )
    PRECISE=$(printf '%s\n' "$ANYTARGET" | grep -E '\.sh$' | sort -u)
    if [ -n "$ANYTARGET" ]; then
        # Targets were identifiable. If none is a shell script, this command
        # writes none, however many it happens to NAME in its payload.
        [ -n "$PRECISE" ] && TARGETS=$(printf '%s\n%s' "$TARGETS" "$PRECISE" | sort -u)
    else
        # Nothing looked like a target, so keep the old broad-and-noisy scan
        # rather than going silent: a missed corruption costs more than a
        # false positive, which is why the broad form was chosen originally.
        TARGETS=$(printf '%s\n%s' "$TARGETS" "$(printf '%s' "$CMD" | grep -oE '[A-Za-z0-9_.$/-]+\.sh')" | sort -u)
    fi
fi
for cand in $TARGETS; do
    case "$cand" in
        *'$'*) continue ;;
    esac
    base=$(basename "$cand")
    # BRACKET THE FIRST CHARACTER so this pgrep cannot match the shell running
    # this hook, whose command line carries the path it was handed. That is the
    # self-matching trap block-self-matching-pgrep exists for, and this is
    # exactly where it would bite again.
    # ANCHOR TO A PATH BOUNDARY. `pgrep -f` matches anywhere in a command line,
    # so a bare basename matches any process whose command line merely CONTAINS
    # it as a substring: `ver.sh` matched a running `wslServer.sh`, and the
    # guard reported VS Code's server as the job about to be corrupted. The
    # basename must start at the beginning, after a `/`, or after whitespace.
    pat="(^|[/[:space:]])[${base:0:1}]${base:1}"
    # `pgrep -af` matches any process whose ARGUMENTS mention the name, which is the
    # very trap this guard exists to prevent, wearing a different hat. Measured
    # 2026-08-27: an edit to the hook suite was refused because a PEER session's
    # `claude -p` carried a long prompt that happened to contain that filename. No
    # interpreter was executing the script at all, and the refusal was unarguable.
    #
    # A process is RUNNING the script only if an interpreter is executing it. So require
    # the matching process to BE a shell, and the name to sit in the first few argv slots
    # where a script argument lives, rather than buried in a prose payload.
    running=""
    for rpid in $(pgrep -f -- "$pat" 2>/dev/null); do
        case "$(ps -o comm= -p "$rpid" 2>/dev/null)" in
            bash | sh | dash | zsh | ksh) ;;
            *) continue ;;
        esac
        rargs=$(tr '\0' ' ' <"/proc/$rpid/cmdline" 2>/dev/null)
        printf '%s' "$rargs" | cut -d' ' -f1-4 | grep -qE -- "$pat" || continue
        printf '%s' "$rargs" | grep -qE '\.claude/hooks/(pre-bash|pre-edit|pre-ask|post-bash)/' && continue
        running="$running$rpid $(printf '%s' "$rargs" | cut -c1-80)
"
    done
    running=$(printf '%s' "$running" | head -2)
    [ -z "$running" ] && continue
    cat >&2 <<MSG
BLOCKED: '${base}' is being executed right now, and this command writes to it.

  $(printf '%s\n' "$running" | sed 's/^/    /')

Bash reads a script LAZILY, by byte offset. Editing it now makes the running
interpreter resume at its old offset inside your new bytes, so it parses
mid-token and dies at an INNOCENT line -- while \`bash -n\` on the file stays
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
MSG
    exit 2
done
exit 0
