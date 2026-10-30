import { describe, expect, it } from 'vitest';
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
