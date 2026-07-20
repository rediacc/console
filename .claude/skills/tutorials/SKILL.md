---
name: tutorials
description: Record, regenerate and publish the www tutorial casts/videos. Use when a tutorial cast is stale, a CLI change invalidates recorded commands, or the tutorial-parity / cast-output gates fail.
user-invocable: false
---

# Tutorials — record, regenerate, publish

The pipeline runs commands **for real** on a local KVM cluster and films the terminal. That is
its value and its cost: it is the only check that catches a command which parses but fails at
runtime.

## Artifact chain

```
.ci/tutorials/<slug>.sh          executed on the bridge VM  ─┐
                                                             ├─> .cast (asciinema)
tutorial-storyboard/<slug>.json  card.commandFull ───────────┘
        │ extract
        ▼
tutorial-transcripts/<lang>/     narration text
        │ generate  (TTS, keyed on textHash)
        ▼
tutorial-timeline/<lang>/        wordTimings + audio refs
        │ video     (ffmpeg)
        ▼
public/assets/tutorials/*.mp4
```

## The loop

```bash
./run.sh www tutorials record --keep-vms   # films; --keep-vms leaves the cluster for video
./run.sh www tutorials extract             # cast markers -> transcripts (preserves text)
./run.sh www tutorials scaffold-locales
./run.sh www tutorials generate            # TTS + timelines
./run.sh www tutorials video --jobs 6      # ffmpeg-bound; raise on a many-core box
```

`www tutorials all` chains record → extract → generate → video.

## Prerequisites

```bash
./rdc.sh ops check      # host readiness (kvm, virsh, libvirtd, groups)
./rdc.sh ops status     # what is running
./rdc.sh ops up         # provision (record does this itself)
./rdc.sh ops down       # destroy
```

**`REDIACC_ALLOW_GRAND_REPO=*` must be exported BEFORE starting an AI-agent session.** The
recorder refuses otherwise (`run.sh` checks `CLAUDECODE`). It cannot be set from inside the
session — that is the point of the guard.

## Rules that cost real time to learn

**Every prompting command needs its confirmation bypass.** A prompt inside a recording hangs
forever; `2>/dev/null` hides the question and `|| true` cannot rescue a command that never
returns. **Enforced in CI** — no need to audit by hand:

```bash
npm run check:ci-tutorial-noninteractive
```

It derives the prompting commands from the CLI's own command tree (an option described as
"Skip confirmation …" *is* the command admitting it prompts), so a new one is covered the day it
lands and a renamed flag cannot silently drop coverage. Currently 18 commands, e.g. `repo delete`,
`backup restore`, `datastore delete`, `machine remove` → `-y/--yes`; `machine prune`,
`machine deprovision`, `storage prune` → `--force`.

`repo up`/`repo down` only prompt for **batch** operations, so the flag is required just with
`--all` — a gate that demands it everywhere would be noise, and noisy gates get suppressed.

**Liveness is the log's mtime, not the process.** A hung recorder still shows in `pgrep`.

```bash
stat -c '%y' <logfile>          # if this is minutes old, it is stuck
ssh <bridge> "uptime"           # load ~0 while "running" = blocked on a prompt
```

**Recording restarts from zero on any interruption.** `.recording-hashes` is written only after a
complete run, so killing it to peek discards all progress. Read the log instead.

**Interruptions fill the VM disks.** Each restart re-uploads renet (~450 MB) and Docker images to
an 11 GB root. If provisioning fails on an scp, the disk is full — `ops down && ops up`, do not
retry.

**Diagnose a hang from the cast, not the log.** The failure text is inside the recording:

```bash
ssh <bridge> "python3 -c \"
import json
print(''.join(e[2] for e in map(json.loads, open('/tmp/tutorial-raw-XXXX.cast'))
      if isinstance(e,list) and len(e)>2 and e[1]=='o')[-1500:])\""
```

## Cost model

TTS reuse is keyed on `textHash` **plus the mp3 existing on disk**
(`private/generative/src/tutorial_tts/cli.py`), not on the cast. So re-recording is nearly free
for audio **if** the cache is present:

```bash
.ci/scripts/deploy/sync-media-from-r2.sh --audio-only   # ~2900 files, ~415 MB
```

`generate` restores this itself. If it starts synthesizing broadly, **stop** — `extract` changed
narration text and the cost assumption is broken.

Wall-clock is dominated by `video` (ffmpeg), not recording.

## Locales

13 locales × 18 tutorials. Timelines exist for all 13; **audio for 10** — `ar/et/tr` have no
narration because the TTS cannot voice them, and fall back like the solution videos. That
asymmetry is by design, not a gap.

## Gates

```bash
npm run check:ci-tutorial-commands    # storyboard commandFull/teardownCommand vs live CLI
npm run check:ci-tutorial-parity      # storyboard vs recorded marker
npm run check:ci-tutorial-casts       # cast output sanity
npm run validate:tutorial-audio -w @rediacc/www
npm run check:ci-locale-tutorial-assets
npm run check:ci-tutorial-caption-sync
npm run check:ci-account-onboarding   # commandFull feeds the portal first-run flow
```

**A static gate cannot catch a runtime constraint.** `backup list --storage X -m Y` parses (both
flags exist) but the CLI rejects the pair. Only executing the tutorial finds that class — which is
the argument for re-recording rather than hand-editing casts.

`tutorial-parity-baseline.json` is exact-keyed and shrink-only: it *demands* deletion of entries
once a scene is re-recorded. Delete them, never re-freeze.

## Publish

```bash
.ci/scripts/deploy/sync-media-to-r2.sh --tutorials-only
```

Commit the regenerated `video-manifest.json`, timelines and `.recording-hashes`.
**Never** run `generate-video-manifest.ts` — it rebuilds from a local filesystem scan and silently
drops every entry whose media is not checked out.

## When a tutorial fails

1. Read the cast (above) — the log only says `exited with code N`.
2. Fix the command against `./rdc.sh <cmd> --help`, never from memory.
3. Update the storyboard `commandFull` to match, or parity breaks.
4. Restart. Completed tutorials are skipped only if the previous run finished.
