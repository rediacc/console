/**
 * Shared Styled Components
 *
 * Consolidated styled components to reduce duplication across pages.
 * Import from '@/components/common/styled' instead of defining in page styles.
 */

import type { ComponentType } from 'react';
import { Table } from 'antd';
import styled from 'styled-components';
import { RediaccButton, RediaccSelect, RediaccStack } from '@/components/ui';
import type { StatusVariant } from '@/styles/primitives';
import type { TableProps } from 'antd';

/**
 * Stack layout with vertical direction, large gap, and full width.
 * Use this for main content sections.
 */
export const ContentStack = styled(RediaccStack).attrs({
  variant: 'spaced-column',
  fullWidth: true,
})``;

// =============================================================================
// SPACING TYPES
// =============================================================================

export type SpacingSize = 'XS' | 'SM' | 'MD' | 'LG' | 'XL';

// =============================================================================
// CENTERED/EMPTY STATE COMPONENTS
// =============================================================================

export interface CenteredStateProps {
  /** Vertical padding size */
  $padding?: SpacingSize;
  /** Show secondary text color */
  $muted?: boolean;
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
`;

// =============================================================================
// STAT DISPLAY COMPONENTS
// =============================================================================
// NOTE: StatLabel, StatValue, and related types have been moved to @/styles/primitives
// to consolidate shared components. Import from there instead.

/**
 * Row for displaying stat label and value
 */
export const StatRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
`;

// =============================================================================
// LAYOUT COMPONENTS
// =============================================================================

export interface HeaderRowProps {
  /** Vertical alignment */
  $align?: 'flex-start' | 'center' | 'flex-end';
  /** Gap between items */
  $spacing?: SpacingSize;
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
`;

/**
 * Flex container with space-between
 */
export const FlexBetween = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export interface ActionsRowProps {
  /** Gap between buttons */
  $spacing?: 'SM' | 'MD';
  /** Alignment */
  $justify?: 'flex-start' | 'flex-end' | 'center';
}

/**
 * Row of action buttons
 */
export const ActionsRow = styled.div<ActionsRowProps>`
  display: flex;
  gap: ${({ $spacing = 'SM', theme }) => theme.spacing[$spacing]}px;
  flex-wrap: wrap;
  justify-content: ${({ $justify = 'flex-end' }) => $justify};
`;

/**
 * Action group for button groups (flex wrap with SM gap)
 */
export const ActionGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: center;
`;

/**
 * Container for action buttons in table cells
 */
export const ActionsContainer = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export interface HeaderSectionProps {
  /** Bottom margin */
  $margin?: 'MD' | 'LG';
}

/**
 * Section header with title and controls
 */
export const HeaderSection = styled.div<HeaderSectionProps>`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ $margin = 'LG', theme }) => theme.spacing[$margin]}px;
`;

export const InlineStack = styled.div<{ $align?: 'flex-start' | 'center' | 'flex-end' }>`
  display: inline-flex;
  align-items: ${({ $align = 'center' }) => $align};
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
`;

const BaseTable = Table as ComponentType<TableProps<unknown>>;

export const DataTable = styled(BaseTable)<{ $isLoading?: boolean }>`
  .ant-spin-nested-loading {
    opacity: ${({ $isLoading }) => ($isLoading ? 0.65 : 1)};
    transition: ${({ theme }) => theme.transitions.DEFAULT};
  }
`;

// =============================================================================
// ACTION BUTTON VARIANTS
// =============================================================================

export interface TableActionButtonProps {
  /** Include gap for label */
  $hasLabel?: boolean;
}

/**
 * Action button for table cells
 *
 * @example
 * <TableActionButton icon={<EditOutlined />} />
 */
export const TableActionButton = styled(RediaccButton).attrs<TableActionButtonProps>((props) => ({
  iconOnly: !props.$hasLabel,
}))<TableActionButtonProps>`
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
`;

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
`;

export const StatusDot = styled.span<{ $variant?: StatusVariant }>`
  width: ${({ theme }) => theme.spacing.SM}px;
  height: ${({ theme }) => theme.spacing.SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  background-color: ${({ theme, $variant = 'info' }) => {
    const colorKey = $variant in theme.colors ? ($variant as keyof typeof theme.colors) : 'info';
    return theme.colors[colorKey];
  }};
  flex-shrink: 0;
`;

// =============================================================================
// STATUS ICON COMPONENTS
// =============================================================================

export type StatusIconVariant =
  | 'success'
  | 'error'
  | 'warning'
  | 'info'
  | 'default'
  | 'online'
  | 'offline'
  | 'unknown'
  | 'testing'
  | 'pending'
  | 'failed';

export interface StatusIconProps {
  /** Status variant - determines color */
  $status?: StatusIconVariant;
  /** Legacy variant prop (maps to $status) */
  $variant?: StatusIconVariant;
  /** Direct color override (use when status variants don't fit) */
  $color?: string;
  /** Icon size - defaults to ICON_SM */
  $size?: 'SM' | 'MD' | 'LG' | number;
}

/**
 * Status icon for displaying status indicators with appropriate colors
 *
 * @example
 * // Using status variant
 * <StatusIcon $status="success"><CheckCircleFilled /></StatusIcon>
 *
 * @example
 * // Using direct color
 * <StatusIcon $color={theme.colors.primary}><InfoCircleFilled /></StatusIcon>
 *
 * @example
 * // Custom size
 * <StatusIcon $status="error" $size="LG"><CloseCircleFilled /></StatusIcon>
 */
export const StatusIcon = styled.span<StatusIconProps>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme, $size = 'SM' }) => {
    if (typeof $size === 'number') {
      return `${$size}px`;
    }
    return `${theme.dimensions[`ICON_${$size}`]}px`;
  }};
  color: ${({ theme, $status, $variant, $color }) => {
    if ($color) {
      return $color;
    }

    // Support both $status and $variant for backwards compatibility
    const status = $status || $variant;

    switch (status) {
      case 'success':
      case 'online':
        return theme.colors.success;
      case 'error':
      case 'failed':
        return theme.colors.error;
      case 'warning':
        return theme.colors.warning;
      case 'info':
      case 'testing':
        return theme.colors.primary;
      case 'offline':
        return theme.colors.textTertiary;
      case 'unknown':
        return theme.colors.textTertiary;
      case 'pending':
      default:
        return theme.colors.textSecondary;
    }
  }};

  .anticon {
    font-size: ${({ theme, $size = 'SM' }) => {
      if (typeof $size === 'number') {
        return `${$size}px`;
      }
      // For child icons, use LG size by default for better visibility
      return `${theme.fontSize.LG}px`;
    }};
  }
`;

// =============================================================================
// FORM COMPONENTS
// =============================================================================

export interface ModalSelectProps {
  /** Use smaller height variant */
  $compact?: boolean;
}

/**
 * Styled Select for use in modals with proper theming
 *
 * @example
 * <ModalSelect $compact>
 *   <Select.Option value="1">Option 1</Select.Option>
 * </ModalSelect>
 */
export const ModalSelect = styled(RediaccSelect).attrs<ModalSelectProps>((props) => ({
  size: props.$compact ? 'sm' : 'md',
  fullWidth: true,
}))<ModalSelectProps>``;

// =============================================================================
// RE-EXPORTS FROM PRIMITIVES AND UI COMPONENTS
// =============================================================================

export type { StatusVariant } from '@/styles/primitives';
// Re-export commonly used primitives for convenience
export {
  ActionBar,
  ContentSection,
  PageCard,
  PageContainer,
  SectionHeaderRow,
} from '@/styles/primitives';
