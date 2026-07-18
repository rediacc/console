#!/usr/bin/env bash
# Smoke-test every guard hook by feeding sample tool_input JSON and asserting the exit code.
# Usage: bash .claude/hooks/test-hooks.sh   (run after `/hooks` reload; needs jq)
# NOTE: suppression test tokens are concatenated at runtime ("@ts-""ignore") so this file's
# text never contains the literal banned token — otherwise the suppressions guard blocks it.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0; FAIL=0

# check <expected-exit> <script-relative-path> <json-stdin> <label>
check() {
  local expected="$1" script="$2" json="$3" label="$4" rc
  echo "$json" | bash "$DIR/$script" >/dev/null 2>&1
  rc=$?
  if [[ "$rc" == "$expected" ]]; then
    PASS=$((PASS+1)); printf 'ok   [%s] %s (exit %s)\n' "$expected" "$label" "$rc"
  else
    FAIL=$((FAIL+1)); printf 'FAIL [%s] %s (got exit %s)\n' "$expected" "$label" "$rc"
  fi
}

bash_json() { printf '{"tool_input":{"command":%s}}' "$(jq -Rn --arg c "$1" '$c')"; }
edit_json() { printf '{"tool_input":{"new_string":%s}}' "$(jq -Rn --arg c "$1" '$c')"; }
multiedit_json() { printf '{"tool_input":{"edits":[{"new_string":%s}]}}' "$(jq -Rn --arg c "$1" '$c')"; }
# wf_edit_json <file_path> <new_string> — Edit payload carrying a target file path.
wf_edit_json() { printf '{"tool_input":{"file_path":%s,"new_string":%s}}' "$(jq -Rn --arg c "$1" '$c')" "$(jq -Rn --arg c "$2" '$c')"; }

# A fat (9 logic line) and a thin (2 logic line) inline `run:` block for the
# workflow-inline guard.
WF_FAT=$'      - name: Big\n        run: |\n          echo 1\n          echo 2\n          echo 3\n          echo 4\n          echo 5\n          echo 6\n          echo 7\n          echo 8\n          echo 9'
WF_THIN=$'      - name: Thin\n        run: |\n          echo hi\n          bash .ci/scripts/quality/x.sh'

# --- should BLOCK (exit 2) ---
check 2 pre-bash/block-protected-files.sh   "$(bash_json 'git checkout .claude/settings.json')" "protected-files"
check 2 pre-bash/block-commit-meta.sh       "$(bash_json 'git commit -m msg Co-Authored-By: bot')" "commit-meta"
check 2 pre-bash/block-binary-deploy.sh     "$(bash_json 'scp renet host:/tmp')" "binary-deploy"
check 2 pre-bash/block-cli-bundle.sh        "$(bash_json 'node packages/cli/dist/x.js')" "cli-bundle"
check 2 pre-bash/block-ssh-docker.sh        "$(bash_json 'ssh host docker ps')" "ssh-docker"
check 2 pre-bash/block-ssh-file-write.sh    "$(bash_json 'cat a | ssh host tee /etc/x')" "ssh-file-write"
check 2 pre-bash/block-ci-polling.sh        "$(bash_json 'sleep 5 && gh run view 1')" "ci-polling"
check 2 pre-bash/block-ci-reverse-poll.sh   "$(bash_json 'gh run view 1 --jq .x && sleep 5')" "ci-reverse-poll"
check 2 pre-bash/block-long-sleep.sh        "$(bash_json 'sleep 30')" "long-sleep"
check 2 pre-bash/block-git-amend.sh         "$(bash_json 'git commit --amend')" "git-amend"
check 2 pre-bash/block-git-force-push.sh    "$(bash_json 'git push --force')" "git-force-push"
check 2 pre-bash/block-git-empty-commit.sh  "$(bash_json 'git commit --allow-empty -m x')" "git-empty-commit"
check 2 pre-edit/block-suppressions.sh      "$(edit_json "a // @ts-""ignore")" "suppressions(new_string)"
check 2 pre-edit/block-suppressions.sh      "$(multiedit_json "b // eslint-""disable")" "suppressions(MultiEdit)"
check 2 pre-edit/block-inline-workflow-run.sh "$(wf_edit_json '.github/workflows/x.yml' "$WF_FAT")" "inline-workflow-run: 9-line block blocked"

# --- should PASS (exit 0) ---
check 0 pre-bash/block-git-amend.sh         "$(bash_json 'git status')" "amend: benign"
check 0 pre-bash/block-ssh-docker.sh        "$(bash_json 'ssh 192.168.111.1 docker ps')" "ssh-docker: bridge allowed"
check 0 pre-bash/block-ssh-file-write.sh    "$(bash_json 'ssh host "cat /etc/criu/runc.conf 2>&1; ls"')" "ssh-file-write: stderr redirect is a read"
check 0 pre-bash/block-ssh-file-write.sh    "$(bash_json 'ssh host "cat /var/log/x >/dev/null 2>&1"')" "ssh-file-write: dev-null read ok"
check 0 pre-bash/block-long-sleep.sh        "$(bash_json 'sleep 10')" "long-sleep: 10s ok"
# The sanctioned terminal-state CI watch (see .claude/agents/pr-babysitter.md) must pass all three CI-poll guards.
WATCH='R=123; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs'
check 0 pre-bash/block-ci-polling.sh        "$(bash_json "$WATCH")" "ci-polling: terminal-state watch ok"
check 0 pre-bash/block-ci-reverse-poll.sh   "$(bash_json "$WATCH")" "ci-reverse-poll: terminal-state watch ok"
check 0 pre-bash/block-long-sleep.sh        "$(bash_json "$WATCH")" "long-sleep: terminal-state watch ok"
check 0 pre-bash/block-git-force-push.sh    "$(bash_json 'git push')" "force-push: plain push ok"
check 0 pre-edit/block-suppressions.sh      "$(edit_json 'const x = 1;')" "suppressions: clean"
check 0 pre-edit/block-inline-workflow-run.sh "$(wf_edit_json '.github/workflows/x.yml' "$WF_THIN")" "inline-workflow-run: thin block ok"
check 0 pre-edit/block-inline-workflow-run.sh "$(wf_edit_json 'packages/cli/src/foo.ts' "$WF_FAT")" "inline-workflow-run: non-workflow file ok"

echo
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" == 0 ]]
