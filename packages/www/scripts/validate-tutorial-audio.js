#!/usr/bin/env node

// ---------------------------------------------------------------------------
// AI TROUBLESHOOTING GUIDE
// ---------------------------------------------------------------------------
//
// This validator checks that tutorial timeline JSON files and audio assets
// are consistent with the transcript files.
//
// IMPORTANT: This script must run AFTER validate-tutorial-transcripts.js.
// If transcripts contain TODO placeholders, fix those FIRST -- otherwise
// the TTS generator will synthesize the literal TODO text as spoken audio.
//
// COMMON ERRORS AND FIXES:
//
// ERROR: "transcriptHash is stale" / "step count must match transcript events"
//   CAUSE: Transcript was updated but TTS audio + timeline not regenerated.
//   FIX: Ensure transcript text is finalized (no TODOs), then run:
//     ./run.sh www tutorials generate
//
// ERROR: "audio file missing"
//   CAUSE: Timeline references an audio file that doesn't exist on disk.
//   FIX: Run: ./run.sh www tutorials generate
//
// ERROR: "Missing tutorial timeline JSON"
//   CAUSE: Timeline file not yet created for this tutorial/language.
//   FIX: Run: ./run.sh www tutorials generate
//
// FULL PIPELINE (when cast files were re-recorded):
//   ./run.sh www tutorials extract
//   ./run.sh www tutorials scaffold-locales
//   # Write narration text for any TODO events (see validate-tutorial-transcripts.js)
//   ./run.sh www tutorials generate
// ---------------------------------------------------------------------------

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { SITE_LOCALES } from '@rediacc/locales';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TRANSCRIPT_DIR = path.join(ROOT, 'src', 'data', 'tutorial-transcripts');
const TIMELINE_DIR = path.join(ROOT, 'src', 'data', 'tutorial-timeline');
const AUDIO_DIR = path.join(ROOT, 'public', 'assets', 'tutorials', 'audio');
// All 13 site locales. This gate runs in CI *after* `sync-media-from-r2.sh --audio-only`
// (ci-quality.yml), so it validates PUBLISHED audio — which is why it stayed at ten while
// ar/et/tr were narrated locally but unpublished. All three are published now, so the list
// is the full set, sourced from packages/locales rather than hand-maintained.
// `--lang <code>` still validates any single locale on demand.
const AUDIO_LANGUAGES = SITE_LOCALES;

// --lang/--cast/--quiet exist so an orchestrator can ask "is locale X finished and
// consistent?" between a narration run and dispatching its renders. Everything this
// file already checks -- transcriptHash vs a recomputed hash, step count vs transcript
// events, per-step id/markerIndex/narrationText equality, replay monotonicity, audioSrc
// existence, wordTimings structure and ordering -- is exactly that readiness question,
// so the alternative (a done-marker file written by the producer) would be a weaker
// claim about the same thing.
function parseCliArgs(argv) {
  const opts = { langs: null, casts: null, quiet: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const take = (name) => {
      const inline = arg.startsWith(`${name}=`) ? arg.slice(name.length + 1) : null;
      if (inline !== null) return inline;
      if (arg === name) {
        i += 1;
        return argv[i];
      }
      return null;
    };
    if (arg === '--quiet' || arg === '-q') {
      opts.quiet = true;
      continue;
    }
    const lang = take('--lang');
    if (lang) {
      opts.langs = new Set((opts.langs ? [...opts.langs] : []).concat(lang.split(',')));
      continue;
    }
    const cast = take('--cast');
    if (cast) {
      opts.casts = new Set((opts.casts ? [...opts.casts] : []).concat(cast.split(',')));
      continue;
    }
    if (arg === '--help' || arg === '-h') {
      console.log(
        'Usage: validate-tutorial-audio.js [--lang a,b] [--cast key,key] [--quiet]\n' +
          '  --lang   validate these locales instead of the published default set\n' +
          '  --cast   restrict to these tutorial cast keys\n' +
          '  --quiet  print nothing on success (exit code is the result)'
      );
      process.exit(0);
    }
    console.error(`validate-tutorial-audio: unknown argument ${arg}`);
    process.exit(2);
  }
  return opts;
}

const CLI = parseCliArgs(process.argv.slice(2));

function shouldValidateLang(lang) {
  return CLI.langs ? CLI.langs.has(lang) : AUDIO_LANGUAGES.includes(lang);
}

// Engines allowed to have produced a timeline. A set rather than one string because the
// migration to voxcpm2 re-narrates 180 timelines and cannot land atomically, so both
// values are legitimately present mid-flight. Keep this in sync with
// tutorial_tts/audio.py::get_engine: the point is to reject an UNKNOWN provider (a typo,
// or an engine nobody reviewed), not to pin one.
const KNOWN_TTS_PROVIDERS = new Set(['qwen3-tts', 'voxcpm2']);
// NO locale reuses English audio any more. ar/et/tr used to have timelines DERIVED from
// the en timelines by derive-fallback-timeline.ts, because Qwen3-TTS could not voice
// them; VoxCPM2 now narrates all 13 natively, so those three have their own mp3s and
// their own word timings like every other locale. derive-fallback-timeline.ts is dormant
// (its FALLBACK_LANGUAGES is empty) and refuses to overwrite a locale that has real
// narration.

// The audio tree is synced to R2, not committed to git (see
// .ci/docs/r2-media-setup.md #9) -- a clean checkout has none of it locally,
// which is expected, not a bug. Only assert individual files exist when the
// tree is present at all (e.g. after `./run.sh www tutorials generate` or
// `.ci/scripts/deploy/sync-media-from-r2.sh --audio-only`); every other
// check in this file (hash consistency, wordTimings structure, replay-range
// sanity) still runs regardless, since none of that depends on the mp3
// bytes actually being on disk.
const AUDIO_TREE_PRESENT = fs.existsSync(AUDIO_DIR);

const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  yellow: (s) => `\x1b[33m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

function hashText(text) {
  return crypto
    .createHash('sha256')
    .update(
      String(text || '')
        .replace(/\s+/g, ' ')
        .trim()
    )
    .digest('hex');
}

function hashTranscript(transcript) {
  const normalized = transcript.events.map((ev) => ({
    id: ev.id,
    markerIndex: ev.markerIndex,
    at: ev.at,
    text: String(ev.text || '')
      .replace(/\s+/g, ' ')
      .trim(),
  }));
  return crypto.createHash('sha256').update(JSON.stringify(normalized)).digest('hex');
}

function listJsonFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .sort((a, b) => a.localeCompare(b));
}

function loadJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf-8'));
}

function pushError(errors, file, message, suggestion) {
  errors.push({ file, message, suggestion });
}

function listTranscriptPairs() {
  const pairs = [];
  if (!fs.existsSync(TRANSCRIPT_DIR)) return pairs;

  for (const lang of fs.readdirSync(TRANSCRIPT_DIR).sort((a, b) => a.localeCompare(b))) {
    const langDir = path.join(TRANSCRIPT_DIR, lang);
    if (!fs.statSync(langDir).isDirectory()) continue;
    for (const file of listJsonFiles(langDir)) {
      const castKey = file.replace(/\.json$/i, '');
      pairs.push({
        lang,
        castKey,
        transcriptPath: path.join(langDir, file),
        timelinePath: path.join(TIMELINE_DIR, lang, file),
      });
    }
  }
  return pairs;
}

function validatePair({ lang, transcriptPath, timelinePath, errors }) {
  if (!shouldValidateLang(lang)) return;

  const transcript = loadJson(transcriptPath);
  const relativeTimeline = path.relative(ROOT, timelinePath);

  if (!fs.existsSync(timelinePath)) {
    pushError(
      errors,
      relativeTimeline,
      'Missing tutorial timeline JSON.',
      'Run: ./run.sh www generate'
    );
    return;
  }

  const timeline = loadJson(timelinePath);
  const steps = Array.isArray(timeline.steps) ? timeline.steps : [];

  if (timeline.version !== 1)
    pushError(errors, relativeTimeline, 'version must be 1.', 'Regenerate timeline');
  if (!KNOWN_TTS_PROVIDERS.has(timeline.provider))
    pushError(
      errors,
      relativeTimeline,
      `provider must be one of: ${[...KNOWN_TTS_PROVIDERS].join(', ')}.`,
      'Regenerate timeline'
    );
  if (timeline.cast !== transcript.cast)
    pushError(errors, relativeTimeline, 'cast must match transcript.cast.', 'Regenerate timeline');
  if (timeline.language !== lang)
    pushError(errors, relativeTimeline, `language must be ${lang}.`, 'Regenerate timeline');
  if (!Array.isArray(timeline.steps))
    pushError(errors, relativeTimeline, 'steps must be an array.', 'Regenerate timeline');

  const expectedHash = hashTranscript(transcript);
  if (timeline.transcriptHash !== expectedHash) {
    pushError(errors, relativeTimeline, 'transcriptHash is stale.', 'Regenerate timeline');
  }

  if (steps.length !== transcript.events.length) {
    pushError(
      errors,
      relativeTimeline,
      'step count must match transcript events count.',
      'Regenerate timeline'
    );
  }

  for (let i = 0; i < Math.min(steps.length, transcript.events.length); i += 1) {
    const step = steps[i];
    const event = transcript.events[i];
    if (step.id !== event.id)
      pushError(errors, relativeTimeline, `steps[${i}].id mismatch`, 'Regenerate timeline');
    if (step.markerIndex !== event.markerIndex)
      pushError(
        errors,
        relativeTimeline,
        `steps[${i}].markerIndex mismatch`,
        'Regenerate timeline'
      );
    if (step.narrationText !== event.text)
      pushError(
        errors,
        relativeTimeline,
        `steps[${i}].narrationText mismatch`,
        'Regenerate timeline'
      );

    if (
      !Number.isFinite(step.replayStartSec) ||
      !Number.isFinite(step.replayEndSec) ||
      step.replayEndSec < step.replayStartSec
    ) {
      pushError(
        errors,
        relativeTimeline,
        `steps[${i}] replay range invalid`,
        'Regenerate timeline'
      );
    }

    if (
      i > 0 &&
      Number.isFinite(step.replayStartSec) &&
      Number.isFinite(steps[i - 1]?.replayStartSec)
    ) {
      if (step.replayStartSec < steps[i - 1].replayStartSec) {
        pushError(
          errors,
          relativeTimeline,
          `steps[${i}] replayStartSec must be sorted`,
          'Regenerate timeline'
        );
      }
    }

    if (
      typeof step.audioSrc !== 'string' ||
      !step.audioSrc.startsWith('/assets/tutorials/audio/')
    ) {
      pushError(errors, relativeTimeline, `steps[${i}].audioSrc invalid`, 'Regenerate timeline');
    } else if (AUDIO_TREE_PRESENT) {
      const absAudio = path.join(ROOT, 'public', step.audioSrc.replace(/^\//, ''));
      if (!fs.existsSync(absAudio)) {
        pushError(
          errors,
          relativeTimeline,
          `steps[${i}] audio file missing: ${step.audioSrc}`,
          'Regenerate timeline audio'
        );
      }
    }

    if (step.wordTimings !== undefined) {
      if (!Array.isArray(step.wordTimings)) {
        pushError(
          errors,
          relativeTimeline,
          `steps[${i}].wordTimings must be array`,
          'Regenerate timeline'
        );
      } else {
        let prev = -1;
        for (let j = 0; j < step.wordTimings.length; j += 1) {
          const wt = step.wordTimings[j];
          if (
            !Number.isFinite(wt.startSec) ||
            !Number.isFinite(wt.endSec) ||
            wt.endSec <= wt.startSec
          ) {
            pushError(
              errors,
              relativeTimeline,
              `steps[${i}].wordTimings[${j}] invalid times`,
              'Regenerate timeline'
            );
          }
          if (
            !Number.isInteger(wt.startChar) ||
            !Number.isInteger(wt.endChar) ||
            wt.startChar < 0 ||
            wt.endChar <= wt.startChar ||
            wt.endChar > event.text.length
          ) {
            pushError(
              errors,
              relativeTimeline,
              `steps[${i}].wordTimings[${j}] invalid char bounds`,
              'Regenerate timeline'
            );
          }
          if (wt.startSec < prev)
            pushError(
              errors,
              relativeTimeline,
              `steps[${i}].wordTimings must be sorted`,
              'Regenerate timeline'
            );
          prev = wt.startSec;
        }
      }
    }

    const textHash = hashText(event.text);
    if (!textHash || textHash.length !== 64) {
      pushError(
        errors,
        relativeTimeline,
        `steps[${i}] text hash computation failed`,
        'Check validator'
      );
    }
  }
}

function main() {
  const errors = [];
  const pairs = listTranscriptPairs().filter(
    (p) => (!CLI.casts || CLI.casts.has(p.castKey)) && shouldValidateLang(p.lang)
  );

  if (!CLI.quiet) {
    console.log(colors.bold('Tutorial Timeline Validation'));
    console.log('='.repeat(60));
  }

  // A selective run that matches nothing must FAIL, not pass. As a readiness gate this
  // is the whole point: "validate locale et" silently checking zero files and exiting 0
  // would tell an orchestrator that an unnarrated locale is ready to render.
  if ((CLI.langs || CLI.casts) && pairs.length === 0) {
    console.error(
      colors.red(
        `✗ No transcript/timeline pairs matched ${CLI.langs ? `--lang ${[...CLI.langs].join(',')}` : ''}` +
          `${CLI.casts ? ` --cast ${[...CLI.casts].join(',')}` : ''}. Nothing was validated.`
      )
    );
    process.exit(1);
  }

  // Likewise fail-closed on a selective run with no audio on disk. The default run
  // tolerates a missing tree (a clean checkout legitimately has none), but an explicit
  // --lang is asking whether real files are ready, and "skipped the file checks" is not
  // an answer to that.
  if ((CLI.langs || CLI.casts) && !AUDIO_TREE_PRESENT) {
    console.error(
      colors.red(
        `✗ Audio tree ${AUDIO_DIR} is absent, so per-file checks cannot run. A selective ` +
          'run must not report success on structure alone.'
      )
    );
    process.exit(1);
  }

  if (!fs.existsSync(TIMELINE_DIR)) {
    console.log(
      colors.yellow(
        'Timeline directory is missing. Skipping validation (generation not bootstrapped yet).'
      )
    );
    console.log('='.repeat(60));
    process.exit(0);
  }

  if (!AUDIO_TREE_PRESENT && !CLI.quiet) {
    console.log(
      colors.yellow(
        'Audio tree not present locally (synced to R2, not committed to git -- see ' +
          '.ci/docs/r2-media-setup.md #9). Skipping per-file existence checks; timeline ' +
          'structure/hash/wordTimings checks still run. To check physical audio files too, run: ' +
          '.ci/scripts/deploy/sync-media-from-r2.sh --audio-only'
      )
    );
  }

  for (const pair of pairs) {
    validatePair({ ...pair, errors });
  }

  if (errors.length === 0) {
    if (!CLI.quiet) {
      console.log(
        colors.green(`✓ Tutorial timelines and assets are valid (${pairs.length} pair(s) checked).`)
      );
      console.log('='.repeat(60));
    }
    process.exit(0);
  }

  console.error(colors.red(`✗ Found ${errors.length} issue(s):`));
  for (const issue of errors) {
    console.error(`- ${issue.file}: ${issue.message}`);
    if (issue.suggestion) console.error(`  -> ${issue.suggestion}`);
  }
  console.log('='.repeat(60));
  process.exit(1);
}

main();
