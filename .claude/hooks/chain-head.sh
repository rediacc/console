#!/usr/bin/env bash
# The ONE command .claude/settings.json registers for a guarded (event, matcher) pattern: the two toolchain checks, then the Python runner that carries the rest of the pattern.
#
# WHY IT IS BASH, and why it is the only bash file the hook chain has. One of the two checks is the check that python3 EXISTS: written in Python it could not run in the one condition it exists to report, and a hook that cannot start does not diagnose itself, the harness sees a failed command. The jq check makes the same argument in reverse, which is why it reads the RAW JSON body rather than a parsed value. A head carrying both therefore cannot be Python either. The allowlist entry for this file is in .ci/policy/.language-policy-allowlist.
#
# IT DECIDES NOTHING ELSE. Every other decision a pattern makes belongs to a member, and the members are the table in .claude/rediacc_hooks/lifecycle.py. Logic added here is logic no reader of that table can see.
#
# THE DEFECT THE jq CHECK CLOSES, measured on a bare machine 2026-08-26. Every bash guard parses its stdin with `jq -r ... 2>/dev/null`, and with no jq that yields an EMPTY string: nothing matches, the hook exits 0, and exit 0 means ALLOW. The whole guard set (force push, blanket git add, destructive restore, worktree add, amend, and the rest) silently became a no-op while the session believed it was protected. That is the "a check that cannot fail" class in docs/agent-reference/TRAPS.md, and it is strictly worse than having no hooks at all, because no-hooks is at least visible.
#
# THE python3 CHECK IS THAT DEFECT ONE TOOLCHAIN LATER. The ported guards are Python modules run through .claude/rediacc_hooks/dispatch.py, so without python3 not one of them can start, and nothing in the session says which guards stopped existing.
#
# ON PostToolUse A REFUSAL PREVENTS NOTHING, the tool having already run. It is there to SURFACE the broken toolchain instead of letting cancel-old-ci.sh and refresh-pr-body.sh quietly do nothing. POSITION is the rest of the contract: running behind the guards these checks protect, they would fire only once those guards had already returned ALLOW.
#
# THE CARVE-OUT, and why it is not a hole. The first version of the jq check blocked EVERY Bash call while jq was missing, including `sudo apt-get install -y jq` and `./run.sh setup`, the two cures its own message prescribes. That is a bootstrap deadlock: it locked the session out of the only actions that could unlock it, and an operator had to run the install by hand. A fail-closed guard that advertises a cure must permit that cure.
#
# THE SECURITY COST IS ZERO. A carve-out only ever applies while its own tool is absent, and while that tool is absent every guard behind it is already inert, so permitting these two remedies weakens nothing that was enforcing anything.
#
# THE MATCH IS DELIBERATELY TIGHT, because a loose one would be a real hole. Chained payloads fail closed: any metacharacter that could start a second command rejects outright, so `apt-get install -y jq; git push --force` cannot ride through on its prefix. `run.sh` matches the SETUP SUBCOMMAND only, never `./run.sh <any>`. The package arm needs a known manager, an install verb AND the package itself in the list, so `apt-get install -y curl` is not a remedy, and a bare `python` is not one either: this repo's floor is python3, and installing python2 would satisfy a looser pattern while leaving the guards inert. A payload this cannot understand is refused, not allowed.
#
# THE READ IS BOUNDED, and happens ONCE for the whole head. `INPUT=$(cat)` on a stdin that stays open and silent blocks forever, and a hang in a PreToolUse hook is not a slow check but a tool call that never returns (measured 2026-09-08 with the interpreter hidden from PATH so the arm is actually reached: exit 124 under an external timeout, against exit 2 in 0s once stdin is closed). `read -t` rather than `timeout cat`, because this runs precisely when the environment is degraded and a bash builtin cannot itself be missing. `-d ''` reads to NUL, that is to EOF, so only a status above 128 is the deadline firing, and the deadline REFUSES rather than allows.
set -u

PAYLOAD=""
IFS= read -r -d "" -t 10 PAYLOAD
if [ "$?" -gt 128 ]; then
    printf 'no payload arrived on stdin within 10s; refusing rather than hanging the tool call.\n' >&2
    exit 2
fi

# `$1` is the ERE matching the missing tool's package in an install list, which is the only part of a remedy that differs between the two checks. The payload is already in memory, so neither check re-reads stdin.
remedy() {
    # Any chaining or substitution metacharacter: refuse without further thought.
    case "$PAYLOAD" in
        *';'* | *'&&'* | *'||'* | *'`'* | *'$('* | *$'\n'*) return 1 ;;
    esac
    # Remedy 1: a package-manager install whose package list includes the missing tool.
    printf '%s' "$PAYLOAD" |
        grep -qE '(apt-get|apt|dnf|yum|pacman|apk|brew)[^"]*(install|add|-S)[^"]*[[:space:]]'"$1"'([[:space:]]|\\"|"|$)' && return 0
    # Remedy 2: this repo's own bootstrap, setup subcommand only.
    printf '%s' "$PAYLOAD" |
        grep -qE '(^|[^A-Za-z0-9_./-])(\./|bash[[:space:]]+|sh[[:space:]]+)?[^"[:space:]]*run\.sh[[:space:]]+setup([[:space:]]|\\"|"|$)' && return 0
    return 1
}

# `--check <tool>` runs that ONE check and stops, which is how the two are reached as commands of their own now that they are not scripts of their own: they are the members of `lifecycle.HEAD`, and they are the old side of the collapse differential. A tool this head does not carry is refused rather than skipped, because skipping it would be a check that cannot fail. .claude/settings.json passes a pattern key, never this.
ONLY=""
[ "${1-}" = "--check" ] && ONLY="${2-}"
case "$ONLY" in
    "" | jq | python3) ;;
    *)
        printf -- '--check %s names no toolchain check this head carries.\n' "$ONLY" >&2
        exit 2
        ;;
esac

wanted() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

if wanted jq && ! command -v jq >/dev/null 2>&1 && ! remedy 'jq'; then
    cat >&2 <<'MSG'
BLOCKED: jq is not installed, and every PreToolUse and PostToolUse Bash hook in
this repo parses its input with jq. Without it they all exit 0, which means ALLOW,
so the entire guard set (force-push, blanket git add, destructive restore,
worktree add, admin merge, amend, and 21 more) is silently inert.

On PostToolUse the tool has ALREADY run, so this exit prevents nothing: it is
there to surface the broken toolchain to the session instead of letting
cancel-old-ci.sh and refresh-pr-body.sh quietly do nothing.

This hook fails closed rather than let that pass unnoticed.

Two commands ARE permitted while jq is missing, because a guard must not forbid
the cure it prescribes. Run either one, on its own, with no ; && || chaining:

  ./run.sh setup                 # installs the whole required toolchain
  sudo apt-get install -y jq     # Debian/Ubuntu, just this one package
  sudo dnf install -y jq         # Fedora/RHEL
  brew install jq                # macOS
MSG
    exit 2
fi

if wanted python3 && ! command -v python3 >/dev/null 2>&1 && ! remedy 'python3([.0-9]*)'; then
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
fi

[ -n "$ONLY" ] && exit 0

# `dirname` IS RESOLVED HERE AND NOT AT THE TOP, because everything above this line has to survive a broken toolchain and `dirname` is a binary on disk like any other. Resolved first, a PATH holding only what the two checks use would break the head before either check could speak, which is the one condition they exist for.
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# `exec` on the right of the pipe replaces the subshell the pipeline already costs, so the runner is not a second process on top of one.
printf '%s' "$PAYLOAD" | exec python3 "$HERE/../rediacc_hooks/lifecycle.py" "$@"
