#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const CAST_DIR = path.join(ROOT, 'public', 'assets', 'tutorials');
const OUT_DIR = path.join(ROOT, 'src', 'data', 'tutorial-transcripts', 'en');

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

function readMarkers(castPath) {
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
    const [at, type, value] = event;
    if (type !== 'm') continue;
    if (typeof at !== 'number' || typeof value !== 'string') continue;

    markers.push({ at, markerText: value });
  }

  return markers;
}

function run() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const castFiles = fs
    .readdirSync(CAST_DIR)
    .filter((f) => f.endsWith('.cast'))
    .sort((a, b) => a.localeCompare(b));

  for (const castFile of castFiles) {
    const castPath = path.join(CAST_DIR, castFile);
    const castKey = castFile.replace(/\.cast$/i, '');
    const markers = readMarkers(castPath);
    const outPath = path.join(OUT_DIR, `${castKey}.json`);

    const existing = fs.existsSync(outPath) ? readJson(outPath) : null;

    const events = markers.map((marker, index) => {
      const existingEvent = existing?.events?.[index];
      return {
        id: `${castKey}-${String(index + 1).padStart(2, '0')}`,
        markerIndex: index,
        at: marker.at,
        text: existingEvent?.text ?? `TODO: write transcript sentence for event ${index + 1}`,
      };
    });

    const doc = {
      cast: `/assets/tutorials/${castFile}`,
      language: 'en',
      version: 1,
      events,
    };

    fs.writeFileSync(outPath, `${JSON.stringify(doc, null, 2)}\n`, 'utf-8');

    const preserved = events.filter((e) => !e.text.startsWith('TODO:')).length;
    const total = events.length;
    const label = existing ? `Updated (${preserved}/${total} preserved)` : 'Scaffolded';
    console.log(`${label} ${path.relative(ROOT, outPath)} (${total} events)`);
  }
}

run();
