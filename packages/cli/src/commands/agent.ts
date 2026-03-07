import { Command } from 'commander';
import { COMMAND_DOMAINS, getCommandDef } from '../config/command-registry.js';
import { t } from '../i18n/index.js';
import { outputService } from '../services/output.js';
import { VERSION } from '../version.js';

interface CommandCapability {
  name: string;
  description: string;
  arguments: { name: string; required: boolean }[];
  options: { flags: string; description: string; default?: unknown }[];
  domain?: string;
  modes?: readonly string[];
}

function walkCommands(cmd: Command, prefix = ''): CommandCapability[] {
  const results: CommandCapability[] = [];

  for (const sub of cmd.commands) {
    const name = prefix ? `${prefix} ${sub.name()}` : sub.name();

    if (sub.name() === 'help') continue;

    // If this command has subcommands, recurse
    if (sub.commands.length > 0) {
      results.push(...walkCommands(sub, name));
    } else {
      // Leaf command — extract args, options, and registry metadata
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

      // Look up registry metadata (extract first word for deeply nested commands)
      const topLevel = (prefix || sub.name()).split(' ')[0];
      const def = getCommandDef(topLevel);

      results.push({
        name,
        description: sub.description(),
        arguments: args,
        options,
        ...(def && {
          domain: COMMAND_DOMAINS[def.domain],
          modes: [...def.modes],
        }),
      });
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
  const agent = program.command('agent').description(t('commands.agent.description'));

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
