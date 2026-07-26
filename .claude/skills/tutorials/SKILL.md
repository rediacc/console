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

**Never wait on `pgrep -f "<phrase>"` when the watcher's own command line contains that
phrase.** `until ! pgrep -f "tutorials generate"; do sleep 15; done` matches ITSELF and can
never exit — it polls forever against a step that already finished. This cost 13 minutes of
apparent "still running" on a completed `generate`. Wait on the log's terminal marker instead,
which is also what actually tells you the step succeeded:

```bash
until grep -q 'Manifests written:' "$LOG"; do sleep 15; done
```

**`video` is safe to stop; `record` and `generate` are not.** Video is pure ffmpeg re-derived
from the timelines — stopping costs CPU only. Stop it whenever its inputs (the casts) are about
to change, rather than letting it finish against stale ones.

**A 15-20 min silent gap in `video2.log` is NORMAL.** The log prints one line per scene START, so
a slow render looks like silence. `tutorial-live-migration.cast` is 160K — 4x the next largest —
and `agg` spends 16+ min per locale on it, six locales at once. Before calling it hung, check the
work rather than the log:

```bash
ps -eo pcpu,etime,comm --sort=-pcpu | head   # agg/ffmpeg with rising ELAPSED = progressing
```

**`ffmpeg` idling is NOT a stall.** Video alternates `agg` (renders the cast to frames) and
`ffmpeg` (muxes). During an agg phase `pgrep ffmpeg` is legitimately 0 while load stays ~40, so a
watcher keyed on "no ffmpeg + stale log" reports completion that never happened. Key completion on
the TOP-LEVEL pid instead — walk `ps -o ppid=` up until the parent is the session relay, then
`while kill -0 <root>`.

**`pgrep … | head -1` picks the WRAPPER, not the worker.** Bit three separate jobs here (video,
record, r2 sync): the lowest pid is the `setsid`/`nohup`/`run.sh` shell that exits immediately,
so a watch on it reports completion while the real work continues. Confirm what you are about to
wait on before waiting on it:

```bash
pgrep -af "<job>"            # read the FULL command lines, pick the one doing the work
ps -o pid=,etime=,cmd= -p <pid>
```

**The PID you launch is not the process doing the work.** `run.sh … video --jobs N` forks a second
`run.sh` that owns the workers; the first exits immediately, so a `kill -0 <launched-pid>` watch
reports "completed" while ffmpeg is still spawning. Kill the process GROUP and verify by count:

```bash
kill -9 -- -$(ps -o pgid= -p <worker-parent> | tr -d ' ')
pgrep -c ffmpeg          # must reach 0; re-check, it respawns while the parent lives
rm -rf /tmp/tutorial-video-*
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

Wall-clock is dominated by `video` (ffmpeg), not recording. Budget it: **18 tutorials × 10
narrated locales = 180 mp4s**, several hours on a 20-core box.

**Do not raise `--jobs` to "use idle cores".** Each ffmpeg is already multi-threaded, so
`--jobs 6` drives load average to ~40 on 20 cores — the box is oversubscribed 2× before you add
anything. Check `/proc/loadavg` against `nproc` before concluding there is headroom.

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

**Parity compares the resolved command PATH, not the text.** `commandPath()` delegates to
`rdcCommandPath()`, which walks the real command tree — a storyboard's `<machine-name>` and the
recording's `machine-11` both resolve to `machine add`. Never reintroduce the old heuristic
("leading tokens up to the first `-` or `<`"): it silently broke when targets became positional
refs, since a concrete value is indistinguishable from a subcommand while a placeholder still
stops the scan. It produced 68 phantom breaks, all of which got baselined.

`tutorial-parity-baseline.json` was exact-keyed and shrink-only: it *demanded* deletion of entries
once a scene was re-recorded. It is now DELETED — all 75 entries turned out to be that one parser
bug, not real drift. If a baseline ever returns, treat a large entry count as evidence of a broken
gate, not of accumulated debt. A baseline that only ever grows is hiding something.

**Recorded commands must use long flags for literal values.** `rdc term connect <ref> -c 'cmd'`
fails parity; use `--command`. When sweeping, anchor on `rdc term connect <one-token>` — several
payloads contain a nested `psql … -c "…"` that must survive.

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

## Sequence validation (CI + local)

`.ci/tutorials/run-sequence.sh` runs EVERY tutorial script sequentially in
website order (derived from the docs' `order:` frontmatter — single source of
truth) on one shared cluster, exit code = verdict. No casts, no asciinema —
this validates the user journey, not the recordings. A doc without a script or
an orphan script is drift and fails the run. CI runs it inside
`ops-vm-provision` (`.github/workflows/ci-ops-test.yml`); adding/removing/
reordering a tutorial updates CI automatically.

Local (cluster must be up; second worker + RustFS needed for the full set):

```bash
VM_CEPH_NODES= ./rdc.sh ops up            # bridge + 2 workers
./private/renet/bin/renet ops rustfs start
./private/renet/bin/renet ops rustfs create-bucket rediacc-test
HOME=<scratch> TUTORIAL_RDC_CMD=$PWD/rdc.sh \
  TUTORIAL_MACHINE_IP=192.168.111.11 TUTORIAL_BACKUP_HOST=192.168.111.12 \
  TUTORIAL_SSH_KEY=~/.renet/staging/.ssh/id_rsa TUTORIAL_CHAR_DELAY=0 \
  .ci/tutorials/run-sequence.sh
```

Use a SCRATCH `HOME` — every tutorial preamble wipes
`~/.config/rediacc/rediacc.json`. `TUTORIAL_ONLY="slug slug"` runs a subset in
sequence order. Local port 3000 must be free (work-with-repo's tunnel; the
driver prechecks and names the holder).
