/** The pure authorized_keys planner (PLAN-ssh-key-source-ranges R1). */
import { describe, expect, it } from 'vitest';
import {
  AccessKeyConflictError,
  type DesiredAccessKey,
  parseAuthorizedKeys,
  planAccessRewrite,
  renderAccessLine,
} from '../authorized-keys.js';

const CONFIG_ID = '0f3c9a21-7d4e-4b6a-9c11-2e5f8d7a6b30';
const OTHER_CONFIG_ID = 'b7e2d4c8-1111-4222-8333-944455556666';

const PROBE_BLOB = 'AAAAC3NzaC1lZDI1NTE5AAAAIBPt7oo67lC50yBAKf8809gQPhdI9PKMrlP4xauV+MTi';
const LAPTOP =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAS/qhFn2nir1rIufUWNt95sXifKT+0k2PEQTURBtw6j laptop';
const REPO1 =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPVN/wmAEeyT/KiHsTnnr2m4IA9jSBsJix/RULhetN3a repo-mail';
const REPO2 =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILPOAeUPLoL0sEouvgatEN4lkLryRUSE574345UGcAWM repo-git';
const TEAM =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINfVd3v1+4zIJd7osLK2jNqhkd7pJ7PWGSfyE/VEYG/I team';
const OTHER =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEhHFMWEgJsVTETiAlNItf/5IPfpQLAj7TO/dLNDmeKg other';
const EC_BLOB =
  'AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBHZ2XomeJI2+pe52e6/dKC7ISN3kVKOoOBSryMO1IP10fao9lHdtepEIK3u/ui62mjrZBJMwWMKdtzJQAqfjUiQ=';
/** EC_BLOB with the two unused padding bits of its last character set: atob decodes both to the same key. */
const EC_BLOB_PADDING_VARIANT =
  'AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBHZ2XomeJI2+pe52e6/dKC7ISN3kVKOoOBSryMO1IP10fao9lHdtepEIK3u/ui62mjrZBJMwWMKdtzJQAqfjUiR=';

const HOSTED = { ipv4: ['104.28.0.0/16'], ipv6: ['2a09:bac0::/29'] };
const RESTRICT = 'no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty,no-user-rc';
const GATEWAY = (repo: string, key: string) =>
  `command="/usr/bin/renet sandbox-gateway ${repo} --guid 6a1c2f0e-0000-4000-8000-00000000000${repo.length} --datastore /mnt/rediacc" ${key}`;

const PROBE_DESIRED: DesiredAccessKey = {
  name: 'console-probe',
  key: `ssh-ed25519 ${PROBE_BLOB} rediacc-live-console-probe-2026-10-26`,
  ranges: HOSTED,
  restrict: true,
};

/** Hostinger-shaped: the hand-written probe line at 15 (its own comment differs), no final newline. */
const HOSTINGER_LINES = [
  '# authorized_keys on hostinger',
  LAPTOP,
  '',
  '# repo keys (rdc repo up)',
  GATEWAY('mail', REPO1),
  GATEWAY('gitlab', REPO2),
  '',
  '# team key',
  TEAM,
  '   ',
  '# a line sshd would ignore',
  'this is not a key line at all',
  OTHER,
  '',
  `from="104.28.0.0/16",${RESTRICT} ssh-ed25519 ${PROBE_BLOB} probe-hand-installed`,
  '',
  '# trailing notes',
  '#   ssh-ed25519 commented-out',
  GATEWAY(
    'nextcloud',
    'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGR1bW15ZHVtbXlkdW1teWR1bW15ZHVtbXlkdW1teQ== nc'
  ),
  '# end',
];
const HOSTINGER = HOSTINGER_LINES.join('\n');

const lines = (text: string) => text.split('\n');

function plan(text: string, desired: DesiredAccessKey[], configId = CONFIG_ID) {
  return planAccessRewrite(parseAuthorizedKeys(text), desired, configId);
}

describe('renderAccessLine', () => {
  it('writes from= with IPv4 then IPv6, the restriction set, the key, its comment and the marker', () => {
    expect(renderAccessLine({ configId: CONFIG_ID, ...PROBE_DESIRED })).toBe(
      `from="104.28.0.0/16,2a09:bac0::/29",${RESTRICT} ssh-ed25519 ${PROBE_BLOB} rediacc-live-console-probe-2026-10-26 rdc-access:0f3c9a21:console-probe`
    );
  });

  it('keeps from= alone when restrict is false', () => {
    const line = renderAccessLine({
      configId: CONFIG_ID,
      name: 'team',
      key: TEAM,
      ranges: { ipv6: ['2a09:bac0::/29', '2001:db8::/32'], ipv4: ['10.0.0.0/8'] },
      restrict: false,
    });
    expect(line).toBe(
      `from="10.0.0.0/8,2a09:bac0::/29,2001:db8::/32" ${TEAM} rdc-access:0f3c9a21:team`
    );
  });

  it('writes no comment field when the key has none', () => {
    const line = renderAccessLine({
      configId: CONFIG_ID,
      name: 'bare',
      key: `ssh-ed25519 ${PROBE_BLOB}`,
      ranges: { ipv4: ['10.0.0.0/8'] },
      restrict: false,
    });
    expect(line).toBe(`from="10.0.0.0/8" ssh-ed25519 ${PROBE_BLOB} rdc-access:0f3c9a21:bare`);
  });
});

describe('parseAuthorizedKeys', () => {
  it('classifies every physical line and keeps the last line without an ending', () => {
    const parsed = parseAuthorizedKeys(HOSTINGER);
    expect(parsed).toHaveLength(20);
    expect(parsed[0].kind).toBe('comment');
    expect(parsed[2].kind).toBe('blank');
    expect(parsed[9].kind).toBe('blank');
    expect(parsed[11].kind).toBe('unparsed');
    expect(parsed[14]).toMatchObject({
      number: 15,
      kind: 'key',
      type: 'ssh-ed25519',
      blob: PROBE_BLOB,
      comment: 'probe-hand-installed',
      eol: '\n',
    });
    expect(parsed[14].marker).toBeUndefined();
    expect(parsed[19].eol).toBe('');
  });

  it('keeps quoted commas and spaces inside one option token', () => {
    const [line] = parseAuthorizedKeys(
      `command="echo a, b \\"c d\\"",from="1.2.0.0/16,2a09:bac0::/29",no-pty ssh-ed25519 ${PROBE_BLOB} my key x`
    );
    expect(line.kind).toBe('key');
    expect(line.options).toBe(
      'command="echo a, b \\"c d\\"",from="1.2.0.0/16,2a09:bac0::/29",no-pty'
    );
    expect(line.optionTokens).toEqual([
      'command="echo a, b \\"c d\\""',
      'from="1.2.0.0/16,2a09:bac0::/29"',
      'no-pty',
    ]);
    expect(line.type).toBe('ssh-ed25519');
    expect(line.blob).toBe(PROBE_BLOB);
    expect(line.comment).toBe('my key x');
  });

  it('reads the marker from the last comment token', () => {
    const [line] = parseAuthorizedKeys(renderAccessLine({ configId: CONFIG_ID, ...PROBE_DESIRED }));
    expect(line.marker).toEqual({ configPrefix: '0f3c9a21', name: 'console-probe' });
    expect(line.optionTokens[0]).toBe('from="104.28.0.0/16,2a09:bac0::/29"');
  });

  it('records CRLF and LF endings per line', () => {
    const parsed = parseAuthorizedKeys(`${LAPTOP}\r\n${TEAM}\n# c\r\n`);
    expect(parsed.map((l) => l.eol)).toEqual(['\r\n', '\n', '\r\n']);
    expect(parsed[0].raw).toBe(LAPTOP);
  });
});

describe('planAccessRewrite on the hostinger fixture', () => {
  it('adopts line 15 in place and leaves every other byte alone', () => {
    const result = plan(HOSTINGER, [PROBE_DESIRED]);
    const rendered = renderAccessLine({ configId: CONFIG_ID, ...PROBE_DESIRED });
    expect(result.changes).toEqual([
      { key: 'console-probe', action: 'adopt', line: 15, text: rendered },
    ]);
    const out = lines(result.text);
    expect(out).toHaveLength(20);
    expect(out[14]).toBe(rendered);
    expect(out.slice(0, 14)).toEqual(HOSTINGER_LINES.slice(0, 14));
    expect(out.slice(15)).toEqual(HOSTINGER_LINES.slice(15));
    expect(result.text.endsWith('\n')).toBe(false);
  });

  it('is idempotent on its own output', () => {
    const first = plan(HOSTINGER, [PROBE_DESIRED]);
    const second = plan(first.text, [PROBE_DESIRED]);
    expect(second.text).toBe(first.text);
    expect(second.changes.map((c) => c.action)).toEqual(['unchanged']);
    expect(second.changes[0].line).toBe(15);
  });

  it('updates line 15 only when the ranges change', () => {
    const adopted = plan(HOSTINGER, [PROBE_DESIRED]).text;
    const narrowed = { ...PROBE_DESIRED, ranges: { ipv6: ['2a09:bac0::/29'] } };
    const result = plan(adopted, [narrowed]);
    expect(result.changes).toEqual([
      {
        key: 'console-probe',
        action: 'update',
        line: 15,
        text: renderAccessLine({ configId: CONFIG_ID, ...narrowed }),
      },
    ]);
    const before = lines(adopted);
    const after = lines(result.text);
    expect(after).toHaveLength(20);
    for (let i = 0; i < 20; i++) if (i !== 14) expect(after[i]).toBe(before[i]);
    expect(after[14]).toContain('from="2a09:bac0::/29",');
  });

  it('removes the managed line when the key is no longer desired', () => {
    const adopted = plan(HOSTINGER, [PROBE_DESIRED]).text;
    const result = plan(adopted, []);
    expect(result.changes.map((c) => [c.action, c.key, c.line])).toEqual([
      ['remove', 'console-probe', 15],
    ]);
    const out = lines(result.text);
    expect(out).toHaveLength(19);
    expect(out).toEqual(HOSTINGER_LINES.filter((_, i) => i !== 14));
  });

  it('drops an unmarked duplicate of the adopted key', () => {
    const withDup = [...HOSTINGER_LINES];
    withDup[17] = `ssh-ed25519 ${PROBE_BLOB} unrestricted-copy`;
    const result = plan(withDup.join('\n'), [PROBE_DESIRED]);
    expect(result.changes.map((c) => [c.action, c.line])).toEqual([
      ['adopt', 15],
      ['drop-duplicate', 18],
    ]);
    const out = lines(result.text);
    expect(out).toHaveLength(19);
    expect(out.some((l) => l.includes('unrestricted-copy'))).toBe(false);
  });

  it('refuses a same-blob line carrying command=', () => {
    const withCommand = [...HOSTINGER_LINES];
    withCommand[17] = `command="/bin/true",no-pty ssh-ed25519 ${PROBE_BLOB} forced`;
    let caught: unknown;
    try {
      plan(withCommand.join('\n'), [PROBE_DESIRED]);
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(AccessKeyConflictError);
    expect((caught as AccessKeyConflictError).code).toBe('ACCESS_KEY_CONFLICT');
    expect((caught as AccessKeyConflictError).line).toBe(18);
    expect((caught as AccessKeyConflictError).keyName).toBe('console-probe');
  });

  it("leaves another config's managed line untouched", () => {
    const foreign = renderAccessLine({
      configId: OTHER_CONFIG_ID,
      name: 'console-probe',
      key: OTHER,
      ranges: HOSTED,
      restrict: true,
    });
    const withForeign = [...HOSTINGER_LINES];
    withForeign[12] = foreign;
    const adopted = plan(withForeign.join('\n'), [PROBE_DESIRED]);
    expect(lines(adopted.text)[12]).toBe(foreign);
    const removed = plan(adopted.text, []);
    expect(removed.changes.map((c) => [c.action, c.line])).toEqual([['remove', 15]]);
    expect(lines(removed.text)[12]).toBe(foreign);
  });
});

describe('planAccessRewrite edge cases', () => {
  it('appends to an empty file', () => {
    const result = plan('', [PROBE_DESIRED]);
    const rendered = renderAccessLine({ configId: CONFIG_ID, ...PROBE_DESIRED });
    expect(result.changes).toEqual([
      { key: 'console-probe', action: 'append', line: 1, text: rendered },
    ]);
    expect(result.text).toBe(`${rendered}\n`);
    expect(plan(result.text, [PROBE_DESIRED]).changes.map((c) => c.action)).toEqual(['unchanged']);
  });

  it('adds the missing final newline only when appending', () => {
    const text = `${LAPTOP}\n${TEAM}`;
    expect(plan(text, []).text).toBe(text);
    const result = plan(text, [PROBE_DESIRED]);
    expect(result.text).toBe(
      `${text}\n${renderAccessLine({ configId: CONFIG_ID, ...PROBE_DESIRED })}\n`
    );
    expect(result.changes[0]).toMatchObject({ action: 'append', line: 3 });
  });

  it('keeps CRLF on untouched lines and on the rewritten line', () => {
    const text = `${LAPTOP}\r\nssh-ed25519 ${PROBE_BLOB} hand\r\n${TEAM}\r\n`;
    const result = plan(text, [PROBE_DESIRED]);
    const rendered = renderAccessLine({ configId: CONFIG_ID, ...PROBE_DESIRED });
    expect(result.text).toBe(`${LAPTOP}\r\n${rendered}\r\n${TEAM}\r\n`);
    const appended = plan(`${LAPTOP}\r\n`, [PROBE_DESIRED]);
    expect(appended.text).toBe(`${LAPTOP}\r\n${rendered}\r\n`);
  });

  it('does not adopt a key that shares the first 50 characters but not the blob', () => {
    const lookalike = `${PROBE_BLOB.slice(0, 60)}${PROBE_BLOB.slice(60).replace(/./g, 'A')}`;
    expect(lookalike.slice(0, 40)).toBe(PROBE_BLOB.slice(0, 40));
    expect(lookalike).not.toBe(PROBE_BLOB);
    const text = `ssh-ed25519 ${lookalike} rediacc-live-console-probe-2026-10-26\n`;
    const result = plan(text, [PROBE_DESIRED]);
    expect(result.changes.map((c) => c.action)).toEqual(['append']);
    expect(lines(result.text)[0]).toBe(text.trimEnd());
  });

  it('drops an unmarked duplicate whose blob differs only in its padding bits', () => {
    const desired: DesiredAccessKey = {
      name: 'ec',
      key: `ecdsa-sha2-nistp256 ${EC_BLOB} ec`,
      ranges: HOSTED,
      restrict: true,
    };
    const text = [
      `ecdsa-sha2-nistp256 ${EC_BLOB} ec`,
      LAPTOP,
      `ecdsa-sha2-nistp256 ${EC_BLOB_PADDING_VARIANT} same-key-other-spelling`,
      '',
    ].join('\n');
    const result = plan(text, [desired]);
    expect(result.changes.map((c) => [c.action, c.line])).toEqual([
      ['adopt', 1],
      ['drop-duplicate', 3],
    ]);
    expect(result.text).toBe(
      `${renderAccessLine({ configId: CONFIG_ID, ...desired })}\n${LAPTOP}\n`
    );
  });

  it('refuses a command= line whose blob differs only in its padding bits', () => {
    const desired: DesiredAccessKey = {
      name: 'ec',
      key: `ecdsa-sha2-nistp256 ${EC_BLOB} ec`,
      ranges: HOSTED,
      restrict: true,
    };
    const text = `command="/bin/true" ecdsa-sha2-nistp256 ${EC_BLOB_PADDING_VARIANT} x\n`;
    expect(() => plan(text, [desired])).toThrow(AccessKeyConflictError);
  });

  it('keeps the rest of a marked line set when one key is added and one removed', () => {
    const team: DesiredAccessKey = {
      name: 'team',
      key: TEAM,
      ranges: { ipv4: ['10.0.0.0/8'] },
      restrict: false,
    };
    const both = plan(HOSTINGER, [PROBE_DESIRED, team]);
    expect(both.changes.map((c) => [c.action, c.key, c.line])).toEqual([
      ['adopt', 'team', 9],
      ['adopt', 'console-probe', 15],
    ]);
    const onlyTeam = plan(both.text, [team]);
    expect(onlyTeam.changes.map((c) => [c.action, c.key, c.line])).toEqual([
      ['unchanged', 'team', 9],
      ['remove', 'console-probe', 15],
    ]);
  });
});
