/** A copy of `source` without `key`; a rest-destructure that binds the dropped value fails the unused-variable rules. */
export function omitKey<T extends object, K extends PropertyKey>(source: T, key: K): Omit<T, K> {
  const copy = { ...source } as Record<PropertyKey, unknown>;
  delete copy[key];
  return copy as Omit<T, K>;
}
