import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { ValidationError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { coerceCliParams, validateFunctionParams } from './queue.js';
import { resolveExtraMachines } from './repo-backup.js';

export interface BackupListEntry {
  name: string;
  isDirectory?: boolean;
  size?: number;
  modTime?: string;
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

export async function fetchBackupList(
  params: Record<string, unknown>,
  options: BackupRunOptions
): Promise<BackupListEntry[]> {
  const provider = await getStateProvider();
  const machineName = options.machine;
  if (!machineName) throw new ValidationError(t('errors.machineRequiredLocal'));
  if (provider.isCloud) {
    throw new ValidationError(t('commands.repo.backup.list.localOnly'));
  }

  const coerced = coerceCliParams('backup_list', params as Record<string, string>);
  validateFunctionParams('backup_list', coerced);
  const extraMachines = await resolveExtraMachines(coerced);

  const result = await localExecutorService.execute({
    functionName: 'backup_list',
    machineName,
    params: coerced,
    extraMachines,
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
    captureOutput: true,
  });

  if (!result.success) {
    renderLocalExecutionFailure(
      result,
      t('commands.shortcuts.run.failedLocal', { error: result.error })
    );
    return [];
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
  const { formatSizeBytes } = await import('@rediacc/shared/queue-vault');
  const resolve = createGuidResolver(await loadGuidMap());

  const rows = entries
    .filter((e) => !e.isDirectory)
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
  const output = outputService.format(rows, 'table', columns);
  outputService.print(output);
}
