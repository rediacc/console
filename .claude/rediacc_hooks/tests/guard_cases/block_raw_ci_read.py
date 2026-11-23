"""The test tables of `block_raw_ci_read`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    # --- refused: every CI_READ_VERBS row, plus the shapes the walk must see through ---
    ("pr checks", "gh pr checks 591"),
    ("pr checks --watch", "gh pr checks 591 --watch"),
    ("pr checks inside a substitution", 'echo "$(gh pr checks 591)"'),
    ("pr view with the rollup", "gh pr view 591 --json headRefOid,statusCheckRollup"),
    ("run list", "gh run list --branch 0930-1 --limit 5"),
    ("watchdog run list", 'gh run list --workflow "Watchdog Monitor" --limit 20'),
    ("run view --job --log", "gh run view --job 104569 --log"),
    ("run view --log-failed", "gh run view 36953549081 --log-failed"),
    ("run view json", "gh run view 36953549081 --json conclusion,jobs"),
    (
        "job log piped through sed and grep (the 2026-10-02 shape)",
        (
            "gh api repos/o/r/actions/jobs/104569/logs --allow-escape-sequences "
            "| sed 's/\\x1b\\[[0-9;]*m//g' | grep -n 'Error'"
        ),
    ),
    ("one job object", "gh api repos/o/r/actions/jobs/104569 --jq .steps"),
    ("run jobs, paginated", "gh api --paginate repos/o/r/actions/runs/36953549081/jobs"),
    (
        "attempt jobs, leading slash",
        "gh api /repos/o/r/actions/runs/36953549081/attempts/2/jobs",
    ),
    ("run log archive", "gh api repos/o/r/actions/runs/36953549081/logs > logs.zip"),
    ("run object", "gh api repos/o/r/actions/runs/36953549081 --jq .conclusion"),
    ("explicit GET", "gh api -X GET repos/o/r/actions/runs/36953549081"),
    (
        "workflow runs with a query string",
        "gh api 'repos/o/r/actions/workflows/ci.yml/runs?branch=0930-1'",
    ),
    ("check-run annotations", "gh api repos/o/r/check-runs/104569/annotations"),
    ("commit check-runs", "gh api repos/o/r/commits/1e7caef2/check-runs"),
    (
        "graphql rollup",
        (
            'gh api graphql -f query=\'{ repository(owner:"o", name:"r") '
            "{ pullRequest(number:591) { commits(last:1) { nodes { commit "
            "{ statusCheckRollup { state } } } } } } }'"
        ),
    ),
    ("inside sh -c", "sh -c 'gh run view 36953549081'"),
    # --- allowed: writes, carve-outs, and prose that only names a read ---
    ("CONTROL: rerun", "gh run rerun 36953549081 --failed"),
    ("CONTROL: cancel", "gh run cancel 36953549081"),
    ("CONTROL: download an artifact", "gh run download 36953549081 -n bridge-logs"),
    ("CONTROL: pr create", "gh pr create --draft --title t --body-file b.md"),
    ("CONTROL: pr edit", "gh pr edit 591 --add-label ci"),
    ("CONTROL: pr ready", "gh pr ready 591"),
    ("CONTROL: pr merge", "gh pr merge 591 --rebase"),
    ("CONTROL: pr comment", "gh pr comment 591 --body-file note.md"),
    ("CONTROL: pr view without rollup", "gh pr view 591 --json headRefOid,isDraft"),
    ("CONTROL: pulls/<n>", "gh api repos/o/r/pulls/591 --jq .head.sha"),
    ("CONTROL: issues", "gh api repos/o/r/issues/591/comments"),
    ("CONTROL: releases", "gh api repos/o/r/releases/latest"),
    ("CONTROL: artifacts", "gh api repos/o/r/actions/runs/36953549081/artifacts"),
    (
        "CONTROL: a check-run write (the DEFECT's target)",
        "gh api -X PATCH repos/o/r/check-runs/104569 -f status=completed",
    ),
    ("CONTROL: a body flag means POST", "gh api repos/o/r/check-runs -f name=x"),
    (
        "CONTROL: rerun-failed-jobs POST",
        "gh api -X POST repos/o/r/actions/runs/36953549081/rerun-failed-jobs",
    ),
    (
        "CONTROL: graphql without rollup fields",
        (
            'gh api graphql -f query=\'mutation { resolveReviewThread(input:{threadId:"T"}) '
            "{ thread { id } } }'"
        ),
    ),
    (
        "CONTROL: a commit message naming gh pr checks",
        'git commit -m "docs: gh pr checks is refused"',
    ),
    ("CONTROL: a heredoc body is data", "cat > note.md <<'EOF'\ngh run view 36953549081\nEOF"),
    ("CONTROL: the tracer itself", ".ci/scripts/ci/ci-trace.py --run 36953549081 --why"),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    ("a read launched by npx -c", "npx -c 'gh pr checks 591'"),
    ("CONTROL: prose naming a launched read", "echo npx -c gh pr checks 591"),
]
