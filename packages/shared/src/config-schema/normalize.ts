/**
 * Normalization of a v3 config document before schema validation.
 *
 * The `resources.storages` family was retired inside schema v3 without a version bump. A config
 * written earlier can still carry it as an empty object, which holds no data, so it is dropped here
 * instead of failing the strict parse. A non-empty `storages` is left in place and stays refused by
 * name in `ResourcesSchema`.
 *
 * One function, reused by every site that turns stored or pulled JSON into a config: the local file
 * load (through `runMigrations`) and the remote-pull cache merge. Pure: the input is not mutated.
 */

function isPlainObject(x: unknown): x is Record<string, unknown> {
  return typeof x === 'object' && x !== null && !Array.isArray(x);
}

export function normalizeV3Document<T>(doc: T): T {
  if (!isPlainObject(doc)) return doc;
  const resources = doc.resources;
  if (!isPlainObject(resources)) return doc;
  const storages = resources.storages;
  if (!isPlainObject(storages) || Object.keys(storages).length > 0) return doc;
  const rest = Object.fromEntries(Object.entries(resources).filter(([key]) => key !== 'storages'));
  return { ...doc, resources: rest } as T;
}
