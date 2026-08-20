## SESSION e6500e92 2026-08-20T06:36:54Z

## What is true right now

Branch `0818-1`, PR **#569 OPEN, READY**. Local HEAD **`d7cad35cb`**, `origin/0818-1` at
`79554375a`: **4 commits UNPUSHED ON PURPOSE**, held so ONE run covers the whole chain.

    2af084b54  gate: ./x.sh scripts must be committed executable
    689ccc071  gate: naturalization model must match repo policy
    af1dc058d  lint: clear check:lint (all 4 errors were mine)
    d7cad35cb  i18n: drain en.json em dashes, 73 chars -> 0

Submodule `private/account` pushed at `3cd870b` (PR #80). `private/growth` (NOT a submodule,
separate GitLab repo, gitignored) at `d9fb7ef`.

## NATURALIZATION IS DONE. Do not re-run it.

`scripts/check-i18n-naturalization.ts` **EXIT=0**, "all 12 maintained locales covered and
fresh", **0 stale** (929 at session start, 79 at red-gates' handback). Final sweep census:
36 combos, 36 exit-0, 0 failures, 24 applies. My sweep process has EXITED; no
`i18n_pipeline` process should be alive.

What made it converge, so nobody re-litigates it: `--reprocess` (a poisoned
`2000_rewrite.json` cache was short-circuiting the model call across four earlier sweeps) and
the unescaped-inner-quote JSON repair (`private/growth` `f09b01f`) that unblocked
`migrationSafety` in five languages.

## `red-gates` OWNS the locale catalogs right now

It is executing step 4: the locale em-dash pass on a FRESH scan, then ONE baseline drain.
Ruling already given and confirmed: the 44 Russian dashes get the **verb supplied**, ru is
**NOT exempted** from the catalog surface, and it flags rather than forces any line that
resists. **Do not touch `packages/www/src/i18n/translations/*.json` until it hands back**, and
do not reuse its old count of 52 findings; 24 applies moved them.

`packages/www/src/data/tutorial-timeline/*/tutorial-backup-restore.json` belongs to session
`3fe0b2ed`. Never touch `agent/3fe0b2ed/**`.

`package-lock.json`: if it shows ONLY `"dev": true` deletions that is the cosmetic npm11 flip.
Restore with `npx -y npm@10 install --package-lock-only --ignore-scripts`; never commit it.

## CI: run `32334401723` terminal, census read job-by-job

10 success (incl. BOTH Procwalk and `Quality / Built-www Gates`), 2 skipped, **1 failure**,
**7 cancelled**, 0 neutral. The 7 cancelled (i18n, Security, Packages, Go, Code, both Renet
builds) **DID NOT REPORT** -- unknown, not good. The one failure is
`check:ci-tutorial-caption-sync`, 8 combos of `tutorial-backup-restore`: **NOT ours and
deliberately NOT skipped**, since `agent/3fe0b2ed/STATE.md` confirms it purged first and
verified the flat cues are real. It clears when 3fe0b2ed re-publishes.

## Next action

1. **When `red-gates` hands back** (#28a63c89), verify its diff against the artifact rather
   than its report, then run `npm run check:ci-em-dash-surfaces` and `npm run check:i18n`
   end to end.
2. `npm run i18n:generate-client -w @rediacc/www` (#4be5bdee), then `check-layout-overflow`
   across all 13 locales, because the imperative rewrite changed sentence length and de/ru
   already run 6-37% longer than English.
3. **ONE push** of all commits, then re-check CI with `gh api` and count `cancelled` and
   `neutral` as DID NOT REPORT.
4. Then FRESH Claude review (head moved, `claude-reviewed:` marker stale, so `Review Complete`
   would go `neutral`), resolve every thread, `CronDelete 7cb9b31f`.
5. Owed once `3fe0b2ed` finishes: remove `no-media-quality` from #569 AND
   `gh label delete no-media-quality`. Never merge, never push `main`.
