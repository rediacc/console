/**
 * The CLI's command policy: the typed command paths, the one enforcement point the root hook
 * calls (`enforceRootCommand`), the named commands whose action judges its own resolved target
 * (`enforceResolvedTarget`), and the agent check of a `--proxy` run. Every decision is
 * `decide`'s (packages/shared/src/policy/decide.ts), asked through `enforce`
 * (services/policy/enforce.ts); the command flags (grandGuard, forkBlocked, agentBlocked) come
 * from the CLI contract, generated from command-metadata.ts.
 */
import path from 'node:path';
import { CLI_CONTRACT, type ContractCommand, getCommand } from '@rediacc/shared/cli-contract';
import { POLICY_DEFAULTS } from '@rediacc/shared/config/defaults';
import {
  type Decision,
  type DecisionCommand,
  type DecisionPrincipal,
  type DecisionTarget,
  type EffectivePolicy,
  findStaleCommandGlobs,
  isClusterLifecycleCommand,
  staleDenyRefusal,
} from '@rediacc/shared/policy';
import type { Command } from 'commander';
import { configFileStorage } from '../adapters/config-file-storage.js';
import type {
  RemoteConfigAdapter,
  RemotePolicyContext,
} from '../adapters/remote-config-adapter.js';
import { COMMAND_METADATA } from '../config/command-metadata.js';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { localPolicyCeiling } from '../services/config/policy-record.js';
import { auditLog } from '../services/core/audit-log.js';
import { currentRequestContext } from '../services/core/request-context.js';
import { paramsFromCommand, positionalsFromCommand } from '../services/executor/proxy-command.js';
import { DecisionError, enforce } from '../services/policy/enforce.js';
import { readEnvOverrides } from '../services/policy/overrides-env.js';
import { resolveTarget, type TargetRef } from '../services/policy/target.js';
import { ERROR_CODES } from '../types/errors.js';
import type { RemoteConfig } from '../types/index.js';
import { isAgentEnvironment } from './agent-guard.js';
import { CliExitError } from './cli-exit-error.js';
import { ValidationError } from './errors.js';
import { isRepoAllowedByGrandEnv } from './grand-env.js';
import {
  isAncestryVerificationAvailable,
  isOverrideLegitimate,
  OVERRIDE_VAR_CLUSTER,
  OVERRIDE_VAR_GRAND,
} from './process-ancestry.js';

export interface CommandPolicy {
  /** Block grand (non-fork) repos in agent mode. Override: REDIACC_ALLOW_GRAND_REPO */
  grandGuard: boolean;
  /** Block fork repos, command is nonsensical on interim fork environments */
  forkBlocked: boolean;
  /**
   * Block in agent mode. Absolute for most commands (run, mcp, no override).
   * The `cluster <verb>` family is the one exception: it can be deliberately
   * unlocked per cluster by the operator via REDIACC_ALLOW_CLUSTER_OPS,
   * ancestry-verified exactly like REDIACC_ALLOW_GRAND_REPO.
   */
  agentBlocked: boolean;
}

/**
 * Typed command path constants. Use these instead of string literals
 * to get compile-time safety and autocomplete.
 */
export const CMD = {
  REPO_UP: 'repo up',
  REPO_DOWN: 'repo down',
  REPO_DELETE: 'repo delete',
  // Deletes a machine image no config names, addressed by GUID; repo delete's grand guard, judged from the machine's fork marker.
  REPO_ADMIN_ORPHAN_DELETE: 'repo admin orphan delete',

  REPO_SYNC_UPLOAD: 'repo sync upload',
  REPO_SYNC_DOWNLOAD: 'repo sync download',
  REPO_PUSH: 'repo push',
  REPO_PULL: 'repo pull',
  // The plumbing subtree moved under `repo admin` (§5.4). Same guards, new paths.
  REPO_ADMIN_VALIDATE: 'repo admin validate',
  REPO_ADMIN_OWNERSHIP: 'repo admin ownership',
  REPO_ADMIN_TEMPLATE: 'repo admin template apply',
  REPO_ADMIN_AUTOSTART_ENABLE: 'repo admin autostart enable',
  REPO_ADMIN_AUTOSTART_DISABLE: 'repo admin autostart disable',
  REPO_RESIZE: 'repo resize',
  REPO_EXPAND: 'repo expand',
  // Carries REPO_DOWN's guards: `--offline` stops the repository's Docker daemon, so it is as disruptive as `repo down`.
  REPO_PRUNE: 'repo prune',
  REPO_PROMOTE: 'repo promote',
  REPO_TUNNEL: 'repo tunnel',
  REPO_EXEC: 'repo exec',
  REPO_COMMIT: 'repo commit',
  REPO_BRANCH: 'repo branch',
  REPO_CHECKOUT: 'repo checkout',
  REPO_MERGE: 'repo merge',
  // Feature layer (spec §5.4): gate class B. Replicate and canary never mutate the primary's data, replicate forks it, canary shares it, so grandGuard is
  // the whole gate; no class-D cluster unlock is required (they stay inside one
  // cluster's datastores, and replicate is the flagship agent-safe demo).
  REPO_REPLICATE: 'repo replicate',
  REPO_REPLICATE_REMOVE: 'repo replicate remove',
  REPO_REPLICATE_REFRESH: 'repo replicate refresh',
  REPO_CANARY_CREATE: 'repo canary create',
  REPO_CANARY_WEIGHT: 'repo canary weight',
  REPO_CANARY_REMOVE: 'repo canary remove',
  // NOTE: `repo secret` subcommands intentionally have no CMD entries. The V2 write-only model removed grandGuard from secret commands, mutation-gate is the safety property, not a command-level policy. If a future need arises (e.g. an entirely new agent gate), reintroduce CMD.REPO_SECRET_* and add a metadata entry that references it. These were 'term repo' / 'vscode repo' ,
  // SYNTHETIC paths that never existed in the tree (term has only ever had `connect`). Keyed to the real leaves now, so the policy gate and the command tree finally agree on the same string.
  TERM_CONNECT: 'term connect',
  VSCODE_CONNECT: 'vscode connect',
  RUN: 'run',
  BACKUP_RESTORE: 'backup restore',
  // Client-side image transfers (PLAN-backup-local-image): download only reads a reflink snapshot, upload registers a NEW repo behind the agent create-gate.
  BACKUP_DOWNLOAD: 'backup download',
  BACKUP_UPLOAD: 'backup upload',
  // Deletes a grand repository's whole backup lineage from the chunk store; the repository itself is kept.
  BACKUP_PURGE: 'backup purge',
  CLUSTER_CREATE: 'cluster create',
  CLUSTER_DESTROY: 'cluster destroy',
  CLUSTER_SCALE: 'cluster scale',
  CLUSTER_FORK: 'cluster fork',
  CLUSTER_MIGRATE: 'cluster migrate',
  CLUSTER_JOIN: 'cluster join',
  CLUSTER_EVICT: 'cluster evict',
  CLUSTER_SNAPSHOT_CREATE: 'cluster snapshot create',
  // Datastore mutations are class D: a datastore holds every repo in it, so moving or destroying one is an infrastructure act, not a repo act.
  DATASTORE_CREATE: 'datastore create',
  DATASTORE_ATTACH: 'datastore attach',
  DATASTORE_DETACH: 'datastore detach',
  DATASTORE_FORK: 'datastore fork',
  DATASTORE_RESIZE: 'datastore resize',
  DATASTORE_DELETE: 'datastore delete',
  DATASTORE_SNAPSHOT_CREATE: 'datastore snapshot create',
} as const;

export type CommandPath = (typeof CMD)[keyof typeof CMD];

/**
 * Backward-compatible Map view of COMMAND_METADATA for consumers that expect a Map.
 * Constructed lazily from the unified metadata.
 */
function buildPoliciesMap(): ReadonlyMap<CommandPath, CommandPolicy> {
  const entries: [CommandPath, CommandPolicy][] = [];
  for (const [path, meta] of Object.entries(COMMAND_METADATA)) {
    if (meta.grandGuard || meta.forkBlocked || meta.agentBlocked) {
      entries.push([
        path as CommandPath,
        {
          grandGuard: meta.grandGuard ?? false,
          forkBlocked: meta.forkBlocked ?? false,
          agentBlocked: meta.agentBlocked ?? false,
        },
      ]);
    }
  }
  return new Map(entries);
}

export const COMMAND_POLICIES: ReadonlyMap<CommandPath, CommandPolicy> = buildPoliciesMap();

/**
 * Commands whose target the action itself resolves, so the root hook cannot read it off the
 * parsed arguments and leaves the decision to the action (agent/plans/PLAN-rmcp-decide.md
 * Design 3). Each action calls `enforceResolvedTarget` once it holds the target; `judgedAs`
 * names the contract entry whose flags the decision reads when it differs from the command's own.
 * Every other command is judged once, by `enforceRootCommand`, before its action runs.
 */
export const ACTION_RESOLVED_TARGETS: ReadonlyMap<string, { reason: string; judgedAs?: string }> =
  new Map<string, { reason: string; judgedAs?: string }>([
    [CMD.BACKUP_DOWNLOAD, { reason: 'each of the variadic refs is resolved and judged in turn' }],
    [CMD.BACKUP_UPLOAD, { reason: 'the repo name comes from the image file name' }],
    [
      CMD.BACKUP_PURGE,
      {
        reason:
          'the target is the ref, else the lineage of a repository the config no longer names',
      },
    ],
    [CMD.BACKUP_RESTORE, { reason: 'the target repo is derived from the artifact ref' }],
    [CMD.REPO_PROMOTE, { reason: 'the target is the grand the fork replaces, not the fork named' }],
    [
      CMD.REPO_CHECKOUT,
      { reason: 'the target is the --from working fork, else the repo the commit belongs to' },
    ],
    [
      CMD.REPO_ADMIN_ORPHAN_DELETE,
      {
        reason:
          "the image is addressed by GUID and its fork state is read from the machine's marker",
      },
    ],
    [CMD.TERM_CONNECT, { reason: 'the target is a machine or a repo, told apart in the action' }],
    [CMD.VSCODE_CONNECT, { reason: 'the target is a machine or a repo, told apart in the action' }],
    [CMD.CLUSTER_JOIN, { reason: 'the cluster is named by the --cluster option' }],
    [CMD.CLUSTER_EVICT, { reason: 'the cluster is the one the named machine belongs to' }],
    [
      'cluster rehearse',
      {
        reason: 'a rehearsal forks the cluster, so it is judged as cluster fork',
        judgedAs: CMD.CLUSTER_FORK,
      },
    ],
  ]);

/** The root option a `needs_confirmation` retry repeats the asked-for name in (cli.ts registers it). */
export const CONFIRM_GRAND_FLAG = '--confirm-grand';

/** The `--confirm-grand` value of this invocation (set by the root hook), or undefined. */
let confirmGrandValue: string | undefined;

/** Record the root `--confirm-grand <name>` value the confirmation retry of a decision reads. */
export function setConfirmGrand(value: string | undefined): void {
  confirmGrandValue = value;
}

/**
 * The commands that recover access to a remote config, by full command path. They must still run
 * when the session cannot be opened (an expired token, an unreachable server, a lost enrollment),
 * so a failed session leaves exactly these unjudged; every other command, config mutations
 * included, is refused with the session error. When the session opens they are judged like any
 * other command.
 *
 * - `config remote enable` re-enrolls a linked config whose device credentials are gone
 *   (config-remote-reenroll.ts) and links a config for the first time.
 * - `config remote status` reports whether this device can open the store.
 * - `subscription login` and `subscription refresh` renew the token the session is opened with.
 */
export const SESSION_RECOVERY_COMMANDS: ReadonlySet<string> = new Set([
  'config remote enable',
  'config remote status',
  'subscription login',
  'subscription refresh',
]);

/**
 * Recovery commands exempt only in one form, and only for one kind of session failure.
 * `config remote disable --local` is the refusal's own way out when the server path is closed for
 * good (config-remote-unlink.ts): the store no longer holds the config, or the server refuses this
 * account. An unreachable server, a timeout or a 5xx is not that, so the unlink is refused with the
 * session error; otherwise a member could unlink during an outage and then run as the owner of the
 * now-local config. The server-backed form needs the session anyway, so it stays judged.
 */
const LOCAL_FORM_RECOVERY_COMMANDS: ReadonlySet<string> = new Set(['config remote disable']);

/**
 * Which session failures leave a run unjudged: `none` refuses every one, `any` admits every one
 * (SESSION_RECOVERY_COMMANDS), and `closed-server-path` admits only a definitive answer that the
 * server path is closed for good, by `closedServerPath`, the same test that names `--local` in the
 * server-backed refusal.
 */
type SessionRecovery = 'none' | 'any' | 'closed-server-path';

/** The session failures this run may skip judgement on. */
function sessionRecoveryOf(commandPath: string, actionCommand: Command): SessionRecovery {
  if (SESSION_RECOVERY_COMMANDS.has(commandPath)) return 'any';
  if (!LOCAL_FORM_RECOVERY_COMMANDS.has(commandPath)) return 'none';
  return (actionCommand.opts() as { local?: unknown }).local === true
    ? 'closed-server-path'
    : 'none';
}

/** The principal and policy a local run is judged with. */
interface LocalJudgement {
  principal: DecisionPrincipal;
  policy: EffectivePolicy | null;
}

/** One session per adapter per process: a command judged twice (variadic refs) asks once. */
const remoteJudgements = new WeakMap<RemoteConfigAdapter, Promise<RemotePolicyContext>>();

/**
 * The principal and policy of a local run, or null when the run is left unjudged.
 *
 * An agent environment (agent-guard.ts) makes the principal an agent, else a human.
 *
 * A LOCAL-file config is owned by the person at the keyboard, so the role is `owner`, and its own
 * `policy` field is the ceiling (D24), refused when malformed or when a deny rule names a command
 * that does not exist, as the executor refuses it. No field, or no config file yet, is no policy.
 *
 * A REMOTE config is judged as the account server names its token's member: the org role and
 * email from `/configs/session` and the effective policy from the policy record
 * (RemoteConfigAdapter.policyContext). A member is never judged as an owner: when the session
 * cannot be opened the run is refused with that error, save for a recovery run (`sessionRecoveryOf`).
 */
async function localJudgement(recovery: SessionRecovery): Promise<LocalJudgement | null> {
  const kind = isAgentEnvironment() ? 'agent' : 'human';
  const owner: DecisionPrincipal = { kind, userEmail: '', orgRole: 'owner' };
  const name = configService.getCurrentName();
  if (!(await configFileStorage.exists(name))) return { principal: owner, policy: null };
  const config = await configFileStorage.load(name);
  if (config.remote !== undefined) return remoteJudgement(kind, recovery, name, config.remote);
  if (config.policy === undefined) return { principal: owner, policy: null };
  const effective = localPolicyCeiling(config);
  for (const document of [effective.org, effective.team]) {
    if (!document) continue;
    const stale = findStaleCommandGlobs(document, LIVE_COMMANDS);
    if (stale.deny.length > 0) throw new ValidationError(staleDenyRefusal(stale.deny));
  }
  return { principal: owner, policy: effective };
}

/** The session's principal and policy for a remote config (see `localJudgement`). */
async function remoteJudgement(
  kind: DecisionPrincipal['kind'],
  recovery: SessionRecovery,
  configName: string,
  remote: RemoteConfig
): Promise<LocalJudgement | null> {
  try {
    const adapter = await configService.getActiveRemoteAdapter();
    if (!adapter) throw new Error('The active config names a remote store but has no adapter.');
    let pending = remoteJudgements.get(adapter);
    if (!pending) {
      pending = adapter.policyContext();
      remoteJudgements.set(adapter, pending);
    }
    const { principal, policy } = await pending;
    return { principal: { kind, ...principal }, policy };
  } catch (error) {
    if (recovery === 'any') return null;
    if (recovery === 'closed-server-path') {
      // Loaded only on this failure path; the unlink module owns the test of a closed server path.
      const { closedServerPath } = await import('../commands/config-remote-unlink.js');
      if (closedServerPath(error, configName, remote) !== undefined) return null;
    }
    throw error;
  }
}

const LIVE_COMMANDS: readonly string[] = CLI_CONTRACT.commands.map((c) => c.pathKey);

/**
 * The contract fields `decide` reads. A hidden command has no contract entry (`rdc run`), so its
 * guard flags come from COMMAND_METADATA, the source the contract is generated from.
 */
function decisionCommandOf(
  commandPath: string,
  entry: ContractCommand | undefined
): DecisionCommand {
  const meta = COMMAND_METADATA[commandPath] as
    | { grandGuard?: boolean; forkBlocked?: boolean; agentBlocked?: boolean }
    | undefined;
  const source = entry ?? meta;
  return {
    pathKey: commandPath,
    destructive: entry?.destructive === true,
    grandGuard: source?.grandGuard === true,
    forkBlocked: source?.forkBlocked === true,
    agentBlocked: source?.agentBlocked === true,
  };
}

/**
 * Record that an agent ran a cluster operation through a legitimate operator opt-in.
 * actor.kind is stamped `agent` automatically by auditLog. Best-effort: an audit-log failure
 * never blocks the allowed operation.
 */
function auditClusterOverride(commandPath: string, subject: string | undefined): void {
  try {
    const xdg = process.env.XDG_CONFIG_HOME ?? `${process.env.HOME ?? ''}/.config`;
    auditLog(`${xdg}/rediacc`, {
      command: commandPath,
      paths: subject ? [subject] : [],
      outcome: 'ok',
      reason: `${OVERRIDE_VAR_CLUSTER} override honored`,
    });
  } catch {
    /* audit-log failure must never block the operation */
  }
}

/** The grand-repo refusal for an agent, naming an opt-in the agent set itself when there is one. */
function grandOptInMessage(name: string): string {
  if (isRepoAllowedByGrandEnv(name) && !isOverrideLegitimate(OVERRIDE_VAR_GRAND)) {
    const key = isAncestryVerificationAvailable()
      ? 'errors.agent.grandGuardOverride'
      : 'errors.agent.grandGuardOverrideNonLinux';
    return t(key, { name, platform: process.platform });
  }
  return t('errors.agent.grandGuard', { name });
}

/** The translated message of a refusal, chosen by its stable code. */
function decisionMessage(
  decision: Decision,
  command: DecisionCommand,
  target: DecisionTarget
): string {
  const name = target.repo?.name ?? POLICY_DEFAULTS.UNNAMED_REPO;
  switch (decision.code) {
    case 'AGENT_BLOCKED':
      return t('errors.agent.commandBlocked', { command: command.pathKey });
    case 'FORK_BLOCKED':
      return t('errors.agent.forkBlocked', { command: command.pathKey });
    case 'AGENT_OPT_IN_MISSING':
      return isClusterLifecycleCommand(command)
        ? t('errors.agent.clusterOpBlocked', { command: command.pathKey })
        : grandOptInMessage(name);
    case 'POLICY_DENIED':
      return t('errors.agent.policyDenied', { command: command.pathKey });
    case 'GRAND_REPO_DENIED':
      return t('errors.agent.grandRepoDenied', { command: command.pathKey, name });
    case 'CLUSTER_OPS_DENIED':
      return t('errors.agent.clusterOpsDenied', { command: command.pathKey });
    case 'CONFIRMATION_REQUIRED':
      return t('errors.agent.confirmationRequired', {
        command: command.pathKey,
        name,
        flag: CONFIRM_GRAND_FLAG,
        value: decision.next?.confirm?.value ?? name,
      });
    case 'ALLOWED':
      return decision.reason;
  }
}

/** A refusal as the CLI error: the translated message, then the code, the reason and the way past. */
function refusalError(decision: Decision, command: DecisionCommand, target: DecisionTarget) {
  const { code, reason, next } = decision;
  return new CliExitError(
    ERROR_CODES.VALIDATION_ERROR,
    decisionMessage(decision, command, target),
    {
      details: [code, reason, ...(next?.run ? [next.run] : [])],
    }
  );
}

interface JudgeArgs {
  principal: DecisionPrincipal;
  command: DecisionCommand;
  target: TargetRef;
  policy: EffectivePolicy | null;
}

/**
 * Ask `enforce` once; a `needs_confirmation` answer whose value the root `--confirm-grand` option
 * repeats is asked again as confirmed. Any refusal becomes the CLI error.
 */
async function judge({ principal, command, target, policy }: JudgeArgs): Promise<void> {
  const overrides = readEnvOverrides();
  const args = { principal, command, target, policy, overrides };
  try {
    await enforce(args);
  } catch (error) {
    if (!(error instanceof DecisionError)) throw error;
    const { decision } = error;
    const confirmed =
      decision.verdict === 'needs_confirmation' &&
      confirmGrandValue !== undefined &&
      confirmGrandValue === decision.next?.confirm?.value;
    if (!confirmed) throw refusalError(decision, command, await resolveTarget(target));
    await enforce({ ...args, confirmation: { granted: true } }).catch(async (retry: unknown) => {
      if (!(retry instanceof DecisionError)) throw retry;
      throw refusalError(retry.decision, command, await resolveTarget(target));
    });
  }
  if (principal.kind === 'agent' && isClusterLifecycleCommand(command)) {
    auditClusterOverride(command.pathKey, target.subject);
  }
}

/**
 * Judge a local run of `commandPath` on `target` against the local policy and the agent rules.
 *
 * Inside an executor request the executor has already judged the command with the caller's real
 * principal and policy (services/serve/policy.ts), so nothing is judged twice. A human owner of a
 * local-file config with no policy is not asked: with no policy document an owner may run every command
 * (`MISSING_POLICY_DEFAULT`), so the answer is `allow` without resolving the target.
 */
async function enforceLocal(
  commandPath: string,
  entry: ContractCommand | undefined,
  target: TargetRef,
  recovery: SessionRecovery = 'none'
): Promise<void> {
  if (currentRequestContext() !== undefined) return;
  const judgement = await localJudgement(recovery);
  if (judgement === null) return;
  const { principal, policy } = judgement;
  if (principal.kind === 'human' && policy === null) return;
  await judge({ principal, command: decisionCommandOf(commandPath, entry), target, policy });
}

/** A positional or flag value as the name it carries, or undefined. */
function refValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

/** The bound value of a positional or option named by the contract, or undefined. */
function boundValue(bag: Record<string, unknown>, name: string | null): string | undefined {
  return name ? refValue(bag[name]) : undefined;
}

/** Positional kinds that name the subject a cluster opt-in must cover. */
const SUBJECT_KINDS: ReadonlySet<string> = new Set(['cluster', 'datastore-ref']);

/**
 * The repo ref, machine and cluster subject an action names, through the contract's positional or
 * flag bindings. A command that names no repo leaves the ref absent, and `decide` counts an absent
 * repo as grand (fail closed).
 */
function targetOf(entry: ContractCommand, actionCommand: Command): TargetRef {
  const params = paramsFromCommand(entry, actionCommand);
  const positionals = positionalsFromCommand(entry, actionCommand);
  const ref = boundValue(positionals, entry.repoPositional) ?? boundValue(params, entry.repoOption);
  const machine =
    boundValue(positionals, entry.machinePositional) ?? boundValue(params, entry.machineOption);
  const subjectPositional = entry.positionals.find((p) => SUBJECT_KINDS.has(p.kind));
  const subject = subjectPositional ? refValue(positionals[subjectPositional.name]) : undefined;
  return {
    ...(ref ? { ref } : {}),
    ...(machine ? { machine } : {}),
    ...(subject ? { subject } : {}),
  };
}

/**
 * The CLI's one enforcement point (agent/plans/PLAN-rmcp-decide.md Design 3), called by the root
 * `preAction` hook for every command before its action runs. The target is read off the parsed
 * arguments through the contract bindings; a command on `ACTION_RESOLVED_TARGETS` is left to its
 * action, which calls `enforceResolvedTarget` once it holds the target.
 *
 * @throws CliExitError carrying the decision code for any verdict but `allow`
 */
export async function enforceRootCommand(
  commandPath: string,
  entry: ContractCommand | undefined,
  actionCommand: Command
): Promise<void> {
  if (ACTION_RESOLVED_TARGETS.has(commandPath)) return;
  const target = entry ? targetOf(entry, actionCommand) : {};
  await enforceLocal(commandPath, entry, target, sessionRecoveryOf(commandPath, actionCommand));
}

/**
 * The decision for a command on `ACTION_RESOLVED_TARGETS`, called by its action with the target it
 * resolved. Any other command is judged by the root hook, so a call for one is a programming error.
 *
 * @throws CliExitError carrying the decision code for any verdict but `allow`
 */
export async function enforceResolvedTarget(commandPath: string, target: TargetRef): Promise<void> {
  const listed = ACTION_RESOLVED_TARGETS.get(commandPath);
  if (!listed) {
    throw new Error(
      `"rdc ${commandPath}" is judged by the root hook; only a command on ACTION_RESOLVED_TARGETS judges its own target.`
    );
  }
  const policyPath = listed.judgedAs ?? commandPath;
  await enforceLocal(policyPath, getCommand(policyPath), target);
}

/**
 * The agent half of a command sent through `--proxy`, judged on this side of the wire
 * (agent/plans/PLAN-rmcp-decide.md D22).
 *
 * The executor sees the caller's account, never whether an agent typed the command, so it cannot
 * ask for the opt-in a human set; this step does, before the request leaves. The decision is
 * `decide`'s, through `enforce`, with the ceiling left open (no policy, owner): the executor
 * judges the real policy with the real principal, so this step adds only the agent rules. The
 * target resolves through the one resolver against the local config; a proxy client usually holds
 * none, so the ref is `unresolved` and counts as grand, and a command that names no repo is judged
 * as one that lands on a grand. A human caller is not judged here.
 *
 * @throws CliExitError carrying the decision code for any verdict but `allow`
 */
export async function enforceProxiedAgentCommand(
  commandPath: string,
  entry: ContractCommand,
  actionCommand: Command
): Promise<void> {
  if (!isAgentEnvironment()) return;
  await judge({
    principal: { kind: 'agent', userEmail: '', orgRole: 'owner' },
    command: decisionCommandOf(commandPath, entry),
    target: targetOf(entry, actionCommand),
    policy: null,
  });
}

/**
 * Validate that a sync --remote path doesn't escape the repository boundary.
 * Rejects absolute paths and path traversal sequences.
 */
export function validateRemotePath(remotePath: string): void {
  if (remotePath.startsWith('/')) {
    throw new ValidationError(t('errors.sync.absolutePathBlocked'));
  }
  const normalized = path.posix.normalize(remotePath);
  if (normalized.startsWith('..')) {
    throw new ValidationError(t('errors.sync.pathTraversalBlocked'));
  }
}
