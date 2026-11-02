/**
 * The longest gap between two firings of a 5-field cron expression, in seconds.
 *
 * `backup snapshot --expected-interval` tells the account server when the next run is due, and the dead-man check
 * fires when that passes. The longest gap is the safe value: a Monday-to-Friday cron is quiet for three days over a
 * weekend, and a shorter figure would raise an alert every Saturday.
 *
 * Pure and clock-free: the result feeds the rendered unit text, which the reconciler diffs by hash, so it is computed
 * over a fixed reference year (2024, a leap year) and never reads the date.
 */

const DAY = 86_400;
const REFERENCE_START = Date.UTC(2024, 0, 1) / 1000;
const REFERENCE_DAYS = 366;

const MONTH_NAMES = [
  'jan',
  'feb',
  'mar',
  'apr',
  'may',
  'jun',
  'jul',
  'aug',
  'sep',
  'oct',
  'nov',
  'dec',
] as const;
const DOW_NAMES = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const;

function atom(raw: string, names: readonly string[], nameBase: number): number {
  const named = names.indexOf(raw.toLowerCase());
  if (named !== -1) return named + nameBase;
  const n = Number(raw);
  if (!Number.isInteger(n) || raw.trim() === '') throw new Error(`Invalid cron value "${raw}"`);
  return n;
}

interface FieldSpec {
  min: number;
  max: number;
  names?: readonly string[];
  nameBase?: number;
}

/** The inclusive bounds one comma part selects: `*`, `a`, `a/n` (a to the field maximum), `a-b`. */
function partBounds(range: string, hasStep: boolean, spec: FieldSpec): [number, number] {
  if (range === '*') return [spec.min, spec.max];
  const names = spec.names ?? [];
  const base = spec.nameBase ?? 0;
  const dash = range.indexOf('-');
  if (dash !== -1) {
    return [atom(range.slice(0, dash), names, base), atom(range.slice(dash + 1), names, base)];
  }
  const from = atom(range, names, base);
  return [from, hasStep ? spec.max : from];
}

/** The step of one comma part (1 when absent). */
function partStep(stepRaw: string | undefined, field: string): number {
  const step = stepRaw === undefined ? 1 : Number(stepRaw);
  if (!Number.isInteger(step) || step < 1) throw new Error(`Invalid cron step in "${field}"`);
  return step;
}

/** The values a cron field selects: a star, a value, a range, any of those with a step, or a comma list of them. */
function expandField(field: string, spec: FieldSpec): Set<number> {
  const out = new Set<number>();
  for (const part of field.split(',')) {
    const [range, stepRaw] = part.split('/');
    const step = partStep(stepRaw, field);
    const [from, to] = partBounds(range, stepRaw !== undefined, spec);
    if (from < spec.min || to > spec.max || from > to) {
      throw new Error(`Cron field "${field}" is out of range`);
    }
    for (let v = from; v <= to; v += step) out.add(v);
  }
  return out;
}

interface DayRule {
  months: Set<number>;
  doms: Set<number>;
  dows: Set<number>;
  domRestricted: boolean;
  dowRestricted: boolean;
}

function dayMatches(date: Date, rule: DayRule): boolean {
  if (!rule.months.has(date.getUTCMonth() + 1)) return false;
  const byDom = rule.doms.has(date.getUTCDate());
  const byDow = rule.dows.has(date.getUTCDay());
  // Standard cron: when both day fields are restricted, a day matches on either.
  return rule.domRestricted && rule.dowRestricted ? byDom || byDow : byDom && byDow;
}

export function cronMaxGapSeconds(cron: string): number {
  const fields = cron.trim().split(/\s+/);
  if (fields.length !== 5)
    throw new Error(`Invalid cron expression: "${cron}" (expected 5 fields)`);
  const [minF, hourF, domF, monF, dowF] = fields;
  const minutes = [...expandField(minF, { min: 0, max: 59 })].sort((a, b) => a - b);
  const hours = [...expandField(hourF, { min: 0, max: 23 })].sort((a, b) => a - b);
  const rule: DayRule = {
    months: expandField(monF, { min: 1, max: 12, names: MONTH_NAMES, nameBase: 1 }),
    doms: expandField(domF, { min: 1, max: 31 }),
    dows: new Set([...expandField(dowF, { min: 0, max: 7, names: DOW_NAMES })].map((d) => d % 7)),
    domRestricted: domF !== '*',
    dowRestricted: dowF !== '*',
  };

  return longestGap(fireTimes(rule, hours, minutes));
}

/** Seconds from the reference start of every firing within the reference year. */
function fireTimes(rule: DayRule, hours: number[], minutes: number[]): number[] {
  const times: number[] = [];
  for (let d = 0; d < REFERENCE_DAYS; d++) {
    if (!dayMatches(new Date((REFERENCE_START + d * DAY) * 1000), rule)) continue;
    for (const h of hours) for (const m of minutes) times.push(d * DAY + h * 3600 + m * 60);
  }
  return times;
}

function longestGap(times: number[]): number {
  if (times.length < 2) return REFERENCE_DAYS * DAY;
  let longest = 0;
  for (let i = 1; i < times.length; i++) longest = Math.max(longest, times[i] - times[i - 1]);
  return longest;
}
