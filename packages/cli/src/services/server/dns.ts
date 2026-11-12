/**
 * DNS for the two public names. The install prints the records to create and waits until both
 * names resolve to the machine. It never writes a customer zone: the one write is a DNS-only record
 * in a zone Rediacc owns (rediacc.io, rediacc.com, rediacc.cloud), and only with CLOUDFLARE_API_TOKEN
 * in the environment and only for a name that does not resolve yet.
 */

import { isIPv6 } from 'node:net';
import {
  WK_APEX_DOMAIN,
  WK_INFRA_DOMAIN,
  WK_PRODUCT_DOMAIN,
} from '@rediacc/shared/config/well-known.generated';
import { t } from '../../i18n/index.js';
import { outputService } from '../core/output.js';
import { ServerError } from './box.js';
import type { ServerDeps } from './types.js';

export const DNS_POLL_MS = 10_000;
export const DNS_TIMEOUT_MS = 30 * 60_000;
export const OWNED_ZONES = [WK_INFRA_DOMAIN, WK_APEX_DOMAIN, WK_PRODUCT_DOMAIN] as const;

/** The Rediacc-owned zone `host` sits in; undefined for any other (a customer's) zone. */
export function ownedZoneOf(host: string): string | undefined {
  return OWNED_ZONES.find((zone) => host === zone || host.endsWith(`.${zone}`));
}

export interface DnsRecord {
  name: string;
  type: 'A' | 'AAAA';
  value: string;
}

export function dnsRecords(hosts: string[], addresses: string[]): DnsRecord[] {
  const out: DnsRecord[] = [];
  for (const name of hosts) {
    for (const value of addresses) {
      out.push({ name, type: isIPv6(value) ? 'AAAA' : 'A', value });
    }
  }
  return out;
}

export function printDnsRecords(records: DnsRecord[]): void {
  outputService.info(t('commands.server.dns.create'));
  for (const r of records)
    outputService.info(`  ${r.name.padEnd(40)} ${r.type.padEnd(5)} ${r.value}`);
}

/** The records that do not resolve to their value yet. */
export async function unresolved(deps: ServerDeps, records: DnsRecord[]): Promise<DnsRecord[]> {
  const answers = new Map<string, string[]>();
  for (const name of new Set(records.map((r) => r.name))) {
    answers.set(name, await deps.resolve(name));
  }
  return records.filter((r) => !(answers.get(r.name) ?? []).includes(r.value));
}

/** Wait until every record resolves; a timeout names the records still missing. */
export async function waitForDns(
  deps: ServerDeps,
  records: DnsRecord[],
  timeoutMs = DNS_TIMEOUT_MS
): Promise<void> {
  const deadline = deps.now() + timeoutMs;
  let missing = await unresolved(deps, records);
  if (missing.length > 0) outputService.info(t('commands.server.dns.waiting'));
  while (missing.length > 0) {
    if (deps.now() >= deadline) {
      throw new ServerError(
        t('commands.server.dns.timeout', {
          records: missing.map((r) => `${r.name} ${r.type} ${r.value}`).join(', '),
        })
      );
    }
    await deps.sleep(DNS_POLL_MS);
    missing = await unresolved(deps, records);
  }
  outputService.success(t('commands.server.dns.resolved'));
}

/**
 * Write the records that do not resolve yet, for names in a Rediacc-owned zone when a token is
 * set. A name that already resolves elsewhere is refused, never rewritten. Returns how many were
 * written; every other record is left for the operator and the wait.
 */
export async function writeOwnedRecords(deps: ServerDeps, records: DnsRecord[]): Promise<number> {
  const token = deps.ownedZoneToken();
  if (!token) return 0;
  let written = 0;
  for (const record of await unresolved(deps, records)) {
    const zone = ownedZoneOf(record.name);
    if (!zone) continue;
    const found = (await deps.resolve(record.name)).filter(
      (a) => isIPv6(a) === (record.type === 'AAAA')
    );
    if (found.length > 0) {
      throw new ServerError(
        t('commands.server.dns.resolvesElsewhere', {
          name: record.name,
          found: found.join(', '),
          want: record.value,
        })
      );
    }
    await deps.writeDns(token, zone, record.type, record.name, record.value);
    outputService.info(t('commands.server.dns.written', { ...record }));
    written++;
  }
  return written;
}
