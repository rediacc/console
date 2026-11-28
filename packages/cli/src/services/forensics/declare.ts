/**
 * `rdc incident declare` (PLAN-forensics-investigation D4): evidence first, machine steps after.
 * The account record goes in first (the incident row, its eviction hold and the R2 lock rules),
 * then the forensic fork `repo fork <ref> --tag incident-<id>` and the switch to Full capture,
 * each outcome reported to the record. A failed step leaves the record and its hold in place;
 * `--resume <id>` runs again only the steps whose newest outcome is not ok.
 */
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import type { ForensicsClient, IncidentRecord, MachineStepName } from './client.js';
import type { MachineSteps, StepRun } from './machine-steps.js';
import { parseWindow } from './window.js';

export interface DeclareOptions {
  since?: string;
  until?: string;
  awareAt?: string;
  resume?: string;
}

/** The repository a declare ref names: the GUID the account store keys evidence by, and its name. */
export interface DeclareRepo {
  guid: string;
  name: string;
}

export interface DeclareDeps {
  client: ForensicsClient;
  repo: (ref: string) => Promise<DeclareRepo>;
  steps: MachineSteps;
  now: () => Date;
}

interface StepOutcome {
  name: MachineStepName;
  outcome: 'ok' | 'failed' | 'skipped';
  detail?: string;
}

export interface DeclareResult {
  incident: IncidentRecord;
  steps: StepOutcome[];
  /** The command that runs the failed steps again; null when every step is ok. */
  retry: string | null;
}

/** The fork tag of an incident: `incident-<id>`, lowercase as the tag grammar requires. */
function incidentForkTag(id: string): string {
  return `incident-${id.toLowerCase()}`;
}

function invalid(message: string): CliExitError {
  return new CliExitError(ERROR_CODES.VALIDATION_ERROR, message);
}

function parseAwareAt(value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) throw invalid(t('forensics.badInstant', { flag: '--aware-at', value }));
  return new Date(parsed).toISOString();
}

/** The incident `--resume` names, refused when it is closed or covers another scope. */
async function resumable(
  client: ForensicsClient,
  id: string,
  repo: DeclareRepo
): Promise<IncidentRecord> {
  const incident = await client.findIncident(id);
  if (incident.scopeKind !== 'repo' || incident.scopeRef !== repo.guid) {
    throw invalid(
      t('incident.resumeScope', {
        id: incident.id,
        scope: `${incident.scopeKind}:${incident.scopeRef}`,
        name: repo.name,
      })
    );
  }
  if (incident.status === 'closed') throw invalid(t('incident.resumeClosed', { id: incident.id }));
  return incident;
}

function stepDone(incident: IncidentRecord, name: MachineStepName): boolean {
  const latest = [...incident.steps].reverse().find((s) => s.name === name);
  return latest?.status === 'ok';
}

/** The incident a run works on: a new declaration, or the one `--resume` names. */
function openIncident(
  repo: DeclareRepo,
  options: DeclareOptions,
  deps: DeclareDeps
): Promise<IncidentRecord> {
  if (options.resume !== undefined) {
    // A resumed incident keeps the window and awareness it was declared with.
    if (options.since ?? options.until ?? options.awareAt) {
      throw invalid(t('incident.resumeWindow'));
    }
    return resumable(deps.client, options.resume, repo);
  }
  const window = parseWindow(options, deps.now());
  const awareAt = parseAwareAt(options.awareAt);
  return deps.client.declareIncident({
    scopeKind: 'repo',
    scopeRef: repo.guid,
    windowFrom: window.from,
    windowTo: window.to,
    ...(awareAt === undefined ? {} : { awareAt }),
  });
}

/** Run one machine step unless its newest outcome is already ok, and report the outcome. */
async function runStep(
  incident: IncidentRecord,
  name: MachineStepName,
  run: () => Promise<StepRun>,
  deps: DeclareDeps,
  forkRef?: string
): Promise<{ incident: IncidentRecord; outcome: StepOutcome }> {
  if (stepDone(incident, name)) return { incident, outcome: { name, outcome: 'skipped' } };
  const result = await run();
  const outcome = result.ok ? 'ok' : 'failed';
  const detail = result.detail === undefined ? {} : { detail: result.detail };
  const recorded = await deps.client.recordStep(incident.id, {
    name,
    outcome,
    ...detail,
    ...(result.ok && forkRef !== undefined ? { forkRef } : {}),
  });
  return { incident: recorded, outcome: { name, outcome, ...detail } };
}

/** Declare (or resume) an incident on the repo `ref` names and run its machine steps. */
export async function declareIncident(
  ref: string,
  options: DeclareOptions,
  deps: DeclareDeps
): Promise<DeclareResult> {
  const repo = await deps.repo(ref);
  const opened = await openIncident(repo, options, deps);
  const tag = incidentForkTag(opened.id);
  const fork = await runStep(
    opened,
    'fork',
    () => deps.steps.fork(ref, tag),
    deps,
    `${repo.name}:${tag}`
  );
  // The level switch runs even after a failed fork: capture at Full protects the evidence still
  // to come, and it does not depend on the snapshot.
  const level = await runStep(fork.incident, 'level', () => deps.steps.level(ref, 'full'), deps);
  const steps = [fork.outcome, level.outcome];
  const failed = steps.some((s) => s.outcome === 'failed');
  return {
    incident: level.incident,
    steps,
    retry: failed ? `rdc incident declare ${ref} --resume ${opened.id}` : null,
  };
}
