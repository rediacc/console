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
// TABLE WRAPPER
// ============================================

/**
 * Table wrapper with bordered card styling and overflow handling
 */
export const TableWrapper = styled.div<{ $variant?: TableVariant }>`
  ${() => borderedCard()}
  overflow: hidden;
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
  }

  /* Header styling */
  .ant-table-thead > tr > th {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    padding: ${({ theme, $size }) => {
      const config = SIZE_CONFIG[$size];
      return `${theme.spacing[config.headerPadding]}px`;
    }};
  }

  /* Cell styling */
  .ant-table-tbody > tr > td {
    padding: ${({ theme, $size }) => {
      const config = SIZE_CONFIG[$size];
      return `${theme.spacing[config.cellPadding]}px`;
    }};
  }

  /* Loading state - reduced opacity during data fetching */
  .ant-spin-nested-loading {
  }

  /* Interactive row styles - hover and click */
  ${({ $interactive }) =>
    $interactive &&
    css`
      .ant-table-tbody > tr {
        cursor: pointer;
      }
    `}

  /* Selection state styles */
  ${({ $selectable }) =>
    $selectable &&
    css`
      .ant-table-tbody > tr.ant-table-row-selected > td {
      }

      .ant-table-tbody > tr.ant-table-row-selected:hover > td {
      }
    `}

  /* Remove margins for nested tables */
  ${({ $removeMargins }) =>
    $removeMargins &&
    css`
      .ant-table.ant-table-small {
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

      .ant-pagination-total-text {
        flex-basis: 100%;
        text-align: center;
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

/**
 * Table cell content wrapper with inline-flex alignment
 */
export const TableCellContent = styled.span`
  display: inline-flex;
  align-items: center;
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
`;

/**
 * Table actions cell container
 */
export const TableActionsCell = styled.div`
  display: inline-flex;
  align-items: center;
`;

// ============================================
// LOADING OVERLAY
// ============================================

/**
 * Loading overlay for table containers
 */
export const TableLoadingOverlay = styled.div`
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: ${({ theme }) => theme.zIndex.OVERLAY};
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
