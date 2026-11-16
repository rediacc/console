# PLAN: re-record the whole tutorial set, narrate it in every locale, and keep a stale cast from going unnoticed again

Status: proposed -- converted from console#606 (operator picked this item 2026-11-16); awaiting operator approval
Owner: e0f36861
First-Seen: 2026-11-16
Depends-On: PLAN-tutorial-recorder-licence.md
Priority: P3 -- every published cast is stale against its script, but the casts still play and the storyboard commands still resolve; the cost is wrong output on screen, not a broken page
Concurrency: exclusive -- the recorder runs on the shared ops VM fleet and rewrites every cast, timeline and transcript in one batch; two recordings at once corrupt each other
Owns: agent/plans/PLAN-tutorial-rerecord.md, packages/www/public/assets/tutorials/*.cast, packages/www/public/assets/tutorials/.recording-hashes, packages/www/src/data/tutorial-timeline/**, packages/www/src/data/tutorial-transcripts/**, packages/www/src/data/video-manifest.json, packages/www/scripts/check-tutorial-parity.ts, .ci/tutorials/tutorial-installation.sh, .ci/tutorials/tutorial-add-server.sh, .ci/tutorials/tutorial-ssh-keys.sh
Live-Proof: bench -- the regenerated timelines, transcripts and video manifest under packages/www/src/data are the www surface, which only bench admits, through the www-smoke check
Source: https://github.com/rediacc/console/issues/606

## Ask

The tutorial casts were filmed against a CLI that has since changed, and the "188-command tutorial re-record debt" (console#523, carried into console#606) asks for the whole set to be filmed again, narrated in all locales and published. The recorder runs every command for real on the KVM fleet, which is the only check that catches a command that parses but fails at runtime (`.claude/skills/tutorials/SKILL.md:147`).
PLAN-tutorial-recorder-licence.md gives the recorder a real licence and re-records the fifteen tutorials that create or fork a repository; this plan finishes the set, narrates it, publishes it with operator approval, and adds the freshness check whose absence let the debt build up unseen.

Search first: no other plan re-records the set; PLAN-tutorial-recorder-licence.md is the only tutorial-recording plan in `agent/plans/`, and `agent/plans/_done/` holds none.

## Context (checked 2026-11-16 against the tree)

1. The set is 18 tutorials: 18 `tutorial-*.sh` scripts under `.ci/tutorials/` (plus `record.sh` and `run-sequence.sh`), 18 casts under `packages/www/public/assets/tutorials/`, 18 storyboards. `npm run check:ci-tutorial-commands` reports "Scanned 18 storyboard(s), 101 runnable command(s)" (rc 0, 2026-11-16). The "188-command" figure in console#523 does not reproduce from any count in the tree; the measured unit is 18 casts and 101 storyboard commands.
2. The recorder's own change detection: `_tutorial_script_hash` (`.ci/media/tutorials.sh:46-50`) is the sha256 of the script plus `.ci/tutorials/lib/tutorial-helpers.sh`, compared against `.recording-hashes` (`:109-114`, `:175-190`); a mismatch queues the tutorial for recording.
3. Measured today with that hash: 18 of 18 tutorials are stale. `.recording-hashes` last changed in 858e6ca3a7 (2026-10-31), and `tutorial-helpers.sh` changed after it in 938452f16c (the activation-skip removal) and 2fc16b442d (licensing in every CI lane), which alone stales all 18. Computed against the helpers as of 858e6ca3a7, 17 of 18 scripts still differ from their stored hash; only `tutorial-managing-secrets` matches.
4. Cast ages: 16 casts were last recorded in 062ce6b0a5 (2026-08-21); `tutorial-managing-secrets.cast` in 858e6ca3a7 (2026-10-31). `tutorial-monitoring.cast` was last changed in fde9b014d8 (2026-11-08, "drop the edge-channel pricing banner and the edge host references"), a hand edit of a cast, which the skill says to replace with a re-record (`SKILL.md:147`).
5. The static gates are green today, which is why the debt is invisible: `check:ci-tutorial-commands`, `check:ci-tutorial-parity` ("Tutorial parity OK for 18 tutorials"), `check:ci-tutorial-casts` ("Checked 18 recording(s)") and `check:ci-tutorial-noninteractive` (22 prompting commands, 60 guarded invocations) all exit 0 on 2026-11-16. The parity backlog file `packages/www/scripts/tutorial-parity-baseline.json` does not exist, so parity carries no deferred drift. No gate reads `.recording-hashes`: `grep -rl recording-hashes` over `scripts`, `packages/www/scripts` and `.ci` finds only `.ci/media/tutorials.sh`.
6. Coverage split with the prerequisite: 15 scripts run `rdc repo create` or `rdc repo fork` and are re-recorded by PLAN-tutorial-recorder-licence.md R3/R4; the other three are `tutorial-installation`, `tutorial-add-server` and `tutorial-ssh-keys`.
7. The loop and its cost: `record --keep-vms`, `extract`, `scaffold-locales`, `generate`, `video --jobs 6` (`SKILL.md:28-36`). TTS reuse is keyed on `textHash` plus the cached mp3, restored with `sync_media_from_r2 --audio-only` (`SKILL.md:119-125`). 18 tutorials across the 10 narrated locales is 180 mp4s, several hours on a 20-core box (`SKILL.md:127`). `ar`, `et` and `tr` have timelines but no narration by design (`SKILL.md:133`).
8. New narration text arrives in the 12 non-English transcript trees as `TODO: translate ...` placeholders written by `packages/www/scripts/scaffold-tutorial-transcript-locales.js` (`todoFor`), and English is the source that the other locales are naturalized from (`docs/i18n/CONVENTIONS.md`).
9. Videos and narration live in R2 bucket `media`, not git; publishing is `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.sync_media_to_r2 --tutorials-only` (`docs/agent-reference/media-assets.md:20`), and the media-pipeline rule forbids a publish without explicit operator approval.
10. The recorder refuses to start in an agent session unless `REDIACC_ALLOW_GRAND_REPO=*` was exported before the session started (`.ci/media/tutorials.sh:92-104`).

## Design

**Order.** The prerequisite lands first (its W1-W4, R3 and R4), because every script that creates a repository needs the licence. This plan then records the three tutorials it does not cover, plus any of the fifteen whose hash has gone stale again since R4, in one batch on one fleet session, so the stateful chain (`run-sequence.sh`) runs in its declared order.

**Narration.** After `extract`, the English transcripts are reviewed first (English is the source), then the `TODO:` placeholders in the 12 other locales are naturalized by i18n writers, then `generate` synthesizes only the changed text in the 10 voiced locales. If `generate` starts synthesizing broadly, the run stops: `extract` changed text it should have kept, and the cost assumption is broken (`SKILL.md:125`).

**One render, one publish.** Rendering and publishing happen once for the whole set, after narration, under one operator approval. PLAN-tutorial-recorder-licence.md OP1 covers the same step for its fifteen casts; running both renders would film the same videos twice, so this plan's OP1 is written to cover all 18, and the lead decides whether the prerequisite's OP1 closes with this one's evidence (an open question for the operator).

**Freshness check.** `check-tutorial-parity.ts` gains a freshness section that reimplements `_tutorial_script_hash` (script plus helpers, sha256) and compares it with `.recording-hashes`. A tutorial whose hash differs is printed with the date of the commit that staled it. The check fails only when a stale tutorial has stayed stale for more than 30 days by that date, so a script edit that needs the VM lab does not turn CI red the same hour, while a debt like today's (18 stale, 16 of them last recorded in August) cannot build up unseen.
The 30-day window is the default and an operator question. A selftest control proves the section fires: a fixture script whose hash differs from its fixture entry by more than 30 days fails.

**Out of scope.** Changing what any tutorial demonstrates; new tutorials; the solution and marketing videos in `private/growth`; voicing `ar`, `et` and `tr`.

## Boxes

- [ ] T1 [writer] Freshness section in `check-tutorial-parity.ts` per Design, with selftest controls for a fresh entry (passes), a stale entry inside the window (prints, passes) and a stale entry past the window (fails). Accept: its selftest controls all PASS, and `npm run check:ci-tutorial-parity` lists all 18 stale tutorials before T3 and exits 0 after it
- [ ] T2 [live] After the prerequisite's R4: record the three uncovered tutorials and every tutorial T1 still reports stale, in sequence order, with only fixes to the three owned scripts if a command fails at runtime (any other script fix is reported to the lead). Accept: `./run.sh www tutorials record --keep-vms` rc 0 and `npm run check:ci-tutorial-casts` rc 0
- [ ] T3 [live] `extract` and `scaffold-locales` on the new casts; review the English transcript diff for narration that changed only because the cast's timing moved. Accept: `./run.sh www tutorials extract` rc 0 and `npm run check:ci-tutorial-parity` rc 0 with no stale tutorial listed
- [ ] T4 [writer] Naturalize every `TODO: translate` entry in the 12 non-English transcript trees per `docs/i18n/CONVENTIONS.md`. Accept: `grep -rl 'TODO: translate' packages/www/src/data/tutorial-transcripts` prints nothing and `npm run check:i18n` rc 0
- [ ] T5 [live] Restore the audio cache, then `generate` for the 10 voiced locales, quoting how many mp3s were synthesized against how many were reused. Accept: `./run.sh www tutorials generate` rc 0, `npm run check:ci-tutorial-caption-sync` rc 0 and `npm run validate:tutorial-audio -w @rediacc/www` rc 0
- [ ] OP1 [operator] Approve rendering all 18 tutorials in the 10 voiced locales and publishing them to R2 (media-pipeline rule). Accept: the operator's answer quoted in the tick, then `./run.sh www tutorials video --jobs 6` rc 0, `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.sync_media_to_r2 --tutorials-only` rc 0 and `npm run check:ci-locale-tutorial-assets` rc 0
- [ ] LP-bench [live] Fresh bench receipt for the regenerated timelines, transcripts and manifest.
  Accept: live-proof bench www-smoke

## Risks

- `www-smoke` writes no receipt until a bench www Worker exists (`.ci/config/proof-tiers.json` `tiers.live.checks.www-smoke`: every run is NOT_VERIFIED), so LP-bench cannot close today; the same holds for the prerequisite's LP box. The plan finishes only once a bench www deploy is recorded.
- A recording interrupted part-way restarts from zero (`.recording-hashes` is written only after a complete run) and refills the VM disks (`SKILL.md:104-108`). T2 runs as one uninterrupted batch on a fleet session nobody else is using; machine 11 carries another agent's work at conversion time, so T2 waits for the fleet.
- T1 can turn CI red on the day it lands if any of today's stale tutorials staled more than 30 days ago. T1 therefore lands in the same push as T3, not before it.
- A runtime failure in one of the fifteen prerequisite-owned scripts surfaces during T2's sequence run; that fix belongs to the prerequisite's owner, and T2 reports it rather than editing a file outside its Owns.
