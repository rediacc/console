import React from 'react';
import { Spin, Empty } from 'antd';
import styled from 'styled-components';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

const CenteredContainer = styled.div<{ $minHeight?: number }>`
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: ${({ $minHeight }) => $minHeight || 200}px;
  padding: ${DESIGN_TOKENS.SPACING.LG}px;
  gap: ${DESIGN_TOKENS.SPACING.SM}px;
`;

const FullHeightContainer = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100%;
  width: 100%;
  gap: ${DESIGN_TOKENS.SPACING.SM}px;
`;

const LoadingText = styled.div`
  margin-top: ${DESIGN_TOKENS.SPACING.SM}px;
  color: var(--color-text-secondary);
  text-align: center;
`;

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
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyMessage || emptyDescription} />
    );
  }

  return <>{children}</>;
};

export { LoadingWrapper };
export default LoadingWrapper;
