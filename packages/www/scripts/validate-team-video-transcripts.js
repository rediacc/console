#!/usr/bin/env node
/**
 * Team Video Transcript Validation
 *
 * Quality gate for team video transcripts:
 * - English transcript exists for every video defined in team-videos.ts video keys
 * - All audio languages have transcript files
 * - No segment has TODO/placeholder text
 * - Segment count matches English
 * - Timestamps are synced with English
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TRANSCRIPT_DIR = path.join(ROOT, 'src', 'data', 'team-video-transcripts');

const AUDIO_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ru', 'zh'];
const ALL_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ru', 'zh', 'ar', 'tr'];

const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

function pushError(errors, file, message, suggestion) {
  errors.push({ file, message, suggestion });
}

function discoverMembers() {
  if (!fs.existsSync(TRANSCRIPT_DIR)) return [];
  return fs
    .readdirSync(TRANSCRIPT_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);
}

function discoverVideoKeys(member) {
  const enDir = path.join(TRANSCRIPT_DIR, member, 'en');
  if (!fs.existsSync(enDir)) return [];
  return fs
    .readdirSync(enDir)
    .filter((f) => f.endsWith('.json') && !f.startsWith('.'))
    .map((f) => f.replace(/\.json$/, ''));
}

function validateSegmentSchema(segments, file, errors) {
  if (!Array.isArray(segments)) {
    pushError(errors, file, 'segments must be an array.', 'Fix JSON structure');
    return;
  }

  segments.forEach((seg, i) => {
    if (!seg || typeof seg !== 'object') {
      pushError(errors, file, `segments[${i}] must be an object.`, 'Fix segment shape');
      return;
    }

    if (typeof seg.start !== 'number' || Number.isNaN(seg.start) || seg.start < 0) {
      pushError(
        errors,
        file,
        `segments[${i}].start must be a non-negative number.`,
        'Set start timestamp'
      );
    }

    if (typeof seg.end !== 'number' || Number.isNaN(seg.end) || seg.end < 0) {
      pushError(
        errors,
        file,
        `segments[${i}].end must be a non-negative number.`,
        'Set end timestamp'
      );
    }

    if (typeof seg.text !== 'string' || seg.text.trim().length === 0) {
      pushError(
        errors,
        file,
        `segments[${i}].text must be a non-empty string.`,
        'Add transcript text'
      );
    }

    if (typeof seg.text === 'string' && /^TODO:/i.test(seg.text)) {
      pushError(
        errors,
        file,
        `segments[${i}].text is a TODO placeholder.`,
        'Write or translate the segment text'
      );
    }
  });
}

function main() {
  const errors = [];
  const members = discoverMembers();

  if (members.length === 0) {
    console.log(colors.dim('No team video transcripts found. Skipping validation.'));
    process.exit(0);
  }

  for (const member of members) {
    const videoKeys = discoverVideoKeys(member);

    if (videoKeys.length === 0) {
      pushError(
        errors,
        `team-video-transcripts/${member}/en/`,
        `No English transcripts found for member "${member}".`,
        'Run team-video extract to generate English transcripts'
      );
      continue;
    }

    for (const videoKey of videoKeys) {
      const enPath = path.join(TRANSCRIPT_DIR, member, 'en', `${videoKey}.json`);
      const enData = readJson(enPath);
      const enSegments = enData.segments || [];
      const enRelative = `team-video-transcripts/${member}/en/${videoKey}.json`;

      // Validate English schema
      validateSegmentSchema(enSegments, enRelative, errors);

      // Check all languages have transcript files
      for (const lang of ALL_LANGUAGES) {
        if (lang === 'en') continue;
        const localePath = path.join(TRANSCRIPT_DIR, member, lang, `${videoKey}.json`);
        const localeRelative = `team-video-transcripts/${member}/${lang}/${videoKey}.json`;

        if (!fs.existsSync(localePath)) {
          pushError(
            errors,
            localeRelative,
            `Missing ${lang} transcript for "${videoKey}".`,
            `Run team-video scaffold-locales to create ${lang} transcript`
          );
          continue;
        }

        const localeData = readJson(localePath);
        const localeSegments = localeData.segments || [];

        // Validate schema
        validateSegmentSchema(localeSegments, localeRelative, errors);

        // Segment count must match English
        if (localeSegments.length !== enSegments.length) {
          pushError(
            errors,
            localeRelative,
            `Segment count (${localeSegments.length}) differs from English (${enSegments.length}).`,
            'Re-run scaffold-locales to sync segment count'
          );
          continue;
        }

        // Timestamps must match English
        for (let i = 0; i < enSegments.length; i++) {
          if (Math.abs(localeSegments[i].start - enSegments[i].start) > 0.001) {
            pushError(
              errors,
              localeRelative,
              `segments[${i}].start (${localeSegments[i].start}) differs from English (${enSegments[i].start}).`,
              'Re-run scaffold-locales to sync timestamps'
            );
          }
          if (Math.abs(localeSegments[i].end - enSegments[i].end) > 0.001) {
            pushError(
              errors,
              localeRelative,
              `segments[${i}].end (${localeSegments[i].end}) differs from English (${enSegments[i].end}).`,
              'Re-run scaffold-locales to sync timestamps'
            );
          }
        }
      }
    }
  }

  console.log(colors.bold('Team Video Transcript Validation'));
  console.log('='.repeat(60));

  if (errors.length === 0) {
    console.log(colors.green('✓ All team video transcript files are valid.'));
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
