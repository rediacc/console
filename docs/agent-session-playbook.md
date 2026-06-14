# Agent Session Playbook

How to run a large, multi-workstream session in this repo. Written from the
tutorial-system big-bang waves; the patterns are generic: reference this file
at session start and apply it to whatever the work is.

## The mainframe (operating loop)

1. **Orient from the filesystem, not from memory.** Background jobs from a
   prior session may have finished or died mid-run. Verify state with cheap
   probes (`ls -la` mtimes, `grep -rl TODO`, gate runs) before redoing or
   skipping anything.
2. **Plan, then lock decisions.** For non-trivial waves: explore (read-only
   agents) → design (plan agent for genuinely unexplored areas only) → ask the
   user ONLY decisions that change the work (2–4 crisp options, recommend one)
   → write the plan → get approval. Don't re-litigate locked decisions.
3. **Parallelize by ownership, not by file.** Split work into independent
   workstreams with disjoint file/resource ownership, run each as a background
   agent, keep cross-cutting engine/code edits in the main context. Track all
   of it as tasks (TaskCreate/TaskUpdate): statuses are the session's ground
   truth.
4. **Sequence what contends.** One lab-heavy iteration loop at a time
   (Playwright timing breaks under CPU load); `nice -n 19` background renders;
   background jobs that only burn CPU can overlap.
5. **Verify like a skeptic.** Exit 0 is not done. Frame-check rendered output
   (Read renders PNG/JPG visually), assert on-screen content, run every gate
   the change touches, and spot-check the one artifact the user will look at
   first.
6. **Report outcome-first.** What changed, what's proven, what's running, what
   remains. Quote real observed output (numbers, error lines), not intentions.

## Principles that made the difference

- **Fix the product, not the demo.** If a tutorial/test needs a hack
  (`|| true`, hidden stderr, fake output), the product is wrong: fix the CLI/
  renet behavior instead. Demos must be honest: every claim PROVEN on screen
  (print the secret, drop the table, show real transferred bytes).
- **Display ≠ execution is allowed, lying is not.** Helpers may format what's
  typed (multi-line params, `~` for `$HOME`) but markers/cards always carry
  the flat, copy-pasteable truth, and the executed command must succeed.
- **Verify-then-lock.** Any scripted flow (cast script, storyboard action)
  gets its mechanics verified LIVE on the lab before being committed to the
  pipeline. Unverified scripts fail expensively at record time.
- **Consistency sweeps.** Fixing one instance (an image pin, a selector, a
  stale key) → grep for every analogous instance and fix or explicitly
  report-and-defer (e.g. product templates vs marketplace templates).
- **Scope discipline.** En before locales; defer expensive derived work
  (locale TTS/videos) until upstream content is user-validated. Text-level
  locale sync (translation, stamps) stays current so gates stay green.
- **Everything local.** No commits, branches, PRs, or releases without an
  explicit per-task user request. Plan approval ≠ publish authorization.

## Delegation patterns

| Pattern | Shape | Used for |
|---|---|---|
| **Tuner loop** | Agent iterates change → run → inspect debug frames → adjust, until frame-verified; reports final diff + evidence | Playwright scenes, anything visual |
| **Verify-then-lock** | Agent prototypes each mechanic on throwaway lab resources (`verify-*` prefix, cleaned up after), then writes the final script | Cast scripts, demo apps |
| **Product-change agent** | Full design handed in (from a Plan agent), implements renet+CLI+i18n+tests, live-verifies on the lab, runs all gates | Cross-stack features |
| **Fan-out** | One Sonnet agent per locale/file tuple, naturalized not literal | 12-locale MDX/i18n |
| **Knowledge handoff** | Each agent's hard-won gotchas (selectors, dialogs, sync bugs) get folded verbatim into the NEXT agent's brief | Sequential tuners |

Brief agents with: exact paths, env vars, iteration command, success criteria,
what NOT to touch (other agents' files, shared lab repos), and "report
deviations instead of working around them."

## Key commands

```bash
# Tutorial pipeline (run.sh stages)
./run.sh www tutorials record [name…] [--force] [--keep-vms]   # bridge VM, hash-gated (.recording-hashes)
./run.sh www tutorials extract                                  # casts → en transcript scaffolds
./run.sh www tutorials scaffold-locales                         # sync locale transcript structure/timestamps
./run.sh www tutorials generate --lang en                       # TTS + timelines (hash-gated per narration)
./run.sh www tutorials video [name] --lang en [--keep-temp]     # render
./run.sh www tutorials validate                                 # casts + transcripts + audio + parity

# Video render with live browser scenes (from packages/www)
REDIACC_CONFIG=tutorial TUTORIAL_MACHINE_NAME=machine-11 REDIACC_SKIP_MACHINE_ACTIVATION=1 \
  npx tsx scripts/generate-tutorial-video.ts --cast <tutorial> --lang en --keep-temp --debug
# --debug → <out>/<tutorial>.debug-frames/ (segstart/segend boundary frames + sidecar)

# Locale transcript translation (idempotent; marker format matters)
npm run tutorials:translate          # fills "TODO: translate <kind> (en: <text>)" markers
grep -rl "TODO: translate" packages/www/src/data/tutorial-transcripts/   # done when empty

# Gates (fast, run before declaring anything done)
npm run check:ci-tutorial-casts      # no error output / hacks in casts
npm run check:ci-tutorial-parity     # cast ↔ storyboard ↔ transcript ↔ MDX
npm run check:ci-locale-tutorial-assets
npm run check:ci-shell-format        # after ANY shell edit: shfmt -w -i 4 <file>
npx tsc --noEmit -p packages/www/tsconfig.json
cd private/renet && go build ./... && go vet ./... && go fmt ./...

# Dev binaries
./rdc.sh --override-local            # rebuild SEA → ~/.local/share/rediacc/bin/rdc (PATH `rdc`)
                                     # REQUIRED after CLI changes that storyboards/scripts invoke via plain `rdc`

# Close-out
cd packages/www && node scripts/generate-search-index.js   # after any www content edit
npm run ci                                                  # full local gate suite
./rdc.sh ops down                                           # tear down lab: ONLY at the very end
```

## Lab quick facts

- Config: `--config tutorial` (never default). Machines: `machine-11`
  (192.168.111.11), `machine-12` (192.168.111.12), bridge `192.168.111.1`.
  After re-provisioning: `rdc config machine scan-keys -m <m>`.
- Env: `REDIACC_ALLOW_GRAND_REPO=*` must be exported by the USER before the
  session (agents can't self-set it: ancestry verification).
  `REDIACC_SKIP_MACHINE_ACTIVATION=1` on unlicensed VMs.
  `REDIACC_SKIP_FILE_WRITE_GUARD=1` for `>` redirects in `term -c`.
- Tutorial repos on the lab: `my-app`, `app(:work/:rollback)`, `demo-pgadmin
  (:experiment)`, staged idempotently by `.ci/tutorials/lib/stage-*.sh`
  (storyboard setupCommands). Throwaway work uses `verify-*` names + cleanup
  (`repo delete` + `config repository remove` for orphan rows).
- Recording happens on the BRIDGE cluster (fresh machines), not the persistent
  lab; scripts' pre-setup must provision from zero. `--keep-vms` keeps the
  cluster for the video stage.

## Verification standards

- A browser scene is done when its boundary frames (`segstart`/`segend`) and a
  mid-scene frame show the intended content: readable text, no load flash, no
  stray dialogs/toasts, correct final state.
- A cast is done when the gate is green AND the steps prove the claim (proof
  beats narration: expect-fail for denials, printed values for injection,
  counters for live state).
- A wave is done when: affected videos re-rendered + frame-verified, gates
  green (en scope), search index regenerated, `npm run ci` fallout triaged
  (deferred-locale reds called out explicitly), and the user told exactly what
  to spot-watch.
