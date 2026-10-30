/**
 * OpenTofu .tf.json Generator
 *
 * Generates provider-agnostic .tf.json configurations from ProviderMapping.
 * No provider-specific branches, all differences are encoded in the mapping.
 */

import type { ProviderMapping } from '../../types/index.js';
import { PROVIDER_LOCK_HOST, PROVIDER_PINS, type ProviderPin } from './provider-pins.generated.js';

interface TfGenerateOptions {
  machineName: string;
  mapping: ProviderMapping;
  apiToken: string;
  sshPublicKey: string;
  overrides?: { region?: string; instanceType?: string; image?: string };
}

/**
 * Build resource attributes from mapping defaults and CLI overrides.
 */
function buildResourceAttrs(
  machineName: string,
  mapping: ProviderMapping,
  sshPublicKey: string,
  resources: Record<string, Record<string, unknown>>,
  overrides?: TfGenerateOptions['overrides']
): Record<string, unknown> {
  const attrs: Record<string, unknown> = {};
  attrs[mapping.labelAttr] = machineName;

  if (mapping.defaults) {
    for (const [key, value] of Object.entries(mapping.defaults)) {
      attrs[key] = value;
    }
  }

  if (overrides?.region) attrs[mapping.regionAttr] = overrides.region;
  if (overrides?.instanceType) attrs[mapping.sizeAttr] = overrides.instanceType;
  if (overrides?.image) attrs[mapping.imageAttr] = overrides.image;

  // SSH key injection
  if (mapping.sshKey.format === 'inline_list') {
    attrs[mapping.sshKey.attr] = [sshPublicKey];
  } else if (mapping.sshKey.keyResource) {
    resources[mapping.sshKey.keyResource] = {
      machine: { name: `${machineName}-key`, public_key: sshPublicKey },
    };
    attrs[mapping.sshKey.attr] = [`\${${mapping.sshKey.keyResource}.machine.id}`];
  }

  return attrs;
}

/**
 * Generate a complete .tf.json object from a ProviderMapping.
 */
export function generateTfJson(options: TfGenerateOptions): Record<string, unknown> {
  const { machineName, mapping, apiToken, sshPublicKey, overrides } = options;

  const providerName = mapping.source.split('/').pop()!;
  const providerNs = mapping.source.split('/')[0];

  const resources: Record<string, Record<string, unknown>> = {};
  const resourceAttrs = buildResourceAttrs(
    machineName,
    mapping,
    sshPublicKey,
    resources,
    overrides
  );
  resources[mapping.resource] = { machine: resourceAttrs };

  // Firewall resource (if configured)
  if (mapping.firewall) {
    const fwRules = buildFirewallRules(mapping, providerName);
    if (fwRules) {
      resources[mapping.firewall.resource] = { machine: fwRules };
      if (mapping.firewall.attachResource) {
        resources[mapping.firewall.attachResource] = {
          machine: {
            firewall_id: `\${${mapping.firewall.resource}.machine.id}`,
            server_ids: [`\${${mapping.resource}.machine.id}`],
          },
        };
      }
    }
  }

  const outputs: Record<string, { value: string }> = {
    ipv4: { value: `\${${mapping.resource}.machine.${mapping.ipv4Output}}` },
  };
  if (mapping.ipv6Output) {
    outputs.ipv6 = { value: `\${${mapping.resource}.machine.${mapping.ipv6Output}}` };
  }

  return {
    terraform: {
      required_providers: {
        [providerName]: {
          source: `${providerNs}/${providerName}`,
          ...(mapping.version ? { version: mapping.version } : {}),
        },
      },
    },
    provider: { [providerName]: { [mapping.tokenAttr]: apiToken } },
    resource: resources,
    output: outputs,
  };
}

function buildFirewallRules(
  mapping: ProviderMapping,
  providerName: string
): Record<string, unknown> | null {
  if (!mapping.firewall) return null;

  const fw = mapping.firewall;
  const commonPorts = [
    { label: 'ssh', port: '22', protocol: 'TCP' },
    { label: 'http', port: '80', protocol: 'TCP' },
    { label: 'https', port: '443', protocol: 'TCP' },
  ];

  // Linode-style firewall (with linodes link)
  if (fw.linkAttr && fw.linkRef) {
    return {
      label: `${providerName}-fw`,
      [fw.linkAttr]: [fw.linkRef],
      inbound_policy: 'DROP',
      outbound_policy: 'ACCEPT',
      inbound: commonPorts.map((p) => ({
        label: p.label,
        action: 'ACCEPT',
        protocol: p.protocol,
        ports: p.port,
        ipv4: ['0.0.0.0/0'],
        ipv6: ['::/0'],
      })),
    };
  }

  // Hetzner-style firewall (separate attachment resource)
  if (fw.attachResource) {
    return {
      name: `${providerName}-fw`,
      rule: commonPorts.map((p) => ({
        direction: 'in',
        protocol: p.protocol.toLowerCase(),
        port: p.port,
        source_ips: ['0.0.0.0/0', '::/0'],
      })),
    };
  }

  return null;
}

/** A `terraform.required_providers` entry of a generated config. */
interface RequiredProvider {
  source?: string;
  version?: string;
}

const LOCK_HEADER =
  '# This file is maintained automatically by "tofu init".\n# Manual edits may be lost in future updates.\n';

/** The pin of a required provider: its source names a pinned provider and its version is the pinned one, or absent. */
function pinOf(
  required: RequiredProvider,
  pins: Readonly<Record<string, ProviderPin>>
): ProviderPin | null {
  if (!required.source) return null;
  const key = required.source.toLowerCase().replace(`${PROVIDER_LOCK_HOST}/`, '');
  const pin = Object.entries(pins).find(([source]) => source.toLowerCase() === key)?.[1];
  if (!pin) return null;
  return required.version === undefined || required.version === pin.version ? pin : null;
}

/**
 * The `.terraform.lock.hcl` text for the pinned providers a config requires, each block as
 * `tofu providers lock` wrote it (scripts/pins/tofu-provider-pins.ts); null when none is pinned.
 * A provider whose config asks for a version other than its pin (a custom provider) is left to
 * tofu, which locks it on init.
 */
export function generateProviderLock(
  requiredProviders: Record<string, RequiredProvider>,
  pins: Readonly<Record<string, ProviderPin>> = PROVIDER_PINS
): string | null {
  const blocks = [
    ...new Set(
      Object.values(requiredProviders)
        .map((r) => pinOf(r, pins)?.lock)
        .filter((b): b is string => b !== undefined)
    ),
  ].sort((a, b) => Number(a > b) - Number(a < b));
  if (blocks.length === 0) return null;
  return `${LOCK_HEADER}\n${blocks.map((b) => `${b}\n`).join('\n')}`;
}
