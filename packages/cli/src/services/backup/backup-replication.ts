/**
 * Replication rules: the account-server side of a `mode: replicate` destination.
 *
 * A replicate destination takes no machine upload. The account server copies each committed snapshot of a lineage from
 * the rule's source store into the destination's target store, so the rule is what makes the destination do anything.
 * Like the retention policy, the CLI DECLARES the rule per lineage and the server holds it:
 *
 *   PUT    /backups/stores/:targetId/replication          {lineageGuid, from}
 *   GET    /backups/stores/replication?lineage=           the lineage's rules
 *   DELETE /backups/stores/:targetId/replication?lineage= drop one rule
 *
 * Nothing here prints. Callers turn the result into messages, and a refusal or an older account server (404) comes back
 * as data, never as a throw: the config write has already happened by the time a rule is pushed.
 */
import type { RdcConfig } from '../../types/index.js';
import { accountServerFetch } from '../account/account-client.js';
import { configService } from '../config/config-resources.js';
import { strategyLineages } from './backup-retention.js';
import { destinationTarget, isReplicateDestination } from './backup-strategy-validate.js';

const STORES_PATH = '/account/api/v1/backups/stores';

/** One rule the server holds: copy `from` into `targetId` for `lineageGuid`. */
export interface ReplicationRule {
  lineageGuid: string;
  targetId: string;
  from: string;
}

/** What a sync did, and what it could not do. */
export interface ReplicationSyncResult {
  /** Rules written (PUT) or dropped (DELETE). */
  done: number;
  /** The account server has no replication routes (HTTP 404), so nothing was done and nothing will be. */
  unsupported: boolean;
  /** One entry per rule the server refused or could not be reached for. */
  failures: { lineageGuid: string; target: string; reason: string }[];
}

interface ReplicateDestination {
  name: string;
  enabled?: boolean;
  target?: string;
  from?: string;
  mode?: string;
}

type StrategyLike = {
  include?: string[];
  exclude?: string[];
  destinations: ReplicateDestination[];
};

const emptyResult = (): ReplicationSyncResult => ({ done: 0, unsupported: false, failures: [] });

/** The replicate destinations of a strategy; `enabledOnly` skips the disabled ones. */
export function replicateDestinations(
  strategy: Pick<StrategyLike, 'destinations'>,
  enabledOnly: boolean
): ReplicateDestination[] {
  return strategy.destinations.filter(
    (d) => isReplicateDestination(d) && (!enabledOnly || d.enabled !== false)
  );
}

/** The rules a strategy declares for the lineages it covers on `machineName` (every machine when absent). */
export function desiredRules(
  strategy: StrategyLike,
  config: RdcConfig,
  machineName?: string
): ReplicationRule[] {
  const lineages = strategyLineages(strategy, config, machineName);
  const rules: ReplicationRule[] = [];
  for (const dest of replicateDestinations(strategy, true)) {
    if (dest.from === undefined) continue;
    for (const lineageGuid of lineages) {
      rules.push({ lineageGuid, targetId: destinationTarget(dest), from: dest.from });
    }
  }
  return rules;
}

function statusOf(error: unknown): number | undefined {
  const status = (error as { status?: unknown } | null)?.status;
  return typeof status === 'number' ? status : undefined;
}

/** The code the account server puts on a refusal, when it sends one. */
function codeOf(error: unknown): string | undefined {
  const code = (error as { code?: unknown } | null)?.code;
  return typeof code === 'string' ? code : undefined;
}

/** The server's answer to a DELETE for a rule it does not hold: nothing to drop, and the route exists. */
const RULE_UNKNOWN = 'BACKUP_REPLICATE_RULE_UNKNOWN';

function reasonOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Run one request per item. A 404 carrying BACKUP_REPLICATE_RULE_UNKNOWN is a rule the server does not hold, which a
 * drop counts as done and moves past. Any other 404 is a server without the replication routes: it folds into
 * `unsupported` and stops, since every later call would 404 too. Any other failure goes into `failures`.
 */
async function applyAll(
  items: { lineageGuid: string; target: string; call: () => Promise<unknown> }[]
): Promise<ReplicationSyncResult> {
  const result = emptyResult();
  for (const item of items) {
    try {
      await item.call();
      result.done++;
    } catch (error) {
      if (statusOf(error) === 404 && codeOf(error) === RULE_UNKNOWN) {
        result.done++;
        continue;
      }
      if (statusOf(error) === 404) {
        result.unsupported = true;
        return result;
      }
      result.failures.push({
        lineageGuid: item.lineageGuid,
        target: item.target,
        reason: reasonOf(error),
      });
    }
  }
  return result;
}

/** Write each rule to the account server. */
export function pushReplicationRules(rules: ReplicationRule[]): Promise<ReplicationSyncResult> {
  return applyAll(
    rules.map((rule) => ({
      lineageGuid: rule.lineageGuid,
      target: rule.targetId,
      call: () =>
        accountServerFetch(`${STORES_PATH}/${encodeURIComponent(rule.targetId)}/replication`, {
          method: 'PUT',
          body: { lineageGuid: rule.lineageGuid, from: rule.from },
        }),
    }))
  );
}

/** Drop the rule of each (lineage, target) pair. A rule the server does not hold (404 BACKUP_REPLICATE_RULE_UNKNOWN) is not a failure and never stops the drops after it; a 404 without that code reads as an older server, which has no rule to drop either. */
export function dropReplicationRules(
  pairs: { lineageGuid: string; targetId: string }[]
): Promise<ReplicationSyncResult> {
  return applyAll(
    pairs.map((pair) => ({
      lineageGuid: pair.lineageGuid,
      target: pair.targetId,
      call: () =>
        accountServerFetch(
          `${STORES_PATH}/${encodeURIComponent(pair.targetId)}/replication?lineage=${encodeURIComponent(pair.lineageGuid)}`,
          { method: 'DELETE' }
        ),
    }))
  );
}

/** The rules the server holds for one lineage; an unreadable route (older server, any failure) is an empty list. */
export async function listReplicationRules(lineageGuid: string): Promise<ReplicationRule[]> {
  try {
    const response = await accountServerFetch<{ rules?: ReplicationRule[] } | undefined>(
      `${STORES_PATH}/replication?lineage=${encodeURIComponent(lineageGuid)}`
    );
    return Array.isArray(response?.rules) ? response.rules : [];
  } catch {
    return [];
  }
}

/** On bind: register a rule per (covered lineage on the machine, enabled replicate destination). */
export async function registerStrategyReplication(
  strategy: StrategyLike,
  machineName: string
): Promise<ReplicationSyncResult> {
  const config = await configService.getCurrent();
  if (!config) return emptyResult();
  return pushReplicationRules(desiredRules(strategy, config, machineName));
}

/**
 * Drop the rules of the given destinations for the lineages the strategy covers on `machineName` (every machine when
 * absent). Used when a replicate destination is removed or disabled, and when the strategy is unbound.
 */
export async function removeReplicationRulesFor(
  strategy: StrategyLike,
  destinations: ReplicateDestination[],
  machineName?: string
): Promise<ReplicationSyncResult> {
  const config = await configService.getCurrent();
  if (!config || destinations.length === 0) return emptyResult();
  const lineages = strategyLineages(strategy, config, machineName);
  const pairs = destinations.flatMap((dest) =>
    lineages.map((lineageGuid) => ({ lineageGuid, targetId: destinationTarget(dest) }))
  );
  return dropReplicationRules(pairs);
}
