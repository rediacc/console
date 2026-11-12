/**
 * `rdc server status|backup|upgrade|licence`, each against an installed domain.
 */

import { delegationCertId } from '@rediacc/shared/subscription';
import { t } from '../../i18n/index.js';
import { outputService } from '../core/output.js';
import { locateRepo, rdcMust, readBundle, readPublicFacts, ServerError, setBoxEnv } from './box.js';
import { decodeCert } from './cert.js';
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
import {
  awaitInboxResult,
  confirmCertId,
  dropCert,
  migrateEnvCert,
  obtainLicence,
  readBootRejected,
  readLiveCert,
} from './licence.js';
import { recordFile } from './state.js';
import type { ServerDeps } from './types.js';

const DEFAULT_TIER = 'licensed';
/** The boot-refusal reason a new cert cannot fix: the box has no key to check certs by. */
const NO_UPSTREAM_KEY = 'no-upstream-key';

export interface StatusResult {
  domain: string;
  machine: string;
  repo: string;
  health: number;
  certificateCoversDomain: boolean;
  tier: string;
  bootstrapMode: boolean;
  /** The live cert's id (`delegationCertId`), as `GET /onprem/cert-status` reports it. */
  certId?: string;
  subscriptionId?: string;
  planCode?: string;
  certIssuedAt?: string;
  certValidUntil?: string;
  freeTierRelay?: boolean;
  /** Set when the box refused its cert at boot: it runs on the free tier and holds no live cert. */
  certRefused?: { reason: string; detail: string; at: string };
  image?: string;
  templateVersion: number;
  builtinTemplateVersion: number;
}

/** Reads only: the box's public facts, its live cert file, one health answer and the free-tier relay. */
export async function serverStatus(deps: ServerDeps, loc: Locator): Promise<StatusResult> {
  const record = requireRecord(loc);
  const where = await locateRepo(record.repo, record.machine);
  const facts = await readPublicFacts(deps, where);
  const refused = await readBootRejected(deps, where);
  const live = refused ? undefined : await readLiveCert(deps, where);
  const cert = live?.decoded;
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
    ...(live && cert
      ? {
          certId: live.certId,
          subscriptionId: cert.subscriptionId,
          planCode: cert.planCode,
          certIssuedAt: cert.issuedAt,
          certValidUntil: cert.validUntil,
        }
      : {}),
    ...(refused
      ? { certRefused: { reason: refused.reason, detail: refused.detail, at: refused.at } }
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
  // One-time move off DELEGATION_CERT_BASE64, which the server no longer reads: its cert goes into
  // the inbox before the restart and the boot decides it. Delete this (and MIGRATE_ENV_CERT) once
  // no deployed box predates template VERSION 4.
  const migrated = await migrateEnvCert(deps, where);
  if (migrated) outputService.info(t('commands.server.upgrade.migratingCert'));
  await rdcMust(deps, ['repo', 'up', repoRef]);
  await waitHealthy(deps, await boxTarget(deps, record));
  if (migrated) await awaitInboxResult(deps, where, migrated.requestId);
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
  /** The applied cert's id (`delegationCertId`). */
  certId: string;
  /** `inbox`: the server took the cert through its cert inbox; `already-current`: it already held it. */
  via: 'inbox' | 'already-current';
}

/**
 * From the free tier to a cert, or to a newer one: the logged-in config mints one for the box's key
 * (or `--cert` brings it), it goes into the box's cert inbox, and the running server validates and
 * applies it. Success needs the server's `applied.json` for this request and then the owner's
 * `GET /onprem/cert-status` reporting the new cert's id. Nothing restarts, and secrets.env only
 * takes the auto-renew settings.
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

  const refused = await readBootRejected(deps, where);
  if (refused?.reason === NO_UPSTREAM_KEY) {
    throw new ServerError(t('commands.server.licence.noUpstreamKey', { domain: record.domain }));
  }
  if (refused) {
    outputService.warn(
      t('commands.server.licence.bootRefused', { reason: refused.reason, detail: refused.detail })
    );
  }
  const live = await readLiveCert(deps, where);
  const result = await obtainLicence(deps, {
    mode: 'auto',
    certFile,
    boxPublicKey: boxKey,
    interactive: false,
  });
  if (result.kind !== 'cert') {
    throw new ServerError(t('commands.server.licence.noCertForUpgrade'));
  }
  const tier = (cert: { planCode?: string } | undefined) => cert?.planCode ?? DEFAULT_TIER;

  const certId = await delegationCertId(result.signed);
  if (!refused && live?.certId === certId) {
    outputService.info(t('commands.server.licence.alreadyCurrent', { certId }));
    return {
      domain: record.domain,
      subscriptionId: result.subscriptionId,
      tier: tier(live.decoded),
      certId,
      via: 'already-current',
    };
  }

  const drop = await dropCert(deps, where, result.signed);
  outputService.info(t('commands.server.licence.droppedCert', { certId: drop.certId }));
  await awaitInboxResult(deps, where, drop.requestId);
  await confirmCertId(deps, await boxTarget(deps, record), record.domain, drop.certId);
  if (refused) {
    const still = await readBootRejected(deps, where);
    if (still) {
      throw new ServerError(
        t('commands.server.licence.bootRefusalStays', { reason: still.reason })
      );
    }
  }
  if (Object.keys(result.env).length > 0) await setBoxEnv(deps, where, result.env);
  outputService.info(t('commands.server.licence.viaInbox'));

  const stored = { ...record, licence: 'cert' as const, subscriptionId: result.subscriptionId };
  await deps.writePrivate(recordFile(record.domain), `${JSON.stringify(stored, null, 2)}\n`);
  return {
    domain: record.domain,
    subscriptionId: result.subscriptionId,
    tier: tier(decodeCert(result.signed)),
    certId: drop.certId,
    via: 'inbox',
  };
}
