#!/usr/bin/env tsx
/**
 * check-ceph-image-pin — the Ceph container pin must be current, and must agree
 * with the code that uses it.
 *
 * WHY THIS EXISTS. `cephadm bootstrap` builds the cluster from a container image
 * while the host parses the admin keyring with apt's `ceph-common`. If the
 * cluster is a newer major than the client, the key it mints is unreadable: Ceph
 * 20 writes a 32-byte type-2 admin key, and a 19.x client reports `Malformed
 * input [buffer:3]` followed by the far less helpful `monclient: keyring not
 * found`.
 *
 * That is not hypothetical. On 2026-08-19 quay.io rebuilt every floating Ceph
 * tag in place (v19, v19.2, v19.2.6, v20, v20.2, v20.2.4 all report "modified
 * Wed, 19 Aug 2026"). The identical console commit passed all seven E2E jobs on
 * 2026-08-19 and failed four of them on 2026-08-20, with no change on either
 * side. Ubuntu noble's ceph-common had not moved since 2026-02-24.
 *
 * A pin fixes that, and then quietly rots: when Ubuntu moves to a 20.x line the
 * pin must move WITH it or the same skew reappears in the opposite direction. So
 * this gate enforces two things a pin cannot enforce about itself:
 *
 *   1. the review date has not passed, and
 *   2. the pin file and the Go constant still name the SAME image.
 *
 * The non-apt hosts (Fedora, EL10, Leap) install the same release from their own
 * repositories, pinned per distro in the `host.<target>` lines and mirrored in
 * the hostPins table of pkg/infra/cephpkg/cephpkg.go, so it also enforces:
 *
 *   3. every host.* line's upstream version (epoch and release stripped) equals
 *      host-version, and equals the Go table's entry for that target, and
 *   4. no key-expiry.* date is within 30 days or past (the OBS signing key that
 *      Leap trusts expires 2027-05-07).
 *
 * Both are text checks. It deliberately does NOT query the registry or a worker:
 * a gate that needs the network fails for reasons that have nothing to do with
 * the thing it guards, and this one runs in the default CI job.
 *
 * Usage: npx tsx scripts/gates/check-ceph-image-pin.ts [--selftest]
 * Exit 0 ok, 1 stale or disagreeing, 2 the check itself could not run.
 *
 * ---- gate ----
 * step: Ceph image pin freshness
 * needs: node, submodules
 * ---- end gate ----
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const PIN_FILE = path.join(ROOT, 'private/renet/.ceph-image-pin');
const GO_FILE = path.join(ROOT, 'private/renet/pkg/infra/ceph/provisioner.go');
const CEPHPKG_FILE = path.join(ROOT, 'private/renet/pkg/infra/cephpkg/cephpkg.go');
const EXPIRY_WARN_DAYS = 30;

export interface Pin {
  image?: string;
  review?: string;
  hostVersion?: string;
  /** host.<target> lines: target -> exact package version. */
  hosts: Record<string, string>;
  /** key-expiry.<name> lines: name -> YYYY-MM-DD. */
  keyExpiry: Record<string, string>;
}

export function parsePin(text: string): Pin {
  const out: Pin = { hosts: {}, keyExpiry: {} };
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const eq = t.indexOf('=');
    if (eq < 0) continue;
    const k = t.slice(0, eq).trim();
    const v = t.slice(eq + 1).trim();
    if (k === 'image') out.image = v;
    else if (k === 'review') out.review = v;
    else if (k === 'host-version') out.hostVersion = v;
    else if (k.startsWith('host.')) out.hosts[k.slice('host.'.length)] = v;
    else if (k.startsWith('key-expiry.')) out.keyExpiry[k.slice('key-expiry.'.length)] = v;
  }
  return out;
}

/** The image named by the Go constant, or undefined when it is absent. */
export function goPinnedImage(src: string): string | undefined {
  return /CephImagePin\s*=\s*"([^"]+)"/.exec(src)?.[1];
}

/** The hostPins table in cephpkg.go: target -> version, or undefined when absent. */
export function goHostPins(src: string): Record<string, string> | undefined {
  const block = /hostPins\s*=\s*map\[string\]string\{([^}]*)\}/.exec(src)?.[1];
  if (block === undefined) return undefined;
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/"([^"]+)"\s*:\s*"([^"]+)"/g)) out[m[1]] = m[2];
  return out;
}

/** Upstream version of a package version: epoch and release stripped. */
export function upstreamVersion(v: string): string {
  const noEpoch = v.includes(':') ? v.slice(v.indexOf(':') + 1) : v;
  const dash = noEpoch.indexOf('-');
  return dash < 0 ? noEpoch : noEpoch.slice(0, dash);
}

/** Problems with the host.* lines against host-version and the Go table. */
export function hostProblems(pin: Pin, goPins: Record<string, string> | undefined): string[] {
  const out: string[] = [];
  const targets = Object.keys(pin.hosts);
  if (targets.length === 0) out.push('the pin file has no host.<target> lines');
  for (const t of targets) {
    const v = pin.hosts[t];
    if (pin.hostVersion && upstreamVersion(v) !== pin.hostVersion) {
      out.push(
        `host.${t}=${v} is upstream ${upstreamVersion(v)}, but host-version is ${pin.hostVersion}`
      );
    }
    if (goPins && goPins[t] !== v) {
      out.push(
        `host.${t}: the pin file says ${v} but the hostPins table in cephpkg.go says ${goPins[t] ?? '(no entry)'}`
      );
    }
  }
  if (goPins) {
    for (const t of Object.keys(goPins)) {
      if (!(t in pin.hosts)) {
        out.push(`cephpkg.go pins ${t}=${goPins[t]} but the pin file has no host.${t} line`);
      }
    }
  }
  return out;
}

/** Problems with key-expiry.* dates: within the warning window, or past. */
export function expiryProblems(pin: Pin, today: Date): string[] {
  const out: string[] = [];
  for (const [name, date] of Object.entries(pin.keyExpiry)) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      out.push(`key-expiry.${name}=${date} is not a YYYY-MM-DD date`);
      continue;
    }
    const left = daysUntil(date, today);
    if (left < 0) {
      out.push(`the ${name} signing key EXPIRED ${-left} day(s) ago (key-expiry.${name}=${date})`);
    } else if (left <= EXPIRY_WARN_DAYS) {
      out.push(
        `the ${name} signing key expires in ${left} day(s) (key-expiry.${name}=${date}); replace it in pkg/infra/cephpkg/keys`
      );
    }
  }
  return out;
}

/** A floating tag is one with no date suffix; those are rebuilt in place. */
export function isFloatingTag(image: string): boolean {
  const tag = image.slice(image.lastIndexOf(':') + 1);
  return !/-\d{8}$/.test(tag);
}

export function daysUntil(review: string, today: Date): number {
  const d = new Date(`${review}T00:00:00Z`);
  return Math.floor((d.getTime() - today.getTime()) / 86_400_000);
}

const HEALTHY_PIN = [
  'host-version=19.2.3',
  'host.ubuntu=19.2.3-0ubuntu0.24.04.3',
  'host.fedora-43=19.2.3-8.fc43',
  'host.el10=2:19.2.3-1.el10s',
  'host.opensuse-16.0=19.2.3-lp160.2.98',
  'key-expiry.obs=2027-05-07',
].join('\n');
const HEALTHY_GO = `var hostPins = map[string]string{
	"ubuntu":        "19.2.3-0ubuntu0.24.04.3",
	"fedora-43":     "19.2.3-8.fc43",
	"el10":          "2:19.2.3-1.el10s",
	"opensuse-16.0": "19.2.3-lp160.2.98",
}`;
const TODAY = new Date('2026-09-29T00:00:00Z');

function selftest(): boolean {
  const cases: { name: string; ok: boolean }[] = [
    {
      name: 'parses image and review',
      ok: parsePin('image=a:b\nreview=2026-01-01').image === 'a:b',
    },
    {
      name: 'ignores comments and blanks',
      ok: parsePin('# image=nope\n\nimage=real:v1').image === 'real:v1',
    },
    {
      name: 'CONTROL: a past review date is reported as overdue',
      ok: daysUntil('2026-01-01', new Date('2026-06-01T00:00:00Z')) < 0,
    },
    {
      name: 'a future review date is NOT overdue (control)',
      ok: daysUntil('2026-12-01', new Date('2026-06-01T00:00:00Z')) > 0,
    },
    {
      name: 'CONTROL: a floating tag IS reported',
      ok: isFloatingTag('quay.io/ceph/ceph:v19.2.6'),
    },
    {
      name: 'a dated tag is NOT reported (control)',
      ok: !isFloatingTag('quay.io/ceph/ceph:v19.2.6-20260818'),
    },
    {
      name: 'reads the Go constant',
      ok:
        goPinnedImage('const CephImagePin = "quay.io/ceph/ceph:v19.2.6-20260818"') ===
        'quay.io/ceph/ceph:v19.2.6-20260818',
    },
    {
      name: 'CONTROL: a missing Go constant is undefined, not an empty match',
      ok: goPinnedImage('const Something = "x"') === undefined,
    },
    {
      name: 'parses host.*, host-version and key-expiry.* lines',
      ok:
        parsePin(HEALTHY_PIN).hosts['el10'] === '2:19.2.3-1.el10s' &&
        parsePin(HEALTHY_PIN).hostVersion === '19.2.3' &&
        parsePin(HEALTHY_PIN).keyExpiry['obs'] === '2027-05-07',
    },
    {
      name: 'strips epoch and release to the upstream version',
      ok:
        upstreamVersion('2:19.2.3-1.el10s') === '19.2.3' &&
        upstreamVersion('19.2.3-0ubuntu0.24.04.3') === '19.2.3',
    },
    {
      name: 'reads the hostPins table',
      ok: goHostPins(HEALTHY_GO)?.['fedora-43'] === '19.2.3-8.fc43',
    },
    {
      name: 'CONTROL: a missing hostPins table is undefined',
      ok: goHostPins('const x = "y"') === undefined,
    },
    {
      name: 'the healthy fixture has no host problems and no expiry problems (control)',
      ok:
        hostProblems(parsePin(HEALTHY_PIN), goHostPins(HEALTHY_GO)).length === 0 &&
        expiryProblems(parsePin(HEALTHY_PIN), TODAY).length === 0,
    },
    {
      name: 'CONTROL: one host line at 19.2.6 is reported',
      ok:
        hostProblems(
          parsePin(
            HEALTHY_PIN.replace('host.fedora-43=19.2.3-8.fc43', 'host.fedora-43=19.2.6-1.fc43')
          ),
          undefined
        ).length === 1,
    },
    {
      name: 'CONTROL: a Go table at a different version than the file is reported',
      ok:
        hostProblems(
          parsePin(HEALTHY_PIN),
          goHostPins(HEALTHY_GO.replace('19.2.3-lp160.2.98', '19.2.6-lp160.1.1'))
        ).length === 1,
    },
    {
      name: 'CONTROL: a Go table target missing from the file is reported',
      ok:
        hostProblems(parsePin(HEALTHY_PIN.replace(/host\.el10=.*\n/, '')), goHostPins(HEALTHY_GO))
          .length >= 1,
    },
    {
      name: 'CONTROL: a key expiring inside 30 days is reported',
      ok:
        expiryProblems(parsePin(HEALTHY_PIN), new Date('2027-04-20T00:00:00Z')).length === 1 &&
        expiryProblems(parsePin(HEALTHY_PIN), new Date('2027-05-08T00:00:00Z')).length === 1,
    },
    {
      name: 'a key expiring in 31 days is NOT reported (control)',
      ok: expiryProblems(parsePin(HEALTHY_PIN), new Date('2027-04-06T00:00:00Z')).length === 0,
    },
  ];
  let bad = 0;
  for (const c of cases) {
    console.log(`  ${c.ok ? 'PASS' : 'FAIL'}  ${c.name}`);
    if (!c.ok) bad++;
  }
  return bad === 0;
}

function main(): number {
  if (!selftest()) {
    console.error('\n✗ self-test failed; refusing to give a verdict.');
    return 2;
  }
  if (process.argv.includes('--selftest')) return 0;

  if (!fs.existsSync(PIN_FILE)) {
    console.error(`✗ ${path.relative(ROOT, PIN_FILE)} is missing.`);
    console.error('  The pin file IS the review mechanism; without it the image floats again.');
    return 1;
  }
  if (!fs.existsSync(GO_FILE)) {
    console.error(`✗ ${path.relative(ROOT, GO_FILE)} is missing (submodule not checked out?).`);
    console.error('  Refusing to pass: this gate cannot verify agreement it never read.');
    return 2;
  }

  const pin = parsePin(fs.readFileSync(PIN_FILE, 'utf8'));
  const goImage = goPinnedImage(fs.readFileSync(GO_FILE, 'utf8'));
  const problems: string[] = [];

  if (!fs.existsSync(CEPHPKG_FILE)) {
    console.error(
      `✗ ${path.relative(ROOT, CEPHPKG_FILE)} is missing (submodule not checked out?).`
    );
    console.error('  Refusing to pass: this gate cannot verify the host pins it never read.');
    return 2;
  }
  const goPins = goHostPins(fs.readFileSync(CEPHPKG_FILE, 'utf8'));
  if (!pin.hostVersion) problems.push('the pin file has no host-version= line');
  if (!goPins)
    problems.push(
      'cephpkg.go no longer defines the hostPins table, so the host pins are not in effect'
    );
  problems.push(...hostProblems(pin, goPins), ...expiryProblems(pin, new Date()));

  if (!pin.image) problems.push('the pin file has no image= line');
  if (!pin.review) problems.push('the pin file has no review= line');

  if (pin.image && goImage && pin.image !== goImage) {
    problems.push(
      `the pin file and the Go constant disagree:\n      file: ${pin.image}\n      code: ${goImage}`
    );
  }
  if (pin.image && !goImage) {
    problems.push('provisioner.go no longer defines CephImagePin, so the pin is not in effect');
  }
  if (pin.image && isFloatingTag(pin.image)) {
    problems.push(
      `${pin.image} is a FLOATING tag. Those are rebuilt in place -- every Ceph tag moved on\n` +
        '      2026-08-19, which is the failure this pin exists to prevent. Use a dated tag.'
    );
  }
  if (pin.review) {
    const left = daysUntil(pin.review, new Date());
    if (left < 0) {
      problems.push(
        `the pin is OVERDUE for review by ${-left} day(s) (review=${pin.review}).\n` +
          `      This is not a formality: when Ubuntu's ceph-common leaves the ${pin.hostVersion?.split('.')[0] ?? '?'}.x\n` +
          '      line, this pin must move with it or the skew returns reversed. The pin file\n' +
          '      carries the full procedure.'
      );
    } else if (left <= 14) {
      console.log(`⚠ Ceph image pin is due for review in ${left} day(s) (${pin.review}).`);
    }
  }

  if (problems.length > 0) {
    console.error(`\n✗ Ceph image pin: ${problems.length} problem(s)\n`);
    for (const p of problems) console.error(`    - ${p}`);
    console.error(`\n  Pin file: ${path.relative(ROOT, PIN_FILE)}`);
    return 1;
  }

  console.log(
    `\n✓ Ceph image pinned to ${pin.image}, code agrees, review due ${pin.review}; ${Object.keys(pin.hosts).length} host pins at ${pin.hostVersion}`
  );
  console.log(
    '  controls: an overdue date, a floating tag, a code/file disagreement, a host.* line off host-version or off the Go table, and a key expiring within 30 days are all reported.'
  );
  return 0;
}

process.exit(main());
