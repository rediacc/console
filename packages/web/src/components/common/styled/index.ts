/**
 * Shared Styled Components
 *
 * Consolidated styled components to reduce duplication across pages.
 * Import from '@/components/common/styled' instead of defining in page styles.
 */

import styled from 'styled-components'
import { Space, Typography, Table } from 'antd'
import type { TableProps } from 'antd'
import type { ComponentType } from 'react'
import { IconButton } from '@/styles/primitives'
import type { StatusVariant } from '@/styles/primitives'

const { Text } = Typography

// =============================================================================
// SPACING TYPES
// =============================================================================

export type SpacingSize = 'XS' | 'SM' | 'MD' | 'LG' | 'XL'

// =============================================================================
// CENTERED/EMPTY STATE COMPONENTS
// =============================================================================

export interface CenteredStateProps {
  /** Vertical padding size */
  $padding?: SpacingSize
  /** Show secondary text color */
  $muted?: boolean
}

/**
 * Centered state for empty tables, loading states, etc.
 *
 * @example
 * <CenteredState $padding="LG" $muted>
 *   <Empty description="No data" />
 * </CenteredState>
 */
export const CenteredState = styled.div<CenteredStateProps>`
  width: 100%;
  text-align: center;
  padding: ${({ $padding = 'LG', theme }) => theme.spacing[$padding]}px 0;
  ${({ $muted, theme }) => $muted && `color: ${theme.colors.textSecondary};`}
`

/**
 * Empty state wrapper - alias for CenteredState
 */
export const EmptyState = styled(CenteredState)``

// =============================================================================
// STAT DISPLAY COMPONENTS
// =============================================================================

export type StatVariant = 'default' | 'success' | 'warning' | 'error' | 'info'

export interface StatLabelProps {
  /** Font size */
  $size?: 'XS' | 'SM' | 'BASE'
}

/**
 * Label for stat values (e.g., "Total Items", "Active")
 */
export const StatLabel = styled(Text)<StatLabelProps>`
  && {
    font-size: ${({ $size = 'SM', theme }) => {
      const sizes = { XS: theme.fontSize.XS, SM: theme.fontSize.CAPTION, BASE: theme.fontSize.SM }
      return `${sizes[$size]}px`
    }};
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export interface StatValueProps {
  /** Color variant based on status */
  $variant?: StatVariant
  /** Custom color (overrides variant) */
  $color?: string
  /** Font size */
  $size?: 'SM' | 'BASE' | 'LG' | 'XL'
}

/**
 * Value display for stats with color variants
 *
 * @example
 * <StatValue $variant="success" $size="LG">42</StatValue>
 */
export const StatValue = styled(Text)<StatValueProps>`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    font-size: ${({ $size = 'LG', theme }) => {
      const sizes = { SM: theme.fontSize.SM, BASE: theme.fontSize.BASE, LG: theme.fontSize.LG, XL: theme.fontSize.XL }
      return `${sizes[$size]}px`
    }};
    color: ${({ $color, $variant = 'default', theme }) => {
      if ($color) return $color
      switch ($variant) {
        case 'success': return theme.colors.success
        case 'warning': return theme.colors.warning
        case 'error': return theme.colors.error
        case 'info': return theme.colors.info
        default: return theme.colors.textPrimary
      }
    }};
  }
`

/**
 * Row for displaying stat label and value
 */
export const StatRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
`

// =============================================================================
// LAYOUT COMPONENTS
// =============================================================================

export interface HeaderRowProps {
  /** Vertical alignment */
  $align?: 'flex-start' | 'center' | 'flex-end'
  /** Gap between items */
  $spacing?: SpacingSize
}

/**
 * Header row with space-between layout
 *
 * @example
 * <HeaderRow $align="center" $spacing="MD">
 *   <Title>Page Title</Title>
 *   <ButtonGroup>...</ButtonGroup>
 * </HeaderRow>
 */
export const HeaderRow = styled.div<HeaderRowProps>`
  display: flex;
  align-items: ${({ $align = 'center' }) => $align};
  justify-content: space-between;
  flex-wrap: wrap;
  gap: ${({ $spacing = 'MD', theme }) => theme.spacing[$spacing]}px;
`

/**
 * Flex container with space-between
 */
export const FlexBetween = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export interface ActionsRowProps {
  /** Gap between buttons */
  $spacing?: 'SM' | 'MD'
  /** Alignment */
  $justify?: 'flex-start' | 'flex-end' | 'center'
}

/**
 * Row of action buttons
 */
export const ActionsRow = styled.div<ActionsRowProps>`
  display: flex;
  gap: ${({ $spacing = 'SM', theme }) => theme.spacing[$spacing]}px;
  flex-wrap: wrap;
  justify-content: ${({ $justify = 'flex-end' }) => $justify};
`

/**
 * Container for action buttons in table cells
 */
export const ActionsContainer = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export interface HeaderSectionProps {
  /** Bottom margin */
  $margin?: 'MD' | 'LG'
}

/**
 * Section header with title and controls
 */
export const HeaderSection = styled.div<HeaderSectionProps>`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ $margin = 'LG', theme }) => theme.spacing[$margin]}px;
`

/**
 * Content stack using antd Space
 */
export const ContentStack = styled(Space).attrs({ orientation: 'vertical', size: 'large' })`
  width: 100%;
`

export const InlineStack = styled.div<{ $align?: 'flex-start' | 'center' | 'flex-end' }>`
  display: inline-flex;
  align-items: ${({ $align = 'center' }) => $align};
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
`

const BaseTable = Table as ComponentType<TableProps<unknown>>

export const DataTable = styled(BaseTable)<{ $isLoading?: boolean }>`
  .ant-spin-nested-loading {
    opacity: ${({ $isLoading }) => ($isLoading ? 0.65 : 1)};
    transition: ${({ theme }) => theme.transitions.DEFAULT};
  }
`

// =============================================================================
// ACTION BUTTON VARIANTS
// =============================================================================

export interface TableActionButtonProps {
  /** Include gap for label */
  $hasLabel?: boolean
}

/**
 * Action button for table cells
 *
 * @example
 * <TableActionButton icon={<EditOutlined />} />
 */
export const TableActionButton = styled(IconButton)<TableActionButtonProps>`
  && {
    ${({ $hasLabel, theme }) =>
      $hasLabel
        ? `
      min-width: ${theme.dimensions.CONTROL_HEIGHT}px;
      padding: 0 ${theme.spacing.SM}px;
      gap: ${theme.spacing.XS}px;
    `
        : `
      width: ${theme.dimensions.CONTROL_HEIGHT}px;
    `}
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  }
`

// =============================================================================
// DIVIDERS
// =============================================================================

/**
 * Horizontal divider line
 */
export const Divider = styled.hr`
  border: none;
  height: 1px;
  width: 100%;
  background-color: ${({ theme }) => theme.colors.borderSecondary};
  margin: ${({ theme }) => theme.spacing.MD}px 0;
`

export const StatusDot = styled.span<{ $variant?: StatusVariant }>`
  width: 8px;
  height: 8px;
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  background-color: ${({ theme, $variant = 'info' }) => {
    const colorKey = $variant in theme.colors ? ($variant as keyof typeof theme.colors) : 'info'
    return theme.colors[colorKey]
  }};
  flex-shrink: 0;
`

// =============================================================================
// RE-EXPORTS FROM PRIMITIVES
// =============================================================================

// Re-export commonly used primitives for convenience
export {
  PageContainer,
  PageCard,
  ContentSection,
  ActionButton,
  IconButton,
  SectionHeaderRow,
  ActionBar,
  StatusBadge,
  StatusTag,
} from '@/styles/primitives'

export type { StatusVariant } from '@/styles/primitives'
