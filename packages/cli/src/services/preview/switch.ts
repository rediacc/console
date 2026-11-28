/**
 * `rdc preview use` and `rdc preview leave` (PLAN-preview-signer.md D6, D8, D11, D12).
 *
 * Both flows take their effects as `deps`, so a test drives the order of events (every check before the
 * first file changes, the state written before the binary is replaced, the way back that works with the
 * preview host and channel gone) without a network or a binary. `preview-deps.ts` wires the real ones.
 */
import { homedir } from 'node:os';
import { join } from 'node:path';
import type { PreviewOverlay } from '@rediacc/shared/config-schema';
import { t } from '../../i18n/index.js';
import type { UpdateManifest } from '../../types/index.js';
import { ValidationError } from '../../utils/errors.js';
import type { PlatformKey } from '../../utils/platform.js';
import { outputService } from '../core/output.js';
import {
  type PreviewBinary,
  type PreviewBuild,
  parsePreviewBuild,
  selectPreviewBinary,
} from './build.js';
import {
  clearPreviewTouch,
  enterPreview,
  leavePreview,
  previewHostFor,
  readPreviewOverlay,
} from './state.js';

/** A preview's licences end at most this long after they were issued (D2, D4). */
const PREVIEW_LICENCE_DAYS = 7;
/** The banner adds the D11 message once fewer than this many days of licence remain. */
const BANNER_WARN_DAYS = 2;

/** Where `use` keeps the CLI it replaces: the emergency exit when the preview binary cannot run `leave`. */
export function previewKeptBinaryPath(platform: NodeJS.Platform = process.platform): string {
  const file = platform === 'win32' ? 'rdc.pre-preview.exe' : 'rdc.pre-preview';
  return join(homedir(), '.local', 'share', 'rediacc', 'preview', file);
}

/** The command that leaves the preview from the kept copy of the CLI. */
function emergencyLeaveCommand(keptPath = previewKeptBinaryPath()): string {
  return `${keptPath} preview leave`;
}

export interface PreviewUseDeps {
  fetchServerInfo(host: string): Promise<{ previewBuild?: unknown }>;
  fetchManifest(name: string): Promise<UpdateManifest>;
  platformKey(): PlatformKey | null;
  /** Whether this install can replace its own binary (a SEA); an npm or dev run cannot. */
  canReplaceBinary(): boolean;
  /** Copy the running CLI to `dest` and return its path in the install and its sha256. */
  keepCurrentBinary(dest: string): Promise<{ installPath: string; sha256: string }>;
  installBinary(binary: PreviewBinary): Promise<void>;
  confirmFormatChange(formatChange: NonNullable<PreviewOverlay['formatChange']>): Promise<boolean>;
  /** The running CLI's version and release channel, recorded for `leave`. */
  current(): { version: string; updateChannel?: string };
  /** The server the config names now, for the message. */
  realServer(): string;
  now(): Date;
}

export interface PreviewUseOptions {
  acceptFormatChange?: boolean;
  /** Where the replaced CLI is kept; tests pass a scratch path. */
  keptPath?: string;
}

/**
 * The D11 text, one source for `use`, the banner and the expiry guidance. `server` is the real server
 * `leave` returns to.
 */
export function previewExpiryMessage(
  overlay: Pick<PreviewOverlay, 'name' | 'licenceEndsAt'>,
  server: string
): string {
  return t('commands.preview.msg.expiryMessage', {
    name: overlay.name,
    date: formatDate(overlay.licenceEndsAt),
    server,
  });
}

function formatDate(iso: string | undefined): string {
  return iso ? iso.slice(0, 10) : '?';
}

/**
 * Every check of `use`, none of which changes a file or the config: the preview server's build, the release
 * manifest, the two sha256s agreeing, and the typed confirmation of an on-disk format change.
 */
async function checkPreviewBuild(
  name: string,
  options: PreviewUseOptions,
  deps: PreviewUseDeps,
  platform: PlatformKey
): Promise<{ host: string; build: PreviewBuild; binary: PreviewBinary }> {
  const host = previewHostFor(name);
  const info = await deps.fetchServerInfo(host);
  const build = parsePreviewBuild(info.previewBuild, name);
  const binary = selectPreviewBinary(await deps.fetchManifest(name), build, platform, name);

  if (build.formatChange && options.acceptFormatChange !== true) {
    outputService.warn(
      t('commands.preview.msg.formatChange', {
        formats: build.formatChange.formats.join(', '),
        reason: build.formatChange.reason,
      })
    );
    if (!(await deps.confirmFormatChange(build.formatChange))) {
      throw new ValidationError(t('errors.preview.formatChangeDeclined', { name }));
    }
  }
  return { host, build, binary };
}

/**
 * Switch the config to preview `name`. Every check (the server's build, the manifest, the two hashes, the
 * format-change confirmation) runs before any file or the config changes. The state is written before the
 * binary is replaced, and removed again when the install fails, so a failed `use` leaves the config as it
 * was.
 */
export async function switchToPreview(
  name: string,
  options: PreviewUseOptions,
  deps: PreviewUseDeps,
  configName?: string
): Promise<PreviewOverlay> {
  const existing = readPreviewOverlay(configName);
  if (existing) {
    throw new ValidationError(t('errors.preview.alreadyActive', { name: existing.name }));
  }
  if (!deps.canReplaceBinary()) {
    throw new ValidationError(t('errors.preview.notSea'));
  }
  const platform = deps.platformKey();
  if (!platform) throw new ValidationError(t('errors.preview.unsupportedPlatform'));

  const { host, build, binary } = await checkPreviewBuild(name, options, deps, platform);

  const keptPath = options.keptPath ?? previewKeptBinaryPath();
  const kept = await deps.keepCurrentBinary(keptPath);
  const now = deps.now();
  const server = deps.realServer();
  const current = deps.current();
  const overlay = await enterPreview(
    {
      name,
      host,
      enteredAt: now.toISOString(),
      channel: name,
      licenceEndsAt: new Date(now.getTime() + PREVIEW_LICENCE_DAYS * 86_400_000).toISOString(),
      ...(build.formatChange ? { formatChange: build.formatChange } : {}),
      previous: {
        cliVersion: current.version,
        cliSha256: kept.sha256,
        binaryPath: kept.installPath,
        ...(current.updateChannel ? { updateChannel: current.updateChannel } : {}),
      },
    },
    configName
  );

  try {
    await deps.installBinary(binary);
  } catch (error) {
    await leavePreview(configName);
    throw error;
  }

  outputService.success(t('commands.preview.msg.useDone', { name, version: binary.version }));
  outputService.info(previewExpiryMessage(overlay, server));
  outputService.info(
    t('commands.preview.msg.emergencyExit', { command: emergencyLeaveCommand(keptPath) })
  );
  return overlay;
}

/** What switching one server's renet back did (C3). */
export interface SwitchBackResult {
  status: 'switched' | 'unreachable';
  detail?: string;
}

export interface PreviewLeaveDeps {
  confirm(message: string): Promise<boolean>;
  /** The renet version a touched server runs now; `null` when it cannot be reached. */
  currentRenetVersion(machine: string): Promise<string | null>;
  switchBack(
    machine: string,
    entry: NonNullable<PreviewOverlay['touched']>[string]
  ): Promise<SwitchBackResult>;
  /** The latest manifest of the channel the CLI was on before `use`; the preview channel is never read. */
  fetchPreviousManifest(channel: string | undefined): Promise<UpdateManifest>;
  platformKey(): PlatformKey | null;
  /** Install `binary` over `targetPath`, forced: its version may be lower than the preview's. */
  installBinaryAt(targetPath: string | undefined, binary: PreviewBinary): Promise<void>;
  /** Put the kept copy back over `targetPath` when its sha256 still equals `sha256`; throws otherwise. */
  restoreKeptCopy(targetPath: string | undefined, sha256: string): Promise<void>;
  /** C4: delete the preview-key licence files of the switched servers and re-license from the real account. */
  relicense(machines: string[]): Promise<void>;
  realServer(): string;
}

export interface PreviewLeaveResult {
  /** Whether the overlay is gone. */
  left: boolean;
  /** Machines whose renet was switched back in this run. */
  switched: string[];
  /** Machines still on the preview renet. */
  remaining: string[];
}

/**
 * Leave the preview. The touched-server list is shown and confirmed before anything moves; each server is
 * switched back and dropped from the list on success; an unreachable server stays listed and keeps the
 * overlay alive (`--machine` finishes it later). With the list empty the overlay and the preview token go,
 * the binary is restored (the previous channel's latest, else the kept copy), and the switched servers are
 * re-licensed from the real account. It never contacts the preview host or channel.
 */
export async function leavePreviewFlow(
  options: { machine?: string },
  deps: PreviewLeaveDeps,
  configName?: string
): Promise<PreviewLeaveResult> {
  const overlay = readPreviewOverlay(configName);
  if (!overlay) {
    outputService.info(t('commands.preview.msg.notActive'));
    return { left: false, switched: [], remaining: [] };
  }
  const selected = selectTouched(overlay, options.machine);

  const switched =
    selected.length > 0 ? await switchBackSelected(selected, overlay, deps, configName) : [];

  const after = readPreviewOverlay(configName);
  const remaining = Object.keys(after?.touched ?? {});
  if (remaining.length > 0) {
    outputService.warn(
      t('commands.preview.msg.leavePending', { machines: remaining.join(', '), name: overlay.name })
    );
    return { left: false, switched, remaining };
  }

  const server = deps.realServer();
  await leavePreview(configName);
  const restored = await restoreBinary(overlay, deps);
  // Re-licensing runs the restored CLI, so a binary that could not be restored leaves it to the operator.
  if (switched.length > 0 && restored) await deps.relicense(switched);
  outputService.success(t('commands.preview.msg.leaveDone', { name: overlay.name, server }));
  return { left: true, switched, remaining: [] };
}

type TouchedEntry = [string, NonNullable<PreviewOverlay['touched']>[string]];

/** The touched servers a run acts on: all of them, or the one `--machine` names, which must be listed. */
function selectTouched(overlay: PreviewOverlay, machine: string | undefined): TouchedEntry[] {
  const listed = Object.entries(overlay.touched ?? {});
  if (machine === undefined) return listed;
  const selected = listed.filter(([m]) => m === machine);
  if (selected.length === 0) {
    throw new ValidationError(
      t('errors.preview.machineNotTouched', { machine, name: overlay.name })
    );
  }
  return selected;
}

/** Confirm the list, then switch each server back; the ones that succeed leave the touched list, the others stay on it. */
async function switchBackSelected(
  selected: TouchedEntry[],
  overlay: PreviewOverlay,
  deps: PreviewLeaveDeps,
  configName: string | undefined
): Promise<string[]> {
  await confirmTouched(selected, overlay, deps);
  const switched: string[] = [];
  for (const [machine, entry] of selected) {
    const result = await deps.switchBack(machine, entry);
    if (result.status === 'switched') {
      await clearPreviewTouch(machine, configName);
      switched.push(machine);
      outputService.success(
        t('commands.preview.msg.switchedBack', { machine, version: entry.version })
      );
    } else {
      outputService.warn(
        t('commands.preview.msg.unreachable', {
          machine,
          detail: result.detail ?? '',
          name: overlay.name,
        })
      );
    }
  }
  return switched;
}

async function confirmTouched(
  selected: TouchedEntry[],
  overlay: PreviewOverlay,
  deps: PreviewLeaveDeps
): Promise<void> {
  const lines: string[] = [];
  for (const [machine, entry] of selected) {
    const now = await deps.currentRenetVersion(machine);
    lines.push(
      t('commands.preview.msg.touchedLine', {
        machine,
        recorded: entry.version,
        current: now ?? t('commands.preview.msg.unreachableVersion'),
      })
    );
  }
  outputService.info(
    [t('commands.preview.msg.touchedHeader', { name: overlay.name }), ...lines].join('\n')
  );
  if (
    !(await deps.confirm(t('commands.preview.msg.confirmSwitchBack', { count: selected.length })))
  ) {
    throw new ValidationError(t('errors.preview.leaveDeclined', { name: overlay.name }));
  }
}

/**
 * The CLI the config had before `use`: the previous channel's latest (forced), or the kept copy when that
 * channel is unreachable or has no usable binary. A failure of both is a loud warning naming the kept
 * copy, never a silent success.
 */
async function restoreBinary(overlay: PreviewOverlay, deps: PreviewLeaveDeps): Promise<boolean> {
  const target = overlay.previous.binaryPath;
  const fromChannel = await restoreFromChannel(overlay, deps);
  if (fromChannel.ok) return true;
  try {
    await deps.restoreKeptCopy(target, overlay.previous.cliSha256);
    outputService.info(
      t('commands.preview.msg.binaryRestoredFromCopy', {
        version: overlay.previous.cliVersion,
        reason: fromChannel.reason,
      })
    );
    return true;
  } catch (error) {
    outputService.warn(
      t('commands.preview.msg.binaryNotRestored', {
        channel: fromChannel.reason,
        copy: error instanceof Error ? error.message : String(error),
        path: previewKeptBinaryPath(),
      })
    );
    return false;
  }
}

/** Install the previous channel's latest build, forced; a failure is a reason, not a throw, so the kept copy gets its turn. */
async function restoreFromChannel(
  overlay: PreviewOverlay,
  deps: PreviewLeaveDeps
): Promise<{ ok: true } | { ok: false; reason: string }> {
  try {
    const platform = deps.platformKey();
    if (!platform) throw new Error(t('errors.preview.unsupportedPlatform'));
    const manifest = await deps.fetchPreviousManifest(overlay.previous.updateChannel);
    const entry = manifest.binaries[platform];
    if (!entry?.sha256) {
      throw new Error(t('errors.preview.noBinary', { name: 'previous', platform }));
    }
    await deps.installBinaryAt(overlay.previous.binaryPath, {
      version: manifest.version,
      sha256: entry.sha256,
      url: entry.url,
    });
    outputService.success(t('commands.preview.msg.binaryRestored', { version: manifest.version }));
    return { ok: true };
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : String(error) };
  }
}

/** The status block: the preview, its licence end, the touched servers and the way back. */
export function previewStatusLines(
  overlay: PreviewOverlay,
  server: string,
  keptPath = previewKeptBinaryPath()
): string[] {
  const lines = [
    t('commands.preview.msg.statusName', { name: overlay.name, host: overlay.host }),
    t('commands.preview.msg.statusSince', {
      date: formatDate(overlay.enteredAt),
      end: formatDate(overlay.licenceEndsAt),
    }),
    t('commands.preview.msg.statusPrevious', {
      version: overlay.previous.cliVersion,
      server,
    }),
  ];
  const touched = Object.entries(overlay.touched ?? {});
  if (touched.length === 0) lines.push(t('commands.preview.msg.statusNoServers'));
  else {
    lines.push(t('commands.preview.msg.statusServers', { count: touched.length }));
    for (const [machine, entry] of touched) {
      lines.push(
        t('commands.preview.msg.statusServer', {
          machine,
          version: entry.version,
          slot: entry.slot,
        })
      );
    }
  }
  if (overlay.formatChange) {
    lines.push(
      t('commands.preview.msg.formatChange', {
        formats: overlay.formatChange.formats.join(', '),
        reason: overlay.formatChange.reason,
      })
    );
  }
  lines.push(t('commands.preview.msg.emergencyExit', { command: emergencyLeaveCommand(keptPath) }));
  return lines;
}

/**
 * The one-line banner every command prints while a preview is active (D8): the preview, the licence end
 * date and `rdc preview leave`. With fewer than {@link BANNER_WARN_DAYS} days left it adds the D11 text.
 * `undefined` outside a preview.
 */
export function previewBanner(
  overlay: PreviewOverlay | undefined,
  server: string,
  now: Date = new Date()
): string | undefined {
  if (!overlay) return undefined;
  const line = t('commands.preview.msg.banner', {
    name: overlay.name,
    date: formatDate(overlay.licenceEndsAt),
  });
  const end = overlay.licenceEndsAt ? Date.parse(overlay.licenceEndsAt) : Number.NaN;
  if (!Number.isNaN(end) && end - now.getTime() < BANNER_WARN_DAYS * 86_400_000) {
    return `${line}\n${previewExpiryMessage(overlay, server)}`;
  }
  return line;
}
