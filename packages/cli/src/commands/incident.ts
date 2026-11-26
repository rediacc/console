import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { ForensicsClient } from '../services/forensics/client.js';
import {
  type DeclareDeps,
  type DeclareOptions,
  type DeclareRepo,
  type DeclareResult,
  declareIncident,
} from '../services/forensics/declare.js';
import {
  type ExportResult,
  exportIncident,
  incidentDetailLines,
  incidentListLines,
  withClocks,
} from '../services/forensics/incident.js';
import { childMachineSteps } from '../services/forensics/machine-steps.js';
import { ERROR_CODES } from '../types/errors.js';
import { CliExitError, notFound } from '../utils/cli-exit-error.js';
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

/** The repository GUID the account store keys evidence by, and the name its forks take. */
async function configRepo(ref: string): Promise<DeclareRepo> {
  // Config-local resolution, as repo-target's resolveRepoRefLocal does it, without that module's executor imports: incident never reaches a machine itself (its fork and level switch are child rdc processes).
  const { parseRef } = await import('../services/addressing/ref-parser.js');
  const { placementViewFromConfig, resolveRefLocal } = await import(
    '../services/addressing/resolve-machine.js'
  );
  const { configService } = await import('../services/config/config-resources.js');
  const parsed = parseRef(ref);
  const config = await configService.getCurrent();
  if (!config) {
    throw notFound(`repository "${parsed.name}" is not in this config.`);
  }
  const { name } = resolveRefLocal(ref, placementViewFromConfig(config));
  const repoKey = parsed.tag ? `${parsed.name}:${parsed.tag}` : parsed.name;
  const repo = await configService.getRepository(repoKey);
  if (!repo?.repositoryGuid) {
    throw new CliExitError(ERROR_CODES.NOT_FOUND, t('forensics.noRepoGuid', { name }));
  }
  return { guid: repo.repositoryGuid, name };
}

const defaultDeclareDeps = (): DeclareDeps => ({
  client: new ForensicsClient(),
  repo: configRepo,
  steps: childMachineSteps,
  now: () => new Date(),
});

/**
 * `rdc incident declare <ref>`: the account record first, then the forensic fork and the switch
 * to Full capture, each step reported. A failed step exits 1 and names the `--resume` command.
 */
export async function runIncidentDeclare(
  ref: string,
  options: DeclareOptions,
  deps: DeclareDeps = defaultDeclareDeps()
): Promise<DeclareResult> {
  const result = await declareIncident(ref, options, deps);
  if (getOutputFormat() === 'json') {
    outputService.print({ ...result, incident: withClocks(result.incident, deps.now()) }, 'json');
  } else {
    printDeclare(result);
  }
  if (result.retry !== null) setExitCode(1);
  return result;
}

function printDeclare(result: DeclareResult): void {
  outputService.success(
    t('incident.declared', {
      id: result.incident.id,
      from: result.incident.windowFrom,
      to: result.incident.windowTo,
    })
  );
  for (const step of result.steps) {
    const values = { name: step.name, detail: step.detail ?? '' };
    if (step.outcome === 'ok') outputService.info(t('incident.stepOk', values));
    else if (step.outcome === 'skipped') outputService.info(t('incident.stepSkipped', values));
    else outputService.warn(t('incident.stepFailed', values).trimEnd());
  }
  if (result.retry !== null) outputService.warn(t('incident.retry', { command: result.retry }));
}

/** `rdc incident close <id>`: close the incident; its hold and lock rules end 30 days later. */
export async function runIncidentClose(
  id: string,
  deps: IncidentDeps = defaultDeps()
): Promise<void> {
  const incident = await deps.client.findIncident(id);
  const closed = withClocks(await deps.client.closeIncident(incident.id), deps.now());
  if (getOutputFormat() === 'json') {
    outputService.print(closed, 'json');
    return;
  }
  outputService.success(t('incident.closed', { id: closed.id, at: closed.releaseAt ?? '' }));
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
    .command('declare')
    .summary(t('commands.incident.declare.descriptionShort'))
    .description(t('commands.incident.declare.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--since <when>', t('commands.repo.rowsSinceOption'))
    .option('--until <when>', t('commands.repo.rowsUntilOption'))
    .option('--aware-at <when>', t('commands.incident.declare.awareAtOption'))
    .option('--resume <id>', t('commands.incident.declare.resumeOption'))
    .action(async (ref: string, options: DeclareOptions) => {
      try {
        await runIncidentDeclare(ref, options);
      } catch (error) {
        handleError(error);
      }
    });

  incident
    .command('close')
    .summary(t('commands.incident.close.descriptionShort'))
    .description(t('commands.incident.close.description'))
    .argument('<id>', t('commands.incident.idArgument'))
    .action(async (id: string) => {
      try {
        await runIncidentClose(id);
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
