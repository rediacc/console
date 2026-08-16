import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { assertMachineExists, assertStorageExists } from './_validate.js';
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

async function assertBackupFromExists(fromName: string, sourceType: unknown): Promise<void> {
  // `local` names the machine whose OWN datastore is read, so it validates as
  // a machine exactly like `machine` does. Spelled out rather than left to the
  // fall-through below: that branch probes machine-then-storage and would
  // happen to succeed, which is the kind of accident that rots into a bug the
  // day storage stops resolving.
  if (sourceType === 'local' || sourceType === 'machine') {
    await assertMachineExists(fromName);
    return;
  }
  if (sourceType === 'storage') {
    await assertStorageExists(fromName);
    return;
  }
  // Unknown source type — pass if it resolves as either machine or storage.
  const isMachine = await assertMachineExists(fromName).then(
    () => true,
    () => false
  );
  if (isMachine) return;
  const isStorage = await assertStorageExists(fromName).then(
    () => true,
    () => false
  );
  if (!isStorage) {
    throw new ValidationError(`"${fromName}" is not a known machine or storage`);
  }
}

export async function fetchBackupList(
  params: Record<string, unknown>,
  options: BackupRunOptions
): Promise<BackupListEntry[]> {
  const machineName = options.machine;
  if (!machineName) throw new ValidationError(t('errors.machineRequiredLocal'));

  const coerced = coerceCliParams('backup_list', params as Record<string, string>);
  validateFunctionParams('backup_list', coerced);

  const fromName = typeof coerced.from === 'string' ? coerced.from : undefined;
  if (fromName) {
    await assertBackupFromExists(fromName, coerced.sourceType);
  }

  const result = await getExecutor().execute({
    functionName: 'backup_list',
    machineName,
    params: coerced,
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
    captureOutput: true,
  });

  if (!result.success) {
    // THROW rather than render-and-return-[]. Returning an empty array printed
    // an error line and then an EMPTY TABLE underneath it, so a failed listing
    // and a datastore with no backups looked identical to a reader scanning
    // output -- and one of those means your backups are missing. The caller's
    // handleError renders this, and the engine's own words are carried along
    // so the operator still sees what renet said.
    renderLocalExecutionFailure(
      result,
      t('commands.shortcuts.run.failedLocal', { error: result.error })
    );
    const tail = (result.stderr ?? result.error ?? '').toString().trim().slice(-400);
    throw new Error(tail ? `backup list failed: ${tail}` : 'backup list failed');
  }

  const payload = extractBackupListPayload(result.stdout ?? '');
  return payload?.entries ?? [];
}

function formatModified(iso: string | undefined): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace('T', ' ').replace(/\..*$/, '');
}

export async function renderBackupList(entries: TaggedBackupEntry[]): Promise<void> {
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const resolve = createGuidResolver(await loadGuidMap());

  // NO isDirectory filter. `backup push` writes a FILE for a LUKS repo and a
  // DIRECTORY for a directory-backed (kube) repo (backup_push.go branches on
  // exactly that), so filtering directories silently discarded every pushed
  // kube repo before it was ever printed.
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
