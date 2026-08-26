#!/usr/bin/env bash
# FAIL CLOSED when jq is missing. Registered FIRST in every PreToolUse chain.
#
# THE DEFECT THIS CLOSES, measured on a bare machine 2026-08-26. Every one of the
# 22 pre-bash and 5 pre-edit hooks parses its stdin with
#   CMD=$(jq -r '.tool_input.command' 2>/dev/null)
# and when jq is not installed that yields an EMPTY string, no pattern matches,
# and the hook exits 0. Exit 0 means allow. So on a machine without jq the entire
# guard set silently becomes a no-op:
#
#   block-git-force-push          exit=0  ALLOWED   (a --force push)
#   block-blanket-git-add         exit=0  ALLOWED   (a wholesale add)
#   block-destructive-git-restore exit=0  ALLOWED   (a worktree-clobbering checkout)
#   block-worktree-add            exit=0  ALLOWED
#   block-git-amend               exit=0  ALLOWED
#
# Nothing reports this. The hooks are registered, they run, they exit 0, and the
# session believes it is protected while every guard it relies on is inert. That
# is the "a check that cannot fail" class in docs/agent-reference/TRAPS.md, and
# it is strictly worse than having no hooks at all, because no-hooks is at least
# visible.
#
# Subagents do NOT escape this: hook config is inherited, and a subagent's own
# `echo hi` was blocked by this guard (verified 2026-08-26). Delegation is not a
# bypass, which is the good outcome.
#
# ---------------------------------------------------------------------------
# THE CARVE-OUT, and why it is not a hole.
#
# The first version of this guard blocked EVERY Bash call while jq was missing,
# including `sudo apt-get install -y jq` and `./run.sh setup` -- the two cures
# its own message prescribes. That is a bootstrap deadlock: it locked the session
# out of the only actions that could unlock it, and an operator had to run the
# install by hand. A fail-closed guard must always leave its own recovery path
# open, and this one advertises a cure, so it must permit that cure.
#
# The security cost is ZERO. This carve-out only ever applies when jq is absent,
# and when jq is absent every other hook is already inert. Permitting these two
# specific remedies weakens nothing that was enforcing anything.
#
# THE MATCH IS DELIBERATELY TIGHT, because a loose one would be a real hole:
#   - chained payloads fail closed. `apt-get install -y jq; git push --force`
#     must NOT ride through on its prefix, so any shell metacharacter that could
#     start a second command (; && || | newline backtick $( ) rejects outright.
#   - `./run.sh setup` matches the SETUP SUBCOMMAND only, never `./run.sh <any>`.
#   - the package-manager arm requires a known manager, an install verb, AND jq
#     in the package list. `apt-get install -y curl` is not a remedy.
#
# AND IT IS PARSED WITHOUT jq, which is the whole point: this code runs exactly
# when jq does not exist, so it reads the raw JSON body rather than the value.
# That is coarser than a real parse, and it is safe here BECAUSE the fallback is
# to block: a payload this cannot understand is refused, not allowed.
# ---------------------------------------------------------------------------
if command -v jq >/dev/null 2>&1; then
    exit 0
fi

INPUT=$(cat)

# Any chaining/substitution metacharacter: refuse without further thought.
case "$INPUT" in
    *';'*|*'&&'*|*'||'*|*'`'*|*'$('*|*$'\n'*) allow=no ;;
    *) allow=maybe ;;
esac

if [ "$allow" = maybe ]; then
    # Remedy 1: a package-manager install whose package list includes jq.
    if printf '%s' "$INPUT" \
        | grep -qE '(apt-get|apt|dnf|yum|pacman|apk|brew)[^"]*(install|add|-S)[^"]*[[:space:]]jq([[:space:]]|\\"|"|$)'; then
        exit 0
    fi
    # Remedy 2: this repo's own bootstrap, setup subcommand only.
    if printf '%s' "$INPUT" \
        | grep -qE '(^|[^A-Za-z0-9_./-])(\./|bash[[:space:]]+|sh[[:space:]]+)?[^"[:space:]]*run\.sh[[:space:]]+setup([[:space:]]|\\"|"|$)'; then
        exit 0
    fi
fi

cat >&2 <<'MSG'
BLOCKED: jq is not installed, and every PreToolUse hook in this repo parses its
input with jq. Without it they all exit 0, which means ALLOW, so the entire guard
set (force-push, blanket git add, destructive restore, worktree add, admin merge,
amend, and 21 more) is silently inert.

This hook fails closed rather than let that pass unnoticed.

Two commands ARE permitted while jq is missing, because a guard must not forbid
the cure it prescribes. Run either one, on its own, with no ; && || chaining:

  ./run.sh setup                 # installs the whole required toolchain
  sudo apt-get install -y jq     # Debian/Ubuntu, just this one package
  sudo dnf install -y jq         # Fedora/RHEL
  brew install jq                # macOS
MSG
exit 2
