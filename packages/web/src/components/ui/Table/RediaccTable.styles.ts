import type { ComponentType } from 'react';
import { Table as AntTable } from 'antd';
import styled, { css } from 'styled-components';
import { borderedCard, media } from '@/styles/mixins';
import type { StyledTheme } from '@/styles/styledTheme';
import type { StyledTableProps, TableSize, TableVariant } from './RediaccTable.types';
import type { TableProps } from 'antd';

// ============================================
// SIZE CONFIGURATION
// ============================================

type SizeConfig = {
  cellPadding: keyof StyledTheme['spacing'];
  headerPadding: keyof StyledTheme['spacing'];
};

const SIZE_CONFIG: Record<TableSize, SizeConfig> = {
  sm: { cellPadding: 'SM', headerPadding: 'SM' },
  md: { cellPadding: 'SM_LG', headerPadding: 'SM_LG' },
  lg: { cellPadding: 'MD', headerPadding: 'MD' },
};

// ============================================
// VARIANT CONFIGURATION
// ============================================

type VariantConfig = {
  borderColor: 'borderSecondary' | 'borderPrimary';
  headerBg: keyof StyledTheme['colors'];
};

const VARIANT_CONFIG: Record<TableVariant, VariantConfig> = {
  default: { borderColor: 'borderSecondary', headerBg: 'bgSecondary' },
  bordered: { borderColor: 'borderPrimary', headerBg: 'bgSecondary' },
  compact: { borderColor: 'borderSecondary', headerBg: 'bgSecondary' },
};

// ============================================
// TABLE WRAPPER
// ============================================

/**
 * Table wrapper with bordered card styling and overflow handling
 */
export const TableWrapper = styled.div<{ $variant?: TableVariant }>`
  ${({ $variant = 'default' }) => borderedCard(VARIANT_CONFIG[$variant].borderColor)}
  overflow: hidden;
  background: ${({ theme }) => theme.colors.bgPrimary};
`;

// ============================================
// MAIN STYLED TABLE
// ============================================

const GenericTable = AntTable as ComponentType<TableProps<unknown>>;

/**
 * Core styled table component with all variant/size/state support
 */
export const StyledRediaccTable = styled(GenericTable)<StyledTableProps>`
  /* Base table background */
  .ant-table {
    background-color: ${({ theme }) => theme.colors.bgPrimary};
    border-radius: inherit;
  }

  /* Header styling */
  .ant-table-thead > tr > th {
    background-color: ${({ theme, $variant }) => theme.colors[VARIANT_CONFIG[$variant].headerBg]};
    color: ${({ theme }) => theme.colors.textSecondary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    padding: ${({ theme, $size }) => {
      const config = SIZE_CONFIG[$size];
      return `${theme.spacing[config.headerPadding]}px`;
    }};
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }

  /* Cell styling */
  .ant-table-tbody > tr > td {
    padding: ${({ theme, $size }) => {
      const config = SIZE_CONFIG[$size];
      return `${theme.spacing[config.cellPadding]}px`;
    }};
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    transition: background-color ${({ theme }) => theme.transitions.FAST};
  }

  /* Loading state - reduced opacity during data fetching */
  .ant-spin-nested-loading {
    opacity: ${({ $isLoading }) => ($isLoading ? 0.65 : 1)};
    transition: opacity ${({ theme }) => theme.transitions.DEFAULT};
  }

  /* Interactive row styles - hover and click */
  ${({ $interactive, theme }) =>
    $interactive &&
    css`
      .ant-table-tbody > tr {
        cursor: pointer;
        transition: background-color ${theme.transitions.HOVER};
      }

      .ant-table-tbody > tr:hover > td {
        background-color: ${theme.colors.bgHover};
      }
    `}

  /* Selection state styles */
  ${({ $selectable, theme }) =>
    $selectable &&
    css`
      .ant-table-tbody > tr.ant-table-row-selected > td {
        background-color: ${theme.colors.primaryBg};
      }

      .ant-table-tbody > tr.ant-table-row-selected:hover > td {
        background-color: ${theme.colors.primaryBg};
      }
    `}

  /* Remove margins for nested tables */
  ${({ $removeMargins }) =>
    $removeMargins &&
    css`
      .ant-table.ant-table-small {
        margin-block: 0;
        margin-inline: 0;
      }
    `}

  /* Mobile responsiveness */
  ${media.mobile`
    -webkit-overflow-scrolling: touch;

    .ant-table-wrapper {
      overflow-x: auto;
    }

    .ant-table-pagination {
      flex-wrap: wrap;
      justify-content: center;
      gap: ${({ theme }) => theme.spacing.SM}px;

      .ant-pagination-total-text {
        flex-basis: 100%;
        text-align: center;
        margin-bottom: ${({ theme }) => theme.spacing.XS}px;
      }
    }
  `}

  /* Compact variant - tighter spacing */
  ${({ $variant, theme }) =>
    $variant === 'compact' &&
    css`
      .ant-table-thead > tr > th,
      .ant-table-tbody > tr > td {
        padding: ${theme.spacing.XS}px ${theme.spacing.SM}px;
      }
    `}
`;

// ============================================
// TABLE CELL PRIMITIVES
// ============================================

type SpacingToken = keyof StyledTheme['spacing'];
type SpacingValue = SpacingToken | number;

const resolveSpacingValue = (
  theme: StyledTheme,
  value?: SpacingValue,
  fallback: SpacingToken = 'SM'
): number => {
  if (typeof value === 'number') return value;
  const token = (value || fallback) as SpacingToken;
  return theme.spacing[token];
};

/**
 * Table cell content wrapper with inline-flex alignment
 */
export const TableCellContent = styled.span<{ $gap?: SpacingValue }>`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
`;

type FontWeightToken = keyof StyledTheme['fontWeight'];

/**
 * Table cell text with optional muted and weight styling
 */
export const TableCellText = styled.span<{
  $muted?: boolean;
  $weight?: FontWeightToken | number;
}>`
  font-weight: ${({ theme, $weight }) => {
    if (typeof $weight === 'number') return $weight;
    return theme.fontWeight[$weight || 'REGULAR'];
  }};
  color: ${({ theme, $muted }) => ($muted ? theme.colors.textSecondary : theme.colors.textPrimary)};
`;

/**
 * Table actions cell container
 */
export const TableActionsCell = styled.div<{ $gap?: SpacingValue }>`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme, $gap }) => resolveSpacingValue(theme, $gap, 'SM')}px;
`;

// ============================================
// LOADING OVERLAY
// ============================================

const withAlpha = (color: string, alphaHex: string) =>
  color.startsWith('#') ? `${color}${alphaHex}` : color;

/**
 * Loading overlay for table containers
 */
export const TableLoadingOverlay = styled.div`
  position: absolute;
  inset: 0;
  background-color: ${({ theme }) => withAlpha(theme.colors.bgPrimary, 'CC')};
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: ${({ theme }) => theme.zIndex.OVERLAY};
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
`;

// ============================================
// EXPANDED ROW CONTAINER
// ============================================

/**
 * Container for expanded row content
 */
export const TableExpandedRowContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px 0;
  position: relative;
`;
