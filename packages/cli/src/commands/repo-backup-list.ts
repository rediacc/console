import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import type { ExecuteResult } from '../services/executor/executor-factory.js';
import { pendingExitCode, runCommandJob } from '../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { optStr } from '../services/jobs/steps-support.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { assertMachineExists } from './_validate.js';
import { coerceCliParams, validateFunctionParams } from './function-params.js';

export interface BackupListEntry {
  name: string;
  isDirectory?: boolean;
  size?: number;
  modTime?: string;
  /**
   * The subdirectory the artifact was found in, relative to the datastore's
   * repositories/ root, empty at the root itself.
   *
   * renet ENUMERATES now rather than being told which fixed directory to probe,
   * so the caller can no longer tag an entry with the directory it asked for.
   */
  path?: string;
}

export interface TaggedBackupEntry extends BackupListEntry {
  mode: string;
}

interface BackupListPayload {
  path?: string;
  entries?: BackupListEntry[];
}

interface BackupRunOptions {
  machine?: string;
  debug?: boolean;
  skipRouterRestart?: boolean;
}

function stripCallbackPrefix(line: string): string {
  const m = /^\[[^\]]+\]\s?(.*)$/.exec(line);
  return m ? m[1] : line;
}

function tryParsePayload(buf: string): BackupListPayload | undefined {
  try {
    const parsed = JSON.parse(buf) as BackupListPayload;
    if (Array.isArray(parsed.entries)) return parsed;
  } catch {
    /* keep accumulating */
  }
  return undefined;
}

function appendLineToBuffer(buf: string, line: string): string | undefined {
  const idx = line.indexOf('{');
  if (idx < 0 && !buf) return undefined;
  return (buf ? `${buf}\n` : '') + (idx >= 0 && !buf ? line.slice(idx) : line);
}

function extractBackupListPayload(stdout: string): BackupListPayload | undefined {
  const trimmed = stdout.trim();
  if (!trimmed) return undefined;
  let buf = '';
  for (const rawLine of trimmed.split('\n')) {
    const next = appendLineToBuffer(buf, stripCallbackPrefix(rawLine));
    if (next === undefined) continue;
    buf = next;
    const parsed = tryParsePayload(buf);
    if (parsed) return parsed;
  }
  return undefined;
}

async function assertBackupFromExists(fromName: string): Promise<void> {
  // `local` names the machine whose OWN datastore is read, so every source type validates as a machine.
  await assertMachineExists(fromName);
}

/** The listing's machine and coerced params; the machine is required and `from` must be a known machine. */
async function prepareBackupList(
  params: Record<string, unknown>,
  options: BackupRunOptions
): Promise<{ machineName: string; coerced: Record<string, unknown> }> {
  const machineName = options.machine;
  if (!machineName) throw new ValidationError(t('errors.machineRequiredLocal'));

  const coerced = coerceCliParams('backup_list', params as Record<string, string>);
  validateFunctionParams('backup_list', coerced);

  const fromName = typeof coerced.from === 'string' ? coerced.from : undefined;
  if (fromName) {
    await assertBackupFromExists(fromName);
  }
  return { machineName, coerced };
}

/**
 * A failed listing throws instead of rendering an error and returning an empty array: an error line followed by an empty table made a failed listing and a datastore with no backups look the same, and one of those means the backups are missing. The caller's handleError renders the throw, and the engine's own words are carried along so renet's reason stays visible.
 */
function throwListFailure(result: ExecuteResult): never {
  renderLocalExecutionFailure(
    result,
    t('commands.shortcuts.run.failedLocal', { error: result.error })
  );
  const tail = (result.stderr ?? result.error ?? '').toString().trim().slice(-400);
  throw new Error(tail ? `backup list failed: ${tail}` : 'backup list failed');
}

/**
 * `backup list` as one read job: the table is its `renderBackupList` step, so a ticket handed back early prints
 * nothing half-done. `refName` narrows the entries to one artifact name or prefix, as the command always did.
 */
export async function listBackups(
  params: Record<string, unknown>,
  options: BackupRunOptions,
  refName?: string
): Promise<void> {
  const { machineName, coerced } = await prepareBackupList(params, options);

  const outcome = await runCommandJob(
    'backup list',
    {
      functionName: 'backup_list',
      machineName,
      params: coerced,
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
      captureOutput: true,
    },
    [planStep('renderBackupList', { machine: machineName, ...(refName ? { ref: refName } : {}) })]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) throwListFailure(outcome.result);
}

bindStepHandler('renderBackupList', async ({ output, params }) => {
  const entries = extractBackupListPayload(output ?? '')?.entries ?? [];
  const refName = optStr(params, 'ref');
  const tagged: TaggedBackupEntry[] = entries.map((e) => ({ ...e, mode: e.path ?? '' }));
  await renderBackupList(
    refName ? tagged.filter((e) => e.name === refName || e.name.startsWith(refName)) : tagged
  );
});

function formatModified(iso: string | undefined): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace('T', ' ').replace(/\..*$/, '');
}

export async function renderBackupList(entries: TaggedBackupEntry[]): Promise<void> {
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const resolve = createGuidResolver(await loadGuidMap());

  // NO isDirectory filter. `backup push` writes a FILE for a LUKS repo and a DIRECTORY for a directory-backed (kube) repo (backup_push.go branches on exactly that), so filtering directories silently discarded every pushed kube repo before it was ever printed.
  const rows = entries
    .map((e) => {
      const resolvedName = resolve(e.name);
      const isResolved = resolvedName !== e.name;
      return {
        mode: e.mode,
        name: isResolved ? resolvedName : e.name,
        guid: e.name,
        size: typeof e.size === 'number' && e.size > 0 ? formatSizeBytes(e.size) : '-',
        modified: formatModified(e.modTime),
      };
    })
    .sort((a, b) =>
      a.mode === b.mode ? a.name.localeCompare(b.name) : a.mode.localeCompare(b.mode)
    );

  const columns = [
    { key: 'mode', header: 'Mode' },
    { key: 'name', header: 'Name' },
    { key: 'guid', header: 'GUID' },
    { key: 'size', header: 'Size', align: 'right' as const },
    { key: 'modified', header: 'Modified' },
  ];
  const output = outputService.format(rows, getOutputFormat(), columns);
  outputService.print(output);
}
