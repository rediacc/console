/**
 * The TLS step (R7). Certificates are per host, never a wildcard.
 *
 *   letsencrypt  renet's default resolver answers HTTP-01 when the machine has no Cloudflare token.
 *   cloudflare   DNS-01 through the machine's infra token (`machine infra set --cf-dns-token`).
 *   byo          the operator's own pair, installed per host by `renet proxy cert install`.
 */

import { t } from '../../i18n/index.js';
import { outputService } from '../core/output.js';
import { RENET_PATH, rdcMust, ServerError } from './box.js';
import { BYO_CERT, BYO_SPLIT, shCommand } from './box-scripts.js';
import type { ServerDeps, TlsMethod } from './types.js';

export interface TlsOptions {
  method: TlsMethod;
  machine: string;
  hosts: string[];
  certEmail?: string;
  cfToken?: string;
  tlsCert?: string;
  tlsKey?: string;
  /** Set as the machine's public IPv4 when it has no infra block yet, which `infra push` needs. */
  publicIPv4?: string;
}

async function installOwnCert(deps: ServerDeps, opts: TlsOptions): Promise<void> {
  if (!opts.tlsCert || !opts.tlsKey) {
    throw new ServerError(t('commands.server.tls.byoNeedsPair'));
  }
  const cert = await deps.readFile(opts.tlsCert);
  const key = await deps.readFile(opts.tlsKey);
  const stdin = `${cert.trimEnd()}\n${BYO_SPLIT}\n${key.trimEnd()}\n`;
  for (const host of opts.hosts) {
    const result = await deps.ssh(opts.machine, shCommand(BYO_CERT, [RENET_PATH, host]), stdin);
    if (result.code !== 0) {
      throw new ServerError(
        t('commands.server.tls.byoFailed', {
          host,
          detail: result.stderr.trim().split('\n').at(-1) ?? '',
        })
      );
    }
    outputService.info(t('commands.server.tls.byoInstalled', { host }));
  }
}

export async function applyTls(deps: ServerDeps, opts: TlsOptions): Promise<void> {
  if (opts.method === 'byo') {
    await installOwnCert(deps, opts);
    return;
  }
  const args = ['machine', 'infra', 'set', opts.machine];
  if (opts.method === 'cloudflare') {
    if (!opts.cfToken) throw new ServerError(t('commands.server.tls.cloudflareNeedsToken'));
    args.push('--cf-dns-token', opts.cfToken);
  }
  if (opts.certEmail) args.push('--cert-email', opts.certEmail);
  if (opts.publicIPv4) args.push('--public-ipv4', opts.publicIPv4);
  if (args.length > 4) await rdcMust(deps, args);
  await rdcMust(deps, ['machine', 'infra', 'push', opts.machine]);
}
