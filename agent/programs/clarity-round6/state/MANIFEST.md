# clarity-round6 program state

Seeded 2026-08-27 by session `e580532b` on branch `0827-1`. Design suite: `/home/developer/console/agent/programs/clarity-round6/`

## Model policy

Opus is the default for coding sub-agents. Fable for the challenging pieces and for planning agents. Sonnet for all translation and naturalization work. At most 2 concurrent writers, disjoint file ownership stated verbatim in every prompt.

## Waves

| id | wave | status | owner | notes |
|---|---|---|---|---|
| w1 | Wave 0 measurement harness and template contract | not started | | SERIAL, lead only, blocks w5 |
| w2 | Wave 1 agent-browser output guard | not started | | independent, can run any time |
| w3 | Wave 2 Remotion 4.0.463 to 4.0.518 | not started | | blocks w8 |
| w4 | Wave 3 video decisions before any render | not started | | blocks w8 |
| w5 | Wave 4 solution-page density | not started | | needs w1 |
| w6 | Wave 5 dark bands outside dark mode | not started | | single owner, main.css |
| w7 | Wave 6 new persona and homepage videos | not started | | blocks w8 |
| w8 | Wave 7 one render and publish pass | not started | | needs w3 w4 w7 |
| w9 | Wave 8 Docker portability | not started | | independent of the www waves |
| w10 | Wave 9 verification and scorecard | not started | | last |

## Active agents

| agent | wave | report path | started | status |
|---|---|---|---|---|
| (none yet) | | | | |

## Operator decisions

All eight answered 2026-08-27. Full text in the program README under `## Operator decisions (ANSWERED ...)`. Summary: A1 all five new videos are AI motion graphics and the founder track is dead; A2 videos end on a held brand mark; A3 the guard is a `block-*.sh`; A4 it BLOCKS; A5 `howItWorks` is a per-page density candidate and the site headlines are untouched; A6 personas get a third manifest namespace; A7 page bands go light and the footer stays dark; A8 every video gets a 1.5s lead hold.

## Discovered bugs

Recorded during planning, all verified, none yet fixed:

1. Every rdc command shown on camera in the 21 solution videos is invalid CLI. 13 of 13
   fail `parseRdcCommand`. Instrument proved with 12 of 12 known-good tutorial commands.
2. `validate:landing-cli-usage` is vacuous. It exits 0 saying no landing terminal sources
   exist, because the i18n terminal blocks were removed while the videos kept a stale copy.
3. `remotion/src/fonts.ts` guards Arabic only. Inter is absent on this host, so all 12
   non-Arabic locales would render in a substituted face, silently, exit 0.
4. Four of five named font families are missing on this host: Inter, JetBrains Mono,
   WenQuanYi Zen Hei, Noto Sans Arabic.
5. `voxcpm` is declared nowhere: not in `private/generative/pyproject.toml`, not in the
   `run.sh` pip list, yet it backs the default TTS engine.
6. `pyproject.toml` pins `torch>=2.2` unpinned, which today resolves to a CUDA 13 build.
   Works on driver 616.56, but a venv rebuild silently changes CUDA major.
7. The video manifest records the TTS engine and NOT the renderer version, so a mid-fleet
   Remotion bump is invisible to CI in exactly the way the Qwen3 drift was.
8. `gpu_lock.py` defaults its lease to `/tmp/rediacc-gpu.lock`, which is per-container and
   therefore does not hold across a containerised narration job.
9. `step7000_visual_qa.py:156` hardcodes `timestamps = [0.5, 1.5]`, the two forced early
   samples that feed `hook_punch`. The A8 lead hold of 1.5s puts BOTH inside the hold, so the adjudicator would judge a frozen frame and the visual loop would dispatch storyboard fixes fleet-wide for a problem that is the new lead-in. Shift both by LEAD_HOLD_SECONDS.
10. `private/growth/founder-video-photo-shoot-plan.md` deleted this session per A1. Tracked
   in `private/growth` git, so recoverable. The two founder research docs were kept.

## Checkpoints

Tree patches at every wave boundary land in `checkpoints/`. A host reboot once destroyed a /tmp scratchpad; durable state exists because of that.
