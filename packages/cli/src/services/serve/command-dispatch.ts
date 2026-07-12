/**
 * In-process command dispatch.
 *
 * /v1/exec names a renet FUNCTION. Only a caller that already has the CLI can
 * work out which function a command runs, because that mapping lives inside each
 * Commander action body and exists nowhere else. A web console has no CLI, so it
 * could render all of the commands and execute almost none of them.
 *
 * So the executor runs the CLI. A request names a command path ("repo fork") and
 * its options; this builds the argv a local `rdc` would have been given, parses
 * it with the real Commander tree, and lets the real action body resolve the
 * function and its params. Nothing here knows what "repo fork" maps to, which is
 * the point: there is no second mapping to drift from the first.
 *
 * WHY IN-PROCESS AND NOT A SUBPROCESS. Shelling out to `rdc` per request would
 * throw away the warm SSH pool and the decrypted config, which is the entire
 * reason a container stays warm. It would also lose the event stream, since the
 * events would have to be re-parsed out of a pipe.
 *
 * WHY IT IS SAFE TO EVALUATE POLICY ON THE PATH. A client that sent both a path
 * and a function could make them disagree, leaving policy to guard a label while
 * something else runs. Here the client sends ONLY the path, and the executor
 * derives the function from it, so what was authorized is by construction what
 * executes.
 *
 * Three things had to be tamed to run CLI code inside a server, and each is a
 * property of the CLI being a one-command-per-process program:
 *   1. Commander's parse state lives on the tree, so each dispatch gets its own.
 *   2. Output goes to stdout, so it is redirected into the request context.
 *   3. Fatal errors call process.exit(), which would kill every other tenant's
 *      in-flight command; inside a context they throw instead.
 */

import type { ContractCommand, ContractOption } from '@rediacc/shared/cli-contract';
import { getCommand } from '@rediacc/shared/cli-contract';
import type { Command } from 'commander';
import { CommanderError } from 'commander';
import { createCli } from '../../cli.js';
import { createOutputState, DispatchExit, runInRequestContext } from '../core/request-context.js';
import type { ExecuteResult, Executor, RenetEvent } from '../executor/types.js';

/** A request the executor refuses before running anything. Answered as a 400. */
export class CommandRejected extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'CommandRejected';
  }
}

/**
 * A request that has been checked and turned into argv, but not yet run.
 *
 * Separate from running it because everything that can be REFUSED must be
 * refused before the response stream opens: once it is open the status is
 * already 200, and a rejection can then only be described inside the body. An
 * unknown command, an interactive one, or a smuggled flag is a 400, so the check
 * happens here and the stream opens only for a request that will actually run.
 */
export interface PreparedCommand {
  entry: ContractCommand;
  argv: string[];
}

export interface DispatchArgs {
  /** The checked request. */
  prepared: PreparedCommand;
  /** The executor the command's machine work must run through. */
  executor: Executor;
  /** Called for every renet event the command streams. */
  onEvent: (event: RenetEvent) => void;
}

export interface DispatchOutcome {
  result: ExecuteResult;
  stdout: string;
  stderr: string;
  /**
   * The renet function the command actually ran, when it ran one.
   *
   * Observed rather than declared: it is read off the executor call the command
   * body made. That makes it the right thing to audit, because it is what
   * happened, not what anyone said would happen. Undefined for a command that
   * touched no machine.
   */
  functionName?: string;
}

/**
 * Commands the executor will not run, however the policy is written.
 *
 * The gate is the contract's own `proxyCapable`, enforced HERE and not only on
 * the client. That distinction is the whole point: `--proxy` refuses these
 * client-side (proxy-command.ts), but a request can reach /v1/command without
 * going through the CLI at all, so the client refusal is advisory. This one is
 * the enforcement, and it must match, which is why both read the same field from
 * the same contract.
 *
 * `proxyCapable` is false for three kinds of command, and every one of them is a
 * real hazard if an executor runs it for a remote caller:
 *   - INTERACTIVE (term connect, a tunnel): needs a TTY or never returns, so it
 *     would hang a request forever and hold a slot.
 *   - CLIENT-SIDE TRANSFER (repo sync upload/download): the paths are on the
 *     CALLER's disk, so proxied it reads or writes the EXECUTOR's filesystem
 *     instead. `repo sync upload --local /root/.ssh/id_rsa` would exfiltrate the
 *     executor's own files.
 *   - LOCAL EFFECT / `other` and `config` plane (config ssh show, config show,
 *     self-update, the MCP server): acts on the executor's own process or returns
 *     its held config in plaintext. `config ssh show` would hand back the
 *     executor's SSH private key; `rdc update` would replace its running binary.
 *
 * Only the `machine` plane, non-interactive and not otherwise excluded, is left,
 * which is exactly what `proxyCapable` marks. Policy is a SEPARATE, later gate:
 * a command can be proxyable and still denied by the org's rules. This one is not
 * about who may run it, but about whether it can be run remotely at all.
 *
 * The reason comes from the contract, not from here, so a newly excluded command
 * explains itself. A contract invariant guarantees a reason is present whenever
 * proxyCapable is false, so it can be surfaced unconditionally.
 */
function assertDispatchable(entry: ContractCommand): void {
  if (!entry.proxyCapable) {
    throw new CommandRejected(
      entry.proxyBlockedReason ?? `"rdc ${entry.pathKey}" cannot be run through the executor.`
    );
  }
}

/**
 * Turn params into argv, using the contract as the only source of truth for what
 * a flag is.
 *
 * An undeclared key is REFUSED rather than ignored. Ignoring it would let a
 * caller quietly believe an option took effect; and were it ever appended
 * blindly, it would be argv injection into the executor's own CLI. Nothing here
 * builds a flag the contract did not declare.
 */
function buildFlags(entry: ContractCommand, params: Record<string, unknown>): string[] {
  const byLong = new Map<string, ContractOption>(entry.options.map((o) => [o.long, o]));

  return Object.entries(params).flatMap(([key, value]) => {
    const option = byLong.get(key);
    if (!option) {
      const declared = entry.options.map((o) => `--${o.long}`).join(', ') || '(none)';
      throw new CommandRejected(
        `"rdc ${entry.pathKey}" has no --${key} option. It accepts: ${declared}.`
      );
    }
    if (value === undefined || value === null) return [];
    return option.valueTaking ? valueFlag(option, value) : switchFlag(option, value);
  });
}

/** A switch is present or absent. "--flag false" is not a thing Commander understands. */
function switchFlag(option: ContractOption, value: unknown): string[] {
  if (typeof value !== 'boolean') {
    throw new CommandRejected(`--${option.long} is a switch, so it takes true or false.`);
  }
  return value ? [`--${option.long}`] : [];
}

/** A value-taking flag, repeated once per value when the option is variadic. */
function valueFlag(option: ContractOption, value: unknown): string[] {
  const values = Array.isArray(value) ? value : [value];
  if (!option.variadic && values.length > 1) {
    throw new CommandRejected(`--${option.long} takes a single value.`);
  }
  return values.flatMap((item) => {
    if (typeof item === 'object') {
      throw new CommandRejected(`--${option.long} takes a text value.`);
    }
    return [`--${option.long}`, String(item)];
  });
}

/**
 * The argv a local `rdc` would have been given.
 *
 * `--output json` and `--yes` are forced, never taken from the caller: the
 * executor has no terminal, so it must never render a table and must never stop
 * at a confirmation prompt that nobody will ever answer. Both are root options,
 * so they lead, exactly as `rdc --output json --yes repo fork ...` does on a
 * laptop (the same shape services/../commands/mcp/executor.ts shells out with).
 */
export function buildArgv(entry: ContractCommand, params: Record<string, unknown>): string[] {
  return ['--output', 'json', '--yes', ...entry.path, ...buildFlags(entry, params)];
}

/**
 * Make a Commander tree safe to run inside a server.
 *
 * Commander's failure mode is a CLI's failure mode: print to stderr and exit the
 * process. An unknown option or a missing required one would therefore kill the
 * executor and every other tenant's command with it. exitOverride makes it throw,
 * and the output configuration keeps its help and error text out of the
 * container's stdout. Both are per-Command, so the whole tree is walked: settings
 * are copied to subcommands when they are CREATED, and this tree already exists.
 */
function harden(command: Command, stderr: string[]): void {
  command.exitOverride();
  command.configureOutput({
    writeOut: (str) => stderr.push(str),
    writeErr: (str) => stderr.push(str),
  });
  for (const child of command.commands) harden(child, stderr);
}

/** The result of a command that ran but reported nothing back through the executor. */
function inertResult(durationMs: number): ExecuteResult {
  return { success: true, exitCode: 0, durationMs };
}

/**
 * Run one command and return what it did.
 *
 * The ExecuteResult is the one the command's own machine work produced, so a
 * console sees exactly what the CLI would have shown. A command that touched no
 * machine (a config-plane read) still succeeds, with its answer in stdout.
 */
export function prepareCommand(pathKey: string, params: Record<string, unknown>): PreparedCommand {
  const entry = getCommand(pathKey);
  if (!entry) {
    throw new CommandRejected(`There is no "rdc ${pathKey}" command.`);
  }
  assertDispatchable(entry);
  return { entry, argv: buildArgv(entry, params) };
}

export async function dispatchCommand(args: DispatchArgs): Promise<DispatchOutcome> {
  const { argv } = args.prepared;
  const started = Date.now();

  // The result of the LAST machine call the command made. A command can make
  // several (fork then up); the caller cares about how the command as a whole
  // ended, which is the final one, or a failure at any point.
  let lastResult: ExecuteResult | undefined;
  let functionName: string | undefined;
  const recordingExecutor: Executor = {
    async execute(options) {
      functionName = options.functionName;
      const result = await args.executor.execute(options);
      lastResult = result;
      return result;
    },
  };

  const context = {
    output: createOutputState(),
    stdout: [] as string[],
    stderr: [] as string[],
    onEvent: args.onEvent,
    executor: recordingExecutor,
  };

  const outcome = await runInRequestContext(context, async () => {
    const program = createCli();
    harden(program, context.stderr);
    try {
      await program.parseAsync(argv, { from: 'user' });
      return { failed: false as const };
    } catch (error) {
      return { failed: true as const, error };
    }
  });

  const stdout = context.stdout.join('\n');
  const stderr = context.stderr.join('\n');

  if (!outcome.failed) {
    return {
      result: lastResult ?? inertResult(Date.now() - started),
      stdout,
      stderr,
      functionName,
    };
  }

  const failure = toFailure(outcome.error, lastResult, Date.now() - started, stderr);
  return { result: failure, stdout, stderr, functionName };
}

/**
 * Turn however the command died into an ExecuteResult.
 *
 * A DispatchExit is the command's own handleError() path: it already rendered
 * its message and, on a laptop, would have exited with that code. A
 * CommanderError is bad argv (a missing required option), which is the caller's
 * fault and worth saying plainly. Anything else is a genuine throw.
 *
 * A failed machine call reports through its own ExecuteResult, which carries the
 * renet error code and guidance, so that is preferred over anything reconstructed
 * here.
 */
function toFailure(
  error: unknown,
  lastResult: ExecuteResult | undefined,
  durationMs: number,
  stderr: string
): ExecuteResult {
  if (lastResult && !lastResult.success) return lastResult;

  if (error instanceof DispatchExit) {
    return {
      success: error.code === 0,
      exitCode: error.code,
      error: error.code === 0 ? undefined : stderr.trim() || error.message,
      durationMs,
    };
  }

  if (error instanceof CommanderError) {
    // Commander has already written the detail (which option was missing) into
    // the captured stderr; its own message is a summary.
    return {
      success: false,
      exitCode: 1,
      error: stderr.trim() || error.message,
      durationMs,
    };
  }

  return {
    success: false,
    exitCode: 1,
    error: error instanceof Error ? error.message : 'The command failed.',
    durationMs,
  };
}
