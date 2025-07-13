export const extractTableData = <T = any[]>(
  response: any, 
  tableIndex = 1,
  defaultValue: T = [] as T
): T => {
  const data = response.tables?.[tableIndex]?.data ?? response.tables?.[0]?.data ?? defaultValue
  return Array.isArray(data) ? data : defaultValue
}

export const extractFilteredTableData = <T extends Record<string, any>>(
  response: any,
  filterFn: (item: T) => boolean,
  tableIndex = 1
): T[] => extractTableData<T[]>(response, tableIndex, []).filter(item => item && filterFn(item))

export const extractResourceData = <T extends { [K in keyof T]: any }>(
  response: any,
  nameField: keyof T,
  tableIndex = 1
): T[] => extractFilteredTableData<T>(response, item => item?.[nameField], tableIndex)

export const parseNestedJson = (data: any, fields: string[]): Record<string, any> => 
  fields.reduce((result, field) => {
    try {
      result[field] = typeof data[field] === 'string' ? JSON.parse(data[field]) : data[field]
    } catch (e) {
      result[field] = data[field]
    }
    return result
  }, {})

export const parseDoubleEncodedJson = <T>(jsonString: string, fields: string[]): T => 
  parseNestedJson(JSON.parse(jsonString), fields) as T

export const fixTripleEncodedFields = (data: any, fields: string[]): void => {
  fields.forEach(field => {
    if (data[field] && typeof data[field] === 'string') {
      try {
        data[field] = JSON.parse(data[field])
      } catch (e) {
        // Failed to parse triple-encoded field
      }
    }
  })
}