/**
 * The pure parts of `rdc server`: the secrets.env stdin, the cert codec, preflight facts, sizes,
 * store domains, image tags and certificate coverage.
 */

import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));

import { envStdin, parseEnvLines } from '../box-scripts.js';
import { assertCertKey, CertError, decodeCert, parseSignedCert } from '../cert.js';
import { imageTag, storeDomainOf } from '../common.js';
import { ownedZoneOf } from '../dns.js';
import { covers } from '../http.js';
import { parsePreflight, preflightProblems, sizeGib } from '../preflight.js';
import { certFor } from './fakes.js';

describe('secrets.env lines', () => {
  it('refuses a value compose or bash would read specially, naming the key only', () => {
    expect(() => envStdin({ TAG: 'a b' })).toThrow(/^TAG /);
    expect(() => envStdin({ TAG: '$(id)' })).not.toThrow(/\$\(id\)/);
    expect(envStdin({ TAG: 'v1', ELITE_IMAGE: 'ghcr.io/x:1' })).toBe(
      'TAG=v1\nELITE_IMAGE=ghcr.io/x:1\n'
    );
  });

  it('parses KEY=value lines, keeping = inside values', () => {
    expect(parseEnvLines('A=b==\nnoise\nB="q"\n')).toEqual({ A: 'b==', B: 'q' });
  });
});

describe('certificates', () => {
  it('reads the base64 form, the JSON form and an answer carrying cert', () => {
    const b64 = certFor('k', 's');
    const json = Buffer.from(b64, 'base64').toString();
    for (const text of [b64, json, JSON.stringify({ cert: JSON.parse(json) })]) {
      expect(decodeCert(parseSignedCert(text)).subscriptionId).toBe('s');
    }
  });

  it('refuses a cert for another key', () => {
    const cert = decodeCert(parseSignedCert(certFor('k')));
    expect(() => assertCertKey(cert, 'other')).toThrow(CertError);
  });
});

describe('preflight', () => {
  const ok = {
    sudo: '1',
    arch: 'aarch64',
    epoch: '1000',
    renet: '0',
    free_kb: String(20 * 1024 * 1024),
  };
  const text = (o: Record<string, string>) =>
    Object.entries(o)
      .map(([k, v]) => `${k}=${v}`)
      .join('\n');

  it('passes a ready box', () => {
    const facts = parsePreflight(`${text(ok)}\nport80=\nport443=`);
    expect(preflightProblems(facts, { machine: 'm', size: '10G', now: 1_000_000 })).toEqual([]);
  });

  it('refuses a proxy-looking holder when renet is not there', () => {
    const facts = parsePreflight(`${text(ok)}\nport80=users:(("traefik",pid=1,fd=3))`);
    const problems = preflightProblems(facts, { machine: 'm', size: '10G', now: 1_000_000 });
    expect(problems.join()).toMatch(/portBusy/);
  });

  it('reads sizes in GiB', () => {
    expect(sizeGib('10G')).toBe(10);
    expect(sizeGib('512M')).toBe(0.5);
    expect(sizeGib('1T')).toBe(1024);
  });
});

describe('names', () => {
  it('derives the store domain and the image tag', () => {
    expect(storeDomainOf('acme.example.com')).toBe('acme-store.example.com');
    expect(imageTag('ghcr.io/rediacc/server:2.1')).toBe('2.1');
    expect(imageTag('localhost:5000/server')).toBe('latest');
    expect(imageTag('ghcr.io/x@sha256:ab')).toBe('latest');
  });

  it('knows which zones Rediacc owns, and no other', () => {
    expect(ownedZoneOf('acme.rediacc.io')).toBe('rediacc.io');
    expect(ownedZoneOf('acme.rediacc.cloud')).toBe('rediacc.cloud');
    expect(ownedZoneOf('acme.notrediacc.io')).toBeUndefined();
    expect(ownedZoneOf('rediacc.io.example.com')).toBeUndefined();
  });

  it('matches certificate names exactly or by a one-label wildcard', () => {
    expect(covers(['acme.example.com'], 'acme.example.com')).toBe(true);
    expect(covers(['*.example.com'], 'acme.example.com')).toBe(true);
    expect(covers(['*.example.com'], 'a.b.example.com')).toBe(false);
    expect(covers([], 'acme.example.com')).toBe(false);
  });
});

describe('the elite template', () => {
  const dir = new URL('../../../../templates/elite/', import.meta.url);
  const read = (name: string) => readFileSync(new URL(name, dir), 'utf8');

  it('Rediaccfile starts the free tier when no delegation cert is present', () => {
    const work = mkdtempSync(join(tmpdir(), 'elite-'));
    writeFileSync(join(work, 'secrets.env'), 'ELITE_DOMAIN=a\n');
    const script = `cd "$1"; source "$2"; REQUIRED_VARS=(ELITE_DOMAIN); load_secrets`;
    const result = spawnSync(
      'bash',
      ['-c', script, 'x', work, fileURLToPath(new URL('Rediaccfile', dir))],
      { encoding: 'utf8' }
    );
    expect(result.status).toBe(0);
    expect(result.stderr).toContain('free tier');
  });

  it('labels both routed services with the ELITE_TLS value, empty by default', () => {
    expect(read('docker-compose.yml').match(/"rediacc\.tls=\$\{ELITE_TLS:-\}"/g)).toHaveLength(2);
  });

  it('passes ROOT_EMAIL and the ON_PREMISE_* variables through to the web service', () => {
    const text = read('docker-compose.yml');
    for (const key of ['ROOT_EMAIL', 'ON_PREMISE_MODE', 'ON_PREMISE_PRIVATE_KEY', 'ON_PREMISE_PUBLIC_KEY']) {
      expect(text).toContain(`- ${key}=\${${key}:-`);
    }
  });
});
