#!/usr/bin/env node
/**
 * Generates the onboarding splash content for the account portal from the
 * canonical tutorial transcripts in @packages/www/.
 *
 * Reads packages/www/src/data/account-onboarding.json and writes
 * private/account/web/src/data/onboarding-content.json.
 *
 * The generated file is imported by private/account/web/src/pages/TutorialSplash.tsx.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const ACCOUNT_WEB_DIR = path.resolve(ROOT, '..', '..', 'private', 'account', 'web');

const MANIFEST_PATH = path.join(ROOT, 'src', 'data', 'account-onboarding.json');
const STORYBOARD_DIR = path.join(ROOT, 'src', 'data', 'tutorial-storyboard');
const TRANSCRIPT_DIR = path.join(ROOT, 'src', 'data', 'tutorial-transcripts');
const OUTPUT_PATH = path.join(ACCOUNT_WEB_DIR, 'src', 'data', 'onboarding-content.json');

// Keep in sync with private/account/web/src/i18n/language.ts
const SUPPORTED_LANGUAGES = [
  'en',
  'de',
  'es',
  'fr',
  'ja',
  'ar',
  'ru',
  'tr',
  'zh',
  'et',
  'ko',
  'pt',
  'it',
] as const;

interface ManifestStep {
  id: string;
  source?: 'manual' | 'storyboard';
  tutorial?: string;
  markerIndex?: number;
  titleKey: string;
  docsPath: string;
  shortProse: string;
  prose?: Record<string, string>;
  command?: string;
  optional?: boolean;
}

interface Manifest {
  version: number;
  steps: ManifestStep[];
}

interface StoryboardScene {
  id: string;
  type: string;
  markerIndex?: number;
  card?: {
    commandFull?: string;
  };
}

interface Storyboard {
  draft?: boolean;
  scenes: StoryboardScene[];
}

interface TranscriptEvent {
  markerIndex?: number;
  prose?: string;
  text?: string;
}

interface TranscriptDoc {
  events?: TranscriptEvent[];
}

function readJson<T = unknown>(filePath: string): T {
  return JSON.parse(readFileSync(filePath, 'utf-8')) as T;
}

function readStoryboard(slug: string): Storyboard {
  return readJson<Storyboard>(path.join(STORYBOARD_DIR, `${slug}.json`));
}

function readTranscript(slug: string, lang: string): TranscriptDoc | null {
  const filePath = path.join(TRANSCRIPT_DIR, lang, `${slug}.json`);
  if (!existsSync(filePath)) return null;
  return readJson<TranscriptDoc>(filePath);
}

function authored(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0 && !value.startsWith('TODO:');
}

function resolveProse(
  step: ManifestStep,
  event: TranscriptEvent | undefined,
  enEvent: TranscriptEvent,
  isEnglish: boolean
): string {
  if (isEnglish && authored(step.shortProse)) {
    return step.shortProse;
  }
  if (event && authored(event.prose)) {
    return event.prose;
  }
  if (authored(enEvent.prose)) {
    return enEvent.prose;
  }
  if (event && authored(event.text)) {
    return event.text;
  }
  if (authored(enEvent.text)) {
    return enEvent.text;
  }
  return '';
}

function buildStoryboardStep(step: ManifestStep) {
  if (!step.tutorial || typeof step.markerIndex !== 'number') {
    throw new Error(`Step "${step.id}" is missing tutorial or markerIndex`);
  }

  const storyboard = readStoryboard(step.tutorial);
  const castNarrated = storyboard.scenes.filter(
    (scene): scene is StoryboardScene & { markerIndex: number } =>
      scene.type === 'cast-narrated' && typeof scene.markerIndex === 'number'
  );

  const scene = castNarrated.find((s) => s.markerIndex === step.markerIndex);
  if (!scene) {
    throw new Error(
      `Step "${step.id}" references markerIndex ${step.markerIndex} in "${step.tutorial}" but no matching cast-narrated scene exists`
    );
  }

  const command = scene.card?.commandFull?.trim();
  if (!command) {
    throw new Error(
      `Step "${step.id}" references "${step.tutorial}" markerIndex ${step.markerIndex} but the scene has no card.commandFull`
    );
  }

  const enTranscript = readTranscript(step.tutorial, 'en');
  if (!enTranscript || !Array.isArray(enTranscript.events)) {
    throw new Error(`English transcript missing for tutorial "${step.tutorial}"`);
  }

  const enEvent = enTranscript.events.find((e) => e.markerIndex === step.markerIndex);
  if (!enEvent) {
    throw new Error(
      `English transcript event missing for "${step.tutorial}" markerIndex ${step.markerIndex}`
    );
  }
  if (!authored(enEvent.prose) && !authored(enEvent.text)) {
    throw new Error(
      `English prose/text is missing or TODO for "${step.tutorial}" markerIndex ${step.markerIndex}`
    );
  }

  const prose: Record<string, string> = {};
  for (const lang of SUPPORTED_LANGUAGES) {
    const isEnglish = lang === 'en';
    const transcript = isEnglish ? enTranscript : readTranscript(step.tutorial, lang);
    const event = transcript?.events?.find((e) => e.markerIndex === step.markerIndex);
    prose[lang] = resolveProse(step, event, enEvent, isEnglish);
  }

  return {
    id: step.id,
    titleKey: step.titleKey,
    docsPath: step.docsPath,
    command,
    optional: step.optional ?? false,
    prose,
  };
}

function buildManualStep(step: ManifestStep) {
  const command = step.command?.trim();
  if (!command) {
    throw new Error(`Manual step "${step.id}" is missing command`);
  }
  if (!authored(step.shortProse)) {
    throw new Error(`Manual step "${step.id}" is missing or TODO shortProse`);
  }

  const prose: Record<string, string> = {};
  for (const lang of SUPPORTED_LANGUAGES) {
    prose[lang] = step.prose?.[lang] ?? step.shortProse;
  }

  return {
    id: step.id,
    titleKey: step.titleKey,
    docsPath: step.docsPath,
    command,
    optional: step.optional ?? false,
    prose,
  };
}

function buildStep(step: ManifestStep) {
  if (step.source === 'manual') {
    return buildManualStep(step);
  }
  return buildStoryboardStep(step);
}

function run(): void {
  const manifest = readJson<Manifest>(MANIFEST_PATH);

  const seenIds = new Set<string>();
  for (const step of manifest.steps) {
    if (seenIds.has(step.id)) {
      throw new Error(`Duplicate step id "${step.id}" in account-onboarding.json`);
    }
    seenIds.add(step.id);
  }

  const steps = manifest.steps.map((step) => buildStep(step));

  const output = {
    version: manifest.version,
    locales: SUPPORTED_LANGUAGES as unknown as string[],
    steps,
  };

  mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
  writeFileSync(OUTPUT_PATH, `${JSON.stringify(output, null, 2)}\n`, 'utf-8');
  console.log(`Generated ${path.relative(ROOT, OUTPUT_PATH)} with ${steps.length} steps`);
}

run();
