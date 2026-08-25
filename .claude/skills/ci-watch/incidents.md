# ci-watch: the incidents behind the rules

Evidence for [SKILL.md](SKILL.md). Both files are capped at 60 lines by
`check:ci-skill-size`, so a new entry means compressing an old one.

## The compound watch that swallowed a red run (2026-08-24)

A watch that waited for CI and THEN for a review marker:

```bash
until <run completed>; do sleep 20; done
gh run view ... --jq '...'                        # verdict printed HERE
until <review marker appears>; do sleep 20; done  # ...then it kept waiting
```

CI failed at 23:55:13 and the verdict, `failed: ["Quality / Static"]`, was
written into the output file. Nothing woke the session: the process had not
exited, having moved into the second `until` to wait for a review that a red run
never posts. It sat unread for ninety minutes, surfacing only when the operator
pasted the failing job's URL and asked "don't you watch?". The background
check-in kept reporting a live worker, because the worker WAS live.

## A watch fired on attempt 1 of a run that was not over (2026-08-25)

Landing console#574, this skill's own PR. The watch reported `cancelled` with
`CI Complete` failed; a re-query moments later returned a null run conclusion,
which reads like a `gh` glitch and is not one. `run_attempt` had gone to **2**:
the watchdog classified `OPS Provision (macos-intel)` — hung 55 minutes on
`Verify: SSH connectivity`, cancelled at its `timeout-minutes: 45` — as
transient and re-dispatched it. Attempt 2 passed, so the verdict the watch
delivered belonged to a superseded attempt.

Two rules came out of it. `completed` is not terminal: require the same
`run_attempt` twice. And classify before fixing: that job had passed on run
32805254228 on the same branch, which makes it transient by the pr-merge skill's
own test, so the correct action was to let the retry run.

Fixing it turned up NINE divergent copies of the loop across docs and hooks, two
of them recommending forms their own neighbouring prose contradicted. Hence
`check:ci-watch-recipe`: one source, pointers everywhere else.

## A killed watch answered as a no-op (2026-08-24)

A round-4 watch was killed rather than completing. The notification was treated
as "no response requested" and the session stopped. The run had gone **green**
and sat unwatched, PR still in draft, until the operator asked.

## `gh run watch` is a convenience, not a contract

`--exit-status` returns non-zero when the run fails
(<https://cli.github.com/manual/gh_run_watch>). It is still rejected here: it
dropped **four times out of four** in one campaign, and has been seen exiting 1
while the run was still `in_progress`. The `until` poll exits on a state you
read yourself, which is the property that matters.

## Why the mechanism is what it is
Confirmed against the docs, not assumed: background output is written to a file
read on demand, and the wake-up is the process exiting. Sources:
<https://code.claude.com/docs/en/interactive-mode> and
<https://code.claude.com/docs/en/tools-reference>.
