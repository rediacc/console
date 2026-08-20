#!/usr/bin/env bash
# Smoke-test every guard hook by feeding sample tool_input JSON and asserting the exit code.
# Usage: bash .claude/hooks/test-hooks.sh   (run after `/hooks` reload; needs jq)
# NOTE: suppression test tokens are concatenated at runtime ("@ts-""ignore") so this file's
# text never contains the literal banned token, otherwise the suppressions guard blocks it.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

# check <expected-exit> <script-relative-path> <json-stdin> <label>
check() {
    local expected="$1" script="$2" json="$3" label="$4" rc
    echo "$json" | bash "$DIR/$script" >/dev/null 2>&1
    rc=$?
    if [[ "$rc" == "$expected" ]]; then
        PASS=$((PASS + 1))
        printf 'ok   [%s] %s (exit %s)\n' "$expected" "$label" "$rc"
    else
        FAIL=$((FAIL + 1))
        printf 'FAIL [%s] %s (got exit %s)\n' "$expected" "$label" "$rc"
    fi
}

# check_out <expected-exit> <script> <json-stdin> <label> <must-contain>
# Like check(), plus an assertion on what the guard SAID. Used where the
# message is the product: the STATE.md guard's whole job since 2026-08-09 is to
# redirect a session to the one writer that can merge, and an exit code alone
# cannot tell "blocked, here is the correct command" from "blocked, good luck".
check_out() {
    local expected="$1" script="$2" json="$3" label="$4" needle="$5" rc out
    out="$(echo "$json" | bash "$DIR/$script" 2>&1 >/dev/null)"
    rc=$?
    if [[ "$rc" == "$expected" ]] && grep -qF "$needle" <<<"$out"; then
        PASS=$((PASS + 1))
        printf 'ok   [%s] %s (exit %s)\n' "$expected" "$label" "$rc"
    else
        FAIL=$((FAIL + 1))
        printf 'FAIL [%s] %s (got exit %s, needle %s)\n' "$expected" "$label" "$rc" \
            "$(grep -qF "$needle" <<<"$out" && echo present || echo MISSING)"
    fi
}

bash_json() { printf '{"tool_input":{"command":%s}}' "$(jq -Rn --arg c "$1" '$c')"; }
edit_json() { printf '{"tool_input":{"new_string":%s}}' "$(jq -Rn --arg c "$1" '$c')"; }
multiedit_json() { printf '{"tool_input":{"edits":[{"new_string":%s}]}}' "$(jq -Rn --arg c "$1" '$c')"; }
# wf_edit_json <file_path> <new_string>: Edit payload carrying a target file path.
wf_edit_json() { printf '{"tool_input":{"file_path":%s,"new_string":%s}}' "$(jq -Rn --arg c "$1" '$c')" "$(jq -Rn --arg c "$2" '$c')"; }
# tool_json <tool_name> <file_path> <content-or-new_string field> <value>
tool_json() { printf '{"tool_name":%s,"tool_input":{"file_path":%s,%s:%s}}' "$(jq -Rn --arg c "$1" '$c')" "$(jq -Rn --arg c "$2" '$c')" "\"$3\"" "$(jq -Rn --arg c "$4" '$c')"; }
STATE_GOOD="$(python3 -c "print('x'*300 + chr(10)*2 + '## Next action' + chr(10)*2 + 'go')")"
STATE_AIMLESS="$(python3 -c "print('x'*300)")"

# A fat (9 logic line) and a thin (2 logic line) inline `run:` block for the
# workflow-inline guard.
WF_FAT=$'      - name: Big\n        run: |\n          echo 1\n          echo 2\n          echo 3\n          echo 4\n          echo 5\n          echo 6\n          echo 7\n          echo 8\n          echo 9'
WF_THIN=$'      - name: Thin\n        run: |\n          echo hi\n          bash .ci/scripts/quality/x.sh'

# --- WIRING: what is on disk and what settings.json registers must match ---
# Every case in this file drives a hook by literal path, which proves the
# script behaves and says NOTHING about whether Claude ever invokes it. Two
# failures are invisible to the whole suite: a hook file nobody registered
# (dead code that tests green and never guards anything), and a registration
# pointing at a file that no longer exists (a hook that silently never fires).
# settings.json is READ here, never written.

# hook_files <hooks-root> -- relative path of every hook script, lib/ excluded
hook_files() {
    local root="$1"
    find "$root" -type f -name '*.sh' -not -path '*/lib/*' 2>/dev/null |
        sed "s|^$root/||" |
        grep -E '^(pre-bash|pre-edit|post-bash)/' | sort -u
}

# hook_registrations <settings-file> -- the same relative paths, as named by
# the hook command strings in settings.json
hook_registrations() {
    jq -r '.hooks // {} | to_entries[] | .value[]? | .hooks[]? | .command // empty' "$1" 2>/dev/null |
        grep -oE '(pre-bash|pre-edit|post-bash)/[A-Za-z0-9._-]+\.sh' | sort -u
}

# check_wiring <settings-file> <hooks-root> -- 0 when the two sets agree, 1
# otherwise, naming every offender on stdout.
check_wiring() {
    local settings="$1" root="$2" rc=0 unwired dangling
    unwired="$(comm -23 <(hook_files "$root") <(hook_registrations "$settings"))"
    dangling="$(comm -13 <(hook_files "$root") <(hook_registrations "$settings"))"
    if [[ -n "$unwired" ]]; then
        rc=1
        while read -r f; do printf 'UNWIRED (on disk, not in settings): %s\n' "$f"; done <<<"$unwired"
    fi
    if [[ -n "$dangling" ]]; then
        rc=1
        while read -r f; do printf 'DANGLING (in settings, not on disk): %s\n' "$f"; done <<<"$dangling"
    fi
    return "$rc"
}

# wiring_case <expected-exit> <settings> <hooks-root> <label> [<must-name>...]
wiring_case() {
    local expected="$1" settings="$2" root="$3" label="$4" out rc miss="" needle
    shift 4
    out="$(check_wiring "$settings" "$root" 2>&1)"
    rc=$?
    for needle in "$@"; do
        grep -qF -- "$needle" <<<"$out" || miss="$miss $needle"
    done
    if [[ "$rc" == "$expected" && -z "$miss" ]]; then
        PASS=$((PASS + 1))
        printf 'ok   [%s] %s (exit %s)\n' "$expected" "$label" "$rc"
    else
        FAIL=$((FAIL + 1))
        printf 'FAIL [%s] %s (got exit %s, unnamed:%s)\n' "$expected" "$label" "$rc" "${miss:- -}"
        sed 's/^/       /' <<<"$out"
    fi
}

wiring_case 0 "$DIR/../settings.json" "$DIR" "wiring: every hook on disk is registered, every registration exists"

# CONTROL, so the green above is agreement and not a check that cannot fire:
# one fixture drops a real registration, the other invents one. Each must fail
# AND name the offender -- a bare non-zero would pass either fixture.
WIRE_TMP="$(mktemp -d)"
jq '(.hooks[]?[]?.hooks) |= map(select((.command // "") | contains("block-worktree-add.sh") | not))' \
    "$DIR/../settings.json" >"$WIRE_TMP/unwired.json"
wiring_case 1 "$WIRE_TMP/unwired.json" "$DIR" "wiring CONTROL: a dropped registration is caught as UNWIRED" \
    "UNWIRED (on disk, not in settings): pre-bash/block-worktree-add.sh"
jq '(.hooks[]?[]?.hooks) |= . + [{"type":"command","command":"bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/pre-bash/block-nonexistent-ghost.sh\""}]' \
    "$DIR/../settings.json" >"$WIRE_TMP/dangling.json"
wiring_case 1 "$WIRE_TMP/dangling.json" "$DIR" "wiring CONTROL: a registration with no file is caught as DANGLING" \
    "DANGLING (in settings, not on disk): pre-bash/block-nonexistent-ghost.sh"
rm -rf "$WIRE_TMP"

# --- should BLOCK (exit 2) ---
check 2 pre-bash/block-protected-files.sh "$(bash_json 'git checkout .claude/settings.json')" "protected-files"
check 2 pre-bash/block-commit-meta.sh "$(bash_json 'git commit -m msg Co-Authored-By: bot')" "commit-meta"
check 2 pre-bash/block-binary-deploy.sh "$(bash_json 'scp renet host:/tmp')" "binary-deploy"
check 2 pre-bash/block-cli-bundle.sh "$(bash_json 'node packages/cli/dist/x.js')" "cli-bundle"
check 2 pre-bash/block-ssh-docker.sh "$(bash_json 'ssh host docker ps')" "ssh-docker"
check 2 pre-bash/block-ssh-file-write.sh "$(bash_json 'cat a | ssh host tee /etc/x')" "ssh-file-write"
check 2 pre-bash/block-ci-polling.sh "$(bash_json 'sleep 5 && gh run view 1')" "ci-polling"
check 2 pre-bash/block-ci-reverse-poll.sh "$(bash_json 'gh run view 1 --jq .x && sleep 5')" "ci-reverse-poll"
check 2 pre-bash/block-long-sleep.sh "$(bash_json 'sleep 30')" "long-sleep"
check 2 pre-bash/block-git-amend.sh "$(bash_json 'git commit --amend')" "git-amend"
check 2 pre-bash/block-git-force-push.sh "$(bash_json 'git push --force')" "git-force-push"
check 2 pre-bash/block-git-empty-commit.sh "$(bash_json 'git commit --allow-empty -m x')" "git-empty-commit"
check 2 pre-bash/block-worktree-add.sh "$(bash_json 'git worktree add ../foo -b bar')" "worktree-add"
check 2 pre-bash/block-worktree-add.sh "$(bash_json 'git -C /some/path worktree add ../x main')" "worktree-add: -C before the subcommand"
check 2 pre-bash/block-worktree-add.sh "$(bash_json 'sh -c "git worktree add ../x"')" "worktree-add: sh -c wrapper bypass"
check 2 pre-bash/block-worktree-add.sh "$(bash_json 'echo start; git worktree add ../x')" "worktree-add: after a command separator"
check 2 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add -A')" "blanket-git-add: -A with no pathspec"
check 2 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add --all')" "blanket-git-add: --all with no pathspec"
check 2 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add .')" "blanket-git-add: a lone dot"
check 2 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add :/')" "blanket-git-add: the repo-root magic pathspec"

# block-destructive-git-restore.sh -- the four commands that DISCARD uncommitted
# work. Added 2026-08-14 after `git checkout -- <one file>`, run to tidy up a
# stray edit, destroyed another live session's uncommitted value in that file.
# The rule had existed in CLAUDE.md for months; a rule protects only the session
# that recalls it at the one second it matters.
H=pre-bash/block-destructive-git-restore.sh
check 2 "$H" "$(bash_json 'git checkout -- packages/www/src/i18n/translations/.translation-hashes.json')" "destructive-git: the exact 2026-08-14 command"
check 2 "$H" "$(bash_json 'git checkout .')" "destructive-git: checkout a lone dot"
check 2 "$H" "$(bash_json 'git restore src/file.ts')" "destructive-git: restore"
check 2 "$H" "$(bash_json 'git -C private/renet restore pkg/chunkstore/session.go')" "destructive-git: restore in a submodule via -C"
check 2 "$H" "$(bash_json 'git stash')" "destructive-git: bare stash"
check 2 "$H" "$(bash_json 'git stash pop')" "destructive-git: stash pop"
check 2 "$H" "$(bash_json 'git clean -fd')" "destructive-git: clean"
check 2 "$H" "$(bash_json 'echo hi; git restore src/')" "destructive-git: after a command separator"
# THE NEGATIVE HALF, which matters more than usual: this guard sits on `git
# checkout`, which sessions use to switch branches all day. A guard that blocks
# that is one sessions demand be removed, leaving no guard at all.
check 0 "$H" "$(bash_json 'git checkout main')" "destructive-git: branch switch is NOT blocked"
check 0 "$H" "$(bash_json 'git checkout -b feature/x')" "destructive-git: branch create is NOT blocked"
check 0 "$H" "$(bash_json 'git stash list')" "destructive-git: stash list is read-only"
check 0 "$H" "$(bash_json 'git stash show -p')" "destructive-git: stash show is read-only"
check 0 "$H" "$(bash_json 'git clean -n')" "destructive-git: clean --dry-run is read-only"
check 0 "$H" "$(bash_json 'git status')" "destructive-git: unrelated git command"
check 2 pre-bash/block-blanket-git-add.sh "$(bash_json 'cd /tmp && git add -A')" "blanket-git-add: after a command separator"
check 2 pre-bash/block-blanket-git-add.sh "$(bash_json 'sh -c "git add -A"')" "blanket-git-add: sh -c wrapper bypass"
# BYPASSES found by review of PR #566, each confirmed by running the guard before
# the fix: all three exited 0 while staging the whole tree. Redirection is not a
# pathspec, and `--` with nothing after it is not a restriction -- git treats an
# empty pathspec list as no restriction at all, so it is the bare form wearing
# the escape's clothes.
check 2 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add -A > /dev/null')" "blanket-git-add: stdout redirection is not a pathspec"
check 2 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add -A 2>&1')" "blanket-git-add: fd redirection is not a pathspec"
check 2 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add -A --')" "blanket-git-add: a bare -- with no pathspec is still blanket"
check 2 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add . > /dev/null')" "blanket-git-add: dot plus redirection"
check 2 pre-bash/block-nondraft-pr-create.sh "$(bash_json 'gh pr create --title x --body y')" "nondraft-create: console without --draft"
check 2 pre-bash/block-nondraft-pr-create.sh "$(bash_json 'cd private/renet && gh pr create --draft --title x')" "nondraft-create: draft on private submodule"
check 2 pre-bash/block-admin-merge.sh "$(bash_json 'gh pr merge 531 --squash --admin')" "admin-merge: --admin banned"
# Adversarial bypass cases (review finding F1): the quote-strip used to let
# shell-wrapper / eval / flag=value / variable-indirection forms slip the ban.
check 2 pre-bash/block-admin-merge.sh "$(bash_json "sh -c 'gh pr merge 531 --admin'")" "admin-merge: sh -c wrapper bypass blocked"
check 2 pre-bash/block-admin-merge.sh "$(bash_json 'bash -c "gh pr merge 531 --admin"')" "admin-merge: bash -c wrapper bypass blocked"
check 2 pre-bash/block-admin-merge.sh "$(bash_json "eval 'gh pr merge 531 --admin'")" "admin-merge: eval wrapper bypass blocked"
# Round-39 review finding: bundled/separate flags before -c defeated both the
# wrapper-unwrap AND the prose-strip (which erases the same quoted payload).
check 2 pre-bash/block-admin-merge.sh "$(bash_json "bash -lc 'gh pr merge 531 --admin'")" "admin-merge: bundled-flag wrapper (bash -lc) bypass blocked"
check 2 pre-bash/block-admin-merge.sh "$(bash_json "sh -eu -c 'gh pr merge 531 --admin'")" "admin-merge: separate-flag wrapper (sh -eu -c) bypass blocked"
check 2 pre-bash/block-admin-merge.sh "$(bash_json "bash -eux -c 'gh pr merge 531 --admin'")" "admin-merge: multi-flag wrapper (bash -eux -c) bypass blocked"
# Round-40 review finding: GNU long options and value-taking short options
# before -c also defeated the round-40 flag-shape regex; fixed via
# token-scanning (any intervening token is skippable) instead of a 4th regex.
check 2 pre-bash/block-admin-merge.sh "$(bash_json "bash --posix -c 'gh pr merge 531 --admin'")" "admin-merge: GNU long-option wrapper (bash --posix -c) bypass blocked"
check 2 pre-bash/block-admin-merge.sh "$(bash_json "bash --norc -c 'gh pr merge 531 --admin'")" "admin-merge: GNU long-option wrapper (bash --norc -c) bypass blocked"
check 2 pre-bash/block-admin-merge.sh "$(bash_json "bash -o pipefail -c 'gh pr merge 531 --admin'")" "admin-merge: value-taking-flag wrapper (bash -o pipefail -c) bypass blocked"
# Round-42 review finding: a path-qualified shell name (exact-match anchor,
# not basename) defeated the token-scanner the same way flag shapes did.
check 2 pre-bash/block-admin-merge.sh "$(bash_json "/bin/bash -c 'gh pr merge 531 --admin'")" "admin-merge: path-qualified shell (/bin/bash -c) bypass blocked"
check 2 pre-bash/block-admin-merge.sh "$(bash_json "./bash -c 'gh pr merge 531 --admin'")" "admin-merge: relative-path shell (./bash -c) bypass blocked"
# Round-44 review finding: a QUOTED shell path defeated the basename strip
# (the last `/` lands inside the quotes, leaving a trailing quote character).
check 2 pre-bash/block-admin-merge.sh "$(bash_json '"/bin/bash" -c '"'"'gh pr merge 531 --admin'"'"'')" 'admin-merge: double-quoted path ("/bin/bash" -c) bypass blocked'
check 2 pre-bash/block-admin-merge.sh "$(bash_json "'/bin/bash' -c 'gh pr merge 531 --admin'")" "admin-merge: single-quoted path ('/bin/bash' -c) bypass blocked"
check 2 pre-bash/block-admin-merge.sh "$(bash_json 'gh pr merge 531 --squash --admin=true')" "admin-merge: --admin=value bypass blocked"
check 2 pre-bash/block-admin-merge.sh "$(bash_json 'X=--admin; gh pr merge 531 $X')" "admin-merge: variable-indirection bypass blocked"
check 2 pre-bash/block-nondraft-pr-create.sh "$(bash_json "sh -c 'gh pr create --title x --body y'")" "nondraft-create: sh -c wrapper bypass blocked"
# Round-46 (live during a real /pr-merge): fields were parsed from the WHOLE
# bash line, so sibling gh invocations donated fields to each other and only
# ONE invocation per line was ever examined. Each of these pairs a compliant
# invocation with a violating one; both must be judged on their own segment.
check 2 pre-bash/block-nondraft-pr-create.sh "$(bash_json 'gh pr create --draft --repo rediacc/console -t x; gh pr create --repo rediacc/console -t y')" "nondraft-create: second create on the line is judged too (no --draft donation)"
check 2 pre-bash/block-nondraft-pr-create.sh "$(bash_json 'gh pr create --draft --repo rediacc/console -t x; gh pr create --draft --repo rediacc/renet -t y')" "nondraft-create: draft-on-private caught in the second segment (no --repo donation)"
check 2 pre-edit/block-suppressions.sh "$(edit_json "a // @ts-""ignore")" "suppressions(new_string)"
check 2 pre-edit/block-suppressions.sh "$(multiedit_json "b // eslint-""disable")" "suppressions(MultiEdit)"
check 2 pre-edit/block-inline-workflow-run.sh "$(wf_edit_json '.github/workflows/x.yml' "$WF_FAT")" "inline-workflow-run: 9-line block blocked"
# STATE.md write guard: the CLI refusal alone is bypassed by a raw Write (the
# document lives at a plain repo path), so the guard is the closing half.
#
# IT DENIES EVERY DIRECT WRITE NOW, shape-valid ones included, and the
# WELL-SHAPED case below is the one that changed. Only the CLI writes STATE.md,
# with the heading, the stamp and the lock that make it recoverable; a
# perfectly shaped whole-file Write lands unstamped, exactly as unrecoverably
# as a malformed one, so a guard that measured LENGTH was waving through the
# only defect that matters. Each case asserts the message too, because
# redirecting to `--state` IS the guard's product.
#
# THE PATHS HERE ARE LITERAL STRINGS with no filesystem behind them, which is
# what makes them dangerous during a move: when the tree went from
# .agent/<branch>/ to agent/<branch>/<session>/ (2026-08-14), every one of
# these cases would have kept passing against the OLD path while the guard
# stopped covering the new one, and the suite would have reported that as
# green. It moved AGAIN on 2026-08-18, when the branch left the path and
# agent/<session>/STATE.md became the live shape, so the same hazard applies to
# these very lines: the live one-level shape is asserted FIRST, and the retired
# two-level shapes after it, because writing THERE is a session running stale
# instructions rather than a path nobody would ever try.
check_out 2 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/agent/deadbeef/STATE.md content tiny)" "agent-state: thin Write blocked" "worklist.py --state"
check_out 2 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/agent/deadbeef/STATE.md content "$STATE_AIMLESS")" "agent-state: aimless Write (no Next action) blocked" "worklist.py --state"
check_out 2 pre-edit/block-agent-state-shape.sh "$(tool_json Edit /r/agent/deadbeef/STATE.md new_string patch)" "agent-state: Edit blocked (rewrite, never append)" "agent/<your-prefix>/STATE.md"
check_out 2 pre-edit/block-agent-state-shape.sh "$(tool_json MultiEdit /r/agent/deadbeef/STATE.md new_string patch)" "agent-state: MultiEdit blocked" "worklist.py --state"
# The live path must be reached at DEPTH inside an absolute path too: a pattern
# anchored at the string start leaves every real checkout open.
check_out 2 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/monorepo/console/agent/deadbeef/STATE.md content "$STATE_GOOD")" "agent-state: the real session path is reached, deep in an absolute path" "agent/<your-prefix>/STATE.md"
check_out 2 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/agent/0814-1/deadbeef/STATE.md content "$STATE_GOOD")" "agent-state: the retired branch/session path is blocked too" "worklist.py --state"
check_out 2 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/.agent/b/STATE.md content "$STATE_GOOD")" "agent-state: the legacy dotted path is blocked too" "worklist.py --state"

# --- should PASS (exit 0) ---
# NOTE: block-premature-ready.sh and block-admin-merge.sh verify live CI/thread
# state over the network on their enforcement paths; only their pattern paths
# (--undo, --auto, --draft flags, non-matching commands) are unit-tested here.
check 0 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add -A -- packages/cli/src')" "blanket-git-add: -A WITH a pathspec is the escape, allowed"
check 0 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add packages/cli/src/foo.ts')" "blanket-git-add: a named file is allowed"
check 0 pre-bash/block-blanket-git-add.sh "$(bash_json 'git -C private/renet add -A -- pkg/')" "blanket-git-add: -C plus a pathspec is allowed"
check 0 pre-bash/block-blanket-git-add.sh "$(bash_json 'git add -A -- . > /dev/null')" "blanket-git-add CONTROL: a real pathspec WITH redirection is still allowed"
# CROSS-TALK CONTROL. Two guards match adjacent `git ... add` shapes, and a
# regex widened by one word would make this one swallow worktree creation --
# which would then be blocked with the WRONG message and the wrong escape.
check 0 pre-bash/block-blanket-git-add.sh "$(bash_json 'git worktree add /tmp/wt main')" "blanket-git-add CONTROL: worktree add is NOT this guard's business"
# --- one open PR at a time -------------------------------------------------
# The guard shells out to `gh pr list`, so these stub it on PATH. Without the
# stub the cases would depend on whatever PRs happen to be open, which is a
# fixture that changes under you: green today, red tomorrow, and never for a
# reason anyone can see.
stub_gh() { # stub_gh <json-or-empty> <exit>; prints a dir to prepend to PATH
    local out="$1" rc="$2" d
    d="$(mktemp -d)"
    {
        echo '#!/usr/bin/env bash'
        printf 'cat <<%s\n%s\n%s\n' "GHEOF" "$out" "GHEOF"
        echo "exit $rc"
    } >"$d/gh"
    chmod +x "$d/gh"
    printf '%s' "$d"
}
gh_case() { # gh_case <expected-rc> <stub-json> <stub-rc> <cmd> <label> [needle]
    local exp="$1" body="$2" grc="$3" cmd="$4" label="$5" needle="${6:-}" d out rc
    d="$(stub_gh "$body" "$grc")"
    out="$(echo "$(bash_json "$cmd")" | PATH="$d:$PATH" bash "$DIR/pre-bash/block-second-open-pr.sh" 2>&1)"
    rc=$?
    rm -rf "$d"
    if [[ "$rc" == "$exp" ]] && { [[ -z "$needle" ]] || grep -qF "$needle" <<<"$out"; }; then
        PASS=$((PASS + 1))
        printf 'ok   [%s] %s\n' "$exp" "$label"
    else
        FAIL=$((FAIL + 1))
        printf 'FAIL [%s] %s (got %s) %s\n' "$exp" "$label" "$rc" "${out:0:90}"
    fi
}
gh_case 2 '[{"number":563,"title":"t","headRefName":"b","isDraft":false}]' 0 \
    'gh pr create --draft -t x -b y' "one-pr: a second create is blocked when one is open" "One at a time"
gh_case 2 '[{"number":563,"title":"t","headRefName":"b","isDraft":false}]' 0 \
    "sh -c 'gh pr create --draft -t x -b y'" "one-pr: sh -c wrapping does not bypass it"
# THE CONTROL THAT MATTERS: with no open PR the guard must be invisible, or it
# would block the FIRST PR too and simply stop all work.
gh_case 0 '[]' 0 'gh pr create --draft -t x -b y' "one-pr CONTROL: the first PR is allowed"
gh_case 0 '[]' 0 'gh pr view 567' "one-pr CONTROL: a non-create gh command is ignored"
# FAILS CLOSED: an unreadable list is not evidence that the list is empty.
gh_case 2 'gh: could not connect' 1 'gh pr create --draft -t x -b y' \
    "one-pr: an unreadable PR list blocks rather than assuming none" "cannot verify"
check 0 pre-bash/block-nondraft-pr-create.sh "$(bash_json 'gh pr create --draft --title x --body y')" "nondraft-create: console with --draft ok"

# --- trapguard PostToolUse rules: they INJECT rather than block, so the product
# is stdout, not the exit code. A rule that exits 0 silently and a rule that
# exits 0 having warned are indistinguishable without asserting on the text.
inject_json() { # inject_json <command> <stdout-of-that-command>
    python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","cwd":sys.argv[1],"tool_input":{"command":sys.argv[2]},"tool_response":{"stdout":sys.argv[3],"stderr":""}}))' "$(cd "$DIR/../.." && pwd)" "$1" "$2"
}
check_inject() { # check_inject <fires|silent> <json> <label> [needle]
    local want="$1" json="$2" label="$3" needle="${4:-}" out
    out="$(echo "$json" | python3 "$DIR/trapguard/dispatch.py" --posttool 2>/dev/null)"
    local got="silent"
    [[ -n "$out" ]] && got="fires"
    if [[ "$got" == "$want" ]] && { [[ -z "$needle" ]] || grep -qF "$needle" <<<"$out"; }; then
        PASS=$((PASS + 1))
        printf 'ok   [%s] %s\n' "$want" "$label"
    else
        FAIL=$((FAIL + 1))
        printf 'FAIL [%s] %s (got %s)\n' "$want" "$label" "$got"
    fi
}
check_inject fires "$(inject_json 'gh run view 1 --json jobs' '{"conclusion":"cancelled","name":"Quality / Static"}')" \
    "trapguard: a cancelled run gets a warning" "cancelled-run-not-passed"
check_inject silent "$(inject_json 'gh run view 1 --json jobs' '{"conclusion":"success","name":"Quality / Static"}')" \
    "trapguard CONTROL: an all-success run is NOT warned about"
check_inject silent "$(inject_json 'gh run view 1 --json jobs' '')" \
    "trapguard CONTROL: an empty response does not fire (absence is not a cancellation)"
# THE SHAPE THAT WAS DEAD CODE until review of PR #567. A failure-filtered query
# returning [] contains no word "cancelled" by construction, because the filter
# removed the cancelled job, so gating on that word made this branch unreachable
# for the only case it existed to catch.
check_inject fires "$(inject_json 'gh run view 1 --jq .jobs[]|select(.conclusion=="failure")' '[]')" \
    "trapguard: a failure-filtered query returning EMPTY is warned about" "cancelled-run-not-passed"
check_inject silent "$(inject_json 'gh run view 1 --json jobs' '[]')" \
    "trapguard CONTROL: an empty result from an UNfiltered query is not that shape"
# Precision decay, observed LIVE within an hour of the rule shipping: it warned about
# output reading `cancelled=0`, which is a session performing exactly the check this
# rule asks for and finding nothing. Counting cancelled jobs must not be punished.
check_inject silent "$(inject_json 'gh run view 1 --json jobs' 'success=44 skipped=39 cancelled=0 failure=1')" \
    "trapguard CONTROL: a cancelled COUNT of zero is the good behaviour, not the trap"
check_inject silent "$(inject_json 'gh run view 1 --json jobs' '{"cancelled": 0, "failure": 1}')" \
    "trapguard CONTROL: the JSON zero-count shape is silent too"
check_inject fires "$(inject_json 'gh run view 1 --json jobs' 'success=40 cancelled=3 failure=1')" \
    "trapguard: a NON-zero cancelled count still fires" "cancelled-run-not-passed"
# The one that matters: a zero count must not MASK a real cancellation beside it.
check_inject fires "$(inject_json 'gh run view 1 --json jobs' 'cancelled=0
{"conclusion":"cancelled","name":"Quality"}')" \
    "trapguard: a zero count does not mask a real cancelled conclusion" "cancelled-run-not-passed"
# The on-disk test is the whole discriminator for the next three: identical
# output, and only the filesystem separates a phantom from a real deletion.
# The phantom needs a path that is UNTRACKED and present, which is the state a
# plumbing-built branch leaves files in. Planted at runtime with a keyed name so
# the case holds in any checkout and a crashed earlier run cannot satisfy it.
TG_PHANTOM="tg_phantom_probe_$$_$(date +%s).txt"
printf 'x\n' >"$(cd "$DIR/../.." && pwd)/$TG_PHANTOM"
check_inject fires "$(inject_json "git diff somebranch -- $TG_PHANTOM" " $TG_PHANTOM | 462 ------
 1 file changed, 462 deletions(-)")" \
    "trapguard: all-deletions diff for an UNTRACKED file still on disk is warned about" "phantom-deletion-diff"
rm -f "$(cd "$DIR/../.." && pwd)/$TG_PHANTOM"
check_inject silent "$(inject_json 'git diff somebranch -- gone/never-existed.sh' ' gone/never-existed.sh | 462 ------
 1 file changed, 462 deletions(-)')" \
    "trapguard CONTROL: the SAME output for an absent path stays silent"
check_inject silent "$(inject_json 'git diff somebranch' ' .claude/hooks/test-hooks.sh | 20 +++---
 1 file changed, 12 insertions(+), 8 deletions(-)')" \
    "trapguard CONTROL: a normal mixed diff stays silent"
check_inject silent "$(inject_json 'git diff --cached somebranch' ' .claude/hooks/test-hooks.sh | 462 ------
 1 file changed, 462 deletions(-)')" \
    "trapguard CONTROL: --cached is exempt (the index IS the subject there)"
# THE FALSE POSITIVE THIS RULE SHIPPED WITH, for one hour. A TRACKED file that
# simply lost lines is a normal diff, and the first version fired on it because
# it keyed on "the file exists". Existence narrows; tracked-ness decides.
check_inject silent "$(inject_json 'git diff --stat package-lock.json' ' package-lock.json | 27 -------
 1 file changed, 27 deletions(-)')" \
    "trapguard CONTROL: a TRACKED file losing lines is an ordinary diff, not a phantom"

# interrupted-cleanup-skipped. Written the same hour it was paid for: a mutation
# test neutered a guard in the live tree, ran the suite, and restored it on the
# next line; the suite outlived the 2-minute tool timeout, the command took
# SIGTERM, and the restore never ran. The output ended on "mutated: guard
# neutered", which is TRUE and reads like a finished step.
inject_killed() { # inject_killed <command> <stdout> <interrupted-bool>
    python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","cwd":sys.argv[1],"tool_input":{"command":sys.argv[2]},"tool_response":{"stdout":sys.argv[3],"stderr":"","interrupted":sys.argv[4]=="true"}}))' "$(cd "$DIR/../.." && pwd)" "$1" "$2" "$3"
}
check_inject fires "$(inject_killed 'python3 -c mutate; bash suite.sh; cp /tmp/worklist.py.orig .claude/hooks/stop/worklist.py' 'mutated: guard neutered' true)" \
    "trapguard: an interrupted command whose tail was a restore is warned about" "interrupted-cleanup-skipped"
# The two conditions are INDEPENDENT alternatives, not one gated behind the
# other, which is the exact defect review found in the sibling rule: the harness
# reports a kill through `interrupted` on some paths and the timeout text on
# others, so either alone must be enough.
check_inject fires "$(inject_killed 'mutate.sh; bash suite.sh; git checkout -- src/x.py' 'Command timed out after 2m 0s' false)" \
    "trapguard: the timeout TEXT alone fires without the interrupted flag" "interrupted-cleanup-skipped"
check_inject fires "$(inject_killed 'mutate.sh; bash suite.sh; cp x.orig x' '' true)" \
    "trapguard: the interrupted FLAG alone fires without the timeout text" "interrupted-cleanup-skipped"
check_inject silent "$(inject_killed 'mutate.sh; bash suite.sh; cp /tmp/x.orig src/x.py' 'all done' false)" \
    "trapguard CONTROL: the same command completing is not warned about"
# A restore that IS the command has no earlier step it could have stranded.
check_inject silent "$(inject_killed 'git restore src/x.py' '' true)" \
    "trapguard CONTROL: a bare restore with no preceding step stays silent"
check_inject silent "$(inject_killed 'npm test; echo done' 'Command timed out after 2m 0s' true)" \
    "trapguard CONTROL: interrupted with nothing to put back stays silent"

check 0 pre-bash/block-nondraft-pr-create.sh "$(bash_json 'cd private/renet && gh pr create --title x --body y')" "nondraft-create: plain create on private submodule ok"
check 0 pre-bash/block-nondraft-pr-create.sh "$(bash_json 'gh pr list --repo rediacc/console')" "nondraft-create: non-create command ignored"
check 0 pre-bash/block-premature-ready.sh "$(bash_json 'gh pr ready 531 --undo')" "premature-ready: --undo always allowed"
check 0 pre-bash/block-premature-ready.sh "$(bash_json 'gh pr view 531')" "premature-ready: non-ready command ignored"
# Regression: the phrase inside heredoc/doc prose is NOT an invocation. The
# unanchored v1 fired on a round-log heredoc that merely mentioned the flow.
check 0 pre-bash/block-premature-ready.sh "$(bash_json $'cat >> log.md <<EOF\ngreen-gated `gh pr ready` + hook-banned --admin\nEOF')" "premature-ready: prose mention in heredoc ignored"
check 0 pre-bash/block-admin-merge.sh "$(bash_json $'cat >> log.md <<EOF\nthe old flow used gh pr merge --admin, now banned\nEOF')" "admin-merge: prose mention in heredoc ignored"
# Even a command-position-looking mention inside a heredoc BODY is data, not a
# command, and must not fire (heredoc-body stripping, the FP that fired on a
# worklist write).
check 0 pre-bash/block-admin-merge.sh "$(bash_json $'cat >> log.md <<EOF\n; gh pr merge 531 --admin\nEOF')" "admin-merge: command-position mention in heredoc body ignored"
# Regression: a multi-line quoted COMMIT MESSAGE mentioning the commands (with
# prose semicolons and even "--admin") is not an invocation. v2 fired on this.
COMMITMSG=$'git commit -m "feat: x\n\n- gh pr ready is hook-gated; gh pr merge --admin is banned" && git push'
check 0 pre-bash/block-premature-ready.sh "$(bash_json "$COMMITMSG")" "premature-ready: quoted commit-msg mention ignored"
check 0 pre-bash/block-admin-merge.sh "$(bash_json "$COMMITMSG")" "admin-merge: quoted commit-msg --admin mention ignored"
# --auto on a rediacc repo now verifies review hygiene LIVE (report reply +
# threads), which this offline harness cannot assert, and that path is covered
# by the hook's manual live proofs. Offline we prove the non-rediacc
# early-exit still holds for --auto.
check 0 pre-bash/block-admin-merge.sh "$(bash_json 'gh pr merge 7 --squash --auto --repo otherorg/tool')" "admin-merge: --auto on non-rediacc repo ignored"
check 0 pre-bash/block-admin-merge.sh "$(bash_json 'gh pr checks 531')" "admin-merge: non-merge command ignored"
# Round-46 cross-attribution, the exact live firing: a sibling `gh pr view`
# donated its --repo to the merge's PR number, resolving a DIFFERENT repo's
# PR #66 (long merged, one unresolved thread) and blocking a clean merge.
# With the segment fix this stays a foreign-repo no-op and never hits the
# network; with the bug it resolves rediacc/renet and blocks.
check 0 pre-bash/block-admin-merge.sh "$(bash_json 'gh pr view 94 --repo rediacc/renet; gh pr merge 66 --repo otherorg/tool')" "admin-merge: sibling gh --repo does not donate to the merge segment"
# NOT asserted here: per-segment --auto and per-segment PR selectors on
# block-admin-merge. Both only change behavior once a rediacc repo is
# resolved, which puts them on the network path this offline harness cannot
# drive (same limitation as the NOTE above). They are covered by the hook's
# live proofs, not by a case that would pass either way -- a green assertion
# that cannot fail is worse than no assertion.
check 0 pre-bash/block-git-amend.sh "$(bash_json 'git status')" "amend: benign"
check 0 pre-bash/block-ssh-docker.sh "$(bash_json 'ssh 192.168.111.1 docker ps')" "ssh-docker: bridge allowed"
check 0 pre-bash/block-ssh-file-write.sh "$(bash_json 'ssh host "cat /etc/criu/runc.conf 2>&1; ls"')" "ssh-file-write: stderr redirect is a read"
check 0 pre-bash/block-ssh-file-write.sh "$(bash_json 'ssh host "cat /var/log/x >/dev/null 2>&1"')" "ssh-file-write: dev-null read ok"
check 0 pre-bash/block-long-sleep.sh "$(bash_json 'sleep 10')" "long-sleep: 10s ok"
# The sanctioned terminal-state CI watch (see .claude/agents/pr-babysitter.md) must pass all three CI-poll guards.
WATCH='R=123; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs'
check 0 pre-bash/block-ci-polling.sh "$(bash_json "$WATCH")" "ci-polling: terminal-state watch ok"
check 0 pre-bash/block-ci-reverse-poll.sh "$(bash_json "$WATCH")" "ci-reverse-poll: terminal-state watch ok"
check 0 pre-bash/block-long-sleep.sh "$(bash_json "$WATCH")" "long-sleep: terminal-state watch ok"
check 0 pre-bash/block-git-force-push.sh "$(bash_json 'git push')" "force-push: plain push ok"
check 0 pre-bash/block-worktree-add.sh "$(bash_json 'git worktree list')" "worktree-add: list ok"
check 0 pre-bash/block-worktree-add.sh "$(bash_json 'git worktree remove ../foo')" "worktree-add: remove ok"
check 0 pre-bash/block-worktree-add.sh "$(bash_json 'git status')" "worktree-add: unrelated git command ok"
check 0 pre-bash/block-worktree-add.sh "$(bash_json 'echo "lets talk about git worktree add sometime"')" "worktree-add: quoted prose mention ignored"
check 0 pre-edit/block-suppressions.sh "$(edit_json 'const x = 1;')" "suppressions: clean"
# INVERTED 2026-08-09: a well-shaped whole-file Write used to PASS here, and
# that is the hole the incident went through. It is now denied like every other
# direct write, and it lives up in the deny block above only in spirit -- it is
# asserted here, beside its controls, so the pair reads as one decision.
check_out 2 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/agent/deadbeef/STATE.md content "$STATE_GOOD")" "agent-state: well-shaped Write is ALSO blocked (shape was never the defect)" "worklist.py --state"
# The controls that keep the guard from being a blanket denial: it must not
# reach RULES.md (sharpened by ordinary edits), the root-level plans, the
# tree's own README, or anything outside the notes tree at all.
#
# EVERY ONE OF THESE IS A NEGATIVE: exit 0 is also what a guard that matches
# NOTHING returns, so they cannot tell a live guard from a dead one and they
# are not trying to. Their job is the opposite one -- to catch a pattern that
# grew too broad -- and `agent` without the leading dot is an ordinary word,
# which is exactly when that stops being hypothetical. The positives above are
# what proves the guard fires at all: break the pattern in the hook so it
# matches nothing, and THEY go red while every line below stays green. That
# one-minute mutation is how this block was checked rather than assumed.
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Edit /r/agent/RULES.md new_string sharpen)" "agent-state: the shared RULES.md edits untouched"
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Edit /r/agent/deadbeef/RULES.md new_string sharpen)" "agent-state: a session's own RULES.md untouched"
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/packages/cli/src/foo.ts content tiny)" "agent-state: non-agent files untouched"
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/.agent/TRAPS.md content "$STATE_GOOD")" "agent-state: TRAPS.md untouched"
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/agent/README.md content "$STATE_GOOD")" "agent-state: the notes tree README untouched"
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/agent/PLAN-thing.md content "$STATE_GOOD")" "agent-state: root-level plan files untouched"
# The docs trees are committed prose that this guard must not own, and they are
# the paths a `*/agent/*/STATE.md` pattern would swallow by accident. Both
# names are asserted: the standing docs live in docs/agent-reference/ since the
# 2026-08-14 move, and docs/agent/ is what that tree was called before.
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/docs/agent/b/s/STATE.md content "$STATE_GOOD")" "agent-state: docs/agent/ is not this guard's tree"
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/docs/agent-reference/b/s/STATE.md content "$STATE_GOOD")" "agent-state: docs/agent-reference/ is not this guard's tree either"
check 0 pre-edit/block-inline-workflow-run.sh "$(wf_edit_json '.github/workflows/x.yml' "$WF_THIN")" "inline-workflow-run: thin block ok"
check 0 pre-edit/block-inline-workflow-run.sh "$(wf_edit_json 'packages/cli/src/foo.ts' "$WF_FAT")" "inline-workflow-run: non-workflow file ok"

# --- warn-remote-drift: needs a real repo pair (a bare origin, a stale local),
# because its subject is git state, not the command string. The origin is a
# filesystem path so the hook's fetch works offline.
DRIFT_TMP="$(mktemp -d)"
git init -q --bare -b main "$DRIFT_TMP/origin.git"
git clone -q "$DRIFT_TMP/origin.git" "$DRIFT_TMP/writer" 2>/dev/null
git -C "$DRIFT_TMP/writer" -c user.email=t@t -c user.name=t commit -q --allow-empty -m c1
git -C "$DRIFT_TMP/writer" push -q origin main 2>/dev/null
git clone -q "$DRIFT_TMP/origin.git" "$DRIFT_TMP/stale" 2>/dev/null
git -C "$DRIFT_TMP/writer" -c user.email=t@t -c user.name=t commit -q --allow-empty -m c2
git -C "$DRIFT_TMP/writer" push -q origin main 2>/dev/null
export CLAUDE_PROJECT_DIR="$DRIFT_TMP/stale"
check 2 pre-bash/warn-remote-drift.sh "$(bash_json 'git push')" "remote-drift: push from a stale local is blocked"
export CLAUDE_PROJECT_DIR="$DRIFT_TMP/writer"
check 0 pre-bash/warn-remote-drift.sh "$(bash_json 'git push')" "remote-drift: aligned local pushes freely"
check 0 pre-bash/warn-remote-drift.sh "$(bash_json 'git status')" "remote-drift: non-push commands untouched"

# --- pr-babysit ROUND LOG: the truncation guard, both directions ------------
# On 2026-08-19 a heartbeat tick refreshed the STATUS block with
# `p.write_text(s[:i] + new)`, which replaces from the STATUS heading to END OF
# FILE and silently deleted the entire round-history appendix, on a file with no
# backup. Two guards close it: a pre-edit one for whole-file tool writes, and a
# pre-bash one for the Bash heredoc that actually did it. Both must also NOT
# block the legitimate shapes, which is why every deny below has an allow beside
# it -- a guard that blocks everything gets routed around, and being routed
# around is worse than a named residual.
RLOG='/home/x/.claude/projects/-home-muhammed-monorepo-console/reports/pr-babysit-0818-1.md'
RL_HEREDOC="python3 - <<'PY'
from pathlib import Path
p=Path('$RLOG'); s=p.read_text(); i=s.index('## STATUS')
p.write_text(s[:i] + new)
PY"
check 2 pre-edit/block-roundlog-write.sh "$(tool_json Write "$RLOG" content x)" "roundlog: a whole-file Write is blocked"
check 0 pre-edit/block-roundlog-write.sh "$(tool_json Edit "$RLOG" new_string x)" "roundlog: a targeted Edit passes (it cannot swallow an unnamed appendix)"
check 0 pre-edit/block-roundlog-write.sh "$(tool_json Write /r/reports/pr-babysit-0818-1-briefing.md content x)" "roundlog: a briefing has its own contract, not this guard's"
check 0 pre-edit/block-roundlog-write.sh "$(tool_json Write packages/www/src/x.astro content x)" "roundlog: an unrelated file is untouched"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "$RL_HEREDOC")" "roundlog: the exact 2026-08-19 heredoc is blocked"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "echo hi > $RLOG")" "roundlog: truncating redirection is blocked"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "sed -i s/a/b/ $RLOG")" "roundlog: sed -i is blocked"
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json "echo hi >> $RLOG")" "roundlog: appending passes (it cannot truncate)"
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json "grep -n STATUS $RLOG")" "roundlog: reading passes"
# THE UNDER-BLOCK REGRESSIONS, found in review 2026-08-19 and each reproduced against the
# live hook before it was fixed. All three are ways a command that genuinely TRUNCATES the
# log was waved through, which is worse than an over-block: the guard reported safety it
# was not providing. Every one has an allow-twin below so the fix cannot be "block more
# until quiet".
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "tee --output-error=warn $RLOG")" "roundlog: tee --output-error=warn truncates, and is not an -a"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "tee -a /tmp/other.txt | tee $RLOG")" "roundlog: a decoy -a on another file does not license a bare tee"
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json "tee --append $RLOG")" "roundlog: long --append is a real append"
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json "tee -ai $RLOG")" "roundlog: a short bundle containing a is a real append"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "tee $RLOG")" "roundlog: a bare tee still truncates"
# cp names the log as a SOURCE here, which is a read, and backing the log up is the most
# useful thing a session can do with it. mv in the same position is NOT a read: it removes
# the log from its path, so the two verbs are deliberately treated differently.
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json "cp $RLOG /tmp/backup.md")" "roundlog: cp with the log as SOURCE is a read"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "cp /tmp/new.md $RLOG")" "roundlog: cp ONTO the log still blocked"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "mv $RLOG /tmp/backup.md")" "roundlog: mv away removes the log, still blocked"
# THE OVER-BLOCK REGRESSIONS. Found in review, then reproduced twice against the
# live hook within minutes: the truncating verbs were matched ANYWHERE in the
# command rather than anchored to the log, so `truncate` hit this script's own
# filename and a bare `cp`/`mv` hit a copy of unrelated files that merely shared
# a command line with a round-log READ. The guard blocked `cat <log>`. Each case
# below is one of those, and each has a still-blocks twin above or below it, so
# the fix cannot be "loosen until quiet".
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json "cp /tmp/a /tmp/b && grep STATUS $RLOG")" "roundlog: an unrelated cp beside a read passes"
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json "grep STATUS $RLOG && mv /tmp/x /tmp/y")" "roundlog: an unrelated mv beside a read passes"
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json "ls .claude/hooks/pre-bash/block-roundlog-truncate.sh; cat $RLOG")" "roundlog: the hook's OWN filename beside a read passes"
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json "tee -a $RLOG < /tmp/x")" "roundlog: tee -a passes (it cannot truncate)"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "cp /tmp/x $RLOG")" "roundlog: cp ONTO the log is blocked"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "mv /tmp/x $RLOG")" "roundlog: mv ONTO the log is blocked"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "tee $RLOG < /tmp/x")" "roundlog: tee WITHOUT -a is blocked"
check 2 pre-bash/block-roundlog-truncate.sh "$(bash_json "truncate -s 0 $RLOG")" "roundlog: truncate on the log is blocked"
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json "worklist.py --roundlog 0818-1")" "roundlog: the sanctioned verb passes"
check 0 pre-bash/block-roundlog-truncate.sh "$(bash_json 'npm run ci')" "roundlog: an unrelated command is untouched"
unset CLAUDE_PROJECT_DIR
rm -rf "$DRIFT_TMP"

# The Stop gate carries its own suite, because its cases need fixtures (a fake
# task dir, a planted transcript, a gh shim) rather than the single-JSON-on-stdin
# shape every case above uses. Delegating keeps both readable, and running it
# from here is what makes it reachable: a test nothing invokes is dead code, and
# the dead-bash gate is right to say so.
# The round-log splice's own controls. Separate from the two guard hooks above:
# those prove the WRONG way is blocked, this proves the RIGHT way preserves the
# appendix, and it carries a control asserting the naive splice still destroys
# it, so the suite cannot quietly stop reproducing the bug it was written for.
RLOG_MOD="$DIR/stop/wl_roundlog.py"
if [[ -f "$RLOG_MOD" ]]; then
    if out="$(python3 "$RLOG_MOD" --selftest 2>&1)"; then
        n=$(grep -c "^  PASS " <<<"$out")
        PASS=$((PASS + n))
        echo "ok   [0] stop/wl_roundlog.py --selftest: $n control(s) passed"
    else
        FAIL=$((FAIL + 1))
        echo "FAIL [1] stop/wl_roundlog.py --selftest"
        grep -E "^  FAIL " <<<"$out" | sed 's/^/       /'
    fi
else
    FAIL=$((FAIL + 1))
    echo "FAIL [1] stop/wl_roundlog.py missing"
fi

# The plan-fidelity check's own controls (stop/wl_planfid.py). Separate from the
# stop suite below, which drives the whole hook: these are the unit-level
# controls that prove the instrument can FIRE on the real 2026-08-19 incident
# (two umbrella items for a four-wave approved plan) and stays SILENT on the
# operator's own correction of it, plus every verification that stands between a
# model claim and a block.
PLANFID_MOD="$DIR/stop/wl_planfid.py"
if [[ -f "$PLANFID_MOD" ]]; then
    if out="$(python3 "$PLANFID_MOD" --selftest 2>&1)"; then
        n=$(grep -c "^  PASS " <<<"$out")
        PASS=$((PASS + n))
        echo "ok   [0] stop/wl_planfid.py --selftest: $n control(s) passed"
    else
        FAIL=$((FAIL + 1))
        echo "FAIL [1] stop/wl_planfid.py --selftest"
        grep -E "^  FAIL " <<<"$out" | sed 's/^/       /'
    fi
else
    FAIL=$((FAIL + 1))
    echo "FAIL [1] stop/wl_planfid.py missing"
fi

STOP_SUITE="$DIR/stop/test-worklist-v5.sh"
if [[ -x "$STOP_SUITE" ]]; then
    echo
    if out="$(bash "$STOP_SUITE" 2>&1)"; then
        n=$(grep -c "^  PASS:" <<<"$out")
        PASS=$((PASS + n))
        echo "ok   [0] stop/test-worklist-v5.sh: $n case(s) passed"
    else
        FAIL=$((FAIL + 1))
        echo "FAIL [1] stop/test-worklist-v5.sh"
        # THE FAILING CASES FIRST, then context. This used to be `tail -20`,
        # which prints the LAST twenty lines -- in a 575-case suite those are
        # almost always PASS lines plus the summary, so the FAIL lines scroll
        # past and CI reports "12 failed" while naming none of them. A failure
        # report that hides the failures forces a re-run to learn anything, and
        # when the failure only reproduces in CI (as this one did) there is no
        # local run to fall back on.
        echo "       --- failing cases ---"
        grep -E "^\s*(FAIL|  - )" <<<"$out" | sed 's/^/       /' | head -40
        echo "       --- tail for context ---"
        sed 's/^/       /' <<<"$out" | tail -12
    fi
else
    FAIL=$((FAIL + 1))
    echo "FAIL [1] stop/test-worklist-v5.sh missing or not executable"
fi

# The report-inbox suite, which this aggregate runner did NOT run. Found by a
# sub-agent while adding cases to it: 125 cases covering the report inbox and
# the whole cross-session waiter/nudge mechanism were invisible here, so a break
# in any of them passed `test-hooks.sh` in silence. Its own header (:5-7) says
# the cases were meant to migrate into the v5 harness "once it frees"; that
# never happened, and the gap outlived the note. Mirrors the STOP_SUITE wiring
# above rather than inventing a second reporting shape.
INBOX_SUITE="$DIR/stop/test-report-inbox.sh"
if [[ -x "$INBOX_SUITE" ]]; then
    echo
    if out="$(bash "$INBOX_SUITE" 2>&1)"; then
        # This suite prints `ok <case>`, NOT the v5 harness's `  PASS:`. Copying
        # the v5 counter verbatim made it count 0 and still report "ok ...
        # 0 case(s) passed" -- a green that verified nothing, which is the exact
        # defect this block was added to close. Refuse a zero count outright.
        n=$(grep -cE "^[[:space:]]*ok[[:space:]]" <<<"$out")
        if [[ "$n" -eq 0 ]]; then
            FAIL=$((FAIL + 1))
            echo "FAIL [1] stop/test-report-inbox.sh: exited 0 but reported 0 cases"
        else
            PASS=$((PASS + n))
            echo "ok   [0] stop/test-report-inbox.sh: $n case(s) passed"
        fi
    else
        FAIL=$((FAIL + 1))
        echo "FAIL [1] stop/test-report-inbox.sh"
        echo "       --- failing cases ---"
        grep -E "^\s*(FAIL|  - )" <<<"$out" | sed 's/^/       /' | head -40
        echo "       --- tail for context ---"
        sed 's/^/       /' <<<"$out" | tail -12
    fi
else
    FAIL=$((FAIL + 1))
    echo "FAIL [1] stop/test-report-inbox.sh missing or not executable"
fi

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == 0 ]]
