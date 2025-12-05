import type { ApiResponse } from '../types/api';

type PlainObject = Record<string, unknown>;

function isPlainObject(value: unknown): value is PlainObject {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function toCamelCase(key: string): string {
  if (!key) return key;
  const firstChar = key[0];
  if (firstChar === firstChar.toLowerCase()) {
    return key;
  }
  return firstChar.toLowerCase() + key.slice(1);
}

function normalizeArray(value: unknown[]): unknown[] {
  return value.map((item) => normalizeValue(item));
}

function normalizeObject(value: PlainObject): PlainObject {
  return Object.entries(value).reduce<PlainObject>((acc, [key, val]) => {
    acc[toCamelCase(key)] = normalizeValue(val);
    return acc;
  }, {});
}

function normalizeValue<T>(value: T): T {
  if (Array.isArray(value)) {
    return normalizeArray(value) as unknown as T;
  }
  if (isPlainObject(value)) {
    return normalizeObject(value) as unknown as T;
  }
  return value;
}

export function normalizeResponse<T = unknown>(response: ApiResponse<T>): ApiResponse<T> {
  return normalizeValue(response);
}

export function normalizeRecord<T>(value: T): T {
  return normalizeValue(value);
}
