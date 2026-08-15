import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  buildPrunePreviewRows,
  type DatastorePrunableResources,
  countPrunedResources,
  parseDatastorePruneOutput,
} from '../datastore-prune-parser.js';

const RESOURCES_JSON = JSON.stringify({
  empty_mounts: null,
  orphan_immovables: null,
  stale_locks: null,
  stale_snapshots: null,
  stale_backup_snapshots: ['.backup-A', '.backup-B'],
  orphan_sandboxes: null,
  iptables_chains: [{ name: 'REDIACC_WILDCARD_64', table: 'filter', network_id: 64 }],
  auth_keys: [
    { path: '/home/x/.ssh/authorized_keys', home_user: 'x', repo_name: 'foo', line_num: 3 },
  ],
  stale_units: null,
});

describe('parseDatastorePruneOutput', () => {
  it('parses a clean prune JSON object', () => {
    const obj = parseDatastorePruneOutput(RESOURCES_JSON);
    expect(obj.stale_backup_snapshots).toEqual(['.backup-A', '.backup-B']);
  });

  it('strips the renet "[repository_prune] " line prefix and parses', () => {
    // Mirror how the bridge relays multi-line indented JSON + a leading log line.
    const pretty = JSON.stringify(JSON.parse(RESOURCES_JSON), null, 2);
    const relayed = [
      '[repository_prune] scanning datastore',
      ...pretty.split('\n').map((l) => `[repository_prune] ${l}`),
    ].join('\n');
    const obj = parseDatastorePruneOutput(relayed);
    expect(obj.stale_backup_snapshots).toEqual(['.backup-A', '.backup-B']);
  });

  it('survives logrus stderr lines interleaved INSIDE the JSON (relay merge)', () => {
    // The renet relay merges the sub-command's stderr into stdout, so under
    // load a logrus line can land between the pretty-printed JSON's lines —
    // inside the brace span. Observed live on `repo trim` (#424 sequence run):
    // parse failed with `time="…" level=info msg="Starting..."` in the capture.
    const pretty = JSON.stringify(JSON.parse(RESOURCES_JSON), null, 2).split('\n');
    const interleaved = [
      'time="2026-07-22T08:51:39Z" level=info msg="Starting..."',
      ...pretty.slice(0, 3),
      'time="2026-07-22T08:51:40Z" level=info msg="Trimming volume..."',
      ...pretty.slice(3),
      'time="2026-07-22T08:51:41Z" level=info msg="Complete: repository_trim completed"',
    ].join('\n');
    const obj = parseDatastorePruneOutput(interleaved);
    expect(obj.stale_backup_snapshots).toEqual(['.backup-A', '.backup-B']);
  });

  it('throws when no JSON object is present', () => {
    expect(() => parseDatastorePruneOutput('no json here')).toThrow();
  });
});

describe('buildPrunePreviewRows', () => {
  it('flattens every category into { type, resource } rows', () => {
    const rows = buildPrunePreviewRows(parseDatastorePruneOutput(RESOURCES_JSON));
    expect(rows).toEqual([
      { type: 'backup-snapshot', resource: '.backup-A' },
      { type: 'backup-snapshot', resource: '.backup-B' },
      { type: 'iptables-chain', resource: 'REDIACC_WILDCARD_64 (network 64)' },
      { type: 'authorized-key', resource: '/home/x/.ssh/authorized_keys:3 (foo)' },
    ]);
  });

  it('treats null/absent categories as empty', () => {
    expect(buildPrunePreviewRows({})).toEqual([]);
    expect(buildPrunePreviewRows({ stale_backup_snapshots: null })).toEqual([]);
  });
});

/**
 * `buildPrunePreviewRows` maps renet's prune JSON through an explicit allowlist,
 * so a resource kind renet learns to report stays INVISIBLE in `rdc`'s preview
 * until someone adds a line. Nothing failed when that happened: the JSON is
 * additive, the parse succeeds, and the new kind is simply never shown. Two
 * kinds (`stale_pull_staging`, `stale_churn_probe_bases`) shipped that way.
 *
 * So the allowlist is pinned against the Go struct it mirrors. The renet
 * submodule is checked out by the CI job that runs these tests (ci-quality.yml,
 * the L6 PACKAGES lane, `submodules: true`); if it is missing the read throws
 * rather than skipping, because a coverage check that quietly does not run is
 * the failure mode this test exists to prevent.
 */
const RENET_PRUNE_GO = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../../../private/renet/pkg/prune/datastore.go'
);

/** Every `json:"…"` tag on renet's `DatastorePrunableResources`. */
function renetPruneResourceTags(): string[] {
  const src = readFileSync(RENET_PRUNE_GO, 'utf8');
  const start = src.indexOf('type DatastorePrunableResources struct {');
  if (start === -1) {
    throw new Error(`DatastorePrunableResources not found in ${RENET_PRUNE_GO}`);
  }
  const body = src.slice(start, src.indexOf('\n}', start));
  return [...body.matchAll(/json:"([a-z_]+)"/g)].map((m) => m[1]);
}

/** One representative item per kind, shaped as renet marshals it. */
const KIND_FIXTURES: Record<string, unknown[]> = {
  empty_mounts: ['guid-a'],
  orphan_immovables: ['guid-b'],
  orphan_state_mirrors: ['guid-c'],
  orphan_legacy_interim: ['guid-d'],
  stale_locks: ['.lock-guid-e'],
  stale_snapshots: ['.snapshot-f'],
  stale_backup_snapshots: ['.backup-g'],
  stale_pull_staging: ['.pull-guid-h'],
  stale_restore_staging: ['.restore-guid-h'],
  stale_churn_probe_bases: ['.churn-probe-i'],
  stale_backup_anchors: ['.chunk-anchors/guid-k'],
  stale_backup_journals: ['default-guid-l.json'],
  orphan_sandboxes: ['sandbox-j'],
  iptables_chains: [{ name: 'REDIACC_WILDCARD_64', table: 'filter', network_id: 64 }],
  auth_keys: [
    { path: '/home/x/.ssh/authorized_keys', home_user: 'x', repo_name: 'r', line_num: 3 },
  ],
  stale_units: [{ path: '/etc/systemd/system/rediacc-docker-64.service', network_id: 64 }],
};

describe('prune resource coverage against renet', () => {
  it('has a fixture for every kind renet reports', () => {
    // Guards the guard: a new Go kind with no fixture would otherwise leave the
    // coverage assertion below silently testing one kind fewer.
    expect(Object.keys(KIND_FIXTURES).sort()).toEqual(renetPruneResourceTags().sort());
  });

  it('emits at least one preview row for every kind renet reports', () => {
    const uncovered = renetPruneResourceTags().filter((tag) => {
      const only: Record<string, unknown> = { [tag]: KIND_FIXTURES[tag] };
      return buildPrunePreviewRows(only).length === 0;
    });
    expect(uncovered).toEqual([]);
  });

  it('maps each kind to exactly one row when all are populated', () => {
    const tags = renetPruneResourceTags();
    const all = Object.fromEntries(
      tags.map((tag) => [tag, KIND_FIXTURES[tag]])
    ) as DatastorePrunableResources;
    expect(buildPrunePreviewRows(all)).toHaveLength(tags.length);
  });
});

describe('countPrunedResources', () => {
  it('sums *_pruned ints and array lengths, ignoring failures', () => {
    const result = {
      mounts_pruned: 2,
      backup_snapshots_pruned: 1,
      iptables_pruned: [{ name: 'a' }, { name: 'b' }],
      auth_keys_pruned: [],
      mounts_failed: [{ error: 'x' }],
    };
    expect(countPrunedResources(result)).toBe(5);
  });
});
