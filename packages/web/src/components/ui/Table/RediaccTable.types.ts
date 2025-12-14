import type { TableProps } from 'antd';

/**
 * Table visual style variants
 * - default: Standard bordered table with card styling
 * - bordered: Enhanced border visibility
 * - compact: Reduced padding for dense data display
 */
export type TableVariant = 'default' | 'bordered' | 'compact';

/**
 * Table size/density options
 * - sm: Small padding (8px)
 * - md: Medium padding (12px) - default
 * - lg: Large padding (16px)
 */
export type TableSize = 'sm' | 'md' | 'lg';

/**
 * RediaccTable component props
 * Extends Ant Design TableProps with additional styling options
 */
export interface RediaccTableProps<T = unknown> extends Omit<TableProps<T>, 'size'> {
  /** Visual style variant */
  variant?: TableVariant;

  /** Row size/density */
  size?: TableSize;

  /** Enable interactive row hover/click styles */
  interactive?: boolean;

  /** Show loading overlay with reduced opacity */
  isLoading?: boolean;

  /** Enable selection highlight for rows */
  selectable?: boolean;

  /** Remove default margins from nested tables */
  removeMargins?: boolean;

  /** Custom wrapper className */
  wrapperClassName?: string;

  /** Test identifier */
  'data-testid'?: string;
}

/**
 * Styled component transient props
 * Prefixed with $ to prevent passing to DOM
 */
export interface StyledTableProps {
  $variant: TableVariant;
  $size: TableSize;
  $interactive?: boolean;
  $isLoading?: boolean;
  $selectable?: boolean;
  $removeMargins?: boolean;
}
