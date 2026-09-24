#!/usr/bin/env tsx
/**
 * Skill Reference Generator
 *
 * Introspects the live Commander.js command tree and prints a markdown
 * reference of all CLI commands grouped by domain, including MCP exposure
 * status and agent guard annotations.
 *
 * Consumed by rdc.sh to regenerate .claude/skills/rdc/reference.md.
 * Markdown goes to stdout; redirect it to the target file.
 *
 * Usage:
 *   npx tsx packages/cli/scripts/generate-skill-reference.ts > reference.md
 */
import type { Command } from 'commander';
import { cli } from '../src/cli.js';
import { type CommandMeta, getCommandMeta } from '../src/config/command-metadata.js';
import { COMMAND_DOMAINS, getCommandDef } from '../src/config/command-registry.js';

/** Fallback domain label for commands without a registry entry */
const UNCATEGORIZED_DOMAIN = 'Other';

interface CommandCapability {
  name: string;
  description: string;
  summary?: string;
  arguments: { name: string; required: boolean }[];
  options: { flags: string; description: string; default?: unknown }[];
  domain?: string;
}

/** Extract a leaf command's capability from a Commander subcommand. */
function extractLeafCapability(sub: Command, name: string, prefix: string): CommandCapability {
  const args = (sub as unknown as { _args: { _name: string; required: boolean }[] })._args.map(
    (a) => ({
      name: a._name,
      required: a.required,
    })
  );

  const options = sub.options
    .filter((o) => o.long !== '--version' && o.long !== '--help')
    .map((o) => ({
      flags: o.flags,
      description: o.description,
      ...(o.defaultValue !== undefined && { default: o.defaultValue }),
    }));

  const topLevel = (prefix || sub.name()).split(' ')[0];
  const def = getCommandDef(topLevel);

  return {
    name,
    description: sub.description(),
    ...(sub.summary() && { summary: sub.summary() }),
    arguments: args,
    options,
    ...(def && {
      domain: COMMAND_DOMAINS[def.domain],
    }),
  };
}

function walkCommands(cmd: Command, prefix = ''): CommandCapability[] {
  const results: CommandCapability[] = [];

  for (const sub of cmd.commands) {
    if (sub.name() === 'help') continue;
    if ((sub as Command & { _hidden?: boolean })._hidden) continue;

    const name = prefix ? `${prefix} ${sub.name()}` : sub.name();

    if (sub.commands.length > 0) {
      results.push(...walkCommands(sub, name));
    } else {
      results.push(extractLeafCapability(sub, name, prefix));
    }
  }

  return results;
}

/** Group commands by domain. */
function groupByDomain(commands: CommandCapability[]): Map<string, CommandCapability[]> {
  const grouped = new Map<string, CommandCapability[]>();
  for (const cmd of commands) {
    const domain = cmd.domain ?? UNCATEGORIZED_DOMAIN;
    const bucket = grouped.get(domain);
    if (bucket) {
      bucket.push(cmd);
    } else {
      grouped.set(domain, [cmd]);
    }
  }
  return grouped;
}

/** Render option lines for a command's markdown block. */
function renderOptions(lines: string[], options: CommandCapability['options']): void {
  if (options.length === 0) return;
  // Markdown heading for the options section
  const MD_OPTIONS_HEADING = '**Options:**';
  lines.push(MD_OPTIONS_HEADING, '');
  for (const opt of options) {
    const def = opt.default === undefined ? '' : ` (default: ${opt.default})`;
    lines.push(`- \`${opt.flags}\`: ${opt.description}${def}`);
  }
  lines.push('');
}

/** Collect annotation badges for a command based on its metadata. */
function collectAnnotations(meta: CommandMeta): string[] {
  const annotations: string[] = [];
  // Markdown annotation labels (not user-facing CLI text)
  const AGENT_BLOCKED_LABEL = 'agent: BLOCKED';
  if (meta.agentBlocked) annotations.push(AGENT_BLOCKED_LABEL);
  if (meta.mcp) annotations.push('MCP tool');
  const FORK_ONLY_LABEL = 'agent: fork-only';
  if (meta.grandGuard) annotations.push(FORK_ONLY_LABEL);
  if (meta.forkBlocked) annotations.push('fork-blocked');
  if (meta.mcpExcludeReason) annotations.push(`MCP excluded: ${meta.mcpExcludeReason}`);
  return annotations;
}

/** The prose-style line floor, `globals.max_line_length` in .ci/config/prose-style-rules.json. */
const PROSE_LINE_FLOOR = 768;

/**
 * Split a description past the prose-style floor at sentence breaks, so the generated file passes R18 without a hand edit that `rdc.sh` would overwrite on its next regeneration.
 * A description that already ends on a full stop is left whole, since R18 never flags that shape, and so is one with no sentence break to use. The rendered markdown is unchanged: consecutive lines are one paragraph.
 */
function wrapAtSentences(text: string): string[] {
  if (text.length <= PROSE_LINE_FLOOR || text.endsWith('.')) return [text];
  const sentences = text.split(/(?<=[.!?])\s+(?=[A-Z(])/);
  const out: string[] = [];
  let current = '';
  for (const sentence of sentences) {
    if (current && current.length + 1 + sentence.length > PROSE_LINE_FLOOR) {
      out.push(current);
      current = sentence;
    } else {
      current = current ? `${current} ${sentence}` : sentence;
    }
  }
  if (current) out.push(current);
  return out;
}

/** Render a single command's markdown block into lines. */
function renderCommandBlock(lines: string[], cmd: CommandCapability): void {
  const argSyntax = cmd.arguments
    .map((a) => (a.required ? `<${a.name}>` : `[${a.name}]`))
    .join(' ');
  lines.push(`### rdc ${cmd.name}${argSyntax ? ` ${argSyntax}` : ''}`, '');

  if (cmd.description) {
    lines.push(...wrapAtSentences(cmd.description), '');
  }

  renderOptions(lines, cmd.options);

  const meta = getCommandMeta(cmd.name);
  const annotations = meta ? collectAnnotations(meta) : [];
  if (annotations.length > 0) {
    lines.push(`> ${annotations.join(' | ')}`, '');
  }
}

/**
 * Generate a markdown reference of all CLI commands grouped by domain.
 * Includes MCP exposure status and agent guard annotations.
 */
function generateReferenceMarkdown(commands: CommandCapability[]): string {
  const lines: string[] = [
    '<!-- AUTO-GENERATED by packages/cli/scripts/generate-skill-reference.ts - do not edit -->',
    '# rdc CLI Reference',
    '',
  ];

  const grouped = groupByDomain(commands);

  for (const [domain, cmds] of grouped) {
    lines.push(`## ${domain}`, '');
    for (const cmd of cmds) {
      renderCommandBlock(lines, cmd);
    }
  }

  return lines.join('\n');
}

process.stdout.write(generateReferenceMarkdown(walkCommands(cli)));
