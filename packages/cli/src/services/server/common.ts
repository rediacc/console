/**
 * What every `rdc server` verb after `install` shares: finding the box by its domain, the image
 * step, and the built-in template's version.
 */

import { isIPv4 } from 'node:net';
import { join } from 'node:path';
import { WK_IMAGE_REGISTRY } from '@rediacc/shared/config/well-known.generated';
import { t } from '../../i18n/index.js';
import { type EmbeddedTemplate, TEMPLATES } from '../../templates/embedded.generated.js';
import type { MachineConfig } from '../../types/index.js';
import { outputService } from '../core/output.js';
import { type RepoOnBox, rdcMust, ServerError } from './box.js';
import { PULL_IMAGE, shCommand } from './box-scripts.js';
import { loadRecord, type ServerRecord } from './state.js';
import type { BoxTarget, ServerDeps } from './types.js';

export const TEMPLATE_NAME = 'elite';
export const DEFAULT_REPO = 'elite';
export const DEFAULT_SIZE = '10G';
export const DEFAULT_IMAGE = `${WK_IMAGE_REGISTRY}/server:latest`;

/** `acme.example.com` -> `acme-store.example.com`. */
export function storeDomainOf(domain: string): string {
  const dot = domain.indexOf('.');
  return dot < 0 ? `${domain}-store` : `${domain.slice(0, dot)}-store${domain.slice(dot)}`;
}

/** The tag of an image ref, `latest` when it names none. */
export function imageTag(ref: string): string {
  const name = ref.slice(ref.lastIndexOf('/') + 1);
  if (name.includes('@')) return 'latest';
  const colon = name.lastIndexOf(':');
  return colon < 0 ? 'latest' : name.slice(colon + 1);
}

/** The built-in template's `VERSION`; 0 while the template ships none. */
export function builtinTemplateVersion(): number {
  const templates: Partial<Record<string, EmbeddedTemplate>> = TEMPLATES;
  const files: Partial<Record<string, string>> = templates[TEMPLATE_NAME]?.files ?? {};
  const raw = files.VERSION ?? '';
  const n = Number.parseInt(raw.trim(), 10);
  return Number.isFinite(n) ? n : 0;
}

/** The addresses the public names must resolve to: the infra block's, else the SSH address when it is an IP. */
export function machineAddresses(machine: MachineConfig): string[] {
  const out: string[] = [];
  const v4 = machine.infra?.publicIPv4 ?? (isIPv4(machine.ip) ? machine.ip : undefined);
  if (v4) out.push(v4);
  if (machine.infra?.publicIPv6) out.push(machine.infra.publicIPv6);
  return out;
}

export interface Locator {
  domain: string;
  machine?: string;
  repo?: string;
}

/** The install record of a domain; `--machine`/`--repo` stand in on a device that did not install it. */
export function requireRecord(loc: Locator): ServerRecord {
  const record = loadRecord(loc.domain);
  if (record) {
    return {
      ...record,
      machine: loc.machine ?? record.machine,
      repo: loc.repo ?? record.repo,
    };
  }
  if (loc.machine) {
    return {
      domain: loc.domain,
      storeDomain: storeDomainOf(loc.domain),
      machine: loc.machine,
      repo: loc.repo ?? DEFAULT_REPO,
      steps: {},
    };
  }
  throw new ServerError(t('commands.server.errors.noRecord', { domain: loc.domain }));
}

export async function boxTarget(
  deps: ServerDeps,
  record: Pick<ServerRecord, 'domain' | 'tlsCa'>,
  address?: string
): Promise<BoxTarget> {
  const ca = record.tlsCa ? await deps.readFile(record.tlsCa) : undefined;
  return { domain: record.domain, ...(address ? { address } : {}), ...(ca ? { ca } : {}) };
}

/**
 * Put the image on the box: ship a saved tar into the repo's `images/` (the Rediaccfile loads it),
 * `docker save` a locally built image and ship that (`--local-image`), or pull the ref inside the repo's own Docker daemon. compose's `pull_policy: never` means nothing
 * pulls it otherwise.
 */
export async function placeImage(
  deps: ServerDeps,
  where: RepoOnBox,
  ref: string,
  imageFile?: string,
  localImage?: boolean
): Promise<void> {
  const repoRef = `${where.repo}@${where.machine}`;
  if (localImage && !imageFile) {
    const tar = join(await deps.tempDir(), 'server.tar');
    outputService.info(t('commands.server.image.saving', { image: ref }));
    if ((await deps.local('docker', ['save', '-o', tar, ref])) !== 0) {
      throw new ServerError(t('commands.server.image.saveFailed', { image: ref }));
    }
    imageFile = tar;
  }
  if (imageFile) {
    await rdcMust(deps, [
      'repo',
      'sync',
      'upload',
      repoRef,
      '--local',
      imageFile,
      '--remote-file',
      'images/server.tar',
      '--verify',
    ]);
    return;
  }
  if (!where.dockerSocket) {
    throw new ServerError(t('commands.server.errors.noDaemon', { repo: where.repo }));
  }
  outputService.info(t('commands.server.image.pulling', { image: ref }));
  const result = await deps.ssh(where.machine, shCommand(PULL_IMAGE, [where.dockerSocket, ref]));
  if (result.code !== 0) {
    throw new ServerError(
      t('commands.server.image.pullFailed', {
        image: ref,
        detail: result.stderr.trim().split('\n').at(-1) ?? '',
      })
    );
  }
}
