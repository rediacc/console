/**
 * Every argv an MCP tool BUILDS must be an argv the CLI ACCEPTS.
 *
 * ★ This is the gate whose absence let `term_exec` rot in place. That tool built
 * `term connect -m <machine> [-r <repo>] -c <cmd>`. P4 deleted `-m` and `-r`, so
 * from that moment the tool emitted an argv the CLI would REJECT — and the whole
 * MCP suite stayed green, because every test asserted the argv a tool BUILDS and
 * not one asserted the CLI would take it. The tool was broken and the tests could
 * not see it, because they were checking the tool against itself.
 *
 * The same hole is open for all 60-odd auto-derived tools: they are generated from
 * the Commander tree, so they LOOK self-consistent, but `excludeOptions`,
 * `appendArgs`, `requiredArgs` and the custom tools are all hand-written and can
 * name a flag that no longer exists.
 *
 * So: build each tool's argv with every field of its schema populated, then resolve
 * that argv against the REAL Commander tree — the command path must exist, every
 * flag must be registered on it (or be a global), and the positionals must fit.
 * Nothing here consults the tool's own metadata for the answer, which is the point.
 */
import type { Command } from 'commander';
import { describe, expect, it } from 'vitest';
import { cli } from '../../../cli.js';
import { buildAllTools, type ToolDef } from '../tools.js';

const TOOLS = buildAllTools(cli);

/** Flags the executor appends to every invocation; they live on the root program. */
const EXECUTOR_GLOBALS = new Set(['--output', '--yes', '--quiet', '--config', '--lang']);

/** Walk argv's leading tokens down the command tree to the command it names. */
function resolveCommand(argv: string[]): { cmd: Command; rest: string[] } | null {
  let cmd: Command = cli;
  let i = 0;

  while (i < argv.length) {
    const token = argv[i];
    if (token.startsWith('-')) break;
    const next: Command | undefined = cmd.commands.find(
      (c) => c.name() === token || c.aliases().includes(token)
    );
    if (!next) break;
    cmd = next;
    i++;
  }

  return cmd === cli ? null : { cmd, rest: argv.slice(i) };
}

/** Is `flag` a registered option on `cmd` or any ancestor (i.e. a global)? */
function optionExists(cmd: Command, flag: string): boolean {
  if (EXECUTOR_GLOBALS.has(flag)) return true;
  for (let node: Command | null = cmd; node; node = node.parent) {
    if (node.options.some((opt) => opt.long === flag || opt.short === flag)) return true;
  }
  return false;
}

/**
 * A value the field will accept. Probed rather than introspected, so it does not
 * depend on Zod internals: try a string, then a boolean, then a number.
 */
function sampleValue(field: unknown): unknown {
  const schema = field as { safeParse?: (v: unknown) => { success: boolean } };
  if (typeof schema.safeParse !== 'function') return 'x';
  for (const candidate of ['x', true, 1]) {
    if (schema.safeParse(candidate).success) return candidate;
  }
  return 'x';
}

/** Populate EVERY field of the tool's schema, so every flag it can emit is emitted. */
function fullArgs(tool: ToolDef): Record<string, unknown> {
  const args: Record<string, unknown> = {};
  for (const [key, field] of Object.entries(tool.schema)) {
    args[key] = sampleValue(field);
  }
  return args;
}

/** Every reason this argv would be rejected by the CLI. */
function rejections(argv: string[]): string[] {
  const resolved = resolveCommand(argv);
  if (!resolved) {
    return [`no such command: "${argv.filter((t) => !t.startsWith('-')).join(' ')}"`];
  }

  const { cmd, rest } = resolved;
  const problems: string[] = [];
  let positionals = 0;

  for (let i = 0; i < rest.length; i++) {
    const token = rest[i];

    if (token.startsWith('--') || (token.startsWith('-') && token.length > 1)) {
      const flag = token.split('=')[0];
      if (!optionExists(cmd, flag)) {
        problems.push(`unknown flag "${flag}" on \`${cmd.name()}\``);
        continue;
      }
      // Skip the flag's value when it was passed as a separate token. Commander
      // consumes the next token for BOTH `--flag <v>` (Option.required) and
      // `--flag [v]` (Option.optional) — `repo diff --content [path]` is the
      // latter, and treating its value as a stray positional is a false alarm.
      const opt = [...cmd.options, ...(cmd.parent?.options ?? [])].find(
        (o) => o.long === flag || o.short === flag
      );
      const takesValue = opt ? opt.required || opt.optional : false;
      if (takesValue && !token.includes('=') && rest[i + 1] && !rest[i + 1].startsWith('-')) {
        i++;
      }
      continue;
    }

    positionals++;
  }

  const registered = cmd.registeredArguments;
  const variadic = registered.some((a) => a.variadic);
  if (!variadic && positionals > registered.length) {
    problems.push(
      `passes ${positionals} positional(s) but \`${cmd.name()}\` registers ${registered.length}`
    );
  }

  return problems;
}

describe('MCP tools emit argv the CLI accepts', () => {
  it('has tools to check (the gate must not pass by finding nothing)', () => {
    // A suite that silently checks zero tools is the failure mode this whole file
    // exists to prevent, so assert the population before asserting anything about it.
    expect(TOOLS.length).toBeGreaterThan(50);
  });

  it.each(
    TOOLS.map((t) => [t.name, t] as const)
  )('%s builds an argv the CLI accepts', (_name, tool) => {
    const argv = tool.command(fullArgs(tool));
    const problems = rejections(argv);

    expect(problems, `rdc ${argv.join(' ')}\n  -> ${problems.join('; ')}`).toEqual([]);
  });

  it.each(
    TOOLS.filter((t) => t.repoArgField).map((t) => [t.name, t] as const)
  )("%s's repoArg names a field that actually exists in its schema", (_name, tool) => {
    // repoArgField drives the grand-repo guard: the guard reads args[repoArgField]
    // to learn which repo is being touched. Name a field that does not exist and
    // it reads `undefined` — the guard then scopes NOTHING, silently, on a tool
    // whose whole reason for carrying the annotation is that it touches a repo.
    // The web console reads the same annotation to pick its repo picker.
    expect(Object.keys(tool.schema)).toContain(tool.repoArgField);
  });
});
