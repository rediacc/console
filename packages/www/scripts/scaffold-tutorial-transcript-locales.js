#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const TRANSCRIPT_DIR = path.join(ROOT, 'src', 'data', 'tutorial-transcripts');
const SOURCE_LANG = 'en';
const TARGET_LANGS = ['de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh', 'et', 'ko', 'pt', 'it'];

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
}

function isAuthored(value) {
  return typeof value === 'string' && value.trim().length > 0 && !value.startsWith('TODO:');
}

function todoFor(kind, enValue) {
  if (typeof enValue === 'string' && enValue.length > 0) {
    return `TODO: translate ${kind} (en: ${enValue})`;
  }
  return `TODO: translate ${kind}`;
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
          const next = {
            ...source.events[i],
            text: `TODO: translate event ${i + 1}`,
          };
          if (typeof source.events[i].afterText === 'string') {
            next.afterText = `TODO: translate after-text for event ${i + 1}`;
          }
          if (typeof source.events[i].cardLabel === 'string') {
            next.cardLabel = todoFor('cardLabel', source.events[i].cardLabel);
          }
          if (typeof source.events[i].prose === 'string') {
            next.prose = todoFor('prose', source.events[i].prose);
          }
          if (typeof source.events[i].afterProse === 'string') {
            next.afterProse = todoFor('afterProse', source.events[i].afterProse);
          }
          existing.events.push(next);
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
        // Sync afterText field: propagate addition/removal, preserve existing translation.
        const srcHasAfter = typeof source.events[i].afterText === 'string';
        const locHasAfter = typeof existing.events[i].afterText === 'string';
        if (srcHasAfter && !locHasAfter) {
          existing.events[i].afterText = `TODO: translate after-text for event ${i + 1}`;
          changed = true;
        } else if (!srcHasAfter && locHasAfter) {
          delete existing.events[i].afterText;
          changed = true;
        }
        // Sync cardLabel field: propagate addition/removal, preserve existing translation.
        const srcHasCard = typeof source.events[i].cardLabel === 'string';
        const locHasCard = typeof existing.events[i].cardLabel === 'string';
        if (srcHasCard && !locHasCard) {
          existing.events[i].cardLabel = todoFor('cardLabel', source.events[i].cardLabel);
          changed = true;
        } else if (!srcHasCard && locHasCard) {
          delete existing.events[i].cardLabel;
          changed = true;
        }
        // Sync prose field (docs-page instructional override).
        const srcHasProse = typeof source.events[i].prose === 'string';
        const locHasProse = typeof existing.events[i].prose === 'string';
        if (srcHasProse && !locHasProse) {
          existing.events[i].prose = todoFor('prose', source.events[i].prose);
          changed = true;
        } else if (!srcHasProse && locHasProse) {
          delete existing.events[i].prose;
          changed = true;
        }
        // Sync afterProse field (docs-page instructional override for afterText).
        const srcHasAfterProse = typeof source.events[i].afterProse === 'string';
        const locHasAfterProse = typeof existing.events[i].afterProse === 'string';
        if (srcHasAfterProse && !locHasAfterProse) {
          existing.events[i].afterProse = todoFor('afterProse', source.events[i].afterProse);
          changed = true;
        } else if (!srcHasAfterProse && locHasAfterProse) {
          delete existing.events[i].afterProse;
          changed = true;
        }
      }

      // Sync top-level `title`: propagate addition/removal, preserve translation.
      const srcHasTitle = typeof source.title === 'string';
      const locHasTitle = typeof existing.title === 'string';
      if (srcHasTitle && !locHasTitle) {
        existing.title = todoFor('title', source.title);
        changed = true;
      } else if (!srcHasTitle && locHasTitle) {
        delete existing.title;
        changed = true;
      }

      // Sync `chapters` map: union of keys, preserve existing translations.
      const srcChapters =
        source.chapters && typeof source.chapters === 'object' ? source.chapters : null;
      if (srcChapters) {
        const existingChapters =
          existing.chapters && typeof existing.chapters === 'object' ? existing.chapters : {};
        const nextChapters = {};
        for (const key of Object.keys(srcChapters)) {
          if (isAuthored(existingChapters[key])) {
            nextChapters[key] = existingChapters[key];
          } else {
            nextChapters[key] = todoFor('chapter', srcChapters[key]);
          }
        }
        const beforeKeys = Object.keys(existingChapters).sort().join(',');
        const afterKeys = Object.keys(nextChapters).sort().join(',');
        if (beforeKeys !== afterKeys || beforeKeys !== Object.keys(srcChapters).sort().join(',')) {
          existing.chapters = nextChapters;
          changed = true;
        } else {
          // Even when key sets match, refresh TODO markers in case the EN value changed.
          for (const key of Object.keys(srcChapters)) {
            if (!isAuthored(existingChapters[key]) && existingChapters[key] !== nextChapters[key]) {
              existing.chapters = nextChapters;
              changed = true;
              break;
            }
          }
        }
      } else if (existing.chapters) {
        delete existing.chapters;
        changed = true;
      }

      // Sync narrations[] (intro/slide/browser/outro narrations) by id.
      // Add missing ids as TODO placeholders, remove extras, preserve translations.
      const sourceNarrations = Array.isArray(source.narrations) ? source.narrations : [];
      const existingNarrations = Array.isArray(existing.narrations) ? existing.narrations : [];
      const existingNarrationByID = new Map(
        existingNarrations.filter((n) => n && typeof n.id === 'string').map((n) => [n.id, n])
      );
      const sourceIDs = new Set();
      const nextNarrations = sourceNarrations.map((src) => {
        if (!src || typeof src.id !== 'string') return src;
        sourceIDs.add(src.id);
        const existingEntry = existingNarrationByID.get(src.id);
        if (existingEntry && typeof existingEntry.text === 'string') {
          return { id: src.id, text: existingEntry.text };
        }
        return { id: src.id, text: `TODO: translate narration ${src.id}` };
      });
      // Detect drift: id-set difference or count change
      const idsDiffer =
        sourceNarrations.length !== existingNarrations.length ||
        existingNarrations.some((n) => n && typeof n.id === 'string' && !sourceIDs.has(n.id)) ||
        sourceNarrations.some((n, i) => existingNarrations[i]?.id !== n?.id);
      if (sourceNarrations.length > 0 && (existingNarrations.length === 0 || idsDiffer)) {
        existing.narrations = nextNarrations;
        changed = true;
      } else if (sourceNarrations.length === 0 && existingNarrations.length > 0) {
        // SAFETY: do NOT auto-delete locale narrations when EN has none.
        // This usually indicates EN was inadvertently wiped (e.g. by an old
        // version of extract). Auto-delete would destroy translation work.
        console.warn(
          `SKIP-DELETE: ${path.relative(ROOT, targetPath)} has narrations[] but EN does not. Reconcile EN before re-running.`
        );
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
      events: source.events.map((event, i) => {
        const next = { ...event, text: event.text };
        if (typeof event.afterText === 'string') {
          next.afterText = `TODO: translate after-text for event ${i + 1}`;
        }
        if (typeof event.cardLabel === 'string') {
          next.cardLabel = todoFor('cardLabel', event.cardLabel);
        }
        if (typeof event.prose === 'string') {
          next.prose = todoFor('prose', event.prose);
        }
        if (typeof event.afterProse === 'string') {
          next.afterProse = todoFor('afterProse', event.afterProse);
        }
        return next;
      }),
    };
    if (typeof source.title === 'string') {
      localized.title = todoFor('title', source.title);
    }
    if (source.chapters && typeof source.chapters === 'object') {
      const nextChapters = {};
      for (const [key, value] of Object.entries(source.chapters)) {
        nextChapters[key] = todoFor('chapter', value);
      }
      localized.chapters = nextChapters;
    }
    if (Array.isArray(source.narrations) && source.narrations.length > 0) {
      localized.narrations = source.narrations.map((n) =>
        n && typeof n.id === 'string' ? { id: n.id, text: `TODO: translate narration ${n.id}` } : n
      );
    }

    writeJson(targetPath, localized);
    console.log(`Scaffolded ${path.relative(ROOT, targetPath)}`);
  }
}
