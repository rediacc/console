type Transformer = (value: string) => Promise<string>;

export function isVaultField(key: string): boolean {
  return key.toLowerCase().includes('vault');
}

export function hasVaultFields(value: unknown): boolean {
  if (value == null) return false;
  if (Array.isArray(value)) {
    return value.some((item) => hasVaultFields(item));
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).some(([key, nested]) => {
      if (isVaultField(key)) return true;
      return hasVaultFields(nested);
    });
  }
  return false;
}

export async function transformVaultFields<T>(value: T, transformer: Transformer): Promise<T> {
  if (Array.isArray(value)) {
    const result = await Promise.all(value.map((item) => transformVaultFields(item, transformer)));
    return result as unknown as T;
  }

  if (typeof value === 'object' && value !== null) {
    const target: Record<string, unknown> = {};
    await Promise.all(
      Object.entries(value).map(async ([key, entryValue]) => {
        if (isVaultField(key) && typeof entryValue === 'string' && entryValue.length > 0) {
          target[key] = await transformer(entryValue);
        } else if (Array.isArray(entryValue) || (entryValue && typeof entryValue === 'object')) {
          target[key] = await transformVaultFields(entryValue, transformer);
        } else {
          target[key] = entryValue;
        }
      })
    );
    return target as T;
  }

  return value;
}
