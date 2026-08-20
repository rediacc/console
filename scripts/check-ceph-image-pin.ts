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
 * Both are text checks. It deliberately does NOT query the registry or a worker:
 * a gate that needs the network fails for reasons that have nothing to do with
 * the thing it guards, and this one runs in the default CI job.
 *
 * Usage: npx tsx scripts/check-ceph-image-pin.ts [--selftest]
 * Exit 0 ok, 1 stale or disagreeing, 2 the check itself could not run.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PIN_FILE = path.join(ROOT, 'private/renet/.ceph-image-pin');
const GO_FILE = path.join(ROOT, 'private/renet/pkg/infra/ceph/provisioner.go');

export interface Pin {
  image?: string;
  review?: string;
  hostMajor?: string;
}

export function parsePin(text: string): Pin {
  const out: Pin = {};
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const eq = t.indexOf('=');
    if (eq < 0) continue;
    const k = t.slice(0, eq).trim();
    const v = t.slice(eq + 1).trim();
    if (k === 'image') out.image = v;
    else if (k === 'review') out.review = v;
    else if (k === 'host-major') out.hostMajor = v;
  }
  return out;
}

/** The image named by the Go constant, or undefined when it is absent. */
export function goPinnedImage(src: string): string | undefined {
  return /CephImagePin\s*=\s*"([^"]+)"/.exec(src)?.[1];
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
          `      This is not a formality: when Ubuntu's ceph-common leaves the ${pin.hostMajor ?? '?'}.x\n` +
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

  console.log(`\n✓ Ceph image pinned to ${pin.image}, code agrees, review due ${pin.review}`);
  console.log(
    '  controls: an overdue date, a floating tag and a code/file disagreement are all reported.'
  );
  return 0;
}

process.exit(main());
