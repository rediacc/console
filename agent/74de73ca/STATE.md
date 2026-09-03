## SESSION 74de73ca 2026-09-03T12:05:03Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** — `6ba240362..535b25a01`. The
working tree is CLEAN; nothing is uncommitted any more. This is a change from every
earlier version of this document, which said the operator pushes: the CI-watch task
explicitly asked for commit-and-push, and the push guard allowed it.

## What is on the branch now (7 new commits, all `PR-TASK: 24c98380`)

`535b25a01` docs(traps) · `b5c02fe11` check:format widening · `44659d249` profiling
layer · `5d470cee9` shadow-compare extraction · `bb8aa55ea` onboarding notice ·
`644a4d071` worklist lineage · `7efc4f7ef` www bundle budget.

`ci:quick` was **292/292 exit 0** on the exact committed tree before pushing.

## The three CI failures this watch fixed

1. **Plan file housekeeping** — `quality-i18n`'s `actions/checkout` had no `with:`, so
   the topology-reading gate refused ("99 commit(s) reachable, 1 graft"). Added
   `fetch-depth: 0` + `filter: blob:none`. Cannot reproduce locally: a dev clone is deep.
2. **Client bundle budget** — NOT the non-determinism the old worklist note claimed. The
   gate under-reported by 124,673 B (its regex demanded whitespace after `import`).
   Fixed, split eager/deferred, and the page changed so the deferral is real.
3. **PR description freshness** — title and body rewritten for the real 48-commit scope.

## Two things that will bite a fresh session

* `gh pr edit --body` is **hook-blocked** and `--body-file` **fails** on a
  Projects-classic GraphQL deprecation. The working form, which the repo's own
  `refresh-pr-body.sh:83` uses, is
  `gh api repos/rediacc/console/pulls/585 -X PATCH -F body=@file`. Keep both
  `worklist-epics` and `pushed-head` marker pairs in whatever you write.
* Commits need a `PR-TASK: <epic>` trailer and must NOT carry `Co-Authored-By` or
  "Generated with" lines — `block-commit-meta.sh` refuses them, whatever the ambient
  attribution guidance says.

## Next action

1. **A CI watch is armed in the background** (`.ci/scripts/ci/ci-trace.py --wait`,
   task `brfvemjgk`) on the pushed head. On its result: if green, stop. If a job failed,
   read that JOB's conclusion — not the run's — because a cancelled run reports nothing,
   and this branch has been fooled by that twice.
2. **`[?] #13d281a2` is now unblocked and is the next real work.** The push has happened,
   so once CI is green run `scripts/dev/derive-shadow-pass-list.sh --branch 0903-1` and
   execute exactly the `gh secret delete` lines it prints — no more. It refuses if no
   passing compare exists and skips any org name shadowed by a repo-level twin.
3. Seed the profiling baseline only after several days of real runs:
   `check_resprofile.py --seed <run-dir>`. Unseeded means nothing is enforced yet.
4. `bws` lives at `$CLAUDE_JOB_DIR/tmp/bws` and needs `--color no`; the Bitwarden token
   in `private/account/.env` **expires 2026-09-08**.
