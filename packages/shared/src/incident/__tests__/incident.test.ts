import { describe, expect, it } from 'vitest';
import {
  addCalendarMonth,
  clockState,
  compareRows,
  IncidentSchema,
  incidentClocks,
  mergeRows,
  releaseAt,
  type TimelineRow,
  TimelineRowSchema,
} from '../index.js';

describe('incidentClocks', () => {
  it('sets early warning at 24 hours and notification at 72 hours after awareness', () => {
    const clocks = incidentClocks({ awareAt: '2026-11-20T09:30:00.000Z' });
    expect(clocks.earlyWarningDue).toBe('2026-11-21T09:30:00.000Z');
    expect(clocks.notificationDue).toBe('2026-11-23T09:30:00.000Z');
  });

  it('counts the final report one calendar month from notified_at', () => {
    const clocks = incidentClocks({
      awareAt: '2026-11-20T09:30:00.000Z',
      notifiedAt: '2026-11-22T12:00:00.000Z',
    });
    expect(clocks.finalReportDue).toBe('2026-12-22T12:00:00.000Z');
    expect(clocks.finalReportFrom).toBe('notified_at');
  });

  it('counts from the notification deadline before a notification is recorded', () => {
    const clocks = incidentClocks({ awareAt: '2026-11-20T09:30:00.000Z', notifiedAt: null });
    expect(clocks.finalReportDue).toBe('2026-12-23T09:30:00.000Z');
    expect(clocks.finalReportFrom).toBe('notification_due');
  });

  it('clamps a month that is shorter and rolls the year', () => {
    expect(addCalendarMonth('2026-01-31T10:00:00.000Z')).toBe('2026-02-28T10:00:00.000Z');
    expect(addCalendarMonth('2028-01-31T10:00:00.000Z')).toBe('2028-02-29T10:00:00.000Z');
    expect(addCalendarMonth('2026-12-15T10:00:00.000Z')).toBe('2027-01-15T10:00:00.000Z');
  });

  it('rejects a value that is not an instant', () => {
    expect(() => incidentClocks({ awareAt: 'yesterday' })).toThrow(RangeError);
  });
});

describe('clockState', () => {
  const now = new Date('2026-11-21T00:00:00.000Z');
  it('names done, overdue, due soon and pending', () => {
    expect(clockState('2026-11-20T00:00:00.000Z', now, true)).toBe('done');
    expect(clockState('2026-11-20T00:00:00.000Z', now, false)).toBe('overdue');
    expect(clockState('2026-11-21T05:00:00.000Z', now, false)).toBe('due_soon');
    expect(clockState('2026-11-22T00:00:00.000Z', now, false)).toBe('pending');
  });
});

const incident = {
  id: 'i-1',
  orgId: 'org-1',
  scopeKind: 'repo',
  scopeRef: 'mail',
  windowFrom: '2026-11-19T00:00:00.000Z',
  windowTo: '2026-11-20T00:00:00.000Z',
  status: 'declared',
  declaredBy: 'u-1',
  declaredAt: '2026-11-20T10:00:00.000Z',
  awareAt: '2026-11-20T09:00:00.000Z',
  notifiedAt: null,
  containedAt: null,
  closedAt: null,
  closedBy: null,
  forkRef: null,
  steps: [],
};

describe('IncidentSchema', () => {
  it('admits an awareness earlier than the declaration and refuses a later one', () => {
    expect(IncidentSchema.safeParse(incident).success).toBe(true);
    expect(
      IncidentSchema.safeParse({ ...incident, awareAt: '2026-11-20T11:00:00.000Z' }).success
    ).toBe(false);
  });

  it('refuses a window that ends before it starts and an unknown field', () => {
    expect(
      IncidentSchema.safeParse({ ...incident, windowTo: '2026-11-18T00:00:00.000Z' }).success
    ).toBe(false);
    expect(IncidentSchema.safeParse({ ...incident, extra: 1 }).success).toBe(false);
  });

  it('releases a closed incident 30 days after the close and never before it', () => {
    expect(releaseAt({ closedAt: null })).toBeNull();
    expect(releaseAt({ closedAt: '2026-11-20T10:00:00.000Z' })).toBe('2026-12-20T10:00:00.000Z');
  });
});

function row(id: string, ts: string): TimelineRow {
  return {
    id,
    ts,
    source: 'forensics',
    basis: 'observed',
    kind: 'open',
    data: { repoGuid: 'g', process: 'cat', path: '/etc/passwd', sensitive: true },
  };
}

describe('timeline rows', () => {
  it('parses every kind and refuses a field the kind does not name', () => {
    expect(TimelineRowSchema.safeParse(row('a', '2026-11-20T10:00:00.000Z')).success).toBe(true);
    const bad = {
      ...row('a', '2026-11-20T10:00:00.000Z'),
      data: { path: '/x', content: 'secret' },
    };
    expect(TimelineRowSchema.safeParse(bad).success).toBe(false);
  });

  it('merges sources by time and breaks a tie by id', () => {
    const merged = mergeRows(
      [row('b', '2026-11-20T10:00:00.000Z'), row('d', '2026-11-20T12:00:00.000Z')],
      [row('a', '2026-11-20T10:00:00.000Z'), row('c', '2026-11-20T11:00:00.000Z')]
    );
    expect(merged.map((r) => r.id)).toEqual(['a', 'b', 'c', 'd']);
    expect(compareRows(merged[0] as TimelineRow, merged[0] as TimelineRow)).toBe(0);
  });
});
