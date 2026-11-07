import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import { configService } from '../services/config/config-resources.js';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../types/index.js';

/** strategy name -> machines binding it, for reporting deployment reach. */
export async function strategyBindings(): Promise<Map<string, string[]>> {
  const machines = await configService.listMachines();
  const bindings = new Map<string, string[]>();
  for (const { name, config } of machines) {
    for (const strategy of config.backupStrategies ?? []) {
      const list = bindings.get(strategy);
      if (list) list.push(name);
      else bindings.set(strategy, [name]);
    }
  }
  return bindings;
}

function formatRetention(retention: NonNullable<BackupStrategyConfig['retention']>): string {
  const parts: [string, number | undefined][] = [
    ['last', retention.keepLast],
    ['within', retention.keepWithinSeconds],
    ['hourly', retention.keepHourly],
    ['daily', retention.keepDaily],
    ['weekly', retention.keepWeekly],
    ['monthly', retention.keepMonthly],
    ['yearly', retention.keepYearly],
  ];
  return parts
    .filter(([, n]) => n !== undefined)
    .map(([name, n]) => `${name}=${n}`)
    .join(',');
}

/** One destination as a cell: its name, with a marker when it is switched off. */
function destinationCell(dest: BackupStrategyDestination): string {
  return dest.enabled === false ? `${dest.name} (disabled)` : dest.name;
}

/** One strategy as a row of `show`: the same fields in every format, so a script and a person read one document. */
export function strategyRow(name: string, strategy: BackupStrategyConfig): Record<string, unknown> {
  return {
    name,
    schedule: strategy.schedule,
    mode: strategy.mode ?? BACKUP_DEFAULTS.MODE,
    enabled: strategy.enabled !== false,
    bandwidthLimit: strategy.bandwidthLimit ?? '-',
    readBandwidthLimit: strategy.readBandwidthLimit ?? '-',
    cpuLimit: strategy.cpuLimit ?? '-',
    include: strategy.include?.join(',') ?? '-',
    exclude: strategy.exclude?.join(',') ?? '-',
    retention: strategy.retention ? formatRetention(strategy.retention) : '-',
    destinations: strategy.destinations.map(destinationCell).join(', ') || '-',
  };
}
