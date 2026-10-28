/**
 * The `access` bucket: SSH keys rdc installs on machines, and the source
 * ranges each may log in from.
 *
 * Pinned here: the shape parses as declared, an access key never resolves to
 * no range (that key would be unrestricted), one public key is never declared
 * twice, a key's stated type matches its blob, the bucket keeps its place in
 * the serialized config, and the whole bucket is field-committed so a push
 * that quietly widens who may log in is rejected.
 */

import { describe, expect, it } from 'vitest';
import { HOSTED_EXECUTOR_SOURCE_RANGES } from '../../config/network.js';
import { buildCommitEntries } from '../payload.js';
import {
  AccessSchema,
  parseConfig,
  type RdcConfig,
  RdcConfigSchema,
  resolveAccessSourceRanges,
  stringifyConfig,
} from '../schemas.js';
import { pathsToCommit } from '../walker.js';

const KEY_A =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEdJ8beAUfRNuwo5eWRUdPfO7aiDeVKO+so+zqsB7Jtg rediacc-live-console-probe-2026-10-26';
const KEY_B = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIN7gIAHNNi3h3d3UbYWPMG9ICxHNb8WcMmfMGrYmop66';
const KEY_EC =
  'ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBKS5JSbceD1LDMpT/UfMWbZtMcYJm0y7URdoInpIEC1iujou1OXHlYVLheg5vzyAtv3mLhCzkXbiFQvbYbZQl7Y= ec';

function fullAccess() {
  return {
    sourceRanges: { ipv4: ['104.28.0.0/16'], ipv6: ['2a09:bac0::/29'] },
    keys: {
      'console-probe': {
        publicKey: KEY_A,
        restrict: true,
        sourceRanges: structuredClone(HOSTED_EXECUTOR_SOURCE_RANGES) as {
          ipv4: string[];
          ipv6: string[];
        },
        machines: {
          hostinger: {},
          'edge-box': { sourceRanges: { ipv6: ['2a09:bac0::/29'] } },
        },
      },
      'team-ops': { publicKey: KEY_EC, restrict: false, machines: { hostinger: {} } },
    },
  };
}

function configWith(access: unknown): RdcConfig {
  return {
    schemaVersion: 3,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 1,
    defaults: { language: 'en', datastoreSize: '95%' },
    encryption: { mode: 'plaintext' },
    resources: { machines: { hostinger: { ip: '72.61.137.225', user: 'muhammed' } } },
    access,
  } as RdcConfig;
}

function issues(access: unknown): string[] {
  const result = AccessSchema.safeParse(access);
  return result.success ? [] : result.error.issues.map((i) => i.message);
}

describe('access in the config', () => {
  it('a full example parses unchanged', () => {
    const parsed = parseConfig(RdcConfigSchema, configWith(fullAccess()), 'test config');
    expect(parsed.access).toEqual(fullAccess());
  });

  it('resolves machine ?? key ?? config, each level replacing the one below whole', () => {
    const access = fullAccess();
    expect(resolveAccessSourceRanges(access, 'console-probe', 'edge-box')).toEqual({
      ipv6: ['2a09:bac0::/29'],
    });
    expect(resolveAccessSourceRanges(access, 'console-probe', 'hostinger')).toEqual(
      access.keys['console-probe'].sourceRanges
    );
    expect(resolveAccessSourceRanges(access, 'team-ops', 'hostinger')).toBe(access.sourceRanges);
    expect(resolveAccessSourceRanges(access, 'missing', 'hostinger')).toBeUndefined();
  });

  it('refuses an access key that resolves to no source range', () => {
    const noDefault = { keys: { k: { publicKey: KEY_A, machines: { hostinger: {} } } } };
    expect(issues(noDefault)[0]).toMatch(/access key k resolves to no source range/);

    const unbound = { keys: { k: { publicKey: KEY_A } } };
    expect(issues(unbound)[0]).toMatch(/resolves to no source range/);

    // Every binding carrying its own ranges is a full resolution.
    const perMachine = {
      keys: {
        k: {
          publicKey: KEY_A,
          machines: { hostinger: { sourceRanges: { ipv4: ['10.0.0.0/8'] } } },
        },
      },
    };
    expect(issues(perMachine)).toEqual([]);
  });

  it('refuses an empty sourceRanges at any level', () => {
    expect(issues({ sourceRanges: {}, keys: {} })).toEqual([
      'sourceRanges needs at least one ipv4 or ipv6 range',
    ]);
  });

  it('refuses two keys declaring the same blob', () => {
    const access = fullAccess();
    (access.keys as Record<string, unknown>).copy = { publicKey: KEY_A.replace(/ \S+$/, ' other') };
    expect(issues(access)).toEqual([
      'access keys console-probe and copy declare the same public key',
    ]);
  });

  it('refuses two keys whose blobs differ only in unused padding bits', () => {
    // 'Y=' and 'Z=' differ only in the two bits atob drops, so both decode to one key.
    const twin = KEY_EC.replace('l7Y= ec', 'l7Z= twin');
    expect(twin).not.toBe(KEY_EC);
    const access = {
      sourceRanges: { ipv4: ['10.0.0.0/8'] },
      keys: { ec: { publicKey: KEY_EC }, twin: { publicKey: twin } },
    };
    expect(issues(access)).toEqual(['access keys ec and twin declare the same public key']);
  });

  it('refuses an undecodable blob before the duplicate check can skip it', () => {
    // canonicalKeyBlob returns null for such a blob and the duplicate check skips it, so the per-key schema must be what refuses it.
    const bad = 'ssh-ed25519 AAAC3NzaC1lZDI1NTE5AAAAI!!!';
    const result = issues({
      sourceRanges: { ipv4: ['10.0.0.0/8'] },
      keys: { a: { publicKey: bad }, b: { publicKey: bad } },
    });
    expect(result).toHaveLength(2);
    for (const message of result) expect(message).toMatch(/not a valid OpenSSH key encoding/);
  });

  it('refuses a stated type that differs from the blob', () => {
    const access = {
      sourceRanges: { ipv4: ['10.0.0.0/8'] },
      keys: { k: { publicKey: KEY_B.replace('ssh-ed25519', 'ssh-rsa') } },
    };
    expect(issues(access)).toEqual(['publicKey says ssh-rsa but its blob encodes ssh-ed25519']);
  });

  it.each([
    [
      'a type outside the list',
      KEY_B.replace('ssh-ed25519', 'ssh-dss'),
      /type ssh-dss is not one of/,
    ],
    ['an authorized_keys line with options', `from="10.0.0.0/8" ${KEY_B}`, /type from=/],
    ['two lines', `${KEY_B}\n${KEY_EC}`, /one OpenSSH public key line/],
    ['a blob that is not base64', 'ssh-ed25519 AAAA!!!!', /not a valid OpenSSH key encoding/],
    ['a truncated blob', 'ssh-ed25519 AAAAC3Nz', /not a valid OpenSSH key encoding/],
    ['the marker in the comment', `${KEY_B} rdc-access:12345678:k`, /must not contain rdc-access:/],
  ])('refuses %s', (_label, publicKey, message) => {
    const result = issues({ sourceRanges: { ipv4: ['10.0.0.0/8'] }, keys: { k: { publicKey } } });
    expect(result).toHaveLength(1);
    expect(result[0]).toMatch(message);
  });

  it('refuses a range with host bits set, naming the canonical form', () => {
    expect(issues({ sourceRanges: { ipv4: ['104.28.1.0/16'] } })).toEqual([
      '104.28.1.0/16 is not a network address; use 104.28.0.0/16',
    ]);
  });

  it('refuses key and machine names that are not resource names', () => {
    expect(
      issues({ sourceRanges: { ipv4: ['10.0.0.0/8'] }, keys: { Bad_Name: { publicKey: KEY_B } } })
    ).not.toEqual([]);
    expect(
      issues({
        sourceRanges: { ipv4: ['10.0.0.0/8'] },
        keys: { k: { publicKey: KEY_B, machines: { 'Not OK': {} } } },
      })
    ).not.toEqual([]);
  });

  it('serializes right after resources and round-trips', () => {
    const config = configWith(fullAccess());
    const text = stringifyConfig(config);
    const topKeys = Object.keys(JSON.parse(text) as object);
    expect(topKeys.indexOf('access')).toBe(topKeys.indexOf('resources') + 1);
    const reparsed = parseConfig(RdcConfigSchema, JSON.parse(text), 'round trip');
    expect(stringifyConfig(reparsed)).toBe(text);
  });

  it('is field-committed as one value, so any edit changes the commitment', () => {
    const config = configWith(fullAccess());
    expect(pathsToCommit(config)).toContain('/access');
    const before = buildCommitEntries(config).find((e) => e.pointer === '/access');

    const widened = configWith(fullAccess());
    (widened.access as ReturnType<typeof fullAccess>).keys['console-probe'].sourceRanges.ipv4.push(
      '0.0.0.0/1'
    );
    const after = buildCommitEntries(widened).find((e) => e.pointer === '/access');
    expect(after?.value).not.toEqual(before?.value);
  });
});
