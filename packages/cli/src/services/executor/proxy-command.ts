/**
 * Running a command through `--proxy`, from the root preAction hook.
 *
 * Interception happens HERE, before the action body runs, and that placement is
 * the whole point of this file. A command's action body reads local config on its
 * way to the executor (utils/repo-executor.ts asks configService for the
 * repository, then writes back a network id), and a proxy client has no config.
 * Intercepting deeper meant the command died before it reached the wire.
 *
 * So the local action never runs at all. This turns the parsed command back into
 * intent (a path and its options), sends that, renders the executor's events as
 * though the work were local, prints whatever the command printed, and ends the
 * process with the exit code the command chose.
 */

import type { ContractCommand } from '@rediacc/shared/cli-contract';
import { getCommand } from '@rediacc/shared/cli-contract';
import type { Command } from 'commander';
import { formatStepDuration, getActiveLabel, getDoneLabel } from '../../utils/timeline.js';
import { exitProcess, writeStderr, writeStdout } from '../core/request-context.js';
import { ProxyClient } from './proxy-client.js';
import type { RenetEvent } from './types.js';

/**
 * Refuse a command that cannot work through the proxy.
 *
 * Three kinds cannot, and the contract marks each one with a reason:
 *   - INTERACTIVE (term connect, repo tunnel): they need a TTY on the operator's
 *     terminal wired to a live session.
 *   - CLIENT-SIDE TRANSFER (repo sync upload/download/status): the files are on
 *     the operator's laptop, and the executor cannot reach them.
 *   - LOCAL EFFECT (config cert-cache pull, cluster kubeconfig, config machine
 *     scan-keys): the command reaches a machine, but its real effect is a write
 *     into the CALLER's own state. Proxied, the executor would write the file on
 *     its own disk and hand back a path that does not exist here. `scan-keys` is
 *     worse still: it would scan from the executor's network position, not yours,
 *     and record the answer in the wrong config.
 *
 * The reason string comes from the contract rather than from this function, so a
 * newly excluded command explains itself without anyone editing this file. A
 * contract invariant guarantees the reason is present whenever proxyCapable is
 * false, which is why it can be printed unconditionally.
 *
 * Called from the root preAction hook, so the operator learns this before
 * anything runs rather than after a confusing failure deep inside a request.
 */
export function assertProxyCapable(
  commandPath: string,
  proxyCapable: boolean,
  proxyBlockedReason?: string
): void {
  if (proxyCapable) return;

  throw new Error(
    proxyBlockedReason ??
      `"rdc ${commandPath}" cannot run through --proxy. It needs your local terminal or ` +
        `filesystem, which the executor cannot reach. Run it without --proxy.`
  );
}

/**
 * Refuse `--background` for a command that cannot become a detached job.
 *
 * Mirrors assertProxyCapable and derives its message from the same
 * `proxyBlockedReason`, because `detachable` is `proxyCapable` minus jobs: a
 * command that cannot be proxied cannot be detached for the same reasons (it
 * needs a terminal, or transfers local files, or writes the caller's own
 * config), and a `rdc job *` command manages jobs rather than doing machine
 * work, so backgrounding one is circular. No new validation invariant: the
 * message is composed here from fields the contract already carries.
 */
export function assertDetachable(commandPath: string, entry: ContractCommand | undefined): void {
  if (entry?.detachable) return;

  if (entry?.domain === 'job') {
    throw new Error(
      `"rdc ${commandPath}" manages detached jobs, so it cannot itself run in the background. ` +
        `Follow a job you started with "rdc job logs".`
    );
  }

  throw new Error(
    entry?.proxyBlockedReason ??
      `"rdc ${commandPath}" cannot run in the background: --background starts the work as a ` +
        `detached job, which only machine-plane commands that survive a dropped connection support.`
  );
}

/**
 * Commander camelCases a long flag when it stores the value: `--skip-router-restart`
 * is read back as `skipRouterRestart`. The wire speaks long flags, because that
 * is what the contract declares and what the executor validates against.
 */
function optionKey(long: string): string {
  return long.replaceAll(/-([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

/**
 * The options the operator actually gave, keyed the way the wire wants them.
 *
 * Read from the ACTION command, so only that command's own options travel. The
 * root's options (--proxy, --config, --output) are the client's business and stay
 * here; sending --proxy to a proxy would be absurd, and sending --config would be
 * asking the executor to use a config file that exists on somebody else's laptop.
 *
 * Only DECLARED options are read, so nothing can travel that the executor would
 * not accept: the contract is the same list on both sides of the wire.
 */
export function paramsFromCommand(
  entry: ContractCommand,
  actionCommand: Command
): Record<string, unknown> {
  const opts = actionCommand.opts();
  const params: Record<string, unknown> = {};

  for (const option of entry.options) {
    const value = opts[optionKey(option.long)];
    if (value === undefined) continue;
    // A switch the operator did not pass is absent, not false. Sending `false`
    // would be harmless but noisy in the audit record of what was asked for.
    if (!option.valueTaking && value === false) continue;
    params[option.long] = value;
  }

  return params;
}

/**
 * The positional values the operator gave, keyed by positional NAME.
 *
 * Read off the parsed command's `processedArgs`, which Commander fills in the
 * exact order it registered its arguments, the same order the generator emitted
 * `entry.positionals`, so index i is positional i. Only DECLARED positionals
 * travel: nothing here can carry a token the contract did not describe.
 */
export function positionalsFromCommand(
  entry: ContractCommand,
  actionCommand: Command
): Record<string, unknown> {
  // Commander fills processedArgs at parse time, aligned with registeredArguments.
  const args = actionCommand.processedArgs as unknown[];
  const positionals: Record<string, unknown> = {};

  entry.positionals.forEach((positional, index) => {
    const value = args[index];
    if (value == null || (Array.isArray(value) && value.length === 0)) return;
    positionals[positional.name] = value;
  });

  return positionals;
}

/**
 * The machine this command targets, read from whichever binding the operator
 * used: the FLAG (`machineOption`, in params) or the POSITIONAL
 * (`machinePositional`, in positionals). Undefined when the command names no
 * machine (a cluster op), in which case a dropped stream cannot be re-attached
 * and the client surfaces the truncation as before.
 */
function targetMachine(
  entry: ContractCommand,
  params: Record<string, unknown>,
  positionals: Record<string, unknown>
): string | undefined {
  const fromFlag = entry.machineOption ? params[entry.machineOption] : undefined;
  if (typeof fromFlag === 'string') return fromFlag;
  const fromPositional = entry.machinePositional ? positionals[entry.machinePositional] : undefined;
  return typeof fromPositional === 'string' ? fromPositional : undefined;
}

/**
 * Render a proxied event exactly as a local run renders it.
 *
 * The events ARE renet's events, forwarded verbatim, so they go through the same
 * timeline helpers. An operator watching `rdc --proxy repo up` sees the same
 * steps ticking over in the same shapes as `rdc repo up`; the only difference is
 * where the SSH happened.
 */
function renderEvent(event: RenetEvent): void {
  switch (event.type) {
    case 'step_start':
      writeStdout(`⠋ ${getActiveLabel(event.name ?? '')}...`);
      break;
    case 'step_done':
      if (!event.name || event.duration_ms === undefined) break;
      writeStdout(
        `\r✔ ${getDoneLabel(event.name)}${event.detail ? ` (${event.detail})` : ''} ` +
          `(${formatStepDuration(event.duration_ms)})\n`
      );
      break;
    case 'log':
      if (event.level === 'error' || event.level === 'fatal' || event.level === 'warning') {
        writeStderr(`  ${event.msg ?? ''}\n`);
      }
      break;
    case 'output':
      if (event.msg) writeStdout(event.msg);
      break;
  }
}

export interface ProxyRunContext {
  baseUrl: string;
  getToken: () => Promise<string>;
  contractVersion: string;
  fetchImpl?: typeof fetch;
}

/**
 * Run the command at the executor and end the process with its exit code.
 *
 * Never returns: the local action must not run afterwards. `exitProcess` is used
 * rather than process.exit so that this stays correct if it is ever reached from
 * inside a dispatch (it unwinds that request instead of killing the process).
 */
export async function runCommandThroughProxy(
  commandPath: string,
  actionCommand: Command,
  context: ProxyRunContext
): Promise<never> {
  const entry = getCommand(commandPath);
  if (!entry) {
    // Unreachable in practice: the contract is generated from this very tree.
    throw new Error(`"rdc ${commandPath}" is not in the contract, so it cannot be proxied.`);
  }

  const client = new ProxyClient({
    baseUrl: context.baseUrl,
    getToken: context.getToken,
    contractVersion: context.contractVersion,
    ...(context.fetchImpl ? { fetchImpl: context.fetchImpl } : {}),
  });

  const params = paramsFromCommand(entry, actionCommand);
  const positionals = positionalsFromCommand(entry, actionCommand);
  const machine = targetMachine(entry, params, positionals);

  const outcome = await client.run(
    commandPath,
    params,
    positionals,
    renderEvent,
    machine ? { machine } : undefined
  );

  // Whatever the command printed at the executor is printed here, verbatim, so
  // `rdc --proxy repo status` shows what `rdc repo status` shows.
  if (outcome.stdout) writeStdout(`${outcome.stdout}\n`);
  if (outcome.stderr) writeStderr(`${outcome.stderr}\n`);

  // Renet's own output has normally been rendered live already, arriving as
  // `output` events the same way it streams to a terminal locally. Print the
  // capture only when none of it came through, so a run never ends silently and
  // nothing is ever shown twice.
  if (!outcome.renderedLiveOutput && outcome.renetStdout) {
    writeStdout(
      outcome.renetStdout.endsWith('\n') ? outcome.renetStdout : `${outcome.renetStdout}\n`
    );
  }

  if (outcome.error) writeStderr(`${outcome.error}\n`);

  return exitProcess(outcome.exitCode);
}
