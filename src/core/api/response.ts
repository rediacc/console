import type { ApiResponse } from '../types'

type ResultRow = Record<string, unknown>

export function getResultSet<T = ResultRow>(response: ApiResponse, index = 1): T[] {
  if (!response.resultSets || response.resultSets.length === 0) {
    return []
  }
  return (response.resultSets[index]?.data ?? response.resultSets[0]?.data ?? []) as T[]
}

export function getResultSetByIndex<T = ResultRow>(response: ApiResponse, resultSetIndex: number): T[] {
  const table = response.resultSets?.find((set) => set.resultSetIndex === resultSetIndex)
  return (table?.data as T[]) ?? []
}

export function extractTableData<T = unknown>(
  response: ApiResponse,
  tableIndex = 1,
  defaultValue: T = [] as unknown as T,
): T {
  const table = response.resultSets?.[tableIndex]?.data ?? response.resultSets?.[0]?.data ?? defaultValue
  return (Array.isArray(table) ? table : defaultValue) as T
}

export function extractFilteredTableData<T>(
  response: ApiResponse,
  filterFn: (item: T) => boolean,
  tableIndex = 1,
): T[] {
  return getResultSet<T>(response, tableIndex).filter((item) => item && filterFn(item))
}

export function extractResourceData<T>(response: ApiResponse, nameField: keyof T, tableIndex = 1): T[] {
  return extractFilteredTableData<T>(
    response,
    (item) => Boolean((item as Record<string, unknown>)[nameField as string]),
    tableIndex,
  )
}

export const dataExtractors = {
  primary: <T = ResultRow>(response: ApiResponse): T[] => getResultSet<T>(response, 0),
  primaryOrSecondary: <T = ResultRow>(response: ApiResponse): T[] => {
    const secondary = response.resultSets?.[1]?.data
    if (secondary && Array.isArray(secondary)) {
      return secondary as T[]
    }
    return getResultSet<T>(response, 0)
  },
}

export const filters = {
  hasName:
    (nameField: string) =>
    (item: Record<string, unknown>) =>
      Boolean(item && item[nameField]),
  isValid: (item: unknown) => Boolean(item),
}

export const createFieldMapper =
  <T>(fieldMap: Record<string, string | ((item: Record<string, unknown>) => unknown)>) =>
  (item: Record<string, unknown>): T => {
    const result = {} as T
    Object.entries(fieldMap).forEach(([key, value]) => {
      if (typeof value === 'function') {
        ;(result as Record<string, unknown>)[key] = value(item)
      } else {
        const defaultValue = key.includes('vault')
          ? '{}'
          : key.includes('Version')
            ? 1
            : key.includes('Count')
              ? 0
              : undefined
        ;(result as Record<string, unknown>)[key] = item[value] ?? defaultValue
      }
    })
    return result
  }

export function parseNestedJson(source: Record<string, unknown>, fields: string[]): Record<string, unknown> {
  return fields.reduce<Record<string, unknown>>((acc, field) => {
    try {
      const value = source[field]
      acc[field] = typeof value === 'string' ? JSON.parse(value) : value
    } catch {
      acc[field] = source[field]
    }
    return acc
  }, {})
}

export function parseDoubleEncodedJson<T>(jsonString: string, fields: string[]): T {
  return parseNestedJson(JSON.parse(jsonString), fields) as T
}

export function fixTripleEncodedFields(target: Record<string, unknown>, fields: string[]): void {
  fields.forEach((field) => {
    const value = target[field]
    if (typeof value === 'string') {
      try {
        target[field] = JSON.parse(value)
      } catch {
        // swallow parse errors
      }
    }
  })
}

export function getFirstRow<T = ResultRow>(response: ApiResponse, tableIndex = 1): T | undefined {
  const rows = getResultSet<T>(response, tableIndex)
  return rows.length ? rows[0] : undefined
}

export function mapResultSet<T = ResultRow, K = unknown>(
  response: ApiResponse,
  mapper: (row: T) => K,
  tableIndex = 1,
): K[] {
  return getResultSet<T>(response, tableIndex).map((row) => mapper(row))
}

export function getScalar<T = unknown>(response: ApiResponse, field: string, tableIndex = 1): T | undefined {
  const row = getFirstRow<Record<string, T>>(response, tableIndex)
  return row ? row[field] : undefined
}
