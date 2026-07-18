/**
 * Provider Resolver
 *
 * Resolves a CloudProviderConfig to a full ProviderMapping by looking up the
 * built-in provider registry or using custom inline mappings.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import type { CloudProviderConfig, ProviderMapping } from '../../types/index.js';
import providerRegistry from './provider-registry.json' with { type: 'json' };

type KnownProviderMapping = Omit<ProviderMapping, 'source'>;

let registryCache: Record<string, KnownProviderMapping> | undefined;

function loadRegistry(): Record<string, KnownProviderMapping> {
  if (registryCache) return registryCache;
  registryCache = providerRegistry as Record<string, KnownProviderMapping>;
  return registryCache;
}

/**
 * Resolve a CloudProviderConfig to a full ProviderMapping.
 * - If config.source is set → build ProviderMapping from custom fields
 * - If config.provider is set → look up in provider-registry.json
 * - Merge user defaults (region, instanceType, image) over registry defaults
 */
/**
 * True for the local libvirt pseudo-provider. KVM never goes through OpenTofu;
 * cluster provisioning routes it to the renet-ops-backed KVM provisioner. The
 * resolver refuses to build a tofu mapping for it so it can never reach the
 * generator.
 */
export function isKvmProvider(provider: string | undefined): boolean {
  return provider === 'kvm';
}

export function resolveProviderMapping(config: CloudProviderConfig): ProviderMapping {
  if (isKvmProvider(config.provider)) {
    throw new Error(
      "Provider 'kvm' is provisioned via renet ops, not OpenTofu; cluster provisioning routes it to the KVM provisioner."
    );
  }

  if (config.source) {
    return resolveCustomProvider(config);
  }

  if (config.provider) {
    return resolveKnownProvider(config);
  }

  throw new Error(
    'Cloud provider config must have either "provider" (known provider) or "source" (custom provider)'
  );
}

function buildCustomDefaults(config: CloudProviderConfig): Record<string, string> | undefined {
  const defaults: Record<string, string> = {};
  if (config.region && config.regionAttr) defaults[config.regionAttr] = config.region;
  if (config.instanceType && config.sizeAttr) defaults[config.sizeAttr] = config.instanceType;
  if (config.image && config.imageAttr) defaults[config.imageAttr] = config.image;
  return Object.keys(defaults).length > 0 ? defaults : undefined;
}

function resolveCustomProvider(config: CloudProviderConfig): ProviderMapping {
  if (!config.source) throw new Error('Custom provider requires "source"');
  if (!config.resource) throw new Error('Custom provider requires "resource"');
  if (!config.ipv4Output) throw new Error('Custom provider requires "ipv4Output"');
  if (!config.sshKey) throw new Error('Custom provider requires "sshKey"');

  return {
    source: config.source,
    version: config.version,
    tokenAttr: config.tokenAttr ?? DEFAULTS.CLOUD.TOKEN_ATTR,
    resource: config.resource,
    labelAttr: config.labelAttr ?? DEFAULTS.CLOUD.LABEL_ATTR,
    regionAttr: config.regionAttr ?? DEFAULTS.CLOUD.REGION_ATTR,
    sizeAttr: config.sizeAttr ?? DEFAULTS.CLOUD.SIZE_ATTR,
    imageAttr: config.imageAttr ?? DEFAULTS.CLOUD.IMAGE_ATTR,
    ipv4Output: config.ipv4Output,
    ipv6Output: config.ipv6Output,
    sshKey: config.sshKey,
    defaults: buildCustomDefaults(config),
  };
}

function resolveKnownProvider(config: CloudProviderConfig): ProviderMapping {
  const registry = loadRegistry();
  if (!(config.provider! in registry)) {
    const available = Object.keys(registry).join(', ');
    throw new Error(
      `Unknown provider "${config.provider}". Known providers: ${available}. Use "source" for custom providers.`
    );
  }
  const entry = registry[config.provider!];

  // Merge user defaults over registry defaults
  const defaults = { ...entry.defaults };
  if (config.region && entry.regionAttr) defaults[entry.regionAttr] = config.region;
  if (config.instanceType && entry.sizeAttr) defaults[entry.sizeAttr] = config.instanceType;
  if (config.image && entry.imageAttr) defaults[entry.imageAttr] = config.image;

  return {
    ...entry,
    source: config.provider!,
    defaults,
  };
}
