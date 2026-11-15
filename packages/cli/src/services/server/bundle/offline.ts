/**
 * The air-gapped halves of `rdc server install --offline --bundle <dir>` and `rdc server upgrade
 * --bundle <dir>`: the options an offline box cannot honour, the preflight beyond the online one,
 * the proxy image, the repo's images, and the two-trip licence (a request out, a cert back).
 */

import { join } from 'node:path';
import { t } from '../../../i18n/index.js';
import { ValidationError } from '../../../utils/errors.js';
import { outputService } from '../../core/output.js';
import { type RepoOnBox, rdcMust, ServerError } from '../box.js';
import { parseEnvLines, shCommand } from '../box-scripts.js';
import { OFFLINE_ESSENTIALS, PROXY_IMAGE_LOAD, PROXY_IMAGE_PROBE } from '../box-scripts-offline.js';
import { assertCertKey, CertError, certToBase64, decodeCert, parseSignedCert } from '../cert.js';
import type { InstallOptions } from '../install-options.js';
import type { PreflightFacts } from '../preflight.js';
import { requestFile } from '../state.js';
import type { IssueOutcome, ServerDeps } from '../types.js';
import { TRAEFIK_REF } from './images.js';
import { BundleError, type BundleManifest } from './manifest.js';

const REQUEST_SCHEMA = 1;

/** The uname machine names a bundle's renet arch covers. */
const ARCH_OF: Record<string, 'amd64' | 'arm64'> = {
  x86_64: 'amd64',
  amd64: 'amd64',
  aarch64: 'arm64',
  arm64: 'arm64',
};

/** Raised when the install stops at the licence step to wait for a cert carried back. */
export class AwaitingCert extends ServerError {}

/** What an air-gapped install refuses up front: anything that needs the internet, or contradicts the bundle. */
export function offlineOptionProblems(opts: InstallOptions): string[] {
  const problems: string[] = [];
  if (!opts.bundle) problems.push(t('commands.server.offline.needsBundle'));
  if (opts.licence === 'free') problems.push(t('commands.server.offline.noFree'));
  if (opts.tls !== undefined && opts.tls !== 'byo') {
    problems.push(t('commands.server.offline.tlsByoOnly', { tls: opts.tls }));
  }
  if (opts.cfToken) problems.push(t('commands.server.offline.noCfToken'));
  if (opts.bwsProject) problems.push(t('commands.server.offline.noBws'));
  if (opts.image || opts.imageFile || opts.localImage) {
    problems.push(t('commands.server.offline.imageFromBundle'));
  }
  return problems;
}

export function assertOfflineOptions(opts: InstallOptions): void {
  if (!opts.offline) {
    if (opts.bundle) throw new ValidationError(t('commands.server.offline.bundleNeedsOffline'));
    return;
  }
  const problems = offlineOptionProblems(opts);
  if (problems.length > 0) throw new ValidationError(problems.join('\n  '));
}

/** The refusals beyond the online preflight: the bundle's arch must be the box's, and the tools renet's offline setup assumes must be there. */
export async function offlinePreflight(
  deps: ServerDeps,
  machine: string,
  facts: Pick<PreflightFacts, 'arch'>,
  manifest: BundleManifest
): Promise<void> {
  const problems: string[] = [];
  const boxArch = ARCH_OF[facts.arch];
  if (boxArch !== manifest.renet.arch) {
    problems.push(
      t('commands.server.offline.archMismatch', { box: facts.arch, bundle: manifest.renet.arch })
    );
  }
  const probe = await deps.ssh(machine, shCommand(OFFLINE_ESSENTIALS, [], false));
  if (probe.code !== 0) {
    throw new ServerError(t('commands.server.preflight.noAnswer', { machine }));
  }
  const missing = (parseEnvLines(probe.stdout).missing ?? '').trim();
  if (missing) problems.push(t('commands.server.offline.missingEssentials', { missing }));
  if (problems.length > 0) {
    throw new ServerError(
      [t('commands.server.preflight.refused', { machine }), ...problems].join('\n  ')
    );
  }
}

/** Load the proxy image into the machine's Docker when it does not hold it, before `renet` converges the proxy. */
export async function loadProxyImage(
  deps: ServerDeps,
  machine: string,
  dir: string,
  manifest: BundleManifest
): Promise<void> {
  const entry = manifest.images.find((i) => i.ref === TRAEFIK_REF);
  if (!entry)
    throw new BundleError(t('commands.server.offline.noProxyImage', { ref: TRAEFIK_REF }));
  const probe = await deps.ssh(machine, shCommand(PROXY_IMAGE_PROBE, [entry.ref]));
  if (parseEnvLines(probe.stdout).traefik === 'present') return;
  outputService.info(t('commands.server.offline.loadingProxy', { image: entry.ref }));
  const remote = `/tmp/rdc-${deps.now()}-traefik.tar`;
  await deps.uploadFile(machine, join(dir, entry.file), remote);
  const loaded = await deps.ssh(machine, shCommand(PROXY_IMAGE_LOAD, [remote]));
  if (loaded.code !== 0) {
    throw new ServerError(
      t('commands.server.offline.loadFailed', {
        image: entry.ref,
        detail: loaded.stderr.trim().split('\n').at(-1) ?? '',
      })
    );
  }
}

/** Ship the server and RustFS tars and their `manifest.txt` into the repo's `images/`, where `up()` loads them. */
export async function uploadBundleImages(
  deps: ServerDeps,
  where: RepoOnBox,
  dir: string
): Promise<void> {
  const repoRef = `${where.repo}@${where.machine}`;
  for (const name of ['server.tar', 'rustfs.tar', 'manifest.txt']) {
    await rdcMust(deps, [
      'repo',
      'sync',
      'upload',
      repoRef,
      '--local',
      join(dir, 'images', name),
      '--remote-file',
      `images/${name}`,
      '--verify',
    ]);
  }
}

/** The request an online machine or the portal turns into a cert: the box's public key and the domain it serves. */
export async function writeCertRequest(
  deps: ServerDeps,
  domain: string,
  publicKey: string
): Promise<string> {
  const file = requestFile(domain);
  const body = {
    schema: REQUEST_SCHEMA,
    domain,
    delegatedPublicKey: publicKey,
    createdAt: new Date(deps.now()).toISOString(),
  };
  await deps.writePrivate(file, `${JSON.stringify(body, null, 2)}\n`);
  return file;
}

function mintRefusal(outcome: Exclude<IssueOutcome, { kind: 'issued' }>): string {
  switch (outcome.kind) {
    case 'no-login':
      return t('commands.server.offline.mintNoLogin');
    case 'missing-scope':
      return t('commands.server.licence.missingScope');
    case 'plan-disallows':
      return t('commands.server.licence.planDisallows', { error: outcome.message });
    case 'other-key':
      return t('commands.server.licence.otherKey', {
        certId: outcome.certId,
        error: outcome.message,
      });
  }
}

/** `rdc server licence mint --request <f> --out <f>`, run online: the request's key becomes a signed cert file `--cert` accepts. */
export async function licenceMint(
  deps: ServerDeps,
  requestPath: string,
  out: string
): Promise<{ subscriptionId: string; validUntil: string }> {
  let key = '';
  try {
    const raw = JSON.parse(await deps.readFile(requestPath)) as Record<string, unknown>;
    if (raw.schema !== REQUEST_SCHEMA || typeof raw.delegatedPublicKey !== 'string') {
      throw new Error('shape');
    }
    key = raw.delegatedPublicKey;
  } catch {
    throw new ServerError(t('commands.server.offline.requestInvalid', { file: requestPath }));
  }
  const outcome = await deps.issueCert(key);
  if (outcome.kind !== 'issued') {
    throw new ServerError(mintRefusal(outcome));
  }
  const signed = parseSignedCert(outcome.cert.certBase64);
  const payload = decodeCert(signed);
  try {
    assertCertKey(payload, key);
  } catch (error) {
    if (error instanceof CertError) {
      throw new ServerError(t('commands.server.licence.issuedKeyMismatch'));
    }
    throw error;
  }
  const json = Buffer.from(certToBase64(signed), 'base64').toString('utf-8');
  await deps.writePrivate(out, `${json}\n`);
  return { subscriptionId: payload.subscriptionId, validUntil: payload.validUntil };
}
