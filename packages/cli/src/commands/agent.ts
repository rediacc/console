import { Command } from 'commander';
import { getCommandMeta, type CommandMeta } from '../config/command-metadata.js';
import { COMMAND_DOMAINS, getCommandDef } from '../config/command-registry.js';
import { t } from '../i18n/index.js';
import { outputService } from '../services/output.js';
import { VERSION } from '../version.js';

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

function findCommand(root: Command, commandPath: string): Command | undefined {
  const parts = commandPath.split(/\s+/);
  let current = root;

  for (const part of parts) {
    const found = current.commands.find((c) => c.name() === part);
    if (!found) return undefined;
    current = found;
  }

  return current;
}

export function registerAgentCommands(program: Command): void {
  const agent = program
    .command('agent')
    .summary(t('commands.agent.descriptionShort'))
    .description(t('commands.agent.description'));

  // rdc agent capabilities
  agent
    .command('capabilities')
    .description(t('commands.agent.capabilities.description'))
    .action(() => {
      const commands = walkCommands(program);
      const result = { version: VERSION, commands };
      outputService.print(result, 'json');
    });

  // rdc agent schema --command <path>
  agent
    .command('schema')
    .description(t('commands.agent.schema.description'))
    .requiredOption('--command <path>', t('options.command'))
    .action((opts: { command: string }) => {
      const commandPath = opts.command;
      const cmd = findCommand(program, commandPath);
      if (!cmd) {
        outputService.error(`Command "${commandPath}" not found`);
        process.exit(1);
      }

      const args = (cmd as unknown as { _args: { _name: string; required: boolean }[] })._args.map(
        (a) => ({
          name: a._name,
          required: a.required,
        })
      );

      const options = cmd.options.map((o) => ({
        flags: o.flags,
        description: o.description,
        required: o.required,
        ...(o.defaultValue !== undefined && { default: o.defaultValue }),
      }));

      const topLevel = commandPath.split(/\s+/)[0];
      const def = getCommandDef(topLevel);

      const schema = {
        command: commandPath,
        description: cmd.description(),
        arguments: args,
        options,
        ...(def && {
          domain: COMMAND_DOMAINS[def.domain],
        }),
        usage: `rdc ${commandPath}${args.map((a) => (a.required ? ` <${a.name}>` : ` [${a.name}]`)).join('')}`,
      };

      outputService.print(schema, 'json');
    });

  // rdc agent exec --command <path>
  agent
    .command('exec')
    .description(t('commands.agent.exec.description'))
    .requiredOption('--command <path>', t('options.command'))
    .action(async (options: { command: string }) => {
      const commandPath = options.command;
      const cmd = findCommand(program, commandPath);
      if (!cmd) {
        outputService.error(`Command "${commandPath}" not found`);
        process.exit(1);
      }

      // Read JSON from stdin
      const chunks: Buffer[] = [];
      for await (const chunk of process.stdin) {
        chunks.push(chunk);
      }
      const input = JSON.parse(Buffer.concat(chunks).toString('utf-8'));

      const argv = buildExecArgv(commandPath, input);

      await program.parseAsync(argv);
    });

  // rdc agent generate-reference
  agent
    .command('generate-reference')
    .description(t('commands.agent.generateReference.description'))
    .action(() => {
      const commands = walkCommands(program);
      const md = generateReferenceMarkdown(commands);
      process.stdout.write(md);
    });
}

function serializeOption(key: string, value: unknown): string[] {
  const flag = `--${key.replaceAll(/([A-Z])/g, '-$1').toLowerCase()}`;
  if (typeof value === 'boolean') {
    return value ? [flag] : [];
  }
  return [flag, String(value)];
}

function buildExecArgv(commandPath: string, input: Record<string, unknown>): string[] {
  const argv: string[] = ['node', 'rdc', ...commandPath.split(/\s+/)];

  // All input keys are named options (no positional arguments)
  for (const [key, value] of Object.entries(input)) {
    argv.push(...serializeOption(key, value));
  }

  // Force JSON output
  argv.push('--output', 'json');
  return argv;
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
    lines.push(`- \`${opt.flags}\` — ${opt.description}${def}`);
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

/** Render a single command's markdown block into lines. */
function renderCommandBlock(lines: string[], cmd: CommandCapability): void {
  const argSyntax = cmd.arguments
    .map((a) => (a.required ? `<${a.name}>` : `[${a.name}]`))
    .join(' ');
  lines.push(`### rdc ${cmd.name}${argSyntax ? ` ${argSyntax}` : ''}`, '');

  if (cmd.description) {
    lines.push(cmd.description, '');
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
    '<!-- AUTO-GENERATED by: rdc agent generate-reference — do not edit -->',
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
