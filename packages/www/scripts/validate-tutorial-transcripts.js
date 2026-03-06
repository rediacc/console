#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const CAST_DIR = path.join(ROOT, 'public', 'assets', 'tutorials');
const TRANSCRIPT_DIR = path.join(ROOT, 'src', 'data', 'tutorial-transcripts');
const TRANSCRIPT_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];

const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

function listCastKeys() {
  return fs
    .readdirSync(CAST_DIR)
    .filter((f) => f.endsWith('.cast'))
    .map((f) => f.replace(/\.cast$/i, ''))
    .sort((a, b) => a.localeCompare(b));
}

function readMarkers(castKey) {
  const castPath = path.join(CAST_DIR, `${castKey}.cast`);
  const lines = fs.readFileSync(castPath, 'utf-8').split(/\r?\n/).filter(Boolean);
  const markers = [];

  for (let i = 1; i < lines.length; i++) {
    let event;
    try {
      event = JSON.parse(lines[i]);
    } catch {
      continue;
    }

    if (!Array.isArray(event) || event.length < 3) continue;
    const [at, type] = event;
    if (type !== 'm' || typeof at !== 'number') continue;
    markers.push({ at, markerIndex: markers.length });
  }

  return markers;
}

function readTranscript(lang, castKey) {
  const filePath = path.join(TRANSCRIPT_DIR, lang, `${castKey}.json`);
  if (!fs.existsSync(filePath)) return null;
  return {
    filePath,
    data: JSON.parse(fs.readFileSync(filePath, 'utf-8')),
  };
}

function pushError(errors, file, message, suggestion) {
  errors.push({ file, message, suggestion });
}

function validateSchema(transcript, file, errors) {
  if (!transcript || typeof transcript !== 'object') {
    pushError(errors, file, 'Transcript file must contain an object.', 'Fix JSON root shape');
    return;
  }

  if (transcript.version !== 1) {
    pushError(errors, file, 'version must be exactly 1.', 'Set "version": 1');
  }

  if (!Array.isArray(transcript.events)) {
    pushError(
      errors,
      file,
      'events must be an array.',
      'Set "events" as an array of event objects'
    );
    return;
  }

  transcript.events.forEach((event, index) => {
    if (!event || typeof event !== 'object') {
      pushError(errors, file, `events[${index}] must be an object.`, 'Fix event shape');
      return;
    }

    if (typeof event.id !== 'string' || event.id.length === 0) {
      pushError(
        errors,
        file,
        `events[${index}].id must be a non-empty string.`,
        'Set a stable event id'
      );
    }

    if (!Number.isInteger(event.markerIndex) || event.markerIndex < 0) {
      pushError(
        errors,
        file,
        `events[${index}].markerIndex must be a non-negative integer.`,
        'Set markerIndex to event marker position'
      );
    }

    if (typeof event.at !== 'number' || Number.isNaN(event.at) || event.at < 0) {
      pushError(
        errors,
        file,
        `events[${index}].at must be a non-negative number.`,
        'Set marker timestamp'
      );
    }

    if (typeof event.text !== 'string' || event.text.trim().length === 0) {
      pushError(
        errors,
        file,
        `events[${index}].text must be a non-empty string.`,
        'Add transcript text'
      );
    }

    if (/\brdc\b/i.test(event.text)) {
      pushError(
        errors,
        file,
        `events[${index}].text must not expose raw command names.`,
        'Rewrite event text in user-facing language'
      );
    }

    if (/^TODO:/i.test(event.text)) {
      pushError(
        errors,
        file,
        `events[${index}].text is a TODO placeholder.`,
        'Write or translate the event text'
      );
    }
  });
}

function validateEnglishParity(castKey, transcript, markers, file, errors) {
  if (transcript.cast !== `/assets/tutorials/${castKey}.cast`) {
    pushError(
      errors,
      file,
      `cast must equal /assets/tutorials/${castKey}.cast.`,
      'Align transcript cast path to the cast file'
    );
  }

  if (transcript.language !== 'en') {
    pushError(
      errors,
      file,
      'language must be "en" for English transcript files.',
      'Set language to en'
    );
  }

  if (transcript.events.length !== markers.length) {
    pushError(
      errors,
      file,
      `English transcript event count (${transcript.events.length}) differs from marker count (${markers.length}).`,
      'Add/remove transcript events to match markers'
    );
  }

  const len = Math.min(transcript.events.length, markers.length);
  for (let i = 0; i < len; i++) {
    const event = transcript.events[i];
    const marker = markers[i];

    if (event.markerIndex !== marker.markerIndex) {
      pushError(
        errors,
        file,
        `events[${i}].markerIndex (${event.markerIndex}) must equal ${marker.markerIndex}.`,
        'Keep marker indices sequential and aligned with cast markers'
      );
    }

    if (Math.abs(event.at - marker.at) > 0.001) {
      pushError(
        errors,
        file,
        `events[${i}].at (${event.at}) differs from cast marker time (${marker.at}).`,
        'Regenerate timestamps from cast markers'
      );
    }
  }
}

function validateOptionalLocale(castKey, lang, transcript, markers, file, errors) {
  if (transcript.cast !== `/assets/tutorials/${castKey}.cast`) {
    pushError(
      errors,
      file,
      `cast must equal /assets/tutorials/${castKey}.cast.`,
      'Align transcript cast path to the cast file'
    );
  }

  if (transcript.language !== lang) {
    pushError(
      errors,
      file,
      `language must be "${lang}" for this locale file.`,
      `Set language to ${lang}`
    );
  }

  if (transcript.events.length !== markers.length) {
    pushError(
      errors,
      file,
      `Locale transcript event count (${transcript.events.length}) differs from marker count (${markers.length}).`,
      'Keep locale transcript event count aligned with marker count'
    );
  }
}

function main() {
  const errors = [];
  const castKeys = listCastKeys();

  for (const castKey of castKeys) {
    const markers = readMarkers(castKey);
    const enFile = readTranscript('en', castKey);

    if (!enFile) {
      pushError(
        errors,
        `src/data/tutorial-transcripts/en/${castKey}.json`,
        'Missing required English transcript file.',
        'Create English transcript JSON'
      );
      continue;
    }

    const enRelative = path.relative(ROOT, enFile.filePath);
    validateSchema(enFile.data, enRelative, errors);
    validateEnglishParity(castKey, enFile.data, markers, enRelative, errors);

    for (const lang of TRANSCRIPT_LANGUAGES) {
      if (lang === 'en') continue;
      const localeFile = readTranscript(lang, castKey);
      if (!localeFile) {
        pushError(
          errors,
          `src/data/tutorial-transcripts/${lang}/${castKey}.json`,
          `Missing required ${lang} transcript file.`,
          `Create ${lang} transcript JSON with translated events`
        );
        continue;
      }

      const localeRelative = path.relative(ROOT, localeFile.filePath);
      validateSchema(localeFile.data, localeRelative, errors);
      validateOptionalLocale(castKey, lang, localeFile.data, markers, localeRelative, errors);

      if (Array.isArray(localeFile.data.events) && Array.isArray(enFile.data.events)) {
        const len = Math.min(localeFile.data.events.length, enFile.data.events.length);
        for (let i = 0; i < len; i += 1) {
          const lev = localeFile.data.events[i];
          const eev = enFile.data.events[i];
          if (lev.id !== eev.id) {
            pushError(
              errors,
              localeRelative,
              `events[${i}].id (${lev.id}) must match English id (${eev.id}).`,
              'Keep localized transcript event IDs aligned with English transcript'
            );
          }
          if (lev.markerIndex !== eev.markerIndex) {
            pushError(
              errors,
              localeRelative,
              `events[${i}].markerIndex (${lev.markerIndex}) must match English markerIndex (${eev.markerIndex}).`,
              'Keep localized transcript markerIndex aligned with English transcript'
            );
          }
          if (Math.abs(Number(lev.at) - Number(eev.at)) > 0.001) {
            pushError(
              errors,
              localeRelative,
              `events[${i}].at (${lev.at}) must match English timestamp (${eev.at}).`,
              'Keep localized transcript timestamps aligned with English transcript'
            );
          }
        }
      }
    }
  }

  console.log(colors.bold('Tutorial Transcript Validation'));
  console.log('='.repeat(60));

  if (errors.length === 0) {
    console.log(colors.green('✓ All tutorial transcript files are valid.'));
    console.log('='.repeat(60));
    process.exit(0);
  }

  for (const error of errors) {
    console.log(colors.red(`✗ ${error.file}`));
    console.log(colors.dim(`  ${error.message}`));
    if (error.suggestion) {
      console.log(colors.cyan(`  → ${error.suggestion}`));
    }
  }

  console.log('='.repeat(60));
  console.log(colors.red(`✗ Validation failed (${errors.length} errors)`));
  process.exit(1);
}

main();
