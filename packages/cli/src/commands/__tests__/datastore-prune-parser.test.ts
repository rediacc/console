import { describe, expect, it } from 'vitest';
import {
  buildPrunePreviewRows,
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
