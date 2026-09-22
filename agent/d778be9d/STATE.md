## SESSION d778be9d 2026-09-22T06:40:49Z

# d778be9d STATE (branch 0914-1, PR #589; local only, no push, PR-TASK: e87fa3ce trailer on every commit)

## Where things stand
HEAD dd5dfba3c. Since eab2fe831 (2 scripts/ops files ported): dd5dfba3c removed 4 dead run-legacy.sh verbs (test, build, pr, check; 396 lines) and fixed a genuinely broken "./run.sh build renet" hint in doctor.ts. service/fix/clean stay bash: fix/clean are read as fixtures by test-run-sh.sh and its pytest port on both sides, service.sh has no other sourcer. 160 bash files remain in .ci/config/language-policy-baseline.json.
A writer (aed62bb44d8349960) is porting the remaining live run-legacy.sh verbs (help, dev, quality where not pinned by test-run-sh.sh) to Python; account/rotation/devbox/worktree are expected to mostly skip (their real logic lives in .ci/lib/*.sh, out of scope this session, or worktree touches real git state); progress in scratchpad/q-progress.txt.

## Next action
1. When the writer reports: spot-check, git add, run the ~20-gate set, commit by name with PR-TASK trailer.
2. After that: .ci/docker/run-in-{web,render}.sh (port from scratch, no port exists yet), the 8 unported bash gate tests (port to pytest per operator default), the 39-script real-run rehearsal (needs the operator's credentials -- prepare a batched checklist naming exactly which secrets/tools each script needs, do not run them without credentials), then W1P6 deletes .ci/config/language-policy-baseline.json once every remaining path is deleted or exempt.
3. Remaining libs (.ci/scripts/lib/*, .ci/lib/*) stay terminal until their sourcers (scripts/ops/drills/dev files, run-legacy.sh) are gone; only 2 of ~17 scripts/ops/drills/dev files ported so far, the rest have concrete blockers (goldens pinned by line number, live sourcers, real Cloudflare/R2/VM/licensing operations).
