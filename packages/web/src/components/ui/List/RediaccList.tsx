import { forwardRef } from 'react';
import { List } from 'antd';
import { StyledRediaccList } from './RediaccList.styles';
import type { RediaccListProps } from './RediaccList.types';

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
    ...rest
  }: RediaccListProps<T>,
  ref: React.Ref<HTMLDivElement>
) {
  return (
    <StyledRediaccList<T>
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
      {...rest}
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
