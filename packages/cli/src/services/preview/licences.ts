/**
 * Licences across the preview switch (PLAN-preview-signer.md D10).
 *
 * A repo licence file lives per signing key (`<root>/repos/<guid>/<keyId>.json`, or under
 * `datastores/<id>/` for a scoped datastore), and renet prefers the master-key file whenever one exists.
 * A preview licence (its subscription id starts with `pv-`) written beside a real one is therefore never
 * chosen, and removing the preview files leaves the real licence in force. On `leave`, for each switched
 * server: a repo with both kinds loses its preview files; a repo with preview files only is re-licensed from
 * the real account through the normal activation path, and loses them only once a real licence file exists.
 * A repo the real plan refuses keeps its preview file and is named with the reason, and no repo is ever
 * deleted.
 */
import { posix } from 'node:path';
import { t } from '../../i18n/index.js';
import { shellQuote } from '../../utils/shell-quote.js';

/** Where renet keeps repo licence files on a machine. */
const LICENSE_ROOT = '/var/lib/rediacc/license';

/** A subscription id minted on a preview starts with this (D3). */
const PREVIEW_SUBSCRIPTION_PREFIX = 'pv-';

const LICENCE_PATH =
  /^\/var\/lib\/rediacc\/license\/(?:datastores\/[^/]+\/)?repos\/([^/]+)\/([0-9a-f]{16})\.json$/;

export interface LicenceFile {
  path: string;
  /** The directory holding the repo's files for one datastore scope: the unit a repo's licence set is judged in. */
  dir: string;
  guid: string;
  keyId: string;
  /** Whether the blob's payload names a preview subscription. */
  preview: boolean;
}

/** One exec that prints every licence file as `<path><TAB><blob json on one line>`. */
export function buildLicenceListCommand(root = LICENSE_ROOT): string {
  return (
    `sudo find ${shellQuote(root)} -type f -path '*/repos/*/*.json' 2>/dev/null | ` +
    `while IFS= read -r f; do printf '%s\\t' "$f"; sudo head -c 65536 "$f" | tr -d '\\n'; echo; done`
  );
}

function isPreviewBlob(blob: unknown): boolean {
  const payload = (blob as { payload?: unknown } | null)?.payload;
  if (typeof payload !== 'string') return false;
  try {
    const decoded = JSON.parse(Buffer.from(payload, 'base64').toString('utf8')) as {
      subscriptionId?: unknown;
    };
    return (
      typeof decoded.subscriptionId === 'string' &&
      decoded.subscriptionId.startsWith(PREVIEW_SUBSCRIPTION_PREFIX)
    );
  } catch {
    return false;
  }
}

/**
 * The licence files of {@link buildLicenceListCommand}'s output. A line that is not a licence path with a
 * parseable blob is an error: a file the scan cannot classify must not be read as "not a preview file".
 */
export function parseLicenceListing(output: string): LicenceFile[] {
  const files: LicenceFile[] = [];
  for (const line of output.split('\n')) {
    if (line.trim() === '') continue;
    const tab = line.indexOf('\t');
    const path = tab < 0 ? line : line.slice(0, tab);
    const match = LICENCE_PATH.exec(path);
    if (!match) throw new Error(`unexpected licence path in listing: ${path}`);
    let blob: unknown;
    try {
      blob = JSON.parse(line.slice(tab + 1));
    } catch {
      throw new Error(`licence file ${path} is not readable JSON`);
    }
    files.push({
      path,
      dir: posix.dirname(path),
      guid: match[1],
      keyId: match[2],
      preview: isPreviewBlob(blob),
    });
  }
  return files;
}

interface RepoLicenceSet {
  dir: string;
  guid: string;
  preview: LicenceFile[];
  real: LicenceFile[];
}

function groupByRepo(files: LicenceFile[]): RepoLicenceSet[] {
  const sets = new Map<string, RepoLicenceSet>();
  for (const file of files) {
    const set = sets.get(file.dir) ?? { dir: file.dir, guid: file.guid, preview: [], real: [] };
    (file.preview ? set.preview : set.real).push(file);
    sets.set(file.dir, set);
  }
  return [...sets.values()].filter((set) => set.preview.length > 0);
}

/** The `rm` of exactly the given licence files; every path is re-checked against the licence layout. */
export function buildDeleteCommand(files: LicenceFile[]): string {
  for (const file of files) {
    if (!LICENCE_PATH.test(file.path)) throw new Error(`refusing to delete ${file.path}`);
  }
  return `sudo rm -f -- ${files.map((f) => shellQuote(f.path)).join(' ')}`;
}

interface LicenceRefusal {
  repo: string;
  guid: string;
  reason: string;
}

export interface LeaveLicenceReport {
  machine: string;
  /** Repos re-licensed from the real account; their preview files are gone. */
  relicensed: string[];
  /** Repos whose preview files were removed because a real licence already stood. */
  cleaned: string[];
  /** Repos the real account did not license: each keeps its preview file. */
  refused: LicenceRefusal[];
}

export interface LicenceDeps {
  exec(machine: string, command: string): Promise<string>;
  /** Re-license one repo from the real account (the normal activation path); a refusal carries the server's reason. */
  relicense(machine: string, guid: string): Promise<{ ok: true } | { ok: false; reason: string }>;
  repoName(guid: string): string;
}

/**
 * The licences of one switched server on `leave`. Nothing is read as a success it did not observe: a repo
 * counts as re-licensed only when a second listing shows a non-preview file in its directory.
 */
export async function releaseLicencesOnLeave(
  machine: string,
  deps: LicenceDeps
): Promise<LeaveLicenceReport> {
  const report: LeaveLicenceReport = { machine, relicensed: [], cleaned: [], refused: [] };
  const before = groupByRepo(
    parseLicenceListing(await deps.exec(machine, buildLicenceListCommand()))
  );

  const already = before.filter((set) => set.real.length > 0);
  if (already.length > 0) {
    await deps.exec(machine, buildDeleteCommand(already.flatMap((set) => set.preview)));
    report.cleaned.push(...already.map((set) => deps.repoName(set.guid)));
  }

  const only = before.filter((set) => set.real.length === 0);
  const failures = new Map<string, string>();
  for (const set of only) {
    const result = await deps.relicense(machine, set.guid);
    if (!result.ok) failures.set(set.dir, result.reason);
  }
  if (only.length === 0) return report;

  const after = parseLicenceListing(await deps.exec(machine, buildLicenceListCommand()));
  for (const set of only) {
    const stands = after.some((file) => file.dir === set.dir && !file.preview);
    const repo = deps.repoName(set.guid);
    if (stands) {
      await deps.exec(machine, buildDeleteCommand(set.preview));
      report.relicensed.push(repo);
    } else {
      report.refused.push({
        repo,
        guid: set.guid,
        reason: failures.get(set.dir) ?? t('commands.preview.msg.licenceNotIssued'),
      });
    }
  }
  return report;
}

/** The lines `leave` prints for a report: what was re-licensed, and each repo the real plan refused with its reason. */
export function licenceReportLines(report: LeaveLicenceReport, server: string): string[] {
  const lines: string[] = [];
  if (report.relicensed.length > 0) {
    lines.push(
      t('commands.preview.msg.licencesRelicensed', {
        machine: report.machine,
        repos: report.relicensed.join(', '),
        server,
      })
    );
  }
  for (const refusal of report.refused) {
    lines.push(
      t('commands.preview.msg.licenceRefused', {
        repo: refusal.repo,
        machine: report.machine,
        server,
        reason: refusal.reason,
      })
    );
  }
  return lines;
}
