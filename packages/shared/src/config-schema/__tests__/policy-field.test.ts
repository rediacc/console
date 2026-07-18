/**
 * The policy document's place in the config.
 *
 * These tests pin the property that makes executor-enforced authorization
 * trustworthy: the rules are FIELD-COMMITTED. The server holds an HMAC over the
 * current value, so a push that rewrites the rules without knowing what they
 * currently say is rejected.
 *
 * That is the threat that matters here. Nobody is much harmed by reading an
 * org's rules; the harm is someone quietly rewriting them to grant themselves
 * access to every machine. A policy field that was merely `.loose()`-passed
 * through the schema would have been exactly that: present, honored by the
 * executor, and silently rewritable.
 */

import { describe, expect, it } from 'vitest';
import { PolicyDocumentSchema } from '../../policy/index.js';
import { buildCommitEntries } from '../payload.js';
import { parseConfig, type RdcConfig, RdcConfigSchema } from '../schemas.js';
import { pathsToCommit } from '../walker.js';

const POLICY = {
  version: 1 as const,
  defaults: { commands: { allow: ['repo *'], deny: ['repo delete'] } },
  teams: { platform: { commands: { allow: ['*'] }, allowClusterOps: true } },
};

function configWithPolicy(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 1,
    defaults: { language: 'en', datastoreSize: '95%' },
    encryption: { mode: 'plaintext' },
    // Deep-cloned: commit entries hold a live reference to the value, so a
    // shared fixture object would let the "tampered" config mutate the original
    // and hide the very difference this file is testing for.
    policy: structuredClone(POLICY),
  };
}

describe('policy document in the config', () => {
  it('is a typed section of the schema, not a loose passthrough', () => {
    const parsed = parseConfig(RdcConfigSchema, configWithPolicy(), 'test config');
    expect(parsed.policy).toEqual(POLICY);
  });

  it('rejects a malformed rule set at parse time', () => {
    const bad = { ...configWithPolicy(), policy: { version: 99, defaults: 'not-an-object' } };
    expect(() => parseConfig(RdcConfigSchema, bad, 'test config')).toThrow();
  });

  it('is field-committed, so the server can reject a silent rewrite', () => {
    const paths = pathsToCommit(configWithPolicy());
    expect(paths).toContain('/policy');
  });

  it('commits the WHOLE document, so any rule change changes the commitment', () => {
    const before = buildCommitEntries(configWithPolicy());
    const policyEntry = before.find((e) => e.pointer === '/policy');
    expect(policyEntry?.value).toEqual(POLICY);

    // Flip a single rule deep inside the document.
    const tampered = configWithPolicy();
    (tampered.policy as typeof POLICY).defaults.commands.deny = [];

    const after = buildCommitEntries(tampered);
    const tamperedEntry = after.find((e) => e.pointer === '/policy');

    // The committed value differs, so the HMAC differs, so the push is rejected.
    expect(tamperedEntry?.value).not.toEqual(policyEntry?.value);
  });

  it('a config with no policy commits nothing for it', () => {
    const noPolicy = configWithPolicy();
    delete (noPolicy as { policy?: unknown }).policy;
    expect(pathsToCommit(noPolicy)).not.toContain('/policy');
  });

  it('the schema accepts exactly what the policy engine validates', () => {
    // One definition, two consumers: if these ever diverged, the executor could
    // honor a document the config would not store, or vice versa.
    expect(PolicyDocumentSchema.safeParse(POLICY).success).toBe(true);
  });
});
