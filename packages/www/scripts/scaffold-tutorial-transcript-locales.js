#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TRANSCRIPT_DIR = path.join(ROOT, 'src', 'data', 'tutorial-transcripts');
const SOURCE_LANG = 'en';
const TARGET_LANGS = ['de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
}

const sourceDir = path.join(TRANSCRIPT_DIR, SOURCE_LANG);
const files = fs
  .readdirSync(sourceDir)
  .filter((f) => f.endsWith('.json'))
  .sort();

for (const file of files) {
  const sourcePath = path.join(sourceDir, file);
  const source = readJson(sourcePath);

  for (const lang of TARGET_LANGS) {
    const targetPath = path.join(TRANSCRIPT_DIR, lang, file);

    if (fs.existsSync(targetPath)) {
      const existing = readJson(targetPath);
      let changed = false;

      // Sync event count: trim excess or add new events from English
      if (existing.events.length > source.events.length) {
        existing.events = existing.events.slice(0, source.events.length);
        changed = true;
      } else if (existing.events.length < source.events.length) {
        for (let i = existing.events.length; i < source.events.length; i++) {
          existing.events.push({
            ...source.events[i],
            text: `TODO: translate event ${i + 1}`,
          });
        }
        changed = true;
      }

      for (let i = 0; i < source.events.length; i++) {
        if (existing.events[i].id !== source.events[i].id) {
          existing.events[i].id = source.events[i].id;
          changed = true;
        }
        if (existing.events[i].at !== source.events[i].at) {
          existing.events[i].at = source.events[i].at;
          changed = true;
        }
        if (existing.events[i].markerIndex !== source.events[i].markerIndex) {
          existing.events[i].markerIndex = source.events[i].markerIndex;
          changed = true;
        }
      }

      if (changed) {
        writeJson(targetPath, existing);
        console.log(`Synced ${path.relative(ROOT, targetPath)}`);
      }
      continue;
    }

    const localized = {
      ...source,
      language: lang,
      events: source.events.map((event) => ({
        ...event,
        text: event.text,
      })),
    };

    writeJson(targetPath, localized);
    console.log(`Scaffolded ${path.relative(ROOT, targetPath)}`);
  }
}
