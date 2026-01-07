import { describe, expect, it } from 'vitest';
import { formatTimestamp } from '../formatTimestamp';

describe('formatTimestamp', () => {
  it('returns "just now" for timestamps less than 1 minute ago', () => {
    const now = new Date();
    const thirtySecondsAgo = new Date(now.getTime() - 30 * 1000);
    expect(formatTimestamp(thirtySecondsAgo.toISOString())).toBe('just now');
  });

  it('returns minutes for timestamps less than 1 hour ago', () => {
    const now = new Date();
    const tenMinutesAgo = new Date(now.getTime() - 10 * 60 * 1000);
    expect(formatTimestamp(tenMinutesAgo.toISOString())).toBe('10 minutes ago');
  });

  it('returns singular "minute" for 1 minute ago', () => {
    const now = new Date();
    const oneMinuteAgo = new Date(now.getTime() - 1 * 60 * 1000);
    expect(formatTimestamp(oneMinuteAgo.toISOString())).toBe('1 minute ago');
  });

  it('returns hours for timestamps less than 1 day ago', () => {
    const now = new Date();
    const fiveHoursAgo = new Date(now.getTime() - 5 * 60 * 60 * 1000);
    expect(formatTimestamp(fiveHoursAgo.toISOString())).toBe('5 hours ago');
  });

  it('returns singular "hour" for 1 hour ago', () => {
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 1 * 60 * 60 * 1000);
    expect(formatTimestamp(oneHourAgo.toISOString())).toBe('1 hour ago');
  });

  it('returns days for timestamps less than 1 week ago', () => {
    const now = new Date();
    const threeDaysAgo = new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000);
    expect(formatTimestamp(threeDaysAgo.toISOString())).toBe('3 days ago');
  });

  it('returns singular "day" for 1 day ago', () => {
    const now = new Date();
    const oneDayAgo = new Date(now.getTime() - 1 * 24 * 60 * 60 * 1000);
    expect(formatTimestamp(oneDayAgo.toISOString())).toBe('1 day ago');
  });

  it('returns locale date string for timestamps older than 1 week', () => {
    const now = new Date();
    const oneMonthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    const expected = oneMonthAgo.toLocaleString();
    expect(formatTimestamp(oneMonthAgo.toISOString())).toBe(expected);
  });
});
