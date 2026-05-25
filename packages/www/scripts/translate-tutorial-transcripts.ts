#!/usr/bin/env node
/**
 * Translates TODO markers in non-EN tutorial transcripts via the Anthropic API.
 *
 * Reads every `tutorial-transcripts/<lang>/*.json` for lang in TARGET_LANGS,
 * finds every string value matching `TODO: translate <kind> (en: <english>)`
 * (or fallback patterns), batches the strings by locale, calls Claude once
 * per locale to translate, and writes the result back in place. Anything
 * already authored (non-TODO string) is preserved verbatim — idempotent.
 *
 * Auth: uses your logged-in Claude Code Pro/Max subscription via the Claude
 * Agent SDK (no ANTHROPIC_API_KEY). Run `claude login` once; the SDK reads the
 * subscription credentials from ~/.claude automatically. A subscription OAuth
 * token cannot be used with the raw Messages API (blocked by Anthropic's ToS),
 * so translation goes through the Agent SDK's query() — the supported path.
 */

import { query } from '@anthropic-ai/claude-agent-sdk';
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const wwwRoot = path.resolve(scriptDir, '..');
const transcriptDir = path.join(wwwRoot, 'src', 'data', 'tutorial-transcripts');

const TARGET_LANGS = ['de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh', 'et', 'ko', 'pt', 'it'];

const LANG_NAMES: Record<string, string> = {
  de: 'German',
  es: 'Spanish',
  fr: 'French',
  ja: 'Japanese',
  ar: 'Arabic',
  ru: 'Russian',
  tr: 'Turkish',
  zh: 'Simplified Chinese',
  et: 'Estonian',
  ko: 'Korean',
  pt: 'Portuguese',
  it: 'Italian',
};

const MODEL = 'claude-sonnet-4-6';

// Match either "TODO: translate <kind> (en: <english>)" or the older
// pattern "TODO: translate <kind> for event N" / "TODO: translate event N".
const TODO_WITH_EN = /^TODO: translate ([^()]+?)\s*\(en:\s*(.+)\)\s*$/;
const TODO_BARE = /^TODO: translate (.+?)\s*$/;

interface TodoSlot {
  /** JSON path components from the root, used to set the translated value back. */
  pathSteps: Array<string | number>;
  /** Field kind for the prompt: cardLabel, chapter, title, narration, after-text, prose, event, etc. */
  kind: string;
  /** English value to translate (if discoverable) or empty if we only have the kind. */
  en: string;
}

function isTodoString(v: unknown): v is string {
  return typeof v === 'string' && v.startsWith('TODO:');
}

function parseTodo(s: string): { kind: string; en: string } | null {
  const m1 = TODO_WITH_EN.exec(s);
  if (m1) return { kind: m1[1].trim(), en: m1[2].trim() };
  const m2 = TODO_BARE.exec(s);
  if (m2) return { kind: m2[1].trim(), en: '' };
  return null;
}

function findTodos(node: unknown, slots: TodoSlot[], pathSteps: Array<string | number> = []): void {
  if (Array.isArray(node)) {
    node.forEach((item, i) => findTodos(item, slots, [...pathSteps, i]));
    return;
  }
  if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
      if (isTodoString(value)) {
        const parsed = parseTodo(value);
        if (parsed) {
          slots.push({ pathSteps: [...pathSteps, key], kind: parsed.kind, en: parsed.en });
        }
      } else {
        findTodos(value, slots, [...pathSteps, key]);
      }
    }
  }
}

function setByPath(
  root: Record<string, unknown> | unknown[],
  pathSteps: Array<string | number>,
  value: string
): void {
  let cursor: unknown = root;
  for (let i = 0; i < pathSteps.length - 1; i++) {
    const step = pathSteps[i];
    if (Array.isArray(cursor) && typeof step === 'number') {
      cursor = cursor[step];
    } else if (cursor && typeof cursor === 'object') {
      cursor = (cursor as Record<string, unknown>)[step as string];
    } else {
      return;
    }
  }
  const last = pathSteps[pathSteps.length - 1];
  if (Array.isArray(cursor) && typeof last === 'number') {
    cursor[last] = value;
  } else if (cursor && typeof cursor === 'object') {
    (cursor as Record<string, unknown>)[last as string] = value;
  }
}

const SYSTEM_PROMPT = `You are a translation engine for tutorial UI strings. The user gives you a JSON array of objects; each object has a "type" (the field's purpose) and an "en" (the English source). You output ONLY a JSON array of the same length where index i is the translated string for input i. No prose, no commentary, no markdown — just the array.

Translation rules:
- Keep technical terms verbatim: rdc, SSH, Cloudflare, Traefik, Docker, renet, Let's Encrypt, JWT, TLS, DNS, IP, JSON, YAML, BTRFS, env files, dotenv, sandbox, fork, repo, repository, container, daemon, terminal.
- Match the field's purpose register:
  - "cardLabel": a 2-3 word UI button label. Match the brevity. Capitalize like a button.
  - "chapter": a short phrase heading, max 6-7 words.
  - "title": a tutorial title, max 5 words.
  - "narration" or "narration <id>": conversational spoken prose. Keep the casual tone and natural rhythm so it works as audio.
  - "after-text for event N": a short post-action confirmation line. Keep it brief.
  - "prose": instructional docs voice. Imperative, second-person where natural.
  - "event N": narration text for that event. Keep conversational.
- Preserve all proper nouns and identifiers exactly.
- Do not add or remove information.
- Do not use em dashes or double hyphens. Use commas, periods, or parentheses instead.
- For Right-to-Left languages (Arabic), still produce a plain string; do not add directionality markers.
- For Simplified Chinese (zh) and Japanese (ja), use proper punctuation conventions.`;

async function translateLocale(lang: string, slots: TodoSlot[]): Promise<string[]> {
  if (slots.length === 0) return [];

  const input = slots.map((s) => ({ type: s.kind, en: s.en }));
  const langName = LANG_NAMES[lang] ?? lang;

  const userMessage = `Translate from English to ${langName}. Return ONLY a JSON array of ${slots.length} strings in the same order.

Input:
${JSON.stringify(input, null, 2)}`;

  // One single-turn, no-tools inference per batch, authenticated by the
  // logged-in Claude Code subscription. settingSources:[] keeps the repo's
  // CLAUDE.md / settings out of the prompt; allowedTools:[] disables all tools.
  let text = '';
  for await (const message of query({
    prompt: userMessage,
    options: {
      model: MODEL,
      systemPrompt: SYSTEM_PROMPT,
      maxTurns: 1,
      allowedTools: [],
      settingSources: [],
    },
  })) {
    if (message.type === 'result') {
      if (message.subtype !== 'success') {
        throw new Error(`Agent SDK returned "${message.subtype}"`);
      }
      text = message.result;
    }
  }

  // Extract the JSON array. Tolerate optional code-fence wrapping.
  const cleaned = text.trim().replace(/^```(?:json)?\s*|\s*```$/g, '');
  const parsed = JSON.parse(cleaned);
  if (!Array.isArray(parsed)) {
    throw new Error(`Expected JSON array, got ${typeof parsed}`);
  }
  if (parsed.length !== slots.length) {
    throw new Error(`Translation count mismatch: expected ${slots.length}, got ${parsed.length}`);
  }
  return parsed.map((v) => (typeof v === 'string' ? v : String(v)));
}

async function translateTutorial(
  lang: string,
  tutorial: string
): Promise<{ translated: number; skipped: number }> {
  const filePath = path.join(transcriptDir, lang, `${tutorial}.json`);
  if (!existsSync(filePath)) return { translated: 0, skipped: 0 };
  const doc = JSON.parse(readFileSync(filePath, 'utf-8')) as Record<string, unknown>;
  const slots: TodoSlot[] = [];
  findTodos(doc, slots);
  if (slots.length === 0) return { translated: 0, skipped: 0 };

  process.stdout.write(`  ${lang}/${tutorial}: ${slots.length} markers… `);
  let translations: string[];
  try {
    translations = await translateLocale(lang, slots);
  } catch (err) {
    console.error(`FAILED (${err instanceof Error ? err.message : String(err)})`);
    return { translated: 0, skipped: slots.length };
  }
  for (let i = 0; i < slots.length; i++) {
    setByPath(doc, slots[i].pathSteps, translations[i]);
  }
  writeFileSync(filePath, `${JSON.stringify(doc, null, 2)}\n`, 'utf-8');
  console.log('done');
  return { translated: slots.length, skipped: 0 };
}

async function main(): Promise<number> {
  const onlyLang = process.argv[2];
  const onlyTutorial = process.argv[3];

  const langs = onlyLang ? [onlyLang] : TARGET_LANGS;
  const enDir = path.join(transcriptDir, 'en');
  const tutorials = onlyTutorial
    ? [onlyTutorial]
    : readdirSync(enDir)
        .filter((f) => f.endsWith('.json'))
        .map((f) => f.replace(/\.json$/, ''));

  console.log(
    `Translating ${langs.length} locales × ${tutorials.length} tutorials = up to ${langs.length * tutorials.length} files`
  );

  let totalTranslated = 0;
  let totalSkipped = 0;
  for (const lang of langs) {
    console.log(`[${lang}]`);
    for (const tutorial of tutorials) {
      const { translated, skipped } = await translateTutorial(lang, tutorial);
      totalTranslated += translated;
      totalSkipped += skipped;
    }
  }
  console.log(`\nTranslated: ${totalTranslated} markers. Skipped (errors): ${totalSkipped}.`);
  return totalSkipped > 0 ? 1 : 0;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
