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
  return !isNaN(date.getTime()) && value.length >= 10;
}

function toTimestamp(value: unknown): number {
  if (value instanceof Date) return value.getTime();
  if (typeof value === 'string' || typeof value === 'number') {
    const ts = new Date(value).getTime();
    return isNaN(ts) ? Number.MAX_SAFE_INTEGER : ts;
  }
  return Number.MAX_SAFE_INTEGER;
}

function isNumericString(value: string): boolean {
  return !isNaN(Number(value)) && value.trim() !== '';
}

/**
 * Core comparison function for sorting values
 * Handles null/undefined, numbers, strings, dates, and booleans
 */
export function compareValues(a: unknown, b: unknown): SortOrder {
  if (a === b) return 0;
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;

  // Handle numeric strings - sort "10" after "2"
  if (typeof a === 'string' && typeof b === 'string') {
    if (isNumericString(a) && isNumericString(b)) {
      return Number(a) - Number(b);
    }
    return a.localeCompare(b);
  }

  if (typeof a === 'number' && typeof b === 'number') {
    return a - b;
  }

  if (typeof a === 'boolean' && typeof b === 'boolean') {
    return (a ? 1 : 0) - (b ? 1 : 0);
  }

  if ((a instanceof Date || isDateString(a)) && (b instanceof Date || isDateString(b))) {
    return toTimestamp(a) - toTimestamp(b);
  }

  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length - b.length;
  }

  return String(a).localeCompare(String(b));
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
