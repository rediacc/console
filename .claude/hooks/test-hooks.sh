#!/usr/bin/env bash
# Smoke-test every guard hook by feeding sample tool_input JSON and asserting the exit code.
# Usage: bash .claude/hooks/test-hooks.sh   (run after `/hooks` reload; needs jq)
# NOTE: suppression test tokens are concatenated at runtime ("@ts-""ignore") so this file's
# text never contains the literal banned token — otherwise the suppressions guard blocks it.
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

bash_json() { printf '{"tool_input":{"command":%s}}' "$(jq -Rn --arg c "$1" '$c')"; }
edit_json() { printf '{"tool_input":{"new_string":%s}}' "$(jq -Rn --arg c "$1" '$c')"; }
multiedit_json() { printf '{"tool_input":{"edits":[{"new_string":%s}]}}' "$(jq -Rn --arg c "$1" '$c')"; }
# wf_edit_json <file_path> <new_string> — Edit payload carrying a target file path.
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
# STATE.md shape guard: the CLI refusal alone is bypassed by a raw Write (the
# document lives at a plain repo path), so the guard is the closing half.
check 2 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/.agent/b/STATE.md content tiny)" "agent-state: thin Write blocked"
check 2 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/.agent/b/STATE.md content "$STATE_AIMLESS")" "agent-state: aimless Write (no Next action) blocked"
check 2 pre-edit/block-agent-state-shape.sh "$(tool_json Edit /r/.agent/b/STATE.md new_string patch)" "agent-state: Edit blocked (rewrite, never append)"

# --- should PASS (exit 0) ---
# NOTE: block-premature-ready.sh and block-admin-merge.sh verify live CI/thread
# state over the network on their enforcement paths; only their pattern paths
# (--undo, --auto, --draft flags, non-matching commands) are unit-tested here.
check 0 pre-bash/block-nondraft-pr-create.sh "$(bash_json 'gh pr create --draft --title x --body y')" "nondraft-create: console with --draft ok"
check 0 pre-bash/block-nondraft-pr-create.sh "$(bash_json 'cd private/renet && gh pr create --title x --body y')" "nondraft-create: plain create on private submodule ok"
check 0 pre-bash/block-nondraft-pr-create.sh "$(bash_json 'gh pr list --repo rediacc/console')" "nondraft-create: non-create command ignored"
check 0 pre-bash/block-premature-ready.sh "$(bash_json 'gh pr ready 531 --undo')" "premature-ready: --undo always allowed"
check 0 pre-bash/block-premature-ready.sh "$(bash_json 'gh pr view 531')" "premature-ready: non-ready command ignored"
# Regression: the phrase inside heredoc/doc prose is NOT an invocation. The
# unanchored v1 fired on a round-log heredoc that merely mentioned the flow.
check 0 pre-bash/block-premature-ready.sh "$(bash_json $'cat >> log.md <<EOF\ngreen-gated `gh pr ready` + hook-banned --admin\nEOF')" "premature-ready: prose mention in heredoc ignored"
check 0 pre-bash/block-admin-merge.sh "$(bash_json $'cat >> log.md <<EOF\nthe old flow used gh pr merge --admin, now banned\nEOF')" "admin-merge: prose mention in heredoc ignored"
# Even a command-position-looking mention inside a heredoc BODY is data, not a
# command, and must not fire (heredoc-body stripping — the FP that fired on a
# worklist write).
check 0 pre-bash/block-admin-merge.sh "$(bash_json $'cat >> log.md <<EOF\n; gh pr merge 531 --admin\nEOF')" "admin-merge: command-position mention in heredoc body ignored"
# Regression: a multi-line quoted COMMIT MESSAGE mentioning the commands (with
# prose semicolons and even "--admin") is not an invocation. v2 fired on this.
COMMITMSG=$'git commit -m "feat: x\n\n- gh pr ready is hook-gated; gh pr merge --admin is banned" && git push'
check 0 pre-bash/block-premature-ready.sh "$(bash_json "$COMMITMSG")" "premature-ready: quoted commit-msg mention ignored"
check 0 pre-bash/block-admin-merge.sh "$(bash_json "$COMMITMSG")" "admin-merge: quoted commit-msg --admin mention ignored"
# --auto on a rediacc repo now verifies review hygiene LIVE (report reply +
# threads), which this offline harness cannot assert — that path is covered
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
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/.agent/b/STATE.md content "$STATE_GOOD")" "agent-state: well-shaped Write passes"
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Edit /r/.agent/b/RULES.md new_string sharpen)" "agent-state: RULES.md edits untouched"
check 0 pre-edit/block-agent-state-shape.sh "$(tool_json Write /r/packages/cli/src/foo.ts content tiny)" "agent-state: non-agent files untouched"
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
unset CLAUDE_PROJECT_DIR
rm -rf "$DRIFT_TMP"

# The Stop gate carries its own suite, because its cases need fixtures (a fake
# task dir, a planted transcript, a gh shim) rather than the single-JSON-on-stdin
# shape every case above uses. Delegating keeps both readable, and running it
# from here is what makes it reachable: a test nothing invokes is dead code, and
# the dead-bash gate is right to say so.
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

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == 0 ]]
