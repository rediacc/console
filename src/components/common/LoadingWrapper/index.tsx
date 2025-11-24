import React from 'react'
import { Spin, Empty } from 'antd'
import styled from 'styled-components'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

const CenteredContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
  padding: ${DESIGN_TOKENS.SPACING.LG}px;
`

const FullHeightContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  width: 100%;
`

export interface LoadingWrapperProps {
  /** Whether content is loading */
  loading: boolean
  /** Content to display when not loading */
  children: React.ReactNode
  /** Whether data is empty after loading */
  isEmpty?: boolean
  /** Custom empty state message */
  emptyMessage?: string
  /** Custom empty state description */
  emptyDescription?: string
  /** Spin size */
  size?: 'small' | 'default' | 'large'
  /** Custom loading tip */
  tip?: string
  /** Whether to center the loading spinner */
  centered?: boolean
  /** Whether to take full height */
  fullHeight?: boolean
  /** Minimum height for loading state */
  minHeight?: number
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
export const LoadingWrapper: React.FC<LoadingWrapperProps> = ({
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
}) => {
  if (loading) {
    if (centered || fullHeight) {
      const Container = fullHeight ? FullHeightContainer : CenteredContainer
      return (
        <Container style={minHeight ? { minHeight } : undefined}>
          <Spin size={size} tip={tip} />
        </Container>
      )
    }
    return <Spin spinning size={size} tip={tip}>{children}</Spin>
  }

  if (isEmpty) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={emptyMessage || emptyDescription}
      />
    )
  }

  return <>{children}</>
}

export default LoadingWrapper
