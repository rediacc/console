/**
 * Executor selection.
 *
 * Every machine-plane command resolves its executor here instead of importing
 * `localExecutorService` directly. The seam earns its keep twice over:
 *
 *   - It is where renet events are teed into an in-flight dispatch, so a command
 *     streams its progress to a console without knowing that anything is
 *     listening (event-tap.ts).
 *   - It is where the executor a dispatch pinned on the request context wins over
 *     the process default, which is how the serve layer drives a command body it
 *     does not control, and how a test drives one without touching a machine.
 *
 * What is NOT here any more: proxy routing. `--proxy` used to swap in a remote
 * executor at this seam, which was too deep to work. A command's action body does
 * config work on the way here (reading the repository, allocating a network id),
 * and a proxy client holds no config, so it never survived the trip. Proxying now
 * intercepts the whole COMMAND, before any action runs (proxy-command.ts), and
 * this file is once again about one thing: which executor runs the work.
 */

import { stateMismatch } from '../../utils/cli-exit-error.js';
import { currentRequestContext } from '../core/request-context.js';
import { attachWindowMs, clientKindFromEnv, invocationMinter } from '../jobs/attach.js';
import { createDaemonExecutor } from './daemon/client.js';
import { runsOutsideJob } from './detached-execution.js';
import { requestExecutor, tapExecutor } from './event-tap.js';
import { localExecutorService } from './local-executor.js';
import type { ExecuteOptions, ExecuteResult, Executor, RepoExpectation } from './types.js';

/**
 * The process default outside a dispatch: the same-host executor daemon, backed
 * by the direct local executor. The daemon amortises SSH/provision/cache cold
 * costs across consecutive `rdc` runs and falls back to the direct executor on
 * anything (no daemon, wrong platform, non-serializable options, a served
 * dispatch).
 *
 * Built lazily on first use, not at module load. `getExecutor` already read
 * `localExecutorService` lazily; constructing the wrapper here at module-init
 * would instead read it EAGERLY, and this module sits in an import cycle where
 * `localExecutorService` is not yet initialised at that moment, capturing
 * `undefined` as the fallback. One instance, since it holds no per-call state.
 */
let daemonBackedExecutor: Executor | undefined;
function getDaemonBackedExecutor(): Executor {
  daemonBackedExecutor ??= createDaemonExecutor(localExecutorService);
  return daemonBackedExecutor;
}

// The factory is the entry point to the executor layer, so callers get the seam's types from here too rather than reaching into an implementation.
export type { ExecuteResult, Executor, RenetEvent } from './types.js';

/**
 * Process-global set by `--background` / `-b` in the root preAction hook.
 *
 * A process global, not a threaded parameter, because there are ~35 hand-rolled
 * execute() call sites and threading a flag through all of them (and every
 * command body between the hook and the seam) is exactly the churn the executor
 * seam exists to avoid. The decorator below reads it once, at the seam.
 */
let backgroundRequested = false;

/** Called by the root preAction hook when `--background` is present. */
export function setBackgroundRequested(value: boolean): void {
  backgroundRequested = value;
}

/** Whether this invocation asked to fire-and-forget its machine work. */
export function isBackgroundRequested(): boolean {
  return backgroundRequested;
}

// --- vault directives (agent/plans/PLAN-detached-jobs.md section 14) ---------

/**
 * What the command layer asked of the NEXT job on one repository and machine:
 * the start precondition `resolveRepoRef` derived (`expect`) and the network ID
 * allocation `ensureRepositoryNetworkId` handed to renet (`networkIdAuto`).
 *
 * Recorded here rather than threaded through each verb because the probe this
 * replaces lived in the shared resolution funnel, not in the ~40 verbs that call
 * it; the seam stamps the directive onto the first call naming that repository
 * on that machine, in the invoking process, so it crosses the executor daemon's
 * socket as plain ExecuteOptions. Each directive is spent by one call, which is
 * what the probe was: one check before the verb's work.
 */
interface VaultDirective {
  machine: string;
  /** Every spelling a call's `params.repository` may use for the repo: key, `name:tag`, GUID. */
  aliases: Set<string>;
  repoGuid: string;
  /** The family name, for the refusal text of the client-side fallback probe. */
  repoName: string;
  expect?: RepoExpectation;
  networkIdAuto?: boolean;
  /** The config key the allocated ID is recorded under. */
  recordAs?: string;
}

/** Outside a dispatch the process is one invocation; inside one, each request keeps its own list. */
const processDirectives: VaultDirective[] = [];
const requestDirectives = new WeakMap<object, VaultDirective[]>();

function directives(): VaultDirective[] {
  const context = currentRequestContext();
  if (!context) return processDirectives;
  let list = requestDirectives.get(context);
  if (!list) {
    list = [];
    requestDirectives.set(context, list);
  }
  return list;
}

function directiveFor(input: {
  machine: string;
  aliases: string[];
  repoGuid: string;
  repoName: string;
}): VaultDirective {
  const list = directives();
  const aliases = input.aliases.filter((alias) => alias !== '');
  const found = list.find(
    (d) => d.machine === input.machine && aliases.some((alias) => d.aliases.has(alias))
  );
  if (found) {
    for (const alias of aliases) found.aliases.add(alias);
    return found;
  }
  const created: VaultDirective = {
    machine: input.machine,
    aliases: new Set(aliases),
    repoGuid: input.repoGuid,
    repoName: input.repoName,
  };
  list.push(created);
  return created;
}

/** Record the start precondition of the next job on this repository and machine. */
export function expectRepoState(input: {
  machine: string;
  aliases: string[];
  repoGuid: string;
  repoName: string;
  expect: RepoExpectation;
}): void {
  directiveFor(input).expect = input.expect;
}

/** Ask the next job on this repository and machine to allocate its network ID (`network_id: "auto"`). */
export function requestNetworkIdAuto(input: {
  machine: string;
  aliases: string[];
  repoGuid: string;
  repoName: string;
  recordAs: string;
}): void {
  const directive = directiveFor(input);
  directive.networkIdAuto = true;
  directive.recordAs = input.recordAs;
}

/** Test seam: drop every pending directive of this scope. */
export function resetVaultDirectives(): void {
  directives().length = 0;
}

/** Take (and spend) the directive the call names, if any. */
function claimDirective(options: ExecuteOptions): VaultDirective | undefined {
  const repo = options.params?.repository;
  if (typeof repo !== 'string' || repo === '') return undefined;
  const list = directives();
  const index = list.findIndex((d) => d.machine === options.machineName && d.aliases.has(repo));
  if (index === -1) return undefined;
  return list.splice(index, 1)[0];
}

/**
 * Apply a claimed directive. A call that stays on `renet execute` never reaches
 * `job start`, which is the only place renet evaluates `expect`, so a
 * `repo_present` there is checked by the client-side presence probe it replaced
 * (failing open on a probe failure, as before).
 */
async function stampDirective(
  options: ExecuteOptions,
  directive: VaultDirective | undefined
): Promise<ExecuteOptions> {
  if (!directive) return options;
  const expect = options.expect ?? directive.expect;
  const outside = runsOutsideJob(options);
  if (outside && expect === 'repo_present') {
    await probePresentOutsideJob(options.machineName, directive);
  }
  return withDirective(options, outside ? undefined : expect, directive.networkIdAuto);
}

/** The call's options with the directive's fields added where the caller set none. */
function withDirective(
  options: ExecuteOptions,
  expect: RepoExpectation | undefined,
  networkIdAuto: boolean | undefined
): ExecuteOptions {
  const auto = options.networkIdAuto ?? networkIdAuto;
  return { ...options, ...(expect ? { expect } : {}), ...(auto ? { networkIdAuto: auto } : {}) };
}

async function probePresentOutsideJob(machine: string, directive: VaultDirective): Promise<void> {
  const { probeRepoPresent } = await import('../repo/repo-mount-check.js');
  if ((await probeRepoPresent(directive.repoGuid, machine)) !== false) return;
  throw stateMismatch(
    `config places ${directive.repoName} on ${machine}, ` +
      `but ${machine} does not have its image. Run "rdc config reconcile", then retry.`
  );
}

/** Record the network ID a `network_id: "auto"` start allocated, under the repo it ran for. */
async function recordAllocatedNetworkId(
  options: ExecuteOptions,
  directive: VaultDirective | undefined,
  result: ExecuteResult
): Promise<void> {
  if (result.networkId === undefined) return;
  const repo = directive?.recordAs ?? options.params?.repository;
  if (typeof repo !== 'string' || repo === '') return;
  const { recordNetworkId } = await import('../config/network-id-discovery.js');
  await recordNetworkId(repo, result.networkId);
}

/**
 * Stamp every call with its entry point's attach window and its request id
 * (agent/plans/PLAN-detached-jobs.md sections 15 and 17). The window comes from
 * the entry point, never from the verb: unlimited for a direct terminal run,
 * JOB_ATTACH_WINDOW_MS inside a served dispatch or an MCP child, and 0 under
 * `--background`, whose ticket returns the moment the job starts.
 *
 * The `--background` global is ignored inside a serve request context: it would
 * otherwise leak across concurrent in-flight requests, and a dispatch's window is
 * the proxy's. The request id is minted here, in the invoking process, once per
 * call, so a start retried after a dropped answer carries the same id and a call
 * served by the executor daemon still carries the client's invocation.
 *
 * A caller's explicit numeric window or request id wins; an undefined window means none was chosen.
 *
 * The call also takes the vault directives recorded for its repository and
 * machine (`expect`, `networkIdAuto`, above), and a network ID the start
 * allocated is written to the config here, in the invoking process that holds it.
 */
export function attachDecorator(inner: Executor): Executor {
  return {
    async execute(options) {
      const served = currentRequestContext() !== undefined;
      const window =
        options.attachWindowMs === undefined
          ? attachWindowMs({
              background: backgroundRequested && !served,
              served,
              client: clientKindFromEnv(),
            })
          : options.attachWindowMs;
      const directive = claimDirective(options);
      const stamped = await stampDirective(options, directive);
      const result = await inner.execute({
        ...stamped,
        attachWindowMs: window,
        requestId: options.requestId ?? invocationMinter().next(options.machineName),
      });
      await recordAllocatedNetworkId(options, directive, result);
      return result;
    },
  };
}

/**
 * The executor for the current invocation.
 *
 * An in-process dispatch (the executor serving a command) pins its own executor
 * on the request context, so that wins. Outside a dispatch there is no context
 * and this is the daemon-backed executor, which transparently falls back to the
 * local executor whenever the daemon is unavailable or the work is not
 * daemon-eligible, so the effective behaviour on a laptop is unchanged.
 * `--background` composes over whichever it is, and is inert inside a dispatch.
 */
export function getExecutor(): Executor {
  return tapExecutor(attachDecorator(requestExecutor() ?? getDaemonBackedExecutor()));
}
