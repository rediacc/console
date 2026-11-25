/**
 * The agent grant's scope, enforced where a hosted call resolves (agent/plans/PLAN-rmcp-agent-grants.md Design 2 and 4).
 *
 * The MCP Worker checks the read-only flag and the tool list against the call's raw arguments; it cannot see the
 * machine and repository a call resolves to, so the machine and repo globs travel with the grant to the executor
 * (`agent-session` answers the scope) and are applied here, against the target the executor's own resolver finds.
 * The tool checks are repeated here too: the executor does not rely on the Worker having made them.
 */

import type { ContractCommand } from '@rediacc/shared/cli-contract';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { McpToolEntry } from '@rediacc/shared/mcp/registry';
import { type DecisionTarget, matchesGlob } from '@rediacc/shared/policy';
import type { requestOf } from '../ai/tools.js';
import { configService } from '../config/config-resources.js';
import {
  createOutputState,
  createRequestConfigScope,
  runInRequestContext,
} from '../core/request-context.js';
import type { AgentGrantScopeAnswer } from './agent-grant-session.js';
import { clusterSubjectOf, resolveExecutorTarget } from './policy.js';

/** The registry tool's own scope check (workers/mcp/src/scope.ts `scopeAdmitsTool`). */
export function scopeAdmitsTool(scope: AgentGrantScopeAnswer, tool: McpToolEntry): boolean {
  if (scope.readOnly && !tool.annotations.readOnlyHint) return false;
  return scope.tools === undefined || scope.tools.includes(tool.name);
}

/** The ref or machine a command names, by flag or by positional (the executor route's own rule). */
export function targetFrom(
  option: string | null,
  positional: string | null,
  params: Record<string, unknown>,
  positionals: Record<string, unknown>
): string | undefined {
  const fromFlag = option ? params[option] : undefined;
  if (typeof fromFlag === 'string') return fromFlag;
  const fromPositional = positional ? positionals[positional] : undefined;
  return typeof fromPositional === 'string' ? fromPositional : undefined;
}

/** The machine a repo lives on: its placement's machine, or the machine its datastore is attached to. */
async function machineOfRepo(config: RdcConfig, name: string): Promise<string | undefined> {
  const repo = await runInRequestContext(
    {
      output: createOutputState(),
      stdout: [],
      stderr: [],
      config: createRequestConfigScope(config),
    },
    () => configService.getRepository(name)
  );
  const placement = repo?.placement;
  if (!placement) return undefined;
  if ('machine' in placement) return placement.machine;
  return config.state?.datastores?.[placement.datastore]?.attachedTo;
}

function repoRefusal(scope: AgentGrantScopeAnswer, target: DecisionTarget): string | undefined {
  if (scope.repos === undefined) return undefined;
  const name = target.repo?.name;
  if (!name) return 'This grant is limited to named repositories, and this call names none.';
  if (scope.repos.some((glob) => matchesGlob(glob, name))) return undefined;
  return `The repository ${name} is outside this grant's repositories.`;
}

async function machineRefusal(
  scope: AgentGrantScopeAnswer,
  target: DecisionTarget,
  config: RdcConfig
): Promise<string | undefined> {
  if (scope.machines === undefined) return undefined;
  const repoName = target.repo?.name;
  const machine = target.machine ?? (repoName ? await machineOfRepo(config, repoName) : undefined);
  if (!machine) return 'This grant is limited to named machines, and this call resolves to none.';
  if (scope.machines.some((glob) => matchesGlob(glob, machine))) return undefined;
  return `The machine ${machine} is outside this grant's machines.`;
}

/**
 * Why the grant's machine and repo globs refuse this call, or undefined when they admit it. A limit that is
 * set and a target the call does not name or resolve is a refusal: a limit that cannot be checked does not admit.
 */
export async function globRefusal(
  scope: AgentGrantScopeAnswer,
  entry: ContractCommand,
  request: ReturnType<typeof requestOf>,
  config: RdcConfig
): Promise<string | undefined> {
  if (scope.machines === undefined && scope.repos === undefined) return undefined;
  const { params, positionals } = request;
  const target = await resolveExecutorTarget(
    entry,
    {
      ref: targetFrom(entry.repoOption, entry.repoPositional, params, positionals),
      machine: targetFrom(entry.machineOption, entry.machinePositional, params, positionals),
      subject: clusterSubjectOf(entry, positionals),
    },
    config
  );
  return repoRefusal(scope, target) ?? (await machineRefusal(scope, target, config));
}
