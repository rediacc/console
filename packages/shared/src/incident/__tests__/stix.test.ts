import { describe, expect, it } from 'vitest';
import type { Ioc } from '../report.js';
import { buildStixBundle, iocPattern, type StixObject, uuidV5 } from '../stix.js';

const obs = { basis: 'observed' as const, value: 'flow record' };
const ioc = (type: Ioc['type'], value: string, extra: Partial<Ioc> = {}): Ioc => ({
  type,
  value,
  firstSeen: '2026-11-20T08:00:00.000Z',
  lastSeen: '2026-11-20T08:05:00.000Z',
  evidence: obs,
  ...extra,
});
const input = (iocs: Ioc[]) => ({
  orgId: 'org-1',
  orgName: 'Example GmbH',
  generatedAt: '2026-11-21T09:00:00.000Z',
  iocs,
});

const TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;
const ID = /^[a-z0-9-]+--[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
/** One comparison expression: `[object-type:path = literal]`, the grammar subset the bundle uses. */
const PATTERN =
  /^\[[a-z][a-z0-9-]*:[A-Za-z_][\w]*(\.(?:[A-Za-z_]\w*|'[^']+'))* = (?:'(?:[^'\\]|\\.)*'|\d+)\]$/;

const SDO_REQUIRED: Record<string, string[]> = {
  identity: ['name', 'identity_class'],
  indicator: ['pattern', 'pattern_type', 'valid_from'],
  'observed-data': ['first_observed', 'last_observed', 'number_observed', 'object_refs'],
  relationship: ['relationship_type', 'source_ref', 'target_ref'],
};
const SCO_REQUIRED: Record<string, string[]> = {
  'ipv4-addr': ['value'],
  'ipv6-addr': ['value'],
  'domain-name': ['value'],
  'autonomous-system': ['number'],
  'network-traffic': ['protocols'],
};

function missing(o: StixObject, keys: readonly string[]): string[] {
  return keys.filter((key) => o[key] === undefined).map((key) => `${o.id}: ${key}`);
}

function badTimestamps(o: StixObject): string[] {
  return ['created', 'modified']
    .filter((key) => !TS.test(String(o[key])))
    .map((key) => `${o.id}: ${key}`);
}

function scoExtras(o: StixObject): string[] {
  return 'created' in o || 'modified' in o ? [`${o.id}: SCO with created`] : [];
}

/** Returns the list of STIX 2.1 conformance problems of one object (empty when valid). */
function problems(o: StixObject): string[] {
  const out: string[] = [];
  if (o.spec_version !== '2.1') out.push(`${o.id}: spec_version`);
  if (!ID.test(o.id) || !o.id.startsWith(`${o.type}--`)) out.push(`${o.id}: id`);
  const sdo = SDO_REQUIRED[o.type];
  const sco = SCO_REQUIRED[o.type];
  if (sdo) out.push(...badTimestamps(o), ...missing(o, sdo));
  else if (sco) out.push(...missing(o, sco), ...scoExtras(o));
  else out.push(`${o.id}: unknown type ${o.type}`);
  if (o.type === 'indicator' && !PATTERN.test(String(o.pattern))) out.push(`${o.id}: pattern`);
  return out;
}

describe('STIX bundle', () => {
  const iocs = [
    ioc('ipv4', '203.0.113.9', { asn: 64500 }),
    ioc('ipv6', '2001:db8::1'),
    ioc('domain', 'evil.example'),
    ioc('port', '4444'),
  ];

  it('gives identical bytes on two runs', async () => {
    const a = JSON.stringify(await buildStixBundle(input(iocs)));
    const b = JSON.stringify(await buildStixBundle(input([...iocs].reverse())));
    expect(b).toBe(a);
  });

  it('meets the required properties of every object and every pattern', async () => {
    const bundle = await buildStixBundle(input(iocs));
    expect(bundle.type).toBe('bundle');
    expect(bundle.id).toMatch(/^bundle--/);
    const bad = bundle.objects.flatMap(problems);
    expect(bad).toEqual([]);
    const types = new Set(bundle.objects.map((o) => o.type));
    for (const t of [
      'identity',
      'indicator',
      'observed-data',
      'relationship',
      'autonomous-system',
    ]) {
      expect(types.has(t)).toBe(true);
    }
    const ids = new Set(bundle.objects.map((o) => o.id));
    const refs = bundle.objects.flatMap((o) =>
      [o.source_ref, o.target_ref, o.created_by_ref].filter((r) => typeof r === 'string')
    );
    expect(refs.length).toBeGreaterThan(0);
    expect(refs.filter((r) => !ids.has(r))).toEqual([]);
  });

  it('gives an IPv6 destination an ipv6-addr pattern', () => {
    expect(iocPattern(ioc('ipv6', '2001:db8::1'))).toBe("[ipv6-addr:value = '2001:db8::1']");
    expect(iocPattern(ioc('ipv4', '203.0.113.9'))).toBe("[ipv4-addr:value = '203.0.113.9']");
  });

  it('emits no file indicator without a process hash', async () => {
    const without = await buildStixBundle(input(iocs));
    expect(without.objects.some((o) => String(o.pattern ?? '').includes('file:'))).toBe(false);
    const hash = 'a'.repeat(64);
    const withHash = await buildStixBundle(input([...iocs, ioc('sha256', hash)]));
    const file = withHash.objects.find((o) => String(o.pattern ?? '').startsWith('[file:'));
    expect(file?.pattern).toBe(`[file:hashes.'SHA-256' = '${hash}']`);
    expect(withHash.objects.flatMap(problems)).toEqual([]);
  });

  it('flags a control object without spec_version', async () => {
    const bundle = await buildStixBundle(input(iocs));
    const broken = {
      ...(bundle.objects[0] as StixObject),
      spec_version: undefined,
    } as unknown as StixObject;
    expect(problems(broken)).toContain(`${broken.id}: spec_version`);
  });

  it('escapes a quote in a pattern literal', () => {
    expect(iocPattern(ioc('domain', "a'b.example"))).toBe("[domain-name:value = 'a\\'b.example']");
  });

  it('matches the RFC 4122 version 5 reference vector', async () => {
    const dns = '6ba7b810-9dad-11d1-80b4-00c04fd430c8';
    expect(await uuidV5('www.example.com', dns)).toBe('2ed6657d-e927-568b-95e1-2665a8aea6a2');
  });
});
