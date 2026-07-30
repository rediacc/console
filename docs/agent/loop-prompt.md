# Automated loop prompt — current

The old template still asked for work that is finished (the TTS migration, the OOM
measurement) and asserted a publish freeze the operator has since lifted. It re-fired every
iteration and had to be argued with each time. Replace it with the text below.

Paste this as the `/loop` prompt:

---

Continue the media/locale work in automated mode; never leave it blocked or unaware.

Each iteration:

**(1) Liveness the RELIABLE way.** Resolve a PID and use `kill -0`, or
`ps -eo cmd | grep "[p]attern"` plus log mtime plus output-file counts. Three traps, all
observed in this repo: `pgrep -f "<string>"` matches your own shell (it has produced a
false "alive", stalled a waiter, and as `pkill -f` killed the invoking shell);
`pgrep -c node` counts `snapfuse` via `nodev`; and `ps -eo pid,etime -p <pid>` silently
ignores `-p` because `-e` means all processes. Also: a piped `cmd | tail`'s `$?` is
**tail's** exit code — redirect to a file and check the real status. If nothing runs and
work remains, RELAUNCH — but diagnose the root cause from the log first, never retry blindly.

**(2) Worklist.** Read `/tmp/claude-worklist/home_muhammed_monorepo_console.md`, renew
leases (max 120 min ahead), tick only what you probed. Refresh the session brief and the
compact-recovery handover.

**(3) Advance, in this order:**

- **Watch cutover** — finish `./run.sh www tutorials watch` per
  `docs/tutorial-render-watch.md`: rewire `www_tutorials_video` onto
  `list-tutorial-render-pairs.js`, delete `_tutorial_video_pairs` (dead-bash will demand
  it), add `_tutorial_watch_producer` + the dispatch/help wiring, then converge
  `www_tutorials_media` onto the same path. No `mapfile` — it is a banned command.
- **Locale consolidation** — `subset()` wiring plus the reverse publish assertion in
  `check-solution-videos.ts`; the no-stray-locale-list gate; the Python
  `site-locales.json` loaders. Do NOT fold `engine_qwen.py::LANGUAGE_LABELS`,
  `asr.py::language_map` or `ASR_CAPTION_LANGS` into it — those describe third-party model
  capability, and merging them is the category error behind the wrong-language-audio bug.
- **Verification** — after any media change, re-run `list-tutorial-render-pairs.js
  --stale-only --require-provider voxcpm2` (must be empty) and the tutorial gate suite.

**Standing constraints.** Publishing to R2 is authorised for the current fleet; anything
beyond it needs a fresh decision. Never commit, never push, never flip `VIDEO_LANGS` ahead
of a populated manifest, never touch `.ci/`, `private/elite` or `private/renet`.
Translations must never be shortened to hit a runtime — English is the only language with
a duration budget. One GPU job at a time: VoxCPM peaks near 12.1 GB of a 12,288 MiB card,
so two do not degrade, they OOM (the lease in `tutorial_tts/gpu_lock.py` enforces this, but
a process started before the lease existed does not hold it).

**Report every iteration** with counts of files that exist, not stages that "completed",
and end with a `## Remaining` section naming every open task by id and its state.
