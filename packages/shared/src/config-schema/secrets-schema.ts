/**
 * The per-repo secrets map: entry and key schemas, the size caps and the aggregate cap
 * (split out of schemas.ts, which stays under the max-lines budget).
 */

import { z } from 'zod';
import { utf8ByteLength } from './primitives.js';

// Per-repo secrets. Two delivery modes:
//   env  → injected as REDIACC_SECRET_<KEY> in the renet shell (compose `${VAR}`).
// file → tmpfs file at /var/run/rediacc/net-<networkId>/secrets/<KEY> on the target machine, referenced by Docker compose `secrets:` block. Fork isolation: registerFork does NOT copy `secrets`; a fork's map is empty.
const SECRET_KEY_REGEX = /^[A-Z][A-Z0-9_]*$/;

// Size caps (gate C11, merged with spec 05). The config file is atomically rewritten and remote-pushed WHOLE on every mutation, and each mode materializes as one k8s Secret object per repo namespace (~1 MiB apiserver cap), so anything larger is a file the data plane should carry.
export const SECRET_ENV_VALUE_MAX_BYTES = 32 * 1024; // 32 KiB per env value
export const SECRET_FILE_VALUE_MAX_BYTES = 256 * 1024; // 256 KiB per file value
export const SECRET_AGGREGATE_MAX_BYTES = 512 * 1024; // 512 KiB per repo per mode

export const SecretEntrySchema = z
  .object({
    mode: z.enum(['env', 'file']),
    value: z.string().min(1, 'Secret value cannot be empty'),
  })
  .superRefine((entry, ctx) => {
    const bytes = utf8ByteLength(entry.value);
    const cap = entry.mode === 'env' ? SECRET_ENV_VALUE_MAX_BYTES : SECRET_FILE_VALUE_MAX_BYTES;
    if (bytes > cap) {
      ctx.addIssue({
        code: 'custom',
        path: ['value'],
        message: `Secret value is ${bytes} bytes; the ${entry.mode}-mode cap is ${cap} bytes. Carry larger payloads on the data plane, not in config.`,
      });
    }
  });

export const SecretKeySchema = z
  .string()
  .min(1)
  .max(64, 'Secret key must be 64 characters or fewer')
  .regex(SECRET_KEY_REGEX, 'Secret key must be UPPER_SNAKE_CASE (uppercase letter then [A-Z0-9_])');

export const SecretsRecordSchema = z
  .record(SecretKeySchema, SecretEntrySchema)
  .superRefine((rec, ctx) => {
    let envTotal = 0;
    let fileTotal = 0;
    for (const entry of Object.values(rec)) {
      const bytes = utf8ByteLength(entry.value);
      if (entry.mode === 'env') envTotal += bytes;
      else fileTotal += bytes;
    }
    if (envTotal > SECRET_AGGREGATE_MAX_BYTES) {
      ctx.addIssue({
        code: 'custom',
        message: `env-mode secrets total ${envTotal} bytes; the per-repo aggregate cap is ${SECRET_AGGREGATE_MAX_BYTES} bytes.`,
      });
    }
    if (fileTotal > SECRET_AGGREGATE_MAX_BYTES) {
      ctx.addIssue({
        code: 'custom',
        message: `file-mode secrets total ${fileTotal} bytes; the per-repo aggregate cap is ${SECRET_AGGREGATE_MAX_BYTES} bytes.`,
      });
    }
  });
