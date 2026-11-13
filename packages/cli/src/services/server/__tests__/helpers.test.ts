/**
 * The pure parts of `rdc server`: the secrets.env stdin, the cert codec, preflight facts, sizes,
 * store domains, image tags and certificate coverage.
 */

import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  WK_IMAGE_REGISTRY,
  WK_INFRA_DOMAIN,
  WK_PRODUCT_DOMAIN,
} from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));

import {
  envStdin,
  INBOX_DROP,
  INBOX_RESULT,
  MIGRATE_ENV_CERT,
  parseEnvLines,
  READ_LIVE_CERT,
} from '../box-scripts.js';
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
    expect(imageTag(`${WK_IMAGE_REGISTRY}/server:2.1`)).toBe('2.1');
    expect(imageTag('localhost:5000/server')).toBe('latest');
    expect(imageTag('ghcr.io/x@sha256:ab')).toBe('latest');
  });

  it('knows which zones Rediacc owns, and no other', () => {
    expect(ownedZoneOf(`acme.${WK_INFRA_DOMAIN}`)).toBe(WK_INFRA_DOMAIN);
    expect(ownedZoneOf(`acme.${WK_PRODUCT_DOMAIN}`)).toBe(WK_PRODUCT_DOMAIN);
    expect(ownedZoneOf('acme.notrediacc.io')).toBeUndefined();
    expect(ownedZoneOf(`${WK_INFRA_DOMAIN}.example.com`)).toBeUndefined();
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

  const rediaccfile = (work: string, script: string) =>
    spawnSync('bash', ['-c', script, 'x', work, fileURLToPath(new URL('Rediaccfile', dir))], {
      encoding: 'utf8',
    });

  it('Rediaccfile starts the free tier when no live cert file is present', () => {
    const work = mkdtempSync(join(tmpdir(), 'elite-'));
    writeFileSync(join(work, 'secrets.env'), 'ELITE_DOMAIN=a\n');
    const result = rediaccfile(
      work,
      'cd "$1"; source "$2"; REQUIRED_VARS=(ELITE_DOMAIN); load_secrets'
    );
    expect(result.status).toBe(0);
    expect(result.stderr).toContain('free tier');
  });

  it('Rediaccfile reads only the live file: a DELEGATION_CERT_BASE64 left in secrets.env is the free tier', () => {
    const work = mkdtempSync(join(tmpdir(), 'elite-'));
    writeFileSync(join(work, 'secrets.env'), 'ELITE_DOMAIN=a\nDELEGATION_CERT_BASE64=abc\n');
    const free = rediaccfile(
      work,
      'cd "$1"; source "$2"; REQUIRED_VARS=(ELITE_DOMAIN); load_secrets'
    );
    expect(free.stderr).toContain('free tier');
    mkdirSync(join(work, 'data/web'), { recursive: true });
    writeFileSync(join(work, 'data/web/delegation-cert.json'), '{}');
    const held = rediaccfile(
      work,
      'cd "$1"; source "$2"; REQUIRED_VARS=(ELITE_DOMAIN); load_secrets'
    );
    expect(held.status).toBe(0);
    expect(held.stderr).not.toContain('free tier');
  });

  it('up creates data/web/cert-inbox at mode 0700', () => {
    const work = mkdtempSync(join(tmpdir(), 'elite-'));
    writeFileSync(join(work, 'secrets.env'), 'ELITE_DOMAIN=a\n');
    const script =
      'cd "$1"; source "$2"; REQUIRED_VARS=(ELITE_DOMAIN); load_images() { :; }; renet() { :; }; up';
    const result = rediaccfile(work, script);
    expect(result.status).toBe(0);
    expect(statSync(join(work, 'data/web/cert-inbox')).mode & 0o777).toBe(0o700);
  });

  it('up stops before compose when the cert inbox cannot be created', () => {
    const work = mkdtempSync(join(tmpdir(), 'elite-'));
    writeFileSync(join(work, 'secrets.env'), 'ELITE_DOMAIN=a\n');
    mkdirSync(join(work, 'data/web'), { recursive: true });
    writeFileSync(join(work, 'data/web/cert-inbox'), 'in the way');
    const script =
      'cd "$1"; source "$2"; REQUIRED_VARS=(ELITE_DOMAIN); load_images() { :; }; renet() { echo ran > ran; }; up';
    const result = rediaccfile(work, script);
    expect(result.status).not.toBe(0);
    expect(existsSync(join(work, 'ran'))).toBe(false);
  });

  describe('load_images', () => {
    // docker is a shell function over a "present" file: `image inspect` succeeds for a listed ref,
    // `load` makes the tar's own refs present, `pull` is recorded.
    const run = (setup: { manifest?: string; tarHolds?: string; offline?: boolean }) => {
      const work = mkdtempSync(join(tmpdir(), 'elite-'));
      mkdirSync(join(work, 'images'));
      writeFileSync(join(work, 'images/server.tar'), '');
      if (setup.manifest !== undefined)
        writeFileSync(join(work, 'images/manifest.txt'), setup.manifest);
      const script = [
        'cd "$1"; source "$2"; TAG=1; : > present; : > pulled',
        setup.offline ? 'ELITE_OFFLINE=1' : ':',
        `docker() { case "$1" in image) grep -qx "$3" present;; load) echo '${setup.tarHolds ?? ''}' >> present;; pull) echo "$2" >> pulled;; esac; }`,
        'load_images; echo "rc=$?"; echo "pulled=$(cat pulled)"',
      ].join('\n');
      const result = rediaccfile(work, script);
      return { out: result.stdout, err: result.stderr };
    };
    const REF = 'ghcr.io/rediacc/server:1';

    it('serves the image from a tar whose manifest ref the load makes present', () => {
      const r = run({ manifest: `server.tar ${REF}\n`, tarHolds: REF });
      expect(r.out).toContain('rc=0');
      expect(r.out).toContain('pulled=\n');
    });

    it('pulls when the tar did not bring the manifest ref', () => {
      const r = run({ manifest: `server.tar ${REF}\n`, tarHolds: 'other:1' });
      expect(r.out).toContain('rc=0');
      expect(r.out).toContain(`pulled=${REF}`);
    });

    it('refuses under ELITE_OFFLINE when the tar did not bring the manifest ref', () => {
      const r = run({ manifest: `server.tar ${REF}\n`, tarHolds: 'other:1', offline: true });
      expect(r.out).toContain('rc=1');
      expect(r.err).toContain('ELITE_OFFLINE=1');
      expect(r.out).toContain('pulled=\n');
    });

    it('refuses a tar the manifest does not name', () => {
      const r = run({ manifest: 'other.tar x:1\n' });
      expect(r.out).toContain('rc=1');
      expect(r.err).toContain('has no ref for images/server.tar');
    });
  });

  it('health resolves the domain to this machine and trusts ELITE_CA_FILE when set', () => {
    const work = mkdtempSync(join(tmpdir(), 'elite-'));
    writeFileSync(join(work, 'secrets.env'), 'ELITE_DOMAIN=acme.example.com\n');
    const script =
      'cd "$1"; source "$2"; REQUIRED_VARS=(ELITE_DOMAIN); curl() { printf "%s\n" "$@" >&2; }; health; ELITE_CA_FILE=/ca.pem health';
    const lines = rediaccfile(work, script).stderr.split('\n');
    expect(lines).toContain('acme.example.com:443:127.0.0.1');
    expect(lines).toContain('https://acme.example.com/health');
    expect(lines.filter((l) => l === '--cacert')).toHaveLength(1);
    expect(lines).toContain('/ca.pem');
  });

  it('web waits for the bucket init to complete', () => {
    const text = read('docker-compose.yml');
    expect(text).toMatch(/rustfs-init:\n\s+condition: service_completed_successfully/);
  });

  it('the compose file carries no DELEGATION_CERT_BASE64, and ON_PREMISE_MODE defaults to true', () => {
    const text = read('docker-compose.yml');
    expect(text).not.toContain('DELEGATION_CERT_BASE64');
    expect(text).toContain('- ON_PREMISE_MODE=${ON_PREMISE_MODE:-true}');
    expect(read('secrets.env.example')).not.toContain('DELEGATION_CERT_BASE64');
    expect(read('VERSION').trim()).toBe('4');
  });

  it('labels both routed services with the ELITE_TLS value, empty by default', () => {
    expect(read('docker-compose.yml').match(/"rediacc\.tls=\$\{ELITE_TLS:-\}"/g)).toHaveLength(2);
  });

  it('passes ROOT_EMAIL and the ON_PREMISE_* variables through to the web service', () => {
    const text = read('docker-compose.yml');
    for (const key of [
      'ROOT_EMAIL',
      'ON_PREMISE_MODE',
      'ON_PREMISE_PRIVATE_KEY',
      'ON_PREMISE_PUBLIC_KEY',
    ]) {
      expect(text).toContain(`- ${key}=\${${key}:-`);
    }
    expect(text).toContain('- ON_PREMISE_MODE=${ON_PREMISE_MODE:-true}');
  });
});

describe('the cert inbox scripts, run in a real shell', () => {
  const run = (script: string, work: string, stdin = '') =>
    spawnSync('sh', ['-c', script, 'server', work], { input: stdin, encoding: 'utf8' });
  const inbox = (work: string, name = '') => join(work, 'data/web/cert-inbox', name);
  const cert = { payload: 'cA==', signature: 'cw==', publicKeyId: 'k' };

  it('INBOX_DROP writes new.json through a .tmp in a 0700 inbox, and refuses while a drop waits', () => {
    const work = mkdtempSync(join(tmpdir(), 'inbox-'));
    const body = `${JSON.stringify({ requestId: 'r1', cert })}\n`;
    const first = run(INBOX_DROP, work, body);
    expect(first.status).toBe(0);
    expect(first.stdout.trim()).toBe('inbox=dropped');
    expect(statSync(inbox(work)).mode & 0o777).toBe(0o700);
    expect(statSync(inbox(work, 'new.json')).mode & 0o777).toBe(0o600);
    expect(readFileSync(inbox(work, 'new.json'), 'utf8')).toBe(body);
    expect(existsSync(inbox(work, 'new.json.tmp'))).toBe(false);

    const second = run(INBOX_DROP, work, '{"requestId":"r2"}\n');
    expect(second.stdout.trim()).toBe('inbox=busy');
    expect(readFileSync(inbox(work, 'new.json'), 'utf8')).toBe(body);
  });

  it('INBOX_DROP refuses while the server holds processing.json', () => {
    const work = mkdtempSync(join(tmpdir(), 'inbox-'));
    mkdirSync(inbox(work), { recursive: true });
    writeFileSync(inbox(work, 'processing.json'), '{}');
    expect(run(INBOX_DROP, work, '{}\n').stdout.trim()).toBe('inbox=busy');
    expect(existsSync(inbox(work, 'new.json'))).toBe(false);
  });

  it('INBOX_RESULT answers only for its own request id', () => {
    const work = mkdtempSync(join(tmpdir(), 'inbox-'));
    mkdirSync(inbox(work), { recursive: true });
    const applied = { requestId: 'mine', certId: 'abcd', issuedAt: '2026-11-12T00:00:00Z' };
    writeFileSync(inbox(work, 'applied.json'), `${JSON.stringify(applied, null, 2)}\n`);
    const out = run(INBOX_RESULT, work, 'mine\n');
    expect(out.status).toBe(0);
    const [head, ...rest] = out.stdout.split('\n');
    expect(head).toBe('result=applied');
    expect(JSON.parse(rest.join('\n'))).toEqual(applied);
    const rejected = { requestId: 'theirs', reason: 'not-newer', detail: 'x' };
    writeFileSync(inbox(work, 'rejected.json'), JSON.stringify(rejected, null, 2));
    expect(run(INBOX_RESULT, work, 'theirs\n').stdout.split('\n')[0]).toBe('result=rejected');
  });

  it('MIGRATE_ENV_CERT drops the env cert when no live file exists, and removes the key', () => {
    const work = mkdtempSync(join(tmpdir(), 'inbox-'));
    const b64 = Buffer.from(JSON.stringify(cert)).toString('base64');
    writeFileSync(
      join(work, 'secrets.env'),
      `TAG=1\nDELEGATION_CERT_BASE64=${b64}\nROOT_EMAIL=a@b\n`
    );
    const out = run(MIGRATE_ENV_CERT, work, 'req-9\n');
    expect(out.status).toBe(0);
    expect(out.stdout.trim()).toBe('migrate=dropped');
    expect(JSON.parse(readFileSync(inbox(work, 'new.json'), 'utf8'))).toEqual({
      requestId: 'req-9',
      cert,
    });
    expect(readFileSync(join(work, 'secrets.env'), 'utf8')).toBe('TAG=1\nROOT_EMAIL=a@b\n');
    expect(statSync(join(work, 'secrets.env')).mode & 0o777).toBe(0o600);
  });

  it('MIGRATE_ENV_CERT only removes the key when a live file exists', () => {
    const work = mkdtempSync(join(tmpdir(), 'inbox-'));
    mkdirSync(join(work, 'data/web'), { recursive: true });
    writeFileSync(join(work, 'data/web/delegation-cert.json'), '{}');
    writeFileSync(join(work, 'secrets.env'), 'DELEGATION_CERT_BASE64=eA==\n');
    expect(run(MIGRATE_ENV_CERT, work, 'r\n').stdout.trim()).toBe('migrate=none');
    expect(existsSync(inbox(work, 'new.json'))).toBe(false);
    expect(readFileSync(join(work, 'secrets.env'), 'utf8')).toBe('');
  });

  it('READ_LIVE_CERT prints the live file, and nothing without one', () => {
    const work = mkdtempSync(join(tmpdir(), 'inbox-'));
    expect(run(READ_LIVE_CERT, work).stdout).toBe('');
    mkdirSync(join(work, 'data/web'), { recursive: true });
    writeFileSync(join(work, 'data/web/delegation-cert.json'), JSON.stringify(cert));
    expect(JSON.parse(run(READ_LIVE_CERT, work).stdout)).toEqual(cert);
  });
});
