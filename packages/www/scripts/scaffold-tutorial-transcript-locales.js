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
    if (fs.existsSync(targetPath)) continue;

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
