#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TRANSCRIPT_DIR = path.join(ROOT, 'src', 'data', 'team-video-transcripts');

// All languages that need transcript files (audio + caption-only)
const TARGET_LANGUAGES = ['de', 'es', 'fr', 'ja', 'ru', 'zh', 'ar', 'tr'];

const colors = {
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n', 'utf-8');
}

function main() {
  // Discover all members that have English transcripts
  if (!fs.existsSync(TRANSCRIPT_DIR)) {
    console.log(colors.dim('No team-video-transcripts directory found, nothing to scaffold.'));
    return;
  }

  const members = fs
    .readdirSync(TRANSCRIPT_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);

  let created = 0;
  let synced = 0;

  console.log(colors.bold('Team Video Transcript Locale Scaffolding'));
  console.log('='.repeat(60));

  for (const member of members) {
    const enDir = path.join(TRANSCRIPT_DIR, member, 'en');
    if (!fs.existsSync(enDir)) continue;

    const enFiles = fs.readdirSync(enDir).filter((f) => f.endsWith('.json') && !f.startsWith('.'));

    for (const file of enFiles) {
      const source = readJson(path.join(enDir, file));

      for (const lang of TARGET_LANGUAGES) {
        const targetPath = path.join(TRANSCRIPT_DIR, member, lang, file);

        if (fs.existsSync(targetPath)) {
          // Sync structure from English, preserve translated text
          const existing = readJson(targetPath);
          const sourceSegments = source.segments || [];
          const existingSegments = existing.segments || [];
          let changed = false;

          // Sync segment count
          if (existingSegments.length !== sourceSegments.length) {
            // Rebuild segments: keep text for matching indices, add TODO for new ones
            const newSegments = sourceSegments.map((seg, i) => ({
              start: seg.start,
              end: seg.end,
              text:
                i < existingSegments.length && existingSegments[i].text
                  ? existingSegments[i].text
                  : `TODO: translate segment ${i + 1}`,
            }));
            existing.segments = newSegments;
            changed = true;
          } else {
            // Sync timestamps from English
            for (let i = 0; i < sourceSegments.length; i++) {
              if (existingSegments[i].start !== sourceSegments[i].start) {
                existingSegments[i].start = sourceSegments[i].start;
                changed = true;
              }
              if (existingSegments[i].end !== sourceSegments[i].end) {
                existingSegments[i].end = sourceSegments[i].end;
                changed = true;
              }
            }
          }

          if (changed) {
            writeJson(targetPath, existing);
            synced++;
            console.log(colors.cyan(`  Synced  ${member}/${lang}/${file}`));
          }
          continue;
        }

        // Create new locale file from English template
        const locale = {
          member: source.member,
          videoKey: source.videoKey,
          segments: (source.segments || []).map((seg) => ({
            start: seg.start,
            end: seg.end,
            text: seg.text, // English text as starting point for translation
          })),
        };

        writeJson(targetPath, locale);
        created++;
        console.log(colors.green(`  Created ${member}/${lang}/${file}`));
      }
    }
  }

  console.log('='.repeat(60));
  console.log(`Created: ${created}, Synced: ${synced}`);
}

main();
