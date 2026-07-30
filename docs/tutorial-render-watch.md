# Productionising the pair-level tutorial render watch

Plan produced 2026-07-29 after the operator pointed out that a working prototype was living
in a session-scoped scratchpad: *"When I exit from this session, your interim script will
not work for new sessions."* Written by a planning agent that read the real files; its
load-bearing claims were then spot-checked against the artifacts (results inline).

## What is being productionised

A daemon that renders each **(tutorial, language) pair** the moment that pair's narration is
final, instead of waiting for a whole language. The per-language version left the CPU idle
at load 2.4 for ~20 minutes while 13 already-narrated `ja` tutorials sat unrendered.

Pair granularity is safe because `tutorial_tts/cli.py` finishes one (lang, cast)
completely — synthesis, the deferred alignment barrier, then an **atomic `os.replace`** of
the timeline — before starting the next.

Rules that must survive the move, each with a measured reason: readiness read from the
artifacts (self-correcting); never call `run.sh www tutorials video` (it restores published
audio from R2 over fresh local narration); per-**tutorial** `flock` (the browser-segment
cache is keyed by tutorial with no language in it); `nice -n 10` on renders and never on
narration; `RDC_TUTORIAL_HWENC=0`; per-pair validation gate; a failed pair recorded and
never retried.

## Defects the plan found in the prototype (all verified)

- **`mapfile` is banned.** `.ci/scripts/security/check-commands.sh:32-33` lists
  `readarray` and `mapfile` as "bash 4+ only - use while read loop", and `./run.sh` is in
  that gate's corpus. The prototype's `mapfile -t pairs` is a hard failure the moment it
  moves. The producer|pool shape removes the array entirely.
- **Hot spin on validation failure.** The prototype returns 0 without recording, so the
  pair stays stale, is re-listed, and re-validated as fast as the loop turns — the idle
  `sleep` branch is never reached. Latent, not active: 0 validation failures so far.
- **Non-atomic mp4 write — the serious one.** `generate-tutorial-video.ts:352` calls
  `addEdgePad(concatOut, outPath, …)`, writing straight to the final path, and the
  vtt/chapters/words/poster sidecars are written *after*. A killed render therefore leaves
  a truncated mp4 with a **fresh mtime**, which an mtime-based staleness predicate reads as
  "done" — permanently. Verified in the source.
- **`ready_pairs` mutates while predicating** (`mkdir -p` inside the query).
- **Dropped precondition:** `run.sh:702` requires the audio directory to exist; the
  prototype omitted that check.

## Where it lives: three functions in `run.sh`, as `./run.sh www tutorials watch`

Mechanical, not aesthetic. The three shell gates have different corpora:

| gate | corpus |
|---|---|
| `check:ci-shell-format` | `.ci/`, `.claude/hooks/`, `./run.sh`, and only `scripts/dev` + `scripts/docker` |
| `check:ci-shell-lint` | `.ci/`, `.claude/hooks/`, `./run.sh`, all of `scripts/` |
| `check:ci-shell-commands` | `.ci/`, all of `scripts/`, `./run.sh` |

**`packages/www/scripts/` is in none of them** (verified) — a `.sh` daemon there would be
unlinted and unformatted forever. `run.sh` is covered by all three and needs no new file,
which also means `check:ci-dead-bash`'s orphan-file check cannot fire and **no allowlist
entry is needed** — worth having, since a `manual:` allowlist entry is a permanent hole
whose liveness probe only checks that the file still exists.

Consequence that cuts both ways: deleting `_tutorial_video_pairs` and
`_tutorial_media_producer`'s emit half becomes **mandatory**, because dead-bash reports a
function the moment its last caller goes.

## Deduplication: the watch keeps none of its own render or pool code

| prototype piece | disposition |
|---|---|
| `render_pair()` flock+nice+failure file | **Delete** — `_tutorial_video_render_one` (`run.sh:713-737`) is byte-identical, including the lock path |
| the `& / wait -n / wait` pool | **Delete** — `_tutorial_video_pool` (`run.sh:812-832`) already reads a pipe *specifically* so a streaming producer can feed it |
| `FAILDIR` + never-retry | **Delete** — the pool's per-pair failure files do it; never-retry becomes a producer property |
| `ready_pairs()` | **Promote out of bash** → `packages/www/scripts/list-tutorial-render-pairs.js` |
| per-pair validation | **Move into the producer**, before emission |

Net new bash: one function, `_tutorial_watch_producer`. Both prototype defects (hot spin,
duplicate dispatch) vanish under one mechanism: an **emit-once-per-timeline-mtime memo**
(`declare -A`, which is allowed — the bash-4 ban covers only `mapfile`/`readarray`
globally). Re-narration changes the mtime, so self-correction is preserved.

## Converge `www_tutorials_media` onto the same path — but as a later step

`_tutorial_media_producer` splits: its narration half becomes `_tutorial_narration_driver`
run in the background; its language-level validate and emit are **deleted**; `media`
becomes `driver & ; _tutorial_watch_producer --until-pid $! | _tutorial_video_pool`.

The behaviour change is bounded: `cli.py` writes the timeline unconditionally per
(lang, cast) — `os.replace` inside the pair loop, guarded only by `--dry-run` — so a
cache-hit run still bumps the mtime and the rendered set is identical. The only pairs that
stop rendering are those whose narration was skipped or failed, which is desired. Add
`--all` if unconditional re-render is ever wanted.

Keep `www_tutorials_video` unconditional: "render exactly these, now" is a distinct verb and
`www_tutorials_all` depends on it.

## Process management

Foreground by default so it composes with `tmux`/`nohup`, plus `--detach`.

**Single instance is required and the per-tutorial flock does not provide it** — that lock
serialises two renders of the same tutorial but does not stop two daemons both rewriting the
same mp4. Use an `flock -n` on `artifacts/tutorial-render-watch/watch.lock`; the kernel lock
is the truth and dies with the process, the pid file is observability only.

`--status` prints holder pid, uptime, in-flight renders, pairs remaining, failures.
`--stop` sends SIGTERM; the producer stops emitting and the pool's final `wait` drains
in-flight renders. **Never SIGKILL a render** — see the atomic-write defect above.

Logs go to `artifacts/tutorial-render-watch/` — gitignored, repo-local, session-agnostic,
and already the convention (`test-tutorial-player-release-gate.js` writes
`artifacts/tutorial-player-release-gate/<stamp>/`). This replaces `/tmp/_tut_video_failures.$$`
and a `mktemp -d`, both unrecoverable once the pid is lost.

## Testability, and the `.ci` tension answered directly

Extract the predicate into `packages/www/scripts/list-tutorial-render-pairs.js` with
`--cast/--lang/--stale-only/--require-provider/--root/--selftest`, emitting
`tutorial<TAB>lang` lang-major. Two improvements over the bash: parse `provider` as JSON
rather than `grep`ping the file, and make the provider a **flag** rather than a hardcoded
migration constant that becomes a lie once the migration ends.

It must refuse to run on an empty tree — that is anti-vacuity root pattern 1.

`.ci/scripts/test/gates/` is the right home **and is barred from this session**. Resolution:

- **Now, no `.ci` change:** ship the fixtures as `--selftest` inside the script and wire
  `check:ci-tutorial-render-queue` into the root `ci` chain. Legal because chain-parity
  enforces workflow ⊆ ci, never the reverse. A vitest test under `packages/www` would be
  dead coverage — that vitest project is referenced by nothing in the `ci` chain.
- **Follow-up for someone not barred:** a `.ci/scripts/test/gates/test-tutorial-render-queue.sh`
  and one `REGISTRY` line in `test-gate-anti-vacuity.sh`.

Required controls in `--selftest`, each of which must FAIL if the predicate is wrong: empty
tree refuses; mp4 missing → listed; timeline newer → listed; **mp4 newer → not listed**;
wrong provider → **not listed**; audio dir absent → not listed.

## Scratchpad artifacts

| artifact | verdict |
|---|---|
| GPU-lock probe (mutual exclusion + `kill -9` resilience) | **Keep** as `private/generative/tests/test_gpu_lock.py`. Note that repo is gitignored by console and independent, so it lands there, not here. |
| anyio overlap probe | **Discard the file, keep the number** — add the measured 3.42s vs 6.40s to `docs/media-pipeline-parallelism.md` §6, which currently asserts the `to_thread` requirement with no measurement behind it. A sleep-mocked stand-in for shipped code rots into a test of nothing. |
| worklist-defaults editor | Discard — one-shot, already applied. |
| the two one-shot chain scripts | Discard — superseded, and they encode the wrong granularity. Their durable lesson (wait on a PID with `kill -0`, never `pgrep -f`) is already in the agent file and must be repeated beside the surviving `ps`-probe. |

## Sequence

Migration is free: the prototype holds its script on an fd, its flock path is identical to
the production helper's, and it has **no in-flight state to lose** because readiness is
derived from artifacts. The one rule: **never run the new watch while the prototype is
alive** — the flock serialises duplicate renders, it does not dedupe them. S1-S4 do no
rendering and are safe to run concurrently with it.

| # | step | proof | control that must fail |
|---|---|---|---|
| S1 | enumerator + `--selftest` + `check:ci-tutorial-render-queue` in the `ci` chain | run the gate; **diff its output against the live prototype's** on the real tree | empty `--root` must exit non-zero; mp4-newer fixture must yield zero lines |
| S2 | rewire `www_tutorials_video` onto it; delete `_tutorial_video_pairs` | render one pair; `check:ci-dead-bash` green | leave the old function body in place — dead-bash must report it |
| S3 | **atomic mp4 write** (render to `.partial`, sidecars, then `renameSync`) | `kill -9` mid-encode; mp4 absent/unchanged and the pair still listed stale | measure the BEFORE first: same kill leaves a fresh-mtime truncated mp4 and the pair vanishes from `--stale-only` |
| S4 | `_tutorial_watch_producer` + `www_tutorials_watch` + dispatch + help | `watch --once --dry-run` matches S1 and starts nothing | a second watch must exit non-zero naming the holder's pid |
| S5 | live cutover, only once the prototype and all renders have drained | `--stale-only` reaches zero against 234 mp4s | attempt cutover with a render in flight — preflight must refuse |
| S6 | converge `www_tutorials_media` | log timestamps show the first render starting before the last cast finishes narrating | capture the BEFORE delta first, or the justification is unmeasurable |
| S7 | gates + docs | the four shell gates, knip, chain-parity | `shfmt -i 4 -ci -d run.sh` empty **and** `shfmt -i 4 -d run.sh` non-empty — that second run is the proof `-ci` was used |
| S8 | `.ci` follow-ups for someone not barred | — | — |

---

## Status, 2026-07-30

| # | state | evidence |
|---|---|---|
| S1 | **done** | `packages/www/scripts/list-tutorial-render-pairs.js`, `--selftest` green with 3 control cases, gated as `check:ci-tutorial-render-queue` in the `ci` chain |
| S2 | **done** | `_tutorial_render_pairs` wraps the predicate; `_tutorial_video_pairs` deleted; `check:ci-dead-bash` exit 0 |
| S3 | **done** | `generate-tutorial-video.ts` renders to `stagePath` (`:142`), one `renameSync` (`:465`), cleanup (`:471`) |
| S4 | **done** | `_tutorial_watch_producer` (`run.sh:975`), `www_tutorials_watch` (`:1056`), dispatch (`:1919`), help (`:1727`); second instance exits non-zero naming the holder's pid |
| S5 | **done** | one real pair rendered through the watch, see below |
| S6 | **BLOCKED on a measurement that costs GPU time** | see below |
| S7 | **done** | the four shell gates + `check:ci-tutorial-render-queue` all exit 0; `shfmt -i 4 -ci -d run.sh` empty while `shfmt -i 4 -d run.sh` is 819 lines, which is the proof `-ci` was used |
| S8 | **done** | `.ci/scripts/test/gates/test-tutorial-render-queue.sh`, auto-discovered by `run-all.sh`'s `gates/test-*.sh` glob — no registration line needed |

### S5: the live render, and a better result than the plan asked for

The plan's S5 proof was "`--stale-only` reaches zero against 234 mp4s", which the fleet already
satisfied without the watch having rendered anything. That is a vacuous pass, so S5 was instead
proven by making exactly one pair stale (`touch` its timeline) and letting the watch render it:
dispatched 1 of 1 stale, 5 render processes observed live, finished cleanly, no `.partial` left,
`--stale-only` back to zero.

**The re-rendered mp4 came out byte-identical** — sha256 `41f8a74f125fd94a…`, size 2593339 and
duration 93.233333 all unchanged, with mtime advanced so the write demonstrably happened. The
render is reproducible from unchanged narration. That is what makes the mtime-based staleness
design safe: a spurious re-render is idempotent rather than a silent content change.

### S6 is blocked, and this is why rather than an excuse

S6's acceptance criterion is "log timestamps show the first render starting before the last cast
finishes narrating". Nothing in the tree can produce that observation now: all 13 locales are
fully narrated, so there is no narration for a render to overlap WITH. Producing it means
re-narrating at least one locale — real GPU time on the card, and the VoxCPM lease would block
any other narration work while it ran.

The convergence itself is also smaller than it looks now: the delegate that built S4 extracted
`_tutorial_auto_jobs()` (`run.sh:670`) so `www_tutorials_media` and `www_tutorials_watch` already
share the job-count arithmetic instead of keeping two copies 400 lines apart. What remains is
`media` narrating everything before rendering anything, rather than feeding the producer.

**Do not fake this one.** A convergence justified by an unmeasured overlap claim is exactly the
`~45%` mistake recorded in `docs/media-pipeline-parallelism.md` §10. Either pay for one locale's
re-narration and measure it, or leave `media` alone — it works.

### S8: why there is no anti-vacuity REGISTRY line

The plan called for "one `REGISTRY` line in `test-gate-anti-vacuity.sh`". That would not work.
That harness builds its fixture with `cp -r "$REPO_ROOT/scripts"` and `cp -r "$REPO_ROOT/.ci/scripts"`
(`test-gate-anti-vacuity.sh:136,143`) and copies nothing from `packages/`. The predicate lives at
`packages/www/scripts/`, so the entry would fail with *No such file or directory* — non-zero for a
reason unrelated to vacuity, which is precisely the false signal that file's own REGISTRY POLICY
warns about, and the same call already made for `check-breakpoint-drift.sh`.

So the empty-tree case lives in a test carrying its own fixture, alongside checks a self-test
cannot honestly make about itself: that the npm gate actually runs `--selftest`, that it chains
with `&&` rather than `;` (which would discard a failing stage), and that the self-test contains
controls. It was mutation-tested: pointed at a stub predicate that reports zero pairs on an empty
tree, it fails with `empty tree must exit non-zero: expected 1, got 0`.
