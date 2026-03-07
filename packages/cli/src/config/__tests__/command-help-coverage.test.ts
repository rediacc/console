/**
 * Command Help Text Coverage Test
 *
 * Ensures every command and subcommand in the registry has a non-empty
 * i18n description in the English locale. Fails CI when a command is added
 * to the registry but its --help description is missing.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { COMMAND_REGISTRY } from '../command-registry.js';

// Load English locale JSON directly (avoids bootstrapping the i18n system)
const localePath = resolve(
  import.meta.dirname,
  '../../i18n/locales/en/cli.json'
);
const locale: Record<string, unknown> = JSON.parse(readFileSync(localePath, 'utf-8'));
const commands = locale.commands as Record<string, Record<string, unknown>>;

/**
 * Registry name → i18n key mapping for commands that don't follow the
 * default `commands.<name>.description` convention.
 */
const I18N_KEY_OVERRIDES: Record<string, string> = {
  run: 'shortcuts.run',
};

/** Resolve a nested key like "repo.up.description" from the commands object. */
function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
  let current: unknown = obj;
  for (const key of path.split('.')) {
    if (current == null || typeof current !== 'object') return undefined;
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}

function i18nKeyFor(cmdName: string): string {
  return I18N_KEY_OVERRIDES[cmdName] ?? cmdName;
}

describe('command help text coverage', () => {
  it('every registry command has a non-empty i18n description', () => {
    const missing: string[] = [];

    for (const cmd of COMMAND_REGISTRY) {
      const key = i18nKeyFor(cmd.name);
      const desc = getNestedValue(commands, `${key}.description`);
      if (typeof desc !== 'string' || desc.trim().length === 0) {
        missing.push(`commands.${key}.description (registry: "${cmd.name}")`);
      }
    }

    if (missing.length > 0) {
      expect.fail(
        `${missing.length} command(s) missing i18n description in en/cli.json:\n` +
          missing.map((k) => `  - ${k}`).join('\n')
      );
    }
  });

  it('every registry subcommand has a non-empty i18n description', () => {
    const missing: string[] = [];

    for (const cmd of COMMAND_REGISTRY) {
      if (!cmd.subcommands) continue;
      const parentKey = i18nKeyFor(cmd.name);

      for (const [subName, subDef] of Object.entries(cmd.subcommands)) {
        // Skip experimental subcommands — they may intentionally lack public help text
        if (subDef.experimental) continue;

        const key = `${parentKey}.${subName}.description`;
        const desc = getNestedValue(commands, key);
        if (typeof desc !== 'string' || desc.trim().length === 0) {
          missing.push(`commands.${key} (registry: "${cmd.name} ${subName}")`);
        }
      }
    }

    if (missing.length > 0) {
      expect.fail(
        `${missing.length} subcommand(s) missing i18n description in en/cli.json:\n` +
          missing.map((k) => `  - ${k}`).join('\n')
      );
    }
  });
});
