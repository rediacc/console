## SESSION e6500e92 2026-08-19T19:17:58Z

## What is true right now

Branch `0818-1`, PR **#569 OPEN and READY**, head **673003323**. `main` untouched.

**CI RED, UPSTREAM, unchanged across 3 heartbeats.** Run `32275458597`: all 10 failures are
ONE step, npm ETARGET on `@inquirer/core@^12.0.0` (published 0.2h before the run,
`.npmrc minimum-release-age=1440` blocks it). NOT this branch. **Self-heals
2026-08-20T17:32Z. Do NOT pin.**

## ALL OPERATOR DECISIONS NOW CLOSED. Everything left is mechanical, blocked on ONE batch.

`c5011baf` (extend the pipeline registry or accept drift) and `fc2cb63a` (D5a) both ticked
this session -- the first was ALREADY answered by the operator earlier ("Full Wave C,
pipeline on haiku") and I'd executed it but never closed the item; the second stays parked
behind D5, which is held. `fd11f8db` sourceHash deleted from the 7 English docs, verified
zero new gate findings. No open `[?]` remain.

## WAVE C NATURALIZATION BATCH: RUNNING, bg pid `1152389`, log
`scratchpad/wave-c-naturalize.log`

**~41min elapsed, 13/36 lang x surface combos done** (homepage+marketing+persona x 12
langs), now on `fr/homepage`. `tail -6` per item means the log looks frozen on the CURRENT
item; check `ps -o etime= -p 1152389` before assuming it died, do NOT kill/restart.

**THREE DISTINCT failure classes seen so far, all SAFE (0 corruption, guard rejects
cleanly), all need a RETRY after the batch ends:**
1. Model invents a plausible sibling key with no English source (`/subtitle` next to
   `/title`) -- ar, de, es `home/solutions`. FIXED going forward: I closed the prompt gap
   in `private/growth/i18n_pipeline/prompts/naturalize.py` +
   `steps/step2000_naturalize.py` (now states the closed id set explicitly). Does NOT
   retroactively help items already processed before the fix landed.
2. Model invents content belonging to a DIFFERENT group entirely (`et/marketing
   disasterRecovery` got 9 ids shaped like `pages.pricing`, confirmed NOT in pricing's own
   offered set either -- genuine invention, not a file mixup).
3. `et__persona__forCtos` -- raw malformed JSON from the model, `exit=1` for that one item;
   loop has no `set -e` so it correctly continued to the next combo.

**When `===ALL DONE===` appears:** run `npm run i18n:naturalize-status` for the real
remaining-stale list (source of truth, NOT this log), retry each surviving skip via
`private/growth/i18n_pipeline` (`bash run.sh --lang <l> --surface <s>`), THEN tick C2c, run
C2e `i18n:generate-client -w @rediacc/www`, then C-V (`check:i18n` + layout-overflow x13).

## Dev server MINE on 4325, do not start another / do not kill

Content store STALE (5 astro dev procs share one `.astro/` cache); docs page shows 3/14
topic rows despite the FILTER ITSELF now being provably correct (fixed + verified this
session: `[hidden]` was losing to an author `display:flex` on `.docs-browse-item` AND
`.newsletter-banner`, both fixed, both independently reproduced by me).

## Next action

1. `ps -o etime= -p 1152389` + `tail -30 scratchpad/wave-c-naturalize.log`.
2. If `===ALL DONE===`: run `i18n:naturalize-status`, retry every surviving skip, then the
   C2e/C-V chain in order.
3. If still running: nothing to do but wait; do not force it synchronous.
4. CI: wait for 2026-08-20T17:32Z, fresh Claude review, resolve threads, `CronDelete
   7cb9b31f`. Never merge, never push `main`.
