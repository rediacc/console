#!/usr/bin/env bash
# FAIL CLOSED when python3 is missing. Registered SECOND in every PreToolUse and
# PostToolUse chain, immediately behind require-jq.sh.
#
# WHY IT IS BASH, and this is the one hook in the program that may never be
# ported. It is the check that python3 exists. Written in Python it would be
# unable to run in exactly the condition it exists to report, and a hook that
# cannot start does not error visibly -- the harness sees a failed command, not
# a diagnosis. require-jq.sh makes the same argument about itself in reverse
# ("AND IT IS PARSED WITHOUT jq, which is the whole point"), and for the same
# reason it reads the raw JSON body rather than a parsed value.
#
# THE DEFECT THIS CLOSES, which is require-jq.sh's defect one toolchain later.
# W5 ports .claude/hooks/** to Python. Once a guard is a Python module invoked
# through .claude/rediacc_hooks/dispatch.py, a machine without python3 gets
# "command not found" from the harness and the guard does not run. Whether that
# reads as ALLOW or as an error is the harness's business and not this repo's,
# and either way nothing in the session says which guards just stopped
# existing. Measured on the bash side 2026-08-26 and recorded in require-jq.sh:
# with jq absent the entire guard set silently became a no-op, and that is
# "strictly worse than having no hooks at all, because no-hooks is at least
# visible".
#
# SO THE POSITION IS PART OF THE CONTRACT, exactly as it is for require-jq.sh.
# Registered after the guards it protects, it would fire only once they had
# already been skipped. It goes SECOND rather than first because jq's absence
# breaks strictly more (every remaining bash guard parses stdin with it), and
# because .ci/scripts/quality/check_hooks_resolvable.py asserts require-jq.sh
# is `cmds[0]` of every chain -- a predicate this hook must satisfy rather than
# re-key.
#
# ---------------------------------------------------------------------------
# THE CARVE-OUT, and why it is not a hole.
#
# Copied deliberately from require-jq.sh, whose header records what happens
# without one: the first version of that guard blocked EVERY Bash call while jq
# was missing, "including `sudo apt-get install -y jq` and `./run.sh setup` --
# the two cures its own message prescribes. That is a bootstrap deadlock: it
# locked the session out of the only actions that could unlock it, and an
# operator had to run the install by hand."
#
# The security cost is ZERO. This carve-out only ever applies when python3 is
# absent, and when python3 is absent every ported guard is already inert.
# Permitting these specific remedies weakens nothing that was enforcing
# anything.
#
# THE MATCH IS DELIBERATELY TIGHT, because a loose one would be a real hole:
#   - chained payloads fail closed. `apt-get install -y python3; git push
#     --force` must NOT ride through on its prefix, so any shell metacharacter
#     that could start a second command (; && || | newline backtick $( )
#     rejects outright.
#   - `./run.sh setup` matches the SETUP SUBCOMMAND only, never `./run.sh <any>`.
#   - the package-manager arm requires a known manager, an install verb, AND a
#     python3 package in the list. `apt-get install -y curl` is not a remedy.
#
# AND IT IS PARSED WITHOUT PYTHON, which is the whole point: this code runs
# exactly when python3 does not exist, so it reads the raw JSON body rather
# than the value. That is coarser than a real parse, and it is safe here
# BECAUSE the fallback is to block: a payload this cannot understand is
# refused, not allowed.
# ---------------------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
    exit 0
fi

# BOUNDED, because `INPUT=$(cat)` is not. `cat` on a stdin that stays open and
# silent blocks forever, and this guard runs as a PreToolUse hook: a hang here
# is not a slow check, it is a tool call that never returns. Measured
# 2026-09-08 with the interpreter hidden from PATH so this arm is actually
# reached and stdin held open by a writer that never writes -- exit 124, killed
# by an external timeout, against exit 2 in 0s once stdin is closed.
#
# `read -t` RATHER THAN `timeout cat`, because this arm exists precisely when
# the environment is degraded and a bash builtin cannot itself be missing.
# `-d ''` reads to NUL, i.e. to EOF, so the normal path returns non-zero with
# INPUT set; only a status above 128 is the deadline firing.
#
# AND IT REFUSES ON TIMEOUT, matching what this file already does with a
# payload it cannot understand: the fallback here is to block, never to allow.
INPUT=""
IFS= read -r -d "" -t 10 INPUT
if [ "$?" -gt 128 ]; then
    printf 'no payload arrived on stdin within 10s; refusing rather than hanging the tool call.\n' >&2
    exit 2
fi

# Any chaining/substitution metacharacter: refuse without further thought.
case "$INPUT" in
    *';'* | *'&&'* | *'||'* | *'`'* | *'$('* | *$'\n'*) allow=no ;;
    *) allow=maybe ;;
esac

if [ "$allow" = maybe ]; then
    # Remedy 1: a package-manager install whose package list includes python3.
    # `python3` and `python3.NN` and Alpine's `python3` all match; a bare
    # `python` does not, because this repo's floor is python3 and installing
    # python2 would satisfy the pattern while leaving the guards inert.
    if printf '%s' "$INPUT" |
        grep -qE '(apt-get|apt|dnf|yum|pacman|apk|brew)[^"]*(install|add|-S)[^"]*[[:space:]]python3([.0-9]*)([[:space:]]|\\"|"|$)'; then
        exit 0
    fi
    # Remedy 2: this repo's own bootstrap, setup subcommand only.
    if printf '%s' "$INPUT" |
        grep -qE '(^|[^A-Za-z0-9_./-])(\./|bash[[:space:]]+|sh[[:space:]]+)?[^"[:space:]]*run\.sh[[:space:]]+setup([[:space:]]|\\"|"|$)'; then
        exit 0
    fi
fi

cat >&2 <<'MSG'
BLOCKED: python3 is not installed, and the guard hooks in this repo are Python
modules run through .claude/rediacc_hooks/dispatch.py. Without python3 not one
of them can start, so the guard set (force-push, blanket git add, destructive
restore, worktree add, admin merge, amend, and the rest) is not protecting this
session at all.

Nothing else would report that. A hook whose interpreter is missing does not
explain itself; it just stops guarding, and every run afterwards looks clean.
This hook fails closed rather than let that pass unnoticed.

Two commands ARE permitted while python3 is missing, because a guard must not
forbid the cure it prescribes. Run either one, on its own, with no ; && ||
chaining:

  ./run.sh setup                      # installs the whole required toolchain
  sudo apt-get install -y python3     # Debian/Ubuntu, just this one package
  sudo dnf install -y python3         # Fedora/RHEL
  brew install python3                # macOS
MSG
exit 2
