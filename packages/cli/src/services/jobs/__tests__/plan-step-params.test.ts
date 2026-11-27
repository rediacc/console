/**
 * planStep keeps only the params a step declares and drops the rest without a word. `backup status`
 * passed `targets` to renderBackupStatus, which declared only `machine` and `expected`, so every
 * store column (newest snapshot, verify, copy lag) printed `-` although the account held the values
 * (hostinger 2026-11-27). This scan holds every literal planStep call in the CLI to its declaration.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { getStepDefinition } from '../steps.js';

const SRC = fileURLToPath(new URL('../../../', import.meta.url));

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === '__tests__' ? [] : sourceFiles(path);
    return name.endsWith('.ts') ? [path] : [];
  });
}

/** The text between an opening brace at `start` and its match. */
function balanced(text: string, start: number): string {
  let depth = 1;
  let i = start;
  while (depth > 0 && i < text.length) {
    const c = text[i];
    if ('{(['.includes(c)) depth++;
    else if ('})]'.includes(c)) depth--;
    i++;
  }
  return text.slice(start, i - 1);
}

/** The top-level keys of an object literal's body; a spread is skipped, since its keys are not literal. */
function topLevelKeys(body: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let token = '';
  for (const c of body) {
    if ('{(['.includes(c)) depth++;
    if ('})]'.includes(c)) depth--;
    if (depth === 0 && c === ',') {
      parts.push(token);
      token = '';
    } else token += c;
  }
  parts.push(token);
  return parts
    .map((p) => p.replace(/\/\/.*$/gm, '').trim())
    .filter((p) => p && !p.startsWith('...'))
    .map((p) => /^([A-Za-z_$][\w$]*)/.exec(p)?.[1] ?? p);
}

/** Every `planStep('<name>', { ... })` in `text`, with the keys it passes. */
function literalPlanSteps(text: string): { step: string; keys: string[] }[] {
  const found: { step: string; keys: string[] }[] = [];
  const call = /planStep\(\s*'([A-Za-z]+)'\s*,\s*\{/g;
  for (let m = call.exec(text); m; m = call.exec(text)) {
    found.push({ step: m[1], keys: topLevelKeys(balanced(text, call.lastIndex)) });
  }
  return found;
}

function undeclared(text: string): string[] {
  return literalPlanSteps(text).flatMap(({ step, keys }) => {
    const def = getStepDefinition(step);
    if (!def) return [`${step}: not a registered step`];
    return keys.filter((k) => !def.params.includes(k)).map((k) => `${step}.${k}`);
  });
}

describe('planStep params are declared by their step', () => {
  it('control: a call passing an undeclared key is caught', () => {
    expect(undeclared("planStep('renderBackupStatus', { machine: m, nope: 1 })")).toEqual([
      'renderBackupStatus.nope',
    ]);
  });

  it('every literal planStep call in the CLI passes only declared keys', () => {
    const files = sourceFiles(SRC);
    const calls = files.flatMap((f) => literalPlanSteps(readFileSync(f, 'utf8')));
    // An empty scan would pass for the wrong reason.
    expect(calls.length).toBeGreaterThan(50);
    const offenders = files.flatMap((f) =>
      undeclared(readFileSync(f, 'utf8')).map((o) => `${f.slice(SRC.length)}: ${o}`)
    );
    expect(offenders).toEqual([]);
  });
});
