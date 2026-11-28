/**
 * Incident deadline clocks (D4): early warning 24 hours and notification 72 hours
 * after awareness, the final report one calendar month after the notification
 * (NIS2 Art. 23(4)(d)). Before a notification is recorded the month counts from
 * the notification deadline, so the clock never starts later than the law allows.
 * Every instant is UTC.
 */
const HOUR_MS = 3_600_000;

export interface IncidentClockInput {
  awareAt: string;
  notifiedAt?: string | null;
}

export interface IncidentClocks {
  earlyWarningDue: string;
  notificationDue: string;
  finalReportDue: string;
  /** What the final-report month counts from. */
  finalReportFrom: 'notified_at' | 'notification_due';
}

/** The same instant one calendar month later, clamped to the last day of a shorter month. */
export function addCalendarMonth(iso: string): string {
  const start = new Date(iso);
  if (Number.isNaN(start.getTime())) throw new RangeError(`not an instant: ${iso}`);
  const year = start.getUTCFullYear();
  const month = start.getUTCMonth() + 1;
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const day = Math.min(start.getUTCDate(), lastDay);
  return new Date(
    Date.UTC(
      year,
      month,
      day,
      start.getUTCHours(),
      start.getUTCMinutes(),
      start.getUTCSeconds(),
      start.getUTCMilliseconds()
    )
  ).toISOString();
}

export function incidentClocks(input: IncidentClockInput): IncidentClocks {
  const aware = Date.parse(input.awareAt);
  if (Number.isNaN(aware)) throw new RangeError(`not an instant: ${input.awareAt}`);
  const earlyWarningDue = new Date(aware + 24 * HOUR_MS).toISOString();
  const notificationDue = new Date(aware + 72 * HOUR_MS).toISOString();
  const notified = input.notifiedAt ?? null;
  return {
    earlyWarningDue,
    notificationDue,
    finalReportDue: addCalendarMonth(notified ?? notificationDue),
    finalReportFrom: notified === null ? 'notification_due' : 'notified_at',
  };
}

export type ClockState = 'done' | 'overdue' | 'due_soon' | 'pending';

/** A clock's state at `now`: done when its step is recorded, `due_soon` inside the last 6 hours. */
export function clockState(dueAt: string, now: Date, done: boolean): ClockState {
  if (done) return 'done';
  const left = Date.parse(dueAt) - now.getTime();
  if (left < 0) return 'overdue';
  return left <= 6 * HOUR_MS ? 'due_soon' : 'pending';
}
