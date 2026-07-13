import type {
  ListResult,
  RepositoryInfo,
} from '@rediacc/shared/renet-contract/data/list-types.generated';
import {
  getContainers,
  getServices,
} from '@rediacc/shared/renet-contract/data/list-types.generated';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/core/output.js';
import type { OutputFormat } from '../../types/index.js';

/**
 * The folded-in refinements from the retired `machine containers|services|repos`
 * commands (06 §6.1): `machine status --containers --health-check`,
 * `--services --stability-check`, `--repositories --search`. Each operates on
 * the same ListResult the status view already fetched.
 */

/** `--health-check`: gate on unhealthy containers, exit 2 if any. */
export function runContainerHealthCheck(
  listResult: ListResult,
  format: OutputFormat,
  resolve: (guid: string) => string
): void {
  const unhealthy = getContainers(listResult).filter((c) => c.health?.status === 'unhealthy');
  if (unhealthy.length === 0) {
    outputService.success(t('commands.machine.status.containersAllHealthy'));
    return;
  }
  outputService.error(
    t('commands.machine.status.containersUnhealthyFound', { count: unhealthy.length })
  );
  if (format === 'json') {
    outputService.print(
      unhealthy.map((c) => ({
        ...c,
        repository: resolve(c.repository),
        repository_guid: c.repository,
      })),
      format
    );
  } else {
    for (const c of unhealthy) {
      outputService.info(`  - ${c.name} (${resolve(c.repository)})`);
    }
  }
  process.exitCode = 2;
}

/** `--stability-check`: gate on unstable services, exit 2 if any. */
export function runServiceStabilityCheck(
  listResult: ListResult,
  format: OutputFormat,
  resolve: (guid: string) => string
): void {
  const unstable = getServices(listResult).filter(
    (s) => s.active_state === 'failed' || s.restart_count > 3 || s.sub_state === 'auto-restart'
  );
  if (unstable.length === 0) {
    outputService.success(t('commands.machine.status.servicesAllStable'));
    return;
  }
  outputService.error(
    t('commands.machine.status.servicesUnstableFound', { count: unstable.length })
  );
  if (format === 'json') {
    outputService.print(
      unstable.map((s) => ({
        ...s,
        repository: resolve(s.repository),
        repository_guid: s.repository,
      })),
      format
    );
  } else {
    for (const s of unstable) {
      outputService.info(
        `  - ${s.service_name} (${s.active_state}, ${s.restart_count} restarts, ${resolve(s.repository)})`
      );
    }
  }
  process.exitCode = 2;
}

/** `--search <text>`: filter the repositories section by name / mount path. */
export function filterRepositoriesBySearch(
  repositories: RepositoryInfo[],
  search: string,
  repoDisplayName: (guid: string, serverName?: string) => string
): RepositoryInfo[] {
  const term = search.toLowerCase();
  return repositories.filter(
    (r) =>
      r.name.toLowerCase().includes(term) ||
      repoDisplayName(r.name, r.repo_name).toLowerCase().includes(term) ||
      (r.mount_path ? r.mount_path.toLowerCase().includes(term) : false)
  );
}
