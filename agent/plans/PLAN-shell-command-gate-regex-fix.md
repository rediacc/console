# PLAN: Fix the two dead-branch regex bugs in `check:ci-shell-commands` (bash twin + Python port + tests + ledger)
Status: compacted
First-Seen: 2026-09-20
Owner: f4da5c2e
Full-Text-Blob: 330e4e7fe9c7c52a3fb4e8de486624d83621ee04
Record-Sig: 21dbbbfb

## Why
Two independent regex bugs in the `check:ci-shell-commands` CI gate made two classes of disallowed commands invisible: a broken `\$\(` escape sequence and a missing `if` branch in the narrow per-command check. An initial blast-radius measurement appeared to show 0 findings, but re-measurement with corrected directory context revealed 46 real violations across the .ci/ and scripts/
corpus.

## Outcome
Landed. Fixed four files: bash twin and Python port regexes (both `\$\(` escapes), test file with two tests renamed and one plant rewritten, and ledger re-recorded. 46 findings fixed: 40 loop rewrites `for VAR in $(seq A B)` → `for ((VAR=A; VAR<=B; VAR++))`, with 6 renaming `_` to `_i` to avoid bash parameter clobbering; 1 timeout fixed for set -e survival; 1 allowlisted as false
positive.

## Lessons
- Blast-radius measurement of a self-locating script must verify ROOT_DIR resolution—running from scratchpad silently breaks scope to nothing without warning.
- Bash's `_` parameter (last argument) is reassigned by every command in a loop body—must rename to `_i` when rewriting `for _ in $(seq...)` to arithmetic form.
- Under `set -e`, bare `wait "$pid"; rc=$?` fails—use `wait "$pid" || rc=$?` to survive errexit.
- A single logical finding (regex bugs) surfaced 46 heterogeneous violations; cluster triage needs direct measurement before dismissing as mechanical.
- The directory context where a measurement script runs is load-bearing for validity; verify corpus path resolves to real repo, not scratchpad.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:01:19Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: package.json, .github/workflows/ci-quality.yml, .ci/scripts/security/check-commands.sh, .ci/rediacc_ci/security/check_commands.py, .ci/scripts/test/gates/test-profiler-report.sh, .ci/tutorials/tutorial-branching.sh, .ci/lib/account.sh, .ci/tutorials/tutorial-networking.sh, .ci/tutorials/tutorial-managing-secrets.sh, .ci/tutorials/tutorial-vscode-browser.sh, .ci/tutorials/lib/stage-branching.sh, .ci/tutorials/tutorial-add-server.sh, .ci/tutorials/tutorial-work-with-repo.sh, .ci/tutorials/tutorial-monitoring.sh, .ci/tutorials/tutorial-backup-restore.sh, .ci/tutorials/tutorial-production-mode.sh, .ci/tutorials/tutorial-create-repo.sh, .ci/tutorials/tutorial-delta-transfer.sh, .ci/tutorials/tutorial-deploy-app.sh, .ci/tutorials/tutorial-forking.sh
Gates: check:ci-dead-python, check:ci-plan-citations, check:ci-pytest, check:ci-python-lint, check:ci-shell-commands
Why-Source: model
Read-History: `git show 330e4e7fe9c7c52a3fb4e8de486624d83621ee04` recovers the text; `git log --find-object=330e4e7fe9c7c52a3fb4e8de486624d83621ee04 --all` names the commit

## History
- 2026-09-20T18:01:19Z compacted by d778be9d from `draft` (record-sig 21dbbbfb)
