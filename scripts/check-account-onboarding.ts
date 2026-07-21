#!/usr/bin/env node
/**
 * Validates that the account portal onboarding splash content stays in sync with
 * the canonical tutorial data in @packages/www/.
 *
 * Checks:
 *   - account-onboarding.json is well-formed
 *   - every referenced tutorial has a storyboard and English transcript
 *   - every referenced markerIndex exists in the storyboard's cast-narrated scenes
 *   - the referenced English transcript event has authored prose/text (not TODO)
 *   - referenced tutorials are not drafts
 *   - the generated onboarding-content.json is up to date (freshness gate)
 */

import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { parseRdcCommand } from '../packages/www/scripts/lib/cli-reference-catalog.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const MANIFEST_PATH = path.join(ROOT, 'packages', 'www', 'src', 'data', 'account-onboarding.json');
const STORYBOARD_DIR = path.join(ROOT, 'packages', 'www', 'src', 'data', 'tutorial-storyboard');
const TRANSCRIPT_DIR = path.join(ROOT, 'packages', 'www', 'src', 'data', 'tutorial-transcripts');
const GENERATED_PATH = path.join(
  ROOT,
  'private',
  'account',
  'web',
  'src',
  'data',
  'onboarding-content.json'
);
const GENERATOR_PATH = path.join(ROOT, 'packages', 'www', 'scripts', 'build-account-onboarding.ts');

interface ManifestStep {
  id: string;
  source?: 'manual' | 'storyboard';
  tutorial?: string;
  markerIndex?: number;
  titleKey: string;
  docsPath: string;
  shortProse: string;
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

/**
 * The command a step MUST carry, derived from the same source the generator reads: the
 * storyboard scene's `card.commandFull`. A step with no tutorial (a plain shell step) takes
 * its command straight from the manifest.
 *
 * This is the oracle. The generated file is not — it is the artifact, and asking the artifact
 * whether it is correct is how this file drifted in the first place.
 */
function expectedCommandFor(step: ManifestStep, issues: Issue[]): string | undefined {
  if (step.tutorial === undefined || step.markerIndex === undefined) return step.command;
  const storyboardPath = path.join(STORYBOARD_DIR, `${step.tutorial}.json`);
  if (!existsSync(storyboardPath)) return undefined;
  const storyboard = readStoryboard(step.tutorial);
  const scene = storyboard.scenes.find(
    (sc) => sc.type === 'cast-narrated' && sc.markerIndex === step.markerIndex
  );
  const cmd = scene?.card?.commandFull?.trim();
  if (!cmd) {
    issues.push({
      step: step.id,
      message: `storyboard scene has no card.commandFull to check the generated command against`,
    });
    return undefined;
  }

  // Presence was never enough. This command is generated verbatim into the
  // portal's first-run flow, so a brand-new user copies and runs it. Asserting
  // only that the field EXISTS let a command the CLI rejects reach that flow.
  // Validated against the live command tree, the same instrument every other
  // CLI gate uses.
  const parsed = parseRdcCommand(cmd);
  if (!parsed.ok && parsed.reason !== 'not-rdc') {
    issues.push({
      step: step.id,
      message:
        `storyboard card.commandFull does not resolve against the live CLI ` +
        `(${parsed.reason}${parsed.flag ? `: ${parsed.flag}` : ''}): ${cmd}`,
    });
  }

  return cmd;
}

function readTranscript(slug: string, lang: string): TranscriptDoc | null {
  const filePath = path.join(TRANSCRIPT_DIR, lang, `${slug}.json`);
  if (!existsSync(filePath)) return null;
  return readJson<TranscriptDoc>(filePath);
}

function authored(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0 && !value.startsWith('TODO:');
}

interface Issue {
  step: string;
  message: string;
}

function validateCommonFields(step: ManifestStep, issues: Issue[]): void {
  if (!step.titleKey || step.titleKey.trim().length === 0) {
    issues.push({ step: step.id, message: 'missing titleKey' });
  }
  if (!step.docsPath || step.docsPath.trim().length === 0) {
    issues.push({ step: step.id, message: 'missing docsPath' });
  }
  if (!authored(step.shortProse)) {
    issues.push({ step: step.id, message: 'missing or TODO shortProse' });
  }
}

function validateManualStep(step: ManifestStep, issues: Issue[]): void {
  validateCommonFields(step, issues);
  if (!step.command || step.command.trim().length === 0) {
    issues.push({ step: step.id, message: 'manual step is missing command' });
  }
}

function validateStoryboardStep(step: ManifestStep, issues: Issue[]): void {
  validateCommonFields(step, issues);

  if (!step.tutorial || step.tutorial.trim().length === 0) {
    issues.push({ step: step.id, message: 'missing tutorial slug' });
    return;
  }
  if (typeof step.markerIndex !== 'number' || step.markerIndex < 0) {
    issues.push({ step: step.id, message: `invalid markerIndex ${String(step.markerIndex)}` });
    return;
  }

  const storyboardPath = path.join(STORYBOARD_DIR, `${step.tutorial}.json`);
  if (!existsSync(storyboardPath)) {
    issues.push({ step: step.id, message: `storyboard missing for "${step.tutorial}"` });
    return;
  }

  const storyboard = readStoryboard(step.tutorial);
  if (storyboard.draft === true) {
    issues.push({ step: step.id, message: `tutorial "${step.tutorial}" is a draft` });
  }

  const castNarrated = storyboard.scenes.filter(
    (scene): scene is StoryboardScene & { markerIndex: number } =>
      scene.type === 'cast-narrated' && typeof scene.markerIndex === 'number'
  );
  const scene = castNarrated.find((s) => s.markerIndex === step.markerIndex);
  if (!scene) {
    issues.push({
      step: step.id,
      message: `markerIndex ${step.markerIndex} not found in cast-narrated scenes of "${step.tutorial}"`,
    });
    return;
  }

  const command = scene.card?.commandFull?.trim();
  if (!command) {
    issues.push({
      step: step.id,
      message: `scene for markerIndex ${step.markerIndex} in "${step.tutorial}" is missing card.commandFull`,
    });
  }

  const transcript = readTranscript(step.tutorial, 'en');
  if (!transcript) {
    issues.push({ step: step.id, message: `English transcript missing for "${step.tutorial}"` });
    return;
  }
  if (!Array.isArray(transcript.events)) {
    issues.push({ step: step.id, message: `English transcript has no events for "${step.tutorial}"` });
    return;
  }
  const event = transcript.events.find((e) => e.markerIndex === step.markerIndex);
  if (!event) {
    issues.push({
      step: step.id,
      message: `English transcript event missing for "${step.tutorial}" markerIndex ${step.markerIndex}`,
    });
    return;
  }
  if (!authored(event.prose) && !authored(event.text)) {
    issues.push({
      step: step.id,
      message: `English prose/text is missing or TODO for "${step.tutorial}" markerIndex ${step.markerIndex}`,
    });
  }
}

function validateManifest(manifest: Manifest, issues: Issue[]): void {
  const seenIds = new Set<string>();

  for (const step of manifest.steps) {
    if (seenIds.has(step.id)) {
      issues.push({ step: step.id, message: `duplicate step id "${step.id}"` });
    }
    seenIds.add(step.id);

    if (step.source === 'manual') {
      validateManualStep(step, issues);
    } else {
      validateStoryboardStep(step, issues);
    }
  }
}

interface GeneratedStep {
  id: string;
  titleKey: string;
  docsPath: string;
  command: string;
  optional: boolean;
  prose: Record<string, string>;
}

interface GeneratedContent {
  version: number;
  steps: GeneratedStep[];
}

function checkFreshness(manifest: Manifest, issues: Issue[]): void {
  if (!existsSync(GENERATED_PATH)) {
    issues.push({ step: '(file)', message: `generated file missing: ${GENERATED_PATH}` });
    return;
  }
  if (!existsSync(GENERATOR_PATH)) {
    issues.push({ step: '(file)', message: `generator script missing: ${GENERATOR_PATH}` });
    return;
  }

  const generated = readJson<GeneratedContent>(GENERATED_PATH);
  if (generated.steps.length !== manifest.steps.length) {
    issues.push({
      step: '(file)',
      message: `onboarding-content.json step count (${generated.steps.length}) does not match manifest (${manifest.steps.length}); run "npm run build:account-onboarding"`,
    });
    return;
  }

  for (let i = 0; i < manifest.steps.length; i++) {
    const mStep = manifest.steps[i];
    const gStep = generated.steps[i];
    if (!gStep) {
      issues.push({ step: mStep.id, message: 'missing generated step' });
      continue;
    }
    if (gStep.id !== mStep.id) {
      issues.push({
        step: mStep.id,
        message: `generated step id mismatch: expected "${mStep.id}", got "${gStep.id}"`,
      });
    }
    if (gStep.titleKey !== mStep.titleKey) {
      issues.push({
        step: mStep.id,
        message: `generated titleKey mismatch; run "npm run build:account-onboarding"`,
      });
    }
    if (gStep.docsPath !== mStep.docsPath) {
      issues.push({
        step: mStep.id,
        message: `generated docsPath mismatch; run "npm run build:account-onboarding"`,
      });
    }
    if (gStep.prose.en !== mStep.shortProse) {
      issues.push({
        step: mStep.id,
        message: `generated English prose does not match manifest shortProse; run "npm run build:account-onboarding"`,
      });
    }
    if (!gStep.command || gStep.command.trim().length === 0) {
      issues.push({
        step: mStep.id,
        message: `generated step is missing command; run "npm run build:account-onboarding"`,
      });
    } else {
      // ★ Compare the command TEXT, not just its non-emptiness.
      //
      // This gate used to check that `command` was a non-empty string and nothing more — so
      // the CORRECT file and a file teaching a DELETED command both passed. That is how a
      // regeneration silently reverted a real fix in the FIRST-RUN FLOW, the very first
      // command a new user ever types, and no gate said a word. It validated the SHAPE and
      // not the THING.
      //
      // The command is derived from the storyboard scene's `card.commandFull`, so a mismatch
      // means the generated file was hand-edited (it is generated — do not) or the storyboard
      // moved underneath it. Either way it is stale, and staleness in this file is a lie told
      // to someone on their first minute with the product.
      const expected = expectedCommandFor(mStep, issues);
      if (expected !== undefined && gStep.command.trim() !== expected.trim()) {
        issues.push({
          step: mStep.id,
          message:
            `generated command does not match its source.\n` +
            `      generated: ${gStep.command}\n` +
            `      source:    ${expected}\n` +
            `      run "npm run build:account-onboarding" (never hand-edit onboarding-content.json)`,
        });
      }
    }
    if ((gStep.optional ?? false) !== (mStep.optional ?? false)) {
      issues.push({
        step: mStep.id,
        message: `generated optional flag mismatch; run "npm run build:account-onboarding"`,
      });
    }
  }
}

function main(): number {
  const issues: Issue[] = [];

  if (!existsSync(MANIFEST_PATH)) {
    console.error(`Manifest not found: ${MANIFEST_PATH}`);
    return 1;
  }

  let manifest: Manifest;
  try {
    manifest = readJson<Manifest>(MANIFEST_PATH);
  } catch (err) {
    console.error(`Failed to parse manifest: ${err instanceof Error ? err.message : String(err)}`);
    return 1;
  }

  validateManifest(manifest, issues);
  checkFreshness(manifest, issues);

  if (issues.length === 0) {
    console.log(`✓ Account onboarding tutorial validation passed (${manifest.steps.length} steps)`);
    return 0;
  }

  console.error(`✗ Account onboarding tutorial validation failed (${issues.length} issue(s))\n`);
  for (const issue of issues) {
    console.error(`  [${issue.step}] ${issue.message}`);
  }
  return 1;
}

process.exit(main());
