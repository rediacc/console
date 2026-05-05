import { describe, expect, it } from 'vitest';
import { parseCertAnchor } from '../cert-anchor.js';

const BASE = 'rediacc.io';

describe('parseCertAnchor', () => {
  it('classifies the apex', () => {
    expect(parseCertAnchor('rediacc.io', BASE).kind).toBe('apex');
  });

  it('classifies the root wildcard', () => {
    expect(parseCertAnchor('*.rediacc.io', BASE).kind).toBe('root');
  });

  it('classifies a single-label top-level subdomain', () => {
    const a = parseCertAnchor('cloud.rediacc.io', BASE);
    expect(a.kind).toBe('top-level');
    expect(a.anchor).toBe('cloud');
  });

  it('classifies a machine-scoped wildcard', () => {
    const a = parseCertAnchor('*.hostinger.rediacc.io', BASE);
    expect(a.kind).toBe('machine');
    expect(a.anchor).toBe('hostinger');
  });

  it('classifies a service.machine subdomain', () => {
    const a = parseCertAnchor('erp.hostinger.rediacc.io', BASE);
    expect(a.kind).toBe('service');
    expect(a.anchor).toBe('erp');
    expect(a.machine).toBe('hostinger');
  });

  it('classifies a GUID-wildcard as guid + machine', () => {
    const a = parseCertAnchor('*.92b2fc75-f33a-435b-a3f5-b57bf625024c.hostinger.rediacc.io', BASE);
    expect(a.kind).toBe('guid');
    expect(a.anchor).toBe('92b2fc75-f33a-435b-a3f5-b57bf625024c');
    expect(a.machine).toBe('hostinger');
  });

  it('classifies a repo-name wildcard as repo-name + machine', () => {
    // Same shape as the GUID case but with a non-GUID head label.
    const a = parseCertAnchor('*.demo-stackoverflow.hostinger.rediacc.io', BASE);
    expect(a.kind).toBe('repo-name');
    expect(a.anchor).toBe('demo-stackoverflow');
    expect(a.machine).toBe('hostinger');
  });

  it('returns opaque for a different base domain', () => {
    expect(parseCertAnchor('foo.example.com', BASE).kind).toBe('opaque');
  });

  it('returns opaque for a deeper wildcard chain', () => {
    expect(parseCertAnchor('*.a.b.c.rediacc.io', BASE).kind).toBe('opaque');
  });

  it('preserves the raw input on every classification', () => {
    const a = parseCertAnchor('*.hostinger.rediacc.io', BASE);
    expect(a.raw).toBe('*.hostinger.rediacc.io');
  });
});
