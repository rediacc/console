#!/usr/bin/env bash
# Refuse a `git commit` whose author email GitHub does not link to an account.
#
# WHAT IT COST WHEN NOTHING CHECKED. On 2026-09-03, 30 of 42 commits on branch
# 0903-1 carried `muhammed@rediacc.com` -- same DISPLAY NAME as the good ones, so
# `git log` looked uniform, while GitHub rendered them with a bare name, no avatar,
# no profile link and no contribution credit. The submodules had it too (7 of 9, 2
# of 2, 1 of 1). Fixing it took a history rewrite across four repositories and a
# force push.
#
# THE CONFIG WAS NOT THE CAUSE, and that decides the whole design. Measured in that
# checkout: no local user.email at all, and `git config --show-origin --get-all
# user.email` named exactly one source, the global file, with the CORRECT address.
# So those 30 came from an override at commit time -- `-c user.email=`, `--author=`,
# GIT_AUTHOR_EMAIL, or a different HOME. A guard that only read `git config` would
# have watched all 30 go past.
#
# WHY THIS DOES NOT PATTERN-MATCH THE COMMAND TEXT. The author identity is not IN
# the command; it comes from git's ident resolution. That is why this guard cannot
# repeat the failure recorded in block-commit-meta.sh's header, where a phrase check
# fired on prose and even on `grep -rn 'co-authored-by' docs/` -- its own audit. A
# command that merely MENTIONS an address is not a commit and is never scanned here.
#
# `git var GIT_AUTHOR_IDENT` implements git's entire precedence chain except
# `--author=`, so this does not reimplement it. Verified:
#     git var GIT_AUTHOR_IDENT                          -> the global address
#     git -c user.email=x@y.z var GIT_AUTHOR_IDENT      -> x@y.z
#     GIT_AUTHOR_EMAIL=e@e.e git var GIT_AUTHOR_IDENT   -> e@e.e
#
# The allowed set is .ci/config/commit-identity.json, GENERATED from GitHub by
# `.ci/scripts/quality/check-commit-identity.sh --refresh` and never hand-authored.
# It cannot be used to smuggle a bad address past CI: the CI gate never consults it
# to PASS a commit -- its verdict is GitHub's own `.author`.

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
hook_init || exit 0

# Is this a commit at all? Command position, so prose about committing is not.
# Deliberately NOT `git tag` and NOT `gh pr create`: a tag writes a tagger and a PR
# body has no author email, so widening here would only invite false positives.
printf '%s' "$SCAN" | grep -qE '(^|[;&|(]|\$\(|`)[[:space:]]*git([[:space:]]+-[A-Za-z-]+([[:space:]]+[^ ;&|]+)?)*[[:space:]]+commit([[:space:]]|$)' || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$ROOT" ] && exit 0

# WHICH REPO IS JUDGED, and this deliberately DIFFERS from block-untagged-commit.sh.
# That guard exits on ANY foreign root because epics are console's business alone.
# Three submodules carried this exact defect, so a commit into one of them IS in
# scope here; only a repo outside this tree is somebody else's identity policy.
TARGET="$(hook_target_root "$SCAN" "$ROOT")"
if [ -n "$TARGET" ]; then
    case "$TARGET" in
        "$ROOT"/*) : ;; # a submodule of this tree -- judge it
        *) exit 0 ;;    # an independent checkout -- not this guard's business
    esac
else
    TARGET="$ROOT"
fi

IDENTITY_FILE="${COMMIT_IDENTITY_FILE:-$ROOT/.ci/config/commit-identity.json}"
if [ ! -r "$IDENTITY_FILE" ]; then
    echo "BLOCKED: cannot read $IDENTITY_FILE, so this commit's author cannot be checked." >&2
    echo "" >&2
    echo "It is a tracked file; inside this tree its absence means a broken checkout." >&2
    echo "Regenerate it from GitHub:" >&2
    echo "    .ci/scripts/quality/check-commit-identity.sh --refresh" >&2
    exit 2
fi

# Collect overrides from the region BEFORE the `commit` verb. Structural, because
# git requires `-c` there, and it keeps a `-m` message body out of the parse.
PRE="${CMD%%commit*}"
CFLAGS=()
while IFS= read -r kv; do
    [ -n "$kv" ] && CFLAGS+=(-c "$kv")
done < <(printf '%s' "$PRE" | grep -oE '\-c[[:space:]]+"?user\.email=[^"[:space:]]+' | sed -E 's/^-c[[:space:]]+"?//')
ENVS=()
while IFS= read -r kv; do
    [ -n "$kv" ] && ENVS+=("$kv")
done < <(printf '%s' "$PRE" | grep -oE '(GIT_AUTHOR_EMAIL|GIT_COMMITTER_EMAIL|EMAIL)=[^[:space:]]+')

resolve() { # resolve <GIT_AUTHOR_IDENT|GIT_COMMITTER_IDENT>
    env ${ENVS[@]+"${ENVS[@]}"} git -C "$TARGET" ${CFLAGS[@]+"${CFLAGS[@]}"} var "$1" 2>/dev/null |
        sed -nE 's/.*<([^>]+)>.*/\1/p'
}
AUTHOR_EMAIL="$(resolve GIT_AUTHOR_IDENT)"
COMMITTER_EMAIL="$(resolve GIT_COMMITTER_IDENT)"

# --author= wins for the author field, and getting at it took two corrections.
#
# It must be read from the RAW command, not the scan: git's form is
# `--author="Name <a@b>"`, and the scan strips quoted spans, so the value was gone
# before the match ran -- leaving `--author=` with nothing after it, and the guard
# permitting the exact override it exists to catch.
#
# But reading the raw command whole was ALSO wrong, and this file's own first commit
# proved it: the message explaining `--author=` contained the string, so the guard
# refused the commit that introduced it. That is precisely the failure recorded in
# block-commit-meta.sh's header, where a phrase check blocked its own audit -- and
# "accept the false positive, it is loud" was the wrong call. A guard that cannot be
# described in a commit message is a guard people route around.
#
# So the MESSAGE VALUE is removed first, then `--author` is looked for in what is
# left. git takes the message as the argument to -m/--message, so a mention inside
# it is prose by construction, while a real `--author` sits outside it.
DEAUTHORED="$(printf '%s' "$CMD" | sed -E \
    -e 's/(-m|--message)[= ]+"[^"]*"/\1 MSG/g' \
    -e "s/(-m|--message)[= ]+'[^']*'/\1 MSG/g" \
    -e 's/(-F|--file)[= ]+[^[:space:]]+/\1 FILE/g')"
OVERRIDE="$(printf '%s' "$DEAUTHORED" |
    grep -oE '\-\-author[= ]+("[^"]*<[^>]+>"|'"'"'[^'"'"']*<[^>]+>'"'"'|[^[:space:]]+@[^[:space:]]+)' |
    head -1 |
    sed -nE 's/.*<([^>]+)>.*/\1/p; s/.*[= ]+([^ "'"'"'<]+@[^ "'"'"'>]+)$/\1/p' | head -1)"
[ -n "$OVERRIDE" ] && AUTHOR_EMAIL="$OVERRIDE"

if [ -z "$AUTHOR_EMAIL" ]; then
    echo "BLOCKED: git cannot resolve an author identity for this commit." >&2
    echo "" >&2
    echo "It would be attributed to a guessed user@hostname, which is the same defect" >&2
    echo "in a worse costume. Set one:" >&2
    echo "    git config --global user.name  \"Your Name\"" >&2
    echo "    git config --global user.email \"you@example.com\"" >&2
    exit 2
fi

allowed() { # allowed <email>
    jq -e --arg e "$1" '
        [ .identities[]
          | .emails[],
            "\(.id)+\(.login)@users.noreply.github.com",
            "\(.login)@users.noreply.github.com"
        ] | index($e) != null' "$IDENTITY_FILE" >/dev/null 2>&1
}

for pair in "author:$AUTHOR_EMAIL" "committer:$COMMITTER_EMAIL"; do
    field="${pair%%:*}"
    email="${pair#*:}"
    [ -z "$email" ] && continue
    # Bot addresses attribute on GitHub and are never this guard's business.
    case "$email" in *'[bot]@users.noreply.github.com') continue ;; esac
    allowed "$email" && continue

    echo "BLOCKED: the $field email <$email> is not linked to a GitHub account." >&2
    echo "" >&2
    echo "GitHub renders such commits with a bare name: no avatar, no profile link," >&2
    echo "no contribution credit. On 2026-09-03 this cost a history rewrite across" >&2
    echo "four repositories after 30 commits landed that way unnoticed." >&2
    echo "" >&2
    echo "Where it came from:" >&2
    git -C "$TARGET" config --show-origin --get-all user.email 2>/dev/null | sed 's/^/    /' >&2
    [ "${#CFLAGS[@]}" -gt 0 ] && echo "    -c on your command line: ${CFLAGS[*]}" >&2
    [ "${#ENVS[@]}" -gt 0 ] && echo "    environment: ${ENVS[*]}" >&2
    [ -n "$OVERRIDE" ] && echo "    --author= on your command line" >&2
    echo "" >&2
    echo "Allowed (from $IDENTITY_FILE):" >&2
    jq -r '.identities[] | .emails[] | "    " + .' "$IDENTITY_FILE" >&2
    echo "" >&2
    echo "Fix: use a linked address, or add this one at" >&2
    echo "https://github.com/settings/emails and re-run --refresh." >&2
    exit 2
done

exit 0
