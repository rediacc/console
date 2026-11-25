import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { ForensicsClient } from '../services/forensics/client.js';
import {
  exportIncident,
  incidentDetailLines,
  incidentListLines,
  withClocks,
} from '../services/forensics/incident.js';
import { getOutputFormat, handleError } from '../utils/errors.js';

export interface IncidentDeps {
  client: ForensicsClient;
  now: () => Date;
}

const defaultDeps = (): IncidentDeps => ({ client: new ForensicsClient(), now: () => new Date() });

/** `rdc incident status [id]`: every incident of the org, or one with its steps and deadline clocks. */
export async function runIncidentStatus(
  id: string | undefined,
  deps: IncidentDeps = defaultDeps()
): Promise<void> {
  const json = getOutputFormat() === 'json';
  if (id === undefined) {
    const incidents = await deps.client.listIncidents();
    if (json) outputService.print({ incidents }, 'json');
    else outputService.print(incidentListLines(incidents));
    return;
  }
  const view = withClocks(await deps.client.findIncident(id), deps.now());
  if (json) outputService.print(view, 'json');
  else outputService.print(incidentDetailLines(view));
}

/** `rdc incident export <id> --out <dir>`: the incident's window written to a directory. */
export async function runIncidentExport(
  id: string,
  options: { out?: string },
  deps: IncidentDeps = defaultDeps()
): Promise<void> {
  const incident = await deps.client.findIncident(id);
  const result = await exportIncident(
    deps.client,
    incident,
    options.out ?? `incident-${incident.id}`,
    deps.now()
  );
  if (getOutputFormat() === 'json') {
    outputService.print(result, 'json');
    return;
  }
  outputService.success(
    t('incident.exported', {
      id: result.incident,
      dir: result.directory,
      rows: result.timelineRows,
    })
  );
  if (result.unreadable > 0)
    outputService.warn(t('forensics.unreadable', { count: result.unreadable }));
  outputService.info(
    result.rawTooLarge
      ? t('incident.rawTooLarge')
      : t('incident.rawListed', { count: result.rawFiles })
  );
}

export function registerIncidentCommand(program: Command): void {
  const incident = program
    .command('incident')
    .summary(t('commands.incident.descriptionShort'))
    .description(t('commands.incident.description'));

  incident
    .command('status')
    .summary(t('commands.incident.status.descriptionShort'))
    .description(t('commands.incident.status.description'))
    .argument('[id]', t('commands.incident.idArgument'))
    .action(async (id: string | undefined) => {
      try {
        await runIncidentStatus(id);
      } catch (error) {
        handleError(error);
      }
    });

  incident
    .command('export')
    .summary(t('commands.incident.export.descriptionShort'))
    .description(t('commands.incident.export.description'))
    .argument('<id>', t('commands.incident.idArgument'))
    .option('--out <dir>', t('commands.incident.export.outOption'))
    .action(async (id: string, options: { out?: string }) => {
      try {
        await runIncidentExport(id, options);
      } catch (error) {
        handleError(error);
      }
    });
}
