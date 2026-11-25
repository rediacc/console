/**
 * STIX 2.1 bundle for an incident report (D4 of PLAN-forensics-reports), built
 * without a library. Every id is a UUIDv5 over the object's content, so building
 * the same report twice gives the same bytes, whatever the input order. A repeated
 * type:value IoC is merged (earliest firstSeen, latest lastSeen, lowest asn). A file
 * indicator exists for every sha256 IoC and carries no observable, so a report with
 * no sha256 IoC emits none.
 */
import { canonicalize } from './canonical.js';
import type { Ioc, IocType } from './report.js';

/** Fixed namespace for the report ids; random once, never changed. */
export const STIX_NAMESPACE = '5a0b9c1e-6d4f-5b7a-9e2c-3f8d1a4c7e60';

export interface StixInput {
  orgId: string;
  orgName?: string;
  /** Report generation time; becomes `created` and `modified` on every object. */
  generatedAt: string;
  iocs: readonly Ioc[];
}

export interface StixObject {
  type: string;
  spec_version: '2.1';
  id: string;
  /** Absent on a cyber-observable object, which STIX does not timestamp. */
  created?: string;
  modified?: string;
  [key: string]: unknown;
}

export interface StixBundle {
  type: 'bundle';
  id: string;
  objects: StixObject[];
}

function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

/** RFC 4122 version 5 UUID of `name` in `namespace`. */
export async function uuidV5(name: string, namespace: string = STIX_NAMESPACE): Promise<string> {
  const ns = hexToBytes(namespace.replaceAll('-', ''));
  const nameBytes = new TextEncoder().encode(name);
  const data = new Uint8Array(ns.length + nameBytes.length);
  data.set(ns, 0);
  data.set(nameBytes, ns.length);
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-1', data));
  const b = digest.slice(0, 16);
  b[6] = ((b[6] ?? 0) & 0x0f) | 0x50;
  b[8] = ((b[8] ?? 0) & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

async function stixId(type: string, content: Record<string, unknown>): Promise<string> {
  return `${type}--${await uuidV5(`${type}:${canonicalize(content as never)}`)}`;
}

/** Escapes a value for a single-quoted STIX pattern string literal. */
export function patternLiteral(value: string): string {
  return `'${value.replaceAll('\\', '\\\\').replaceAll("'", "\\'")}'`;
}

/** The STIX pattern for one IoC. */
export function iocPattern(ioc: Pick<Ioc, 'type' | 'value'>): string {
  const lit = patternLiteral(ioc.value);
  const byType: Record<IocType, string> = {
    ipv4: `[ipv4-addr:value = ${lit}]`,
    ipv6: `[ipv6-addr:value = ${lit}]`,
    domain: `[domain-name:value = ${lit}]`,
    port: `[network-traffic:dst_port = ${Number.parseInt(ioc.value, 10)}]`,
    sha256: `[file:hashes.'SHA-256' = ${lit}]`,
  };
  return byType[ioc.type];
}

function observableOf(ioc: Ioc): { type: string; fields: Record<string, unknown> } | null {
  switch (ioc.type) {
    case 'ipv4':
      return { type: 'ipv4-addr', fields: { value: ioc.value } };
    case 'ipv6':
      return { type: 'ipv6-addr', fields: { value: ioc.value } };
    case 'domain':
      return { type: 'domain-name', fields: { value: ioc.value } };
    case 'port':
      return {
        type: 'network-traffic',
        fields: { dst_port: Number.parseInt(ioc.value, 10), protocols: ['tcp'] },
      };
    case 'sha256':
      return null;
  }
}

interface Common {
  spec_version: '2.1';
  created: string;
  modified: string;
}

function iocKey(ioc: Pick<Ioc, 'type' | 'value'>): string {
  return `${ioc.type}:${ioc.value}`;
}

function byKey(a: Ioc, b: Ioc): number {
  const [x, y] = [iocKey(a), iocKey(b)];
  if (x === y) return 0;
  return x < y ? -1 : 1;
}

/** One IoC per type:value, sorted by key; a repeat widens the window and keeps the lowest asn. */
function mergeDuplicates(iocs: readonly Ioc[]): Ioc[] {
  const merged = new Map<string, Ioc>();
  for (const ioc of iocs) {
    const prev = merged.get(iocKey(ioc));
    if (!prev) {
      merged.set(iocKey(ioc), ioc);
      continue;
    }
    const asns = [prev.asn, ioc.asn].filter((n): n is number => n !== undefined);
    merged.set(iocKey(ioc), {
      ...prev,
      firstSeen: ioc.firstSeen < prev.firstSeen ? ioc.firstSeen : prev.firstSeen,
      lastSeen: ioc.lastSeen > prev.lastSeen ? ioc.lastSeen : prev.lastSeen,
      ...(asns.length > 0 ? { asn: Math.min(...asns) } : {}),
    });
  }
  return [...merged.values()].sort(byKey);
}

async function relationship(
  common: Common,
  creator: string,
  kind: string,
  source: string,
  target: string
): Promise<StixObject> {
  return {
    type: 'relationship',
    ...common,
    id: await stixId('relationship', { k: kind, s: source, t: target }),
    created_by_ref: creator,
    relationship_type: kind,
    source_ref: source,
    target_ref: target,
  };
}

async function autonomousSystem(ioc: Ioc): Promise<StixObject | null> {
  if (ioc.asn === undefined || (ioc.type !== 'ipv4' && ioc.type !== 'ipv6')) return null;
  const id = await stixId('autonomous-system', { number: ioc.asn });
  return { type: 'autonomous-system', spec_version: '2.1', id, number: ioc.asn } as StixObject;
}

/** Every object one IoC contributes: indicator, observable, optional AS, observed-data, relationships. */
async function objectsForIoc(ioc: Ioc, common: Common, creator: string): Promise<StixObject[]> {
  const indicator: StixObject = {
    type: 'indicator',
    ...common,
    id: await stixId('indicator', { type: ioc.type, value: ioc.value }),
    created_by_ref: creator,
    name: `${ioc.type} ${ioc.value}`,
    pattern: iocPattern(ioc),
    pattern_type: 'stix',
    valid_from: ioc.firstSeen,
  };
  const observable = observableOf(ioc);
  if (!observable) return [indicator];

  const sco = {
    type: observable.type,
    spec_version: '2.1',
    id: await stixId(observable.type, observable.fields),
    ...observable.fields,
  } as StixObject;
  const as = await autonomousSystem(ioc);
  const observed: StixObject = {
    type: 'observed-data',
    ...common,
    id: await stixId('observed-data', {
      type: ioc.type,
      value: ioc.value,
      first: ioc.firstSeen,
      last: ioc.lastSeen,
    }),
    created_by_ref: creator,
    first_observed: ioc.firstSeen,
    last_observed: ioc.lastSeen,
    number_observed: 1,
    object_refs: as ? [sco.id, as.id] : [sco.id],
  };
  return [
    indicator,
    sco,
    ...(as ? [as] : []),
    observed,
    await relationship(common, creator, 'based-on', indicator.id, sco.id),
    await relationship(common, creator, 'related-to', observed.id, indicator.id),
  ];
}

/** Builds the bundle; identical input gives an identical result. */
export async function buildStixBundle(input: StixInput): Promise<StixBundle> {
  const common: Common = {
    spec_version: '2.1',
    created: input.generatedAt,
    modified: input.generatedAt,
  };
  const identity: StixObject = {
    type: 'identity',
    ...common,
    id: await stixId('identity', { orgId: input.orgId }),
    name: input.orgName ?? input.orgId,
    identity_class: 'organization',
  };

  const byId = new Map<string, StixObject>([[identity.id, identity]]);
  for (const ioc of mergeDuplicates(input.iocs)) {
    for (const o of await objectsForIoc(ioc, common, identity.id)) byId.set(o.id, o);
  }
  const objects = [...byId.values()];
  return {
    type: 'bundle',
    id: await stixId('bundle', { objects: objects.map((o) => o.id) }),
    objects,
  };
}
