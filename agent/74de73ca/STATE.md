## SESSION 74de73ca 2026-09-05T01:16:09Z

## Where things stand

Branch `0903-1`, PR #585, epic `24c98380`. Everything of mine is COMMITTED AND PUSHED;
the working tree holds nothing of mine. CI runs continuously; `d1589e0b` is holding
`/pr-merge` until the head is green.

My commits, newest first: `32e191e6c` (check:ci-schema-call-sites + gate-bind refuses to
delete a registered step), `385bb06bb` (revert), `840185431` (16 vacuity floors + the
enumeration-vacuity widening), `ddc4fa17d`, `3fe226463`, `1269d8aad` (judge log),
`8faba232c`, `1e8026bdb`, `332a98af6`.

## The two things that keep biting, both mine

- **The shared git index.** Three times tonight my STAGED files were swept into
  `d1589e0b`'s commits, because I stage, run a 55-second `ci:quick`, then commit, and
  `git add` writes an index both sessions share. THE FIX I KEEP FORGETTING: run
  `ci:quick` FIRST, then `git add && git commit` as ONE command. Nothing of mine should
  ever sit staged across a slow run.
- **Checking a family instance by instance.** I gave three vacuity floors an env
  override and not the fourth; a per-site sweep of the judge call sites missed the
  fifth. The gates I wrote for this exist because I kept doing it: `check:ci-schema-call-sites`
  enumerates from source, and `gate-test:vacuity-floors` drives each floor.

## Live collaboration

`d1589e0b` is mid-`/migrate` (tracked worklist store under `agent/worklist/`, `wl_store.py`,
`worklist-cases/*.sh`). Their files are theirs: attribute a red before diagnosing, then
`worklist.py --ask`, never edit. That has paid off every time tonight. They have fixed
three of my defects (`45dd63875` action-refs floor, the TS2352, the half-landed floors)
and I have fixed none of theirs by editing -- only by telling them.

`gate-bind --write` now REFUSES to drop a step that the manifest still registers. It ate
four of theirs before that guard existed; hand-registered steps belong BELOW the
`# <<< gate-bind` marker.

## Next action

Nothing of mine is in flight. In order:

1. Watch CI (`.ci/scripts/ci/ci-trace.py`). If red, attribute the failing job before
   diagnosing -- most reds tonight were a peer's in-flight work, and two of mine were
   caught by their sweeps first.
2. Poll the mailbox (`worklist.py --poll 74de73ca`) and answer anything from `d1589e0b`.
   Check `ps -eo pid,args | grep "[w]l_wait.py 74de73ca"` BEFORE relaunching a waiter;
   they accumulate.
3. `GH_TOKEN="$(gh auth token)" npm run ci:quick` needs ONE token variable, not two --
   verified 303/303 with `GITHUB_TOKEN` unset.
