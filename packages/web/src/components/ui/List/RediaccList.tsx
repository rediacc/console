import { forwardRef } from 'react';
import { List, type ListProps } from 'antd';
import { StyledRediaccList } from './RediaccList.styles';
import type { RediaccListProps, ListVariant, ListSize } from './RediaccList.types';

// Styled props for the list component
interface StyledListProps {
  $variant: ListVariant;
  $size: ListSize;
  $split?: boolean;
}

// Using a function component with generics
function RediaccListInner<T>(
  {
    variant = 'default',
    size = 'md',
    split = true,
    dataSource,
    renderItem,
    header,
    footer,
    loading,
    locale,
    rowKey,
    className,
    style,
    'data-testid': dataTestId,
  }: RediaccListProps<T>,
  ref: React.ForwardedRef<HTMLDivElement>
) {
  // Cast to a component that accepts both styled props and List props
  const ListComponent = StyledRediaccList as React.ComponentType<
    ListProps<T> & StyledListProps & { ref?: React.ForwardedRef<HTMLDivElement> }
  >;
  return (
    <ListComponent
      ref={ref}
      $variant={variant}
      $size={size}
      $split={split}
      split={split}
      dataSource={dataSource}
      renderItem={renderItem}
      header={header}
      footer={footer}
      loading={loading}
      locale={locale}
      rowKey={rowKey}
      className={className}
      style={style}
      data-testid={dataTestId}
    />
  );
}

// Export with forwardRef - note: this loses generic inference
type RediaccListComponent = <T>(
  props: RediaccListProps<T> & { ref?: React.Ref<HTMLDivElement> }
) => React.ReactElement;

interface RediaccListStatics {
  Item: typeof List.Item;
}

export const RediaccList = forwardRef(RediaccListInner) as unknown as RediaccListComponent &
  RediaccListStatics;

// Attach List.Item as a static property
RediaccList.Item = List.Item;

(RediaccList as React.FC).displayName = 'RediaccList';
