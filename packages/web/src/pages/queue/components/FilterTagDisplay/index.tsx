import React from 'react'
import { Tag, Button } from 'antd'
import styled from 'styled-components'
import type { Dayjs } from 'dayjs'

type FilterTagValue = string | string[] | boolean | [Dayjs | null, Dayjs | null] | null

export interface FilterTagConfig {
  key: string
  value: FilterTagValue
  label: string
  color?: string
}

export interface FilterTagDisplayProps {
  filters: FilterTagConfig[]
  onClear: (key: string, value?: string) => void
  onClearAll?: () => void
  showClearAll?: boolean
  clearAllText?: string
}

const FilterTagBar = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
`

const ClearButton = styled(Button)`
  font-size: 12px;
  padding: 0 4px;
  height: auto;
`

const isStringArray = (value: FilterTagValue): value is string[] =>
  Array.isArray(value) && value.every(item => typeof item === 'string')

const hasFormatFunction = (value: unknown): value is Dayjs =>
  typeof value === 'object' &&
  value !== null &&
  'format' in value &&
  typeof (value as Dayjs).format === 'function'

const isDateRangeValue = (value: FilterTagValue): value is [Dayjs | null, Dayjs | null] =>
  Array.isArray(value) &&
  value.length === 2 &&
  (value[0] === null || hasFormatFunction(value[0])) &&
  (value[1] === null || hasFormatFunction(value[1]))

/**
 * Reusable component for displaying active filter tags with close functionality.
 * Supports string, array, boolean, and date range filter values.
 */
const FilterTagDisplay: React.FC<FilterTagDisplayProps> = ({
  filters,
  onClear,
  onClearAll,
  showClearAll = true,
  clearAllText = 'Clear',
}) => {
  // Filter out empty/inactive filters
  const activeFilters = filters.filter(filter => {
    if (filter.value === null || filter.value === undefined || filter.value === '') {
      return false
    }
    if (Array.isArray(filter.value) && filter.value.length === 0) {
      return false
    }
    if (typeof filter.value === 'boolean' && !filter.value) {
      return false
    }
    return true
  })

  if (activeFilters.length === 0) {
    return null
  }

  const renderFilterTag = (filter: FilterTagConfig) => {
    const { key, value, label, color = 'blue' } = filter

    // Handle array values (e.g., multiple status selections)
    if (isStringArray(value)) {
      return value.map(item => (
        <Tag
          key={`${key}-${item}`}
          closable
          onClose={() => onClear(key, item)}
          color={color}
        >
          {item}
        </Tag>
      ))
    }

    // Handle date range (array with date objects)
    if (isDateRangeValue(value)) {
      return (
        <Tag
          key={key}
          closable
          onClose={() => onClear(key)}
          color={color}
        >
          {label}
        </Tag>
      )
    }

    // Handle boolean and string values
    return (
      <Tag
        key={key}
        closable
        onClose={() => onClear(key)}
        color={color}
      >
        {label}
      </Tag>
    )
  }

  return (
    <FilterTagBar>
      {activeFilters.map(filter => (
        <React.Fragment key={filter.key}>
          {renderFilterTag(filter)}
        </React.Fragment>
      ))}
      {showClearAll && onClearAll && (
        <ClearButton type="link" size="small" onClick={onClearAll}>
          {clearAllText}
        </ClearButton>
      )}
    </FilterTagBar>
  )
}

export default FilterTagDisplay
