import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { OPENTOFU_PIN } from '../../tools/opentofu-pin.generated.js';
import registry from '../provider-registry.json' with { type: 'json' };
import { resolveProviderMapping } from '../provider-resolver.js';
import { generateTfJson } from '../tf-generator.js';

// cherryservers/cherryservers 1.6.1 schema, read offline with:
//   tofu init && tofu providers schema -json   (main.tf.json requiring cherryservers/cherryservers 1.6.1)
// cherryservers_server required arguments: plan (string), project_id (number), region (string).
// Optional: hostname, image, ssh_key_ids (set of string), user_data, tags, cycle, ...
// Computed: id, state, power_state, pricing, ip_addresses, a SET of objects with
//   address, address_family (number), cidr, id, type, vlan_id.
// There is no `primary_ip` attribute (the former mapping), and a set cannot be indexed by path,
// so the IPv4 output is a for-expression over ip_addresses.
const SERVER_ATTRS = new Set([
  'plan',
  'project_id',
  'region',
  'hostname',
  'image',
  'ssh_key_ids',
  'ip_addresses',
]);
const IP_ADDRESS_FIELDS = new Set(['address', 'address_family', 'cidr', 'id', 'type', 'vlan_id']);

const generate = (env: NodeJS.ProcessEnv) =>
  generateTfJson({
    machineName: 'vm1',
    mapping: resolveProviderMapping({
      provider: 'cherryservers/cherryservers',
      apiToken: 'tok',
    }),
    apiToken: 'tok',
    sshPublicKey: 'ssh-ed25519 AAAA',
    env,
  });

describe('cherryservers mapping', () => {
  it('wires project_id as a number from CHERRY_PROJECT_ID', () => {
    const tf = generate({ CHERRY_PROJECT_ID: '123456' });
    const server = (tf.resource as Record<string, Record<string, Record<string, unknown>>>)
      .cherryservers_server.machine;
    expect(server.project_id).toBe(123456);
    expect(server.plan).toBe('cloud_vps_3');
    expect(server.region).toBe('eu_nord_1');
    for (const key of Object.keys(server)) expect(SERVER_ATTRS.has(key)).toBe(true);
  });

  it('fails clearly when CHERRY_PROJECT_ID is unset', () => {
    expect(() => generate({})).toThrow(/CHERRY_PROJECT_ID/);
  });

  it('outputs an IPv4 built from ip_addresses fields that exist in the 1.6.1 schema', () => {
    const tf = generate({ CHERRY_PROJECT_ID: '1' });
    const value = (tf.output as Record<string, { value: string }>).ipv4.value;
    expect(value).toContain('cherryservers_server.machine.ip_addresses');
    expect(value).not.toContain('primary_ip');
    expect(value).not.toContain('@self');
    expect(SERVER_ATTRS.has('ip_addresses')).toBe(true);
    const fields = [...value.matchAll(/\ba\.(\w+)/g)].map((m) => m[1]);
    expect(fields.length).toBeGreaterThan(0);
    for (const f of fields) expect(IP_ADDRESS_FIELDS.has(f)).toBe(true);
  });
});

// The IPv4 output's selection logic, evaluated by the real tofu (`tofu console` needs no provider or
// network) with @self.ip_addresses replaced by literal address lists.

const TOFU_BIN =
  process.env.REDIACC_TOFU ??
  join(homedir(), '.local/state/rediacc/tools/opentofu', OPENTOFU_PIN.version, 'tofu');
const HAVE_TOFU = process.platform !== 'win32' && existsSync(TOFU_BIN);

function evalIpv4(addresses: { address: string; type: string; family: number }[]): string {
  const entry = (registry as Record<string, { ipv4Output?: string }>)[
    'cherryservers/cherryservers'
  ];
  const expr = String(entry.ipv4Output ?? '');
  const list = `[${addresses
    .map((a) => `{address = "${a.address}", type = "${a.type}", address_family = ${a.family}}`)
    .join(', ')}]`;
  const out = execFileSync(TOFU_BIN, ['console'], {
    input: `${expr.replaceAll('@self.ip_addresses', list)}\n`,
    encoding: 'utf8',
  });
  return out.trim().replace(/^"|"$/g, '');
}

describe.skipIf(!HAVE_TOFU && process.env.CI !== 'true')('cherryservers IPv4 selection', () => {
  it('prefers the primary-ip IPv4', () => {
    expect(
      evalIpv4([
        { address: '10.0.0.5', type: 'private-ip', family: 4 },
        { address: '203.0.113.7', type: 'floating-ip', family: 4 },
        { address: '198.51.100.9', type: 'primary-ip', family: 4 },
      ])
    ).toBe('198.51.100.9');
  });

  it('falls back to the first public IPv4 when no address is typed primary-ip, skipping private, loopback, link-local and CGNAT ranges', () => {
    expect(
      evalIpv4([
        { address: '10.0.0.5', type: 'private', family: 4 },
        { address: '172.20.1.1', type: 'private', family: 4 },
        { address: '192.168.1.2', type: 'private', family: 4 },
        { address: '127.0.0.1', type: 'loopback', family: 4 },
        { address: '169.254.0.9', type: 'link-local', family: 4 },
        { address: '100.64.3.3', type: 'cgnat', family: 4 },
        { address: '2001:db8::1', type: 'public', family: 6 },
        { address: '203.0.113.7', type: 'public', family: 4 },
      ])
    ).toBe('203.0.113.7');
  });

  it('errors instead of answering null or a private address when no public IPv4 exists', () => {
    expect(() => evalIpv4([{ address: '10.0.0.5', type: 'private', family: 4 }])).toThrow();
  });
});
