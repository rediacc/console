import type { JSX, Ref } from 'react';
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
 * <RediaccTable<MyDataType>
 *   dataSource={data}
 *   columns={columns}
 *   interactive
 *   selectable
 *   size="md"
 * />
 * ```
 */
function RediaccTableInner<T extends object = object>(
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
  }: RediaccTableProps<T>,
  ref: Ref<HTMLDivElement>
) {
  return (
    <TableWrapper ref={ref} $variant={variant} className={wrapperClassName} data-testid={testId}>
      <StyledRediaccTable
        $variant={variant}
        $size={size}
        $interactive={interactive}
        $isLoading={isLoading}
        $selectable={selectable}
        $removeMargins={removeMargins}
        {...(tableProps as Record<string, unknown>)}
      />
    </TableWrapper>
  );
}

// Export with generic support using type assertion
export const RediaccTable = RediaccTableInner as <T extends object = object>(
  props: RediaccTableProps<T> & { ref?: Ref<HTMLDivElement> }
) => JSX.Element;
