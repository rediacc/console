#!/usr/bin/env node

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TRANSCRIPT_DIR = path.join(ROOT, 'src', 'data', 'tutorial-transcripts');
const TIMELINE_DIR = path.join(ROOT, 'src', 'data', 'tutorial-timeline');
const AUDIO_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ru', 'zh'];
const AUDIO_FALLBACK_LANGUAGES = ['ar', 'tr'];

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
  if (!AUDIO_LANGUAGES.includes(lang)) return;

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
  if (timeline.provider !== 'qwen3-tts')
    pushError(errors, relativeTimeline, 'provider must be qwen3-tts.', 'Regenerate timeline');
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
    } else {
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
  const pairs = listTranscriptPairs();

  console.log(colors.bold('Tutorial Timeline Validation'));
  console.log('='.repeat(60));

  if (!fs.existsSync(TIMELINE_DIR)) {
    console.log(
      colors.yellow(
        'Timeline directory is missing. Skipping validation (generation not bootstrapped yet).'
      )
    );
    console.log('='.repeat(60));
    process.exit(0);
  }

  for (const blockedLang of AUDIO_FALLBACK_LANGUAGES) {
    const blockedDir = path.join(TIMELINE_DIR, blockedLang);
    if (!fs.existsSync(blockedDir)) continue;
    for (const file of listJsonFiles(blockedDir)) {
      pushError(
        errors,
        path.relative(ROOT, path.join(blockedDir, file)),
        `Locale ${blockedLang} should not contain tutorial timeline files.`,
        'Delete locale timeline and use English fallback'
      );
    }
  }

  for (const pair of pairs) {
    validatePair({ ...pair, errors });
  }

  if (errors.length === 0) {
    console.log(colors.green('✓ Tutorial timelines and assets are valid.'));
    console.log('='.repeat(60));
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
