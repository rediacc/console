## SESSION 97604f47 2026-08-18T03:40:48Z

Branch is now `main` (the `/pr-merge` of `0815-1` completed). `main` is READ-ONLY here: never push it, never commit to it. The next task starts with a fresh `MMDD-N` branch BEFORE any tracked file is edited.

## The landing is DONE

    console  #568 -> MERGED 2026-08-18T03:31:09Z, main = 8a03fe5ae
    renet    #103 -> d53e1d3b0
    account  #79  -> 0ca94c5ce
    elite    #15  -> 187e06385

All rebase-merged, judged by PR state (`git branch --merged` lies on these repos). Every pointer bump was made only after proving `git diff --stat <old-tip> <new-main>` was EMPTY.

The operator authorised the merge explicitly when the `claude-reviewed` marker could not be refreshed: the gate refused with `go=false ... review cap reached (7/7)`, a budget cap I would not circumvent. Marker sits at `b31b3f889`, head merged at `92af50079`; the unreviewed delta was three files, none product code.

## What is still running

NO `bump-none` label (labels: bug, enhancement), so this IS release-worthy. Console CI on `main` is run **32095775730** (watch `b5l5b1zl8`); when it goes green it dispatches the Release workflow -- git tag, GitHub Release, R2 upload, EDGE DEPLOY. Both do main-only work that PR CI only dry-ran, so they can fail where every PR check was green.

If a step fails: read its COMPLETE log first, prefer doing nothing because the watchdog auto-retries transient main failures, and classify with the flow's own test -- did this job run and pass on the PR run? Ran-and-passed means transient, do NOT "fix" it. Never re-dispatch a release; that is the operator's call.

## The dirty tree is NOT yours

Four modified tracked files and four untracked paths are the operator's WIP and a peer session's work. The operator said verbatim: *"do not commit or do not discard any of them"*. The constraint now lives in `agent/main/RULES.md:67`. Re-read `git status` rather than trusting any list; the set drifts.

Switching branches while keeping them was done by backup -> `checkout -f` -> restore, verified byte-identical by md5. NOT by stash.

## Next action

1. Run `git submodule update --init --recursive` -- the fast-forward moved 91 commits and the submodule records moved with it. Step 4 requires this and it has NOT been done yet.
2. Watch `32095775730` to terminal, then find the Release run (`gh run list --repo rediacc/console --workflow "Release" --limit 3`, event `workflow_dispatch`, matching 8a03fe5ae) and watch that.
3. AFTER the Release run is green, re-sync: `git fetch origin --prune`, `git merge --ff-only origin/main`, `git submodule update --init --recursive`. CD pushes TWO `[skip ci]` commits back to `main` every release (homebrew-tap pointer, contract floor), so the checkout ends up 2 behind with a STALE `private/homebrew-tap` record. If a submodule shows dirty, decide by which commit is NEWER (`git merge-base --is-ancestor`), never by whose work it looks like -- committing a behind record ships a rollback.
4. Report: merged SHAs, release outcome with its tag, and the on-`main` hand-back warning.
