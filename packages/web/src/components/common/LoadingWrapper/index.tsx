import React from 'react';
import { Empty, Flex, Spin } from 'antd';

const CenteredContainer: React.FC<
  React.HTMLAttributes<HTMLDivElement> & { $minHeight?: number }
> = ({ $minHeight, style, ...props }) => (
  <Flex
    vertical
    justify="center"
    align="center"
    // eslint-disable-next-line no-restricted-syntax
    style={{
      minHeight: $minHeight ?? 200,
      ...style,
    }}
    {...props}
  />
);

const FullHeightContainer: React.FC<React.HTMLAttributes<HTMLDivElement>> = (props) => (
  <Flex vertical justify="center" align="center" className="h-full w-full" {...props} />
);

const LoadingText: React.FC<React.HTMLAttributes<HTMLDivElement>> = (props) => (
  <Flex className="text-center" {...props} />
);

export interface LoadingWrapperProps {
  /** Whether content is loading */
  loading: boolean;
  /** Content to display when not loading */
  children: React.ReactNode;
  /** Whether data is empty after loading */
  isEmpty?: boolean;
  /** Custom empty state message */
  emptyMessage?: string;
  /** Custom empty state description */
  emptyDescription?: string;
  /** Spin size */
  size?: 'small' | 'default' | 'large';
  /** Custom loading tip (text shown next to or below spinner) */
  tip?: string;
  /** Whether to center the loading spinner */
  centered?: boolean;
  /** Whether to take full height */
  fullHeight?: boolean;
  /** Minimum height for loading state */
  minHeight?: number;
  /** Show loading text below spinner (when centered/fullHeight) */
  showTextBelow?: boolean;
  /** Custom data-testid for the loading container */
  'data-testid'?: string;
}

/**
 * Wrapper component for consistent loading state handling.
 *
 * @example
 * // Basic usage
 * <LoadingWrapper loading={isLoading}>
 *   <DataTable data={data} />
 * </LoadingWrapper>
 *
 * @example
 * // With empty state
 * <LoadingWrapper
 *   loading={isLoading}
 *   isEmpty={data.length === 0}
 *   emptyMessage="No items found"
 * >
 *   <DataTable data={data} />
 * </LoadingWrapper>
 *
 * @example
 * // Centered loading
 * <LoadingWrapper loading={isLoading} centered>
 *   <Content />
 * </LoadingWrapper>
 */
const LoadingWrapper: React.FC<LoadingWrapperProps> = ({
  loading,
  children,
  isEmpty = false,
  emptyMessage,
  emptyDescription,
  size = 'default',
  tip,
  centered = false,
  fullHeight = false,
  minHeight,
  showTextBelow = false,
  'data-testid': dataTestId,
}) => {
  if (loading) {
    if (centered || fullHeight) {
      const Container = fullHeight ? FullHeightContainer : CenteredContainer;
      return (
        <Container $minHeight={minHeight} data-testid={dataTestId}>
          <Spin size={size} tip={!showTextBelow ? tip : undefined} />
          {showTextBelow && tip && <LoadingText>{tip}</LoadingText>}
        </Container>
      );
    }
    return (
      <Spin spinning size={size} tip={tip}>
        {children}
      </Spin>
    );
  }

  if (isEmpty) {
    return (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyMessage ?? emptyDescription} />
    );
  }

  return <>{children}</>;
};

export { LoadingWrapper };
export default LoadingWrapper;
