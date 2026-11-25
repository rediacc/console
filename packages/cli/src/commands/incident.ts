import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { ForensicsClient } from '../services/forensics/client.js';
import {
  type ExportResult,
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

/**
 * `rdc incident export <id> --out <dir>`: the incident's window written to a directory with its
 * raw files, verified on the way; exit 1 when the downloaded evidence shows a gap or an edit.
 */
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
  const failed = result.verification !== null && !result.verification.clean;
  if (getOutputFormat() === 'json') {
    outputService.print(result, 'json');
  } else {
    printExport(result);
  }
  if (failed) setExitCode(1);
}

function printExport(result: ExportResult): void {
  outputService.success(
    t('incident.exported', {
      id: result.incident,
      dir: result.directory,
      rows: result.timelineRows,
    })
  );
  if (result.unreadable > 0)
    outputService.warn(t('forensics.unreadable', { count: result.unreadable }));
  const verification = result.verification;
  if (result.rawTooLarge) {
    outputService.info(t('incident.rawTooLarge'));
  } else if (verification === null) {
    outputService.info(t('incident.rawListed', { count: result.rawFiles }));
  } else if (verification.clean) {
    outputService.info(t('incident.rawVerified', { count: verification.files }));
  } else {
    for (const g of verification.gaps)
      outputService.warn(t('forensics.verifyGap', { ref: g.ref, reason: g.reason }));
    for (const e of verification.edits)
      outputService.warn(t('forensics.verifyEdit', { ref: e.ref, reason: e.reason }));
    outputService.warn(
      t('incident.rawNotVerified', {
        gaps: verification.gaps.length,
        edits: verification.edits.length,
      })
    );
  }
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
