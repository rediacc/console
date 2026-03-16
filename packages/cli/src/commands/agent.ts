import { Command } from 'commander';
import { COMMAND_METADATA, type CommandMeta } from '../config/command-metadata.js';
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
  modes?: readonly string[];
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
      modes: [...def.modes],
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

  // rdc agent schema <command>
  agent
    .command('schema <command>')
    .description(t('commands.agent.schema.description'))
    .action((commandPath: string) => {
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
          modes: [...def.modes],
        }),
        usage: `rdc ${commandPath}${args.map((a) => (a.required ? ` <${a.name}>` : ` [${a.name}]`)).join('')}`,
      };

      outputService.print(schema, 'json');
    });

  // rdc agent exec <command>
  agent
    .command('exec <command>')
    .description(t('commands.agent.exec.description'))
    .action(async (commandPath: string) => {
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

      const cmdArgs = (cmd as unknown as { _args: { _name: string }[] })._args;
      const argv = buildExecArgv(commandPath, cmdArgs, input);

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

function buildExecArgv(
  commandPath: string,
  cmdArgs: { _name: string }[],
  input: Record<string, unknown>
): string[] {
  const argv: string[] = ['node', 'rdc', ...commandPath.split(/\s+/)];

  // Add positional arguments
  for (const argDef of cmdArgs) {
    if (input[argDef._name] !== undefined) {
      argv.push(String(input[argDef._name]));
    }
  }

  // Add options
  const positionalNames = new Set(cmdArgs.map((a) => a._name));
  for (const [key, value] of Object.entries(input)) {
    if (!positionalNames.has(key)) {
      argv.push(...serializeOption(key, value));
    }
  }

  // Force JSON output
  argv.push('--output', 'json');
  return argv;
}

/** Check whether a command targets the cloud adapter only. */
function isCloudOnlyCommand(cmd: CommandCapability): boolean {
  return cmd.modes?.length === 1 && cmd.modes[0] === 'cloud';
}

/** Group commands by domain, excluding cloud-only entries. */
function groupByDomain(commands: CommandCapability[]): Map<string, CommandCapability[]> {
  const grouped = new Map<string, CommandCapability[]>();
  for (const cmd of commands) {
    if (isCloudOnlyCommand(cmd)) continue;
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
  if (meta.mcp) annotations.push('MCP tool');
  // Markdown annotation labels (not user-facing CLI text)
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

  const meta = COMMAND_METADATA[cmd.name];
  const annotations = collectAnnotations(meta);
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
