import type { ApiResponse } from '../types/api'

export type ResponseExtractor<T> = (response: ApiResponse<T>) => T[]
export type ResponseFilter<T> = (item: T) => boolean
export type ResponseMapper<T, R> = (item: T) => R

const getPrimaryResultSet = <T>(response: ApiResponse<T>): T[] => {
  if (!response.resultSets || response.resultSets.length === 0) {
    return []
  }

  const primary = response.resultSets.find((set) => set.resultSetIndex === 0) ?? response.resultSets[0]
  return (primary?.data as T[]) ?? []
}

export const responseExtractors = {
  primary: getPrimaryResultSet,
  primaryOrSecondary: <T>(response: ApiResponse<T>): T[] => {
    const secondary = response.resultSets?.[1]?.data
    if (Array.isArray(secondary) && secondary.length > 0) {
      return secondary as T[]
    }
    return getPrimaryResultSet(response)
  },
  byIndex: <T>(index: number): ResponseExtractor<T> => {
    return (response: ApiResponse<T>) => {
      if (!response.resultSets || response.resultSets.length === 0) {
        return []
      }

      const table =
        response.resultSets.find((set) => set.resultSetIndex === index) ??
        response.resultSets[index] ??
        response.resultSets[0]

      return (table?.data as T[]) ?? []
    }
  },
}

export const responseFilters = {
  hasField:
    (field: string): ResponseFilter<Record<string, unknown>> =>
    (item) =>
      Boolean(item?.[field]),
  truthy: <T>(item: T) => Boolean(item),
}

export interface ParseResponseOptions<TInput, TOutput> {
  extractor?: ResponseExtractor<TInput>
  filter?: ResponseFilter<TInput>
  map?: ResponseMapper<TInput, TOutput>
}

export function parseResponse<TInput, TOutput = TInput>(
  response: ApiResponse<TInput>,
  options: ParseResponseOptions<TInput, TOutput> = {}
): TOutput[] {
  const { extractor = responseExtractors.primary as ResponseExtractor<TInput>, filter, map } = options
  const rows = extractor(response)
  const filteredRows = filter ? rows.filter(filter) : rows

  if (map) {
    return filteredRows.map(map)
  }

  return filteredRows as unknown as TOutput[]
}

export function parseFirst<TInput, TOutput = TInput>(
  response: ApiResponse<TInput>,
  options: ParseResponseOptions<TInput, TOutput> = {}
): TOutput | null {
  const rows = parseResponse(response, options)
  return rows.length > 0 ? rows[0] : null
}
