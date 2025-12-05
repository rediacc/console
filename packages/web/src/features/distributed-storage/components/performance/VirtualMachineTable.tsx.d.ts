declare module 'react-window-infinite-loader' {
  import { Component, ReactElement } from 'react';
  import { FixedSizeList } from 'react-window';

  export interface InfiniteLoaderProps {
    isItemLoaded: (index: number) => boolean;
    itemCount: number;
    loadMoreItems: (startIndex: number, stopIndex: number) => Promise<void> | void;
    minimumBatchSize?: number;
    threshold?: number;
    children: (props: {
      onItemsRendered: (props: { visibleStartIndex: number; visibleStopIndex: number }) => void;
      ref: (ref: FixedSizeList | null) => void;
    }) => ReactElement;
  }

  export default class InfiniteLoader extends Component<InfiniteLoaderProps> {}
}
