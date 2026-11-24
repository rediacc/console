# PLAN: Console animations -- run blocks animate from the step ids renet already emits, with an indeterminate fallback and reduced motion honoured
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-console-run-index.md -- the animations render inside the run blocks and through the animation slot that plan's RI8 builds (C22, C29)
Priority: P2 -- the shadcn `animate-in` classes on dialogs, menus and popovers are dead today (zero `animate-in` or `@keyframes enter` rules in the built private/account/web/dist/assets CSS, measured 2026-11-23), and a running block shows only a step list
Concurrency: parallel -- wave 1: AN1 (dependency and CSS import) and AN2 (phase map) are file-disjoint; wave 2: AN3 (scenes) and AN6 (coverage gate, after PLAN-tooling-code-reduction.md#CR2); wave 3: AN4 (run block mount), AN5 (translations); wave 4: AN7 (e2e). AN4 edits RunBlock.tsx, which PLAN-console-run-index.md RI8 creates; it lands after RI8
Owns: agent/plans/PLAN-console-animations.md, private/account/web/package.json, private/account/web/package-lock.json, private/account/web/src/styles/app.css, private/account/web/src/lib/run-phases.ts, private/account/web/src/lib/run-phases.json, private/account/web/src/lib/__tests__/run-phases.test.ts, private/account/web/src/components/console/animations/**, private/account/web/src/components/console/runs/RunBlock.tsx, private/account/web/src/components/console/runs/__tests__/run-block-animation.test.tsx, private/account/web/src/i18n/locales/*/console.json, .ci/rediacc_ci/quality/step_phase_coverage.py, .ci/rediacc_ci/tests/gates/test_gate_step_phase_coverage.py, private/account (gitlink bump only), private/account/e2e/tests/27-console/27-04-run-animations.test.ts
Live-Proof: bench -- the account web bundle with the new scenes and tw-animate-css is deployed to the eu bench portal and a real `repo fork` and `repo up` animate there (AN-L1)

## Ask

C29: animations use the step names renet already emits and nothing new from renet; operations without steps (backup to storage, restore, cluster operations) show an indeterminate animation; reduced motion is honoured. The animations render inside the run blocks of PLAN-console-run-index.md (C22) and later in the AI timeline (C34). The www clone visual is a visual reference only.

## Context

1. The step mechanism is `StepTimer` (private/renet/pkg/output/steps.go:47-110): `Start(name)`, `Done`, `Fail` with detail `failed`, `Record(name, d, detail)`; it emits `step_start` and `step_done`. The ids live at the call sites, not in steps.go.
2. Fork: `cow_sync` (private/renet/cmd/renet/repository_fork.go:368), `cow_reflink` (:378), `luks_mount` (:506); `cow_clone` on commit (private/renet/cmd/renet/repository_commit.go:143).
3. Push: `checkpoint` (private/renet/cmd/renet/backup_push.go:238, constant `cmdCheckpoint` at private/renet/cmd/renet/literals.go:12), `snapshot` (private/renet/cmd/renet/backup_push.go:249, `FlagSnapshot` at private/renet/cmd/renet/ceph_root.go:19), `transfer` (private/renet/cmd/renet/backup_push.go:286). Pull: `preseed`, `transfer`, `verify`, `finalize` (private/renet/cmd/renet/backup_pull.go:276, :291, :301, :327).
4. Up: `luks_mount`, `docker_daemon` (private/renet/pkg/orchestration/workflows.go:79, :175), `compose_up` (private/renet/pkg/orchestration/up_down_workflows.go:245). Down: `compose_down` (private/renet/pkg/orchestration/up_down_workflows.go:410), `luks_unmount`, `docker_stop` (private/renet/pkg/orchestration/workflows.go:518, :539).
5. Migrate runs push, down and a delta push through the same functions, then records `cutover_complete` (private/renet/cmd/renet/repository_migrate.go:25, :275) through `timer.Record`.
6. The CLI labels steps at packages/cli/src/utils/timeline.ts:8-90; `cow_sync`, `cow_reflink` and `cutover_complete` have no label there and print raw.
7. The web folds `step_start` and `step_done` into steps (private/account/web/src/components/console/StepTimeline.tsx:31-64) and shows raw step names.
8. `useReducedMotion` tracks the media query live (private/account/web/src/hooks/useReducedMotion.ts:10-23); app.css already cuts every animation to 0.01 ms under reduced motion (private/account/web/src/styles/app.css:198-205), so a scene must stand as a static frame, not as its first animation frame.
9. app.css imports only `tailwindcss` (private/account/web/src/styles/app.css:1); `tw-animate-css` is not in private/account/web/package.json, while dialog.tsx uses `animate-in`, `fade-in-0` and `zoom-in-95` (private/account/web/src/components/ui/dialog.tsx:23, :45), as do six other ui components.
10. The www clone visual is a production card and a clone card side by side (packages/www/src/components/solution-pages/SPHowItWorks.astro:108-126).

## Design

D1. **Scenes keyed by step id, not by command.** `run-phases.json` maps each animated step id to a scene and a phase: `clone` (cow_sync, cow_reflink, cow_clone), `transfer` (checkpoint, snapshot, transfer, preseed, verify, finalize), `start` (luks_mount, docker_daemon, compose_up), `stop` (compose_down, luks_unmount, docker_stop), `cutover` (cutover_complete). Every other id renet emits is listed under `plain`, which keeps the step list without a scene. The scene follows the open step, so migrate plays transfer, stop, transfer, cutover in order with no command table, and a future command that reuses these steps animates for free.

D2. **Indeterminate fallback.** A running block with no step event animates the indeterminate scene (a slow sweep over a single machine card); the first mapped step switches to its scene. This covers backup to storage, restore and cluster operations without a hand list (C29), and a failed step (`detail: failed`) freezes the scene in the error tone.

D3. **CSS and inline SVG only.** Each scene is one inline SVG with CSS keyframes in `animations.css` beside it, two machine cards in the www clone style (Context 10) drawn fresh for the console, no new animation library: the motions needed are translate, opacity and stroke-dash, which CSS covers, so a library would add bundle weight for nothing.

D4. **Reduced motion.** Under `useReducedMotion()` a scene renders its static end frame of the current phase with the phase caption, and progress shows as the step count; no keyframe runs.

D5. **tw-animate-css.** Installed as a dependency of the web app and imported after `tailwindcss` in app.css, so the shadcn `data-[state]` classes animate. Before: zero `@keyframes enter` rules in the built CSS; after: present. The version is older than the release-age window (.ci/config/release-age.json).

D6. **Captions.** One caption per scene and phase in console.json (for example "Cloning with copy-on-write"), the step id as a fallback, translated into 13 locales.

D7. **Coverage gate.** `step_phase_coverage.py` lists every step id the non-test renet sources pass to a timer's `Start` or `Record` (a literal, or a same-package string constant) and fails when one is neither a scene step nor `plain` in run-phases.json, or when the json names an id renet no longer emits. Declared in the CR2 gate header grammar with a selftest control.

## Ordering against other live plans

- PLAN-console-run-index.md lands first (header edge); AN4 edits its RunBlock.tsx after RI8.
- PLAN-console-ai-assistant.md reuses `RunAnimation` in its timeline (C34, C35) after this plan lands; nothing here waits on it.
- AN6 waits on PLAN-tooling-code-reduction.md#CR2, which holds the gate wiring files.

## Tasks

- [x] AN1 [writer] Install `tw-animate-css` in private/account/web and import it in app.css after `tailwindcss` (D5), with the lockfile written by the pinned npm.
  Owns: private/account/web/package.json, private/account/web/package-lock.json, private/account/web/src/styles/app.css
  Depends on: none.
  Accept: before the change, `(cd private/account/web && npm run build)` rc 0 and `grep -c "@keyframes enter" private/account/web/dist/assets/*.css` prints 0; after it, the same build rc 0 and the count is at least 1; `npm run check:ci-lockfile` rc 0.
    (ticked) 2026-11-24T20:29:40Z by d778be9d: landed in account gitlink 878815856b: run animations box, vitest run-phases animations runs 42 passed rc 0
- [x] AN2 [writer] Phase map (D1, D2): run-phases.json and `phaseFor(events)` in lib/run-phases.ts returning the scene, the phase, the failed flag, or `indeterminate` when no step has arrived.
  Owns: private/account/web/src/lib/run-phases.ts, private/account/web/src/lib/run-phases.json, private/account/web/src/lib/__tests__/run-phases.test.ts
  Depends on: none.
  Accept: `(cd private/account/web && npx vitest run src/lib/__tests__/run-phases.test.ts)` rc 0: a fork stream yields clone then start, a migrate stream yields transfer, stop, transfer, cutover, an empty stream yields indeterminate, a `plain` id keeps the previous scene, a failed step sets the flag.
    (ticked) 2026-11-24T20:29:49Z by d778be9d: landed in account gitlink 878815856b: run animations box, vitest run-phases animations runs 42 passed rc 0
- [x] AN3 [writer] Scenes (D3, D4): `RunAnimation` and the clone, transfer, start, stop, cutover and indeterminate scenes as inline SVG with CSS keyframes under components/console/animations/, a static end frame under reduced motion, English captions in console.json.
  Owns: private/account/web/src/components/console/animations/**, private/account/web/src/i18n/locales/en/console.json
  Depends on: AN2.
  Accept: `(cd private/account/web && npx vitest run src/components/console/animations)` rc 0: each scene renders for its phase, reduced motion renders no element with an `animation` class and shows the caption, a failed phase renders the error tone.
    (ticked) 2026-11-24T20:29:56Z by d778be9d: landed in account gitlink 878815856b: run animations box, vitest run-phases animations runs 42 passed rc 0
- [x] AN4 [writer] Mount `RunAnimation` in the animation slot of RunBlock for running and just-finished blocks, folding with the block.
  Owns: private/account/web/src/components/console/runs/RunBlock.tsx, private/account/web/src/components/console/runs/__tests__/run-block-animation.test.tsx
  Depends on: AN3, PLAN-console-run-index.md#RI8.
  Accept: `(cd private/account/web && npx vitest run src/components/console/runs/__tests__/run-block-animation.test.tsx)` rc 0: a running block with `cow_reflink` open shows the clone scene, a folded block shows none.
    (ticked) 2026-11-24T20:30:02Z by d778be9d: landed in account gitlink 878815856b: run animations box, vitest run-phases animations runs 42 passed rc 0
- [x] AN5 [writer] Translate the scene captions into the 12 other locales of console.json, naturalized per docs/i18n/CONVENTIONS.md, writers on sonnet.
  Owns: private/account/web/src/i18n/locales/*/console.json
  Depends on: AN3.
  Accept: `npm run check:ci-i18n-account-key-usage` rc 0 and `npm run ci -- --narrow` rc 0.
    (ticked) 2026-11-24T21:03:10Z by d778be9d: AN5 landed 24d722c5ea; check:i18n rc 0; vitest animations and i18n 22 passed
- [ ] AN6 [writer] Step coverage gate (D7): .ci/rediacc_ci/quality/step_phase_coverage.py with its `---- gate ----` header (lane quality-code, selftest true) and its gate test, the control planting an unmapped renet step id and a stale json id.
  Owns: .ci/rediacc_ci/quality/step_phase_coverage.py, .ci/rediacc_ci/tests/gates/test_gate_step_phase_coverage.py
  Depends on: AN2, PLAN-tooling-code-reduction.md#CR2.
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.quality.step_phase_coverage` rc 0 on the tree; `PYTHONPATH=.ci python3 -m rediacc_ci.quality.step_phase_coverage --selftest` rc 0 with both controls failing as planted; `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/gates/test_gate_step_phase_coverage.py` rc 0.
- [x] AN7 [writer] E2e: a routed NDJSON stream carrying fork step events shows the clone scene in the run block, then the start scene; under `reducedMotion: 'reduce'` emulation the static frame and caption show; a stream with no steps shows the indeterminate scene.
  Owns: private/account/e2e/tests/27-console/27-04-run-animations.test.ts
  Depends on: AN4.
  Accept: `(cd private/account/e2e && npx playwright test tests/27-console/27-04-run-animations.test.ts)` rc 0.
    (ticked) 2026-11-24T20:30:09Z by d778be9d: landed in account gitlink 878815856b: run animations box, vitest run-phases animations runs 42 passed rc 0
- [ ] LP-bench [live] Deploy the branch's account Worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) so AN-L1 drives the bundle this branch builds.
  Accept: live-proof bench account-smoke
- [ ] AN-L1 [live] eu bench: from the console, `repo fork` of a bench repo shows the clone scene then the start scene in its run block, `repo down` of the fork shows the stop scene, and a dialog opens with the tw-animate-css fade. Local-route: deploy-bench -- the branch account Worker serves the eu bench portal and the browser is driven from this machine.
  Depends on: LP-bench.
  Accept: a screen recording or three screenshots per scene and the requestIds recorded in this plan.

## Risks

- A renet step added without a json entry fails AN6 in CI, which is the intent; the fix is one json line.
- tw-animate-css turns on motion in every shadcn component at once; the global reduced-motion rule (Context 8) still applies to them.
