import React from 'react'
import { Tag, Button } from 'antd'
import styled from 'styled-components'

export interface FilterTagConfig {
  key: string
  value: string | string[] | boolean | [any, any] | null
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
    if (Array.isArray(value) && typeof value[0] !== 'object') {
      return (value as string[]).map(item => (
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
    if (Array.isArray(value) && value.length === 2 && value[0]?.format) {
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
