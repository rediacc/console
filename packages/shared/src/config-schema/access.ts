/**
 * The access section of the config schema: SSH keys rdc installs on machines
 * (`rdc machine access push`), with the source ranges each may log in from.
 * Re-exported from schemas.ts, which composes `AccessSchema` into
 * `RdcConfigSchema`.
 */

import { z } from 'zod';
import { canonicalCidr, isNetworkAddress, parseCidr } from '../validation/cidr.js';
import { resourceName } from './primitives.js';

// =============================================================================
// Access: SSH keys rdc installs on machines, with their source ranges
// =============================================================================

/** Most entries one `ipv4` or `ipv6` list may carry. */
const MAX_SOURCE_RANGES_PER_LIST = 32;

/**
 * The token that marks an authorized_keys line rdc manages:
 * `rdc-access:<configId[0:8]>:<key name>`, the last token of the line. A
 * declared public key's own comment must not carry it.
 */
export const ACCESS_KEY_MARKER_PREFIX = 'rdc-access:';

const cidrv4Format = z.cidrv4();
const cidrv6Format = z.cidrv6();

/**
 * One entry of a source range list: a CIDR range of the list's family, a
 * prefix length above 0, and no host bits set (sshd matches nothing on a range
 * with host bits set, so the error names the network address to write).
 */
function cidrEntryProblem(value: string, family: 4 | 6): string | null {
  const list = family === 4 ? 'ipv4' : 'ipv6';
  const parsed = parseCidr(value);
  if (parsed !== null && parsed.family !== family) {
    return `${value} is an IPv${parsed.family} range; list it under ${family === 4 ? 'ipv6' : 'ipv4'}`;
  }
  const format = family === 4 ? cidrv4Format : cidrv6Format;
  if (parsed === null || !format.safeParse(value).success) {
    return `${value} is not an IPv${family} CIDR range`;
  }
  if (parsed.prefix === 0) {
    return `${value} allows every ${list} address; a source range needs a prefix length above 0`;
  }
  if (!isNetworkAddress(parsed)) {
    return `${value} is not a network address; use ${canonicalCidr(value)}`;
  }
  return null;
}

function cidrEntry(family: 4 | 6) {
  return z.string().superRefine((value, ctx) => {
    const message = cidrEntryProblem(value, family);
    if (message !== null) ctx.addIssue({ code: 'custom', message });
  });
}

/** Report every entry of one list that repeats an earlier entry after canonicalisation. */
function reportDuplicateRanges(list: 'ipv4' | 'ipv6', values: string[], ctx: z.RefinementCtx) {
  const seen = new Map<string, string>();
  for (const [index, value] of values.entries()) {
    const canonical = canonicalCidr(value);
    if (canonical === null) continue;
    const first = seen.get(canonical);
    if (first === undefined) {
      seen.set(canonical, value);
      continue;
    }
    ctx.addIssue({
      code: 'custom',
      path: [list, index],
      message: `${value} duplicates ${first} (both are ${canonical})`,
    });
  }
}

/**
 * The source addresses sshd admits a key from (`from="..."`). At least one
 * entry across both lists: an access key with no range would be unrestricted,
 * and an unrestricted key belongs in `credentials.ssh`.
 */
export const SourceRangesSchema = z
  .object({
    ipv4: z.array(cidrEntry(4)).max(MAX_SOURCE_RANGES_PER_LIST).optional(),
    ipv6: z.array(cidrEntry(6)).max(MAX_SOURCE_RANGES_PER_LIST).optional(),
  })
  .superRefine((ranges, ctx) => {
    if ((ranges.ipv4?.length ?? 0) + (ranges.ipv6?.length ?? 0) === 0) {
      ctx.addIssue({
        code: 'custom',
        message: 'sourceRanges needs at least one ipv4 or ipv6 range',
      });
    }
    reportDuplicateRanges('ipv4', ranges.ipv4 ?? [], ctx);
    reportDuplicateRanges('ipv6', ranges.ipv6 ?? [], ctx);
  });

/** OpenSSH public key types an access key may declare. */
export const ACCESS_KEY_TYPES = [
  'ssh-ed25519',
  'ssh-rsa',
  'ecdsa-sha2-nistp256',
  'ecdsa-sha2-nistp384',
  'ecdsa-sha2-nistp521',
  'sk-ssh-ed25519@openssh.com',
  'sk-ecdsa-sha2-nistp256@openssh.com',
] as const;

const OPENSSH_PUBLIC_KEY_LINE = /^(\S+) (\S+)(?: (.+))?$/;
const BASE64_BLOB = /^[A-Za-z0-9+/]+={0,2}$/;

/** The key type encoded at the start of an OpenSSH public key blob, or null. */
function blobKeyType(blob: string): string | null {
  if (!BASE64_BLOB.test(blob) || blob.length % 4 !== 0) return null;
  let bytes: string;
  try {
    bytes = atob(blob);
  } catch {
    return null;
  }
  if (bytes.length < 4) return null;
  const length =
    ((bytes.charCodeAt(0) << 24) >>> 0) +
    (bytes.charCodeAt(1) << 16) +
    (bytes.charCodeAt(2) << 8) +
    bytes.charCodeAt(3);
  if (length === 0 || length > 64 || bytes.length < 4 + length) return null;
  return bytes.slice(4, 4 + length);
}

/**
 * Split one OpenSSH public key line into type, blob and optional comment.
 * Null when the line is not of that shape (options in front, several lines,
 * stray whitespace).
 */
export function parseOpenSshPublicKey(
  line: string
): { type: string; blob: string; comment?: string } | null {
  if (/[\r\n]/.test(line)) return null;
  const match = OPENSSH_PUBLIC_KEY_LINE.exec(line);
  if (!match) return null;
  const [, type, blob, comment] = match;
  return comment === undefined ? { type, blob } : { type, blob, comment };
}

/**
 * The base64 blob re-encoded from its decoded bytes, or null when it does not decode. Two
 * spellings of one key (atob ignores unused padding bits, so 'AAA=' and 'AAB=' decode alike)
 * give the same value, which is what sshd compares; key identity is judged on this, never on the
 * text.
 */
export function canonicalKeyBlob(blob: string): string | null {
  try {
    return btoa(atob(blob));
  } catch {
    return null;
  }
}

const OpenSshPublicKeySchema = z.string().superRefine((value, ctx) => {
  const parsed = parseOpenSshPublicKey(value);
  if (parsed === null) {
    ctx.addIssue({
      code: 'custom',
      message: 'publicKey must be one OpenSSH public key line: "<type> <base64> [comment]"',
    });
    return;
  }
  if (!(ACCESS_KEY_TYPES as readonly string[]).includes(parsed.type)) {
    ctx.addIssue({
      code: 'custom',
      message: `publicKey type ${parsed.type} is not one of ${ACCESS_KEY_TYPES.join(', ')}`,
    });
    return;
  }
  const inner = blobKeyType(parsed.blob);
  if (inner === null) {
    ctx.addIssue({ code: 'custom', message: 'publicKey blob is not a valid OpenSSH key encoding' });
    return;
  }
  if (inner !== parsed.type) {
    ctx.addIssue({
      code: 'custom',
      message: `publicKey says ${parsed.type} but its blob encodes ${inner}`,
    });
    return;
  }
  if (parsed.comment?.includes(ACCESS_KEY_MARKER_PREFIX)) {
    ctx.addIssue({
      code: 'custom',
      message: `publicKey comment must not contain ${ACCESS_KEY_MARKER_PREFIX}: rdc writes that marker itself`,
    });
  }
});

const AccessKeyMachineSchema = z.object({
  /** Replaces the key's ranges whole for this machine. */
  sourceRanges: SourceRangesSchema,
});

/**
 * One machine binding: `true` when the key's (or the config's) ranges apply,
 * `{ sourceRanges }` when the binding carries its own. A plain binding is a
 * leaf, never `{}`: the push no-op check (push-visibility.ts `normalize`)
 * reads an empty object as no content, so a `{}` binding was never pushed.
 */
const AccessKeyBindingSchema = z.union([z.literal(true), AccessKeyMachineSchema]);

export const AccessKeySchema = z.object({
  publicKey: OpenSshPublicKeySchema,
  /**
   * Absent or true: the line also carries no-port-forwarding, no-agent-forwarding,
   * no-X11-forwarding, no-pty and no-user-rc. False keeps `from=` alone.
   */
  restrict: z.boolean().optional(),
  /** Replaces `access.sourceRanges` whole for this key. */
  sourceRanges: SourceRangesSchema.optional(),
  /** Machines (resources.machines names) this key is installed on. */
  machines: z.record(resourceName, AccessKeyBindingSchema).optional(),
});

type SourceRanges = z.infer<typeof SourceRangesSchema>;
type AccessKey = z.infer<typeof AccessKeySchema>;
type AccessKeyBinding = z.infer<typeof AccessKeyBindingSchema>;

/** The binding's own ranges, or undefined for a plain (`true`) binding. */
export function bindingSourceRanges(
  binding: AccessKeyBinding | undefined
): SourceRanges | undefined {
  return binding === undefined || binding === true ? undefined : binding.sourceRanges;
}

/**
 * The ranges one (key, machine) pair resolves to:
 * `keys[k].machines[m].sourceRanges` ?? `keys[k].sourceRanges` ?? `access.sourceRanges`.
 * Each level replaces the one below whole. Pass no machine for the key's own
 * default (what a new binding without ranges would get).
 */
export function resolveAccessSourceRanges(
  access: { sourceRanges?: SourceRanges; keys?: Record<string, AccessKey> },
  keyName: string,
  machineName?: string
): SourceRanges | undefined {
  const key = access.keys?.[keyName];
  if (key === undefined) return undefined;
  const machineLevel =
    machineName === undefined ? undefined : bindingSourceRanges(key.machines?.[machineName]);
  return machineLevel ?? key.sourceRanges ?? access.sourceRanges;
}

/**
 * Empty resolution: no range at the key or config level, and either no
 * binding or a binding without its own ranges.
 */
function resolvesToNoRange(key: AccessKey, configRanges: SourceRanges | undefined): boolean {
  if ((key.sourceRanges ?? configRanges) !== undefined) return false;
  const bindings = Object.values(key.machines ?? {});
  return bindings.length === 0 || bindings.some((m) => bindingSourceRanges(m) === undefined);
}

export const AccessSchema = z
  .object({
    /** Config-wide default ranges for every access key. */
    sourceRanges: SourceRangesSchema.optional(),
    keys: z.record(resourceName, AccessKeySchema).optional(),
  })
  .superRefine((access, ctx) => {
    const blobOwner = new Map<string, string>();
    for (const [name, key] of Object.entries(access.keys ?? {})) {
      if (resolvesToNoRange(key, access.sourceRanges)) {
        ctx.addIssue({
          code: 'custom',
          path: ['keys', name],
          message: `access key ${name} resolves to no source range; set sourceRanges on the key or on access (an unrestricted key belongs in credentials.ssh)`,
        });
      }
      const raw = parseOpenSshPublicKey(key.publicKey)?.blob;
      const blob = raw === undefined ? null : canonicalKeyBlob(raw);
      if (blob === null) continue;
      const owner = blobOwner.get(blob);
      if (owner === undefined) {
        blobOwner.set(blob, name);
        continue;
      }
      ctx.addIssue({
        code: 'custom',
        path: ['keys', name, 'publicKey'],
        message: `access keys ${owner} and ${name} declare the same public key`,
      });
    }
  });

type AccessConfig = z.infer<typeof AccessSchema>;
type AccessKeyMachine = z.infer<typeof AccessKeyMachineSchema>;

export type { AccessConfig, AccessKey, AccessKeyBinding, AccessKeyMachine, SourceRanges };
