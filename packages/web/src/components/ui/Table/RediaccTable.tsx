import { forwardRef } from 'react';
import { StyledRediaccTable, TableWrapper } from './RediaccTable.styles';
import type { RediaccTableProps } from './RediaccTable.types';

/**
 * RediaccTable - Unified table component with consistent styling
 *
 * Features:
 * - Variant styles: default, bordered, compact
 * - Size options: sm, md, lg
 * - Interactive row hover/click states
 * - Loading state with opacity transition
 * - Selection highlighting
 * - Mobile responsiveness
 * - Nested table margin removal
 *
 * @example
 * ```tsx
 * <RediaccTable
 *   dataSource={data}
 *   columns={columns}
 *   interactive
 *   selectable
 *   size="md"
 * />
 * ```
 */
export const RediaccTable = forwardRef<HTMLDivElement, RediaccTableProps>(
  (
    {
      variant = 'default',
      size = 'md',
      interactive = false,
      isLoading = false,
      selectable = false,
      removeMargins = false,
      wrapperClassName,
      'data-testid': testId,
      ...tableProps
    },
    ref
  ) => {
    return (
      <TableWrapper
        ref={ref}
        $variant={variant}
        className={wrapperClassName}
        data-testid={testId}
      >
        <StyledRediaccTable
          $variant={variant}
          $size={size}
          $interactive={interactive}
          $isLoading={isLoading}
          $selectable={selectable}
          $removeMargins={removeMargins}
          {...tableProps}
        />
      </TableWrapper>
    );
  }
);

RediaccTable.displayName = 'RediaccTable';
