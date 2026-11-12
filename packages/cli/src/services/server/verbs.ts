/**
 * `rdc server status|backup|upgrade|licence`, each against an installed domain.
 */

import { t } from '../../i18n/index.js';
import { outputService } from '../core/output.js';
import { locateRepo, rdcMust, readBundle, readPublicFacts, ServerError, setBoxEnv } from './box.js';
import { decodeCertBase64 } from './cert.js';
import {
  boxTarget,
  builtinTemplateVersion,
  DEFAULT_IMAGE,
  imageTag,
  type Locator,
  placeImage,
  requireRecord,
  TEMPLATE_NAME,
} from './common.js';
import { covers, probeFreeTier, waitHealthy } from './http.js';
import { obtainLicence } from './licence.js';
import { recordFile } from './state.js';
import type { ServerDeps } from './types.js';

export interface StatusResult {
  domain: string;
  machine: string;
  repo: string;
  health: number;
  certificateCoversDomain: boolean;
  tier: string;
  bootstrapMode: boolean;
  subscriptionId?: string;
  planCode?: string;
  certValidUntil?: string;
  freeTierRelay?: boolean;
  image?: string;
  templateVersion: number;
  builtinTemplateVersion: number;
}

/** Reads only: the box's public facts, one health answer and the free-tier relay. */
export async function serverStatus(deps: ServerDeps, loc: Locator): Promise<StatusResult> {
  const record = requireRecord(loc);
  const where = await locateRepo(record.repo, record.machine);
  const facts = await readPublicFacts(deps, where);
  const cert = decodeCertBase64(facts.values.DELEGATION_CERT_BASE64);
  const target = await boxTarget(deps, record);
  const health = await deps.box(target, 'GET', '/health');
  const relay = health.status === 200 ? await probeFreeTier(deps, target) : undefined;
  return {
    domain: record.domain,
    machine: record.machine,
    repo: record.repo,
    health: health.status,
    certificateCoversDomain: covers(health.sans, record.domain),
    tier: cert ? cert.planCode : 'free',
    bootstrapMode: !cert,
    ...(cert
      ? {
          subscriptionId: cert.subscriptionId,
          planCode: cert.planCode,
          certValidUntil: cert.validUntil,
        }
      : {}),
    ...(relay === undefined ? {} : { freeTierRelay: relay }),
    ...(facts.values.ELITE_IMAGE ? { image: facts.values.ELITE_IMAGE } : {}),
    templateVersion: facts.templateVersion,
    builtinTemplateVersion: builtinTemplateVersion(),
  };
}

/** The recovery bundle, streamed to stdout or written to `out` at 0600. */
export async function serverBackup(deps: ServerDeps, loc: Locator, out?: string): Promise<void> {
  const record = requireRecord(loc);
  const where = await locateRepo(record.repo, record.machine);
  const bundle = await readBundle(deps, where, record.domain);
  if (out) {
    await deps.writePrivate(out, bundle);
    outputService.success(t('commands.server.backup.written', { file: out }));
    return;
  }
  deps.stdout(bundle);
}

export interface UpgradeOptions {
  image?: string;
  imageFile?: string;
  localImage?: boolean;
}

export interface UpgradeResult {
  domain: string;
  rollback: string;
  image: string;
  templateReapplied: boolean;
  templateVersion: number;
}

function stamp(now: number): string {
  return new Date(now)
    .toISOString()
    .replace(/[-:]/g, '')
    .replace(/\.\d+Z$/, '')
    .toLowerCase();
}

/**
 * Fork first (the rollback point), then the new image, the template again only when the built-in
 * one is newer than the deployed `VERSION`, the image ref, and `repo up`.
 */
export async function serverUpgrade(
  deps: ServerDeps,
  loc: Locator,
  opts: UpgradeOptions
): Promise<UpgradeResult> {
  const record = requireRecord(loc);
  const where = await locateRepo(record.repo, record.machine);
  const repoRef = `${record.repo}@${record.machine}`;
  const facts = await readPublicFacts(deps, where);

  const tag = `pre-upgrade-${stamp(deps.now())}`;
  outputService.info(t('commands.server.upgrade.forking', { tag }));
  await rdcMust(deps, ['repo', 'fork', repoRef, '--tag', tag]);

  const image = opts.image ?? facts.values.ELITE_IMAGE ?? record.image ?? DEFAULT_IMAGE;
  await placeImage(deps, where, image, opts.imageFile, opts.localImage);

  const builtin = builtinTemplateVersion();
  const reapply = builtin > facts.templateVersion;
  if (reapply) {
    outputService.info(
      t('commands.server.upgrade.template', { from: facts.templateVersion, to: builtin })
    );
    await rdcMust(deps, [
      'repo',
      'admin',
      'template',
      'apply',
      repoRef,
      '--template',
      TEMPLATE_NAME,
    ]);
  } else {
    outputService.info(
      t('commands.server.upgrade.templateCurrent', { version: facts.templateVersion })
    );
  }

  await setBoxEnv(deps, where, { ELITE_IMAGE: image, TAG: imageTag(image) });
  await rdcMust(deps, ['repo', 'up', repoRef]);
  await waitHealthy(deps, await boxTarget(deps, record));
  return {
    domain: record.domain,
    rollback: `${record.repo}:${tag}`,
    image,
    templateReapplied: reapply,
    templateVersion: reapply ? builtin : facts.templateVersion,
  };
}

export interface LicenceUpgradeResult {
  domain: string;
  subscriptionId: string;
  tier: string;
}

/**
 * From the free tier to a cert: the logged-in config mints one for the box's key (or `--cert`
 * brings it), it goes into secrets.env, and `repo up` restarts the server, which adopts it at boot.
 */
export async function serverLicence(
  deps: ServerDeps,
  loc: Locator,
  certFile?: string
): Promise<LicenceUpgradeResult> {
  const record = requireRecord(loc);
  const where = await locateRepo(record.repo, record.machine);
  const facts = await readPublicFacts(deps, where);
  const boxKey = facts.values.ACCOUNT_ED25519_PUBLIC_KEY;
  if (!boxKey) throw new ServerError(t('commands.server.errors.keygenNoKey'));

  const result = await obtainLicence(deps, {
    mode: 'auto',
    certFile,
    boxPublicKey: boxKey,
    interactive: false,
  });
  if (result.kind !== 'cert') {
    throw new ServerError(t('commands.server.licence.noCertForUpgrade'));
  }
  await setBoxEnv(deps, where, result.env);
  await rdcMust(deps, ['repo', 'up', `${record.repo}@${record.machine}`]);
  const target = await boxTarget(deps, record);
  await waitHealthy(deps, target);
  if ((await probeFreeTier(deps, target)) === true) {
    throw new ServerError(t('commands.server.licence.stillFree', { domain: record.domain }));
  }
  const stored = { ...record, licence: 'cert' as const, subscriptionId: result.subscriptionId };
  await deps.writePrivate(recordFile(record.domain), `${JSON.stringify(stored, null, 2)}\n`);
  const cert = decodeCertBase64(result.env.DELEGATION_CERT_BASE64);
  return {
    domain: record.domain,
    subscriptionId: result.subscriptionId,
    tier: cert?.planCode ?? 'licensed',
  };
}
