/**
 * Generic table sorting utilities.
 * Provides type-safe sorter factories that handle null/undefined values consistently.
 */

type SortOrder = number;

type Primitive = string | number | boolean | Date | null | undefined;

type NestedKeyOf<T> = {
  [K in keyof T & string]: T[K] extends Primitive
    ? K
    : T[K] extends object
      ? K | `${K}.${NestedKeyOf<T[K]>}`
      : K;
}[keyof T & string];

function getNestedValue<T>(obj: T, path: string): unknown {
  return path.split('.').reduce((current: unknown, key: string) => {
    if (current && typeof current === 'object') {
      return (current as Record<string, unknown>)[key];
    }
    return undefined;
  }, obj);
}

function isDateString(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const date = new Date(value);
  return !Number.isNaN(date.getTime()) && value.length >= 10;
}

function toTimestamp(value: unknown): number {
  if (value instanceof Date) return value.getTime();
  if (typeof value === 'string' || typeof value === 'number') {
    const ts = new Date(value).getTime();
    return Number.isNaN(ts) ? Number.MAX_SAFE_INTEGER : ts;
  }
  return Number.MAX_SAFE_INTEGER;
}

function isNumericString(value: string): boolean {
  return !Number.isNaN(Number(value)) && value.trim() !== '';
}

/** Compare two strings, handling numeric strings */
function compareStrings(a: string, b: string): SortOrder {
  const bothNumeric = isNumericString(a) && isNumericString(b);
  return bothNumeric ? Number(a) - Number(b) : a.localeCompare(b);
}

/** Compare two numbers */
function compareNumbers(a: number, b: number): SortOrder {
  return a - b;
}

/** Compare two booleans */
function compareBooleans(a: boolean, b: boolean): SortOrder {
  return (a ? 1 : 0) - (b ? 1 : 0);
}

/** Compare two arrays by length */
function compareArrays(a: unknown[], b: unknown[]): SortOrder {
  return a.length - b.length;
}

/** Compare date-like values */
function compareDates(a: unknown, b: unknown): SortOrder {
  return toTimestamp(a) - toTimestamp(b);
}

/** Check if value is date-like */
function isDateLike(value: unknown): boolean {
  return value instanceof Date || isDateString(value);
}

/** Handle null comparison, returns comparison result or undefined if both non-null */
function compareNulls(a: unknown, b: unknown): SortOrder | undefined {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return undefined;
}

/** Compare typed values after null check */
function compareTypedValues(a: unknown, b: unknown): SortOrder {
  const typeA = typeof a;
  const typeB = typeof b;

  if (typeA === 'string' && typeB === 'string') {
    return compareStrings(a as string, b as string);
  }

  if (typeA === 'number' && typeB === 'number') {
    return compareNumbers(a as number, b as number);
  }

  if (typeA === 'boolean' && typeB === 'boolean') {
    return compareBooleans(a as boolean, b as boolean);
  }

  if (isDateLike(a) && isDateLike(b)) {
    return compareDates(a, b);
  }

  if (Array.isArray(a) && Array.isArray(b)) {
    return compareArrays(a, b);
  }

  return String(a).localeCompare(String(b));
}

/**
 * Core comparison function for sorting values
 * Handles null/undefined, numbers, strings, dates, and booleans
 */
export function compareValues(a: unknown, b: unknown): SortOrder {
  if (a === b) return 0;

  const nullResult = compareNulls(a, b);
  if (nullResult !== undefined) return nullResult;

  return compareTypedValues(a, b);
}

/**
 * Creates an auto-detecting sorter that determines comparison type from the data.
 * Handles null/undefined values consistently (nulls sort to end).
 *
 * @example
 * const columns = [
 *   { title: 'Name', dataIndex: 'name', sorter: createSorter<User>('name') },
 *   { title: 'Age', dataIndex: 'age', sorter: createSorter<User>('age') },
 * ]
 */
export function createSorter<T>(field: NestedKeyOf<T>) {
  return (a: T, b: T): SortOrder => {
    const valA = getNestedValue(a, field);
    const valB = getNestedValue(b, field);
    return compareValues(valA, valB);
  };
}

/**
 * Creates a date sorter that handles Date objects, ISO strings, and timestamps.
 */
export function createDateSorter<T>(field: NestedKeyOf<T>) {
  return (a: T, b: T): SortOrder => {
    const valA = getNestedValue(a, field);
    const valB = getNestedValue(b, field);

    if (valA == null && valB == null) return 0;
    if (valA == null) return 1;
    if (valB == null) return -1;

    return toTimestamp(valA) - toTimestamp(valB);
  };
}

/**
 * Creates a sorter from a custom value extractor function.
 * Useful for computed values or complex sorting logic.
 *
 * @example
 * sorter: createCustomSorter<Container>(
 *   (c) => c.state === 'running' ? 0 : c.state === 'paused' ? 1 : 2
 * )
 */
export function createCustomSorter<T>(getValue: (item: T) => unknown) {
  return (a: T, b: T): SortOrder => {
    const valA = getValue(a);
    const valB = getValue(b);
    return compareValues(valA, valB);
  };
}

/**
 * Creates an array length sorter for fields containing arrays.
 */
export function createArrayLengthSorter<T>(field: NestedKeyOf<T>) {
  return (a: T, b: T): SortOrder => {
    const valA = getNestedValue(a, field);
    const valB = getNestedValue(b, field);

    const lenA = Array.isArray(valA) ? valA.length : 0;
    const lenB = Array.isArray(valB) ? valB.length : 0;

    return lenA - lenB;
  };
}
