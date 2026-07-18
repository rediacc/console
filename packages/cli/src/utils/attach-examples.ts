/**
 * Attaches the curated worked examples (COMMAND_EXAMPLES in config/command-docs)
 * to the built Commander tree as a localized "Examples:" help block. Called once
 * from cli.ts after the tree is fully constructed.
 *
 * The block is rendered eagerly with the active locale (the same pattern the
 * hand-written addHelpText calls use), so `rdc <cmd> --help` shows the examples
 * in the operator's language. Keys resolve through the standard i18n resolver,
 * which the runtime help-render gate (scripts/check-cli-i18n-help-render.ts)
 * exercises so a missing/raw key fails loudly.
 */
import type { Command } from 'commander';
import { COMMAND_EXAMPLES } from '../config/command-docs.js';
import { t } from '../i18n/index.js';

/** The space-joined path from the root's children down to `command`. */
function pathKeyOf(command: Command): string {
  const segments: string[] = [];
  let node: Command = command;
  while (node.parent) {
    segments.unshift(node.name());
    node = node.parent;
  }
  return segments.join(' ');
}

/** Render the "Examples:" block for a command, one example per two lines. */
function renderExamplesBlock(pathKey: string): string {
  const examples = COMMAND_EXAMPLES[pathKey];
  const lines = [`\n${t('help.examples')}`];
  for (const example of examples) {
    lines.push(`  $ ${example.command}`);
    lines.push(`      ${t(example.descriptionKey)}`);
  }
  return `${lines.join('\n')}\n`;
}

/**
 * Walk the whole command tree; every command that has curated examples gets a
 * localized "Examples:" section appended to its help output.
 */
export function attachExamples(root: Command): void {
  const visit = (command: Command): void => {
    for (const sub of command.commands) {
      const pathKey = pathKeyOf(sub);
      if (pathKey in COMMAND_EXAMPLES) {
        sub.addHelpText('after', renderExamplesBlock(pathKey));
      }
      visit(sub);
    }
  };
  visit(root);
}
